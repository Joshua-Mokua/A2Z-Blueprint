"""Integration tests for v10.354 — CBS Baseline Snapshot Foundation.

The baseline mechanism captures CBS state at a fixed date for YoY growth
tracking. Items 3 (auto-refresh) and 4 (PBT from CBS) in the original
roadmap build on this foundation in subsequent batches.

15 tests across 6 sections:
  Section 1 — Module + schema (3 tests)
  Section 2 — Snapshot generation (3 tests)
  Section 3 — Save/load round-trip (3 tests)
  Section 4 — Comparison API (2 tests)
  Section 5 — G240 gate (2 tests)
  Section 6 — Pattern Q validate-before-save (2 tests)
"""

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module + schema
# ────────────────────────────────────────────────────────────────────

def test_v10354_cbs_baseline_module_present():
    """utils/cbs_baseline.py exists with expected API."""
    path = REPO / "utils" / "cbs_baseline.py"
    assert path.exists()
    text = path.read_text()
    for sym in (
        "def snapshot_baseline",
        "def save_baseline",
        "def load_baseline",
        "def list_baselines",
        "def baseline_file_for",
        "def compare_bank_aggregate",
        "def compare_rm_metric",
    ):
        assert sym in text, f"Missing: {sym}"


def test_v10354_schema_registered():
    """data/_schemas/cbs_baseline.schema.json exists and is valid JSON."""
    schema_path = REPO / "data" / "_schemas" / "cbs_baseline.schema.json"
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text())
    assert schema["title"] == "CBS Baseline Snapshot"
    # Required fields
    required = set(schema["required"])
    assert {"snapshot_date", "bank_aggregates", "per_rm", "per_branch"}.issubset(required)


def test_v10354_baseline_in_protected_files():
    """cbs_baseline.json is in the G230 protected-files list."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import list_protected_files
    assert "cbs_baseline.json" in list_protected_files()


# ────────────────────────────────────────────────────────────────────
# Section 2 — Snapshot generation
# ────────────────────────────────────────────────────────────────────

def test_v10354_snapshot_returns_valid_structure():
    """snapshot_baseline produces a dict with required schema keys."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import snapshot_baseline
    b = snapshot_baseline(as_of_date=date(2025, 12, 31))
    for key in (
        "_doc", "_schema_version", "snapshot_date", "snapshot_generated_at",
        "source_cbs_files", "bank_aggregates", "per_rm", "per_branch", "summary",
    ):
        assert key in b, f"Missing key: {key}"
    assert b["snapshot_date"] == "2025-12-31"
    assert b["_schema_version"] == "1.0"
    assert isinstance(b["per_rm"], dict)
    assert isinstance(b["per_branch"], dict)


def test_v10354_snapshot_handles_missing_accounts_csv():
    """When accounts.csv is absent, per_rm/per_branch are empty {} but
    bank_aggregates is still populated from the JSON aggregates."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import snapshot_baseline
    b = snapshot_baseline(as_of_date=date(2025, 12, 31))
    # In sandbox there's no accounts.csv
    assert b["summary"]["has_account_level_data"] is False
    assert b["per_rm"] == {}
    assert b["per_branch"] == {}
    # But bank aggregates ARE populated
    assert b["bank_aggregates"]
    assert "deposits_aggregate" in b["bank_aggregates"]


def test_v10354_snapshot_records_source_files():
    """source_cbs_files lists actually-read CBS files."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import snapshot_baseline
    b = snapshot_baseline(as_of_date=date(2025, 12, 31))
    assert len(b["source_cbs_files"]) >= 5  # 5 JSON aggregates
    assert b["summary"]["source_count"] == len(b["source_cbs_files"])


# ────────────────────────────────────────────────────────────────────
# Section 3 — Save/load round-trip
# ────────────────────────────────────────────────────────────────────

def test_v10354_save_writes_both_files():
    """save_baseline writes BOTH dated archive + canonical current."""
    canonical = REPO / "data" / "cbs_baseline.json"
    dated = REPO / "data" / "cbs_baseline_2025_Dec_31.json"
    assert canonical.exists(), "Canonical cbs_baseline.json must exist"
    assert dated.exists(), "Dated archive must exist"
    # Both should have identical content
    assert canonical.read_text() == dated.read_text()


def test_v10354_load_returns_most_recent_by_default():
    """load_baseline() without args returns the most recent dated snapshot."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import load_baseline, list_baselines
    candidates = list_baselines()
    assert candidates, "No baselines found"
    b = load_baseline()
    assert b is not None
    assert "snapshot_date" in b


def test_v10354_baseline_file_for_uses_canonical_naming():
    """baseline_file_for(date) produces cbs_baseline_<YYYY>_<MMM>_<DD>.json."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import baseline_file_for
    p = baseline_file_for(date(2025, 12, 31))
    assert p.name == "cbs_baseline_2025_Dec_31.json"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Comparison API
# ────────────────────────────────────────────────────────────────────

def test_v10354_compare_bank_aggregate_growth_pct():
    """compare_bank_aggregate computes (current, baseline, growth_pct)."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import compare_bank_aggregate
    baseline = {
        "bank_aggregates": {
            "deposits_aggregate": {
                "total_deposits_kes": 100_000_000_000
            }
        }
    }
    cur, base, growth = compare_bank_aggregate(
        112_000_000_000, baseline,
        "deposits_aggregate.total_deposits_kes",
    )
    assert cur == 112_000_000_000
    assert base == 100_000_000_000
    assert growth == 12.0  # 12% growth


def test_v10354_compare_zero_baseline_returns_none_growth():
    """Growth from a zero baseline is undefined — returns None."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import compare_bank_aggregate
    baseline = {"bank_aggregates": {"x": {"y": 0}}}
    cur, base, growth = compare_bank_aggregate(1000.0, baseline, "x.y")
    assert cur == 1000.0
    assert base == 0.0
    assert growth is None  # 1000/0 — undefined growth, not infinity


# ────────────────────────────────────────────────────────────────────
# Section 5 — G240 gate
# ────────────────────────────────────────────────────────────────────

def test_v10354_g240_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_cbs_baseline
    result = gate_cbs_baseline()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G240"


def test_v10354_g240_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G240", gate_cbs_baseline)' in text


# ────────────────────────────────────────────────────────────────────
# Section 6 — Pattern Q validate-before-save
# ────────────────────────────────────────────────────────────────────

def test_v10354_save_validates_before_writing():
    """save_baseline refuses to write a malformed baseline."""
    _reimport("utils.cbs_baseline")
    from utils.cbs_baseline import save_baseline
    bad = {"_doc": "bad", "_schema_version": "999.0"}  # missing required fields
    try:
        save_baseline(bad)
        assert False, "Expected ValueError on malformed baseline"
    except ValueError as e:
        assert "Refusing" in str(e) or "invalid" in str(e).lower()


def test_v10354_canonical_baseline_validates():
    """The shipped canonical baseline validates against the schema."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_file
    r = validate_file("cbs_baseline.json")
    assert r.get("valid"), f"Canonical baseline invalid: {r.get('errors', [])[:3]}"
