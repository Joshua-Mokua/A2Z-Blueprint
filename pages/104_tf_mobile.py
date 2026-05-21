"""
Phase 2B — Trade Finance Mobile (pages/104)
=================================================================
v10.289 — covers Standard #279 (Trade Finance Mobile App, lone).

Audience: Corporate banking RMs, mobile security team, trade finance
operations, IT digital banking.

Mobile session + device + push notification + offline draft cockpit.
The Trade Finance Mobile App is a UI delivery concern that consumes
the existing TradeFinanceCorporatePortalEngine API (ENH-271) — this
cockpit catalogues the mobile-specific state that lives outside the
portal validation logic. Following the v10.283 SWIFT lone-standard
pattern: dedicated cockpit + dedicated G gate + diagnostic-only stance.

Tab map (5 tabs):
  1. Mobile sessions          — register + lifecycle
  2. Devices                  — register, revoke
  3. Push notifications       — record outcomes
  4. Offline drafts           — queue tracking
  5. Metrics                  — sessions + notification delivery rate
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
from utils.trade_finance_mobile import (
    TradeFinanceMobileEngine,
    MOBILE_SESSION_STATES, DEVICE_PLATFORMS, DEVICE_STATES,
    PUSH_NOTIFICATION_TYPES, PUSH_DELIVERY_OUTCOMES,
    DRAFT_TYPES, DRAFT_STATES,
    DEFAULT_SESSION_TIMEOUT_MINUTES,
    DEFAULT_DEVICE_REGISTRATION_TTL_DAYS,
    DEFAULT_PUSH_DELIVERY_TIMEOUT_SECONDS,
    DEFAULT_OFFLINE_DRAFT_TTL_HOURS,
    CBK_MOBILE_BANKING_REFERENCE, DPA_MOBILE_REFERENCE,
)

try:
    from pages._access import require_access
    require_access("trade_finance.tf_mobile")
except Exception:
    pass


@st.cache_resource
def _engine():
    return TradeFinanceMobileEngine()


def main():
    st.title("📱 Trade Finance Mobile Cockpit")
    st.caption(
        f"v10.289 · Standard #279 · Mobile session + device + push + "
        f"offline draft tracking. Session timeout: "
        f"{DEFAULT_SESSION_TIMEOUT_MINUTES}m · Device TTL: "
        f"{DEFAULT_DEVICE_REGISTRATION_TTL_DAYS}d · Draft TTL: "
        f"{DEFAULT_OFFLINE_DRAFT_TTL_HOURS}h. "
        f"Frameworks: {CBK_MOBILE_BANKING_REFERENCE} · "
        f"{DPA_MOBILE_REFERENCE}. UI delivery is a thin wrapper over "
        f"TradeFinanceCorporatePortalEngine (ENH-271)."
    )

    eng = _engine()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "🔐 Sessions",
        "📲 Devices",
        "🔔 Push notifications",
        "💾 Offline drafts",
        "📊 Metrics",
    ])

    # ---------- Tab 1: Sessions ----------
    with tabs[0]:
        st.subheader("Mobile sessions")
        st.caption(
            f"States: {', '.join(MOBILE_SESSION_STATES)} · "
            f"Lifecycle: INITIATED → AUTHENTICATED → ACTIVE → "
            f"EXPIRED/REVOKED.",
        )
        with st.form("session_form"):
            sid = st.text_input("Session ID")
            uname = st.text_input("Username")
            did = st.text_input("Device ID")
            srea = st.text_input("Registration reason")
            if st.form_submit_button("Register session"):
                res = eng.register_mobile_session(
                    {"session_id": sid, "username": uname,
                     "device_id": did},
                    actor=actor, reason=srea,
                )
                audit_log(
                    action="register_mobile_session",
                    username=actor,
                    module="tf_mobile",
                )
                if res.get("registered"):
                    st.success(
                        f"Session {sid} registered (INITIATED)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Transition session state"):
            with st.form("session_state"):
                tid = st.text_input("Session ID", key="sess_st_id")
                ns = st.selectbox(
                    "New state", MOBILE_SESSION_STATES,
                )
                tre = st.text_input("Reason", key="sess_st_reason")
                if st.form_submit_button("Transition"):
                    res = eng.transition_session_state(
                        tid, ns, actor=actor, reason=tre,
                    )
                    audit_log(
                        action="transition_mobile_session_state",
                        username=actor,
                        module="tf_mobile",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        uname_q = st.text_input(
            "Show active sessions for user", key="active_q",
        )
        if st.button("List"):
            sessions = eng.active_sessions_for_user(uname_q)
            st.metric("Active or authenticated", len(sessions))
            for s in sessions[:10]:
                st.write(
                    f"• `{s.get('session_id')}` "
                    f"({s.get('state')}) — device "
                    f"{s.get('device_id')}",
                )

    # ---------- Tab 2: Devices ----------
    with tabs[1]:
        st.subheader("Device registry")
        st.caption(
            f"Platforms: {', '.join(DEVICE_PLATFORMS)} · "
            f"States: {', '.join(DEVICE_STATES)}",
        )
        with st.form("device_form"):
            did = st.text_input("Device ID")
            dun = st.text_input("Username", key="dev_user")
            dpl = st.selectbox("Platform", DEVICE_PLATFORMS)
            dfp = st.text_input("Device fingerprint")
            drea = st.text_input("Reason", key="dev_reason")
            if st.form_submit_button("Register device"):
                res = eng.register_device(
                    {"device_id": did, "username": dun,
                     "platform": dpl, "device_fingerprint": dfp},
                    actor=actor, reason=drea,
                )
                audit_log(
                    action="register_mobile_device",
                    username=actor,
                    module="tf_mobile",
                )
                if res.get("registered"):
                    st.success(
                        f"Device {did} registered (REGISTERED)",
                    )
                else:
                    st.error(res.get("error", "Failed"))

        with st.expander("Revoke device"):
            with st.form("device_revoke"):
                rid = st.text_input(
                    "Device ID", key="rev_id",
                )
                rrea = st.text_input(
                    "Revocation reason", key="rev_reason",
                )
                if st.form_submit_button("Revoke"):
                    res = eng.revoke_device(
                        rid, actor=actor, reason=rrea,
                    )
                    audit_log(
                        action="revoke_mobile_device",
                        username=actor,
                        module="tf_mobile",
                    )
                    if res.get("revoked"):
                        st.success(f"Device {rid} revoked")
                    else:
                        st.error(res.get("error", "Failed"))

    # ---------- Tab 3: Push notifications ----------
    with tabs[2]:
        st.subheader("Push notifications")
        st.caption(
            f"Types: {', '.join(PUSH_NOTIFICATION_TYPES)} · "
            f"Outcomes: {', '.join(PUSH_DELIVERY_OUTCOMES)} · "
            f"Timeout: {DEFAULT_PUSH_DELIVERY_TIMEOUT_SECONDS}s",
        )
        with st.form("notif_form"):
            nid = st.text_input("Notification ID")
            ndid = st.text_input("Device ID", key="notif_did")
            ntype = st.selectbox("Type", PUSH_NOTIFICATION_TYPES)
            nout = st.selectbox(
                "Outcome", PUSH_DELIVERY_OUTCOMES,
            )
            nref = st.text_input(
                "Subject reference (e.g. LC-2026-001)",
            )
            if st.form_submit_button("Record notification"):
                res = eng.record_push_notification(
                    {"notification_id": nid,
                     "device_id": ndid,
                     "notification_type": ntype,
                     "outcome": nout,
                     "subject_ref": nref},
                    actor=actor,
                )
                audit_log(
                    action="record_push_notification",
                    username=actor,
                    module="tf_mobile",
                )
                if res.get("recorded"):
                    st.success(f"Notification {nid} recorded")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 4: Offline drafts ----------
    with tabs[3]:
        st.subheader("Offline drafts")
        st.caption(
            f"Types: {', '.join(DRAFT_TYPES)} · "
            f"States: {', '.join(DRAFT_STATES)} · "
            f"TTL: {DEFAULT_OFFLINE_DRAFT_TTL_HOURS}h. "
            f"Drafts queue locally and sync when network returns; "
            f"actual submission validates through "
            f"TradeFinanceCorporatePortalEngine.",
        )
        with st.form("draft_form"):
            drid = st.text_input("Draft ID")
            drsid = st.text_input(
                "Session ID", key="draft_sid",
            )
            drtype = st.selectbox("Draft type", DRAFT_TYPES)
            drstate = st.selectbox("State", DRAFT_STATES)
            drsum = st.text_area("Payload summary")
            if st.form_submit_button("Record draft"):
                res = eng.record_offline_draft(
                    {"draft_id": drid,
                     "session_id": drsid,
                     "draft_type": drtype,
                     "state": drstate,
                     "payload_summary": drsum},
                    actor=actor,
                )
                audit_log(
                    action="record_offline_draft",
                    username=actor,
                    module="tf_mobile",
                )
                if res.get("recorded"):
                    st.success(f"Draft {drid} recorded ({drstate})")
                else:
                    st.error(res.get("error", "Failed"))

    # ---------- Tab 5: Metrics ----------
    with tabs[4]:
        st.subheader("Mobile metrics")
        ndays = st.number_input(
            "Window (days)", min_value=1, value=30,
            key="mob_metrics_days",
        )
        if st.button("Refresh"):
            m = eng.session_metrics(days=int(ndays))
            cols = st.columns(4)
            cols[0].metric("Sessions", m["total_sessions"])
            cols[1].metric("Active", m["active"])
            cols[2].metric("Expired", m["expired"])
            cols[3].metric("Revoked", m["revoked"])

            cols2 = st.columns(2)
            cols2[0].metric(
                "Notifications", m["total_notifications"],
            )
            cols2[1].metric(
                "Delivery rate",
                f"{m['notification_delivery_rate_pct']}%",
            )

            if m["total_sessions"] and m["revoked"]:
                rev_rate = round(
                    100 * m["revoked"] / m["total_sessions"], 1,
                )
                if rev_rate > 5:
                    st.warning(
                        f"Revocation rate at {rev_rate}% — "
                        f"investigate device security incidents.",
                    )


main()
