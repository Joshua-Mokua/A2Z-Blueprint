"""pages/27_compliance_arc_cockpit.py — AML/Compliance Arc Cockpit (v10.169).

Phase 3 AML/Compliance Module closure — 11th module closure in platform
history (after Treasury v10.155). Locks all 9 AML/Compliance standards
(ENH-191..ENH-199) and ratchets the cluster against regression.

The page makes the 9 AML/Compliance arc engines operator-driveable from
the browser through 7 thematic tabs grouping engines per workflow logic.

The companion FastAPI router `utils/api_compliance.py` exposes the same
engine methods over JSON for the planned React frontend. Cockpit and API
share the engine layer as the source of truth — same pattern as Treasury
v10.155.

DESIGN DISCIPLINE (carried forward from v10.155 Treasury closure)
-----------------------------------------------------------------
1. Streamlit/import fallback at top so module loads even when Streamlit
   isn't installed (sandbox-friendly)
2. require_access uses REAL signature: require_access(module: str,
   silent: bool = False). Module ID is "compliance" — the AML/Compliance
   role group (Admin, Compliance Officer, Head of Compliance, MLRO).
3. audit_log uses REAL signature: action, username, detail, module
4. @st.cache_resource caches engine instances at session level
5. Read-only display except for state-mutating buttons that go through
   the explicit FastAPI POST endpoints in utils/api_compliance.py

7 THEMATIC TAB STRUCTURE (G4 7-tab limit)
-----------------------------------------
1. 📊 Dashboard      — cross-engine board pack + enterprise risk score
2. 👤 KYC + Screening — KycOnboardingEngine + ScreeningOrchestrator
3. 🚨 AML Monitoring  — AmlMonitoringEngine alerts + escalations
4. 📋 SAR Filings     — SarFilingEngine lifecycle + POCAMLA deadlines
5. 📊 Risk Assessment — ComplianceRiskAssessmentEngine 5-dim scorecard
6. 📑 Reg + Policy    — RegulatoryChangeEngine + PolicyManagementEngine
7. 🎓 Training        — ComplianceTrainingEngine + ExaminerReportingEngine

This grouping reflects operational adjacency and KEEPS examiner_reporting
co-located with training because both produce regulator-facing artifacts.
The 9 engines fit into 7 tabs without skipping any surface.
"""
from __future__ import annotations
from datetime import datetime, timezone

try:
    import streamlit as st
    import pandas as pd
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None  # type: ignore
    pd = None  # type: ignore

# Engines — 9 AML/Compliance arc + screening_orchestrator from prior session
from utils.kyc_onboarding import KycOnboardingEngine
from utils.aml_monitoring import AmlMonitoringEngine
from utils.sar_filing import SarFilingEngine
from utils.compliance_risk_assessment import (
    ComplianceRiskAssessmentEngine)
from utils.examiner_reporting import ExaminerReportingEngine
from utils.regulatory_change import RegulatoryChangeEngine
from utils.policy_management import PolicyManagementEngine
from utils.compliance_training import ComplianceTrainingEngine

try:
    from utils.screening_orchestrator import ScreeningOrchestrator
    SCREENING_AVAILABLE = True
except ImportError:
    SCREENING_AVAILABLE = False
    ScreeningOrchestrator = None  # type: ignore

try:
    from pages._shared import load_shared_state
    from pages._access import require_access
    from utils.core_audit import audit_log
    SHARED_AVAILABLE = True
except ImportError:
    SHARED_AVAILABLE = False
    def load_shared_state():
        return {}
    def require_access(module: str, silent: bool = False):
        return True
    def audit_log(action: str, username: str, detail: str = "",
                    module: str = "", before: str = "",
                    after: str = ""):
        pass

try:
    from pages._cockpit_render import render_summary as _render_summary
except ImportError:
    def _render_summary(summary, *, exclude=()):
        if STREAMLIT_AVAILABLE:
            _render_summary(summary)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

if STREAMLIT_AVAILABLE:
    st.set_page_config(
        page_title="Compliance Arc Cockpit",
        page_icon="🛡️",
        layout="wide")

    if SHARED_AVAILABLE:
        load_shared_state()
        require_access("compliance")

    st.title("🛡️ AML/Compliance Arc Cockpit")
    st.caption(
        "v10.169 closure — 9 engines (ENH-191..ENH-199) spanning KYC/KYB "
        "onboarding, PEP/sanctions screening, AML transaction monitoring, "
        "SAR/STR filing, enterprise compliance risk assessment, examiner-"
        "ready reporting, regulatory change management, policy management "
        "& attestation, and compliance training. All engines read-only "
        "in this view; state-mutating workflows (register customer, "
        "build SAR filing, transition policy, record attestation) go "
        "through the explicit FastAPI POST endpoints in utils/"
        "api_compliance.py with audit-trailed Pydantic validation.")

    # Engine instances cached at session level
    @st.cache_resource
    def _get_engines():
        kyc = KycOnboardingEngine()
        aml = AmlMonitoringEngine()
        sar = SarFilingEngine()
        risk = ComplianceRiskAssessmentEngine()
        examiner = ExaminerReportingEngine()
        reg_change = RegulatoryChangeEngine()
        policy = PolicyManagementEngine()
        training = ComplianceTrainingEngine()
        screening = (ScreeningOrchestrator()
                     if SCREENING_AVAILABLE else None)
        return {
            "kyc": kyc, "aml": aml, "sar": sar, "risk": risk,
            "examiner": examiner, "reg_change": reg_change,
            "policy": policy, "training": training,
            "screening": screening,
        }

    engines = _get_engines()

    # ----------------------------------------------------------------
    # 7 thematic tabs grouping the 9 engines
    # ----------------------------------------------------------------

    tabs = st.tabs([
        "📊 Dashboard",
        "👤 KYC + Screening",
        "🚨 AML Monitoring",
        "📋 SAR Filings",
        "📊 Risk Assessment",
        "📑 Reg + Policy",
        "🎓 Training + Examiner",
    ])

    # ----------------------------------------------------------------
    # Tab 1 — Dashboard
    # ----------------------------------------------------------------
    with tabs[0]:
        st.subheader("Cross-engine compliance posture")
        st.caption(
            "Single view rolling up all 9 engines. The headline number "
            "is the enterprise compliance risk score from ENH-198.")

        # Run an assessment if none exists yet
        if engines["risk"].latest_assessment() is None:
            with st.spinner("Running enterprise compliance risk assessment..."):
                engines["risk"].assess(
                    kyc_engine=engines["kyc"],
                    aml_engine=engines["aml"],
                    sar_engine=engines["sar"])

        latest = engines["risk"].latest_assessment()
        if latest is not None:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Risk Score", f"{latest.total_score} / 100")
            col2.metric("Risk Band", latest.risk_band.value)
            col3.metric("Customers", latest.n_customers)
            col4.metric("Critical Alerts", latest.n_critical_alerts)

        st.markdown("---")
        st.markdown("### Module-by-module health")
        engine_summaries = [
            ("ENH-191 KYC/KYB", engines["kyc"]),
            ("ENH-193 AML Monitoring", engines["aml"]),
            ("ENH-194 SAR Filing", engines["sar"]),
            ("ENH-198 Compliance Risk", engines["risk"]),
            ("ENH-199 Examiner Reporting", engines["examiner"]),
            ("ENH-195 Regulatory Change", engines["reg_change"]),
            ("ENH-196 Policy Management", engines["policy"]),
            ("ENH-197 Training", engines["training"]),
        ]
        for label, eng in engine_summaries:
            with st.expander(f"{label} — {eng.board_summary().get('engine', '')}"):
                _render_summary(eng.board_summary())

        if SHARED_AVAILABLE:
            audit_log(action="compliance.cockpit.dashboard.viewed",
                          username=st.session_state.get(
                              "username", "system"),
                          module="compliance")

    # ----------------------------------------------------------------
    # Tab 2 — KYC + Screening
    # ----------------------------------------------------------------
    with tabs[1]:
        st.subheader("👤 KYC/KYB Onboarding + PEP/Sanctions Screening")
        st.caption("ENH-191 KycOnboardingEngine + ENH-192 ScreeningOrchestrator")
        kyc_summary = engines["kyc"].board_summary()
        col1, col2, col3 = st.columns(3)
        col1.metric("KYC decisions", kyc_summary.get("n_kyc", 0))
        col2.metric("KYB decisions", kyc_summary.get("n_kyb", 0))
        col3.metric("Tier counts", str(kyc_summary.get(
            "tier_counts", {})))

        with st.expander("KYC engine board"):
            _render_summary(kyc_summary)

        if engines["screening"] is not None:
            st.markdown("---")
            st.markdown("### PEP/Sanctions Screening")
            with st.expander("Screening engine board"):
                try:
                    _render_summary(engines["screening"].board_summary())
                except Exception as e:
                    st.warning(
                        f"Screening engine present but board_summary "
                        f"failed: {type(e).__name__}: {e}")
        else:
            st.info("ScreeningOrchestrator not available in this build")

    # ----------------------------------------------------------------
    # Tab 3 — AML Monitoring
    # ----------------------------------------------------------------
    with tabs[2]:
        st.subheader("🚨 AML Transaction Monitoring")
        st.caption(
            "ENH-193 AmlMonitoringEngine — orchestrates Standard #59 "
            "TransactionMonitoringEngine with tier-aware severity "
            "escalation and sanctions auto-critical")
        aml_summary = engines["aml"].board_summary()
        col1, col2, col3 = st.columns(3)
        col1.metric("Customers monitored",
                       aml_summary.get("n_customers_monitored", 0))
        col2.metric("Total alerts",
                       aml_summary.get("n_total_alerts", 0))
        col3.metric("Critical alerts",
                       aml_summary.get("n_total_critical_alerts", 0))

        with st.expander("Outcome distribution"):
            _render_summary(aml_summary.get("outcome_counts", {}))
        with st.expander("ML layer status (honest deferral)"):
            st.text(aml_summary.get("ml_layer_status", ""))
        with st.expander("Full board"):
            _render_summary(aml_summary)

    # ----------------------------------------------------------------
    # Tab 4 — SAR Filings
    # ----------------------------------------------------------------
    with tabs[3]:
        st.subheader("📋 SAR/STR Filings — POCAMLA §44 Compliance")
        st.caption("ENH-194 SarFilingEngine — 7-day filing deadline")
        sar_summary = engines["sar"].board_summary()
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total filings",
                       sar_summary.get("n_filings_total", 0))
        col2.metric("Submitted",
                       sar_summary.get("n_submitted", 0))
        col3.metric("Under investigation",
                       sar_summary.get("n_under_investigation", 0))
        n_overdue = sar_summary.get("n_overdue_drafts", 0)
        col4.metric("⚠ Overdue drafts", n_overdue,
                       delta=f"-{n_overdue}" if n_overdue > 0
                       else "0",
                       delta_color="inverse")

        if n_overdue > 0:
            st.error(
                f"⚠ {n_overdue} DRAFT filings past POCAMLA §44 7-day "
                f"deadline — DIRECT REGULATORY EXPOSURE.")

        with st.expander("Submission method (honest deferral)"):
            st.text(sar_summary.get("submission_method", ""))
        with st.expander("Full board"):
            _render_summary(sar_summary)

    # ----------------------------------------------------------------
    # Tab 5 — Risk Assessment
    # ----------------------------------------------------------------
    with tabs[4]:
        st.subheader("📊 Enterprise Compliance Risk Assessment")
        st.caption(
            "ENH-198 ComplianceRiskAssessmentEngine — 5-dimension "
            "scorecard rolling up KYC + AML + SAR engines into one "
            "headline number")

        latest = engines["risk"].latest_assessment()
        if latest is None:
            st.info("No assessment yet. Use Dashboard tab to run one.")
        else:
            col1, col2, col3 = st.columns(3)
            col1.metric("Total score", f"{latest.total_score} / 100")
            col2.metric("Risk band", latest.risk_band.value)
            col3.metric("Contradictions",
                          len(latest.contradictions))

            st.markdown("### 5-dimension breakdown")
            for c in latest.components:
                with st.expander(
                        f"{c.dimension}: {c.points} pts (raw="
                        f"{c.raw_value}, cap={c.cap})"):
                    st.markdown("**Contributing factors:**")
                    for f in c.contributing_factors:
                        st.markdown(f"- {f}")

            if latest.contradictions:
                st.warning(
                    f"⚠ {len(latest.contradictions)} cross-cluster "
                    "contradictions surfaced")
                for ct in latest.contradictions:
                    st.markdown(f"- {ct}")

            with st.expander("Honest deferrals"):
                st.markdown(
                    f"**Trend analysis:** {latest.trend_analysis_status}")
                st.markdown(
                    f"**Industry concentration:** "
                    f"{latest.industry_concentration_status}")
                st.markdown(
                    f"**ML predictive:** {latest.ml_predictive_status}")

    # ----------------------------------------------------------------
    # Tab 6 — Reg + Policy
    # ----------------------------------------------------------------
    with tabs[5]:
        st.subheader("📑 Regulatory Change + Policy Management")
        st.caption(
            "ENH-195 RegulatoryChangeEngine (inbound) + "
            "ENH-196 PolicyManagementEngine (institution policies). "
            "policies_for_change() reverse-lookup completes the "
            "bidirectional linkage.")

        reg_summary = engines["reg_change"].board_summary()
        pol_summary = engines["policy"].board_summary()

        st.markdown("### Regulatory Changes")
        col1, col2, col3 = st.columns(3)
        col1.metric("Total changes",
                       reg_summary.get("n_changes_total", 0))
        col2.metric("Critical open",
                       reg_summary.get("n_critical_open", 0))
        col3.metric("Overdue attestations",
                       reg_summary.get("n_overdue_attestations", 0))

        with st.expander("Sources + severities"):
            _render_summary({
                "by_source": reg_summary.get("source_counts", {}),
                "by_severity": reg_summary.get("severity_counts", {}),
                "by_status": reg_summary.get("status_counts", {}),
            })
        with st.expander("Honest deferrals"):
            st.text(reg_summary.get("automated_feed_status", ""))

        st.markdown("---")
        st.markdown("### Policies")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Unique policies",
                       pol_summary.get("n_unique_policies", 0))
        col2.metric("Total versions",
                       pol_summary.get("n_total_versions", 0))
        col3.metric("Active",
                       pol_summary.get("n_active_versions", 0))
        col4.metric("⚠ Overdue attestations",
                       pol_summary.get(
                           "n_overdue_attestations", 0))

        with st.expander("Honest deferrals"):
            st.text(pol_summary.get("document_storage_status", ""))
            st.text(pol_summary.get(
                "esignature_verification_status", ""))

    # ----------------------------------------------------------------
    # Tab 7 — Training + Examiner
    # ----------------------------------------------------------------
    with tabs[6]:
        st.subheader("🎓 Compliance Training + Examiner-Ready Reporting")
        st.caption(
            "ENH-197 ComplianceTrainingEngine (course catalogue + "
            "assignments + certifications) + ENH-199 "
            "ExaminerReportingEngine (FFIEC examination packages)")

        tr_summary = engines["training"].board_summary()
        st.markdown("### Compliance Training")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Courses published",
                       tr_summary.get("n_courses_published", 0))
        col2.metric("Active certifications",
                       tr_summary.get(
                           "n_active_certifications", 0))
        col3.metric("⚠ Overdue assignments",
                       tr_summary.get(
                           "n_assignments_overdue", 0))
        col4.metric("⚠ Expiring certs (30d)",
                       tr_summary.get(
                           "n_certifications_expiring_30d", 0))

        with st.expander("Honest deferrals"):
            st.text(tr_summary.get("lms_integration_status", ""))
            st.text(tr_summary.get("course_content_status", ""))

        st.markdown("---")
        st.markdown("### Examiner Reporting")
        ex_summary = engines["examiner"].board_summary()
        st.metric("Examination packages built",
                       ex_summary.get("n_packages", 0))
        with st.expander("Latest package health"):
            if "latest_health" in ex_summary:
                _render_summary(ex_summary["latest_health"])
            else:
                st.info(
                    "No examination packages built yet. The package "
                    "build flow becomes available in the next "
                    "increment when POST endpoints ship.")
        with st.expander("Export format (honest deferral)"):
            st.text(ex_summary.get("export_format_status", ""))


# ---------------------------------------------------------------------------
# Page audit footer
# ---------------------------------------------------------------------------

if STREAMLIT_AVAILABLE and SHARED_AVAILABLE:
    audit_log(
        action="compliance.cockpit.viewed",
        username=st.session_state.get("username", "system"),
        module="compliance",
        detail=(f"viewed v10.169 cockpit at "
                  f"{datetime.now(timezone.utc).isoformat()}"))
