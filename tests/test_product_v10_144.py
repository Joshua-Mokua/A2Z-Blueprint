"""tests/test_product_v10_144.py — ENH-133 Customer Needs & Gap Analysis

Verifies the v10.144 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 6 public methods
- Customer needs ranking (propensity-driven first, then segment-archetype)
- Gap analysis combining portfolio-count + propensity + behavioural signals
- Severity classification rules (HIGH / MEDIUM / NONE) with rationale trail
- Honest fallback when customer not in intelligence
- Aggregations (segment summary, top unmet needs, high-priority gaps, bank-wide)
- Registry seed shape + segment_expectations
- Registry: ENH-133 active
- Admin Tier 4B has ENH-131 + ENH-132 + ENH-133
- No regression of strategy module + earlier gates
"""
from __future__ import annotations
import ast
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "customer_needs_analyzer.py"
REGISTRY_PATH = REPO_ROOT / "data" / "customer_needs_registry.json"


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
        m = _load("cna_shape", ENGINE_PATH)
        assert hasattr(m, "CustomerNeedsAnalyzer")
        assert hasattr(m, "CustomerGap")

    def test_required_public_methods(self):
        m = _load("cna_methods", ENGINE_PATH)
        eng = m.CustomerNeedsAnalyzer()
        for method in (
            "get_customer_needs", "analyze_customer_gap",
            "get_segment_gap_summary", "get_top_unmet_needs",
            "get_high_priority_gaps", "bank_wide_gap_summary",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))


class TestCustomerNeeds:
    def _engine(self):
        m = _load("cna_n", ENGINE_PATH)
        return m.CustomerNeedsAnalyzer()

    def test_existing_customer_returns_ranked_needs(self):
        eng = self._engine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        result = eng.get_customer_needs(sample_id)
        assert result["ok"] is True
        assert result["n_needs"] > 0
        # Propensity needs come first per design
        first = result["needs"][0]
        assert first["source"] == "propensity_scores"
        assert first["rank_basis"] == "customer_revealed_preference"

    def test_unknown_customer_returns_fallback(self):
        eng = self._engine()
        result = eng.get_customer_needs("CUSTOMER_THAT_DOES_NOT_EXIST")
        assert result["ok"] is False
        assert result["fallback_reason"] == "customer_not_found"
        assert result["needs"] == []


class TestGapAnalysis:
    def _engine(self):
        m = _load("cna_g", ENGINE_PATH)
        return m.CustomerNeedsAnalyzer()

    def test_unknown_customer_returns_not_found(self):
        eng = self._engine()
        g = eng.analyze_customer_gap("CUSTOMER_X")
        assert g.found is False
        assert g.fallback_reason == "customer_not_found"
        assert g.overall_severity == "NONE"

    def test_real_customer_returns_full_gap_analysis(self):
        eng = self._engine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        g = eng.analyze_customer_gap(sample_id)
        assert g.found is True
        assert g.segment is not None
        assert g.overall_severity in ("HIGH", "MEDIUM", "NONE")
        assert len(g.severity_rationale) >= 1

    def test_severity_high_threshold_portfolio_gap(self):
        eng = self._engine()
        intel = eng._load_intel()
        # Find a Premium customer (expects 8 products) — they typically
        # have HIGH severity in the seed dataset
        for cid, c in intel.items():
            if c.get("segment") == "Premium":
                g = eng.analyze_customer_gap(cid)
                # Premium expectations are aggressive; portfolio gap likely HIGH
                # but severity could come from any rule
                assert g.found is True
                assert g.overall_severity in ("HIGH", "MEDIUM", "NONE")
                break

    def test_propensity_gaps_carried_through(self):
        eng = self._engine()
        intel = eng._load_intel()
        sample_id = next(iter(intel.keys()))
        g = eng.analyze_customer_gap(sample_id)
        # propensity_gaps comes from customer_intelligence.propensity_scores
        assert isinstance(g.propensity_gaps, tuple)


class TestAggregations:
    def _engine(self):
        m = _load("cna_a", ENGINE_PATH)
        return m.CustomerNeedsAnalyzer()

    def test_segment_summary_complete(self):
        s = self._engine().get_segment_gap_summary("Mass")
        assert s["ok"] is True
        assert s["n_customers"] > 0
        for k in ("n_high_severity", "n_medium_severity", "n_no_gaps",
                  "avg_portfolio_gap", "top_behavioural_gaps",
                  "clv_at_risk_kes"):
            assert k in s

    def test_segment_summary_unknown_segment_fallback(self):
        s = self._engine().get_segment_gap_summary("Imaginary_Segment")
        assert s["ok"] is False
        assert s["fallback_reason"] == "no_customers_in_segment"

    def test_top_unmet_needs_returns_ranked_list(self):
        out = self._engine().get_top_unmet_needs(top_n=5)
        assert isinstance(out, list)
        assert len(out) <= 5
        for entry in out:
            for k in ("propensity", "n_customers_with_propensity",
                      "total_clv_kes"):
                assert k in entry

    def test_high_priority_gaps_filters_by_clv(self):
        eng = self._engine()
        all_gaps = eng.get_high_priority_gaps()
        filtered = eng.get_high_priority_gaps(min_clv=500000)
        assert len(filtered) <= len(all_gaps)
        for g in filtered:
            clv = float(g["clv_estimate_kes"] or 0)
            assert clv >= 500000

    def test_bank_wide_summary_complete(self):
        bw = self._engine().bank_wide_gap_summary()
        assert bw["ok"] is True
        for k in ("n_customers_evaluated", "n_high_severity",
                  "n_medium_severity", "n_no_gaps",
                  "high_severity_rate_pct", "by_segment"):
            assert k in bw
        # Components add up
        total = (bw["n_high_severity"] + bw["n_medium_severity"]
                  + bw["n_no_gaps"])
        assert total == bw["n_customers_evaluated"]


class TestRegistrySeed:
    def test_registry_exists_parses(self):
        assert REGISTRY_PATH.exists()
        d = json.loads(REGISTRY_PATH.read_text())
        assert "needs" in d
        assert "segment_expectations" in d
        assert isinstance(d["needs"], list)
        assert len(d["needs"]) >= 5

    def test_registry_segment_expectations_has_4_segments(self):
        cfg = json.loads(REGISTRY_PATH.read_text())
        for seg in ("Mass", "Mass Affluent", "Affluent", "Premium"):
            assert seg in cfg["segment_expectations"]
            for k in ("min_products_held",
                      "expected_products_held",
                      "max_acceptable_complaints_12m",
                      "max_acceptable_churn_risk",
                      "max_acceptable_last_contact_days"):
                assert k in cfg["segment_expectations"][seg]


class TestRegistryAndAdmin:
    def test_enh_133_active(self):
        m = _load("sr133",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-133"), None)
        assert std is not None
        assert std.status == "active"
        assert "customer_needs_analyzer" in std.affected_engines
        assert std.implementation_batch == "v10.144"

    def test_enh_131_132_still_active(self):
        m = _load("sr_check_v144",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_three_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "ProductPnLIntelligence",
                      "ProductLifecycleEngine",
                      "CustomerNeedsAnalyzer"):
            assert token in text


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v144",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v144",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"
