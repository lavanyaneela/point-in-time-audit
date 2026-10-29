"""Inserts the real GitHub handle into badge URLs and clone commands.

The repository ships with GITHUB_USERNAME as a deliberate placeholder,
because a badge pointing at a repository that does not exist renders as
"unknown" and reads worse than no badge. Run `make set-handle HANDLE=you`
once after creating the remote, before pushing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLACEHOLDER = "GITHUB_USERNAME"
FILES = ["README.md", "docs/defense-guide.md"]


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1]:
        print("usage: python tools/set_handle.py <github-handle>", file=sys.stderr)
        return 2
    handle = sys.argv[1]
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37})", handle):
        print(f"{handle!r} does not look like a GitHub handle", file=sys.stderr)
        return 2
    changed = 0
    for name in FILES:
        path = REPO / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if PLACEHOLDER in text:
            path.write_text(text.replace(PLACEHOLDER, handle), encoding="utf-8")
            changed += 1
    print(f"handle set in {changed} files; commit the change before pushing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
