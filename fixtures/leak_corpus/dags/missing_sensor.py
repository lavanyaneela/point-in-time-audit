"""Corpus DAG: clean SQL, no arrival completeness sensor upstream of the
training task. The leak has no SQL in it; it is a scheduling fact."""

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

with DAG(dag_id="missing_sensor") as dag:
    ingest = EmptyOperator(task_id="ingest")
    build = SQLExecuteQueryOperator(
        task_id="build_features",
        sql="""
            SELECT p.entity_id, COUNT(*) AS n
            FROM predictions AS p
            JOIN events AS e
              ON e.entity_id = p.entity_id
             AND e.fact_time <= p.prediction_time
             AND e.arrival_time <= p.prediction_time
            GROUP BY p.entity_id
        """,
    )
    train = EmptyOperator(task_id="train_model")
    ingest >> build >> train
