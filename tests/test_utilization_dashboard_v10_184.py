"""tests/test_utilization_dashboard_v10_184.py — v10.184 ENH-160
UtilizationDashboardEngine tests."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_module_imports(self):
        from utils import utilization_dashboard as ud
        for n in ("UtilizationDashboardEngine",
                   "UtilizationObservation",
                   "UtilizationSnapshot",
                   "TeamRollup", "UtilizationBand",
                   "DEFAULT_LOWER_THRESHOLD",
                   "DEFAULT_UPPER_THRESHOLD",
                   "DEFAULT_BREACH_THRESHOLD"):
            assert hasattr(ud, n), f"missing: {n}"


class TestRegistry:
    def test_enh_160_active(self):
        m = _load("reg_v184",
                    REPO_ROOT / "utils" / "standards_registry.py")
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-160"), None)
        assert s.status == "active"
        assert s.affected_engines == ("utilization_dashboard",)
        assert s.implementation_batch == "v10.184"


class TestHubIntegration:
    def test_tier_32_entry(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "UtilizationDashboardEngine" in text
        assert "ENH-160" in text


class TestObservationValidation:
    def test_empty_channel_rejected(self):
        from utils.utilization_dashboard import (
            UtilizationObservation)
        try:
            UtilizationObservation("", "T", "M", 5, 3)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_empty_team_rejected(self):
        from utils.utilization_dashboard import (
            UtilizationObservation)
        try:
            UtilizationObservation("C", "", "M", 5, 3)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_empty_manager_rejected(self):
        from utils.utilization_dashboard import (
            UtilizationObservation)
        try:
            UtilizationObservation("C", "T", "", 5, 3)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_busy_exceeds_available_rejected(self):
        from utils.utilization_dashboard import (
            UtilizationObservation)
        try:
            UtilizationObservation("C", "T", "M", 5, 10)
        except ValueError:
            return
        raise AssertionError("expected reject")

    def test_negative_values_rejected(self):
        from utils.utilization_dashboard import (
            UtilizationObservation)
        for avail, busy in [(-1, 0), (5, -1)]:
            try:
                UtilizationObservation("C", "T", "M", avail, busy)
            except ValueError:
                continue
            raise AssertionError(
                f"expected reject avail={avail} busy={busy}")


class TestThresholdValidation:
    def test_engine_rejects_misordered_thresholds(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine)
        for lo, up, br in [(0.5, 0.4, 0.95),
                            (0.5, 0.85, 0.7),
                            (-0.1, 0.5, 0.95),
                            (0.5, 0.85, 1.5)]:
            try:
                UtilizationDashboardEngine(
                    lower_threshold=lo, upper_threshold=up,
                    breach_threshold=br)
            except ValueError:
                continue
            raise AssertionError(
                f"expected reject for ({lo},{up},{br})")


class TestBandClassification:
    def _eng(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine)
        return UtilizationDashboardEngine()

    def _obs(self, avail, busy):
        from utils.utilization_dashboard import (
            UtilizationObservation)
        return UtilizationObservation("C", "T", "M", avail, busy)

    def test_under_used(self):
        from utils.utilization_dashboard import UtilizationBand
        eng = self._eng()
        s = eng.submit_observation(self._obs(10, 3))
        assert s.band == UtilizationBand.UNDER_USED

    def test_balanced(self):
        from utils.utilization_dashboard import UtilizationBand
        eng = self._eng()
        s = eng.submit_observation(self._obs(10, 7))
        assert s.band == UtilizationBand.BALANCED

    def test_stretched(self):
        from utils.utilization_dashboard import UtilizationBand
        eng = self._eng()
        s = eng.submit_observation(self._obs(10, 9))
        assert s.band == UtilizationBand.STRETCHED

    def test_breach(self):
        from utils.utilization_dashboard import UtilizationBand
        eng = self._eng()
        s = eng.submit_observation(self._obs(10, 10))
        assert s.band == UtilizationBand.BREACH

    def test_zero_available_yields_none_pct(self):
        eng = self._eng()
        s = eng.submit_observation(self._obs(0, 0))
        assert s.utilization_pct is None


class TestTSLEnrichment:
    def _setup(self):
        from utils.tsl_optimization import (
            TSLOptimizationEngine, TSLTarget, TSLChannelType)
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine, UtilizationObservation)
        tsl = TSLOptimizationEngine()
        tsl.set_target(TSLTarget(
            "CC:RETAIL", TSLChannelType.CALL_CENTER,
            0.80, 30, 240))
        eng = UtilizationDashboardEngine(tsl_engine=tsl)
        return eng, UtilizationObservation

    def test_enriches_when_target_exists(self):
        eng, OB = self._setup()
        s = eng.submit_observation(OB(
            "CC:RETAIL", "T", "M", 10, 8,
            observed_arrivals_per_hour=120,
            observed_aht_seconds=240))
        assert s.target_sl == 0.80
        assert s.current_sl is not None
        assert s.sl_meets_target is not None

    def test_no_enrichment_without_load_data(self):
        eng, OB = self._setup()
        s = eng.submit_observation(OB(
            "CC:RETAIL", "T", "M", 10, 8))
        assert s.target_sl == 0.80
        # No arrivals/AHT data → no current_sl
        assert s.current_sl is None
        assert s.sl_meets_target is None

    def test_no_enrichment_for_unknown_channel(self):
        eng, OB = self._setup()
        s = eng.submit_observation(OB(
            "UNKNOWN_CH", "T", "M", 10, 8))
        assert s.target_sl is None


class TestPrivacyFilter:
    def _populate(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine, UtilizationObservation)
        eng = UtilizationDashboardEngine()
        for ch, mgr in [("CC", "M1"), ("EM", "M1"),
                          ("CC", "M2"), ("EM", "M2")]:
            eng.submit_observation(UtilizationObservation(
                ch, f"team-{mgr}", mgr, 5, 3))
        return eng

    def test_manager_only_sees_own(self):
        eng = self._populate()
        m1 = eng.list_snapshots(manager_id="M1")
        assert all(s.manager_id == "M1" for s in m1)
        assert len(m1) == 2

    def test_unknown_manager_returns_empty(self):
        eng = self._populate()
        m9 = eng.list_snapshots(manager_id="M9")
        assert m9 == []

    def test_no_manager_returns_all(self):
        eng = self._populate()
        all_s = eng.list_snapshots()
        assert len(all_s) == 4


class TestLatestPerChannel:
    def test_picks_most_recent(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine, UtilizationObservation)
        eng = UtilizationDashboardEngine()
        t0 = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
        t1 = t0 + timedelta(hours=1)
        eng.submit_observation(UtilizationObservation(
            "CC", "T", "M", 10, 5, observed_at=t0))
        eng.submit_observation(UtilizationObservation(
            "CC", "T", "M", 10, 8, observed_at=t1))
        latest = eng.latest_per_channel()
        assert len(latest) == 1
        assert latest[0].agents_busy == 8


class TestTeamRollup:
    def test_rollup_aggregates_team(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine, UtilizationObservation)
        eng = UtilizationDashboardEngine()
        eng.submit_observation(UtilizationObservation(
            "CC", "TEAM_A", "M", 10, 5))
        eng.submit_observation(UtilizationObservation(
            "EM", "TEAM_A", "M", 6, 4))
        rollup = eng.team_rollup("TEAM_A")
        assert rollup.n_channels == 2
        assert rollup.total_agents_available == 16
        assert rollup.total_agents_busy == 9
        assert rollup.weighted_utilization_pct is not None
        assert abs(
            rollup.weighted_utilization_pct - 9 / 16) < 1e-9

    def test_rollup_empty_team_safe(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine)
        eng = UtilizationDashboardEngine()
        rollup = eng.team_rollup("MISSING_TEAM",
                                   manager_id="M")
        assert rollup.n_channels == 0
        assert rollup.weighted_utilization_pct is None


class TestBreaches:
    def test_only_breach_band_returned(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine, UtilizationObservation)
        eng = UtilizationDashboardEngine()
        eng.submit_observation(UtilizationObservation(
            "BAD", "T", "M", 10, 10))   # 1.0 = breach
        eng.submit_observation(UtilizationObservation(
            "OK", "T", "M", 10, 7))     # 0.7 = balanced
        breaches = eng.list_breaches()
        assert len(breaches) == 1
        assert breaches[0].channel_key == "BAD"


class TestHonestDeferrals:
    def test_board_summary_names_deferrals(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine)
        eng = UtilizationDashboardEngine()
        b = eng.board_summary()
        for key in ("REAL_TIME_TELEPHONY_FEED",
                     "BREAK_TIME_DETECTION",
                     "ADHERENCE_TRACKING",
                     "HISTORICAL_TREND_PERSISTENCE"):
            assert key in b["deferrals"]
            assert "DEFERRED" in b["deferrals"][key]


class TestNoRegression:
    def test_audit_still_155(self):
        m = _load("audit_v184",
                    REPO_ROOT / "scripts" / "audit.py")
        assert len(m.GATES) == 155
        for gid, gfn in m.GATES:
            assert gfn()["passed"] is True

    def test_v183_balancing_works(self):
        from utils.cross_channel_balancing import (
            CrossChannelBalancingEngine)
        from utils.tsl_optimization import TSLOptimizationEngine
        bal = CrossChannelBalancingEngine(TSLOptimizationEngine())
        assert "ENH-159" in bal.board_summary()["engine"]
