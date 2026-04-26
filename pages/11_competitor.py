"""pages/11_competitor.py — Competitor Intelligence.
Kenya banking market: rates, market share, KPIs vs peers. CBK data.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log
import requests, re

require_access("competitor")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔍 Competitor Intelligence</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Kenya banking market · Peer rates · Market share · KPI benchmarking</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=300, show_spinner=False)
def _load():
    p = DATA / "competitor_data.json"
    return json.loads(p.read_text()) if p.exists() else {}

data = _load()
if not data:
    st.info("Competitor data not available."); st.stop()

banks = data.get("banks",{}); rates_dep = data.get("deposit_rates",{})
rates_lend = data.get("lending_rates",{}); mkt_share = data.get("market_share",{})
OUR_BANK = "Ecobank"

tabs = st.tabs(["📊 Market Overview","💱 Rate Comparison","🏆 KPI Benchmarking","📈 Market Share","🤖 AI Market Brief"])

# ── TAB 1: Market Overview ─────────────────────────────────────────
with tabs[0]:
    st.markdown(f"**Kenya banking sector — {data.get('as_at',str(today))}**")
    st.markdown(f"CBK Rate: **{data.get('cbk_rate',13)}%**")
    
    bank_rows = [{"Bank":bdata.get("full_name", "")[:28],"Tier":bdata.get("tier", ""),
                   "Assets (B)":bdata.get("assets_kes_b", 0),"Loans (B)":bdata.get("loans_kes_b", 0),
                   "Deposits (B)":bdata.get("deposits_kes_b", 0),"NPL%":bdata.get("npl_pct", 0),
                   "CAR%":bdata["car_pct"],"NIM%":bdata.get("nim_pct", 0),"ROE%":bdata.get("roe_pct", 0),
                   "Branches":bdata["branches"]}
                  for bank, bdata in sorted(banks.items(), key=lambda x:-x[1]["assets_kes_b"])]
    df_banks = pd.DataFrame(bank_rows)
    
    # Highlight our bank
    def _highlight_ours(row):
        is_ours = OUR_BANK.lower() in row["Bank"].lower()
        return ["background-color: #E8F5EE; font-weight:bold" if is_ours else "" for _ in row]
    
    st.dataframe(df_banks.style.apply(_highlight_ours, axis=1), use_container_width=True, hide_index=True)
    
    our = banks.get(OUR_BANK,{})
    if our:
        st.markdown("---")
        st.markdown("**Our position vs Tier 1 average:**")
        t1_banks = [v for v in banks.values() if v["tier"]==1]
        t1_avg = lambda key: sum(b.get(key,0) for b in t1_banks)/max(len(t1_banks),1)
        comps = [("NPL%",our.get("npl_pct",0),t1_avg("npl_pct"),True),
                 ("NIM%",our.get("nim_pct",0),t1_avg("nim_pct"),False),
                 ("ROE%",our.get("roe_pct",0),t1_avg("roe_pct"),False),
                 ("CAR%",our.get("car_pct",0),t1_avg("car_pct"),False)]
        _oc = st.columns(4)
        for col,(metric,ours_v,t1_v,lower_better) in zip(_oc,comps):
            is_better = (ours_v < t1_v) if lower_better else (ours_v > t1_v)
            col.metric(f"Our {metric}", f"{ours_v}%", f"Peer avg: {t1_v:.1f}%",
                       delta_color="normal" if is_better else "inverse")

# ── TAB 2: Rate Comparison ─────────────────────────────────────────
with tabs[1]:
    r1,r2 = st.tabs(["📥 Deposit Rates","📤 Lending Rates"])
    with r1:
        st.markdown("**Deposit rates comparison (% p.a.):**")
        for tenor, rate_map in rates_dep.items():
            _dep_rows = [{"Bank":b,"Rate%":r,"vs Ours":f"{r-rate_map.get(OUR_BANK,0):+.2f}pp"}
                          for b,r in sorted(rate_map.items(), key=lambda x:-x[1])]
            our_rate = rate_map.get(OUR_BANK,0)
            better = sum(1 for b,r in rate_map.items() if b!=OUR_BANK and r<our_rate)
            icon = "🟢" if better >= len(rate_map)//2 else "🔴"
            st.markdown(f"**{tenor}:** {icon} We offer {our_rate}% — better than {better}/{len(rate_map)-1} peers")
        
        df_dep = pd.DataFrame({tenor: rate_map for tenor,rate_map in rates_dep.items()}).T
        st.dataframe(df_dep, use_container_width=True)
        
    with r2:
        st.markdown("**Lending rates comparison (% p.a.):**")
        df_lend = pd.DataFrame({prod: rate_map for prod,rate_map in rates_lend.items()}).T
        st.dataframe(df_lend, use_container_width=True)
        for prod, rate_map in rates_lend.items():
            our_r = rate_map.get(OUR_BANK,0)
            cheaper_than_us = [b for b,r in rate_map.items() if b!=OUR_BANK and r<our_r]
            if cheaper_than_us:
                st.warning(f"⚠️ **{prod}**: {cheaper_than_us} offer lower rates — review pricing")

# ── TAB 3: KPI Benchmarking ─────────────────────────────────────────
with tabs[2]:
    st.markdown("**KPI benchmarking vs peer group:**")
    our = banks.get(OUR_BANK,{})
    if our:
        kpi_rows = []
        for metric, label, lower_better in [
            ("npl_pct","NPL Ratio (%)",True), ("car_pct","Capital Adequacy (%)",False),
            ("nim_pct","Net Interest Margin (%)",False), ("roe_pct","Return on Equity (%)",False),
        ]:
            vals = {b:v.get(metric,0) for b,v in banks.items()}
            our_v = vals.get(OUR_BANK,0)
            rank  = sorted(vals.values(), reverse=not lower_better).index(our_v)+1
            best  = min(vals.values()) if lower_better else max(vals.values())
            worst = max(vals.values()) if lower_better else min(vals.values())
            status= "🟢 Top" if rank<=3 else "🟡 Mid" if rank<=6 else "🔴 Bottom"
            kpi_rows.append({"KPI":label,"Ecobank":our_v,"Industry Best":best,
                               "Industry Worst":worst,"Rank":f"#{rank} of {len(vals)}","Status":status})
        st.dataframe(pd.DataFrame(kpi_rows), use_container_width=True, hide_index=True)

# ── TAB 4: Market Share ─────────────────────────────────────────────
with tabs[3]:
    st.markdown("**Market share analysis:**")
    for mtype, label in [("total_assets_pct","Total Assets"),
                          ("total_deposits_pct","Total Deposits"),
                          ("digital_customers_pct","Digital Customers")]:
        share = mkt_share.get(mtype,{})
        our_s = share.get(OUR_BANK,0)
        st.markdown(f"**{label}:** Ecobank {our_s:.1f}% market share")
    
    share_data = mkt_share.get("total_assets_pct",{})
    df_share   = pd.DataFrame({"Bank":list(share_data.keys()),
                                 "Share%":list(share_data.values())}).sort_values("Share%",ascending=False)
    st.bar_chart(df_share.set_index("Bank")["Share%"])

# ── TAB 5: AI Market Brief ──────────────────────────────────────────
with tabs[4]:
    st.markdown("**AI-generated competitive intelligence brief:**")
    st.caption("Claude analyses our position vs peers and generates a strategic brief.")
    our = banks.get(OUR_BANK,{})
    if st.button("🤖 Generate competitive brief", key="ci_ai", type="primary"):
        audit_log("COMPETITOR_BRIEF_GENERATED", uname, "AI competitive brief")
        with st.spinner("Analysing competitive landscape…"):
            try:
                _context = (f"Ecobank Kenya: Assets KES {our.get('assets_kes_b',0)}B, "
                            f"NPL {our.get('npl_pct',0)}%, NIM {our.get('nim_pct',0)}%, "
                            f"ROE {our.get('roe_pct',0)}%, {our.get('branches',0)} branches. "
                            f"Market share assets: {mkt_share.get('total_assets_pct',{}).get(OUR_BANK,0):.1f}%. "
                            f"KCB leads with 23.1%, Equity 20.4%. "
                            f"Our 12M FD rate {rates_dep.get('12M Fixed',{}).get(OUR_BANK,0)}% — "
                            f"highest among peers.")
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json"},
                    json={"model":"claude-sonnet-4-20250514","max_tokens":600,
                          "system":"You are a banking strategy analyst covering Kenya. Write a concise, actionable competitive intelligence brief.",
                          "messages":[{"role":"user","content":
                              f"Write a 4-bullet competitive intelligence brief for Ecobank Kenya management: {_context}. "
                              "Focus on: 1) Key vulnerability, 2) Key opportunity, 3) Rate positioning, 4) Digital gap."}]},
                    timeout=30)
                resp.raise_for_status()
                st.markdown(resp.json()["content"][0]["text"])
            except Exception as e:
                st.error(f"Brief unavailable: {str(e)[:80]}")
