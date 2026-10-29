"""Re-measures every published figure and writes docs/metrics.json.

Nothing is typed by hand. The test count and coverage come from machine
readable outputs (junit XML and the coverage JSON), the experiment figures
from the experiment scripts run fresh, and the daylight saving figures from
re-running the broken session against the fixed one. Minimums and the
coverage percentage round down, never to nearest, because a figure published
under the words "at least" must survive its own decimals.

Anchors carried here are the exact wording the documents must use with the
value substituted in. Alternatives are alternatives: one match is enough.
Small numbers are checked only through anchors. check_numbers.py consumes
this file; collect never reads the documents and check never measures.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

OUT = REPO / "docs" / "metrics.json"
EXPERIMENTS = [
    "e1_leak_measurement.py",
    "e2_feature_attribution.py",
    "e3_analyzer_detection.py",
    "e4_delay_sweep.py",
    "e5_dialect_agreement.py",
]

CHECKED_DOCUMENTS = [
    "README.md",
    "docs/defense-guide.md",
    "docs/failure-modes.md",
    "docs/adr/ADR-001-seeded-generator.md",
    "docs/adr/ADR-002-two-engines-as-referees.md",
    "docs/adr/ADR-003-airflow-validated-not-executed.md",
    "docs/adr/ADR-004-analyzer-scope.md",
    "docs/adr/ADR-005-chosen-delays-and-the-boundary.md",
]



# The exact wording the documents use, one entry per published phrasing.
# Every anchor must appear in at least one checked document (the liveness
# gate) and no two metrics may share one, even by containment.
ANCHORS = {
    "tests_total": ["{} tests"],
    "coverage_line_pct": ["{}% line coverage"],
    "events_total": ["{} events"],
    "entities_total": ["{} entities"],
    "positives_total": ["{} positive outcomes"],
    "seeds": ["{} paired splits", "{} seeds", "all {} seeds"],
    "auc_point_in_time": [
        "honest AUC is {}",
        "| point in time | `fact_time <= prediction_time AND arrival_time <= prediction_time` | {} |",
    ],
    "auc_fact_only": [
        "reads {}",
        "an AUC of {}",
        "| fact time only | `fact_time <= prediction_time` | {} |",
    ],
    "auc_latest": ["latest-value join scores {}", "| latest value | none | {} |"],
    "gap_fact_only_pp_mean": [
        "{} points of held-out AUC",
        "{} points of AUC",
        "joint gap of {}",
        "the {} joint gap",
    ],
    "gap_fact_only_pp_min": ["never below {} points"],
    "gap_fact_only_pp_max": ["to {} points across", "points to {}"],
    "gap_latest_pp_mean": ["fabricates {} points"],
    "features_total": ["{} features"],
    "leaking_features": ["{} of them leak"],
    "worst_feature_name": ["worst offender is {}"],
    "worst_feature_pp": ["{} points by itself", "| incident_count_90d | +{} |"],
    "feature_severity_pp": ["| incident_severity_max_90d | +{} |"],
    "feature_status_pp": ["| status_risky | +{} |"],
    "sum_of_parts_pp": ["parts sum to {}"],
    "leaking_parts_pp": ["alone sum to {}"],
    "clean_parts_offset_pp": ["subtract {} points"],
    "corpus_cases_total": ["{} corpus cases"],
    "leak_cases_total": ["the {} leak cases"],
    "leak_cases_detected": ["names {} of"],
    "overall_catch_pct": ["catches {}% of the corpus leak cases"],
    "direct_catch_pct": ["{}% of direct sites"],
    "direct_cases": ["all {} direct"],
    "undetectable_classes_total": [
        "{} leak classes",
        "{} structurally invisible",
        "{} classes it cannot",
    ],
    "undetected_cases": ["{} leak cases invisible", "misses {} cases"],
    "clean_cases": ["{} clean cases"],
    "clean_false_positives": ["{} false positives"],
    "clean_expectation_cases": ["{} cases whose ground"],
    "clean_expectation_flags": ["flags {} of them"],
    "clean_fp_upper_pct": ["below {}% at 95"],
    "clean_flagged_cases": ["{} correct predicates", "flags {} semantically"],
    "crossover_share_pct": ["crossover sits at {}%", "past {}% of temporal"],
    "gap_at_zero_delay_pp": [
        "{} points remain",
        "{} points at zero",
        "from {} to a",
        "| 0 | {} |",
    ],
    "gap_at_seven_delay_pp": ["| 7 | {} |"],
    "gap_at_sixty_delay_pp": ["climbs to {}", "climb to {}", "| 60 | {} |"],
    "dialects_agreeing": ["{} of 3 dialects"],
    "sql_files_total": ["{} committed SQL files"],
    "dst_entities_affected": ["clips {} windows"],
    "dst_first_entity": ["entity {} loses", "entity {} alone"],
    "dst_lost_value": ["worth {} of summed"],
    "dst_minutes_inside": ["{} minutes inside"],
}


def floor_to(value: float, decimals: int) -> float:
    scale = 10**decimals
    return math.floor(value * scale) / scale


def run_suite() -> tuple[int, float]:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--junitxml=junit.xml",
            "--cov=point_in_time_audit",
            "--cov-report=json",
            "-q",
        ],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    )
    suite = ET.parse(REPO / "junit.xml").getroot().find("testsuite")
    collected = int(suite.get("tests"))
    coverage = json.loads((REPO / "coverage.json").read_text())
    return collected, floor_to(coverage["totals"]["percent_covered"], 1)


def run_experiments() -> None:
    for script in EXPERIMENTS:
        subprocess.run(
            [sys.executable, str(REPO / "experiments" / script)],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )


def measure_dst_story() -> dict:
    """Re-measure the daylight saving miss: the fixed UTC session against a
    reconstructed America/New_York session, on the committed fixture."""
    import duckdb

    from point_in_time_audit.config import GeneratorConfig
    from point_in_time_audit.dialects.emit import emit_feature_sql
    from point_in_time_audit.eventlog import load_fixture

    fixture = load_fixture(REPO / "fixtures" / "event_log", GeneratorConfig())

    def build(tz: str):
        con = duckdb.connect()
        try:
            con.execute("SET threads TO 1")
            con.execute(f"SET TimeZone = '{tz}'")
            con.register("events", fixture.events)
            con.register("predictions", fixture.predictions)
            return (
                con.execute(emit_feature_sql("duckdb", "point_in_time"))
                .df()
                .set_index("entity_id")
            )
        finally:
            con.close()

    utc = build("UTC")
    broken = build("America/New_York")
    column = "activity_amount_sum_30d"
    differs = utc[column].round(6) != broken[column].round(6)
    affected = int(differs.fillna(False).sum())
    entity = int(utc.index[differs.fillna(False)][0])
    delta = round(float(utc.loc[entity, column] - broken.loc[entity, column]), 6)

    prediction = fixture.predictions.set_index("entity_id").loc[entity]
    lower = float(prediction["prediction_days"]) - 30.0
    lost = fixture.events[
        (fixture.events["entity_id"] == entity)
        & (fixture.events["event_type"] == "activity")
        & (fixture.events["fact_days"] > lower)
        & (fixture.events["fact_days"] < lower + 1.0 / 24.0)
        & (fixture.events["arrival_days"] <= float(prediction["prediction_days"]))
    ].sort_values("fact_days")
    minutes = round(float((lost.iloc[0]["fact_days"] - lower) * 1440.0), 1)
    return {
        "dst_entities_affected": affected,
        "dst_first_entity": entity,
        "dst_lost_value": delta,
        "dst_minutes_inside": minutes,
    }


def exact_binomial_upper_pct(successes: int, trials: int, confidence: float = 0.95) -> float:
    """Exact upper bound for a measured zero: 1 - alpha^(1/n). Only the
    zero case is needed here; anything else is a bug in the corpus."""
    if successes != 0:
        raise ValueError("this collector only prices measured zeros")
    return round(100.0 * (1.0 - (1.0 - confidence) ** (1.0 / trials)), 1)


def main() -> int:
    collected, coverage_pct = run_suite()
    run_experiments()

    out_dir = REPO / "docs" / "experiments"
    e1 = json.loads((out_dir / "e1_leak_measurement.json").read_text())
    e2 = json.loads((out_dir / "e2_feature_attribution.json").read_text())
    e3 = json.loads((out_dir / "e3_analyzer_detection.json").read_text())
    e4 = json.loads((out_dir / "e4_delay_sweep.json").read_text())
    e5 = json.loads((out_dir / "e5_dialect_agreement.json").read_text())
    dst = measure_dst_story()

    gap_sixty = next(
        p["gap_pp_mean"] for p in e4["points"] if p["incident_delay_median_days"] == 60.0
    )

    metrics = {
        "tests_total": collected,
        "coverage_line_pct": coverage_pct,
        "events_total": e1["events_total"],
        "entities_total": e1["entities_total"],
        "positives_total": e1["positives_total"],
        "seeds": e1["seeds"],
        "auc_point_in_time": e1["auc_mean"]["point_in_time"],
        "auc_fact_only": e1["auc_mean"]["fact_only"],
        "auc_latest": e1["auc_mean"]["latest"],
        "gap_fact_only_pp_mean": e1["gap_fact_only_pp_mean"],
        "gap_fact_only_pp_min": e1["gap_fact_only_pp_min"],
        "gap_fact_only_pp_max": e1["gap_fact_only_pp_max"],
        "gap_latest_pp_mean": e1["gap_latest_pp_mean"],
        "features_total": e2["features_total"],
        "leaking_features": e2["leaking_features"],
        "worst_feature_name": e2["worst_feature_name"],
        "worst_feature_pp": e2["worst_feature_pp"],
        "feature_severity_pp": round(
            e2["per_feature"]["incident_severity_max_90d"]["fabricated_auc_pp_mean"], 2
        ),
        "feature_status_pp": round(
            e2["per_feature"]["status_risky"]["fabricated_auc_pp_mean"], 2
        ),
        "sum_of_parts_pp": e2["sum_of_parts_pp"],
        "leaking_parts_pp": round(
            sum(
                v["fabricated_auc_pp_mean"]
                for v in e2["per_feature"].values()
                if v["fabricated_auc_pp_mean"] >= 1.0
            ),
            2,
        ),
        "clean_parts_offset_pp": round(
            abs(
                e2["sum_of_parts_pp"]
                - sum(
                    v["fabricated_auc_pp_mean"]
                    for v in e2["per_feature"].values()
                    if v["fabricated_auc_pp_mean"] >= 1.0
                )
            ),
            2,
        ),
        "corpus_cases_total": e3["corpus_cases_total"],
        "leak_cases_total": e3["leak_cases_total"],
        "leak_cases_detected": e3["leak_cases_detected"],
        "overall_catch_pct": e3["overall_catch_pct"],
        "direct_catch_pct": e3["direct_catch_pct"],
        "direct_cases": e3["direct_cases"],
        "undetectable_classes_total": e3["undetectable_classes_total"],
        "undetected_cases": e3["undetected_cases"],
        "clean_cases": e3["clean_cases"],
        "clean_false_positives": e3["clean_false_positives"],
        "clean_expectation_cases": e3["clean_expectation_cases"],
        "clean_expectation_flags": e3["clean_expectation_flags"],
        "clean_fp_upper_pct": exact_binomial_upper_pct(
            e3["clean_false_positives"], e3["clean_cases"]
        ),
        "clean_flagged_cases": e3["clean_flagged_cases"],
        "crossover_share_pct": e3["crossover_intermediate_share_pct"],
        "gap_at_zero_delay_pp": e4["gap_at_zero_delay_pp"],
        "gap_at_seven_delay_pp": next(
            p["gap_pp_mean"] for p in e4["points"] if p["incident_delay_median_days"] == 7.0
        ),
        "gap_at_sixty_delay_pp": gap_sixty,
        "dialects_agreeing": e5["dialects_agreeing"],
        "sql_files_total": len(list((REPO / "sql").rglob("*.sql"))),
        **dst,
    }

    anchors = ANCHORS

    missing = [name for name in metrics if name not in anchors]
    if missing:
        raise SystemExit(f"metrics without anchors: {missing}")

    payload = {
        "metrics": metrics,
        "anchors": anchors,
        "checked_documents": CHECKED_DOCUMENTS,
        "note": (
            "every value here is produced by running the suite, the experiments "
            "and the daylight saving reconstruction; nothing is typed by hand"
        ),
    }
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(metrics)} metrics to {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
