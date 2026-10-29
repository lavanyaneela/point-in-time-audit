# The one promise this repository makes to a reviewer is that `make verify`
# passes from a fresh clone with no network. Everything else is convenience.

PYTHON ?= python3

.PHONY: verify lint test receipts experiments fixture sql demo report sweep set-handle clean

verify: lint test receipts

lint:
	$(PYTHON) -m ruff check src tests experiments tools dags

test:
	$(PYTHON) -m pytest --junitxml=junit.xml --cov=point_in_time_audit --cov-report=json --cov-report=term-missing:skip-covered

# Re-measures every published figure and fails if any document disagrees.
receipts:
	$(PYTHON) tools/collect_metrics.py
	$(PYTHON) tools/check_numbers.py
	$(PYTHON) tools/check_durations.py

# Runs E1, E2, E3 and E5 end to end and refreshes docs/experiments/.
# E4 is the delay sweep; it is slower and has its own target below.
experiments:
	$(PYTHON) experiments/e1_leak_measurement.py
	$(PYTHON) experiments/e2_feature_attribution.py
	$(PYTHON) experiments/e3_analyzer_detection.py
	$(PYTHON) experiments/e5_dialect_agreement.py

# Regenerates the committed event log fixture from the seeded generator.
# CI diffs the result against the committed bytes, so running this on an
# unchanged config must leave the tree clean.
fixture:
	$(PYTHON) tools/make_fixture.py

# Regenerates the committed dialect SQL from the feature and audit specs.
# Same contract as `fixture`: a clean tree on an unchanged spec.
sql:
	$(PYTHON) tools/emit_sql.py

# The delay sweep behind E4.
sweep:
	$(PYTHON) experiments/e4_delay_sweep.py

# Runs the audit against the committed fixture and prints the verdict.
# The scan exits 1 on this repository's corpus by design (it contains leaks),
# so the recipe reports the code instead of failing the make run. See the
# README section on exit codes before branching on this in automation.
demo:
	-$(PYTHON) -m point_in_time_audit.cli scan --sql sql/spark --registry fixtures/schema_registry.yaml; echo "pit-audit scan exited $$?"
	-$(PYTHON) -m point_in_time_audit.cli measure --fixture fixtures/event_log; echo "pit-audit measure exited $$?"

report:
	$(PYTHON) tools/render_report.py

# Inserts the real GitHub handle into badge URLs and clone commands.
set-handle:
	$(PYTHON) tools/set_handle.py $(HANDLE)

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.json junit.xml spark-warehouse
