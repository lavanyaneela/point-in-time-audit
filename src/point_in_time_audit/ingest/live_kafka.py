"""Round trip the committed event log through a real Kafka broker.

Runs only under the optional kafka extra against a reachable broker, so it
is excluded from the default coverage denominator (disclosed in the
README's credibility line). The contract it proves is narrow and exact: the
payload that comes back out of the broker content-hashes to the same value
the fixture manifest pins, and within each partition the offsets preserve
arrival order. It proves nothing about throughput, retention, rebalancing
or any behaviour under load, and the README says so in as many words.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..eventlog import _content_hash, load_fixture

PAYLOAD_COLUMNS = [
    "event_id",
    "entity_id",
    "event_type",
    "fact_days",
    "arrival_days",
    "value",
    "status",
]


def produce_fixture(bootstrap: str, fixture_dir: Path, topic: str) -> int:
    """Produce every fixture record, keyed by entity, partitioned as the
    manifest declares, in arrival order. Returns the record count."""
    from confluent_kafka import Producer

    fixture = load_fixture(fixture_dir)
    producer = Producer({"bootstrap.servers": bootstrap})
    events = fixture.events.sort_values(["partition", "kafka_offset"])
    for row in events.itertuples(index=False):
        payload = {c: getattr(row, c) for c in PAYLOAD_COLUMNS}
        if pd.isna(payload["status"]):
            payload["status"] = None
        producer.produce(
            topic,
            key=str(row.kafka_key),
            value=json.dumps(payload, sort_keys=True, default=float),
            partition=int(row.partition),
        )
    producer.flush(30)
    return int(len(events))


def consume_events(bootstrap: str, topic: str, expected_rows: int, timeout_s: float = 60.0) -> pd.DataFrame:
    """Consume exactly expected_rows records from offset zero and return
    them as a frame in the canonical arrival order."""
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": "pit-audit-roundtrip",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    metadata = consumer.list_topics(topic, timeout=timeout_s)
    partitions = [TopicPartition(topic, p, 0) for p in metadata.topics[topic].partitions]
    consumer.assign(partitions)

    rows: list[dict] = []
    while len(rows) < expected_rows:
        message = consumer.poll(timeout=timeout_s)
        if message is None:
            break
        if message.error():
            raise RuntimeError(str(message.error()))
        payload = json.loads(message.value())
        payload["partition"] = message.partition()
        payload["kafka_offset"] = message.offset()
        rows.append(payload)
    consumer.close()

    frame = pd.DataFrame(rows)
    return frame.sort_values("event_id").reset_index(drop=True)


def roundtrip_matches_manifest(bootstrap: str, fixture_dir: Path, topic: str) -> bool:
    """Produce, consume, and hold the consumed payload to the manifest's
    content hash and the consumed offsets to arrival order per partition."""
    fixture = load_fixture(fixture_dir)
    n = produce_fixture(bootstrap, fixture_dir, topic)
    consumed = consume_events(bootstrap, topic, expected_rows=n)
    if len(consumed) != n:
        return False
    for _, group in consumed.groupby("partition"):
        ordered = group.sort_values("kafka_offset")
        if not ordered["arrival_days"].is_monotonic_increasing:
            return False
    payload = consumed[PAYLOAD_COLUMNS].copy()
    payload["entity_id"] = payload["entity_id"].astype("int32")
    want = fixture.events[PAYLOAD_COLUMNS].reset_index(drop=True)
    return _content_hash(payload) == _content_hash(want)
