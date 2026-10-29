"""The gate half: static analysis of SQL and DAG definitions.

A static analyzer cannot prove a pipeline is point-in-time correct. What it
can do, cheaply and in CI, is flag the join sites that cannot possibly be
correct because they never mention an arrival time, and refuse outright when
the schema has no arrival column to mention, which is the impossibility made
operational (exit code 2). E3 measures the classes it misses, because a gate
that does not publish its own blind spots is a linter wearing a hard hat.
"""

from .report import ExitCode, Finding, Verdict

__all__ = ["ExitCode", "Finding", "Verdict"]
