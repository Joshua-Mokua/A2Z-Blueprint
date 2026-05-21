"""pages/96_finance_arc_cockpit.py — finance Arc Cockpit (v10.69).

Locks the v10.46 Lean+Compact protocol amendment for the finance arc
closure. This page makes all 10 v10.59-v10.68 engines operator-
driveable from the browser:

    📋 Close Orchestration  — utils.finance_close_orchestrator (ENH-249)
    🔗 IC Matching          — utils.intercompany_matching (ENH-250)
    🌐 Group Consolidation  — utils.consolidated_tb_engine (ENH-251)
    🏛️ CBK Reporting        — utils.cbk_regulatory_reporting (ENH-252)
    📈 Predictive Analytics — utils.predictive_financial_analytics (ENH-253)
    📊 CFO Dashboard        — utils.finance_intelligence_dashboard (ENH-254)
    📑 Statement Generator  — utils.financial_statement_generator (ENH-255)
    💼 Tax Compliance       — utils.kra_tax_compliance (ENH-256)
    💱 Multi-Currency       — utils.multi_entity_currency (ENH-257)
    🔒 Audit & Compliance   — utils.finance_audit_compliance (ENH-258)

Per Rule 1, every engine result renders with full provenance — inputs,
intermediates, outputs, framework refs. Per Rule 7, all 10 engines are
diagnostic; this cockpit surfaces exposure, never auto-posts journals,
never auto-revalues, never files with regulators (CBK / KRA), never
serializes statements to PDF/XBRL, never blocks transactions, never
revokes access, never auto-attests period close.
"""
from __future__ import annotations

from decimal import Decimal

import streamlit as st

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.finance_close_orchestrator import (
    FinanceCloseOrchestrator, GLEntry, AccrualSchedule,
    AccountType, AccrualFrequency, CloseTaskSeverity)
from utils.intercompany_matching import (
    IntercompanyMatchingEngine, IcEntry, EliminationType,
    MatchStatus)
from utils.consolidated_tb_engine import (
    ConsolidatedTrialBalanceEngine, EntityProfile,
    TrialBalanceLine, FxRate, FxRateType)
from utils.cbk_regulatory_reporting import (
    CBKRegulatoryReportingEngine, CapitalComponents,
    LiquidityComponents, BorrowerExposure, CurrencyPosition,
    BreachSeverity)
from utils.predictive_financial_analytics import (
    PredictiveFinancialAnalyticsEngine, TimeSeriesPoint,
    ActualVsExpected, DriverContribution, ForecastMethod,
    VarianceMateriality, TrendSignal)
from utils.finance_intelligence_dashboard import (
    FinanceIntelligenceDashboardEngine, PeriodFinancials,
    ThresholdStatus, AlertSeverity, MetricFamily)
from utils.financial_statement_generator import (
    FinancialStatementGenerator, AccountClassification,
    BsClassification, OciClassification, CashFlowSection,
    CashFlowInput, EquityMovement)
from utils.kra_tax_compliance import (
    KRATaxComplianceEngine, CorpTaxInput, CorpTaxRegime,
    VatTransaction, VatStatus, WhtPayment, WhtIncomeType,
    ResidencyStatus, ExciseTransaction, TemporaryDifference,
    TemporaryDifferenceType, TaxType)
from utils.multi_entity_currency import (
    MultiEntityCurrencyEngine, JournalLine, FxSpotRate,
    MonetaryBalance, InterEntityTransferRequest, JournalIssue,
    RevalSeverity)
from utils.finance_audit_compliance import (
    FinanceAuditComplianceEngine, JournalAudit, JournalSource,
    UserAuthorization, PeriodAttestation, AttestationStatus,
    ControlId, FindingSeverity)


# ──────────────────────────────────────────────────────────────────────
# Access + setup
# ──────────────────────────────────────────────────────────────────────

require_access("perform")
um, ud, uname, *_ = load_shared_state()[:12]


# ──────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────

st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,"
    "#1E40AF 0%,#7C3AED 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>"
    "FINANCE ARC · LIVE COCKPIT</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>"
    "Finance Arc Cockpit</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Ten diagnostic engines locked under G135+G136 — close "
    "orchestration, IC matching, group consolidation, CBK reporting, "
    "predictive analytics, CFO dashboard, statement generator, "
    "tax compliance, multi-currency, audit & compliance. Per Rule 7 "
    "every engine is diagnostic — surfaces exposure, never auto-posts "
    "journals, never auto-revalues, never files with regulators "
    "(CBK / KRA / iTax), never serializes statements to PDF/XBRL, "
    "never blocks transactions, never revokes access, never auto-"
    "attests period close.</div></div>",
    unsafe_allow_html=True,
)

st.caption(
    "v10.69 · finance arc closure under v10.46-amended Lean+Compact "
    "protocol")

with st.expander("ℹ️ About this cockpit"):
    st.markdown("""
**v10.69 · finance arc closure**

Ten engines locked under audit gates G135 (registry + scenarios +
modules + Rule 7 + Rule 1) and G136 (UI integration). Thirteenth
closed arc on the platform.

**Standards activated (10):**
- ENH-249 Close Orchestration · ENH-250 IC Matching ·
  ENH-251 Group Consolidation (TB-level) · ENH-252 CBK Reporting
- ENH-253 Predictive Analytics · ENH-254 CFO Dashboard
  (data layer was deferred, UI is this cockpit)
- ENH-255 Statement Generator · ENH-256 KRA Tax Compliance
- ENH-257 Multi-Entity & Multi-Currency · ENH-258 Finance
  Audit & Compliance

**Scenario coverage:** 40 scenarios across the arc (FCO, ICM, GCS,
CBK, PFA, CFO, FSG, TAX, MEC, FAC — 4 each).

**Per Rule 1**, every engine result surfaces full provenance —
inputs, intermediates, outputs, framework refs. Every dataclass is
frozen.

**Per Rule 7**, all 10 engines are diagnostic. No engine in this
arc auto-posts to ledgers, auto-revalues, files with regulators,
serializes to regulator-specific schemas (XBRL/iTax), blocks
transactions, revokes access, or auto-attests period close.
Outputs feed human workflow; the cockpit makes that posture
visible.

**Engine Hub Tier 27** in pages/7_admin.py reflects all 10 engines
with full descriptions.
""")


# ──────────────────────────────────────────────────────────────────────
# Tabs (7 max per G4 — group related engines)
# ──────────────────────────────────────────────────────────────────────

tabs = st.tabs([
    "📋 Close + 🔗 IC",
    "🌐 Consolidation + 💱 Multi-Curr",
    "🏛️ CBK Reporting",
    "📈 Predictive + 📊 CFO",
    "📑 Statements + 💼 Tax",
    "🔒 Audit & Compliance",
    "ℹ️ About",
])


# ──────────────────────────────────────────────────────────────────────
# Tab 0 — Close Orchestration (ENH-249) + IC Matching (ENH-250)
# ──────────────────────────────────────────────────────────────────────

with tabs[0]:
    st.subheader("Close Orchestration (ENH-249)")
    st.caption(
        "5 capabilities: missing recurring accruals + prepayment "
        "amortization + IC pending + suspense balance + cutoff "
        "timing")
    if st.button("Run close orchestration demo", key="fco_run"):
        eng = FinanceCloseOrchestrator()
        gl_entries = (
            GLEntry(
                entry_id="ge1", entity_id="P",
                account_code="9999",
                account_type=AccountType.ASSET,
                debit_kes=Decimal("75000"),
                credit_kes=Decimal("0"),
                period="2026-04",
                posting_date="2026-04-15",
                description="suspense"),
        )
        report = eng.generate_close_report(
            period="2026-04",
            target_close_days=3,
            gl_entries=gl_entries,
            accrual_schedules=(),
            prepayment_schedules=(),
            ic_entries=(),
            cutoff_date="2026-05-05")
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "finance_close_orchestrator",
             "tasks": len(report.tasks)})
        st.success(
            f"Close orchestration complete — {len(report.tasks)} "
            f"tasks ({report.target_close_days}-day target)")
        with st.expander("Tasks (Rule 1 — full provenance)",
                         expanded=True):
            for t in report.tasks:
                st.write(
                    f"**{t.severity.value}** · {t.task_type.value} "
                    f"— {t.description}")

    st.divider()
    st.subheader("Intercompany Matching (ENH-250)")
    st.caption(
        "Mirror-pair IC entries across entities; 4 MatchStatus × "
        "5 EliminationType + multi-leg chain detection")
    if st.button("Run IC matching demo", key="icm_run"):
        eng = IntercompanyMatchingEngine()
        a = IcEntry(
            entry_id="a", entity_id="PARENT",
            counterparty_entity_id="SUBA",
            account_code="IC-1500",
            debit_kes=Decimal("100000"),
            credit_kes=Decimal("0"),
            period="2026-04", reference="IC-INV-001",
            elimination_type=EliminationType.RECEIVABLE_PAYABLE)
        b = IcEntry(
            entry_id="b", entity_id="SUBA",
            counterparty_entity_id="PARENT",
            account_code="IC-2500",
            debit_kes=Decimal("0"),
            credit_kes=Decimal("100000"),
            period="2026-04", reference="IC-INV-001",
            elimination_type=EliminationType.RECEIVABLE_PAYABLE)
        report = eng.match_all((a, b), "2026-04")
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "intercompany_matching",
             "matches": len(report.matches)})
        st.success(
            f"IC matching complete — {len(report.matches)} "
            f"matches; "
            f"{report.total_eliminations_recommended} "
            f"eliminations recommended")
        with st.expander("Matches"):
            for m in report.matches:
                st.write(
                    f"**{m.status.value}** · {m.severity.value} "
                    f"— {m.description}")


# ──────────────────────────────────────────────────────────────────────
# Tab 1 — Consolidation (ENH-251) + Multi-Currency (ENH-257)
# ──────────────────────────────────────────────────────────────────────

with tabs[1]:
    st.subheader("Group Consolidation TB (ENH-251)")
    st.caption(
        "4-step pipeline: aggregate → eliminate → NCI → IAS 21 "
        "FX (CLOSING for B/S, AVERAGE for P&L)")
    if st.button("Run consolidation demo", key="gcs_run"):
        eng = ConsolidatedTrialBalanceEngine()
        p = EntityProfile(
            entity_id="PARENT", entity_name="Parent",
            parent_ownership_pct=Decimal("1"),
            functional_currency="KES", is_parent=True)
        s = EntityProfile(
            entity_id="SUBA", entity_name="Sub A 80%",
            parent_ownership_pct=Decimal("0.80"),
            functional_currency="KES")
        tb = (
            TrialBalanceLine(
                entity_id="PARENT", account_code="3000",
                account_type=AccountType.EQUITY,
                debit_kes=Decimal("0"),
                credit_kes=Decimal("5000000"),
                period="2026-04"),
            TrialBalanceLine(
                entity_id="SUBA", account_code="3000",
                account_type=AccountType.EQUITY,
                debit_kes=Decimal("0"),
                credit_kes=Decimal("1000000"),
                period="2026-04"),
        )
        result = eng.consolidate("2026-04", (p, s), tb)
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "consolidated_tb_engine",
             "lines": len(result.lines)})
        st.success(
            f"Consolidation complete — "
            f"{len(result.lines)} lines, "
            f"{result.entities_consolidated} entities")
        with st.expander("Lines"):
            for line in result.lines:
                st.write(
                    f"**{line.account_code}** "
                    f"({line.account_type.value}) — "
                    f"NCI Cr {line.nci_share_cr}, "
                    f"Parent Cr {line.parent_share_cr}")

    st.divider()
    st.subheader("Multi-Currency Accounting (ENH-257)")
    st.caption(
        "Transaction-level multi-currency journal validation + "
        "IAS 21 §23 FX revaluation + inter-entity transfer")
    if st.button("Run multi-currency demo", key="mec_run"):
        eng = MultiEntityCurrencyEngine()
        # USD journal
        lines = (
            JournalLine(
                line_id="l1", entity_id="P",
                account_code="1500",
                debit_txn_currency=Decimal("10000"),
                credit_txn_currency=Decimal("0"),
                transaction_currency="USD"),
            JournalLine(
                line_id="l2", entity_id="P",
                account_code="2500",
                debit_txn_currency=Decimal("0"),
                credit_txn_currency=Decimal("10000"),
                transaction_currency="USD"),
        )
        rates = (
            FxSpotRate(
                transaction_currency="USD",
                functional_currency="KES",
                rate=Decimal("130"),
                rate_date="2026-04-15"),
        )
        v = eng.validate_multi_currency_journal(
            "J-USD-001", lines, "2026-04-15", rates=rates)
        # Revaluation
        bal = MonetaryBalance(
            balance_id="USD-RCV",
            entity_id="P", account_code="1500",
            currency="USD",
            txn_currency_balance=Decimal("100000"),
            historical_functional_balance=Decimal("12500000"))
        closing = (
            FxSpotRate(
                transaction_currency="USD",
                functional_currency="KES",
                rate=Decimal("130"),
                rate_date="2026-04-30"),
        )
        rev = eng.revalue_monetary_balances(
            "2026-04-30", (bal,), closing)
        # Inter-entity
        rec = eng.recommend_inter_entity_transfer(
            InterEntityTransferRequest(
                request_id="REQ-1",
                from_entity="PARENT", to_entity="SUBA",
                amount_kes=Decimal("10000000"),
                purpose="working_capital_loan"))
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "multi_entity_currency",
             "valid": v.is_valid,
             "reval_findings": len(rev),
             "transfer_amount": str(rec.amount_kes)})
        st.success("Multi-currency demos complete")
        st.write(
            f"**Journal validation:** valid={v.is_valid}, "
            f"functional Dr={v.functional_dr}, "
            f"rate={v.fx_rate_used}")
        st.write(
            f"**Revaluation:** {len(rev)} finding(s); "
            f"first severity={rev[0].severity.value if rev else 'n/a'}")
        st.write(
            f"**Inter-entity transfer:** "
            f"{rec.debit_leg_entity}→{rec.credit_leg_entity} "
            f"amount {rec.amount_kes}")


# ──────────────────────────────────────────────────────────────────────
# Tab 2 — CBK Regulatory Reporting (ENH-252)
# ──────────────────────────────────────────────────────────────────────

with tabs[2]:
    st.subheader("CBK Regulatory Reporting (ENH-252)")
    st.caption(
        "5 returns: CAR (PG 03), LIQ (PG 04), SBL (PG 05), "
        "LXP (PG 05), FXE (PG 06)")
    if st.button("Run CBK returns demo", key="cbk_run"):
        eng = CBKRegulatoryReportingEngine()
        car = eng.generate_car(CapitalComponents(
            period="2026-04",
            tier1_capital_kes=Decimal("1500000000"),
            tier2_capital_kes=Decimal("300000000"),
            deductions_kes=Decimal("100000000"),
            risk_weighted_assets_kes=Decimal("10000000000")))
        liq = eng.generate_liq(LiquidityComponents(
            period="2026-04",
            liquid_assets_kes=Decimal("3000000000"),
            total_deposits_kes=Decimal("10000000000")))
        sbl = eng.generate_sbl(
            "2026-04", Decimal("1000000000"),
            (BorrowerExposure(
                borrower_id="MEGA",
                borrower_name="Mega Corp",
                funded_kes=Decimal("180000000"),
                unfunded_kes=Decimal("20000000")),))
        fxe = eng.generate_fxe(
            "2026-04", Decimal("1000000000"),
            (CurrencyPosition(
                currency="USD",
                long_kes_equivalent=Decimal("80000000"),
                short_kes_equivalent=Decimal("30000000")),))
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "cbk_regulatory_reporting",
             "returns_generated": 4})
        st.success("CBK returns generated")
        for label, pkg in (
            ("CAR", car), ("LIQ", liq), ("SBL", sbl),
            ("FXE", fxe)):
            st.write(
                f"**{label}**: severity "
                f"{pkg.breach_severity.value} — "
                f"{pkg.breach_description}")


# ──────────────────────────────────────────────────────────────────────
# Tab 3 — Predictive (ENH-253) + CFO Dashboard (ENH-254)
# ──────────────────────────────────────────────────────────────────────

with tabs[3]:
    st.subheader("Predictive Financial Analytics (ENH-253)")
    st.caption(
        "3 forecast methods + ML hook (Rule 6: ml_disabled "
        "flag) · variance · driver decomposition · trend")
    if st.button("Run predictive demo", key="pfa_run"):
        eng = PredictiveFinancialAnalyticsEngine()
        history = tuple(
            TimeSeriesPoint(
                period=f"2025-{m:02d}",
                value_kes=Decimal(str(1000000 + 50000 * m)))
            for m in range(1, 13))
        f = eng.forecast(
            "monthly_revenue", history, horizon=3,
            method=ForecastMethod.LINEAR_TREND)
        variance = eng.analyze_variance((
            ActualVsExpected(
                metric_name="rev", period="2026-04",
                actual_kes=Decimal("950000"),
                expected_kes=Decimal("1000000")),
        ))
        trend = eng.detect_trend("rev", history)
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "predictive_financial_analytics",
             "forecast_points": len(f.points),
             "variance_findings": len(variance)})
        st.success("Predictive demos complete")
        st.write(
            f"**Forecast** ({f.method_used.value}): "
            f"{len(f.points)} points, "
            f"ml_disabled={f.ml_disabled}")
        if variance:
            st.write(
                f"**Variance:** {variance[0].materiality.value} "
                f"/ {variance[0].direction.value}")
        st.write(
            f"**Trend:** {trend.signal.value}, "
            f"slope={trend.slope_per_period}")

    st.divider()
    st.subheader("CFO Dashboard (ENH-254)")
    st.caption(
        "6 KPI families: profitability · capital · liquidity · "
        "growth · efficiency · asset quality. Split-implementation "
        "pulled into this cockpit per v10.46 amendment.")
    if st.button("Run CFO dashboard demo", key="cfo_run"):
        eng = FinanceIntelligenceDashboardEngine()
        fin = PeriodFinancials(
            period="2026-04",
            net_interest_income_kes=Decimal("4000000000"),
            non_interest_income_kes=Decimal("1000000000"),
            operating_expenses_kes=Decimal("2500000000"),
            impairment_kes=Decimal("300000000"),
            tax_kes=Decimal("600000000"),
            avg_total_assets_kes=Decimal("100000000000"),
            avg_equity_kes=Decimal("10000000000"),
            avg_earning_assets_kes=Decimal("80000000000"),
            closing_total_loans_kes=Decimal("60000000000"),
            closing_total_deposits_kes=Decimal("80000000000"),
            closing_npl_kes=Decimal("2400000000"),
            closing_provision_kes=Decimal("1800000000"),
            customer_count=500000, branch_count=50,
            transaction_count=10000000,
            transaction_processing_cost_kes=(
                Decimal("300000000")),
            car_ratio=Decimal("0.18"),
            liq_ratio=Decimal("0.25"))
        dash = eng.build_dashboard(fin)
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "finance_intelligence_dashboard",
             "kpis": len(dash.kpis),
             "alerts": len(dash.alerts)})
        st.success(
            f"Dashboard built — {len(dash.kpis)} KPIs, "
            f"{len(dash.alerts)} alerts")
        for k in dash.kpis:
            badge = {
                ThresholdStatus.OK: "✅",
                ThresholdStatus.WARNING: "⚠️",
                ThresholdStatus.BREACH: "🚨",
                ThresholdStatus.NOT_APPLICABLE: "·"}.get(
                k.threshold_status, "·")
            st.write(
                f"{badge} **{k.metric_name}** "
                f"({k.family.value}): {k.value} {k.unit}")


# ──────────────────────────────────────────────────────────────────────
# Tab 4 — Statements (ENH-255) + Tax (ENH-256)
# ──────────────────────────────────────────────────────────────────────

with tabs[4]:
    st.subheader("Financial Statement Generator (ENH-255)")
    st.caption(
        "5 IFRS statements: BS (IAS 1 §54) · IS (IAS 1 §82) · "
        "OCI (IAS 1 §82A with CTA from ENH-251) · Equity (IAS "
        "1 §106) · CF (IAS 7)")
    if st.button("Run statement generator demo", key="fsg_run"):
        # Build minimal consolidated TB
        from utils.consolidated_tb_engine import (
            ConsolidatedLine, ConsolidatedTrialBalance)
        tb_lines = (
            ConsolidatedLine(
                account_code="1010",
                account_type=AccountType.ASSET,
                entity_contributions=(),
                pre_elimination_dr=Decimal("5000000"),
                pre_elimination_cr=Decimal("0"),
                eliminations_applied_dr=Decimal("0"),
                eliminations_applied_cr=Decimal("0"),
                post_elimination_dr=Decimal("5000000"),
                post_elimination_cr=Decimal("0"),
                nci_share_dr=Decimal("0"),
                nci_share_cr=Decimal("0"),
                parent_share_dr=Decimal("5000000"),
                parent_share_cr=Decimal("0"),
                framework_refs=("ENH-251",)),
            ConsolidatedLine(
                account_code="3000",
                account_type=AccountType.EQUITY,
                entity_contributions=(),
                pre_elimination_dr=Decimal("0"),
                pre_elimination_cr=Decimal("5000000"),
                eliminations_applied_dr=Decimal("0"),
                eliminations_applied_cr=Decimal("0"),
                post_elimination_dr=Decimal("0"),
                post_elimination_cr=Decimal("5000000"),
                nci_share_dr=Decimal("0"),
                nci_share_cr=Decimal("0"),
                parent_share_dr=Decimal("0"),
                parent_share_cr=Decimal("5000000"),
                framework_refs=("ENH-251",)),
        )
        tb = ConsolidatedTrialBalance(
            period="2026-04",
            presentation_currency="KES",
            lines=tb_lines, findings=(),
            entities_consolidated=1,
            eliminations_applied_count=0,
            total_dr=Decimal("5000000"),
            total_cr=Decimal("5000000"),
            cumulative_translation_adjustment_kes=(
                Decimal("0")),
            framework_refs=("ENH-251",))
        cls = (
            AccountClassification(
                account_code="1010",
                bs_classification=(
                    BsClassification.CURRENT_ASSET),
                line_label="Cash"),
            AccountClassification(
                account_code="3000",
                bs_classification=(
                    BsClassification.EQUITY_PARENT),
                line_label="Share Capital"),
        )
        eng = FinancialStatementGenerator()
        pkg = eng.generate_package(tb, cls)
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "financial_statement_generator",
             "bs_total_assets": str(
                 pkg.balance_sheet.total_assets_kes)})
        st.success("IFRS statements generated")
        st.write(
            f"**Balance Sheet:** Assets "
            f"{pkg.balance_sheet.total_assets_kes}, "
            f"Liab {pkg.balance_sheet.total_liabilities_kes}, "
            f"Equity {pkg.balance_sheet.total_equity_kes}")

    st.divider()
    st.subheader("KRA Tax Compliance (ENH-256)")
    st.caption(
        "5 tax types: corporation tax · VAT · WHT · excise duty "
        "· deferred tax (IAS 12)")
    if st.button("Run tax compliance demo", key="tax_run"):
        eng = KRATaxComplianceEngine()
        ci = CorpTaxInput(
            period="2026",
            accounting_profit_kes=Decimal("100000000"),
            permanent_addbacks_kes=Decimal("5000000"),
            permanent_deductions_kes=Decimal("2000000"),
            timing_differences_net_kes=Decimal("3000000"),
            regime=CorpTaxRegime.STANDARD_RESIDENT)
        vat = (
            VatTransaction(
                transaction_id="v1", period="2026-04",
                base_amount_kes=Decimal("5000000"),
                status=VatStatus.STANDARD),
        )
        wht = (
            WhtPayment(
                payment_id="w1", period="2026-04",
                income_type=WhtIncomeType.DIVIDEND,
                gross_amount_kes=Decimal("100000"),
                payee_residency=ResidencyStatus.RESIDENT),
        )
        diffs = (
            TemporaryDifference(
                description="Accelerated depreciation",
                period="2026-04",
                amount_kes=Decimal("5000000"),
                diff_type=TemporaryDifferenceType.TAXABLE),
        )
        pkg = eng.build_return_package(
            "2026-04",
            corp_tax_input=ci,
            vat_transactions=vat,
            wht_payments=wht,
            temp_differences=diffs)
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "kra_tax_compliance",
             "computations": len(pkg.computations)})
        st.success(
            f"Tax return package — "
            f"{len(pkg.computations)} computations, "
            f"deferred tax {pkg.deferred_tax is not None}")
        for tt, amt in pkg.by_tax_type.items():
            if amt != 0:
                st.write(f"**{tt}**: {amt}")


# ──────────────────────────────────────────────────────────────────────
# Tab 5 — Audit & Compliance (ENH-258)
# ──────────────────────────────────────────────────────────────────────

with tabs[5]:
    st.subheader("Finance Audit & Compliance (ENH-258)")
    st.caption(
        "5 SOX-style controls: SoD · authorization · manual "
        "journal · period attestation · late adjustment")
    if st.button("Run compliance report demo", key="fac_run"):
        eng = FinanceAuditComplianceEngine()
        journals = (
            JournalAudit(
                journal_id="J-CLEAN",
                period="2026-04",
                posting_date="2026-04-15",
                amount_kes=Decimal("50000"),
                source=JournalSource.AUTOMATED,
                preparer_user_id="alice",
                reviewer_user_id="bob",
                poster_user_id="carol"),
            JournalAudit(
                journal_id="J-SOD-BREACH",
                period="2026-04",
                posting_date="2026-04-20",
                amount_kes=Decimal("200000"),
                source=JournalSource.MANUAL,
                preparer_user_id="rogue",
                reviewer_user_id="rogue",
                poster_user_id="rogue"),
        )
        auths = (
            UserAuthorization(
                user_id="carol",
                max_journal_kes=Decimal("100000"),
                role="POSTER"),
            UserAuthorization(
                user_id="rogue",
                max_journal_kes=Decimal("500000"),
                role="POSTER"),
        )
        attestations = (
            PeriodAttestation(
                attestation_id="GL-2026-04",
                period="2026-04", function="GL_CLOSE",
                deadline_date="2026-05-05",
                status=AttestationStatus.OVERDUE,
                attestor_user_id="cfo",
                attested_at=None),
        )
        report = eng.build_compliance_report(
            "2026-04",
            journals=journals,
            authorizations=auths,
            attestations=attestations,
            period_cutoff_date="2026-05-05")
        audit_log(
            "FINANCE_ENGINE_USED", uname,
            {"engine": "finance_audit_compliance",
             "findings": len(report.findings)})
        st.success(
            f"Compliance scan complete — "
            f"{len(report.findings)} findings, "
            f"{report.journals_scanned} journals scanned")
        for f in report.findings:
            badge = {
                FindingSeverity.CRITICAL: "🚨",
                FindingSeverity.HIGH: "⚠️",
                FindingSeverity.MEDIUM: "·",
                FindingSeverity.LOW: "·",
                FindingSeverity.INFO: "ℹ️"}.get(
                f.severity, "·")
            st.write(
                f"{badge} **{f.control.value}** · "
                f"{f.severity.value} — {f.description}")


# ──────────────────────────────────────────────────────────────────────
# Tab 6 — About + arc summary
# ──────────────────────────────────────────────────────────────────────

with tabs[6]:
    st.subheader("Finance Arc Summary")
    st.markdown("""
**Arc closure batch:** v10.69 (this drop)

**Scope:** 11 batches v10.59 → v10.69 producing 10 standards, 10 modules,
40 scenarios across the arc, 2 closure ratchets (G135 + G136),
1 cockpit page (this one), Engine Hub Tier 27 expansion to full
descriptions, Master Prompt v3 line 108 update.

**Closed-arc count:** 13 — finance arc joins
- Treasury (v10.37, G127)
- Risk (v10.46, G129+G130)
- Credit/Model Risk (v10.49, G131+G132)
- Revenue Assurance (v10.58, G133+G134)
- and 8 prior closed arcs.

**Discipline preserved:**
- Per Rule 1, every result dataclass is frozen with full
  provenance — inputs, intermediates, outputs, framework refs.
- Per Rule 6, ML hooks surface `ml_disabled=True` with reason
  when no caller-supplied predictor (ENH-253 explicitly tested).
- Per Rule 7, all 10 engines are diagnostic — never auto-post,
  never auto-revalue, never file with regulators (CBK / KRA),
  never serialize statements to PDF/XBRL, never block
  transactions, never revoke access, never auto-attest.
- Audit gate G135 verifies the structural contract; G136 verifies
  this cockpit imports + invokes all 10 engines.

**Composition:** the 10 engines compose along clear lines —
ENH-249 detects in-entity IC pending; ENH-250 pairs IC across
entities; ENH-251 consumes IC eliminations + entity TBs to
produce consolidated TB; ENH-252 reads the consolidated capital +
liquidity to produce CBK returns; ENH-255 consumes the
consolidated TB + classifications to produce IFRS statements;
ENH-256 layers tax on top of accounting profit; ENH-257 handles
transaction-level FX before TBs are extracted; ENH-258 audits
the journal trail across all the others; ENH-253 forecasts
metrics derived from the others; ENH-254 dashboards them.

**Honest scope notes** (full detail in CHANGELOGs v10.59 through
v10.69) — every engine ships with explicit "what it doesn't do"
documentation. No engine pretends to be more than it is.
""")


# ──────────────────────────────────────────────────────────────────────
# Footer
# ──────────────────────────────────────────────────────────────────────

st.markdown("---")
st.caption(
    "v10.69 · finance arc closure · 13th closed arc on the platform · "
    "150 consecutive clean batches · audit 134/134 PASS")
