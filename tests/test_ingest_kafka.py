"""The broker round trip, run only where a broker is reachable.

The import of confluent_kafka happens inside the test bodies, never at
module level, so collection is identical on every machine and the published
test count cannot drift with an optional extra (a lesson learned on an
earlier repository, where a module level importorskip made the count differ
between a laptop and CI)."""

import os
from pathlib import Path

import pytest

from point_in_time_audit.ingest.live_kafka import PAYLOAD_COLUMNS

REPO = Path(__file__).resolve().parents[1]
BOOTSTRAP = os.environ.get("PIT_KAFKA_BOOTSTRAP")

pytestmark = pytest.mark.kafka


def test_the_payload_columns_are_exactly_the_manifest_hashed_ones():
    assert PAYLOAD_COLUMNS == [
        "event_id",
        "entity_id",
        "event_type",
        "fact_days",
        "arrival_days",
        "value",
        "status",
    ]


@pytest.mark.skipif(not BOOTSTRAP, reason="set PIT_KAFKA_BOOTSTRAP to run against a broker")
def test_the_fixture_round_trips_through_a_real_broker_bit_for_bit():
    pytest.importorskip("confluent_kafka")
    from point_in_time_audit.ingest.live_kafka import roundtrip_matches_manifest

    assert roundtrip_matches_manifest(
        BOOTSTRAP, REPO / "fixtures" / "event_log", topic="entity-events-roundtrip"
    )
