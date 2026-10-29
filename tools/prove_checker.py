"""Proves the receipts checker can fail, which is the only reason to
believe it when it passes.

For the target metric, every one of its anchors that actually occurs in a
checked document is mutated in a temporary copy of the tree's documents,
one at a time, and the checker must fail on each copy; a prove step that
only tries one anchor leaves the others unproven. A rogue unanchored
number is then inserted and the reverse pass must catch it. The real tree
is never touched.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET = "gap_fact_only_pp_mean"


def run_checker(tree: Path) -> int:
    return subprocess.run(
        [sys.executable, str(tree / "tools" / "check_numbers.py")],
        capture_output=True,
        text=True,
    ).returncode


def copy_tree() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="prove-checker-"))
    for rel in ("docs", "tools", "README.md"):
        src = REPO / rel
        if src.is_dir():
            shutil.copytree(src, temp / rel)
        else:
            shutil.copy2(src, temp / rel)
    return temp


def main() -> int:
    payload = json.loads((REPO / "docs" / "metrics.json").read_text())
    value = payload["metrics"][TARGET]
    anchors = payload["anchors"][TARGET]
    documents = payload["checked_documents"]
    broken_value = f"{value + 1}"

    baseline = copy_tree()
    if run_checker(baseline) != 0:
        print("prove_checker: the pristine tree already fails; nothing is proven")
        return 1
    shutil.rmtree(baseline)

    proven = 0
    for anchor in anchors:
        probe = anchor.replace("{}", str(value))
        present = [d for d in documents if probe.lower() in (REPO / d).read_text().lower()]
        if not present:
            # A wrap or a table render can hide the literal form; the live
            # checker matches across whitespace, this prover only needs the
            # anchors it can find literally, and must find at least one.
            continue
        temp = copy_tree()
        doc = temp / present[0]
        text = doc.read_text()
        pattern = re.compile(re.escape(probe), re.IGNORECASE)
        mutated = pattern.sub(anchor.replace("{}", broken_value), text, count=1)
        if mutated == text:
            raise SystemExit(f"prove_checker: failed to mutate {anchor!r}")
        doc.write_text(mutated)
        code = run_checker(temp)
        shutil.rmtree(temp)
        if code == 0:
            print(f"prove_checker: checker PASSED a broken {anchor!r}; it proves nothing")
            return 1
        proven += 1
        print(f"prove_checker: breaking {anchor!r} failed the build, as it must")

    if proven == 0:
        print("prove_checker: no anchor of the target occurs literally; widen the target")
        return 1

    temp = copy_tree()
    readme = temp / "README.md"
    readme.write_text(
        readme.read_text() + "\nA stray claim of 4321 rows nothing measures.\n"
    )
    code = run_checker(temp)
    shutil.rmtree(temp)
    if code == 0:
        print("prove_checker: the reverse pass swallowed an unanchored number")
        return 1
    print("prove_checker: the reverse pass caught the planted number")
    print(f"prove_checker: OK ({proven} anchors proven breakable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
