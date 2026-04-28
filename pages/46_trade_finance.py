"""pages/46_trade_finance.py — Trade Finance Tracker.
LC issuance, documentary collections, acceptance tracking, utilisation.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("trade_finance")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚢 Trade Finance</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "LC issuance · Documentary collections · Acceptance · Utilisation</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"trade_finance.json"
    return a2z_db.load_json(p) if p.exists() else []

lcs = _load()
active   = [l for l in lcs if l["status"] not in ("Settled","Expired","Cancelled")]
expiring = [l for l in active if l.get("expiry_date") and
            0<=(date.fromisoformat(l["expiry_date"][:10])-today).days<=cfg("lc_expiry_warning_days",14)]
total_usd = sum(l["amount"] for l in active)/1e6
discrepancies = sum(l.get("discrepancies",0) for l in lcs)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Active LCs",         len(active))
m2.metric("Total Value (USD M)", f"{total_usd:.1f}")
m3.metric("Expiring in 14d",    len(expiring), delta_color="normal" if not expiring else "inverse")
m4.metric("Discrepancies",      discrepancies, delta_color="normal" if not discrepancies else "inverse")
m5.metric("Commission (KES M)",  f"{sum(l['commission_earned'] for l in lcs)/1e6:.2f}")

if expiring:
    st.warning(f"⚠️ {len(expiring)} LC(s) expiring within 14 days — check with client on shipment")

tabs = st.tabs(["📋 LC Register","⏰ Expiring Soon","⚠️ Discrepancies","📊 Analytics","🏦 Correspondent Banks"])

def _render_lcs(lc_list, title=""):
    if not lc_list: st.success("None in this view."); return
    rows=[{"ID":l["id"],"Type":l["lc_type"],"Ccy":l["currency"],
            "Amount":f"{l['amount']:,.0f}","Equivalent (KES M)":round(l["kes_equivalent"]/1e6,2),
            "Status":l["status"],"Applicant":l["applicant"][:20],
            "Beneficiary":l["beneficiary"][:20],"Correspondent":l["correspondent"][:20],
            "Expiry":l["expiry_date"][:10],"Disc.":l.get("discrepancies",0),
            "Util%":l["utilised_pct"]}
           for l in sorted(lc_list,key=lambda x:x["expiry_date"])]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[0]:
    f1,f2 = st.columns(2)
    ftype = f1.multiselect("LC Type",["Import LC","Export LC","Standby LC","Transferable LC"],
                            default=["Import LC","Export LC"], key="tf_type")
    fstat = f2.multiselect("Status",list(set(l["status"] for l in lcs)),
                            default=["Issued","Advised","Negotiated","Accepted"], key="tf_stat")
    vis = [l for l in lcs if l["lc_type"] in ftype and l["status"] in fstat]
    st.markdown(f"**{len(vis)} LCs** · USD {sum(l['amount'] for l in vis)/1e6:.1f}M")
    _render_lcs(vis)

with tabs[1]:
    _render_lcs(expiring)
    if expiring:
        st.markdown("**Action:** Contact each applicant to confirm shipment/utilisation status or request extension.")

with tabs[2]:
    disc_lcs = [l for l in lcs if l.get("discrepancies",0)>0]
    if disc_lcs:
        st.warning(f"⚠️ {len(disc_lcs)} LCs with document discrepancies")
        _render_lcs(disc_lcs)
    else:
        st.success("✅ No document discrepancies outstanding.")

with tabs[3]:
    type_ct = Counter(l["lc_type"] for l in lcs)
    st.markdown("**LC volume by type:**")
    st.bar_chart(pd.DataFrame({"Count":dict(type_ct.most_common())}).T.T)
    st.markdown("**Top currencies:**")
    ccy_val = defaultdict(float)
    for l in lcs: ccy_val[l["currency"]] += l["amount"]
    for ccy,val in sorted(ccy_val.items(),key=lambda x:-x[1]):
        st.markdown(f"  {ccy}: {val/1e6:.1f}M")

with tabs[4]:
    corr_ct = Counter(l["correspondent"] for l in lcs)
    st.markdown("**Correspondent banks — LC volumes:**")
    cb_rows=[{"Correspondent":cb,"LC Count":n,"USD Value (M)":round(sum(l["amount"] for l in lcs if l["correspondent"]==cb)/1e6,1)}
              for cb,n in corr_ct.most_common()]
    st.dataframe(pd.DataFrame(cb_rows),use_container_width=True,hide_index=True)
