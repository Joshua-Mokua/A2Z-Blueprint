"""
Phase 2B — Compliance Dashboard & KPIs (pages/103)
=================================================================
v10.288 — covers Standard #200 (Compliance Dashboard & KPIs).

Audience: CCO, MD, audit committee, board, examiners (read-only).

Read-side composition over CMS suite (#191–#200) — KYC, KYB, AML,
sanctions, SAR, regulatory change, policy, training, risk assessment,
examiner portal. The dashboard never modifies upstream engines; it
catalogues what each one currently reports and surfaces breaches.

Tab map (7 tabs; G4 ceiling, planned upfront):
  1. KPI definitions          — register + state transitions
  2. KPI observations         — record observed values + severity
  3. Executive views          — board pack / audit committee / CCO
  4. Per-framework summary    — CBK / DPA Kenya / POCAMLA / Basel / ISO
  5. Breach log               — RED + CRITICAL across all frameworks
  6. Drill-down by domain     — filter observations by KPI_DOMAINS
  7. Metrics                  — counts + trend at the dashboard level
"""

from __future__ import annotations

import streamlit as st

from utils.core_audit import audit_log
from utils.compliance_dashboard import (
    ComplianceDashboardEngine,
    KPI_DOMAINS, KPI_FREQUENCIES, KPI_STATES,
    KPI_BREACH_SEVERITIES, EXECUTIVE_VIEW_TYPES,
    REGULATORY_FRAMEWORKS,
    DEFAULT_KPI_REFRESH_HOURS, DEFAULT_BREACH_ESCALATION_HOURS,
    CBK_PRUDENTIAL_REFERENCE, DPA_KENYA_REFERENCE, AML_REFERENCE,
)

try:
    from pages._access import require_access
    require_access("compliance_regulatory.compliance_dashboard")
except Exception:
    pass


@st.cache_resource
def _engine():
    return ComplianceDashboardEngine()


def main():
    st.title("⚖️ Compliance Dashboard & KPIs")
    st.caption(
        f"v10.288 · Standard #200 · Read-side composition over the CMS "
        f"suite (#191–#200). Refresh: "
        f"{DEFAULT_KPI_REFRESH_HOURS}h · Breach escalation: "
        f"{DEFAULT_BREACH_ESCALATION_HOURS}h. Frameworks: "
        f"{CBK_PRUDENTIAL_REFERENCE} · {DPA_KENYA_REFERENCE} · "
        f"{AML_REFERENCE}."
    )

    eng = _engine()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "📋 KPI definitions",
        "📊 Observations",
        "🧑‍💼 Executive views",
        "🌐 Per-framework summary",
        "🚨 Breach log",
        "🔍 Drill-down by domain",
        "📈 Metrics",
    ])

    # ---------- Tab 1: KPI definitions ----------
    with tabs[0]:
        st.subheader("KPI definitions (Standard #200)")
        st.caption(
            f"Domains: {', '.join(KPI_DOMAINS)} · "
            f"Frequencies: {', '.join(KPI_FREQUENCIES)} · "
            f"Frameworks: {', '.join(REGULATORY_FRAMEWORKS)}",
        )
        with st.form("kpi_def_form"):
            kid = st.text_input("KPI ID")
            kname = st.text_input("Name")
            kdom = st.selectbox("Domain", KPI_DOMAINS)
            kfreq = st.selectbox("Frequency", KPI_FREQUENCIES)
            kfwk = st.selectbox("Framework", REGULATORY_FRAMEWORKS)
            kamber = st.text_input("Amber threshold")
            kred = st.text_input("Red threshold")
            kreason = st.text_input("Registration reason")
            if st.form_submit_button("Register KPI"):
                res = eng.register_kpi_definition(
                    {"kpi_id": kid, "name": kname,
                     "domain": kdom, "frequency": kfreq,
                     "framework": kfwk,
                     "amber_threshold": kamber,
                     "red_threshold": kred},
                    actor=actor, reason=kreason,
                )
                audit_log(
                    action="register_compliance_kpi",
                    username=actor,
                    module="compliance_dashboard",
                )
                if res.get("registered"):
                    st.success(f"KPI {kid} registered (ACTIVE)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition KPI state"):
            with st.form("kpi_state_form"):
                tid = st.text_input("KPI ID", key="kpi_st_id")
                ns = st.selectbox("New state", KPI_STATES)
                tre = st.text_input("Reason", key="kpi_st_reason")
                if st.form_submit_button("Transition"):
                    res = eng.transition_kpi_state(
                        tid, ns, actor=actor, reason=tre,
                    )
                    audit_log(
                        action="transition_compliance_kpi_state",
                        username=actor,
                        module="compliance_dashboard",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 2: Observations ----------
    with tabs[1]:
        st.subheader("KPI observations")
        st.caption(
            f"Severities: {', '.join(KPI_BREACH_SEVERITIES)}. "
            f"Each observation is read-only after recording.",
        )
        with st.form("obs_form"):
            oid = st.text_input("Observation ID")
            okid = st.text_input("KPI ID", key="obs_kid")
            oval = st.text_input("Observed value")
            osev = st.selectbox("Severity", KPI_BREACH_SEVERITIES)
            onarr = st.text_area("Narrative")
            if st.form_submit_button("Record observation"):
                res = eng.record_kpi_observation(
                    {"observation_id": oid,
                     "kpi_id": okid,
                     "observed_value": oval,
                     "severity": osev,
                     "narrative": onarr},
                    actor=actor,
                )
                audit_log(
                    action="record_compliance_kpi_observation",
                    username=actor,
                    module="compliance_dashboard",
                )
                if res.get("recorded"):
                    st.success(f"Observation {oid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 3: Executive views ----------
    with tabs[2]:
        st.subheader("Executive views")
        st.caption(
            f"View types: {', '.join(EXECUTIVE_VIEW_TYPES)}. "
            f"Curated KPI bundles for board pack, audit committee, "
            f"CCO dashboard, regulator briefing, internal review.",
        )
        with st.form("view_form"):
            vid = st.text_input("View ID")
            vtype = st.selectbox(
                "View type", EXECUTIVE_VIEW_TYPES,
            )
            vtitle = st.text_input("Title")
            vkpis = st.text_input(
                "KPI IDs (comma-separated)",
            )
            vaud = st.text_input("Audience")
            vreason = st.text_input("Reason", key="view_reason")
            if st.form_submit_button("Register view"):
                kpi_list = [
                    k.strip() for k in vkpis.split(",")
                    if k.strip()
                ]
                res = eng.register_executive_view(
                    {"view_id": vid, "view_type": vtype,
                     "title": vtitle, "kpi_ids": kpi_list,
                     "audience": vaud},
                    actor=actor, reason=vreason,
                )
                audit_log(
                    action="register_executive_view",
                    username=actor,
                    module="compliance_dashboard",
                )
                if res.get("registered"):
                    st.success(f"View {vid} registered")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 4: Per-framework summary ----------
    with tabs[3]:
        st.subheader("Per-framework summary")
        st.caption(
            f"Aggregates across active KPIs. Frameworks: "
            f"{', '.join(REGULATORY_FRAMEWORKS)}.",
        )
        cols = st.columns(2)
        fwk = cols[0].selectbox(
            "Framework",
            ["ALL", *REGULATORY_FRAMEWORKS],
            key="fwk_select",
        )
        days = cols[1].number_input(
            "Window (days)", min_value=1, value=30,
            key="fwk_days",
        )
        if st.button("Compute summary"):
            framework_arg = None if fwk == "ALL" else fwk
            s = eng.compliance_summary(
                framework=framework_arg, days=int(days),
            )
            if "error" in s:
                st.error(s["error"])
            else:
                metrics = st.columns(4)
                metrics[0].metric(
                    "Active KPIs", s["active_kpi_count"],
                )
                metrics[1].metric(
                    "Observations", s["observations_in_window"],
                )
                metrics[2].metric(
                    "RED + CRITICAL",
                    s["red_or_critical_count"],
                )
                metrics[3].metric(
                    "KPIs with data",
                    s["latest_per_kpi_count"],
                )
                if s["per_severity"]:
                    st.markdown("**By severity:**")
                    for sev, n in s["per_severity"].items():
                        st.write(f"• `{sev}`: {n}")
                if s["per_domain"]:
                    st.markdown("**By domain:**")
                    for d, n in s["per_domain"].items():
                        st.write(f"• `{d}`: {n}")

    # ---------- Tab 5: Breach log ----------
    with tabs[4]:
        st.subheader("Breach log (RED + CRITICAL)")
        st.caption(
            "Default lists every RED and CRITICAL observation. "
            "Filter to a single severity to narrow the view.",
        )
        sev_filter = st.selectbox(
            "Severity filter",
            ["RED + CRITICAL (default)", *KPI_BREACH_SEVERITIES],
            key="breach_sev",
        )
        if st.button("Show breach log"):
            sev_arg = (
                None if sev_filter == "RED + CRITICAL (default)"
                else sev_filter
            )
            breaches = eng.kpi_breach_log(severity=sev_arg)
            st.metric("Breaches found", len(breaches))
            for b in breaches[:25]:
                st.write(
                    f"• `{b.get('observation_id')}` "
                    f"({b.get('severity')}) — KPI "
                    f"{b.get('kpi_id')}: "
                    f"observed {b.get('observed_value')} "
                    f"at {b.get('observed_at', '')[:19]}",
                )
                if b.get("narrative"):
                    st.caption(f"   {b['narrative']}")

    # ---------- Tab 6: Drill-down by domain ----------
    with tabs[5]:
        st.subheader("Drill-down by domain")
        st.caption(
            "Inspect observations for a single KPI domain. "
            "Useful for the CCO when preparing the board pack.",
        )
        dom_filter = st.selectbox(
            "Domain", KPI_DOMAINS, key="drill_dom",
        )
        if st.button("Drill down"):
            # Compose: filter all observations by KPIs in this domain.
            # The engine doesn't have a per-domain method (would
            # bloat the API); compose at the cockpit instead.
            try:
                from utils.db import db as _db
                kpis = _db.dual_load(
                    eng.kpis_path,
                    table="compliance_kpis",
                    index_cols=("kpi_id",),
                ) or []
                obs = _db.dual_load(
                    eng.observations_path,
                    table="compliance_kpi_observations",
                    index_cols=("observation_id",),
                ) or []
            except Exception:
                kpis, obs = [], []

            domain_kpi_ids = {
                k.get("kpi_id") for k in kpis
                if k.get("domain") == dom_filter
            }
            scoped = [
                o for o in obs
                if o.get("kpi_id") in domain_kpi_ids
            ]
            cols = st.columns(3)
            cols[0].metric(
                f"KPIs in {dom_filter}",
                len(domain_kpi_ids),
            )
            cols[1].metric("Observations", len(scoped))
            red_count = sum(
                1 for o in scoped
                if o.get("severity") in ("RED", "CRITICAL")
            )
            cols[2].metric("RED + CRITICAL", red_count)
            for o in scoped[:15]:
                st.write(
                    f"• `{o.get('kpi_id')}` "
                    f"({o.get('severity')}) — "
                    f"{o.get('observed_value')} at "
                    f"{o.get('observed_at', '')[:19]}",
                )

    # ---------- Tab 7: Metrics ----------
    with tabs[6]:
        st.subheader("Dashboard-level metrics")
        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="metrics_days",
        )
        if st.button("Refresh metrics"):
            s = eng.compliance_summary(days=int(ndays))
            cols = st.columns(4)
            cols[0].metric(
                "Active KPIs (all frameworks)",
                s["active_kpi_count"],
            )
            cols[1].metric(
                "Observations recorded",
                s["observations_in_window"],
            )
            cols[2].metric(
                "RED + CRITICAL",
                s["red_or_critical_count"],
            )
            cols[3].metric(
                "Coverage",
                (
                    f"{s['latest_per_kpi_count']}/"
                    f"{s['active_kpi_count']}"
                    if s["active_kpi_count"]
                    else "0/0"
                ),
            )

            if s["active_kpi_count"] and s["latest_per_kpi_count"]:
                cov = round(
                    100 *
                    s["latest_per_kpi_count"] /
                    s["active_kpi_count"], 1,
                )
                if cov < 80:
                    st.warning(
                        f"Coverage at {cov}% — some active KPIs "
                        f"have no observation in the window. "
                        f"Review refresh schedules.",
                    )


main()
