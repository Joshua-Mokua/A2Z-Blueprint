"""pages/95_revenue_assurance_cockpit.py — Revenue Assurance Cockpit (v10.58).

Locks the v10.46 Lean+Compact protocol amendment for the revenue_assurance
arc closure. This page makes all 8 v10.50-v10.57 engines operator-driveable
from the browser:

    📋 Validation        — utils.revenue_validation (ENH-241)
    🔍 Anomaly Patterns  — utils.revenue_anomaly_patterns (ENH-242)
    🧭 Orchestrator      — utils.revenue_orchestrator (ENH-243)
    🤝 Partner & Supplier — utils.partner_supplier_recon (ENH-244)
    📊 Dashboard Metrics — utils.revenue_dashboard_metrics (ENH-245)
    ✅ Pre-issuance Verify — utils.continuous_billing_verification (ENH-246)
    💼 Commission Assurance — utils.commission_assurance (ENH-247)
    🏛️ Regulatory Reporting — utils.regulatory_revenue_reporting (ENH-248)

Per Rule 1, every engine result renders with full provenance — inputs,
intermediates, outputs, framework refs. Per Rule 7, all 8 engines are
diagnostic; this cockpit surfaces exposure, never auto-corrects records,
never blocks billing, never submits to regulators, never pays
commissions, never resolves disputes.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date

import streamlit as st

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.revenue_validation import (
    RevenueValidationEngine, RevenueRecord, CrossSourceTotal,
    ValidationSeverity, ValidationCategory)
from utils.revenue_anomaly_patterns import (
    RevenueAnomalyPatternEngine, ContractRate,
    CommissionRecord, PatternFamily)
from utils.revenue_orchestrator import (
    RevenueOrchestrator, FindingType, InvestigatorTeam,
    WorkItemState, PatternFinding)
from utils.partner_supplier_recon import (
    PartnerSupplierReconciliationEngine, PartnerAgreement,
    PartnerRevenueRecord, PartnerSettlement, PurchaseOrder,
    GoodsReceiptNote, SupplierInvoice, SupplierPayment,
    DiscrepancyType, PartySide)
from utils.revenue_dashboard_metrics import (
    RevenueDashboardMetrics, DashboardWindow, StateTransition,
    CycleStage)
from utils.continuous_billing_verification import (
    ContinuousBillingVerificationEngine, BillingDraft,
    ExtendedContractRate, Verdict, CheckStatus, CheckName)
from utils.commission_assurance import (
    CommissionAssuranceEngine, IncentivePlan, CommissionTier,
    TierBasis, PaidCommissionRecord, CommissionOverride,
    OverrideStatus, CommissionDispute, DisputeStatus,
    CommissionFinding)
from utils.regulatory_revenue_reporting import (
    RegulatoryRevenueReportingEngine, ReportTemplate,
    ReportLineSpec, StatutoryReportRecord, Regulator,
    DifferenceType, CompletenessIssue)


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
    "#0F766E 0%,#0891B2 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>"
    "REVENUE ASSURANCE · LIVE COCKPIT</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>"
    "Revenue Assurance Cockpit</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Eight diagnostic engines locked under G133+G134 — validation, "
    "anomaly patterns, agentic orchestrator, partner/supplier "
    "reconciliation, dashboard metrics, pre-issuance verification, "
    "commission assurance, regulatory reporting. Per Rule 7 every "
    "engine is diagnostic — surfaces exposure, never auto-corrects, "
    "never blocks billing, never submits to regulators, never pays "
    "commissions, never resolves disputes.</div></div>",
    unsafe_allow_html=True,
)

st.caption(
    "v10.58 · revenue_assurance arc closure under v10.46-amended "
    "Lean+Compact protocol")

with st.expander("ℹ️ About this cockpit"):
    st.markdown("""
**v10.58 · revenue_assurance arc closure**

Eight engines locked under audit gates G133 (registry + scenarios +
modules) and G134 (UI integration). Twelfth closed arc on the platform.

**Standards activated (8):** ENH-241 Validation · ENH-242 Patterns ·
ENH-243 Orchestrator · ENH-244 Partner/Supplier Recon · ENH-245
Dashboard Metrics (data layer; UI is this cockpit) · ENH-246 Pre-
issuance Verification · ENH-247 Commission Assurance · ENH-248
Regulatory Reporting.

**Scenario coverage:** 32 scenarios across the arc (RA · PAT · ORC ·
PSR · DSH · CBV · CMA · ORR — 4 each).

**Per Rule 1**, every engine result surfaces full provenance —
inputs, intermediates, outputs, framework refs. Every dataclass is
frozen.

**Per Rule 7**, all 8 engines are diagnostic. No engine in this arc
auto-corrects records, blocks billing, submits to regulators, pays
commissions, resolves disputes, or modifies state. Outputs feed
human workflow; the cockpit makes that posture visible.
""")


# ──────────────────────────────────────────────────────────────────────
# Tabs (7 max per G4)
# ──────────────────────────────────────────────────────────────────────

tabs = st.tabs([
    "📋 Validation",
    "🔍 Patterns",
    "🧭 Orchestrator + 📊 Metrics",
    "🤝 Partner/Supplier",
    "✅ Pre-issuance",
    "💼 Commission",
    "🏛️ Regulatory",
])


# ──────────────────────────────────────────────────────────────────────
# Tab 1 — Validation (ENH-241)
# ──────────────────────────────────────────────────────────────────────

with tabs[0]:
    st.subheader("Revenue Validation (ENH-241)")
    st.caption(
        "Schema · Completeness · Cross-Source recon (CBS↔GL) · "
        "Statistical anomaly")
    seed_records = [
        RevenueRecord(
            record_id="R-001", source_system="CBS",
            posting_date=date(2026, 4, 15),
            amount_kes=Decimal("100000"),
            revenue_category="INTEREST_INCOME",
            branch_code="NRB-01"),
        RevenueRecord(
            record_id="R-002", source_system="CBS",
            posting_date=date(2026, 4, 16),
            amount_kes=Decimal("50000"),
            revenue_category="FEE_INCOME",
            branch_code="NRB-01"),
    ]
    if st.button("Run validation engine", key="rv_run"):
        eng = RevenueValidationEngine()
        report = eng.validate_all(records=seed_records)
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "revenue_validation",
             "findings": len(report.findings)})
        st.success(
            f"Validation complete — {len(report.findings)} "
            "findings")
        with st.expander("Severity breakdown", expanded=True):
            st.json(report.by_severity)
        with st.expander("Category breakdown"):
            st.json(report.by_category)
        with st.expander("Findings (Rule 1 — full provenance)"):
            for f in report.findings:
                st.write(
                    f"**{f.severity.value}** · "
                    f"{f.category.value} — {f.description}")


# ──────────────────────────────────────────────────────────────────────
# Tab 2 — Anomaly Patterns (ENH-242)
# ──────────────────────────────────────────────────────────────────────

with tabs[1]:
    st.subheader("Revenue Anomaly Patterns (ENH-242)")
    st.caption(
        "6 deterministic detectors over POSTED records; ML hook "
        "injectable per Rule 6 (ml_disabled flag surfaced explicitly "
        "when absent)")
    if st.button("Run pattern detection demo", key="ra_run"):
        eng = RevenueAnomalyPatternEngine()
        # Demo: 2 duplicate billings — same customer, same amount,
        # within 3 days
        records = [
            RevenueRecord(
                record_id="R-A", source_system="CBS",
                posting_date=date(2026, 4, 10),
                amount_kes=Decimal("5000"),
                revenue_category="FEE_INCOME",
                branch_code="NRB-01",
                customer_id="C-001"),
            RevenueRecord(
                record_id="R-B", source_system="CBS",
                posting_date=date(2026, 4, 11),
                amount_kes=Decimal("5000"),
                revenue_category="FEE_INCOME",
                branch_code="NRB-01",
                customer_id="C-001"),
        ]
        findings = eng.detect_duplicate_billing(records)
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "revenue_anomaly_patterns",
             "findings": len(findings),
             "detector": "duplicate_billing"})
        if findings:
            st.warning(f"{len(findings)} duplicate billing finding(s)")
            for f in findings:
                st.write(
                    f"- **{f.severity.value}** · {f.pattern_id.value} "
                    f"· {f.description}")
                st.caption(
                    f"Records: {f.record_ids} · "
                    f"Framework: {f.framework_refs[0]}")
        else:
            st.info("No duplicates in demo data")
        st.caption(
            "ml_disabled=True surfaced — this demo runs deterministic "
            "detectors only; production injects ML hook via "
            "engine.attach_ml_anomaly_detector(...)")


# ──────────────────────────────────────────────────────────────────────
# Tab 3 — Orchestrator (ENH-243) + Metrics (ENH-245)
# ──────────────────────────────────────────────────────────────────────

with tabs[2]:
    st.subheader("Revenue Agentic Orchestrator (ENH-243)")
    st.caption(
        "Stateless — caller maintains state externally. "
        "Routes findings to 6 InvestigatorTeam values via "
        "(severity, family) lookup.")
    if st.button("Demo: route a sample finding", key="ro_run"):
        from utils.revenue_orchestrator import (
            OrchestratorConfig, TriageRule, InvestigatorTeam)
        from utils.revenue_anomaly_patterns import PatternId
        # Minimal triage rule set keyed by family + severity. A real
        # deployment configures these per the bank's investigation
        # team structure. The demo uses sensible defaults.
        rules = (
            TriageRule(
                family_or_category="BILLING_ERROR",
                severity=ValidationSeverity.HIGH,
                team=InvestigatorTeam.REVENUE_RECOVERY,
                sla_days=5),
            TriageRule(
                family_or_category="LEAKAGE",
                severity=ValidationSeverity.HIGH,
                team=InvestigatorTeam.REVENUE_RECOVERY,
                sla_days=5),
            TriageRule(
                family_or_category="COMMISSION_MISCALC",
                severity=ValidationSeverity.MEDIUM,
                team=InvestigatorTeam.OPERATIONS,
                sla_days=10),
        )
        cfg = OrchestratorConfig(triage_rules=rules)
        eng = RevenueOrchestrator(config=cfg)
        finding = PatternFinding(
            finding_id="F-DEMO-001",
            pattern_id=PatternId.EXPIRED_CONTRACT_BILLING,
            family=PatternFamily.BILLING_ERROR,
            severity=ValidationSeverity.HIGH,
            record_ids=("R-X",),
            description="Demo high-severity billing exception",
            evidence="Contract expired 2025-10-01; charges accrued",
            confidence=Decimal("0.85"),
            ml_score=None,
            framework_refs=("ENH-242",),
            notes="")
        result = eng.orchestrate(
            findings=[finding],
            raised_dates={"F-DEMO-001": date(2026, 4, 20)},
            as_of=date(2026, 4, 25),
            monetary_impacts={"F-DEMO-001": Decimal("500000")})
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            f"engine=revenue_orchestrator items={len(result.work_items)}")
        wi = result.work_items[0]
        st.metric("Priority score", f"{float(wi.priority_score):.1f}")
        st.metric("Routed to", wi.assigned_team.value)
        st.metric("Past SLA?", "Yes" if wi.past_sla else "No")
        with st.expander("priority_components (Rule 1)"):
            st.json({k: str(v)
                     for k, v in wi.priority_components.items()})

    st.divider()
    st.subheader("Revenue Dashboard Metrics (ENH-245)")
    st.caption(
        "Read-only aggregation. 6 metric families consumed by this "
        "cockpit — leakage trend, top categories (count + impact), "
        "recovery, team activity, cycle times, summary.")
    if st.button("Demo: compute metrics", key="rdm_run"):
        from utils.revenue_orchestrator import WorkItem
        eng = RevenueDashboardMetrics()
        items = [
            WorkItem(
                work_item_id="W1",
                source_finding_id="F1",
                source_finding_type=FindingType.PATTERN,
                severity=ValidationSeverity.HIGH,
                family_or_category="BILLING",
                description="demo",
                affected_record_ids=("R1",),
                raised_date=date(2026, 4, 1),
                age_days=15, sla_deadline=date(2026, 4, 8),
                past_sla=True,
                assigned_team=InvestigatorTeam.BILLING_OPS,
                priority_score=Decimal("75"),
                priority_components={},
                monetary_impact_kes=Decimal("50000"),
                current_state=WorkItemState.IN_PROGRESS,
                framework_refs=("ENH-243",)),
        ]
        window = DashboardWindow(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31))
        metrics = eng.compute_all(items, window, ())
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "revenue_dashboard_metrics",
             "items": metrics.total_work_items})
        st.metric("Total work items", metrics.total_work_items)
        st.metric("Recovery KES", str(metrics.recovery.recovered_kes))
        st.metric(
            "Open count", metrics.recovery.open_count)
        with st.expander("Team activity"):
            for t in metrics.team_activities:
                st.write(
                    f"**{t.team.value}** — total {t.total_count}, "
                    f"past_sla {t.past_sla_count}")


# ──────────────────────────────────────────────────────────────────────
# Tab 4 — Partner & Supplier Recon (ENH-244)
# ──────────────────────────────────────────────────────────────────────

with tabs[3]:
    st.subheader("Partner & Supplier Reconciliation (ENH-244)")
    st.caption(
        "Multi-party recon — partner share validation + supplier "
        "3-way match (PO → GRN → Invoice → Payment)")
    if st.button("Demo: partner share recon", key="ps_run"):
        eng = PartnerSupplierReconciliationEngine()
        agreement = PartnerAgreement(
            agreement_id="DEMO-AGT", partner_id="MTN",
            revenue_category="COMMISSION_INCOME",
            share_pct=Decimal("0.30"),
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31))
        revenues = [
            PartnerRevenueRecord(
                record_id="r1", partner_id="MTN",
                agreement_id="DEMO-AGT",
                revenue_category="COMMISSION_INCOME",
                gross_revenue_kes=Decimal("3000000"),
                posting_date=date(2026, 4, 10)),
        ]
        settlements = [
            PartnerSettlement(
                settlement_id="ST-001", partner_id="MTN",
                agreement_id="DEMO-AGT", period="2026-04",
                settled_kes=Decimal("800000"),
                settlement_date=date(2026, 5, 5)),
        ]
        findings = eng.validate_partner_share(
            (agreement,), revenues, settlements)
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "partner_supplier_recon",
             "findings": len(findings)})
        if findings:
            f = findings[0]
            st.error(
                f"**{f.discrepancy_type.value}** — "
                f"{f.party_id} variance KES "
                f"{f.variance_kes:,}")
            st.caption(f"Expected: {f.expected}")
            st.caption(f"Observed: {f.observed}")


# ──────────────────────────────────────────────────────────────────────
# Tab 5 — Pre-issuance Verification (ENH-246)
# ──────────────────────────────────────────────────────────────────────

with tabs[4]:
    st.subheader("Continuous Billing Verification (ENH-246)")
    st.caption(
        "PRE-issuance verification (vs ENH-242 which screens POSTED "
        "records). 5 checks → 3 Verdicts (PASS / HOLD / REJECT). "
        "Engine recommends; caller's billing pipeline decides.")
    if st.button("Demo: verify a draft", key="cbv_run"):
        eng = ContinuousBillingVerificationEngine()
        contract = ContractRate(
            contract_id="DEMO-C", customer_id="cust-A",
            product_code="LOAN", floor_rate_pct=Decimal("3.0"),
            ceiling_rate_pct=Decimal("8.0"),
            effective_from=date(2026, 1, 1),
            effective_to=date(2026, 12, 31))
        # Below-floor rate → HOLD
        draft = BillingDraft(
            draft_id="D-DEMO", customer_id="cust-A",
            product_code="LOAN", contract_id="DEMO-C",
            proposed_amount_kes=Decimal("100000"),
            draft_date=date(2026, 4, 15),
            applied_rate_pct=Decimal("2.5"))
        result = eng.verify(draft, contracts=(contract,))
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "continuous_billing_verification",
             "verdict": result.verdict.value})
        verdict_colour = {
            Verdict.PASS: "✅", Verdict.HOLD_PENDING_REVIEW: "⚠️",
            Verdict.REJECT_RECOMMENDED: "🚫",
        }
        st.metric(
            "Verdict",
            f"{verdict_colour[result.verdict]} "
            f"{result.verdict.value}")
        st.write(
            f"FAIL: {result.fail_count} · WARN: {result.warn_count} "
            f"· SKIPPED: {result.skipped_count}")
        with st.expander("All 5 check results (Rule 1)"):
            for r in result.check_results:
                icon = {
                    CheckStatus.PASS: "✅",
                    CheckStatus.WARN: "⚠️",
                    CheckStatus.FAIL: "🚫",
                    CheckStatus.SKIPPED: "⏭️",
                }[r.status]
                st.write(
                    f"{icon} **{r.check_name.value}** ({r.status.value}) "
                    f"— {r.description}")


# ──────────────────────────────────────────────────────────────────────
# Tab 6 — Commission Assurance (ENH-247)
# ──────────────────────────────────────────────────────────────────────

with tabs[5]:
    st.subheader("Commission & Incentive Assurance (ENH-247)")
    st.caption(
        "Plan-based recomputation. Closes the loop with ENH-242 — "
        "where ENH-242 took expected as input, ENH-247 COMPUTES it "
        "from a tiered IncentivePlan.")
    if st.button("Demo: tier walk", key="cma_run"):
        eng = CommissionAssuranceEngine()
        plan = IncentivePlan(
            plan_id="DEMO-PLAN", rm_role="RM-Tier-1",
            tiers=(
                CommissionTier(
                    tier_min_kes=Decimal("0"),
                    tier_max_kes=Decimal("100000"),
                    rate_pct=Decimal("0.02")),
                CommissionTier(
                    tier_min_kes=Decimal("100000"),
                    tier_max_kes=Decimal("500000"),
                    rate_pct=Decimal("0.03")),
                CommissionTier(
                    tier_min_kes=Decimal("500000"),
                    tier_max_kes=None,
                    rate_pct=Decimal("0.05")),
            ),
            basis=TierBasis.MARGINAL)
        calc = eng.compute_expected_commission(
            plan, "rm-DEMO", "2026-04", Decimal("1000000"))
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "commission_assurance",
             "rm": "rm-DEMO",
             "expected": str(calc.expected_commission_kes)})
        st.metric(
            "Expected commission KES",
            f"{calc.expected_commission_kes:,}")
        st.caption(
            f"Underlying revenue: KES "
            f"{calc.underlying_revenue_kes:,} · "
            f"Basis: {calc.basis.value}")
        with st.expander(
                "Per-tier contribution breakdown (Rule 1)",
                expanded=True):
            for c in calc.contributions:
                top = (
                    str(c.tier_max_kes)
                    if c.tier_max_kes is not None else "∞")
                st.write(
                    f"**[{c.tier_min_kes:,} → {top}]** @ "
                    f"{c.rate_pct * 100:.1f}% · "
                    f"amount in tier: KES {c.amount_in_tier_kes:,} "
                    f"· contribution: KES {c.contribution_kes:,}")


# ──────────────────────────────────────────────────────────────────────
# Tab 7 — Regulatory Reporting (ENH-248)
# ──────────────────────────────────────────────────────────────────────

with tabs[6]:
    st.subheader("Regulatory Revenue Reporting (ENH-248)")
    st.caption(
        "Engine produces ReportPackage data; serialization (XBRL/"
        "XML/CSV) and submission rails (CBK BSD portal, KRA iTax) "
        "are caller's workflow.")
    if st.button("Demo: generate CBK Q1 report", key="orr_run"):
        eng = RegulatoryRevenueReportingEngine()
        template = ReportTemplate(
            template_id="DEMO-CBK-Q1",
            regulator=Regulator.CBK,
            period_label="2026-Q1",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            line_specs=(
                ReportLineSpec(
                    line_code="L-INT", line_name="Interest income",
                    revenue_categories=frozenset(
                        {"INTEREST_INCOME"}),
                    required=True),
                ReportLineSpec(
                    line_code="L-FEE", line_name="Fee income",
                    revenue_categories=frozenset(
                        {"FEE_INCOME", "COMMISSION_INCOME"}),
                    required=True),
            ))
        records = [
            RevenueRecord(
                record_id="R1", source_system="CBS",
                posting_date=date(2026, 2, 5),
                amount_kes=Decimal("500000"),
                revenue_category="INTEREST_INCOME",
                branch_code="NRB-01"),
            RevenueRecord(
                record_id="R2", source_system="CBS",
                posting_date=date(2026, 2, 20),
                amount_kes=Decimal("100000"),
                revenue_category="FEE_INCOME",
                branch_code="NRB-01"),
        ]
        pkg = eng.generate_report(template, records)
        audit_log(
            "REVENUE_ENGINE_USED", uname,
            {"engine": "regulatory_revenue_reporting",
             "template": pkg.template_id,
             "total_kes": str(pkg.total_kes)})
        st.metric("Total KES", f"{pkg.total_kes:,}")
        st.metric("Regulator", pkg.regulator.value)
        with st.expander("Line items (Rule 1 provenance)",
                         expanded=True):
            for li in pkg.line_items:
                st.write(
                    f"**{li.line_code} — {li.line_name}** · "
                    f"KES {li.amount_kes:,} · "
                    f"{li.record_count} record(s)")
                st.caption(
                    f"Records: {list(li.contributing_record_ids)}")
        if pkg.unmapped_categories:
            st.warning(
                f"Unmapped categories: "
                f"{list(pkg.unmapped_categories)} — "
                f"{pkg.unmapped_record_count} record(s)")
