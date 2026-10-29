"""The analyzer held to the ground truth corpus case by case, plus the unit
properties the corpus exercises in aggregate."""

from pathlib import Path

import pytest
import yaml

from point_in_time_audit.audit.report import Verdict
from point_in_time_audit.audit.sql_analyzer import analyze_sql_path, analyze_sql_text

REPO = Path(__file__).resolve().parents[1]
CORPUS = REPO / "fixtures" / "leak_corpus"
SPEC = yaml.safe_load((CORPUS / "expected.yaml").read_text())

SQL_CASES = [c for c in SPEC["cases"] if c["file"].endswith(".sql")]


def _expected_exit(case) -> int:
    detectable = SPEC["classes"][case["class"]]["detectable"]
    if case["class"] == "clean_flagged":
        return 1
    if case["expectation"] == "clean":
        return 0
    if case["expectation"] == "refused":
        return 2
    return 1 if detectable else 0


@pytest.mark.parametrize("case", SQL_CASES, ids=[c["file"] for c in SQL_CASES])
def test_each_corpus_case_lands_on_its_declared_exit_code(registry, case):
    report = analyze_sql_path(CORPUS / case["file"], registry)
    assert int(report.exit_code()) == _expected_exit(case)


@pytest.mark.parametrize(
    "case",
    [c for c in SQL_CASES if not SPEC["classes"][c["class"]]["detectable"]],
    ids=lambda c: c["file"],
)
def test_every_relay_case_is_left_uncertified_rather_than_passed_silently(registry, case):
    report = analyze_sql_path(CORPUS / case["file"], registry)
    assert report.infos, (
        "a structurally invisible leak must at least leave an out-of-scope "
        "notice; silence here is certification by omission"
    )


def test_the_corpus_run_produces_findings_at_all(registry):
    """The regression that motivates this test: under a renamed sqlglot
    argument the analyzer saw zero relations in every scope and passed the
    entire corpus by finding nothing. Twenty one of thirty six expectations
    missed, every miss a silent pass."""
    total = 0
    for case in SQL_CASES:
        total += len(analyze_sql_path(CORPUS / case["file"], registry).findings)
    assert total >= len(SQL_CASES) // 2


def test_a_clean_join_earns_an_explicit_ok_finding_not_silence(registry):
    report = analyze_sql_path(CORPUS / "clean/direct_join_on.sql", registry)
    assert [f.verdict for f in report.findings] == [Verdict.OK]


def test_a_predicate_under_an_or_gives_no_guarantee(registry):
    text = """
    SELECT p.entity_id FROM predictions p JOIN events e
    ON e.entity_id = p.entity_id
    WHERE e.fact_time <= p.prediction_time
      AND (e.arrival_time <= p.prediction_time OR e.value > 0)
    """
    report = analyze_sql_text(text, registry)
    assert report.leaks, "an arrival check that only sometimes applies is not a check"


def test_unqualified_columns_resolve_when_exactly_one_table_owns_them(registry):
    text = """
    SELECT p.entity_id FROM predictions p JOIN events e
    ON e.entity_id = p.entity_id
    WHERE fact_time <= prediction_time AND arrival_time <= prediction_time
    """
    report = analyze_sql_text(text, registry)
    assert [f.verdict for f in report.findings] == [Verdict.OK]


def test_ambiguous_unqualified_columns_do_not_resolve_by_guess(registry):
    text = """
    SELECT p.entity_id FROM predictions p
    JOIN events e ON e.entity_id = p.entity_id
    JOIN incidents i ON i.entity_id = p.entity_id
    WHERE entity_id = 1
    """
    report = analyze_sql_text(text, registry)
    assert all(f.verdict == Verdict.NO_TIME_PREDICATE for f in report.findings)


def test_the_wrong_comparand_detail_names_the_offending_predicate(registry):
    report = analyze_sql_path(CORPUS / "wrong_comparand/current_timestamp.sql", registry)
    (finding,) = report.leaks
    assert "CURRENT_TIMESTAMP" in finding.detail.upper()


def test_lineage_survives_across_statements_in_one_file(registry):
    report = analyze_sql_path(CORPUS / "intermediate_table/two_hops.sql", registry)
    (info,) = report.infos
    assert info.event_table == "events"
    assert "not analyzable at table grain" in info.detail


def test_lineage_threads_across_files_when_shared(registry):
    lineage: dict[str, set[str]] = {}
    analyze_sql_text(
        "CREATE TABLE staged AS SELECT entity_id, value FROM events",
        registry,
        lineage=lineage,
    )
    report = analyze_sql_text(
        "SELECT p.entity_id FROM predictions p JOIN staged s ON s.entity_id = p.entity_id",
        registry,
        lineage=lineage,
    )
    assert report.infos and not report.leaks and not report.refusals


def test_an_unregistered_table_with_no_provenance_is_refused(registry):
    report = analyze_sql_path(CORPUS / "refusal/unregistered_table.sql", registry)
    (finding,) = report.refusals
    assert finding.verdict == Verdict.REFUSED_UNREGISTERED
    assert finding.event_table == "mystery_scores"


def test_the_single_timestamp_refusal_names_the_unrepresentable_question(registry):
    report = analyze_sql_path(CORPUS / "refusal/single_timestamp_table.sql", registry)
    (finding,) = report.refusals
    assert finding.verdict == Verdict.REFUSED_NO_ARRIVAL_COLUMN
    assert "unrepresentable" in finding.detail


def test_a_leak_takes_exit_precedence_over_a_refusal(registry):
    report = analyze_sql_path(CORPUS / "refusal/leak_beats_refusal.sql", registry)
    assert report.leaks and report.refusals
    assert int(report.exit_code()) == 1


def test_a_select_with_no_prediction_table_is_out_of_every_scope(registry):
    report = analyze_sql_text("SELECT entity_id, MAX(value) FROM events GROUP BY 1", registry)
    assert not report.findings and not report.infos


def test_the_render_includes_the_exit_code_line(registry):
    report = analyze_sql_path(CORPUS / "clean/direct_join_on.sql", registry)
    assert "exit code: 0 (CLEAN)" in report.render()


def test_the_render_of_an_empty_report_says_so(registry):
    report = analyze_sql_text("SELECT 1", registry)
    assert "no temporal joins" in report.render()


def test_the_repositorys_own_honest_build_is_ok_at_the_visible_scope(registry):
    report = analyze_sql_path(REPO / "sql" / "spark" / "features_point_in_time.sql", registry)
    assert Verdict.OK in [f.verdict for f in report.findings]
    assert not report.leaks


def test_the_repositorys_own_naive_builds_convict_themselves(registry):
    for name in ("features_fact_only.sql", "features_latest.sql"):
        report = analyze_sql_path(REPO / "sql" / "spark" / name, registry)
        assert report.leaks, name
