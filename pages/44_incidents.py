"""pages/44_incidents.py — IT Incident Management.
P1-P4 incidents, SLA tracking, root cause, CBK-reportable events.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("incidents")

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
is_it    = any(x in role.lower() for x in ("ict","digital","information","network","database","head of ict","head of digital"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚨 Incident Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "P1–P4 incidents · SLA tracking · Root cause · CBK reportable</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"incidents.json"
    return a2z_db.load_json(p) if p.exists() else []

incidents = _load()
priority_ct = Counter(i["priority"] for i in incidents)
open_inc    = [i for i in incidents if i["status"] in ("Open","In Progress")]
breached    = [i for i in incidents if i.get("sla_breached")]
cbk_rep     = [i for i in incidents if i.get("cbk_reportable")]

PRIORITY_SLA = {"P1":4,"P2":8,"P3":24,"P4":72}

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("🔴 P1 (Critical)", priority_ct.get("P1",0))
m2.metric("🟠 P2 (High)",     priority_ct.get("P2",0))
m3.metric("🟡 P3 (Medium)",   priority_ct.get("P3",0))
m4.metric("SLA Breached",     len(breached), delta_color="normal" if not breached else "inverse")
m5.metric("CBK Reportable",   len(cbk_rep),  delta_color="normal" if not cbk_rep else "inverse")

if open_inc:
    p1_open = [i for i in open_inc if i["priority"]=="P1"]
    if p1_open:
        st.error(f"🔴 {len(p1_open)} P1 CRITICAL incidents open — immediate action required!")

tabs = st.tabs(["🔴 Open","📋 All Incidents","➕ Log Incident","📊 Analytics","📄 CBK Report"])

def _render_incidents(inc_list):
    if not inc_list: st.success("No incidents in this view."); return
    p_clr = {"P1":"#DC2626","P2":"#D97706","P3":"#3B82F6","P4":"#6B7280"}
    rows = [{"ID":i["id"],"Priority":i["priority"],"System":i["system"][:20],
              "Title":i["title"][:40],"Status":i["status"],
              "Assigned":i.get("assigned_to","")[:20],"Raised":i["raised_date"][:10],
              "Resolved":i.get("resolved_date","")[:10],
              "Resolution (hrs)":i.get("resolution_time_hours",""),
              "SLA (hrs)":PRIORITY_SLA.get(i["priority"],99),
              "CBK":("⚠️" if i.get("cbk_reportable") else ""),
              "SLA Breach":("🔴" if i.get("sla_breached") else "")}
             for i in sorted(inc_list,key=lambda x:{"P1":0,"P2":1,"P3":2,"P4":3}.get(x["priority"],4))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[0]: _render_incidents(open_inc)
with tabs[1]:
    f1,f2 = st.columns(2)
    fp = f1.multiselect("Priority",["P1","P2","P3","P4"],default=["P1","P2"],key="inc_pri")
    fs = f2.selectbox("Status",["All","Open","In Progress","Resolved","Closed"],key="inc_stat")
    vis = [i for i in incidents
           if i["priority"] in fp
           and (fs=="All" or i["status"]==fs)]
    _render_incidents(vis)

with tabs[2]:
    st.markdown("**Log a new incident:**")
    i1,i2,i3 = st.columns(3)
    inc_sys  = i1.selectbox("System",["Core Banking (T24)","Mobile App","USSD Gateway","Internet Banking","ATM Network","SWIFT","Internal Network","Data Centre","Email Platform","CBS API","Other"],key="inc_sys")
    inc_pri  = i2.selectbox("Priority",["P1","P2","P3","P4"],key="inc_pri_new",
                             help="P1=Critical(≤4h), P2=High(≤8h), P3=Medium(≤24h), P4=Low(≤72h)")
    inc_stat = i3.selectbox("Initial status",["Open","In Progress"],key="inc_stat_new")
    inc_title= st.text_input("Incident title",key="inc_title")
    inc_desc = st.text_area("Description",height=80,key="inc_desc")
    inc_cbk  = st.checkbox("CBK reportable (P1 incidents affecting customer data or system availability)",key="inc_cbk")
    if st.button("🚨 Log incident",key="inc_log",type="primary"):
        if inc_title:
            all_i = json.loads((DATA/"incidents.json").read_text())
            new_id= f"INC{len(all_i)+1:05d}"
            all_i.append({"id":new_id,"title":inc_title,"system":inc_sys,"priority":inc_pri,
                           "status":inc_stat,"raised_by":uname,"assigned_to":"",
                           "raised_date":str(today),"resolved_date":"","resolution_time_hours":None,
                           "root_cause":"","cbk_reportable":inc_cbk,"sla_breached":False,"description":inc_desc})
            (DATA/"incidents.json").write_text(json.dumps(all_i,indent=2))
            audit_log("INCIDENT_LOGGED",uname,f"{new_id} {inc_pri}: {inc_title[:40]}")
            _bsc_trigger(uname, "K067")
            st.cache_data.clear(); st.success(f"✅ Incident {new_id} logged"); st.rerun()
        else: st.error("Title is required")

with tabs[3]:
    sys_ct  = Counter(i["system"] for i in incidents)
    st.markdown("**Incidents by system:**")
    st.bar_chart(pd.DataFrame({"Count":dict(sys_ct.most_common(8))}).T.T)
    st.markdown("**Resolution time by priority (hours, resolved incidents):**")
    res_inc = [i for i in incidents if i.get("resolution_time_hours")]
    if res_inc:
        pri_res = {}
        for p in ["P1","P2","P3","P4"]:
            vals = [i["resolution_time_hours"] for i in res_inc if i["priority"]==p]
            if vals: pri_res[p] = round(sum(vals)/len(vals),1)
        sla_df = pd.DataFrame({"Avg Resolution (hrs)":pri_res,"SLA Target (hrs)":PRIORITY_SLA})
        st.dataframe(sla_df,use_container_width=True)

with tabs[4]:
    st.markdown("**CBK-reportable incidents — must be reported within 24 hours:**")
    if cbk_rep:
        cr_rows=[{"ID":i["id"],"Priority":i["priority"],"System":i["system"],
                   "Title":i["title"][:40],"Status":i["status"],"Raised":i["raised_date"][:10]}
                  for i in cbk_rep]
        st.dataframe(pd.DataFrame(cr_rows),use_container_width=True,hide_index=True)
        st.warning(f"⚠️ {len(cbk_rep)} incident(s) require CBK notification per CBK/ICT/08/2019")
    else:
        st.success("No CBK-reportable incidents recorded.")
