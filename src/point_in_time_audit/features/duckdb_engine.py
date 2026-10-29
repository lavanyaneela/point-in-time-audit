"""DuckDB execution of the compiled feature SQL.

This engine is one half of the referee pair. It deliberately takes the SQL
route (the exact text committed under sql/duckdb/) rather than wrapping the
Spark build, so a disagreement between engines indicts one compiler instead
of both. Single threaded on purpose: the published numbers are derived from
feature tables both engines agree on, and this engine's determinism is what
makes that agreement byte-checkable.
"""

from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd

from ..dialects.emit import emit_feature_sql
from .spec import FEATURE_NAMES

ROUND_DECIMALS = 6


def build_features_duckdb(events: pd.DataFrame, predictions: pd.DataFrame, policy: str) -> pd.DataFrame:
    """Returns one row per entity with the spec's feature columns, rounded.

    Rounding to six decimals is the agreed comparison grain between engines:
    a float sum is associative in no engine, so both round before anything
    downstream reads the values.
    """
    con = duckdb.connect()
    try:
        con.execute("SET threads TO 1")
        con.register("events", events)
        con.register("predictions", predictions)
        sql = emit_feature_sql("duckdb", policy)
        out = con.execute(sql).df()
    finally:
        con.close()
    out = out.set_index("entity_id").loc[predictions["entity_id"].to_numpy()]
    for name in FEATURE_NAMES:
        out[name] = np.round(out[name].astype(float), ROUND_DECIMALS)
    return out[list(FEATURE_NAMES)].reset_index()
