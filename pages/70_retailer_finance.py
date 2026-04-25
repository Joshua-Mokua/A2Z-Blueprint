"""pages/70_retailer_finance.py — Retailer Finance & Supply Chain.
Dept: Commercial & Corporate | KPIs: K060 K061 K062 | BSC: Auto-scored
Hardcoded: facility types, supply chain categories, max tenor, CBK reporting
Configurable: interest rate bands, approved buyers, TAT target, NPL threshold
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

require_access("retailer_finance")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_comm  = any(x in role for x in ("commercial","retail","relationship","credit","manager","head","director"))

FACILITY_TYPES  = ["LPO Finance","Invoice Discounting","Supply Chain Finance","Distributor Credit"]
SUPPLY_CHAINS   = ["FMCG","Electronics","Pharmaceuticals","Construction","Agriculture","Clothing","Petroleum"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"retailer_finance.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    if not mc.exists(): return {}
    return json.loads(mc.read_text(encoding="utf-8")).get("retailer_finance",{})

def _save(data):
    (DATA/"retailer_finance.json").write_text(json.dumps(data,indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
rate_floor      = conf_cfg.get("interest_rate_floor_pct",12.0)
rate_ceiling    = conf_cfg.get("interest_rate_ceiling_pct",20.0)
tat_target      = conf_cfg.get("tat_target_days",3)
npl_threshold   = conf_cfg.get("npl_threshold_pct",5.0)
approved_buyers = conf_cfg.get("approved_buyers",[])
buyer_names     = [b["name"] for b in approved_buyers if b.get("active",True)]

active_rf   = [r for r in records if r.get("status") in ("Disbursed","Repaying")]
npl_rf      = [r for r in records if r.get("dpd",0)>90 or r.get("status")=="NPL"]
portfolio_m = round(sum(r.get("outstanding_kes",r.get("amount_kes",0)) for r in active_rf)/1e6,1)
npl_pct     = round(sum(r.get("outstanding_kes",0) for r in npl_rf)/max(sum(r.get("outstanding_kes",0) for r in active_rf),1)*100,1)
my_deals    = [r for r in records if r.get("rm_code","")==uname]

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🛒 Retailer Finance</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Commercial & Corporate · K060 · K061 · K062</span></div>",
    unsafe_allow_html=True)

if npl_pct > npl_threshold:
    st.error(f"🔴 RF NPL {npl_pct}% exceeds {npl_threshold}% threshold")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Active deals",     len(active_rf))
m2.metric("Portfolio",        f"KES {portfolio_m:.0f}M")
m3.metric("NPL rate",         f"{npl_pct}%", delta_color="inverse" if npl_pct>npl_threshold else "off")
m4.metric("My deals",         len(my_deals))
m5.metric("Approved buyers",  len(buyer_names))

tabs = st.tabs(["📋 Portfolio","🔍 Deal Detail","➕ New Deal","📊 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    fstat = f1.selectbox("Status",["All"]+["Application","Credit Review","Approved","Disbursed","Repaying","Closed","NPL"],key="rf_fstat")
    fsc   = f2.selectbox("Supply chain",["All"]+SUPPLY_CHAINS,key="rf_fsc")
    fmine = f3.checkbox("My deals only",key="rf_fmine")
    vis = [r for r in records
           if (fstat=="All" or r.get("status","")==fstat)
           and (fsc=="All" or r.get("supply_chain","")==fsc)
           and (not fmine or r.get("rm_code","")==uname)]
    rows = [{"ID":r["id"],"Buyer":r.get("buyer_name","")[:20],"Type":r.get("facility_type","")[:18],
              "Chain":r.get("supply_chain",""),"Amount(M)":round(r.get("amount_kes",0)/1e6,1),
              "Outstanding(M)":round(r.get("outstanding_kes",0)/1e6,1),
              "Tenor(d)":r.get("tenor_days",""),"Rate%":r.get("interest_rate_pa",0),
              "Status":r.get("status",""),"DPD":r.get("dpd",0),
              "LPO":r.get("lpo_reference","")[:10]} for r in vis]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    if records:
        sel = st.selectbox("Select deal",[f"{r['id']} — {r.get('buyer_name','')} ({r.get('facility_type','')})" for r in records],key="rf_dsel")
        deal = next((r for r in records if r["id"]==sel.split(" — ")[0]),{})
        if deal:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Amount",f"KES {deal.get('amount_kes',0)/1e6:.1f}M")
            c2.metric("Outstanding",f"KES {deal.get('outstanding_kes',0)/1e6:.1f}M")
            c3.metric("Utilisation",f"{deal.get('buyer_utilisation_pct',0):.0f}%")
            c4.metric("DPD",deal.get("dpd",0))
            st.markdown(f"**Buyer:** {deal.get('buyer_name','')} | **Supplier:** {deal.get('supplier_name','')}")
            st.markdown(f"**Type:** {deal.get('facility_type','')} | **Chain:** {deal.get('supply_chain','')}")
            st.markdown(f"**Tenor:** {deal.get('tenor_days','')}d | **Rate:** {deal.get('interest_rate_pa',0):.2f}% p.a. | **Collateral:** {deal.get('collateral','')}")
            st.markdown(f"**LPO:** {deal.get('lpo_reference','')} | **Invoice:** {deal.get('invoice_ref','')}")
            if deal.get("rm_code","") == uname or is_admin:
                new_stat = st.selectbox("Update status",["Application","Credit Review","Approved","Disbursed","Repaying","Closed","NPL"],
                                       index=["Application","Credit Review","Approved","Disbursed","Repaying","Closed","NPL"].index(deal.get("status","Application")) if deal.get("status") in ["Application","Credit Review","Approved","Disbursed","Repaying","Closed","NPL"] else 0,
                                       key="rf_upd_stat")
                if st.button("💾 Update status",key="rf_upd_btn"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"]==deal["id"]: rec["status"]=new_stat; break
                    _save(all_r)
                    audit_log("RF_STATUS_UPDATED",uname,f"{deal['id']}: {new_stat}")
                    _bsc_trigger(uname,"K060")
                    st.success("✅ Updated"); st.rerun()

with tabs[2]:
    if is_comm or is_admin:
        r1,r2 = st.columns(2)
        all_buyers = buyer_names if buyer_names else ["Enter buyer name below"]
        buyer_mode = r1.radio("Buyer",["Approved buyer","Other buyer"],key="rf_bmode",horizontal=True)
        if buyer_mode=="Approved buyer" and buyer_names:
            buyer_ = r1.selectbox("Select buyer",buyer_names,key="rf_bsel")
            buyer_limit = next((b.get("limit_m",0) for b in approved_buyers if b.get("name","")==buyer_),0)
            r1.caption(f"Approved limit: KES {buyer_limit}M")
        else:
            buyer_ = r1.text_input("Buyer name *",key="rf_bname")
        supp_  = r2.text_input("Supplier name",key="rf_supp")
        ftype_ = r1.selectbox("Facility type",FACILITY_TYPES,key="rf_ftype")
        sc_    = r2.selectbox("Supply chain",SUPPLY_CHAINS,key="rf_sc2")
        amt_   = r1.number_input("Amount (KES)",0.0,100_000_000.0,key="rf_amt")
        tenor_ = r2.selectbox("Tenor (days)",[30,60,90,120],key="rf_tenor")
        rate_  = r1.number_input("Interest rate % p.a.",float(rate_floor),float(rate_ceiling),float(rate_floor+2),0.25,key="rf_rate")
        lpo_   = r2.text_input("LPO / Invoice reference *",key="rf_lpo")
        if st.button("💾 Create deal",key="rf_create",type="primary"):
            if str(buyer_).strip() and amt_>0 and lpo_.strip():
                all_r = _load()
                all_r.append({"id":f"RF{len(all_r)+1:04d}","buyer_name":str(buyer_).strip(),
                              "buyer_cif":"","supplier_name":supp_.strip(),"supplier_cif":"",
                              "supply_chain":sc_,"facility_type":ftype_,"amount_kes":amt_,
                              "tenor_days":tenor_,"interest_rate_pa":rate_,"status":"Application",
                              "application_date":str(today),"disbursement_date":"","maturity_date":"",
                              "lpo_reference":lpo_,"invoice_ref":"","rm_code":uname,"branch":"",
                              "collateral":"LPO/Invoice assignment","buyer_limit_kes":amt_*3,
                              "buyer_utilisation_pct":0,"repaid_kes":0,"outstanding_kes":amt_,"dpd":0,"notes":""})
                _save(all_r)
                audit_log("RF_DEAL_CREATED",uname,f"{buyer_}: KES {amt_/1e6:.1f}M {ftype_}")
                _bsc_trigger(uname,"K060")
                st.success("✅ Deal created"); st.rerun()
            else:
                st.error("Buyer, amount and LPO reference required.")

with tabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        by_type = defaultdict(lambda:{"count":0,"amount":0,"outstanding":0})
        for r in records:
            t=r.get("facility_type","Other")
            by_type[t]["count"]+=1; by_type[t]["amount"]+=r.get("amount_kes",0); by_type[t]["outstanding"]+=r.get("outstanding_kes",0)
        st.markdown("**By facility type:**")
        rows=[{"Type":t,"Deals":v["count"],"Amount(M)":round(v["amount"]/1e6,1),"Outstanding(M)":round(v["outstanding"]/1e6,1)}
               for t,v in sorted(by_type.items(),key=lambda x:-x[1]["amount"])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with c2:
        by_chain = defaultdict(lambda:{"count":0,"amount":0})
        for r in records:
            c=r.get("supply_chain","Other"); by_chain[c]["count"]+=1; by_chain[c]["amount"]+=r.get("amount_kes",0)
        st.markdown("**By supply chain:**")
        rows=[{"Chain":c,"Deals":v["count"],"Amount(M)":round(v["amount"]/1e6,1)} for c,v in sorted(by_chain.items(),key=lambda x:-x[1]["amount"])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Facility types, supply chain categories, max tenor 180 days, CBK reportable")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("retailer_finance",{}).get("configurable",{})
        c1,c2,c3,c4 = st.columns(4)
        new_floor   = c1.number_input("Rate floor (%)",0.0,50.0,float(cfg_m.get("interest_rate_floor_pct",12.0)),0.25,key="rf_cfg_floor")
        new_ceil    = c2.number_input("Rate ceiling (%)",0.0,50.0,float(cfg_m.get("interest_rate_ceiling_pct",20.0)),0.25,key="rf_cfg_ceil")
        new_tat     = c3.number_input("TAT target (days)",1,30,int(cfg_m.get("tat_target_days",3)),key="rf_cfg_tat")
        new_npl     = c4.number_input("NPL threshold (%)",0.5,20.0,float(cfg_m.get("npl_threshold_pct",5.0)),0.5,key="rf_cfg_npl")
        st.markdown("**Approved buyers:**")
        for b in cfg_m.get("approved_buyers",[]):
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{b.get('name','')}**")
            c2.markdown(f"Limit: KES {b.get('limit_m',0)}M")
            c3.checkbox("Active",b.get("active",True),key=f"rf_b_act_{b.get('id','')}")
        with st.expander("➕ Add approved buyer"):
            r1,r2 = st.columns(2)
            bn = r1.text_input("Buyer name",key="rf_bn"); bl = r2.number_input("Limit (KES M)",0.0,key="rf_bl")
            if st.button("Add buyer",key="rf_badd"):
                if bn.strip():
                    cfg_m.setdefault("approved_buyers",[]).append({"id":bn.upper().replace(" ","_")[:10],"name":bn.strip(),"limit_m":bl,"active":True})
                    audit_log("RF_BUYER_ADDED",uname,bn)
        if st.button("💾 Save config",key="rf_cfg_save",type="primary"):
            cfg_m.update({"interest_rate_floor_pct":new_floor,"interest_rate_ceiling_pct":new_ceil,"tat_target_days":new_tat,"npl_threshold_pct":new_npl})
            mc["retailer_finance"]["configurable"]=cfg_m
            (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("RF_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

with tabs[5]:
    bsc_rows=[
        {"KPI":"K060 — RF Portfolio","Target":f"KES {conf_cfg.get('max_buyer_exposure_m',500):.0f}M","Actual":f"KES {portfolio_m:.0f}M","Status":"🟢" if portfolio_m>0 else "🟡"},
        {"KPI":"K061 — LPO TAT","Target":f"< {tat_target} days","Actual":"3 days (est)","Status":"🟢"},
        {"KPI":"K062 — RF NPL","Target":f"< {npl_threshold}%","Actual":f"{npl_pct}%","Status":"🟢" if npl_pct<npl_threshold else "🔴"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="rf_bsc",type="primary"):
        _bsc_trigger(uname,"K060"); st.success("✅ BSC updated"); st.rerun()
