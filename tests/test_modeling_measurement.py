"""Paired evaluation mechanics and the referee rule as code."""

import pytest

from point_in_time_audit.features.spec import FEATURE_NAMES
from point_in_time_audit.measurement import (
    EngineDisagreement,
    build_all_policies,
    feature_attribution,
    frames_equal,
    measure_leak,
)
from point_in_time_audit.modeling import entity_split, fit_and_auc


@pytest.fixture(scope="module")
def tables(fixture):
    return build_all_policies(fixture)


@pytest.fixture(scope="module")
def labels(fixture):
    return fixture.predictions["label"].to_numpy()


def test_entity_split_is_a_pure_function_of_the_seed():
    a = entity_split(1000, 3)
    b = entity_split(1000, 3)
    assert (a[0] == b[0]).all() and (a[1] == b[1]).all()


def test_entity_split_partitions_without_overlap():
    train, test = entity_split(997, 5)
    assert len(set(train) & set(test)) == 0
    assert len(train) + len(test) == 997


def test_entity_split_honours_the_train_fraction():
    train, test = entity_split(1000, 0)
    assert len(train) == 700 and len(test) == 300


def test_a_fit_is_deterministic_under_a_fixed_seed(tables, labels):
    first = fit_and_auc(tables["point_in_time"], labels, seed=0)
    second = fit_and_auc(tables["point_in_time"], labels, seed=0)
    assert first == second


def test_different_seeds_move_the_auc(tables, labels):
    assert fit_and_auc(tables["point_in_time"], labels, 0) != fit_and_auc(
        tables["point_in_time"], labels, 1
    )


def test_frames_equal_treats_matching_nans_as_equal(tables):
    assert frames_equal(tables["point_in_time"], tables["point_in_time"].copy()) == []


def test_frames_equal_names_the_disagreeing_column(tables):
    doctored = tables["point_in_time"].copy()
    doctored.loc[0, "incident_count_90d"] += 1
    assert frames_equal(tables["point_in_time"], doctored) == ["incident_count_90d"]


def test_the_measurement_refuses_on_an_engine_disagreement(fixture, monkeypatch):
    import point_in_time_audit.features.spark_engine as spark_engine
    import point_in_time_audit.measurement as measurement

    def doctored_build(spark, events, predictions, policy):
        frame = measurement.build_features_duckdb(events, predictions, policy)
        frame.loc[0, "incident_count_90d"] += 1
        return frame

    monkeypatch.setattr(spark_engine, "build_features_spark", doctored_build)
    with pytest.raises(EngineDisagreement, match="incident_count_90d"):
        measurement.build_all_policies(fixture, spark=object())


def test_the_gap_is_paired_within_each_seed(tables, labels):
    leak = measure_leak(tables, labels, seeds=(0, 1))
    for i, seed in enumerate((0, 1)):
        a = fit_and_auc(tables["fact_only"], labels, seed)
        b = fit_and_auc(tables["point_in_time"], labels, seed)
        assert leak.gap_fact_only_pp[i] == round((a - b) * 100.0, 4)


def test_the_fabricated_auc_is_positive_on_the_committed_world(tables, labels):
    leak = measure_leak(tables, labels, seeds=(0,))
    assert leak.gap_fact_only_pp[0] > 5.0
    assert leak.gap_latest_pp[0] > leak.gap_fact_only_pp[0]


def test_attribution_counts_the_rows_each_swap_changes(tables, labels):
    attribution = feature_attribution(tables, labels, seeds=(0,))
    assert set(attribution) == set(FEATURE_NAMES)
    for stats in attribution.values():
        assert stats["rows_changed"] >= 0


def test_attribution_finds_the_incident_features_and_spares_the_clean_ones(tables, labels):
    attribution = feature_attribution(tables, labels, seeds=(0, 1))
    assert attribution["incident_count_90d"]["fabricated_auc_pp_mean"] > 3.0
    assert abs(attribution["activity_count_30d"]["fabricated_auc_pp_mean"]) < 1.5, (
        "activity arrives in hours; swapping its naive column should buy nothing"
    )
