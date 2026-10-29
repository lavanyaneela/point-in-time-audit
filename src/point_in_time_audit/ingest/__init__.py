"""Ingest: how events enter, with their arrival order intact.

The default ingest path is the committed log in fixtures/event_log, read by
eventlog.load_fixture: it carries the full Kafka record envelope (topic,
partition, per partition offsets in arrival order, key, timestamp) with no
broker, which is what keeps `make verify` offline and every number
reproducible.

live_kafka is the same path against a real broker, behind the optional
kafka extra, exercised by a non blocking CI job with a service container.
A job exists that round trips the fixture through a real broker and checks
the consumed content hash against the manifest; nothing in this repository
claims more than that about Kafka, and nothing here was measured under
broker load.
"""
