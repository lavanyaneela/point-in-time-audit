"""The repository's own pipeline as an Airflow DAG.

The DAG is real: it parses under Airflow's loader in the optional-extra CI
job, its structure is pinned by the ast-based tests, and the audit gate it
ends with is this repository's own scan, so the pipeline that builds the
features is gated by the tool that checks them. What is not real is a
scheduler executing it; ADR-003 names that boundary and what running one
would add.

The task order is the argument: ingest lands facts with their arrival
times, the watermark sensor refuses to proceed until every partition has
delivered past the interval end, and only then do features build and the model
train. Remove the sensor and every task still succeeds, every row is still
present eventually, and the training set quietly contains facts nobody knew
at prediction time. That failure needs no SQL, which is why the scan checks
the schedule as well as the queries.
"""

from __future__ import annotations

from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.providers.common.sql.sensors.sql import SqlSensor


def _ingest_event_log() -> None:
    """Loads and manifest-verifies the committed, Kafka shaped log. In
    production this callable is a consumer writing to the warehouse; here
    the committed parquet already is the table, so loading and verifying
    it is the whole ingest and nothing further is written."""
    from point_in_time_audit.config import GeneratorConfig
    from point_in_time_audit.eventlog import load_fixture

    load_fixture("fixtures/event_log", GeneratorConfig())


def _train_model() -> None:
    """Trains on the point-in-time feature table and logs held out AUC."""
    from point_in_time_audit.config import GeneratorConfig
    from point_in_time_audit.eventlog import load_fixture
    from point_in_time_audit.features.duckdb_engine import build_features_duckdb
    from point_in_time_audit.modeling import fit_and_auc

    fixture = load_fixture("fixtures/event_log", GeneratorConfig())
    features = build_features_duckdb(fixture.events, fixture.predictions, "point_in_time")
    fit_and_auc(features, fixture.predictions["label"].to_numpy(), seed=0)


with DAG(
    dag_id="point_in_time_feature_pipeline",
    schedule="@daily",
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=10)},
) as dag:
    ingest_event_log = PythonOperator(
        task_id="ingest_event_log",
        python_callable=_ingest_event_log,
    )

    # The watermark is per partition on purpose. A global MAX(arrival_time)
    # is satisfied by one late row while a 30 day incident is still in
    # flight, which would make this sensor the wrong_sensor_semantics class
    # the corpus declares invisible. The committed log guarantees arrival
    # order within each partition (offset order is arrival order), so the
    # minimum of the per partition maxima is a true low watermark under
    # this repository's own ingest model: every partition has delivered
    # past the interval end, therefore nothing older is still in flight.
    arrival_watermark_sensor = SqlSensor(
        task_id="arrival_watermark_sensor",
        conn_id="warehouse",
        sql=(
            "SELECT MIN(latest_arrival) >= '{{ data_interval_end }}' FROM ("
            "SELECT partition, MAX(arrival_time) AS latest_arrival "
            "FROM events GROUP BY partition) AS per_partition"
        ),
        poke_interval=300,
        timeout=6 * 3600,
    )

    audit_gate = BashOperator(
        task_id="audit_gate",
        bash_command=(
            "pit-audit scan --sql sql/spark/features_point_in_time.sql --dags dags "
            "--registry fixtures/schema_registry.yaml"
        ),
    )

    build_features = SQLExecuteQueryOperator(
        task_id="build_features",
        conn_id="warehouse",
        sql="sql/spark/features_point_in_time.sql",
    )

    train_model = PythonOperator(
        task_id="train_model",
        python_callable=_train_model,
    )

    ingest_event_log >> arrival_watermark_sensor >> audit_gate >> build_features >> train_model
