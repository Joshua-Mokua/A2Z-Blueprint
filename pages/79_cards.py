"""pages/79_cards.py — Card Lifecycle Management.
Issuance, activation, disputes, fraud, chargebacks.
Dept: Retail Banking | KPIs: K087 K088 K089 K090
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

require_access("products_pricing.cards")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_card  = any(x in role for x in ("retail","card","operation","manager","head","director"))

CARD_TYPES = ["Debit Visa","Debit MasterCard","Credit Visa Gold","Credit MC Platinum",
              "Prepaid Visa","Business Credit","Diaspora Card","Youth Card","Premium Black"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"card_management.json", table="card_management")

def _save(data):
    a2z_db.dual_save(DATA/"card_management.json", data, table="card_management", flat_cols=('id', 'card_number_masked', 'customer_cif', 'customer_name', 'card_type', 'issue_date', 'expiry_date', 'status', 'ytd_spend_kes', 'has_dispute', 'fraud_flagged', 'branch', 'rm_code'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("card_management",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
dispute_target = conf_cfg.get("dispute_resolution_target_pct",95)
fraud_threshold= conf_cfg.get("fraud_loss_threshold_pct",0.05)

active     = [c for c in records if c.get("status")=="Active"]
activated  = [c for c in records if c.get("activation_date","") and c.get("activation_date","")>=str(today-timedelta(days=30))]
disputes   = [c for c in records if c.get("has_dispute")]
disp_open  = [c for c in disputes if not c.get("dispute_resolved")]
disp_sla   = [c for c in disputes if c.get("dispute_resolved") and c.get("dispute_actual_days",999)<=c.get("dispute_sla_days",7)]
fraud_cards= [c for c in records if c.get("fraud_flagged")]
total_spend= sum(c.get("ytd_spend_kes",0) for c in records)/1e6
total_fraud= sum(c.get("fraud_loss_kes",0) for c in records)
fraud_pct  = round(total_fraud/max(total_spend*1e6,1)*100,3)
dispute_sla_pct = round(len(disp_sla)/max(len(disputes),1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💳 Card Lifecycle Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Retail Banking · K087-K090</span></div>",
    unsafe_allow_html=True)

if disp_open: st.warning(f"⚠️ {len(disp_open)} open card disputes")
if fraud_pct > fraud_threshold: st.error(f"🔴 Card fraud loss {fraud_pct}% above threshold {fraud_threshold}%")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total cards",     len(records))
m2.metric("Active cards",    len(active))
m3.metric("YTD spend",       f"KES {total_spend:.1f}M")
m4.metric("Open disputes",   len(disp_open), delta_color="inverse" if disp_open else "off")
m5.metric("Dispute SLA",     f"{dispute_sla_pct}%", delta_color="off" if dispute_sla_pct>=dispute_target else "inverse")

tabs = st.tabs(["💳 Card Register","🔍 Card Detail","⚖️ Disputes","🚨 Fraud","➕ Issue Card","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2 = st.columns(2)
    ftype = f1.selectbox("Type",["All"]+CARD_TYPES,key="cd_t")
    fstat = f2.selectbox("Status",["All","Issued","Activated","Active","Blocked","Expired","Lost","Stolen","Closed"],key="cd_s")
    vis = [c for c in records if (ftype=="All" or c.get("card_type","")==ftype) and (fstat=="All" or c.get("status","")==fstat)]
    rows = [{"Card":c.get("card_number_masked",""),"Customer":c.get("customer_name","")[:18],
              "Type":c.get("card_type","")[:18],"Status":c.get("status",""),
              "YTD Spend":f"KES {c.get('ytd_spend_kes',0):,.0f}",
              "Disputes":"⚖️" if c.get("has_dispute") else "",
              "Fraud":"🚨" if c.get("fraud_flagged") else ""} for c in vis[:200]]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    if records:
        sel = st.selectbox("Select card",[c.get("card_number_masked","") for c in records[:100]],key="cd_sel")
        c = next((x for x in records if x.get("card_number_masked","")==sel),{})
        if c:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Status",c.get("status",""))
            c2.metric("YTD Spend",f"KES {c.get('ytd_spend_kes',0):,.0f}")
            c3.metric("YTD Txns",c.get("ytd_transactions",0))
            c4.metric("Outstanding",f"KES {c.get('outstanding_kes',0):,.0f}")

with tabs[2]:
    if disp_open:
        for c in disp_open:
            with st.expander(f"⚖️ {c.get('card_number_masked','')} — {c.get('dispute_type','')} — KES {c.get('dispute_amount_kes',0):,.0f}"):
                if is_card and st.button("✅ Resolve",key=f"cd_res_{c['id']}",type="primary"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"]==c["id"]:
                            rec["dispute_resolved"]=True
                            rec["dispute_actual_days"]=(today-date.fromisoformat(rec.get("dispute_filed_date",str(today))[:10])).days
                            break
                    _save(all_r); audit_log("CARD_DISPUTE_RESOLVED",uname,c["id"])
                    _bsc_trigger(uname,"K089")
                    st.success("✅ Dispute resolved"); st.rerun()
    else: st.success("✅ No open disputes.")

with tabs[3]:
    if fraud_cards:
        rows=[{"Card":c.get("card_number_masked",""),"Customer":c.get("customer_name","")[:20],
                "Loss":f"KES {c.get('fraud_loss_kes',0):,.0f}","Type":c.get("dispute_type","")} for c in fraud_cards]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.metric("Total fraud loss",f"KES {total_fraud:,.0f}")
    else: st.success("✅ No fraud cases.")

with tabs[4]:
    if is_card or is_admin:
        r1,r2 = st.columns(2)
        cif  = r1.text_input("Customer CIF *",key="cd_n_cif")
        cn   = r2.text_input("Customer name *",key="cd_n_cn")
        ct   = r1.selectbox("Card type",CARD_TYPES,key="cd_n_ct")
        if st.button("💾 Issue card",key="cd_n_save",type="primary"):
            if cif.strip() and cn.strip():
                all_r = _load()
                import random as _r
                all_r.append({"id":f"CARD{len(all_r)+1:05d}",
                              "card_number_masked":f"****{_r.randint(1000,9999)}",
                              "customer_cif":cif,"customer_name":cn,"card_type":ct,
                              "issue_date":str(today),"activation_date":"",
                              "expiry_date":str(today+timedelta(days=365*4)),
                              "status":"Issued","ytd_spend_kes":0,"ytd_transactions":0,
                              "credit_limit_kes":0,"outstanding_kes":0,
                              "has_dispute":False,"dispute_type":"","dispute_amount_kes":0,
                              "dispute_filed_date":"","dispute_resolved":False,
                              "dispute_sla_days":7,"dispute_actual_days":0,
                              "fraud_flagged":False,"fraud_loss_kes":0,
                              "branch":"","rm_code":uname,"channel_used":"",
                              "monthly_fee_kes":150,"notes":""})
                _save(all_r); audit_log("CARD_ISSUED",uname,f"{cn}: {ct}"); _bsc_trigger(uname,"K087")
                st.success("✅ Card issued"); st.rerun()

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Visa/MasterCard, dispute SLA 7 days, fraud reporting 24h, PCI DSS")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("card_management",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_dt = c1.number_input("Dispute target (%)",50,100,int(cfg_m.get("dispute_resolution_target_pct",95)),key="cd_cfg_dt")
        new_ft = c2.number_input("Fraud threshold (%)",0.01,1.0,float(cfg_m.get("fraud_loss_threshold_pct",0.05)),0.01,key="cd_cfg_ft")
        if st.button("💾 Save",key="cd_cfg_save",type="primary"):
            cfg_m.update({"dispute_resolution_target_pct":new_dt,"fraud_loss_threshold_pct":new_ft})
            mc["card_management"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CARD_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[6]:
    bsc_rows=[
        {"KPI":"K087 — Cards Activated","Target":"100","Actual":str(len(activated)),"Status":"🟢" if len(activated)>=100 else "🟡","Weight":"8%"},
        {"KPI":"K088 — Card Spend","Target":"KES 200M","Actual":f"KES {total_spend:.1f}M","Status":"🟢" if total_spend>=200 else "🟡","Weight":"10%"},
        {"KPI":"K089 — Dispute SLA","Target":f"> {dispute_target}%","Actual":f"{dispute_sla_pct}%","Status":"🟢" if dispute_sla_pct>=dispute_target else "🟡","Weight":"8%"},
        {"KPI":"K090 — Fraud Loss","Target":f"< {fraud_threshold}%","Actual":f"{fraud_pct}%","Status":"🟢" if fraud_pct<=fraud_threshold else "🔴","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="cd_bsc",type="primary"):
        _bsc_trigger(uname,"K087"); st.success("✅ BSC updated"); st.rerun()
