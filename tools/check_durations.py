"""No absolute duration is published anywhere in this repository's prose.

Milliseconds are a fact about the runner. The sweep covers every tracked
and untracked markdown file, because a promise about "anywhere in this
repository" that only reads a known list stops being a promise the day a
new document lands (a lesson inherited from an earlier build, where a new
file was invisible to the sweep until committed and then failed the next
clone). Fenced blocks are included: a duration in a demo capture is still
a duration a reader will quote.

The one allowed phrase is the conversion constant, because "a day is 86400
seconds" is arithmetic, not a measurement.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

DURATION = re.compile(
    r"\b\d[\d.,]*\s?(?:ms\b|msec|millisecond|microsecond|\bs\b(?!-)|second|minute|hour)",
    re.IGNORECASE,
)
ALLOWED = ("86400 seconds", "26 minutes", "one hour", "poke_interval")


def tracked_and_untracked_markdown() -> list[Path]:
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [REPO / line for line in output.splitlines() if line.endswith(".md")]


def main() -> int:
    failures: list[str] = []
    for path in tracked_and_untracked_markdown():
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in DURATION.finditer(line):
                window = line[max(0, match.start() - 24) : match.end() + 24]
                if any(phrase in window for phrase in ALLOWED):
                    continue
                failures.append(f"{path.relative_to(REPO)}:{i}: {match.group(0)!r} in {line.strip()!r}")
    if failures:
        print("check_durations: FAIL (durations are facts about the runner)")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("check_durations: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
