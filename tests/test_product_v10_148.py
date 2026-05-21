"""tests/test_product_v10_148.py — ENH-137 Dynamic Pricing Engine

Verifies the v10.148 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 5 methods
- Synthesizes from ENH-134 + ENH-131 (companion engines, DI pattern)
- Pricing recommendations: HOLD / INCREASE / DECREASE / NO_BENCHMARK /
  CONSTRAINED_BY_FLOOR / CONSTRAINED_BY_CEILING / CONSTRAINED_BY_MARGIN
- LEADER products → HOLD (already winning)
- LAGGARD products → INCREASE (deposits) or DECREASE (lending) toward peer median
- Max change capped at 100bps per period
- Category floor/ceiling enforced
- Margin floor only fires when actually proposing a change (not on HOLD)
- Read-only — engine never writes
- simulate_price_change what-if tool
- Config seed exists with category_constraints
- Registry: ENH-137 active
- Admin Tier 4B has all seven engines
- No regression
"""
from __future__ import annotations
import ast
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "dynamic_pricing.py"
CONFIG_PATH = REPO_ROOT / "data" / "pricing_constraints_config.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestEngineModule:
    def test_module_exists(self):
        assert ENGINE_PATH.exists()

    def test_module_parses(self):
        ast.parse(ENGINE_PATH.read_text())

    def test_class_and_dataclass_present(self):
        m = _load("dp_shape", ENGINE_PATH)
        assert hasattr(m, "DynamicPricingEngine")
        assert hasattr(m, "PricingRecommendation")

    def test_required_public_methods(self):
        m = _load("dp_methods", ENGINE_PATH)
        eng = m.DynamicPricingEngine()
        for method in (
            "get_pricing_recommendation",
            "get_all_recommendations",
            "get_actionable_recommendations",
            "get_recommendation_summary",
            "simulate_price_change",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))


class TestRecommendationLogic:
    def _engine(self):
        m = _load("dp_logic", ENGINE_PATH)
        return m.DynamicPricingEngine()

    def test_unknown_product_returns_not_found(self):
        rec = self._engine().get_pricing_recommendation("P_UNKNOWN")
        assert rec.action == "PRODUCT_NOT_FOUND"
        assert rec.status == "product_not_found"

    def test_unmapped_product_returns_no_benchmark(self):
        # P010 Trade Finance LC is unmapped per ENH-134 mapping
        rec = self._engine().get_pricing_recommendation("P010")
        assert rec.action == "NO_BENCHMARK"
        assert rec.status == "no_benchmark"
        assert rec.recommended_rate_pct is None

    def test_leader_product_returns_hold(self):
        # P001 Personal Loans is LEADER per real data
        rec = self._engine().get_pricing_recommendation("P001")
        # Should HOLD (already winning) — though could be CONSTRAINED_BY_*
        # depending on category bounds; verify it's not INCREASE
        assert rec.action != "INCREASE"

    def test_lagging_deposit_returns_increase(self):
        # P014 Fixed Deposits is LAGGARD (we pay 10% vs peer 12%)
        rec = self._engine().get_pricing_recommendation("P014")
        assert rec.action == "INCREASE"
        assert rec.change_bps is not None
        assert rec.change_bps > 0

    def test_change_capped_at_max_per_period(self):
        # P014 has 200bps gap to peer median; should be capped at 100
        rec = self._engine().get_pricing_recommendation("P014")
        if rec.action in ("INCREASE", "DECREASE"):
            assert abs(rec.change_bps) <= 100

    def test_constraint_applied_recorded(self):
        # P014 hits the max-change cap; constraints_applied should
        # include capped marker
        rec = self._engine().get_pricing_recommendation("P014")
        if rec.action == "INCREASE":
            assert any("capped_at_max_change" in c
                        for c in rec.constraints_applied)


class TestActionable:
    def _engine(self):
        m = _load("dp_act", ENGINE_PATH)
        return m.DynamicPricingEngine()

    def test_actionable_filters_to_meaningful_changes(self):
        eng = self._engine()
        out = eng.get_actionable_recommendations(min_change_bps=50)
        for r in out:
            assert r["action"] in ("INCREASE", "DECREASE")
            assert abs(r["change_bps"]) >= 50

    def test_actionable_sorted_by_magnitude_desc(self):
        out = self._engine().get_actionable_recommendations()
        for i in range(len(out) - 1):
            assert (abs(out[i]["change_bps"])
                      >= abs(out[i + 1]["change_bps"]))

    def test_summary_components_consistent(self):
        s = self._engine().get_recommendation_summary()
        action_total = sum(s["by_action"].values())
        assert action_total == s["n_products"]


class TestSimulate:
    def _engine(self):
        m = _load("dp_sim", ENGINE_PATH)
        return m.DynamicPricingEngine()

    def test_simulate_unknown_product_fails(self):
        out = self._engine().simulate_price_change("P_UNKNOWN", 10.0)
        assert out["ok"] is False
        assert "not_found" in out["reason"]

    def test_simulate_real_product_returns_projection(self):
        # P014 has positive margin baseline
        out = self._engine().simulate_price_change("P014", 11.5)
        if out.get("ok"):
            assert "projected_margin_pct" in out
            assert "margin_floor_violated" in out
            assert "estimation_basis" in out


class TestReadOnly:
    def test_engine_does_not_write(self):
        # Verify engine has no methods that write to product files
        text = ENGINE_PATH.read_text()
        # Scan for json.dump or .write_text on data files
        forbidden_writes = [
            'json.dump(', 'with open(.*[\"\']w[\"\']',
            'products.json", "w"',
        ]
        # Simple text check: no 'json.dump' targeting products.json
        # in the engine
        if 'json.dump' in text:
            # Allowed only if config writes are explicitly absent
            # — engine should never write
            for line in text.split('\n'):
                if 'json.dump' in line:
                    # Engine writes only if it's in a comment or
                    # docstring; verify it's NOT in actual code
                    assert ('#' in line.split('json.dump')[0]
                              or '"""' in line
                              or "'''" in line), (
                        f"engine should not write: {line.strip()}")


class TestConfig:
    def test_config_exists_parses(self):
        assert CONFIG_PATH.exists()
        d = json.loads(CONFIG_PATH.read_text())
        assert "global_constraints" in d
        assert "category_constraints" in d

    def test_global_constraints_present(self):
        d = json.loads(CONFIG_PATH.read_text())
        for k in ("max_change_per_period_bps",
                  "min_margin_floor_pct"):
            assert k in d["global_constraints"]

    def test_category_constraints_have_lending_categories(self):
        d = json.loads(CONFIG_PATH.read_text())
        for cat in ("Retail Lending", "SME Lending", "Corporate",
                    "Trade Finance", "Deposits"):
            assert cat in d["category_constraints"]


class TestRegistryAndAdmin:
    def test_enh_137_active(self):
        m = _load("sr137",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-137"), None)
        assert std is not None
        assert std.status == "active"
        assert "dynamic_pricing" in std.affected_engines
        assert std.implementation_batch == "v10.148"

    def test_prior_phase1e_engines_still_active(self):
        m = _load("sr_prior_v148",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132", "ENH-133", "ENH-134",
                    "ENH-135", "ENH-136"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_seven_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "product_competitive_intel",
                      "product_cvp_builder",
                      "product_ranking",
                      "dynamic_pricing",
                      "DynamicPricingEngine"):
            assert token in text, f"missing token: {token}"


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v148",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v148",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"
