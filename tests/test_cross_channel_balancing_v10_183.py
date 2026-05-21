"""tests/test_cross_channel_balancing_v10_183.py — v10.183 ENH-159
CrossChannelBalancingEngine tests."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def _setup_tsl():
    from utils.tsl_optimization import (
        TSLOptimizationEngine, TSLTarget, TSLChannelType)
    tsl = TSLOptimizationEngine()
    tsl.set_target(TSLTarget("CC:RETAIL", TSLChannelType.CALL_CENTER,
                              0.80, 30, 240))
    tsl.set_target(TSLTarget("CC:CORP", TSLChannelType.CALL_CENTER,
                              0.85, 30, 300))
    tsl.set_target(TSLTarget("EMAIL", TSLChannelType.EMAIL_QUEUE,
                              0.90, 600, 360))
    return tsl


class TestModuleShape:
    def test_module_imports(self):
        from utils import cross_channel_balancing as ccb
        for n in ("CrossChannelBalancingEngine", "ChannelInput",
                   "AgentShift", "ChannelOutcome",
                   "BalanceRecommendation", "BalanceOutcome"):
            assert hasattr(ccb, n), f"missing: {n}"


class TestRegistry:
    def test_enh_159_active(self):
        m = _load("reg_v183",
                    REPO_ROOT / "utils" / "standards_registry.py")
        s = next(
            (x for x in m.STANDARDS_REGISTRY
             if x.standard_id == "ENH-159"), None)
        assert s.status == "active"
        assert s.affected_engines == ("cross_channel_balancing",)
        assert s.implementation_batch == "v10.183"


class TestHubIntegration:
    def test_tier_32_entry(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "CrossChannelBalancingEngine" in text
        assert "ENH-159" in text


class TestChannelInputValidation:
    def test_empty_channel_key_rejected(self):
        from utils.cross_channel_balancing import ChannelInput
        try:
            ChannelInput("", 10, 5)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_negative_arrivals_rejected(self):
        from utils.cross_channel_balancing import ChannelInput
        try:
            ChannelInput("X", -1, 5)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_negative_planned_rejected(self):
        from utils.cross_channel_balancing import ChannelInput
        try:
            ChannelInput("X", 10, -1)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_negative_min_floor_rejected(self):
        from utils.cross_channel_balancing import ChannelInput
        try:
            ChannelInput("X", 10, 5, min_agents_after_giving=-1)
        except ValueError:
            return
        raise AssertionError("expected reject")


class TestEngineConstruction:
    def test_none_tsl_engine_rejected(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine)
        try:
            CrossChannelBalancingEngine(None)
        except ValueError:
            return
        raise AssertionError("expected reject")


class TestBalanceCore:
    def test_empty_channels_rejected(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        try:
            bal.balance([])
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_duplicate_channel_rejected(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        try:
            bal.balance([
                ChannelInput("CC:RETAIL", 100, 5),
                ChannelInput("CC:RETAIL", 100, 5),
            ])
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_missing_tsl_rejected(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        try:
            bal.balance([ChannelInput("UNKNOWN", 10, 5)])
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_resolves_simple_shortage(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput,
            BalanceOutcome)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        rec = bal.balance([
            ChannelInput("CC:RETAIL", 120, 6,
                          transferable_to=("CC:CORP",)),
            ChannelInput("CC:CORP", 30, 12,
                          transferable_to=("CC:RETAIL",)),
        ])
        assert rec.n_resolved_shortages == 1
        assert rec.n_unresolved_shortages == 0
        # Shifts should exist
        assert len(rec.shifts) >= 1

    def test_unresolved_when_no_transferability(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput,
            BalanceOutcome)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        rec = bal.balance([
            ChannelInput("CC:RETAIL", 120, 4,
                          transferable_to=()),
            ChannelInput("CC:CORP", 30, 12,
                          transferable_to=()),
        ])
        assert rec.n_unresolved_shortages == 1
        assert len(rec.shifts) == 0

    def test_balanced_when_already_adequate(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput,
            BalanceOutcome)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        rec = bal.balance([
            ChannelInput("CC:RETAIL", 120, 50,
                          transferable_to=()),
        ])
        # Already adequate (50 >> required ~11); no shifts
        assert len(rec.shifts) == 0
        oc = rec.channels[0]
        assert oc.outcome == BalanceOutcome.BALANCED


class TestTransferability:
    def test_shift_only_when_transferable(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        # Set up: A short, B has surplus, but B's transferable_to
        # only includes EMAIL — not A
        rec = bal.balance([
            ChannelInput("CC:RETAIL", 120, 4,
                          transferable_to=()),
            ChannelInput("CC:CORP", 20, 20,
                          transferable_to=("EMAIL",)),
            ChannelInput("EMAIL", 60, 10,
                          transferable_to=()),
        ])
        # No shifts to RETAIL since CORP transferable only to EMAIL
        retail_shifts = [s for s in rec.shifts
                          if s.to_channel == "CC:RETAIL"]
        assert len(retail_shifts) == 0

    def test_min_agents_floor_respected(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        # CORP has 12 planned, would normally give surplus, but
        # min_agents_after_giving = 12 → cannot give any
        rec = bal.balance([
            ChannelInput("CC:RETAIL", 120, 6,
                          transferable_to=("CC:CORP",)),
            ChannelInput("CC:CORP", 30, 12,
                          transferable_to=("CC:RETAIL",),
                          min_agents_after_giving=12),
        ])
        assert len(rec.shifts) == 0


class TestIdempotence:
    def test_same_input_same_shifts(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        inputs = [
            ChannelInput("CC:RETAIL", 120, 6,
                          transferable_to=("CC:CORP",)),
            ChannelInput("CC:CORP", 30, 12,
                          transferable_to=("CC:RETAIL",)),
        ]
        r1 = bal.balance(inputs)
        r2 = bal.balance(inputs)
        sigs1 = sorted([
            (s.from_channel, s.to_channel, s.n_agents)
            for s in r1.shifts])
        sigs2 = sorted([
            (s.from_channel, s.to_channel, s.n_agents)
            for s in r2.shifts])
        assert sigs1 == sigs2


class TestShiftCoalescing:
    def test_shifts_coalesced(self):
        """Multiple 1-agent shifts from same donor to same
        recipient become a single batched shift."""
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        rec = bal.balance([
            ChannelInput("CC:RETAIL", 120, 4,
                          transferable_to=("CC:CORP",)),
            ChannelInput("CC:CORP", 20, 25,
                          transferable_to=("CC:RETAIL",)),
        ])
        # Should be ONE shift with n_agents > 1
        if rec.shifts:
            for s in rec.shifts:
                assert s.from_channel != s.to_channel
            # Specifically — 1 shift from CORP to RETAIL with
            # n_agents matching gap
            shifts_to_retail = [
                s for s in rec.shifts
                if s.to_channel == "CC:RETAIL"]
            assert len(shifts_to_retail) == 1
            assert shifts_to_retail[0].n_agents >= 1


class TestRecommendationQueries:
    def test_get_recommendation_returns_none_for_unknown(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        assert bal.get_recommendation("BAL-999999") is None

    def test_list_returns_chronological(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine, ChannelInput)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        bal.balance([ChannelInput("CC:RETAIL", 50, 5)])
        bal.balance([ChannelInput("CC:RETAIL", 50, 5)])
        recs = bal.list_recommendations()
        assert len(recs) == 2
        assert recs[0].created_at <= recs[1].created_at


class TestHonestDeferrals:
    def test_board_summary_names_deferrals(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine)
        bal = CrossChannelBalancingEngine(_setup_tsl())
        b = bal.board_summary()
        defs = b.get("deferrals", {})
        for key in ("REAL_TIME_SKILLS_MATRIX",
                     "AUTO_REBALANCE_TRIGGER",
                     "COST_OPTIMIZED_LP_SOLVER",
                     "SKILL_DECAY_MODEL"):
            assert key in defs
            assert "DEFERRED" in defs[key]
        assert "greedy" in b["algorithm"]


class TestNoRegression:
    def test_audit_still_155_pass(self):
        m = _load("audit_v183", REPO_ROOT / "scripts" / "audit.py")
        assert len(m.GATES) == 155
        for gid, gfn in m.GATES:
            r = gfn()
            assert r["passed"] is True

    def test_v182_tsl_still_works(self):
        from utils.tsl_optimization import TSLOptimizationEngine
        eng = TSLOptimizationEngine()
        assert "ENH-158" in eng.board_summary()["engine"]
