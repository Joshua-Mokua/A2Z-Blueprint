"""pages/75_data_protection.py — Data Protection Office.
DPA Kenya 2019 — DPIA register, breach register, ROPA.
Dept: Compliance | KPIs: K075 K076 K077
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

require_access("data_protection")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_dpo   = any(x in role for x in ("dpo","compliance","legal","data protection","manager","head","director"))

DPA_PRINCIPLES = ["Lawfulness","Purpose Limitation","Data Minimisation","Accuracy","Storage Limitation","Integrity","Confidentiality"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"dpo_register.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return json.loads(mc.read_text(encoding="utf-8")).get("data_protection",{}) if mc.exists() else {}

def _save(data):
    (DATA/"dpo_register.json").write_text(json.dumps(data,indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
dpia_target = conf_cfg.get("dpia_target_days",30)

dpias    = [r for r in records if r.get("type")=="DPIA"]
breaches = [r for r in records if r.get("type")=="Breach"]
ropa     = [r for r in records if r.get("type")=="ROPA"]
dpia_done= [r for r in dpias if r.get("status")=="Approved"]
dpia_ot  = [r for r in dpia_done if r.get("on_time")]
dpia_pct = round(len(dpia_ot)/max(len(dpia_done),1)*100,1)
breach_72= [b for b in breaches if b.get("reported_within_72h")]
breach_72pct = round(len(breach_72)/max(len(breaches),1)*100,1)
ropa_current = [r for r in ropa if r.get("last_reviewed","")>=str(today-timedelta(days=365))]
ropa_pct = round(len(ropa_current)/max(len(ropa),1)*100,1)
critical_breaches = [b for b in breaches if b.get("risk_level")=="Critical"]
total_fines = sum(b.get("fines_paid_kes",0) for b in breaches)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔒 Data Protection Office</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "DPA Kenya 2019 · ODPC · K075 · K076 · K077</span></div>",
    unsafe_allow_html=True)

if critical_breaches:
    st.error(f"🔴 {len(critical_breaches)} CRITICAL data breach(es) — escalate to ODPC immediately")
if total_fines > 0:
    st.warning(f"⚠️ Total ODPC fines paid YTD: KES {total_fines:,}")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("DPIAs",       len(dpias))
m2.metric("Breaches",    len(breaches), delta_color="inverse" if breaches else "off")
m3.metric("ROPA records",len(ropa))
m4.metric("72h reporting", f"{breach_72pct}%", delta_color="off" if breach_72pct>=95 else "inverse")
m5.metric("DPIA on-time",  f"{dpia_pct}%",     delta_color="off" if dpia_pct>=80 else "inverse")

tabs = st.tabs(["📋 DPIA Register","🚨 Breach Register","📚 ROPA","➕ New Record","⚖️ Compliance","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2 = st.columns(2)
    fstat = f1.selectbox("Status",["All","Approved","In Progress","Under Review","Pending"],key="dpo_dstat")
    frisk = f2.selectbox("Risk level",["All","Low","Medium","High"],key="dpo_drisk")
    vis = [r for r in dpias
           if (fstat=="All" or r.get("status","")==fstat)
           and (frisk=="All" or r.get("risk_level","")==frisk)]
    rows = [{"ID":r["id"],"Subject":r.get("subject","")[:30],"Risk":r.get("risk_level",""),
              "Status":r.get("status",""),"Started":r.get("started_date","")[:10],
              "Due":r.get("due_date","")[:10] if r.get("due_date") else "Done",
              "Actions":f"{r.get('actions_closed',0)}/{r.get('mitigation_actions',0)}",
              "ICO":"⚠️" if r.get("ico_consultation_required") else ""}
             for r in vis]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    if breaches:
        for b in breaches[:30]:
            risk_icon = {"Critical":"🔴","High":"🟠","Medium":"🟡","Low":"🟢"}.get(b.get("risk_level","Low"),"")
            with st.expander(f"{risk_icon} {b.get('subject','')} — {b.get('started_date','')[:10]}"):
                c1,c2,c3 = st.columns(3)
                c1.metric("Affected records",f"{b.get('affected_records',0):,}")
                c2.metric("72h reporting", "✅ Yes" if b.get("reported_within_72h") else "❌ No",
                          delta_color="off" if b.get("reported_within_72h") else "inverse")
                c3.metric("Fines paid",    f"KES {b.get('fines_paid_kes',0):,.0f}")
                st.markdown(f"**Root cause:** {b.get('root_cause','—')} | **Status:** {b.get('status','—')}")
                st.markdown(f"**Remediation actions:** {b.get('remediation_taken',0)}")
    else:
        st.success("✅ No data breaches reported.")

with tabs[2]:
    rows = [{"Activity":r.get("subject","")[:30],"Categories":", ".join(r.get("data_categories",[]))[:30],
              "Legal basis":r.get("legal_basis",""),"Retention (yrs)":r.get("retention_period_years",""),
              "Subjects":r.get("data_subjects",""),"Cross-border":"✅" if r.get("cross_border") else "",
              "Last reviewed":r.get("last_reviewed","")[:10],"Next review":r.get("next_review","")[:10],
              "Department":r.get("department","")} for r in ropa]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(f"ROPA up-to-date: {ropa_pct}% (target: 100%)")

with tabs[3]:
    if is_dpo or is_admin:
        rec_type = st.radio("Record type",["DPIA","Breach","ROPA"],horizontal=True,key="dpo_new_type")
        if rec_type=="DPIA":
            r1,r2 = st.columns(2)
            sub  = r1.text_input("Subject (project/process) *",key="dpo_dpia_sub")
            risk = r2.selectbox("Risk level",["Low","Medium","High"],key="dpo_dpia_risk")
            cats = st.multiselect("Data categories",["Personal","Financial","Sensitive","Biometric","Location"],key="dpo_dpia_cats")
            due  = r1.date_input("Target completion date", today+timedelta(days=dpia_target), key="dpo_dpia_due")
            ico  = r2.checkbox("ICO consultation required", key="dpo_dpia_ico")
            if st.button("💾 Save DPIA",key="dpo_dpia_save",type="primary"):
                if sub.strip():
                    all_r = _load()
                    all_r.append({"id":f"DPIA{len(dpias)+1:04d}","type":"DPIA","subject":sub.strip(),
                                  "risk_level":risk,"data_categories":cats,"status":"Pending",
                                  "started_date":str(today),"due_date":str(due),"completed_date":"",
                                  "on_time":False,"dpo_reviewer":uname,
                                  "department":ud.get("department",""),"mitigation_actions":0,
                                  "actions_closed":0,"ico_consultation_required":ico})
                    _save(all_r); audit_log("DPIA_CREATED",uname,sub); _bsc_trigger(uname,"K075")
                    st.success("✅ DPIA created"); st.rerun()
        elif rec_type=="Breach":
            r1,r2 = st.columns(2)
            sub  = r1.text_input("Breach description *",key="dpo_br_sub")
            risk = r2.selectbox("Risk level",["Low","Medium","High","Critical"],key="dpo_br_risk")
            affected = r1.number_input("Affected records",1,1_000_000,key="dpo_br_aff")
            cause = r2.selectbox("Root cause",["Human Error","System Vulnerability","Phishing","Unauthorised Access","Third Party"],key="dpo_br_rc")
            reported = st.checkbox("Reported to ODPC within 72 hours",True,key="dpo_br_72h")
            if st.button("💾 Log breach",key="dpo_br_save",type="primary"):
                if sub.strip():
                    all_r = _load()
                    all_r.append({"id":f"BREACH{len(breaches)+1:04d}","type":"Breach","subject":sub.strip(),
                                  "risk_level":risk,"started_date":str(today),"completed_date":"",
                                  "reported_to_odpc":reported,"reported_within_72h":reported,
                                  "affected_records":affected,"root_cause":cause,"status":"Investigating",
                                  "remediation_taken":0,"fines_paid_kes":0,"data_categories":[],
                                  "department":ud.get("department",""),"dpo_reviewer":uname})
                    _save(all_r); audit_log("BREACH_LOGGED",uname,sub); _bsc_trigger(uname,"K076")
                    st.success("✅ Breach logged — start ODPC notification immediately if not done")
                    st.rerun()

with tabs[4]:
    st.markdown("**DPA Kenya 2019 Principles:**")
    for p in DPA_PRINCIPLES: st.markdown(f"  ✅ {p}")
    st.info("Data Protection Act 2019 (Kenya) | Regulator: ODPC | Max penalty: KES 5M or 1% turnover")
    st.markdown(f"**Compliance Score:**")
    score = round((dpia_pct + breach_72pct + ropa_pct)/3, 1)
    st.metric("Overall DPA Compliance", f"{score}/100",
              delta_color="off" if score>=90 else "inverse")

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: DPA Kenya 2019, ODPC, 72h breach window, KES 5M max penalty, principles")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("data_protection",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_dpia = c1.number_input("DPIA target days",7,90,int(cfg_m.get("dpia_target_days",30)),key="dpo_cfg_dpia")
        new_ropa = c2.number_input("ROPA review months",6,24,int(cfg_m.get("ropa_review_frequency_months",12)),key="dpo_cfg_ropa")
        if st.button("💾 Save",key="dpo_cfg_save",type="primary"):
            cfg_m.update({"dpia_target_days":new_dpia,"ropa_review_frequency_months":new_ropa})
            mc["data_protection"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("DPO_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Admin only.")

with tabs[6]:
    bsc_rows=[
        {"KPI":"K075 — DPIAs on time","Target":"> 80%","Actual":f"{dpia_pct}%","Status":"🟢" if dpia_pct>=80 else "🟡","Weight":"8%"},
        {"KPI":"K076 — 72h breach reporting","Target":"100%","Actual":f"{breach_72pct}%","Status":"🟢" if breach_72pct>=95 else "🔴","Weight":"10%"},
        {"KPI":"K077 — ROPA up-to-date","Target":"100%","Actual":f"{ropa_pct}%","Status":"🟢" if ropa_pct>=90 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="dpo_bsc",type="primary"):
        _bsc_trigger(uname,"K075"); st.success("✅ BSC updated"); st.rerun()
