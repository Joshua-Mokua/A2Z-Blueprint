"""pages/71_bid_bond.py — Bid Bond & Guarantees Management.
Issue, track and manage bid bonds, performance bonds and advance payment guarantees.
BSC: K063 (bonds issued), K064 (commission), K065 (expiry management).
Department: Trade Finance. Roles: Trade Finance Officer, Guarantees Officer.
"""
import streamlit as st, pandas as pd, json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from decimal import Decimal
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("bid_bond")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_tf    = any(x in role for x in ("trade","guarantee","bond","head","director","manager"))

def _bsc_trigger(u,k=""):
    try:
        from utils.core import update_bsc_from_modules as _u; _u(u)
    except: pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"bid_bonds.json"
    raw = json.loads(p.read_text()) if p.exists() else []
    for r in raw:
        for k,v in r.items():
            if isinstance(v,Decimal): r[k]=float(v)
    return raw

@st.cache_data(ttl=60)
def _cfg():
    p = DATA/"bidbond_config.json"
    if p.exists(): return json.loads(p.read_text())
    return {
        "bond_types":[
            {"id":"BID","name":"Bid Bond","commission_pct":0.5,"max_tenor_days":180,"cbk_reportable":False,"active":True},
            {"id":"PERF","name":"Performance Bond","commission_pct":1.0,"max_tenor_days":365,"cbk_reportable":True,"active":True},
            {"id":"APG","name":"Advance Payment Guarantee","commission_pct":1.5,"max_tenor_days":365,"cbk_reportable":True,"active":True},
            {"id":"PAY","name":"Payment Guarantee","commission_pct":0.75,"max_tenor_days":180,"cbk_reportable":True,"active":True},
            {"id":"CUST","name":"Customs Bond","commission_pct":0.5,"max_tenor_days":365,"cbk_reportable":False,"active":True},
            {"id":"RENTAL","name":"Rental Guarantee","commission_pct":1.0,"max_tenor_days":730,"cbk_reportable":False,"active":True},
        ],
        "approved_beneficiaries":["Government of Kenya","KRA","KEBS","KeNHA","KPLC","Nairobi City County","KPA"],
        "cbk_report_threshold_kes":10_000_000,
        "max_single_exposure_m":500.0,
    }

def _save(recs): (DATA/"bid_bonds.json").write_text(json.dumps(recs,indent=2)); st.cache_data.clear()

records = _load(); cfg = _cfg()
active   = [r for r in records if r.get("status")=="Active"]
called   = [r for r in records if r.get("status")=="Called"]
expiring = [r for r in records if r.get("status")=="Active" and r.get("expiry_date","")<=str(today+timedelta(days=30))]
cbk_due  = [r for r in records if r.get("cbk_reportable") and not r.get("cbk_reported")]
my_bonds = [r for r in records if r.get("officer_username")==uname] if not is_admin else records

total_commission = sum(float(r.get("commission_kes",0) or 0) for r in my_bonds)/1e6
total_liability  = sum(float(r.get("bond_amount_kes",0) or 0) for r in active)/1e9

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🔏 Bid Bonds & Guarantees</span><span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>Bid bonds · Performance bonds · APGs · Payment guarantees</span></div>",unsafe_allow_html=True)
if called: st.error(f"🔴 {len(called)} bond(s) have been called — immediate action required")
if expiring: st.warning(f"⚠️ {len(expiring)} bond(s) expiring within 30 days")
if cbk_due: st.warning(f"⚠️ {len(cbk_due)} bond(s) pending CBK regulatory reporting")

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Active bonds",len(active))
m2.metric("Called",len(called),delta_color="inverse" if called else "normal")
m3.metric("Expiring (30d)",len(expiring))
m4.metric("Liability (KES B)",f"{total_liability:.2f}")
m5.metric("My commission (KES M)",f"{total_commission:.1f}")
m6.metric("CBK reporting due",len(cbk_due))

tabs = st.tabs(["📋 Register","⚡ Actions Required","➕ Issue Bond","📊 Analytics","⚙️ Config","🎯 BSC"])

with tabs[0]:
    f1,f2 = st.columns(2)
    fb = f1.selectbox("Bond type",["All"]+[b["id"] for b in cfg["bond_types"]],key="bb_fbtype")
    fs = f2.selectbox("Status",["All","Active","Expired","Called","Returned","Cancelled"],key="bb_fstat")
    vis = [r for r in records if (fb=="All" or r.get("bond_type","")==fb) and (fs=="All" or r.get("status","")==fs)]
    rows=[{"Ref":r["id"],"Type":r.get("bond_type",""),"Beneficiary":r.get("beneficiary","")[:20],"Amount (M)":round(float(r.get("bond_amount_kes",0) or 0)/1e6,1),"Commission (KES)":f"{float(r.get('commission_kes',0) or 0):,.0f}","Issue":r.get("issue_date","")[:10],"Expiry":r.get("expiry_date","")[:10],"Status":r.get("status",""),"CBK":"✅" if r.get("cbk_reported") else "⏳" if r.get("cbk_reportable") else "—","Called":"🔴" if r.get("status")=="Called" else ""}for r in sorted(vis,key=lambda x:x.get("expiry_date",""))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(f"Total liability: KES {sum(float(r.get('bond_amount_kes',0) or 0) for r in vis)/1e9:.2f}B across {len(vis)} instruments")

with tabs[1]:
    for section,items,icon,action in [("Called bonds",called,"🔴","Investigate immediately"),("CBK reporting due",cbk_due,"📋","File within 5 days"),("Expiring bonds",expiring,"⚠️","Renew or close")]:
        if items:
            st.markdown(f"**{icon} {section} ({len(items)}) — {action}:**")
            rows=[{"Ref":r["id"],"Type":r.get("bond_type",""),"Beneficiary":r.get("beneficiary","")[:22],"Amount (M)":round(float(r.get("bond_amount_kes",0) or 0)/1e6,1),"Expiry":r.get("expiry_date","")[:10]}for r in items]
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    if called and (is_tf or is_admin):
        sel_called = st.selectbox("Select called bond to action",[r["id"] for r in called],key="bb_called_sel")
        act = st.selectbox("Action",["Pay","Dispute","Negotiate","Escalate"],key="bb_called_act")
        note = st.text_area("Action notes",key="bb_called_note")
        if st.button("💾 Record action",key="bb_called_save",type="primary"):
            all_r = _load()
            for r2 in all_r:
                if r2["id"]==sel_called: r2["action_taken"]=act; r2["action_notes"]=note; r2["actioned_by"]=uname
            _save(all_r); audit_log("BOND_CALLED_ACTIONED",uname,f"{sel_called}: {act}")
            _bsc_trigger(uname,"K065"); st.success("✅ Action recorded"); st.rerun()

with tabs[2]:
    if is_tf or is_admin:
        bond_type_opts = [b["id"] for b in cfg["bond_types"] if b.get("active")]
        beneficiary_opts = cfg["approved_beneficiaries"] + ["Other"]
        c1,c2 = st.columns(2)
        _principal = c1.text_input("Principal / Applicant *",key="bb_nprincipal")
        _beneficiary = c2.selectbox("Beneficiary",beneficiary_opts,key="bb_nbene")
        if _beneficiary=="Other": _beneficiary = st.text_input("Specify beneficiary",key="bb_nbene_other")
        _btype = c1.selectbox("Bond type",bond_type_opts,key="bb_nbtype")
        _amount= c2.number_input("Bond amount (KES)",0.0,10_000_000_000.0,1_000_000.0,key="bb_namt")
        _issue = c1.date_input("Issue date",today,key="bb_nissue")
        _expiry= c2.date_input("Expiry date",today+timedelta(days=90),key="bb_nexpiry")
        btype_def = next((b for b in cfg["bond_types"] if b["id"]==_btype),{})
        comm_pct  = btype_def.get("commission_pct",0.5)
        commission= _amount*comm_pct/100
        cbk_report= _amount>=cfg.get("cbk_report_threshold_kes",10_000_000) or btype_def.get("cbk_reportable")
        st.info(f"Commission: KES {commission:,.0f} ({comm_pct:.2f}%) | CBK reportable: {'Yes' if cbk_report else 'No'}")
        _tender_no = st.text_input("Tender / contract reference",key="bb_ntender")
        if st.button("💾 Issue bond",key="bb_nissue_btn",type="primary"):
            if _principal.strip():
                all_r = _load()
                all_r.append({"id":f"BB{len(all_r)+1:05d}","bond_type":_btype,"principal":_principal.strip(),"beneficiary":_beneficiary,"bond_amount_kes":_amount,"commission_kes":commission,"commission_pct":comm_pct,"issue_date":str(_issue),"expiry_date":str(_expiry),"status":"Active","tender_reference":_tender_no.strip(),"cbk_reportable":bool(cbk_report),"cbk_reported":False,"officer_username":uname,"created_by":uname,"created_at":str(today)})
                _save(all_r); audit_log("BOND_ISSUED",uname,f"{_btype}: {_principal} KES {_amount:,.0f}")
                _bsc_trigger(uname,"K063"); st.success(f"✅ Bond issued — commission KES {commission:,.0f}"); st.rerun()
            else: st.error("Principal required")
    else: st.info("Bond issuance for Trade Finance team.")

with tabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By bond type:**")
        by_btype = defaultdict(lambda:{"count":0,"amount":0,"commission":0})
        for r in records:
            t=r.get("bond_type","Other")
            by_btype[t]["count"]+=1; by_btype[t]["amount"]+=float(r.get("bond_amount_kes",0) or 0)
            by_btype[t]["commission"]+=float(r.get("commission_kes",0) or 0)
        bt_rows=[{"Type":t,"Bonds":v["count"],"Amount (M)":round(v["amount"]/1e6,1),"Commission (KES)":f"{v['commission']:,.0f}"}for t,v in sorted(by_btype.items(),key=lambda x:-x[1]["amount"])]
        st.dataframe(pd.DataFrame(bt_rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By beneficiary:**")
        by_bene = defaultdict(lambda:{"count":0,"amount":0})
        for r in records:
            b=r.get("beneficiary","Other")
            by_bene[b]["count"]+=1; by_bene[b]["amount"]+=float(r.get("bond_amount_kes",0) or 0)
        bn_rows=[{"Beneficiary":b[:22],"Bonds":v["count"],"Amount (M)":round(v["amount"]/1e6,1)}for b,v in sorted(by_bene.items(),key=lambda x:-x[1]["amount"])]
        st.dataframe(pd.DataFrame(bn_rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin or is_tf:
        st.markdown("**Bond types — commission rates configurable:**")
        for bt in cfg["bond_types"]:
            c1,c2,c3,c4 = st.columns([3,2,2,1])
            c1.markdown(f"**{bt['name']}**")
            new_comm = c2.number_input("Commission %",0.0,10.0,float(bt.get("commission_pct",0.5)),0.25,key=f"bt_comm_{bt['id']}")
            c3.markdown(f"Max tenor: {bt['max_tenor_days']}d | CBK: {'Yes' if bt.get('cbk_reportable') else 'No'}")
            bt["commission_pct"]=new_comm; bt["active"]=c4.checkbox("Active",value=bt.get("active",True),key=f"bt_act_{bt['id']}")
        new_cbk = st.number_input("CBK report threshold (KES)",0.0,100_000_000.0,float(cfg.get("cbk_report_threshold_kes",10_000_000)),1_000_000.0,key="bb_cbk_thr")
        if st.button("💾 Save config",key="bb_cfg_save",type="primary"):
            cfg["cbk_report_threshold_kes"]=new_cbk
            (DATA/"bidbond_config.json").write_text(json.dumps(cfg,indent=2))
            st.cache_data.clear(); audit_log("BIDBOND_CFG_SAVED",uname,""); st.success("✅"); st.rerun()
    else: st.info("Config for Trade Finance management.")

with tabs[5]:
    st.markdown("**Bid Bond & Guarantees BSC KPIs:**")
    st.metric("K063 — Bonds Issued",len(my_bonds),"Target 20")
    st.metric("K064 — Commission Revenue",f"KES {total_commission:.1f}M","Target KES 5M",delta_color="normal" if total_commission>=5 else "inverse")
    managed = sum(1 for r in my_bonds if r.get("status") in ("Expired","Returned") or r.get("expiry_date","")>=str(today))
    st.metric("K065 — Bond Expiry Management",f"{managed/max(len(my_bonds),1)*100:.0f}%","Target 90%")
    if st.button("🔄 Refresh BSC",key="bb_bsc_ref"): _bsc_trigger(uname,"bid_bond"); st.success("✅"); st.rerun()
