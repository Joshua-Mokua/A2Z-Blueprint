"""pages/64_vendors.py — Vendor Management Register.
Vendor onboarding, KRA compliance, performance ratings, contract linkage.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("vendor_management")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_proc  = any(x in role for x in ("procurement","head of procurement","facilities"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🤝 Vendor Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Vendor register · KRA compliance · Performance · Onboarding · Suspension</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA / "vendor_register.json"
    return json.loads(p.read_text()) if p.exists() else []

vendors = _load()
active     = [v for v in vendors if v.get("status")=="Active"]
non_kra    = [v for v in vendors if not v.get("tax_compliance")]
no_insur   = [v for v in vendors if not v.get("insurance_valid")]
suspended  = [v for v in vendors if v.get("status")=="Suspended"]

if non_kra:
    st.error(f"🔴 {len(non_kra)} vendor(s) with invalid KRA compliance — payments should be withheld")
if suspended:
    st.warning(f"⚠️ {len(suspended)} vendor(s) suspended — check before raising POs")

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Vendors",   len(vendors))
m2.metric("Active",          len(active))
m3.metric("KRA Non-Compliant",len(non_kra),delta_color="normal" if not non_kra else "inverse")
m4.metric("Suspended",       len(suspended))

tabs = st.tabs(["📋 Vendor List","⚠️ Compliance","📊 Performance","➕ Onboard Vendor"])

with tabs[0]:
    f1,f2 = st.columns(2)
    fstat = f1.selectbox("Status",["All","Active","Suspended","Under Review"],key="vnd_st")
    fcat  = f2.selectbox("Category",["All"]+sorted(set(v.get("category","") for v in vendors)),key="vnd_cat")
    vis   = [v for v in vendors
             if (fstat=="All" or v.get("status")==fstat)
             and (fcat=="All" or v.get("category")==fcat)]
    rows  = [{"ID":v["id"],"Vendor":v["name"][:25],"Category":v["category"][:18],
               "KRA":"✅" if v.get("tax_compliance") else "❌",
               "Insurance":"✅" if v.get("insurance_valid") else "❌",
               "Rating":v.get("rating",0),"Spend YTD (M)":v.get("total_spend_ytd_m",0),
               "Open POs":v.get("open_pos",0),"Status":v.get("status",""),
               "Last Review":v.get("last_reviewed","")[:10]}
              for v in sorted(vis, key=lambda x: -x.get("total_spend_ytd_m",0))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[1]:
    st.markdown("**KRA non-compliant vendors — payments must be withheld:**")
    if non_kra:
        nc_rows = [{"Vendor":v["name"],"Spend YTD (M)":v.get("total_spend_ytd_m",0),
                     "Last Review":v.get("last_reviewed","")[:10],"Status":v.get("status","")}
                    for v in non_kra]
        st.dataframe(pd.DataFrame(nc_rows), use_container_width=True, hide_index=True)
        st.caption("⚠️ Per KRA regulation, withholding tax must be applied and valid compliance certificates required before payment.")
    else:
        st.success("✅ All vendors KRA-compliant")

    st.markdown("**No insurance coverage:**")
    if no_insur:
        ni_rows = [{"Vendor":v["name"],"Category":v["category"],"Status":v.get("status","")}
                    for v in no_insur]
        st.dataframe(pd.DataFrame(ni_rows), use_container_width=True, hide_index=True)

with tabs[2]:
    top = sorted(vendors, key=lambda x: -x.get("total_spend_ytd_m",0))[:10]
    st.markdown("**Top 10 vendors by YTD spend:**")
    st.bar_chart(pd.DataFrame({"Spend YTD (M)":{v["name"]:v["total_spend_ytd_m"] for v in top}}))
    st.markdown("**Vendor performance ratings:**")
    rat_rows = [{"Vendor":v["name"][:25],"Rating":v.get("rating",0),
                  "Spend YTD (M)":v.get("total_spend_ytd_m",0),
                  "Category":v.get("category","")[:18]}
                 for v in sorted(vendors, key=lambda x: -x.get("rating",0))]
    st.dataframe(pd.DataFrame(rat_rows), use_container_width=True, hide_index=True)

with tabs[3]:
    if is_proc or is_admin:
        CATS = ["IT Equipment","Office Supplies","Cleaning & Sanitation","Furniture & Fittings",
                "Security Services","Utilities","Professional Services","Travel & Accommodation",
                "Printing & Stationery","Vehicle Fleet","Maintenance & Repairs","Other"]
        r1,r2 = st.columns(2)
        _vname = st.text_input("Vendor name *",key="vnd_name")
        _vcat  = r1.selectbox("Category",CATS,key="vnd_vcat")
        _vkra  = st.text_input("KRA PIN *",key="vnd_kra")
        _vreg  = r2.text_input("Business registration no. *",key="vnd_reg")
        _vcp   = st.text_input("Contact person",key="vnd_cp")
        _vph   = r1.text_input("Phone",key="vnd_ph")
        _vem   = r2.text_input("Email",key="vnd_em")
        _vkra_ok = st.checkbox("KRA compliance verified",key="vnd_kra_ok")
        _vins_ok = st.checkbox("Insurance verified",key="vnd_ins_ok")
        if st.button("✅ Onboard vendor",key="vnd_add",type="primary"):
            if _vname.strip() and _vkra.strip():
                all_v = json.loads((DATA/"vendor_register.json").read_text())
                all_v.append({
                    "id":f"VND{len(all_v)+1:04d}","name":_vname.strip(),"category":_vcat,
                    "kra_pin":_vkra.strip(),"registration_no":_vreg.strip(),"contact_person":_vcp,
                    "phone":_vph,"email":_vem,"address":"","status":"Active",
                    "onboarding_date":str(today),"last_reviewed":str(today),
                    "next_review":"","tax_compliance":_vkra_ok,"insurance_valid":_vins_ok,
                    "bank_details":{},"rating":3.0,"total_spend_ytd_m":0,"open_pos":0,"notes":""
                })
                (DATA/"vendor_register.json").write_text(json.dumps(all_v,indent=2))
                audit_log("VENDOR_ONBOARDED",uname,_vname.strip())
                st.cache_data.clear(); st.success(f"✅ {_vname} onboarded"); st.rerun()
            else: st.error("Vendor name and KRA PIN required.")
    else: st.info("Vendor onboarding available to Procurement team.")
