"""Renders docs/report.html from the committed measurements.

One static page, no network, every number read from docs/metrics.json and
the experiment outputs so the report cannot say anything the receipts do
not already guard. Styling is deliberately spare: black on white, tables,
the same register as the README.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "report.html"

STYLE = """
body { font-family: Georgia, serif; color: #000; background: #fff;
       max-width: 52rem; margin: 2rem auto; padding: 0 1rem; }
h1, h2 { font-weight: normal; }
table { border-collapse: collapse; margin: 1rem 0; width: 100%; }
th, td { border: 1px solid #000; padding: 0.35rem 0.6rem; text-align: left; }
caption { text-align: left; font-style: italic; padding-bottom: 0.3rem; }
"""


def table(caption: str, rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>" for k, v in rows
    )
    return f"<table><caption>{html.escape(caption)}</caption>{body}</table>"


def main() -> int:
    metrics = json.loads((REPO / "docs" / "metrics.json").read_text())["metrics"]
    e4 = json.loads((REPO / "docs" / "experiments" / "e4_delay_sweep.json").read_text())

    headline = table(
        "The leak, measured",
        [
            ("fabricated AUC, fact-only vs point-in-time", f"{metrics['gap_fact_only_pp_mean']} points"),
            ("spread across seeds", f"{metrics['gap_fact_only_pp_min']} to {metrics['gap_fact_only_pp_max']} points"),
            ("fabricated AUC, latest vs point-in-time", f"{metrics['gap_latest_pp_mean']} points"),
            ("worst single feature", f"{metrics['worst_feature_name']}, {metrics['worst_feature_pp']} points"),
        ],
    )
    gate = table(
        "The gate, with its misses on the label",
        [
            ("direct join detection", f"{metrics['direct_catch_pct']}%"),
            ("overall corpus detection", f"{metrics['overall_catch_pct']}%"),
            ("structurally invisible classes", str(metrics["undetectable_classes_total"])),
            (
                "flags on clean ground truth",
                f"{metrics['clean_expectation_flags']} of {metrics['clean_expectation_cases']}, every one a wrapped correct predicate",
            ),
            (
                "false positives on bare-predicate clean cases",
                f"{metrics['clean_false_positives']} of {metrics['clean_cases']}",
            ),
            ("crossover intermediate share", f"{metrics['crossover_share_pct']}%"),
        ],
    )
    sweep = table(
        "E4: fabricated AUC by incident delay median",
        [(f"{p['incident_delay_median_days']} days", f"{p['gap_pp_mean']} points") for p in e4["points"]],
    )
    credibility = table(
        "Credibility",
        [
            ("tests", str(metrics["tests_total"])),
            ("line coverage", f"{metrics['coverage_line_pct']}%"),
            ("dialects agreeing", f"{metrics['dialects_agreeing']} of 3"),
            ("committed SQL files", str(metrics["sql_files_total"])),
        ],
    )
    OUT.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>point-in-time-audit report</title><style>{STYLE}</style></head><body>"
        "<h1>point-in-time-audit: the measured report</h1>"
        "<p>Every figure below is re-measured by <code>make verify</code> and guarded "
        "by the receipts mechanism; this page only renders what the JSON already says.</p>"
        + headline
        + gate
        + sweep
        + credibility
        + "</body></html>\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
