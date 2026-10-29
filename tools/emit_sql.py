"""Regenerates the committed SQL under sql/ from the specs.

Twelve feature builds (four dialects by three policies) and four audit
queries per dialect. Same contract as the fixture: on an unchanged spec this
leaves the tree clean, and CI runs it followed by `git diff --exit-code` so a
spec edit that forgets to regenerate fails loudly.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from point_in_time_audit.config import POLICIES  # noqa: E402
from point_in_time_audit.dialects.emit import (  # noqa: E402
    AUDIT_QUERY_NAMES,
    DIALECTS,
    emit_audit_sql,
    emit_feature_sql,
)

SQL_ROOT = Path(__file__).resolve().parents[1] / "sql"


def main() -> int:
    written = 0
    for dialect in DIALECTS:
        out = SQL_ROOT / dialect
        out.mkdir(parents=True, exist_ok=True)
        for policy in POLICIES:
            path = out / f"features_{policy}.sql"
            path.write_text(emit_feature_sql(dialect, policy), encoding="utf-8")
            written += 1
        for name in AUDIT_QUERY_NAMES:
            path = out / f"{name}.sql"
            path.write_text(emit_audit_sql(dialect, name), encoding="utf-8")
            written += 1
    print(f"wrote {written} SQL files under {SQL_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
