"""
Phase 2B — CIMS Batch 1: Capture & Classification (pages/105)
=================================================================
v10.290 — covers Standards #166 (Omnichannel Capture),
#167 (NLP Classification), #168 (STP Engine), #173 (Unified Identity).

Audience: CIMS operations, contact centre, identity stewards,
ML/NLP team, customer experience.

Tab map (7 tabs; right at G4 ceiling, planned upfront):
  1. Capture sessions          — register + lifecycle + handoffs
  2. Channel touches           — record + summary
  3. NLP classification        — request + result + override
  4. STP decisions             — request + decision + manual review
  5. STP eligibility rules     — register
  6. Unified identity          — identity + links + merges
  7. Metrics                   — capture, NLP, STP, identity
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

from utils.cims_omnichannel_capture import (
    OmnichannelCaptureEngine,
    CHANNELS, CAPTURE_STATES, INSTRUCTION_TYPES,
    DEFAULT_CAPTURE_TIMEOUT_MINUTES,
    DEFAULT_ABANDONMENT_THRESHOLD_MINUTES,
)
from utils.cims_nlp_classification import (
    NLPClassificationEngine,
    INTENT_CATEGORIES, CONFIDENCE_TIERS,
    CLASSIFICATION_STATES, MODEL_VERSION_STATES,
    DEFAULT_CONFIDENCE_HIGH_THRESHOLD,
    DEFAULT_CONFIDENCE_MEDIUM_THRESHOLD,
    DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS,
)
from utils.cims_stp_engine import (
    StraightThroughProcessingEngine,
    STP_DECISION_STATES, RISK_TIERS,
    ELIGIBILITY_CRITERIA, REJECTION_REASONS,
    DEFAULT_STP_AMOUNT_LIMIT_LOW_RISK,
    DEFAULT_STP_AMOUNT_LIMIT_MEDIUM_RISK,
    DEFAULT_KYC_FRESHNESS_DAYS,
)
from utils.cims_unified_identity import (
    UnifiedIdentityEngine,
    IDENTITY_LINK_TYPES, IDENTITY_STATES, MERGE_OUTCOMES,
    DEFAULT_MERGE_REVIEW_HOURS, DEFAULT_FLAGGED_REVIEW_HOURS,
)

# Phase 3 standing rule: do NOT silently swallow require_access
# failures. Pages must fail loud so misconfigured access is visible.
from pages._access import require_access
require_access("operations.cims_capture")


@st.cache_resource
def _engines():
    return {
        "cap": OmnichannelCaptureEngine(),
        "nlp": NLPClassificationEngine(),
        "stp": StraightThroughProcessingEngine(),
        "uid": UnifiedIdentityEngine(),
    }


def main():
    st.title("📥 CIMS — Capture & Classification")
    st.caption(
        "v10.290 · Standards #166 + #167 + #168 + #173 · "
        "Phase 2B Batch 1: omnichannel instruction capture, NLP "
        "classification, STP routing, unified customer identity. "
        f"Capture timeout: {DEFAULT_CAPTURE_TIMEOUT_MINUTES}m · "
        f"NLP timeout: {DEFAULT_CLASSIFICATION_TIMEOUT_SECONDS}s · "
        f"KYC freshness: {DEFAULT_KYC_FRESHNESS_DAYS}d."
    )

    eng = _engines()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "📥 Capture sessions",
        "🔀 Channel touches",
        "🧠 NLP classification",
        "⚡ STP decisions",
        "📐 STP rules",
        "🆔 Unified identity",
        "📊 Metrics",
    ])

    # ---------- Tab 1: Capture sessions ----------
    with tabs[0]:
        st.subheader("Omnichannel capture sessions (Standard #166)")
        st.caption(
            f"Channels: {', '.join(CHANNELS)} · "
            f"Instruction types: {', '.join(INSTRUCTION_TYPES)}",
        )
        with st.form("cap_session_form"):
            sid = st.text_input("Session ID")
            cid = st.text_input("Customer ID")
            itype = st.selectbox(
                "Instruction type", INSTRUCTION_TYPES,
            )
            ochan = st.selectbox(
                "Originating channel", CHANNELS,
            )
            srea = st.text_input("Reason")
            if st.form_submit_button("Register session"):
                res = eng["cap"].register_capture_session(
                    {"session_id": sid, "customer_id": cid,
                     "instruction_type": itype,
                     "originating_channel": ochan},
                    actor=actor, reason=srea,
                )
                audit_log(
                    action="register_capture_session",
                    username=actor,
                    module="cims_capture",
                )
                if res.get("registered"):
                    st.success(
                        f"Session {sid} registered (INITIATED)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition + handoffs"):
            with st.form("cap_state_form"):
                tsid = st.text_input(
                    "Session ID", key="cap_st_sid",
                )
                ns = st.selectbox(
                    "New state", CAPTURE_STATES,
                )
                trea = st.text_input(
                    "Reason", key="cap_st_reason",
                )
                if st.form_submit_button("Transition state"):
                    res = eng["cap"].transition_capture_state(
                        tsid, ns, actor=actor, reason=trea,
                    )
                    audit_log(
                        action="transition_capture_state",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

            with st.form("cap_handoff_form"):
                hid = st.text_input("Handoff ID")
                hsid = st.text_input(
                    "Session ID", key="cap_h_sid",
                )
                hfrom = st.selectbox(
                    "From channel", CHANNELS, key="cap_h_from",
                )
                hto = st.selectbox(
                    "To channel", CHANNELS, key="cap_h_to",
                )
                hctx = st.checkbox("Context preserved", value=True)
                hrea = st.text_input(
                    "Reason", key="cap_h_reason",
                )
                if st.form_submit_button("Register handoff"):
                    res = eng["cap"].register_handoff(
                        {"handoff_id": hid, "session_id": hsid,
                         "from_channel": hfrom,
                         "to_channel": hto,
                         "context_preserved": hctx},
                        actor=actor, reason=hrea,
                    )
                    audit_log(
                        action="register_capture_handoff",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("registered"):
                        st.success(f"Handoff {hid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        sid_q = st.text_input(
            "Session ID for summary", key="cap_sum_sid",
        )
        if st.button("Show summary"):
            s = eng["cap"].capture_summary(sid_q)
            if s.get("found"):
                cols = st.columns(4)
                cols[0].metric("State", s["state"])
                cols[1].metric(
                    "Channels touched", s["channel_count"],
                )
                cols[2].metric("Touches", s["touches_count"])
                cols[3].metric("Handoffs", s["handoffs_count"])
                if s.get("is_omnichannel"):
                    st.info(
                        f"Omnichannel: "
                        f"{', '.join(s['channels_touched'])}",
                    )
            else:
                st.error(s.get("error", "Not found"))

    # ---------- Tab 2: Channel touches ----------
    with tabs[1]:
        st.subheader("Channel touches")
        st.caption(
            "Record per-channel interaction events for a capture "
            "session. Used to surface omnichannel sessions and "
            f"abandonment beyond {DEFAULT_ABANDONMENT_THRESHOLD_MINUTES}m.",
        )
        with st.form("touch_form"):
            tid = st.text_input("Touch ID")
            tsid = st.text_input("Session ID", key="t_sid")
            tchan = st.selectbox("Channel", CHANNELS, key="t_chan")
            tfp = st.text_input("Fingerprint")
            tdur = st.number_input(
                "Duration (seconds)", min_value=0, value=0,
            )
            if st.form_submit_button("Record touch"):
                res = eng["cap"].record_channel_touch(
                    {"touch_id": tid, "session_id": tsid,
                     "channel": tchan, "fingerprint": tfp,
                     "duration_seconds": int(tdur) if tdur else None},
                    actor=actor,
                )
                audit_log(
                    action="record_channel_touch",
                    username=actor,
                    module="cims_capture",
                )
                if res.get("recorded"):
                    st.success(f"Touch {tid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

        chan_q = st.selectbox(
            "Sessions originating from channel",
            CHANNELS, key="orig_chan",
        )
        if st.button("List"):
            sessions = eng["cap"].sessions_by_channel(chan_q)
            st.metric("Sessions", len(sessions))
            for s in sessions[:15]:
                st.write(
                    f"• `{s.get('session_id')}` "
                    f"({s.get('state')}) — "
                    f"{s.get('instruction_type')} for "
                    f"{s.get('customer_id')}",
                )

    # ---------- Tab 3: NLP classification ----------
    with tabs[2]:
        st.subheader("NLP classification (Standard #167)")
        st.caption(
            f"Intents: {', '.join(INTENT_CATEGORIES)} · "
            f"Confidence tiers: {', '.join(CONFIDENCE_TIERS)} · "
            f"Thresholds: HIGH ≥ "
            f"{DEFAULT_CONFIDENCE_HIGH_THRESHOLD}, "
            f"MEDIUM ≥ {DEFAULT_CONFIDENCE_MEDIUM_THRESHOLD}",
        )
        with st.form("nlp_req_form"):
            nrid = st.text_input("Request ID")
            ncsid = st.text_input("Capture session ID")
            ntext = st.text_area("Raw text")
            nchan = st.text_input("Channel hint")
            if st.form_submit_button("Submit request"):
                res = eng["nlp"].register_classification_request(
                    {"request_id": nrid,
                     "capture_session_id": ncsid,
                     "raw_text": ntext,
                     "channel_hint": nchan},
                    actor=actor,
                )
                audit_log(
                    action="register_nlp_classification_request",
                    username=actor,
                    module="cims_capture",
                )
                if res.get("registered"):
                    st.success(f"Request {nrid} submitted")
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Record classification result"):
            with st.form("nlp_res_form"):
                resid = st.text_input("Result ID")
                resrid = st.text_input(
                    "Request ID", key="res_rid",
                )
                resint = st.selectbox("Intent", INTENT_CATEGORIES)
                restier = st.selectbox(
                    "Confidence tier", CONFIDENCE_TIERS,
                )
                resscore = st.number_input(
                    "Confidence score (0.0–1.0)",
                    min_value=0.0, max_value=1.0,
                    value=0.5, step=0.05,
                )
                resver = st.text_input("Model version")
                if st.form_submit_button("Record result"):
                    res = eng["nlp"].record_classification_result(
                        {"result_id": resid,
                         "request_id": resrid,
                         "intent": resint,
                         "confidence_tier": restier,
                         "confidence_score": resscore,
                         "model_version": resver},
                        actor=actor,
                    )
                    audit_log(
                        action="record_nlp_classification_result",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("recorded"):
                        st.success(f"Result {resid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Human override"):
            with st.form("nlp_override_form"):
                ovid = st.text_input("Override ID")
                ovrid = st.text_input(
                    "Request ID", key="ov_rid",
                )
                ovorig = st.selectbox(
                    "Original intent", INTENT_CATEGORIES,
                    key="ov_orig",
                )
                ovcorr = st.selectbox(
                    "Corrected intent", INTENT_CATEGORIES,
                    key="ov_corr",
                )
                ovrea = st.text_input(
                    "Rationale", key="ov_rea",
                )
                if st.form_submit_button("Record override"):
                    res = eng["nlp"].record_human_override(
                        {"override_id": ovid,
                         "request_id": ovrid,
                         "original_intent": ovorig,
                         "corrected_intent": ovcorr},
                        actor=actor, reason=ovrea,
                    )
                    audit_log(
                        action="record_nlp_human_override",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("recorded"):
                        st.success(f"Override {ovid} recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Transition classification state"):
            with st.form("nlp_state_form"):
                tnsid = st.text_input(
                    "Request ID", key="nlp_st_rid",
                )
                tns = st.selectbox(
                    "New state", CLASSIFICATION_STATES,
                )
                tnrea = st.text_input(
                    "Reason", key="nlp_st_reason",
                )
                if st.form_submit_button("Transition"):
                    res = eng["nlp"].transition_classification_state(
                        tnsid, tns, actor=actor, reason=tnrea,
                    )
                    audit_log(
                        action="transition_nlp_classification_state",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        thresh = st.selectbox(
            "Show requests below confidence",
            CONFIDENCE_TIERS, key="conf_thresh",
        )
        if st.button("List"):
            below = eng["nlp"].requests_below_confidence(
                threshold=thresh,
            )
            st.metric(f"Below {thresh}", len(below))
            for r in below[:15]:
                st.write(
                    f"• `{r.get('result_id')}` "
                    f"({r.get('confidence_tier')}, "
                    f"{r.get('confidence_score', 'n/a')}) — "
                    f"intent {r.get('intent')}",
                )

    # ---------- Tab 4: STP decisions ----------
    with tabs[3]:
        st.subheader("STP decisions (Standard #168)")
        st.caption(
            f"Decision states: {', '.join(STP_DECISION_STATES)} · "
            f"Risk tiers: {', '.join(RISK_TIERS)} · "
            f"LOW risk STP cap: KES "
            f"{DEFAULT_STP_AMOUNT_LIMIT_LOW_RISK:,} · "
            f"MEDIUM risk STP cap: KES "
            f"{DEFAULT_STP_AMOUNT_LIMIT_MEDIUM_RISK:,}",
        )
        with st.form("stp_req_form"):
            srid = st.text_input("Request ID")
            siid = st.text_input("Instruction ID")
            sit = st.text_input("Instruction type")
            srtier = st.selectbox(
                "Customer risk tier", RISK_TIERS,
            )
            samt = st.number_input(
                "Amount", min_value=0, value=0,
            )
            scur = st.text_input("Currency", value="KES")
            schan = st.text_input("Channel")
            srea = st.text_input("Reason", key="stp_req_rea")
            if st.form_submit_button("Register STP request"):
                res = eng["stp"].register_stp_request(
                    {"request_id": srid,
                     "instruction_id": siid,
                     "instruction_type": sit,
                     "customer_risk_tier": srtier,
                     "amount": float(samt) if samt else None,
                     "currency": scur,
                     "channel": schan},
                    actor=actor, reason=srea,
                )
                audit_log(
                    action="register_stp_request",
                    username=actor,
                    module="cims_capture",
                )
                if res.get("registered"):
                    st.success(
                        f"Request {srid} registered (EVALUATING)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Record decision + transition"):
            with st.form("stp_dec_form"):
                did = st.text_input("Decision ID")
                drid = st.text_input(
                    "Request ID", key="dec_rid",
                )
                ddec = st.selectbox(
                    "Decision", STP_DECISION_STATES,
                )
                drej = st.selectbox(
                    "Rejection reason (if applicable)",
                    ["—", *REJECTION_REASONS],
                )
                drea = st.text_input(
                    "Rationale", key="dec_rea",
                )
                if st.form_submit_button("Record decision"):
                    rej = None if drej == "—" else drej
                    res1 = eng["stp"].record_stp_decision(
                        {"decision_id": did,
                         "request_id": drid,
                         "decision": ddec,
                         "rejection_reason": rej},
                        actor=actor, reason=drea,
                    )
                    res2 = eng["stp"].transition_decision_state(
                        drid, ddec, actor=actor, reason=drea,
                    )
                    audit_log(
                        action="record_stp_decision",
                        username=actor,
                        module="cims_capture",
                    )
                    if res1.get("recorded") and res2.get("transitioned"):
                        st.success(
                            f"Decision {did}: {res2.get('from')} → "
                            f"{res2.get('to')}",
                        )
                    else:
                        st.warning(
                            f"record={res1}, transition={res2}",
                        )

        if st.button("Pending manual review"):
            pending = eng["stp"].pending_manual_review()
            st.metric("Pending", len(pending))
            for p in pending[:15]:
                st.write(
                    f"• `{p.get('request_id')}` "
                    f"(risk {p.get('customer_risk_tier')}, "
                    f"amount {p.get('amount')}, "
                    f"{p.get('instruction_type')})",
                )

    # ---------- Tab 5: STP eligibility rules ----------
    with tabs[4]:
        st.subheader("STP eligibility rules")
        st.caption(
            f"Criteria: {', '.join(ELIGIBILITY_CRITERIA)}",
        )
        with st.form("stp_rule_form"):
            rid = st.text_input("Rule ID")
            rcrit = st.selectbox(
                "Criterion", ELIGIBILITY_CRITERIA,
            )
            rinst = st.text_input("Applies to instruction type")
            rthresh = st.text_input("Threshold value")
            rrea = st.text_input(
                "Reason", key="rule_reason",
            )
            if st.form_submit_button("Register rule"):
                res = eng["stp"].register_eligibility_rule(
                    {"rule_id": rid, "criterion": rcrit,
                     "applies_to_instruction_type": rinst,
                     "threshold_value": rthresh},
                    actor=actor, reason=rrea,
                )
                audit_log(
                    action="register_stp_eligibility_rule",
                    username=actor,
                    module="cims_capture",
                )
                if res.get("registered"):
                    st.success(f"Rule {rid} registered")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 6: Unified identity ----------
    with tabs[5]:
        st.subheader("Unified identity (Standard #173)")
        st.caption(
            f"Link types: {', '.join(IDENTITY_LINK_TYPES)} · "
            f"States: {', '.join(IDENTITY_STATES)} · "
            f"Merge review: {DEFAULT_MERGE_REVIEW_HOURS}h · "
            f"Flagged review: {DEFAULT_FLAGGED_REVIEW_HOURS}h",
        )
        with st.form("uid_form"):
            iid = st.text_input("Identity ID")
            iname = st.text_input("Display name")
            iemail = st.text_input("Primary email")
            iphone = st.text_input("Primary phone")
            irea = st.text_input("Reason", key="uid_reason")
            if st.form_submit_button("Register identity"):
                res = eng["uid"].register_unified_identity(
                    {"identity_id": iid,
                     "display_name": iname,
                     "primary_email": iemail,
                     "primary_phone": iphone},
                    actor=actor, reason=irea,
                )
                audit_log(
                    action="register_unified_identity",
                    username=actor,
                    module="cims_capture",
                )
                if res.get("registered"):
                    st.success(
                        f"Identity {iid} registered (PROVISIONAL)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Register link"):
            with st.form("uid_link_form"):
                lid = st.text_input("Link ID")
                liid = st.text_input(
                    "Identity ID", key="link_iid",
                )
                ltype = st.selectbox(
                    "Link type", IDENTITY_LINK_TYPES,
                )
                lext = st.text_input("External ID")
                lver = st.checkbox("Verified", value=False)
                lrea = st.text_input(
                    "Reason", key="link_reason",
                )
                if st.form_submit_button("Register link"):
                    res = eng["uid"].register_identity_link(
                        {"link_id": lid,
                         "identity_id": liid,
                         "link_type": ltype,
                         "external_id": lext,
                         "verified": lver},
                        actor=actor, reason=lrea,
                    )
                    audit_log(
                        action="register_identity_link",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("registered"):
                        st.success(f"Link {lid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Propose merge"):
            with st.form("uid_merge_form"):
                mid = st.text_input("Merge ID")
                mprim = st.text_input(
                    "Primary identity ID", key="m_prim",
                )
                msec = st.text_input(
                    "Secondary identity ID", key="m_sec",
                )
                mscore = st.number_input(
                    "Match score (0.0–1.0)",
                    min_value=0.0, max_value=1.0,
                    value=0.0, step=0.05,
                )
                mevid = st.text_input(
                    "Evidence (comma-separated)",
                )
                mrea = st.text_input(
                    "Reason", key="merge_reason",
                )
                if st.form_submit_button("Propose merge"):
                    evid_list = [
                        e.strip() for e in mevid.split(",")
                        if e.strip()
                    ]
                    res = eng["uid"].propose_merge(
                        {"merge_id": mid,
                         "primary_identity_id": mprim,
                         "secondary_identity_id": msec,
                         "match_score": mscore,
                         "match_evidence": evid_list},
                        actor=actor, reason=mrea,
                    )
                    audit_log(
                        action="propose_identity_merge",
                        username=actor,
                        module="cims_capture",
                    )
                    if res.get("proposed"):
                        st.success(f"Merge {mid} proposed")
                    else:
                        st.error(res.get("error", "Failed"))

        with st.expander("Approve / reject merge"):
            with st.form("uid_decide_form"):
                did = st.text_input(
                    "Merge ID", key="decide_mid",
                )
                action_choice = st.radio(
                    "Action", ["Approve", "Reject"],
                )
                drea = st.text_input(
                    "Reason", key="decide_reason",
                )
                if st.form_submit_button("Apply"):
                    if action_choice == "Approve":
                        res = eng["uid"].approve_merge(
                            did, actor=actor, reason=drea,
                        )
                        ok = res.get("approved")
                    else:
                        res = eng["uid"].reject_merge(
                            did, actor=actor, reason=drea,
                        )
                        ok = res.get("rejected")
                    audit_log(
                        action=f"{action_choice.lower()}_identity_merge",
                        username=actor,
                        module="cims_capture",
                    )
                    if ok:
                        st.success(f"{action_choice} applied")
                    else:
                        st.error(res.get("error", "Failed"))

        if st.button("Pending merges"):
            pending = eng["uid"].pending_merges()
            st.metric("Pending", len(pending))
            for p in pending[:15]:
                st.write(
                    f"• `{p.get('merge_id')}` — "
                    f"{p.get('primary_identity_id')} ↔ "
                    f"{p.get('secondary_identity_id')} "
                    f"(score {p.get('match_score', 'n/a')})",
                )

    # ---------- Tab 7: Metrics ----------
    with tabs[6]:
        st.subheader("CIMS Batch 1 metrics")
        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="cims1_days",
        )
        if st.button("Refresh metrics"):
            mn = eng["nlp"].classification_metrics(
                days=int(ndays),
            )
            ms = eng["stp"].stp_metrics(days=int(ndays))

            st.markdown("**NLP (#167):**")
            cols = st.columns(4)
            cols[0].metric(
                "Classifications",
                mn["total_classifications"],
            )
            cols[1].metric(
                "HIGH confidence",
                f"{mn['high_confidence_pct']}%",
            )
            cols[2].metric(
                "Human overrides",
                mn["human_overrides"],
            )
            cols[3].metric(
                "Override rate",
                f"{mn['override_rate_pct']}%",
            )

            st.markdown("**STP (#168):**")
            cols = st.columns(4)
            cols[0].metric("Requests", ms["total_requests"])
            cols[1].metric("STP approved", ms["stp_approved"])
            cols[2].metric(
                "STP rate", f"{ms['stp_rate_pct']}%",
            )
            cols[3].metric(
                "Pending manual",
                ms["pending_manual_review"],
            )


main()
