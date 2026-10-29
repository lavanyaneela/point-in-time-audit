"""E1: how much performance is fabricated by leakage.

Three pipelines over the same events, differing only in the admissibility
predicate, the same model, the same paired entity splits. The headline is
the fact-only gap, because fact-only is the pipeline that passes code
review; the latest-value gap is reported beside it as the ceiling.

The referee rule runs here for real: features are built by both engines and
the experiment refuses to publish if they disagree on a single value.
"""

from __future__ import annotations

import numpy as np
from common import configure, load_default_fixture, log_fields, write_result

from point_in_time_audit.features.spark_engine import get_spark
from point_in_time_audit.measurement import build_all_policies, measure_leak


def main() -> int:
    logger = configure()
    fixture = load_default_fixture()
    spark = get_spark("e1-leak-measurement")
    try:
        tables = build_all_policies(fixture, spark=spark)
    finally:
        spark.stop()
    log_fields(logger, "features built and referee checked", policies=len(tables))

    labels = fixture.predictions["label"].to_numpy()
    leak = measure_leak(tables, labels)

    payload = {
        "events_total": fixture.manifest["events_total"],
        "entities_total": fixture.manifest["entities_total"],
        "positives_total": fixture.manifest["positives_total"],
        "seeds": len(leak.gap_fact_only_pp),
        "auc_by_policy": {p: v for p, v in leak.aucs.items()},
        "auc_mean": {p: round(float(np.mean(v)), 4) for p, v in leak.aucs.items()},
        "gap_fact_only_pp": leak.gap_fact_only_pp,
        "gap_fact_only_pp_mean": round(leak.mean_gap_fact_only_pp, 2),
        "gap_fact_only_pp_min": round(min(leak.gap_fact_only_pp), 2),
        "gap_fact_only_pp_max": round(max(leak.gap_fact_only_pp), 2),
        "gap_latest_pp": leak.gap_latest_pp,
        "gap_latest_pp_mean": round(leak.mean_gap_latest_pp, 2),
        "referee": "spark and duckdb builds compared value for value before any fit",
    }
    path = write_result("e1_leak_measurement.json", payload)
    log_fields(
        logger,
        "e1 written",
        path=path.name,
        gap_fact_only_pp=payload["gap_fact_only_pp_mean"],
        gap_latest_pp=payload["gap_latest_pp_mean"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
