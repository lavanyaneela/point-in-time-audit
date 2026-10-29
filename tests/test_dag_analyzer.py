"""DAG parsing by source, the sensor rule, and the repository's own DAG
pinned structurally."""

from pathlib import Path

import pytest

from point_in_time_audit.audit.dag_analyzer import (
    analyze_dag_path,
    parse_dag_source,
    topological_order,
)
from point_in_time_audit.audit.report import Verdict

REPO = Path(__file__).resolve().parents[1]
CORPUS_DAGS = REPO / "fixtures" / "leak_corpus" / "dags"
PIPELINE_DAG = REPO / "dags" / "feature_pipeline_dag.py"


def test_tasks_and_edges_parse_from_source_without_importing_airflow():
    tasks = parse_dag_source((CORPUS_DAGS / "with_sensor.py").read_text())
    assert set(tasks) == {"arrival_watermark_sensor", "build_features", "train_model"}
    assert tasks["build_features"].upstream == {"arrival_watermark_sensor"}
    assert tasks["train_model"].upstream == {"build_features"}


def test_sensor_detection_reads_operator_and_task_names():
    tasks = parse_dag_source((CORPUS_DAGS / "with_sensor.py").read_text())
    assert tasks["arrival_watermark_sensor"].is_sensor
    assert not tasks["train_model"].is_sensor


def test_training_markers_cover_build_and_train_tasks():
    tasks = parse_dag_source((CORPUS_DAGS / "missing_sensor.py").read_text())
    assert tasks["build_features"].is_training
    assert tasks["train_model"].is_training
    assert not tasks["ingest"].is_training


def test_a_missing_sensor_is_flagged_for_every_training_task(registry):
    report = analyze_dag_path(CORPUS_DAGS / "missing_sensor.py", registry)
    schedule_findings = [f for f in report.leaks if f.event_table == "(schedule)"]
    assert len(schedule_findings) == 2
    assert all("sensor" in f.detail for f in schedule_findings)


def test_a_present_sensor_satisfies_the_rule_transitively(registry):
    report = analyze_dag_path(CORPUS_DAGS / "with_sensor.py", registry)
    assert not report.leaks


def test_the_wrong_sensor_is_statically_indistinguishable_and_passes(registry):
    report = analyze_dag_path(CORPUS_DAGS / "wrong_sensor_semantics.py", registry)
    assert not report.leaks, (
        "a sensor waiting on a row count has correct structure; this pass is "
        "the measured blindness E3 records, not an oversight"
    )


def test_inline_task_sql_is_analyzed_through_the_shared_lineage(registry):
    text = '''
build = SQLExecuteQueryOperator(
    task_id="build_features",
    sql="""
        SELECT p.entity_id FROM predictions p
        JOIN events e ON e.entity_id = p.entity_id
    """,
)
sensor = SqlSensor(task_id="arrival_sensor", sql="SELECT 1")
sensor >> build
'''
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(text)
        path = Path(handle.name)
    report = analyze_dag_path(path, registry)
    assert any(f.verdict == Verdict.NO_TIME_PREDICATE for f in report.leaks)


def test_a_sql_file_reference_resolves_from_the_repository_root(registry):
    report = analyze_dag_path(PIPELINE_DAG, registry)
    assert Verdict.OK in [f.verdict for f in report.findings]


def test_an_unresolvable_sql_file_is_flagged_not_skipped(registry, tmp_path):
    dag = tmp_path / "dags" / "lost.py"
    dag.parent.mkdir()
    dag.write_text(
        'x = SQLExecuteQueryOperator(task_id="build_features", sql="sql/missing.sql")\n'
    )
    report = analyze_dag_path(dag, registry)
    assert any(f.verdict == Verdict.UNANALYZABLE for f in report.leaks)


def test_topological_order_respects_edges():
    tasks = parse_dag_source((CORPUS_DAGS / "with_sensor.py").read_text())
    order = topological_order(tasks)
    assert order.index("arrival_watermark_sensor") < order.index("build_features")
    assert order.index("build_features") < order.index("train_model")


def test_topological_order_terminates_on_a_cycle():
    tasks = parse_dag_source(
        'a = Op(task_id="a")\nb = Op(task_id="b")\na >> b\nb >> a\n'
    )
    assert sorted(topological_order(tasks)) == ["a", "b"]


class TestThePipelineDagItself:
    def test_it_has_exactly_the_five_documented_tasks(self):
        tasks = parse_dag_source(PIPELINE_DAG.read_text())
        assert set(tasks) == {
            "ingest_event_log",
            "arrival_watermark_sensor",
            "audit_gate",
            "build_features",
            "train_model",
        }

    def test_the_sensor_gates_everything_downstream_of_ingest(self):
        tasks = parse_dag_source(PIPELINE_DAG.read_text())
        assert tasks["arrival_watermark_sensor"].upstream == {"ingest_event_log"}
        assert tasks["audit_gate"].upstream == {"arrival_watermark_sensor"}
        assert tasks["build_features"].upstream == {"audit_gate"}
        assert tasks["train_model"].upstream == {"build_features"}

    def test_its_own_scan_comes_back_clean(self, registry):
        report = analyze_dag_path(PIPELINE_DAG, registry)
        assert int(report.exit_code()) == 0

    def test_the_gate_task_runs_this_repositorys_own_scan(self):
        text = PIPELINE_DAG.read_text()
        assert "pit-audit scan" in text


@pytest.mark.airflow
def test_the_dag_imports_under_a_real_airflow_loader():
    airflow_models = pytest.importorskip("airflow.models")
    bag = airflow_models.DagBag(dag_folder=str(PIPELINE_DAG.parent), include_examples=False)
    assert not bag.import_errors
    assert "point_in_time_feature_pipeline" in bag.dags
