"""Corpus DAG: the arrival watermark sensor gates the build. The watermark
is per partition for the same reason the repository's own DAG uses that
form: a global MAX(arrival_time) is satisfied by one late row, which is
the wrong_sensor_semantics shape wearing the right name. This sketch
assumes every partition carries rows; the pipeline DAG additionally pins
the partition count."""

from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sensors.sql import SqlSensor

with DAG(dag_id="with_sensor") as dag:
    arrival_watermark_sensor = SqlSensor(
        task_id="arrival_watermark_sensor",
        sql=(
            "SELECT MIN(latest_arrival) >= :cutoff FROM ("
            "SELECT partition, MAX(arrival_time) AS latest_arrival "
            "FROM events GROUP BY partition) AS per_partition"
        ),
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
    arrival_watermark_sensor >> build >> train
