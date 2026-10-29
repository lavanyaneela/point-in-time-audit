"""The declarative feature spec both engines and every SQL dialect compile.

One spec, many compilers, is the design that makes the referee arrangement
possible: if the Spark build and the DuckDB build each hand-implemented their
own feature definitions, a disagreement between them would be ambiguous. With
a shared spec, a disagreement is a bug in exactly one compiler.

Kinds:
    window_count    count of events of a type with fact_time inside a window
    window_sum      sum of value over the same window
    window_max      max of value over the same window
    last_value      value of the latest visible event of a type
    days_since_last days between prediction time and the latest visible fact
    last_status_eq  1.0 when the latest visible status event equals a literal

Window bounds always use fact_time, because the window is business logic.
Which events are admissible at all is the visibility policy, and that is the
only thing the three pipelines disagree about.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    event_type: str
    kind: str
    window_days: int | None = None
    status_literal: str | None = None


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec("activity_count_30d", "activity", "window_count", window_days=30),
    FeatureSpec("activity_amount_sum_30d", "activity", "window_sum", window_days=30),
    FeatureSpec("days_since_last_activity", "activity", "days_since_last"),
    FeatureSpec("last_risk_score", "risk_assessment", "last_value"),
    FeatureSpec("incident_count_90d", "incident", "window_count", window_days=90),
    FeatureSpec("incident_severity_max_90d", "incident", "window_max", window_days=90),
    FeatureSpec("status_risky", "status_change", "last_status_eq", status_literal="risky"),
)

FEATURE_NAMES: tuple[str, ...] = tuple(f.name for f in FEATURES)

# Features whose absence means zero (a count of nothing is zero) versus
# features whose absence means unknown (the max of nothing is not zero).
ZERO_WHEN_ABSENT: frozenset[str] = frozenset(
    f.name for f in FEATURES if f.kind in ("window_count", "window_sum", "last_status_eq")
)


def visibility_predicate_text(policy: str) -> str:
    """The policy, spelled as the SQL predicate each pipeline applies.

    This exact text is what the static analyzer looks for the shape of: a
    temporal join is point-in-time correct only when both comparisons are
    present. Keeping the canonical wording here, next to the spec, is what
    lets the README quote the contract without inventing a second phrasing.
    """
    if policy == "latest":
        return ""
    if policy == "fact_only":
        return "e.fact_time <= p.prediction_time"
    if policy == "point_in_time":
        return "e.fact_time <= p.prediction_time AND e.arrival_time <= p.prediction_time"
    raise ValueError(f"unknown policy: {policy!r}")
