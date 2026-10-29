"""The fixture's three identities and the refusals they power."""

import json

import pytest

from point_in_time_audit.config import GeneratorConfig
from point_in_time_audit.eventlog import (
    FixtureError,
    load_fixture,
    materialize_times,
    write_fixture,
)
from point_in_time_audit.generator import generate_world


@pytest.fixture(scope="module")
def small_round_trip(tmp_path_factory):
    from dataclasses import replace

    cfg = replace(GeneratorConfig(), n_entities=120, seed=11)
    events, predictions = generate_world(cfg)
    out = tmp_path_factory.mktemp("fixture")
    manifest = write_fixture(events, predictions, cfg, out)
    return cfg, out, manifest


def test_a_written_fixture_loads_and_verifies(small_round_trip):
    cfg, out, manifest = small_round_trip
    fx = load_fixture(out, cfg)
    assert fx.manifest == manifest
    assert len(fx.events) == manifest["events_total"]


def test_loading_under_a_drifted_config_refuses(small_round_trip):
    _, out, _ = small_round_trip
    from dataclasses import replace

    drifted = replace(GeneratorConfig(), n_entities=120, seed=12)
    with pytest.raises(FixtureError, match="different config"):
        load_fixture(out, drifted)


def test_loading_without_a_config_skips_only_the_identity_check(small_round_trip):
    _, out, _ = small_round_trip
    load_fixture(out)


def test_a_tampered_parquet_fails_the_content_hash(small_round_trip, tmp_path):
    import shutil

    cfg, out, _ = small_round_trip
    import pandas as pd

    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    events = pd.read_parquet(copy / "events.parquet")
    events.loc[0, "value"] = 999999.0
    events.to_parquet(copy / "events.parquet", index=False, compression="zstd")
    with pytest.raises(FixtureError, match="content hash"):
        load_fixture(copy, cfg)


def test_a_missing_manifest_is_a_named_refusal(tmp_path):
    with pytest.raises(FixtureError, match="no manifest"):
        load_fixture(tmp_path)


def test_a_wrong_row_count_in_the_manifest_is_caught(small_round_trip, tmp_path):
    import shutil

    cfg, out, _ = small_round_trip
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    manifest = json.loads((copy / "manifest.json").read_text())
    manifest["events_total"] += 1
    # keep the content hashes valid so the count check is the one that fires
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(FixtureError, match="row count"):
        load_fixture(copy, cfg)


def test_offsets_within_a_partition_follow_arrival_order(fixture):
    for _, group in fixture.events.groupby("partition"):
        ordered = group.sort_values("kafka_offset")
        assert ordered["arrival_days"].is_monotonic_increasing


def test_offsets_within_a_partition_are_contiguous_from_zero(fixture):
    for _, group in fixture.events.groupby("partition"):
        offsets = sorted(group["kafka_offset"].tolist())
        assert offsets == list(range(len(offsets)))


def test_partitioning_is_entity_id_modulo_the_declared_count(fixture):
    n = fixture.manifest["partitions"]
    assert (fixture.events["partition"] == fixture.events["entity_id"] % n).all()


def test_the_kafka_key_is_the_entity_id(fixture):
    sample = fixture.events.head(500)
    assert (sample["kafka_key"] == sample["entity_id"].astype(str)).all()


def test_the_committed_manifest_matches_the_committed_config(fixture):
    assert fixture.manifest["generator_config_sha256"] == GeneratorConfig().config_hash()


def test_the_committed_counts_are_the_published_ones(fixture):
    assert fixture.manifest["events_total"] == len(fixture.events)
    assert fixture.manifest["entities_total"] == fixture.predictions["entity_id"].nunique()
    assert fixture.manifest["positives_total"] == int(fixture.predictions["label"].sum())


def test_materialize_times_matches_the_fixture_writer_conversion(fixture):
    events, predictions = generate_world(GeneratorConfig())
    ev, pr = materialize_times(events, predictions)
    merged = ev.merge(
        fixture.events[["event_id", "fact_time", "arrival_time"]], on="event_id", suffixes=("", "_fx")
    )
    assert (merged["fact_time"] == merged["fact_time_fx"]).all()
    assert (merged["arrival_time"] == merged["arrival_time_fx"]).all()
    assert (pr["prediction_time"] == fixture.predictions["prediction_time"]).all()
