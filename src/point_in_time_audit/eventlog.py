"""The committed, Kafka-shaped event log.

Arrival time is a streaming concept: a log preserves the order facts landed,
a warehouse table does not. This module keeps that concept without a broker.
Each record carries the envelope a Kafka consumer would see (topic, partition,
offset, key, timestamp) and the offset order within a partition is the arrival
order, because that is the information the rest of the repository is about.

The manifest pins three identities: the bytes of each committed file, a
content hash computed over a canonical CSV serialisation of the rows, and the
hash of the generator config that produced them. Bytes catch tampering.
Content catches a parquet writer version changing the bytes while the data is
identical. The config hash catches the quiet failure where a drifted config
regenerates a different world under the same filename (the fixture refuses to
load rather than feeding it to the experiments).
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import GeneratorConfig
from .generator import to_timestamp

TOPIC = "entity-events"
MANIFEST_NAME = "manifest.json"
EVENTS_NAME = "events.parquet"
PREDICTIONS_NAME = "predictions.parquet"


class FixtureError(RuntimeError):
    """Raised when a committed fixture does not match its manifest."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _content_hash(frame: pd.DataFrame) -> str:
    """Writer-version-independent identity: canonical CSV of the sorted rows."""
    buf = io.StringIO()
    frame.to_csv(buf, index=False, float_format="%.6f", lineterminator="\n")
    return _sha256_bytes(buf.getvalue().encode("utf-8"))


def _with_envelope(events: pd.DataFrame, n_partitions: int) -> pd.DataFrame:
    out = events.copy()
    out["topic"] = TOPIC
    out["partition"] = (out["entity_id"] % n_partitions).astype("int32")
    # Offsets are per partition, in arrival order. events is already sorted by
    # arrival, so a cumulative count within partition is exactly the offset a
    # broker would have assigned.
    out["kafka_offset"] = out.groupby("partition").cumcount().astype("int64")
    out["kafka_key"] = out["entity_id"].astype(str)
    return out


@dataclass(frozen=True)
class Fixture:
    events: pd.DataFrame
    predictions: pd.DataFrame
    manifest: dict


def materialize_times(
    events: pd.DataFrame, predictions: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Adds the timestamp columns the SQL surface reads to frames fresh from
    the generator, which carries only float days. The committed fixture gets
    these at write time; an in-memory world (the E4 sweep) gets them here,
    through the same conversion, so both paths exercise the same SQL."""
    ev = events.copy()
    ev["fact_time"] = to_timestamp(ev["fact_days"])
    ev["arrival_time"] = to_timestamp(ev["arrival_days"])
    pr = predictions.copy()
    pr["prediction_time"] = to_timestamp(pr["prediction_days"])
    return ev, pr


def write_fixture(
    events: pd.DataFrame, predictions: pd.DataFrame, cfg: GeneratorConfig, out_dir: Path
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    enveloped = _with_envelope(events, cfg.n_partitions)
    enveloped["fact_time"] = to_timestamp(enveloped["fact_days"])
    enveloped["arrival_time"] = to_timestamp(enveloped["arrival_days"])

    preds = predictions.copy()
    preds["prediction_time"] = to_timestamp(preds["prediction_days"])

    events_path = out_dir / EVENTS_NAME
    preds_path = out_dir / PREDICTIONS_NAME
    enveloped.to_parquet(events_path, index=False, compression="zstd")
    preds.to_parquet(preds_path, index=False, compression="zstd")

    manifest = {
        "generator_config_sha256": cfg.config_hash(),
        "files": {
            EVENTS_NAME: {
                "sha256": _sha256_file(events_path),
                "content_sha256": _content_hash(enveloped.drop(columns=["fact_time", "arrival_time"])),
                "rows": int(len(enveloped)),
            },
            PREDICTIONS_NAME: {
                "sha256": _sha256_file(preds_path),
                "content_sha256": _content_hash(preds.drop(columns=["prediction_time"])),
                "rows": int(len(preds)),
            },
        },
        "events_total": int(len(enveloped)),
        "entities_total": int(predictions["entity_id"].nunique()),
        "positives_total": int(predictions["label"].sum()),
        "topic": TOPIC,
        "partitions": cfg.n_partitions,
    }
    (out_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_fixture(fixture_dir: Path, cfg: GeneratorConfig | None = None) -> Fixture:
    """Loads and verifies a committed fixture.

    Verification order is deliberate: config identity first, because a stale
    config is the failure a byte hash cannot name, then content hashes, which
    survive a parquet writer upgrade, then row counts.
    """
    fixture_dir = Path(fixture_dir)
    manifest_path = fixture_dir / MANIFEST_NAME
    if not manifest_path.exists():
        raise FixtureError(f"no manifest at {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if cfg is not None and manifest["generator_config_sha256"] != cfg.config_hash():
        raise FixtureError(
            "fixture was generated under a different config; refusing to load it. "
            "Run `make fixture` and inspect the diff."
        )

    events = pd.read_parquet(fixture_dir / EVENTS_NAME)
    preds = pd.read_parquet(fixture_dir / PREDICTIONS_NAME)

    got = _content_hash(events.drop(columns=["fact_time", "arrival_time"]))
    want = manifest["files"][EVENTS_NAME]["content_sha256"]
    if got != want:
        raise FixtureError(f"events content hash mismatch: {got} != {want}")
    got = _content_hash(preds.drop(columns=["prediction_time"]))
    want = manifest["files"][PREDICTIONS_NAME]["content_sha256"]
    if got != want:
        raise FixtureError(f"predictions content hash mismatch: {got} != {want}")
    if len(events) != manifest["events_total"]:
        raise FixtureError("events row count disagrees with manifest")

    return Fixture(events=events, predictions=preds, manifest=manifest)
