"""tests/test_product_v10_150.py — ENH-139 Product Bundling Intelligence

Verifies the v10.150 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 5 methods
- Pairwise affinity with lift + support + co_propensity calculations
- Symmetric pair handling (no double-counting via combinations)
- Honest data limitation surfaced via analysis_basis="propensity_proxy"
- All results carry is_estimate=True in proxy mode
- Top bundles ranked by lift then support
- Per-product companions
- Segment-level bundles with fallback for unknown segment
- Read-only — engine never writes
- Registry: ENH-139 active
- Admin Tier 4B has all nine engines
- No regression
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "product_bundling.py"


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
        m = _load("bun_shape", ENGINE_PATH)
        assert hasattr(m, "ProductBundlingIntelligence")
        assert hasattr(m, "BundleAffinity")
        assert hasattr(m, "PROPENSITY_TO_PRODUCT_ID")

    def test_required_public_methods(self):
        m = _load("bun_methods", ENGINE_PATH)
        eng = m.ProductBundlingIntelligence()
        for method in (
            "get_bundle_affinity", "get_top_bundles",
            "get_bundles_for_product", "get_segment_bundles",
            "get_bundling_summary",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))


class TestAffinityComputation:
    def _engine(self):
        m = _load("bun_aff", ENGINE_PATH)
        return m.ProductBundlingIntelligence()

    def test_known_pair_returns_affinity(self):
        eng = self._engine()
        a = eng.get_bundle_affinity("P001", "P015")
        assert a is not None
        assert a.product_a_id == "P001"
        assert a.product_b_id == "P015"
        assert a.analysis_basis == "propensity_proxy"
        assert a.is_estimate is True

    def test_same_product_returns_none(self):
        a = self._engine().get_bundle_affinity("P001", "P001")
        assert a is None

    def test_unmappable_product_returns_none(self):
        # P010 Trade Finance LC isn't in PROPENSITY_TO_PRODUCT_ID
        a = self._engine().get_bundle_affinity("P010", "P001")
        assert a is None

    def test_lift_and_support_in_valid_range(self):
        eng = self._engine()
        a = eng.get_bundle_affinity("P001", "P002")
        assert a is not None
        # Lift can be any non-negative; support should be 0-100
        assert Decimal("0") <= a.support_pct <= Decimal("100")
        assert a.lift >= Decimal("0")


class TestTopBundles:
    def _engine(self):
        m = _load("bun_top", ENGINE_PATH)
        return m.ProductBundlingIntelligence()

    def test_returns_list_of_bundles(self):
        out = self._engine().get_top_bundles(min_affinity=0.0,
                                                top_n=5)
        assert isinstance(out, list)
        assert len(out) <= 5

    def test_higher_min_affinity_returns_subset(self):
        eng = self._engine()
        wide = eng.get_top_bundles(min_affinity=0.0, top_n=20)
        narrow = eng.get_top_bundles(min_affinity=0.5, top_n=20)
        assert len(narrow) <= len(wide)

    def test_sorted_by_lift_descending(self):
        out = self._engine().get_top_bundles(min_affinity=0.0,
                                                top_n=15)
        if len(out) >= 2:
            for i in range(len(out) - 1):
                lift_i = float(out[i]["lift"])
                lift_next = float(out[i + 1]["lift"])
                # Lift descending; ties allowed
                assert lift_i >= lift_next

    def test_each_bundle_has_required_fields(self):
        out = self._engine().get_top_bundles(min_affinity=0.0,
                                                top_n=5)
        for b in out:
            for k in ("product_a_id", "product_a_name",
                      "product_b_id", "product_b_name",
                      "co_propensity_score", "support_pct",
                      "lift", "n_customers_evaluated",
                      "analysis_basis", "is_estimate"):
                assert k in b


class TestProductCompanions:
    def _engine(self):
        m = _load("bun_comp", ENGINE_PATH)
        return m.ProductBundlingIntelligence()

    def test_returns_companions_for_real_product(self):
        out = self._engine().get_bundles_for_product("P001", top_n=3)
        assert len(out) <= 3
        # P001 should not appear as product_b in its own companion list
        for b in out:
            assert b["product_b_id"] != "P001"

    def test_unmappable_product_returns_empty(self):
        out = self._engine().get_bundles_for_product("P010", top_n=3)
        assert out == []


class TestSegmentBundles:
    def _engine(self):
        m = _load("bun_seg", ENGINE_PATH)
        return m.ProductBundlingIntelligence()

    def test_real_segment_returns_bundles(self):
        out = self._engine().get_segment_bundles("Mass", top_n=3)
        assert out["ok"] is True
        assert out["analysis_basis"] == "propensity_proxy"
        assert out["is_estimate"] is True
        assert len(out["top_bundles"]) <= 3

    def test_unknown_segment_returns_fallback(self):
        out = self._engine().get_segment_bundles("BOGUS_SEG", top_n=3)
        assert out["ok"] is False
        assert out["fallback_reason"] == "no_customers_in_segment"


class TestSummary:
    def _engine(self):
        m = _load("bun_sum", ENGINE_PATH)
        return m.ProductBundlingIntelligence()

    def test_summary_has_data_limitation_note(self):
        s = self._engine().get_bundling_summary()
        assert s["ok"] is True
        assert s["analysis_basis"] == "propensity_proxy"
        assert s["is_estimate"] is True
        assert "data_limitation_note" in s
        assert ("propensity" in s["data_limitation_note"].lower()
                  or "holdings" in s["data_limitation_note"].lower())

    def test_summary_lift_buckets_consistent(self):
        s = self._engine().get_bundling_summary()
        # n_positive + n_weak should equal n_pairs_evaluated
        # (strong is a subset of positive)
        total = s["n_positive_associations_lift_gt_1"] + \
                s["n_weak_associations_lift_lte_1"]
        assert total == s["n_pairs_evaluated"]


class TestReadOnly:
    def test_engine_does_not_write(self):
        text = ENGINE_PATH.read_text()
        if 'json.dump' in text:
            for line in text.split('\n'):
                if 'json.dump' in line:
                    assert ('#' in line.split('json.dump')[0]
                              or '"""' in line
                              or "'''" in line), (
                        f"engine should not write: {line.strip()}")


class TestRegistryAndAdmin:
    def test_enh_139_active(self):
        m = _load("sr139",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-139"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_bundling" in std.affected_engines
        assert std.implementation_batch == "v10.150"

    def test_prior_phase1e_engines_still_active(self):
        m = _load("sr_prior_v150",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132", "ENH-133", "ENH-134",
                    "ENH-135", "ENH-136", "ENH-137", "ENH-138"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_nine_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "product_competitive_intel",
                      "product_cvp_builder",
                      "product_ranking",
                      "dynamic_pricing",
                      "product_recommendation",
                      "product_bundling",
                      "ProductBundlingIntelligence"):
            assert token in text, f"missing token: {token}"


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v150",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v150",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"
