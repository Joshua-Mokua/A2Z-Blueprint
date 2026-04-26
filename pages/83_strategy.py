"""pages/83_strategy.py — Strategic Initiatives.
Strategy execution dashboard. Links strategy to projects to BSC.
Dept: Executive | KPIs: K101 K102 K103
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log
from utils.db import db as a2z_db

require_access("strategic_initiatives")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_exec  = any(x in role for x in ("md","ceo","director","chief","head","strategy","manager"))

PILLARS = ["Customer Experience","Operational Excellence","Financial Performance",
           "People & Culture","Digital Transformation","Risk & Compliance"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"strategic_initiatives.json", table="strategic_initiatives")

def _save(data):
    a2z_db.dual_save(DATA/"strategic_initiatives.json", data, table="strategic_initiatives", flat_cols=('id', 'name', 'pillar', 'sponsor', 'owner', 'owner_username', 'start_date', 'target_end_date', 'actual_end_date', 'completion_pct', 'status', 'rag_status', 'budget_kes_m', 'spent_kes_m', 'department'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("strategic_initiatives",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
amber_threshold = conf_cfg.get("amber_threshold_completion_pct",70)
red_threshold   = conf_cfg.get("red_threshold_completion_pct",40)

on_track  = [r for r in records if r.get("status") in ("On Track","Completed")]
at_risk   = [r for r in records if r.get("status")=="At Risk"]
behind    = [r for r in records if r.get("status")=="Behind"]
completed = [r for r in records if r.get("status")=="Completed"]
on_track_pct = round(len(on_track)/max(len(records),1)*100,1)
exec_score   = round(sum(r.get("completion_pct",0) for r in records)/max(len(records),1),1)

# ROI vs plan
roi_data = [(r.get("expected_roi_pct",0), r.get("actual_roi_pct",0)) for r in completed]
avg_expected = sum(e for e,_ in roi_data)/max(len(roi_data),1)
avg_actual   = sum(a for _,a in roi_data)/max(len(roi_data),1)
roi_pct = round((avg_actual/max(avg_expected,1))*100,1) if avg_expected else 100

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🎯 Strategic Initiatives</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Executive · K101-K103</span></div>",
    unsafe_allow_html=True)

if behind: st.error(f"🔴 {len(behind)} initiative(s) BEHIND — escalate to ExCo")
if at_risk: st.warning(f"⚠️ {len(at_risk)} initiative(s) AT RISK")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Initiatives",     len(records))
m2.metric("On track",        len(on_track), delta_color="off" if on_track_pct>=70 else "inverse")
m3.metric("Completed",       len(completed))
m4.metric("Execution score", f"{exec_score}/100")
m5.metric("ROI vs plan",     f"{roi_pct}%")

tabs = st.tabs(["📊 Portfolio","📋 Initiatives","➕ New","📈 Pillars","⚙️ Config","📈 BSC"])

with tabs[0]:
    rag_counts = {"Green":0,"Amber":0,"Red":0}
    for r in records: rag_counts[r.get("rag_status","Amber")] = rag_counts.get(r.get("rag_status","Amber"),0)+1
    c1,c2,c3 = st.columns(3)
    c1.metric("🟢 Green", rag_counts.get("Green",0))
    c2.metric("🟡 Amber", rag_counts.get("Amber",0))
    c3.metric("🔴 Red",   rag_counts.get("Red",0))
    st.bar_chart(pd.DataFrame({"Initiatives":rag_counts}))

with tabs[1]:
    f1,f2 = st.columns(2)
    fpil = f1.selectbox("Pillar",["All"]+PILLARS,key="st_fpil")
    frag = f2.selectbox("RAG",["All","Green","Amber","Red"],key="st_frag")
    vis = [r for r in records
           if (fpil=="All" or r.get("pillar","")==fpil)
           and (frag=="All" or r.get("rag_status","")==frag)]
    rows=[{"ID":r["id"],"Name":r.get("name","")[:25],"Pillar":r.get("pillar","")[:20],
            "Sponsor":r.get("sponsor","")[:15],"Status":r.get("status",""),
            "RAG":r.get("rag_status",""),"Progress":f"{r.get('completion_pct',0)}%",
            "Budget(M)":r.get("budget_kes_m",0),"Spent(M)":r.get("spent_kes_m",0),
            "Target":r.get("target_end_date","")[:10]} for r in vis]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[2]:
    if is_exec or is_admin:
        r1,r2 = st.columns(2)
        nm    = r1.text_input("Name *",key="st_n_nm")
        pil   = r2.selectbox("Pillar",PILLARS,key="st_n_pil")
        sp    = r1.selectbox("Sponsor",["MD","Director Retail","Director Commercial","Director Risk","Director IT","CFO","CRO"],key="st_n_sp")
        bud   = r2.number_input("Budget (KES M)",0.1,1000.0,10.0,key="st_n_bud")
        td    = r1.date_input("Target end date",today+timedelta(days=365),key="st_n_td")
        roi   = r2.number_input("Expected ROI %",0.0,200.0,30.0,key="st_n_roi")
        if st.button("💾 Create",key="st_n_save",type="primary"):
            if nm.strip():
                all_r = _load()
                all_r.append({"id":f"INIT{len(all_r)+1:04d}","name":nm,
                              "description":f"{pil} initiative","pillar":pil,
                              "sponsor":sp,"owner":uname,"owner_username":uname,
                              "start_date":str(today),"target_end_date":str(td),
                              "actual_end_date":"","completion_pct":0,
                              "status":"On Track","rag_status":"Green","budget_kes_m":bud,
                              "spent_kes_m":0,"expected_roi_pct":roi,"actual_roi_pct":0,
                              "linked_projects":0,"linked_kpis":[],"linked_bsc_kpis":[],
                              "key_milestones":0,"milestones_met":0,
                              "department":ud.get("department",""),
                              "stakeholders":1,"risks_identified":0,"risks_mitigated":0,
                              "last_updated":str(today),"next_review":str(today+timedelta(days=30)),
                              "executive_summary":"","notes":""})
                _save(all_r); audit_log("INITIATIVE_CREATED",uname,nm); _bsc_trigger(uname,"K101")
                st.success("✅ Initiative created"); st.rerun()

with tabs[3]:
    by_pillar = defaultdict(lambda:{"count":0,"avg_compl":0,"on_track":0})
    for r in records:
        p = r.get("pillar","Other")
        by_pillar[p]["count"] += 1
        by_pillar[p]["avg_compl"] += r.get("completion_pct",0)
        if r.get("status") in ("On Track","Completed"): by_pillar[p]["on_track"] += 1
    rows = [{"Pillar":p,"Count":v["count"],
              "Avg progress":f"{v['avg_compl']/max(v['count'],1):.0f}%",
              "On track":f"{v['on_track']}/{v['count']}"}
             for p,v in by_pillar.items()]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: RAG levels (Green/Amber/Red), 30-day review frequency")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("strategic_initiatives",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_a = c1.number_input("Amber threshold (%)",30,90,int(cfg_m.get("amber_threshold_completion_pct",70)),key="st_c_a")
        new_r = c2.number_input("Red threshold (%)",10,60,int(cfg_m.get("red_threshold_completion_pct",40)),key="st_c_r")
        if st.button("💾 Save",key="st_cfg_save",type="primary"):
            cfg_m.update({"amber_threshold_completion_pct":new_a,"red_threshold_completion_pct":new_r})
            mc["strategic_initiatives"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("STRATEGY_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[5]:
    bsc_rows=[
        {"KPI":"K101 — Initiatives On Track","Target":"> 80%","Actual":f"{on_track_pct}%","Status":"🟢" if on_track_pct>=80 else "🟡","Weight":"10%"},
        {"KPI":"K102 — Execution Score","Target":"> 70","Actual":f"{exec_score}","Status":"🟢" if exec_score>=70 else "🟡","Weight":"8%"},
        {"KPI":"K103 — Initiative ROI","Target":"> 100%","Actual":f"{roi_pct}%","Status":"🟢" if roi_pct>=100 else "🟡","Weight":"8%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="st_bsc",type="primary"):
        _bsc_trigger(uname,"K101"); st.success("✅ BSC updated"); st.rerun()
