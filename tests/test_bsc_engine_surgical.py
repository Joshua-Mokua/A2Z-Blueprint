"""tests/test_bsc_engine_surgical.py — v10.106 surgical top-up for
utils/bsc_engine.py.

v10.105 took bsc_engine 74.2% → 92.7% across 29 tests targeting 5
categories of uncovered paths. Three categories of edge cases remained
uncovered, totaling 17 specific lines:

  - Line 141:        KPI with `code` field (not just `id`) added to index
  - Lines 241, 248:  validate rejects non-string staff_code / kpi_id
  - Lines 326-328:   _persist load_json failure path
  - Lines 347-349:   _persist save_json failure path
  - Lines 361-362:   _audit exception swallow
  - Lines 406-408:   submit calls _audit("BSC_PERSIST_FAILED") on persist failure
  - Lines 461-462:   submit_batch TypeError catch
  - Lines 509-510:   get_actual Decimal conversion fails

Lines 593-595 (the _self_test AssertionError handler) are deliberately
NOT covered here. That's debug-output code in a path that only fires
when the engine's own internal asserts fail — low value, awkward to
test cleanly without monkey-patching internal state.

Target: 92.7% → ≥95% (Standard #4 spec target).
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Same fixture pattern as tests/test_bsc_engine.py + closeout."""
    from utils import bsc_engine

    (tmp_path / "kpi_library.json").write_text(json.dumps({
        "kpis": [{"id": "DEP_GROWTH", "name": "Deposit Growth"}],
        "active_kpis": ["DEP_GROWTH"],
    }), encoding="utf-8")
    (tmp_path / "users.json").write_text(json.dumps({
        "william001": {"staff_code": "300001"},
    }), encoding="utf-8")

    monkeypatch.setattr(bsc_engine, "DATA_DIR", tmp_path)
    bsc_engine._refresh_indexes()
    return tmp_path


# ── Line 141 — KPI with code field ────────────────────────────────

def test_kpi_with_code_field_added_to_index(tmp_path, monkeypatch):
    """A KPI dict that has both `id` and `code` should get indexed
    under both. The existing fixture's KPI has only `id`; this test
    exercises the line-141 branch where `code` is also indexed."""
    (tmp_path / "kpi_library.json").write_text(json.dumps({
        "kpis": [{
            "id": "K001",
            "code": "DEP_GROWTH_SEMANTIC",
            "name": "Deposit Growth",
        }],
        "active_kpis": ["K001"],
    }), encoding="utf-8")
    (tmp_path / "users.json").write_text("{}", encoding="utf-8")

    from utils import bsc_engine
    monkeypatch.setattr(bsc_engine, "DATA_DIR", tmp_path)
    bsc_engine._refresh_indexes()

    idx = bsc_engine._load_kpi_index()
    # Both keys point to the same KPI dict
    assert "K001" in idx
    assert "DEP_GROWTH_SEMANTIC" in idx
    # And the same dict (line 141: idx[str(code)] = kpi)
    assert idx["DEP_GROWTH_SEMANTIC"]["id"] == "K001"


# ── Lines 241, 248 — validate non-string staff_code / kpi_id ──────

def test_validate_rejects_non_string_staff_code(tmp_data_dir):
    """staff_code passed as int (not string) → rejected with specific
    error message. Existing tests use empty strings or whitespace;
    this hits the `not isinstance(staff_code, str)` branch."""
    from utils import bsc_engine
    record = {
        "staff_code": 300001,  # int, not str
        "kpi_id": "DEP_GROWTH",
        "value": 12.5,
        "period": "2026-04",
        "source_module": "test",
    }
    ok, err = bsc_engine.validate(record)
    assert ok is False
    assert "staff_code" in err and "non-empty string" in err


def test_validate_rejects_non_string_kpi_id(tmp_data_dir):
    """kpi_id as int (or any non-string) → rejected. Hits line 248."""
    from utils import bsc_engine
    record = {
        "staff_code": "300001",
        "kpi_id": 12345,  # int, not str
        "value": 12.5,
        "period": "2026-04",
        "source_module": "test",
    }
    ok, err = bsc_engine.validate(record)
    assert ok is False
    assert "kpi_id" in err and "non-empty string" in err


# ── Lines 326-328 — _persist load failure ─────────────────────────

def test_persist_handles_load_failure(tmp_data_dir, monkeypatch):
    """When db.load_json raises during _persist's read, submit returns
    (False, 'persistence load failed: ...') rather than crashing.

    Hits lines 326-328 (the except block in _persist's load section)
    and lines 406-408 (submit's BSC_PERSIST_FAILED audit) in one
    chained exercise.
    """
    from utils import bsc_engine, db as a2z_db_mod

    # Force load_json to raise during persist (but NOT during the
    # initial index loads — they've already cached above)
    call_count = {"n": 0}
    original_load = a2z_db_mod.db.load_json

    def selective_raise(path, *a, **kw):
        # Let kpi_library + users loads succeed (they're cached anyway,
        # but defensive). Only raise on the period's actuals file.
        path_str = str(path)
        if "actuals" in path_str.lower() or path_str.endswith(".json"):
            if "kpi_library" not in path_str and "users" not in path_str:
                raise OSError("simulated load failure")
        return original_load(path, *a, **kw)

    monkeypatch.setattr(
        a2z_db_mod.db, "load_json", selective_raise)

    # Submit triggers _persist → load_json (raises) → returns (False, ...)
    # → submit calls _audit("BSC_PERSIST_FAILED") → returns (False, ...)
    ok, msg = bsc_engine.submit(
        "300001", "DEP_GROWTH", 12.5, "2026-04", "test")
    assert ok is False
    assert "persistence" in msg.lower() and "load" in msg.lower()


# ── Lines 347-349 — _persist save failure ─────────────────────────

def test_persist_handles_save_failure(tmp_data_dir, monkeypatch):
    """When db.save_json raises during _persist's write, submit returns
    (False, 'persistence save failed: ...').

    Different path than load failure — the existing record loads
    successfully, but writing the updated list fails. Hits lines
    347-349 (save's except block) and lines 406-408 (BSC_PERSIST_FAILED).
    """
    from utils import bsc_engine, db as a2z_db_mod

    def raising_save(*a, **kw):
        raise OSError("simulated save failure")
    monkeypatch.setattr(
        a2z_db_mod.db, "save_json", raising_save)

    ok, msg = bsc_engine.submit(
        "300001", "DEP_GROWTH", 12.5, "2026-04", "test")
    assert ok is False
    assert "persistence" in msg.lower() and "save" in msg.lower()


# ── Lines 361-362 — _audit exception swallow ──────────────────────

def test_audit_swallows_exceptions(tmp_data_dir, monkeypatch):
    """If core_audit.audit_log raises, _audit logs at debug level and
    returns. Submit succeeds anyway because audit failures must never
    block the primary write path.

    Hits lines 361-362 (_audit's except block).
    """
    # Patch core_audit.audit_log to raise
    from utils import core_audit
    monkeypatch.setattr(
        core_audit, "audit_log",
        lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("audit_log crash")))

    # Submit should succeed despite the audit raising
    from utils import bsc_engine
    ok, msg = bsc_engine.submit(
        "300001", "DEP_GROWTH", 12.5, "2026-04", "test")
    assert ok is True, (
        f"Submit must not be blocked by audit failures; got {ok}/{msg}")


# ── Lines 461-462 — submit_batch TypeError catch ──────────────────

def test_submit_batch_handles_type_error(tmp_data_dir, monkeypatch):
    """If submit() raises TypeError (e.g. from a bad signature scenario
    we engineer via monkeypatch), submit_batch catches and reports it
    as 'submit signature error: ...' instead of crashing the batch.

    Hits lines 461-462 (the except TypeError block in submit_batch).
    """
    from utils import bsc_engine

    # Patch submit to raise TypeError (simulates a signature mismatch)
    original_submit = bsc_engine.submit

    def raising_submit(**kwargs):
        raise TypeError("simulated signature mismatch")
    monkeypatch.setattr(bsc_engine, "submit", raising_submit)

    batch = [
        {"staff_code": "300001", "kpi_id": "DEP_GROWTH",
         "value": 1.0, "period": "2026-04"},
    ]
    result = bsc_engine.submit_batch(
        batch, source_module="test", actor="t")

    # Restore to avoid leaking to other tests
    monkeypatch.setattr(bsc_engine, "submit", original_submit)

    assert result["ok"] == 0
    assert result["rejected"] == 1
    assert len(result["errors"]) == 1
    assert "signature" in result["errors"][0]["error"].lower()


# ── Lines 509-510 — get_actual Decimal failure ────────────────────

def test_get_actual_returns_none_when_decimal_conversion_fails(
        tmp_path, monkeypatch):
    """If a stored value can't be converted to Decimal (e.g. a dict
    or list got stored), get_actual returns None instead of crashing.

    Hits lines 509-510 (get_actual's Decimal-coercion except block).
    """
    # Build a malformed actuals file directly
    (tmp_path / "kpi_library.json").write_text(json.dumps({
        "kpis": [{"id": "DEP_GROWTH", "name": "Deposit Growth"}],
        "active_kpis": ["DEP_GROWTH"],
    }), encoding="utf-8")
    (tmp_path / "users.json").write_text(json.dumps({
        "william001": {"staff_code": "300001"},
    }), encoding="utf-8")

    from utils import bsc_engine
    monkeypatch.setattr(bsc_engine, "DATA_DIR", tmp_path)
    bsc_engine._refresh_indexes()

    # Resolve the file _persist would write to
    fpath = bsc_engine._file_for_period("2026-04")
    fpath.parent.mkdir(parents=True, exist_ok=True)
    # Write a record whose value is unconvertible to Decimal
    fpath.write_text(json.dumps([{
        "staff_code": "300001",
        "kpi_id": "DEP_GROWTH",
        "value": {"nested": "dict"},  # Decimal(str({...})) fails
        "period": "2026-04",
        "source_module": "test",
        "submitted_at": "2026-04-01T00:00:00Z",
        "idem_hash": "fake-hash",
    }]), encoding="utf-8")

    result = bsc_engine.get_actual(
        "300001", "DEP_GROWTH", "2026-04")
    assert result is None
