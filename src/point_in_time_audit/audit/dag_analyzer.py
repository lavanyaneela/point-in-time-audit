"""Static analysis of Airflow DAG files, by reading the source, not by
importing it.

Importing a DAG executes arbitrary code and drags in a scheduler's worth of
dependencies, so this analyzer parses the Python with the ast module and
reads three things: operator constructions (task_id plus any sql argument),
dependency edges written with the >> operator, and which tasks are sensors.
That is enough to thread SQL through the lineage in task order and to check
one scheduling property the SQL alone cannot carry: a task that trains or
builds features must sit downstream of an arrival completeness sensor,
because clean SQL executed before the facts have landed is a leak with no
SQL in it.

The property has a named limit (ADR-004): a sensor that exists and is wired
correctly but waits on the wrong signal, row counts instead of an arrival
watermark, is statically indistinguishable from a correct one. E3 carries
that class at a measured detection rate of zero.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .report import Finding, ScanReport, Verdict
from .schema_registry import SchemaRegistry
from .sql_analyzer import analyze_sql_text

TRAINING_MARKERS = ("train", "features", "build_features")
SENSOR_MARKERS = ("sensor",)


@dataclass
class DagTask:
    name: str
    operator: str
    sql: str | None = None
    upstream: set[str] = field(default_factory=set)

    @property
    def is_sensor(self) -> bool:
        return any(m in self.operator.lower() for m in SENSOR_MARKERS) or any(
            m in self.name.lower() for m in SENSOR_MARKERS
        )

    @property
    def is_training(self) -> bool:
        return any(m in self.name.lower() for m in TRAINING_MARKERS)


def _string_value(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def parse_dag_source(text: str) -> dict[str, DagTask]:
    tree = ast.parse(text)
    tasks: dict[str, DagTask] = {}
    var_to_task: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            func = call.func
            op_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            task_id = None
            sql = None
            for kw in call.keywords:
                if kw.arg == "task_id":
                    task_id = _string_value(kw.value)
                elif kw.arg == "sql":
                    sql = _string_value(kw.value)
            if task_id is not None:
                tasks[task_id] = DagTask(name=task_id, operator=op_name, sql=sql)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_to_task[target.id] = task_id

    def chain_names(expr: ast.expr) -> list[str]:
        if isinstance(expr, ast.Name) and expr.id in var_to_task:
            return [var_to_task[expr.id]]
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.RShift):
            return chain_names(expr.left) + chain_names(expr.right)
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.BinOp):
            names = chain_names(node.value)
            for up, down in zip(names, names[1:], strict=False):
                if down in tasks:
                    tasks[down].upstream.add(up)
    return tasks


def _transitive_upstream(tasks: dict[str, DagTask], name: str) -> set[str]:
    seen: set[str] = set()
    frontier = list(tasks[name].upstream)
    while frontier:
        cur = frontier.pop()
        if cur in seen or cur not in tasks:
            continue
        seen.add(cur)
        frontier.extend(tasks[cur].upstream)
    return seen


def topological_order(tasks: dict[str, DagTask]) -> list[str]:
    order: list[str] = []
    placed: set[str] = set()
    remaining = dict(tasks)
    while remaining:
        ready = sorted(
            n for n, t in remaining.items() if all(u in placed or u not in tasks for u in t.upstream)
        )
        if not ready:
            order.extend(sorted(remaining))
            break
        for n in ready:
            order.append(n)
            placed.add(n)
            remaining.pop(n)
    return order


def analyze_dag_path(path: Path, registry: SchemaRegistry) -> ScanReport:
    text = Path(path).read_text(encoding="utf-8")
    tasks = parse_dag_source(text)
    report = ScanReport()

    # Thread each task's SQL through one shared lineage, in task order, so a
    # naive join baked into an upstream task's target table is at least
    # recorded as ancestry when a downstream task reads it.
    lineage: dict[str, set[str]] = {}
    for name in topological_order(tasks):
        task = tasks[name]
        if task.sql:
            sub = analyze_sql_text(
                task.sql,
                registry,
                source=f"{path}::{name}",
                lineage=lineage,
            )
            report.findings.extend(sub.findings)
            report.infos.extend(sub.infos)

    for name, task in tasks.items():
        if not task.is_training:
            continue
        upstream = _transitive_upstream(tasks, name)
        has_sensor = any(tasks[u].is_sensor for u in upstream if u in tasks)
        if not has_sensor:
            report.findings.append(
                Finding(
                    source=str(path),
                    site=f"task {name}",
                    event_table="(schedule)",
                    verdict=Verdict.MISSING_ARRIVAL,
                    detail=(
                        "training task has no arrival completeness sensor upstream; "
                        "clean SQL executed before the facts have landed is still a leak"
                    ),
                )
            )
    return report
