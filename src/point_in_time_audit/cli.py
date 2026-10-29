"""The pit-audit command line: scan, measure, pivot.

Exit codes are the product surface and are shared by both halves:

    0  no leak detected by any check
    1  leak detected; offending joins or features named
    2  refused: the schema has no arrival time column, so the question is
       unanswerable for this data, which is the impossibility operational
    3  tool error

A broad exception handler maps crashes to 3, because exit 1 must always
mean "the answer is no", never "the tool fell over". Set PIT_AUDIT_DEBUG=1
to re-raise, because a handler like this otherwise makes a real bug look
like a user error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .audit.pivot import crossover_intermediate_share
from .audit.report import ExitCode, ScanReport
from .audit.schema_registry import load_registry
from .config import GeneratorConfig
from .logging_setup import configure, log_fields

DEFAULT_THRESHOLD_PP = 2.0


def _cmd_scan(args: argparse.Namespace) -> int:
    from .audit.dag_analyzer import analyze_dag_path
    from .audit.sql_analyzer import analyze_sql_path

    registry = load_registry(Path(args.registry))
    report = ScanReport()
    lineage: dict[str, set[str]] = {}

    sql_files: list[Path] = []
    for item in args.sql or []:
        p = Path(item)
        sql_files.extend(sorted(p.rglob("*.sql")) if p.is_dir() else [p])
    for path in sql_files:
        sub = analyze_sql_path(path, registry, dialect=args.dialect, lineage=lineage)
        report.findings.extend(sub.findings)
        report.infos.extend(sub.infos)

    dag_files: list[Path] = []
    for item in args.dags or []:
        p = Path(item)
        dag_files.extend(sorted(p.rglob("*.py")) if p.is_dir() else [p])
    for path in dag_files:
        sub = analyze_dag_path(path, registry)
        report.findings.extend(sub.findings)
        report.infos.extend(sub.infos)

    print(report.render())
    return int(report.exit_code())


def _cmd_measure(args: argparse.Namespace) -> int:
    import numpy as np

    from .eventlog import load_fixture
    from .measurement import build_all_policies, feature_attribution, measure_leak

    logger = configure()
    registry = load_registry(Path(args.registry))
    events_entry = registry.get("events")
    if events_entry is None or events_entry.arrival_time_column is None:
        print(
            "refused: the registry declares no arrival time column for the events table, "
            "so no pipeline over it can be told apart from a leaking one. "
            "The measurement cannot be run, which is the finding."
        )
        return int(ExitCode.REFUSED)

    fixture = load_fixture(Path(args.fixture), GeneratorConfig())
    tables = build_all_policies(fixture)
    labels = fixture.predictions["label"].to_numpy()
    seeds = tuple(int(s) for s in args.seeds.split(","))
    leak = measure_leak(tables, labels, seeds=seeds)
    gap = leak.mean_gap_fact_only_pp
    log_fields(logger, "measured", gap_fact_only_pp=round(gap, 2), seeds=len(seeds))

    print(f"held-out AUC, mean over {len(seeds)} paired splits:")
    for policy, values in leak.aucs.items():
        print(f"  {policy:15s} {float(np.mean(values)):.4f}")
    print(f"fabricated AUC, fact-only versus point-in-time: {gap:.2f} points")
    print(f"fabricated AUC, latest versus point-in-time:    {leak.mean_gap_latest_pp:.2f} points")

    attribution = feature_attribution(tables, labels, seeds=seeds)
    ranked = sorted(attribution.items(), key=lambda kv: -kv[1]["fabricated_auc_pp_mean"])
    print("per-feature fabricated AUC (one honest column swapped for its naive column):")
    for name, stats in ranked:
        print(f"  {name:28s} {stats['fabricated_auc_pp_mean']:+6.2f} points")

    if gap > args.threshold_pp:
        print(f"leak detected: {gap:.2f} points exceeds the {args.threshold_pp:.2f} point threshold")
        return int(ExitCode.LEAK)
    print(f"no leak above the {args.threshold_pp:.2f} point threshold")
    return int(ExitCode.CLEAN)


def _cmd_pivot(args: argparse.Namespace) -> int:
    import json

    e3 = json.loads(Path(args.e3).read_text(encoding="utf-8"))
    c = float(e3["direct_catch_rate"])
    f_star = crossover_intermediate_share(c)
    print(
        f"measured catch rate on direct join sites: {c:.3f}\n"
        f"crossover share of intermediate-table routing: {f_star:.3f}\n"
        "past that share, undetected leak sites outnumber detected ones and the\n"
        "fix is structural: arrival time as a first class column a feature store\n"
        "enforces, not a better regex"
    )
    return int(ExitCode.CLEAN)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pit-audit", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="static analysis of SQL files and DAG definitions")
    scan.add_argument("--sql", nargs="*", help="SQL files or directories")
    scan.add_argument("--dags", nargs="*", help="DAG files or directories")
    scan.add_argument("--registry", required=True, help="schema registry YAML")
    scan.add_argument("--dialect", default="spark", help="SQL dialect for parsing")
    scan.set_defaults(func=_cmd_scan)

    measure = sub.add_parser("measure", help="measure the AUC the naive pipelines fabricate")
    measure.add_argument("--fixture", required=True, help="event log fixture directory")
    measure.add_argument("--registry", default="fixtures/schema_registry.yaml")
    measure.add_argument("--seeds", default="0,1,2,3,4")
    measure.add_argument("--threshold-pp", type=float, default=DEFAULT_THRESHOLD_PP)
    measure.set_defaults(func=_cmd_measure)

    pivot = sub.add_parser("pivot", help="when static analysis stops being the right tool")
    pivot.add_argument("--e3", default="docs/experiments/e3_analyzer_detection.json")
    pivot.set_defaults(func=_cmd_pivot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as err:  # noqa: BLE001
        if os.environ.get("PIT_AUDIT_DEBUG") == "1":
            raise
        print(f"tool error: {err}", file=sys.stderr)
        return int(ExitCode.ERROR)


if __name__ == "__main__":
    raise SystemExit(main())
