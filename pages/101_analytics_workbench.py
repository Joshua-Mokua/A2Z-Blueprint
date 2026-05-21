"""
Phase 2B — Analytics Hub: Workbench + Reports (pages/101)
=================================================================
v10.286 — covers Standards #286 (Credit Analyst Workbench) and
#287 (Scheduled Reports & Alerts).

Audience: Credit analysts, MIS analysts, compliance reporting.

Tab map (6 tabs):
  1. Workbench session         — open/inspect session, transitions
  2. Data pulls + conflicts    — record snapshots from upstream sources
  3. Analyst notes             — capture observations + rationale
  4. Schedules                 — recurring report delivery configuration
  5. Alerts                    — threshold rules and state
  6. Deliveries                — recent activity + metrics
"""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from utils.core_audit import audit_log
from utils.analytics_credit_workbench import (
    CreditWorkbenchEngine,
    WORKBENCH_SESSION_STATES, DATA_SOURCES,
    VIEW_TYPES, NOTE_CATEGORIES,
    DEFAULT_SESSION_TIMEOUT_HOURS, DEFAULT_DATA_PULL_CACHE_MINUTES,
)
from utils.analytics_scheduled_reports import (
    ScheduledReportsEngine,
    DELIVERY_CHANNELS, SCHEDULE_FREQUENCIES, SCHEDULE_STATES,
    ALERT_TRIGGER_TYPES, ALERT_STATES, DELIVERY_STATES,
    DEFAULT_DELIVERY_TIMEOUT_SECONDS, DEFAULT_RETRY_LIMIT,
)

try:
    from pages._access import require_access
    require_access("shared.analytics_workbench")
except Exception:
    pass


@st.cache_resource
def _engines():
    return {
        "wb": CreditWorkbenchEngine(),
        "rs": ScheduledReportsEngine(),
    }


def main():
    st.title("📊 Analytics Hub — Workbench & Reports")
    st.caption(
        "v10.286 · Standards #286 + #287 · Credit analyst workbench, "
        "scheduled reports, alert rules, delivery metrics"
    )

    eng = _engines()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "🧑‍💼 Workbench session",
        "🔍 Data pulls + conflicts",
        "📝 Analyst notes",
        "📅 Schedules",
        "🚨 Alerts",
        "📤 Deliveries",
    ])

    # ---------- Tab 1: Workbench session ----------
    with tabs[0]:
        st.subheader("Credit analyst workbench (Standard #286)")
        st.caption(
            f"States: {', '.join(WORKBENCH_SESSION_STATES)}. "
            f"Default session timeout: "
            f"{DEFAULT_SESSION_TIMEOUT_HOURS}h."
        )

        with st.form("wb_session_form"):
            sid = st.text_input("Session ID")
            cid = st.text_input("Customer ID")
            lapp = st.text_input("Loan application ID")
            role = st.text_input(
                "Analyst role", value="credit_analyst",
            )
            purpose = st.text_input("Purpose")
            reason = st.text_input("Registration reason")
            if st.form_submit_button("Open session"):
                res = eng["wb"].register_workbench_session(
                    {"session_id": sid, "customer_id": cid,
                     "loan_application_id": lapp,
                     "analyst_role": role,
                     "purpose": purpose},
                    actor=actor, reason=reason,
                )
                audit_log(
                    action="register_workbench_session",
                    username=actor,
                    module="analytics_workbench",
                )
                if res.get("registered"):
                    st.success(f"Session {sid} opened (OPEN)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition session state"):
            with st.form("wb_state_form"):
                sid_t = st.text_input("Session ID", key="ws_sid")
                ns = st.selectbox(
                    "New state", WORKBENCH_SESSION_STATES,
                )
                reason_t = st.text_input("Reason", key="ws_reason")
                if st.form_submit_button("Transition"):
                    res = eng["wb"].transition_session_state(
                        sid_t, ns, actor=actor, reason=reason_t,
                    )
                    audit_log(
                        action="transition_workbench_session_state",
                        username=actor,
                        module="analytics_workbench",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Register a workbench view"):
            with st.form("wb_view_form"):
                vid = st.text_input("View ID")
                vsid = st.text_input(
                    "Session ID", key="wv_sid",
                )
                vtype = st.selectbox("View type", VIEW_TYPES)
                vtitle = st.text_input("Title")
                vreason = st.text_input("Reason", key="wv_reason")
                if st.form_submit_button("Register view"):
                    res = eng["wb"].register_workbench_view(
                        {"view_id": vid, "session_id": vsid,
                         "view_type": vtype, "title": vtitle},
                        actor=actor, reason=vreason,
                    )
                    audit_log(
                        action="register_workbench_view",
                        username=actor,
                        module="analytics_workbench",
                    )
                    if res.get("registered"):
                        st.success(f"View {vid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        sid_s = st.text_input(
            "Session ID for summary", key="ws_summary_sid",
        )
        if st.button("Show summary"):
            s = eng["wb"].workbench_summary(sid_s)
            if s.get("found"):
                cols = st.columns(4)
                cols[0].metric("State", s["state"])
                cols[1].metric(
                    "Data pulls", s["data_pulls_count"],
                )
                cols[2].metric("Notes", s["notes_count"])
                cols[3].metric(
                    "Sources covered",
                    f"{len(s['sources_pulled'])}/"
                    f"{len(DATA_SOURCES)}",
                )
                if s["sources_missing"]:
                    st.info(
                        "Sources not yet pulled: "
                        + ", ".join(s["sources_missing"]),
                    )
            else:
                st.error(s.get("error", "Not found"))

    # ---------- Tab 2: Data pulls + conflicts ----------
    with tabs[1]:
        st.subheader("Upstream data pulls and conflicts")
        st.caption(
            f"Sources: {', '.join(DATA_SOURCES)}. Cache: "
            f"{DEFAULT_DATA_PULL_CACHE_MINUTES}m."
        )

        with st.form("pull_form"):
            pid = st.text_input("Pull ID")
            psid = st.text_input("Session ID", key="dp_sid")
            psrc = st.selectbox("Data source", DATA_SOURCES)
            psum = st.text_area("Snapshot summary")
            pdec = st.text_input("Snapshot decision")
            pscore = st.text_input("Snapshot score")
            if st.form_submit_button("Record pull"):
                res = eng["wb"].record_data_pull(
                    {"pull_id": pid, "session_id": psid,
                     "data_source": psrc,
                     "snapshot_summary": psum,
                     "snapshot_decision": pdec,
                     "snapshot_score": pscore},
                    actor=actor,
                )
                audit_log(
                    action="record_workbench_data_pull",
                    username=actor,
                    module="analytics_workbench",
                )
                if res.get("recorded"):
                    st.success(f"Pull {pid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        sid_c = st.text_input(
            "Session ID for conflict report", key="cr_sid",
        )
        if st.button("Run conflict report"):
            cr = eng["wb"].conflict_report(sid_c)
            cols = st.columns(3)
            cols[0].metric("Total pulls", cr["total_pulls"])
            cols[1].metric(
                "Distinct decisions", cr["distinct_decisions"],
            )
            cols[2].metric(
                "Conflicts", cr["conflict_count"],
            )
            if cr["conflicts"]:
                st.warning("Conflicting decisions detected:")
                for c in cr["conflicts"]:
                    st.write(
                        f"• `{c['decision']}`: "
                        f"{', '.join(c['sources'])} "
                        f"({c['pull_count']} pulls)",
                    )

    # ---------- Tab 3: Analyst notes ----------
    with tabs[2]:
        st.subheader("Analyst notes")
        st.caption(
            f"Categories: {', '.join(NOTE_CATEGORIES)}.",
        )
        with st.form("note_form"):
            nid = st.text_input("Note ID")
            nsid = st.text_input("Session ID", key="n_sid")
            ncat = st.selectbox("Category", NOTE_CATEGORIES)
            nbody = st.text_area("Note body")
            nlinked = st.text_input(
                "Linked pull ID (optional)",
            )
            if st.form_submit_button("Record note"):
                res = eng["wb"].record_analyst_note(
                    {"note_id": nid, "session_id": nsid,
                     "category": ncat, "body": nbody,
                     "linked_pull_id": nlinked},
                    actor=actor,
                )
                audit_log(
                    action="record_analyst_note",
                    username=actor,
                    module="analytics_workbench",
                )
                if res.get("recorded"):
                    st.success(f"Note {nid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 4: Schedules ----------
    with tabs[3]:
        st.subheader("Scheduled reports (Standard #287)")
        st.caption(
            f"Channels: {', '.join(DELIVERY_CHANNELS)}. "
            f"Frequencies: {', '.join(SCHEDULE_FREQUENCIES)}."
        )

        with st.form("sch_form"):
            schid = st.text_input("Schedule ID")
            rep = st.text_input("Report ID")
            freq = st.selectbox(
                "Frequency", SCHEDULE_FREQUENCIES,
            )
            chan = st.selectbox("Channel", DELIVERY_CHANNELS)
            recips = st.text_input(
                "Recipients (comma-separated)",
            )
            reason = st.text_input("Reason", key="sch_reason")
            if st.form_submit_button("Register schedule"):
                rec_list = [
                    r.strip() for r in recips.split(",")
                    if r.strip()
                ]
                res = eng["rs"].register_schedule(
                    {"schedule_id": schid, "report_id": rep,
                     "frequency": freq, "channel": chan,
                     "recipients": rec_list},
                    actor=actor, reason=reason,
                )
                audit_log(
                    action="register_report_schedule",
                    username=actor,
                    module="analytics_workbench",
                )
                if res.get("registered"):
                    st.success(
                        f"Schedule {schid} registered (ACTIVE)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition schedule state"):
            with st.form("sch_state_form"):
                schid_t = st.text_input(
                    "Schedule ID", key="ss_sid",
                )
                ns = st.selectbox(
                    "New state", SCHEDULE_STATES,
                )
                reason_t = st.text_input(
                    "Reason", key="ss_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["rs"].transition_schedule_state(
                        schid_t, ns, actor=actor, reason=reason_t,
                    )
                    audit_log(
                        action="transition_schedule_state",
                        username=actor,
                        module="analytics_workbench",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        within = st.number_input(
            "Schedules due within (minutes)",
            min_value=1, value=60,
        )
        if st.button("List due schedules"):
            due = eng["rs"].schedules_due(
                within_minutes=int(within),
            )
            st.metric("Schedules due", len(due))
            for d in due[:10]:
                st.write(
                    f"• {d.get('schedule_id')} → "
                    f"{d.get('report_id')} "
                    f"({d.get('frequency')}, "
                    f"{d.get('channel')}) "
                    f"at {d.get('next_run_at', '')[:19]}",
                )

    # ---------- Tab 5: Alerts ----------
    with tabs[4]:
        st.subheader("Alert rules")
        st.caption(
            f"Triggers: {', '.join(ALERT_TRIGGER_TYPES)}. "
            f"States: {', '.join(ALERT_STATES)}."
        )
        with st.form("alert_form"):
            aid = st.text_input("Alert ID")
            metric = st.text_input("Metric ID")
            trig = st.selectbox(
                "Trigger type", ALERT_TRIGGER_TYPES,
            )
            thresh = st.text_input("Threshold value")
            achan = st.selectbox(
                "Channel", DELIVERY_CHANNELS, key="al_chan",
            )
            arecips = st.text_input(
                "Recipients (comma-separated)", key="al_recips",
            )
            areason = st.text_input("Reason", key="al_reason")
            if st.form_submit_button("Register alert rule"):
                arec_list = [
                    r.strip() for r in arecips.split(",")
                    if r.strip()
                ]
                res = eng["rs"].register_alert_rule(
                    {"alert_id": aid, "metric_id": metric,
                     "trigger_type": trig,
                     "threshold_value": thresh,
                     "channel": achan, "recipients": arec_list},
                    actor=actor, reason=areason,
                )
                audit_log(
                    action="register_alert_rule",
                    username=actor,
                    module="analytics_workbench",
                )
                if res.get("registered"):
                    st.success(
                        f"Alert {aid} registered (ACTIVE)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition alert state"):
            with st.form("alert_state_form"):
                aid_t = st.text_input(
                    "Alert ID", key="as_aid",
                )
                ns = st.selectbox("New state", ALERT_STATES)
                reason_t = st.text_input(
                    "Reason", key="as_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["rs"].transition_alert_state(
                        aid_t, ns, actor=actor, reason=reason_t,
                    )
                    audit_log(
                        action="transition_alert_state",
                        username=actor,
                        module="analytics_workbench",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 6: Deliveries ----------
    with tabs[5]:
        st.subheader("Deliveries")
        st.caption(
            f"Delivery states: {', '.join(DELIVERY_STATES)}. "
            f"Default timeout: "
            f"{DEFAULT_DELIVERY_TIMEOUT_SECONDS}s · "
            f"retry limit {DEFAULT_RETRY_LIMIT}."
        )
        with st.form("delivery_form"):
            did = st.text_input("Delivery ID")
            dsid = st.text_input(
                "Schedule ID (or alert ID via alert_id field)",
            )
            dchan = st.selectbox(
                "Channel", DELIVERY_CHANNELS, key="d_chan",
            )
            drecips = st.text_input(
                "Recipients (comma-separated)", key="d_recips",
            )
            dstate = st.selectbox(
                "Initial state", DELIVERY_STATES,
            )
            if st.form_submit_button("Record delivery"):
                drec_list = [
                    r.strip() for r in drecips.split(",")
                    if r.strip()
                ]
                res = eng["rs"].record_delivery(
                    {"delivery_id": did, "schedule_id": dsid,
                     "channel": dchan, "recipients": drec_list,
                     "state": dstate},
                    actor=actor,
                )
                audit_log(
                    action="record_delivery",
                    username=actor,
                    module="analytics_workbench",
                )
                if res.get("recorded"):
                    st.success(f"Delivery {did} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="dm_days",
        )
        if st.button("Delivery metrics"):
            m = eng["rs"].delivery_metrics(days=int(ndays))
            cols = st.columns(4)
            cols[0].metric("Total", m["total_deliveries"])
            cols[1].metric("Delivered", m["delivered"])
            cols[2].metric("Failed", m["failed"])
            cols[3].metric(
                "Delivery rate", f"{m['delivery_rate_pct']}%",
            )
            if m["per_channel"]:
                st.markdown("**Per channel:**")
                for ch, stats in m["per_channel"].items():
                    st.write(
                        f"• `{ch}`: "
                        f"{stats['delivered']}/{stats['total']} "
                        f"delivered ({stats['failed']} failed)",
                    )


main()
