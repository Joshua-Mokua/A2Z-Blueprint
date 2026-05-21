"""pages/63_assets.py — Asset Management Register.
Fixed asset lifecycle: acquisition, tracking, depreciation, disposal.
Co-owned: Procurement records assets; Finance handles depreciation/disposal.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("operations.asset_register")

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
is_proc  = any(x in role for x in ("procurement","facilities","head of procurement"))
is_fin   = any(x in role for x in ("financial","cfo","finance","controller"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏢 Asset Register</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Fixed assets · Depreciation · Condition · Disposal · NBV tracking</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA / "asset_register.json"
    return a2z_db.load_json(p) if p.exists() else []

assets = _load()
total_cost = sum(a.get("purchase_cost_kes",0) for a in assets)
total_nbv  = sum(a.get("net_book_value_kes",0) for a in assets)
total_dep  = sum(a.get("accumulated_dep_kes",0) for a in assets)
poor       = [a for a in assets if a.get("condition") in ("Poor","Under Maintenance")]
warranty   = [a for a in assets if a.get("warranty_expiry","") < str(today) and not a.get("disposal_date")]

if poor:
    st.warning(f"⚠️ {len(poor)} asset(s) in Poor condition or under maintenance — review required")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Assets",      len(assets))
m2.metric("Total Cost",        f"KES {total_cost/1e6:.1f}M")
m3.metric("Net Book Value",    f"KES {total_nbv/1e6:.1f}M")
m4.metric("Accumulated Dep.",  f"KES {total_dep/1e6:.1f}M")
m5.metric("Warranty Expired",  len(warranty))

tabs = st.tabs(["📋 Asset Register","⚠️ Alerts","📊 Depreciation","🏷️ By Location","➕ Add Asset","🗑️ Dispose"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    fcat  = f1.selectbox("Category",["All"]+sorted(set(a.get("category","") for a in assets)),key="ast_cat")
    floc  = f2.selectbox("Location",["All"]+sorted(set(a.get("location","") for a in assets)),key="ast_loc")
    fcond = f3.selectbox("Condition",["All","Good","Fair","Poor","Under Maintenance"],key="ast_cond")
    vis   = [a for a in assets
             if (fcat=="All" or a.get("category")==fcat)
             and (floc=="All" or a.get("location")==floc)
             and (fcond=="All" or a.get("condition")==fcond)
             and not a.get("disposal_date")]
    rows  = [{"ID":a["id"],"Name":a["name"][:30],"Category":a["category"][:15],
               "Location":a["location"][:18],"Dept":a.get("assigned_to_dept","")[:15],
               "Cost (KES)":f"{a['purchase_cost_kes']:,.0f}",
               "NBV (KES)":f"{a['net_book_value_kes']:,.0f}",
               "Condition":a["condition"],"Purchased":a["purchase_date"][:10],
               "Warranty":("⚠️ Expired" if a.get("warranty_expiry","")< str(today) else "✅ Valid")}
              for a in sorted(vis, key=lambda x: -x.get("purchase_cost_kes",0))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Showing {len(vis)} active assets")

with tabs[1]:
    st.markdown(f"**{len(poor)} asset(s) requiring attention:**")
    if poor:
        p_rows = [{"ID":a["id"],"Name":a["name"][:30],"Condition":a["condition"],
                    "Location":a["location"][:18],"Last Inspection":a.get("last_inspection","")[:10],
                    "NBV (KES)":f"{a['net_book_value_kes']:,.0f}"}
                   for a in poor]
        st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
    st.markdown(f"**{len(warranty)} asset(s) with expired warranty:**")
    if warranty:
        w_rows = [{"ID":a["id"],"Name":a["name"][:30],"Warranty Expired":a.get("warranty_expiry","")[:10],
                    "Location":a["location"][:18],"Condition":a["condition"]}
                   for a in warranty[:10]]
        st.dataframe(pd.DataFrame(w_rows), use_container_width=True, hide_index=True)

with tabs[2]:
    st.markdown("**Depreciation summary by category (KES):**")
    dep_by_cat = {}
    for a in assets:
        cat = a.get("category","Other")
        if cat not in dep_by_cat: dep_by_cat[cat] = {"cost":0,"dep":0,"nbv":0}
        dep_by_cat[cat]["cost"] += a.get("purchase_cost_kes",0)
        dep_by_cat[cat]["dep"]  += a.get("accumulated_dep_kes",0)
        dep_by_cat[cat]["nbv"]  += a.get("net_book_value_kes",0)
    dep_rows = [{"Category":cat,"Cost (KES M)":round(v["cost"]/1e6,2),
                  "Accumulated Dep (M)":round(v["dep"]/1e6,2),
                  "NBV (KES M)":round(v["nbv"]/1e6,2),
                  "Dep %":f"{v['dep']/max(v['cost'],1)*100:.0f}%"}
                 for cat,v in sorted(dep_by_cat.items(),key=lambda x:-x[1]["cost"])]
    st.dataframe(pd.DataFrame(dep_rows), use_container_width=True, hide_index=True)
    st.line_chart(pd.DataFrame({"NBV (M)":[r["NBV (KES M)"] for r in dep_rows]},
                                index=[r["Category"][:15] for r in dep_rows]))

with tabs[3]:
    loc_data = {}
    for a in assets:
        loc = a.get("location","Other")
        if loc not in loc_data: loc_data[loc] = {"count":0,"nbv":0}
        loc_data[loc]["count"] += 1
        loc_data[loc]["nbv"]   += a.get("net_book_value_kes",0)
    loc_rows = [{"Location":loc,"Assets":v["count"],"Total NBV (KES M)":round(v["nbv"]/1e6,2)}
                 for loc,v in sorted(loc_data.items(),key=lambda x:-x[1]["nbv"])]
    st.dataframe(pd.DataFrame(loc_rows), use_container_width=True, hide_index=True)

with tabs[4]:
    if is_proc or is_admin:
        CATS = ["IT Equipment","Furniture","Vehicle","Office Equipment","Network Infrastructure",
                "Security Equipment","Cleaning Equipment","Air Conditioning","Generator","Other"]
        LOCS = ["Head Office","Westlands Branch","Karen Branch","Mombasa Branch",
                "Kisumu Branch","Nakuru Branch","CBD Branch"]
        from utils.core import get_org_config as _goc2
        _depts2 = [d["name"] for d in _goc2().get("departments",[]) if d.get("active",True)]
        r1,r2,r3 = st.columns(3)
        _name = st.text_input("Asset name *",key="ast_name")
        _acat = r1.selectbox("Category",CATS,key="ast_acat")
        _aloc = r2.selectbox("Location",LOCS,key="ast_aloc")
        _adpt = r3.selectbox("Assigned to department",_depts2,key="ast_adpt")
        _cost = st.number_input("Purchase cost (KES)",1_000.0,50_000_000.0,100_000.0,key="ast_cost")
        _life = st.selectbox("Useful life (years)",[3,5,7,10],key="ast_life")
        _pdate= st.date_input("Purchase date",key="ast_pdate")
        _sn   = st.text_input("Serial number",key="ast_sn")
        _ven  = st.text_input("Vendor",key="ast_ven")
        if st.button("➕ Add asset",key="ast_add",type="primary"):
            if _name.strip():
                all_a = json.loads((DATA/"asset_register.json").read_text())
                dep_rate = 1.0 / _life
                yrs = (today - _pdate).days / 365
                accum = min(1.0, yrs * dep_rate) * _cost
                all_a.append({
                    "id":f"AST{len(all_a)+1:05d}","name":_name.strip(),"category":_acat,
                    "serial_number":_sn,"location":_aloc,"assigned_to_dept":_adpt,
                    "purchase_date":str(_pdate),"purchase_cost_kes":_cost,"vendor":_ven,
                    "useful_life_years":_life,"depreciation_rate_pct":round(dep_rate*100,1),
                    "accumulated_dep_kes":round(accum,0),"net_book_value_kes":round(max(0,_cost-accum),0),
                    "condition":"Good","warranty_expiry":"","last_inspection":str(today),
                    "next_inspection":"","insurance_policy":"","disposal_date":"","disposal_reason":"",
                    "barcode":f"BAR{len(all_a)+1:07d}","notes":"","make_model":"","custodian":uname
                })
                (DATA/"asset_register.json").write_text(json.dumps(all_a,indent=2))
                audit_log("ASSET_ADDED",uname,f"{_name}: KES {_cost:,.0f}")
                _bsc_trigger(uname, "K051")
                st.cache_data.clear(); st.success("✅ Asset added"); st.rerun()
    else: st.info("Asset addition available to Procurement team.")

with tabs[5]:
    if is_proc or is_fin or is_admin:
        active_assets = [a for a in assets if not a.get("disposal_date")]
        disp_sel = st.selectbox("Select asset to dispose",
                                 [f"{a['id']} — {a['name'][:40]}" for a in active_assets],
                                 key="ast_disp_sel")
        disp_reason = st.selectbox("Disposal reason",
                                    ["End of useful life","Damaged beyond repair","Stolen",
                                     "Sold","Donated","Obsolete","Trade-in"],
                                    key="ast_disp_rsn")
        disp_val = st.number_input("Disposal/Salvage value (KES)",0.0,key="ast_disp_val")
        if st.button("🗑️ Record disposal",key="ast_disp_btn",type="secondary"):
            disp_id = disp_sel.split(" — ")[0]
            all_a = json.loads((DATA/"asset_register.json").read_text())
            for a in all_a:
                if a["id"]==disp_id:
                    a["disposal_date"]=str(today); a["disposal_reason"]=disp_reason
                    a["notes"]=f"Disposed {today}: {disp_reason}, salvage KES {disp_val:,.0f}"
            (DATA/"asset_register.json").write_text(json.dumps(all_a,indent=2))
            audit_log("ASSET_DISPOSED",uname,f"{disp_id}: {disp_reason}")
            _bsc_trigger(uname, "K051")
            st.cache_data.clear(); st.success("✅ Disposal recorded"); st.rerun()
    else: st.info("Disposal recording available to Procurement and Finance teams.")
