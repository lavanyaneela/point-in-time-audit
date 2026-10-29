"""PySpark execution of the feature spec, written the way a Databricks job is
written: a chain of named, testable transformations over DataFrames, local
mode, no cluster, no network.

As-of feature construction at scale is a Spark-shaped problem, which is why
this engine exists and is the one the README's pipeline section describes.
The Databricks runtime itself is not exercised and nothing here implies it is
(the boundary table names this). The compiled Spark-dialect SQL is a third,
independent expression of the same spec; E5 runs it through this session's
spark.sql and holds it to the same rows.

Independence from the DuckDB engine is deliberate and total: this engine
works in float days with DataFrame operations, the other executes committed
timestamp SQL. The two representations are exactly interchangeable because
day values are rounded to microsecond-representable precision before the
fixture is written, and the referee tests exist to catch the day that stops
being true.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from .spec import FEATURE_NAMES, FEATURES

ROUND_DECIMALS = 6


def get_spark(app_name: str = "point-in-time-audit") -> SparkSession:
    """A local session configured for determinism: UTC, modest parallelism,
    no UI. Session timezone matters because the fixture's timestamps are UTC
    and a local-zone session silently shifts every predicate by the runner's
    offset."""
    return (
        SparkSession.builder.master("local[2]")
        .appName(app_name)
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )


def visible_events(events: DataFrame, predictions: DataFrame, policy: str) -> DataFrame:
    """The admissibility join: the only thing the three pipelines disagree
    about. The canonical wording of the contract lives in
    features/spec.visibility_predicate_text; this is the same two comparisons
    in DataFrame form, over the float day columns."""
    joined = predictions.join(events, on="entity_id", how="inner")
    if policy == "latest":
        return joined
    if policy == "fact_only":
        return joined.where(F.col("fact_days") <= F.col("prediction_days"))
    if policy == "point_in_time":
        return joined.where(
            (F.col("fact_days") <= F.col("prediction_days"))
            & (F.col("arrival_days") <= F.col("prediction_days"))
        )
    raise ValueError(f"unknown policy: {policy!r}")


def _window_aggregates(visible: DataFrame) -> list[DataFrame]:
    frames = []
    groups: dict[tuple[str, int], list] = {}
    for f in FEATURES:
        if f.kind in ("window_count", "window_sum", "window_max"):
            groups.setdefault((f.event_type, f.window_days), []).append(f)
    for (event_type, days), specs in groups.items():
        windowed = visible.where(
            (F.col("event_type") == event_type)
            & (F.col("fact_days") > F.col("prediction_days") - float(days))
            & (F.col("fact_days") <= F.col("prediction_days"))
        )
        aggs = []
        for f in specs:
            if f.kind == "window_count":
                aggs.append(F.count(F.lit(1)).cast("double").alias(f.name))
            elif f.kind == "window_sum":
                aggs.append(F.sum("value").alias(f.name))
            else:
                aggs.append(F.max("value").alias(f.name))
        frames.append(windowed.groupBy("entity_id").agg(*aggs))
    return frames


def _latest_aggregates(visible: DataFrame) -> list[DataFrame]:
    frames = []
    order = Window.partitionBy("entity_id").orderBy(
        F.col("fact_days").desc(), F.col("arrival_days").desc(), F.col("event_id").desc()
    )
    for f in FEATURES:
        if f.kind == "days_since_last":
            frames.append(
                visible.where(F.col("event_type") == f.event_type)
                .groupBy("entity_id", "prediction_days")
                .agg((F.col("prediction_days") - F.max("fact_days")).alias(f.name))
                .select("entity_id", f.name)
            )
        elif f.kind == "last_value":
            frames.append(
                visible.where(F.col("event_type") == f.event_type)
                .withColumn("rn", F.row_number().over(order))
                .where(F.col("rn") == 1)
                .select("entity_id", F.col("value").alias(f.name))
            )
        elif f.kind == "last_status_eq":
            frames.append(
                visible.where(F.col("event_type") == f.event_type)
                .withColumn("rn", F.row_number().over(order))
                .where(F.col("rn") == 1)
                .select(
                    "entity_id",
                    F.when(F.col("status") == f.status_literal, F.lit(1.0))
                    .otherwise(F.lit(0.0))
                    .alias(f.name),
                )
            )
    return frames


def build_features_spark(
    spark: SparkSession, events: pd.DataFrame, predictions: pd.DataFrame, policy: str
) -> pd.DataFrame:
    """Same contract as the DuckDB engine: one row per entity, spec columns,
    rounded to the shared grain, absent counts and sums as zero, absent
    maxima and latest values as null.

    The frames go through a temporary parquet round trip rather than through
    createDataFrame, because parquet is the interchange both engines already
    trust and it keeps this path independent of pandas-to-Spark conversion
    behaviour across versions.
    """
    with tempfile.TemporaryDirectory() as td:
        ev_path = str(Path(td) / "events.parquet")
        pr_path = str(Path(td) / "predictions.parquet")
        events[
            ["event_id", "entity_id", "event_type", "fact_days", "arrival_days", "value", "status"]
        ].to_parquet(ev_path, index=False)
        predictions[["entity_id", "prediction_days"]].to_parquet(pr_path, index=False)
        ev = spark.read.parquet(ev_path)
        pr = spark.read.parquet(pr_path)

        vis = visible_events(ev, pr, policy)
        base = pr.select("entity_id")
        for frame in _window_aggregates(vis) + _latest_aggregates(vis):
            base = base.join(frame, on="entity_id", how="left")

        fill_zero = {
            f.name: 0.0
            for f in FEATURES
            if f.kind in ("window_count", "window_sum", "last_status_eq")
        }
        base = base.fillna(fill_zero)
        rows = base.select("entity_id", *FEATURE_NAMES).collect()

    out = pd.DataFrame(rows, columns=["entity_id"] + list(FEATURE_NAMES))
    out = out.set_index("entity_id").loc[predictions["entity_id"].to_numpy()]
    for name in FEATURE_NAMES:
        out[name] = np.round(out[name].astype(float), ROUND_DECIMALS)
    return out.reset_index()
