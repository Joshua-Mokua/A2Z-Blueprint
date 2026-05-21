"""pages/85_esg.py — ESG & Climate Risk.
Green lending, sustainability, climate risk assessments.
Dept: Risk & Compliance | KPIs: K106 K107 K108
CBK Climate Risk Guidance 2023.
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

require_access("risk.esg")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_esg   = any(x in role for x in ("sustainability","esg","risk","climate","manager","head","director"))

GREEN_SECTORS = ["Renewable Energy","Sustainable Agriculture","Green Buildings","Clean Transport",
                 "Water Management","Waste Recycling","Energy Efficiency","Climate-Smart Manufacturing"]
ESG_PILLARS = ["Environmental","Social","Governance"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load_dict(DATA/"esg_climate.json", table_map={'green_loans': 'esg_green_loans', 'esg_initiatives': 'esg_initiatives', 'climate_risk_assessments': 'esg_climate_assessments', 'esg_score': 'esg_score_snapshot'})

def _save(data):
    """Save nested-dict module data — JSON only (PG nested writes are explicit per sub-table)."""
    (DATA/"esg_climate.json").write_text(json.dumps(data,indent=2,default=str))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("esg_climate",{}) if mc.exists() else {}


data = _load()
green_loans = data.get("green_loans",[])
esg_inits   = data.get("esg_initiatives",[])
clim_assess = data.get("climate_risk_assessments",[])
esg_score   = data.get("esg_score",{}).get("overall",0)
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
green_target = conf_cfg.get("green_loan_target_pct",15)
esg_target   = conf_cfg.get("esg_score_target",75)

green_total = sum(g.get("amount_kes_m",0) for g in green_loans)
clim_done   = [c for c in clim_assess if c.get("completed")]
clim_pct    = round(len(clim_done)/max(len(clim_assess),1)*100,1)
total_carbon= sum(g.get("carbon_offset_tons_yr",0) for g in green_loans)
total_jobs  = sum(g.get("jobs_created",0) for g in green_loans)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🌱 ESG & Climate Risk</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "CBK Climate Risk Guidance 2023 · K106-K108</span></div>",
    unsafe_allow_html=True)

if esg_score < esg_target:
    st.warning(f"⚠️ ESG score {esg_score} below target {esg_target}")
if clim_pct < 80:
    st.warning(f"⚠️ Climate assessments only {clim_pct}% complete")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Green portfolio", f"KES {green_total:.0f}M")
m2.metric("ESG initiatives", len(esg_inits))
m3.metric("Climate done",    f"{clim_pct}%")
m4.metric("ESG score",       f"{esg_score}/100")
m5.metric("Carbon offset",   f"{total_carbon:,} t/yr")

tabs = st.tabs(["💚 Green Loans","🌍 ESG Initiatives","🌡️ Climate Risk","📊 ESG Score","➕ New","⚙️ Config","📈 BSC"])

with tabs[0]:
    rows = [{"ID":g["id"],"Customer":g.get("customer","")[:18],
              "Sector":g.get("sector","")[:20],"Amount(M)":g.get("amount_kes_m",0),
              "Carbon offset":f"{g.get('carbon_offset_tons_yr',0):,}",
              "Jobs":g.get("jobs_created",0),"ESG score":g.get("esg_score",0),
              "Status":g.get("status",""),"Verified":"✅" if g.get("verified") else ""}
             for g in green_loans]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    by_sec = defaultdict(float)
    for g in green_loans: by_sec[g.get("sector","")] += g.get("amount_kes_m",0)
    st.bar_chart(pd.DataFrame({"KES M":by_sec}))

with tabs[1]:
    rows = [{"Name":i.get("name",""),"Category":i.get("category",""),
              "Budget(M)":i.get("budget_kes_m",0),"Spent(M)":i.get("spent_kes_m",0),
              "Beneficiaries":f"{i.get('beneficiaries',0):,}",
              "Progress":f"{i.get('completion_pct',0)}%",
              "Impact":f"{i.get('impact_value',0):,} {i.get('impact_metric','')}"}
             for i in esg_inits]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[2]:
    rows = [{"Risk type":c.get("risk_type","")[:25],
              "Segment":c.get("portfolio_segment",""),
              "Exposure(B)":c.get("exposure_kes_b",0),
              "Risk score":c.get("risk_score",0),
              "Done":"✅" if c.get("completed") else "⏳",
              "Stress test":"✅" if c.get("stress_test_done") else "❌",
              "CBK reportable":"📌" if c.get("cbk_reportable") else ""} for c in clim_assess]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[3]:
    sc = data.get("esg_score",{})
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Overall",        f"{sc.get('overall',0):.1f}", delta=f"{sc.get('overall',0)-sc.get('previous',0):+.1f}")
    c2.metric("Environmental",  f"{sc.get('environmental',0):.1f}")
    c3.metric("Social",         f"{sc.get('social',0):.1f}")
    c4.metric("Governance",     f"{sc.get('governance',0):.1f}")
    st.caption(f"Trend: {sc.get('trend','')} | Rated by: {sc.get('rated_by','')} | As of: {sc.get('as_of','')}")

with tabs[4]:
    if is_esg or is_admin:
        kind = st.radio("Type",["Green Loan","ESG Initiative"],horizontal=True,key="esg_n_kind")
        if kind=="Green Loan":
            r1,r2 = st.columns(2)
            cust = r1.text_input("Customer *",key="esg_n_cust")
            sec  = r2.selectbox("Sector",GREEN_SECTORS,key="esg_n_sec")
            amt  = r1.number_input("Amount (KES M)",0.1,1000.0,5.0,0.1,key="esg_n_amt")
            carbon=r2.number_input("Carbon offset (t/yr)",0,100000,500,key="esg_n_carbon")
            if st.button("💾 Create",key="esg_n_save",type="primary"):
                if cust.strip():
                    all_d = _load()
                    all_d.setdefault("green_loans",[]).append({
                        "id":f"GL{len(green_loans)+1:04d}","customer":cust,"sector":sec,
                        "amount_kes_m":amt,"tenor_years":5,"interest_rate":12,
                        "carbon_offset_tons_yr":carbon,"energy_saved_mwh":0,
                        "jobs_created":0,"disbursed_date":str(today),"status":"Disbursed",
                        "monitored":False,"verified":False,"esg_score":75
                    })
                    _save(all_d); audit_log("GREEN_LOAN_CREATED",uname,cust); _bsc_trigger(uname,"K106")
                    st.success("✅ Green loan created"); st.rerun()
        else:
            r1,r2 = st.columns(2)
            nm  = r1.text_input("Initiative name *",key="esg_n_inm")
            cat = r2.selectbox("Category",ESG_PILLARS,key="esg_n_cat")
            bud = r1.number_input("Budget (KES M)",0.1,100.0,1.0,key="esg_n_bud")
            if st.button("💾 Create initiative",key="esg_n_save2",type="primary"):
                if nm.strip():
                    all_d = _load()
                    all_d.setdefault("esg_initiatives",[]).append({
                        "id":f"ESG{len(esg_inits)+1:04d}","name":nm,"category":cat,
                        "budget_kes_m":bud,"spent_kes_m":0,"beneficiaries":0,
                        "started_date":str(today),"completion_pct":0,"owner":uname,
                        "department":ud.get("department",""),"impact_metric":"",
                        "impact_value":0,"reported_publicly":False
                    })
                    _save(all_d); audit_log("ESG_INITIATIVE_CREATED",uname,nm); _bsc_trigger(uname,"K108")
                    st.success("✅ Initiative created"); st.rerun()

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: CBK Climate Risk Guidance 2023, ESG pillars (E/S/G), climate risk types")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("esg_climate",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_g = c1.number_input("Green target (%)",1,30,int(cfg_m.get("green_loan_target_pct",15)),key="esg_c_g")
        new_s = c2.number_input("ESG score target",50,100,int(cfg_m.get("esg_score_target",75)),key="esg_c_s")
        if st.button("💾 Save",key="esg_cfg_save",type="primary"):
            cfg_m.update({"green_loan_target_pct":new_g,"esg_score_target":new_s})
            mc["esg_climate"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("ESG_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[6]:
    bsc_rows=[
        {"KPI":"K106 — Green Portfolio","Target":"KES 5,000M","Actual":f"KES {green_total:.0f}M","Status":"🟢" if green_total>=5000 else "🟡","Weight":"8%"},
        {"KPI":"K107 — Climate Assessments","Target":"> 80%","Actual":f"{clim_pct}%","Status":"🟢" if clim_pct>=80 else "🟡","Weight":"5%"},
        {"KPI":"K108 — ESG Score","Target":f"> {esg_target}","Actual":f"{esg_score}","Status":"🟢" if esg_score>=esg_target else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="esg_bsc",type="primary"):
        _bsc_trigger(uname,"K106"); st.success("✅ BSC updated"); st.rerun()
