# Changelog

The format follows Keep a Changelog, versions follow semantic intent: the
measured leak first, the gate second, the full surface third. All three
landed in one concentrated build (the defense guide carries the provenance
note), with the tags minted together at the end of the session, each
placed on the commit where its capability completed.

## [0.3.0] - 2026-10-29

### Added
- SQL compiled to four dialects, 28 committed files, with E5 holding every
  dialect to the DuckDB reference value for value.
- The Airflow pipeline DAG that gates itself, structural tests over its
  task graph, and the optional real-loader import job.
- The Kafka round trip under the optional extra and its non blocking CI
  job against a real single node broker.
- E4, the arrival delay sweep, referee checked at every point, with the
  zero delay residual as its finding.
- The receipts mechanism in full: collector, checker with per anchor
  liveness and audited exemptions, duration sweep, and the prover that
  breaks every anchor of the headline figure on purpose.
- The composite action, the measured report page, the architecture
  diagram, the defense guide and the failure mode catalogue.

## [0.2.0] - 2026-10-29

### Added
- The static analyzer: schema registry, SQL scope analysis over sqlglot,
  DAG analysis over ast, table grain lineage, the exit code contract with
  refusal as a first class answer, and the pivot arithmetic.
- The ground truth corpus, 36 cases across 12 classes, with E3 measuring
  detection per class including the structurally invisible ones.
- The pit-audit CLI with scan, measure and pivot.

### Fixed
- The analyzer read a renamed parser field and certified the entire corpus
  by finding nothing; pinned by a regression test that requires findings
  at all.

## [0.1.0] - 2026-10-29

### Added
- The seeded world with fact and arrival timestamps, the Kafka shaped
  committed event log with a three identity manifest, the declarative
  feature spec, the Spark and DuckDB referee engines, paired leak
  measurement and per feature attribution, E1 and E2.

### Fixed
- Session timezone calendar arithmetic clipped one hour from every window
  crossing the spring forward transition; both engines pinned to UTC, the
  broken session kept reproducible by a test.
- The first world let one feature carry the whole gap as a label copy;
  recalibrated after E2 convicted it.
