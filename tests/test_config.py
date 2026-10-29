"""The config is the fixture's identity; these pin that identity's rules."""

from dataclasses import replace

from point_in_time_audit.config import POLICIES, DelayConfig, GeneratorConfig


def test_the_same_config_hashes_to_the_same_value_twice():
    assert GeneratorConfig().config_hash() == GeneratorConfig().config_hash()


def test_changing_any_field_changes_the_config_hash():
    base = GeneratorConfig()
    assert replace(base, seed=8).config_hash() != base.config_hash()


def test_changing_a_nested_delay_field_changes_the_config_hash():
    base = GeneratorConfig()
    tweaked = replace(base, delays=DelayConfig(incident_median=29.0))
    assert tweaked.config_hash() != base.config_hash()


def test_the_config_hash_is_a_sha256_hex_digest():
    assert len(GeneratorConfig().config_hash()) == 64


def test_the_three_policies_are_exactly_the_documented_ones():
    assert POLICIES == ("latest", "fact_only", "point_in_time")


def test_the_config_is_frozen_so_cache_keys_cannot_drift():
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        GeneratorConfig().seed = 9  # type: ignore[misc]


def test_the_default_incident_delay_median_is_thirty_days():
    assert GeneratorConfig().delays.incident_median == 30.0


def test_a_zero_delay_median_is_a_legal_sweep_endpoint():
    DelayConfig(incident_median=0.0)
