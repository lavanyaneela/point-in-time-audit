"""The generator is the ground truth factory; these pin the properties every
published number quietly depends on."""

import numpy as np
import pandas as pd

from point_in_time_audit.config import GeneratorConfig
from point_in_time_audit.generator import generate_world, to_timestamp


def _world():
    return generate_world(GeneratorConfig())


def test_two_runs_of_the_same_config_are_identical():
    e1, p1 = _world()
    e2, p2 = _world()
    pd.testing.assert_frame_equal(e1, e2)
    pd.testing.assert_frame_equal(p1, p2)


def test_event_ids_are_a_contiguous_zero_based_sequence():
    events, _ = _world()
    assert events["event_id"].tolist() == list(range(len(events)))


def test_events_are_sorted_by_arrival_which_is_the_order_a_log_keeps():
    events, _ = _world()
    assert events["arrival_days"].is_monotonic_increasing


def test_every_event_type_the_spec_reads_is_present():
    events, _ = _world()
    assert set(events["event_type"].unique()) == {
        "activity",
        "incident",
        "risk_assessment",
        "status_change",
    }


def test_no_event_arrives_before_it_became_true():
    events, _ = _world()
    assert (events["arrival_days"] >= events["fact_days"]).all()


def test_incident_facts_sit_inside_the_configured_band_around_prediction():
    cfg = GeneratorConfig()
    events, predictions = generate_world(cfg)
    merged = events[events["event_type"] == "incident"].merge(
        predictions[["entity_id", "prediction_days"]], on="entity_id"
    )
    offset = merged["fact_days"] - merged["prediction_days"]
    assert offset.min() >= -cfg.incident_fact_before - 1e-6
    assert offset.max() <= cfg.incident_fact_after + 1e-6


def test_risky_corrections_are_backdated_before_prediction_and_arrive_after():
    events, predictions = generate_world(GeneratorConfig())
    risky = events[(events["event_type"] == "status_change") & (events["status"] == "risky")]
    merged = risky.merge(predictions[["entity_id", "prediction_days"]], on="entity_id")
    assert (merged["fact_days"] <= merged["prediction_days"]).all()
    assert (merged["arrival_days"] > merged["prediction_days"]).all()


def test_some_corrections_fire_wrongly_for_negative_outcomes():
    events, predictions = generate_world(GeneratorConfig())
    risky = events[(events["event_type"] == "status_change") & (events["status"] == "risky")]
    merged = risky.merge(predictions[["entity_id", "label"]], on="entity_id")
    assert (merged["label"] == 0).sum() > 0, (
        "with no false corrections the status feature is a label copy, "
        "which E2 convicted once already"
    )


def test_most_corrections_still_attach_to_positive_outcomes():
    events, predictions = generate_world(GeneratorConfig())
    risky = events[(events["event_type"] == "status_change") & (events["status"] == "risky")]
    merged = risky.merge(predictions[["entity_id", "label"]], on="entity_id")
    assert (merged["label"] == 1).mean() > 0.5


def test_prevalence_sits_in_a_learnable_band():
    _, predictions = _world()
    rate = predictions["label"].mean()
    assert 0.10 < rate < 0.35


def test_every_entity_gets_exactly_one_prediction():
    _, predictions = _world()
    assert predictions["entity_id"].is_unique
    assert len(predictions) == GeneratorConfig().n_entities


def test_prediction_times_sit_inside_the_configured_window():
    cfg = GeneratorConfig()
    _, predictions = generate_world(cfg)
    lo, hi = cfg.prediction_window
    assert predictions["prediction_days"].between(lo, hi).all()


def test_a_zero_delay_median_produces_instant_arrivals_for_incidents():
    from dataclasses import replace

    from point_in_time_audit.config import DelayConfig

    cfg = replace(GeneratorConfig(), delays=DelayConfig(incident_median=0.0))
    events, _ = generate_world(cfg)
    incidents = events[events["event_type"] == "incident"]
    assert np.allclose(incidents["arrival_days"], incidents["fact_days"])


def test_day_values_land_on_exact_microsecond_boundaries():
    days = pd.Series([0.0, 1.5, 71.200296, 119.999999])
    stamps = to_timestamp(days)
    micros = (stamps - pd.Timestamp("2025-01-01", tz="UTC")).dt.total_seconds().mul(1e6)
    want = (days * 86400.0 * 1e6).round()
    assert np.array_equal(micros.round().to_numpy(), want.to_numpy()), (
        "one microsecond per six-decimal day value is the invariant that "
        "keeps timestamp predicates and day predicates equivalent; a day "
        "value that lands between microseconds would let the two SQL "
        "surfaces disagree at exact-equality boundaries"
    )
    ordered = to_timestamp(pd.Series([10.0, 10.000001]))
    assert ordered.iloc[0] < ordered.iloc[1], "adjacent day values stay distinct"


def test_incident_count_rises_with_latent_risk_by_construction():
    cfg = GeneratorConfig()
    rng_check = np.exp(cfg.incident_rate_base + cfg.incident_rate_risk * np.array([-1.0, 1.0]))
    assert rng_check[1] > rng_check[0]


def test_label_depends_on_the_windowed_incident_count():
    events, predictions = generate_world(GeneratorConfig())
    merged = events[events["event_type"] == "incident"].merge(
        predictions[["entity_id", "prediction_days"]], on="entity_id"
    )
    in_window = merged[
        (merged["fact_days"] > merged["prediction_days"] - 90)
        & (merged["fact_days"] <= merged["prediction_days"])
    ]
    counts = in_window.groupby("entity_id").size()
    joined = predictions.set_index("entity_id").join(counts.rename("k")).fillna({"k": 0})
    with_incidents = joined[joined["k"] >= 2]["label"].mean()
    without = joined[joined["k"] == 0]["label"].mean()
    assert with_incidents > without + 0.2
