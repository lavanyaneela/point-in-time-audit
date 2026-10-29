"""Model training and paired evaluation.

The model is deliberately boring: a histogram gradient boosting classifier
with native missing-value handling, because the subject of this repository is
the feature table, not the estimator. What is not boring is the pairing: the
same entity split, derived from the seed alone, evaluates every pipeline, so
an AUC gap is a within-split difference and its spread across seeds is the
spread of the gap, not the spread of two unrelated splits.

Fits run under a single compute thread. Multi-threaded histogram building
accumulates floats in a nondeterministic order, and a published number that
moves in its last digits between machines fails its own receipts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from threadpoolctl import threadpool_limits

from .features.spec import FEATURE_NAMES

TRAIN_FRACTION = 0.7
DEFAULT_SEEDS = (0, 1, 2, 3, 4)


@dataclass(frozen=True)
class SplitAuc:
    seed: int
    auc: float


def entity_split(n_entities: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Train and test index arrays over entities, a pure function of the seed."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(n_entities)
    cut = int(round(TRAIN_FRACTION * n_entities))
    return order[:cut], order[cut:]


def fit_and_auc(features: pd.DataFrame, labels: np.ndarray, seed: int) -> float:
    """One split, one fit, one held-out AUC."""
    x = features[list(FEATURE_NAMES)].to_numpy(dtype=float)
    train_idx, test_idx = entity_split(len(labels), seed)
    clf = HistGradientBoostingClassifier(
        random_state=seed,
        max_iter=200,
        learning_rate=0.1,
        early_stopping=False,
    )
    with threadpool_limits(limits=1):
        clf.fit(x[train_idx], labels[train_idx])
        scores = clf.predict_proba(x[test_idx])[:, 1]
    return float(roc_auc_score(labels[test_idx], scores))


def evaluate_over_seeds(
    features: pd.DataFrame, labels: np.ndarray, seeds: tuple[int, ...] = DEFAULT_SEEDS
) -> list[SplitAuc]:
    return [SplitAuc(seed=s, auc=round(fit_and_auc(features, labels, s), 6)) for s in seeds]
