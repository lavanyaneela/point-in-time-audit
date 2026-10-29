"""The receipts stay welded to their source of truth."""

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_collector():
    spec = importlib.util.spec_from_file_location(
        "collect_metrics", REPO / "tools" / "collect_metrics.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_anchors_match_the_collector_exactly():
    collector = _load_collector()
    committed = json.loads((REPO / "docs" / "metrics.json").read_text())
    assert committed["anchors"] == collector.ANCHORS, (
        "metrics.json was written by a different collector than the one in "
        "the tree; run make receipts"
    )


def test_every_committed_metric_has_an_anchor_entry():
    committed = json.loads((REPO / "docs" / "metrics.json").read_text())
    missing = [k for k in committed["metrics"] if k not in committed["anchors"]]
    assert missing == []


def test_every_checked_document_exists():
    committed = json.loads((REPO / "docs" / "metrics.json").read_text())
    missing = [d for d in committed["checked_documents"] if not (REPO / d).exists()]
    assert missing == []


def test_the_collector_checks_the_documents_the_charter_names():
    collector = _load_collector()
    assert "README.md" in collector.CHECKED_DOCUMENTS
    assert "docs/defense-guide.md" in collector.CHECKED_DOCUMENTS
    assert any(d.startswith("docs/adr/") for d in collector.CHECKED_DOCUMENTS)
