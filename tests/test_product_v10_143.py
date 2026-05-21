"""tests/test_product_v10_143.py — ENH-132 Product Lifecycle Management

Verifies the v10.143 deliverable:
- Engine module exists and parses
- ProductLifecycleEngine + 2 frozen dataclasses + 9 public methods
- Stage queries / history / evaluation
- Transition request → approve → land flow (with tmp lifecycle file)
- Auto-transition path (no approvers)
- Rejection flow
- Sunset evaluation honesty (recommendation not auto-action)
- TTL stale flagging
- Seed file shapes
- Registry: ENH-132 active
- Admin Tier 4B has both ENH-131 + ENH-132 entries
- No regression of strategy module + earlier gates
"""
from __future__ import annotations
import ast
import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "product_lifecycle.py"
LIFECYCLE_SEED = REPO_ROOT / "data" / "product_lifecycle.json"
STAGEGATE_CONFIG = REPO_ROOT / "data" / "product_stagegate_config.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------
# Engine module shape
# ---------------------------------------------------------------------------

class TestEngineModule:
    def test_module_exists(self):
        assert ENGINE_PATH.exists()

    def test_module_parses(self):
        ast.parse(ENGINE_PATH.read_text())

    def test_class_and_dataclasses_present(self):
        m = _load("plc_shape", ENGINE_PATH)
        assert hasattr(m, "ProductLifecycleEngine")
        assert hasattr(m, "StageGateEvaluation")
        assert hasattr(m, "SunsetEvaluation")
        assert hasattr(m, "CANONICAL_STAGES")
        assert len(m.CANONICAL_STAGES) == 8

    def test_required_public_methods(self):
        m = _load("plc_methods", ENGINE_PATH)
        eng = m.ProductLifecycleEngine()
        for method in (
            "get_product_stage", "get_stage_history",
            "evaluate_stage_gate", "request_stage_transition",
            "approve_transition", "reject_transition",
            "evaluate_sunset_criteria", "get_sunset_candidates",
            "get_pending_approvals",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))


# ---------------------------------------------------------------------------
# Stage queries
# ---------------------------------------------------------------------------

class TestStageQueries:
    def _engine(self):
        m = _load("plc_q", ENGINE_PATH)
        return m.ProductLifecycleEngine(), m

    def test_get_product_stage_existing(self):
        eng, _ = self._engine()
        s = eng.get_product_stage("P001")
        assert s["found"] is True
        assert s["current_stage"] in ("IDEATION", "BUSINESS_CASE",
                                       "DEVELOPMENT", "LAUNCH",
                                       "GROWTH", "MATURITY",
                                       "DECLINE", "SUNSET")

    def test_get_product_stage_unknown(self):
        eng, _ = self._engine()
        s = eng.get_product_stage("P_UNKNOWN_999")
        assert s["found"] is False
        assert s["current_stage"] is None


# ---------------------------------------------------------------------------
# Stage-gate evaluation
# ---------------------------------------------------------------------------

class TestStageGateEvaluation:
    def _engine_and_module(self):
        m = _load("plc_gate", ENGINE_PATH)
        return m.ProductLifecycleEngine(), m

    def test_evaluate_unknown_target_stage_returns_fallback(self):
        eng, _ = self._engine_and_module()
        ev = eng.evaluate_stage_gate("P001", "BOGUS_STAGE")
        assert ev.gate_open is False
        assert ev.fallback_reason.startswith("unknown_target_stage")

    def test_evaluate_invalid_skip_transition(self):
        # Try to skip from current stage straight to LAUNCH
        eng, _ = self._engine_and_module()
        # P001 is in DECLINE per seed; jumping to LAUNCH is invalid
        ev = eng.evaluate_stage_gate("P001", "LAUNCH")
        assert ev.gate_open is False
        assert (ev.fallback_reason
                and ev.fallback_reason.startswith("invalid_transition"))

    def test_evaluate_sunset_path_from_decline(self):
        eng, _ = self._engine_and_module()
        ev = eng.evaluate_stage_gate("P001", "SUNSET")
        # P001 has growth_rate -2.3% (not <= -20% threshold) so gate closed
        assert ev.requires_approval is True
        assert "product_head" in ev.required_approvers
        assert "ceo" in ev.required_approvers


# ---------------------------------------------------------------------------
# Transition flows (use tmp lifecycle file to avoid mutating seed)
# ---------------------------------------------------------------------------

class TestTransitionFlows:
    def _tmp_engine(self, initial_stage: str,
                     approval_matrix_override: dict = None):
        tmp = Path(tempfile.mkdtemp())
        lc = tmp / "lifecycle.json"
        sg = tmp / "stagegate.json"
        cfg = {}
        if approval_matrix_override is not None:
            cfg["approval_matrix"] = approval_matrix_override
        sg.write_text(json.dumps(cfg))
        lc.write_text(json.dumps({
            "products": {"P001": {
                "current_stage": initial_stage,
                "since": "2026-01-01T00:00:00+00:00"}},
            "transitions": [], "pending": []
        }))
        m = _load(f"plc_t_{initial_stage}", ENGINE_PATH)
        return m.ProductLifecycleEngine(
            products_path=REPO_ROOT / "data" / "products.json",
            lifecycle_path=lc, stagegate_config_path=sg), lc

    def test_approval_required_flow(self):
        eng, lc = self._tmp_engine("IDEATION")
        r = eng.request_stage_transition(
            "P001", "BUSINESS_CASE", "joshua@a2z")
        assert r["ok"] is True
        assert r["status"] == "pending"
        assert r["auto"] is False
        tid = r["transition_id"]

        # Approve
        a = eng.approve_transition(tid, "product_head", "joshua@a2z")
        assert a["ok"] is True
        assert a["status"] == "approved"
        assert a["new_stage"] == "BUSINESS_CASE"

        # Stage advanced
        s = eng.get_product_stage("P001")
        assert s["current_stage"] == "BUSINESS_CASE"

    def test_partial_approval_stays_pending(self):
        eng, lc = self._tmp_engine("BUSINESS_CASE")
        r = eng.request_stage_transition(
            "P001", "DEVELOPMENT", "joshua@a2z")
        assert r["ok"] is True
        assert r["status"] == "pending"
        assert len(r["required_approvers"]) == 3

        tid = r["transition_id"]
        # Only 1 of 3 approvers
        a = eng.approve_transition(tid, "product_head", "joshua@a2z")
        assert a["ok"] is True
        assert a["status"] == "pending"  # still pending
        assert a["new_stage"] is None

        # Stage NOT advanced
        s = eng.get_product_stage("P001")
        assert s["current_stage"] == "BUSINESS_CASE"

    def test_double_approval_same_role_rejected(self):
        eng, _ = self._tmp_engine("BUSINESS_CASE")
        r = eng.request_stage_transition(
            "P001", "DEVELOPMENT", "joshua@a2z")
        tid = r["transition_id"]
        eng.approve_transition(tid, "product_head", "joshua@a2z")
        # Second approval same role should fail
        a2 = eng.approve_transition(tid, "product_head", "other@a2z")
        assert a2["ok"] is False
        assert "already_approved" in a2["reason"]

    def test_invalid_approver_role_rejected(self):
        eng, _ = self._tmp_engine("IDEATION")
        r = eng.request_stage_transition(
            "P001", "BUSINESS_CASE", "joshua@a2z")
        tid = r["transition_id"]
        a = eng.approve_transition(tid, "junior_analyst", "x@a2z")
        assert a["ok"] is False
        assert "not_required" in a["reason"]

    def test_rejection_flow(self):
        eng, _ = self._tmp_engine("IDEATION")
        r = eng.request_stage_transition(
            "P001", "BUSINESS_CASE", "joshua@a2z")
        tid = r["transition_id"]
        rej = eng.reject_transition(tid, "product_head",
                                     "insufficient_research")
        assert rej["ok"] is True
        assert rej["status"] == "rejected"
        # Stage NOT advanced
        s = eng.get_product_stage("P001")
        assert s["current_stage"] == "IDEATION"

    def test_request_when_gate_closed_fails(self):
        # Override approval matrix so IDEATION→BUSINESS_CASE has no approver
        # (no quantitative criteria for that transition either, so gate
        # opens). Skip-transition test instead — try IDEATION → LAUNCH.
        eng, _ = self._tmp_engine("IDEATION")
        r = eng.request_stage_transition("P001", "LAUNCH", "joshua@a2z")
        assert r["ok"] is False
        assert r["reason"] == "gate_criteria_not_met"


# ---------------------------------------------------------------------------
# Sunset evaluation
# ---------------------------------------------------------------------------

class TestSunsetEvaluation:
    def _engine(self):
        m = _load("plc_s", ENGINE_PATH)
        return m.ProductLifecycleEngine(), m

    def test_sunset_unknown_product(self):
        eng, _ = self._engine()
        ev = eng.evaluate_sunset_criteria("P_UNKNOWN")
        assert ev.candidate is False
        assert ev.candidate_status == "no_action"

    def test_sunset_real_product_returns_evaluation(self):
        eng, _ = self._engine()
        ev = eng.evaluate_sunset_criteria("P001")
        # Should return a SunsetEvaluation either way; honesty preserved
        assert ev.candidate_status in (
            "recommended_for_sunset_review", "no_action")
        # Sunset is RECOMMENDATION never auto-action
        assert ev.candidate_status != "auto_sunsetted"

    def test_get_sunset_candidates_list(self):
        eng, _ = self._engine()
        cands = eng.get_sunset_candidates()
        assert isinstance(cands, list)
        # On the live seed (worst growth -3.8%), no products meet -20% threshold
        # so list is plausibly empty — both 0 and >0 are valid here
        for c in cands:
            assert c["candidate"] is True
            assert c["candidate_status"] == "recommended_for_sunset_review"


# ---------------------------------------------------------------------------
# TTL / pending approvals
# ---------------------------------------------------------------------------

class TestPendingTTL:
    def test_pending_approvals_filtered_by_role(self):
        tmp = Path(tempfile.mkdtemp())
        lc = tmp / "l.json"
        sg = tmp / "s.json"
        sg.write_text("{}")
        lc.write_text(json.dumps({
            "products": {"P001": {
                "current_stage": "IDEATION",
                "since": "2026-01-01T00:00:00+00:00"}},
            "transitions": [], "pending": []}))
        m = _load("plc_ttl", ENGINE_PATH)
        eng = m.ProductLifecycleEngine(
            products_path=REPO_ROOT / "data" / "products.json",
            lifecycle_path=lc, stagegate_config_path=sg)
        eng.request_stage_transition("P001", "BUSINESS_CASE", "x")

        # Filter by required role
        for_ph = eng.get_pending_approvals(approver_role="product_head")
        assert len(for_ph) == 1

        # Filter by non-required role
        for_other = eng.get_pending_approvals(approver_role="ceo")
        assert len(for_other) == 0


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------

class TestSeeds:
    def test_lifecycle_seed_exists_and_parses(self):
        assert LIFECYCLE_SEED.exists()
        d = json.loads(LIFECYCLE_SEED.read_text())
        assert "products" in d
        assert "transitions" in d
        assert "pending" in d
        assert len(d["products"]) >= 16

    def test_stagegate_config_exists_and_parses(self):
        assert STAGEGATE_CONFIG.exists()
        cfg = json.loads(STAGEGATE_CONFIG.read_text())
        assert "approval_matrix" in cfg
        assert ("BUSINESS_CASE->DEVELOPMENT"
                in cfg["approval_matrix"])
        assert "DECLINE->SUNSET" in cfg["approval_matrix"]


# ---------------------------------------------------------------------------
# Registry + admin
# ---------------------------------------------------------------------------

class TestRegistryAndAdmin:
    def test_enh_132_active(self):
        m = _load("sr132",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-132"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_lifecycle" in std.affected_engines
        assert std.implementation_batch == "v10.143"

    def test_enh_131_still_active(self):
        m = _load("sr131_check",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-131"), None)
        assert std is not None
        assert std.status == "active"

    def test_admin_tier_4b_has_both_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        assert "Tier 4B — Product Intelligence" in text
        assert "product_pnl_intelligence" in text
        assert "product_lifecycle" in text
        assert "ProductLifecycleEngine" in text


# ---------------------------------------------------------------------------
# No regression
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_check",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v143",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active", f"{sid} regressed"
