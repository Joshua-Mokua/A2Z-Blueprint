"""pages/71_bid_bond.py — Bid Bond & Guarantees Management.
Dept: Trade Finance | KPIs: K063 K064 K065 | BSC: Auto-scored
Hardcoded: bond types, CBK reporting threshold, board approval threshold
Configurable: commission rates per bond type, collateral types, approved beneficiaries
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

require_access("bid_bond")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_tf    = any(x in role for x in ("trade","commercial","credit","guarantee","manager","head","director"))

BOND_TYPES = ["Bid Bond","Performance Bond","Advance Payment Guarantee","Retention Bond","Customs Bond"]
CBK_THRESHOLD_M = 50.0

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"bid_bonds.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    if not mc.exists(): return {}
    return json.loads(mc.read_text(encoding="utf-8")).get("bid_bond",{})

def _save(data):
    (DATA/"bid_bonds.json").write_text(json.dumps(data,indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
comm_rates    = conf_cfg.get("commission_rates",{bt:1.0 for bt in BOND_TYPES})
coll_types    = conf_cfg.get("collateral_types",[])
coll_names    = [c["name"] for c in coll_types] or ["Cash Margin","Property Charge","Debenture","Crosscharge"]
approved_bens = conf_cfg.get("approved_beneficiaries",[])
call_thresh   = conf_cfg.get("call_rate_threshold_pct",2.0)

active_bb    = [r for r in records if r.get("status")=="Active"]
issued_bb    = [r for r in records if r.get("status") in ("Issued","Active")]
called_bb    = [r for r in records if r.get("called")]
expiring_bb  = [r for r in active_bb if r.get("expiry_date","")<=str(today+timedelta(days=30))]
total_exp    = sum(r.get("amount_kes",0) for r in active_bb)
total_rev    = sum(r.get("commission_kes",0) for r in records)
call_rate    = round(len(called_bb)/max(len(issued_bb),1)*100,1)
cbk_needed   = [r for r in issued_bb if r.get("amount_kes",0)/1e6>=CBK_THRESHOLD_M and not r.get("cbk_reported")]

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📜 Bid Bond & Guarantees</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Trade Finance · K063 · K064 · K065</span></div>",
    unsafe_allow_html=True)

if called_bb:
    st.error(f"🔴 {len(called_bb)} bond(s) called — immediate action required")
if expiring_bb:
    st.warning(f"⚠️ {len(expiring_bb)} bond(s) expiring within 30 days")
if cbk_needed:
    st.warning(f"⚠️ {len(cbk_needed)} bond(s) above KES {CBK_THRESHOLD_M}M requiring CBK reporting")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total bonds",      len(records))
m2.metric("Active",           len(active_bb))
m3.metric("Exposure",         f"KES {total_exp/1e9:.1f}B")
m4.metric("Commission YTD",   f"KES {total_rev/1e6:.1f}M")
m5.metric("Call rate",        f"{call_rate}%", delta_color="inverse" if call_rate>call_thresh else "off")

tabs = st.tabs(["📋 Register","⚡ Actions Required","➕ Issue Bond","📊 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    ftype = f1.selectbox("Bond type",["All"]+BOND_TYPES,key="bb_ftype")
    fstat = f2.selectbox("Status",["All","Application","Approved","Issued","Active","Expired","Called","Cancelled"],key="bb_fstat")
    fsearch= f3.text_input("Search customer/ref",key="bb_fsearch")
    vis = [r for r in records
           if (ftype=="All" or r.get("bond_type","")==ftype)
           and (fstat=="All" or r.get("status","")==fstat)
           and (not fsearch or fsearch.lower() in r.get("customer_name","").lower()
                or fsearch.lower() in r.get("reference","").lower())]
    rows=[{"Ref":r.get("reference","")[:15],"Type":r.get("bond_type","")[:18],
            "Customer":r.get("customer_name","")[:20],"Beneficiary":r.get("beneficiary","")[:20],
            "Amount(M)":round(r.get("amount_kes",0)/1e6,1),"Commission":f"KES {r.get('commission_kes',0):,.0f}",
            "Issued":r.get("issue_date","")[:10],"Expiry":r.get("expiry_date","")[:10],
            "Status":r.get("status",""),"CBK":"✅" if r.get("cbk_reported") else "⏳" if r.get("amount_kes",0)/1e6>=CBK_THRESHOLD_M else "",
            "Called":"🔴" if r.get("called") else ""} for r in vis]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    if called_bb:
        st.markdown("**🔴 Called bonds — action required:**")
        for r in called_bb:
            with st.expander(f"🔴 {r.get('reference','')} — {r.get('customer_name','')[:30]}"):
                c1,c2,c3 = st.columns(3)
                c1.metric("Bond Amount",f"KES {r.get('amount_kes',0)/1e6:.1f}M")
                c2.metric("Called Amount",f"KES {r.get('called_amount',0)/1e6:.1f}M")
                c3.metric("Beneficiary",r.get("beneficiary","")[:20])
                action = st.selectbox("Action",["Select","Pay beneficiary","Dispute call","Customer indemnity"],key=f"bb_call_{r['id']}")
                notes  = st.text_area("Notes",key=f"bb_call_note_{r['id']}")
                if st.button("Apply",key=f"bb_call_apply_{r['id']}",type="primary"):
                    if action!="Select":
                        audit_log("BOND_CALL_ACTIONED",uname,f"{r['id']}: {action}")
                        st.success(f"✅ {action} applied")
    if cbk_needed:
        st.markdown("**⚠️ CBK reporting outstanding:**")
        for r in cbk_needed:
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{r.get('reference','')}** — {r.get('customer_name','')[:25]}")
            c2.markdown(f"KES {r.get('amount_kes',0)/1e6:.1f}M")
            if c3.button("Mark reported",key=f"bb_cbk_{r['id']}"):
                all_r = _load()
                for rec in all_r:
                    if rec["id"]==r["id"]: rec["cbk_reported"]=True; break
                _save(all_r)
                audit_log("BOND_CBK_REPORTED",uname,r["id"])
                st.success("✅ CBK reported"); st.rerun()
    if expiring_bb:
        st.markdown("**⚠️ Expiring within 30 days:**")
        exp_rows=[{"Ref":r.get("reference",""),"Customer":r.get("customer_name","")[:20],"Expiry":r.get("expiry_date","")[:10],"Amount(M)":round(r.get("amount_kes",0)/1e6,1)} for r in expiring_bb]
        st.dataframe(pd.DataFrame(exp_rows),use_container_width=True,hide_index=True)
    if not called_bb and not cbk_needed and not expiring_bb:
        st.success("✅ No actions required.")

with tabs[2]:
    if is_tf or is_admin:
        ben_opts = approved_bens if approved_bens else ["Government of Kenya","Kenya Power","Ministry of Works"]
        r1,r2 = st.columns(2)
        cust_  = r1.text_input("Customer name *",key="bb_cust")
        cif_   = r2.text_input("Customer CIF",key="bb_cif")
        btype_ = r1.selectbox("Bond type *",BOND_TYPES,key="bb_btype2")
        benef_ = r2.selectbox("Beneficiary",ben_opts+["Other"],key="bb_benef")
        if benef_=="Other": benef_ = st.text_input("Beneficiary name",key="bb_benef_other")
        proj_  = r1.text_input("Project name",key="bb_proj")
        amt_   = r2.number_input("Bond amount (KES)",0.0,key="bb_amt")
        comm_r = comm_rates.get(btype_,1.0)
        comm_kes = round(amt_*comm_r/100,0) if amt_>0 else 0
        r1.caption(f"Commission rate: {comm_r}% → KES {comm_kes:,.0f}")
        coll_  = r2.selectbox("Collateral",coll_names,key="bb_coll")
        expiry_= r1.date_input("Expiry date",today+timedelta(days=180),key="bb_exp")
        cbk_rpt= amt_/1e6>=CBK_THRESHOLD_M
        if cbk_rpt: st.warning(f"⚠️ Amount ≥ KES {CBK_THRESHOLD_M}M — CBK reporting required after issuance")
        if st.button("💾 Issue bond",key="bb_issue",type="primary"):
            if cust_.strip() and amt_>0 and str(benef_).strip():
                all_r = _load()
                all_r.append({"id":f"BB{len(all_r)+1:04d}","reference":f"ECOBB{len(all_r)+100000}",
                              "bond_type":btype_,"customer_name":cust_.strip(),"customer_cif":cif_,
                              "beneficiary":str(benef_).strip(),"project_name":proj_,"amount_kes":amt_,"currency":"KES",
                              "commission_pct":comm_r,"commission_kes":comm_kes,"issue_date":str(today),
                              "expiry_date":str(expiry_),"status":"Issued","collateral_type":coll_,
                              "collateral_value":amt_*1.25,"rm_code":uname,"credit_approved_by":"",
                              "cbk_reported":False,"called":False,"called_amount":0,"extended_count":0,"notes":""})
                _save(all_r)
                audit_log("BOND_ISSUED",uname,f"{cust_}: KES {amt_/1e6:.1f}M {btype_}")
                _bsc_trigger(uname,"K063")
                st.success(f"✅ Bond issued — Commission: KES {comm_kes:,.0f}"); st.rerun()
    else:
        st.info("Bond issuance available to Trade Finance team.")

with tabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        by_type = defaultdict(lambda:{"count":0,"exposure":0,"revenue":0})
        for r in records:
            t=r.get("bond_type","Other"); by_type[t]["count"]+=1; by_type[t]["exposure"]+=r.get("amount_kes",0); by_type[t]["revenue"]+=r.get("commission_kes",0)
        st.markdown("**By bond type:**")
        rows=[{"Type":t,"Bonds":v["count"],"Exposure(M)":round(v["exposure"]/1e6,1),"Revenue":f"KES {v['revenue']:,.0f}"} for t,v in sorted(by_type.items(),key=lambda x:-x[1]["exposure"])]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with c2:
        by_ben = defaultdict(lambda:{"count":0,"exposure":0})
        for r in records: b=r.get("beneficiary","Other"); by_ben[b]["count"]+=1; by_ben[b]["exposure"]+=r.get("amount_kes",0)
        st.markdown("**By beneficiary:**")
        rows=[{"Beneficiary":b[:25],"Bonds":v["count"],"Exposure(M)":round(v["exposure"]/1e6,1)} for b,v in sorted(by_ben.items(),key=lambda x:-x[1]["exposure"])[:10]]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info(f"ℹ️ Hardcoded: Bond types, CBK reporting threshold KES {CBK_THRESHOLD_M}M, board approval threshold KES 500M")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("bid_bond",{}).get("configurable",{})
        st.markdown("**Commission rates by bond type:**")
        new_rates = {}
        for bt in BOND_TYPES:
            new_rates[bt] = st.number_input(f"{bt} commission %",0.1,5.0,float(cfg_m.get("commission_rates",{}).get(bt,1.0)),0.05,key=f"bb_cr_{bt}")
        new_call = st.number_input("Call rate alert threshold (%)",0.1,10.0,float(cfg_m.get("call_rate_threshold_pct",2.0)),0.1,key="bb_cfg_call")
        st.markdown("**Approved beneficiaries:**")
        curr_bens = cfg_m.get("approved_beneficiaries",[])
        st.write(curr_bens)
        new_ben = st.text_input("Add beneficiary",key="bb_new_ben")
        if st.button("➕ Add",key="bb_ben_add") and new_ben.strip():
            curr_bens.append(new_ben.strip()); audit_log("BB_BENEF_ADDED",uname,new_ben)
        if st.button("💾 Save config",key="bb_cfg_save",type="primary"):
            cfg_m.update({"commission_rates":new_rates,"call_rate_threshold_pct":new_call,"approved_beneficiaries":curr_bens})
            mc["bid_bond"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("BB_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

with tabs[5]:
    bsc_rows=[
        {"KPI":"K063 — Bond Revenue","Target":"KES 5M","Actual":f"KES {total_rev/1e6:.1f}M","Status":"🟢" if total_rev>5e6 else "🟡","Weight":"10%"},
        {"KPI":"K064 — Bonds Issued","Target":"20","Actual":str(len(issued_bb)),"Status":"🟢" if len(issued_bb)>=20 else "🟡","Weight":"8%"},
        {"KPI":"K065 — Bond Call Rate","Target":f"< {call_thresh}%","Actual":f"{call_rate}%","Status":"🟢" if call_rate<call_thresh else "🔴","Weight":"8%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="bb_bsc",type="primary"):
        _bsc_trigger(uname,"K063"); st.success("✅ BSC updated"); st.rerun()
