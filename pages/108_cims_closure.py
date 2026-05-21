"""
Phase 2B — CIMS Batch 4 (FINAL): Closure (pages/108)
=================================================================
v10.293 — covers Standards #177 (Customer Self-Service Portal),
#179 (Performance Analytics Dashboard), #180 (Completion
Feedback Loop). FINAL CIMS arc batch.

Audience: Operations leads, MD, board, customer experience team.

Tab map (7 tabs at G4 ceiling — planned upfront):
  1. Portal sessions          — register + state transitions + filter
  2. Status queries + actions — record queries + register action requests
  3. KPI definitions          — register + state transitions + summary
  4. KPI observations         — record + breach by severity
  5. Executive views          — register + access events
  6. Feedback surveys         — register + state + record responses + summary
  7. Optimizations            — recommendations + Cat D rule_based surfacing
"""

from __future__ import annotations

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from utils.core_audit import audit_log
from utils.cims_self_service_portal import (
    SelfServicePortalEngine,
    PORTAL_SESSION_STATES, PORTAL_AUTH_METHODS,
    ACTION_REQUEST_TYPES, ACTION_REQUEST_STATES,
    STATUS_QUERY_TYPES,
    DEFAULT_REQUEST_ACK_TARGET_MINUTES,
    DEFAULT_SESSION_HARD_TIMEOUT_MINUTES,
    DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES,
)
from utils.cims_analytics_dashboard import (
    CIMSAnalyticsDashboardEngine,
    KPI_DOMAINS, KPI_FREQUENCIES,
    KPI_DEFINITION_STATES, KPI_DIRECTIONS,
    KPI_STATUS_BANDS, EXECUTIVE_VIEW_TYPES,
    TREND_DIRECTIONS,
    DEFAULT_AMBER_RED_BUFFER_PCT,
    DEFAULT_GREEN_AMBER_BUFFER_PCT,
    DEFAULT_TREND_MIN_OBSERVATIONS,
)
from utils.cims_completion_feedback import (
    CompletionFeedbackEngine,
    FEEDBACK_CHANNELS, SURVEY_STATES,
    FEEDBACK_DIMENSIONS, NPS_TIERS,
    OPTIMIZATION_RECOMMENDATION_KINDS,
    RECOMMENDATION_STATES,
    DEFAULT_FEEDBACK_RETENTION_DAYS,
    DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION,
    DEFAULT_NPS_PROMOTER_THRESHOLD,
    DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD,
)

# Phase 3 standing rule: do NOT silently swallow require_access
# failures. Pages must fail loud so misconfigured access is visible.
from pages._access import require_access
require_access("operations.cims_closure")


@st.cache_resource
def _engines():
    return {
        "portal": SelfServicePortalEngine(),
        "dash": CIMSAnalyticsDashboardEngine(),
        "fb": CompletionFeedbackEngine(),
    }


def main():
    st.title("🎯 CIMS — Closure: Portal · Dashboard · Feedback")
    st.caption(
        "v10.293 · Standards #177 + #179 + #180 · "
        "Final CIMS batch (15/15 complete after this drop)"
    )

    eng = _engines()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "🌐 Portal sessions",
        "📋 Queries + actions",
        "📊 KPI definitions",
        "📈 Observations + breach",
        "👔 Executive views",
        "📝 Feedback surveys",
        "💡 Optimizations",
    ])

    # ---------- Tab 1: Portal sessions ----------
    with tabs[0]:
        st.subheader("Customer self-service portal (Standard #177)")
        st.caption(
            f"Session states: {', '.join(PORTAL_SESSION_STATES)} · "
            f"Auth methods: {', '.join(PORTAL_AUTH_METHODS)} · "
            f"Idle timeout: "
            f"{DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES}min · "
            f"Hard timeout: "
            f"{DEFAULT_SESSION_HARD_TIMEOUT_MINUTES}min"
        )

        with st.form("portal_sess"):
            sid = st.text_input("Session ID")
            scid = st.text_input("Customer ID")
            sauth = st.selectbox("Auth method", PORTAL_AUTH_METHODS)
            srea = st.text_input("Reason")
            if st.form_submit_button("Register session"):
                res = eng["portal"].register_portal_session(
                    {"session_id": sid,
                     "customer_id": scid,
                     "auth_method": sauth},
                    actor=actor, reason=srea,
                )
                audit_log(
                    action="register_portal_session",
                    username=actor, module="cims_closure",
                )
                if res.get("registered"):
                    st.success(
                        f"Session {sid} registered "
                        f"(AUTHENTICATED)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition session state"):
            with st.form("portal_state"):
                tsid = st.text_input(
                    "Session ID", key="ps_ts_sid",
                )
                ns = st.selectbox(
                    "New state", PORTAL_SESSION_STATES,
                )
                tr = st.text_input(
                    "Reason", key="ps_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["portal"].transition_session_state(
                        tsid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_portal_session_state",
                        username=actor, module="cims_closure",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 2: Queries + actions ----------
    with tabs[1]:
        st.subheader("Status queries and action requests")
        st.caption(
            f"Query types: {', '.join(STATUS_QUERY_TYPES)} · "
            f"Action types: {', '.join(ACTION_REQUEST_TYPES)} · "
            f"Action states: {', '.join(ACTION_REQUEST_STATES)} · "
            f"Ack target: "
            f"{DEFAULT_REQUEST_ACK_TARGET_MINUTES}min"
        )

        with st.form("query_form"):
            qid = st.text_input("Query ID")
            qsid = st.text_input("Session ID")
            qtype = st.selectbox(
                "Query type", STATUS_QUERY_TYPES,
            )
            qiid = st.text_input("Instruction ID (optional)")
            qnar = st.text_area("Narrative")
            if st.form_submit_button("Record query"):
                res = eng["portal"].record_status_query(
                    {"query_id": qid,
                     "session_id": qsid,
                     "query_type": qtype,
                     "instruction_id": qiid,
                     "narrative": qnar},
                    actor=actor,
                )
                audit_log(
                    action="record_status_query",
                    username=actor, module="cims_closure",
                )
                if res.get("recorded"):
                    st.success(f"Query {qid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Register action request"):
            with st.form("action_form"):
                aid = st.text_input("Request ID")
                asid = st.text_input(
                    "Session ID", key="act_sid",
                )
                aiid = st.text_input("Instruction ID")
                atype = st.selectbox(
                    "Request type", ACTION_REQUEST_TYPES,
                )
                anar = st.text_area("Narrative", key="act_narr")
                area = st.text_input(
                    "Reason", key="act_reason",
                )
                if st.form_submit_button("Register"):
                    res = eng["portal"].register_action_request(
                        {"request_id": aid,
                         "session_id": asid,
                         "instruction_id": aiid,
                         "request_type": atype,
                         "narrative": anar},
                        actor=actor, reason=area,
                    )
                    audit_log(
                        action="register_action_request",
                        username=actor, module="cims_closure",
                    )
                    if res.get("registered"):
                        st.success(
                            f"Request {aid} registered (SUBMITTED)",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Transition request state"):
            with st.form("req_state"):
                trid = st.text_input(
                    "Request ID", key="req_ts_rid",
                )
                ns = st.selectbox(
                    "New state", ACTION_REQUEST_STATES,
                )
                tr = st.text_input(
                    "Reason", key="req_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["portal"].transition_request_state(
                        trid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_request_state",
                        username=actor, module="cims_closure",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        cid = st.text_input(
            "Customer ID for open requests", key="cust_open",
        )
        if st.button("Customer open requests"):
            opens = eng["portal"].customer_open_requests(cid)
            st.metric("Open", len(opens))
            for r in opens[:10]:
                st.write(
                    f"• `{r.get('request_id')}` "
                    f"({r.get('request_type')}, "
                    f"{r.get('state')}) — "
                    f"{r.get('narrative', '')[:80]}",
                )

        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="portal_days",
        )
        if st.button("Portal metrics"):
            m = eng["portal"].portal_metrics(days=int(ndays))
            cols = st.columns(2)
            cols[0].metric(
                "Sessions", m.get("total_sessions", 0),
            )
            cols[1].metric(
                "Queries", m.get("total_queries", 0),
            )
            st.write("Per state:", m.get("per_state", {}))
            st.write(
                "Per query type:",
                m.get("per_query_type", {}),
            )

    # ---------- Tab 3: KPI definitions ----------
    with tabs[2]:
        st.subheader(
            "Performance KPIs (Standard #179)",
        )
        st.caption(
            f"Domains: {', '.join(KPI_DOMAINS)} · "
            f"Frequencies: {', '.join(KPI_FREQUENCIES)} · "
            f"Status bands: {', '.join(KPI_STATUS_BANDS)} · "
            f"Buffers: GREEN-AMBER="
            f"{DEFAULT_GREEN_AMBER_BUFFER_PCT}%, "
            f"AMBER-RED={DEFAULT_AMBER_RED_BUFFER_PCT}%"
        )

        with st.form("kpi_def"):
            kid = st.text_input("KPI ID")
            kname = st.text_input("Name")
            kdom = st.selectbox("Domain", KPI_DOMAINS)
            kfreq = st.selectbox("Frequency", KPI_FREQUENCIES)
            kdir = st.selectbox(
                "Direction", KPI_DIRECTIONS,
            )
            ktarget = st.number_input(
                "Target value", value=80.0,
            )
            krea = st.text_input("Reason")
            if st.form_submit_button("Register definition"):
                res = eng["dash"].register_kpi_definition(
                    {"definition_id": kid,
                     "name": kname,
                     "domain": kdom,
                     "frequency": kfreq,
                     "direction": kdir,
                     "target_value": float(ktarget)},
                    actor=actor, reason=krea,
                )
                audit_log(
                    action="register_kpi_definition",
                    username=actor, module="cims_closure",
                )
                if res.get("registered"):
                    st.success(f"KPI {kid} registered (DRAFT)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition KPI state"):
            with st.form("kpi_state"):
                tkid = st.text_input(
                    "KPI ID", key="kpi_ts_kid",
                )
                ns = st.selectbox(
                    "New state", KPI_DEFINITION_STATES,
                )
                tr = st.text_input(
                    "Reason", key="kpi_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["dash"].transition_definition_state(
                        tkid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_kpi_state",
                        username=actor, module="cims_closure",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button("Dashboard summary"):
            s = eng["dash"].dashboard_summary()
            cols = st.columns(2)
            cols[0].metric(
                "Total definitions",
                s.get("total_definitions", 0),
            )
            cols[1].metric(
                "Active",
                s.get("active_definitions", 0),
            )
            st.write(
                "Per domain:",
                s.get("per_domain", {}),
            )
            st.write(
                "Per frequency:",
                s.get("per_frequency", {}),
            )

    # ---------- Tab 4: Observations + breach ----------
    with tabs[3]:
        st.subheader("KPI observations and breach summary")

        with st.form("obs_form"):
            oid = st.text_input("Observation ID")
            okid = st.text_input("KPI ID", key="obs_kid")
            oval = st.number_input(
                "Observed value", value=0.0,
            )
            oband = st.selectbox(
                "Status band", KPI_STATUS_BANDS,
            )
            otd = st.selectbox(
                "Trend direction (optional)",
                ["(unset)"] + list(TREND_DIRECTIONS),
            )
            onar = st.text_area("Narrative")
            if st.form_submit_button("Record observation"):
                payload = {"observation_id": oid,
                              "definition_id": okid,
                              "value": float(oval),
                              "status_band": oband,
                              "narrative": onar}
                if otd != "(unset)":
                    payload["trend_direction"] = otd
                res = eng["dash"].record_kpi_observation(
                    payload, actor=actor,
                )
                audit_log(
                    action="record_kpi_observation",
                    username=actor, module="cims_closure",
                )
                if res.get("recorded"):
                    st.success(f"Observation {oid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        st.markdown("---")
        st.markdown("**KPI status report**")
        rkid = st.text_input(
            "KPI ID for status report", key="ksr_kid",
        )
        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="ksr_days",
        )
        if st.button("KPI status report"):
            r = eng["dash"].kpi_status_report(
                rkid, days=int(ndays),
            )
            if "error" in r:
                st.error(r["error"])
            else:
                cols = st.columns(3)
                cols[0].metric(
                    "Observations", r.get("total_observations", 0),
                )
                cols[1].metric(
                    "Latest band",
                    r.get("latest_status_band", "—"),
                )
                cols[2].metric(
                    "Latest value",
                    r.get("latest_value", "—"),
                )
                st.write(
                    "Per status band:",
                    r.get("per_status_band", {}),
                )

    # ---------- Tab 5: Executive views ----------
    with tabs[4]:
        st.subheader("Executive views")
        st.caption(
            f"View types: {', '.join(EXECUTIVE_VIEW_TYPES)}"
        )

        with st.form("view_form"):
            vid = st.text_input("View ID")
            vtype = st.selectbox(
                "View type", EXECUTIVE_VIEW_TYPES,
            )
            vaud = st.text_input("Audience")
            vrea = st.text_input("Reason")
            if st.form_submit_button("Register view"):
                res = eng["dash"].register_executive_view(
                    {"view_id": vid,
                     "view_type": vtype,
                     "audience": vaud},
                    actor=actor, reason=vrea,
                )
                audit_log(
                    action="register_executive_view",
                    username=actor, module="cims_closure",
                )
                if res.get("registered"):
                    st.success(f"View {vid} registered")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Register trend snapshot"):
            with st.form("trend_form"):
                tsid = st.text_input("Snapshot ID")
                tskid = st.text_input(
                    "KPI ID", key="trend_kid",
                )
                tsdir = st.selectbox(
                    "Trend direction", TREND_DIRECTIONS,
                )
                tsobs = st.number_input(
                    "Observation count",
                    min_value=0, value=0,
                )
                tsnar = st.text_area(
                    "Narrative", key="trend_narr",
                )
                tsrea = st.text_input(
                    "Reason", key="trend_reason",
                )
                if st.form_submit_button("Register snapshot"):
                    res = eng["dash"].register_trend_snapshot(
                        {"snapshot_id": tsid,
                         "definition_id": tskid,
                         "trend_direction": tsdir,
                         "observation_count": int(tsobs),
                         "narrative": tsnar},
                        actor=actor, reason=tsrea,
                    )
                    audit_log(
                        action="register_trend_snapshot",
                        username=actor, module="cims_closure",
                    )
                    if res.get("registered"):
                        st.success(
                            f"Trend snapshot {tsid} registered",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 6: Feedback surveys ----------
    with tabs[5]:
        st.subheader("Completion feedback (Standard #180)")
        st.caption(
            f"Channels: {', '.join(FEEDBACK_CHANNELS)} · "
            f"Dimensions: {', '.join(FEEDBACK_DIMENSIONS)} · "
            f"NPS tiers: {', '.join(NPS_TIERS)} "
            f"(promoter≥{DEFAULT_NPS_PROMOTER_THRESHOLD}, "
            f"passive {DEFAULT_NPS_PASSIVE_LOWER_THRESHOLD}-8) · "
            f"Retention: {DEFAULT_FEEDBACK_RETENTION_DAYS}d"
        )

        with st.form("survey_form"):
            sid = st.text_input("Survey ID")
            sname = st.text_input("Name")
            schan = st.selectbox(
                "Channel", FEEDBACK_CHANNELS,
            )
            sdims = st.multiselect(
                "Dimensions", FEEDBACK_DIMENSIONS,
            )
            srea = st.text_input("Reason")
            if st.form_submit_button("Register survey"):
                res = eng["fb"].register_feedback_survey(
                    {"survey_id": sid, "name": sname,
                     "channel": schan, "dimensions": sdims},
                    actor=actor, reason=srea,
                )
                audit_log(
                    action="register_feedback_survey",
                    username=actor, module="cims_closure",
                )
                if res.get("registered"):
                    st.success(f"Survey {sid} registered (DRAFT)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition survey state"):
            with st.form("sv_state"):
                tsid = st.text_input(
                    "Survey ID", key="sv_ts_sid",
                )
                ns = st.selectbox(
                    "New state", SURVEY_STATES,
                )
                tr = st.text_input(
                    "Reason", key="sv_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["fb"].transition_survey_state(
                        tsid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_survey_state",
                        username=actor, module="cims_closure",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Record feedback response"):
            with st.form("resp_form"):
                rid = st.text_input("Response ID")
                rsid = st.text_input(
                    "Survey ID", key="resp_sid",
                )
                rsess = st.text_input("Linked session ID")
                rs_cs = st.number_input(
                    "OVERALL_SATISFACTION (1-5)",
                    min_value=0, max_value=5, value=0,
                )
                rs_eu = st.number_input(
                    "EASE_OF_USE (1-5)",
                    min_value=0, max_value=5, value=0,
                )
                rs_sp = st.number_input(
                    "SPEED (1-5)",
                    min_value=0, max_value=5, value=0,
                )
                rs_ah = st.number_input(
                    "AGENT_HELPFULNESS (1-5)",
                    min_value=0, max_value=5, value=0,
                )
                rs_om = st.number_input(
                    "OUTCOME_MET_EXPECTATIONS (1-5)",
                    min_value=0, max_value=5, value=0,
                )
                rs_nps = st.number_input(
                    "NPS (0-10)",
                    min_value=0, max_value=10, value=0,
                )
                rnar = st.text_area(
                    "Narrative", key="resp_narr",
                )
                if st.form_submit_button("Record"):
                    scores: dict = {}
                    if rs_cs > 0:
                        scores["OVERALL_SATISFACTION"] = int(rs_cs)
                    if rs_eu > 0:
                        scores["EASE_OF_USE"] = int(rs_eu)
                    if rs_sp > 0:
                        scores["SPEED"] = int(rs_sp)
                    if rs_ah > 0:
                        scores["AGENT_HELPFULNESS"] = int(rs_ah)
                    if rs_om > 0:
                        scores["OUTCOME_MET_EXPECTATIONS"] = int(rs_om)
                    scores["NPS"] = int(rs_nps)
                    res = eng["fb"].record_feedback_response(
                        {"response_id": rid,
                         "survey_id": rsid,
                         "linked_session_id": rsess,
                         "scores": scores,
                         "narrative": rnar},
                        actor=actor,
                    )
                    audit_log(
                        action="record_feedback_response",
                        username=actor, module="cims_closure",
                    )
                    if res.get("recorded"):
                        st.success(f"Response {rid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="fb_days",
        )
        if st.button("Feedback summary"):
            s = eng["fb"].feedback_summary(days=int(ndays))
            cols = st.columns(3)
            cols[0].metric(
                "Responses", s["total_responses"],
            )
            cols[1].metric(
                "NPS", s.get("nps_score") if s.get("nps_score") is not None else "—",
            )
            cols[2].metric("Promoters", s["promoters"])
            st.write(
                "Per-dimension avg:",
                s.get("per_dimension_avg", {}),
            )

    # ---------- Tab 7: Optimizations ----------
    with tabs[6]:
        st.subheader(
            "Optimization recommendations (Cat D Rule 7)",
        )
        st.caption(
            f"Kinds: "
            f"{', '.join(OPTIMIZATION_RECOMMENDATION_KINDS)} · "
            f"States: {', '.join(RECOMMENDATION_STATES)} · "
            f"Min responses: "
            f"{DEFAULT_MIN_RESPONSES_FOR_RECOMMENDATION}"
        )

        with st.form("rec_form"):
            rid = st.text_input("Recommendation ID")
            rkind = st.selectbox(
                "Kind", OPTIMIZATION_RECOMMENDATION_KINDS,
            )
            rnar = st.text_area("Narrative")
            rev = st.text_area("Supporting evidence")
            rrea = st.text_input("Reason")
            if st.form_submit_button("Register recommendation"):
                res = eng["fb"].register_optimization_recommendation(
                    {"recommendation_id": rid,
                     "kind": rkind,
                     "narrative": rnar,
                     "supporting_evidence": rev},
                    actor=actor, reason=rrea,
                )
                audit_log(
                    action="register_optimization_recommendation",
                    username=actor, module="cims_closure",
                )
                if res.get("registered"):
                    st.success(
                        f"Recommendation {rid} registered "
                        f"(PROPOSED)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition recommendation state"):
            with st.form("rec_state"):
                trid = st.text_input(
                    "Recommendation ID", key="rec_ts_rid",
                )
                ns = st.selectbox(
                    "New state", RECOMMENDATION_STATES,
                )
                tr = st.text_input(
                    "Reason", key="rec_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["fb"].transition_recommendation_state(
                        trid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_recommendation_state",
                        username=actor, module="cims_closure",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button(
            "Surface optimizations (rule_based, no ML)",
        ):
            r = eng["fb"].surface_optimizations()
            st.metric("Basis", r["basis"])
            st.caption(r.get("reason", ""))
            for rec in r["rule_based_recommendations"]:
                kind = rec.get("kind") or "INSUFFICIENT_DATA"
                st.write(
                    f"• `{kind}` — {rec.get('narrative', '')}",
                )
                if rec.get("evidence"):
                    st.caption(f"  evidence: {rec['evidence']}")


main()
