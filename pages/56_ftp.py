"""pages/56_ftp.py — Funds Transfer Pricing (FTP).
NIM attribution by product and SBU. FTP curve configurable via Admin.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("transfer_pricing")
DATA  = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_fin   = any(x in role for x in ("financial","cfo","treasury","chief financial","controller"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>💱 Transfer Pricing (FTP)</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "NIM attribution · Product spread · SBU contribution · FTP curve</span></div>",
            unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"transfer_pricing.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("FTP data not available."); st.stop()

base   = data.get("base_rate_pct",0)
ftp    = data.get("ftp_rates",{})
prods  = data.get("by_product",[])
sbus   = data.get("by_branch_sbu",[])
warn_  = cfg("ftp_spread_warning_pct", 0.5)

m1,m2,m3 = st.columns(3)
m1.metric("Base Rate (CBR)",    f"{base:.1f}%")
m2.metric("Products analysed",  len(prods))
m3.metric("NIM spread warning", f"<{warn_:.1f}%")

tabs = st.tabs(["📦 By Product","🏢 By SBU","📐 FTP Curve","💡 Insights"])

with tabs[0]:
    st.markdown("**FTP spread by product — positive spread = margin, negative = cross-subsidy:**")
    p_rows=[{"Product":p["product"],"Volume (B)":p["volume_b"],
              "Customer Rate %":p["avg_rate_pct"],"FTP Rate %":p["ftp_pct"],
              "Spread %":round(p["avg_rate_pct"]-p["ftp_pct"],2),
              "Duration (mths)":p["duration_months"],
              "Flag":("🔴 Negative spread" if p["avg_rate_pct"]<p["ftp_pct"] else
                      "🟡 Thin" if p["avg_rate_pct"]-p["ftp_pct"]<warn_ else "🟢 OK")}
             for p in sorted(prods,key=lambda x:x["avg_rate_pct"]-x["ftp_pct"])]
    st.dataframe(pd.DataFrame(p_rows),use_container_width=True,hide_index=True)
    neg = [p for p in prods if p["avg_rate_pct"]<p["ftp_pct"]]
    if neg:
        st.warning(f"⚠️ {len(neg)} product(s) with negative NIM spread — pricing review required: {[p['product'] for p in neg]}")

with tabs[1]:
    sbu_rows=[{"Unit":s["unit"],"Assets (B)":s["assets_b"],"Liabilities (B)":s["liabilities_b"],
                "FTP Income (M)":s["ftp_income_m"],"NIM Contribution (M)":s["nim_contribution_m"],
                "Status":("🟢" if s["nim_contribution_m"]>0 else "🔴")}
               for s in sorted(sbus,key=lambda x:-x.get("nim_contribution_m",0))]
    st.dataframe(pd.DataFrame(sbu_rows),use_container_width=True,hide_index=True)
    total_nim = sum(s.get("nim_contribution_m",0) for s in sbus)
    st.metric("Total NIM Contribution",f"KES {total_nim:.0f}M")

with tabs[2]:
    st.markdown("**FTP reference rates by tenor (configurable via Admin → Treasury Config):**")
    ftp_rows=[{"Tenor":k,"FTP Rate %":v} for k,v in ftp.items()]
    st.dataframe(pd.DataFrame(ftp_rows),use_container_width=True,hide_index=True)

with tabs[3]:
    st.markdown("**Key insights:**")
    neg_prods = [p["product"] for p in prods if p["avg_rate_pct"]<p["ftp_pct"]]
    top_sbu   = max(sbus,key=lambda x:x.get("nim_contribution_m",0)) if sbus else {}
    if neg_prods:
        st.error(f"🔴 Negative-spread products: {', '.join(neg_prods)} — pricing below cost of funds")
    if top_sbu:
        st.success(f"✅ Top NIM contributor: {top_sbu.get('unit','')} — KES {top_sbu.get('nim_contribution_m',0):.0f}M")
    st.caption("FTP allocates the cost of funding to each product/SBU. Positive spread = earning above cost. "
               "Negative spread = selling below cost of funds — requires ALCO review.")
