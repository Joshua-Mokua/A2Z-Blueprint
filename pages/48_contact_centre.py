"""pages/48_contact_centre.py — Contact Centre Dashboard.
Call volumes, AHT, FCR, CSAT, agent scorecards, queue view.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("contact_centre")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📞 Contact Centre</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Calls · AHT · FCR · CSAT · Queue · Agent scorecards</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=15)
def _load():
    p = DATA/"contact_centre.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("Contact centre data not available."); st.stop()

td   = data.get("today",{})
agents = data.get("agents",[])
queue  = data.get("queue_now",{})

# Live queue alert
if queue.get("waiting",0) > cfg("cc_queue_alert_high",8):
    st.error(f"🔴 HIGH QUEUE: {queue['waiting']} callers waiting · Longest wait: {queue['longest_wait_sec']}s")
elif queue.get("waiting",0) > cfg("cc_queue_alert_low",3):
    st.warning(f"⚠️ {queue.get('waiting',0)} callers waiting · Longest wait: {queue.get('longest_wait_sec',0)}s")
else:
    st.success(f"✅ Queue clear: {queue.get('waiting',0)} waiting")

tabs = st.tabs(["📊 Today","👤 Agent Scorecards","📋 Issue Breakdown","📈 Monthly Trend"])

with tabs[0]:
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Calls Received",  td.get("calls_received",0))
    c2.metric("Answered",        td.get("calls_answered",0))
    c3.metric("Abandoned",       td.get("abandoned",0),
              delta_color="normal" if td.get("abandoned",0)<cfg("cc_abandoned_target",100) else "inverse")
    c4.metric("SLA ≤30s",        f"{td.get('sla_within_30s_pct',0):.1f}%",
              delta_color="normal" if td.get("sla_within_30s_pct",0)>=cfg("contact_centre_sla_pct",80) else "inverse")
    c5.metric("FCR",             f"{td.get('fcr_pct',0):.1f}%",
              delta_color="normal" if td.get("fcr_pct",0)>=cfg("contact_centre_fcr_pct",70) else "inverse")
    c6.metric("CSAT",            f"{td.get('csat_score',0):.1f}/5.0",
              delta_color="normal" if td.get("csat_score",0)>=cfg("cc_csat_target",3.5) else "inverse")
    c1,c2,c3 = st.columns(3)
    aht_min = td.get("aht_seconds",0)//60
    aht_sec = td.get("aht_seconds",0)%60
    c1.metric("AHT",    f"{aht_min}m {aht_sec}s")
    c2.metric("Avg Wait",f"{td.get('avg_wait_seconds',0)}s")
    c3.metric("Escalations",td.get("escalations",0))

with tabs[1]:
    st.markdown("**Agent scorecards — today:**")
    status_icon = {"Available":"🟢","On Call":"🔵","Wrap-up":"🟡","Break":"⚪"}
    a_rows=[{"Agent":a["name"],"Status":status_icon.get(a["status"],"")+a["status"],
              "Calls":a["calls_today"],"AHT":f"{a['aht_seconds']//60}m {a['aht_seconds']%60}s",
              "FCR%":a["fcr_pct"],"CSAT":a["csat"],
              "Grade":("🟢" if a["fcr_pct"]>=75 and a["csat"]>=4.0 else "🟡" if a["fcr_pct"]>=60 else "🔴")}
             for a in sorted(agents,key=lambda x:-x["calls_today"])]
    st.dataframe(pd.DataFrame(a_rows),use_container_width=True,hide_index=True)

with tabs[2]:
    issues = data.get("common_issues",[])
    i_rows=[{"Issue":i["issue"],"Count":i["count"],"Share":f"{i['pct']:.1f}%"} for i in issues]
    st.dataframe(pd.DataFrame(i_rows),use_container_width=True,hide_index=True)
    st.bar_chart(pd.DataFrame({"Calls":[i["count"] for i in issues]},
                               index=[i["issue"] for i in issues]))

with tabs[3]:
    monthly = data.get("monthly",[])
    if monthly:
        st.line_chart(pd.DataFrame({"Calls":[m["calls"] for m in monthly],
                                     "FCR%":[m["fcr"] for m in monthly]},
                                    index=[m["month"] for m in monthly]))
