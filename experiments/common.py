"""Shared plumbing for the experiments.

Outputs are committed measurements: JSON with sorted keys, rounded values
and no timestamps, so a rerun on an unchanged repository leaves the tree
byte-identical and CI can diff it. The generator config hash travels in
every file so a number can always be traced to the world that produced it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from point_in_time_audit.config import GeneratorConfig  # noqa: E402
from point_in_time_audit.eventlog import Fixture, load_fixture  # noqa: E402
from point_in_time_audit.logging_setup import configure, log_fields  # noqa: E402

OUT_DIR = REPO / "docs" / "experiments"
FIXTURE_DIR = REPO / "fixtures" / "event_log"

__all__ = [
    "FIXTURE_DIR",
    "OUT_DIR",
    "REPO",
    "Fixture",
    "GeneratorConfig",
    "configure",
    "load_default_fixture",
    "log_fields",
    "write_result",
]


def load_default_fixture() -> Fixture:
    return load_fixture(FIXTURE_DIR, GeneratorConfig())


def write_result(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"generator_config_sha256": GeneratorConfig().config_hash(), **payload}
    path = OUT_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
