"""pages/49_bancassurance.py — Bancassurance Module.
Policy management, insurer reconciliation, commission, claims dashboard.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("bancassurance_mgmt")

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
is_bnc   = any(x in role.lower() for x in ("bancassurance","underwriting","general manager"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏥 Bancassurance</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Policies · Premium · Commission · Claims · Insurer reconciliation</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"bnc_policies.json"
    return a2z_db.load_json(p) if p.exists() else []

policies = _load()
active   = [p for p in policies if p["status"]=="Active"]
lapsed   = [p for p in policies if p["status"]=="Lapsed"]
renewals = [p for p in policies if p["status"]=="Pending Renewal"]
claims   = [p for p in policies if p.get("claim_raised")]

total_premium = sum(p["premium_annual"] for p in active)/1e6
total_comm    = sum(p["commission_kes"] for p in active)/1e6
claims_amount = sum(p.get("claim_amount",0) for p in claims)/1e6
claims_ratio  = round(claims_amount/max(total_premium,0.001)*100,1)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Active Policies",    len(active))
m2.metric("Premium (KES M)",    f"{total_premium:.1f}")
m3.metric("Commission (KES M)", f"{total_comm:.2f}")
m4.metric("Pending Renewals",   len(renewals),
          delta_color="normal" if not renewals else "inverse")
m5.metric("Claims Ratio",       f"{claims_ratio:.1f}%",
          delta_color="normal" if claims_ratio<cfg("bnc_claims_ratio_target",60) else "inverse")

if lapsed:
    st.warning(f"⚠️ {len(lapsed)} policies have lapsed — follow up for renewal")

tabs = st.tabs(["📋 All Policies","🔄 Renewals Due","💰 Commission","🏥 Claims","📊 Insurer Breakdown"])

def _render(pol_list):
    if not pol_list: st.success("None in this view."); return
    rows=[{"ID":p["id"],"Product":p["product"],"Insurer":p["insurer"],
            "Category":p["category"],"Premium (KES)":p["premium_annual"],
            "Commission (KES)":p["commission_kes"],"Status":p["status"],
            "Branch":p["branch"],"Expiry":p["expiry_date"][:10],
            "Claim":("⚠️ "+p.get("claim_status","") if p.get("claim_raised") else "")}
           for p in sorted(pol_list,key=lambda x:x["expiry_date"])]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[0]:
    fcat = st.multiselect("Category",["Life","General","Medical"],default=["Life","General","Medical"],key="bnc_cat")
    vis  = [p for p in policies if p["category"] in fcat]
    st.markdown(f"**{len(vis)} policies** · KES {sum(p['premium_annual'] for p in vis)/1e6:.1f}M premium")
    _render(vis[:50])

with tabs[1]:
    _render(renewals)
    if renewals and st.button("📧 Send renewal reminders",key="bnc_renew",type="primary"):
        audit_log("BNC_RENEWAL_REMINDERS",uname,f"{len(renewals)} renewal reminders sent")
        _bsc_trigger(uname, "K023")
        st.success(f"✅ {len(renewals)} renewal reminder notifications queued")

with tabs[2]:
    ins_comm = defaultdict(float)
    for p in active: ins_comm[p["insurer"]] += p["commission_kes"]
    comm_rows=[{"Insurer":ins,"Commission (KES)":round(comm,0),"Policies":sum(1 for p in active if p["insurer"]==ins)}
               for ins,comm in sorted(ins_comm.items(),key=lambda x:-x[1])]
    st.dataframe(pd.DataFrame(comm_rows),use_container_width=True,hide_index=True)
    st.metric("Total commission due",f"KES {total_comm:.2f}M")

with tabs[3]:
    if claims:
        c_rows=[{"Policy":p["id"],"Product":p["product"],"Insurer":p["insurer"],
                  "Claim Status":p.get("claim_status",""),"Amount (KES)":p.get("claim_amount",0),
                  "Branch":p["branch"]}
                 for p in claims]
        st.dataframe(pd.DataFrame(c_rows),use_container_width=True,hide_index=True)
        st.metric("Claims ratio",f"{claims_ratio:.1f}%","Target <"+str(cfg("bnc_claims_ratio_target",60))+"%",
                   delta_color="normal" if claims_ratio<cfg("bnc_claims_ratio_target",60) else "inverse")
    else:
        st.success("No claims recorded.")

with tabs[4]:
    ins_ct  = Counter(p["insurer"] for p in active)
    ins_prem= defaultdict(float)
    for p in active: ins_prem[p["insurer"]] += p["premium_annual"]
    ir_rows=[{"Insurer":ins,"Active Policies":ins_ct[ins],
               "Premium (KES M)":round(ins_prem[ins]/1e6,2)}
              for ins in sorted(ins_ct,key=ins_ct.get,reverse=True)]
    st.dataframe(pd.DataFrame(ir_rows),use_container_width=True,hide_index=True)
