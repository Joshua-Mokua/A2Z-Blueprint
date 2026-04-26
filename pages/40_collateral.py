"""pages/40_collateral.py — Collateral Management System.
Register, valuation calendar, insurance expiry, LTV monitoring.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("collateral")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏠 Collateral Register</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Collateral register · Valuations · Insurance · LTV monitoring</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"collateral_register.json"
    return a2z_db.load_json(p) if p.exists() else []

coll = _load()

# Alerts
ins_lapsed  = [c for c in coll if c.get("status")=="Insurance Lapsed"]
val_due_30  = [c for c in coll if c.get("next_valuation") and 0<=(date.fromisoformat(c["next_valuation"][:10])-today).days<=cfg("collateral_valuation_warning_days",30)]
high_ltv    = [c for c in coll if c.get("ltv",0)>cfg("collateral_ltv_alert",90)]
total_val   = sum(c.get("market_value",0) for c in coll)/1e9

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Collateral",  f"KES {total_val:.1f}B")
m2.metric("Insurance Lapsed",  len(ins_lapsed), delta_color="normal" if not ins_lapsed else "inverse")
m3.metric("Valuations due 30d",len(val_due_30))
m4.metric("High LTV (>90%)",   len(high_ltv), delta_color="normal" if not high_ltv else "inverse")

if ins_lapsed:
    st.error(f"🔴 {len(ins_lapsed)} collateral items with lapsed insurance — action required")
if high_ltv:
    st.warning(f"⚠️ {len(high_ltv)} facilities with LTV above 90% — review collateral adequacy")

tabs = st.tabs(["📋 Register","⏰ Valuations Due","🛡️ Insurance","📊 Analytics"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    filt_type = f1.selectbox("Type",["All"]+sorted(set(c["collateral_type"] for c in coll)),key="col_type")
    filt_stat = f2.selectbox("Status",["All","Active","Pending Revaluation","Insurance Lapsed","Released"],key="col_stat")
    filt_ltv  = f3.slider("Max LTV%",50,200,200,key="col_ltv")
    vis = [c for c in coll
           if (filt_type=="All" or c["collateral_type"]==filt_type)
           and (filt_stat=="All" or c["status"]==filt_stat)
           and c.get("ltv",0)<=filt_ltv]
    rows=[{"ID":c["id"],"Account":c["account_number"][:18],"Type":c["collateral_type"],
            "Market Value (M)":round(c["market_value"]/1e6,2),"Outstanding (M)":round(c["loan_outstanding"]/1e6,2),
            "LTV%":c["ltv"],"Status":c["status"],"Valuer":c["valuer"][:15],
            "Next Valuation":c["next_valuation"][:10],"Insurance Expiry":c["insurance_expiry"][:10]}
           for c in sorted(vis,key=lambda x:-x.get("ltv",0))[:50]]
    if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(f"{len(vis)} records shown")

with tabs[1]:
    due = sorted(val_due_30, key=lambda x:x["next_valuation"])
    if due:
        st.warning(f"⚠️ {len(due)} valuations due within 30 days:")
        vrows=[{"ID":c["id"],"Account":c["account_number"][:18],"Type":c["collateral_type"],
                "Current Value (M)":round(c["market_value"]/1e6,2),"Valuer":c["valuer"],
                "Due":c["next_valuation"][:10],"RM":c["rm"][:18],"Branch":c["branch"][:20]}
               for c in due]
        st.dataframe(pd.DataFrame(vrows),use_container_width=True,hide_index=True)
    else:
        st.success("No valuations due in the next 30 days.")

with tabs[2]:
    ins = [c for c in coll if c.get("insurance_expiry")]
    ins_due_60 = [c for c in ins if 0<=(date.fromisoformat(c["insurance_expiry"][:10])-today).days<=60]
    st.markdown(f"**{len(ins_lapsed)} lapsed · {len(ins_due_60)} expiring within 60 days:**")
    irows=[{"ID":c["id"],"Account":c["account_number"][:18],"Type":c["collateral_type"],
             "Market Value (M)":round(c["market_value"]/1e6,2),"Expiry":c["insurance_expiry"][:10],
             "Status":c["status"],"RM":c["rm"][:18]}
            for c in sorted(ins_lapsed+ins_due_60,key=lambda x:x["insurance_expiry"])[:30]]
    if irows: st.dataframe(pd.DataFrame(irows),use_container_width=True,hide_index=True)

with tabs[3]:
    type_ct = Counter(c["collateral_type"] for c in coll)
    st.markdown("**Collateral composition:**")
    st.bar_chart(pd.DataFrame({"Count":dict(type_ct.most_common())}).T.T)
    st.markdown("**LTV distribution:**")
    import pandas as _pd_a
    ltv_bins={"<50%":0,"50-70%":0,"70-90%":0,"90-100%":0,">100%":0}
    for c in coll:
        ltv=c.get("ltv",0)
        if ltv<50: ltv_bins["<50%"]+=1
        elif ltv<70: ltv_bins["50-70%"]+=1
        elif ltv<90: ltv_bins["70-90%"]+=1
        elif ltv<=100: ltv_bins["90-100%"]+=1
        else: ltv_bins[">100%"]+=1
    st.bar_chart(_pd_a.DataFrame({"Cases":ltv_bins}))
