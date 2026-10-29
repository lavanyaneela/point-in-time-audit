"""Static analysis of SQL for temporal joins that cannot be point-in-time
correct, because they never state an arrival predicate.

What this file is and is not. It is complete over direct joins: at any query
scope that references both a registered prediction table and a registered
event table, a join without a bare arrival-before-prediction conjunct is
flagged, including predicates hidden inside functions or expressions the
analyzer cannot certify (those are flagged as unanalyzable rather than
trusted). It is deliberately incomplete in precision: a correct predicate
wrapped in a UDF is flagged too, and the false positive rate that costs is
measured and published by E3 instead of being tuned away.

What it structurally cannot see is any leak whose event table is not in the
scope being read: a naive join baked into an intermediate table upstream, or
relayed through a CTE, leaves no event table at the consumption site. Those
scopes are reported as out-of-scope information, never certified clean, and
E3 measures the miss rate at exactly 100 percent for those classes, which is
the opening impossibility reappearing one level up (ADR-004).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import expressions as exp

from .report import Finding, ScanReport, Verdict
from .schema_registry import SchemaRegistry, TableEntry

COMPARISONS = (exp.LTE, exp.LT, exp.GTE, exp.GT)


@dataclass
class Scope:
    """One SELECT and the relations it reads directly."""

    select: exp.Select
    site: str
    tables: dict[str, TableEntry]  # alias -> registry entry (direct, registered)
    derived: dict[str, set[str]]  # alias -> registered event tables it relays


def _statement_target(stmt: exp.Expression) -> str | None:
    if isinstance(stmt, exp.Create) and stmt.find(exp.Select) is not None:
        table = stmt.find(exp.Table)
        return table.name.lower() if table is not None else None
    if isinstance(stmt, exp.Insert):
        table = stmt.find(exp.Table)
        return table.name.lower() if table is not None else None
    return None


def _tables_in(tree: exp.Expression) -> set[str]:
    return {t.name.lower() for t in tree.find_all(exp.Table)}


def _direct_relations(select: exp.Select) -> list[tuple[str, exp.Expression]]:
    """(alias, node) for each FROM or JOIN source of this select only."""
    out: list[tuple[str, exp.Expression]] = []
    sources: list[exp.Expression] = []
    # sqlglot renamed the Select arg from "from" to "from_" at version 30;
    # read both so the analyzer does not silently see zero relations under
    # one of them, which is exactly how its first corpus run failed.
    from_clause = select.args.get("from_") or select.args.get("from")
    if from_clause is not None:
        sources.append(from_clause.this)
    for join in select.args.get("joins") or []:
        sources.append(join.this)
    for node in sources:
        if isinstance(node, exp.Table):
            out.append((node.alias_or_name.lower(), node))
        elif isinstance(node, exp.Subquery):
            out.append((node.alias_or_name.lower(), node))
    return out


def _cte_event_ancestry(
    select: exp.Select, registry: SchemaRegistry, lineage: dict[str, set[str]]
) -> dict[str, set[str]]:
    """For each CTE defined on this statement, the registered event tables it
    reads, directly or through earlier CTEs and earlier statements."""
    out: dict[str, set[str]] = {}
    with_clause = select.root().find(exp.With)
    if with_clause is None:
        return out
    for cte in with_clause.expressions:
        name = cte.alias_or_name.lower()
        ancestry: set[str] = set()
        for t in _tables_in(cte.this):
            entry = registry.get(t)
            if entry is not None and entry.kind == "event":
                ancestry.add(t)
            ancestry |= out.get(t, set())
            ancestry |= lineage.get(t, set())
        out[name] = ancestry
    return out


def _conjuncts(select: exp.Select) -> list[exp.Expression]:
    """Top level AND conjuncts from WHERE and every JOIN ON in this scope.
    Anything under an OR gives no guarantee and is not a conjunct."""
    parts: list[exp.Expression] = []
    where = select.args.get("where")
    if where is not None:
        parts.append(where.this)
    for join in select.args.get("joins") or []:
        on = join.args.get("on")
        if on is not None:
            parts.append(on)
    out: list[exp.Expression] = []

    def split(node: exp.Expression) -> None:
        if isinstance(node, exp.And):
            split(node.left)
            split(node.right)
        elif isinstance(node, exp.Paren):
            split(node.this)
        else:
            out.append(node)

    for p in parts:
        split(p)
    return out


def _column_refs(node: exp.Expression) -> list[exp.Column]:
    return list(node.find_all(exp.Column))


def _resolve(col: exp.Column, scope_tables: dict[str, TableEntry]) -> tuple[str, str] | None:
    """(alias, column_name) when the column belongs to a registered relation
    in this scope. Unqualified columns resolve only when exactly one in-scope
    relation registers that column name; the analyzer guesses nothing else."""
    name = col.name.lower()
    qualifier = col.table.lower() if col.table else None
    if qualifier:
        if qualifier in scope_tables:
            return qualifier, name
        return None
    owners = []
    for alias, entry in scope_tables.items():
        known = {
            entry.fact_time_column,
            entry.arrival_time_column,
            entry.prediction_time_column,
            entry.entity_key,
        }
        if name in known:
            owners.append(alias)
    if len(owners) == 1:
        return owners[0], name
    return None


def _is_bare_column(node: exp.Expression) -> bool:
    return isinstance(node, exp.Column)


def _side_is_prediction_time(
    node: exp.Expression, scope_tables: dict[str, TableEntry]
) -> bool:
    """True when the expression's only column reference is a prediction time
    column. Arithmetic around it (a window lower bound) is allowed; a second
    column is not, because then the comparand is no longer the prediction
    instant."""
    cols = _column_refs(node)
    if len(cols) != 1:
        return False
    resolved = _resolve(cols[0], scope_tables)
    if resolved is None:
        return False
    alias, name = resolved
    entry = scope_tables[alias]
    return entry.kind == "prediction" and name == entry.prediction_time_column


def _classify_event_join(
    scope_tables: dict[str, TableEntry],
    alias: str,
    entry: TableEntry,
    conjuncts: list[exp.Expression],
) -> tuple[Verdict, str]:
    fact_ok = False
    arrival_ok = False
    wrong_comparand: str | None = None
    unanalyzable: str | None = None

    for conj in conjuncts:
        touches = [
            r
            for c in _column_refs(conj)
            if (r := _resolve(c, scope_tables)) is not None and r[0] == alias
        ]
        temporal = [
            name
            for _, name in touches
            if name in (entry.fact_time_column, entry.arrival_time_column)
        ]
        if not temporal:
            continue
        if isinstance(conj, COMPARISONS):
            left, right = conj.left, conj.right
            for event_side, other_side, small_side in (
                (left, right, isinstance(conj, (exp.LTE, exp.LT))),
                (right, left, isinstance(conj, (exp.GTE, exp.GT))),
            ):
                if not _is_bare_column(event_side):
                    continue
                resolved = _resolve(event_side, scope_tables)
                if resolved is None or resolved[0] != alias:
                    continue
                name = resolved[1]
                if name == entry.arrival_time_column:
                    if small_side and _side_is_prediction_time(other_side, scope_tables):
                        arrival_ok = True
                    else:
                        wrong_comparand = conj.sql()
                elif name == entry.fact_time_column:
                    if _side_is_prediction_time(other_side, scope_tables):
                        fact_ok = True
                break
            else:
                unanalyzable = conj.sql()
        else:
            # A function call, a CASE, a COALESCE, a BETWEEN: the analyzer
            # does not certify what it cannot read, so a temporal predicate
            # in any shape but a bare comparison is flagged, including the
            # correct ones. E3 prices that choice as a false positive rate.
            unanalyzable = conj.sql()

    if arrival_ok:
        return Verdict.OK, ""
    if wrong_comparand is not None:
        return (
            Verdict.WRONG_COMPARAND,
            f"arrival predicate compares against something that is not the prediction instant: {wrong_comparand}",
        )
    if unanalyzable is not None:
        return (
            Verdict.UNANALYZABLE,
            f"temporal predicate the analyzer cannot certify: {unanalyzable}",
        )
    if fact_ok:
        return (
            Verdict.MISSING_ARRIVAL,
            "fact predicate present, arrival predicate absent: a fact can be true before "
            "prediction time and arrive after it",
        )
    return Verdict.NO_TIME_PREDICATE, "join carries no temporal predicate at all"


def analyze_sql_text(
    text: str,
    registry: SchemaRegistry,
    source: str = "<sql>",
    dialect: str = "spark",
    lineage: dict[str, set[str]] | None = None,
) -> ScanReport:
    """Analyze one SQL file's worth of statements. `lineage` carries derived
    table ancestry across files (the DAG analyzer threads it through in task
    order) and is updated in place for CREATE TABLE AS and INSERT targets."""
    lineage = lineage if lineage is not None else {}
    report = ScanReport()
    statements = sqlglot.parse(text, read=dialect)

    for i, stmt in enumerate(statements):
        if stmt is None:
            continue
        target = _statement_target(stmt)
        if target is not None:
            ancestry: set[str] = set()
            for t in _tables_in(stmt):
                if t == target:
                    continue
                entry = registry.get(t)
                if entry is not None and entry.kind == "event":
                    ancestry.add(t)
                ancestry |= lineage.get(t, set())
            lineage[target] = lineage.get(target, set()) | ancestry

        for select in stmt.find_all(exp.Select):
            site = f"statement {i + 1}"
            cte_ancestry = _cte_event_ancestry(select, registry, lineage)
            relations = _direct_relations(select)

            scope_tables: dict[str, TableEntry] = {}
            relayed: dict[str, set[str]] = {}
            unknown: list[str] = []
            cte_names = set(cte_ancestry)
            for alias, node in relations:
                if isinstance(node, exp.Table):
                    entry = registry.get(node.name)
                    if entry is not None:
                        scope_tables[alias] = entry
                        continue
                    name = node.name.lower()
                    via = cte_ancestry.get(name, set()) | lineage.get(name, set())
                    if via:
                        relayed[alias] = via
                    elif name not in cte_names and name not in lineage:
                        unknown.append(name)
                elif isinstance(node, exp.Subquery):
                    via = {
                        t
                        for t in _tables_in(node)
                        if (e := registry.get(t)) is not None and e.kind == "event"
                    }
                    if via:
                        relayed[alias] = via

            predictions = {a: e for a, e in scope_tables.items() if e.kind == "prediction"}
            events = {a: e for a, e in scope_tables.items() if e.kind == "event"}
            if not predictions:
                continue

            conjuncts = _conjuncts(select)
            for name in unknown:
                report.findings.append(
                    Finding(
                        source=source,
                        site=site,
                        event_table=name,
                        verdict=Verdict.REFUSED_UNREGISTERED,
                        detail=(
                            "this relation is not in the schema registry and no provenance "
                            "for it is visible, so whether its values were knowable cannot "
                            "be posed; register the table or exclude it"
                        ),
                    )
                )
            for alias, entry in events.items():
                if entry.arrival_time_column is None:
                    report.findings.append(
                        Finding(
                            source=source,
                            site=site,
                            event_table=entry.name,
                            verdict=Verdict.REFUSED_NO_ARRIVAL_COLUMN,
                            detail=(
                                "the registry declares no arrival time column for this table, "
                                "so whether a value was knowable is unrepresentable in it; "
                                "the audit refuses rather than guesses"
                            ),
                        )
                    )
                    continue
                verdict, detail = _classify_event_join(scope_tables, alias, entry, conjuncts)
                report.findings.append(
                    Finding(
                        source=source,
                        site=site,
                        event_table=entry.name,
                        verdict=verdict,
                        detail=detail,
                    )
                )
            for alias, via in relayed.items():
                report.infos.append(
                    Finding(
                        source=source,
                        site=site,
                        event_table=",".join(sorted(via)),
                        verdict=Verdict.OUT_OF_SCOPE,
                        detail=(
                            f"relation {alias!r} derives from an event table but the join "
                            "site carries no event table the analyzer can read; provenance "
                            "is not analyzable at table grain and this site is NOT certified"
                        ),
                    )
                )
    return report


def analyze_sql_path(
    path: Path,
    registry: SchemaRegistry,
    dialect: str = "spark",
    lineage: dict[str, set[str]] | None = None,
) -> ScanReport:
    text = Path(path).read_text(encoding="utf-8")
    return analyze_sql_text(text, registry, source=str(path), dialect=dialect, lineage=lineage)
