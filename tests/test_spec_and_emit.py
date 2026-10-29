"""One spec, many compilers: these hold the compilers to the spec and the
committed SQL to the compilers."""

from pathlib import Path

import duckdb
import pytest
import sqlglot

from point_in_time_audit.config import POLICIES
from point_in_time_audit.dialects.emit import (
    AUDIT_QUERY_NAMES,
    DIALECTS,
    emit_audit_sql,
    emit_feature_sql,
)
from point_in_time_audit.features.spec import (
    FEATURE_NAMES,
    FEATURES,
    ZERO_WHEN_ABSENT,
    visibility_predicate_text,
)

REPO = Path(__file__).resolve().parents[1]


def test_feature_names_are_unique():
    assert len(set(FEATURE_NAMES)) == len(FEATURE_NAMES)


def test_every_window_feature_declares_a_window():
    for f in FEATURES:
        if f.kind.startswith("window_"):
            assert f.window_days is not None


def test_zero_when_absent_covers_counts_sums_and_status_only():
    for f in FEATURES:
        assert (f.name in ZERO_WHEN_ABSENT) == (
            f.kind in ("window_count", "window_sum", "last_status_eq")
        )


def test_the_point_in_time_predicate_names_both_timestamps():
    text = visibility_predicate_text("point_in_time")
    assert "fact_time" in text and "arrival_time" in text


def test_the_latest_policy_has_no_predicate_at_all():
    assert visibility_predicate_text("latest") == ""


def test_an_unknown_policy_is_an_error_not_a_guess():
    with pytest.raises(ValueError):
        visibility_predicate_text("optimistic")


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("policy", POLICIES)
def test_emitted_feature_sql_parses_under_its_own_dialect(dialect, policy):
    sqlglot.parse_one(emit_feature_sql(dialect, policy), read=dialect)


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("name", AUDIT_QUERY_NAMES)
def test_emitted_audit_sql_parses_under_its_own_dialect(dialect, name):
    sqlglot.parse_one(emit_audit_sql(dialect, name), read=dialect)


@pytest.mark.parametrize("dialect", DIALECTS)
def test_only_the_point_in_time_build_carries_the_arrival_predicate(dialect):
    assert "arrival_time <= p.prediction_time" in emit_feature_sql(dialect, "point_in_time")
    assert "arrival_time <= p.prediction_time" not in emit_feature_sql(dialect, "fact_only")


@pytest.mark.parametrize("dialect", DIALECTS)
def test_the_naive_builds_carry_their_warnings_in_the_header(dialect):
    assert "WARNING" in emit_feature_sql(dialect, "fact_only")
    assert "WARNING" in emit_feature_sql(dialect, "latest")
    assert "WARNING" not in emit_feature_sql(dialect, "point_in_time")


def test_every_committed_sql_file_matches_a_fresh_emission():
    for dialect in DIALECTS:
        for policy in POLICIES:
            path = REPO / "sql" / dialect / f"features_{policy}.sql"
            assert path.read_text() == emit_feature_sql(dialect, policy), path
        for name in AUDIT_QUERY_NAMES:
            path = REPO / "sql" / dialect / f"{name}.sql"
            assert path.read_text() == emit_audit_sql(dialect, name), path


def test_no_committed_sql_file_exists_outside_the_emitted_set():
    expected = {
        f"{d}/features_{p}.sql" for d in DIALECTS for p in POLICIES
    } | {f"{d}/{n}.sql" for d in DIALECTS for n in AUDIT_QUERY_NAMES}
    actual = {
        str(p.relative_to(REPO / "sql")) for p in (REPO / "sql").rglob("*.sql")
    }
    assert actual == expected


@pytest.mark.parametrize("name", AUDIT_QUERY_NAMES)
def test_each_audit_query_returns_rows_on_the_committed_fixture(fixture, name):
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.register("events", fixture.events)
        con.register("predictions", fixture.predictions)
        frame = con.execute(emit_audit_sql("duckdb", name)).df()
    finally:
        con.close()
    assert len(frame) > 0


def test_the_leak_candidates_query_finds_only_unknowable_rows(fixture):
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.register("events", fixture.events)
        con.register("predictions", fixture.predictions)
        frame = con.execute(emit_audit_sql("duckdb", "leak_candidates")).df()
    finally:
        con.close()
    assert (frame["earliest_arrival_after_days"] > 0).all()


def test_an_unknown_dialect_is_refused():
    with pytest.raises(ValueError):
        emit_feature_sql("postgres", "point_in_time")
    with pytest.raises(ValueError):
        emit_audit_sql("postgres", "leak_candidates")


def test_an_unknown_audit_query_name_is_refused():
    with pytest.raises(ValueError):
        emit_audit_sql("duckdb", "nonexistent")
