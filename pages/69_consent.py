"""pages/69_consent.py — Consent Management (Kenya Data Protection Act 2019).
Records, tracks and renews customer consent. Configurable consent types and channels.
BSC: K058 (coverage rate), K059 (renewals processed).
Department: Risk & Compliance. Roles: Data Protection Officer, Compliance Officer.
"""
import streamlit as st, pandas as pd, json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from decimal import Decimal
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("consent_management")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_comp  = any(x in role for x in ("compliance","data","legal","risk","head"))

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _u; _u(username)
    except: pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"consent_register.json"
    return a2z_db.load_json(p) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    p = DATA/"consent_config.json"
    if p.exists(): return a2z_db.load_json(p)
    return {
        "consent_types":[
            {"id":"MARKETING","name":"Marketing Communications","duration_days":365,"active":True},
            {"id":"DATA_SHARE","name":"Data Sharing with Partners","duration_days":365,"active":True},
            {"id":"CREDIT_REF","name":"Credit Reference Bureau","duration_days":1095,"active":True},
            {"id":"DIGITAL","name":"Digital Banking Enrolment","duration_days":730,"active":True},
            {"id":"INSURANCE","name":"Bancassurance Products","duration_days":365,"active":True},
            {"id":"RESEARCH","name":"Customer Research","duration_days":180,"active":True},
        ],
        "collection_channels":["Branch","Mobile App","Online Banking","USSD","Call Centre","Agent"],
        "renewal_notice_days":30,
        "expiry_action":"Flag for renewal",
    }

def _save(recs): (DATA/"consent_register.json").write_text(json.dumps(recs,indent=2)); st.cache_data.clear()

records = _load(); cfg = _cfg()
active  = [r for r in records if r.get("status")=="Active"]
expiring= [r for r in records if r.get("status")=="Active" and
            r.get("expiry_date","") <= str(today+timedelta(days=cfg.get("renewal_notice_days",30)))]
expired = [r for r in records if r.get("status")=="Expired"]
total_custs = len(set(r.get("customer_id","") for r in records))
coverage= round(len(active)/max(total_custs,1)*100,1)

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🔐 Consent Management</span><span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>DPA 2019 compliance · Customer data consent tracking</span></div>",unsafe_allow_html=True)
if expiring: st.warning(f"⚠️ {len(expiring)} consents expiring within {cfg['renewal_notice_days']} days")
if coverage<90: st.error(f"🔴 Consent coverage {coverage:.0f}% — below 90% regulatory threshold")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total records",f"{len(records):,}")
m2.metric("Active consents",f"{len(active):,}")
m3.metric("Coverage rate",f"{coverage:.1f}%",delta_color="normal" if coverage>=95 else "inverse")
m4.metric("Expiring soon",len(expiring),delta_color="inverse" if expiring else "normal")
m5.metric("Expired",len(expired))

tabs = st.tabs(["📋 Register","⚠️ Expiring","📊 Analytics","➕ Record Consent","🔄 Bulk Actions","⚙️ Config","🎯 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    fs = f1.selectbox("Status",["All","Active","Expired","Withdrawn"],key="con_fstat")
    ft = f2.selectbox("Type",["All"]+[c["id"] for c in cfg["consent_types"]],key="con_ftype")
    fc = f3.text_input("Customer ID / name",key="con_fsearch")
    vis = [r for r in records if (fs=="All" or r.get("status","")==fs) and (ft=="All" or r.get("consent_type","")==ft) and (not fc or fc.lower() in r.get("customer_id","").lower() or fc.lower() in r.get("customer_name","").lower())]
    rows=[{"ID":r["id"],"Customer":r.get("customer_name","")[:20],"Type":r.get("consent_type","")[:15],"Channel":r.get("channel",""),"Given":r.get("consent_date","")[:10],"Expiry":r.get("expiry_date","")[:10],"Status":r.get("status",""),"Renewed":"✅" if r.get("renewed") else ""}for r in sorted(vis,key=lambda x:x.get("expiry_date",""))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    st.markdown("**Consents requiring renewal action:**")
    if expiring:
        exp_rows = [{"ID":r["id"],"Customer":r.get("customer_name","")[:20],"Type":r.get("consent_type",""),"Expiry":r.get("expiry_date","")[:10],"Days left":(date.fromisoformat(r.get("expiry_date",str(today)))- today).days} for r in sorted(expiring,key=lambda x:x.get("expiry_date",""))]
        st.dataframe(pd.DataFrame(exp_rows),use_container_width=True,hide_index=True)
        if st.button("📧 Flag all for renewal outreach",key="flag_renewal"):
            audit_log("CONSENT_RENEWAL_FLAGGED",uname,f"{len(expiring)} consents flagged")
            st.success(f"✅ {len(expiring)} consents flagged for outreach")
    else: st.success("✅ No consents expiring soon")

with tabs[2]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By consent type:**")
        by_type = defaultdict(lambda:{"active":0,"expired":0})
        for r in records:
            t=r.get("consent_type","Other")
            by_type[t]["active" if r.get("status")=="Active" else "expired"] += 1
        type_rows = [{"Type":t,"Active":v["active"],"Expired":v["expired"],"Total":v["active"]+v["expired"]} for t,v in sorted(by_type.items(),key=lambda x:-x[1]["active"])]
        st.dataframe(pd.DataFrame(type_rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By channel:**")
        by_ch = defaultdict(int)
        for r in records: by_ch[r.get("channel","Unknown")] += 1
        ch_rows = [{"Channel":c,"Count":n,"Share":f"{n/max(len(records),1)*100:.0f}%"} for c,n in sorted(by_ch.items(),key=lambda x:-x[1])]
        st.dataframe(pd.DataFrame(ch_rows),use_container_width=True,hide_index=True)

with tabs[3]:
    type_opts = [c["id"] for c in cfg["consent_types"] if c.get("active")]
    ch_opts   = cfg["collection_channels"]
    c1,c2 = st.columns(2)
    _cid  = c1.text_input("Customer ID *",key="con_ncid")
    _cname= c2.text_input("Customer name *",key="con_ncname")
    _ctype= c1.selectbox("Consent type",type_opts,key="con_ntype")
    _cch  = c2.selectbox("Collection channel",ch_opts,key="con_nch")
    _cdate= st.date_input("Consent date",today,key="con_ndate")
    # Auto-compute expiry
    type_dur = next((c["duration_days"] for c in cfg["consent_types"] if c["id"]==_ctype),365)
    exp_date = _cdate + timedelta(days=type_dur)
    st.info(f"Expiry: {exp_date} ({type_dur} days)")
    _witness = st.text_input("Witness / staff ID",key="con_nwitness")
    if st.button("💾 Record consent",key="con_nsave",type="primary"):
        if _cid.strip() and _cname.strip():
            all_r = _load()
            all_r.append({"id":f"CON{len(all_r)+1:06d}","customer_id":_cid.strip(),"customer_name":_cname.strip(),"consent_type":_ctype,"channel":_cch,"consent_date":str(_cdate),"expiry_date":str(exp_date),"status":"Active","renewed":False,"recorded_by":uname,"witness":_witness.strip(),"action":"Recorded"})
            _save(all_r)
            audit_log("CONSENT_RECORDED",uname,f"{_cid}: {_ctype}")
            _bsc_trigger(uname,"K058")
            st.success("✅ Consent recorded"); st.rerun()
        else: st.error("Customer ID and name required")

with tabs[4]:
    if is_comp or is_admin:
        st.markdown("**Bulk renewal processing:**")
        if expiring:
            if st.button(f"✅ Renew all {len(expiring)} expiring consents",key="bulk_renew",type="primary"):
                all_r = _load(); cnt=0
                for r2 in all_r:
                    if r2.get("status")=="Active" and r2.get("expiry_date","")<=str(today+timedelta(days=cfg["renewal_notice_days"])):
                        type_dur2 = next((c["duration_days"] for c in cfg["consent_types"] if c["id"]==r2.get("consent_type")),365)
                        r2["expiry_date"]=str(date.fromisoformat(r2["expiry_date"])+timedelta(days=type_dur2))
                        r2["renewed"]=True; r2["renewed_by"]=uname; cnt+=1
                _save(all_r)
                audit_log("CONSENT_BULK_RENEWED",uname,f"{cnt} consents renewed")
                _bsc_trigger(uname,"K059")
                st.success(f"✅ {cnt} consents renewed"); st.rerun()
    else: st.info("Bulk actions for Compliance team.")

with tabs[5]:
    if is_admin or is_comp:
        st.markdown("**Consent types — admin configurable:**")
        for ct in cfg["consent_types"]:
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{ct['name']}**")
            c2.markdown(f"Duration: {ct['duration_days']} days")
            ct["active"] = c3.checkbox("Active",value=ct.get("active",True),key=f"ct_{ct['id']}")
        new_notice = st.number_input("Renewal notice (days)",7,180,cfg.get("renewal_notice_days",30),key="con_notice")
        if st.button("💾 Save config",key="con_cfg_save",type="primary"):
            cfg["renewal_notice_days"]=new_notice
            (DATA/"consent_config.json").write_text(json.dumps(cfg,indent=2))
            st.cache_data.clear(); audit_log("CONSENT_CFG_SAVED",uname,"")
            st.success("✅ Saved"); st.rerun()
    else: st.info("Config for Compliance management.")

with tabs[6]:
    st.markdown("**Consent Management BSC KPIs:**")
    st.metric("K058 — Coverage Rate",f"{coverage:.1f}%",delta="Target ≥95%",delta_color="normal" if coverage>=95 else "inverse")
    renewals_done = sum(1 for r in records if r.get("renewed") and r.get("renewed_by")==uname)
    st.metric("K059 — Renewals Processed (you)",renewals_done,delta="Target 50")
    if st.button("🔄 Refresh BSC",key="con_bsc_ref"): _bsc_trigger(uname,"consent"); st.success("✅"); st.rerun()
