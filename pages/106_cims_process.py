"""
Phase 2B — CIMS Batch 2: Process Intelligence & Prediction (pages/106)
=================================================================
v10.291 — covers Standards #169 (Process Intelligence & Digital Twin),
#170 (Predictive Dropout Prevention), #174 (Next Best Action),
#175 (Automated Exception Management).

Audience: Operations, MIS analysts, RM, contact centre supervisors.

Tab map (7 tabs at G4 ceiling — planned upfront):
  1. Process twins             — register + state transitions + summary
  2. Process events            — record step events + bottleneck report
  3. Dropout signals + scoring — register signals + Cat D rule_based scoring
  4. Interventions             — register + outcome + save-rate metrics
  5. NBA recommendations       — rank + record + acceptance metrics
  6. Exception lifecycle       — register + transitions + escalations
  7. Resolution + SLA report   — record resolution + SLA breach report
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
from utils.cims_process_intelligence import (
    ProcessIntelligenceEngine,
    PROCESS_INSTANCE_STATES, STEP_EVENT_TYPES, STEP_OUTCOMES,
    BOTTLENECK_TYPES,
    DEFAULT_BOTTLENECK_DURATION_PERCENTILE,
    DEFAULT_BOTTLENECK_RETRY_THRESHOLD,
    DEFAULT_DIGITAL_TWIN_REFRESH_SECONDS,
)
from utils.cims_dropout_prevention import (
    DropoutPreventionEngine,
    DROPOUT_RISK_TIERS, SIGNAL_STATES,
    INTERVENTION_TYPES, INTERVENTION_OUTCOMES,
    DROPOUT_RISK_FACTOR_WEIGHTS_PCT,
    DEFAULT_PREDICTION_HORIZON_HOURS,
    DEFAULT_INTERVENTION_COOLDOWN_HOURS,
)
from utils.cims_next_best_action import (
    NextBestActionEngine,
    NBA_ACTION_TYPES, NBA_RULE_STATES,
    RECOMMENDATION_OUTCOMES, ACTION_PRIORITY_TIERS,
    NBA_RULE_FACTOR_WEIGHTS_PCT,
    DEFAULT_TOP_N_RECOMMENDATIONS,
    DEFAULT_RECOMMENDATION_TTL_HOURS,
)
from utils.cims_exception_management import (
    ExceptionManagementEngine,
    EXCEPTION_SEVERITIES, EXCEPTION_STATES,
    ESCALATION_TARGETS, RESOLUTION_OUTCOMES,
    EXCEPTION_CATEGORIES, SLA_TARGETS_HOURS,
    DEFAULT_AUTO_ESCALATION_THRESHOLD_HOURS_FOR_HIGH,
    DEFAULT_REASSIGNMENT_LIMIT,
)

# Phase 3 standing rule: do NOT silently swallow require_access
# failures. Pages must fail loud so misconfigured access is visible.
from pages._access import require_access
require_access("operations.cims_process")


@st.cache_resource
def _engines():
    return {
        "pi": ProcessIntelligenceEngine(),
        "dp": DropoutPreventionEngine(),
        "nba": NextBestActionEngine(),
        "ex": ExceptionManagementEngine(),
    }


def main():
    st.title("🔄 CIMS — Process Intelligence & Prediction")
    st.caption(
        "v10.291 · Standards #169 + #170 + #174 + #175 · "
        "Digital twin, dropout prevention, next best action, "
        "automated exceptions"
    )

    eng = _engines()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "🌐 Process twins",
        "📊 Events + bottlenecks",
        "🎯 Dropout signals",
        "📞 Interventions",
        "💡 Next best action",
        "⚠️ Exception lifecycle",
        "📈 Resolution + SLA",
    ])

    # ---------- Tab 1: Process twins ----------
    with tabs[0]:
        st.subheader("Digital twin (Standard #169)")
        st.caption(
            f"States: {', '.join(PROCESS_INSTANCE_STATES)} · "
            f"Refresh: {DEFAULT_DIGITAL_TWIN_REFRESH_SECONDS}s"
        )
        with st.form("twin_def"):
            pid = st.text_input("Process ID")
            pname = st.text_input("Process name")
            pti = st.text_input("Instruction type")
            preason = st.text_input("Reason")
            if st.form_submit_button("Register process definition"):
                res = eng["pi"].register_process_definition(
                    {"process_id": pid, "name": pname,
                     "instruction_type": pti,
                     "expected_step_count": 0},
                    actor=actor, reason=preason,
                )
                audit_log(
                    action="register_process_definition",
                    username=actor, module="cims_process",
                )
                if res.get("registered"):
                    st.success(f"Definition {pid} registered")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Register process instance"):
            with st.form("inst_form"):
                iid = st.text_input("Instance ID")
                ipid = st.text_input("Process ID", key="inst_pid")
                isid = st.text_input("Capture session ID")
                ireason = st.text_input("Reason", key="inst_reason")
                if st.form_submit_button("Register instance"):
                    res = eng["pi"].register_process_instance(
                        {"instance_id": iid, "process_id": ipid,
                         "capture_session_id": isid},
                        actor=actor, reason=ireason,
                    )
                    audit_log(
                        action="register_process_instance",
                        username=actor, module="cims_process",
                    )
                    if res.get("registered"):
                        st.success(f"Instance {iid} registered (PENDING)")
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Transition instance state"):
            with st.form("inst_state"):
                tid = st.text_input(
                    "Instance ID", key="ts_iid",
                )
                ns = st.selectbox(
                    "New state", PROCESS_INSTANCE_STATES,
                )
                tr = st.text_input(
                    "Reason", key="ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["pi"].transition_instance_state(
                        tid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_process_instance_state",
                        username=actor, module="cims_process",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        sf = st.selectbox(
            "List instances by state",
            PROCESS_INSTANCE_STATES, key="filter_inst",
        )
        if st.button("List"):
            insts = eng["pi"].instances_in_state(sf)
            st.metric(sf, len(insts))
            for i in insts[:10]:
                st.write(
                    f"• `{i.get('instance_id')}` "
                    f"(process {i.get('process_id')}) "
                    f"— session {i.get('capture_session_id')}",
                )

    # ---------- Tab 2: Events + bottlenecks ----------
    with tabs[1]:
        st.subheader("Step events and bottlenecks")
        st.caption(
            f"Event types: {', '.join(STEP_EVENT_TYPES)} · "
            f"Outcomes: {', '.join(STEP_OUTCOMES)}"
        )
        with st.form("step_event"):
            eid = st.text_input("Event ID")
            eiid = st.text_input("Instance ID")
            estep = st.text_input("Step name")
            eet = st.selectbox("Event type", STEP_EVENT_TYPES)
            eoc = st.selectbox("Outcome", STEP_OUTCOMES)
            edur = st.number_input(
                "Duration (ms)", min_value=0, value=0,
            )
            if st.form_submit_button("Record event"):
                res = eng["pi"].record_step_event(
                    {"event_id": eid, "instance_id": eiid,
                     "step_name": estep, "event_type": eet,
                     "outcome": eoc,
                     "duration_ms": int(edur)},
                    actor=actor,
                )
                audit_log(
                    action="record_step_event",
                    username=actor, module="cims_process",
                )
                if res.get("recorded"):
                    st.success(f"Event {eid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Bottleneck window (days)", min_value=1, value=30,
            key="bn_days",
        )
        bn_pid = st.text_input(
            "Process ID (optional filter)", key="bn_pid",
        )
        if st.button("Bottleneck report"):
            r = eng["pi"].bottleneck_summary(
                process_id=(bn_pid or None),
                days=int(ndays),
            )
            st.metric("Steps observed", r.get("step_count", 0))
            st.metric(
                "Bottlenecks",
                r.get("bottleneck_count", 0),
            )
            for b in r.get("bottlenecks", [])[:10]:
                st.write(
                    f"• `{b.get('step_name')}` "
                    f"({b.get('bottleneck_type')}) — "
                    f"{b.get('detail', '')}",
                )

    # ---------- Tab 3: Dropout signals + scoring ----------
    with tabs[2]:
        st.subheader("Predictive dropout (Standard #170)")
        st.caption(
            f"Risk tiers: {', '.join(DROPOUT_RISK_TIERS)} · "
            f"Horizon: {DEFAULT_PREDICTION_HORIZON_HOURS}h · "
            f"Cooldown: {DEFAULT_INTERVENTION_COOLDOWN_HOURS}h"
        )
        st.markdown(
            "**Rule-based factor weights (sum 100):**",
        )
        st.write(", ".join(
            f"{k}={v}%"
            for k, v in DROPOUT_RISK_FACTOR_WEIGHTS_PCT.items()
        ))
        with st.expander("Score dropout risk (rule_based, no ML)"):
            with st.form("dp_score"):
                sd = st.number_input(
                    "Session duration (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                ch = st.number_input(
                    "Channel hops (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                pd_ = st.number_input(
                    "Process deviation (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                ha = st.number_input(
                    "Historical abandonment (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                ic = st.number_input(
                    "Instruction complexity (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                if st.form_submit_button("Score"):
                    r = eng["dp"].score_dropout_risk({
                        "session_duration": int(sd),
                        "channel_hops": int(ch),
                        "process_deviation": int(pd_),
                        "historical_abandonment": int(ha),
                        "instruction_complexity": int(ic),
                    })
                    cols = st.columns(3)
                    cols[0].metric(
                        "Rule-based score",
                        r["rule_based_score"],
                    )
                    cols[1].metric(
                        "Tier", r["rule_based_tier"],
                    )
                    cols[2].metric("Basis", r["basis"])
                    st.caption(r.get("reason", ""))

        with st.form("dp_signal"):
            sid = st.text_input("Signal ID")
            csid = st.text_input("Capture session ID")
            score = st.number_input(
                "Risk score (0-100)",
                min_value=0, max_value=100, value=0,
            )
            tier = st.selectbox("Risk tier", DROPOUT_RISK_TIERS)
            narr = st.text_area("Narrative")
            sreason = st.text_input("Reason", key="dp_reason")
            if st.form_submit_button("Register signal"):
                res = eng["dp"].register_dropout_signal(
                    {"signal_id": sid,
                     "capture_session_id": csid,
                     "risk_score": int(score),
                     "risk_tier": tier,
                     "narrative": narr},
                    actor=actor, reason=sreason,
                )
                audit_log(
                    action="register_dropout_signal",
                    username=actor, module="cims_process",
                )
                if res.get("registered"):
                    st.success(f"Signal {sid} registered (DETECTED)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition signal state"):
            with st.form("dp_state"):
                tsid = st.text_input(
                    "Signal ID", key="dp_ts_sid",
                )
                ns = st.selectbox("New state", SIGNAL_STATES)
                tr = st.text_input(
                    "Reason", key="dp_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["dp"].transition_signal_state(
                        tsid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_dropout_signal_state",
                        username=actor, module="cims_process",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 4: Interventions ----------
    with tabs[3]:
        st.subheader("Interventions and outcomes")
        st.caption(
            f"Types: {', '.join(INTERVENTION_TYPES)} · "
            f"Outcomes: {', '.join(INTERVENTION_OUTCOMES)}"
        )
        with st.form("int_form"):
            iid = st.text_input("Intervention ID")
            isid = st.text_input(
                "Signal ID", key="int_sid",
            )
            itype = st.selectbox(
                "Intervention type", INTERVENTION_TYPES,
            )
            inarr = st.text_area("Narrative")
            irea = st.text_input("Reason", key="int_reason")
            if st.form_submit_button("Register intervention"):
                res = eng["dp"].register_intervention(
                    {"intervention_id": iid,
                     "signal_id": isid,
                     "intervention_type": itype,
                     "narrative": inarr},
                    actor=actor, reason=irea,
                )
                audit_log(
                    action="register_intervention",
                    username=actor, module="cims_process",
                )
                if res.get("registered"):
                    st.success(f"Intervention {iid} registered")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Record intervention outcome"):
            with st.form("int_out"):
                oid = st.text_input("Outcome ID")
                oiid = st.text_input(
                    "Intervention ID", key="int_o_iid",
                )
                oc = st.selectbox(
                    "Outcome", INTERVENTION_OUTCOMES,
                )
                onarr = st.text_area(
                    "Narrative", key="int_o_narr",
                )
                if st.form_submit_button("Record outcome"):
                    res = eng["dp"].record_intervention_outcome(
                        {"outcome_id": oid,
                         "intervention_id": oiid,
                         "outcome": oc,
                         "narrative": onarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_intervention_outcome",
                        username=actor, module="cims_process",
                    )
                    if res.get("recorded"):
                        st.success(f"Outcome {oid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Window (days)", min_value=1, value=30, key="int_days",
        )
        if st.button("Intervention metrics"):
            m = eng["dp"].intervention_metrics(days=int(ndays))
            cols = st.columns(3)
            cols[0].metric(
                "Outcomes", m["total_outcomes"],
            )
            cols[1].metric(
                "Save rate",
                f"{m['save_rate_pct']}%",
            )
            for oc, n in m.get("per_outcome", {}).items():
                st.write(f"• `{oc}`: {n}")

    # ---------- Tab 5: Next best action ----------
    with tabs[4]:
        st.subheader("Next best action (Standard #174)")
        st.caption(
            f"Actions: {', '.join(NBA_ACTION_TYPES)} · "
            f"Top N: {DEFAULT_TOP_N_RECOMMENDATIONS} · "
            f"TTL: {DEFAULT_RECOMMENDATION_TTL_HOURS}h"
        )
        st.markdown("**Rule-based weights (sum 100):**")
        st.write(", ".join(
            f"{k}={v}%"
            for k, v in NBA_RULE_FACTOR_WEIGHTS_PCT.items()
        ))

        with st.expander("Rank next actions (rule_based)"):
            with st.form("nba_rank"):
                fit = st.number_input(
                    "Instruction-type fit (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                ss = st.number_input(
                    "Session state (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                dr = st.number_input(
                    "Dropout risk (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                hist = st.number_input(
                    "Customer history (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                cp = st.number_input(
                    "Channel preference (0-100)",
                    min_value=0, max_value=100, value=0,
                )
                if st.form_submit_button("Rank"):
                    r = eng["nba"].rank_next_actions({
                        "instruction_type_fit": int(fit),
                        "session_state": int(ss),
                        "dropout_risk": int(dr),
                        "customer_history": int(hist),
                        "channel_preference": int(cp),
                    })
                    st.metric("Basis", r["basis"])
                    st.markdown(
                        f"**Top {DEFAULT_TOP_N_RECOMMENDATIONS}:**",
                    )
                    for rec in r["rule_based_rankings"]:
                        st.write(
                            f"#{rec['rank']} `{rec['action_type']}` "
                            f"(score {rec['score']}, "
                            f"{rec['priority']})",
                        )

        with st.form("nba_rule"):
            rid = st.text_input("Rule ID")
            rname = st.text_input("Name")
            rat = st.selectbox(
                "Action type", NBA_ACTION_TYPES,
            )
            rit = st.text_input("Instruction type")
            rdp = st.selectbox(
                "Default priority", ACTION_PRIORITY_TIERS,
            )
            rrea = st.text_input("Reason", key="nba_reason")
            if st.form_submit_button("Register rule"):
                res = eng["nba"].register_nba_rule(
                    {"rule_id": rid, "name": rname,
                     "action_type": rat, "instruction_type": rit,
                     "default_priority": rdp},
                    actor=actor, reason=rrea,
                )
                audit_log(
                    action="register_nba_rule",
                    username=actor, module="cims_process",
                )
                if res.get("registered"):
                    st.success(f"Rule {rid} registered (ACTIVE)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Record recommendation outcome"):
            with st.form("nba_out"):
                oid = st.text_input("Outcome ID", key="nba_oid")
                orid = st.text_input(
                    "Recommendation ID", key="nba_orid",
                )
                oc = st.selectbox(
                    "Outcome", RECOMMENDATION_OUTCOMES,
                )
                onarr = st.text_area(
                    "Narrative", key="nba_onarr",
                )
                if st.form_submit_button("Record"):
                    res = eng["nba"].record_recommendation_outcome(
                        {"outcome_id": oid,
                         "recommendation_id": orid,
                         "outcome": oc,
                         "narrative": onarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_recommendation_outcome",
                        username=actor, module="cims_process",
                    )
                    if res.get("recorded"):
                        st.success(f"Outcome {oid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Window (days)", min_value=1, value=30, key="nba_days",
        )
        if st.button("NBA metrics"):
            m = eng["nba"].nba_metrics(days=int(ndays))
            cols = st.columns(2)
            cols[0].metric(
                "Total outcomes", m["total_outcomes"],
            )
            cols[1].metric(
                "Acceptance rate",
                f"{m['acceptance_rate_pct']}%",
            )
            for oc, n in m.get("per_outcome", {}).items():
                st.write(f"• `{oc}`: {n}")

    # ---------- Tab 6: Exception lifecycle ----------
    with tabs[5]:
        st.subheader("Exception lifecycle (Standard #175)")
        st.caption(
            f"Categories: {', '.join(EXCEPTION_CATEGORIES)} · "
            f"Severities: {', '.join(EXCEPTION_SEVERITIES)} · "
            f"States: {', '.join(EXCEPTION_STATES)}"
        )
        st.markdown(
            f"**SLA targets (hours):** "
            f"LOW={SLA_TARGETS_HOURS['LOW']}, "
            f"MEDIUM={SLA_TARGETS_HOURS['MEDIUM']}, "
            f"HIGH={SLA_TARGETS_HOURS['HIGH']}, "
            f"CRITICAL={SLA_TARGETS_HOURS['CRITICAL']}",
        )

        with st.form("exc_form"):
            eid = st.text_input("Exception ID")
            ecat = st.selectbox(
                "Category", EXCEPTION_CATEGORIES,
            )
            esev = st.selectbox(
                "Severity", EXCEPTION_SEVERITIES,
            )
            enarr = st.text_area("Narrative")
            elsid = st.text_input(
                "Linked session ID (optional)",
            )
            ereason = st.text_input("Reason", key="exc_reason")
            if st.form_submit_button("Register exception"):
                res = eng["ex"].register_exception(
                    {"exception_id": eid,
                     "exception_category": ecat,
                     "severity": esev, "narrative": enarr,
                     "linked_session_id": elsid},
                    actor=actor, reason=ereason,
                )
                audit_log(
                    action="register_exception",
                    username=actor, module="cims_process",
                )
                if res.get("registered"):
                    st.success(
                        f"Exception {eid} registered (OPEN, "
                        f"SLA target {res.get('sla_target_hours')}h)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition exception state"):
            with st.form("exc_state"):
                teid = st.text_input(
                    "Exception ID", key="exc_ts_eid",
                )
                ns = st.selectbox(
                    "New state", EXCEPTION_STATES,
                )
                tr = st.text_input(
                    "Reason", key="exc_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["ex"].transition_exception_state(
                        teid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_exception_state",
                        username=actor, module="cims_process",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Record escalation"):
            with st.form("esc_form"):
                escid = st.text_input("Escalation ID")
                eseid = st.text_input(
                    "Exception ID", key="esc_eid",
                )
                etgt = st.selectbox(
                    "Target", ESCALATION_TARGETS,
                )
                etrig = st.selectbox(
                    "Trigger", ["manual", "auto"],
                )
                enarr = st.text_area(
                    "Narrative", key="esc_narr",
                )
                if st.form_submit_button("Record"):
                    res = eng["ex"].record_escalation(
                        {"escalation_id": escid,
                         "exception_id": eseid,
                         "target": etgt,
                         "trigger": etrig,
                         "narrative": enarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_escalation",
                        username=actor, module="cims_process",
                    )
                    if res.get("recorded"):
                        st.success(f"Escalation {escid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        sf = st.selectbox(
            "Filter open by severity",
            ["(all)"] + list(EXCEPTION_SEVERITIES),
            key="exc_filter",
        )
        if st.button("Show open exceptions"):
            sev = None if sf == "(all)" else sf
            opens = eng["ex"].open_exceptions_by_severity(sev)
            st.metric("Open", len(opens))
            for e in opens[:10]:
                st.write(
                    f"• `{e.get('exception_id')}` "
                    f"({e.get('severity')}, "
                    f"{e.get('state')}) "
                    f"— {e.get('exception_category')}: "
                    f"{e.get('narrative', '')[:80]}",
                )

    # ---------- Tab 7: Resolution + SLA ----------
    with tabs[6]:
        st.subheader("Resolution + SLA breach report")
        st.caption(
            f"Resolution outcomes: {', '.join(RESOLUTION_OUTCOMES)} · "
            f"Auto-escalation HIGH threshold: "
            f"{DEFAULT_AUTO_ESCALATION_THRESHOLD_HOURS_FOR_HIGH}h · "
            f"Reassignment limit: {DEFAULT_REASSIGNMENT_LIMIT}"
        )
        with st.form("res_form"):
            rid = st.text_input("Resolution ID")
            reid = st.text_input(
                "Exception ID", key="res_eid",
            )
            roc = st.selectbox(
                "Outcome", RESOLUTION_OUTCOMES,
            )
            rnarr = st.text_area("Narrative")
            if st.form_submit_button("Record resolution"):
                res = eng["ex"].record_resolution(
                    {"resolution_id": rid,
                     "exception_id": reid,
                     "outcome": roc,
                     "narrative": rnarr},
                    actor=actor,
                )
                audit_log(
                    action="record_resolution",
                    username=actor, module="cims_process",
                )
                if res.get("recorded"):
                    st.success(f"Resolution {rid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="sla_days",
        )
        if st.button("SLA breach report"):
            r = eng["ex"].sla_breach_report(days=int(ndays))
            cols = st.columns(3)
            cols[0].metric(
                "Exceptions", r["exceptions_in_window"],
            )
            cols[1].metric("Breaches", r["breach_count"])
            cols[2].metric(
                "Breach %", f"{r['breach_pct']}%",
            )
            for b in r.get("breaches", [])[:10]:
                st.write(
                    f"• `{b.get('exception_id')}` "
                    f"({b.get('severity')}) — "
                    f"target {b.get('sla_target_hours')}h, "
                    f"actual {b.get('actual_hours')}h, "
                    f"{b.get('outcome')}",
                )


main()
