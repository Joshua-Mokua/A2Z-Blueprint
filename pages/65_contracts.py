"""pages/65_contracts.py — Contracts Register.
Vendor contracts lifecycle: active, expiring, renewals, SLA terms.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("contracts")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_proc  = any(x in role for x in ("procurement","head of procurement","company secretary","legal"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📄 Contracts Register</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Vendor contracts · Expiry alerts · Renewals · SLA terms · Value tracking</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA / "contracts.json"
    return a2z_db.load_json(p) if p.exists() else []

contracts = _load()
expiring  = [c for c in contracts if c.get("status")=="Expiring Soon"]
expired   = [c for c in contracts if c.get("status")=="Expired"]
active    = [c for c in contracts if c.get("status")=="Active"]
total_val = sum(c.get("value_kes",0) for c in active)

if expiring:
    st.warning(f"⚠️ {len(expiring)} contract(s) expiring within 90 days — initiate renewal")
if expired:
    st.error(f"🔴 {len(expired)} contract(s) EXPIRED — services may be operating without valid contract")

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Contracts",  len(contracts))
m2.metric("Active",           len(active))
m3.metric("Expiring <90d",    len(expiring), delta_color="normal" if not expiring else "inverse")
m4.metric("Total Value (Active)", f"KES {total_val/1e6:.1f}M")

tabs = st.tabs(["📋 All Contracts","⏰ Expiry Alerts","➕ New Contract","📊 Analytics"])

with tabs[0]:
    f1,f2 = st.columns(2)
    fstat = f1.selectbox("Status",["All","Active","Expiring Soon","Expired","Under Review"],key="con_st")
    fcat  = f2.selectbox("Category",["All"]+sorted(set(c.get("category","") for c in contracts)),key="con_cat")
    vis   = [c for c in contracts
             if (fstat=="All" or c.get("status")==fstat)
             and (fcat=="All" or c.get("category")==fcat)]
    rows  = [{"ID":c["id"],"Title":c["title"][:35],"Vendor":c["vendor"][:18],
               "Type":c.get("contract_type","")[:18],"Value (KES M)":round(c.get("value_kes",0)/1e6,2),
               "Start":c.get("start_date","")[:10],"End":c.get("end_date","")[:10],
               "Status":c.get("status",""),"Auto-Renew":"✅" if c.get("auto_renew") else "",
               "SLA":c.get("sla_terms","")[:20]}
              for c in sorted(vis, key=lambda x: x.get("end_date",""))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[1]:
    if expiring or expired:
        for c in sorted(expiring + expired, key=lambda x: x.get("end_date","")):
            days = (date.fromisoformat(c["end_date"]) - today).days
            icon = "🔴" if days < 0 else "🟡"
            msg  = f"EXPIRED {abs(days)}d ago" if days < 0 else f"Expires in {days} days"
            with st.expander(f"{icon} {c['title'][:50]} — {msg}"):
                st.markdown(f"**Vendor:** {c['vendor']}  |  **Value:** KES {c['value_kes']/1e6:.2f}M")
                st.markdown(f"**End date:** {c['end_date']}  |  **Auto-renew:** {'Yes' if c.get('auto_renew') else 'No'}")
                st.markdown(f"**Renewal notice:** {c.get('renewal_notice_days',30)} days  |  **SLA:** {c.get('sla_terms','')}")
                if is_proc or is_admin:
                    if st.button(f"📋 Initiate renewal",key=f"con_renew_{c['id']}",type="primary"):
                        all_c = json.loads((DATA/"contracts.json").read_text())
                        for c2 in all_c:
                            if c2["id"]==c["id"]: c2["status"]="Under Review"
                        (DATA/"contracts.json").write_text(json.dumps(all_c,indent=2))
                        audit_log("CONTRACT_RENEWAL_INITIATED",uname,c["id"])
                        _bsc_trigger(uname, "K039")
                        st.cache_data.clear(); st.success("✅ Renewal initiated"); st.rerun()
    else:
        st.success("✅ No contracts expiring or expired")

with tabs[2]:
    if is_proc or is_admin:
        CONTRACT_TYPES = ["Service Level Agreement","Annual Maintenance","Lease","Software License",
                          "Professional Services","Supply Agreement","Retainer","Framework Agreement"]
        CATS = ["IT Equipment","Office Supplies","Security Services","Utilities","Professional Services",
                "Travel & Accommodation","Maintenance & Repairs","Vehicle Fleet","Other"]
        VENDORS_LIST = [v["name"] for v in json.loads((DATA/"vendor_register.json").read_text())] if (DATA/"vendor_register.json").exists() else []
        from utils.core import get_org_config as _goc3
        _depts3 = [d["name"] for d in _goc3().get("departments",[]) if d.get("active",True)]
        r1,r2 = st.columns(2)
        _ctitle  = st.text_input("Contract title *",key="con_title")
        _cvend   = r1.selectbox("Vendor",VENDORS_LIST or ["Enter vendor name"],key="con_vend")
        _ctype   = r2.selectbox("Contract type",CONTRACT_TYPES,key="con_type")
        _ccat    = r1.selectbox("Category",CATS,key="con_cat_n")
        _cdept   = r2.selectbox("Department",_depts3,key="con_dept")
        _cval    = st.number_input("Contract value (KES)",1000.0,50_000_000.0,500_000.0,key="con_val")
        _cstart  = st.date_input("Start date",key="con_start")
        _cend    = st.date_input("End date",key="con_end")
        _cauto   = st.checkbox("Auto-renew",key="con_auto")
        _csla    = st.text_input("SLA terms (e.g. 4h response, 24h resolution)",key="con_sla")
        if st.button("💾 Save contract",key="con_save",type="primary"):
            if _ctitle.strip():
                all_c = json.loads((DATA/"contracts.json").read_text())
                end_dt = str(_cend)
                status = ("Expiring Soon" if (date.fromisoformat(end_dt)-today).days<=90
                          else "Active" if date.fromisoformat(end_dt)>=today else "Expired")
                all_c.append({
                    "id":f"CON{len(all_c)+1:04d}","title":_ctitle.strip(),"vendor":_cvend,
                    "category":_ccat,"contract_type":_ctype,"department":_cdept,
                    "value_kes":_cval,"start_date":str(_cstart),"end_date":end_dt,"status":status,
                    "auto_renew":_cauto,"renewal_notice_days":30,"signed_by":uname,
                    "contract_manager":uname,"document_ref":"","sla_terms":_csla,
                    "penalties":False,"notes":""
                })
                (DATA/"contracts.json").write_text(json.dumps(all_c,indent=2))
                audit_log("CONTRACT_ADDED",uname,f"{_ctitle}: KES {_cval:,.0f}")
                _bsc_trigger(uname, "K039")
                st.cache_data.clear(); st.success("✅ Contract saved"); st.rerun()
    else: st.info("Contract management available to Procurement and Legal teams.")

with tabs[3]:
    by_type = {}
    for c in active: by_type[c.get("contract_type","Other")] = by_type.get(c.get("contract_type","Other"),0) + c.get("value_kes",0)
    st.markdown("**Active contract value by type (KES M):**")
    st.bar_chart(pd.DataFrame({"KES M":{k:v/1e6 for k,v in by_type.items()}}))
