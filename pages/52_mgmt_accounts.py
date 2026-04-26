"""pages/52_mgmt_accounts.py — Management Accounts Pack.
Monthly P&L, balance sheet, key ratios. Thresholds via org_config.
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
from utils.core import audit_log

require_access("mgmt_accounts")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_fin   = any(x in role for x in ("financial","cfo","finance","controller","chief financial"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>📑 Management Accounts</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Monthly P&L · Balance Sheet · Key Ratios · Trend</span></div>", unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"mgmt_accounts.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("Management accounts not available."); st.stop()

period = data.get("period","")
ratios = data.get("key_ratios",{})
inc    = data.get("income_statement",{})
bs     = data.get("balance_sheet",{})
cir_tgt= cfg("cir_target_pct", 55)

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("NIM",f"{ratios.get('nim_pct',0):.2f}%")
m2.metric("CIR",f"{ratios.get('cir_pct',0):.1f}%",f"Target {cir_tgt}%",
          delta_color="normal" if ratios.get("cir_pct",99)<=cir_tgt else "inverse")
m3.metric("ROA",f"{ratios.get('roa_pct',0):.2f}%")
m4.metric("ROE",f"{ratios.get('roe_pct',0):.1f}%")
m5.metric("CAR",f"{ratios.get('car_pct',0):.1f}%")
m6.metric("NPL",f"{ratios.get('npl_pct',0):.1f}%",
          delta_color="normal" if ratios.get("npl_pct",0)<=6 else "inverse")

tabs = st.tabs(["📊 P&L","🏦 Balance Sheet","📈 Trend","📐 Ratios","📥 Export"])

with tabs[0]:
    st.markdown(f"**Income Statement — {period}** (KES M)")
    PNL = [("Interest Income","interest_income"),("Interest Expense","interest_expense"),
           ("Net Interest Income","net_interest_income"),("Fee Income","fee_income"),
           ("Forex Income","forex_income"),("Total Income","total_income"),
           ("Operating Expenses","opex"),("Provisions","provisions"),("PBT","pbt")]
    rows=[]
    for label,key in PNL:
        d=inc.get(key,{})
        a,b,p=d.get("actual_m",0),d.get("budget_m",0),d.get("prior_m",0)
        rows.append({"Line item":label,"Actual (M)":a,"Budget (M)":b,"Prior (M)":p,
                     "Variance":round(a-b,1),"Var%":f"{(a-b)/max(abs(b),1)*100:+.1f}%"})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    st.markdown(f"**Balance Sheet — {period}** (KES B)")
    BS=[("Net Loans","loans_net_b"),("Investments","investments_b"),("Cash","cash_b"),
        ("Total Assets","total_assets_b"),("Customer Deposits","customer_deposits_b"),
        ("Borrowings","borrowings_b"),("Equity","equity_b")]
    bs_rows=[{"Item":l,"Current (B)":bs.get(k,{}).get("actual",0),
              "Prior (B)":bs.get(k,{}).get("prior",0),
              "Change":round(bs.get(k,{}).get("actual",0)-bs.get(k,{}).get("prior",0),2)}
             for l,k in BS]
    st.dataframe(pd.DataFrame(bs_rows),use_container_width=True,hide_index=True)

with tabs[2]:
    trend=data.get("monthly_trend",[])
    if trend:
        st.line_chart(pd.DataFrame({"NII":[t["nii_m"] for t in trend],
                                     "PBT":[t["pbt_m"] for t in trend]},
                                    index=[t["month"] for t in trend]))
        st.line_chart(pd.DataFrame({"CIR%":[round(t["cir"],1) for t in trend]},
                                    index=[t["month"] for t in trend]))

with tabs[3]:
    st.dataframe(pd.DataFrame([{"Ratio":k.replace("_pct"," (%)").replace("_"," ").title(),
                                 "Value":f"{v:.2f}"}
                                for k,v in ratios.items()]),
                 use_container_width=True,hide_index=True)

with tabs[4]:
    if is_fin or is_admin:
        import io
        rows2=[{"Line":l,"Actual_M":inc.get(k,{}).get("actual_m",0),
                "Budget_M":inc.get(k,{}).get("budget_m",0)}
               for l,k in PNL]
        buf=io.BytesIO()
        pd.DataFrame(rows2).to_excel(buf,index=False,engine="openpyxl"); buf.seek(0)
        st.download_button("📥 Download P&L",data=buf.getvalue(),
                           file_name=f"MgmtAccounts_{period}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="ma_dl")
    else: st.info("Export available to Finance team.")
