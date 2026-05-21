"""
Phase 2B — CIMS Batch 3: Compliance & Audit (pages/107)
=================================================================
v10.292 — covers Standards #171 (Regulatory SLA Enforcement),
#172 (Secure Document & PAN Management), #176 (Audit-Ready
Instruction History), #178 (Agent Workspace).

Audience: Compliance officers, operations leads, examiners
(read-only), agent workspace users.

Tab map (7 tabs at G4 ceiling — planned upfront):
  1. SLA definitions          — register + state transitions
  2. SLA obligations + breach  — register + state + breach + upcoming
  3. PAN tokens               — register + state transitions + inventory
  4. Documents + access events — register + state + access events + summary
  5. Audit history             — record + correction + history-by-session
  6. Examiner queries + reviews — record + summary
  7. Agent workspace           — agents + queue + actions + workload
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
from utils.cims_regulatory_sla import (
    RegulatorySLAEngine,
    REGULATORY_FRAMEWORKS, SLA_DEFINITION_STATES,
    OBLIGATION_STATES, OBLIGATION_EVENT_TYPES,
    SLA_BREACH_SEVERITIES,
    INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS,
    DEFAULT_REMINDER_AT_HOURS_REMAINING,
    DEFAULT_APPROACHING_AT_HOURS_REMAINING,
)
from utils.cims_secure_pan_documents import (
    SecurePANDocumentEngine,
    PAN_TOKEN_STATES, DOCUMENT_STATES,
    DOCUMENT_TYPES, ACCESS_EVENT_TYPES,
    PAN_FIELD_KINDS,
    DEFAULT_TOKEN_TTL_DAYS,
    DEFAULT_DOCUMENT_RETENTION_YEARS,
    PCI_DSS_RAW_PAN_PROHIBITED,
)
from utils.cims_audit_ready_history import (
    AuditReadyHistoryEngine,
    HISTORY_RECORD_KINDS, ALLOWED_CORRECTION_REASONS,
    EXAMINER_QUERY_TYPES, EXAMINER_RESPONSE_OUTCOMES,
    COMPLIANCE_REVIEW_OUTCOMES,
    DEFAULT_RETENTION_YEARS,
)
from utils.cims_agent_workspace import (
    AgentWorkspaceEngine,
    AGENT_STATES, WORK_ITEM_STATES,
    WORK_ITEM_PRIORITIES, WORK_ITEM_SOURCES,
    AGENT_ACTION_KINDS, AGENT_SKILL_TAGS,
    DEFAULT_QUEUE_REASSIGNMENT_HOURS,
    DEFAULT_AGENT_BREAK_LIMIT_MINUTES,
    DEFAULT_QUEUE_DEPTH_THRESHOLD,
)

# Phase 3 standing rule: do NOT silently swallow require_access
# failures. Pages must fail loud so misconfigured access is visible.
from pages._access import require_access
require_access("operations.cims_compliance")


@st.cache_resource
def _engines():
    return {
        "sla": RegulatorySLAEngine(),
        "pan": SecurePANDocumentEngine(),
        "hist": AuditReadyHistoryEngine(),
        "agent": AgentWorkspaceEngine(),
    }


def main():
    st.title("⚖️ CIMS — Compliance & Audit")
    st.caption(
        "v10.292 · Standards #171 + #172 + #176 + #178 · "
        "Regulatory SLA, secure PAN/documents, audit-ready history, "
        "agent workspace"
    )

    eng = _engines()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "📋 SLA definitions",
        "⏱️ SLA obligations",
        "🔐 PAN tokens",
        "📄 Documents",
        "📚 Audit history",
        "🔍 Examiner queries",
        "👥 Agent workspace",
    ])

    # ---------- Tab 1: SLA definitions ----------
    with tabs[0]:
        st.subheader("Regulatory SLA definitions (Standard #171)")
        st.caption(
            f"Frameworks: {', '.join(REGULATORY_FRAMEWORKS)} · "
            f"States: {', '.join(SLA_DEFINITION_STATES)}"
        )
        st.markdown(
            "**Default deadlines (hours):** " + " · ".join(
                f"{k}={v}h"
                for k, v in INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS.items()
            ),
        )
        with st.form("sla_def"):
            did = st.text_input("Definition ID")
            dname = st.text_input("Name")
            dfr = st.selectbox("Framework", REGULATORY_FRAMEWORKS)
            dit = st.text_input("Instruction type")
            dh = st.number_input(
                "Deadline (hours)", min_value=1, value=240,
            )
            dnarr = st.text_area("Narrative")
            drea = st.text_input("Reason", key="sla_def_reason")
            if st.form_submit_button("Register definition"):
                res = eng["sla"].register_sla_definition(
                    {"definition_id": did, "name": dname,
                     "framework": dfr, "instruction_type": dit,
                     "deadline_hours": int(dh),
                     "narrative": dnarr},
                    actor=actor, reason=drea,
                )
                audit_log(
                    action="register_sla_definition",
                    username=actor, module="cims_compliance",
                )
                if res.get("registered"):
                    st.success(f"Definition {did} registered (DRAFT)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition definition state"):
            with st.form("sla_def_state"):
                tid = st.text_input(
                    "Definition ID", key="sla_def_ts_id",
                )
                ns = st.selectbox(
                    "New state", SLA_DEFINITION_STATES,
                )
                tr = st.text_input(
                    "Reason", key="sla_def_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["sla"].transition_definition_state(
                        tid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_sla_definition_state",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 2: SLA obligations + breach ----------
    with tabs[1]:
        st.subheader("SLA obligations and breach report")
        st.caption(
            f"States: {', '.join(OBLIGATION_STATES)} · "
            f"Reminder: {DEFAULT_REMINDER_AT_HOURS_REMAINING}h · "
            f"Approaching: {DEFAULT_APPROACHING_AT_HOURS_REMAINING}h · "
            f"Severities: {', '.join(SLA_BREACH_SEVERITIES)}"
        )
        with st.form("sla_obl"):
            oid = st.text_input("Obligation ID")
            odid = st.text_input(
                "Definition ID", key="sla_obl_def",
            )
            olsid = st.text_input("Linked session ID")
            odeadline = st.text_input(
                "Deadline at (ISO timestamp)",
            )
            ornarr = st.text_area(
                "Narrative", key="sla_obl_narr",
            )
            orea = st.text_input(
                "Reason", key="sla_obl_reason",
            )
            if st.form_submit_button("Register obligation"):
                res = eng["sla"].register_sla_obligation(
                    {"obligation_id": oid,
                     "definition_id": odid,
                     "linked_session_id": olsid,
                     "deadline_at": odeadline},
                    actor=actor, reason=orea,
                )
                audit_log(
                    action="register_sla_obligation",
                    username=actor, module="cims_compliance",
                )
                if res.get("registered"):
                    st.success(f"Obligation {oid} registered (PENDING)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition obligation state"):
            with st.form("sla_obl_state"):
                tid = st.text_input(
                    "Obligation ID", key="sla_obl_ts_id",
                )
                ns = st.selectbox(
                    "New state", OBLIGATION_STATES,
                )
                tr = st.text_input(
                    "Reason", key="sla_obl_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["sla"].transition_obligation_state(
                        tid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_sla_obligation_state",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Record obligation event"):
            with st.form("sla_event"):
                eid = st.text_input("Event ID", key="sla_ev_id")
                eoid = st.text_input(
                    "Obligation ID", key="sla_ev_oid",
                )
                eet = st.selectbox(
                    "Event type", OBLIGATION_EVENT_TYPES,
                )
                enarr = st.text_area(
                    "Narrative", key="sla_ev_narr",
                )
                if st.form_submit_button("Record event"):
                    res = eng["sla"].record_obligation_event(
                        {"event_id": eid, "obligation_id": eoid,
                         "event_type": eet, "narrative": enarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_sla_obligation_event",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("recorded"):
                        st.success(f"Event {eid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        cols = st.columns(2)
        with cols[0]:
            ndays = st.number_input(
                "Breach window (days)", min_value=1, value=30,
                key="sla_breach_days",
            )
            if st.button("Breach report"):
                r = eng["sla"].breach_report(days=int(ndays))
                cs = st.columns(3)
                cs[0].metric(
                    "Obligations", r["obligations_in_window"],
                )
                cs[1].metric("Breaches", r["breach_count"])
                cs[2].metric(
                    "Breach %", f"{r['breach_pct']}%",
                )
                for b in r.get("breached", [])[:10]:
                    st.write(
                        f"• `{b.get('obligation_id')}` "
                        f"(deadline {b.get('deadline_at')[:19]}) "
                        f"— {b.get('outcome')}",
                    )
        with cols[1]:
            wh = st.number_input(
                "Upcoming within (hours)", min_value=1, value=24,
                key="sla_upcoming_hours",
            )
            if st.button("Upcoming deadlines"):
                up = eng["sla"].upcoming_deadlines(within_hours=int(wh))
                st.metric("Upcoming", len(up))
                for u in up[:10]:
                    st.write(
                        f"• `{u.get('obligation_id')}` "
                        f"({u.get('hours_remaining')}h remaining) "
                        f"— session {u.get('linked_session_id')}",
                    )

    # ---------- Tab 3: PAN tokens ----------
    with tabs[2]:
        st.subheader("Tokenised PAN registry (Standard #172)")
        st.caption(
            f"Kinds: {', '.join(PAN_FIELD_KINDS)} · "
            f"States: {', '.join(PAN_TOKEN_STATES)} · "
            f"TTL: {DEFAULT_TOKEN_TTL_DAYS}d · "
            f"PCI raw-PAN prohibited: {PCI_DSS_RAW_PAN_PROHIBITED}"
        )
        st.warning(
            "🚫 Engine rejects any field that looks like a raw PAN "
            "(13–19 digit Luhn-valid string, including embedded). "
            "Use TOKEN, LAST_FOUR (4 digits), or BIN (6 digits)."
        )
        with st.form("pan_token"):
            tid = st.text_input("Token ID")
            tval = st.text_input("Token value")
            tk = st.selectbox("Kind", PAN_FIELD_KINDS)
            tcust = st.text_input("Owner customer ID")
            tsch = st.text_input("Scheme (optional)")
            trea = st.text_input("Reason", key="pan_reason")
            if st.form_submit_button("Register token"):
                res = eng["pan"].register_token(
                    {"token_id": tid, "token_value": tval,
                     "kind": tk, "owner_customer_id": tcust,
                     "scheme": tsch},
                    actor=actor, reason=trea,
                )
                audit_log(
                    action="register_pan_token",
                    username=actor, module="cims_compliance",
                )
                if res.get("registered"):
                    st.success(f"Token {tid} registered (ACTIVE)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition token state"):
            with st.form("pan_state"):
                tid = st.text_input("Token ID", key="pan_ts_id")
                ns = st.selectbox(
                    "New state", PAN_TOKEN_STATES,
                )
                tr = st.text_input(
                    "Reason", key="pan_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["pan"].transition_token_state(
                        tid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_pan_token_state",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button("PAN inventory summary"):
            s = eng["pan"].pan_inventory_summary()
            cs = st.columns(2)
            cs[0].metric("Total tokens", s["total_tokens"])
            cs[1].metric("TTL (days)", s["token_ttl_days"])
            st.markdown("**Per state:**")
            for k, v in s.get("per_state", {}).items():
                st.write(f"• `{k}`: {v}")
            st.markdown("**Per kind:**")
            for k, v in s.get("per_kind", {}).items():
                st.write(f"• `{k}`: {v}")

    # ---------- Tab 4: Documents + access events ----------
    with tabs[3]:
        st.subheader("Document vault registry")
        st.caption(
            f"Types: {', '.join(DOCUMENT_TYPES)} · "
            f"States: {', '.join(DOCUMENT_STATES)} · "
            f"Retention: {DEFAULT_DOCUMENT_RETENTION_YEARS}y"
        )
        with st.form("doc_form"):
            did = st.text_input("Document ID")
            dt = st.selectbox(
                "Document type", DOCUMENT_TYPES,
            )
            dvref = st.text_input("Vault reference")
            dcust = st.text_input(
                "Owner customer ID", key="doc_cust",
            )
            dlsid = st.text_input(
                "Linked session ID (optional)",
            )
            dnarr = st.text_area(
                "Narrative", key="doc_narr",
            )
            drea = st.text_input("Reason", key="doc_reason")
            if st.form_submit_button("Register document"):
                res = eng["pan"].register_document(
                    {"document_id": did,
                     "document_type": dt,
                     "vault_reference": dvref,
                     "owner_customer_id": dcust,
                     "linked_session_id": dlsid,
                     "narrative": dnarr},
                    actor=actor, reason=drea,
                )
                audit_log(
                    action="register_document",
                    username=actor, module="cims_compliance",
                )
                if res.get("registered"):
                    st.success(f"Document {did} registered (UPLOADED)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition document state"):
            with st.form("doc_state"):
                tid = st.text_input("Document ID", key="doc_ts_id")
                ns = st.selectbox(
                    "New state", DOCUMENT_STATES,
                )
                tr = st.text_input(
                    "Reason", key="doc_ts_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["pan"].transition_document_state(
                        tid, ns, actor=actor, reason=tr,
                    )
                    audit_log(
                        action="transition_document_state",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Record access event"):
            with st.form("acc_form"):
                eid = st.text_input("Event ID", key="acc_id")
                et = st.selectbox(
                    "Event type", ACCESS_EVENT_TYPES,
                )
                esid = st.text_input("Subject ID (token or document)")
                enarr = st.text_area(
                    "Narrative", key="acc_narr",
                )
                if st.form_submit_button("Record event"):
                    res = eng["pan"].record_access_event(
                        {"event_id": eid, "event_type": et,
                         "subject_id": esid, "narrative": enarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_access_event",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("recorded"):
                        st.success(f"Event {eid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button("Document inventory summary"):
            s = eng["pan"].document_inventory_summary()
            cs = st.columns(2)
            cs[0].metric(
                "Total documents", s["total_documents"],
            )
            cs[1].metric(
                "Retention (years)", s["retention_years"],
            )
            st.markdown("**Per state:**")
            for k, v in s.get("per_state", {}).items():
                st.write(f"• `{k}`: {v}")

    # ---------- Tab 5: Audit history ----------
    with tabs[4]:
        st.subheader("Append-only audit history (Standard #176)")
        st.caption(
            f"Kinds: {', '.join(HISTORY_RECORD_KINDS)} · "
            f"Retention: {DEFAULT_RETENTION_YEARS}y · "
            f"Records are immutable; corrections supersede"
        )
        with st.form("hist_rec"):
            rid = st.text_input("Record ID")
            rk = st.selectbox(
                "Kind", HISTORY_RECORD_KINDS,
            )
            rls = st.text_input(
                "Linked session ID", key="hist_rls",
            )
            rsub = st.text_input("Subject ID")
            rnarr = st.text_area(
                "Narrative", key="hist_narr",
            )
            rrea = st.text_input(
                "Reason", key="hist_reason",
            )
            if st.form_submit_button("Register history record"):
                res = eng["hist"].register_history_record(
                    {"record_id": rid, "kind": rk,
                     "linked_session_id": rls,
                     "subject_id": rsub,
                     "narrative": rnarr},
                    actor=actor, reason=rrea,
                )
                audit_log(
                    action="register_history_record",
                    username=actor, module="cims_compliance",
                )
                if res.get("registered"):
                    st.success(f"Record {rid} registered (immutable)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Register correction"):
            with st.form("corr_form"):
                cid = st.text_input("Correction ID")
                csup = st.text_input(
                    "Supersedes record ID", key="corr_sup",
                )
                ccr = st.selectbox(
                    "Correction reason", ALLOWED_CORRECTION_REASONS,
                )
                cnarr = st.text_area(
                    "Narrative", key="corr_narr",
                )
                crrea = st.text_input(
                    "Reason", key="corr_reason",
                )
                if st.form_submit_button("Register correction"):
                    res = eng["hist"].register_correction(
                        {"correction_id": cid,
                         "supersedes_record_id": csup,
                         "correction_reason": ccr,
                         "narrative": cnarr},
                        actor=actor, reason=crrea,
                    )
                    audit_log(
                        action="register_history_correction",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("registered"):
                        st.success(
                            f"Correction {cid} registered "
                            f"(supersedes {csup})",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        sid_q = st.text_input(
            "Session ID for history query", key="hist_q",
        )
        if st.button("Show history for session") and sid_q:
            recs = eng["hist"].history_for_session(sid_q)
            st.metric("Records", len(recs))
            for r in recs[:10]:
                st.write(
                    f"• `{r.get('record_id')}` "
                    f"({r.get('kind')}) "
                    f"— {r.get('narrative', '')[:80]}",
                )
                if r.get("corrections"):
                    st.caption(
                        f"  ↳ {len(r['corrections'])} correction(s)",
                    )

    # ---------- Tab 6: Examiner queries + reviews ----------
    with tabs[5]:
        st.subheader("Examiner queries + compliance reviews")
        st.caption(
            f"Query types: {', '.join(EXAMINER_QUERY_TYPES)} · "
            f"Outcomes: {', '.join(EXAMINER_RESPONSE_OUTCOMES)}"
        )
        with st.form("exam_q"):
            qid = st.text_input("Query ID")
            qt = st.selectbox(
                "Query type", EXAMINER_QUERY_TYPES,
            )
            qename = st.text_input("Examiner name")
            qoc = st.selectbox(
                "Outcome", EXAMINER_RESPONSE_OUTCOMES,
            )
            qnarr = st.text_area(
                "Narrative", key="exam_q_narr",
            )
            if st.form_submit_button("Record examiner query"):
                res = eng["hist"].record_examiner_query(
                    {"query_id": qid, "query_type": qt,
                     "examiner_name": qename, "outcome": qoc,
                     "narrative": qnarr},
                    actor=actor,
                )
                audit_log(
                    action="record_examiner_query",
                    username=actor, module="cims_compliance",
                )
                if res.get("recorded"):
                    st.success(f"Query {qid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Record compliance review"):
            with st.form("rev_form"):
                rid = st.text_input("Review ID")
                rsc = st.text_input("Scope")
                roc = st.selectbox(
                    "Outcome", COMPLIANCE_REVIEW_OUTCOMES,
                )
                rnarr = st.text_area(
                    "Narrative", key="rev_narr",
                )
                if st.form_submit_button("Record review"):
                    res = eng["hist"].record_compliance_review(
                        {"review_id": rid, "scope": rsc,
                         "outcome": roc, "narrative": rnarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_compliance_review",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("recorded"):
                        st.success(f"Review {rid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        ndays = st.number_input(
            "Window (days)", min_value=1, value=90,
            key="exam_days",
        )
        if st.button("Examiner summary"):
            s = eng["hist"].examiner_summary(days=int(ndays))
            cs = st.columns(2)
            cs[0].metric("Queries", s["total_queries"])
            cs[1].metric(
                "Provision rate",
                f"{s['provision_rate_pct']}%",
            )
            for t, n in s.get("per_type", {}).items():
                st.write(f"• `{t}`: {n}")

    # ---------- Tab 7: Agent workspace ----------
    with tabs[6]:
        st.subheader("Agent workspace (Standard #178)")
        st.caption(
            f"Agent states: {', '.join(AGENT_STATES)} · "
            f"Item states: {', '.join(WORK_ITEM_STATES)} · "
            f"Skills: {', '.join(AGENT_SKILL_TAGS)} · "
            f"Queue threshold: {DEFAULT_QUEUE_DEPTH_THRESHOLD} · "
            f"Reassignment: {DEFAULT_QUEUE_REASSIGNMENT_HOURS}h · "
            f"Break limit: {DEFAULT_AGENT_BREAK_LIMIT_MINUTES}min"
        )
        with st.form("agt_form"):
            aid = st.text_input("Agent ID")
            aname = st.text_input("Name")
            askills = st.multiselect(
                "Skill tags", AGENT_SKILL_TAGS,
            )
            arrea = st.text_input("Reason", key="agt_reason")
            if st.form_submit_button("Register agent"):
                res = eng["agent"].register_agent(
                    {"agent_id": aid, "name": aname,
                     "skill_tags": list(askills)},
                    actor=actor, reason=arrea,
                )
                audit_log(
                    action="register_agent",
                    username=actor, module="cims_compliance",
                )
                if res.get("registered"):
                    st.success(f"Agent {aid} registered (AVAILABLE)")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Enqueue work item"):
            with st.form("itm_form"):
                iid = st.text_input("Item ID")
                ils = st.text_input("Linked session ID")
                isrc = st.selectbox(
                    "Source", WORK_ITEM_SOURCES,
                )
                ipri = st.selectbox(
                    "Priority", WORK_ITEM_PRIORITIES,
                )
                inarr = st.text_area(
                    "Narrative", key="itm_narr",
                )
                isk = st.selectbox(
                    "Required skill", AGENT_SKILL_TAGS,
                )
                irea = st.text_input(
                    "Reason", key="itm_reason",
                )
                if st.form_submit_button("Enqueue"):
                    res = eng["agent"].enqueue_work_item(
                        {"item_id": iid,
                         "linked_session_id": ils,
                         "source": isrc, "priority": ipri,
                         "narrative": inarr,
                         "required_skill": isk},
                        actor=actor, reason=irea,
                    )
                    audit_log(
                        action="enqueue_work_item",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("enqueued"):
                        st.success(f"Item {iid} enqueued (QUEUED)")
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Record agent action"):
            with st.form("act_form"):
                acid = st.text_input("Action ID")
                acaid = st.text_input(
                    "Agent ID", key="act_aid",
                )
                aciid = st.text_input(
                    "Item ID", key="act_iid",
                )
                ack = st.selectbox(
                    "Action kind", AGENT_ACTION_KINDS,
                )
                acnarr = st.text_area(
                    "Narrative", key="act_narr",
                )
                if st.form_submit_button("Record action"):
                    res = eng["agent"].record_action(
                        {"action_id": acid, "agent_id": acaid,
                         "item_id": aciid, "action_kind": ack,
                         "narrative": acnarr},
                        actor=actor,
                    )
                    audit_log(
                        action="record_agent_action",
                        username=actor, module="cims_compliance",
                    )
                    if res.get("recorded"):
                        st.success(f"Action {acid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button("Queue summary"):
            s = eng["agent"].queue_summary()
            cs = st.columns(3)
            cs[0].metric("Total items", s["total_items"])
            cs[1].metric(
                "Queue depth", s["queue_depth"],
            )
            cs[2].metric(
                "Threshold", s["queue_depth_threshold"],
            )
            if s.get("exceeds_threshold"):
                st.error("⚠️ Queue depth exceeds threshold")
            for st_name, n in s.get("per_state", {}).items():
                st.write(f"• `{st_name}`: {n}")

        if st.button("Workload by agent"):
            w = eng["agent"].workload_by_agent()
            for ag, kinds in w.items():
                st.markdown(f"**`{ag}`:**")
                for k, n in kinds.items():
                    st.write(f"  • `{k}`: {n}")


main()
