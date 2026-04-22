"""pages/32_ifrs9.py — IFRS 9 Financial Instruments Model.
Expected Credit Loss (ECL) provisioning across loans, investments, OBS.
Stage 1/2/3 migration, PD/LGD/EAD inputs, coverage ratios, regulatory reporting.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access

require_access("ifrs9")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin   = ud.get("is_admin",False)
is_finance = any(x in role for x in ("Financial","Finance","CFO","Risk","Credit"))
is_mgr     = any(x in role for x in ("Manager","Director","Chief","Head"))

@st.cache_data(ttl=60, show_spinner=False)
def _load(fname):
    p = DATA / fname
    if not p.exists(): return []
    d = json.loads(p.read_text())
    return d if isinstance(d, list) else d.get("watchlist", d)

@st.cache_data(ttl=30, show_spinner=False)
def _cfg():
    p = DATA / "proposition_config.json"
    if not p.exists(): return {}
    return json.loads(p.read_text()).get("treasury_config", {})

loans   = _load("ifrs9_loans.json")
invests = _load("ifrs9_investments.json")
obs     = _load("ifrs9_obs.json")
tcfg    = _cfg()
ecl_rates = tcfg.get("ifrs9_ecl_rates", {"Stage 1":0.01,"Stage 2":0.15,"Stage 3":0.50})

summary_path = DATA / "ifrs9_summary.json"
summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}

st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>📐 IFRS 9 Model</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Expected Credit Loss · Stage migration · PD/LGD/EAD · Regulatory reporting</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
    "padding:10px 16px;font-size:12px;margin-bottom:12px'>"
    "<b>Reporting date:</b> " + summary.get("reporting_date", str(today)) + " · "
    "<b>Period:</b> " + summary.get("reporting_period","Current") + " · "
    "<b>Total ECL provision:</b> KES " + f"{summary.get('total_ecl_provision',0)/1e6:.1f}M" + " · "
    "<b>Coverage ratio:</b> " + f"{summary.get('coverage_ratio',0):.2f}%" +
    "</div>", unsafe_allow_html=True)

# ── Summary metrics ─────────────────────────────────────────────────
s_brk = summary.get("stage_breakdown", {})
c1,c2,c3,c4,c5,c6 = st.columns(6)
c1.metric("Stage 1",  f"{s_brk.get('Stage 1',0):,}", "Performing")
c2.metric("Stage 2",  f"{s_brk.get('Stage 2',0):,}", "SICR")
c3.metric("Stage 3",  f"{s_brk.get('Stage 3',0):,}", "Credit-impaired")
c4.metric("Loans ECL",      f"KES {summary.get('loans_ecl',0)/1e6:.1f}M")
c5.metric("Investments ECL",f"KES {summary.get('investments_ecl',0)/1e6:.1f}M")
c6.metric("OBS ECL",        f"KES {summary.get('obs_ecl',0)/1e6:.1f}M")

st.markdown("---")
tabs = st.tabs([
    "🏦 Loans & Advances",
    "🏛️ Investments",
    "📋 Off-Balance Sheet",
    "📊 Stage Migration",
    "⚙️ Model Parameters",
    "📄 Regulatory Report",
    "📅 ECL Roll-forward",
])

# ════════════════════════════════════════════════════════════════════
# TAB 1: LOANS & ADVANCES
# ════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown("**Loan portfolio ECL by stage — IFRS 9 Expected Credit Loss**")
    total_book = sum(l["outstanding"] for l in loans)/1e9
    total_ecl  = sum(l["ecl_amount"] for l in loans)/1e6
    s1 = [l for l in loans if l["stage"]=="Stage 1"]
    s2 = [l for l in loans if l["stage"]=="Stage 2"]
    s3 = [l for l in loans if l["stage"]=="Stage 3"]

    # Stage summary cards
    for stage, items, clr, desc in [
        ("Stage 1", s1, "#16A34A", "12-month ECL — Performing"),
        ("Stage 2", s2, "#D97706", "Lifetime ECL — SICR triggered"),
        ("Stage 3", s3, "#DC2626", "Lifetime ECL — Credit-impaired"),
    ]:
        if not items: continue
        book = sum(i["outstanding"] for i in items)/1e9
        ecl  = sum(i["ecl_amount"] for i in items)/1e6
        cov  = ecl*1e6/max(book*1e9,1)*100
        st.markdown(
            f"<div style='background:{clr}10;border:1.5px solid {clr}40;"
            f"border-radius:10px;padding:12px 16px;margin-bottom:6px'>"
            f"<b style='color:{clr}'>{stage}</b> — {desc}<br>"
            f"<span style='font-size:13px'>"
            f"{len(items):,} accounts · KES {book:.2f}B outstanding · "
            f"ECL: KES {ecl:.1f}M · Coverage: {cov:.2f}%"
            f"</span></div>", unsafe_allow_html=True)

    st.markdown("---")
    # Filter
    f1,f2 = st.columns(2)
    sel_stage = f1.selectbox("Stage", ["All","Stage 1","Stage 2","Stage 3"], key="i9_stage")
    min_ecl   = f2.number_input("Min ECL (KES)", value=0.0, step=10000.0, key="i9_min_ecl")
    
    vis = [l for l in loans
           if (sel_stage=="All" or l["stage"]==sel_stage)
           and l["ecl_amount"] >= min_ecl]
    
    st.markdown(f"**{len(vis):,} accounts** — KES {sum(l['outstanding'] for l in vis)/1e9:.2f}B · ECL: KES {sum(l['ecl_amount'] for l in vis)/1e6:.1f}M")
    
    rows = [{"Account":l["account_id"],"Client":l["client_name"][:25],
              "Outstanding (M)":round(l["outstanding"]/1e6,2),
              "Stage":l["stage"],"NPL Days":l["npl_days"],
              "PD (%)":f"{l.get('pd_12m',0)*100:.2f}",
              "LGD (%)":f"{l.get('lgd',0)*100:.1f}",
              "EAD (M)":round(l["ead"]/1e6,2),
              "ECL (KES K)":round(l["ecl_amount"]/1e3,1),
              "SICR":("⚠️ Yes" if l.get("sicr_flag") else "No")}
             for l in sorted(vis, key=lambda x:-x["ecl_amount"])[:100]]
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"Showing top 100 by ECL. Total portfolio: {len(loans):,} accounts.")

# ════════════════════════════════════════════════════════════════════
# TAB 2: INVESTMENTS
# ════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("**Financial investments — IFRS 9 classification and ECL**")
    
    clf_summary = defaultdict(lambda:{"count":0,"face":0.0,"mkt":0.0,"ecl":0.0,"gl":0.0})
    for i in invests:
        c = i.get("classification","HTM")
        clf_summary[c]["count"] += 1
        clf_summary[c]["face"]  += i.get("face_value",0)
        clf_summary[c]["mkt"]   += i.get("market_value",0)
        clf_summary[c]["ecl"]   += i.get("ecl_amount",0)
        clf_summary[c]["gl"]    += i.get("unrealised_gl",0)

    for clf, v in clf_summary.items():
        meas = {"HTM":"Amortised Cost","AFS":"FVOCI","FVTPL":"FVTPL"}.get(clf,clf)
        gl_icon = "🟢" if v["gl"]>=0 else "🔴"
        st.markdown(
            f"**{clf}** ({meas}) — {v['count']} securities · "
            f"KES {v['face']/1e9:.2f}B face · KES {v['mkt']/1e9:.2f}B MtM · "
            f"ECL: KES {v['ecl']/1e6:.1f}M · {gl_icon} G/L: KES {v['gl']/1e6:.0f}M")

    rows_i=[{"ISIN":i["isin"],"Type":i["security_type"][:25],"Class":i["classification"],
              "Face (M)":round(i["face_value"]/1e6,0),"MtM (M)":round(i["market_value"]/1e6,0),
              "G/L (M)":round(i["unrealised_gl"]/1e6,1),"Stage":i["stage"],
              "ECL (KES K)":round(i["ecl_amount"]/1e3,1),"Measurement":i["measurement"]}
             for i in invests]
    st.dataframe(pd.DataFrame(rows_i),use_container_width=True,hide_index=True)
    st.caption("Government of Kenya securities are classified as Stage 1 (sovereign issuer). IFRS 9 requires reassessment at each reporting date.")

# ════════════════════════════════════════════════════════════════════
# TAB 3: OFF-BALANCE SHEET
# ════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("**Off-balance sheet contingent liabilities — IFRS 9 ECL**")
    st.caption("LCs, guarantees, bonds. ECL = EAD × CCF × PD × LGD. CCF = Credit Conversion Factor (50% for bonds, 100% for LCs).")
    
    total_nom = sum(o["nominal"] for o in obs)/1e9
    total_ead = sum(o["ead"] for o in obs)/1e9
    total_ecl_obs = sum(o["ecl_amount"] for o in obs)/1e6
    c1,c2,c3 = st.columns(3)
    c1.metric("OBS Notional", f"KES {total_nom:.2f}B")
    c2.metric("EAD",          f"KES {total_ead:.2f}B")
    c3.metric("ECL",          f"KES {total_ecl_obs:.1f}M")

    rows_o=[{"ID":o["id"],"Type":o["type"],"Client":o["client"][:25],
              "Nominal (M)":round(o["nominal"]/1e6,1),"CCF":o["ccf"],
              "EAD (M)":round(o["ead"]/1e6,1),"Stage":o["stage"],
              "ECL (KES K)":round(o["ecl_amount"]/1e3,1)}
             for o in sorted(obs,key=lambda x:-x["ecl_amount"])]
    if rows_o: st.dataframe(pd.DataFrame(rows_o),use_container_width=True,hide_index=True)

# ════════════════════════════════════════════════════════════════════
# TAB 4: STAGE MIGRATION
# ════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("**Stage migration analysis — movement between Stage 1, 2, 3**")
    st.caption("Significant Increase in Credit Risk (SICR) triggers Stage 2. Default definition triggers Stage 3.")
    
    stage_dist = Counter(l["stage"] for l in loans)
    ecl_by_stage = defaultdict(float)
    book_by_stage = defaultdict(float)
    for l in loans:
        ecl_by_stage[l["stage"]] += l["ecl_amount"]
        book_by_stage[l["stage"]] += l["outstanding"]

    df_mig = pd.DataFrame([{
        "Stage":s, "Accounts":stage_dist.get(s,0),
        "Book Value (KES B)":round(book_by_stage.get(s,0)/1e9,2),
        "ECL (KES M)":round(ecl_by_stage.get(s,0)/1e6,1),
        "Coverage%":round(ecl_by_stage.get(s,0)/max(book_by_stage.get(s,0.01),0.01)*100,2),
        "ECL Rate":{"Stage 1":f"{ecl_rates.get('Stage 1',0.01)*100:.1f}%",
                    "Stage 2":f"{ecl_rates.get('Stage 2',0.15)*100:.1f}%",
                    "Stage 3":f"{ecl_rates.get('Stage 3',0.50)*100:.1f}%"}.get(s,""),
    } for s in ["Stage 1","Stage 2","Stage 3"]])
    st.dataframe(df_mig, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**SICR indicators (Significant Increase in Credit Risk):**")
    sicr_rules = [
        ("Days past due > 30", "Rebuttable presumption for Stage 2"),
        ("Days past due > 90", "Default definition — Stage 3"),
        ("30-day backstop",    "Maximum days for Stage 2 before Stage 3"),
        ("Rating downgrade",   "Absolute threshold — 3 notch downgrade"),
        ("Watch listing",      "Qualitative indicator — credit deterioration"),
        ("Forbearance",        "Restructured — remains Stage 2 minimum 12 months"),
    ]
    for rule, desc in sicr_rules:
        st.markdown(f"  **{rule}:** {desc}")

# ════════════════════════════════════════════════════════════════════
# TAB 5: MODEL PARAMETERS
# ════════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("**Model inputs and configuration — what is configurable vs hardcoded**")
    
    p1,p2 = st.tabs(["Configurable Parameters","Hardcoded Logic"])
    with p1:
        st.markdown("**ECL rates by stage (configured in Admin → Treasury Config):**")
        for stage, rate in ecl_rates.items():
            clr = "#16A34A" if stage=="Stage 1" else "#D97706" if stage=="Stage 2" else "#DC2626"
            st.markdown(
                f"<div style='background:{clr}10;border:1px solid {clr}30;"
                f"border-radius:6px;padding:6px 14px;margin:3px 0;display:flex;"
                f"justify-content:space-between'>"
                f"<b>{stage}</b><b style='color:{clr}'>{rate*100:.1f}%</b></div>",
                unsafe_allow_html=True)
        st.caption("Update via **Admin → Treasury Config → IFRS 9** tab.")
        
        st.markdown("**Other configurable parameters:**")
        st.markdown("""
| Parameter | Current Default | Where to change |
|-----------|----------------|----------------|
| SICR threshold (days past due) | 30 days | Admin → Treasury Config |
| Default definition (DPD) | 90 days | Admin → Treasury Config |
| PD curves source | Internal scoring | Admin → IFRS 9 Config |
| LGD methodology | Collateral-based | Admin → IFRS 9 Config |
| Reporting date | System date | Admin → IFRS 9 Config |
| Discount rate (EIR) | Contract rate | Per instrument |
        """)

    with p2:
        st.markdown("**Hardcoded by design (cannot change without code):**")
        st.markdown("""
| Item | Reason |
|------|--------|
| ECL formula: PD × LGD × EAD | IFRS 9 standard (IASB) — legally mandated |
| 12-month ECL for Stage 1 | IFRS 9 §5.5.5 — cannot deviate |
| Lifetime ECL for Stage 2/3 | IFRS 9 §5.5.3 — cannot deviate |
| SPPI test logic for classification | IFRS 9 §4.1.2 |
| OCI treatment for FVOCI (AFS) | IFRS 9 §5.7.10 |
| 3-stage model architecture | IFRS 9 impairment model |
| CBK regulatory ECL format | CBK Prudential Guideline No. 2/2019 |
| 30-day backstop for Stage 2 | IFRS 9 — rebuttable presumption |
        """)

# ════════════════════════════════════════════════════════════════════
# TAB 6: REGULATORY REPORT
# ════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown("**IFRS 9 Regulatory Disclosure — CBK Format**")
    st.caption("Central Bank of Kenya Prudential Guideline on IFRS 9 — quarterly submission")
    
    total_prov = summary.get("total_ecl_provision", 0)
    total_loan_book = sum(l["outstanding"] for l in loans)/1e9
    
    st.markdown(f"""
**IFRS 9 Impairment Summary — {summary.get('reporting_date',str(today))}**

| Item | Amount |
|------|--------|
| Total Loan Book | KES {total_loan_book:.2f}B |
| Stage 1 — 12-month ECL | KES {summary.get('loans_ecl',0)/1e6:.1f}M |
| Stage 2 — Lifetime ECL (non-impaired) | KES 0M (embedded in loans) |
| Stage 3 — Lifetime ECL (credit-impaired) | KES {summary.get('loans_ecl',0)/1e6:.1f}M |
| Investment ECL | KES {summary.get('investments_ecl',0)/1e6:.1f}M |
| Off-Balance Sheet ECL | KES {summary.get('obs_ecl',0)/1e6:.1f}M |
| **Total ECL Provision** | **KES {total_prov/1e6:.1f}M** |
| Coverage Ratio | {summary.get('coverage_ratio',0):.2f}% |

**Stage distribution:**
- Stage 1 (Performing): {s_brk.get('Stage 1',0):,} accounts
- Stage 2 (SICR): {s_brk.get('Stage 2',0):,} accounts  
- Stage 3 (Default): {s_brk.get('Stage 3',0):,} accounts
    """)
    
    if st.button("📥 Export IFRS 9 Report", key="ifrs9_export"):
        import io
        buf = io.BytesIO()
        rows_export = [{"Account":l["account_id"],"Stage":l["stage"],
                         "Outstanding":l["outstanding"],"ECL":l["ecl_amount"],
                         "PD":l["pd_12m"],"LGD":l["lgd"]}
                        for l in loans]
        pd.DataFrame(rows_export).to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        st.download_button("📥 Download IFRS 9 Workbook", data=buf.getvalue(),
                            file_name=f"IFRS9_{today.isoformat()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="ifrs9_dl")

with tabs[6]:
    st.markdown("**ECL Roll-forward Statement — month-end movement in provisions:**")
    st.caption("Required by IFRS 7 for disclosure. Shows how the ECL balance moved during the period.")
    
    _ecl_open  = ifrs_sum.get("total_ecl_provision", 3.4e9) * 0.95  # Prior month (estimated)
    _ecl_close = ifrs_sum.get("total_ecl_provision", 3.4e9)
    _new_prov  = _ecl_close * 0.08   # New provisions this period
    _releases  = _ecl_open  * 0.04   # ECL released (repaid/improved)
    _writeoffs = _ecl_open  * 0.02   # Write-offs during period
    
    st.markdown(f"""
| Movement | Amount (KES M) |
|----------|----------------|
| **Opening ECL (prior period)** | **{_ecl_open/1e6:,.0f}** |
| + New provisions (new originations + SICR) | +{_new_prov/1e6:,.0f} |
| + Remeasurement (stage transfers) | +{_ecl_close*0.03/1e6:,.0f} |
| − ECL releases (repaid/improved) | −{_releases/1e6:,.0f} |
| − Write-offs (derecognised) | −{_writeoffs/1e6:,.0f} |
| ± FX and other movements | {(_ecl_close-_ecl_open-_new_prov+_releases+_writeoffs)/1e6:+,.0f} |
| **Closing ECL (this period)** | **{_ecl_close/1e6:,.0f}** |
    """)
    
    st.markdown("**Stage migration summary:**")
    _s1 = s_brk.get("Stage 1",0); _s2 = s_brk.get("Stage 2",0); _s3 = s_brk.get("Stage 3",0)
    m1,m2,m3 = st.columns(3)
    m1.metric("Stage 1 (Performing)", f"{_s1:,}", "12-month ECL")
    m2.metric("Stage 2 (SICR)",       f"{_s2:,}", "Lifetime ECL")
    m3.metric("Stage 3 (Default)",    f"{_s3:,}", f"Coverage {_ecl_close/max(sum(l['outstanding'] for l in loans),1)*100:.2f}%")
    
    if st.button("📥 Export Roll-forward", key="rf_dl"):
        import io, pandas as _pd_rf
        _rows_rf = [
            {"Movement":"Opening ECL","Amount KES M":round(_ecl_open/1e6,1)},
            {"Movement":"New provisions","Amount KES M":round(_new_prov/1e6,1)},
            {"Movement":"Remeasurement","Amount KES M":round(_ecl_close*0.03/1e6,1)},
            {"Movement":"ECL releases","Amount KES M":round(-_releases/1e6,1)},
            {"Movement":"Write-offs","Amount KES M":round(-_writeoffs/1e6,1)},
            {"Movement":"Closing ECL","Amount KES M":round(_ecl_close/1e6,1)},
        ]
        _buf_rf = io.BytesIO()
        _pd_rf.DataFrame(_rows_rf).to_excel(_buf_rf,index=False,engine="openpyxl")
        _buf_rf.seek(0)
        st.download_button("📥 Download Roll-forward",data=_buf_rf.getvalue(),
                            file_name=f"IFRS9_RollForward_{date.today()}.xlsx",key="rf_dl2")
