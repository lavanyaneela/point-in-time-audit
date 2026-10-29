"""Regenerates the committed event log fixture from the default config.

Idempotence is the contract: on an unchanged config and an unchanged
generator, running this must leave `git status` clean on the content hashes.
CI runs it and diffs the manifest's content hashes, not the parquet bytes,
because parquet bytes are a fact about the writer version (the regeneration
job additionally pins the writer version so the bytes stay stable too).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from point_in_time_audit.config import GeneratorConfig  # noqa: E402
from point_in_time_audit.eventlog import write_fixture  # noqa: E402
from point_in_time_audit.generator import generate_world  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "event_log"


def main() -> int:
    cfg = GeneratorConfig()
    events, predictions = generate_world(cfg)
    manifest = write_fixture(events, predictions, cfg, FIXTURE_DIR)
    print(
        f"wrote {manifest['events_total']} events for {manifest['entities_total']} entities "
        f"({manifest['positives_total']} positives) to {FIXTURE_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
