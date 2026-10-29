"""Fails the build when a document quotes a figure the code no longer
produces, or quotes a figure nothing re-measures.

Forward pass: every anchor of every metric is compiled to a pattern whose
slot accepts a number (thousands-grouped or plain, with a lookbehind so it
cannot fire inside a hash) or, for string metrics, an identifier. Patterns
match case-insensitively and across line wraps. Every occurrence anywhere in
a checked document, fenced blocks included, must carry the current value;
one stale occurrence fails the build even when a correct one sits beside it.
Every anchor must be used by at least one document (an orphaned anchor is a
guard guarding nothing, and an orphaned anchor on a flagship figure is how a
reworded sentence goes feral), and no two metrics may share an anchor, even
by containment.

Reverse pass: every number in prose must be a rendered metric value or an
exemption. Fenced blocks, inline code and HTML attributes are excluded; ISO
dates and ordered-list markers are stripped first. Single digit integers are
structural (exit codes, list positions) and are governed by rule 3: small
metrics are checked through anchors only. Exemptions must each be used,
carry a reason, and never equal a rendered metric value.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
METRICS_PATH = REPO / "docs" / "metrics.json"

NUMBER_SLOT = r"(?<![\w.-])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w.])"
TEXT_SLOT = r"([\w][\w./-]*)"
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
ORDERED_LIST = re.compile(r"^(\s*)\d+\.\s", re.MULTILINE)
FENCE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
HTML_TAG = re.compile(r"<[^>\n]+>")

# Numbers that appear in prose and are configuration constants rather than
# measurements. Each needs a reason; each must be used; none may collide
# with a rendered metric value.
EXEMPTIONS: dict[str, str] = {
    "86400": "seconds in a day, the conversion constant the UTC pin relies on",
    "30": "the activity window and the default incident delay median, in days",
    "60": "the top of the E4 delay sweep, in days",
    "95": "the confidence level of the exact binomial bound, in percent",
    "3.11": "the minimum Python version in the quickstart",
    "26": "minutes inside the lost hour for the first affected event",
}


def rendered_forms(value) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        out.add(value)
        return out
    if isinstance(value, bool):
        return {str(value)}
    if isinstance(value, int):
        out.add(str(value))
        out.add(f"{value:,}")
        return out
    out.add(f"{value}")
    if float(value).is_integer():
        out.add(str(int(value)))
        out.add(f"{int(value):,}")
    return out


def normalise_number(text: str) -> str:
    text = text.replace(",", "")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def anchor_pattern(template: str, is_text: bool) -> re.Pattern:
    slot = TEXT_SLOT if is_text else NUMBER_SLOT
    parts = [re.escape(p) for p in template.split("{}")]
    body = slot.join(part.replace(r"\ ", r"\s+") for part in parts)
    return re.compile(body, re.IGNORECASE)


def strip_for_reverse(text: str) -> str:
    text = FENCE.sub(" ", text)
    text = INLINE_CODE.sub(" ", text)
    text = HTML_TAG.sub(" ", text)
    text = ISO_DATE.sub(" ", text)
    text = ORDERED_LIST.sub(r"\1", text)
    return text


def main() -> int:
    payload = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    metrics: dict = payload["metrics"]
    anchors: dict[str, list[str]] = payload["anchors"]
    documents = {
        name: (REPO / name).read_text(encoding="utf-8")
        for name in payload["checked_documents"]
        if (REPO / name).exists()
    }
    missing_docs = [n for n in payload["checked_documents"] if n not in documents]
    failures: list[str] = []
    if missing_docs:
        failures.append(f"checked documents missing from the tree: {missing_docs}")

    # No two metrics share an anchor, including by containment.
    flattened = [
        (metric, template.replace("{}", "\x00").lower())
        for metric, templates in anchors.items()
        for template in templates
    ]
    for i, (metric_a, body_a) in enumerate(flattened):
        for metric_b, body_b in flattened[i + 1 :]:
            if metric_a != metric_b and (body_a in body_b or body_b in body_a):
                failures.append(
                    f"anchors collide between {metric_a} and {metric_b}: "
                    f"{body_a!r} vs {body_b!r}"
                )

    all_rendered: set[str] = set()
    for value in metrics.values():
        all_rendered |= {normalise_number(f) if not isinstance(value, str) else f for f in rendered_forms(value)}

    # Forward pass.
    for metric, templates in anchors.items():
        value = metrics[metric]
        is_text = isinstance(value, str)
        accepted = (
            {value}
            if is_text
            else {normalise_number(f) for f in rendered_forms(value)}
        )
        for template in templates:
            pattern = anchor_pattern(template, is_text)
            used = False
            for name, text in documents.items():
                for match in pattern.finditer(text):
                    used = True
                    got = match.group(1) if is_text else normalise_number(match.group(1))
                    if got not in accepted:
                        line = text[: match.start()].count("\n") + 1
                        failures.append(
                            f"{name}:{line}: anchor {template!r} of {metric} carries "
                            f"{match.group(1)!r}, the measured value is {value!r}"
                        )
            if not used:
                failures.append(
                    f"orphaned anchor: no checked document uses {template!r} ({metric})"
                )

    # Exemption hygiene.
    for exempt in EXEMPTIONS:
        if normalise_number(exempt) in all_rendered:
            failures.append(
                f"exemption {exempt!r} equals a rendered metric value; a measured "
                "figure may never hide behind an exemption"
            )
    used_exemptions: set[str] = set()

    # Reverse pass.
    for name, text in documents.items():
        stripped = strip_for_reverse(text)
        for match in re.finditer(NUMBER_SLOT, stripped):
            raw = match.group(1)
            norm = normalise_number(raw)
            if "." not in norm and len(norm) < 2:
                continue  # rule 3: single digits are anchored, never digit-matched
            if norm in all_rendered:
                continue
            if raw in EXEMPTIONS or norm in EXEMPTIONS:
                used_exemptions.add(raw if raw in EXEMPTIONS else norm)
                continue
            line = stripped[: match.start()].count("\n") + 1
            failures.append(
                f"{name}:{line}: the number {raw!r} matches no metric and no "
                "exemption; nothing re-measures it"
            )

    for exempt in EXEMPTIONS:
        if exempt not in used_exemptions:
            failures.append(
                f"unused exemption {exempt!r}; an exemption nothing needs is a "
                "hole waiting for a number"
            )

    if failures:
        print("check_numbers: FAIL")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        f"check_numbers: OK ({len(metrics)} metrics, "
        f"{sum(len(t) for t in anchors.values())} anchors, {len(documents)} documents)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
