"""pages/35_stress_testing.py — Portfolio Stress Testing Engine.
Scenario-based stress testing: rate shocks, FX movements, credit crunch.
CBK ICAAP requirements. AI generates executive narrative.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access
import requests

require_access("stress_testing")
DATA = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
is_exec  = any(x in role for x in ("Chief","Director","Managing","Head","CFO","Risk","Treasury"))

@st.cache_data(ttl=60, show_spinner=False)
def _load(fname):
    p = DATA / fname
    return json.loads(p.read_text()) if p.exists() else {}

scenarios = _load("stress_scenarios.json")
ifrs_sum  = _load("ifrs9_summary.json")
alm       = _load("treasury_alm.json")

# Read bank baseline from MD actuals
try:
    import openpyxl
    act_file = sorted([f for f in DATA.glob('actuals_*.xlsx') if 'backup' not in f.name],reverse=True)[0]
    wb = openpyxl.load_workbook(str(act_file)); ws = wb.active
    hdr = [ws.cell(2,c).value for c in range(1,ws.max_column+1)]
    kpi_c=hdr.index('KPI')+1; ac_c=hdr.index('YTD_Actual')+1; sc2=hdr.index('Staff Code')+1
    MD_ACTUALS={}
    for row in ws.iter_rows(min_row=3,values_only=True):
        if not row[0] or str(row[sc2-1] or '')!='300001': continue
        MD_ACTUALS[str(row[kpi_c-1] or '')]=float(row[ac_c-1] or 0)
except: MD_ACTUALS={}

# Baseline figures
BASE_LOAN_BOOK   = MD_ACTUALS.get("Loan Book Growth", 2.6e12)
BASE_PBT         = MD_ACTUALS.get("PBT", 6.65e11)
BASE_NFI         = MD_ACTUALS.get("Total NFI", 1.33e11)
BASE_NPL         = MD_ACTUALS.get("NPL Ratio", 11.0)
BASE_ECL         = ifrs_sum.get("total_ecl_provision", 3.4e9)
BASE_LCR         = alm.get("liquidity_ratios",{}).get("lcr",{}).get("value",122.7)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔥 Stress Testing</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Portfolio stress scenarios · CBK ICAAP · Rate/FX/Credit shocks</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='background:#FFF7ED;border:1px solid #FED7AA;border-radius:8px;"
    "padding:8px 14px;font-size:12px;margin-bottom:10px'>"
    "Stress testing is required under CBK Prudential Guideline No. CB/PG/08 (ICAAP). "
    "These scenarios test the bank's capital adequacy under adverse conditions.</div>",
    unsafe_allow_html=True)

tabs = st.tabs(["📊 Scenario Runner","📈 Side-by-Side","🎛️ Custom Scenario","📄 ICAAP Report"])

# ── TAB 1: Scenario Runner ─────────────────────────────────────────
with tabs[0]:
    st.markdown("**Select scenario to stress-test:**")
    scenario_names = {k: v["name"] for k,v in scenarios.items()}
    sel_key = st.selectbox("Scenario", list(scenario_names.keys()),
                            format_func=lambda x: scenario_names[x], key="st_sel")
    sc = scenarios[sel_key]
    assump = sc.get("assumptions",{})
    impact = sc.get("impacts",{})

    # Show assumptions
    st.markdown(f"**{sc['name']}:** {sc['description']}")
    a1,a2,a3,a4 = st.columns(4)
    cbk_chg = assump.get("cbk_rate_change",0)
    a1.metric("CBK Rate Change",    f"{cbk_chg:+.0f}bps",  delta_color="normal" if cbk_chg<=0 else "inverse")
    a2.metric("GDP Growth",         f"{assump.get('gdp_growth',5):.1f}%")
    a3.metric("Inflation",          f"{assump.get('inflation',6):.1f}%")
    a4.metric("KES Depreciation",   f"{assump.get('shilling_depreciation',0):+.0f}%")

    st.markdown("---")

    # Compute stressed values
    npl_chg   = impact.get("npl_change",0)
    book_chg  = impact.get("loan_book_growth",0)/100
    nfi_chg   = impact.get("interest_income_change",0)/100
    ecl_chg   = impact.get("ecl_change",0)/100

    stressed_npl  = round(BASE_NPL + npl_chg, 2)
    stressed_book = round(BASE_LOAN_BOOK * (1 + book_chg) / 1e9, 1)
    stressed_pbt  = round(BASE_PBT * (1 + nfi_chg) / 1e9, 2)
    stressed_ecl  = round(BASE_ECL * (1 + ecl_chg) / 1e6, 0)
    stressed_lcr  = round(BASE_LCR - abs(npl_chg) * 3, 1) if npl_chg > 0 else round(BASE_LCR + 5, 1)

    st.markdown("**Stressed outcomes:**")
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Loan Book",    f"KES {stressed_book:.0f}B",
              f"{book_chg*100:+.0f}%", delta_color="normal" if book_chg>=0 else "inverse")
    m2.metric("NPL Ratio",    f"{stressed_npl:.1f}%",
              f"{npl_chg:+.1f}pp", delta_color="normal" if npl_chg<=0 else "inverse")
    m3.metric("PBT",          f"KES {stressed_pbt:.2f}B",
              f"{nfi_chg*100:+.0f}%", delta_color="normal" if nfi_chg>=0 else "inverse")
    m4.metric("ECL Provision",f"KES {stressed_ecl:,.0f}M",
              f"{ecl_chg*100:+.0f}%", delta_color="normal" if ecl_chg<=0 else "inverse")
    m5.metric("LCR",          f"{stressed_lcr:.1f}%",
              "Above 100%" if stressed_lcr>=100 else "BREACH",
              delta_color="normal" if stressed_lcr>=100 else "inverse")

    # AI narrative
    if st.button("🤖 Generate ICAAP narrative for this scenario", key="st_ai"):
        with st.spinner("Generating regulatory narrative…"):
            try:
                resp = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type":"application/json"},
                    json={
                        "model":"claude-sonnet-4-20250514",
                        "max_tokens":500,
                        "system":"You are a bank risk manager writing ICAAP stress test commentary for CBK submission. Be precise, regulatory in tone.",
                        "messages":[{"role":"user","content":
                            f"Scenario: {sc['name']}. {sc['description']}. "
                            f"Key impacts: NPL {BASE_NPL:.1f}%→{stressed_npl:.1f}%, "
                            f"Loan book change {book_chg*100:+.0f}%, "
                            f"ECL provision change {ecl_chg*100:+.0f}%, "
                            f"LCR {BASE_LCR:.1f}%→{stressed_lcr:.1f}%. "
                            f"Write a 3-paragraph ICAAP stress test commentary suitable for CBK submission."}]
                    }, timeout=30)
                resp.raise_for_status()
                st.markdown("**ICAAP Narrative:**")
                st.markdown(resp.json()["content"][0]["text"])
            except Exception as e:
                st.error(f"AI unavailable: {str(e)[:80]}")

# ── TAB 2: Side-by-Side ────────────────────────────────────────────
with tabs[1]:
    st.markdown("**All scenarios compared:**")
    rows = []
    for k, sc in scenarios.items():
        imp = sc.get("impacts",{}); ass = sc.get("assumptions",{})
        rows.append({
            "Scenario":          sc["name"],
            "CBK Chg (bps)":     f"{ass.get('cbk_rate_change',0):+.0f}",
            "NPL (pp chg)":      f"{imp.get('npl_change',0):+.1f}",
            "Loan Book":         f"{imp.get('loan_book_growth',0):+.0f}%",
            "PBT":               f"{imp.get('interest_income_change',0):+.0f}%",
            "ECL":               f"{imp.get('ecl_change',0):+.0f}%",
            "Stressed NPL":      f"{BASE_NPL+imp.get('npl_change',0):.1f}%",
            "Stressed LCR":      f"{max(BASE_LCR - abs(imp.get('npl_change',0))*3, 80):.0f}%",
            "Capital Impact":    "🔴 Severe" if imp.get("npl_change",0)>6 else
                                  "🟡 Moderate" if imp.get("npl_change",0)>2 else "🟢 Manageable"
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── TAB 3: Custom Scenario ─────────────────────────────────────────
with tabs[2]:
    st.markdown("**Build a custom stress scenario:**")
    cc1,cc2 = st.columns(2)
    c_name   = cc1.text_input("Scenario name", value="Custom Scenario 1", key="st_cname")
    c_cbk    = cc1.number_input("CBK rate change (bps)", value=0.0, step=25.0, key="st_cbk")
    c_gdp    = cc1.number_input("GDP growth (%)", value=5.0, step=0.5, key="st_gdp")
    c_npl    = cc2.number_input("NPL change (pp)", value=0.0, step=0.5, key="st_npl")
    c_kes    = cc2.number_input("KES depreciation (%)", value=0.0, step=1.0, key="st_kes")
    c_ecl    = cc2.number_input("ECL provision change (%)", value=0.0, step=5.0, key="st_ecl")

    if st.button("▶️ Run custom scenario", key="st_custom", type="primary"):
        s_npl  = round(BASE_NPL+c_npl,2)
        s_ecl  = round(BASE_ECL*(1+c_ecl/100)/1e6,0)
        s_lcr  = round(BASE_LCR-abs(c_npl)*3,1) if c_npl>0 else round(BASE_LCR+3,1)
        st.markdown("**Custom scenario results:**")
        r1,r2,r3,r4 = st.columns(4)
        r1.metric("Stressed NPL",  f"{s_npl:.1f}%",  f"{c_npl:+.1f}pp")
        r2.metric("Stressed ECL",  f"KES {s_ecl:,.0f}M", f"{c_ecl:+.0f}%")
        r3.metric("Stressed LCR",  f"{s_lcr:.1f}%", "OK" if s_lcr>=100 else "BREACH",
                  delta_color="normal" if s_lcr>=100 else "inverse")
        r4.metric("CBK Rate",      f"{13.0+c_cbk/100:.2f}%", f"{c_cbk:+.0f}bps")

# ── TAB 4: ICAAP Report ────────────────────────────────────────────
with tabs[3]:
    st.markdown("**ICAAP Stress Testing Summary Report**")
    st.caption("Central Bank of Kenya — ICAAP Stress Testing requirements per CBK/PG/08")
    st.markdown(f"""
**Report Date:** {today}  
**Bank:** Ecobank Kenya Limited  
**Reporting Period:** Annual 2025

---

**1. Baseline Capital Position**

| Metric | Value |
|--------|-------|
| NPL Ratio | {BASE_NPL:.1f}% |
| Total ECL Provision | KES {BASE_ECL/1e6:,.0f}M |
| LCR | {BASE_LCR:.1f}% |
| Loan Book | KES {BASE_LOAN_BOOK/1e9:,.0f}B |
| PBT | KES {BASE_PBT/1e9:,.2f}B |

---

**2. Scenarios Tested**
""")
    for k, sc in scenarios.items():
        imp = sc.get("impacts",{})
        severity = "Severe" if imp.get("npl_change",0)>6 else "Moderate" if imp.get("npl_change",0)>2 else "Mild"
        st.markdown(f"- **{sc['name']}** ({severity}): NPL {imp.get('npl_change',0):+.1f}pp, ECL {imp.get('ecl_change',0):+.0f}%")

    st.markdown("""
---
**3. Key Risk Indicators**

Scenarios that result in LCR below 100% or NPL above 15% trigger capital contingency plans.

**4. Management Actions**

Contingency buffer maintained per CBK ICAAP requirements. Capital enhancement strategies include retained earnings, Tier 2 subordinated debt, and portfolio deleveraging.
    """)
    if st.download_button("📥 Export ICAAP Report",
                           data=f"ICAAP Stress Testing Report — {today}".encode(),
                           file_name=f"ICAAP_StressTest_{today}.txt", key="st_dl"):
        st.success("Report downloaded")
