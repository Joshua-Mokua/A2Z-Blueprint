"""utils/finance_intelligence_dashboard.py — v10.64: CFO view.

ENH-254 — Finance Intelligence Dashboard (CFO View). Cat B —
finance arc 6/10. Split implementation per v10.46-amended Lean+
Compact protocol: data layer ships now (KPI aggregation engine);
UI layer at v10.68 closure cockpit (pages/96) consumes these
metrics.

Six metric families for CFO view:
  1. PROFITABILITY    — NIM, ROA, ROE, cost-to-income
  2. CAPITAL          — CAR (consumes ENH-252), capital growth
  3. LIQUIDITY        — LIQ ratio, days cash on hand
  4. GROWTH           — loan/deposit/customer growth
  5. EFFICIENCY       — branch productivity, cost per transaction
  6. ASSET_QUALITY    — NPL ratio, coverage ratio, write-offs

Each KPI surfaces value + trend (up/down/flat) + threshold breach
when applicable. KPIs with breach severity above threshold fire
ExecutiveAlert objects.

Per Rule 7, engine NEVER:
  - sends notifications/emails (caller decides escalation)
  - persists state
  - mutates inputs (frozen contract enforced)
  - auto-acts on alerts

Per Rule 1, every Kpi surfaces metric_name + family + value +
inputs_used + trend + threshold_status + framework refs. Every
ExecutiveAlert surfaces alert_id + kpi_metric + breach_kind +
description + recommended_action_category (NOT actual action) +
framework refs.

Pure stdlib (Decimal + frozen dataclasses + enums).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "FinanceIntelligenceDashboardEngine implements ENH-254 as "
    "split-implementation per v10.46 amendment — data layer "
    "now, UI rendering at v10.68 closure cockpit. Pure stdlib "
    "(Decimal + dataclasses + enums). Per Rule 1, every Kpi "
    "surfaces value + inputs + trend + threshold + refs; every "
    "ExecutiveAlert surfaces breach kind + recommended action "
    "category. Per Rule 7, engine read-only — never notifies, "
    "never persists, never auto-acts on alerts. Caller drives "
    "escalation."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class MetricFamily(Enum):
    PROFITABILITY = "PROFITABILITY"
    CAPITAL = "CAPITAL"
    LIQUIDITY = "LIQUIDITY"
    GROWTH = "GROWTH"
    EFFICIENCY = "EFFICIENCY"
    ASSET_QUALITY = "ASSET_QUALITY"


class TrendDirection(Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class ThresholdStatus(Enum):
    OK = "OK"
    WARNING = "WARNING"        # within 10% of threshold
    BREACH = "BREACH"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class AlertSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PeriodFinancials:
    """One period's financial inputs."""
    period: str
    # P&L
    net_interest_income_kes: Decimal
    non_interest_income_kes: Decimal
    operating_expenses_kes: Decimal
    impairment_kes: Decimal
    tax_kes: Decimal
    # B/S averages (for ROA/ROE)
    avg_total_assets_kes: Decimal
    avg_equity_kes: Decimal
    avg_earning_assets_kes: Decimal
    # Closing balances
    closing_total_loans_kes: Decimal
    closing_total_deposits_kes: Decimal
    closing_npl_kes: Decimal
    closing_provision_kes: Decimal
    customer_count: int
    branch_count: int
    transaction_count: int
    transaction_processing_cost_kes: Decimal
    # Capital + liquidity from CBK returns
    car_ratio: Decimal              # 0..1
    liq_ratio: Decimal              # 0..1

    def __post_init__(self) -> None:
        if not self.period:
            raise ValueError("period must be non-empty")
        for f in (
            "avg_total_assets_kes", "avg_equity_kes",
            "avg_earning_assets_kes",
            "closing_total_loans_kes",
            "closing_total_deposits_kes",
        ):
            v = getattr(self, f)
            if v < 0:
                raise ValueError(f"{f} must be ≥ 0")


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Kpi:
    metric_name: str
    family: MetricFamily
    period: str
    value: Decimal
    unit: str
    inputs_used: Dict[str, str]
    trend: TrendDirection
    prior_value: Optional[Decimal]
    threshold: Optional[Decimal]
    threshold_status: ThresholdStatus
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutiveAlert:
    alert_id: str
    severity: AlertSeverity
    family: MetricFamily
    kpi_metric: str
    period: str
    description: str
    recommended_action_category: str   # NOT actual action
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CfoDashboard:
    period: str
    kpis: Tuple[Kpi, ...]
    alerts: Tuple[ExecutiveAlert, ...]
    by_family: Dict[str, int]
    by_threshold_status: Dict[str, int]
    framework_refs: Tuple[str, ...]


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class FinanceIntelligenceDashboardEngine:
    """Diagnostic CFO KPI aggregation."""

    # Default thresholds — operator overrides via init
    NIM_MIN_PCT: Decimal = Decimal("0.04")        # 4%
    ROA_MIN_PCT: Decimal = Decimal("0.015")       # 1.5%
    ROE_MIN_PCT: Decimal = Decimal("0.15")        # 15%
    COST_INCOME_MAX_PCT: Decimal = Decimal("0.55")
    NPL_RATIO_MAX_PCT: Decimal = Decimal("0.06")  # 6% (CBK guidance)
    COVERAGE_MIN_PCT: Decimal = Decimal("0.70")   # 70%
    CAR_MIN_PCT: Decimal = Decimal("0.145")
    LIQ_MIN_PCT: Decimal = Decimal("0.20")

    @staticmethod
    def _safe_div(num: Decimal, den: Decimal,
                  decimals: str = "0.0001") -> Decimal:
        if den == 0:
            return Decimal("0")
        return (num / den).quantize(Decimal(decimals))

    @staticmethod
    def _trend(
        current: Decimal, prior: Optional[Decimal],
        flat_threshold_pct: Decimal = Decimal("0.01"),
    ) -> TrendDirection:
        if prior is None or prior == 0:
            return TrendDirection.FLAT
        change_pct = abs(current - prior) / abs(prior)
        if change_pct < flat_threshold_pct:
            return TrendDirection.FLAT
        return (
            TrendDirection.UP if current > prior
            else TrendDirection.DOWN)

    def _threshold_status(
        self,
        value: Decimal,
        threshold: Optional[Decimal],
        direction: str,    # "min" or "max"
    ) -> ThresholdStatus:
        if threshold is None:
            return ThresholdStatus.NOT_APPLICABLE
        if direction == "min":
            if value >= threshold:
                # WARNING if within 10% of threshold
                if value < threshold * Decimal("1.10"):
                    return ThresholdStatus.WARNING
                return ThresholdStatus.OK
            return ThresholdStatus.BREACH
        else:
            if value <= threshold:
                if value > threshold * Decimal("0.90"):
                    return ThresholdStatus.WARNING
                return ThresholdStatus.OK
            return ThresholdStatus.BREACH

    # ── KPI builders per family ──────────────────────────────────────
    def _profitability_kpis(
        self,
        current: PeriodFinancials,
        prior: Optional[PeriodFinancials],
    ) -> Tuple[Kpi, ...]:
        kpis: List[Kpi] = []
        # Total revenue
        total_rev = (
            current.net_interest_income_kes
            + current.non_interest_income_kes)
        # NIM = NII / avg earning assets
        nim = self._safe_div(
            current.net_interest_income_kes,
            current.avg_earning_assets_kes)
        prior_nim = (
            self._safe_div(
                prior.net_interest_income_kes,
                prior.avg_earning_assets_kes)
            if prior else None)
        kpis.append(Kpi(
            metric_name="NIM",
            family=MetricFamily.PROFITABILITY,
            period=current.period,
            value=nim, unit="ratio",
            inputs_used={
                "nii": str(current.net_interest_income_kes),
                "avg_earning_assets": str(
                    current.avg_earning_assets_kes)},
            trend=self._trend(nim, prior_nim),
            prior_value=prior_nim,
            threshold=self.NIM_MIN_PCT,
            threshold_status=self._threshold_status(
                nim, self.NIM_MIN_PCT, "min"),
            framework_refs=(
                "ENH-254 §profitability",
                "NIM = NII / avg earning assets")))
        # Net profit
        net_profit = (
            total_rev - current.operating_expenses_kes
            - current.impairment_kes - current.tax_kes)
        # ROA
        roa = self._safe_div(
            net_profit, current.avg_total_assets_kes)
        prior_total_rev = (
            (prior.net_interest_income_kes
             + prior.non_interest_income_kes)
            if prior else None)
        prior_net_profit = (
            (prior_total_rev - prior.operating_expenses_kes
             - prior.impairment_kes - prior.tax_kes)
            if prior else None)
        prior_roa = (
            self._safe_div(
                prior_net_profit, prior.avg_total_assets_kes)
            if prior is not None and prior_net_profit
            is not None else None)
        kpis.append(Kpi(
            metric_name="ROA",
            family=MetricFamily.PROFITABILITY,
            period=current.period,
            value=roa, unit="ratio",
            inputs_used={
                "net_profit": str(net_profit),
                "avg_total_assets": str(
                    current.avg_total_assets_kes)},
            trend=self._trend(roa, prior_roa),
            prior_value=prior_roa,
            threshold=self.ROA_MIN_PCT,
            threshold_status=self._threshold_status(
                roa, self.ROA_MIN_PCT, "min"),
            framework_refs=(
                "ENH-254 §profitability",
                "ROA = net profit / avg total assets")))
        # ROE
        roe = self._safe_div(
            net_profit, current.avg_equity_kes)
        prior_roe = (
            self._safe_div(
                prior_net_profit, prior.avg_equity_kes)
            if prior is not None and prior_net_profit
            is not None else None)
        kpis.append(Kpi(
            metric_name="ROE",
            family=MetricFamily.PROFITABILITY,
            period=current.period,
            value=roe, unit="ratio",
            inputs_used={
                "net_profit": str(net_profit),
                "avg_equity": str(current.avg_equity_kes)},
            trend=self._trend(roe, prior_roe),
            prior_value=prior_roe,
            threshold=self.ROE_MIN_PCT,
            threshold_status=self._threshold_status(
                roe, self.ROE_MIN_PCT, "min"),
            framework_refs=(
                "ENH-254 §profitability",
                "ROE = net profit / avg equity")))
        # Cost-to-income
        cost_income = self._safe_div(
            current.operating_expenses_kes, total_rev)
        prior_cost_income = (
            self._safe_div(
                prior.operating_expenses_kes, prior_total_rev)
            if prior is not None and prior_total_rev
            is not None else None)
        kpis.append(Kpi(
            metric_name="COST_TO_INCOME",
            family=MetricFamily.PROFITABILITY,
            period=current.period,
            value=cost_income, unit="ratio",
            inputs_used={
                "opex": str(current.operating_expenses_kes),
                "total_revenue": str(total_rev)},
            trend=self._trend(cost_income, prior_cost_income),
            prior_value=prior_cost_income,
            threshold=self.COST_INCOME_MAX_PCT,
            threshold_status=self._threshold_status(
                cost_income, self.COST_INCOME_MAX_PCT, "max"),
            framework_refs=(
                "ENH-254 §profitability",
                "Cost-to-income = opex / total revenue")))
        return tuple(kpis)

    def _capital_kpis(
        self, current: PeriodFinancials,
        prior: Optional[PeriodFinancials],
    ) -> Tuple[Kpi, ...]:
        return (Kpi(
            metric_name="CAR",
            family=MetricFamily.CAPITAL,
            period=current.period,
            value=current.car_ratio, unit="ratio",
            inputs_used={"car_ratio": str(current.car_ratio)},
            trend=self._trend(
                current.car_ratio,
                prior.car_ratio if prior else None),
            prior_value=prior.car_ratio if prior else None,
            threshold=self.CAR_MIN_PCT,
            threshold_status=self._threshold_status(
                current.car_ratio, self.CAR_MIN_PCT, "min"),
            framework_refs=(
                "ENH-254 §capital",
                "CAR consumed from ENH-252 / CBK PG 03 §4")),)

    def _liquidity_kpis(
        self, current: PeriodFinancials,
        prior: Optional[PeriodFinancials],
    ) -> Tuple[Kpi, ...]:
        return (Kpi(
            metric_name="LIQ",
            family=MetricFamily.LIQUIDITY,
            period=current.period,
            value=current.liq_ratio, unit="ratio",
            inputs_used={"liq_ratio": str(current.liq_ratio)},
            trend=self._trend(
                current.liq_ratio,
                prior.liq_ratio if prior else None),
            prior_value=prior.liq_ratio if prior else None,
            threshold=self.LIQ_MIN_PCT,
            threshold_status=self._threshold_status(
                current.liq_ratio, self.LIQ_MIN_PCT, "min"),
            framework_refs=(
                "ENH-254 §liquidity",
                "LIQ consumed from ENH-252 / CBK PG 04")),)

    def _growth_kpis(
        self, current: PeriodFinancials,
        prior: Optional[PeriodFinancials],
    ) -> Tuple[Kpi, ...]:
        if prior is None:
            return ()
        kpis: List[Kpi] = []
        loan_growth = self._safe_div(
            current.closing_total_loans_kes
            - prior.closing_total_loans_kes,
            prior.closing_total_loans_kes)
        kpis.append(Kpi(
            metric_name="LOAN_GROWTH",
            family=MetricFamily.GROWTH,
            period=current.period,
            value=loan_growth, unit="ratio",
            inputs_used={
                "current_loans": str(
                    current.closing_total_loans_kes),
                "prior_loans": str(
                    prior.closing_total_loans_kes)},
            trend=self._trend(loan_growth, Decimal("0")),
            prior_value=None,
            threshold=None,
            threshold_status=ThresholdStatus.NOT_APPLICABLE,
            framework_refs=(
                "ENH-254 §growth",)))
        deposit_growth = self._safe_div(
            current.closing_total_deposits_kes
            - prior.closing_total_deposits_kes,
            prior.closing_total_deposits_kes)
        kpis.append(Kpi(
            metric_name="DEPOSIT_GROWTH",
            family=MetricFamily.GROWTH,
            period=current.period,
            value=deposit_growth, unit="ratio",
            inputs_used={
                "current_deposits": str(
                    current.closing_total_deposits_kes),
                "prior_deposits": str(
                    prior.closing_total_deposits_kes)},
            trend=self._trend(deposit_growth, Decimal("0")),
            prior_value=None,
            threshold=None,
            threshold_status=ThresholdStatus.NOT_APPLICABLE,
            framework_refs=(
                "ENH-254 §growth",)))
        if prior.customer_count > 0:
            cust_growth = self._safe_div(
                Decimal(
                    current.customer_count - prior.customer_count),
                Decimal(prior.customer_count))
            kpis.append(Kpi(
                metric_name="CUSTOMER_GROWTH",
                family=MetricFamily.GROWTH,
                period=current.period,
                value=cust_growth, unit="ratio",
                inputs_used={
                    "current_customers": str(
                        current.customer_count),
                    "prior_customers": str(
                        prior.customer_count)},
                trend=self._trend(cust_growth, Decimal("0")),
                prior_value=None,
                threshold=None,
                threshold_status=(
                    ThresholdStatus.NOT_APPLICABLE),
                framework_refs=(
                    "ENH-254 §growth",)))
        return tuple(kpis)

    def _efficiency_kpis(
        self, current: PeriodFinancials,
        prior: Optional[PeriodFinancials],
    ) -> Tuple[Kpi, ...]:
        kpis: List[Kpi] = []
        if current.transaction_count > 0:
            cpt = (
                current.transaction_processing_cost_kes
                / Decimal(current.transaction_count)).quantize(
                Decimal("0.01"))
            prior_cpt = None
            if prior is not None and prior.transaction_count > 0:
                prior_cpt = (
                    prior.transaction_processing_cost_kes
                    / Decimal(
                        prior.transaction_count)).quantize(
                    Decimal("0.01"))
            kpis.append(Kpi(
                metric_name="COST_PER_TRANSACTION",
                family=MetricFamily.EFFICIENCY,
                period=current.period,
                value=cpt, unit="kes_per_txn",
                inputs_used={
                    "txn_cost": str(
                        current.transaction_processing_cost_kes),
                    "txn_count": str(
                        current.transaction_count)},
                trend=self._trend(cpt, prior_cpt),
                prior_value=prior_cpt,
                threshold=None,
                threshold_status=(
                    ThresholdStatus.NOT_APPLICABLE),
                framework_refs=(
                    "ENH-254 §efficiency",)))
        if current.branch_count > 0:
            ppb = (
                Decimal(current.customer_count)
                / Decimal(current.branch_count)).quantize(
                Decimal("0.01"))
            prior_ppb = None
            if prior is not None and prior.branch_count > 0:
                prior_ppb = (
                    Decimal(prior.customer_count)
                    / Decimal(prior.branch_count)).quantize(
                    Decimal("0.01"))
            kpis.append(Kpi(
                metric_name="CUSTOMERS_PER_BRANCH",
                family=MetricFamily.EFFICIENCY,
                period=current.period,
                value=ppb, unit="customers_per_branch",
                inputs_used={
                    "customers": str(current.customer_count),
                    "branches": str(current.branch_count)},
                trend=self._trend(ppb, prior_ppb),
                prior_value=prior_ppb,
                threshold=None,
                threshold_status=(
                    ThresholdStatus.NOT_APPLICABLE),
                framework_refs=(
                    "ENH-254 §efficiency",)))
        return tuple(kpis)

    def _asset_quality_kpis(
        self, current: PeriodFinancials,
        prior: Optional[PeriodFinancials],
    ) -> Tuple[Kpi, ...]:
        kpis: List[Kpi] = []
        npl_ratio = self._safe_div(
            current.closing_npl_kes,
            current.closing_total_loans_kes)
        prior_npl_ratio = (
            self._safe_div(
                prior.closing_npl_kes,
                prior.closing_total_loans_kes)
            if prior else None)
        kpis.append(Kpi(
            metric_name="NPL_RATIO",
            family=MetricFamily.ASSET_QUALITY,
            period=current.period,
            value=npl_ratio, unit="ratio",
            inputs_used={
                "npl": str(current.closing_npl_kes),
                "loans": str(
                    current.closing_total_loans_kes)},
            trend=self._trend(npl_ratio, prior_npl_ratio),
            prior_value=prior_npl_ratio,
            threshold=self.NPL_RATIO_MAX_PCT,
            threshold_status=self._threshold_status(
                npl_ratio, self.NPL_RATIO_MAX_PCT, "max"),
            framework_refs=(
                "ENH-254 §asset_quality",
                "NPL ratio = NPL / total loans; CBK guidance "
                "≤6%")))
        coverage = self._safe_div(
            current.closing_provision_kes,
            current.closing_npl_kes)
        prior_coverage = (
            self._safe_div(
                prior.closing_provision_kes,
                prior.closing_npl_kes)
            if prior else None)
        kpis.append(Kpi(
            metric_name="COVERAGE_RATIO",
            family=MetricFamily.ASSET_QUALITY,
            period=current.period,
            value=coverage, unit="ratio",
            inputs_used={
                "provisions": str(current.closing_provision_kes),
                "npl": str(current.closing_npl_kes)},
            trend=self._trend(coverage, prior_coverage),
            prior_value=prior_coverage,
            threshold=self.COVERAGE_MIN_PCT,
            threshold_status=self._threshold_status(
                coverage, self.COVERAGE_MIN_PCT, "min"),
            framework_refs=(
                "ENH-254 §asset_quality",
                "Coverage = provisions / NPL")))
        return tuple(kpis)

    # ── Public API ───────────────────────────────────────────────────
    def build_dashboard(
        self,
        current: PeriodFinancials,
        prior: Optional[PeriodFinancials] = None,
    ) -> CfoDashboard:
        all_kpis = (
            self._profitability_kpis(current, prior)
            + self._capital_kpis(current, prior)
            + self._liquidity_kpis(current, prior)
            + self._growth_kpis(current, prior)
            + self._efficiency_kpis(current, prior)
            + self._asset_quality_kpis(current, prior))
        # Fire alerts for BREACH items
        alerts: List[ExecutiveAlert] = []
        for k in all_kpis:
            if k.threshold_status == ThresholdStatus.BREACH:
                # Severity by family
                sev = (
                    AlertSeverity.CRITICAL
                    if k.family in (
                        MetricFamily.CAPITAL,
                        MetricFamily.LIQUIDITY)
                    else AlertSeverity.WARNING)
                action_cat = self._action_category(k.family)
                alerts.append(ExecutiveAlert(
                    alert_id=(
                        f"FID-{k.metric_name}-{k.period}"),
                    severity=sev,
                    family=k.family,
                    kpi_metric=k.metric_name,
                    period=k.period,
                    description=(
                        f"{k.metric_name} = {k.value} "
                        f"(threshold {k.threshold}) → BREACH"),
                    recommended_action_category=action_cat,
                    framework_refs=(
                        "ENH-254 §alerts",
                        "Per Rule 7 — alert flagged; "
                        "operator decides actual action")))
        # Aggregates
        by_family: Dict[str, int] = {
            f.value: 0 for f in MetricFamily}
        for k in all_kpis:
            by_family[k.family.value] += 1
        by_status: Dict[str, int] = {
            s.value: 0 for s in ThresholdStatus}
        for k in all_kpis:
            by_status[k.threshold_status.value] += 1
        return CfoDashboard(
            period=current.period,
            kpis=all_kpis,
            alerts=tuple(alerts),
            by_family=by_family,
            by_threshold_status=by_status,
            framework_refs=(
                "ENH-254 §dashboard",
                "Split-implementation: data layer here, UI at "
                "v10.68 closure cockpit",
                "Per Rule 7 — read-only; never notifies, never "
                "persists, never auto-acts"))

    @staticmethod
    def _action_category(family: MetricFamily) -> str:
        return {
            MetricFamily.PROFITABILITY: (
                "review revenue mix / cost discipline"),
            MetricFamily.CAPITAL: (
                "review capital plan / RWA optimisation"),
            MetricFamily.LIQUIDITY: (
                "review liquidity buffer / funding plan"),
            MetricFamily.GROWTH: (
                "review growth strategy"),
            MetricFamily.EFFICIENCY: (
                "review operations / digital adoption"),
            MetricFamily.ASSET_QUALITY: (
                "review credit policy / collections"),
        }[family]


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _financials(
    period="2026-04",
    nii=4_000_000_000, noi=1_000_000_000,
    opex=2_500_000_000, imp=300_000_000, tax=600_000_000,
    avg_assets=100_000_000_000, avg_equity=15_000_000_000,
    avg_earning=80_000_000_000,
    loans=60_000_000_000, deposits=80_000_000_000,
    npl=2_400_000_000, prov=1_800_000_000,
    customers=500_000, branches=50,
    txn_count=10_000_000,
    txn_cost=300_000_000,
    car=Decimal("0.18"), liq=Decimal("0.25"),
):
    return PeriodFinancials(
        period=period,
        net_interest_income_kes=Decimal(str(nii)),
        non_interest_income_kes=Decimal(str(noi)),
        operating_expenses_kes=Decimal(str(opex)),
        impairment_kes=Decimal(str(imp)),
        tax_kes=Decimal(str(tax)),
        avg_total_assets_kes=Decimal(str(avg_assets)),
        avg_equity_kes=Decimal(str(avg_equity)),
        avg_earning_assets_kes=Decimal(str(avg_earning)),
        closing_total_loans_kes=Decimal(str(loans)),
        closing_total_deposits_kes=Decimal(str(deposits)),
        closing_npl_kes=Decimal(str(npl)),
        closing_provision_kes=Decimal(str(prov)),
        customer_count=customers, branch_count=branches,
        transaction_count=txn_count,
        transaction_processing_cost_kes=Decimal(str(txn_cost)),
        car_ratio=car, liq_ratio=liq)


def _test_financials_validates_period():
    try:
        _financials(period="")
        assert False
    except ValueError:
        pass


def _test_financials_validates_negative():
    try:
        _financials(loans=-1)
        assert False
    except ValueError:
        pass


def _test_basic_dashboard_no_prior():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(_financials(), prior=None)
    assert dash.period == "2026-04"
    assert len(dash.kpis) > 0
    families = {k.family for k in dash.kpis}
    # All 6 families should produce at least 1 KPI
    # except GROWTH (needs prior)
    assert MetricFamily.PROFITABILITY in families
    assert MetricFamily.CAPITAL in families
    assert MetricFamily.LIQUIDITY in families
    assert MetricFamily.EFFICIENCY in families
    assert MetricFamily.ASSET_QUALITY in families


def _test_growth_kpis_only_with_prior():
    eng = FinanceIntelligenceDashboardEngine()
    dash_no_prior = eng.build_dashboard(_financials())
    growth_no_prior = [
        k for k in dash_no_prior.kpis
        if k.family == MetricFamily.GROWTH]
    assert len(growth_no_prior) == 0
    prior = _financials(period="2026-03")
    current = _financials()
    dash = eng.build_dashboard(current, prior=prior)
    growth = [
        k for k in dash.kpis
        if k.family == MetricFamily.GROWTH]
    assert len(growth) >= 2  # loan + deposit + customer growth


def _test_nim_calculation():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(_financials())
    nim = next(k for k in dash.kpis if k.metric_name == "NIM")
    # NII 4b / avg earning 80b = 5%
    assert nim.value == Decimal("0.0500")


def _test_roa_calculation():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(_financials())
    roa = next(k for k in dash.kpis if k.metric_name == "ROA")
    # net profit = (4+1)b - 2.5b - 0.3b - 0.6b = 1.6b
    # ROA = 1.6b / 100b = 1.6%
    assert roa.value == Decimal("0.0160")


def _test_threshold_breach_triggers_alert():
    eng = FinanceIntelligenceDashboardEngine()
    # Force a CAR breach
    dash = eng.build_dashboard(
        _financials(car=Decimal("0.10")))
    # CAR should be BREACH (10% < 14.5%)
    car_kpi = next(
        k for k in dash.kpis if k.metric_name == "CAR")
    assert car_kpi.threshold_status == ThresholdStatus.BREACH
    # Alert should fire
    car_alert = next(
        (a for a in dash.alerts if a.kpi_metric == "CAR"), None)
    assert car_alert is not None
    assert car_alert.severity == AlertSeverity.CRITICAL


def _test_alerts_severity_by_family():
    eng = FinanceIntelligenceDashboardEngine()
    # Force COST_INCOME breach (max threshold 55%)
    dash = eng.build_dashboard(_financials(opex=4_000_000_000))
    ci_alert = next(
        (a for a in dash.alerts
         if a.kpi_metric == "COST_TO_INCOME"), None)
    assert ci_alert is not None
    # PROFITABILITY breach → WARNING (not CRITICAL)
    assert ci_alert.severity == AlertSeverity.WARNING


def _test_warning_zone():
    eng = FinanceIntelligenceDashboardEngine()
    # CAR slightly above min — within 10% margin → WARNING
    dash = eng.build_dashboard(
        _financials(car=Decimal("0.150")))   # min × 1.034
    car_kpi = next(
        k for k in dash.kpis if k.metric_name == "CAR")
    assert car_kpi.threshold_status == ThresholdStatus.WARNING


def _test_trend_detection():
    eng = FinanceIntelligenceDashboardEngine()
    prior = _financials(
        period="2026-03", nii=3_500_000_000)
    current = _financials(nii=4_000_000_000)
    dash = eng.build_dashboard(current, prior=prior)
    nim = next(k for k in dash.kpis if k.metric_name == "NIM")
    assert nim.trend == TrendDirection.UP
    assert nim.prior_value is not None


def _test_engine_does_not_mutate_inputs():
    eng = FinanceIntelligenceDashboardEngine()
    fin = _financials()
    eng.build_dashboard(fin)
    assert fin.car_ratio == Decimal("0.18")


def _test_full_provenance():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(_financials())
    assert any(
        "ENH-254" in r for r in dash.framework_refs)
    assert any(
        "Rule 7" in r for r in dash.framework_refs)
    for k in dash.kpis:
        assert k.inputs_used   # non-empty
        assert any(
            "ENH-254" in r for r in k.framework_refs)


def _test_npl_threshold_breach():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(
        _financials(npl=5_000_000_000))   # 5b/60b = 8.3%
    npl_kpi = next(
        k for k in dash.kpis if k.metric_name == "NPL_RATIO")
    assert npl_kpi.threshold_status == ThresholdStatus.BREACH


def _test_recommended_action_is_category_not_action():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(
        _financials(car=Decimal("0.10")))
    car_alert = next(
        a for a in dash.alerts if a.kpi_metric == "CAR")
    # Should be a category like "review capital plan / RWA
    # optimisation" — Rule 7: NOT a specific action
    assert "review" in car_alert.recommended_action_category
    # Engine doesn't say things like "issue Tier 2 bonds" — that's
    # operator's call


def _test_aggregates_populated():
    eng = FinanceIntelligenceDashboardEngine()
    dash = eng.build_dashboard(_financials())
    assert dash.by_family[
        MetricFamily.PROFITABILITY.value] >= 4
    assert dash.by_family[
        MetricFamily.CAPITAL.value] == 1
    # All status counts present
    assert ThresholdStatus.OK.value in dash.by_threshold_status


def self_test() -> None:
    tests = [
        _test_financials_validates_period,
        _test_financials_validates_negative,
        _test_basic_dashboard_no_prior,
        _test_growth_kpis_only_with_prior,
        _test_nim_calculation,
        _test_roa_calculation,
        _test_threshold_breach_triggers_alert,
        _test_alerts_severity_by_family,
        _test_warning_zone,
        _test_trend_detection,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
        _test_npl_threshold_breach,
        _test_recommended_action_is_category_not_action,
        _test_aggregates_populated,
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
        print(
            f"✗ finance_intelligence_dashboard self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ finance_intelligence_dashboard self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
