"""pages/82_oprisk.py — Operational Risk Loss Database.
Basel II/III loss event capture, near-misses, lessons learned.
Dept: Risk & Compliance | KPIs: K098 K099 K100
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

require_access("risk.operational")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_risk  = any(x in role for x in ("risk","audit","compliance","manager","head","director","chief"))

CATEGORIES = ["Internal Fraud","External Fraud","Employment Practices","Clients/Products",
              "Damage to Assets","Business Disruption","Execution Failures"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"op_risk_losses.json", table="op_risk_losses")

def _save(data):
    a2z_db.dual_save(DATA/"op_risk_losses.json", data, table="op_risk_losses", flat_cols=('id', 'event_date', 'discovered_date', 'category', 'type', 'description', 'gross_loss_kes', 'recovered_kes', 'net_loss_kes', 'department', 'branch', 'status', 'regulatory_reportable'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("operational_risk",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
loss_target = conf_cfg.get("loss_event_target_count",100)
nm_target   = conf_cfg.get("near_miss_target_count",200)

losses    = [r for r in records if r.get("type")!="Near Miss"]
near_miss = [r for r in records if r.get("type")=="Near Miss"]
total_net = sum(r.get("net_loss_kes",0) for r in losses)
crit_loss = [r for r in losses if r.get("net_loss_kes",0)>=1_000_000]
open_inv  = [r for r in records if r.get("status")=="Under Review"]

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>⚠️ Operational Risk Losses</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Risk & Compliance · Basel II/III · K098-K100</span></div>",
    unsafe_allow_html=True)

if crit_loss: st.warning(f"⚠️ {len(crit_loss)} loss event(s) above KES 1M — CBK reportable")
if open_inv: st.info(f"ℹ️ {len(open_inv)} open investigations")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Loss events",     len(losses))
m2.metric("Near-misses",     len(near_miss))
m3.metric("Net losses YTD",  f"KES {total_net/1e6:.1f}M", delta_color="off")
m4.metric("Open investigations", len(open_inv))
m5.metric("CBK reportable",  len(crit_loss))

tabs = st.tabs(["📋 Loss Register","💡 Near-misses","➕ Log Event","📊 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    fcat  = f1.selectbox("Category",["All"]+CATEGORIES,key="op_fcat")
    fdept = f2.selectbox("Department",["All"]+sorted(set(r.get("department","") for r in records)),key="op_fdept")
    fstat = f3.selectbox("Status",["All","Closed","Under Review"],key="op_fstat")
    vis = [r for r in losses
           if (fcat=="All" or r.get("category","")==fcat)
           and (fdept=="All" or r.get("department","")==fdept)
           and (fstat=="All" or r.get("status","")==fstat)]
    rows = [{"ID":r["id"],"Date":r.get("event_date","")[:10],"Category":r.get("category","")[:20],
              "Type":r.get("type",""),"Net loss":f"KES {r.get('net_loss_kes',0):,.0f}",
              "Department":r.get("department",""),"Root cause":r.get("root_cause","")[:18],
              "Status":r.get("status","")}
             for r in sorted(vis,key=lambda x:x.get("event_date",""),reverse=True)]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    if near_miss:
        nm_rows=[{"ID":r["id"],"Date":r.get("event_date","")[:10],
                   "Category":r.get("category","")[:20],
                   "Description":r.get("description","")[:40],
                   "Root cause":r.get("root_cause","")[:18],
                   "RCSA updated":"✅" if r.get("rcsa_updated") else "❌"}
                  for r in near_miss]
        st.dataframe(pd.DataFrame(nm_rows),use_container_width=True,hide_index=True)
        st.caption(f"Near-miss capture rate: {len(near_miss)}/{nm_target} target ({len(near_miss)/nm_target*100:.0f}%)")

with tabs[2]:
    r1,r2 = st.columns(2)
    cat   = r1.selectbox("Category",CATEGORIES,key="op_n_cat")
    typ   = r2.selectbox("Type",["Loss Event","Near Miss","Recovered Loss","Pending Loss"],key="op_n_typ")
    desc  = st.text_area("Description *",key="op_n_desc")
    gross = r1.number_input("Gross loss (KES)",0,100_000_000,0,key="op_n_gross")
    recov = r2.number_input("Recovered (KES)",0,100_000_000,0,key="op_n_rec")
    rc    = r1.selectbox("Root cause",["Process Failure","System Error","Human Error","External Event","Third Party","Fraud"],key="op_n_rc")
    dept  = r2.text_input("Department",ud.get("department",""),key="op_n_dept")
    if st.button("💾 Log event",key="op_n_save",type="primary"):
        if desc.strip():
            all_r = _load()
            all_r.append({"id":f"OPL{len(all_r)+1:05d}","event_date":str(today),
                          "discovered_date":str(today),"category":cat,"type":typ,
                          "description":desc,"gross_loss_kes":gross,"recovered_kes":recov,
                          "net_loss_kes":gross-recov,"department":dept,"branch":"",
                          "root_cause":rc,"reported_by":uname,"status":"Under Review",
                          "investigation_complete":False,"lessons_learned":False,
                          "rcsa_updated":False,"basel_category":"Level 1",
                          "regulatory_reportable":gross>=1_000_000,
                          "control_failure":False,"notes":""})
            _save(all_r); audit_log("OPRISK_EVENT_LOGGED",uname,f"{cat}: {desc[:40]}")
            _bsc_trigger(uname,"K099" if typ!="Near Miss" else "K100")
            st.success("✅ Event logged"); st.rerun()

with tabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By category:**")
        by_cat = defaultdict(lambda:{"count":0,"loss":0})
        for r in losses:
            c = r.get("category","Other")
            by_cat[c]["count"] += 1
            by_cat[c]["loss"]  += r.get("net_loss_kes",0)
        rows = [{"Category":c[:20],"Events":v["count"],"Net loss":f"KES {v['loss']:,.0f}"}
                 for c,v in sorted(by_cat.items(),key=lambda x:-x[1]["loss"])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By department:**")
        by_dept = defaultdict(lambda:{"count":0,"loss":0})
        for r in losses:
            d = r.get("department","Other")
            by_dept[d]["count"] += 1
            by_dept[d]["loss"]  += r.get("net_loss_kes",0)
        rows = [{"Department":d,"Events":v["count"],"Net loss":f"KES {v['loss']:,.0f}"}
                 for d,v in sorted(by_dept.items(),key=lambda x:-x[1]["loss"])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Basel II/III categories, KES 1M reportable threshold, near-miss capture required")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("operational_risk",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_lt = c1.number_input("Loss event target",10,500,int(cfg_m.get("loss_event_target_count",100)),key="op_c_lt")
        new_nt = c2.number_input("Near-miss target",10,500,int(cfg_m.get("near_miss_target_count",200)),key="op_c_nt")
        if st.button("💾 Save",key="op_cfg_save",type="primary"):
            cfg_m.update({"loss_event_target_count":new_lt,"near_miss_target_count":new_nt})
            mc["operational_risk"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("OPRISK_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[5]:
    bsc_rows=[
        {"KPI":"K098 — Net Losses YTD","Target":"< KES 50M","Actual":f"KES {total_net/1e6:.1f}M","Status":"🟢" if total_net<50e6 else "🟡","Weight":"8%"},
        {"KPI":"K099 — Loss Events Reported","Target":f"{loss_target}","Actual":str(len(losses)),"Status":"🟢" if len(losses)>=loss_target*0.5 else "🟡","Weight":"5%"},
        {"KPI":"K100 — Near-misses","Target":f"{nm_target}","Actual":str(len(near_miss)),"Status":"🟢" if len(near_miss)>=nm_target*0.3 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="op_bsc",type="primary"):
        _bsc_trigger(uname,"K098"); st.success("✅ BSC updated"); st.rerun()
