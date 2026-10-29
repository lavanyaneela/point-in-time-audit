"""Findings, verdicts and the exit code contract.

The contract is the product. Most leak detectors silently assume the one
timestamp they can see is the truth; this one distinguishes "no leak found"
from "leak found" from "your schema cannot answer the question", and the
third of those is the most important line of code in the repository.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class ExitCode(enum.IntEnum):
    CLEAN = 0
    LEAK = 1
    REFUSED = 2
    ERROR = 3


class Verdict(enum.Enum):
    OK = "ok"
    MISSING_ARRIVAL = "missing_arrival_predicate"
    NO_TIME_PREDICATE = "no_time_predicate"
    WRONG_COMPARAND = "wrong_comparand"
    UNANALYZABLE = "unanalyzable_predicate"
    OUT_OF_SCOPE = "out_of_scope_relation"
    REFUSED_NO_ARRIVAL_COLUMN = "refused_no_arrival_column"
    REFUSED_UNREGISTERED = "refused_unregistered_table"

    @property
    def is_leak(self) -> bool:
        return self in (
            Verdict.MISSING_ARRIVAL,
            Verdict.NO_TIME_PREDICATE,
            Verdict.WRONG_COMPARAND,
            Verdict.UNANALYZABLE,
        )

    @property
    def is_refusal(self) -> bool:
        return self in (Verdict.REFUSED_NO_ARRIVAL_COLUMN, Verdict.REFUSED_UNREGISTERED)


@dataclass(frozen=True)
class Finding:
    source: str
    site: str
    event_table: str
    verdict: Verdict
    detail: str = ""


@dataclass
class ScanReport:
    findings: list[Finding] = field(default_factory=list)
    infos: list[Finding] = field(default_factory=list)

    @property
    def leaks(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict.is_leak]

    @property
    def refusals(self) -> list[Finding]:
        return [f for f in self.findings if f.verdict.is_refusal]

    def exit_code(self) -> ExitCode:
        """Leak beats refusal when both are present, because a named leak is
        actionable immediately while the refusal still appears in the output.
        Precedence is part of the documented contract, not an accident of
        iteration order."""
        if self.leaks:
            return ExitCode.LEAK
        if self.refusals:
            return ExitCode.REFUSED
        return ExitCode.CLEAN

    def render(self) -> str:
        lines: list[str] = []
        for f in sorted(self.findings, key=lambda x: (x.source, x.site, x.event_table)):
            lines.append(f"{f.verdict.value:32s} {f.source} :: {f.site} :: {f.event_table}")
            if f.detail:
                lines.append(f"{'':32s} {f.detail}")
        for f in sorted(self.infos, key=lambda x: (x.source, x.site)):
            lines.append(f"info: {f.verdict.value:26s} {f.source} :: {f.site} :: {f.event_table}")
        if not lines:
            lines.append("no temporal joins against registered event tables were found")
        lines.append(f"exit code: {int(self.exit_code())} ({self.exit_code().name})")
        return "\n".join(lines)
