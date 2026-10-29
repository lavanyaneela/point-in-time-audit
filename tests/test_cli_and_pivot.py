"""The exit code contract exercised end to end, and the pivot arithmetic."""

import json
from pathlib import Path

import pytest

from point_in_time_audit.audit.pivot import crossover_intermediate_share
from point_in_time_audit.cli import main

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "fixtures" / "leak_corpus"
REGISTRY = str(REPO / "fixtures" / "schema_registry.yaml")


def test_scan_exits_zero_on_a_clean_file(capsys):
    code = main(["scan", "--sql", str(CORPUS / "clean/direct_join_on.sql"), "--registry", REGISTRY])
    assert code == 0
    assert "CLEAN" in capsys.readouterr().out


def test_scan_exits_one_and_names_the_join_on_a_leak(capsys):
    code = main(
        ["scan", "--sql", str(CORPUS / "fact_only_predicate/classic_on_clause.sql"), "--registry", REGISTRY]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "missing_arrival_predicate" in out and "events" in out


def test_scan_exits_two_when_the_schema_cannot_pose_the_question(capsys):
    code = main(
        ["scan", "--sql", str(CORPUS / "refusal/single_timestamp_table.sql"), "--registry", REGISTRY]
    )
    assert code == 2
    assert "refused_no_arrival_column" in capsys.readouterr().out


def test_scan_walks_directories_and_aggregates(capsys):
    code = main(["scan", "--sql", str(CORPUS / "clean"), "--registry", REGISTRY])
    assert code == 0


def test_scan_takes_dag_directories_too(capsys):
    code = main(
        ["scan", "--dags", str(CORPUS / "dags" / "missing_sensor.py"), "--registry", REGISTRY]
    )
    assert code == 1


def test_a_crash_maps_to_exit_three(capsys):
    code = main(["scan", "--sql", "clean", "--registry", "/nonexistent.yaml"])
    assert code == 3
    assert "tool error" in capsys.readouterr().err


def test_the_debug_escape_hatch_reraises(monkeypatch):
    monkeypatch.setenv("PIT_AUDIT_DEBUG", "1")
    with pytest.raises(FileNotFoundError):
        main(["scan", "--sql", "clean", "--registry", "/nonexistent.yaml"])


def test_measure_exits_one_on_the_committed_fixture(capsys):
    code = main(
        [
            "measure",
            "--fixture",
            str(REPO / "fixtures" / "event_log"),
            "--registry",
            REGISTRY,
            "--seeds",
            "0",
        ]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "fabricated AUC" in out and "leak detected" in out


def test_measure_exits_zero_when_the_threshold_is_above_the_gap(capsys):
    code = main(
        [
            "measure",
            "--fixture",
            str(REPO / "fixtures" / "event_log"),
            "--registry",
            REGISTRY,
            "--seeds",
            "0",
            "--threshold-pp",
            "99",
        ]
    )
    assert code == 0


def test_measure_refuses_when_the_registry_has_no_arrival_column(tmp_path, capsys):
    registry = tmp_path / "registry.yaml"
    registry.write_text(
        "tables:\n"
        "  events:\n"
        "    kind: event\n"
        "    entity_key: entity_id\n"
        "    fact_time_column: fact_time\n"
        "    arrival_time_column: null\n"
        "  predictions:\n"
        "    kind: prediction\n"
        "    entity_key: entity_id\n"
        "    prediction_time_column: prediction_time\n"
    )
    code = main(
        ["measure", "--fixture", str(REPO / "fixtures" / "event_log"), "--registry", str(registry)]
    )
    assert code == 2
    assert "cannot be run, which is the finding" in capsys.readouterr().out


def test_pivot_reads_the_committed_e3_output(capsys):
    code = main(["pivot", "--e3", str(REPO / "docs" / "experiments" / "e3_analyzer_detection.json")])
    assert code == 0
    assert "feature store" in capsys.readouterr().out


def test_pivot_at_full_catch_rate_crosses_at_one_half():
    assert crossover_intermediate_share(1.0) == 0.5


def test_pivot_at_half_catch_rate_is_already_lost():
    assert crossover_intermediate_share(0.5) == 0.0


def test_pivot_clamps_below_half_to_zero():
    assert crossover_intermediate_share(0.3) == 0.0


def test_pivot_rejects_rates_outside_the_unit_interval():
    with pytest.raises(ValueError):
        crossover_intermediate_share(1.2)
    with pytest.raises(ValueError):
        crossover_intermediate_share(-0.1)


def test_pivot_at_zero_catch_rate_is_zero_not_a_division_crash():
    assert crossover_intermediate_share(0.0) == 0.0


def test_the_committed_e3_crossover_matches_the_formula():
    e3 = json.loads(
        (REPO / "docs" / "experiments" / "e3_analyzer_detection.json").read_text()
    )
    assert e3["crossover_intermediate_share"] == round(
        crossover_intermediate_share(e3["direct_catch_rate"]), 4
    )
