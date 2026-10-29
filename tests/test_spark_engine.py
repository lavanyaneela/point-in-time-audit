"""The referee suite: the Spark build held to the DuckDB build value for
value, plus the policy filters on the paper-checkable world."""

import numpy as np
import pytest

from conftest import tiny_world
from point_in_time_audit.eventlog import materialize_times
from point_in_time_audit.features.duckdb_engine import build_features_duckdb
from point_in_time_audit.features.spark_engine import build_features_spark
from point_in_time_audit.features.spec import FEATURE_NAMES
from point_in_time_audit.measurement import frames_equal

pytestmark = pytest.mark.spark


@pytest.mark.parametrize("policy", ["latest", "fact_only", "point_in_time"])
def test_both_engines_agree_on_every_value_of_the_committed_fixture(spark, fixture, policy):
    duck = build_features_duckdb(fixture.events, fixture.predictions, policy)
    spk = build_features_spark(spark, fixture.events, fixture.predictions, policy)
    assert frames_equal(duck, spk) == []


def test_the_spark_build_is_identical_across_two_runs(spark, fixture):
    first = build_features_spark(spark, fixture.events, fixture.predictions, "point_in_time")
    second = build_features_spark(spark, fixture.events, fixture.predictions, "point_in_time")
    for name in FEATURE_NAMES:
        x, y = first[name].to_numpy(), second[name].to_numpy()
        assert bool((((np.isnan(x)) & (np.isnan(y))) | (x == y)).all()), name


def test_the_spark_session_runs_in_utc(spark):
    assert spark.conf.get("spark.sql.session.timeZone") == "UTC"


@pytest.mark.parametrize(
    ("policy", "expected_incidents"),
    [("latest", 1.0), ("fact_only", 1.0), ("point_in_time", 0.0)],
)
def test_policy_visibility_on_the_paper_world(spark, policy, expected_incidents):
    events, predictions = materialize_times(*tiny_world())
    row = build_features_spark(spark, events, predictions, policy).iloc[0]
    assert row["incident_count_90d"] == expected_incidents


def test_an_unknown_policy_is_an_error(spark, fixture):
    with pytest.raises(ValueError):
        build_features_spark(spark, fixture.events, fixture.predictions, "wishful")


def test_absent_counts_fill_to_zero_and_absent_maxima_stay_null(spark):
    events, predictions = materialize_times(*tiny_world())
    row = build_features_spark(spark, events, predictions, "point_in_time").iloc[0]
    assert row["incident_count_90d"] == 0.0
    assert np.isnan(row["incident_severity_max_90d"])
