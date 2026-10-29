"""Shared fixtures. The SparkSession is session-scoped because startup costs
seconds; every Spark test shares it and none may stop it."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from point_in_time_audit.audit.schema_registry import load_registry
from point_in_time_audit.config import GeneratorConfig
from point_in_time_audit.eventlog import load_fixture

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fixture():
    return load_fixture(REPO / "fixtures" / "event_log", GeneratorConfig())


@pytest.fixture(scope="session")
def registry():
    return load_registry(REPO / "fixtures" / "schema_registry.yaml")


@pytest.fixture(scope="session")
def spark():
    from point_in_time_audit.features.spark_engine import get_spark

    session = get_spark("pit-audit-tests")
    yield session
    session.stop()


def tiny_world() -> tuple[pd.DataFrame, pd.DataFrame]:
    """A five-event world with every visibility case the engines must get
    right, hand-checkable on paper. Prediction at day 10.

    event 0: activity, fact 2, arrival 2.1    -> visible to all policies
    event 1: incident, fact 8, arrival 15     -> fact_only yes, point_in_time no
    event 2: incident, fact 12, arrival 12.5  -> latest yes, fact_only no
    event 3: risk,     fact 9, arrival 9.5, value 1.5 -> visible to all
    event 4: risk,     fact 11, arrival 11.2, value 9 -> latest only
    """
    events = pd.DataFrame(
        {
            "event_id": [0, 1, 2, 3, 4],
            "entity_id": pd.array([1, 1, 1, 1, 1], dtype="int32"),
            "event_type": [
                "activity",
                "incident",
                "incident",
                "risk_assessment",
                "risk_assessment",
            ],
            "fact_days": [2.0, 8.0, 12.0, 9.0, 11.0],
            "arrival_days": [2.1, 15.0, 12.5, 9.5, 11.2],
            "value": [100.0, 5.0, 7.0, 1.5, 9.0],
            "status": [None, None, None, None, None],
        }
    )
    predictions = pd.DataFrame(
        {
            "entity_id": pd.array([1], dtype="int32"),
            "prediction_days": [10.0],
            "label": pd.array([1], dtype="int8"),
        }
    )
    return events, predictions
