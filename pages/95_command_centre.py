"""
Phase 2A — Command Centre Workbench (pages/95)
=================================================================
v10.280 — covers Standards #311-#320 (10 standards across 8 engines)

Tab map (7 tabs covering 10 standards):
  1. Dashboard + Briefing      — #311 + #316
  2. Alert Routing             — #312
  3. Forecasting & What-If     — #313 + #314
  4. NL Query                  — #315
  5. Crisis & Incidents        — #317
  6. Initiatives & BSC         — #318
  7. Comms + Board             — #319 + #320
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from utils.core_audit import audit_log
from utils.command_centre_dashboard import (
    CommandCentreDashboardEngine,
    DASHBOARD_WIDGET_TYPES, WIDGET_PRIORITIES, REFRESH_INTERVALS_SECONDS,
)
from utils.command_centre_alert_routing import (
    CommandCentreAlertRoutingEngine,
    EXEC_ALERT_SEVERITIES, EXEC_ROUTING_TARGETS, ROUTING_RULE_STATES,
)
from utils.command_centre_forecasting import (
    CommandCentreForecastingEngine,
    FORECAST_TARGETS, FORECAST_HORIZONS_PERIODS, FORECAST_MODEL_STATES,
)
from utils.command_centre_nl_query import (
    CommandCentreNLQueryEngine,
    QUERY_INTENT_TYPES, QUERY_FEEDBACK_OUTCOMES,
)
from utils.command_centre_mobile_board import (
    CommandCentreMobileBoardEngine,
    BRIEFING_PACK_STATES, BRIEFING_SECTION_TYPES,
    BOARD_MEETING_STATES, BOARD_VOTE_OUTCOMES,
    BOARD_PAPER_TYPES, ACTION_ITEM_STATES,
)
from utils.command_centre_crisis import (
    CommandCentreCrisisEngine,
    INCIDENT_SEVERITIES, INCIDENT_STATES, PLAYBOOK_TYPES,
    DECISION_TYPES, STAKEHOLDER_TYPES,
)
from utils.command_centre_strategic_initiatives import (
    CommandCentreStrategicInitiativesEngine,
    INITIATIVE_RAG_STATES, INITIATIVE_PHASES,
    MILESTONE_STATES, BSC_PERSPECTIVES,
)
from utils.command_centre_stakeholder_comms import (
    CommandCentreStakeholderCommsEngine,
    STAKEHOLDER_COMM_TYPES, COMM_CHANNELS, COMM_STATES,
    TEMPLATE_STATES, RESPONSE_OUTCOMES,
)

try:
    from pages._access import require_access
    require_access("shared.command_centre")
except Exception:
    pass


@st.cache_resource
def _engines():
    return {
        "dashboard": CommandCentreDashboardEngine(),
        "alerts": CommandCentreAlertRoutingEngine(),
        "forecasting": CommandCentreForecastingEngine(),
        "nlq": CommandCentreNLQueryEngine(),
        "mobile_board": CommandCentreMobileBoardEngine(),
        "crisis": CommandCentreCrisisEngine(),
        "initiatives": CommandCentreStrategicInitiativesEngine(),
        "comms": CommandCentreStakeholderCommsEngine(),
    }


def main():
    st.title("🏛️ Command Centre — Executive Workbench")
    st.caption(
        "v10.280 · Standards #311-#320 · MD/CEO dashboard + briefing · "
        "alerts · forecasting · what-if · NL query · "
        "crisis playbook · initiatives · comms + board portal"
    )
    eng = _engines()

    tabs = st.tabs([
        "📊 Dashboard + Briefing",
        "🚨 Alert Routing",
        "📈 Forecasting & What-If",
        "💬 NL Query",
        "⚠️ Crisis & Incidents",
        "🎯 Initiatives & BSC",
        "🏛️ Comms + Board",
    ])

    # Tab 1: Dashboard (#311) + Mobile Briefing (#316)
    with tabs[0]:
        st.subheader("📊 MD/CEO Dashboard + Mobile Briefing — #311 + #316")
        sub_dash, sub_brief = st.tabs(["Live Dashboard", "Briefing Pack"])

        with sub_dash:
            col1, col2 = st.columns([2, 1])
            with col1:
                role_filter = st.selectbox(
                    "Viewer role",
                    options=list(EXEC_ROUTING_TARGETS) + ["EXECUTIVE"],
                    index=0,
                    key="dash_role",
                )
                snap = eng["dashboard"].dashboard_snapshot(role_filter)
                st.metric("Widgets visible", snap["widget_count"])
                if snap["stale_count"] > 0:
                    st.warning(
                        f"⚠️ {snap['stale_count']} widget(s) showing stale data."
                    )
                for widget in snap["widgets"][:10]:
                    stale_badge = "⚠️ STALE" if widget["stale"] else ""
                    st.markdown(
                        f"**{widget['widget_name']}** [{widget['priority']}] "
                        f"{stale_badge}"
                    )
            with col2:
                with st.expander("➕ Register widget", expanded=False):
                    with st.form("reg_widget"):
                        wid = st.text_input("Widget ID")
                        wname = st.text_input("Widget name")
                        wtype = st.selectbox("Widget type",
                                                  DASHBOARD_WIDGET_TYPES)
                        wprio = st.selectbox("Priority",
                                                  WIDGET_PRIORITIES, index=2)
                        wrefresh = st.selectbox("Refresh seconds",
                                                      REFRESH_INTERVALS_SECONDS,
                                                      index=1)
                        wreason = st.text_input("Reason")
                        if st.form_submit_button("Register"):
                            if all([wid, wname, wreason]):
                                r = eng["dashboard"].register_kpi_widget(
                                    {"widget_id": wid, "widget_name": wname,
                                      "widget_type": wtype,
                                      "priority": wprio,
                                      "refresh_seconds": wrefresh,
                                      "drill_down_dimensions": []},
                                    actor="cdo", reason=wreason,
                                )
                                if r["registered"]:
                                    audit_log(
                                        action="register_kpi_widget",
                                        username="cdo",
                                        module="command_centre",
                                    )
                                    st.success("Widget registered.")
                                    st.rerun()
                                else:
                                    st.error(f"Failed: {r.get('error', '?')}")

        with sub_brief:
            viewer = st.selectbox("Viewer role",
                                       options=list(EXEC_ROUTING_TARGETS),
                                       key="brief_viewer")
            pack_id = st.text_input("Pack ID to fetch",
                                          value="PACK-MD-DAILY")
            if st.button("Fetch pack") and pack_id:
                r = eng["mobile_board"].fetch_pack_for_role(pack_id, viewer)
                if r["available"]:
                    st.success(f"Pack: {r['pack_name']} ({r['as_of_date']})")
                    for s in r["sections"]:
                        st.markdown(f"### {s.get('title', '')}")
                        st.caption(f"_{s.get('section_type', '')}_")
                        if s.get("content"):
                            st.write(s["content"])
                else:
                    st.warning(f"Not available: {r.get('error', '?')}")

    # Tab 2: Alert Routing (#312)
    with tabs[1]:
        st.subheader("🚨 Executive Alert Routing — #312")
        col1, col2 = st.columns([2, 1])
        with col1:
            role = st.selectbox("Executive role",
                                    EXEC_ROUTING_TARGETS,
                                    key="exec_alert_role")
            queue = eng["alerts"].executive_alert_queue(role)
            st.metric(f"{role} alerts (today + history)", len(queue))
            for a in queue[:20]:
                st.markdown(
                    f"**[{a.get('severity')}]** {a.get('alert_type')} "
                    f"_{a.get('source_entity_id', '')}_ "
                    f"<small>at {a.get('routed_at', '')[:16]}</small>",
                    unsafe_allow_html=True,
                )
        with col2:
            with st.expander("➕ Register routing rule", expanded=False):
                with st.form("reg_rule"):
                    rid = st.text_input("Rule ID")
                    rname = st.text_input("Rule name")
                    rmin = st.selectbox("Min severity",
                                              EXEC_ALERT_SEVERITIES, index=1)
                    rtargets = st.multiselect("Target roles",
                                                    EXEC_ROUTING_TARGETS,
                                                    default=["MD"])
                    rreason = st.text_input("Reason", key="rule_reason")
                    if st.form_submit_button("Register"):
                        if all([rid, rname, rtargets, rreason]):
                            r = eng["alerts"].register_routing_rule(
                                {"rule_id": rid, "rule_name": rname,
                                  "min_severity": rmin,
                                  "target_roles": rtargets},
                                actor="cdo", reason=rreason,
                            )
                            if r["registered"]:
                                audit_log(
                                    action="register_routing_rule",
                                    username="cdo",
                                    module="command_centre",
                                )
                                st.success("Rule registered.")
                                st.rerun()
                            else:
                                st.error(f"Failed: {r.get('error', '?')}")

    # Tab 3: Forecasting + What-If (#313 + #314)
    with tabs[2]:
        st.subheader("📈 Forecasting & What-If — #313 + #314")
        st.caption(
            "Driver-based forecasting with 80% confidence bands. "
            "What-if shocks → tornado sensitivity."
        )
        with st.expander("➕ Register model", expanded=False):
            with st.form("reg_model"):
                mid = st.text_input("Model ID")
                mname = st.text_input("Model name")
                mtarget = st.selectbox("Target", FORECAST_TARGETS)
                mbase = st.text_input("Baseline value", value="1000000")
                mgrowth = st.text_input("Baseline growth %", value="3")
                mreason = st.text_input("Reason", key="model_reason")
                if st.form_submit_button("Register"):
                    if all([mid, mname, mbase, mreason]):
                        r = eng["forecasting"].register_forecast_model(
                            {"model_id": mid, "model_name": mname,
                              "target": mtarget,
                              "baseline_value": mbase,
                              "baseline_growth_pct": mgrowth,
                              "driver_weights": {
                                  "macro_growth": "1.5",
                                  "interest_rate": "1.2",
                                  "default_rate": "-2.0",
                              }},
                            actor="cfo", reason=mreason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_forecast_model",
                                username="cfo",
                                module="command_centre",
                            )
                            st.success("Model registered (DRAFT).")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")
        st.info(
            "💡 Models register in DRAFT. Tornado sensitivity is a "
            "per-driver shock analysis showing largest-impact drivers first."
        )

    # Tab 4: NL Query (#315)
    with tabs[3]:
        st.subheader("💬 Natural-Language Query — #315")
        nlq_query = st.text_input(
            "Your question",
            placeholder="show NPL trend by segment last quarter",
        )
        nlq_role = st.selectbox("Asking as",
                                       options=list(EXEC_ROUTING_TARGETS),
                                       key="nlq_role")
        if st.button("Submit query") and nlq_query:
            r = eng["nlq"].submit_query(nlq_query, nlq_role)
            if r["submitted"]:
                audit_log(
                    action="submit_nl_query",
                    username=nlq_role,
                    module="command_centre",
                )
                st.success(f"Intent detected: {r['intent']}")
                st.metric("Confidence", f"{r['confidence_pct']}%")
                st.write(r["answer"])
                if r.get("structured_query"):
                    st.code(r["structured_query"], language="sql")
                if r["fallback_used"]:
                    st.caption(
                        "_Fallback used — production deployment requires RAG._"
                    )

        st.divider()
        st.markdown("**Recent queries**")
        history = eng["nlq"].list_query_history(limit=10)
        for h in history:
            st.markdown(
                f"_{h.get('submitted_at', '')[:16]}_ "
                f"**[{h.get('intent', '?')}]** "
                f"{h.get('query_text', '')[:80]}"
            )

    # Tab 5: Crisis (#317)
    with tabs[4]:
        st.subheader("⚠️ Crisis Playbook & Incident Command — #317")
        col1, col2 = st.columns([2, 1])
        with col1:
            opens = eng["crisis"].open_incidents()
            st.metric("Open incidents", len(opens))
            for i in opens:
                st.markdown(
                    f"**[{i['severity']}]** {i['title']} "
                    f"_state: {i['state']}_",
                )
        with col2:
            with st.expander("➕ Register playbook", expanded=False):
                with st.form("reg_playbook"):
                    pbid = st.text_input("Playbook ID")
                    pbname = st.text_input("Playbook name")
                    pbtype = st.selectbox("Playbook type", PLAYBOOK_TYPES)
                    pbreason = st.text_input("Reason", key="pb_reason")
                    if st.form_submit_button("Register"):
                        if all([pbid, pbname, pbreason]):
                            r = eng["crisis"].register_playbook(
                                {"playbook_id": pbid,
                                  "playbook_name": pbname,
                                  "playbook_type": pbtype,
                                  "incident_commander_role": "COO"},
                                actor="cro", reason=pbreason,
                            )
                            if r["registered"]:
                                audit_log(
                                    action="register_playbook",
                                    username="cro",
                                    module="command_centre",
                                )
                                st.success("Playbook registered.")
                                st.rerun()
                            else:
                                st.error(f"Failed: {r.get('error', '?')}")

    # Tab 6: Strategic Initiatives + BSC (#318)
    with tabs[5]:
        st.subheader("🎯 Strategic Initiatives & BSC Linkage — #318")
        portfolio = eng["initiatives"].portfolio_summary()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", portfolio["total_initiatives"])
        c2.metric("Active", portfolio["active_initiatives"])
        c3.metric("At Risk", portfolio["at_risk_count"])
        c4.metric("RED", portfolio["rag_distribution"].get("RED", 0))
        if portfolio["at_risk_initiatives"]:
            st.warning("**At-risk initiatives**")
            for r in portfolio["at_risk_initiatives"][:10]:
                st.markdown(
                    f"- **{r['initiative_name']}** "
                    f"`{r['rag_status']}` `{r['phase']}` "
                    f"_{r['owner_role']}_"
                )
        with st.expander("➕ Register initiative", expanded=False):
            with st.form("reg_init"):
                iid = st.text_input("Initiative ID")
                iname = st.text_input("Initiative name")
                iowner = st.selectbox(
                    "Owner role",
                    options=["MD", "CEO", "CFO",
                                "CRO", "COO", "CIO", "CCO"],
                )
                itarget = st.text_input(
                    "Target completion (YYYY-MM-DD)", value="2026-12-31",
                )
                ireason = st.text_input("Reason", key="init_reason")
                if st.form_submit_button("Register"):
                    if all([iid, iname, itarget, ireason]):
                        r = eng["initiatives"].register_initiative(
                            {"initiative_id": iid,
                              "initiative_name": iname,
                              "owner_role": iowner,
                              "target_completion": itarget},
                            actor="md", reason=ireason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_initiative",
                                username="md",
                                module="command_centre",
                            )
                            st.success("Initiative registered.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")

    # Tab 7: Stakeholder Comms + Board (#319 + #320)
    with tabs[6]:
        st.subheader(
            "🏛️ Stakeholder Comms + Board Portal — #319 + #320"
        )
        sub1, sub2 = st.tabs(["Stakeholder Comms", "Board Portal"])
        with sub1:
            stype_filter = st.selectbox(
                "Filter by stakeholder type",
                options=["(All)"] + list(STAKEHOLDER_COMM_TYPES),
            )
            type_arg = (
                None if stype_filter == "(All)" else stype_filter
            )
            outstanding = eng["comms"].list_outstanding(type_arg)
            st.metric("Outstanding comms", len(outstanding))
            for c in outstanding[:15]:
                st.markdown(
                    f"**[{c['stakeholder_type']}]** {c['subject']} "
                    f"_{c['state']}_ "
                    f"<small>via {c['channel']}</small>",
                    unsafe_allow_html=True,
                )
        with sub2:
            mbid = st.text_input("Meeting ID to fetch",
                                       value="BM-2026-Q2")
            mbmember = st.text_input("Board member ID", value="MEM-1")
            if st.button("Fetch meeting") and mbid and mbmember:
                r = eng["mobile_board"].fetch_meeting_for_member(
                    mbid, mbmember,
                )
                if r["available"]:
                    st.success(
                        f"Meeting: {r['meeting_name']} "
                        f"({r['scheduled_for']})"
                    )
                    st.write(f"State: **{r['state']}**")
                    st.write(
                        f"Papers: {len(r['papers'])} · "
                        f"Votes: {len(r['votes'])} · "
                        f"Actions: {len(r['actions'])}"
                    )
                    if r.get("minutes"):
                        st.markdown("### Minutes")
                        st.write(r["minutes"].get("text", ""))
                else:
                    st.warning(f"Not available: {r.get('error', '?')}")


if __name__ == "__main__":
    main()
