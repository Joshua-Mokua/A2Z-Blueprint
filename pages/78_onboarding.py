"""pages/78_onboarding.py — Customer Onboarding Journey.
Track funnel from application start to Active Customer.
Dept: Retail Banking | KPIs: K084 K085 K086
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

require_access("customer_onboarding")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_retail= any(x in role for x in ("retail","digital","operation","onboard","customer","manager","head","director"))

STAGES = ["Application Started","ID Verified","KYC Completed","Account Approved",
          "Account Funded","First Transaction","Active Customer"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"customer_onboarding.json", table="customer_onboarding")

def _save(data):
    a2z_db.dual_save(DATA/"customer_onboarding.json", data, table="customer_onboarding", flat_cols=('id', 'customer_name', 'phone', 'channel', 'product', 'started_date', 'completed_date', 'current_stage', 'stages_completed', 'abandoned', 'rm_assigned', 'branch_assigned'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("customer_onboarding",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
tat_target = conf_cfg.get("tat_target_hours",24)
comp_target= conf_cfg.get("completion_target_pct",70)

completed = [r for r in records if r.get("current_stage")=="Active Customer"]
abandoned = [r for r in records if r.get("abandoned")]
in_progress= [r for r in records if not r.get("abandoned") and r.get("current_stage")!="Active Customer"]
completion_rate = round(len(completed)/max(len(records),1)*100,1)
tats = [r.get("tat_hours",0) for r in completed if r.get("tat_hours")]
avg_tat = round(sum(tats)/max(len(tats),1),1) if tats else 0
first_login_pct = round(sum(1 for r in completed if r.get("first_login_within_7d"))/max(len(completed),1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🎯 Customer Onboarding</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Retail Banking · K084 · K085 · K086</span></div>",
    unsafe_allow_html=True)

if completion_rate < comp_target:
    st.warning(f"⚠️ Completion rate {completion_rate}% below target {comp_target}%")
if avg_tat > tat_target:
    st.warning(f"⚠️ Average TAT {avg_tat}h above target {tat_target}h")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total journeys",  len(records))
m2.metric("Completed",       len(completed))
m3.metric("In progress",     len(in_progress))
m4.metric("Completion rate", f"{completion_rate}%", delta_color="off" if completion_rate>=comp_target else "inverse")
m5.metric("Avg TAT (hrs)",   f"{avg_tat}",          delta_color="off" if avg_tat<=tat_target else "inverse")

tabs = st.tabs(["📊 Funnel","📋 Journey Tracker","🔴 Abandoned","➕ New Journey","📈 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    funnel = []
    for stage in STAGES:
        n = sum(1 for r in records if r.get("stages_completed",0) >= STAGES.index(stage)+1)
        funnel.append({"Stage":stage,"Customers":n,"% of Started":f"{n/max(len(records),1)*100:.0f}%"})
    st.dataframe(pd.DataFrame(funnel),use_container_width=True,hide_index=True)
    st.bar_chart(pd.DataFrame({"Customers":{f["Stage"]:f["Customers"] for f in funnel}}))

with tabs[1]:
    f1,f2,f3 = st.columns(3)
    fch  = f1.selectbox("Channel",["All"]+sorted(set(r.get("channel","") for r in records)),key="ob_ch")
    fpr  = f2.selectbox("Product",["All"]+sorted(set(r.get("product","") for r in records)),key="ob_pr")
    fst  = f3.selectbox("Stage",["All"]+STAGES,key="ob_st")
    vis = [r for r in records
           if (fch=="All" or r.get("channel","")==fch)
           and (fpr=="All" or r.get("product","")==fpr)
           and (fst=="All" or r.get("current_stage","")==fst)]
    rows = [{"ID":r["id"],"Customer":r.get("customer_name","")[:18],
              "Channel":r.get("channel",""),"Product":r.get("product","")[:18],
              "Started":r.get("started_date","")[:10],"Current Stage":r.get("current_stage",""),
              "Progress":f"{r.get('stages_completed',0)}/7",
              "TAT (hrs)":r.get("tat_hours","—"),"eKYC":"✅" if r.get("ekyc_passed") else "❌",
              "Abandoned":"🔴" if r.get("abandoned") else "",
              "First login":"✅" if r.get("first_login_within_7d") else ""}
             for r in vis[:200]]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[2]:
    if abandoned:
        st.markdown(f"**{len(abandoned)} abandoned applications:**")
        ab_reasons = defaultdict(int)
        for a in abandoned: ab_reasons[a.get("abandonment_reason","Unknown")] += 1
        rows = [{"Reason":r,"Count":c,"%":f"{c/len(abandoned)*100:.0f}%"}
                 for r,c in sorted(ab_reasons.items(),key=lambda x:-x[1])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        if is_retail or is_admin:
            if st.button("📧 Trigger re-engagement campaign",key="ob_reeng",type="primary"):
                audit_log("ONBOARDING_REENG",uname,f"{len(abandoned)} abandoned customers")
                _bsc_trigger(uname,"K085")
                st.success(f"✅ Re-engagement triggered for {len(abandoned)} customers")

with tabs[3]:
    if is_retail or is_admin:
        r1,r2 = st.columns(2)
        cname  = r1.text_input("Customer name *",key="ob_new_name")
        phone  = r2.text_input("Phone number *",key="ob_new_phone")
        ch     = r1.selectbox("Channel",["Mobile App","Web Portal","Branch","Agent","Call Centre","WhatsApp"],key="ob_new_ch")
        prod   = r2.selectbox("Product",["Personal Current","Personal Savings","SME Current","Salary Account",
                                          "Premium Account","Corporate Current","Diaspora Account","Youth Account"],key="ob_new_pr")
        if st.button("💾 Start journey",key="ob_new_save",type="primary"):
            if cname.strip() and phone.strip():
                all_r = _load()
                all_r.append({
                    "id":f"ONB{len(all_r)+1:05d}","customer_name":cname.strip(),"phone":phone.strip(),
                    "channel":ch,"product":prod,"started_date":str(today),"completed_date":"",
                    "current_stage":"Application Started","stages_completed":1,"total_stages":7,
                    "completion_pct":14.3,"tat_hours":None,"ekyc_passed":False,
                    "documents_uploaded":0,"abandoned":False,"abandonment_reason":"",
                    "first_login_within_7d":False,"first_transaction_30d":False,
                    "agent_assisted":False,"branch_assigned":"","rm_assigned":uname,
                    "device_type":"","referral_source":"","notes":""
                })
                _save(all_r); audit_log("ONBOARDING_STARTED",uname,cname); _bsc_trigger(uname,"K085")
                st.success("✅ Journey started"); st.rerun()

with tabs[4]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By channel:**")
        by_ch = defaultdict(lambda:{"total":0,"complete":0})
        for r in records:
            c = r.get("channel","Other")
            by_ch[c]["total"] += 1
            if r.get("current_stage")=="Active Customer": by_ch[c]["complete"] += 1
        rows = [{"Channel":c,"Total":v["total"],"Completed":v["complete"],
                  "Rate":f"{v['complete']/max(v['total'],1)*100:.0f}%"}
                for c,v in sorted(by_ch.items())]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By product:**")
        by_pr = defaultdict(lambda:{"total":0,"complete":0})
        for r in records:
            p = r.get("product","Other")
            by_pr[p]["total"] += 1
            if r.get("current_stage")=="Active Customer": by_pr[p]["complete"] += 1
        rows = [{"Product":p[:25],"Total":v["total"],"Completed":v["complete"],
                  "Rate":f"{v['complete']/max(v['total'],1)*100:.0f}%"}
                for p,v in sorted(by_pr.items(),key=lambda x:-x[1]["total"])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: 7-stage journey, eKYC required, AML/CFT screening, supported channels")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("customer_onboarding",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_tat = c1.number_input("TAT target (hours)",1,168,int(cfg_m.get("tat_target_hours",24)),key="ob_cfg_tat")
        new_comp= c2.number_input("Completion target (%)",10,100,int(cfg_m.get("completion_target_pct",70)),key="ob_cfg_comp")
        if st.button("💾 Save",key="ob_cfg_save",type="primary"):
            cfg_m.update({"tat_target_hours":new_tat,"completion_target_pct":new_comp})
            mc["customer_onboarding"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("ONBOARDING_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Admin only.")

with tabs[6]:
    bsc_rows=[
        {"KPI":"K084 — Account Opening TAT","Target":f"< {tat_target}h","Actual":f"{avg_tat}h","Status":"🟢" if avg_tat<=tat_target else "🟡","Weight":"8%"},
        {"KPI":"K085 — Onboarding Completion","Target":f"> {comp_target}%","Actual":f"{completion_rate}%","Status":"🟢" if completion_rate>=comp_target else "🟡","Weight":"10%"},
        {"KPI":"K086 — First Login Within 7d","Target":"> 80%","Actual":f"{first_login_pct}%","Status":"🟢" if first_login_pct>=80 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="ob_bsc",type="primary"):
        _bsc_trigger(uname,"K084"); st.success("✅ BSC updated"); st.rerun()
