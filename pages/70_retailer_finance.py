"""pages/70_retailer_finance.py — Retailer Finance & Supply Chain.
Distributor finance, approved buyer programmes, invoice discounting, supply chain finance.
BSC: K060 (disbursements), K061 (portfolio NPL), K062 (buyers onboarded).
Department: Commercial Banking. Roles: SME RM, Head of SME, Supply Chain Officer.
"""
import streamlit as st, pandas as pd, json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from decimal import Decimal
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("retailer_finance")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_comm  = any(x in role for x in ("relationship","commercial","sme","supply","trade","head"))

def _bsc_trigger(u,k=""):
    try:
        from utils.core import update_bsc_from_modules as _u; _u(u)
    except: pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"retailer_finance.json"
    raw = a2z_db.load_json(p) if p.exists() else []
    for r in raw:
        for k,v in r.items():
            if isinstance(v,Decimal): r[k]=float(v)
    return raw

@st.cache_data(ttl=60)
def _cfg():
    p = DATA/"retailer_config.json"
    if p.exists(): return a2z_db.load_json(p)
    return {
        "facility_types":[
            {"id":"DIST","name":"Distributor Finance","max_tenor_days":90,"active":True},
            {"id":"BUYER","name":"Approved Buyer Programme","max_tenor_days":60,"active":True},
            {"id":"INVOICE","name":"Invoice Discounting","max_tenor_days":120,"active":True},
            {"id":"LPO","name":"LPO Financing","max_tenor_days":30,"active":True},
            {"id":"AGRI","name":"Agri-Finance","max_tenor_days":180,"active":True},
        ],
        "supply_chains":["FMCG","Petroleum","Agriculture","Construction","Healthcare","Pharmaceuticals","Telecoms"],
        "approved_anchors":["Safaricom","EABL","BAT Kenya","Nation Media","KCB Group","Equity Group"],
        "npl_threshold_pct":3.0,
        "max_single_buyer_pct":25.0,
    }

def _save(recs): (DATA/"retailer_finance.json").write_text(json.dumps(recs,indent=2)); st.cache_data.clear()

records = _load(); cfg = _cfg()
my_records = [r for r in records if r.get("rm_username")==uname] if not is_admin else records
active = [r for r in records if r.get("status")=="Active"]
total_disb = sum(float(r.get("disbursed_m",0) or 0) for r in (my_records if not is_admin else records))
total_outstanding = sum(float(r.get("outstanding_m",0) or 0) for r in active)
npl_count = sum(1 for r in active if float(r.get("dpd",0) or 0)>=90)
npl_pct = round(npl_count/max(len(active),1)*100,1)
new_buyers = sum(1 for r in my_records if r.get("new_buyer"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🏪 Retailer & Supply Chain Finance</span><span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>Distributor finance · Approved buyers · Invoice discounting</span></div>",unsafe_allow_html=True)
if npl_pct > cfg.get("npl_threshold_pct",3.0): st.warning(f"⚠️ Portfolio NPL {npl_pct:.1f}% exceeds {cfg['npl_threshold_pct']:.1f}% threshold")
m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Active deals",len(active))
m2.metric("My disbursements",f"KES {total_disb:.0f}M")
m3.metric("Outstanding",f"KES {total_outstanding:.0f}M")
m4.metric("Portfolio NPL",f"{npl_pct:.1f}%",delta_color="normal" if npl_pct<=cfg["npl_threshold_pct"] else "inverse")
m5.metric("New buyers",new_buyers)

tabs = st.tabs(["📋 Portfolio","🔍 Deal Detail","➕ New Deal","📊 Analytics","⚙️ Config","🎯 BSC"])

with tabs[0]:
    vis = my_records if not is_admin else records
    f1,f2 = st.columns(2)
    ff = f1.selectbox("Facility type",["All"]+[f["id"] for f in cfg["facility_types"]],key="rf_ftype")
    fs = f2.selectbox("Status",["All","Active","Closed","NPL","Restructured"],key="rf_fstat")
    vis = [r for r in vis if (ff=="All" or r.get("facility_type","")==ff) and (fs=="All" or r.get("status","")==fs)]
    rows = [{"ID":r["id"],"Client":r.get("client_name","")[:22],"Type":r.get("facility_type",""),"Chain":r.get("supply_chain","")[:12],"Limit (M)":round(float(r.get("limit_m",0) or 0),1),"Utilised (M)":round(float(r.get("disbursed_m",0) or 0),1),"Util%":f"{float(r.get('utilisation_pct',0) or 0):.0f}%","DPD":int(r.get("dpd",0) or 0),"Status":r.get("status",""),"NPL":"🔴" if float(r.get("dpd",0) or 0)>=90 else ""} for r in sorted(vis,key=lambda x:-float(x.get("limit_m",0) or 0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(f"Portfolio: {len(vis)} deals | KES {sum(float(r.get('disbursed_m',0) or 0) for r in vis):.0f}M disbursed")

with tabs[1]:
    if vis:
        sel = st.selectbox("Select deal",[f"{r['id']} — {r.get('client_name','')[:30]}" for r in vis],key="rf_dsel")
        deal_id = sel.split(" — ")[0]
        deal = next((r for r in vis if r["id"]==deal_id),{})
        if deal:
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Limit",f"KES {float(deal.get('limit_m',0) or 0):.1f}M")
            c2.metric("Disbursed",f"KES {float(deal.get('disbursed_m',0) or 0):.1f}M")
            c3.metric("Utilisation",f"{float(deal.get('utilisation_pct',0) or 0):.0f}%")
            c4.metric("DPD",int(deal.get("dpd",0) or 0))
            st.markdown(f"**Anchor:** {deal.get('anchor_name','—')} | **Chain:** {deal.get('supply_chain','—')} | **Tenor:** {deal.get('tenor_days',0)} days")

with tabs[2]:
    if is_comm or is_admin:
        ftype_opts = [f["id"] for f in cfg["facility_types"] if f.get("active")]
        chain_opts = cfg["supply_chains"]
        anchor_opts = cfg["approved_anchors"]
        c1,c2 = st.columns(2)
        _cname = c1.text_input("Client name *",key="rf_ncname")
        _anchor= c2.selectbox("Anchor / Off-taker",anchor_opts,key="rf_nanchor")
        _ftype = c1.selectbox("Facility type",ftype_opts,key="rf_nftype")
        _chain = c2.selectbox("Supply chain",chain_opts,key="rf_nchain")
        _limit = c1.number_input("Facility limit (KES M)",0.0,5000.0,10.0,key="rf_nlimit")
        _disb  = c2.number_input("Initial disbursement (KES M)",0.0,5000.0,0.0,key="rf_ndisb")
        _tenor = st.number_input("Tenor (days)",1,365,60,key="rf_ntenor")
        _new_b = st.checkbox("New buyer (first time in programme)",key="rf_nnewb")
        if st.button("💾 Create deal",key="rf_ncreate",type="primary"):
            if _cname.strip():
                all_r = _load()
                util = round(_disb/max(_limit,0.001)*100,1) if _limit else 0
                all_r.append({"id":f"RF{len(all_r)+1:05d}","client_name":_cname.strip(),"facility_type":_ftype,"supply_chain":_chain,"anchor_name":_anchor,"limit_m":_limit,"disbursed_m":_disb,"outstanding_m":_disb,"utilisation_pct":util,"tenor_days":_tenor,"dpd":0,"status":"Active","new_buyer":_new_b,"rm_username":uname,"created_by":uname,"created_at":str(today)})
                _save(all_r)
                audit_log("RF_DEAL_CREATED",uname,f"{_cname}: KES {_limit:.0f}M {_ftype}")
                _bsc_trigger(uname,"K060")
                st.success("✅ Deal created"); st.rerun()
            else: st.error("Client name required")
    else: st.info("Deal creation for Commercial Banking team.")

with tabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By facility type:**")
        by_ftype = defaultdict(lambda:{"count":0,"value":0,"npl":0})
        for r in records:
            t=r.get("facility_type","Other")
            by_ftype[t]["count"]+=1; by_ftype[t]["value"]+=float(r.get("disbursed_m",0) or 0)
            if float(r.get("dpd",0) or 0)>=90: by_ftype[t]["npl"]+=1
        ft_rows=[{"Type":t,"Deals":v["count"],"Disbursed (M)":round(v["value"],0),"NPL":v["npl"]}for t,v in sorted(by_ftype.items(),key=lambda x:-x[1]["value"])]
        st.dataframe(pd.DataFrame(ft_rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By supply chain:**")
        by_chain = defaultdict(lambda:{"count":0,"value":0})
        for r in records:
            c=r.get("supply_chain","Other")
            by_chain[c]["count"]+=1; by_chain[c]["value"]+=float(r.get("disbursed_m",0) or 0)
        ch_rows=[{"Chain":c,"Deals":v["count"],"KES M":round(v["value"],0)}for c,v in sorted(by_chain.items(),key=lambda x:-x[1]["value"])]
        st.dataframe(pd.DataFrame(ch_rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin or is_comm:
        st.markdown("**Facility types — configurable:**")
        for ft in cfg["facility_types"]:
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{ft['name']}**")
            c2.markdown(f"Max tenor: {ft['max_tenor_days']} days")
            ft["active"]=c3.checkbox("Active",value=ft.get("active",True),key=f"ft_{ft['id']}")
        new_npl = st.number_input("NPL threshold (%)",0.0,20.0,cfg.get("npl_threshold_pct",3.0),0.5,key="rf_npl_thr")
        if st.button("💾 Save config",key="rf_cfg_save",type="primary"):
            cfg["npl_threshold_pct"]=new_npl
            (DATA/"retailer_config.json").write_text(json.dumps(cfg,indent=2))
            st.cache_data.clear(); audit_log("RF_CFG_SAVED",uname,""); st.success("✅"); st.rerun()
    else: st.info("Config for Commercial management.")

with tabs[5]:
    st.markdown("**Retailer Finance BSC KPIs:**")
    st.metric("K060 — Disbursements",f"KES {total_disb:.0f}M","Target KES 100M",delta_color="normal" if total_disb>=100 else "inverse")
    st.metric("K061 — Portfolio NPL",f"{npl_pct:.1f}%","Target ≤3%",delta_color="normal" if npl_pct<=3 else "inverse")
    st.metric("K062 — New Buyers",new_buyers,"Target 10",delta_color="normal" if new_buyers>=10 else "inverse")
    if st.button("🔄 Refresh BSC",key="rf_bsc_ref"): _bsc_trigger(uname,"retailer"); st.success("✅"); st.rerun()
