"""The registry refuses malformed declarations loudly."""

import pytest

from point_in_time_audit.audit.schema_registry import RegistryError, load_registry


def _write(tmp_path, text):
    path = tmp_path / "registry.yaml"
    path.write_text(text)
    return path


def test_the_committed_registry_loads_with_the_four_tables(registry):
    assert set(registry.tables) == {"events", "incidents", "crm_accounts", "predictions"}


def test_event_and_prediction_views_partition_the_tables(registry):
    assert set(registry.event_tables()) == {"events", "incidents", "crm_accounts"}
    assert set(registry.prediction_tables()) == {"predictions"}


def test_lookups_are_case_insensitive(registry):
    assert registry.get("EVENTS") is registry.get("events")


def test_an_unknown_table_returns_none_not_a_guess(registry):
    assert registry.get("mystery") is None


def test_the_single_timestamp_table_has_no_arrival_column(registry):
    assert registry.get("crm_accounts").arrival_time_column is None


def test_a_missing_tables_mapping_is_rejected(tmp_path):
    with pytest.raises(RegistryError, match="tables"):
        load_registry(_write(tmp_path, "nothing: here\n"))


def test_an_unknown_kind_is_rejected(tmp_path):
    with pytest.raises(RegistryError, match="kind"):
        load_registry(_write(tmp_path, "tables:\n  t:\n    kind: dimension\n"))


def test_a_prediction_table_without_its_time_column_is_rejected(tmp_path):
    with pytest.raises(RegistryError, match="prediction_time_column"):
        load_registry(_write(tmp_path, "tables:\n  p:\n    kind: prediction\n"))


def test_declared_column_names_are_lowercased_for_matching(tmp_path):
    registry = load_registry(
        _write(
            tmp_path,
            "tables:\n"
            "  e:\n"
            "    kind: event\n"
            "    fact_time_column: Fact_Time\n"
            "    arrival_time_column: ARRIVAL_TIME\n",
        )
    )
    entry = registry.get("e")
    assert entry.fact_time_column == "fact_time"
    assert entry.arrival_time_column == "arrival_time"


def test_the_default_entity_key_is_entity_id(tmp_path):
    registry = load_registry(
        _write(tmp_path, "tables:\n  e:\n    kind: event\n    fact_time_column: ft\n")
    )
    assert registry.get("e").entity_key == "entity_id"
