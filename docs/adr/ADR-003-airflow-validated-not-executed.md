# ADR-003: Airflow validated structurally rather than executed

Status: accepted.

## Decision

The pipeline DAG in `dags/` is a real Airflow DAG: real operators, a real
sensor, real dependency edges, and the repository's own audit as its gate
task. Its structure is pinned by tests that parse the source with `ast`,
the analyzer reads it the same way, and an optional CI job loads it through
Airflow's own `DagBag` to prove it imports cleanly. No scheduler executes
it, in CI or anywhere else in this repository.

## Why the line sits here

Running a scheduler adds three things: proof that task code executes under
Airflow's serialization and templating, observed retry and timeout
behaviour, and sensor poking against a live warehouse. All three require a
long-running service and a warehouse connection, which breaks the rule that
`make verify` passes from a fresh clone with no network and no credentials,
and that rule is what makes every other number in this repository checkable
by a stranger. The trade is explicit: structural truth is bought at the
price of runtime truth, and nothing in the README implies the second.

What structural validation does establish is the part of the argument this
repository actually makes: the task order. The arrival watermark sensor
gates the build and the training task sits downstream of it, which is the
one scheduling property the SQL alone cannot carry, and it is checked both
by the pinned-structure tests and by the analyzer's sensor rule.

## What running a scheduler would add, named

Executing the DAG against a real warehouse would add: evidence that the
sensor's SQL template renders and pokes correctly, evidence that the
`build_features` task's file-referenced SQL resolves under Airflow's
template search path rather than this repository's resolver, and observed
behaviour when the sensor times out. Anyone extending this repository
toward that should start with a `docker compose` Airflow and point the
`warehouse` connection at DuckDB; the DAG was written so that nothing about
it needs to change.

## The limit the analyzer inherits from this boundary

A sensor is recognised structurally, by its operator and name, which is
also why a sensor waiting on the wrong signal is invisible (ADR-004, and
the wrong_sensor_semantics class E3 scores at zero). Executing a scheduler
would not fix that; only semantics would, and semantics are not static.
