"""E4: how much does arrival delay matter.

The committed world's incident delay has a 30 day median. This sweep
regenerates the world at six medians, from zero to sixty days, and
re-measures the fact-only gap at each, with both engines building every
point so no sweep number rests on one engine's opinion.

The zero endpoint is the interesting one: with incident delay removed, the
gap does not go to zero, because the backdated corrections arrive on their
own clock. Whatever remains at zero is the leak class no ingestion speedup
removes, which is the argument for the arrival predicate over faster pipes.
"""

from __future__ import annotations

import numpy as np
from common import configure, log_fields, write_result

from point_in_time_audit.config import DelayConfig, GeneratorConfig
from point_in_time_audit.eventlog import materialize_times
from point_in_time_audit.features.duckdb_engine import build_features_duckdb
from point_in_time_audit.features.spark_engine import build_features_spark, get_spark
from point_in_time_audit.generator import generate_world
from point_in_time_audit.measurement import EngineDisagreement, frames_equal
from point_in_time_audit.modeling import DEFAULT_SEEDS, fit_and_auc

MEDIANS = (0.0, 3.5, 7.0, 14.0, 30.0, 60.0)
POLICIES = ("fact_only", "point_in_time")


def main() -> int:
    logger = configure()
    spark = get_spark("e4-delay-sweep")
    points = []
    try:
        for median in MEDIANS:
            cfg = GeneratorConfig(delays=DelayConfig(incident_median=median))
            events, predictions = materialize_times(*generate_world(cfg))
            labels = predictions["label"].to_numpy()
            tables = {}
            for policy in POLICIES:
                duck = build_features_duckdb(events, predictions, policy)
                sp = build_features_spark(spark, events, predictions, policy)
                bad = frames_equal(duck, sp)
                if bad:
                    raise EngineDisagreement(
                        f"median {median}: engines disagree on {', '.join(bad)}"
                    )
                tables[policy] = duck
            gaps = []
            auc_fact = []
            auc_pit = []
            for seed in DEFAULT_SEEDS:
                a = fit_and_auc(tables["fact_only"], labels, seed)
                b = fit_and_auc(tables["point_in_time"], labels, seed)
                gaps.append(round((a - b) * 100.0, 4))
                auc_fact.append(round(a, 6))
                auc_pit.append(round(b, 6))
            points.append(
                {
                    "incident_delay_median_days": median,
                    "gap_pp": gaps,
                    "gap_pp_mean": round(float(np.mean(gaps)), 2),
                    "auc_fact_only_mean": round(float(np.mean(auc_fact)), 4),
                    "auc_point_in_time_mean": round(float(np.mean(auc_pit)), 4),
                    "positives_total": int(labels.sum()),
                }
            )
            log_fields(
                logger, "sweep point", median=median, gap_pp=points[-1]["gap_pp_mean"]
            )
    finally:
        spark.stop()

    payload = {
        "medians_days": list(MEDIANS),
        "points": points,
        "gap_at_zero_delay_pp": points[0]["gap_pp_mean"],
        "gap_at_default_pp": next(
            p["gap_pp_mean"] for p in points if p["incident_delay_median_days"] == 30.0
        ),
        "residual_note": (
            "the gap at zero incident delay is the backdated correction leak, "
            "which arrives on its own clock and which no ingestion speedup removes"
        ),
        "referee": "both engines built every sweep point; disagreement refuses the sweep",
    }
    path = write_result("e4_delay_sweep.json", payload)
    log_fields(logger, "e4 written", path=path.name, zero=payload["gap_at_zero_delay_pp"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
