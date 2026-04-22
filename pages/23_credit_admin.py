"""pages/23_credit_admin.py — Credit Administration.
Pre-disbursement conditions, CAMs, security perfection, disbursement queue.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("credit_admin")
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

tabs = st.tabs(["📋 All Cases","✅ Ready to Disburse","⏳ Conditions Outstanding","📊 Analytics"])

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
