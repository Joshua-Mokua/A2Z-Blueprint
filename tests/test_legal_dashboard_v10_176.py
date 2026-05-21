"""tests/test_legal_dashboard_v10_176.py — ENH-228 Legal Dashboard.

Verifies the cross-engine composition engine that pulls board_summary()
from the 6 Legal source engines (ENH-222..227) and produces a unified
GC dashboard with health score, banding, and risk heatmap.
"""
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path
from datetime import date, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    """The engine module exports exactly the expected public surface."""

    def test_imports(self):
        from utils.legal_dashboard import (
            HealthBand, DashboardSection, AlertSeverity,
            DataAvailability, TransitionOutcome, SectionView,
            DashboardComposition, LegalDashboardEngine,
        )
        assert HealthBand is not None
        assert LegalDashboardEngine is not None

    def test_health_band_values(self):
        from utils.legal_dashboard import HealthBand
        assert HealthBand.EXCELLENT.value == "EXCELLENT"
        assert HealthBand.GOOD.value == "GOOD"
        assert HealthBand.CONCERNING.value == "CONCERNING"
        assert HealthBand.CRITICAL.value == "CRITICAL"

    def test_seven_dashboard_sections(self):
        from utils.legal_dashboard import DashboardSection
        assert len(DashboardSection) == 7
        names = {s.value for s in DashboardSection}
        assert names == {
            "CONTRACTS", "MATTERS", "SPEND", "OBLIGATIONS",
            "HOLDS", "COUNSEL", "CLAUSES",
        }

    def test_four_alert_severities(self):
        from utils.legal_dashboard import AlertSeverity
        assert len(AlertSeverity) == 4
        assert AlertSeverity.LOW.value == "LOW"
        assert AlertSeverity.CRITICAL.value == "CRITICAL"

    def test_three_data_availabilities(self):
        from utils.legal_dashboard import DataAvailability
        assert len(DataAvailability) == 3
        assert DataAvailability.FULL.value == "FULL"
        assert DataAvailability.UNAVAILABLE.value == "UNAVAILABLE"


class TestRegistry:
    def test_enh228_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        s = next((x for x in STANDARDS_REGISTRY
                  if x.standard_id == "ENH-228"), None)
        assert s is not None
        assert s.status == "active"
        assert s.affected_engines == ("legal_dashboard",)
        assert s.implementation_batch == "v10.176"


class TestHubIntegration:
    def test_legal_dashboard_in_tier_31(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text(
            encoding="utf-8")
        assert "legal_dashboard" in text
        assert "LegalDashboardEngine" in text
        assert "ENH-228" in text


class TestEmptyEngineWiring:
    """When all source engines are None, dashboard reports honestly."""

    def test_all_none_returns_critical(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        b = eng.board_summary()
        assert b["overall_health"] == 0.0
        assert b["health_band"] == "CRITICAL"
        assert b["n_sections_unavail"] == 6
        assert b["n_sections_full"] == 0
        assert b["partial_data"] is True
        assert b["divisor"] == 0

    def test_all_none_six_sections_returned(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        b = eng.board_summary()
        assert len(b["sections"]) == 6
        for s in b["sections"]:
            assert s["availability"] == "UNAVAILABLE"
            assert s["health"] == 0.0
            assert s["severity"] == "CRITICAL"

    def test_all_none_heatmap_has_seven_cells(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        hm = eng.risk_heatmap()
        assert len(hm) == 7
        # 6 sections critical + 1 contracts MEDIUM
        assert hm["CONTRACTS"] == "MEDIUM"
        assert hm["OBLIGATIONS"] == "CRITICAL"


class TestFullEngineWiring:
    """When all engines wired but empty, expect EXCELLENT (100%)."""

    def _wire_all(self):
        from utils.obligation_tracking import ObligationTrackingEngine
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        from utils.clause_library import ClauseLibraryEngine
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        from utils.legal_dashboard import LegalDashboardEngine
        return LegalDashboardEngine(
            obligation_engine=ObligationTrackingEngine(),
            case_engine=LegalCaseManagementEngine(),
            spend_engine=LegalSpendManagementEngine(),
            counsel_engine=OutsideCounselPortalEngine(),
            clause_engine=ClauseLibraryEngine(),
            hold_engine=LegalHoldManagementEngine(),
        )

    def test_all_empty_engines_excellent(self):
        eng = self._wire_all()
        b = eng.board_summary()
        assert b["overall_health"] == 100.0
        assert b["health_band"] == "EXCELLENT"
        assert b["n_sections_full"] == 6
        assert b["n_sections_unavail"] == 0
        assert b["partial_data"] is False
        assert b["divisor"] == 6

    def test_all_empty_engines_low_severity(self):
        eng = self._wire_all()
        hm = eng.risk_heatmap()
        # 6 LOW + 1 CONTRACTS MEDIUM
        assert hm["OBLIGATIONS"] == "LOW"
        assert hm["MATTERS"] == "LOW"
        assert hm["CONTRACTS"] == "MEDIUM"


class TestObligationsHealthDrop:
    """Register breached obligations, observe section health drop."""

    def test_one_in_four_breached_drops_health(self):
        from utils.obligation_tracking import (
            ObligationTrackingEngine, ObligationKind)
        from utils.legal_dashboard import LegalDashboardEngine

        ob = ObligationTrackingEngine()
        # 3 future, 1 past
        for i, days in enumerate([200, 200, 200, -10]):
            ob.register_obligation(
                contract_id=f"C-{i+1}", counterparty="X",
                title=f"t{i}", description="d",
                kind=ObligationKind.CONTRACT_RENEWAL,
                deadline_date=(
                    date.today() + timedelta(days=days)).isoformat(),
                owner_role="LEGAL_HEAD",
            )

        dash = LegalDashboardEngine(obligation_engine=ob)
        b = dash.board_summary()
        ob_sec = next(s for s in b["sections"]
                      if s["section"] == "OBLIGATIONS")
        # 3/4 = 75% — MEDIUM
        assert ob_sec["health"] == 75.0
        assert ob_sec["severity"] == "MEDIUM"
        assert ob_sec["availability"] == "FULL"


class TestBrokenEngineHandling:
    """When an engine raises, it's marked UNAVAILABLE and excluded
    from the average."""

    def test_broken_engine_marked_unavailable(self):
        from utils.legal_dashboard import LegalDashboardEngine
        from utils.obligation_tracking import (
            ObligationTrackingEngine)

        class Broken:
            def board_summary(self):
                raise RuntimeError("simulated")

        dash = LegalDashboardEngine(
            obligation_engine=ObligationTrackingEngine(),
            case_engine=Broken(),
        )
        b = dash.board_summary()
        matters_sec = next(s for s in b["sections"]
                           if s["section"] == "MATTERS")
        assert matters_sec["availability"] == "UNAVAILABLE"
        assert matters_sec["health"] == 0.0
        assert matters_sec["severity"] == "CRITICAL"
        # Divisor should exclude UNAVAILABLE sections
        assert b["divisor"] == 1  # only obligations was wired
        assert b["partial_data"] is True

    def test_engine_returning_non_dict_marked_unavailable(self):
        from utils.legal_dashboard import LegalDashboardEngine

        class Weird:
            def board_summary(self):
                return "not a dict"

        dash = LegalDashboardEngine(case_engine=Weird())
        b = dash.board_summary()
        matters_sec = next(s for s in b["sections"]
                           if s["section"] == "MATTERS")
        assert matters_sec["availability"] == "UNAVAILABLE"


class TestHealthBanding:
    """Verify the 4-band classification thresholds."""

    def test_band_excellent_at_90(self):
        from utils.legal_dashboard import _band, HealthBand
        assert _band(95.0) == HealthBand.EXCELLENT
        assert _band(85.0) == HealthBand.EXCELLENT

    def test_band_good_at_75(self):
        from utils.legal_dashboard import _band, HealthBand
        assert _band(75.0) == HealthBand.GOOD
        assert _band(70.0) == HealthBand.GOOD

    def test_band_concerning_at_60(self):
        from utils.legal_dashboard import _band, HealthBand
        assert _band(60.0) == HealthBand.CONCERNING
        assert _band(50.0) == HealthBand.CONCERNING

    def test_band_critical_below_50(self):
        from utils.legal_dashboard import _band, HealthBand
        assert _band(49.9) == HealthBand.CRITICAL
        assert _band(0.0) == HealthBand.CRITICAL


class TestSeverityFromHealth:
    """The heatmap inverts health → severity."""

    def test_high_health_low_severity(self):
        from utils.legal_dashboard import (
            _severity_from_health, AlertSeverity)
        assert _severity_from_health(95.0) == AlertSeverity.LOW
        assert _severity_from_health(85.0) == AlertSeverity.LOW

    def test_low_health_critical_severity(self):
        from utils.legal_dashboard import (
            _severity_from_health, AlertSeverity)
        assert _severity_from_health(40.0) == AlertSeverity.CRITICAL


class TestHonestDeferrals:
    """The board_summary names every deferred capability honestly."""

    def test_deferrals_named(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        b = eng.board_summary()
        assert "DEFERRED" in b["real_time_refresh"]
        assert "DEFERRED" in b["trend_analysis"]
        assert "ENH-230" in b["trend_analysis"]
        assert "DEFERRED" in b["doc_repository_health"]
        assert "ENH-229" in b["doc_repository_health"]


class TestPortfolioSummary:
    """The board_summary surface for examiner consumption."""

    def test_engine_name_and_basis(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        b = eng.board_summary()
        assert b["engine"] == "ENH-228 LegalDashboardEngine"
        assert "GC governance" in b["regulatory_basis"]

    def test_composed_at_utc_iso(self):
        from utils.legal_dashboard import LegalDashboardEngine
        eng = LegalDashboardEngine()
        b = eng.board_summary()
        assert "T" in b["composed_at_utc"]
        assert "+" in b["composed_at_utc"] or "Z" in b["composed_at_utc"]


class TestNoRegression:
    """Adding ENH-228 must not break the prior 6 Legal engines."""

    def test_obligation_engine_still_works(self):
        from utils.obligation_tracking import (
            ObligationTrackingEngine)
        eng = ObligationTrackingEngine()
        assert "ENH-222" in eng.board_summary()["engine"]

    def test_case_engine_still_works(self):
        from utils.legal_case_management import (
            LegalCaseManagementEngine)
        eng = LegalCaseManagementEngine()
        assert "ENH-223" in eng.board_summary()["engine"]

    def test_counsel_engine_still_works(self):
        from utils.outside_counsel_portal import (
            OutsideCounselPortalEngine)
        eng = OutsideCounselPortalEngine()
        assert "ENH-224" in eng.board_summary()["engine"]

    def test_spend_engine_still_works(self):
        from utils.legal_spend_management import (
            LegalSpendManagementEngine)
        eng = LegalSpendManagementEngine()
        assert "ENH-225" in eng.board_summary()["engine"]

    def test_clause_engine_still_works(self):
        from utils.clause_library import ClauseLibraryEngine
        eng = ClauseLibraryEngine()
        assert "ENH-226" in eng.board_summary()["engine"]

    def test_hold_engine_still_works(self):
        from utils.legal_hold_management import (
            LegalHoldManagementEngine)
        eng = LegalHoldManagementEngine()
        assert "ENH-227" in eng.board_summary()["engine"]
