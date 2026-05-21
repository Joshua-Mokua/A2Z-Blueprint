"""tests/test_bsc_engine.py — exercise the BSC central engine.

The engine is the single chokepoint for performance data (addendum
Standards #1 + #2). These tests cover every path through the public
API: submit, submit_batch, get_actual, get_actuals_for_period, validate.

Coverage targets:
  - Happy path (create + read back)
  - Idempotency (replay → update, hash stability)
  - Validation: every fail-closed check
  - Period normalisation (monthly, quarterly, malformed)
  - Bounds (MIN_VALUE, MAX_VALUE, NaN, infinity, bool)
  - Batch (mixed valid/invalid, source_module override)
  - Metadata flat-scalar filter
"""
from __future__ import annotations

import math
from decimal import Decimal

import pytest


# ── Happy path ──────────────────────────────────────────────────────────
class TestHappyPath:
    def test_submit_creates_record(self, tmp_data_dir):
        from utils.bsc_engine import submit
        ok, msg = submit(
            staff_code    = "300001",
            kpi_id        = "K001",
            value         = 12.5,
            period        = "2026-04",
            source_module = "test",
        )
        assert ok is True
        assert msg == "created"

    def test_submit_with_actor_and_metadata(self, tmp_data_dir):
        from utils.bsc_engine import submit
        ok, msg = submit(
            staff_code    = "300001",
            kpi_id        = "K001",
            value         = 12.5,
            period        = "2026-04",
            source_module = "test",
            actor         = "tester",
            metadata      = {"detail": "From unit test", "line": 42},
        )
        assert ok and msg == "created"

    def test_get_actual_returns_decimal(self, tmp_data_dir):
        from utils.bsc_engine import submit, get_actual
        submit(
            staff_code    = "300001", kpi_id = "K001", value = 99.7,
            period        = "2026-04", source_module = "test",
        )
        v = get_actual(staff_code="300001", kpi_id="K001", period="2026-04")
        assert v == Decimal("99.7")
        assert isinstance(v, Decimal)

    def test_get_actual_returns_none_for_missing(self, tmp_data_dir):
        from utils.bsc_engine import get_actual
        v = get_actual(staff_code="300001", kpi_id="K001", period="2026-04")
        assert v is None


# ── Idempotency (replay → update) ──────────────────────────────────────
class TestIdempotency:
    def test_replay_updates_not_duplicates(self, tmp_data_dir):
        from utils.bsc_engine import submit, get_actuals_for_period
        # First submission
        ok, msg = submit(
            staff_code    = "300001", kpi_id = "K001", value = 10,
            period        = "2026-04", source_module = "test",
        )
        assert ok and msg == "created"
        # Second submission with same key fields → update
        ok, msg = submit(
            staff_code    = "300001", kpi_id = "K001", value = 20,
            period        = "2026-04", source_module = "test",
        )
        assert ok and msg == "updated"
        # Storage has one record, not two
        records = get_actuals_for_period("2026-04")
        assert len(records) == 1
        assert records[0]["value"] == 20.0

    def test_different_source_creates_separate_record(self, tmp_data_dir):
        from utils.bsc_engine import submit, get_actuals_for_period
        submit("300001", "K001", 10, "2026-04", "etl_a")
        submit("300001", "K001", 11, "2026-04", "etl_b")
        records = get_actuals_for_period("2026-04")
        # Same staff/kpi/period but different source — TWO records
        assert len(records) == 2

    def test_idempotency_hash_stable(self, tmp_data_dir):
        from utils.bsc_engine import _idempotency_hash
        h1 = _idempotency_hash("300001", "K001", "2026-04", "test")
        h2 = _idempotency_hash("300001", "K001", "2026-04", "test")
        assert h1 == h2
        # Different inputs → different hash
        h3 = _idempotency_hash("300001", "K001", "2026-04", "OTHER")
        assert h1 != h3


# ── Validation: each fail-closed check ─────────────────────────────────
@pytest.mark.security
class TestValidation:
    def test_missing_staff_code_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "kpi_id": "K001", "value": 1,
            "period": "2026-04", "source_module": "test",
        })
        assert not ok
        assert "staff_code" in err

    def test_unknown_user_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "999999", "kpi_id": "K001", "value": 1,
            "period": "2026-04", "source_module": "test",
        })
        assert not ok
        assert "users registry" in err

    def test_unknown_kpi_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "BOGUS", "value": 1,
            "period": "2026-04", "source_module": "test",
        })
        assert not ok
        assert "kpi_library" in err

    def test_nan_value_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "K001", "value": float("nan"),
            "period": "2026-04", "source_module": "test",
        })
        assert not ok
        assert "finite" in err

    def test_infinity_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "K001", "value": float("inf"),
            "period": "2026-04", "source_module": "test",
        })
        assert not ok

    def test_bool_value_rejected(self, tmp_data_dir):
        """bool is a subclass of int — disallow explicitly. A True
        sneaking in as 1.0 would be a category error in performance data."""
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "K001", "value": True,
            "period": "2026-04", "source_module": "test",
        })
        assert not ok

    def test_string_value_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "K001", "value": "twelve",
            "period": "2026-04", "source_module": "test",
        })
        assert not ok

    def test_decimal_value_accepted(self, tmp_data_dir):
        from utils.bsc_engine import submit
        ok, msg = submit(
            "300001", "K001", Decimal("12.345"), "2026-04", "test",
        )
        assert ok

    def test_int_value_accepted(self, tmp_data_dir):
        from utils.bsc_engine import submit
        ok, _ = submit("300001", "K001", 42, "2026-04", "test")
        assert ok

    def test_empty_source_module_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "K001", "value": 1,
            "period": "2026-04", "source_module": "",
        })
        assert not ok
        assert "source_module" in err

    def test_whitespace_source_module_rejected(self, tmp_data_dir):
        from utils.bsc_engine import validate
        ok, err = validate({
            "staff_code": "300001", "kpi_id": "K001", "value": 1,
            "period": "2026-04", "source_module": "   ",
        })
        assert not ok


# ── Period format ──────────────────────────────────────────────────────
class TestPeriodFormat:
    @pytest.mark.parametrize("period,expected", [
        ("2026-01", "2026-01"),
        ("2026-12", "2026-12"),
        ("2026-Q1", "2026-Q1"),
        ("2026-Q4", "2026-Q4"),
        ("2026-q2", "2026-Q2"),  # lowercase Q normalised
    ])
    def test_valid_periods(self, tmp_data_dir, period, expected):
        from utils.bsc_engine import _normalise_period
        assert _normalise_period(period) == expected

    @pytest.mark.parametrize("period", [
        "2026-13",      # month 13
        "2026-00",      # month 00
        "2026-Q5",      # quarter 5
        "2026-Q0",      # quarter 0
        "April 2026",
        "2026/04",
        "26-04",
        "",
        "  ",
        None,
        42,
    ])
    def test_invalid_periods_rejected(self, tmp_data_dir, period):
        from utils.bsc_engine import _normalise_period
        assert _normalise_period(period) is None


# ── Bounds ─────────────────────────────────────────────────────────────
class TestBounds:
    def test_value_at_max_accepted(self, tmp_data_dir):
        from utils.bsc_engine import _coerce_value, MAX_VALUE
        # At the boundary
        v = _coerce_value(MAX_VALUE)
        assert v is not None and v == MAX_VALUE

    def test_value_above_max_rejected(self, tmp_data_dir):
        from utils.bsc_engine import _coerce_value, MAX_VALUE
        assert _coerce_value(MAX_VALUE * 10) is None

    def test_value_at_min_accepted(self, tmp_data_dir):
        from utils.bsc_engine import _coerce_value, MIN_VALUE
        assert _coerce_value(MIN_VALUE) == MIN_VALUE

    def test_value_below_min_rejected(self, tmp_data_dir):
        from utils.bsc_engine import _coerce_value, MIN_VALUE
        assert _coerce_value(MIN_VALUE * 10) is None


# ── Batch ──────────────────────────────────────────────────────────────
class TestBatch:
    def test_all_valid_batch(self, tmp_data_dir):
        from utils.bsc_engine import submit_batch
        result = submit_batch(
            records = [
                {"staff_code": "300001", "kpi_id": "K001", "value": 1, "period": "2026-01"},
                {"staff_code": "300002", "kpi_id": "K001", "value": 2, "period": "2026-01"},
            ],
            source_module = "test_etl",
        )
        assert result["ok"] == 2
        assert result["rejected"] == 0
        assert result["created"] == 2

    def test_mixed_batch(self, tmp_data_dir):
        from utils.bsc_engine import submit_batch
        result = submit_batch(
            records = [
                {"staff_code": "300001", "kpi_id": "K001", "value": 1, "period": "2026-01"},
                {"staff_code": "BAD",    "kpi_id": "K001", "value": 2, "period": "2026-01"},
                {"staff_code": "300002", "kpi_id": "BOGUS","value": 3, "period": "2026-01"},
            ],
            source_module = "test_etl",
        )
        assert result["ok"] == 1
        assert result["rejected"] == 2
        assert len(result["errors"]) == 2

    def test_batch_overrides_per_record_source_module(self, tmp_data_dir):
        from utils.bsc_engine import submit_batch, get_actuals_for_period
        submit_batch(
            records = [
                # Caller tries to set source_module per-record; should be overridden
                {"staff_code": "300001", "kpi_id": "K001", "value": 1,
                 "period": "2026-04", "source_module": "lying"},
            ],
            source_module = "true_source",
        )
        records = get_actuals_for_period("2026-04")
        assert len(records) == 1
        assert records[0]["source_module"] == "true_source"

    def test_batch_with_non_dict_records(self, tmp_data_dir):
        from utils.bsc_engine import submit_batch
        result = submit_batch(
            records = [
                {"staff_code": "300001", "kpi_id": "K001", "value": 1, "period": "2026-01"},
                "not a dict",
                None,
                42,
            ],
            source_module = "test",
        )
        assert result["ok"] == 1
        assert result["rejected"] == 3

    def test_batch_with_non_list_records(self, tmp_data_dir):
        from utils.bsc_engine import submit_batch
        result = submit_batch("not a list", source_module="test")
        assert result["ok"] == 0
        assert result["errors"]


# ── Metadata filter ────────────────────────────────────────────────────
class TestMetadata:
    def test_metadata_keeps_flat_scalars(self, tmp_data_dir):
        from utils.bsc_engine import submit, get_actuals_for_period
        submit(
            "300001", "K001", 1, "2026-04", "test",
            metadata={"text": "ok", "n": 42, "f": 1.5, "b": True, "n0": None},
        )
        records = get_actuals_for_period("2026-04")
        meta = records[0]["metadata"]
        assert meta == {"text": "ok", "n": 42, "f": 1.5, "b": True, "n0": None}

    def test_metadata_strips_nested(self, tmp_data_dir):
        from utils.bsc_engine import submit, get_actuals_for_period
        submit(
            "300001", "K001", 1, "2026-04", "test",
            metadata={"keep": "yes", "nested": {"drop": "me"}, "list": [1, 2]},
        )
        records = get_actuals_for_period("2026-04")
        meta = records[0]["metadata"]
        assert "keep" in meta
        assert "nested" not in meta
        assert "list" not in meta


# ── Audit calls (Standard #6) ──────────────────────────────────────────
@pytest.mark.security
class TestAuditCompliance:
    def test_audit_log_called_on_success(self, tmp_data_dir, monkeypatch):
        """Every successful submission MUST emit an audit_log entry per
        addendum Standard #6 (audit/logging/traceability)."""
        seen = []

        def _stub(action, user, detail, module=None):
            seen.append((action, user, module))

        # Patch the audit_log import target
        import utils.bsc_engine as _bsc
        monkeypatch.setattr(_bsc, "_audit", lambda a, u, d: seen.append((a, u, "bsc_engine")))

        from utils.bsc_engine import submit
        submit("300001", "K001", 1, "2026-04", "test", actor="tester")
        # At least one BSC_SUBMIT entry
        actions = [a for a, _, _ in seen]
        assert "BSC_SUBMIT" in actions

    def test_audit_log_called_on_rejection(self, tmp_data_dir, monkeypatch):
        seen = []
        import utils.bsc_engine as _bsc
        monkeypatch.setattr(_bsc, "_audit", lambda a, u, d: seen.append(a))

        from utils.bsc_engine import submit
        submit("999999", "K001", 1, "2026-04", "test")  # unknown user
        assert "BSC_REJECTED" in seen
