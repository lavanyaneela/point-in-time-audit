"""As-of semantics on a world small enough to check on paper, plus the
reconstruction of the daylight saving bug the referee pair caught."""

import duckdb
import numpy as np
import pytest

from conftest import tiny_world
from point_in_time_audit.dialects.emit import emit_feature_sql
from point_in_time_audit.eventlog import materialize_times
from point_in_time_audit.features.duckdb_engine import build_features_duckdb


@pytest.fixture(scope="module")
def tiny_tables():
    events, predictions = tiny_world()
    events, predictions = materialize_times(events, predictions)
    return {
        policy: build_features_duckdb(events, predictions, policy).iloc[0]
        for policy in ("latest", "fact_only", "point_in_time")
    }


def test_point_in_time_excludes_the_fact_that_had_not_arrived(tiny_tables):
    assert tiny_tables["point_in_time"]["incident_count_90d"] == 0.0


def test_fact_only_admits_the_fact_that_had_not_arrived(tiny_tables):
    assert tiny_tables["fact_only"]["incident_count_90d"] == 1.0


def test_latest_admits_even_the_fact_from_the_future(tiny_tables):
    assert tiny_tables["latest"]["incident_count_90d"] == 1.0, (
        "the day-12 incident is outside the 90 day window upper bound, so only "
        "the day-8 incident counts even under latest"
    )
    assert tiny_tables["latest"]["incident_severity_max_90d"] == 5.0


def test_the_last_risk_score_differs_by_policy_exactly_as_visibility_says(tiny_tables):
    assert tiny_tables["point_in_time"]["last_risk_score"] == 1.5
    assert tiny_tables["fact_only"]["last_risk_score"] == 1.5
    assert tiny_tables["latest"]["last_risk_score"] == 9.0


def test_a_max_over_nothing_is_null_not_zero(tiny_tables):
    assert np.isnan(tiny_tables["point_in_time"]["incident_severity_max_90d"])


def test_a_count_over_nothing_is_zero(tiny_tables):
    assert tiny_tables["point_in_time"]["incident_count_90d"] == 0.0


def test_the_window_upper_bound_is_inclusive_and_the_lower_bound_is_not():
    events, predictions = tiny_world()
    events.loc[0, ["fact_days", "arrival_days"]] = [10.0, 10.0]  # exactly at prediction
    events.loc[1, ["fact_days", "arrival_days"]] = [-20.0, -19.0]  # exactly window edge
    events.loc[1, "event_type"] = "activity"
    ev, pr = materialize_times(events, predictions)
    row = build_features_duckdb(ev, pr, "point_in_time").iloc[0]
    assert row["activity_count_30d"] == 1.0, (
        "fact exactly at the prediction instant is inside; fact exactly at "
        "prediction minus 30 days is outside, because the lower bound is strict"
    )


def test_last_value_ties_break_on_arrival_then_event_id():
    events, predictions = tiny_world()
    events.loc[4, ["fact_days", "arrival_days"]] = [9.0, 9.8]  # tie on fact with event 3
    ev, pr = materialize_times(events, predictions)
    row = build_features_duckdb(ev, pr, "point_in_time").iloc[0]
    assert row["last_risk_score"] == 9.0, "later arrival wins the fact tie"


def test_an_unknown_policy_is_an_error(fixture):
    with pytest.raises(ValueError):
        build_features_duckdb(fixture.events, fixture.predictions, "hopeful")


def test_output_rows_follow_the_prediction_frame_order(fixture):
    out = build_features_duckdb(fixture.events.head(5000), fixture.predictions, "point_in_time")
    assert out["entity_id"].tolist() == fixture.predictions["entity_id"].tolist()


class TestDaylightSavingReconstruction:
    """The war story, re-run on every verify. INTERVAL 30 DAY on TIMESTAMPTZ
    is calendar arithmetic in the session timezone; under America/New_York
    every window spanning the 2025-03-09 spring forward is one hour short,
    and on the committed world that session silently drops events for 20
    entities. Event 49075 sits 26 minutes inside the lost hour and is worth
    16.59965 of its entity's activity sum. The broken session is
    reconstructed here so the test proving the fix would fail against the
    bug it fixes. The figures were first recorded on the pre-calibration
    world (entity 126, a 5.112007 move) and re-derived when the world was
    recalibrated; the mechanism is identical."""

    ENTITY = 139
    EVENT = 49075
    HONEST_SUM = 87.124111
    BROKEN_SUM = 70.524461

    def _run_under_timezone(self, fixture, tz: str) -> float:
        con = duckdb.connect()
        try:
            con.execute("SET threads TO 1")
            con.execute(f"SET TimeZone = '{tz}'")
            con.register("events", fixture.events)
            con.register("predictions", fixture.predictions)
            out = con.execute(emit_feature_sql("duckdb", "point_in_time")).df()
        finally:
            con.close()
        entity_id = int(fixture.predictions.iloc[self.ENTITY]["entity_id"])
        return float(
            np.round(out.set_index("entity_id").loc[entity_id, "activity_amount_sum_30d"], 6)
        )

    def test_the_fixed_engine_includes_the_dst_hour(self, fixture):
        assert self._run_under_timezone(fixture, "UTC") == self.HONEST_SUM

    def test_the_broken_session_reproduces_the_miss_exactly(self, fixture):
        assert self._run_under_timezone(fixture, "America/New_York") == self.BROKEN_SUM

    def test_the_dropped_event_sits_inside_the_spring_forward_hour(self, fixture):
        event = fixture.events.set_index("event_id").loc[self.EVENT]
        prediction = fixture.predictions.iloc[self.ENTITY]
        assert int(event["entity_id"]) == int(prediction["entity_id"])
        gap_days = float(event["fact_days"] - (prediction["prediction_days"] - 30.0))
        assert 0.0 < gap_days < (1.0 / 24.0), (
            "the event is inside the one hour the naive window loses"
        )
        assert round(self.HONEST_SUM - self.BROKEN_SUM, 6) == round(float(event["value"]), 6)
