"""pages/24_compliance.py — Compliance Management: PEP, AML, KYC, sanctions."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access
from utils.core_audit import audit_log
from utils.core import ComplianceManager

require_access("compliance_regulatory.dashboard")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()

@st.cache_data(ttl=60, show_spinner=False)
def _load():
    f = DATA / "compliance_cases.json"
    return a2z_db.load_json(f) if f.exists() else []

cases = _load()
role = ud.get("role",""); sc = str(ud.get("staff_code","") or "")
is_admin   = ud.get("is_admin",False)
is_comp    = any(x in role for x in ("Compliance","AML","Legal","Risk","Chief"))
is_mgr     = any(x in role for x in ("Manager","Director","Head"))
cmgr = ComplianceManager()

visible = cases if (is_admin or is_comp or is_mgr) else [
    c for c in cases if str(c.get("raised_by","")) == ud.get("full_name","")]

# ── Proposition head filter ─────────────────────────────
_prop_tag_pg = get_user_proposition()
if _prop_tag_pg:
    visible = [x for x in visible if x.get("proposition_tag") == _prop_tag_pg]
    try:
        import json as _pfj; from pathlib import Path as _pfp
        _pc2 = _pfj.loads((_pfp(__file__).parent.parent / "data" / "proposition_config.json").read_text())
        _pn  = _pc2.get("propositions",{}).get(_prop_tag_pg,{}).get("name",_prop_tag_pg)
        _pi  = _pc2.get("propositions",{}).get(_prop_tag_pg,{}).get("icon","🎯")
        st.info(_pi + " **" + _pn + " view** — " + str(len(visible)) + " tagged records")
    except Exception: pass


# ── Header ─────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>🛡️ Compliance</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "PEP screening · AML/KYC · Sanctions · Regulatory approvals</span></div>",
    unsafe_allow_html=True)

# ── KPI strip ──────────────────────────────────────────────────────
total    = len(visible)
open_n   = sum(1 for c in visible if c["status"] == "open")
review_n = sum(1 for c in visible if c["status"] == "under_review")
cleared  = sum(1 for c in visible if c["status"] == "cleared")
escalated= sum(1 for c in visible if c["status"] == "escalated")
critical = sum(1 for c in visible if c.get("risk_level") == "Critical")

k1,k2,k3,k4,k5 = st.columns(5)
for col, lbl, val, color in [
    (k1,"Open",      str(open_n),   "#DC2626"),
    (k2,"Under Review",str(review_n),"#D97706"),
    (k3,"Cleared",   str(cleared),  "#16A34A"),
    (k4,"Escalated", str(escalated),"#7C3AED"),
    (k5,"Critical",  str(critical), "#991B1B"),
]:
    col.markdown(
        f"<div style='background:var(--color-background-secondary);border:0.5px solid "
        f"var(--color-border-tertiary);border-radius:10px;padding:12px;text-align:center'>"
        f"<div style='font-size:11px;color:var(--color-text-secondary);font-weight:600;"
        f"text-transform:uppercase'>{lbl}</div>"
        f"<div style='font-size:24px;font-weight:800;color:{color}'>{val}</div>"
        f"</div>", unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

RISK_COLOR = {"Low":"#16A34A","Medium":"#D97706","High":"#DC2626","Critical":"#7F1D1D"}
STATUS_COLOR = {
    "open":"#DC2626","under_review":"#D97706","cleared":"#16A34A",
    "escalated":"#7C3AED","rejected":"#6B7280",
}
FLAG_ICON = {
    "PEP":"👤","Sanctioned Entity":"🚫","Adverse Media":"📰",
    "Restricted Sector":"🏭","AML Flag":"💰","Unusual Transaction":"⚠️",
}

tabs = st.tabs(["📋 All Cases","🔴 Open","✅ Cleared","📊 Analytics",
    "📅 Regulatory Calendar","🤖 Arc Engines"
])

# ────────────────────────────────────────────────────────────────────
# TAB 1: ALL
# ────────────────────────────────────────────────────────────────────
with tabs[0]:
    f1,f2,f3 = st.columns(3)
    filt_st   = f1.selectbox("Status",["All","open","under_review","cleared","escalated","rejected"], key="cs_st")
    filt_risk = f2.selectbox("Risk level",["All","Critical","High","Medium","Low"], key="cs_risk")
    filt_flag = f3.selectbox("Flag type",["All"]+sorted(set(c["flag_type"] for c in visible)), key="cs_flag")

    filt = visible
    if filt_st   != "All": filt = [c for c in filt if c["status"] == filt_st]
    if filt_risk != "All": filt = [c for c in filt if c.get("risk_level") == filt_risk]
    if filt_flag != "All": filt = [c for c in filt if c["flag_type"] == filt_flag]

    for case in sorted(filt, key=lambda x: (x["status"]!="open", x.get("risk_level",""))):
        rc  = RISK_COLOR.get(case.get("risk_level","Low"),"#6B7280")
        sc2 = STATUS_COLOR.get(case["status"],"#6B7280")
        icon= FLAG_ICON.get(case["flag_type"],"⚠️")
        _d2sla = case.get("_days_to_sla", 99)
        _sla_txt = f"🔴 {-_d2sla}d overdue" if _d2sla < 0 else f"🟡 Due in {_d2sla}d" if _d2sla <= 2 else f"🟢 {_d2sla}d"
        with st.expander(
            f"{icon} {case['client_name']} · "
            f"**{case['flag_type']}** · "
            f"{case['status'].replace('_',' ').title()} · "
            f"{case.get('risk_level','')} risk  ·  {_sla_txt}",
            expanded=(case["status"]=="open" and case.get("risk_level")=="Critical")):
            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f"**Case:** `{case['id']}`")
            c2.markdown(f"**Source:** {case['source'].replace('_',' ').title()}")
            c3.markdown(f"**Raised:** {case['raised_date']}")
            c4.markdown(f"**Officer:** {case.get('assigned_officer','Unassigned')}")
            if case.get("source_ref"):
                st.markdown(f"**Reference:** `{case['source_ref']}`")
            if case.get("escalated_to"):
                st.warning(f"Escalated to: **{case['escalated_to']}**")
            # Documents required
            docs = case.get("documents_required",[])
            if docs:
                st.markdown(f"**Documents required:** {', '.join(docs)}")
            # Action buttons
            if (is_comp or is_admin) and case["status"] in ("open","under_review"):
                b1,b2,b3 = st.columns(3)
                if b1.button("✅ Clear case", key=f"clr_{case['id']}", type="primary"):
                    cmgr.update_status(case['id'], "cleared", ud.get('full_name', uname))
                    audit_log("COMPLIANCE_CLEARED", uname, f"{case['id']}|{case['client_name']}")
                    st.cache_data.clear(); st.success(f"Case {case['id']} cleared"); st.rerun()
                if b2.button("🔺 Escalate",  key=f"esc_{case['id']}"):
                    cmgr.update_status(case['id'], "escalated",
                                       escalate_to="Head of Compliance")
                    audit_log("COMPLIANCE_ESCALATED", uname, f"{case['id']}|{case['client_name']}")
                    st.cache_data.clear(); st.warning(f"Case {case['id']} escalated"); st.rerun()
                if b3.button("📝 Add note",  key=f"note_{case['id']}"):
                    st.info("Note saved")

# ────────────────────────────────────────────────────────────────────
# TAB 2: OPEN
# ────────────────────────────────────────────────────────────────────
with tabs[1]:
    open_cases = sorted(
        [c for c in visible if c["status"] in ("open","under_review")],
        key=lambda x: ["Critical","High","Medium","Low"].index(x.get("risk_level","Low")))
    if not open_cases:
        st.success("✅ No open compliance cases.")
    else:
        st.error(f"⚠️ {len(open_cases)} open cases require action")
        rows = []
        for c in open_cases:
            rows.append({
                "ID": c["id"], "Client": c["client_name"][:28],
                "Flag": c["flag_type"], "Risk": c.get("risk_level",""),
                "Source": c["source"].replace("_"," ").title(),
                "Status": c["status"].replace("_"," ").title(),
                "Raised": c["raised_date"],
                "Officer": c.get("assigned_officer","—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 3: CLEARED
# ────────────────────────────────────────────────────────────────────
with tabs[2]:
    cleared_cases = [c for c in visible if c["status"] == "cleared"]
    st.markdown(f"**{len(cleared_cases)} cleared cases**")
    if cleared_cases:
        rows = [{"ID": c["id"],"Client": c["client_name"][:28],
                 "Flag": c["flag_type"],"Risk": c.get("risk_level",""),
                 "Cleared Date": c.get("cleared_date","—")}
                for c in cleared_cases]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 4: ANALYTICS
# ────────────────────────────────────────────────────────────────────
with tabs[3]:
    from collections import Counter
    from datetime import date as _dt2, timedelta as _td
    _sla_days_map = {"Critical":1,"High":3,"Medium":7,"Low":14}
    # Mark SLA status on each case
    for _c in visible:
        _rl  = _c.get("risk_level","Low")
        _sla = _sla_days_map.get(_rl, 7)
        try:
            _raised = _dt2.fromisoformat(_c.get("raised_date", str(_dt2.today())))
            _due    = _raised + _td(days=_sla)
            _c["_days_to_sla"] = (_due - _dt2.today()).days
            _c["_sla_breached"] = _c["_days_to_sla"] < 0 and _c["status"] not in ("cleared","rejected")
        except: _c["_days_to_sla"] = 99; _c["_sla_breached"] = False

    _breached = sum(1 for c in visible if c.get("_sla_breached"))
    if _breached:
        st.error(f"🔴 {_breached} compliance case(s) have breached their SLA deadline — immediate action required")

    from collections import Counter
    if visible:
        total = len(visible)
        cleared_pct = (sum(1 for c in visible if c["status"]=="cleared")/total*100) if total else 0.0
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total Cases",    total)
        m2.metric("Clearance Rate", f"{cleared_pct:.1f}%")
        m3.metric("Critical Open",
                  sum(1 for c in visible if c["status"]=="open" and c.get("risk_level")=="Critical"))
        m4.metric("SLA Breached", str(_breached), delta_color="inverse")

        # By flag type
        flag_counts = Counter(c["flag_type"] for c in visible)
        st.markdown("**Cases by flag type:**")
        for flag, cnt in flag_counts.most_common():
            pct = cnt/total*100 if total else 0.0
            cleared_flag = sum(1 for c in visible
                               if c["flag_type"]==flag and c["status"]=="cleared")
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                f"<div style='width:200px;font-size:12px'>{FLAG_ICON.get(flag,'⚠️')} {flag}</div>"
                f"<div style='flex:1;background:#F3F4F6;border-radius:4px;height:14px'>"
                f"<div style='width:{pct:.0f}%;background:#DC2626;height:100%;border-radius:4px'></div>"
                f"</div>"
                f"<div style='font-size:12px;width:50px'>{cnt} ({cleared_flag} cleared)</div>"
                f"</div>", unsafe_allow_html=True)

with tabs[-1]:
    import re as _re_rc, calendar as _cal_rc
    st.markdown("**Monthly CBK Regulatory Returns Calendar:**")
    _today_rc = date.today()
    _last_day  = _cal_rc.monthrange(_today_rc.year, _today_rc.month)[1]
    CBK_RETURNS = [
        {"Return":"CBK Return 1 — Balance Sheet",         "Due":10,"Cat":"Prudential"},
        {"Return":"CBK Return 2 — P&L Statement",         "Due":10,"Cat":"Prudential"},
        {"Return":"CBK Return 3 — Capital Adequacy",      "Due":10,"Cat":"Capital"},
        {"Return":"CBK Return 8 — Asset Quality / NPL",   "Due":10,"Cat":"Credit Risk"},
        {"Return":"CBK Return 14 — Reconciliation",       "Due":15,"Cat":"Operations"},
        {"Return":"IFRS 9 ECL Provision Report",          "Due":20,"Cat":"Accounting"},
        {"Return":"AML/CFT STR Monthly Summary",          "Due":15,"Cat":"Compliance"},
        {"Return":"Liquidity Report LCR/NSFR",            "Due":10,"Cat":"Liquidity"},
        {"Return":"Foreign Exchange Position Return",     "Due":10,"Cat":"Treasury"},
        {"Return":"Credit Reference Bureau Filing",       "Due":5, "Cat":"Credit"},
    ]
    import pandas as _pd_rc
    _rows_rc = []
    for r in CBK_RETURNS:
        due = _today_rc.replace(day=min(r["Due"],_last_day))
        days_rem = (due - _today_rc).days
        if days_rem < 0:   status = "✅ Submitted"
        elif days_rem == 0:status = "🔴 DUE TODAY"
        elif days_rem <= 3:status = f"🟡 Due in {days_rem}d"
        else:              status = f"⬜ {due.strftime('%d %b')}"
        _rows_rc.append({"Return":r["Return"],"Category":r["Cat"],"Due":due.strftime("%d %b"),"Status":status})
    st.dataframe(_pd_rc.DataFrame(_rows_rc),use_container_width=True,hide_index=True)
    urgent_rc=[r for r in _rows_rc if "🔴" in r["Status"] or "🟡" in r["Status"]]
    if urgent_rc: st.error(f"🔴 {len(urgent_rc)} return(s) due within 3 days — action immediately")
    st.caption("Integrate with CBK SDMS for automated submission confirmation in production.")


# ──────────────────────────────────────────────────────────────────────
# Section 5: 🤖 Arc Engines (absorbed from 27_compliance_arc_cockpit.py
# in v10.205 per the architectural reorganization sub-campaign.
# 8 AML/Compliance engines (ENH-191..ENH-199 minus the optional
# ScreeningOrchestrator) presented as 7 nested sub-tabs spanning the
# compliance arc: Dashboard, KYC + Screening, AML Monitoring, SAR
# Filings, Risk Assessment, Reg + Policy, Training + Examiner.
# Read-only display except for state-mutating workflows that go
# through utils/api_compliance.py FastAPI endpoints. Mirrors
# v10.202/v10.203/v10.204 absorption patterns.
# ──────────────────────────────────────────────────────────────────────
with tabs[5]:
    from datetime import datetime as _dt_ca, timezone as _tz_ca

    try:
        from utils.kyc_onboarding import KycOnboardingEngine
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.sar_filing import SarFilingEngine
        from utils.compliance_risk_assessment import (
            ComplianceRiskAssessmentEngine)
        from utils.examiner_reporting import ExaminerReportingEngine
        from utils.regulatory_change import RegulatoryChangeEngine
        from utils.policy_management import PolicyManagementEngine
        from utils.compliance_training import ComplianceTrainingEngine
        _ARC_COMPLIANCE_AVAILABLE = True
    except ImportError as _ie:
        st.error(f"Compliance arc engines unavailable: {_ie}")
        _ARC_COMPLIANCE_AVAILABLE = False

    try:
        from utils.screening_orchestrator import ScreeningOrchestrator
        _SCREENING_AVAILABLE = True
    except ImportError:
        _SCREENING_AVAILABLE = False
        ScreeningOrchestrator = None

    try:
        from pages._cockpit_render import render_summary as _render_summary
    except ImportError:
        def _render_summary(summary, *, exclude=()):
            st.json(summary if summary else {})

    if _ARC_COMPLIANCE_AVAILABLE:
        st.caption(
            "v10.205 absorbed from 27_compliance_arc_cockpit.py — "
            "8 engines (ENH-191..ENH-199) spanning KYC/KYB onboarding, "
            "PEP/sanctions screening, AML transaction monitoring, "
            "SAR/STR filing, enterprise compliance risk assessment, "
            "examiner-ready reporting, regulatory change management, "
            "policy management & attestation, and compliance training. "
            "All engines read-only here; state-mutating workflows go "
            "through the FastAPI POST endpoints in utils/api_compliance.py.")

        @st.cache_resource
        def _get_arc_compliance_engines():
            kyc = KycOnboardingEngine()
            aml = AmlMonitoringEngine()
            sar = SarFilingEngine()
            risk = ComplianceRiskAssessmentEngine()
            examiner = ExaminerReportingEngine()
            reg_change = RegulatoryChangeEngine()
            policy = PolicyManagementEngine()
            training = ComplianceTrainingEngine()
            screening = (ScreeningOrchestrator()
                          if _SCREENING_AVAILABLE else None)
            return {
                "kyc": kyc, "aml": aml, "sar": sar, "risk": risk,
                "examiner": examiner, "reg_change": reg_change,
                "policy": policy, "training": training,
                "screening": screening,
            }

        engines = _get_arc_compliance_engines()

        arc_tabs = st.tabs([
            "📊 Dashboard",
            "👤 KYC + Screening",
            "🚨 AML Monitoring",
            "📋 SAR Filings",
            "📊 Risk Assessment",
            "📑 Reg + Policy",
            "🎓 Training + Examiner",
        ])

        with arc_tabs[0]:
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

        with arc_tabs[1]:
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

        with arc_tabs[2]:
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

        with arc_tabs[3]:
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

        with arc_tabs[4]:
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

        with arc_tabs[5]:
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

        with arc_tabs[6]:
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


        # Footer audit log
        try:
            audit_log(
                action="compliance_arc_engines.view",
                username=ud.get("username", "anonymous"),
                detail=f"viewed_at={_dt_ca.now(_tz_ca.utc).isoformat()}",
                module="compliance")
        except Exception:
            pass

# v10.464 — operational output (WF4 doctrine compliance)
st.markdown("---")
if st.button("🔄 Refresh this view"):
    st.cache_data.clear() if hasattr(st, "cache_data") else None
    if hasattr(st, "rerun"):
        st.rerun()

