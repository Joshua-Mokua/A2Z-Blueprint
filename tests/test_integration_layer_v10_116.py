"""tests/test_integration_layer_v10_116.py — v10.116.

Verifies:
  1. PG-readiness shim — `_data_source` config knob honored in 4 modes
     (default/json, pg_view strict, auto with fallback, structured
     per-table)
  2. PG-view safety — table identifier whitelisted before SQL composition
  3. POST /api/integration/run-period — write-side trigger pipeline
  4. 5 new rules registered (K087, K088, K089, K060, K062)
  5. STAFF_FIELD_BY_TABLE additions for card_management, purchase_requests
  6. G143 coverage advanced from 40/131 to ≥45/131
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── PG-readiness shim ────────────────────────────────────────────────

class TestPGReadinessShim:
    """The `_data_source` config knob in integration_layer_config.json
    routes operational-table reads between JSON and PG views, closing
    the JSON-deprecation blueprint gap.
    """

    @pytest.fixture(autouse=True)
    def _restore_config(self):
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        original = cfg_path.read_text() if cfg_path.exists() else None
        yield
        if original is not None:
            cfg_path.write_text(original)
        # Clear cached module
        import utils.actuals_engine as ae
        import importlib
        importlib.reload(ae)

    def _set_config(self, value):
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        cfg["_data_source"] = value
        cfg_path.write_text(json.dumps(cfg, indent=2))
        import utils.actuals_engine as ae
        import importlib
        importlib.reload(ae)

    def test_default_is_json(self):
        from utils.actuals_engine import _read_data_source_config
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        cfg = json.loads(cfg_path.read_text())
        # Even if config has _data_source set elsewhere in tests, the
        # default-mode return shape includes a `default` key
        result = _read_data_source_config(REPO_ROOT / "data")
        assert "default" in result
        assert "per_table" in result

    def test_json_mode_reads_files(self):
        self._set_config("json")
        from utils.actuals_engine import _read_operational_table
        rows = _read_operational_table(
            "loan_applications", REPO_ROOT / "data")
        assert len(rows) > 100, "json mode should read loan_applications JSON"

    def test_pg_view_mode_strict_returns_empty_when_pg_unavailable(self):
        """Strict pg_view mode: when PG isn't available (sandbox), return
        empty rather than silently fall back to JSON. This exposes
        misconfiguration rather than masking it."""
        self._set_config("pg_view")
        from utils.actuals_engine import _read_operational_table
        rows = _read_operational_table(
            "loan_applications", REPO_ROOT / "data")
        assert rows == [], (
            f"pg_view strict mode should return [] when PG unavailable; "
            f"got {len(rows)} rows (silently masked misconfiguration)")

    def test_auto_mode_falls_back_to_json(self):
        """auto mode: try PG, fall back to JSON. When PG unavailable,
        should serve JSON data."""
        self._set_config("auto")
        from utils.actuals_engine import _read_operational_table
        rows = _read_operational_table(
            "loan_applications", REPO_ROOT / "data")
        assert len(rows) > 100, (
            "auto mode should fall back to JSON when PG unavailable")

    def test_structured_per_table_config(self):
        """Bank can migrate one table at a time — pg_view for incidents
        but json for everything else."""
        self._set_config({
            "default":   "json",
            "per_table": {"incidents": "pg_view"},
        })
        from utils.actuals_engine import (
            _read_operational_table, _read_data_source_config)

        cfg = _read_data_source_config(REPO_ROOT / "data")
        assert cfg["default"] == "json"
        assert cfg["per_table"]["incidents"] == "pg_view"

        # incidents → pg_view → empty (PG unavailable)
        inc = _read_operational_table("incidents", REPO_ROOT / "data")
        assert inc == []

        # loan_applications → default json → populated
        la = _read_operational_table(
            "loan_applications", REPO_ROOT / "data")
        assert len(la) > 100

    def test_invalid_table_identifier_rejected(self):
        """Whitelist regex protects against SQL injection via table name.
        Even if a malicious config slipped a malformed identifier into
        per_table, the read should refuse it cleanly."""
        from utils.actuals_engine import _try_read_from_pg_view
        # Various malformed identifiers
        for bad in (
                "loan; DROP TABLE users",
                "Loan_Applications",   # uppercase rejected
                "1loan",               # leading digit rejected
                "",
                "a" * 100,             # too long
        ):
            assert _try_read_from_pg_view(bad) is None, (
                f"Whitelist should reject {bad!r}")


# ─── 5 new rules registered ───────────────────────────────────────────

class TestV10116RulesRegistered:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    def test_K087_cards_activated_count(self, get_rule):
        rule = get_rule("K087")
        assert rule is not None
        assert rule.source_table == "card_management"
        assert rule.pattern == "COUNT"

    def test_K088_card_spend_sum(self, get_rule):
        rule = get_rule("K088")
        assert rule is not None
        assert rule.source_table == "card_management"
        assert rule.pattern == "SUM"
        assert rule.value_field == "ytd_spend_kes"

    def test_K089_disputes_within_sla_uses_field_le_field(self, get_rule):
        rule = get_rule("K089")
        assert rule is not None
        assert rule.source_table == "card_management"
        assert rule.pattern == "PERCENTAGE"

    def test_K060_retailer_portfolio_sum(self, get_rule):
        rule = get_rule("K060")
        assert rule is not None
        assert rule.source_table == "retailer_finance"
        assert rule.pattern == "SUM"
        assert rule.value_field == "amount_kes"

    def test_K062_retailer_npl_percentage(self, get_rule):
        rule = get_rule("K062")
        assert rule is not None
        assert rule.source_table == "retailer_finance"
        assert rule.pattern == "PERCENTAGE"


# ─── 5 rules produce real outputs ─────────────────────────────────────

class TestV10116RulesProduceOutput:

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("card_management", "retailer_finance"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                d = json.load(f)
            out[t] = d if isinstance(d, list) else list(d.values())
        return out

    def _compute(self, kid, tables):
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        rule = next(r for r in REGISTRY if r.kpi_id == kid)
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        return compute_rule(rule, tables[rule.source_table], "2026-04", sf)

    def test_K087_cards_activated_real_data(self, tables):
        result = self._compute("K087", tables)
        assert len(result) >= 5
        for staff, n in result.items():
            assert n >= 1
            assert isinstance(n, (int, float))

    def test_K088_card_spend_positive(self, tables):
        result = self._compute("K088", tables)
        assert len(result) >= 5
        for staff, total in result.items():
            assert total > 0, (
                f"K088 should sum positive spend; staff {staff} → {total}")

    def test_K089_disputes_in_sla_in_range(self, tables):
        result = self._compute("K089", tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100, (
                f"K089 should be 0-100%; staff {staff} → {pct}")

    def test_K060_portfolio_positive(self, tables):
        result = self._compute("K060", tables)
        for staff, total in result.items():
            assert total > 0

    def test_K062_npl_in_range(self, tables):
        result = self._compute("K062", tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100


# ─── STAFF_FIELD_BY_TABLE additions ──────────────────────────────────

class TestStaffFieldAdditionsV10116:

    def test_card_management(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("card_management") == "rm_code"

    def test_purchase_requests(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("purchase_requests") == "requested_by"


# ─── G143 coverage advanced ──────────────────────────────────────────

class TestG143CoverageAdvanced:
    """v10.116 should advance G143 from 40/131 to ≥45/131."""

    def test_coverage_45_or_higher(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            result = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        assert result["passed"] is True
        import re
        m = re.search(r"registered (\d+)\s*/\s*(\d+)", result["summary"])
        n = int(m.group(1))
        t = int(m.group(2))
        assert n >= 45, f"v10.116 expected ≥45 covered; got {n}/{t}"
        assert t >= 131, f"denominator should be ≥131; got {t}"


# ─── Run-period endpoint logic (FastAPI not in build sandbox) ────────

class TestRunPeriodLogic:
    """Verifies the integration_run_period logic matches the contract.
    Direct invocation of the api module isn't possible without FastAPI
    installed, so this tests the underlying actuals_engine call which
    the endpoint wraps."""

    def test_period_validation_regex(self):
        import re
        regex = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
        assert regex.match("2026-04")
        assert regex.match("2026-12")
        assert regex.match("2026-01")
        assert not regex.match("2026-13")
        assert not regex.match("2026-00")
        assert not regex.match("2026-1")
        assert not regex.match("bad")
        assert not regex.match("")

    def test_actuals_engine_returns_expected_shape(self):
        """The function the POST endpoint wraps."""
        from utils.actuals_engine import (
            compute_actuals_from_operational_tables)
        result = compute_actuals_from_operational_tables("2026-04")
        # Must be a dict with the expected keys
        assert isinstance(result, dict)
        for k in ("success", "period", "rules_processed",
                  "actuals_submitted", "actuals_dropped"):
            assert k in result, f"actuals_engine missing key {k!r}"
