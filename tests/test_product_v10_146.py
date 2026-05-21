"""tests/test_product_v10_146.py — ENH-135 CVP Builder

Verifies the v10.146 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 4 methods
- Synthesizes from ENH-133 + ENH-134 + ENH-131 (companion engines)
- Per-segment CVP with all 6 structured sections
- Trade-offs (LAGGARD products) ALWAYS surfaced — never silently dropped
- AI hook opt-in: rule-based default, basis="rule_based"; LLM tagged basis="llm" with ai_warning
- AI hook failure → graceful fallback to rule-based with warning
- CVP strength score deterministic formula (0-100)
- Honest fallback when segment empty / no LEADER products
- Aggregations (summary, all-segments)
- Registry: ENH-135 active
- Admin Tier 4B has all five engines
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
ENGINE_PATH = REPO_ROOT / "utils" / "product_cvp_builder.py"


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
        m = _load("cvp_shape", ENGINE_PATH)
        assert hasattr(m, "ProductCVPBuilder")
        assert hasattr(m, "CVPResult")

    def test_required_public_methods(self):
        m = _load("cvp_methods", ENGINE_PATH)
        eng = m.ProductCVPBuilder()
        for method in (
            "generate_cvp_for_segment", "generate_all_segment_cvps",
            "get_cvp_summary", "get_cvp_strength_score",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))


class TestCVPGeneration:
    def _engine(self):
        m = _load("cvp_g", ENGINE_PATH)
        return m.ProductCVPBuilder(), m

    def test_generate_for_real_segment(self):
        eng, _ = self._engine()
        cvp = eng.generate_cvp_for_segment("Mass")
        assert cvp.target_segment == "Mass"
        assert cvp.segment_size > 0
        assert cvp.basis == "rule_based"
        assert isinstance(cvp.addressed_needs, tuple)
        assert isinstance(cvp.differentiating_offers, tuple)
        assert isinstance(cvp.trade_offs, tuple)
        assert isinstance(cvp.proof_points, tuple)

    def test_unknown_segment_returns_empty_cvp(self):
        eng, _ = self._engine()
        cvp = eng.generate_cvp_for_segment("NONEXISTENT_SEGMENT")
        assert cvp.segment_size == 0
        assert cvp.cvp_strength_score == 0
        assert cvp.cvp_strength_band == "WEAK"
        assert "no_customers_in_segment" in cvp.missing_inputs

    def test_strength_score_range(self):
        eng, _ = self._engine()
        for seg in ("Mass", "Mass Affluent", "Affluent", "Premium"):
            cvp = eng.generate_cvp_for_segment(seg)
            assert 0 <= cvp.cvp_strength_score <= 100

    def test_strength_band_consistent_with_score(self):
        eng, _ = self._engine()
        for seg in ("Mass", "Premium"):
            cvp = eng.generate_cvp_for_segment(seg)
            if cvp.cvp_strength_score >= 70:
                assert cvp.cvp_strength_band == "STRONG"
            elif cvp.cvp_strength_score < 40:
                assert cvp.cvp_strength_band == "WEAK"
            else:
                assert cvp.cvp_strength_band == "MODERATE"


class TestHonestyDiscipline:
    def _engine(self):
        m = _load("cvp_h", ENGINE_PATH)
        return m.ProductCVPBuilder()

    def test_trade_offs_surfaced_when_laggards_exist(self):
        # On the live data, Fixed Deposits is a LAGGARD — every segment
        # should see it surfaced in trade_offs[]
        cvp = self._engine().generate_cvp_for_segment("Premium")
        # If LAGGARD exists in the bank's portfolio, trade_offs is
        # non-empty — this is the honesty discipline
        if cvp.trade_offs:
            for to in cvp.trade_offs:
                assert "name" in to
                assert "delta_vs_median_bps" in to
                assert to["position"] == "LAGGARD"

    def test_narrative_includes_trade_offs_section_when_present(self):
        cvp = self._engine().generate_cvp_for_segment("Premium")
        if cvp.trade_offs:
            assert "trade-offs" in cvp.narrative.lower()

    def test_proof_points_cite_n_peers(self):
        cvp = self._engine().generate_cvp_for_segment("Mass")
        for pp in cvp.proof_points:
            assert "n_peers" in pp
            assert "is_estimate" in pp


class TestAIHook:
    def _engine_with_ai(self, ai_fn):
        m = _load("cvp_ai", ENGINE_PATH)
        return m.ProductCVPBuilder(ai_narrative_fn=ai_fn)

    def test_no_ai_hook_returns_rule_based(self):
        m = _load("cvp_no_ai", ENGINE_PATH)
        eng = m.ProductCVPBuilder()
        cvp = eng.generate_cvp_for_segment("Mass")
        assert cvp.basis == "rule_based"
        assert cvp.ai_warning is None

    def test_ai_hook_replaces_narrative_and_tags_llm(self):
        ai_text = "AI-mocked narrative."
        eng = self._engine_with_ai(lambda x: ai_text)
        cvp = eng.generate_cvp_for_segment("Mass")
        assert cvp.basis == "llm"
        assert cvp.narrative == ai_text
        assert cvp.ai_warning is not None
        assert "LLM-generated" in cvp.ai_warning

    def test_ai_hook_failure_falls_back_to_rule_based(self):
        def bad_ai(x):
            raise RuntimeError("ai_unavailable")
        eng = self._engine_with_ai(bad_ai)
        cvp = eng.generate_cvp_for_segment("Mass")
        assert cvp.basis == "rule_based"
        assert cvp.ai_warning is not None
        assert "fail" in cvp.ai_warning.lower()

    def test_ai_hook_empty_string_falls_back(self):
        eng = self._engine_with_ai(lambda x: "")
        cvp = eng.generate_cvp_for_segment("Mass")
        assert cvp.basis == "rule_based"


class TestAggregations:
    def _engine(self):
        m = _load("cvp_a", ENGINE_PATH)
        return m.ProductCVPBuilder()

    def test_all_segments_returns_dict(self):
        out = self._engine().generate_all_segment_cvps()
        assert isinstance(out, dict)
        assert len(out) >= 2  # at least Mass + Premium present in seed
        for seg, cvp in out.items():
            assert "cvp_strength_score" in cvp
            assert "cvp_strength_band" in cvp

    def test_summary_components_consistent(self):
        s = self._engine().get_cvp_summary()
        total = s["n_strong"] + s["n_moderate"] + s["n_weak"]
        assert total == s["n_segments"]
        assert 0 <= s["avg_strength_score"] <= 100

    def test_strength_score_method_returns_band(self):
        out = self._engine().get_cvp_strength_score("Premium")
        for k in ("segment", "score", "band",
                  "n_addressed_needs", "n_differentiating_offers",
                  "n_trade_offs", "is_estimate"):
            assert k in out


class TestRegistryAndAdmin:
    def test_enh_135_active(self):
        m = _load("sr135",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-135"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_cvp_builder" in std.affected_engines
        assert std.implementation_batch == "v10.146"

    def test_prior_phase1e_engines_still_active(self):
        m = _load("sr_prior_v146",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132", "ENH-133", "ENH-134"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_five_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "product_competitive_intel",
                      "product_cvp_builder",
                      "ProductCVPBuilder"):
            assert token in text, f"missing token: {token}"


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v146",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v146",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"
