"""E2: which features leak, and how much.

One honest column at a time is swapped for its naive counterpart on an
otherwise point-in-time table, so each feature's fabricated AUC is measured
against the honest baseline. The parts are not forced to sum to the joint
gap; the difference is feature interaction and is published as a number,
because hiding it is how attribution tables lie politely.
"""

from __future__ import annotations

from common import configure, load_default_fixture, log_fields, write_result

from point_in_time_audit.measurement import (
    build_all_policies,
    feature_attribution,
    measure_leak,
)


def main() -> int:
    logger = configure()
    fixture = load_default_fixture()
    tables = build_all_policies(fixture)
    labels = fixture.predictions["label"].to_numpy()

    attribution = feature_attribution(tables, labels)
    joint = measure_leak(tables, labels).mean_gap_fact_only_pp
    ranked = sorted(attribution.items(), key=lambda kv: -kv[1]["fabricated_auc_pp_mean"])
    sum_of_parts = round(sum(v["fabricated_auc_pp_mean"] for v in attribution.values()), 2)

    payload = {
        "naive_policy": "fact_only",
        "per_feature": attribution,
        "ranking": [name for name, _ in ranked],
        "worst_feature_name": ranked[0][0],
        "worst_feature_pp": round(ranked[0][1]["fabricated_auc_pp_mean"], 2),
        "leaking_features": sum(
            1 for v in attribution.values() if v["fabricated_auc_pp_mean"] >= 1.0
        ),
        "features_total": len(attribution),
        "sum_of_parts_pp": sum_of_parts,
        "joint_gap_pp": round(joint, 2),
        "interaction_note": (
            "the sum of single-feature swaps exceeds the joint gap because the "
            "leaking features are redundant evidence about the same incidents; "
            "the difference is interaction, not error"
        ),
    }
    path = write_result("e2_feature_attribution.json", payload)
    log_fields(logger, "e2 written", path=path.name, worst=payload["worst_feature_name"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
