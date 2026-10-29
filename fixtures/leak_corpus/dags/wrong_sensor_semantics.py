"""Corpus DAG: a sensor exists and is wired correctly, but it waits on a row
count, not an arrival watermark. Statically indistinguishable from the
correct DAG; the analyzer passes it and E3 records the class at zero."""

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sensors.sql import SqlSensor

with DAG(dag_id="wrong_sensor_semantics") as dag:
    row_count_sensor = SqlSensor(
        task_id="row_count_sensor",
        sql="SELECT COUNT(*) > 100000 FROM events",
    )
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
    row_count_sensor >> build >> train
