"""The schema registry: which columns mean what, declared, never guessed.

The analyzer refuses rather than infers. A column named updated_at might be
a fact time, an arrival time, or neither, and guessing is how leak detectors
end up blessing the exact tables they should refuse. The registry is a
committed YAML file an engineer fills in once per table; a table it does not
list, or lists without an arrival column, produces a refusal (exit code 2),
which is the repository's one sentence thesis running as code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class RegistryError(ValueError):
    """Raised when the registry file itself is malformed."""


@dataclass(frozen=True)
class TableEntry:
    name: str
    kind: str  # "event" or "prediction"
    entity_key: str
    fact_time_column: str | None = None
    arrival_time_column: str | None = None
    prediction_time_column: str | None = None


@dataclass(frozen=True)
class SchemaRegistry:
    tables: dict[str, TableEntry]

    def event_tables(self) -> dict[str, TableEntry]:
        return {n: t for n, t in self.tables.items() if t.kind == "event"}

    def prediction_tables(self) -> dict[str, TableEntry]:
        return {n: t for n, t in self.tables.items() if t.kind == "prediction"}

    def get(self, name: str) -> TableEntry | None:
        return self.tables.get(name.lower())


def load_registry(path: Path) -> SchemaRegistry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "tables" not in raw:
        raise RegistryError(f"{path}: expected a top-level 'tables' mapping")
    tables: dict[str, TableEntry] = {}
    for name, body in raw["tables"].items():
        body = body or {}
        kind = body.get("kind")
        if kind not in ("event", "prediction"):
            raise RegistryError(f"{path}: table {name!r} has kind {kind!r}, expected event or prediction")
        if kind == "prediction" and not body.get("prediction_time_column"):
            raise RegistryError(f"{path}: prediction table {name!r} needs prediction_time_column")
        tables[name.lower()] = TableEntry(
            name=name.lower(),
            kind=kind,
            entity_key=body.get("entity_key", "entity_id"),
            fact_time_column=_lower(body.get("fact_time_column")),
            arrival_time_column=_lower(body.get("arrival_time_column")),
            prediction_time_column=_lower(body.get("prediction_time_column")),
        )
    return SchemaRegistry(tables=tables)


def _lower(value: str | None) -> str | None:
    return value.lower() if isinstance(value, str) else None
