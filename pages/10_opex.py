"""pages/10_opex.py — Operating Leverage & P&L Intelligence.
CIR analysis, SBU profitability, branch P&L, staff productivity, trend analysis.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access

require_access("opex")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
is_exec  = any(x in role for x in ("Chief","Director","Managing","Head","CFO","Finance","Controller"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📉 Operating Leverage</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "CIR · SBU P&L · Branch profitability · Staff productivity</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60, show_spinner=False)
def _load():
    p = DATA / "opex_data.json"
    return json.loads(p.read_text()) if p.exists() else {}

opex = _load()
if not opex:
    st.info("Operating leverage data not available. Run data refresh from Admin."); st.stop()

bank  = opex.get("bank",{})
sbus  = opex.get("by_sbu",{})
brs   = opex.get("branches",[])

# ── Key metrics banner ───────────────────────────────────────────────
cir     = bank.get("cir_pct",0)
cir_tgt = bank.get("target_cir_pct",55)
cir_clr = "#16A34A" if cir<=cir_tgt else "#DC2626"

st.markdown(
    f"<div style='background:{cir_clr}10;border:1.5px solid {cir_clr}40;border-radius:10px;"
    f"padding:10px 18px;margin-bottom:10px;display:flex;gap:24px;flex-wrap:wrap'>"
    f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Cost-to-Income Ratio</div>"
    f"<div style='font-size:26px;font-weight:800;color:{cir_clr}'>{cir:.1f}%</div>"
    f"<div style='font-size:11px;color:{cir_clr}'>Target: {cir_tgt}%</div></div>"
    f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
    f"<div style='font-size:11px;color:var(--color-text-tertiary)'>Total Income</div>"
    f"<div style='font-size:20px;font-weight:700'>KES {bank.get('total_income_kes_b',0):.1f}B</div></div>"
    f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
    f"<div style='font-size:11px;color:var(--color-text-tertiary)'>Total OpEx</div>"
    f"<div style='font-size:20px;font-weight:700'>KES {bank.get('total_opex_kes_b',0):.1f}B</div></div>"
    f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
    f"<div style='font-size:11px;color:var(--color-text-tertiary)'>PBT</div>"
    f"<div style='font-size:20px;font-weight:700'>KES {bank.get('pbt_kes_b',0):.1f}B</div></div>"
    f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
    f"<div style='font-size:11px;color:var(--color-text-tertiary)'>ROE</div>"
    f"<div style='font-size:20px;font-weight:700'>{bank.get('roe_pct',0):.1f}%</div></div>"
    f"</div>", unsafe_allow_html=True)

tabs = st.tabs(["🏛️ Bank Summary","📊 SBU P&L","🏢 Branch P&L","👥 Staff Productivity","📐 OpEx Breakdown"])

# ── TAB 1: Bank Summary ─────────────────────────────────────────────
with tabs[0]:
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Interest Income",   f"KES {bank.get('interest_income_kes_b',0):.1f}B")
    c2.metric("Non-interest Income",f"KES {bank.get('non_interest_income_b',0):.1f}B")
    c3.metric("Staff Costs",       f"KES {bank.get('staff_costs_kes_b',0):.1f}B",
              f"{bank.get('staff_costs_kes_b',0)/max(bank.get('total_opex_kes_b',1),0.01)*100:.0f}% of opex")
    c4.metric("IT Costs",          f"KES {bank.get('it_costs_kes_b',0):.1f}B")
    c5.metric("PAT",               f"KES {bank.get('pat_kes_b',0):.1f}B",
              f"ROA {bank.get('roa_pct',0):.1f}%")
    
    st.markdown("---")
    st.markdown("**CIR target tracking:**")
    _gap = cir - cir_tgt
    st.markdown(
        f"Current CIR **{cir:.1f}%** vs target **{cir_tgt:.1f}%** — "
        f"{'🔴 Above target by ' + str(round(_gap,1)) + 'pp' if _gap>0 else '✅ Below target by ' + str(round(-_gap,1)) + 'pp'}. "
        f"To hit {cir_tgt}% target, need to reduce opex by "
        f"KES {max(0,(cir-cir_tgt)/100*bank.get('total_income_kes_b',13))*1e9/1e9:.2f}B "
        f"or grow income by KES {max(0,bank.get('total_opex_kes_b',8)/((cir_tgt/100))-bank.get('total_income_kes_b',13))*1e9/1e9:.2f}B.")

# ── TAB 2: SBU P&L ─────────────────────────────────────────────────
with tabs[1]:
    st.markdown("**P&L by Strategic Business Unit:**")
    sbu_rows = [{"SBU":sbu,"Income (B)":v.get("income_b", 0),"OpEx (B)":v.get("opex_b", 0),
                  "CIR%":v.get("cir", 0),"PBT (B)":v.get("pbt_b", 0),"Loans (B)":v.get("loans_b",0),
                  "Deposits (B)":v.get("deposits_b",0),"Staff":v.get("staff",0)}
                 for sbu,v in sbus.items()]
    df_sbu = pd.DataFrame(sbu_rows)
    st.dataframe(df_sbu, use_container_width=True, hide_index=True)
    
    # Highlight inefficient SBUs
    for sbu, v in sbus.items():
        if v.get("cir", 0) > 80:
            st.warning(f"⚠️ **{sbu}**: CIR {v['cir']:.0f}% — above 80% threshold. Review cost structure.")
        elif v.get("pbt_b",0) < 0:
            st.error(f"🔴 **{sbu}**: Loss-making (PBT KES {v['pbt_b']:.1f}B). Action required.")
    
    st.markdown("**SBU income vs opex:**")
    st.bar_chart(pd.DataFrame({"Income":df_sbu["Income (B)"].values,
                                "OpEx":  df_sbu["OpEx (B)"].values},
                               index=df_sbu["SBU"].values))

# ── TAB 3: Branch P&L ──────────────────────────────────────────────
with tabs[2]:
    st.markdown("**Branch profitability ranking:**")
    f1,f2 = st.columns(2)
    sort_by = f1.selectbox("Sort by", ["profit_m","cir_pct","income_m","deposits_m"], key="op_sort")
    top_n   = f2.slider("Show top N branches", 10, len(brs), min(25,len(brs)), key="op_n")
    
    br_rows = [{"Branch":b["branch"][:25],"Income (M)":b["income_m"],"OpEx (M)":b["opex_m"],
                 "Profit (M)":b["profit_m"],"CIR%":b["cir_pct"],
                 "Loans (M)":b["loans_m"],"Deposits (M)":b["deposits_m"],
                 "Staff":b["staff"],"Income/Staff (KES K)":b.get("income_per_staff",0)}
                for b in sorted(brs, key=lambda x:-x.get(sort_by,0))[:top_n]]
    st.dataframe(pd.DataFrame(br_rows), use_container_width=True, hide_index=True)
    
    # Loss-making branches
    loss_branches = [b for b in brs if b.get("profit_m",0) < 0]
    if loss_branches:
        st.error(f"🔴 {len(loss_branches)} loss-making branch(es): {[b['branch'][:15] for b in loss_branches[:5]]}")
    
    # CIR distribution
    cir_gt80 = sum(1 for b in brs if b.get("cir_pct",0)>80)
    if cir_gt80:
        st.warning(f"⚠️ {cir_gt80} branches with CIR >80%")

# ── TAB 4: Staff Productivity ───────────────────────────────────────
with tabs[3]:
    st.markdown("**Staff productivity analysis:**")
    total_staff = sum(b["staff"] for b in brs)
    total_inc   = sum(b["income_m"] for b in brs)
    avg_prod    = total_inc*1e6/max(total_staff,1)/1e3
    
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Branch Staff", f"{total_staff:,}")
    c2.metric("Avg Income/Staff",   f"KES {avg_prod:.0f}K")
    c3.metric("Target Income/Staff",f"KES 400K")
    c4.metric("Gap",                f"KES {400-avg_prod:.0f}K",
              delta_color="normal" if avg_prod>=400 else "inverse")
    
    # Top 10 by productivity
    prod_rows = sorted([{"Branch":b["branch"][:25],
                          "Staff":b["staff"],"Income (M)":b["income_m"],
                          "Income/Staff (KES K)":b.get("income_per_staff",0)}
                         for b in brs], key=lambda x:-x["Income/Staff (KES K)"])[:10]
    st.markdown("**Top 10 branches by staff productivity:**")
    st.dataframe(pd.DataFrame(prod_rows), use_container_width=True, hide_index=True)

# ── TAB 5: OpEx Breakdown ───────────────────────────────────────────
with tabs[4]:
    st.markdown("**Bank-level operating cost breakdown:**")
    opex_items = {
        "Staff Costs":     bank.get("staff_costs_kes_b",3.2),
        "IT & Technology": bank.get("it_costs_kes_b",0.8),
        "Premises":        bank.get("premises_kes_b",0.6),
        "Other OpEx":      bank.get("other_opex_kes_b",3.3),
    }
    df_opex = pd.DataFrame([{"Category":k,"KES B":v,"% of total":round(v/max(bank.get('total_opex_kes_b',8),0.01)*100,1)}
                              for k,v in opex_items.items()])
    st.dataframe(df_opex, use_container_width=True, hide_index=True)
    st.bar_chart(pd.DataFrame({"KES B":list(opex_items.values())}, index=list(opex_items.keys())))
    
    st.markdown("**Cost reduction opportunities:**")
    opp = []
    if bank.get("cir_pct",0) > 55: opp.append(f"• CIR at {bank['cir_pct']:.1f}% — target 55%: need KES {(bank['cir_pct']-55)/100*bank.get('total_income_kes_b',13):.2f}B cost reduction")
    if bank.get("it_costs_kes_b",0)/bank.get("total_opex_kes_b",8) < 0.12: opp.append("• IT spend below 12% of opex — may need digital investment to reduce manual costs")
    for o in opp: st.markdown(o)
