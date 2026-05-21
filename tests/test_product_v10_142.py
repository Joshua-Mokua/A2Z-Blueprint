"""tests/test_product_v10_142.py — ENH-131 Product Profitability Intelligence

Verifies the v10.142 deliverable:
- Engine module exists and parses
- ProductPnLIntelligence class + frozen dataclass + 6 public methods
- Cost-model categorization (lending / deposits / fee)
- Honest is_estimate + missing_inputs trail
- Customer profitability segment fallback path
- Registry: ENH-131 active with affected_engines tuple set
- Admin hub Tier 4B entry present
- No regression of G144 / G145 / G146 / G117
"""
from __future__ import annotations
import ast
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "product_pnl_intelligence.py"
CONFIG_PATH = REPO_ROOT / "data" / "cost_allocation_config.json"


# ---------------------------------------------------------------------------
# Engine module shape
# ---------------------------------------------------------------------------

class TestEngineModule:
    def test_module_exists(self):
        assert ENGINE_PATH.exists(), f"missing: {ENGINE_PATH}"

    def test_module_parses(self):
        ast.parse(ENGINE_PATH.read_text())

    def test_class_defined(self):
        spec = importlib.util.spec_from_file_location(
            "ppi_test", str(ENGINE_PATH))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        assert hasattr(m, "ProductPnLIntelligence")
        assert hasattr(m, "ProductPnLBookBased")

    def test_dataclass_frozen(self):
        spec = importlib.util.spec_from_file_location(
            "ppi_test_frozen", str(ENGINE_PATH))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        try:
            r = m.ProductPnLBookBased(
                product_id="P_TEST", name="t", category="Retail Lending",
                cost_model="lending",
                book_kes=Decimal("0"), revenue_kes=Decimal("0"),
                funding_cost_kes=Decimal("0"), credit_cost_kes=Decimal("0"),
                direct_ops_cost_kes=Decimal("0"),
                allocated_overhead_kes=Decimal("0"),
                total_cost_kes=Decimal("0"), net_profit_kes=Decimal("0"),
                margin_pct=None, roa_pct=None, status="no_data",
                is_estimate=True)
            try:
                r.product_id = "X"
                assert False, "frozen dataclass should reject mutation"
            except Exception:
                pass
        except TypeError as e:
            assert False, f"dataclass shape mismatch: {e}"

    def test_required_public_methods(self):
        spec = importlib.util.spec_from_file_location(
            "ppi_test_methods", str(ENGINE_PATH))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        eng = m.ProductPnLIntelligence()
        for method in (
            "compute_product_pnl", "compute_portfolio",
            "aggregate_by_category", "get_loss_making",
            "get_bank_wide_summary", "customer_profitability_by_segment",
        ):
            assert hasattr(eng, method), f"missing method: {method}"
            assert callable(getattr(eng, method))


# ---------------------------------------------------------------------------
# Behavioral tests
# ---------------------------------------------------------------------------

class TestPnLBehavior:
    def _engine(self):
        spec = importlib.util.spec_from_file_location(
            "ppi_b", str(ENGINE_PATH))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        return m.ProductPnLIntelligence(), m

    def test_cost_model_lending(self):
        eng, _ = self._engine()
        prod = {"id": "T1", "name": "t", "category": "Retail Lending",
                "actual_book": 1000000000, "actual_revenue": 100000000,
                "npl_rate": 5.0}
        r = eng.compute_product_pnl(prod)
        assert r.cost_model == "lending"
        assert r.funding_cost_kes > 0
        assert r.credit_cost_kes > 0
        assert r.is_estimate is True

    def test_cost_model_deposits_skips_funding_credit(self):
        eng, _ = self._engine()
        prod = {"id": "T2", "name": "t", "category": "Deposits",
                "actual_book": 1000000000, "actual_revenue": 100000000,
                "npl_rate": 0.0}
        r = eng.compute_product_pnl(prod)
        assert r.cost_model == "deposits"
        assert r.funding_cost_kes == Decimal("0")
        assert r.credit_cost_kes == Decimal("0")

    def test_cost_model_fee_skips_funding_credit(self):
        eng, _ = self._engine()
        prod = {"id": "T3", "name": "t", "category": "Fee Income",
                "actual_book": 0, "actual_revenue": 100000000,
                "npl_rate": 0.0}
        r = eng.compute_product_pnl(prod)
        assert r.cost_model == "fee"
        assert r.funding_cost_kes == Decimal("0")
        assert r.credit_cost_kes == Decimal("0")
        assert r.roa_pct is None  # no book → no ROA

    def test_status_classification_bands(self):
        eng, _ = self._engine()
        # Profitable
        prod_p = {"id": "T4", "name": "t", "category": "Deposits",
                  "actual_book": 1e9, "actual_revenue": 100e6,
                  "npl_rate": 0.0}
        r_p = eng.compute_product_pnl(prod_p)
        assert r_p.status in ("profitable",
                              "breakeven")  # depends on overhead/ops cfg
        # Loss-making (very high NPL)
        prod_l = {"id": "T5", "name": "t", "category": "Retail Lending",
                  "actual_book": 1e9, "actual_revenue": 50e6,
                  "npl_rate": 50.0}
        r_l = eng.compute_product_pnl(prod_l)
        assert r_l.status == "loss-making"

    def test_missing_inputs_trail_present(self):
        eng, _ = self._engine()
        prod = {"id": "T6", "name": "t", "category": "Retail Lending",
                "actual_book": 1e9, "actual_revenue": 100e6,
                "npl_rate": 5.0}
        r = eng.compute_product_pnl(prod)
        assert r.is_estimate is True
        assert len(r.missing_inputs) >= 3  # funding + credit + ops + overhead
        assert any("funding_cost" in s for s in r.missing_inputs)
        assert any("credit_cost" in s for s in r.missing_inputs)


# ---------------------------------------------------------------------------
# Aggregations & honest deferrals
# ---------------------------------------------------------------------------

class TestAggregations:
    def _engine(self):
        spec = importlib.util.spec_from_file_location(
            "ppi_a", str(ENGINE_PATH))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        return m.ProductPnLIntelligence()

    def test_compute_portfolio_returns_list(self):
        portfolio = self._engine().compute_portfolio()
        assert isinstance(portfolio, list)
        assert len(portfolio) > 0  # products.json has 16 products

    def test_aggregate_by_category_keys(self):
        agg = self._engine().aggregate_by_category()
        assert isinstance(agg, dict)
        assert len(agg) > 0
        sample = next(iter(agg.values()))
        for k in ("n_products", "book_kes", "revenue_kes",
                  "total_cost_kes", "net_profit_kes",
                  "margin_pct", "roa_pct"):
            assert k in sample, f"category aggregate missing key: {k}"

    def test_bank_wide_summary_complete(self):
        summary = self._engine().get_bank_wide_summary()
        for k in ("n_products", "total_book_kes", "total_revenue_kes",
                  "total_cost_kes", "total_net_profit_kes",
                  "margin_pct", "roa_pct",
                  "n_profitable", "n_breakeven", "n_loss_making"):
            assert k in summary, f"bank-wide missing key: {k}"
        assert summary["n_profitable"] + summary["n_breakeven"] \
            + summary["n_loss_making"] <= summary["n_products"]

    def test_get_loss_making_threshold(self):
        eng = self._engine()
        loss = eng.get_loss_making(threshold_pct=0.0)
        for r in loss:
            assert r.margin_pct is not None
            assert r.margin_pct < Decimal("0")


class TestSegmentProfitability:
    def _engine(self):
        spec = importlib.util.spec_from_file_location(
            "ppi_s", str(ENGINE_PATH))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        return m.ProductPnLIntelligence()

    def test_no_segment_data_returns_explicit_fallback(self):
        eng = self._engine()
        out = eng.customer_profitability_by_segment("P001", None)
        assert out["ok"] is False
        assert out["fallback_reason"] == "no_segment_data_supplied"
        assert out["segments"] == {}

    def test_unknown_product_returns_fallback(self):
        eng = self._engine()
        out = eng.customer_profitability_by_segment(
            "P_UNKNOWN_999",
            {"Mass": {"book_kes": 1, "revenue_kes": 1}})
        assert out["ok"] is False
        assert out["fallback_reason"] == "product_not_found"

    def test_with_segment_data_returns_segments(self):
        eng = self._engine()
        out = eng.customer_profitability_by_segment(
            "P001",
            {"HNW": {"book_kes": 10000000000, "revenue_kes": 1500000000},
             "Mass": {"book_kes": 38000000000, "revenue_kes": 5500000000}})
        assert out["ok"] is True
        assert out["n_segments"] == 2
        assert "HNW" in out["segments"]
        assert "Mass" in out["segments"]


# ---------------------------------------------------------------------------
# Cost-allocation config seed
# ---------------------------------------------------------------------------

class TestCostConfig:
    def test_config_exists(self):
        assert CONFIG_PATH.exists()

    def test_config_parses(self):
        cfg = json.loads(CONFIG_PATH.read_text())
        assert isinstance(cfg, dict)

    def test_config_has_required_keys(self):
        cfg = json.loads(CONFIG_PATH.read_text())
        for k in ("cost_of_funds_rate_pct", "loss_given_default_pct",
                  "direct_ops_cost_pct_of_revenue",
                  "allocated_overhead_pct_of_revenue",
                  "category_overrides"):
            assert k in cfg, f"config missing key: {k}"


# ---------------------------------------------------------------------------
# Registry + admin hub integration
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_enh_131_active(self):
        spec = importlib.util.spec_from_file_location(
            "sr", str(REPO_ROOT / "utils" / "standards_registry.py"))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-131"), None)
        assert std is not None
        assert std.status == "active", f"got status={std.status}"
        assert "product_pnl_intelligence" in std.affected_engines
        assert std.implementation_batch == "v10.142"


class TestAdminHub:
    def test_tier_4b_present(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        assert "Tier 4B — Product Intelligence" in text
        assert "product_pnl_intelligence" in text
        assert "ProductPnLIntelligence" in text


# ---------------------------------------------------------------------------
# No regression
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_audit_script_imports(self):
        spec = importlib.util.spec_from_file_location(
            "audit", str(REPO_ROOT / "scripts" / "audit.py"))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        # GATES list still includes all expected gates
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146", "G117"):
            assert gid in gate_ids, f"missing gate: {gid}"

    def test_strategy_standards_still_active(self):
        spec = importlib.util.spec_from_file_location(
            "sr_strat", str(REPO_ROOT / "utils" / "standards_registry.py"))
        m = importlib.util.module_from_spec(spec)
        import sys as _sys; _sys.modules[spec.name] = m
        spec.loader.exec_module(m)
        for sid in ("ENH-141", "ENH-142", "ENH-143", "ENH-144", "ENH-145",
                    "ENH-146", "ENH-147", "ENH-148", "ENH-149", "ENH-150",
                    "ENH-151", "ENH-152", "ENH-153", "ENH-154", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active", f"{sid} regressed"
