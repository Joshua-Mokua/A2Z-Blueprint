"""tests/test_volume_four_batch.py — Standards #31-#35 (v5.50).

Coverage:
  Standard #31 — FLEXCUBE Staging Schema
  Standard #32 — FlexcubeConnectionManager
  Standard #33 — ETL DAG
  Standard #34 — FLEXCUBE_TO_A2Z_MAPPINGS
  Standard #35 — ReconciliationEngine

One harness test:
  - test_reconciliation_correctness_meets_99_percent → G42
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
RECON_FIXTURES = ROOT / "tests" / "fixtures" / "reconciliation_scenarios.json"
RECON_RESULTS  = ROOT / "reconciliation_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestFilesExist:
    def test_staging_module(self):
        assert (ROOT / "utils" / "flexcube_staging.py").exists()

    def test_connection_module(self):
        assert (ROOT / "utils" / "flexcube_connection.py").exists()

    def test_etl_dag_module(self):
        assert (ROOT / "utils" / "flexcube_etl_dag.py").exists()

    def test_mappings_module(self):
        assert (ROOT / "utils" / "flexcube_mappings.py").exists()

    def test_reconciliation_engine_module(self):
        assert (ROOT / "utils" / "reconciliation_engine.py").exists()

    def test_reconciliation_fixtures(self):
        assert RECON_FIXTURES.exists()
        data = json.loads(RECON_FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 10


# ═══════════════════════════════════════════════════════════════════════
# Standard #31 — Staging schema
# ═══════════════════════════════════════════════════════════════════════

class TestStandard31:
    def test_extract_control_has_spec_columns(self):
        from utils.flexcube_staging import (
            build_extract_control_ddl, ddl_contains_required_columns,
            EXTRACT_CONTROL_REQUIRED_COLUMNS,
        )
        ddl = build_extract_control_ddl()
        check = ddl_contains_required_columns(ddl, EXTRACT_CONTROL_REQUIRED_COLUMNS)
        assert check["valid"], f"missing: {check['missing']}"

    def test_sttm_customer_raw_has_spec_columns(self):
        from utils.flexcube_staging import (
            build_sttm_customer_raw_ddl, ddl_contains_required_columns,
            STTM_CUSTOMER_RAW_REQUIRED_COLUMNS,
        )
        ddl = build_sttm_customer_raw_ddl()
        check = ddl_contains_required_columns(ddl, STTM_CUSTOMER_RAW_REQUIRED_COLUMNS)
        assert check["valid"], f"missing: {check['missing']}"

    def test_validate_staging_schema(self):
        from utils.flexcube_staging import validate_staging_schema
        v = validate_staging_schema()
        assert v["valid"], f"errors: {v['errors']}"
        assert v["tables_validated"] == 2

    def test_full_schema_combines_both(self):
        from utils.flexcube_staging import build_full_staging_schema_ddl
        ddl = build_full_staging_schema_ddl()
        assert "extract_control" in ddl
        assert "sttm_customer_raw" in ddl


# ═══════════════════════════════════════════════════════════════════════
# Standard #32 — Connection manager
# ═══════════════════════════════════════════════════════════════════════

class TestStandard32:
    def test_class_has_spec_method(self):
        from utils.flexcube_connection import FlexcubeConnectionManager
        assert hasattr(FlexcubeConnectionManager, "execute_query")

    def test_spec_literals(self):
        from utils.flexcube_connection import FlexcubeConnectionManager
        assert FlexcubeConnectionManager.MAX_ATTEMPTS == 3
        assert FlexcubeConnectionManager.WAIT_MULTIPLIER == 1.0

    def test_retries_three_times_then_raises(self):
        from utils.flexcube_connection import FlexcubeConnectionManager

        class _AlwaysFail:
            attempts = 0
            def connect(self):
                self.attempts += 1
                raise ConnectionError(f"fail #{self.attempts}")

        eng = _AlwaysFail()
        mgr = FlexcubeConnectionManager(engine=eng, sleep_fn=lambda s: None)
        with pytest.raises(ConnectionError):
            mgr.execute_query("SELECT 1")
        assert eng.attempts == 3

    def test_exponential_backoff_timing(self):
        from utils.flexcube_connection import FlexcubeConnectionManager

        class _Fail2:
            attempts = 0
            def connect(self):
                self.attempts += 1
                if self.attempts < 3:
                    raise ConnectionError("fail")
                class _C:
                    def execute(self, q, p=None):
                        class _Cur:
                            description = [("c",)]
                            def fetchall(self): return []
                        return _Cur()
                    def __enter__(self): return self
                    def __exit__(self, *a): pass
                return _C()

        waits = []
        mgr = FlexcubeConnectionManager(
            engine=_Fail2(), sleep_fn=lambda s: waits.append(s),
        )
        mgr.execute_query("SELECT 1")
        assert waits == [1.0, 2.0]    # multiplier=1, exp(2^0)=1, exp(2^1)=2

    def test_empty_query_raises(self):
        from utils.flexcube_connection import FlexcubeConnectionManager
        mgr = FlexcubeConnectionManager(engine=object())
        with pytest.raises(ValueError):
            mgr.execute_query("")
        with pytest.raises(ValueError):
            mgr.execute_query(None)

    def test_missing_engine_raises(self):
        from utils.flexcube_connection import FlexcubeConnectionManager
        mgr = FlexcubeConnectionManager()
        with pytest.raises(RuntimeError):
            mgr.execute_query("SELECT 1")


# ═══════════════════════════════════════════════════════════════════════
# Standard #33 — ETL DAG
# ═══════════════════════════════════════════════════════════════════════

class TestStandard33:
    def test_dag_id_and_schedule(self):
        from utils.flexcube_etl_dag import build_dag_spec
        spec = build_dag_spec()
        assert spec.dag_id == "flexcube_daily_etl"
        assert spec.schedule_interval == "0 1 * * *"

    def test_all_four_task_ids_present(self):
        from utils.flexcube_etl_dag import build_dag_spec
        spec = build_dag_spec()
        ids = spec.task_ids()
        for tid in ("extract_sttm_customer", "transform_to_customer_master",
                    "load_clean", "submit_to_bsc"):
            assert tid in ids

    def test_dependency_chain_linear(self):
        from utils.flexcube_etl_dag import build_dag_spec
        spec = build_dag_spec()
        deps = set(spec.dependencies)
        assert ("extract_sttm_customer", "transform_to_customer_master") in deps
        assert ("transform_to_customer_master", "load_clean") in deps
        assert ("load_clean", "submit_to_bsc") in deps

    def test_module_exposes_dag_symbol(self):
        import utils.flexcube_etl_dag as m
        assert hasattr(m, "dag")

    def test_extract_table_raises_without_connection(self):
        from utils.flexcube_etl_dag import extract_table
        with pytest.raises(RuntimeError):
            extract_table()

    def test_transform_uses_spec_field_names(self):
        from utils.flexcube_etl_dag import transform_customers
        result = transform_customers(
            raw_rows=[{"cust_no": "C1", "cust_name": "Big Corp"}]
        )
        assert result["rows_transformed"] == 1
        out = result["transformed_rows"][0]
        assert out["customer_code"] == "C1"
        assert out["customer_name"] == "Big Corp"


# ═══════════════════════════════════════════════════════════════════════
# Standard #34 — Mappings
# ═══════════════════════════════════════════════════════════════════════

class TestStandard34:
    def test_spec_entry_byte_for_byte(self):
        from utils.flexcube_mappings import FLEXCUBE_TO_A2Z_MAPPINGS
        spec = FLEXCUBE_TO_A2Z_MAPPINGS["sttm_customer"]
        assert spec["a2z_table"] == "customer.customer_master"
        assert spec["fields"]["cust_no"] == "customer_code"
        assert spec["fields"]["cust_name"] == "customer_name"

    def test_validate_catalog(self):
        from utils.flexcube_mappings import validate_mappings_catalog
        v = validate_mappings_catalog()
        assert v["valid"]

    def test_lookups_return_spec_values(self):
        from utils.flexcube_mappings import lookup_a2z_table, lookup_a2z_field
        assert lookup_a2z_table("sttm_customer") == "customer.customer_master"
        assert lookup_a2z_field("sttm_customer", "cust_no") == "customer_code"

    def test_lookup_misses_return_none(self):
        from utils.flexcube_mappings import lookup_a2z_table, lookup_a2z_field
        assert lookup_a2z_table("nonexistent") is None
        assert lookup_a2z_field("sttm_customer", "made_up") is None
        assert lookup_a2z_field("nonexistent", "cust_no") is None


# ═══════════════════════════════════════════════════════════════════════
# Standard #35 — ReconciliationEngine
# ═══════════════════════════════════════════════════════════════════════

class TestStandard35:
    def test_class_has_spec_methods(self):
        from utils.reconciliation_engine import ReconciliationEngine
        eng = ReconciliationEngine()
        assert hasattr(eng, "run_full_reconciliation")
        assert hasattr(eng, "compare")
        assert hasattr(eng, "log_break")
        assert hasattr(ReconciliationEngine, "THRESHOLDS")

    def test_spec_literal_checks(self):
        from utils.reconciliation_engine import ReconciliationEngine, DEFAULT_CHECKS
        assert "customer_count"  in DEFAULT_CHECKS
        assert "deposit_balance" in DEFAULT_CHECKS
        assert "loan_balance"    in DEFAULT_CHECKS

    def test_empty_date_returns_empty(self):
        from utils.reconciliation_engine import ReconciliationEngine
        assert ReconciliationEngine().run_full_reconciliation("") == {}

    def test_break_logged_above_threshold(self):
        from utils.reconciliation_engine import ReconciliationEngine
        breaks = []
        eng = ReconciliationEngine(
            flexcube_count_fn=lambda c, d: Decimal("100") if c == "customer_count" else Decimal("0"),
            a2z_count_fn=lambda c, d: Decimal("105") if c == "customer_count" else Decimal("0"),
            break_log_fn=lambda r: breaks.append(r),
        )
        r = eng.run_full_reconciliation("2026-04-29")
        # customer_count threshold=0, 5-diff is a break
        assert len(breaks) == 1
        assert breaks[0]["check_name"] == "customer_count"

    def test_stale_extract_blocks_pass(self):
        from utils.reconciliation_engine import ReconciliationEngine
        eng = ReconciliationEngine(
            flexcube_count_fn=lambda c, d: Decimal("100"),
            a2z_count_fn=lambda c, d: Decimal("100"),
            extract_control_fn=lambda t: {"last_extract_date": "2026-04-25"},
            break_log_fn=lambda r: None,
        )
        r = eng.run_full_reconciliation("2026-04-29")
        assert r["extract_stale"] is True
        assert r["checks_not_run"] == 3
        assert r["checks_passed"] == 0
        assert "Mandatory Standard #11" in r["data_quality_warning"]


# ═══════════════════════════════════════════════════════════════════════
# Harness — Reconciliation correctness (G42)
# ═══════════════════════════════════════════════════════════════════════

def test_reconciliation_correctness_meets_99_percent():
    """Runs every fixture in tests/fixtures/reconciliation_scenarios.json
    against the engine and asserts ≥99% of expected outcomes match.
    Writes G42 artifact.
    """
    from utils.reconciliation_engine import ReconciliationEngine

    scenarios = json.loads(RECON_FIXTURES.read_text())
    assert len(scenarios) >= 10

    correct = 0
    results = []
    for s in scenarios:
        inp = s["input"]
        fc = inp["flexcube"]
        a2z = inp["a2z"]
        ec  = inp.get("extract_control")

        breaks: list = []
        eng = ReconciliationEngine(
            flexcube_count_fn=lambda c, d: Decimal(fc[c]) if c in fc else None,
            a2z_count_fn=lambda c, d: Decimal(a2z[c]) if c in a2z else None,
            extract_control_fn=lambda t: ec,
            break_log_fn=lambda r: breaks.append(r),
        )
        r = eng.run_full_reconciliation("2026-04-29")
        expected = s["expected"]

        ok = True
        diffs = []
        for k in ("checks_passed", "checks_failed", "checks_not_run"):
            if k in expected and r.get(k) != expected[k]:
                ok = False
                diffs.append(f"{k}={r.get(k)} vs {expected[k]}")
        if "extract_stale" in expected and r.get("extract_stale") != expected["extract_stale"]:
            ok = False
            diffs.append(f"extract_stale={r.get('extract_stale')}")
        if "all_checks_passed" in expected:
            actual = (r.get("meta") or {}).get("all_checks_passed")
            if actual != expected["all_checks_passed"]:
                ok = False
                diffs.append(f"all_checks_passed={actual}")
        if "warning_present" in expected:
            present = r.get("data_quality_warning") is not None
            if present != expected["warning_present"]:
                ok = False
                diffs.append(f"warning_present={present}")
        if "warning_substring" in expected:
            if expected["warning_substring"] not in (r.get("data_quality_warning") or ""):
                ok = False
                diffs.append("warning_substring missing")
        if "expected_breaks_count" in expected:
            if len(breaks) != expected["expected_breaks_count"]:
                ok = False
                diffs.append(f"breaks_count={len(breaks)} vs {expected['expected_breaks_count']}")
        if "break_check" in expected:
            check_break = next(
                (b for b in breaks if b["check_name"] == expected["break_check"]),
                None
            )
            if not check_break:
                ok = False
                diffs.append(f"no break for {expected['break_check']!r}")
            else:
                if "break_variance" in expected:
                    if abs(check_break["variance"] - expected["break_variance"]) > 0.01:
                        ok = False
                        diffs.append(f"break_variance={check_break['variance']}")
                if "break_abs_variance" in expected:
                    if abs(check_break["abs_variance"] - expected["break_abs_variance"]) > 0.01:
                        ok = False
                        diffs.append(f"break_abs_variance={check_break['abs_variance']}")
        if "deposit_abs_variance" in expected:
            dep = next((c for c in r["checks"] if c["check_name"] == "deposit_balance"), None)
            if not dep or abs((dep.get("abs_variance") or 0) - expected["deposit_abs_variance"]) > 0.001:
                ok = False
                diffs.append(f"deposit_abs_variance={dep.get('abs_variance') if dep else None}")

        if ok:
            correct += 1
        results.append({"id": s["id"], "matched": ok, "diffs": diffs})

    total = len(scenarios)
    accuracy = correct / total * 100
    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total,
        "correct":         correct,
        "accuracy_pct":    round(accuracy, 2),
        "spec_target_pct": 99.0,
        "all_passed":      accuracy >= 99.0,
        "results":         results,
    }
    RECON_RESULTS.write_text(json.dumps(artifact, indent=2))
    assert accuracy >= 99.0, f"correctness {accuracy:.1f}% < 99%; failures: " + \
        ", ".join(f"{r['id']}({r['diffs']})" for r in results if not r["matched"])
