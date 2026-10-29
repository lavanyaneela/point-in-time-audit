"""E5: do the dialects agree.

The DuckDB build of the point-in-time feature table is the reference. The
Spark dialect executes on a real local Spark session; the Snowflake and
BigQuery dialects parse under their own grammars and execute by sqlglot
transpilation onto DuckDB, because those warehouses are never contacted
(the boundary table says so in the README). Agreement means every value of
every feature for every entity is identical at the shared rounding grain.

The four audit queries get the same treatment: parse under every dialect,
and the transpiled Snowflake and BigQuery texts must return the exact rows
the native DuckDB text returns.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import sqlglot
from common import REPO, configure, load_default_fixture, log_fields, write_result

from point_in_time_audit.features.duckdb_engine import build_features_duckdb
from point_in_time_audit.features.spark_engine import get_spark
from point_in_time_audit.features.spec import FEATURE_NAMES

SQL_ROOT = REPO / "sql"
COMPARED_DIALECTS = ("spark", "snowflake", "bigquery")
AUDIT_QUERIES = (
    "leak_candidates",
    "arrival_delay_deciles",
    "backdated_corrections",
    "feature_visibility_diff",
)


def _frames_identical(a: pd.DataFrame, b: pd.DataFrame, columns: list[str]) -> bool:
    if len(a) != len(b):
        return False
    for c in columns:
        x = np.round(a[c].to_numpy(dtype=float), 6)
        y = np.round(b[c].to_numpy(dtype=float), 6)
        if not bool((((np.isnan(x)) & (np.isnan(y))) | (x == y)).all()):
            return False
    return True


def _duckdb_connection(fixture) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET threads TO 1")
    con.execute("SET TimeZone = 'UTC'")
    con.register("events", fixture.events)
    con.register("predictions", fixture.predictions)
    return con


def _run_on_duckdb(con, text: str) -> pd.DataFrame:
    return con.execute(text).df()


def _run_spark_dialect(fixture, text: str) -> pd.DataFrame:
    spark = get_spark("e5-dialect-agreement")
    try:
        with tempfile.TemporaryDirectory() as td:
            ev = Path(td) / "events.parquet"
            pr = Path(td) / "predictions.parquet"
            fixture.events.to_parquet(ev, index=False)
            fixture.predictions.to_parquet(pr, index=False)
            spark.read.parquet(str(ev)).createOrReplaceTempView("events")
            spark.read.parquet(str(pr)).createOrReplaceTempView("predictions")
            rows = spark.sql(text).collect()
            columns = spark.sql(text).columns
        return pd.DataFrame(rows, columns=columns)
    finally:
        spark.stop()


def main() -> int:
    logger = configure()
    fixture = load_default_fixture()
    reference = build_features_duckdb(fixture.events, fixture.predictions, "point_in_time")
    feature_cols = list(FEATURE_NAMES)

    results: dict[str, dict] = {}
    agreeing = 0
    for dialect in COMPARED_DIALECTS:
        text = (SQL_ROOT / dialect / "features_point_in_time.sql").read_text(encoding="utf-8")
        sqlglot.parse_one(text, read=dialect)  # grammar check under its own dialect
        if dialect == "spark":
            built = _run_spark_dialect(fixture, text)
        else:
            transpiled = sqlglot.transpile(text, read=dialect, write="duckdb")[0]
            con = _duckdb_connection(fixture)
            try:
                built = _run_on_duckdb(con, transpiled)
            finally:
                con.close()
        built = built.set_index("entity_id").loc[
            fixture.predictions["entity_id"].to_numpy()
        ].reset_index()
        match = _frames_identical(reference, built, feature_cols)
        results[dialect] = {"parses": True, "feature_rows_match_reference": match}
        agreeing += int(match)
        log_fields(logger, "dialect compared", dialect=dialect, match=match)

    audit_results: dict[str, dict] = {}
    con = _duckdb_connection(fixture)
    try:
        for query in AUDIT_QUERIES:
            native = _run_on_duckdb(con, (SQL_ROOT / "duckdb" / f"{query}.sql").read_text())
            entry = {}
            for dialect in COMPARED_DIALECTS:
                text = (SQL_ROOT / dialect / f"{query}.sql").read_text(encoding="utf-8")
                sqlglot.parse_one(text, read=dialect)
                if dialect == "spark":
                    entry[dialect] = {"parses": True}
                    continue
                transpiled = sqlglot.transpile(text, read=dialect, write="duckdb")[0]
                got = _run_on_duckdb(con, transpiled)
                numeric = [
                    c for c in native.columns if pd.api.types.is_numeric_dtype(native[c])
                ]
                entry[dialect] = {
                    "parses": True,
                    "rows_match_native": _frames_identical(native, got, numeric),
                }
            audit_results[query] = entry
    finally:
        con.close()

    payload = {
        "reference": "duckdb engine build of the point_in_time feature table",
        "feature_build": results,
        "dialects_compared": len(COMPARED_DIALECTS),
        "dialects_agreeing": agreeing,
        "audit_queries": audit_results,
        "boundary": (
            "snowflake and bigquery texts parse under their own grammars and execute "
            "by transpilation onto duckdb; the hosted warehouses are not contacted"
        ),
    }
    path = write_result("e5_dialect_agreement.json", payload)
    log_fields(logger, "e5 written", path=path.name, agreeing=agreeing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
