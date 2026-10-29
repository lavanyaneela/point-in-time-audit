"""The committed experiment outputs held consistent with each other and with
the corpus, so a stale JSON cannot sit quietly next to fresh code."""

import json
from pathlib import Path

import numpy as np
import yaml

from point_in_time_audit.config import GeneratorConfig

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "experiments"


def _load(name):
    return json.loads((OUT / name).read_text())


def test_every_output_names_the_config_that_produced_it():
    expected = GeneratorConfig().config_hash()
    for path in sorted(OUT.glob("*.json")):
        assert json.loads(path.read_text())["generator_config_sha256"] == expected, path.name


def test_e1_means_are_the_means_of_their_published_lists():
    e1 = _load("e1_leak_measurement.json")
    assert e1["gap_fact_only_pp_mean"] == round(float(np.mean(e1["gap_fact_only_pp"])), 2)
    assert e1["gap_latest_pp_mean"] == round(float(np.mean(e1["gap_latest_pp"])), 2)
    for policy, values in e1["auc_by_policy"].items():
        assert e1["auc_mean"][policy] == round(float(np.mean(values)), 4)


def test_e1_counts_match_the_fixture_manifest(fixture):
    e1 = _load("e1_leak_measurement.json")
    assert e1["events_total"] == fixture.manifest["events_total"]
    assert e1["entities_total"] == fixture.manifest["entities_total"]
    assert e1["positives_total"] == fixture.manifest["positives_total"]


def test_e1_and_e4_agree_at_the_default_delay_point():
    e1 = _load("e1_leak_measurement.json")
    e4 = _load("e4_delay_sweep.json")
    default_point = next(
        p for p in e4["points"] if p["incident_delay_median_days"] == 30.0
    )
    assert default_point["gap_pp_mean"] == e1["gap_fact_only_pp_mean"], (
        "the sweep's 30 day point regenerates the committed world and must "
        "reproduce E1 at the published precision; a difference there means "
        "a seed or a config drifted"
    )


def test_e2_worst_feature_leads_its_own_ranking():
    e2 = _load("e2_feature_attribution.json")
    assert e2["ranking"][0] == e2["worst_feature_name"]
    assert (
        e2["per_feature"][e2["worst_feature_name"]]["fabricated_auc_pp_mean"]
        == max(v["fabricated_auc_pp_mean"] for v in e2["per_feature"].values())
    )


def test_e2_interaction_is_published_not_hidden():
    e2 = _load("e2_feature_attribution.json")
    assert e2["sum_of_parts_pp"] != e2["joint_gap_pp"]
    assert "interaction" in e2["interaction_note"]


def test_e3_counts_reconcile_with_the_corpus_spec():
    e3 = _load("e3_analyzer_detection.json")
    spec = yaml.safe_load((REPO / "fixtures" / "leak_corpus" / "expected.yaml").read_text())
    assert e3["corpus_cases_total"] == len(spec["cases"])
    leak_cases = [c for c in spec["cases"] if c["expectation"] == "leak"]
    assert e3["leak_cases_total"] == len(leak_cases)
    assert e3["undetectable_classes_total"] == len(e3["undetectable_classes"])
    assert e3["leak_cases_detected"] == e3["direct_hits"]


def test_e3_overall_catch_is_the_published_ratio():
    e3 = _load("e3_analyzer_detection.json")
    assert e3["overall_catch_pct"] == round(
        100.0 * e3["leak_cases_detected"] / e3["leak_cases_total"], 1
    )


def test_e4_holds_the_positive_count_constant_across_sweep_points():
    e4 = _load("e4_delay_sweep.json")
    positives = {p["positives_total"] for p in e4["points"]}
    assert len(positives) == 1, (
        "the sweep varies the incident delay and nothing else; a point with "
        "its own positive count is a different world, which is exactly how "
        "the first cut of the zero endpoint shipped before the audit"
    )


def test_e4_gaps_grow_with_delay_and_do_not_vanish_at_zero():
    e4 = _load("e4_delay_sweep.json")
    gaps = [p["gap_pp_mean"] for p in e4["points"]]
    assert gaps == sorted(gaps), "the sweep should be monotone on this world"
    assert e4["gap_at_zero_delay_pp"] > 1.0, (
        "the residual at zero delay is the backdated correction leak"
    )


def test_e5_agreement_count_matches_the_per_dialect_flags():
    e5 = _load("e5_dialect_agreement.json")
    matches = sum(
        1 for d in e5["feature_build"].values() if d["feature_rows_match_reference"]
    )
    assert e5["dialects_agreeing"] == matches
    for entry in e5["audit_queries"].values():
        for dialect, result in entry.items():
            assert result["parses"], dialect
            if "rows_match_reference" in result:
                assert result["rows_match_reference"], dialect
