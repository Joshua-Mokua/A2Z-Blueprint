"""pages/51_agency_banking.py — Agency Banking Monitor.
Agent locations, float levels, txn volumes, downtime, compliance.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("agency_banking")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏪 Agency Banking</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Agent network · Float · Transactions · Compliance · Downtime</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"agents_data.json"
    return a2z_db.load_json(p) if p.exists() else []

agents = _load()
active  = [a for a in agents if a["status"]=="Active"]
inactive= [a for a in agents if a["status"]!="Active"]
low_float = [a for a in active if a["float_utilisation_pct"]>cfg("agent_float_alert_pct",90)]
no_txn    = [a for a in active if a["txn_count_today"]==0]
non_comp  = [a for a in agents if not a.get("compliance_docs_complete")]

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Agents",      len(agents))
m2.metric("Active",            len(active))
m3.metric("Low Float (>90%)",  len(low_float), delta_color="normal" if not low_float else "inverse")
m4.metric("No Txns Today",     len(no_txn),    delta_color="normal" if not no_txn else "inverse")
m5.metric("Compliance Gap",    len(non_comp),  delta_color="normal" if not non_comp else "inverse")

if low_float:
    st.warning(f"⚠️ {len(low_float)} agents with float utilisation >90% — top up required")
if non_comp:
    st.error(f"🔴 {len(non_comp)} agents with incomplete compliance documentation")

tabs = st.tabs(["📋 All Agents","⚠️ Alerts","📊 Analytics","📍 By Town"])

def _render(agent_list):
    if not agent_list: st.success("None here."); return
    rows=[{"ID":a["id"],"Town":a["town"],"Status":a["status"],
            "Float (KES)":f"{a['float_balance']:,.0f}",
            "Float Util%":f"{a['float_utilisation_pct']:.0f}%",
            "Txns Today":a["txn_count_today"],
            "Value Today (KES)":f"{a['txn_value_today_kes']:,.0f}",
            "Uptime 30d":f"{a['uptime_30d_pct']:.0f}%",
            "Docs OK":("✅" if a.get("compliance_docs_complete") else "❌"),
            "Last Txn":a.get("last_txn","")[:10]}
           for a in sorted(agent_list,key=lambda x:-x["txn_count_today"])]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[0]:
    f1,f2 = st.columns(2)
    fstat  = f1.selectbox("Status",["All","Active","Inactive","Suspended"],key="agn_stat")
    ftown  = f2.selectbox("Town",["All"]+sorted(set(a["town"] for a in agents)),key="agn_town")
    vis = [a for a in agents
           if (fstat=="All" or a["status"]==fstat)
           and (ftown=="All" or a["town"]==ftown)]
    st.markdown(f"**{len(vis)} agents** · {sum(a['txn_count_today'] for a in vis):,} txns today")
    _render(vis[:30])

with tabs[1]:
    all_alerts = low_float + no_txn + non_comp
    if all_alerts:
        _render(list({a["id"]:a for a in all_alerts}.values()))
    else:
        st.success("✅ No agent alerts.")

with tabs[2]:
    st.markdown("**Float utilisation distribution:**")
    util_bins={"<50%":0,"50-75%":0,"75-90%":0,"90-100%":0,">100%":0}
    for a in active:
        u=a["float_utilisation_pct"]
        if u<cfg('agent_float_vlow',50): util_bins["<50%"]+=1
        elif u<cfg('agent_float_low',75): util_bins["50-75%"]+=1
        elif u<90: util_bins["75-90%"]+=1
        elif u<=100: util_bins["90-100%"]+=1
        else: util_bins[">100%"]+=1
    st.bar_chart(pd.DataFrame({"Agents":util_bins}))

with tabs[3]:
    town_ct  = Counter(a["town"] for a in active)
    town_txn = {}
    for a in active: town_txn[a["town"]] = town_txn.get(a["town"],0)+a["txn_count_today"]
    t_rows=[{"Town":t,"Active Agents":n,"Txns Today":town_txn.get(t,0)}
             for t,n in sorted(town_ct.items(),key=lambda x:-x[1])]
    st.dataframe(pd.DataFrame(t_rows),use_container_width=True,hide_index=True)
