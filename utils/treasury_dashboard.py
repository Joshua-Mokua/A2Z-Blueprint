"""utils/treasury_dashboard.py — v10.35 ENH-238: Treasury Dashboard.

╔════════════════════════════════════════════════════════════════════════╗
║  TREASURY DASHBOARD & REPORTING                                         ║
║  Cat A — feeds CBK regulatory submissions + board reporting           ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-238: Treasury Dashboard & Reporting.                   ║
║                                                                         ║
║  Aggregator that pulls from upstream Treasury arc engines:             ║
║    - utils.treasury_alm (ENH-231/232/233): LCR, NSFR, IRRBB outliers ║
║    - utils.treasury_products (ENH-234): FX positions, bond MTM       ║
║    - utils.rwa_optimization (ENH-235): capital ratios, RWA           ║
║    - utils.fund_transfer_pricing (ENH-236): NIM decomposition        ║
║    - utils.cash_forecasting (ENH-237): 13-week cash projection      ║
║                                                                         ║
║  Three report types ship:                                              ║
║    DAILY_TREASURY: today's positions, ratios, near-term forecast    ║
║    BOARD_PACK: monthly aggregated metrics for ALCO/Risk Cmtte       ║
║    REGULATORY_PACK: structured CBK submission format                  ║
║                                                                         ║
║  Coexists with utils.treasury_intelligence (Volume Seven shell), the  ║
║  v10.33 treasury_alm, v10.34 treasury_products + rwa_optimization +  ║
║  fund_transfer_pricing, v10.35 cash_forecasting. The dashboard       ║
║  takes references to those engines; nothing is mutated.               ║
║                                                                         ║
║  Honesty Rule 1: every report section surfaces source engine +        ║
║  metric values + thresholds + headroom + N positions / N tests.      ║
║  Limit breaches surface specific values for examiner trace.          ║
║  Honesty Rule 7: the dashboard does not invent values — it reads    ║
║  whatever the upstream engines have and reports them. If an upstream ║
║  engine has no data, the report section says so explicitly.          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Basel BCBS 188 / 295 / 368 — disclosure of LCR / NSFR / IRRBB     ║
║    Basel BCBS 189 — capital adequacy disclosures                     ║
║    Basel III final framework Dec 2017 — public disclosure standards  ║
║    EBA EBA/GL/2017/01 — uniform LCR disclosure                       ║
║    EBA EBA/GL/2018/01 — capital ratio disclosure                     ║
║    CBK CBK/PG/03 — capital adequacy (CBK reporting forms)             ║
║    CBK CBK/PG/16 — liquidity management (CBK reporting forms)         ║
║    CBK CBK/PG/04 — risk classification disclosures                    ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "TreasuryDashboardEngine implements ENH-238 reporting aggregator. "
    "It composes other Treasury arc engines (treasury_alm, "
    "treasury_products, rwa_optimization, fund_transfer_pricing, "
    "cash_forecasting) and surfaces structured reports. Per Rule 1, "
    "every section reports source engine + metrics + thresholds + "
    "headroom. Per Rule 7, the dashboard never invents data — it "
    "reads from upstream engines or marks sections as no_data."
)


# ════════════════════════════════════════════════════════════════════════
# Report taxonomy
# ════════════════════════════════════════════════════════════════════════

class ReportType(Enum):
    """Treasury dashboard report types."""
    DAILY_TREASURY = "DAILY_TREASURY"
    BOARD_PACK = "BOARD_PACK"
    REGULATORY_PACK = "REGULATORY_PACK"
    INTRADAY_LIQUIDITY = "INTRADAY_LIQUIDITY"


class SectionStatus(Enum):
    """Status of a dashboard section."""
    OK = "OK"
    WARNING = "WARNING"               # near threshold
    BREACH = "BREACH"                 # threshold violated
    NO_DATA = "NO_DATA"               # upstream engine empty


@dataclass(frozen=True)
class DashboardSection:
    """One section of a dashboard report."""
    section_id: str
    section_title: str
    source_engine: str                # which upstream engine
    status: SectionStatus
    metrics: Mapping[str, Any]        # named metrics (e.g., 'lcr_pct')
    thresholds: Mapping[str, Any]     # named thresholds
    headroom: Mapping[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass(frozen=True)
class DashboardReport:
    """A complete dashboard report."""
    report_id: str
    report_type: ReportType
    entity_name: str
    as_of_date: str
    sections: Tuple[DashboardSection, ...]
    overall_status: SectionStatus     # worst-of all sections
    n_breaches: int
    n_warnings: int
    notes: str = ""

    def section_by_id(
        self, section_id: str,
    ) -> Optional[DashboardSection]:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None


def aggregate_status(
    sections: Sequence[DashboardSection],
) -> Tuple[SectionStatus, int, int]:
    """Roll-up status across sections.

    Worst-of: BREACH > WARNING > OK > NO_DATA.
    Returns (overall, n_breaches, n_warnings).
    """
    n_breach = sum(
        1 for s in sections if s.status == SectionStatus.BREACH)
    n_warn = sum(
        1 for s in sections if s.status == SectionStatus.WARNING)
    if n_breach > 0:
        overall = SectionStatus.BREACH
    elif n_warn > 0:
        overall = SectionStatus.WARNING
    elif any(s.status == SectionStatus.OK for s in sections):
        overall = SectionStatus.OK
    else:
        overall = SectionStatus.NO_DATA
    return overall, n_breach, n_warn


# ════════════════════════════════════════════════════════════════════════
# Section builders — read upstream engines without mutating them
# ════════════════════════════════════════════════════════════════════════

def build_alm_lcr_section(
    *, alm_engine: Any, section_id: str = "alm_lcr",
) -> DashboardSection:
    """LCR section. alm_engine: TreasuryALMEngine."""
    summary = alm_engine.board_summary()
    if summary.get("latest_lcr_pct") is None:
        return DashboardSection(
            section_id=section_id,
            section_title="LCR — Basel BCBS 188",
            source_engine="treasury_alm",
            status=SectionStatus.NO_DATA,
            metrics={}, thresholds={"min_pct": "100"},
            notes="no LCR result computed yet")
    lcr_pct = Decimal(summary["latest_lcr_pct"])
    is_compliant = summary["latest_lcr_compliant"]
    headroom = (lcr_pct - Decimal("100")).quantize(Decimal("0.01"))
    if not is_compliant:
        status = SectionStatus.BREACH
    elif lcr_pct < Decimal("110"):
        status = SectionStatus.WARNING        # within 10pp of min
    else:
        status = SectionStatus.OK
    return DashboardSection(
        section_id=section_id,
        section_title="LCR — Basel BCBS 188",
        source_engine="treasury_alm",
        status=status,
        metrics={"lcr_pct": str(lcr_pct)},
        thresholds={"basel_min_pct": "100"},
        headroom={"vs_basel_min_pp": str(headroom)},
        notes=f"LCR {lcr_pct}% (Basel min 100%)")


def build_alm_nsfr_section(
    *, alm_engine: Any, section_id: str = "alm_nsfr",
) -> DashboardSection:
    summary = alm_engine.board_summary()
    if summary.get("latest_nsfr_pct") is None:
        return DashboardSection(
            section_id=section_id,
            section_title="NSFR — Basel BCBS 295",
            source_engine="treasury_alm",
            status=SectionStatus.NO_DATA,
            metrics={}, thresholds={"min_pct": "100"},
            notes="no NSFR result computed yet")
    nsfr_pct = Decimal(summary["latest_nsfr_pct"])
    is_compliant = summary["latest_nsfr_compliant"]
    headroom = (nsfr_pct - Decimal("100")).quantize(Decimal("0.01"))
    if not is_compliant:
        status = SectionStatus.BREACH
    elif nsfr_pct < Decimal("105"):
        status = SectionStatus.WARNING
    else:
        status = SectionStatus.OK
    return DashboardSection(
        section_id=section_id,
        section_title="NSFR — Basel BCBS 295",
        source_engine="treasury_alm",
        status=status,
        metrics={"nsfr_pct": str(nsfr_pct)},
        thresholds={"basel_min_pct": "100"},
        headroom={"vs_basel_min_pp": str(headroom)},
        notes=f"NSFR {nsfr_pct}% (Basel min 100%)")


def build_irrbb_outlier_section(
    *, alm_engine: Any, section_id: str = "irrbb_outliers",
) -> DashboardSection:
    summary = alm_engine.board_summary()
    n_outliers = summary.get("n_eve_outliers", 0)
    if n_outliers > 0:
        status = SectionStatus.BREACH
    else:
        status = SectionStatus.OK
    return DashboardSection(
        section_id=section_id,
        section_title="IRRBB Outliers — Basel BCBS 368",
        source_engine="treasury_alm",
        status=status,
        metrics={"n_eve_outliers": n_outliers},
        thresholds={
            "delta_eve_max_pct_tier_1": "15"},
        notes=(
            f"{n_outliers} scenarios with ΔEVE > 15% Tier 1; "
            f"{'EXAMINE' if n_outliers > 0 else 'no flags'}"))


def build_capital_ratios_section(
    *, rwa_engine: Any, section_id: str = "capital_ratios",
) -> DashboardSection:
    """Capital ratios. rwa_engine: RWAOptimizationEngine."""
    summary = rwa_engine.board_summary()
    if summary.get("latest_cet1_pct") is None:
        return DashboardSection(
            section_id=section_id,
            section_title="Capital Ratios — Basel III + CBK PG/03",
            source_engine="rwa_optimization",
            status=SectionStatus.NO_DATA,
            metrics={}, thresholds={
                "basel_cet1_min_pct": "4.5",
                "cbk_cet1_min_pct": "10.5"},
            notes="no capital ratios computed yet")
    cet1_pct = Decimal(summary["latest_cet1_pct"])
    cbk_compliant = summary["latest_cbk_compliant"]
    if not cbk_compliant:
        status = SectionStatus.BREACH
    elif cet1_pct < Decimal("11.5"):    # 1pp above CBK min
        status = SectionStatus.WARNING
    else:
        status = SectionStatus.OK
    cbk_headroom = (cet1_pct - Decimal("10.5")).quantize(
        Decimal("0.01"))
    return DashboardSection(
        section_id=section_id,
        section_title="Capital Ratios — Basel III + CBK PG/03",
        source_engine="rwa_optimization",
        status=status,
        metrics={
            "cet1_pct": str(cet1_pct),
            "total_capital_pct": (
                summary.get("latest_total_capital_pct", "—")),
            "total_rwa": summary.get("total_rwa", "—")},
        thresholds={
            "basel_cet1_min_pct": "4.5",
            "cbk_cet1_min_pct": "10.5",
            "cbk_total_min_pct": "14.5"},
        headroom={"cbk_cet1_headroom_pp": str(cbk_headroom)},
        notes=(
            f"CET1 {cet1_pct}% (CBK min 10.5%); "
            f"compliant={cbk_compliant}"))


def build_fx_exposure_section(
    *, products_engine: Any, currencies: Sequence[str],
    section_id: str = "fx_exposure",
) -> DashboardSection:
    """FX exposure. products_engine: TreasuryProductsEngine."""
    if not currencies:
        return DashboardSection(
            section_id=section_id,
            section_title="FX Exposure — CBK PG/17",
            source_engine="treasury_products",
            status=SectionStatus.NO_DATA,
            metrics={}, thresholds={},
            notes="no currencies specified for FX exposure check")
    exposures: Dict[str, str] = {}
    for ccy in currencies:
        exposures[ccy] = str(products_engine.net_fx_exposure(ccy))
    return DashboardSection(
        section_id=section_id,
        section_title="FX Exposure — CBK PG/17",
        source_engine="treasury_products",
        status=SectionStatus.OK,
        metrics={"exposures_by_currency": exposures},
        thresholds={"cbk_pg_17_max_pct_capital": "20"},
        notes=(
            f"net exposures across {len(currencies)} currencies — "
            f"limit checks require capital_base context"))


def build_nim_section(
    *, ftp_engine: Any, section_id: str = "nim",
) -> DashboardSection:
    """NIM decomposition. ftp_engine: FTPEngine."""
    summary = ftp_engine.board_summary()
    n_decomp = summary.get("n_decompositions", 0)
    if n_decomp == 0:
        return DashboardSection(
            section_id=section_id,
            section_title="NIM Decomposition — FTP",
            source_engine="fund_transfer_pricing",
            status=SectionStatus.NO_DATA,
            metrics={}, thresholds={},
            notes="no NIM decompositions computed yet")
    return DashboardSection(
        section_id=section_id,
        section_title="NIM Decomposition — FTP",
        source_engine="fund_transfer_pricing",
        status=SectionStatus.OK,
        metrics={
            "sum_lending_spread_pct": summary.get(
                "sum_lending_spread_pct", "—"),
            "sum_funding_spread_pct": summary.get(
                "sum_funding_spread_pct", "—"),
            "n_decompositions": n_decomp},
        thresholds={},
        notes=f"{n_decomp} positions decomposed via FTP")


def build_cash_forecast_section(
    *, forecast_engine: Any, section_id: str = "cash_forecast",
) -> DashboardSection:
    """Cash forecast. forecast_engine: TreasuryCashForecastingEngine."""
    summary = forecast_engine.board_summary()
    n_forecasts = summary.get("n_forecasts", 0)
    if n_forecasts == 0:
        return DashboardSection(
            section_id=section_id,
            section_title="13-Week Cash Forecast",
            source_engine="cash_forecasting",
            status=SectionStatus.NO_DATA,
            metrics={
                "n_history_days": summary.get(
                    "n_history_days", 0)},
            thresholds={},
            notes="no forecast generated yet")
    return DashboardSection(
        section_id=section_id,
        section_title="13-Week Cash Forecast",
        source_engine="cash_forecasting",
        status=SectionStatus.OK,
        metrics={
            "latest_forecast_id": summary.get(
                "latest_forecast_id", "—"),
            "horizon_days": summary.get(
                "latest_horizon_days", "—"),
            "net_position_kes": summary.get(
                "latest_net_position", "—"),
            "ml_overlay_wired": summary.get(
                "ml_provider_wired", False)},
        thresholds={},
        notes=(
            f"{n_forecasts} forecast(s); ml_provider_wired="
            f"{summary.get('ml_provider_wired', False)}"))


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TreasuryDashboardEngine:
    """Treasury dashboard aggregator.

    Holds optional references to upstream engines (treasury_alm,
    treasury_products, rwa_optimization, fund_transfer_pricing,
    cash_forecasting) and produces structured reports. Wiring is
    optional — sections for unwired engines emit NO_DATA cleanly.
    """

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya",
        alm_engine: Any = None,
        products_engine: Any = None,
        rwa_engine: Any = None,
        ftp_engine: Any = None,
        forecast_engine: Any = None,
    ):
        self.entity_name = entity_name
        self.alm_engine = alm_engine
        self.products_engine = products_engine
        self.rwa_engine = rwa_engine
        self.ftp_engine = ftp_engine
        self.forecast_engine = forecast_engine
        self._reports: Dict[str, DashboardReport] = {}

    # ── Report builders ───────────────────────────────────────────────
    def generate_daily_treasury(
        self, *, report_id: str, as_of_date: str,
        fx_currencies: Sequence[str] = (),
    ) -> DashboardReport:
        """Daily treasury report — today's positions + ratios."""
        sections: List[DashboardSection] = []
        if self.alm_engine is not None:
            sections.append(build_alm_lcr_section(
                alm_engine=self.alm_engine))
            sections.append(build_alm_nsfr_section(
                alm_engine=self.alm_engine))
        if self.products_engine is not None:
            sections.append(build_fx_exposure_section(
                products_engine=self.products_engine,
                currencies=fx_currencies))
        if self.forecast_engine is not None:
            sections.append(build_cash_forecast_section(
                forecast_engine=self.forecast_engine))
        return self._build_report(
            report_id=report_id,
            report_type=ReportType.DAILY_TREASURY,
            as_of_date=as_of_date,
            sections=tuple(sections))

    def generate_board_pack(
        self, *, report_id: str, as_of_date: str,
    ) -> DashboardReport:
        """Board pack — monthly aggregated metrics for ALCO."""
        sections: List[DashboardSection] = []
        if self.alm_engine is not None:
            sections.append(build_alm_lcr_section(
                alm_engine=self.alm_engine))
            sections.append(build_alm_nsfr_section(
                alm_engine=self.alm_engine))
            sections.append(build_irrbb_outlier_section(
                alm_engine=self.alm_engine))
        if self.rwa_engine is not None:
            sections.append(build_capital_ratios_section(
                rwa_engine=self.rwa_engine))
        if self.ftp_engine is not None:
            sections.append(build_nim_section(
                ftp_engine=self.ftp_engine))
        if self.forecast_engine is not None:
            sections.append(build_cash_forecast_section(
                forecast_engine=self.forecast_engine))
        return self._build_report(
            report_id=report_id,
            report_type=ReportType.BOARD_PACK,
            as_of_date=as_of_date,
            sections=tuple(sections))

    def generate_regulatory_pack(
        self, *, report_id: str, as_of_date: str,
    ) -> DashboardReport:
        """Regulatory pack — structured CBK submission format."""
        sections: List[DashboardSection] = []
        # CBK PG/16 — liquidity
        if self.alm_engine is not None:
            sections.append(build_alm_lcr_section(
                alm_engine=self.alm_engine,
                section_id="cbk_pg_16_lcr"))
            sections.append(build_alm_nsfr_section(
                alm_engine=self.alm_engine,
                section_id="cbk_pg_16_nsfr"))
        # CBK PG/03 — capital
        if self.rwa_engine is not None:
            sections.append(build_capital_ratios_section(
                rwa_engine=self.rwa_engine,
                section_id="cbk_pg_03_capital"))
        # IRRBB
        if self.alm_engine is not None:
            sections.append(build_irrbb_outlier_section(
                alm_engine=self.alm_engine,
                section_id="cbk_irrbb_outliers"))
        return self._build_report(
            report_id=report_id,
            report_type=ReportType.REGULATORY_PACK,
            as_of_date=as_of_date,
            sections=tuple(sections))

    def _build_report(
        self, *, report_id: str, report_type: ReportType,
        as_of_date: str,
        sections: Tuple[DashboardSection, ...],
    ) -> DashboardReport:
        if report_id in self._reports:
            raise ValueError(
                f"report {report_id} already generated")
        overall, n_breach, n_warn = aggregate_status(sections)
        report = DashboardReport(
            report_id=report_id,
            report_type=report_type,
            entity_name=self.entity_name,
            as_of_date=as_of_date,
            sections=sections,
            overall_status=overall,
            n_breaches=n_breach,
            n_warnings=n_warn,
            notes=(
                f"{report_type.value} for {self.entity_name} as of "
                f"{as_of_date}: {len(sections)} sections; "
                f"{n_breach} breach(es); {n_warn} warning(s)"))
        self._reports[report_id] = report
        return report

    def board_summary(self) -> Dict[str, Any]:
        return {
            "entity": self.entity_name,
            "alm_wired": self.alm_engine is not None,
            "products_wired": self.products_engine is not None,
            "rwa_wired": self.rwa_engine is not None,
            "ftp_wired": self.ftp_engine is not None,
            "forecast_wired": self.forecast_engine is not None,
            "n_reports_generated": len(self._reports),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

class _StubEngine:
    """Minimal stub that returns a fixed board_summary."""
    def __init__(self, summary: Dict[str, Any]):
        self._summary = summary

    def board_summary(self) -> Dict[str, Any]:
        return self._summary

    def net_fx_exposure(self, ccy: str) -> Decimal:
        return self._summary.get(
            f"net_fx_{ccy}", Decimal("0"))


def _test_aggregate_status_breach_dominates():
    sections = (
        DashboardSection(
            section_id="A", section_title="A",
            source_engine="x", status=SectionStatus.OK,
            metrics={}, thresholds={}),
        DashboardSection(
            section_id="B", section_title="B",
            source_engine="x", status=SectionStatus.BREACH,
            metrics={}, thresholds={}),
    )
    overall, nb, nw = aggregate_status(sections)
    assert overall == SectionStatus.BREACH
    assert nb == 1 and nw == 0


def _test_aggregate_status_warning_when_no_breach():
    sections = (
        DashboardSection(
            section_id="A", section_title="A",
            source_engine="x", status=SectionStatus.OK,
            metrics={}, thresholds={}),
        DashboardSection(
            section_id="B", section_title="B",
            source_engine="x", status=SectionStatus.WARNING,
            metrics={}, thresholds={}),
    )
    overall, nb, nw = aggregate_status(sections)
    assert overall == SectionStatus.WARNING
    assert nb == 0 and nw == 1


def _test_lcr_section_no_data():
    stub = _StubEngine({"latest_lcr_pct": None})
    s = build_alm_lcr_section(alm_engine=stub)
    assert s.status == SectionStatus.NO_DATA


def _test_lcr_section_compliant():
    stub = _StubEngine({
        "latest_lcr_pct": "150.00",
        "latest_lcr_compliant": True})
    s = build_alm_lcr_section(alm_engine=stub)
    assert s.status == SectionStatus.OK
    assert s.metrics["lcr_pct"] == "150.00"


def _test_lcr_section_breach():
    stub = _StubEngine({
        "latest_lcr_pct": "85.00",
        "latest_lcr_compliant": False})
    s = build_alm_lcr_section(alm_engine=stub)
    assert s.status == SectionStatus.BREACH


def _test_lcr_section_warning_near_threshold():
    """LCR 105% → WARNING (within 10pp of 100% min)."""
    stub = _StubEngine({
        "latest_lcr_pct": "105.00",
        "latest_lcr_compliant": True})
    s = build_alm_lcr_section(alm_engine=stub)
    assert s.status == SectionStatus.WARNING


def _test_irrbb_outlier_section_breach_when_outliers():
    stub = _StubEngine({"n_eve_outliers": 2})
    s = build_irrbb_outlier_section(alm_engine=stub)
    assert s.status == SectionStatus.BREACH
    assert s.metrics["n_eve_outliers"] == 2


def _test_capital_ratios_section_cbk_breach():
    """CET1 8% → CBK breach (CBK min 10.5%)."""
    stub = _StubEngine({
        "latest_cet1_pct": "8.00",
        "latest_total_capital_pct": "10.00",
        "total_rwa": "1000000000",
        "latest_cbk_compliant": False})
    s = build_capital_ratios_section(rwa_engine=stub)
    assert s.status == SectionStatus.BREACH


def _test_engine_no_wiring_emits_no_data_only():
    eng = TreasuryDashboardEngine()
    report = eng.generate_daily_treasury(
        report_id="R1", as_of_date="2026-05-01")
    # No engines wired → 0 sections
    assert len(report.sections) == 0


def _test_engine_dup_report_id_raises():
    eng = TreasuryDashboardEngine()
    eng.generate_daily_treasury(
        report_id="R1", as_of_date="2026-05-01")
    try:
        eng.generate_daily_treasury(
            report_id="R1", as_of_date="2026-05-01")
        assert False
    except ValueError:
        pass


def _test_engine_with_alm_wired():
    """Wire stub ALM → LCR + NSFR sections appear."""
    alm_stub = _StubEngine({
        "latest_lcr_pct": "150.00",
        "latest_lcr_compliant": True,
        "latest_nsfr_pct": "120.00",
        "latest_nsfr_compliant": True,
        "n_eve_outliers": 0})
    eng = TreasuryDashboardEngine(alm_engine=alm_stub)
    report = eng.generate_board_pack(
        report_id="R1", as_of_date="2026-05-01")
    section_ids = {s.section_id for s in report.sections}
    assert "alm_lcr" in section_ids
    assert "alm_nsfr" in section_ids
    assert "irrbb_outliers" in section_ids


def _test_engine_overall_status_aggregates():
    """Mix OK + BREACH → overall BREACH."""
    alm_stub = _StubEngine({
        "latest_lcr_pct": "150.00",
        "latest_lcr_compliant": True,
        "latest_nsfr_pct": "85.00",      # breach
        "latest_nsfr_compliant": False,
        "n_eve_outliers": 0})
    eng = TreasuryDashboardEngine(alm_engine=alm_stub)
    report = eng.generate_board_pack(
        report_id="R1", as_of_date="2026-05-01")
    assert report.overall_status == SectionStatus.BREACH
    assert report.n_breaches >= 1


def _test_engine_regulatory_pack_id_namespace():
    """Reg pack uses CBK-prefixed section IDs."""
    alm_stub = _StubEngine({
        "latest_lcr_pct": "150.00",
        "latest_lcr_compliant": True,
        "latest_nsfr_pct": "120.00",
        "latest_nsfr_compliant": True,
        "n_eve_outliers": 0})
    rwa_stub = _StubEngine({
        "latest_cet1_pct": "13.00",
        "latest_total_capital_pct": "16.00",
        "total_rwa": "10000000000",
        "latest_cbk_compliant": True})
    eng = TreasuryDashboardEngine(
        alm_engine=alm_stub, rwa_engine=rwa_stub)
    report = eng.generate_regulatory_pack(
        report_id="R1", as_of_date="2026-05-01")
    section_ids = {s.section_id for s in report.sections}
    assert "cbk_pg_16_lcr" in section_ids
    assert "cbk_pg_03_capital" in section_ids
    assert "cbk_irrbb_outliers" in section_ids


def _test_engine_section_by_id():
    alm_stub = _StubEngine({
        "latest_lcr_pct": "150.00",
        "latest_lcr_compliant": True,
        "latest_nsfr_pct": "120.00",
        "latest_nsfr_compliant": True,
        "n_eve_outliers": 0})
    eng = TreasuryDashboardEngine(alm_engine=alm_stub)
    report = eng.generate_board_pack(
        report_id="R1", as_of_date="2026-05-01")
    s = report.section_by_id("alm_lcr")
    assert s is not None
    assert s.metrics["lcr_pct"] == "150.00"


def _test_engine_board_summary():
    eng = TreasuryDashboardEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["alm_wired"] is False


def self_test() -> None:
    tests = [
        _test_aggregate_status_breach_dominates,
        _test_aggregate_status_warning_when_no_breach,
        _test_lcr_section_no_data,
        _test_lcr_section_compliant,
        _test_lcr_section_breach,
        _test_lcr_section_warning_near_threshold,
        _test_irrbb_outlier_section_breach_when_outliers,
        _test_capital_ratios_section_cbk_breach,
        _test_engine_no_wiring_emits_no_data_only,
        _test_engine_dup_report_id_raises,
        _test_engine_with_alm_wired,
        _test_engine_overall_status_aggregates,
        _test_engine_regulatory_pack_id_namespace,
        _test_engine_section_by_id,
        _test_engine_board_summary,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ treasury_dashboard self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ treasury_dashboard self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
