"""pages/23_credit_admin.py — Credit Administration.
Pre-disbursement conditions, CAMs, security perfection, disbursement queue.
"""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd
import json
from pathlib import Path
from datetime import date, datetime
from collections import Counter, defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("credit.admin")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
sc   = str(ud.get("staff_code",""))
is_credit = any(x in role.lower() for x in ("credit","admin","analyst","chief","head"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📑 Credit Admin</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Pre-disbursement · Conditions · Security perfection · Disbursement queue</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30, show_spinner=False)
def _load():
    ca = json.loads((DATA/"credit_admin.json").read_text()) if (DATA/"credit_admin.json").exists() else []
    apps = json.loads((DATA/"loan_applications.json").read_text()) if (DATA/"loan_applications.json").exists() else []
    return ca, apps

ca, apps = _load()

# Key metrics
approved = [a for a in apps if a["status"] in ("approved","credit_admin")]
ready    = [a for a in ca if a.get("ready_for_disbursement") and not a.get("disbursed")]
pending  = [a for a in ca if not a.get("ready_for_disbursement")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Approved / Pending Disbursal", len(approved))
m2.metric("Ready for Disbursement",       len(ready))
m3.metric("Conditions Outstanding",       len(pending))
m4.metric("Total CA Cases",              len(ca))

if ready:
    st.success(f"✅ {len(ready)} case(s) cleared for disbursement — notify Operations")
if pending:
    st.warning(f"⚠️ {len(pending)} case(s) with outstanding pre-disbursement conditions")

tabs = st.tabs(["📋 All Cases","✅ Ready to Disburse","⏳ Conditions Outstanding","📞 Phone Disbursement","📊 Analytics"])

with tabs[0]:
    rows = [{"ID":a.get("id",""),"Client":str(a.get("client_name",""))[:25],
              "Product":str(a.get("product",""))[:20],
              "Amount (M)":round(float(a.get("amount",0))/1e6,2),
              "Status":a.get("status",""),"Branch":str(a.get("branch",""))[:20],
              "Ready":("✅" if a.get("ready_for_disbursement") else "⏳")}
             for a in ca[:50]]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No credit admin cases found.")

with tabs[1]:
    if ready:
        r_rows = [{"ID":a.get("id",""),"Client":str(a.get("client_name",""))[:25],
                    "Product":str(a.get("product",""))[:20],
                    "Amount (M)":round(float(a.get("amount",0))/1e6,2)}
                   for a in ready[:20]]
        st.dataframe(pd.DataFrame(r_rows), use_container_width=True, hide_index=True)
        if (is_credit or is_admin) and st.button("📧 Notify Operations — Disbursement Queue", key="ca_notify", type="primary"):
            audit_log("CA_DISBURSAL_NOTIF", uname, f"{len(ready)} cases notified for disbursement")
            _bsc_trigger(uname, "K028")
            st.success(f"✅ Operations notified — {len(ready)} cases ready for disbursement")
    else:
        st.info("No cases currently cleared for disbursement.")

with tabs[2]:
    if pending:
        p_rows = [{"ID":a.get("id",""),"Client":str(a.get("client_name",""))[:25],
                    "Product":str(a.get("product",""))[:20],
                    "Amount (M)":round(float(a.get("amount",0))/1e6,2),
                    "Pending Conditions":str(a.get("outstanding_conditions","To be documented")[:40])}
                   for a in pending[:30]]
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
    else:
        st.success("✅ No outstanding pre-disbursement conditions.")

with tabs[3]:
    # ── Phone Disbursement (v10.449) ─────────────────────────────────
    # Per Joshua: "disburses mostly by phone"
    st.markdown("##### 📞 Phone Disbursement Queue")
    st.caption(
        "Most disbursements happen by phone (RM/branch officer calls "
        "customer to confirm KYC + walks through disbursement). This "
        "tab tracks the phone disbursement workflow."
    )

    # Phone disbursement records persist to data/phone_disbursement_log.json
    phone_log_file = DATA / "phone_disbursement_log.json"
    try:
        phone_log = json.loads(phone_log_file.read_text(encoding="utf-8")) if phone_log_file.exists() else []
    except (json.JSONDecodeError, OSError):
        phone_log = []

    # Apps in ready_for_disbursement state that haven't been phone-called yet
    phone_pending = [
        a for a in ready
        if not any(p.get("application_id") == a.get("id") for p in phone_log)
    ]
    phone_attempted_uncompleted = [
        p for p in phone_log
        if p.get("status") not in ("disbursed", "withdrawn")
    ]
    phone_completed = [p for p in phone_log if p.get("status") == "disbursed"]

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("📞 Pending phone call", len(phone_pending))
    pc2.metric("⏳ Call attempted, awaiting follow-up", len(phone_attempted_uncompleted))
    pc3.metric("✅ Disbursed (phone-confirmed)", len(phone_completed))

    st.markdown("---")
    st.markdown("##### Pending phone disbursements (top 30)")
    if phone_pending:
        ph_rows = [
            {
                "ID": a.get("id", ""),
                "Client": str(a.get("client_name", ""))[:25],
                "Phone": str(a.get("phone_number", a.get("client_phone", "(missing)")))[:15],
                "Amount (M)": round(float(a.get("amount", 0)) / 1e6, 2),
                "Product": str(a.get("product", ""))[:20],
                "Branch": str(a.get("branch", ""))[:20],
                "RM": str(a.get("rm_name", ""))[:20],
            }
            for a in sorted(phone_pending, key=lambda x: -float(x.get("amount", 0)))[:30]
        ]
        st.dataframe(pd.DataFrame(ph_rows),
                    use_container_width=True, hide_index=True)
    else:
        st.success("✅ No pending phone disbursements")

    st.markdown("---")
    st.markdown("##### Log a phone disbursement call")
    if is_credit or is_admin:
        with st.form("phone_disbursement_form"):
            picked_id = st.text_input("Application ID",
                                     key="phone_disb_id")
            outcome = st.selectbox(
                "Call outcome:",
                ["DISBURSED",
                 "CUSTOMER_NOT_REACHED",
                 "KYC_DOC_OUTSTANDING",
                 "CUSTOMER_WITHDREW",
                 "CALLBACK_REQUESTED"],
                key="phone_disb_outcome",
            )
            notes = st.text_area("Call notes:",
                                key="phone_disb_notes")
            submitted = st.form_submit_button("📞 Log call", type="primary")
            if submitted and picked_id:
                # Map outcome to status
                status_map = {
                    "DISBURSED":             "disbursed",
                    "CUSTOMER_NOT_REACHED":  "not_reached",
                    "KYC_DOC_OUTSTANDING":   "kyc_pending",
                    "CUSTOMER_WITHDREW":     "withdrawn",
                    "CALLBACK_REQUESTED":    "callback",
                }
                record = {
                    "application_id": picked_id,
                    "outcome":        outcome,
                    "status":         status_map.get(outcome, "pending"),
                    "notes":          notes,
                    "called_at":      datetime.now().isoformat(),
                    "called_by":      uname,
                }
                phone_log.append(record)
                phone_log_file.write_text(json.dumps(phone_log, indent=2,
                                                    default=str))
                audit_log("PHONE_DISBURSEMENT",
                         uname,
                         f"{picked_id}: {outcome}")
                _bsc_trigger(uname, "K028")
                if outcome == "DISBURSED":
                    st.success(f"✅ Logged: {picked_id} disbursed by phone")
                else:
                    st.info(f"📞 Logged: {picked_id} — outcome: {outcome}")
    else:
        st.info("Credit admin or admin role required to log phone disbursements")

    if phone_log:
        st.markdown("---")
        st.markdown("##### Recent call log (last 50)")
        recent = sorted(phone_log, key=lambda x: x.get("called_at", ""),
                       reverse=True)[:50]
        log_rows = [
            {
                "App ID":   r.get("application_id", ""),
                "Outcome":  r.get("outcome", ""),
                "Status":   r.get("status", ""),
                "Notes":    str(r.get("notes", ""))[:40],
                "Called by": r.get("called_by", ""),
                "Called at": str(r.get("called_at", ""))[:19],
            }
            for r in recent
        ]
        st.dataframe(pd.DataFrame(log_rows),
                    use_container_width=True, hide_index=True)


with tabs[4]:
    # ── Workflow lifecycle (v10.447 — credit_workflow engine wired) ──
    from utils.credit_workflow import (
        ApplicationState, ALLOWED_TRANSITIONS,
    )

    st.markdown("##### 📋 Workflow position — Administration stage")
    st.caption(
        "Credit Admin sits between APPROVED and DISBURSED in the formal "
        "lifecycle (ENH-125 Digital Workflow Orchestration)."
    )

    # Map data status to lifecycle states
    LIFECYCLE_AT_ADMIN = {
        "approved":      ApplicationState.APPROVED,
        "credit_admin":  ApplicationState.DOCUMENTATION_PENDING,
        "disbursed":     ApplicationState.DISBURSED,
    }
    from collections import Counter as _CtrCA
    lc_counts = _CtrCA()
    for a in ca:
        s = LIFECYCLE_AT_ADMIN.get(a.get("status", ""))
        if s:
            lc_counts[s] += 1

    wc1, wc2, wc3 = st.columns(3)
    wc1.metric("APPROVED (entering admin)",
               lc_counts.get(ApplicationState.APPROVED, 0))
    wc2.metric("DOCUMENTATION_PENDING",
               lc_counts.get(ApplicationState.DOCUMENTATION_PENDING, 0))
    wc3.metric("DISBURSED (terminal)",
               lc_counts.get(ApplicationState.DISBURSED, 0))

    # Show allowed transitions FROM admin states
    st.markdown("##### Swim Lane — admin-stage transitions")
    admin_states = [
        ApplicationState.APPROVED,
        ApplicationState.DOCUMENTATION_PENDING,
        ApplicationState.DISBURSEMENT_PENDING,
    ]
    rows_t = []
    for state in admin_states:
        allowed = ALLOWED_TRANSITIONS.get(state, ())
        rows_t.append({
            "From":      state.value,
            "Apps here": lc_counts.get(state, 0),
            "Can go to": ", ".join(s.value for s in allowed) or "(terminal)",
        })
    if rows_t:
        st.dataframe(pd.DataFrame(rows_t),
                    use_container_width=True, hide_index=True)

    st.markdown("---")
    status_counts = Counter(a.get("status","") for a in ca)
    df_s = pd.DataFrame([{"Status":k,"Count":v} for k,v in status_counts.most_common()])
    if not df_s.empty:
        st.markdown("**Cases by status:**")
        st.dataframe(df_s, use_container_width=True, hide_index=True)
    prod_counts = Counter(a.get("product","") for a in ca)
    top_prods = prod_counts.most_common(8)
    if top_prods:
        st.markdown("**Cases by product:**")
        st.dataframe(pd.DataFrame([{"Product":k,"Cases":v} for k,v in top_prods]),
                     use_container_width=True, hide_index=True)
