"""
Phase 2B — Analytics Hub: NLQ + Anomaly + Export (pages/102)
=================================================================
v10.287 — covers Standards #288 (NLQ), #289 (Anomaly Detection),
#290 (Data Export & Integration Hub).

Audience: MIS analysts, compliance, data engineers, DPO.

Tab map (7 tabs; right at the G4 ceiling, planned upfront):
  1. NLQ — submit + lifecycle
  2. NLQ — safety & outcomes
  3. Anomaly rules
  4. Anomaly observations
  5. Data export requests
  6. Integration endpoints
  7. Metrics dashboard
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
from utils.analytics_nlq import (
    NLQEngine,
    QUERY_REQUEST_STATES, QUERY_DOMAINS,
    SAFETY_VERDICTS, EXECUTION_OUTCOMES as NLQ_EXECUTION_OUTCOMES,
    DEFAULT_QUERY_TIMEOUT_SECONDS, DEFAULT_MAX_ROWS_RETURNED,
    DEFAULT_TRANSLATION_RETRY_LIMIT,
)
from utils.analytics_anomaly_detection import (
    AnomalyDetectionEngine,
    DETECTION_METHODS, RULE_STATES,
    ANOMALY_SEVERITIES, ANOMALY_STATES, ANOMALY_CLASSIFICATIONS,
    DEFAULT_DETECTION_INTERVAL_MINUTES,
    DEFAULT_SEVERITY_ESCALATION_HOURS,
)
from utils.analytics_data_export import (
    DataExportEngine,
    EXPORT_FORMATS, EXPORT_REQUEST_STATES,
    PII_TIERS, INTEGRATION_TYPES,
    EXECUTION_OUTCOMES as EXPORT_EXECUTION_OUTCOMES,
    DEFAULT_EXPORT_TIMEOUT_SECONDS, DEFAULT_RETENTION_DAYS,
)

try:
    from pages._access import require_access
    require_access("shared.analytics_advanced")
except Exception:
    pass


@st.cache_resource
def _engines():
    return {
        "nlq": NLQEngine(),
        "anom": AnomalyDetectionEngine(),
        "exp": DataExportEngine(),
    }


def main():
    st.title("📊 Analytics Hub — NLQ, Anomaly & Export")
    st.caption(
        "v10.287 · Standards #288 + #289 + #290 · Natural language query, "
        "anomaly detection, data export hub"
    )

    eng = _engines()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "💬 NLQ submit",
        "🔒 NLQ safety",
        "📐 Anomaly rules",
        "🚨 Anomaly observations",
        "📤 Export requests",
        "🔗 Integration endpoints",
        "📈 Metrics",
    ])

    # ---------- Tab 1: NLQ submit + lifecycle ----------
    with tabs[0]:
        st.subheader("Natural Language Query (Standard #288)")
        st.caption(
            f"Domains: {', '.join(QUERY_DOMAINS)} · "
            f"Timeout: {DEFAULT_QUERY_TIMEOUT_SECONDS}s · "
            f"Max rows: {DEFAULT_MAX_ROWS_RETURNED:,} · "
            f"Retry limit: {DEFAULT_TRANSLATION_RETRY_LIMIT}"
        )
        with st.form("nlq_submit"):
            rid = st.text_input("Request ID")
            nl = st.text_area("Natural language query")
            dom = st.selectbox("Domain", QUERY_DOMAINS)
            if st.form_submit_button("Submit"):
                res = eng["nlq"].register_query_request(
                    {"request_id": rid, "natural_language": nl,
                     "domain": dom},
                    actor=actor,
                )
                audit_log(
                    action="register_nlq_request",
                    username=actor,
                    module="analytics_advanced",
                )
                if res.get("registered"):
                    st.success(f"Submitted {rid} (SUBMITTED)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition request state"):
            with st.form("nlq_state"):
                tid = st.text_input("Request ID", key="nlq_st_rid")
                ns = st.selectbox("New state", QUERY_REQUEST_STATES)
                tsql = st.text_area(
                    "Translated SQL (only for TRANSLATED transition)",
                )
                tr = st.text_input("Reason", key="nlq_st_reason")
                if st.form_submit_button("Transition"):
                    res = eng["nlq"].transition_request_state(
                        tid, ns, actor=actor, reason=tr,
                        translated_sql=tsql,
                    )
                    audit_log(
                        action="transition_nlq_request_state",
                        username=actor,
                        module="analytics_advanced",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        state_filter = st.selectbox(
            "List requests by state", QUERY_REQUEST_STATES,
            key="nlq_filter",
        )
        if st.button("List"):
            requests = eng["nlq"].requests_by_state(state_filter)
            st.metric(state_filter, len(requests))
            for r in requests[:10]:
                st.write(
                    f"• {r.get('request_id')} ({r.get('domain')}) "
                    f"— {r.get('natural_language', '')[:80]}",
                )

    # ---------- Tab 2: NLQ safety + outcomes ----------
    with tabs[1]:
        st.subheader("NLQ safety reviews and execution outcomes")
        st.caption(
            f"Verdicts: {', '.join(SAFETY_VERDICTS)} · "
            f"Outcomes: {', '.join(NLQ_EXECUTION_OUTCOMES)}"
        )
        with st.form("nlq_review"):
            vid = st.text_input("Review ID")
            vrid = st.text_input("Request ID", key="nlq_v_rid")
            verdict = st.selectbox("Verdict", SAFETY_VERDICTS)
            vrat = st.text_area("Rationale")
            if st.form_submit_button("Record review"):
                res = eng["nlq"].record_safety_review(
                    {"review_id": vid, "request_id": vrid,
                     "verdict": verdict, "rationale": vrat},
                    actor=actor,
                )
                audit_log(
                    action="record_nlq_safety_review",
                    username=actor,
                    module="analytics_advanced",
                )
                if res.get("recorded"):
                    st.success(f"Review {vid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Record execution outcome"):
            with st.form("nlq_outcome"):
                oid = st.text_input("Outcome ID")
                orid = st.text_input(
                    "Request ID", key="nlq_o_rid",
                )
                oc = st.selectbox("Outcome", NLQ_EXECUTION_OUTCOMES)
                rrows = st.number_input(
                    "Rows returned", min_value=0, value=0,
                )
                rdur = st.number_input(
                    "Duration (ms)", min_value=0, value=0,
                )
                if st.form_submit_button("Record outcome"):
                    res = eng["nlq"].record_execution_outcome(
                        {"outcome_id": oid, "request_id": orid,
                         "outcome": oc,
                         "rows_returned": int(rrows),
                         "duration_ms": int(rdur)},
                        actor=actor,
                    )
                    audit_log(
                        action="record_nlq_execution_outcome",
                        username=actor,
                        module="analytics_advanced",
                    )
                    if res.get("recorded"):
                        st.success(f"Outcome {oid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 3: Anomaly rules ----------
    with tabs[2]:
        st.subheader("Anomaly detection rules (Standard #289)")
        st.caption(
            f"Methods: {', '.join(DETECTION_METHODS)} · "
            f"Default detection interval: "
            f"{DEFAULT_DETECTION_INTERVAL_MINUTES}m · "
            f"Severity escalation: "
            f"{DEFAULT_SEVERITY_ESCALATION_HOURS}h"
        )
        with st.form("anom_rule"):
            arid = st.text_input("Rule ID")
            amet = st.text_input("Metric ID")
            ameth = st.selectbox("Method", DETECTION_METHODS)
            athr = st.text_input("Threshold value")
            asev = st.selectbox("Severity", ANOMALY_SEVERITIES)
            area = st.text_input("Reason")
            if st.form_submit_button("Register rule"):
                res = eng["anom"].register_detection_rule(
                    {"rule_id": arid, "metric_id": amet,
                     "method": ameth, "threshold_value": athr,
                     "severity": asev},
                    actor=actor, reason=area,
                )
                audit_log(
                    action="register_anomaly_rule",
                    username=actor,
                    module="analytics_advanced",
                )
                if res.get("registered"):
                    st.success(f"Rule {arid} registered (ACTIVE)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition rule state"):
            with st.form("anom_rule_state"):
                rid_t = st.text_input(
                    "Rule ID", key="anom_rs_rid",
                )
                ns = st.selectbox("New state", RULE_STATES)
                rea_t = st.text_input(
                    "Reason", key="anom_rs_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["anom"].transition_rule_state(
                        rid_t, ns, actor=actor, reason=rea_t,
                    )
                    audit_log(
                        action="transition_anomaly_rule_state",
                        username=actor,
                        module="analytics_advanced",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 4: Anomaly observations ----------
    with tabs[3]:
        st.subheader("Anomaly observations")
        st.caption(
            f"Severities: {', '.join(ANOMALY_SEVERITIES)} · "
            f"States: {', '.join(ANOMALY_STATES)} · "
            f"Classifications: {', '.join(ANOMALY_CLASSIFICATIONS)}"
        )
        with st.form("anom_obs"):
            oid = st.text_input("Observation ID")
            orid = st.text_input("Rule ID", key="anom_obs_rid")
            omet = st.text_input("Metric ID", key="anom_obs_met")
            oobs = st.text_input("Observed value")
            oexp = st.text_input("Expected value")
            osev = st.selectbox(
                "Severity", ANOMALY_SEVERITIES, key="anom_obs_sev",
            )
            if st.form_submit_button("Record observation"):
                res = eng["anom"].record_anomaly_observation(
                    {"observation_id": oid, "rule_id": orid,
                     "metric_id": omet, "observed_value": oobs,
                     "expected_value": oexp, "severity": osev},
                    actor=actor,
                )
                audit_log(
                    action="record_anomaly_observation",
                    username=actor,
                    module="analytics_advanced",
                )
                if res.get("recorded"):
                    st.success(f"Observation {oid} recorded (OPEN)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Classify + transition observation"):
            with st.form("anom_classify"):
                cid = st.text_input(
                    "Observation ID", key="anom_cl_oid",
                )
                ccls = st.selectbox(
                    "Classification", ANOMALY_CLASSIFICATIONS,
                )
                ns = st.selectbox(
                    "New state", ANOMALY_STATES,
                    key="anom_cl_state",
                )
                crea = st.text_input(
                    "Reason", key="anom_cl_reason",
                )
                if st.form_submit_button("Apply"):
                    r1 = eng["anom"].classify_anomaly(
                        cid, ccls, actor=actor, reason=crea,
                    )
                    r2 = eng["anom"].transition_observation_state(
                        cid, ns, actor=actor, reason=crea,
                    )
                    audit_log(
                        action="classify_anomaly",
                        username=actor,
                        module="analytics_advanced",
                    )
                    if r1.get("classified") and r2.get("transitioned"):
                        st.success(
                            f"Classified {ccls}, "
                            f"transitioned to {ns}",
                        )
                    else:
                        st.warning(
                            f"classify={r1}, transition={r2}",
                        )

        if st.button("Show high-severity open"):
            hsos = eng["anom"].high_severity_open()
            st.metric("Open HIGH/CRITICAL", len(hsos))
            for h in hsos[:10]:
                st.write(
                    f"• `{h.get('observation_id')}` "
                    f"({h.get('severity')}, "
                    f"{h.get('state')}) "
                    f"— metric {h.get('metric_id')}: "
                    f"{h.get('observed_value')} "
                    f"(expected {h.get('expected_value', 'n/a')})",
                )

    # ---------- Tab 5: Export requests ----------
    with tabs[4]:
        st.subheader("Data export requests (Standard #290)")
        st.caption(
            f"Formats: {', '.join(EXPORT_FORMATS)} · "
            f"PII tiers: {', '.join(PII_TIERS)} · "
            f"Timeout: {DEFAULT_EXPORT_TIMEOUT_SECONDS}s · "
            f"Retention: {DEFAULT_RETENTION_DAYS}d"
        )
        st.warning(
            "CRITICAL_PII exports require a named approver and a "
            "documented reason citing DPA Kenya 2019.",
        )
        with st.form("exp_request"):
            erid = st.text_input("Request ID")
            eds = st.text_input("Dataset ID")
            efmt = st.selectbox("Format", EXPORT_FORMATS)
            edst = st.text_input("Destination")
            epii = st.selectbox("PII tier", PII_TIERS)
            erows = st.number_input(
                "Row count estimate (optional)",
                min_value=0, value=0,
            )
            erea = st.text_input("Reason")
            if st.form_submit_button("Register request"):
                res = eng["exp"].register_export_request(
                    {"request_id": erid, "dataset_id": eds,
                     "format": efmt, "destination": edst,
                     "pii_tier": epii,
                     "row_count_estimate": (
                         int(erows) if erows > 0 else None
                     )},
                    actor=actor, reason=erea,
                )
                audit_log(
                    action="register_data_export_request",
                    username=actor,
                    module="analytics_advanced",
                )
                if res.get("registered"):
                    st.success(f"Request {erid} (REQUESTED)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition request state"):
            with st.form("exp_state"):
                tid = st.text_input(
                    "Request ID", key="exp_st_rid",
                )
                ns = st.selectbox("New state", EXPORT_REQUEST_STATES)
                tre = st.text_input("Reason", key="exp_st_reason")
                if st.form_submit_button("Transition"):
                    res = eng["exp"].transition_request_state(
                        tid, ns, actor=actor, reason=tre,
                    )
                    audit_log(
                        action="transition_export_request_state",
                        username=actor,
                        module="analytics_advanced",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Record execution"):
            with st.form("exp_exec"):
                xid = st.text_input("Execution ID")
                xrid = st.text_input(
                    "Request ID", key="exp_x_rid",
                )
                xoc = st.selectbox(
                    "Outcome", EXPORT_EXECUTION_OUTCOMES,
                )
                xrows = st.number_input(
                    "Rows exported", min_value=0, value=0,
                )
                xbytes = st.number_input(
                    "Bytes exported", min_value=0, value=0,
                )
                xdur = st.number_input(
                    "Duration (s)", min_value=0, value=0,
                )
                if st.form_submit_button("Record"):
                    res = eng["exp"].record_export_execution(
                        {"execution_id": xid, "request_id": xrid,
                         "outcome": xoc,
                         "rows_exported": int(xrows),
                         "bytes_exported": int(xbytes),
                         "duration_seconds": int(xdur)},
                        actor=actor,
                    )
                    audit_log(
                        action="record_export_execution",
                        username=actor,
                        module="analytics_advanced",
                    )
                    if res.get("recorded"):
                        st.success(f"Execution {xid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button("Show CRITICAL_PII pending review"):
            pending = eng["exp"].pii_critical_pending_review()
            st.metric("Pending", len(pending))
            for p in pending[:10]:
                st.write(
                    f"• `{p.get('request_id')}` "
                    f"→ {p.get('destination')} "
                    f"(dataset {p.get('dataset_id')}, "
                    f"~{p.get('row_count_estimate', 'n/a')} rows)",
                )

    # ---------- Tab 6: Integration endpoints ----------
    with tabs[5]:
        st.subheader("Integration endpoints")
        st.caption(f"Types: {', '.join(INTEGRATION_TYPES)}")
        with st.form("ep_form"):
            eid = st.text_input("Endpoint ID")
            ename = st.text_input("Name")
            etype = st.selectbox("Type", INTEGRATION_TYPES)
            eurl = st.text_input("URL")
            eauth = st.selectbox(
                "Auth", ["API_KEY", "OAUTH2_BEARER",
                              "OPENID_CONNECT", "MUTUAL_TLS"],
            )
            ereason = st.text_input("Reason", key="ep_reason")
            if st.form_submit_button("Register endpoint"):
                res = eng["exp"].register_integration_endpoint(
                    {"endpoint_id": eid, "name": ename,
                     "integration_type": etype, "url": eurl,
                     "auth_method": eauth},
                    actor=actor, reason=ereason,
                )
                audit_log(
                    action="register_integration_endpoint",
                    username=actor,
                    module="analytics_advanced",
                )
                if res.get("registered"):
                    st.success(f"Endpoint {eid} registered")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 7: Metrics ----------
    with tabs[6]:
        st.subheader("Metrics")
        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
        )

        if st.button("Refresh"):
            mn = eng["nlq"].query_metrics(days=int(ndays))
            ma = eng["anom"].anomaly_metrics(days=int(ndays))
            me = eng["exp"].export_metrics(days=int(ndays))

            st.markdown("**NLQ (#288):**")
            cols = st.columns(4)
            cols[0].metric("Requests", mn["total_requests"])
            cols[1].metric("Executed", mn["executed"])
            cols[2].metric("Rejected", mn["rejected"])
            cols[3].metric(
                "Success rate", f"{mn['success_rate_pct']}%",
            )

            st.markdown("**Anomaly (#289):**")
            cols = st.columns(4)
            cols[0].metric(
                "Observations", ma["total_observations"],
            )
            cols[1].metric(
                "Critical",
                ma["per_severity"].get("CRITICAL", 0),
            )
            cols[2].metric(
                "Resolved",
                ma["per_state"].get("RESOLVED", 0),
            )
            cols[3].metric(
                "Data quality rate",
                f"{ma['data_quality_rate_pct']}%",
            )

            st.markdown("**Data Export (#290):**")
            cols = st.columns(4)
            cols[0].metric("Executions", me["total_executions"])
            cols[1].metric("Success", me["success"])
            cols[2].metric("Failed", me["failed"])
            cols[3].metric(
                "Bytes (MB)",
                f"{me['total_bytes_exported'] / 1_000_000:,.1f}",
            )


main()
