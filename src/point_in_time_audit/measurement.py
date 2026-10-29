"""The measurement half: how much AUC a visibility policy fabricates.

This module is shared by the E1 and E2 experiments and by `pit-audit
measure`, so the number the CLI gates on and the number the README quotes are
the same code path.

The referee rule is enforced here, not in the experiments: features are built
by both engines and the measurement refuses to proceed on any disagreement,
because a published figure derived from one engine's private opinion of the
as-of semantics is exactly the failure mode this repository is about.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import POLICIES
from .eventlog import Fixture
from .features.duckdb_engine import build_features_duckdb
from .features.spec import FEATURE_NAMES
from .modeling import DEFAULT_SEEDS, evaluate_over_seeds, fit_and_auc


class EngineDisagreement(RuntimeError):
    """Raised when the Spark and DuckDB builds differ on any feature value."""


def frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> list[str]:
    """Feature columns on which the two builds disagree (nan equals nan)."""
    bad = []
    for name in FEATURE_NAMES:
        x, y = a[name].to_numpy(dtype=float), b[name].to_numpy(dtype=float)
        same = (np.isnan(x) & np.isnan(y)) | (x == y)
        if not bool(same.all()):
            bad.append(name)
    return bad


def build_all_policies(
    fixture: Fixture, spark=None
) -> dict[str, pd.DataFrame]:
    """Feature tables per policy, referee-checked when a Spark session is
    passed. Without one (the pure-DuckDB path the CLI uses for speed), the
    caller inherits the DuckDB build alone and the parity suite remains the
    guarantee that the two engines agree on this fixture."""
    tables: dict[str, pd.DataFrame] = {}
    for policy in POLICIES:
        duck = build_features_duckdb(fixture.events, fixture.predictions, policy)
        if spark is not None:
            from .features.spark_engine import build_features_spark

            sp = build_features_spark(spark, fixture.events, fixture.predictions, policy)
            bad = frames_equal(duck, sp)
            if bad:
                raise EngineDisagreement(
                    f"engines disagree under policy {policy!r} on: {', '.join(bad)}"
                )
        tables[policy] = duck
    return tables


@dataclass(frozen=True)
class LeakMeasurement:
    aucs: dict[str, list[float]]
    gap_fact_only_pp: list[float]
    gap_latest_pp: list[float]

    @property
    def mean_gap_fact_only_pp(self) -> float:
        return float(np.mean(self.gap_fact_only_pp))

    @property
    def mean_gap_latest_pp(self) -> float:
        return float(np.mean(self.gap_latest_pp))


def measure_leak(
    tables: dict[str, pd.DataFrame],
    labels: np.ndarray,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
) -> LeakMeasurement:
    """Paired AUC gaps in percentage points, per seed.

    The gap is paired: one seed fixes one entity split, every policy is
    evaluated on it, and the gap is the within-split difference. Reported
    per seed so the spread published is the spread of the gap itself.
    """
    aucs = {p: [r.auc for r in evaluate_over_seeds(tables[p], labels, seeds)] for p in POLICIES}
    gap_fact = [
        round((a - b) * 100.0, 4)
        for a, b in zip(aucs["fact_only"], aucs["point_in_time"], strict=True)
    ]
    gap_latest = [
        round((a - b) * 100.0, 4)
        for a, b in zip(aucs["latest"], aucs["point_in_time"], strict=True)
    ]
    return LeakMeasurement(aucs=aucs, gap_fact_only_pp=gap_fact, gap_latest_pp=gap_latest)


def feature_attribution(
    tables: dict[str, pd.DataFrame],
    labels: np.ndarray,
    naive_policy: str = "fact_only",
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
) -> dict[str, dict[str, float]]:
    """Per-feature fabricated AUC: swap one feature's honest column for its
    naive column on an otherwise point-in-time table and measure what the
    swap alone buys.

    This isolates each feature's leak against the honest baseline rather
    than dividing the joint gap by fiat; the parts are not forced to sum to
    the whole, and E2 publishes that sum next to the joint gap because the
    difference between them is feature interaction, not error.
    """
    base = tables["point_in_time"]
    naive = tables[naive_policy]
    baseline = {s: fit_and_auc(base, labels, s) for s in seeds}

    out: dict[str, dict[str, float]] = {}
    for name in FEATURE_NAMES:
        swapped = base.copy()
        swapped[name] = naive[name].to_numpy()
        deltas = [(fit_and_auc(swapped, labels, s) - baseline[s]) * 100.0 for s in seeds]
        changed = int((~(
            (base[name].isna() & naive[name].isna())
            | (base[name].to_numpy(dtype=float) == naive[name].to_numpy(dtype=float))
        )).sum())
        out[name] = {
            "fabricated_auc_pp_mean": round(float(np.mean(deltas)), 4),
            "fabricated_auc_pp_min": round(float(np.min(deltas)), 4),
            "fabricated_auc_pp_max": round(float(np.max(deltas)), 4),
            "rows_changed": changed,
        }
    return out
