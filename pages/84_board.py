"""pages/84_board.py — Board Pack & Papers.
Submission tracking, action items, follow-through.
Dept: Executive | KPIs: K104 K105
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.db import db as a2z_db

require_access("board_papers")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_exec  = any(x in role for x in ("md","ceo","director","chief","secretary","head","manager","legal"))

COMMITTEES = ["Main Board","Board Audit Committee","Board Risk Committee","Board Credit Committee",
              "Board Nomination Committee","Board IT Committee","Board Compensation Committee","ALCO"]
PAPER_TYPES = ["Strategy Update","Quarterly Performance","Risk Report","Audit Report","Credit Approval",
               "Capital Plan","Compliance Report","Operational Report","Project Status","Customer Update",
               "Cybersecurity","ESG Report","HR Report"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"board_papers.json", table="board_papers")

def _save(data):
    a2z_db.dual_save(DATA/"board_papers.json", data, table="board_papers", flat_cols=('id', 'title', 'type', 'committee', 'meeting_date', 'submission_deadline', 'submitted_date', 'submitted_on_time', 'submitted_by', 'status', 'action_items', 'actions_closed', 'department'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("board_papers",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()

submitted = [r for r in records if r.get("submitted_date")]
on_time   = [r for r in records if r.get("submitted_on_time")]
on_time_pct = round(len(on_time)/max(len(submitted),1)*100,1)
total_actions = sum(r.get("action_items",0) for r in records)
closed_actions= sum(r.get("actions_closed",0) for r in records)
overdue_actions = sum(r.get("actions_overdue",0) for r in records)
actions_closed_pct = round(closed_actions/max(total_actions,1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 Board Pack & Papers</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Executive · K104 · K105</span></div>",
    unsafe_allow_html=True)

if overdue_actions>10: st.warning(f"⚠️ {overdue_actions} board action items overdue")
if on_time_pct < 80: st.warning(f"⚠️ Only {on_time_pct}% of board papers submitted on time")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total papers",  len(records))
m2.metric("On time",       f"{on_time_pct}%", delta_color="off" if on_time_pct>=80 else "inverse")
m3.metric("Action items",  total_actions)
m4.metric("Actions closed",f"{actions_closed_pct}%")
m5.metric("Overdue",       overdue_actions, delta_color="inverse" if overdue_actions else "off")

tabs = st.tabs(["📋 Papers","🎯 Action Items","➕ New Paper","📊 By Committee","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    fcom = f1.selectbox("Committee",["All"]+COMMITTEES,key="bp_fcom")
    ftyp = f2.selectbox("Type",["All"]+PAPER_TYPES,key="bp_ftyp")
    fstat= f3.selectbox("Status",["All","Approved","Under Review","Returned"],key="bp_fstat")
    vis = [r for r in records
           if (fcom=="All" or r.get("committee","")==fcom)
           and (ftyp=="All" or r.get("type","")==ftyp)
           and (fstat=="All" or r.get("status","")==fstat)]
    rows = [{"Title":r.get("title","")[:30],"Committee":r.get("committee","")[:18],
              "Type":r.get("type","")[:18],"Meeting":r.get("meeting_date","")[:10],
              "Submitted":r.get("submitted_date","")[:10],
              "On time":"✅" if r.get("submitted_on_time") else "❌",
              "Status":r.get("status",""),
              "Actions":f"{r.get('actions_closed',0)}/{r.get('action_items',0)}"}
             for r in sorted(vis,key=lambda x:x.get("meeting_date",""),reverse=True)]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    open_papers = [r for r in records if r.get("action_items",0)>r.get("actions_closed",0)]
    if open_papers:
        for r in open_papers[:30]:
            with st.expander(f"📌 {r.get('title','')} — {r.get('actions_closed',0)}/{r.get('action_items',0)} actions closed"):
                if (is_exec or is_admin) and st.button("Close one action",key=f"bp_ac_{r['id']}"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"]==r["id"]:
                            rec["actions_closed"]=min(rec.get("actions_closed",0)+1,rec.get("action_items",0))
                            break
                    _save(all_r); audit_log("BOARD_ACTION_CLOSED",uname,r["id"]); _bsc_trigger(uname,"K105")
                    st.success("✅ Action closed"); st.rerun()

with tabs[2]:
    if is_exec or is_admin:
        r1,r2 = st.columns(2)
        title = r1.text_input("Paper title *",key="bp_n_title")
        com   = r2.selectbox("Committee",COMMITTEES,key="bp_n_com")
        ptyp  = r1.selectbox("Type",PAPER_TYPES,key="bp_n_typ")
        meet  = r2.date_input("Meeting date",today+timedelta(days=14),key="bp_n_meet")
        deadl = r1.date_input("Submission deadline",today+timedelta(days=7),key="bp_n_deadl")
        if st.button("💾 Create paper",key="bp_n_save",type="primary"):
            if title.strip():
                all_r = _load()
                all_r.append({"id":f"BP{len(all_r)+1:04d}","title":title,"type":ptyp,
                              "committee":com,"meeting_date":str(meet),
                              "submission_deadline":str(deadl),"submitted_date":"",
                              "submitted_on_time":False,"submitted_by":uname,
                              "approved_by":"","status":"Under Review",
                              "action_items":0,"actions_closed":0,"actions_overdue":0,
                              "decisions_taken":0,"department":ud.get("department",""),
                              "pages":0,"supporting_docs":0,"circulated_to":7,
                              "next_review":"","notes":""})
                _save(all_r); audit_log("BOARD_PAPER_CREATED",uname,title); _bsc_trigger(uname,"K104")
                st.success("✅ Paper created"); st.rerun()

with tabs[3]:
    by_com = defaultdict(lambda:{"count":0,"on_time":0,"actions":0,"closed":0})
    for r in records:
        c = r.get("committee","Other")
        by_com[c]["count"] += 1
        if r.get("submitted_on_time"): by_com[c]["on_time"] += 1
        by_com[c]["actions"] += r.get("action_items",0)
        by_com[c]["closed"]  += r.get("actions_closed",0)
    rows = [{"Committee":c,"Papers":v["count"],
              "On time":f"{v['on_time']}/{v['count']}",
              "Actions":f"{v['closed']}/{v['actions']}"}
             for c,v in by_com.items()]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: 8 committees, 7-day minimum circulation, CBK Corporate Governance Guidelines")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("board_papers",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_buf = c1.number_input("Deadline buffer (days)",1,30,int(cfg_m.get("deadline_buffer_days",7)),key="bp_c_buf")
        new_act = c2.number_input("Action target (days)",7,90,int(cfg_m.get("action_item_target_days",30)),key="bp_c_act")
        if st.button("💾 Save",key="bp_cfg_save",type="primary"):
            cfg_m.update({"deadline_buffer_days":new_buf,"action_item_target_days":new_act})
            mc["board_papers"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("BOARD_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[5]:
    bsc_rows=[
        {"KPI":"K104 — Papers On Time","Target":"> 90%","Actual":f"{on_time_pct}%","Status":"🟢" if on_time_pct>=90 else "🟡","Weight":"5%"},
        {"KPI":"K105 — Actions Closed","Target":"> 80%","Actual":f"{actions_closed_pct}%","Status":"🟢" if actions_closed_pct>=80 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="bp_bsc",type="primary"):
        _bsc_trigger(uname,"K104"); st.success("✅ BSC updated"); st.rerun()
