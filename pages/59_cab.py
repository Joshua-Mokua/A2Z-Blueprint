"""pages/59_cab.py — Change Management Register (CAB)."""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("cab")

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
is_admin = ud.get("is_admin", False)
is_it    = any(x in ud.get("role","").lower() for x in ("ict","digital","information","database","network","manager core banking"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔄 Change Management (CAB)</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Change requests · CAB approvals · Rollback plans · PIR</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA / "cab_register.json"
    return json.loads(p.read_text()) if p.exists() else []

changes = _load()
open_c  = [c for c in changes if c.get("status") in ("Draft","Pending CAB","CAB Approved","Implementing")]
emerg   = [c for c in changes if c.get("change_type") == "Emergency" and c.get("status") not in ("Completed","Cancelled")]
cbk_req = [c for c in changes if c.get("cbk_notification_required") and c.get("status") not in ("Completed","Cancelled")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Changes",    len(changes))
m2.metric("Open / Active",    len(open_c))
m3.metric("Emergency Changes",len(emerg),  delta_color="normal" if not emerg else "inverse")
m4.metric("CBK Notification", len(cbk_req),delta_color="normal" if not cbk_req else "inverse")

if emerg:
    st.error(f"🔴 {len(emerg)} emergency change(s) active — expedited CAB review required")
if cbk_req:
    st.warning(f"⚠️ {len(cbk_req)} change(s) require CBK notification per ICT/08/2019")

tabs = st.tabs(["📋 All Changes","⚡ Emergency","📊 Analytics","➕ New Change","✅ PIR"])

def _render_changes(chg_list):
    if not chg_list: st.success("None here."); return
    rows = [{"ID": c["id"], "Title": c["title"][:40], "System": c["system"][:20],
              "Type": c["change_type"], "Risk": c["risk_level"],
              "Status": c["status"][:20], "CAB Date": c.get("cab_date","")[:10],
              "Planned": c.get("planned_start","")[:10],
              "CBK": "⚠️" if c.get("cbk_notification_required") else "",
              "PIR": "✅" if c.get("post_impl_review") else ""}
             for c in sorted(chg_list, key=lambda x: x.get("planned_start",""))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[0]:
    f1, f2 = st.columns(2)
    ftype = f1.selectbox("Type", ["All","Standard","Normal","Emergency","Pre-approved"], key="cab_tp")
    frisk = f2.selectbox("Risk", ["All","High","Medium","Low"], key="cab_rsk")
    vis   = [c for c in changes
             if (ftype=="All" or c.get("change_type")==ftype)
             and (frisk=="All" or c.get("risk_level")==frisk)]
    _render_changes(vis)

with tabs[1]:
    _render_changes(emerg)
    if emerg:
        st.markdown("Emergency changes require post-implementation review within 48 hours.")

with tabs[2]:
    sys_ct = Counter(c["system"] for c in changes)
    st.markdown("**Changes by system:**")
    st.bar_chart(pd.DataFrame({"Count": dict(sys_ct.most_common(8))}).T.T)
    status_ct = Counter(c["status"] for c in changes)
    st.markdown("**Changes by status:**")
    st.bar_chart(pd.DataFrame({"Count": dict(status_ct.most_common())}).T.T)

with tabs[3]:
    if is_it or is_admin:
        SYSTEMS = ["Core Banking (T24)","Mobile App","Internet Banking","SWIFT","ATM Network",
                   "Internal Network","Database","Email Platform","CBS API","Other"]
        r1, r2, r3 = st.columns(3)
        _sys   = r1.selectbox("System", SYSTEMS, key="cab_nsys")
        _ctype = r2.selectbox("Change type", ["Standard","Normal","Emergency","Pre-approved"], key="cab_ntype")
        _risk  = r3.selectbox("Risk level", ["Low","Medium","High"], key="cab_nrisk")
        _title = st.text_input("Change title", key="cab_ntitle")
        _impact= st.text_input("Customer impact", placeholder="e.g. No downtime / Maintenance window 02:00-04:00", key="cab_nimp")
        _rb    = st.text_area("Rollback plan", height=60, key="cab_nrb")
        _cbk   = st.checkbox("CBK notification required", key="cab_ncbk")
        if st.button("➕ Submit change request", key="cab_create", type="primary"):
            if _title.strip():
                all_c = json.loads((DATA/"cab_register.json").read_text())
                all_c.append({
                    "id": f"CHG{len(all_c)+1:05d}", "title": _title.strip(),
                    "system": _sys, "change_type": _ctype, "risk_level": _risk,
                    "status": "Draft", "requestor": uname,
                    "cab_date": "", "planned_start": "", "planned_end": "", "actual_end": "",
                    "rollback_plan": _rb, "impact": _impact,
                    "cbk_notification_required": _cbk, "post_impl_review": False, "pir_outcome": "", "notes": ""
                })
                (DATA/"cab_register.json").write_text(json.dumps(all_c, indent=2))
                audit_log("CAB_CHANGE_RAISED", uname, f"{_ctype}: {_title[:60]}")
                _bsc_trigger(uname, "K036")
                st.cache_data.clear(); st.success("✅ Change request submitted"); st.rerun()
            else: st.error("Title required.")
    else:
        st.info("Change request submission available to IT team.")

with tabs[4]:
    pir_due = [c for c in changes if c.get("status")=="Completed" and not c.get("post_impl_review")]
    st.markdown(f"**{len(pir_due)} completed change(s) pending Post-Implementation Review:**")
    if pir_due:
        for c in pir_due[:10]:
            with st.expander(f"{c['id']}: {c['title'][:50]}"):
                outcome = st.selectbox("PIR outcome", ["Successful","Partially successful","Issues noted"], key=f"pir_{c['id']}")
                if st.button("✅ Record PIR", key=f"pir_save_{c['id']}", type="primary"):
                    all_c = json.loads((DATA/"cab_register.json").read_text())
                    for c2 in all_c:
                        if c2["id"]==c["id"]: c2["post_impl_review"]=True; c2["pir_outcome"]=outcome
                    (DATA/"cab_register.json").write_text(json.dumps(all_c, indent=2))
                    audit_log("CAB_PIR_RECORDED", uname, f"{c['id']}: {outcome}")
                    _bsc_trigger(uname, "K036")
                    st.cache_data.clear(); st.success("✅ PIR recorded"); st.rerun()
    else:
        st.success("✅ All completed changes have PIRs on file.")
