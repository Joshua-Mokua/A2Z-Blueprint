"""
tests/integration/test_pg_read_path_cutover_v10307.py
================================================================================
v10.307 — First PG read-path cutover. Proves the v10.306 migration
infrastructure works end-to-end by routing the
compliance_regulatory_returns composer through the existing
`_data_source.per_table.<table>` shim from v10.116.

Why compliance_regulatory_returns?
  - Has a v10.306 PG table (compliance_regulatory_returns)
  - Has a v10.306 migrator (migrate_compliance_regulatory_returns)
  - 60-record file (small, easy to verify byte-equivalent reads)
  - Already wired into Compliance cockpit tab 5
  - Has a documented HTTP endpoint

Approach:
  1. Add a `_load_table_via_shim()` helper to cockpit_read that
     calls into utils.actuals_engine._read_operational_table()
  2. Route compliance_regulatory_returns through it
  3. Default config = "json" (cockpit reads JSON, current
     behavior preserved)
  4. Setting per_table.compliance_regulatory_returns = "auto" or
     "pg_view" flips the read path without code changes
  5. Verification test: same composer returns same data either way
     when PG is empty (both fall back to JSON via auto mode)

Test sections:
  1. _load_table_via_shim helper exists
  2. Composer respects the shim (returns same data in default mode)
  3. Setting per_table = "auto" doesn't break the composer
  4. The new "pg_capable" status surface
  5. G197 audit gate
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir():
    d = tempfile.mkdtemp(prefix="pg_cutover_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Section 1 — Helper exists
# ============================================================

def test_load_table_via_shim_helper_exists():
    """cockpit_read must expose a helper that routes through
    the existing _data_source shim from actuals_engine."""
    from utils import cockpit_read
    assert hasattr(cockpit_read, "_load_table_via_shim"), (
        "cockpit_read must expose _load_table_via_shim() "
        "for PG read-path cutover"
    )


def test_load_table_via_shim_returns_list(tmp_data_dir):
    """Helper returns a list of dicts, same shape as
    _safe_load_json for list-keyed JSON files. Default
    config (no _data_source key) reads JSON exactly as
    before."""
    from utils.cockpit_read import _load_table_via_shim

    records = [{"id": "X", "value": 1}]
    (tmp_data_dir / "compliance_regulatory_returns.json"
     ).write_text(json.dumps(records))

    result = _load_table_via_shim(
        "compliance_regulatory_returns",
        data_dir=tmp_data_dir,
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "X"


def test_load_table_via_shim_handles_missing_file(tmp_data_dir):
    """Same defensive posture as _safe_load_json — missing
    file returns empty list."""
    from utils.cockpit_read import _load_table_via_shim
    result = _load_table_via_shim(
        "does_not_exist",
        data_dir=tmp_data_dir,
    )
    assert result == []


# ============================================================
# Section 2 — Composer behavior unchanged in default mode
# ============================================================

def test_compliance_regulatory_returns_uses_shim(tmp_data_dir):
    """The composer must route through _load_table_via_shim
    so flipping the config takes effect without code changes."""
    src = (REPO_ROOT / "utils" / "cockpit_read.py").read_text()
    # Find the composer body, tolerant of return annotation
    import re
    match = re.search(
        r"def compliance_regulatory_returns\([^)]*\)"
        r"\s*(?:->[^:]+)?:"
        r"(.*?)(?=\ndef\s|\Z)",
        src, re.DOTALL,
    )
    assert match, "Could not locate composer body"
    body = match.group(1)
    assert "_load_table_via_shim" in body, (
        "compliance_regulatory_returns must use "
        "_load_table_via_shim for the cutover to work"
    )


def test_compliance_returns_unchanged_in_default_config(
    tmp_data_dir,
):
    """With no _data_source config, the composer behaves
    exactly as before. Cockpit users see no change."""
    from utils.cockpit_read import compliance_regulatory_returns

    records = [
        {"id": "R1", "return_name": "CBK Q1",
         "due_date": "2026-03-31", "status": "filed",
         "on_time": True},
        {"id": "R2", "return_name": "KRA VAT",
         "due_date": "2026-04-30", "status": "pending",
         "on_time": None},
    ]
    # No integration_layer_config.json at all
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))

    result = compliance_regulatory_returns(data_dir=tmp_data_dir)
    assert isinstance(result, list)
    assert len(result) == 2
    ids = sorted(r["id"] for r in result)
    assert ids == ["R1", "R2"]


def test_compliance_returns_with_default_json_mode(
    tmp_data_dir,
):
    """Explicit `"default": "json"` config behaves the same
    as no config at all."""
    from utils.cockpit_read import compliance_regulatory_returns

    records = [
        {"id": "R1", "return_name": "X", "status": "filed"},
    ]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))
    (tmp_data_dir / "integration_layer_config.json").write_text(
        json.dumps({
            "_data_source": {
                "default": "json",
                "per_table": {},
            },
        }))

    result = compliance_regulatory_returns(data_dir=tmp_data_dir)
    assert len(result) == 1
    assert result[0]["id"] == "R1"


# ============================================================
# Section 3 — Auto mode falls back when PG unavailable
# ============================================================

def test_compliance_returns_auto_mode_falls_back_to_json(
    tmp_data_dir,
):
    """`auto` mode: try PG first, fall back to JSON silently
    when PG isn't reachable. In this test environment PG is
    not configured, so auto = JSON in practice."""
    from utils.cockpit_read import compliance_regulatory_returns

    records = [
        {"id": "R1", "return_name": "Y"},
    ]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))
    (tmp_data_dir / "integration_layer_config.json").write_text(
        json.dumps({
            "_data_source": {
                "default": "json",
                "per_table": {
                    "compliance_regulatory_returns": "auto",
                },
            },
        }))

    # PG isn't configured in the test env, so auto must fall
    # back gracefully to JSON. This is the cutover safety net.
    result = compliance_regulatory_returns(data_dir=tmp_data_dir)
    assert len(result) == 1


# ============================================================
# Section 4 — pg_capable status surface
# ============================================================

def test_cockpit_read_exposes_pg_capable_tables():
    """A new helper lists tables that have a PG migration in
    place. Operators can use it to know what's safely
    flippable. Returns at least the v10.306 set."""
    from utils.cockpit_read import pg_capable_tables
    tables = pg_capable_tables()
    assert isinstance(tables, (list, set, tuple))
    expected = {
        "audit_reviews",
        "compliance_regulatory_returns",
        "incidents",
        "nps_responses",
        "rcsa_register",
    }
    actual = set(tables)
    missing = expected - actual
    assert not missing, (
        f"pg_capable_tables() missing v10.306 tables: {missing}"
    )


# ============================================================
# Section 5 — Audit gate G197
# ============================================================

def test_g197_gate_exists_and_passes():
    from scripts.audit import GATES
    g197 = None
    for gid, fn in GATES:
        if gid == "G197":
            g197 = fn()
            break
    assert g197 is not None, "G197 not registered"
    assert g197["passed"], (
        f"G197 failed. Summary: {g197.get('summary', '')}. "
        f"Violations: {g197.get('violations', [])[:5]}"
    )


# ============================================================
# Section 6 — Existing tests still pass with shim
# ============================================================

def test_existing_compliance_returns_test_still_passes(
    tmp_data_dir,
):
    """The existing v10.301 test for the composer must keep
    passing — the cutover is backward-compatible."""
    from utils.cockpit_read import compliance_regulatory_returns

    # Same shape as test_compliance_live_cockpit's test data
    records = [
        {"id": "R1", "due_date": "2025-01-31",
         "filed_date": None, "status": "pending"},
        {"id": "R2", "due_date": "2025-03-31",
         "filed_date": "2025-03-25", "status": "filed",
         "on_time": True},
    ]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))
    result = compliance_regulatory_returns(data_dir=tmp_data_dir)
    assert len(result) == 2
