"""E3: what the analyzer misses, by class, against committed ground truth.

The corpus in fixtures/leak_corpus declares what the world is per case; this
experiment runs the analyzer over all of it and reports detection per class,
the false positive rate on clean cases, the precision cost on correct but
uncertifiable predicates, and the refusal behaviour. The undetectable
classes are the point: a leak relayed through an intermediate table or a
CTE leaves no event table at the site the analyzer reads, and a sensor
waiting on the wrong signal has correct structure. Publishing those rates
at their measured zero is what separates a gate from a linter.

The pivot is computed here too: the intermediate-table share past which
undetected leak sites outnumber detected ones, evaluated at the measured
direct catch rate.
"""

from __future__ import annotations

import yaml

from common import REPO, configure, log_fields, write_result
from point_in_time_audit.audit.dag_analyzer import analyze_dag_path
from point_in_time_audit.audit.pivot import crossover_intermediate_share
from point_in_time_audit.audit.schema_registry import load_registry
from point_in_time_audit.audit.sql_analyzer import analyze_sql_path

CORPUS = REPO / "fixtures" / "leak_corpus"


def main() -> int:
    logger = configure()
    registry = load_registry(REPO / "fixtures" / "schema_registry.yaml")
    spec = yaml.safe_load((CORPUS / "expected.yaml").read_text(encoding="utf-8"))

    per_class: dict[str, dict] = {
        name: {"cases": 0, "leak_findings": 0, "refusals": 0, "clean_passes": 0}
        for name in spec["classes"]
    }
    per_case = []

    for case in spec["cases"]:
        path = CORPUS / case["file"]
        if path.suffix == ".py":
            report = analyze_dag_path(path, registry)
        else:
            report = analyze_sql_path(path, registry)
        bucket = per_class[case["class"]]
        bucket["cases"] += 1
        flagged = len(report.leaks) > 0
        refused = len(report.refusals) > 0 and not flagged
        if flagged:
            bucket["leak_findings"] += 1
        elif refused:
            bucket["refusals"] += 1
        else:
            bucket["clean_passes"] += 1
        per_case.append(
            {
                "file": case["file"],
                "class": case["class"],
                "expectation": case["expectation"],
                "exit_code": int(report.exit_code()),
                "uncertified_relays": len(report.infos),
            }
        )

    # Aggregate over cases, not classes. The refusal class holds both exit 2
    # cases and one leak case, and the first cut of this experiment summed at
    # class grain, which silently counted two correct refusals as missed
    # leaks and published 90 percent where the measured rate is 100.
    undetectable_leak_classes = sorted(
        n
        for n, meta in spec["classes"].items()
        if not meta["detectable"]
        and any(c["class"] == n and c["expectation"] == "leak" for c in spec["cases"])
    )
    flagged_by_file = {c["file"]: c["exit_code"] == 1 for c in per_case}
    leak_cases = [c for c in spec["cases"] if c["expectation"] == "leak"]
    direct = [c for c in leak_cases if spec["classes"][c["class"]]["detectable"]]
    relayed = [c for c in leak_cases if not spec["classes"][c["class"]]["detectable"]]
    direct_cases = len(direct)
    direct_hits = sum(1 for c in direct if flagged_by_file[c["file"]])
    missed_cases = len(relayed)
    missed_hits = sum(1 for c in relayed if flagged_by_file[c["file"]])
    all_leak_cases = direct_cases + missed_cases
    all_leak_hits = direct_hits + missed_hits

    clean_cases = per_class["clean"]["cases"] + per_class["sensor_present"]["cases"]
    clean_false_positives = (
        per_class["clean"]["leak_findings"] + per_class["sensor_present"]["leak_findings"]
    )
    flagged_correct = per_class["clean_flagged"]["leak_findings"]

    direct_catch_rate = round(direct_hits / direct_cases, 4)
    payload = {
        "per_class": {
            name: {
                **stats,
                "detection_rate": (
                    round(stats["leak_findings"] / stats["cases"], 4) if stats["cases"] else None
                ),
                "detectable_by_declaration": spec["classes"][name]["detectable"],
                "grain": spec["classes"][name]["grain"],
            }
            for name, stats in per_class.items()
        },
        "per_case": per_case,
        "corpus_cases_total": len(spec["cases"]),
        "leak_cases_total": all_leak_cases,
        "leak_cases_detected": all_leak_hits,
        "overall_catch_pct": round(100.0 * all_leak_hits / all_leak_cases, 1),
        "direct_cases": direct_cases,
        "direct_hits": direct_hits,
        "direct_catch_rate": direct_catch_rate,
        "direct_catch_pct": round(100.0 * direct_catch_rate, 1),
        "undetectable_classes": undetectable_leak_classes,
        "undetectable_classes_total": len(undetectable_leak_classes),
        "undetected_cases": missed_cases - missed_hits,
        "clean_cases": clean_cases,
        "clean_false_positives": clean_false_positives,
        "clean_flagged_cases": per_class["clean_flagged"]["cases"],
        "clean_flagged_flagged": flagged_correct,
        "refusal_cases_refused": per_class["refusal"]["refusals"],
        "crossover_intermediate_share": round(
            crossover_intermediate_share(direct_catch_rate), 4
        ),
        "crossover_intermediate_share_pct": round(
            100.0 * crossover_intermediate_share(direct_catch_rate), 1
        ),
    }
    path = write_result("e3_analyzer_detection.json", payload)
    log_fields(
        logger,
        "e3 written",
        path=path.name,
        overall_catch_pct=payload["overall_catch_pct"],
        undetectable=payload["undetectable_classes_total"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
