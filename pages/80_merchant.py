"""pages/80_merchant.py — Merchant Acquiring.
POS terminals, merchant onboarding, MDR revenue.
Dept: Commercial & Corporate | KPIs: K091 K092 K093
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

require_access("merchant_acquiring")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_comm  = any(x in role for x in ("commercial","retail","merchant","digital","manager","head","director","relationship"))

MERCHANT_TYPES = ["Supermarket","Restaurant","Petrol Station","Pharmacy","Hardware","Hotel",
                  "Boutique","Electronics","Hospital","School","Salon","Online Store"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"merchant_acquiring.json", table="merchant_acquiring")

def _save(data):
    a2z_db.dual_save(DATA/"merchant_acquiring.json", data, table="merchant_acquiring", flat_cols=('id', 'merchant_name', 'merchant_type', 'kra_pin', 'onboarding_date', 'status', 'active', 'pos_terminals', 'active_terminals', 'ytd_revenue_kes', 'branch', 'rm_code', 'category'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("merchant_acquiring",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
tat_target = conf_cfg.get("tat_target_days",7)

active = [m for m in records if m.get("active")]
total_pos    = sum(m.get("active_terminals",0) for m in records)
total_rev_m  = sum(m.get("ytd_revenue_kes",0) for m in records)/1e6
total_vol_m  = sum(m.get("ytd_value_m",0) for m in records)
avg_tat = round(sum(m.get("tat_days",0) for m in records)/max(len(records),1),1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏪 Merchant Acquiring</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Commercial & Corporate · K091-K093</span></div>",
    unsafe_allow_html=True)

if avg_tat > tat_target: st.warning(f"⚠️ Avg onboarding TAT {avg_tat}d above target {tat_target}d")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total merchants", len(records))
m2.metric("Active",          len(active))
m3.metric("Active POS",      f"{total_pos:,}")
m4.metric("Volume YTD",      f"KES {total_vol_m:.0f}M")
m5.metric("Revenue YTD",     f"KES {total_rev_m:.1f}M")

tabs = st.tabs(["🏪 Merchant Register","📊 POS Performance","➕ Onboard","📈 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2 = st.columns(2)
    fcat = f1.selectbox("Category",["All","MSME","Mid-Market","Corporate","Premier"],key="mer_c")
    fst  = f2.selectbox("Status",["All","Application","KYC","Approved","Active","Suspended","Terminated"],key="mer_s")
    vis = [m for m in records if (fcat=="All" or m.get("category","")==fcat) and (fst=="All" or m.get("status","")==fst)]
    rows = [{"Merchant":m.get("merchant_name","")[:25],"Type":m.get("merchant_type",""),
              "Status":m.get("status",""),"POS":m.get("active_terminals",0),
              "Volume YTD":f"KES {m.get('ytd_value_m',0):.1f}M",
              "Revenue YTD":f"KES {m.get('ytd_revenue_kes',0):,.0f}",
              "MDR":f"{m.get('mdr_pct',0):.2f}%","TAT":m.get("tat_days",0)} for m in vis]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    by_type = defaultdict(lambda:{"count":0,"pos":0,"vol":0,"rev":0})
    for m in records:
        t = m.get("merchant_type","Other")
        by_type[t]["count"] += 1
        by_type[t]["pos"]   += m.get("active_terminals",0)
        by_type[t]["vol"]   += m.get("ytd_value_m",0)
        by_type[t]["rev"]   += m.get("ytd_revenue_kes",0)
    rows=[{"Type":t,"Merchants":v["count"],"POS":v["pos"],
            "Volume(M)":round(v["vol"],1),"Revenue":f"KES {v['rev']:,.0f}"}
           for t,v in sorted(by_type.items(),key=lambda x:-x[1]["rev"])]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[2]:
    if is_comm or is_admin:
        r1,r2 = st.columns(2)
        mn  = r1.text_input("Merchant name *",key="mer_n_mn")
        mt  = r2.selectbox("Merchant type",MERCHANT_TYPES,key="mer_n_mt")
        kra = r1.text_input("KRA PIN *",key="mer_n_kra")
        npos= r2.number_input("POS terminals",1,50,1,key="mer_n_pos")
        mdr = r1.number_input("MDR %",0.5,3.0,1.5,0.1,key="mer_n_mdr")
        cat = r2.selectbox("Category",["MSME","Mid-Market","Corporate","Premier"],key="mer_n_cat")
        if st.button("💾 Onboard merchant",key="mer_n_save",type="primary"):
            if mn.strip() and kra.strip():
                all_r = _load()
                all_r.append({"id":f"MER{len(all_r)+1:05d}","merchant_name":mn,"merchant_type":mt,
                              "trading_name":mn,"kra_pin":kra,"onboarding_date":str(today),
                              "tat_days":0,"status":"Application","active":False,
                              "pos_terminals":npos,"active_terminals":0,"monthly_volume":0,
                              "monthly_value_m":0,"ytd_value_m":0,"ytd_revenue_kes":0,
                              "mdr_pct":mdr,"settlement_account":"","settlement_t_plus":1,
                              "branch":"","rm_code":uname,"complaints_30d":0,"chargebacks_30d":0,
                              "fraud_flagged":False,"category":cat,
                              "contract_renewal":str(today+timedelta(days=365)),"notes":""})
                _save(all_r); audit_log("MERCHANT_ONBOARDED",uname,mn); _bsc_trigger(uname,"K091")
                st.success("✅ Merchant onboarded"); st.rerun()

with tabs[3]:
    by_cat = defaultdict(lambda:{"count":0,"rev":0,"vol":0})
    for m in records:
        c = m.get("category","Other")
        by_cat[c]["count"] += 1
        by_cat[c]["rev"]   += m.get("ytd_revenue_kes",0)
        by_cat[c]["vol"]   += m.get("ytd_value_m",0)
    st.dataframe(pd.DataFrame([{"Category":c,"Merchants":v["count"],"Revenue":f"KES {v['rev']:,.0f}",
                                  "Volume(M)":round(v["vol"],1)} for c,v in by_cat.items()]),
                 use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Visa/MasterCard, KES settlement, KYC required")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("merchant_acquiring",{}).get("configurable",{})
        new_tat = st.number_input("TAT target (days)",1,30,int(cfg_m.get("tat_target_days",7)),key="mer_cfg_tat")
        if st.button("💾 Save",key="mer_cfg_save",type="primary"):
            cfg_m["tat_target_days"]=new_tat
            mc["merchant_acquiring"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("MERCHANT_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[5]:
    bsc_rows=[
        {"KPI":"K091 — Active POS Merchants","Target":"100","Actual":str(len(active)),"Status":"🟢" if len(active)>=100 else "🟡","Weight":"8%"},
        {"KPI":"K092 — Acquiring Revenue","Target":"KES 50M","Actual":f"KES {total_rev_m:.1f}M","Status":"🟢" if total_rev_m>=50 else "🟡","Weight":"10%"},
        {"KPI":"K093 — Onboarding TAT","Target":f"< {tat_target}d","Actual":f"{avg_tat}d","Status":"🟢" if avg_tat<=tat_target else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="mer_bsc",type="primary"):
        _bsc_trigger(uname,"K091"); st.success("✅ BSC updated"); st.rerun()
