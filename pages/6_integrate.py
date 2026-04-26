"""pages/6_integrate.py — MD & Executive Command Centre.
Real-time cross-module intelligence: P&L, credit, pipeline, treasury,
risk, people, digital — all in one board-ready view.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict
from datetime import date, timedelta
from pages._shared import load_shared_state
from pages._access import require_access

require_access("integrate")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
is_exec  = any(x in role for x in ("Chief","Director","Managing","Head","Risk","CFO","Finance"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔗 Integrate</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "MD command centre · Real-time cross-module · Board view</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30, show_spinner=False)
def _loads():
    def _j(f): 
        p=DATA/f; return a2z_db.load_json(p) if p.exists() else {}
    def _jl(f):
        p=DATA/f
        if not p.exists(): return []
        d=a2z_db.load_json(p)
        return d if isinstance(d,list) else d.get("watchlist",list(d.values())[:500])
    scores  = _j("feb_2026_staff_scores.json")
    apps    = _jl("loan_applications.json")
    pipe    = _jl("pipeline.json")
    fd      = _jl("treasury_fd.json")
    rms     = _jl("rms_reconciliations.json")
    legal   = _jl("legal_matters.json")
    comp    = _jl("compliance_cases.json")
    opex    = _j("opex_data.json")
    dr      = _jl("debt_recovery.json")
    alerts  = _jl("smart_alerts.json")
    ifrs    = _j("ifrs9_summary.json")
    targets = _jl("bank_targets.json")
    return scores,apps,pipe,fd,rms,legal,comp,opex,dr,alerts,ifrs,targets

scores,apps,pipe,fd_data,rms,legal,comp,opex,dr,alerts,ifrs,targets = _loads()

# ── Pre-compute all metrics ─────────────────────────────────────────
bank = opex.get("bank",{})
n_staff   = len(scores)
avg_bsc   = round(sum(s["final_score"] for s in scores.values())/max(n_staff,1),2) if scores else 0
bsc_above = sum(1 for s in scores.values() if s["final_score"]>=3.5)
bsc_below = sum(1 for s in scores.values() if s["final_score"]<2.5)

active_pipe = [d for d in pipe if d.get("stage") not in ("Closed Won","Closed Lost")]
pipe_val    = sum(float(d.get("amount",0)) for d in active_pipe)/1e9
won_val     = sum(float(d.get("amount",0)) for d in pipe if d["stage"]=="Closed Won")/1e9

pending_apps = len([a for a in apps if a["status"] in ("submitted","assigned","analysis")])
approved_nd  = len([a for a in apps if a["status"] in ("approved","credit_admin")])
disb_vol     = sum(a.get("amount",0) for a in apps if a["status"]=="disbursed")/1e9

fd_pending   = len([r for r in fd_data if r["status"]=="pending"])
fd_maturing7 = len([r for r in fd_data if r.get("maturity_date") and
                    r["status"] in ("approved","booked") and
                    0<=(date.fromisoformat(str(r.get("maturity_date","9999-12-31"))[:10])-today).days<=7])

rms_breaks  = len([r for r in rms if r["status"]!="Matched"])
rms_var_m   = sum(r.get("abs_variance",0) for r in rms if r["status"]!="Matched")/1e6

legal_open  = len([m for m in legal if m["status"] not in ("completed","on_hold")])
legal_breach= len([m for m in legal if m.get("sla_breached") and m["status"]!="completed"])

comp_crit   = len([c for c in comp if c["status"]=="open" and c.get("risk_level")=="Critical"])
comp_open   = len([c for c in comp if c["status"] in ("open","under_review")])

dr_total    = sum(c.get("outstanding",0) for c in dr)/1e9
dr_recovered= sum(c.get("amount_recovered",0) for c in dr)/1e6

ecl_prov    = ifrs.get("total_ecl_provision",3.4e9)/1e9

crit_alerts = [a for a in alerts if a.get("severity")=="critical"]
warn_alerts = [a for a in alerts if a.get("severity")=="warning"]

tabs = st.tabs([
    "🏛️ Executive Summary",
    "💼 Credit & Pipeline",
    "💹 Treasury & Markets",
    "⚖️ Risk & Compliance",
    "👥 People & HR",
    "🔔 Live Alerts",
])

# ── TAB 1: Executive Summary ────────────────────────────────────────
with tabs[0]:
    # Traffic light indicators
    def _tl(ok, warn=None):
        if ok: return "🟢"
        if warn is not None and warn: return "🟡"
        return "🔴"
    
    st.markdown("**Bank health dashboard — real-time:**")
    
    # Row 1 — Financial
    r1 = st.columns(5)
    r1[0].metric("PBT", f"KES {bank.get('pbt_kes_b',0):.1f}B", "YTD")
    r1[1].metric("CIR", f"{bank.get('cir_pct',0):.1f}%",
                 f"Target {bank.get('target_cir_pct',55):.0f}%",
                 delta_color="normal" if bank.get("cir_pct",99)<bank.get("target_cir_pct",55) else "inverse")
    r1[2].metric("ROE", f"{bank.get('roe_pct',0):.1f}%")
    r1[3].metric("Active Pipeline", f"KES {pipe_val:.1f}B", f"{len(active_pipe)} deals")
    r1[4].metric("Disbursed YTD", f"KES {disb_vol:.1f}B")
    
    # Row 2 — Credit quality
    r2 = st.columns(5)
    r2[0].metric("NPL Ratio", f"{bank.get('npl_pct',11.0) if hasattr(bank,'get') else 11.0:.1f}%")
    r2[1].metric("ECL Provision", f"KES {ecl_prov:.1f}B")
    r2[2].metric("Pending Apps", f"{pending_apps:,}", f"{approved_nd} approved/undisbursed")
    r2[3].metric("RMS Breaks", f"{rms_breaks:,}", f"KES {rms_var_m:.0f}M variance",
                 delta_color="normal" if rms_breaks<20 else "inverse")
    r2[4].metric("Critical Alerts", f"{len(crit_alerts):,}",
                 delta_color="normal" if not crit_alerts else "inverse")
    
    # Row 3 — People & Risk
    r3 = st.columns(5)
    r3[0].metric("BSC Avg Score", f"{avg_bsc:.2f}/5.0", f"{n_staff:,} staff")
    r3[1].metric("On Track (≥3.5)", f"{bsc_above:,}", f"{bsc_above/max(n_staff,1)*100:.0f}%")
    r3[2].metric("At Risk (<2.5)", f"{bsc_below:,}",
                 delta_color="normal" if bsc_below<20 else "inverse")
    r3[3].metric("Compliance Open", f"{comp_open:,}", f"{comp_crit} critical",
                 delta_color="normal" if comp_crit==0 else "inverse")
    r3[4].metric("Legal Breaches", f"{legal_breach:,}",
                 delta_color="normal" if legal_breach==0 else "inverse")
    
    st.markdown("---")
    
    # Status summary table
    statuses = [
        ("Financial Performance", bank.get("pbt_kes_b",0)>0, bank.get("pbt_kes_b",0)>0),
        ("Cost Efficiency (CIR)",  bank.get("cir_pct",99)<bank.get("target_cir_pct",55),
                                   bank.get("cir_pct",99)<65),
        ("Credit Pipeline",        pending_apps<100, pending_apps<200),
        ("Treasury / FDs",         fd_maturing7==0, fd_maturing7<=3),
        ("Reconciliation",         rms_breaks<20, rms_breaks<50),
        ("Compliance",             comp_crit==0, comp_open<20),
        ("Legal",                  legal_breach==0, legal_open<50),
        ("Debt Recovery",          True, True),
        ("BSC Scores",             avg_bsc>=3.5, avg_bsc>=3.0),
        ("Alerts",                 len(crit_alerts)==0, len(crit_alerts)<=3),
    ]
    st.markdown("**Area status summary:**")
    cols = st.columns(5)
    for i, (area, ok, warn_ok) in enumerate(statuses):
        cols[i%5].markdown(
            f"<div style='padding:4px 8px;margin:2px;border-radius:6px;"
            f"background:{'#DCFCE7' if ok else '#FEF9C3' if warn_ok else '#FEE2E2'}'>"
            f"{_tl(ok, warn_ok)} {area}</div>", unsafe_allow_html=True)

# ── TAB 2: Credit & Pipeline ────────────────────────────────────────
with tabs[1]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Credit queue:**")
        queue_data = {
            "Submitted":   len([a for a in apps if a["status"]=="submitted"]),
            "Analysis":    len([a for a in apps if a["status"] in ("assigned","analysis")]),
            "Credit Admin":len([a for a in apps if a["status"]=="credit_admin"]),
            "Approved":    len([a for a in apps if a["status"]=="approved"]),
            "Disbursed":   len([a for a in apps if a["status"]=="disbursed"]),
            "Declined":    len([a for a in apps if a["status"]=="declined"]),
        }
        for stage, n in queue_data.items():
            pct = n/max(len(apps),1)*100
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"padding:3px 6px;border-radius:4px;margin:2px;background:#F9FAFB'>"
                f"<span>{stage}</span><span style='font-weight:600'>{n:,} ({pct:.0f}%)</span></div>",
                unsafe_allow_html=True)
    with c2:
        st.markdown("**Pipeline by stage:**")
        stage_totals = defaultdict(float)
        for d in active_pipe:
            stage_totals[d.get("stage","?")] += float(d.get("amount",0))/1e6
        for stage, val_m in sorted(stage_totals.items(), key=lambda x:-x[1]):
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"padding:3px 6px;border-radius:4px;margin:2px;background:#F9FAFB'>"
                f"<span>{stage}</span><span style='font-weight:600'>KES {val_m:.0f}M</span></div>",
                unsafe_allow_html=True)
    
    # Top 10 deals
    st.markdown("**Top pipeline deals:**")
    top_deals = sorted(active_pipe, key=lambda x:-float(x.get("amount",0)))[:10]
    df_top = pd.DataFrame([{"Client":d.get("client_name","")[:22],"Product":d.get("product","")[:20],
                              "Amount (M)":round(float(d.get("amount",0))/1e6,1),
                              "Stage":d.get("stage",""),"Win%":f"{d.get('win_probability_ai',0)*100:.0f}%",
                              "RM":d.get("rm_name","")[:18]}
                             for d in top_deals])
    st.dataframe(df_top, use_container_width=True, hide_index=True)

# ── TAB 3: Treasury & Markets ───────────────────────────────────────
with tabs[2]:
    t1,t2,t3 = st.columns(3)
    fd_book = sum(r["amount"] for r in fd_data if r["status"] in ("approved","booked") and r["currency"]=="KES")/1e9
    fx_data = []
    try:
        fx_data = json.loads((DATA/"treasury_fx.json").read_text())
    except: pass
    fx_settled = [d for d in fx_data if d["status"] in ("Confirmed","Settled")]
    fx_vol = sum(d.get("kes_amount",0) for d in fx_settled)/1e9
    
    t1.metric("FD Book (KES)",  f"KES {fd_book:.1f}B")
    t2.metric("FD Pending Rat.",f"{fd_pending:,} FDs")
    t3.metric("FX Volume YTD",  f"KES {fx_vol:.1f}B")
    
    if fd_maturing7:
        st.error(f"🔴 **{fd_maturing7} FD(s) maturing within 7 days** — Treasury action required")
    
    # ALM summary
    try:
        alm = json.loads((DATA/"treasury_alm.json").read_text())
        liq = alm.get("liquidity_ratios",{})
        lcr  = liq.get("lcr",{}).get("value",0)
        nsfr = liq.get("nsfr",{}).get("value",0)
        a1,a2,a3,a4 = st.columns(4)
        a1.metric("LCR",  f"{lcr:.1f}%", "Min 100%",   delta_color="normal" if lcr>=100 else "inverse")
        a2.metric("NSFR", f"{nsfr:.1f}%","Min 100%",   delta_color="normal" if nsfr>=100 else "inverse")
        a3.metric("NIM",  f"{bank.get('nim_pct',7.8):.1f}%")
        a4.metric("Loan/Deposit",f"{liq.get('loan_to_deposit',{}).get('value',78):.1f}%")
    except: pass

# ── TAB 4: Risk & Compliance ────────────────────────────────────────
with tabs[3]:
    r1,r2 = st.columns(2)
    with r1:
        st.markdown("**Compliance status:**")
        comp_by_risk = defaultdict(int)
        for c in comp: comp_by_risk[c.get("risk_level","Low")] += 1 if c["status"]=="open" else 0
        for lvl in ["Critical","High","Medium","Low"]:
            n = comp_by_risk.get(lvl,0)
            clr = {"Critical":"#DC2626","High":"#D97706","Medium":"#3B82F6","Low":"#16A34A"}.get(lvl,"#6B7280")
            if n>0:
                st.markdown(
                    f"<div style='background:{clr}12;border-left:3px solid {clr};"
                    f"padding:4px 10px;margin:2px;border-radius:0 4px 4px 0'>"
                    f"<b style='color:{clr}'>{lvl}</b>: {n} open</div>", unsafe_allow_html=True)
        st.markdown(f"Total open compliance cases: **{comp_open}**")
    
    with r2:
        st.markdown("**Legal & recovery:**")
        st.metric("Open legal matters", legal_open)
        st.metric("SLA breaches",        legal_breach, delta_color="normal" if legal_breach==0 else "inverse")
        st.metric("NPL recovery book",   f"KES {dr_total:.1f}B")
        st.metric("Recovered YTD",       f"KES {dr_recovered:.0f}M")
    
    st.markdown("**IFRS 9 ECL snapshot:**")
    s_brk = ifrs.get("stage_breakdown",{})
    ei1,ei2,ei3,ei4 = st.columns(4)
    ei1.metric("Stage 1 (Performing)", f"{s_brk.get('Stage 1',0):,}")
    ei2.metric("Stage 2 (SICR)",       f"{s_brk.get('Stage 2',0):,}")
    ei3.metric("Stage 3 (Default)",    f"{s_brk.get('Stage 3',0):,}")
    ei4.metric("ECL Provision",        f"KES {ecl_prov:.1f}B")

# ── TAB 5: People ───────────────────────────────────────────────────
with tabs[4]:
    p1,p2,p3,p4 = st.columns(4)
    p1.metric("Total Staff",     f"{n_staff:,}")
    p2.metric("Avg BSC Score",   f"{avg_bsc:.2f}/5.0")
    p3.metric("Exceeds (≥3.5)",  f"{bsc_above:,}", f"{bsc_above/max(n_staff,1)*100:.0f}%")
    p4.metric("At Risk (<2.5)",  f"{bsc_below:,}",
              delta_color="normal" if bsc_below==0 else "inverse")
    
    # Role distribution
    role_dist = defaultdict(int)
    for s in scores.values():
        rl = s.get("role","").lower()
        if "manager" in rl: role_dist["Managers"]+=1
        elif "officer" in rl or "teller" in rl: role_dist["Officers"]+=1
        elif "analyst" in rl: role_dist["Analysts"]+=1
        elif "head" in rl or "director" in rl or "chief" in rl: role_dist["Executives"]+=1
        else: role_dist["Others"]+=1
    
    df_roles = pd.DataFrame([{"Role Group":k,"Count":v} for k,v in sorted(role_dist.items(),key=lambda x:-x[1])])
    st.dataframe(df_roles, use_container_width=True, hide_index=True)

# ── TAB 6: Live Alerts ──────────────────────────────────────────────
with tabs[5]:
    if crit_alerts:
        st.error(f"🔴 **{len(crit_alerts)} critical alerts**")
    all_alerts_disp = sorted(alerts, key=lambda x:{"critical":0,"warning":1,"info":2}.get(x.get("severity",""),3))
    for a in all_alerts_disp[:20]:
        sev   = a.get("severity","info")
        clr   = {"critical":"#DC2626","warning":"#D97706","info":"#3B82F6"}.get(sev,"#6B7280")
        st.markdown(
            f"<div style='border-left:3px solid {clr};padding:4px 10px;margin:3px;"
            f"background:{clr}08;border-radius:0 6px 6px 0'>"
            f"<span style='font-size:11px;font-weight:700;color:{clr}'>"
            f"{a.get('icon','•')} {a.get('title','')}</span>"
            f"<span style='font-size:10px;color:var(--color-text-tertiary);margin-left:8px'>"
            f"{a.get('message','')[:60]}</span></div>", unsafe_allow_html=True)
    if not all_alerts_disp:
        st.success("✅ No active alerts")
