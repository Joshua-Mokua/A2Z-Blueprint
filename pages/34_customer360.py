"""pages/34_customer360.py — Customer 360 Intelligence.
Full customer view: products, propensity scores, churn risk,
next best action, relationship history, digital engagement.
"""
import streamlit as st
from utils.db import db as a2z_db
from utils.config import currency_symbol
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access
import requests, re

require_access("shared.customer_360")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

@st.cache_data(ttl=60, show_spinner=False)
def _load(fname):
    p = DATA / fname
    if not p.exists(): return {}
    d = a2z_db.load_json(p)
    return d

ci_raw   = _load("customer_intelligence.json")
apps_raw = _load("loan_applications.json")
pipe_raw = _load("pipeline.json")
edms_raw = _load("edms_documents.json")
legal_raw= _load("legal_matters.json")

apps  = apps_raw  if isinstance(apps_raw,  list) else []
pipeline = pipe_raw if isinstance(pipe_raw, list) else []
edms  = edms_raw  if isinstance(edms_raw,  list) else []
legal = legal_raw if isinstance(legal_raw, list) else []

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🎯 Customer 360</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Propensity · Churn risk · Next best action · Full relationship view</span></div>",
    unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────
# v7.8: Customer Value Composite (composite_scores.py surfacing)
# ─────────────────────────────────────────────────────────────────
with st.expander("📊 Customer Value Composite (v6.0 / v7.8 surfaced)", expanded=False):
    from utils.composite_scores import customer_value_composite

    st.caption(
        "v7.8 surfacing of `composite_scores.customer_value_composite()` on this "
        "domain page (per Charter §13). Composes RFM segment + CLV + customer "
        "value tier into a single 0-100 score with HEALTHY / MODERATE / LOW "
        "severity bands. Inputs below are illustrative; pick a customer in "
        "Tab 1 (Customer Lookup) for live values in production deployment."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Inputs (illustrative high-value customer):**")
        cv_rfm = st.selectbox("RFM segment",
            ["CHAMPIONS", "LOYAL", "POTENTIAL", "AT_RISK", "HIBERNATING", "LOST"],
            key="cv_health_rfm")
        cv_clv = st.number_input(f"CLV ({currency_symbol()})", 0, 10_000_000, 850_000,
                                  step=10_000, key="cv_health_clv")
        cv_tier = st.selectbox("Customer value tier",
            ["PLATINUM", "GOLD", "SILVER", "BRONZE", "STANDARD"],
            key="cv_health_tier")

    with c2:
        cv_result = customer_value_composite(
            rfm_segment=cv_rfm,
            clv_kes=float(cv_clv),
            customer_value_tier=cv_tier,
        )
        cv_score = cv_result.get("score")
        cv_severity = cv_result.get("severity")
        sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                     "LOW": "🚨", "UNKNOWN": "⚠"}.get(cv_severity, "")
        st.metric("Customer Value score",
                  f"{cv_score:.1f}/100" if cv_score is not None else "—",
                  cv_severity)
        st.markdown(f"**{sev_color} {cv_severity}**")

        if cv_result.get("components"):
            st.markdown("**Component scores:**")
            for k, v in cv_result["components"].items():
                st.markdown(f"- `{k}`: {v:.1f}")

tabs = st.tabs([
    "🔍 Customer Lookup",
    "📊 Portfolio Intelligence",
    "⚠️ Churn Risk",
    "💡 Next Best Action",
    "📈 Segment Analytics",
    "💰 Customer Lifetime Value",
    "📄 IFRS 7 / IAS 24 Disclosures",
])

# ── TAB 1: Customer Lookup ──────────────────────────────────────────
with tabs[0]:
    c1,c2 = st.columns([2,1])
    search_q = c1.text_input("Search by CIF, name, or account", key="c360_q",
                              placeholder="e.g. 100625608 or Grace Wanjiku…")
    sel_seg  = c2.selectbox("Filter by segment",
                             ["All","Premium","Affluent","Mass Affluent","Mass"], key="c360_seg")

    if search_q:
        matches = {}
        q = search_q.strip().lower()
        for cif, info in ci_raw.items():
            if (q in str(cif) or
                q in info.get("segment","").lower() or
                any(q in t.lower() for t in info.get("tags",[]))):
                matches[cif] = info
        if sel_seg != "All":
            matches = {k:v for k,v in matches.items() if v.get("segment")==sel_seg}

        st.markdown(f"**{len(matches)} matches**")
        if matches:
            sel_cif = st.selectbox("Select customer:", list(matches.keys())[:30], key="c360_sel")
            info    = matches.get(sel_cif,{})

            # Customer card
            segment = info.get("segment","Mass")
            seg_clr = {"Premium":"#7C3AED","Affluent":"#0891B2","Mass Affluent":"#16A34A","Mass":"#6B7280"}.get(segment,"#6B7280")
            churn   = info.get("churn_risk",0)
            churn_clr = "#DC2626" if churn>0.25 else "#D97706" if churn>0.15 else "#16A34A"

            st.markdown(
                f"<div style='background:var(--color-background-secondary);border-radius:12px;"
                f"padding:16px;margin:8px 0;border:1px solid var(--color-border)'>"
                f"<div style='display:flex;align-items:center;gap:16px;flex-wrap:wrap'>"
                f"<div style='background:{seg_clr};color:white;border-radius:50%;width:48px;height:48px;"
                f"display:flex;align-items:center;justify-content:center;font-size:20px'>👤</div>"
                f"<div style='flex:1'>"
                f"<div style='font-size:16px;font-weight:700'>CIF: {sel_cif}</div>"
                f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
                f"<span style='background:{seg_clr}20;color:{seg_clr};border-radius:10px;"
                f"padding:1px 8px'>{segment}</span> · "
                f"Tags: {', '.join(info.get('tags',[]))} · "
                f"Products held: {info.get('products_held',1)} · "
                f"CLV: {currency_symbol()} {info.get('clv_estimate',0)/1e3:.0f}K</div></div>"
                f"<div style='text-align:right'>"
                f"<div style='font-size:11px;color:var(--color-text-tertiary)'>Churn risk</div>"
                f"<div style='font-size:20px;font-weight:800;color:{churn_clr}'>{churn*100:.0f}%</div>"
                f"</div></div></div>", unsafe_allow_html=True)

            # Detail columns
            d1,d2,d3 = st.columns(3)
            d1.markdown("**Propensity scores:**")
            for prod, score in sorted(info.get("propensity_scores",{}).items(), key=lambda x:-x[1]):
                bar = "█"*int(score*10)
                d1.markdown(f"  {prod[:20]}: **{score*100:.0f}%** {bar}")

            d2.markdown("**Engagement:**")
            d2.metric("Digital", info.get("digital_engagement","—"))
            d2.metric("NPS Score", info.get("nps_score","—"))
            d2.metric("Complaints (12m)", info.get("complaints_12m",0))
            d2.metric("Last contact", f"{info.get('last_contact_days',0)}d ago")

            d3.markdown("**Next Best Action:**")
            nba = info.get("nba","—")
            nba_score = info.get("propensity_scores",{}).get(nba,0)
            d3.markdown(
                f"<div style='background:#EFF6FF;border:1.5px solid #3B82F6;"
                f"border-radius:8px;padding:10px;'>"
                f"<div style='font-size:14px;font-weight:700;color:#1D4ED8'>💡 {nba}</div>"
                f"<div style='font-size:12px;color:#6B7280'>{nba_score*100:.0f}% propensity</div>"
                f"</div>", unsafe_allow_html=True)

            # Related records
            cif_apps  = [a for a in apps if str(a.get("client_cif",""))==sel_cif]
            cif_pipe  = [d for d in pipeline if str(d.get("client_cif",""))==sel_cif]
            cif_docs  = [d for d in edms if str(d.get("client_cif",""))==sel_cif]
            cif_legal = [m for m in legal if str(m.get("client_cif",""))==sel_cif]

            if any([cif_apps, cif_pipe, cif_docs, cif_legal]):
                st.markdown("**Related records:**")
                r1,r2,r3,r4 = st.columns(4)
                r1.metric("Loan Applications", len(cif_apps))
                r2.metric("Pipeline Deals", len(cif_pipe))
                r3.metric("Documents", len(cif_docs))
                r4.metric("Legal Matters", len(cif_legal))

            # AI Relationship Summary
            if st.button("🤖 Generate AI relationship summary", key="c360_ai"):
                with st.spinner("Generating…"):
                    try:
                        resp = requests.post(
                            "https://api.anthropic.com/v1/messages",
                            headers={"Content-Type":"application/json"},
                            json={
                                "model":"claude-sonnet-4-20250514",
                                "max_tokens":400,
                                "system":"You are a bank relationship manager. Write a concise 3-sentence customer intelligence note for an RM brief.",
                                "messages":[{"role":"user","content":
                                    f"Customer profile: CIF {sel_cif}, Segment {segment}, "
                                    f"Products held {info.get('products_held',1)}, "
                                    f"Digital engagement {info.get('digital_engagement','Medium')}, "
                                    f"Churn risk {churn*100:.0f}%, NPS {info.get('nps_score',5)}/10, "
                                    f"Top propensity: {nba} ({nba_score*100:.0f}%), "
                                    f"CLV {currency_symbol()} {info.get('clv_estimate',0)/1e3:.0f}K. "
                                    f"Loan applications: {len(cif_apps)}, Pipeline deals: {len(cif_pipe)}."}]
                            }, timeout=20)
                        resp.raise_for_status()
                        st.markdown("**AI Relationship Brief:**")
                        st.info(resp.json()["content"][0]["text"])
                    except Exception as e:
                        st.error(f"AI brief unavailable: {str(e)[:80]}")
    else:
        st.info("Enter a CIF number or search term to view customer intelligence.")

# ── TAB 2: Portfolio Intelligence ──────────────────────────────────
with tabs[1]:
    st.markdown("**Portfolio-wide customer intelligence:**")
    segs = {"Premium":0,"Affluent":0,"Mass Affluent":0,"Mass":0}
    nba_counts = defaultdict(int)
    churn_high = churn_med = churn_low = 0
    total_clv = 0
    for info in ci_raw.values():
        segs[info.get("segment","Mass")] = segs.get(info.get("segment","Mass"),0)+1
        nba_counts[info.get("nba","—")] += 1
        cr = info.get("churn_risk",0)
        if cr > 0.25: churn_high+=1
        elif cr > 0.15: churn_med+=1
        else: churn_low+=1
        total_clv += info.get("clv_estimate",0)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total Customers", f"{len(ci_raw):,}")
    c2.metric("Total CLV (est.)",f"{currency_symbol()} {total_clv/1e9:.1f}B")
    c3.metric("High Churn Risk", f"{churn_high:,}", f"{churn_high/len(ci_raw)*100:.0f}%")
    c4.metric("Premium/Affluent",f"{segs['Premium']+segs['Affluent']:,}")

    st.markdown("**Segment distribution:**")
    df_seg = pd.DataFrame([{"Segment":s,"Count":n,"Share%":round(n/len(ci_raw)*100,1)}
                            for s,n in segs.items()])
    st.dataframe(df_seg, use_container_width=True, hide_index=True)

    st.markdown("**Next Best Action distribution:**")
    df_nba = pd.DataFrame([{"Product":p,"Customers":n} for p,n in sorted(nba_counts.items(),key=lambda x:-x[1])])
    st.bar_chart(df_nba.set_index("Product")["Customers"])

# ── TAB 3: Churn Risk ───────────────────────────────────────────────
with tabs[2]:
    _churn_sub_tabs = st.tabs([
        "📊 High-Risk List (existing)",
        "🎯 Churn Score Engine (Standard #58, v5.91)",
        "📋 Retention Priority (Standard #58, v5.91)",
        "🌳 Engine Reference (Standard #58, v5.91)",
    ])

    with _churn_sub_tabs[0]:
        st.markdown("**High churn risk customers — prioritise retention:**")
        high_risk = [(cif,info) for cif,info in ci_raw.items() if info.get("churn_risk",0)>0.25]
        high_risk.sort(key=lambda x:-x[1].get("churn_risk",0))

        c1,c2,c3 = st.columns(3)
        c1.metric("High Risk (>25%)",f"{len(high_risk):,}")
        c2.metric("Potential CLV at risk",f"{currency_symbol()} {sum(i.get('clv_estimate',0) for _,i in high_risk)/1e6:.0f}M")
        c3.metric("Avg churn risk",f"{sum(i.get('churn_risk',0) for _,i in high_risk)/max(len(high_risk),1)*100:.0f}%")

        df_ch = pd.DataFrame([{
            "CIF":cif,"Segment":info.get("segment",""),"Churn Risk":f"{info.get('churn_risk',0)*100:.0f}%",
            f"CLV ({currency_symbol()} K)":round(info.get("clv_estimate",0)/1e3,0),
            "Last Contact":f"{info.get('last_contact_days',0)}d",
            "NBA":info.get("nba",""),"NPS":info.get("nps_score",""),
        } for cif,info in high_risk[:50]])
        st.dataframe(df_ch, use_container_width=True, hide_index=True)

    with _churn_sub_tabs[1]:
        # ── Churn Score Engine (Standard #58, integrated v5.91) ──
        from utils.churn_prediction import (
            ChurnPredictionEngine, ChurnSignals,
            CHURN_FEATURE_WEIGHTS, CHURN_HIGH_RISK_THRESHOLD,
            CHURN_MEDIUM_RISK_THRESHOLD, CHURN_LOW_RISK_THRESHOLD,
            CHURN_SEGMENTS, BALANCE_DROP_PCT_THRESHOLD,
            COMPLAINT_OPEN_DAYS_THRESHOLD, CSAT_LOW_THRESHOLD,
            NO_TXN_DAYS_THRESHOLD, TENURE_NEW_DAYS_THRESHOLD,
            SPEC_DEVIATION_NOTE,
        )
        from decimal import Decimal as _D_ch
        from utils.core_audit import audit_log as _audit_log_ch

        st.markdown(
            f"**Standard #58 — Churn Score Engine** (deterministic rule-based "
            f"weighted-sum scoring per Rule 7). "
            f"Engine evaluates {len(CHURN_FEATURE_WEIGHTS)} signals with "
            f"weights summing to 100 and returns a 0-100 score + 4-tier segment.")
        st.caption(
            f"Tier thresholds: HIGH_RISK ≥ {CHURN_HIGH_RISK_THRESHOLD} · "
            f"MEDIUM_RISK ≥ {CHURN_MEDIUM_RISK_THRESHOLD} · "
            f"LOW_RISK ≥ {CHURN_LOW_RISK_THRESHOLD} · "
            f"STABLE < {CHURN_LOW_RISK_THRESHOLD}. "
            f"ML-based churn classifier deferred per spec deviation #8.")

        ch_inner = st.tabs([
            "🔍 Single Customer Score",
            "🎯 Demo Customer Builder",
        ])

        # ──── Single Customer Score ────
        with ch_inner[0]:
            st.markdown(
                "**Score a single customer** — provide signals; engine returns "
                "0-100 score with triggered factors + missing signals (Rule 6 transparency).")

            cc1, cc2 = st.columns(2)
            with cc1:
                ch_id = st.text_input("Customer ID",
                                        value="CUST_2026_001", key="ch_id")
                ch_days_txn = st.number_input(
                    "Days since last txn",
                    min_value=0, value=80, step=5, key="ch_days_txn",
                    help=f"≥{NO_TXN_DAYS_THRESHOLD} days triggers no_txn_60_days flag (weight 30)")
                ch_balance_drop = st.number_input(
                    "Balance drop % (90d)",
                    min_value=0.0, max_value=100.0, value=55.0, step=5.0,
                    key="ch_balance_drop",
                    help=f"≥{int(BALANCE_DROP_PCT_THRESHOLD)}% triggers balance_dropping_50pct (weight 20)")
                ch_complaint = st.number_input(
                    "Open complaint days",
                    min_value=0, value=0, step=1, key="ch_complaint",
                    help=f"≥{COMPLAINT_OPEN_DAYS_THRESHOLD}d unresolved triggers complaint_unresolved (weight 15)")
            with cc2:
                ch_competitor = st.number_input(
                    "Competitor cheques count (30d)",
                    min_value=0, value=0, step=1, key="ch_competitor",
                    help="≥1 cheque to competitor triggers competitor_check (weight 10)")
                ch_products = st.number_input(
                    "Product holdings count",
                    min_value=0, value=2, step=1, key="ch_products",
                    help="==1 triggers single_product_only (weight 10)")
                ch_csat = st.number_input(
                    "Last CSAT score (1-5)",
                    min_value=0, max_value=5, value=3, step=1, key="ch_csat",
                    help=f"≤{CSAT_LOW_THRESHOLD} triggers csat_low (weight 10). Use 0 to indicate no CSAT data.")
                ch_tenure = st.number_input(
                    "Tenure (days)",
                    min_value=0, value=400, step=30, key="ch_tenure",
                    help=f"<{TENURE_NEW_DAYS_THRESHOLD} triggers tenure_under_1y (weight 5)")

            if st.button("🎯 Compute churn score",
                           key="ch_score_btn", type="primary"):
                signals = ChurnSignals(
                    customer_id=ch_id,
                    days_since_last_txn=int(ch_days_txn),
                    balance_drop_pct_90d=_D_ch(str(ch_balance_drop)),
                    open_complaint_days=int(ch_complaint),
                    competitor_cheques_count_30d=int(ch_competitor),
                    product_holdings_count=int(ch_products),
                    last_csat_score=int(ch_csat) if ch_csat > 0 else None,
                    tenure_days=int(ch_tenure),
                )
                r = ChurnPredictionEngine.churn_score_rule_based(signals)
                score = int(_D_ch(str(r["score"])))
                segment = r["segment"]
                triggered = r.get("triggered_factors", [])
                missing = r.get("missing_signals", [])

                # Verdict banner
                seg_colors = {
                    "STABLE": "#10B981",
                    "LOW_RISK": "#3B82F6",
                    "MEDIUM_RISK": "#F59E0B",
                    "HIGH_RISK": "#DC2626",
                }
                seg_emoji = {"STABLE": "✅", "LOW_RISK": "🔵",
                             "MEDIUM_RISK": "🟡", "HIGH_RISK": "🔴"}
                color = seg_colors.get(segment, "#6B7280")
                emoji = seg_emoji.get(segment, "⚪")

                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"CHURN SCORE</div>"
                    f"<div style='font-size:32px;font-weight:800;color:{color};margin-top:6px'>"
                    f"{emoji} {score} → {segment}</div>"
                    f"<div style='font-size:14px;margin-top:6px'>"
                    f"{len(triggered)} triggered factor(s), "
                    f"{len(missing)} missing signal(s)</div></div>",
                    unsafe_allow_html=True)

                # Triggered factors
                if triggered:
                    st.markdown("**Triggered factors (sorted by weight):**")
                    trig_rows = []
                    for f in sorted(triggered, key=lambda f: -CHURN_FEATURE_WEIGHTS.get(f, 0)):
                        weight = CHURN_FEATURE_WEIGHTS.get(f, 0)
                        trig_rows.append({
                            "Factor": f,
                            "Weight (points)": weight,
                            "Contributes to score": f"+{weight}",
                        })
                    st.dataframe(pd.DataFrame(trig_rows),
                                 use_container_width=True, hide_index=True)

                # Missing signals (Rule 6)
                if missing:
                    st.warning(
                        f"⚠ **{len(missing)} signal(s) missing** "
                        "(Rule 6 transparency — score may be lower-bounded): "
                        f"{', '.join(missing)}")

                # Segment guidance
                if segment == "HIGH_RISK":
                    st.error(
                        f"🔴 **HIGH RISK** — immediate retention action required. "
                        "RM should make personal contact within 7 days. "
                        "Consider relationship pricing, product upgrade, "
                        "or executive escalation if HNW customer.")
                elif segment == "MEDIUM_RISK":
                    st.warning(
                        f"🟡 **MEDIUM RISK** — proactive outreach recommended. "
                        "Schedule check-in call within 14 days. "
                        "Identify root cause from triggered factors.")
                elif segment == "LOW_RISK":
                    st.info(
                        f"🔵 **LOW RISK** — early warning signals present. "
                        "Include in routine engagement campaigns. "
                        "Monitor for trend deterioration.")
                else:
                    st.success(
                        f"✅ **STABLE** — no significant churn signals. "
                        "Standard retention practices.")

                _audit_log_ch("IFRS_ENGINE_USED", uname,
                               f"ChurnPred #58: score {ch_id} "
                               f"score={score} segment={segment} "
                               f"triggered={len(triggered)} missing={len(missing)}")

        # ──── Demo Customer Builder ────
        with ch_inner[1]:
            st.markdown(
                "**Demo customer scenarios** — pre-configured profiles to "
                "demonstrate each tier and edge cases.")

            scenario = st.selectbox(
                "Scenario",
                [
                    "STABLE — recently active, multi-product, high CSAT",
                    "LOW_RISK — single missing signal",
                    "MEDIUM_RISK — 2 flags triggered (60pts)",
                    "HIGH_RISK — multiple flags (95pts)",
                    "All signals missing (Rule 6 — low confidence)",
                    "No-txn dominant (60+ days inactive only)",
                    "Complaint + CSAT combo",
                ],
                key="ch_demo_scenario")

            scenarios = {
                "STABLE — recently active, multi-product, high CSAT": dict(
                    customer_id="DEMO_STABLE",
                    days_since_last_txn=5, product_holdings_count=4,
                    last_csat_score=4, tenure_days=900),
                "LOW_RISK — single missing signal": dict(
                    customer_id="DEMO_LOW",
                    days_since_last_txn=30, product_holdings_count=1,
                    tenure_days=400),
                "MEDIUM_RISK — 2 flags triggered (60pts)": dict(
                    customer_id="DEMO_MED",
                    days_since_last_txn=80,
                    balance_drop_pct_90d=_D_ch("60"),
                    product_holdings_count=2, tenure_days=500),
                "HIGH_RISK — multiple flags (95pts)": dict(
                    customer_id="DEMO_HIGH",
                    days_since_last_txn=120,
                    balance_drop_pct_90d=_D_ch("75"),
                    open_complaint_days=30,
                    competitor_cheques_count_30d=2,
                    product_holdings_count=1,
                    last_csat_score=1, tenure_days=900),
                "All signals missing (Rule 6 — low confidence)": dict(
                    customer_id="DEMO_MISSING"),
                "No-txn dominant (60+ days inactive only)": dict(
                    customer_id="DEMO_INACTIVE",
                    days_since_last_txn=90,
                    product_holdings_count=3, tenure_days=800),
                "Complaint + CSAT combo": dict(
                    customer_id="DEMO_UNHAPPY",
                    days_since_last_txn=20,
                    open_complaint_days=21,
                    last_csat_score=1,
                    product_holdings_count=2, tenure_days=600),
            }
            cust_cfg = scenarios[scenario]

            st.json({k: str(v) for k, v in cust_cfg.items()})

            if st.button("🎯 Run scenario",
                           key="ch_demo_btn", type="primary"):
                demo_signals = ChurnSignals(**cust_cfg)
                r = ChurnPredictionEngine.churn_score_rule_based(demo_signals)
                score = int(_D_ch(str(r["score"])))
                segment = r["segment"]
                triggered = r.get("triggered_factors", [])
                missing = r.get("missing_signals", [])

                seg_emoji = {"STABLE": "✅", "LOW_RISK": "🔵",
                             "MEDIUM_RISK": "🟡", "HIGH_RISK": "🔴"}.get(segment, "⚪")

                st.markdown(
                    f"### {seg_emoji} Score: **{score}** → **{segment}**")
                if triggered:
                    st.markdown(
                        f"**Triggered factors:** {', '.join(triggered)} "
                        f"(total weight = {sum(CHURN_FEATURE_WEIGHTS.get(f, 0) for f in triggered)})")
                if missing:
                    st.caption(f"Missing signals (Rule 6): {', '.join(missing)}")

                _audit_log_ch("IFRS_ENGINE_USED", uname,
                               f"ChurnPred #58: scenario {cust_cfg['customer_id']} "
                               f"score={score} segment={segment}")

    with _churn_sub_tabs[2]:
        # ── Retention Priority (Standard #58, v5.91) ──
        from utils.churn_prediction import (
            ChurnPredictionEngine, ChurnSignals,
            CHURN_HIGH_RISK_THRESHOLD,
        )
        from decimal import Decimal as _D_rp
        from utils.core_audit import audit_log as _audit_log_rp

        st.markdown(
            "**Retention Intervention Priority** — engine ranks customers "
            "by churn risk, returns prioritized list for RM team outreach.")
        st.caption(
            "Demo dataset: 10-customer portfolio spanning all 4 risk tiers "
            "plus customers with missing signals. Engine returns priority_list "
            "(HIGH+MEDIUM only), low_confidence_count (all-missing customers), "
            "scored_customers count.")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_churn_portfolio():
            return [
                # HIGH_RISK — multiple flags
                ChurnSignals(customer_id="HNW_001",
                              days_since_last_txn=120,
                              balance_drop_pct_90d=_D_rp("75"),
                              open_complaint_days=30,
                              competitor_cheques_count_30d=2,
                              product_holdings_count=1,
                              last_csat_score=1, tenure_days=900),
                # HIGH_RISK — different combo
                ChurnSignals(customer_id="RET_001",
                              days_since_last_txn=85,
                              balance_drop_pct_90d=_D_rp("65"),
                              open_complaint_days=20,
                              product_holdings_count=1, tenure_days=600),
                # MEDIUM_RISK — 2 flags
                ChurnSignals(customer_id="RET_002",
                              days_since_last_txn=70,
                              balance_drop_pct_90d=_D_rp("55"),
                              product_holdings_count=2, tenure_days=500),
                # MEDIUM_RISK — different combo
                ChurnSignals(customer_id="SME_001",
                              days_since_last_txn=65,
                              competitor_cheques_count_30d=1,
                              last_csat_score=2,
                              product_holdings_count=2, tenure_days=800),
                # LOW_RISK
                ChurnSignals(customer_id="RET_003",
                              days_since_last_txn=30,
                              product_holdings_count=1, tenure_days=400),
                # LOW_RISK — borderline
                ChurnSignals(customer_id="RET_004",
                              days_since_last_txn=20,
                              product_holdings_count=1, tenure_days=300),
                # STABLE
                ChurnSignals(customer_id="STABLE_001",
                              days_since_last_txn=5,
                              product_holdings_count=4,
                              last_csat_score=5, tenure_days=1000),
                # STABLE
                ChurnSignals(customer_id="STABLE_002",
                              days_since_last_txn=10,
                              product_holdings_count=3,
                              last_csat_score=4, tenure_days=800),
                # All-missing — Rule 6 low confidence
                ChurnSignals(customer_id="MISSING_001"),
                # New customer with limited signals
                ChurnSignals(customer_id="NEW_001",
                              days_since_last_txn=10,
                              product_holdings_count=1,
                              tenure_days=60),
            ]

        rp_max = st.slider(
            "Max priority list size",
            min_value=5, max_value=50, value=20, step=5,
            key="ch_rp_max")

        if st.button("📋 Compute retention priority",
                       key="ch_rp_btn", type="primary"):
            portfolio = _demo_churn_portfolio()
            r = ChurnPredictionEngine.retention_intervention_priority(
                portfolio, max_priority_count=rp_max)

            total = int(r["total_customers"])
            scored = int(r["scored_customers"])
            low_conf = int(r["low_confidence_count"])
            priority_count = int(r["priority_count"])
            priority_list = r.get("priority_list", [])

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total customers", total)
            k2.metric("Scored", scored)
            k3.metric("Low confidence", low_conf,
                       help="Customers with all signals missing (Rule 6).")
            k4.metric("Priority (HIGH+MEDIUM)",
                       priority_count,
                       help="Customers requiring intervention.")

            if priority_list:
                st.markdown("**Priority intervention list:**")
                seg_emoji = {"HIGH_RISK": "🔴", "MEDIUM_RISK": "🟡"}
                rows = []
                for p in priority_list:
                    seg = p["segment"]
                    triggered_str = ", ".join(p.get("triggered_factors", [])[:3])
                    if len(p.get("triggered_factors", [])) > 3:
                        triggered_str += f" +{len(p['triggered_factors']) - 3} more"
                    rows.append({
                        "Customer": p["customer_id"],
                        "Score": int(_D_rp(str(p["score"]))),
                        "Tier": f"{seg_emoji.get(seg, '⚪')} {seg}",
                        "Top triggers": triggered_str or "—",
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # Tier breakdown
                from collections import Counter
                tier_counter = Counter([p["segment"] for p in priority_list])
                high_count = tier_counter.get("HIGH_RISK", 0)
                med_count = tier_counter.get("MEDIUM_RISK", 0)

                tk1, tk2 = st.columns(2)
                tk1.metric("🔴 HIGH_RISK", high_count,
                            help="7-day intervention window.")
                tk2.metric("🟡 MEDIUM_RISK", med_count,
                            help="14-day intervention window.")

                # Bar chart of top scores
                chart_data = pd.DataFrame({
                    "Score": [int(_D_rp(str(p["score"]))) for p in priority_list]
                }, index=[p["customer_id"] for p in priority_list])
                st.markdown("**Priority customer scores:**")
                st.bar_chart(chart_data)

                # Pipeline guidance
                if high_count >= 3:
                    st.error(
                        f"🔴 **{high_count} HIGH_RISK customer(s)** — "
                        "RM team should make personal contact within 7 days. "
                        "Consider executive escalation for HNW customers.")
                elif high_count > 0:
                    st.warning(
                        f"⚠ **{high_count} HIGH_RISK customer(s)** require "
                        "immediate attention within 7 days.")
                elif med_count > 0:
                    st.info(
                        f"ℹ **{med_count} MEDIUM_RISK customer(s)** — "
                        "schedule outreach within 14 days.")
                else:
                    st.success(
                        "✅ No customers in HIGH/MEDIUM risk tiers — "
                        "portfolio stable.")
            else:
                st.success(
                    "✅ No customers in priority list — portfolio stable.")

            if low_conf > 0:
                st.caption(
                    f"💡 **{low_conf} customer(s) with all signals missing** — "
                    "production deployment should ensure data ingestion pipelines "
                    "populate ChurnSignals fields from CBS to enable scoring.")

            _audit_log_rp("IFRS_ENGINE_USED", uname,
                           f"ChurnPred #58: retention_priority total={total} "
                           f"scored={scored} low_conf={low_conf} priority={priority_count}")

    with _churn_sub_tabs[3]:
        # ── Engine Reference (Standard #58, v5.91) ──
        from utils.churn_prediction import (
            CHURN_FEATURE_WEIGHTS, CHURN_HIGH_RISK_THRESHOLD,
            CHURN_MEDIUM_RISK_THRESHOLD, CHURN_LOW_RISK_THRESHOLD,
            CHURN_SEGMENTS, BALANCE_DROP_PCT_THRESHOLD,
            COMPLAINT_OPEN_DAYS_THRESHOLD, CSAT_LOW_THRESHOLD,
            NO_TXN_DAYS_THRESHOLD, TENURE_NEW_DAYS_THRESHOLD,
            SPEC_DEVIATION_NOTE,
        )

        st.markdown("**Engine Constants Reference** (single source of truth)")

        st.markdown(
            f"**7 churn features with weights** "
            f"(sum = {sum(CHURN_FEATURE_WEIGHTS.values())} "
            f"— max possible score):")
        feature_descriptions = {
            "no_txn_60_days": f"Days since last txn ≥ {NO_TXN_DAYS_THRESHOLD}d",
            "balance_dropping_50pct": f"Balance drop ≥ {int(BALANCE_DROP_PCT_THRESHOLD)}% in 90 days",
            "complaint_unresolved": f"Open complaint ≥ {COMPLAINT_OPEN_DAYS_THRESHOLD} days",
            "competitor_check": "≥1 cheque to competitor bank in 30 days",
            "single_product_only": "Customer holds only 1 product",
            "csat_low": f"Last CSAT score ≤ {CSAT_LOW_THRESHOLD}",
            "tenure_under_1y": f"Tenure < {TENURE_NEW_DAYS_THRESHOLD} days",
        }
        feat_rows = sorted(
            [{"Feature": f,
               "Weight": w,
               "Trigger": feature_descriptions.get(f, "—")}
             for f, w in CHURN_FEATURE_WEIGHTS.items()],
            key=lambda r: -r["Weight"])
        st.dataframe(pd.DataFrame(feat_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Risk segment thresholds:**")
        seg_rows = [
            {"Segment": "🔴 HIGH_RISK",
              "Score range": f"≥ {CHURN_HIGH_RISK_THRESHOLD}",
              "Action SLA": "7-day RM contact"},
            {"Segment": "🟡 MEDIUM_RISK",
              "Score range": f"{CHURN_MEDIUM_RISK_THRESHOLD}-{CHURN_HIGH_RISK_THRESHOLD - 1}",
              "Action SLA": "14-day outreach"},
            {"Segment": "🔵 LOW_RISK",
              "Score range": f"{CHURN_LOW_RISK_THRESHOLD}-{CHURN_MEDIUM_RISK_THRESHOLD - 1}",
              "Action SLA": "Routine engagement"},
            {"Segment": "✅ STABLE",
              "Score range": f"< {CHURN_LOW_RISK_THRESHOLD}",
              "Action SLA": "Standard practices"},
        ]
        st.dataframe(pd.DataFrame(seg_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Spec deviation #8 — ML churn classifier deferred:**")
        st.warning(
            f"ℹ {SPEC_DEVIATION_NOTE}")
        st.caption(
            "Per Rule 7 (no silent ML predictions), `churn_score_predict` does "
            "NOT fall back to ML when no `ml_churn_fn` is provided — instead it "
            "returns the rule-based score with explicit `basis='rule_based'` "
            "and `reason='no_ml_churn_model_loaded'`. Production deployment that "
            "trains a churn model can plug it in via the callback; until then, "
            "deterministic rule-based scoring is the primary path. "
            "Engine integrates well with v5.90 Customer Segmentation: "
            "CANNOT_LOSE_THEM segment customers should be cross-checked against "
            "this churn engine for retention prioritization.")

# ── TAB 4: Next Best Action ──────────────────────────────────────────
with tabs[3]:
    st.markdown("**Next Best Action — top cross-sell and upsell opportunities:**")
    for prod in ["Personal Loan","Mortgage","Fixed Deposit","Insurance","Business Loan"]:
        candidates = [(cif,info) for cif,info in ci_raw.items()
                      if info.get("nba")==prod and info.get("propensity_scores",{}).get(prod,0)>0.30]
        candidates.sort(key=lambda x:-x[1].get("propensity_scores",{}).get(prod,0))
        if candidates:
            avg_p = sum(i.get("propensity_scores",{}).get(prod,0) for _,i in candidates)/len(candidates)
            total_clv_prod = sum(i.get("clv_estimate",0) for _,i in candidates)/1e6
            st.markdown(
                f"**{prod}** — {len(candidates):,} customers · avg propensity {avg_p*100:.0f}% · "
                f"total CLV {currency_symbol()} {total_clv_prod:.0f}M")

# ── TAB 5: Segment Analytics ────────────────────────────────────────
with tabs[4]:
    # ─────────────────────────────────────────────────────────────
    # v7.13: Cards Engine surfacing (L05 visibility — completes engine + loop + UI chain)
    # ─────────────────────────────────────────────────────────────
    with st.expander("🃏 Card Usage Profile (v7.12 engine / v7.13 surfaced — L05)", expanded=False):
        from utils.cards import CardsEngine, CardTransaction
        from utils.customer_segmentation import CustomerSegmentationEngine
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from decimal import Decimal as _D

        st.caption(
            "v7.13 surfacing of `utils.cards.CardsEngine` and the L05 loop "
            "consumer `customer_segmentation.enrich_segment_with_card_usage()`. "
            "Pick a usage scenario below and watch the cards engine produce a "
            "PUBLISHED_LANGUAGE payload that the segmentation engine consumes "
            "to enrich the base RFM segment. Inputs are illustrative — "
            "production wires from real card transaction streams."
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Scenario picker:**")
            scenario = st.selectbox(
                "Card usage scenario",
                ["High-velocity diverse (uplifts segment)",
                 "Dormant card (downgrades segment)",
                 "Foreign-heavy (TRAVELER_PROFILE flag)",
                 "Single dominant category (SPECIALIST_PROFILE flag)",
                 "Typical retail (no enrichment)"],
                key="c360_cards_scenario")

            base_segment = st.selectbox(
                "Base RFM segment",
                ["HIBERNATING", "LOST", "AT_RISK", "POTENTIAL",
                 "PROMISING", "LOYAL", "CHAMPIONS"],
                index=5,  # default LOYAL
                key="c360_cards_base_segment")

        # Build illustrative txns per scenario
        ref_dt = _dt(2026, 4, 30, tzinfo=_tz.utc)
        txns = []
        if scenario.startswith("High-velocity"):
            mccs = ["5411", "5812", "5942", "5311", "4111", "5732", "5814"]
            for i in range(35):
                txns.append(CardTransaction(
                    f"T{i:03d}", "DEMO", "DEMO_CUST",
                    _D("4500") + _D(str(i * 200)),
                    ref_dt - _td(days=i % 28),
                    mccs[i % len(mccs)],
                    "KE", "Nairobi"))
        elif scenario.startswith("Dormant"):
            txns.append(CardTransaction(
                "T01", "DEMO", "DEMO_CUST", _D("2500"),
                ref_dt - _td(days=120),
                "5411", "KE", "Nairobi"))
        elif scenario.startswith("Foreign-heavy"):
            countries = ["AE", "AE", "GB", "AE", "ZA", "GB", "AE", "US", "KE",
                         "AE", "GB", "AE", "ZA", "AE"]
            for i, country in enumerate(countries):
                txns.append(CardTransaction(
                    f"T{i:03d}", "DEMO", "DEMO_CUST",
                    _D("8000"),
                    ref_dt - _td(days=i),
                    "5812", country, "Various"))
        elif scenario.startswith("Single dominant"):
            for i in range(15):
                mcc = "5411" if i < 13 else "5812"  # 13 of 15 = 86.7% dominant
                txns.append(CardTransaction(
                    f"T{i:03d}", "DEMO", "DEMO_CUST",
                    _D("3500"),
                    ref_dt - _td(days=i * 2),
                    mcc, "KE", "Nairobi"))
        else:  # Typical retail
            mccs = ["5411", "5812", "5311"]
            for i in range(8):
                txns.append(CardTransaction(
                    f"T{i:03d}", "DEMO", "DEMO_CUST",
                    _D("4000"),
                    ref_dt - _td(days=i * 3),
                    mccs[i % 3], "KE", "Nairobi"))

        profile = CardsEngine.card_usage_profile(
            "DEMO", txns, reference_date=ref_dt)

        with c2:
            st.markdown("**Cards engine PRODUCER output:**")
            v = profile["velocity"]
            mcc = profile["merchant_category_mix"]
            geo = profile["geographic_pattern"]
            sev_color = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🟠",
                         "DORMANT": "🚨"}.get(v.get("velocity_class"), "")
            st.markdown(
                f"- **Velocity:** {sev_color} {v.get('velocity_class')} "
                f"({v.get('txn_count_30d', 0)} txns/30d)")
            if mcc.get("computed"):
                st.markdown(
                    f"- **Top MCC:** `{mcc.get('dominant_category')}` "
                    f"({mcc.get('dominant_category_pct')}%)")
                st.markdown(
                    f"- **Diversity score:** {mcc.get('category_diversity_score')}/100")
            if geo.get("computed"):
                conc = geo.get("geographic_concentration", "")
                conc_icon = {"HOME_DOMINANT": "🇰🇪",
                             "SPLIT": "🌍", "FOREIGN_HEAVY": "✈️"}.get(conc, "")
                st.markdown(
                    f"- **Geographic:** {conc_icon} {conc} "
                    f"(home={geo.get('home_country_pct')}%, "
                    f"foreign countries={geo.get('foreign_country_count')})")

        st.markdown("---")
        st.markdown("**L05 CONSUMER — segmentation enrichment:**")

        result = CustomerSegmentationEngine.enrich_segment_with_card_usage(
            base_rfm_segment=base_segment,
            card_usage_profile=profile)

        cc1, cc2 = st.columns(2)
        with cc1:
            base_label = result["base_segment"]
            enriched_label = result["enriched_segment"]
            arrow = "→" if base_label != enriched_label else "↔ (no change)"
            st.markdown(f"#### `{base_label}` {arrow} `{enriched_label}`")
            if result.get("modifiers_applied"):
                for m in result["modifiers_applied"]:
                    st.markdown(
                        f"- **Modifier:** {m['from']} → {m['to']} "
                        f"(*{m['reason']}*)")
            else:
                st.caption("No segment modification applied.")

        with cc2:
            if result.get("profile_flags"):
                st.markdown("**Profile flags:**")
                for f in result["profile_flags"]:
                    flag_icon = {"TRAVELER_PROFILE": "✈️",
                                 "SPECIALIST_PROFILE": "🎯"}.get(f, "")
                    st.markdown(f"- {flag_icon} `{f}`")
            else:
                st.caption("No profile flags raised for this scenario.")
            st.caption(
                f"Consumed payload version: `{result.get('consumed_payload_version')}` · "
                f"Pattern: `{result.get('pattern')}`")

        st.info(
            "💡 **L05 chain complete:** v7.12 built `utils/cards.py` (engine "
            "+ CardsEngine + CardTransaction); the same batch wired the "
            "consumer in `customer_segmentation.enrich_segment_with_card_usage()`. "
            "v7.13 surfaces the producer + consumer here so operators can "
            "see the loop fire on real scenarios. Next step: production "
            "wiring against real card transaction streams."
        )

    _seg_sub_tabs = st.tabs([
        "📊 Segment Aggregation (existing)",
        "🎯 RFM Analysis (Standard #65, v5.90)",
        "💎 Value Tiers (Standard #65, v5.90)",
        "🔄 Lifecycle Stage (Standard #65, v5.90)",
        "🌳 Engine Reference (Standard #65, v5.90)",
        "🏛️ Customer Value Segments (Standard #66, v5.96)",
    ])

    with _seg_sub_tabs[0]:
        st.markdown("**Segment-level analytics:**")
        seg_agg = defaultdict(lambda:{"count":0,"clv":0,"churn":0,"nps":0})
        for info in ci_raw.values():
            s = info.get("segment","Mass")
            seg_agg[s]["count"]+=1; seg_agg[s]["clv"]+=info.get("clv_estimate",0)
            seg_agg[s]["churn"]+=info.get("churn_risk",0); seg_agg[s]["nps"]+=info.get("nps_score",5)
        df_sa = pd.DataFrame([{
            "Segment":s,"Customers":v["count"],
            f"Avg CLV ({currency_symbol()} K)":round(v["clv"]/v["count"]/1e3,0),
            "Avg Churn Risk%":round(v["churn"]/v["count"]*100,1),
            "Avg NPS":round(v["nps"]/v["count"],1),
        } for s,v in seg_agg.items()])
        st.dataframe(df_sa, use_container_width=True, hide_index=True)

    with _seg_sub_tabs[1]:
        # ── RFM Analysis (Standard #65, integrated v5.90) ──
        from utils.customer_segmentation import (
            CustomerSegmentationEngine, CustomerRecord, CustomerTransaction,
            RFM_SEGMENTS, DEFAULT_RFM_WINDOW_DAYS,
        )
        from datetime import date as _date_cs, timedelta as _td_cs
        from decimal import Decimal as _D_cs
        from utils.core_audit import audit_log as _audit_log_cs

        st.markdown(
            f"**Standard #65 — RFM Analysis** (Recency / Frequency / Monetary). "
            f"Engine assigns 1-5 quintile scores per dimension and maps "
            f"(R, F, M) tuple to one of {len(RFM_SEGMENTS)} segments.")
        st.caption(
            f"Default RFM window: {DEFAULT_RFM_WINDOW_DAYS} days. "
            "Segments range from CHAMPIONS (top engagement + spend) "
            "to LOST (no recent activity, low spend).")

        # Demo dataset — 8 customers with deliberately varied activity
        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_rfm_data():
            ref = _date_cs(2026, 5, 1)
            customers = []
            txns = []
            for i in range(8):
                cust_id = f"DEMO_C{i:03d}"
                customers.append(CustomerRecord(
                    customer_id=cust_id, cif_id=f"DEMO_CIF_{i:03d}",
                    onboarded_date=_date_cs(2024, 1, 1),
                    total_relationship_balance_kes=_D_cs(str(100000 * (i + 1)))))
                # i=0 most active down to i=7 least active
                activity = 8 - i
                for j in range(activity):
                    days_ago = j * (30 if i < 4 else 90)
                    txns.append(CustomerTransaction(
                        txn_id=f"T_{cust_id}_{j}",
                        customer_id=cust_id,
                        txn_date=ref - _td_cs(days=days_ago),
                        amount_kes=_D_cs(str(50000 * (8 - i)))))
            return customers, txns

        rfm_customers, rfm_txns = _demo_rfm_data()
        rfm_ref = st.date_input(
            "Reference date",
            value=_date_cs(2026, 5, 1), key="cs_rfm_ref")
        rfm_window = st.slider(
            "RFM window (days)",
            min_value=30, max_value=730, value=DEFAULT_RFM_WINDOW_DAYS, step=30,
            key="cs_rfm_window",
            help=f"Default {DEFAULT_RFM_WINDOW_DAYS} days. Smaller window emphasizes recent behavior.")

        if st.button("🎯 Compute RFM scores",
                       key="cs_rfm_btn", type="primary"):
            r = CustomerSegmentationEngine.rfm_scores(
                rfm_customers, rfm_txns,
                reference_date=rfm_ref,
                window_days=int(rfm_window))

            scored = int(r["scored_customer_count"])
            unscored = int(r["unscored_customer_count"])
            scores = r.get("scores", [])

            k1, k2, k3 = st.columns(3)
            k1.metric("Customers scored", scored)
            k2.metric("Unscored (Rule 6)", unscored,
                       help="Customers with no transactions in window.")
            k3.metric("Window (days)", int(r["window_days"]))

            if scores:
                # Build per-customer table with rfm_segment label
                rows = []
                seg_count = {}
                for s in scores:
                    r_s = int(_D_cs(str(s["r_score"])))
                    f_s = int(_D_cs(str(s["f_score"])))
                    m_s = int(_D_cs(str(s["m_score"])))
                    label = CustomerSegmentationEngine.rfm_segment(r_s, f_s, m_s)
                    seg_count[label] = seg_count.get(label, 0) + 1
                    rows.append({
                        "Customer": s["customer_id"],
                        "Recency (days)": int(_D_cs(str(s["recency_days"]))),
                        "Frequency": int(_D_cs(str(s["frequency"]))),
                        f"Monetary ({currency_symbol()})": int(_D_cs(str(s["monetary_kes"]))),
                        "R/F/M": s["rfm_combined"],
                        "Segment": label,
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # Segment distribution
                st.markdown("**RFM segment distribution:**")
                seg_rows = sorted(
                    [{"Segment": k, "Count": v,
                      "% of scored": f"{v/scored*100:.1f}%"}
                     for k, v in seg_count.items()],
                    key=lambda r: -r["Count"])
                st.dataframe(pd.DataFrame(seg_rows),
                             use_container_width=True, hide_index=True)

                _audit_log_cs("IFRS_ENGINE_USED", uname,
                               f"Segmentation #65: RFM scored={scored} unscored={unscored} "
                               f"window={int(rfm_window)}d segments={seg_count}")

    with _seg_sub_tabs[2]:
        # ── Value Tier Assignment (Standard #65, v5.90) ──
        from utils.customer_segmentation import (
            CustomerSegmentationEngine, CustomerRecord,
            VALUE_TIERS, VALUE_TIER_HNI_MIN,
            VALUE_TIER_MASS_AFFLUENT_MIN, VALUE_TIER_MASS_MIN,
        )
        from decimal import Decimal as _D_vt
        from utils.core_audit import audit_log as _audit_log_vt

        st.markdown(
            f"**Standard #65 — Value Tier Assignment**. "
            f"Engine buckets customers into {len(VALUE_TIERS)} tiers based on "
            f"total relationship balance.")
        st.caption(
            f"HNI ≥ {currency_symbol()} {int(float(VALUE_TIER_HNI_MIN)/1e6):,}M · "
            f"MASS_AFFLUENT ≥ {currency_symbol()} {int(float(VALUE_TIER_MASS_AFFLUENT_MIN)/1e6):,}M · "
            f"MASS ≥ {currency_symbol()} {int(float(VALUE_TIER_MASS_MIN)/1000):,}K · "
            f"SMALL < {currency_symbol()} {int(float(VALUE_TIER_MASS_MIN)/1000):,}K. "
            f"Customers without balance data are flagged unassigned (Rule 6).")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_value_customers():
            return [
                CustomerRecord("V_HNI_001", "CIF_HNI_001",
                               total_relationship_balance_kes=_D_vt("80000000")),
                CustomerRecord("V_HNI_002", "CIF_HNI_002",
                               total_relationship_balance_kes=_D_vt("55000000")),
                CustomerRecord("V_MA_001", "CIF_MA_001",
                               total_relationship_balance_kes=_D_vt("12000000")),
                CustomerRecord("V_MA_002", "CIF_MA_002",
                               total_relationship_balance_kes=_D_vt("8000000")),
                CustomerRecord("V_MA_003", "CIF_MA_003",
                               total_relationship_balance_kes=_D_vt("6500000")),
                CustomerRecord("V_MASS_001", "CIF_MASS_001",
                               total_relationship_balance_kes=_D_vt("500000")),
                CustomerRecord("V_MASS_002", "CIF_MASS_002",
                               total_relationship_balance_kes=_D_vt("250000")),
                CustomerRecord("V_MASS_003", "CIF_MASS_003",
                               total_relationship_balance_kes=_D_vt("150000")),
                CustomerRecord("V_SMALL_001", "CIF_SMALL_001",
                               total_relationship_balance_kes=_D_vt("80000")),
                CustomerRecord("V_SMALL_002", "CIF_SMALL_002",
                               total_relationship_balance_kes=_D_vt("30000")),
                CustomerRecord("V_NONE_001", "CIF_NONE_001"),  # missing balance
            ]

        if st.button("💎 Assign value tiers",
                       key="cs_vt_btn", type="primary"):
            value_customers = _demo_value_customers()
            r = CustomerSegmentationEngine.value_tier_assignment(value_customers)

            assigned = int(r["assigned_count"])
            unassigned = int(r["unassigned_count"])
            tier_dist = r.get("tier_distribution", {})

            k1, k2, k3 = st.columns(3)
            k1.metric("Total customers", len(value_customers))
            k2.metric("Assigned", assigned)
            k3.metric("Unassigned (Rule 6)", unassigned,
                       help="Customers with no balance data.")

            # Tier distribution
            st.markdown("**Tier distribution:**")
            tier_emoji = {"HNI": "💎", "MASS_AFFLUENT": "🌟",
                           "MASS": "🟢", "SMALL": "⚪"}
            tier_rows = []
            for tier in VALUE_TIERS:
                count = int(tier_dist.get(tier, 0))
                pct = (count / assigned * 100) if assigned else 0
                tier_rows.append({
                    "Tier": f"{tier_emoji.get(tier, '⚪')} {tier}",
                    "Count": count,
                    "% of assigned": f"{pct:.1f}%",
                })
            st.dataframe(pd.DataFrame(tier_rows),
                         use_container_width=True, hide_index=True)

            # Bar chart
            chart_data = pd.DataFrame({
                "Customers": [int(tier_dist.get(t, 0)) for t in VALUE_TIERS]
            }, index=list(VALUE_TIERS))
            st.bar_chart(chart_data)

            # Per-customer assignments
            st.markdown("**Per-customer assignments:**")
            assignments = r.get("assignments", [])
            ar_rows = []
            for a in assignments:
                ar_rows.append({
                    "Customer": a["customer_id"],
                    f"Balance ({currency_symbol()})": int(_D_vt(str(a["balance_kes"]))),
                    "Tier": f"{tier_emoji.get(a['value_tier'], '⚪')} {a['value_tier']}",
                })
            if ar_rows:
                st.dataframe(pd.DataFrame(ar_rows),
                             use_container_width=True, hide_index=True)

            if unassigned > 0:
                unassigned_sample = r.get("unassigned_sample", [])
                st.warning(
                    f"⚠ {unassigned} customer(s) unassigned due to missing balance: "
                    f"{', '.join(unassigned_sample[:5])}"
                    + (f" + {unassigned - 5} more"
                       if unassigned > 5 else "")
                    + " (Rule 6 transparency)")

            _audit_log_vt("IFRS_ENGINE_USED", uname,
                           f"Segmentation #65: value_tier assigned={assigned} "
                           f"unassigned={unassigned} dist={tier_dist}")

    with _seg_sub_tabs[3]:
        # ── Lifecycle Stage (Standard #65, v5.90) ──
        from utils.customer_segmentation import (
            CustomerSegmentationEngine, CustomerRecord,
            LIFECYCLE_STAGES, LIFECYCLE_NEW_DAYS, LIFECYCLE_GROWING_DAYS,
            LIFECYCLE_DORMANT_DAYS,
        )
        from datetime import date as _date_lc
        from decimal import Decimal as _D_lc
        from utils.core_audit import audit_log as _audit_log_lc

        st.markdown(
            f"**Standard #65 — Lifecycle Stage**. "
            f"Classifies a customer into one of {len(LIFECYCLE_STAGES)} stages "
            f"based on tenure + last transaction recency.")
        st.caption(
            f"NEW: tenure < {LIFECYCLE_NEW_DAYS}d · "
            f"GROWING: tenure < {LIFECYCLE_GROWING_DAYS}d · "
            f"MATURE: tenure ≥ {LIFECYCLE_GROWING_DAYS}d AND active txn within {LIFECYCLE_DORMANT_DAYS}d · "
            f"DORMANT: no txn for ≥ {LIFECYCLE_DORMANT_DAYS}d.")

        c1, c2 = st.columns(2)
        with c1:
            lc_id = st.text_input("Customer ID",
                                    value="CUST_LC_001", key="cs_lc_id")
            lc_cif = st.text_input("CIF ID",
                                     value="CIF_LC_001", key="cs_lc_cif")
            lc_onboarded = st.date_input(
                "Onboarded date",
                value=_date_lc(2024, 6, 1), key="cs_lc_onboarded",
                help="Determines tenure for NEW/GROWING/MATURE classification.")
        with c2:
            lc_last_txn = st.date_input(
                "Last transaction date",
                value=_date_lc(2026, 4, 28), key="cs_lc_last_txn",
                help="Determines DORMANT classification.")
            lc_balance = st.number_input(
                f"Balance ({currency_symbol()} K)",
                min_value=0.0, value=300.0, step=50.0,
                key="cs_lc_balance",
                help="Balance is informational; doesn't affect lifecycle stage.")
            lc_ref = st.date_input(
                "Reference date",
                value=_date_lc(2026, 5, 1), key="cs_lc_ref")

        if st.button("🔄 Compute lifecycle stage",
                       key="cs_lc_btn", type="primary"):
            cust = CustomerRecord(
                customer_id=lc_id, cif_id=lc_cif,
                onboarded_date=lc_onboarded,
                last_transaction_date=lc_last_txn,
                total_relationship_balance_kes=_D_lc(str(lc_balance * 1000)))
            r = CustomerSegmentationEngine.lifecycle_stage(cust, lc_ref)

            stage = r.get("stage")
            if stage is None:
                st.error(
                    f"⛔ Cannot compute stage: `{r.get('reason', '—')}` "
                    "(Rule 6 transparency)")
            else:
                stage_emoji = {"NEW": "🆕", "GROWING": "🌱",
                                "MATURE": "🌳", "DORMANT": "💤"}
                emoji = stage_emoji.get(stage, "⚪")
                stage_color = {"NEW": "#3B82F6", "GROWING": "#10B981",
                                "MATURE": "#F59E0B", "DORMANT": "#6B7280"}.get(stage, "#6B7280")

                st.markdown(
                    f"<div style='padding:14px;background:{stage_color}22;"
                    f"border-left:6px solid {stage_color};border-radius:10px'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"LIFECYCLE STAGE</div>"
                    f"<div style='font-size:24px;font-weight:800;color:{stage_color}'>"
                    f"{emoji} {stage}</div></div>",
                    unsafe_allow_html=True)

                k1, k2 = st.columns(2)
                k1.metric("Days active",
                           r.get("days_active", "—"),
                           help="Tenure since onboarding.")
                k2.metric("Days since last txn",
                           r.get("days_since_last_txn", "—"),
                           help=f"DORMANT if ≥{LIFECYCLE_DORMANT_DAYS}d.")

                # Stage guidance
                if stage == "NEW":
                    st.info(
                        "🆕 **New customer** — first 90 days. Critical onboarding period; "
                        "ensure first product activation within 30 days.")
                elif stage == "GROWING":
                    st.info(
                        "🌱 **Growing customer** — 90 to 365 days. Cross-sell opportunity "
                        "ideal; relationship balance trajectory determines future tier.")
                elif stage == "MATURE":
                    st.success(
                        "🌳 **Mature customer** — established relationship. "
                        "Retention focus; deepen wallet share.")
                else:
                    st.warning(
                        f"💤 **Dormant** — no transactions for "
                        f"{r.get('days_since_last_txn')}d. Reactivation campaign "
                        "appropriate; consider account closure if dormancy persists.")

                _audit_log_lc("IFRS_ENGINE_USED", uname,
                               f"Segmentation #65: lifecycle {lc_id} stage={stage}")

    with _seg_sub_tabs[4]:
        # ── Engine Reference (Standard #65, v5.90) ──
        from utils.customer_segmentation import (
            VALUE_TIERS, VALUE_TIER_HNI_MIN,
            VALUE_TIER_MASS_AFFLUENT_MIN, VALUE_TIER_MASS_MIN,
            LIFECYCLE_STAGES, LIFECYCLE_NEW_DAYS,
            LIFECYCLE_GROWING_DAYS, LIFECYCLE_DORMANT_DAYS,
            RFM_SEGMENTS, DEFAULT_RFM_WINDOW_DAYS,
        )
        st.markdown("**Engine Constants Reference** (single source of truth)")

        st.markdown(f"**Value tiers** ({len(VALUE_TIERS)}):")
        vt_rows = [
            {"Tier": "💎 HNI",
              f"Min balance ({currency_symbol()})": f"{int(VALUE_TIER_HNI_MIN):,}",
              "Description": "High-Net-worth Individual"},
            {"Tier": "🌟 MASS_AFFLUENT",
              f"Min balance ({currency_symbol()})": f"{int(VALUE_TIER_MASS_AFFLUENT_MIN):,}",
              "Description": "Mass affluent (typically RM-managed)"},
            {"Tier": "🟢 MASS",
              f"Min balance ({currency_symbol()})": f"{int(VALUE_TIER_MASS_MIN):,}",
              "Description": "Mass market (digital-first)"},
            {"Tier": "⚪ SMALL",
              f"Min balance ({currency_symbol()})": f"< {int(VALUE_TIER_MASS_MIN):,}",
              "Description": "Small balance (cost-to-serve focus)"},
        ]
        st.dataframe(pd.DataFrame(vt_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**Lifecycle stages** ({len(LIFECYCLE_STAGES)}):")
        lc_rows = [
            {"Stage": "🆕 NEW",
              "Trigger": f"Tenure < {LIFECYCLE_NEW_DAYS} days"},
            {"Stage": "🌱 GROWING",
              "Trigger": f"Tenure {LIFECYCLE_NEW_DAYS}-{LIFECYCLE_GROWING_DAYS} days"},
            {"Stage": "🌳 MATURE",
              "Trigger": f"Tenure ≥ {LIFECYCLE_GROWING_DAYS}d + active txn within {LIFECYCLE_DORMANT_DAYS}d"},
            {"Stage": "💤 DORMANT",
              "Trigger": f"No transactions for ≥ {LIFECYCLE_DORMANT_DAYS}d"},
        ]
        st.dataframe(pd.DataFrame(lc_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**RFM segments** ({len(RFM_SEGMENTS)}):")
        rfm_descriptions = {
            "CHAMPIONS": "High R, F, M — most engaged + spending",
            "LOYAL": "High F, M but lower recency — periodic high-value customers",
            "POTENTIAL_LOYALIST": "Recent + frequent but lower spend — nurture for upsell",
            "NEW_CUSTOMERS": "High R but low F, M — recent acquisitions to onboard",
            "PROMISING": "Recent activity, modest F + M",
            "NEED_ATTENTION": "Mid scores across all dimensions",
            "ABOUT_TO_SLEEP": "Low R + F — risk of disengagement",
            "AT_RISK": "Mid R, F, M — engagement declining",
            "CANNOT_LOSE_THEM": "Low R but high F + M — high-value churn risk!",
            "HIBERNATING": "Low R + F, mid M",
            "LOST": "All metrics low — likely churned",
        }
        rfm_rows = [
            {"Segment": s,
              "Description": rfm_descriptions.get(s, "—")}
            for s in RFM_SEGMENTS
        ]
        st.dataframe(pd.DataFrame(rfm_rows),
                     use_container_width=True, hide_index=True)

        st.caption(
            f"RFM scoring window default: **{DEFAULT_RFM_WINDOW_DAYS} days**. "
            "R/F/M scores are 1-5 quintiles within the customer population. "
            "rfm_segment label maps the (R, F, M) tuple to a categorical segment "
            "for action planning. Per Rule 7 — engine uses deterministic rule-based "
            "logic; ML clustering (k-means/DBSCAN) is downstream work.")

    # ════════════════════════════════════════════════════════════════
    # _SEG_SUB_TABS[5]: Customer Value Segments (Standard #66, integrated v5.96)
    # ════════════════════════════════════════════════════════════════
    with _seg_sub_tabs[5]:
        from utils.customer_value_segments import (
            CustomerValueEngine, ClvInputs,
            CUSTOMER_SEGMENTS, SEGMENT_TIERS, SEGMENT_TIER_BANDS_KES,
            TENURE_BANDS, TENURE_BAND_YEARS,
            ACTIVITY_STATUSES, ATTRITED_THRESHOLD_DAYS, DORMANT_THRESHOLD_DAYS,
            DEFAULT_DISCOUNT_RATE_PCT as _CVS_DEFAULT_DISCOUNT,
        )
        from decimal import Decimal as _D_cvs
        from utils.core_audit import audit_log as _audit_log_cvs

        st.markdown(
            f"**Standard #66 — Customer Value Segments Engine**. "
            f"Adds a third segmentation lens distinct from v5.90 RFM "
            f"(transaction-based behavioral) and v5.95 CLV (balance/yield NPV): "
            f"**banking-archetype × tier-band × tenure × activity-status** "
            f"based on annual_contribution_kes.")
        st.caption(
            f"6 customer segments × 4 tier bands × 4 tenure bands × "
            f"3 activity statuses = **288 possible cells**. "
            f"Tier thresholds ({currency_symbol()} annual contribution): "
            f"PLATINUM ≥ 1M / GOLD ≥ 250K / SILVER ≥ 50K / BRONZE ≥ 0.")

        _cvs_inner = st.tabs([
            "🏷️ Tier Classifier",
            "📅 Tenure & Activity",
            "💰 CLV Calculator (perpetuity)",
            "📊 Segment Aggregate",
            "🌳 Engine Reference",
        ])

        # ────────── Inner[0]: Tier Classifier ──────────
        with _cvs_inner[0]:
            st.markdown(
                "**Tier classification by annual contribution** — "
                "engine `segment_classification(annual_contribution_kes)` "
                "returns one of 4 tiers or None (Rule 6).")
            st.caption(
                f"Boundaries from engine constants: "
                f"PLATINUM ≥ {SEGMENT_TIER_BANDS_KES['PLATINUM'][0]:,} · "
                f"GOLD ≥ {SEGMENT_TIER_BANDS_KES['GOLD'][0]:,} · "
                f"SILVER ≥ {SEGMENT_TIER_BANDS_KES['SILVER'][0]:,} · "
                f"BRONZE ≥ {SEGMENT_TIER_BANDS_KES['BRONZE'][0]:,}.")

            tc1, tc2 = st.columns(2)
            with tc1:
                cvs_contribution = st.number_input(
                    f"Annual contribution ({currency_symbol()})",
                    min_value=-1_000_000.0, value=350_000.0, step=10_000.0,
                    key="cvs_contribution",
                    help="Negative values test Rule 6 (returns None).")
            with tc2:
                cvs_test_none = st.checkbox(
                    "Test None input (Rule 6)",
                    value=False, key="cvs_test_none")

            if st.button("🏷️ Classify tier",
                           key="cvs_classify_btn", type="primary"):
                contrib = None if cvs_test_none else _D_cvs(str(cvs_contribution))
                tier = CustomerValueEngine.segment_classification(contrib)

                if tier is None:
                    st.error(
                        f"⛔ Engine returned **None** "
                        f"(input was {'None' if cvs_test_none else f'{currency_symbol()} {cvs_contribution:,.0f}'}). "
                        "Per Rule 6, engine doesn't silently coerce negative or "
                        "missing values to BRONZE — caller can detect missing "
                        "data and surface to user.")
                else:
                    tier_color = {"PLATINUM": "#9CA3AF", "GOLD": "#F59E0B",
                                   "SILVER": "#6B7280", "BRONZE": "#A16207"}.get(tier)
                    tier_emoji = {"PLATINUM": "💎", "GOLD": "🥇",
                                   "SILVER": "🥈", "BRONZE": "🥉"}.get(tier)

                    st.markdown(
                        f"<div style='padding:18px;background:{tier_color}22;"
                        f"border-left:6px solid {tier_color};border-radius:12px'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"TIER CLASSIFICATION</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{tier_color};margin-top:4px'>"
                        f"{tier_emoji} {tier}</div>"
                        f"<div style='font-size:13px;margin-top:6px'>"
                        f"Annual contribution: <b>{currency_symbol()} {cvs_contribution:,.0f}</b></div></div>",
                        unsafe_allow_html=True)

                _audit_log_cvs("IFRS_ENGINE_USED", uname,
                                f"CustomerValue #66: tier_classify "
                                f"contribution={cvs_contribution:.0f} → {tier}")

        # ────────── Inner[1]: Tenure & Activity ──────────
        with _cvs_inner[1]:
            st.markdown(
                "**Tenure band + activity status** — engine has 2 standalone "
                "label methods: `tenure_band(years_open)` and "
                "`activity_status(days_since_last_txn)`.")
            st.caption(
                f"Tenure: NEW < {TENURE_BAND_YEARS['NEW'][1]}y · "
                f"DEVELOPING < {TENURE_BAND_YEARS['DEVELOPING'][1]}y · "
                f"ESTABLISHED < {TENURE_BAND_YEARS['ESTABLISHED'][1]}y · "
                f"LOYAL ≥ {TENURE_BAND_YEARS['LOYAL'][0]}y. "
                f"Activity: ACTIVE < {DORMANT_THRESHOLD_DAYS}d · "
                f"DORMANT < {ATTRITED_THRESHOLD_DAYS}d · "
                f"ATTRITED ≥ {ATTRITED_THRESHOLD_DAYS}d.")

            tac1, tac2 = st.columns(2)
            with tac1:
                cvs_tenure = st.number_input(
                    "Years open",
                    min_value=0.0, max_value=50.0,
                    value=2.5, step=0.1,
                    key="cvs_tenure")
            with tac2:
                cvs_days = st.number_input(
                    "Days since last txn",
                    min_value=0, max_value=730,
                    value=45, step=5,
                    key="cvs_days")

            if st.button("📅 Classify tenure + activity",
                           key="cvs_ta_btn", type="primary"):
                tband = CustomerValueEngine.tenure_band(cvs_tenure)
                astatus = CustomerValueEngine.activity_status(int(cvs_days))

                tband_emoji = {"NEW": "🆕", "DEVELOPING": "🌱",
                                "ESTABLISHED": "🏛️", "LOYAL": "👑"}.get(tband, "⚪")
                astatus_emoji = {"ACTIVE": "✅", "DORMANT": "⏳",
                                   "ATTRITED": "⛔"}.get(astatus, "⚪")
                astatus_color = {"ACTIVE": "#10B981", "DORMANT": "#F59E0B",
                                   "ATTRITED": "#DC2626"}.get(astatus, "#6B7280")

                k1, k2 = st.columns(2)
                with k1:
                    st.markdown(
                        f"<div style='padding:14px;background:#3B82F622;"
                        f"border-left:6px solid #3B82F6;border-radius:10px'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"TENURE BAND</div>"
                        f"<div style='font-size:22px;font-weight:800;color:#1E40AF;margin-top:4px'>"
                        f"{tband_emoji} {tband}</div>"
                        f"<div style='font-size:12px;margin-top:4px'>"
                        f"Years open: <b>{cvs_tenure}</b></div></div>",
                        unsafe_allow_html=True)
                with k2:
                    st.markdown(
                        f"<div style='padding:14px;background:{astatus_color}22;"
                        f"border-left:6px solid {astatus_color};border-radius:10px'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"ACTIVITY STATUS</div>"
                        f"<div style='font-size:22px;font-weight:800;color:{astatus_color};margin-top:4px'>"
                        f"{astatus_emoji} {astatus}</div>"
                        f"<div style='font-size:12px;margin-top:4px'>"
                        f"Days since last txn: <b>{int(cvs_days)}</b></div></div>",
                        unsafe_allow_html=True)

                # Combined guidance
                if tband == "LOYAL" and astatus == "ATTRITED":
                    st.error(
                        "🚨 **Long-tenure customer attrition** — this is the "
                        "highest-cost churn pattern. Immediate retention "
                        "outreach + post-mortem to prevent future attrition.")
                elif tband == "NEW" and astatus == "DORMANT":
                    st.warning(
                        "⚠ **New customer dormancy** — onboarding likely "
                        "broke down. Engagement campaign within 30 days.")
                elif astatus == "ACTIVE" and tband in ("ESTABLISHED", "LOYAL"):
                    st.success(
                        "✅ **Healthy long-term relationship** — maintain "
                        "via standard relationship management.")

                _audit_log_cvs("IFRS_ENGINE_USED", uname,
                                f"CustomerValue #66: tenure+activity "
                                f"tenure={cvs_tenure}y → {tband}, "
                                f"days={int(cvs_days)} → {astatus}")

        # ────────── Inner[2]: CLV Calculator (perpetuity) ──────────
        with _cvs_inner[2]:
            st.markdown(
                "**CLV calculator — perpetuity-with-attrition model**. "
                "Engine method `clv(ClvInputs)` uses retention rate as "
                "an attrition discount on top of the time-value discount.")
            st.caption(
                "💡 **Distinct from v5.95 CLV** which uses balance × yield × "
                "fixed contribution margin × NPV horizon. v5.96 uses "
                "annual_contribution_kes directly + retention_rate_pct as "
                "attrition factor — more realistic for relationships where "
                "retention isn't certain.")

            cv1, cv2 = st.columns(2)
            with cv1:
                cvs_id = st.text_input("Customer ID",
                                         value="DEMO_CVS_001",
                                         key="cvs_id")
                cvs_annual = st.number_input(
                    f"Annual contribution ({currency_symbol()})",
                    min_value=0.0, value=100_000.0, step=10_000.0,
                    key="cvs_annual")
                cvs_exp_tenure = st.number_input(
                    "Expected tenure (years)",
                    min_value=1, max_value=50,
                    value=10, step=1,
                    key="cvs_exp_tenure")
            with cv2:
                cvs_retention = st.number_input(
                    "Retention rate (%/year)",
                    min_value=50.0, max_value=99.0,
                    value=85.0, step=1.0,
                    key="cvs_retention",
                    help="Probability customer stays each year. "
                         "Lower retention → lower CLV.")
                cvs_discount = st.number_input(
                    "Discount rate (%)",
                    min_value=1.0, max_value=30.0,
                    value=float(_CVS_DEFAULT_DISCOUNT),
                    step=0.5,
                    key="cvs_discount")
                cvs_run_sensitivity = st.checkbox(
                    "Also run retention sensitivity sweep",
                    value=True, key="cvs_run_sens")

            if st.button("💰 Compute CLV",
                           key="cvs_clv_btn", type="primary"):
                inputs = ClvInputs(
                    customer_id=cvs_id,
                    annual_contribution_kes=_D_cvs(str(cvs_annual)),
                    expected_tenure_years=int(cvs_exp_tenure),
                    retention_rate_pct=_D_cvs(str(cvs_retention)),
                    discount_rate_pct=_D_cvs(str(cvs_discount)),
                )
                r = CustomerValueEngine.clv(inputs)

                computed = str(r.get("computed", "False")).lower() == "true"
                clv_kes_raw = r.get("clv_kes")
                if not computed or clv_kes_raw in (None, "None"):
                    st.error(
                        f"⛔ Engine returned `computed=False` "
                        f"(reason: `{r.get('reason', '—')}`). Per Rule 6, "
                        "engine surfaces invalid/missing inputs explicitly "
                        "rather than returning a misleading zero.")
                else:
                    clv_value = float(_D_cvs(str(clv_kes_raw)))
                    st.markdown(
                        f"<div style='padding:18px;background:#10B98122;"
                        f"border-left:6px solid #10B981;border-radius:12px'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"CLV (PERPETUITY-WITH-ATTRITION)</div>"
                        f"<div style='font-size:28px;font-weight:800;color:#10B981;margin-top:4px'>"
                        f"💰 {currency_symbol()} {clv_value:,.0f}</div>"
                        f"<div style='font-size:13px;margin-top:6px'>"
                        f"Annual: {currency_symbol()} {cvs_annual:,.0f} · "
                        f"Tenure: {int(cvs_exp_tenure)}y · "
                        f"Retention: {cvs_retention}% · "
                        f"Discount: {cvs_discount}%</div></div>",
                        unsafe_allow_html=True)

                if cvs_run_sensitivity:
                    st.markdown("### 🔬 Retention rate sensitivity")
                    sens_rows = []
                    for ret in [60, 70, 75, 80, 85, 90, 95]:
                        ri = ClvInputs(
                            customer_id=cvs_id,
                            annual_contribution_kes=_D_cvs(str(cvs_annual)),
                            expected_tenure_years=int(cvs_exp_tenure),
                            retention_rate_pct=_D_cvs(str(ret)),
                            discount_rate_pct=_D_cvs(str(cvs_discount)),
                        )
                        rr = CustomerValueEngine.clv(ri)
                        if str(rr.get("computed", "False")).lower() == "true":
                            sens_rows.append({
                                "Retention rate (%)": ret,
                                f"CLV ({currency_symbol()})": float(_D_cvs(str(rr["clv_kes"]))),
                            })
                    if sens_rows:
                        df_sens = pd.DataFrame(sens_rows)
                        chart_sens = pd.DataFrame({
                            f"CLV ({currency_symbol()})": df_sens[f"CLV ({currency_symbol()})"]
                        }, index=[f"{r}%" for r in df_sens["Retention rate (%)"]])
                        st.line_chart(chart_sens)
                        df_sens_disp = df_sens.copy()
                        df_sens_disp[f"CLV ({currency_symbol()})"] = df_sens_disp[f"CLV ({currency_symbol()})"].apply(
                            lambda v: f"{v:,.0f}")
                        st.dataframe(df_sens_disp,
                                     use_container_width=True, hide_index=True)

                        spread = (max(r[f"CLV ({currency_symbol()})"] for r in sens_rows) -
                                  min(r[f"CLV ({currency_symbol()})"] for r in sens_rows))
                        ratio = (max(r[f"CLV ({currency_symbol()})"] for r in sens_rows) /
                                 min(r[f"CLV ({currency_symbol()})"] for r in sens_rows)
                                 if min(r[f"CLV ({currency_symbol()})"] for r in sens_rows) > 0
                                 else 0)
                        st.caption(
                            f"Spread: {currency_symbol()} {spread:,.0f}. Max/Min ratio: {ratio:.1f}x. "
                            "**Retention rate is the most leveraged assumption** — "
                            "small improvements in retention compound dramatically "
                            "in CLV. Investments in onboarding/engagement that lift "
                            "retention by 5pp can be worth more than equivalent "
                            "acquisition spend.")

                _audit_log_cvs("IFRS_ENGINE_USED", uname,
                                f"CustomerValue #66: clv {cvs_id} "
                                f"annual={cvs_annual:.0f} tenure={cvs_exp_tenure} "
                                f"retention={cvs_retention} computed={computed}")

        # ────────── Inner[3]: Segment Aggregate ──────────
        with _cvs_inner[3]:
            st.markdown(
                "**Segment-level profitability aggregate** — "
                "engine `segment_profitability_aggregate(customers, segment)` "
                "filters customer list by segment and returns "
                "n + total_contribution + avg_contribution.")
            st.caption(
                "Useful for: M&A scenarios (what's the aggregate value of "
                "the HNW book?), tier-shift impact analysis (if 10% MASS "
                "moves to AFFLUENT, what's the lift?).")

            sa_n = st.slider("Demo portfolio size",
                              min_value=10, max_value=100,
                              value=30, step=5,
                              key="sa_n")

            if st.button("📊 Run segment aggregation",
                           key="cvs_sa_btn", type="primary"):
                # Build deterministic synthetic portfolio across 6 segments
                import random as _random_sa
                _random_sa.seed(42)  # deterministic
                n = int(sa_n)
                segments_pool = list(CUSTOMER_SEGMENTS)
                # Distribution: 50% MASS, 20% AFFLUENT, 10% HNW, 10% SME, 8% CORPORATE, 2% GOVERNMENT
                seg_distribution = {
                    "MASS": 0.50, "AFFLUENT": 0.20, "HNW": 0.10,
                    "SME": 0.10, "CORPORATE": 0.08, "GOVERNMENT": 0.02,
                }
                contribution_ranges = {
                    "MASS": (5_000, 80_000),
                    "AFFLUENT": (80_000, 400_000),
                    "HNW": (400_000, 3_000_000),
                    "SME": (200_000, 2_000_000),
                    "CORPORATE": (1_000_000, 15_000_000),
                    "GOVERNMENT": (5_000_000, 50_000_000),
                }
                customers_pool = []
                for i in range(n):
                    # Pick segment by distribution
                    pick = _random_sa.random()
                    cum = 0
                    seg_pick = "MASS"
                    for seg, prob in seg_distribution.items():
                        cum += prob
                        if pick <= cum:
                            seg_pick = seg
                            break
                    lo, hi = contribution_ranges[seg_pick]
                    contrib = _random_sa.uniform(lo, hi)
                    customers_pool.append({
                        "customer_id": f"SA_C{i:03d}",
                        "segment": seg_pick,
                        "annual_contribution_kes": contrib,
                    })

                # Run aggregate per segment
                rows = []
                for seg in CUSTOMER_SEGMENTS:
                    r = CustomerValueEngine.segment_profitability_aggregate(
                        customers_pool, seg)
                    n_in_seg = int(r["n"])
                    total = float(_D_cvs(str(r["total_contribution_kes"])))
                    avg = (float(_D_cvs(str(r["avg_contribution_kes"])))
                            if r.get("avg_contribution_kes") not in (None, "None")
                            else None)
                    rows.append({
                        "Segment": seg,
                        "N customers": n_in_seg,
                        "% of portfolio":
                            f"{n_in_seg/n*100:.1f}%" if n else "—",
                        f"Total contribution ({currency_symbol()})":
                            f"{total:,.0f}",
                        f"Avg contribution ({currency_symbol()})":
                            f"{avg:,.0f}" if avg is not None else "—",
                    })

                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # Total snapshot
                total_portfolio = sum(c["annual_contribution_kes"]
                                       for c in customers_pool)
                k1, k2, k3 = st.columns(3)
                k1.metric("Portfolio size", n)
                k2.metric("Total annual contribution",
                           f"{currency_symbol()} {total_portfolio:,.0f}")
                k3.metric("Avg per customer",
                           f"{currency_symbol()} {total_portfolio/n:,.0f}")

                # Bar chart by segment
                segment_totals = {seg: 0.0 for seg in CUSTOMER_SEGMENTS}
                for c in customers_pool:
                    segment_totals[c["segment"]] += c["annual_contribution_kes"]
                chart_seg = pd.DataFrame({
                    f"Total contribution ({currency_symbol()})": list(segment_totals.values())
                }, index=list(segment_totals.keys()))
                st.markdown("**Total contribution by segment (bar):**")
                st.bar_chart(chart_seg)

                # Concentration insight (Pareto-like)
                gov_share = (segment_totals["GOVERNMENT"] / total_portfolio
                             if total_portfolio else 0)
                hnw_share = (segment_totals["HNW"] / total_portfolio
                             if total_portfolio else 0)
                top2_share = gov_share + hnw_share
                if top2_share >= 0.5:
                    st.warning(
                        f"⚠ **{top2_share*100:.0f}% concentration** in "
                        f"GOVERNMENT + HNW segments — top-of-pyramid risk. "
                        "Segment diversification considerations apply.")

                _audit_log_cvs("IFRS_ENGINE_USED", uname,
                                f"CustomerValue #66: segment_aggregate "
                                f"portfolio={n} total={total_portfolio:.0f}")

        # ────────── Inner[4]: Engine Reference ──────────
        with _cvs_inner[4]:
            st.markdown("**Engine Constants Reference** (single source of truth)")

            st.markdown(f"**6 customer segments** (banking archetypes):")
            cs_rows = [{"Segment": s} for s in CUSTOMER_SEGMENTS]
            st.dataframe(pd.DataFrame(cs_rows),
                         use_container_width=True, hide_index=True)

            st.markdown(
                f"**4 segment tiers** (annual contribution thresholds):")
            tier_emoji = {"PLATINUM": "💎", "GOLD": "🥇",
                           "SILVER": "🥈", "BRONZE": "🥉"}
            tier_rows = []
            for tier in SEGMENT_TIERS:
                lo, hi = SEGMENT_TIER_BANDS_KES[tier]
                tier_rows.append({
                    "Tier": f"{tier_emoji.get(tier, '⚪')} {tier}",
                    f"Lower bound ({currency_symbol()})": f"{lo:,}",
                    f"Upper bound ({currency_symbol()})": (f"{hi:,}"
                                            if hi < 999_999_999_999 else "∞"),
                })
            st.dataframe(pd.DataFrame(tier_rows),
                         use_container_width=True, hide_index=True)

            st.markdown(f"**4 tenure bands**:")
            tband_rows = []
            for tband in TENURE_BANDS:
                lo, hi = TENURE_BAND_YEARS[tband]
                tband_rows.append({
                    "Band": tband,
                    "Years (lower)": lo,
                    "Years (upper)": hi if hi < 999 else "∞",
                })
            st.dataframe(pd.DataFrame(tband_rows),
                         use_container_width=True, hide_index=True)

            st.markdown(f"**3 activity statuses**:")
            ac_rows = [
                {"Status": "ACTIVE",
                  "Threshold (days since last txn)": f"< {DORMANT_THRESHOLD_DAYS}"},
                {"Status": "DORMANT",
                  "Threshold (days since last txn)":
                      f"{DORMANT_THRESHOLD_DAYS} - {ATTRITED_THRESHOLD_DAYS - 1}"},
                {"Status": "ATTRITED",
                  "Threshold (days since last txn)": f"≥ {ATTRITED_THRESHOLD_DAYS}"},
            ]
            st.dataframe(pd.DataFrame(ac_rows),
                         use_container_width=True, hide_index=True)

            st.markdown("**5 engine methods (all STATIC):**")
            m_rows = [
                {"Method": "segment_classification(annual_contribution_kes)",
                  "Returns": "tier name | None (Rule 6)"},
                {"Method": "tenure_band(years_open)",
                  "Returns": "band name | None"},
                {"Method": "activity_status(days_since_last_txn)",
                  "Returns": "status | None"},
                {"Method": "clv(ClvInputs)",
                  "Returns": "dict with clv_kes + computed flag + reason"},
                {"Method": "segment_profitability_aggregate(customers, segment)",
                  "Returns": "dict with n + total_contribution + avg_contribution"},
            ]
            st.dataframe(pd.DataFrame(m_rows),
                         use_container_width=True, hide_index=True)

            st.markdown("**Three segmentation lenses comparison:**")
            lens_rows = [
                {"Lens": "v5.90 RFM",
                  "Engine": "customer_segmentation",
                  "Primitive": "transactions (recency, frequency, monetary)",
                  "Output": "11 RFM segments (CHAMPIONS, LOST, etc.)"},
                {"Lens": "v5.95 CLV",
                  "Engine": "customer_lifetime_value",
                  "Primitive": "balances × product yields × NPV",
                  "Output": "4 profitability segments (HIGH_VALUE, etc.)"},
                {"Lens": "v5.96 Customer Value",
                  "Engine": "customer_value_segments",
                  "Primitive": "annual contribution + retention",
                  "Output": "6 segments × 4 tiers × 4 tenure × 3 activity = 288 cells"},
            ]
            st.dataframe(pd.DataFrame(lens_rows),
                         use_container_width=True, hide_index=True)

            st.caption(
                "💡 **Three lenses are independent and complementary**. "
                "A customer can be CHAMPIONS (RFM, high transaction activity) + "
                "MEDIUM (CLV, modest balance × yield) + GOLD/AFFLUENT/LOYAL/ACTIVE "
                "(v5.96, contributes 350K/year as long-term affluent customer). "
                "Production deployment may want a **unified composite score** "
                "combining all three lenses; engine doesn't provide this directly "
                "but caller can compose. Rule 7 honored — all 3 engines are "
                "deterministic rule-based (no silent ML).")


# ════════════════════════════════════════════════════════════════
# TAB 6: Customer Lifetime Value (Standard #95, integrated v5.75)
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    from utils.customer_lifetime_value import (
        CustomerLifetimeValueEngine, CustomerForCLV, ProductHolding,
        PRODUCT_TYPES, PRODUCT_YIELDS_PCT, PROFITABILITY_SEGMENTS,
        CLV_HIGH_VALUE_MIN, CLV_MEDIUM_MIN,
        DEFAULT_DISCOUNT_RATE_PCT, DEFAULT_HORIZON_YEARS,
        DEFAULT_CONTRIBUTION_MARGIN_PCT, DEFAULT_ANNUAL_SERVICING_COST_KES,
    )
    from decimal import Decimal as _D_clv
    from utils.core_audit import audit_log

    st.markdown(
        "**Standard #95 — Customer Lifetime Value (CLV)** "
        "engine. NPV of customer contribution over a "
        f"{DEFAULT_HORIZON_YEARS}-year horizon at "
        f"{DEFAULT_DISCOUNT_RATE_PCT}% discount rate."
    )
    st.caption(
        f"Profitability segments: HIGH_VALUE ≥ {currency_symbol()} {CLV_HIGH_VALUE_MIN:,.0f} · "
        f"MEDIUM ≥ {currency_symbol()} {CLV_MEDIUM_MIN:,.0f} · LOW ≥ 0 · UNPROFITABLE < 0. "
        f"Default contribution margin: {DEFAULT_CONTRIBUTION_MARGIN_PCT}%; "
        f"annual servicing cost: {currency_symbol()} {DEFAULT_ANNUAL_SERVICING_COST_KES:,.0f}."
    )

    clv_sub_tabs = st.tabs([
        "💰 Customer CLV Calculator",
        "🌳 Product Yield Reference",
        "📊 Portfolio CLV Distribution",
        "💵 Customer P&L (Standard #57, v5.92)",
        "🎯 Allocation Method Comparison (#57, v5.92)",
        "🌳 Profitability Engine Reference (#57, v5.92)",
        "📦 CLV Depth (Standard #95, v5.95)",
    ])

    # ---- Customer CLV calculator ----
    with clv_sub_tabs[0]:
        st.markdown("**Compute CLV for any customer** (standalone tool — uses your inputs).")
        c1, c2 = st.columns(2)
        with c1:
            clv_cust_id = st.text_input("Customer ID", value="C001",
                                          key="clv_cust_id")
            clv_cif_id = st.text_input("CIF ID", value="100123",
                                         key="clv_cif_id")
            clv_tenure = st.number_input("Tenure (years)",
                                           min_value=0.0, value=5.0, step=0.5,
                                           key="clv_tenure")
        with c2:
            clv_horizon = st.number_input("Horizon (years)",
                                            min_value=1, value=DEFAULT_HORIZON_YEARS,
                                            step=1, key="clv_horizon")
            clv_disc = st.number_input("Discount rate (%)",
                                         min_value=0.0,
                                         value=float(DEFAULT_DISCOUNT_RATE_PCT),
                                         step=0.5, key="clv_disc")
            clv_margin = st.number_input("Contribution margin (%)",
                                           min_value=0.0, max_value=100.0,
                                           value=float(DEFAULT_CONTRIBUTION_MARGIN_PCT),
                                           step=5.0, key="clv_margin")

        st.markdown("**Product holdings** (up to 4):")
        clv_holdings_data = []
        for i in range(4):
            with st.expander(f"Holding {i+1}", expanded=(i < 2)):
                hc1, hc2 = st.columns(2)
                with hc1:
                    p_type = st.selectbox(
                        "Product type",
                        ["(none)"] + list(PRODUCT_TYPES),
                        index=[0, 1, 5, 0][i] if i < 4 else 0,
                        key=f"clv_h_type_{i}")
                with hc2:
                    p_bal = st.number_input(
                        f"Balance / outstanding ({currency_symbol()})",
                        min_value=0.0,
                        value=[500_000.0, 3_000_000.0, 0.0, 0.0][i] if i < 4 else 0.0,
                        step=10_000.0, key=f"clv_h_bal_{i}")
                if p_type != "(none)" and p_bal > 0:
                    clv_holdings_data.append({"type": p_type, "bal": p_bal})

        if st.button("Compute CLV", key="clv_compute_btn", type="primary"):
            if not clv_holdings_data:
                st.warning("Add at least one product holding with non-zero balance.")
            else:
                holdings = [
                    ProductHolding(
                        holding_id=f"H{idx+1}",
                        customer_id=clv_cust_id,
                        product_type=h["type"],
                        balance_or_outstanding_kes=_D_clv(str(h["bal"])))
                    for idx, h in enumerate(clv_holdings_data)
                ]
                customer = CustomerForCLV(
                    customer_id=clv_cust_id, cif_id=clv_cif_id,
                    tenure_years=_D_clv(str(clv_tenure)),
                    holdings=holdings)
                r = CustomerLifetimeValueEngine.clv_npv(
                    customer,
                    horizon_years=int(clv_horizon),
                    discount_rate_pct=_D_clv(str(clv_disc)),
                    margin_pct=_D_clv(str(clv_margin)))
                clv_kes = r.get("clv_npv_kes")
                if clv_kes is not None:
                    clv_d = _D_clv(str(clv_kes))
                    seg = CustomerLifetimeValueEngine.profitability_segment(clv_d)
                    seg_colors = {
                        "HIGH_VALUE": "#059669", "MEDIUM": "#3B82F6",
                        "LOW": "#F59E0B", "UNPROFITABLE": "#DC2626",
                        "UNKNOWN": "#6B7280",
                    }
                    color = seg_colors.get(seg, "#6B7280")
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("CLV NPV (KES)",
                               f"{clv_d:,.2f}",
                               help=f"Sum of discounted contribution over "
                                    f"{clv_horizon} years")
                    k2.metric("Annual revenue (KES)",
                               f"{_D_clv(str(r.get('annual_revenue_kes', 0))):,.2f}")
                    k3.metric(f"Annual contribution ({currency_symbol()})",
                               f"{_D_clv(str(r.get('annual_contribution_kes', 0))):,.2f}",
                               help=f"Revenue × {clv_margin}% margin "
                                    f"− KES {DEFAULT_ANNUAL_SERVICING_COST_KES} servicing")
                    with k4:
                        st.markdown(
                            f"<div style='padding:12px;background:{color}22;"
                            f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                            f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                            f"SEGMENT</div>"
                            f"<div style='font-size:22px;font-weight:800;color:{color};margin-top:4px'>"
                            f"{seg}</div></div>", unsafe_allow_html=True)

                    # Per-holding breakdown
                    scored = r.get("scored_holdings", [])
                    if scored:
                        st.markdown("**Per-holding revenue:**")
                        hdf = pd.DataFrame(scored)
                        st.dataframe(hdf, use_container_width=True, hide_index=True)

                    excluded = r.get("excluded_holdings_count", 0)
                    if excluded:
                        st.warning(
                            f"⚠ {excluded} holding(s) excluded — missing balance "
                            f"or unknown product type (Rule 6 transparency).")

                    audit_log("IFRS_ENGINE_USED", uname,
                                f"CLV #95: Customer={clv_cust_id} CLV={clv_d} segment={seg}")
                else:
                    st.error(f"Could not compute. Reason: {r.get('reason', 'unknown')}")

    # ---- Product yield reference ----
    with clv_sub_tabs[1]:
        st.markdown("**Product Yield Reference** (engine constant — single source of truth)")
        st.caption(
            "These yields are bound byte-for-byte in the engine and used in "
            "every CLV computation. Changes to yields require engine code review."
        )
        yield_rows = [
            {"Product type": p,
              "Yield (% per year)": float(PRODUCT_YIELDS_PCT.get(p, 0)),
              "Notes": {
                  "SAVINGS": "Spread on deposit base",
                  "CURRENT": "Free funds — high spread",
                  "TERM_DEPOSIT": "Locked-in spread",
                  "PERSONAL_LOAN": "Lending margin",
                  "MORTGAGE": "Long-term lending margin",
                  "CREDIT_CARD": "High-margin revolving",
                  "TRADE_FINANCE": "Fee-based",
                  "INVESTMENT": "AUM-based fee",
              }.get(p, "")}
            for p in PRODUCT_TYPES
        ]
        st.dataframe(pd.DataFrame(yield_rows),
                     use_container_width=True, hide_index=True)

    # ---- Portfolio CLV distribution ----
    with clv_sub_tabs[2]:
        st.markdown(
            "**Portfolio CLV — derived from existing customer intelligence data**")
        st.caption(
            "Uses each customer's pre-computed `clv_estimate` from "
            "`customer_intelligence.json` and bins into the 4 engine "
            "PROFITABILITY_SEGMENTS for portfolio-level visibility."
        )
        if not ci_raw:
            st.info("Customer intelligence data not loaded.")
        else:
            seg_counts = {s: 0 for s in PROFITABILITY_SEGMENTS}
            seg_value = {s: 0.0 for s in PROFITABILITY_SEGMENTS}
            for cif, info in ci_raw.items():
                clv_est = info.get("clv_estimate", 0) or 0
                seg = CustomerLifetimeValueEngine.profitability_segment(
                    _D_clv(str(clv_est)))
                if seg in seg_counts:
                    seg_counts[seg] += 1
                    seg_value[seg] += float(clv_est)

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("HIGH_VALUE",
                       seg_counts.get("HIGH_VALUE", 0),
                       f"{currency_symbol()} {seg_value.get('HIGH_VALUE', 0)/1e6:.1f}M")
            k2.metric("MEDIUM",
                       seg_counts.get("MEDIUM", 0),
                       f"{currency_symbol()} {seg_value.get('MEDIUM', 0)/1e6:.1f}M")
            k3.metric("LOW",
                       seg_counts.get("LOW", 0),
                       f"{currency_symbol()} {seg_value.get('LOW', 0)/1e6:.1f}M")
            k4.metric("UNPROFITABLE",
                       seg_counts.get("UNPROFITABLE", 0),
                       f"{currency_symbol()} {seg_value.get('UNPROFITABLE', 0)/1e6:.1f}M")

            seg_df = pd.DataFrame([
                {"Segment": s,
                  "Customers": seg_counts.get(s, 0),
                  "Total CLV (KES M)": round(seg_value.get(s, 0)/1e6, 2)}
                for s in PROFITABILITY_SEGMENTS])
            st.dataframe(seg_df, use_container_width=True, hide_index=True)

            audit_log("IFRS_ENGINE_USED", uname,
                        f"CLV #95: Portfolio scan {sum(seg_counts.values())} customers")

    # ════════════════════════════════════════════════════════════════
    # CLV_SUB_TABS[3]: Customer P&L (Standard #57, integrated v5.92)
    # ════════════════════════════════════════════════════════════════
    with clv_sub_tabs[3]:
        from utils.customer_profitability import (
            CustomerProfitabilityEngine, CustomerPnL,
            ALLOCATION_METHODS, DEFAULT_ALLOCATION_METHOD,
        )
        from decimal import Decimal as _D_cp
        from utils.core_audit import audit_log as _audit_log_cp

        st.markdown(
            f"**Standard #57 — Customer Profitability Engine**. "
            f"Computes per-customer P&L (revenue + direct costs + allocated indirect costs → PBT) "
            f"using one of {len(ALLOCATION_METHODS)} allocation methods.")
        st.caption(
            f"Default: {DEFAULT_ALLOCATION_METHOD}. "
            "Engine supports FTP-based interest income/expense reconstruction. "
            "Per Rule 6, missing inputs are surfaced in `meta.missing_components` not silently zeroed.")

        st.markdown("**Build a customer P&L** — provide revenue + direct costs + overhead allocation inputs:")

        c1, c2 = st.columns(2)
        with c1:
            cp_id = st.text_input("Customer ID",
                                    value="CUST_PNL_001", key="cp_id")
            cp_period = st.text_input("Period",
                                        value="2025-12", key="cp_period")
            cp_segment = st.selectbox("Segment",
                                         ["Premium", "SME", "Retail", "HNW"],
                                         key="cp_segment")
            cp_method = st.selectbox(
                "Allocation method",
                list(ALLOCATION_METHODS),
                index=list(ALLOCATION_METHODS).index(DEFAULT_ALLOCATION_METHOD),
                key="cp_method",
                help="equal_per_customer divides overhead by customer count. "
                      "revenue_weighted allocates by share of bank revenue. "
                      "asset_weighted by share of assets. "
                      "activity_weighted by share of activity units.")

        with c2:
            st.markdown("**Revenue components (KES)**:")
            cp_rev_int = st.number_input("Interest income",
                                            min_value=0.0, value=250000.0, step=10000.0,
                                            key="cp_rev_int")
            cp_rev_fee = st.number_input("Fee income",
                                            min_value=0.0, value=85000.0, step=5000.0,
                                            key="cp_rev_fee")
            cp_rev_other = st.number_input("Other income",
                                              min_value=0.0, value=15000.0, step=1000.0,
                                              key="cp_rev_other")

        with st.expander("Direct costs (KES)"):
            dc1, dc2, dc3 = st.columns(3)
            cp_dc_int = dc1.number_input("Interest expense",
                                            min_value=0.0, value=80000.0, step=5000.0,
                                            key="cp_dc_int")
            cp_dc_llp = dc2.number_input("Loan loss provisions",
                                            min_value=0.0, value=25000.0, step=2500.0,
                                            key="cp_dc_llp")
            cp_dc_txn = dc3.number_input("Transaction costs",
                                            min_value=0.0, value=12000.0, step=1000.0,
                                            key="cp_dc_txn")

        with st.expander("Overhead pool + allocation inputs"):
            oc1, oc2 = st.columns(2)
            cp_overhead = oc1.number_input("Overhead pool (KES B, period)",
                                              min_value=0.0, value=50.0, step=1.0,
                                              key="cp_overhead",
                                              help="Bank-wide indirect cost pool for the period.")
            cp_total_revenue = oc2.number_input("Bank total revenue (KES B)",
                                                  min_value=0.0, value=25.0, step=1.0,
                                                  key="cp_total_revenue")
            cp_customer_count = oc1.number_input("Total active customers",
                                                    min_value=1, value=700000, step=10000,
                                                    key="cp_customer_count")
            cp_my_assets_m = oc2.number_input("Customer assets (KES M)",
                                                 min_value=0.0, value=5.0, step=0.5,
                                                 key="cp_my_assets_m")

        if st.button("💵 Compute customer P&L",
                       key="cp_pnl_btn", type="primary"):
            # Build DI callbacks from form inputs
            my_revenue_total = (cp_rev_int + cp_rev_fee + cp_rev_other)

            def _customer_lookup(cid):
                return {"customer_id": cid, "cif_id": cid,
                          "segment": cp_segment, "name": f"Test {cid}"}

            def _revenue(cid, period):
                return {
                    "interest_income": _D_cp(str(cp_rev_int)),
                    "fee_income": _D_cp(str(cp_rev_fee)),
                    "other_income": _D_cp(str(cp_rev_other)),
                }

            def _direct_costs(cid, period):
                return {
                    "interest_expense": _D_cp(str(cp_dc_int)),
                    "loan_loss_provisions": _D_cp(str(cp_dc_llp)),
                    "transaction_costs": _D_cp(str(cp_dc_txn)),
                }

            def _overhead_pool(period):
                return _D_cp(str(cp_overhead * 1e9))

            def _alloc_inputs(cid, period):
                return {
                    "customer_count": int(cp_customer_count),
                    "my_revenue": float(my_revenue_total),
                    "total_revenue": float(cp_total_revenue * 1e9),
                    "my_assets": float(cp_my_assets_m * 1e6),
                    "total_assets": float(cp_total_revenue * 1e9 * 28),  # rough total assets ~28x revenue
                    "my_activity_units": 100,
                    "total_activity_units": 50_000_000,
                }

            engine_cp = CustomerProfitabilityEngine(
                customer_lookup_fn=_customer_lookup,
                revenue_fn=_revenue,
                direct_costs_fn=_direct_costs,
                overhead_pool_fn=_overhead_pool,
                allocation_inputs_fn=_alloc_inputs,
                allocation_method=cp_method,
            )
            r = engine_cp.calculate_customer_pnl(cp_id, cp_period)

            if not r:
                st.error("⛔ Engine returned empty — customer not found in lookup.")
            else:
                # Top-line P&L summary
                pbt = float(_D_cp(str(r["pbt"])))
                pbt_margin = r.get("pbt_margin")
                total_revenue = float(_D_cp(str(r["total_revenue"])))
                total_direct = float(_D_cp(str(r["total_direct_costs"])))
                total_indirect = float(_D_cp(str(r["total_indirect_costs"])))

                # Verdict banner
                if pbt > 0:
                    color = "#10B981"
                    emoji = "✅"
                    label = "PROFITABLE"
                elif pbt == 0:
                    color = "#6B7280"
                    emoji = "⚪"
                    label = "BREAK-EVEN"
                else:
                    color = "#DC2626"
                    emoji = "❌"
                    label = "UNPROFITABLE"
                margin_str = (f"{float(_D_cp(str(pbt_margin)))*100:.2f}%"
                              if pbt_margin not in (None, "None") else "—")

                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"CUSTOMER P&L</div>"
                    f"<div style='font-size:28px;font-weight:800;color:{color};margin-top:6px'>"
                    f"{emoji} {label}: {currency_symbol()} {pbt:,.0f}</div>"
                    f"<div style='font-size:14px;margin-top:6px'>"
                    f"PBT Margin: <b>{margin_str}</b> · Allocation: <b>{cp_method}</b></div></div>",
                    unsafe_allow_html=True)

                # 3-line breakdown
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total revenue", f"{currency_symbol()} {total_revenue:,.0f}")
                k2.metric("Direct costs", f"{currency_symbol()} {total_direct:,.0f}")
                k3.metric("Indirect costs (allocated)", f"{currency_symbol()} {total_indirect:,.0f}")
                k4.metric("PBT", f"{currency_symbol()} {pbt:,.0f}")

                # Component breakdown
                rev_comp = r.get("revenue", {})
                dc_comp = r.get("direct_costs", {})
                ic_comp = r.get("indirect_costs", {})

                st.markdown("**Revenue components:**")
                rev_rows = [{"Component": k.replace("_", " ").title(),
                              "Amount (KES)": float(_D_cp(str(v)))}
                            for k, v in rev_comp.items()]
                rev_rows.append({"Component": "**TOTAL**",
                                  "Amount (KES)": total_revenue})
                st.dataframe(pd.DataFrame(rev_rows),
                             use_container_width=True, hide_index=True)

                st.markdown("**Cost components (direct + allocated):**")
                cost_rows = []
                for k, v in dc_comp.items():
                    cost_rows.append({"Type": "Direct",
                                       "Component": k.replace("_", " ").title(),
                                       "Amount (KES)": float(_D_cp(str(v)))})
                for k, v in ic_comp.items():
                    cost_rows.append({"Type": "Indirect",
                                       "Component": k.replace("_", " ").title(),
                                       "Amount (KES)": float(_D_cp(str(v)))})
                cost_rows.append({"Type": "**TOTAL**",
                                   "Component": "All costs",
                                   "Amount (KES)": total_direct + total_indirect})
                st.dataframe(pd.DataFrame(cost_rows),
                             use_container_width=True, hide_index=True)

                # Meta + transparency
                meta = r.get("meta", {})
                missing = meta.get("missing_components", [])
                if missing:
                    st.warning(
                        f"⚠ Missing components (Rule 6): {', '.join(missing)}")

                with st.expander("Engine metadata (for traceability)"):
                    st.json({
                        "allocation_method": meta.get("allocation_method"),
                        "ftp_mode": meta.get("ftp_mode"),
                        "balance_basis": meta.get("balance_basis"),
                        "input_currency": meta.get("input_currency"),
                        "tolerance_excel_pct": meta.get("tolerance_excel_pct"),
                        "generated_at": meta.get("generated_at"),
                    })

                _audit_log_cp("IFRS_ENGINE_USED", uname,
                               f"CustomerProfitability #57: P&L {cp_id} period={cp_period} "
                               f"method={cp_method} pbt={pbt:.0f} margin={margin_str}")

    # ════════════════════════════════════════════════════════════════
    # CLV_SUB_TABS[4]: Allocation Method Comparison (Standard #57, v5.92)
    # ════════════════════════════════════════════════════════════════
    with clv_sub_tabs[4]:
        from utils.customer_profitability import (
            CustomerProfitabilityEngine, ALLOCATION_METHODS,
        )
        from decimal import Decimal as _D_cmp
        from utils.core_audit import audit_log as _audit_log_cmp

        st.markdown(
            "**Allocation Method Sensitivity** — same customer, same revenues + direct costs, "
            "but **4 different allocation methods produce 4 different PBT outcomes**.")
        st.caption(
            "💡 This is the most important strategic decision in customer profitability. "
            "Different methods favor different customer profiles: equal-per-customer favors "
            "high-revenue customers; revenue-weighted is fairest at portfolio level; "
            "asset-weighted recognizes balance-sheet contribution; "
            "activity-weighted ties cost to actual usage.")

        if st.button("🎯 Compare 4 allocation methods",
                       key="cp_cmp_btn", type="primary"):
            # Use same fixed inputs across all 4 methods
            FIXED_REV_INT, FIXED_REV_FEE, FIXED_REV_OTHER = 250000, 85000, 15000
            FIXED_DC_INT, FIXED_DC_LLP, FIXED_DC_TXN = 80000, 25000, 12000
            FIXED_OVERHEAD = 50_000_000_000
            FIXED_TOTAL_REV = 25_000_000_000

            def _cust_lookup(cid):
                return {"customer_id": cid, "cif_id": cid, "segment": "Premium"}
            def _rev(cid, p):
                return {"interest_income": _D_cmp(str(FIXED_REV_INT)),
                        "fee_income": _D_cmp(str(FIXED_REV_FEE)),
                        "other_income": _D_cmp(str(FIXED_REV_OTHER))}
            def _dc(cid, p):
                return {"interest_expense": _D_cmp(str(FIXED_DC_INT)),
                        "loan_loss_provisions": _D_cmp(str(FIXED_DC_LLP)),
                        "transaction_costs": _D_cmp(str(FIXED_DC_TXN))}
            def _oh(p):
                return _D_cmp(str(FIXED_OVERHEAD))
            def _alloc(cid, p):
                return {"customer_count": 700000,
                        "my_revenue": FIXED_REV_INT + FIXED_REV_FEE + FIXED_REV_OTHER,
                        "total_revenue": FIXED_TOTAL_REV,
                        "my_assets": 5_000_000,
                        "total_assets": 700_000_000_000,
                        "my_activity_units": 1200,
                        "total_activity_units": 50_000_000}

            results = []
            for method in ALLOCATION_METHODS:
                e = CustomerProfitabilityEngine(
                    customer_lookup_fn=_cust_lookup, revenue_fn=_rev,
                    direct_costs_fn=_dc, overhead_pool_fn=_oh,
                    allocation_inputs_fn=_alloc, allocation_method=method)
                r = e.calculate_customer_pnl("CIF_CMP", "2025-12")
                results.append({
                    "Method": method,
                    "Indirect (KES)": float(_D_cmp(str(r.get("total_indirect_costs", 0)))),
                    "PBT (KES)": float(_D_cmp(str(r.get("pbt", 0)))),
                    "PBT Margin": (f"{float(_D_cmp(str(r['pbt_margin'])))*100:.2f}%"
                                    if r.get("pbt_margin") not in (None, "None")
                                    else "—"),
                })

            st.markdown("**Same customer (Revenue=350K, Direct costs=117K), 4 allocation outcomes:**")
            comp_df = pd.DataFrame(results)
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

            # Bar chart of PBT
            chart_data = pd.DataFrame({
                "PBT (KES)": [r["PBT (KES)"] for r in results]
            }, index=[r["Method"] for r in results])
            st.markdown("**PBT by allocation method:**")
            st.bar_chart(chart_data)

            # Insight
            pbts = [r["PBT (KES)"] for r in results]
            spread = max(pbts) - min(pbts)
            st.warning(
                f"⚠ **PBT spread across methods: {currency_symbol()} {spread:,.0f}** "
                f"(min={min(pbts):,.0f}, max={max(pbts):,.0f}). "
                "Same customer can be 'profitable' OR 'unprofitable' depending on "
                "allocation choice. Consistency in method matters more than the "
                "specific choice — the bank should pick one and stick with it for "
                "performance management.")

            _audit_log_cmp("IFRS_ENGINE_USED", uname,
                            f"CustomerProfitability #57: allocation comparison "
                            f"spread={spread:.0f} min_pbt={min(pbts):.0f} max_pbt={max(pbts):.0f}")

    # ════════════════════════════════════════════════════════════════
    # CLV_SUB_TABS[5]: Engine Reference (Standard #57, v5.92)
    # ════════════════════════════════════════════════════════════════
    with clv_sub_tabs[5]:
        from utils.customer_profitability import (
            ALLOCATION_METHODS, DEFAULT_ALLOCATION_METHOD,
            EXCEL_MATCH_TOLERANCE,
        )

        st.markdown("**Engine Constants Reference** (single source of truth)")

        st.markdown(f"**Allocation methods** ({len(ALLOCATION_METHODS)}):")
        method_descriptions = {
            "equal_per_customer":
                "Overhead ÷ total active customer count. Simple, but penalizes "
                "low-revenue customers disproportionately.",
            "revenue_weighted":
                "Customer's share of bank-wide revenue × overhead pool. "
                "Most common in retail banking. **Default.**",
            "asset_weighted":
                "Customer's share of bank-wide assets (loans + deposits) × overhead. "
                "Recognizes balance-sheet contribution; favors HNW.",
            "activity_weighted":
                "Customer's share of bank-wide activity units (transactions, branch "
                "visits, etc.) × overhead. Best matches cost causation.",
        }
        method_rows = [
            {"Method": m,
              "Description": method_descriptions.get(m, "—"),
              "Default": "✓" if m == DEFAULT_ALLOCATION_METHOD else ""}
            for m in ALLOCATION_METHODS
        ]
        st.dataframe(pd.DataFrame(method_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Engine inputs** (all DI-injected, REQUIRED):")
        input_rows = [
            {"Callback": "customer_lookup_fn(customer_id)",
              "Returns": "dict | None — customer profile (CIF, segment)"},
            {"Callback": "revenue_fn(customer_id, period)",
              "Returns": "dict[str, Decimal] — revenue components"},
            {"Callback": "direct_costs_fn(customer_id, period)",
              "Returns": "dict[str, Decimal] — direct cost components"},
            {"Callback": "overhead_pool_fn(period)",
              "Returns": "Decimal — bank-wide indirect cost pool"},
            {"Callback": "allocation_inputs_fn(customer_id, period)",
              "Returns": "dict — customer_count, my_revenue, total_revenue, my_assets, total_assets, etc."},
            {"Callback": "ftp_inputs_fn(customer_id, period) [optional]",
              "Returns": "dict — ftp_rate, deposit_balance, loan_balance, period_fraction (only when ftp_mode='on')"},
        ]
        st.dataframe(pd.DataFrame(input_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Engine output** (returns dict with these top-level keys):")
        output_rows = [
            {"Key": "pbt", "Type": "float",
              "Description": "Profit before tax (revenue - direct - indirect)"},
            {"Key": "pbt_margin", "Type": "float | None",
              "Description": "PBT / total_revenue (None if revenue=0)"},
            {"Key": "revenue", "Type": "dict",
              "Description": "Per-component revenue breakdown"},
            {"Key": "direct_costs", "Type": "dict",
              "Description": "Per-component direct cost breakdown"},
            {"Key": "indirect_costs", "Type": "dict",
              "Description": "Allocated indirect costs (single 'allocated_overhead' key)"},
            {"Key": "total_revenue / total_direct_costs / total_indirect_costs",
              "Type": "float", "Description": "Sums of components"},
            {"Key": "meta", "Type": "dict",
              "Description": "customer_id, period, allocation_method, ftp_mode, missing_components, generated_at"},
        ]
        st.dataframe(pd.DataFrame(output_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**FTP mode behavior:**")
        st.caption(
            "When `ftp_mode='on'`, engine reconstructs interest income/expense from "
            "FTP rates rather than using the revenue/direct_costs callbacks for those "
            "items. **Per Rule 6, missing FTP inputs are surfaced** in `meta.ftp_missing` "
            "rather than silently zeroed — production deployment that wants FTP-based "
            "P&L must populate ftp_rate + deposit_balance + loan_balance + period_fraction.")

        st.markdown(f"**Excel reconciliation tolerance:** {float(EXCEL_MATCH_TOLERANCE)*100:.2f}% "
                     "— engine outputs match Excel reference to within this tolerance.")

        st.caption(
            "💡 The engine integrates with v5.75 Customer Lifetime Value (#95) — CLV is the "
            "NPV of future P&L cash flows, while Customer Profitability gives the current-period "
            "P&L. Together they answer: *is this customer profitable now?* (Profitability) and "
            "*will this customer be valuable over their lifetime?* (CLV). The customer-centric "
            "quartet is now: NBA (v5.89) + Segmentation (v5.90) + Churn (v5.91) + "
            "Profitability (v5.92).")

    # ════════════════════════════════════════════════════════════════
    # CLV_SUB_TABS[6]: CLV Depth (Standard #95, integrated v5.95)
    # ════════════════════════════════════════════════════════════════
    with clv_sub_tabs[6]:
        st.markdown(
            "**CLV depth analysis** — three engine paths v5.75 didn't surface: "
            "per-holding revenue, sensitivity to assumptions, and portfolio NPV "
            "aggregate. Complements the v5.75 CLV calculator and v5.92 "
            "Profitability tabs above.")

        _clv_depth_inner = st.tabs([
            "📦 Per-Holding Revenue",
            "🔬 Sensitivity Analysis",
            "🌐 Portfolio NPV Aggregate",
        ])

        # ────────────── Inner[0]: Per-Holding Revenue ──────────────
        with _clv_depth_inner[0]:
            from utils.customer_lifetime_value import (
                CustomerLifetimeValueEngine, ProductHolding,
                PRODUCT_TYPES, PRODUCT_YIELDS_PCT,
            )
            from decimal import Decimal as _D_phr
            from utils.core_audit import audit_log as _audit_log_phr

            st.markdown(
                "**Standard #95 — Per-Holding Revenue Breakdown**. "
                "Engine method `product_revenue(holdings)` returns per-holding "
                "annual revenue using `PRODUCT_YIELDS_PCT` lookup, with Rule 6 "
                "transparency for unknown product types.")
            st.caption(
                "Useful for portfolio drill-down — shows which products contribute "
                "the most revenue. Different from CLV (which is NPV over horizon); "
                "this is per-product gross annual yield × balance.")

            phr_c1, phr_c2 = st.columns(2)
            with phr_c1:
                phr_n = st.slider("Number of holdings",
                                    min_value=1, max_value=8,
                                    value=4, key="phr_n")
            with phr_c2:
                phr_unknown = st.checkbox(
                    "Include UNKNOWN_PRODUCT (test Rule 6)",
                    value=False, key="phr_unknown")

            # Build holdings list with deterministic defaults
            phr_defaults = [
                ("MORTGAGE", 5_000_000.0),
                ("INVESTMENT", 1_500_000.0),
                ("CREDIT_CARD", 200_000.0),
                ("SAVINGS", 800_000.0),
                ("CURRENT", 600_000.0),
                ("PERSONAL_LOAN", 400_000.0),
                ("TERM_DEPOSIT", 1_000_000.0),
                ("TRADE_FINANCE", 2_500_000.0),
            ]
            holdings_input = []
            for i in range(int(phr_n)):
                ptype_default, bal_default = phr_defaults[i % len(phr_defaults)]
                r1, r2 = st.columns([2, 2])
                with r1:
                    ptype = st.selectbox(
                        f"Holding {i+1} type",
                        list(PRODUCT_TYPES),
                        index=list(PRODUCT_TYPES).index(ptype_default),
                        key=f"phr_type_{i}")
                with r2:
                    bal = st.number_input(
                        f"Holding {i+1} balance (KES)",
                        min_value=0.0, value=bal_default, step=10000.0,
                        key=f"phr_bal_{i}")
                holdings_input.append((ptype, bal))

            if phr_unknown:
                holdings_input.append(("UNKNOWN_PRODUCT", 100_000.0))

            if st.button("📦 Compute per-holding revenue",
                           key="phr_btn", type="primary"):
                holdings = [
                    ProductHolding(
                        holding_id=f"H{i:03d}",
                        customer_id="DEMO_CUST",
                        product_type=ptype,
                        balance_or_outstanding_kes=_D_phr(str(bal)),
                    )
                    for i, (ptype, bal) in enumerate(holdings_input)
                ]
                r = CustomerLifetimeValueEngine.product_revenue(holdings)

                holding_count = int(r["holding_count"])
                scored = int(r["scored_count"])
                excluded = int(r["excluded_count"])
                total_rev = float(_D_phr(str(r["total_annual_revenue_kes"])))

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total holdings", holding_count)
                k2.metric("Scored", scored)
                k3.metric("Excluded (unknown product)", excluded,
                            help="Per Rule 6 — engine surfaces holdings with no yield mapping.")
                k4.metric("Total annual revenue", f"{currency_symbol()} {total_rev:,.0f}")

                per_holding = r.get("per_holding", [])
                if per_holding:
                    st.markdown("**Per-holding revenue breakdown:**")
                    rows = []
                    for h in per_holding:
                        rev = float(_D_phr(str(h["annual_revenue_kes"])))
                        rows.append({
                            "Holding": h["holding_id"],
                            "Product": h["product_type"],
                            f"Balance ({currency_symbol()})": f"{float(_D_phr(str(h['balance_kes']))):,.0f}",
                            "Yield %": f"{float(_D_phr(str(h['yield_pct']))):.2f}",
                            "Annual revenue (KES)": f"{rev:,.0f}",
                            "% of total": (f"{rev/total_rev*100:.1f}%"
                                            if total_rev else "—"),
                        })
                    st.dataframe(pd.DataFrame(rows),
                                 use_container_width=True, hide_index=True)

                    # Bar chart
                    if total_rev > 0:
                        chart_data = pd.DataFrame({
                            "Annual revenue": [float(_D_phr(str(h["annual_revenue_kes"])))
                                                 for h in per_holding]
                        }, index=[f"{h['holding_id']} ({h['product_type']})"
                                    for h in per_holding])
                        st.markdown("**Revenue by holding:**")
                        st.bar_chart(chart_data)

                if excluded > 0:
                    st.warning(
                        f"⚠ {excluded} holding(s) excluded — product type not in "
                        f"PRODUCT_YIELDS_PCT lookup. Engine doesn't silently zero "
                        "them — they're surfaced so caller can extend yield mapping "
                        "or remap to known type.")

                _audit_log_phr("IFRS_ENGINE_USED", uname,
                                f"CLV #95: per-holding revenue scored={scored} "
                                f"excluded={excluded} total_rev={total_rev:.0f}")

        # ────────────── Inner[1]: Sensitivity Analysis ──────────────
        with _clv_depth_inner[1]:
            from utils.customer_lifetime_value import (
                CustomerLifetimeValueEngine, CustomerForCLV, ProductHolding,
                DEFAULT_HORIZON_YEARS, DEFAULT_DISCOUNT_RATE_PCT,
                DEFAULT_CONTRIBUTION_MARGIN_PCT,
            )
            from decimal import Decimal as _D_sens
            from utils.core_audit import audit_log as _audit_log_sens

            st.markdown(
                "**Standard #95 — CLV Sensitivity Analysis**. "
                "Engine takes horizon + discount rate + margin as parameters — "
                "surface the sensitivity to make assumption choices visible.")
            st.caption(
                "💡 CLV is highly sensitive to assumption choices. Same customer "
                "can show 3-7x different NPVs across reasonable horizon/discount "
                "ranges. **Bank should set policy on these assumptions** before "
                "using CLV for decisions.")

            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                sens_tenure = st.number_input("Tenure (years)",
                                                min_value=0.0, value=3.0, step=0.5,
                                                key="sens_tenure")
            with sc2:
                sens_mortgage = st.number_input("Mortgage balance (KES)",
                                                  min_value=0.0, value=2_000_000.0,
                                                  step=100_000.0,
                                                  key="sens_mortgage")
            with sc3:
                sens_investment = st.number_input("Investment balance (KES)",
                                                    min_value=0.0, value=500_000.0,
                                                    step=50_000.0,
                                                    key="sens_investment")

            sens_demo_customer = CustomerForCLV(
                customer_id="SENS_DEMO",
                cif_id="CIF_SENS",
                tenure_years=_D_sens(str(sens_tenure)),
                holdings=[
                    ProductHolding("H001", "SENS_DEMO", "MORTGAGE",
                                    _D_sens(str(sens_mortgage))),
                    ProductHolding("H002", "SENS_DEMO", "INVESTMENT",
                                    _D_sens(str(sens_investment))),
                ],
            )

            if st.button("🔬 Run sensitivity analyses",
                           key="sens_btn", type="primary"):
                # Horizon sensitivity
                st.markdown("### 📈 Horizon sensitivity")
                horizon_rows = []
                for h in [1, 2, 3, 5, 7, 10, 15]:
                    r = CustomerLifetimeValueEngine.clv_npv(
                        sens_demo_customer, horizon_years=h)
                    horizon_rows.append({
                        "Horizon (years)": h,
                        "CLV NPV (KES)": float(_D_sens(str(r["clv_npv_kes"]))),
                    })
                df_h = pd.DataFrame(horizon_rows)
                chart_h = pd.DataFrame({
                    "CLV NPV (KES)": df_h["CLV NPV (KES)"]
                }, index=[f"{h}y" for h in df_h["Horizon (years)"]])
                st.line_chart(chart_h)
                df_h_disp = df_h.copy()
                df_h_disp["CLV NPV (KES)"] = df_h_disp["CLV NPV (KES)"].apply(
                    lambda v: f"{v:,.0f}")
                st.dataframe(df_h_disp,
                             use_container_width=True, hide_index=True)

                spread_h = max(df_h["CLV NPV (KES)"]) - min(df_h["CLV NPV (KES)"])
                ratio_h = (max(df_h["CLV NPV (KES)"]) /
                            min(df_h["CLV NPV (KES)"])
                            if min(df_h["CLV NPV (KES)"]) > 0 else 0)
                st.caption(
                    f"Spread: {currency_symbol()} {spread_h:,.0f}. "
                    f"Max/Min ratio: {ratio_h:.1f}x. "
                    "Bank policy on horizon (typically 3-5y for retail, "
                    "5-10y for HNW) materially affects investment decisions.")

                # Discount rate sensitivity
                st.markdown("### 📉 Discount rate sensitivity")
                disc_rows = []
                for d in ["6", "8", "10", "12", "15", "18", "22"]:
                    r = CustomerLifetimeValueEngine.clv_npv(
                        sens_demo_customer, discount_rate_pct=_D_sens(d))
                    disc_rows.append({
                        "Discount rate (%)": float(d),
                        "CLV NPV (KES)": float(_D_sens(str(r["clv_npv_kes"]))),
                    })
                df_d = pd.DataFrame(disc_rows)
                chart_d = pd.DataFrame({
                    "CLV NPV (KES)": df_d["CLV NPV (KES)"]
                }, index=[f"{d}%" for d in df_d["Discount rate (%)"]])
                st.line_chart(chart_d)
                df_d_disp = df_d.copy()
                df_d_disp["CLV NPV (KES)"] = df_d_disp["CLV NPV (KES)"].apply(
                    lambda v: f"{v:,.0f}")
                st.dataframe(df_d_disp,
                             use_container_width=True, hide_index=True)

                spread_d = max(df_d["CLV NPV (KES)"]) - min(df_d["CLV NPV (KES)"])
                st.caption(
                    f"Spread: {currency_symbol()} {spread_d:,.0f}. "
                    "Higher discount rate aggressively discounts future cash "
                    "flows. Bank's WACC or hurdle rate is the right anchor — "
                    f"default {DEFAULT_DISCOUNT_RATE_PCT}% is a reasonable "
                    "Tier-2 anchor.")

                # Margin sensitivity
                st.markdown("### 💰 Contribution margin sensitivity")
                margin_rows = []
                for m in ["30", "40", "50", "60", "70", "80"]:
                    r = CustomerLifetimeValueEngine.clv_npv(
                        sens_demo_customer, margin_pct=_D_sens(m))
                    margin_rows.append({
                        "Contribution margin (%)": float(m),
                        "CLV NPV (KES)": float(_D_sens(str(r["clv_npv_kes"]))),
                    })
                df_m = pd.DataFrame(margin_rows)
                chart_m = pd.DataFrame({
                    "CLV NPV (KES)": df_m["CLV NPV (KES)"]
                }, index=[f"{m}%" for m in df_m["Contribution margin (%)"]])
                st.line_chart(chart_m)
                df_m_disp = df_m.copy()
                df_m_disp["CLV NPV (KES)"] = df_m_disp["CLV NPV (KES)"].apply(
                    lambda v: f"{v:,.0f}")
                st.dataframe(df_m_disp,
                             use_container_width=True, hide_index=True)

                st.caption(
                    "Margin sensitivity is **linear** — doubling margin doubles CLV. "
                    "Margin should reflect actual product profit-to-revenue ratio, "
                    f"not aspirational. Default {DEFAULT_CONTRIBUTION_MARGIN_PCT}% "
                    "is reasonable for retail banking but may overstate for "
                    "FX-fee-heavy SME, understate for low-touch deposit-only "
                    "relationships.")

                _audit_log_sens("IFRS_ENGINE_USED", uname,
                                 f"CLV #95: sensitivity tenure={sens_tenure}y "
                                 f"horizon_spread={spread_h:.0f} "
                                 f"discount_spread={spread_d:.0f}")

        # ────────────── Inner[2]: Portfolio NPV Aggregate ──────────────
        with _clv_depth_inner[2]:
            from utils.customer_lifetime_value import (
                CustomerLifetimeValueEngine, CustomerForCLV, ProductHolding,
                PROFITABILITY_SEGMENTS, CLV_HIGH_VALUE_MIN, CLV_MEDIUM_MIN,
                DEFAULT_HORIZON_YEARS, DEFAULT_DISCOUNT_RATE_PCT,
            )
            from decimal import Decimal as _D_agg
            from utils.core_audit import audit_log as _audit_log_agg

            st.markdown(
                "**Standard #95 — Portfolio NPV Aggregate**. "
                "Engine method `clv_aggregate(customers, horizon, discount)` "
                "computes portfolio-level total NPV, median CLV, and segment "
                "distribution across {scored, unscored} customers (Rule 6).")
            st.caption(
                "Useful for: portfolio valuation in M&A scenarios, tier-shift "
                "impact analysis, board-level CLV reporting. Different from "
                "v5.75 Portfolio CLV Distribution (which scans by segment) — "
                "this is a single roll-up across the input set.")

            agg_c1, agg_c2 = st.columns(2)
            with agg_c1:
                agg_n = st.slider("Demo portfolio size",
                                    min_value=5, max_value=50,
                                    value=10, step=5,
                                    key="agg_n")
                agg_horizon = st.number_input(
                    "Horizon (years)",
                    min_value=1, max_value=15,
                    value=DEFAULT_HORIZON_YEARS, step=1,
                    key="agg_horizon")
            with agg_c2:
                agg_discount = st.number_input(
                    "Discount rate (%)",
                    min_value=1.0, max_value=30.0,
                    value=float(DEFAULT_DISCOUNT_RATE_PCT), step=0.5,
                    key="agg_discount")
                agg_unscored = st.checkbox(
                    "Include 10% unscored customers (test Rule 6)",
                    value=True, key="agg_unscored")

            if st.button("🌐 Run portfolio NPV aggregation",
                           key="agg_btn", type="primary"):
                n = int(agg_n)
                customers_agg = []
                unscored_target = int(n * 0.1) if agg_unscored else 0

                for i in range(n):
                    if i < n // 5:
                        profile = [("MORTGAGE", 6_000_000),
                                    ("INVESTMENT", 3_000_000)]
                        tenure = 5.0
                    elif i < n * 2 // 5:
                        profile = [("MORTGAGE", 2_500_000),
                                    ("CURRENT", 800_000)]
                        tenure = 3.0
                    elif i < n * 3 // 5:
                        profile = [("CURRENT", 350_000),
                                    ("CREDIT_CARD", 80_000)]
                        tenure = 2.0
                    elif i < n * 4 // 5:
                        profile = [("SAVINGS", 50_000)]
                        tenure = 1.0
                    else:
                        profile = [("PERSONAL_LOAN", 300_000),
                                    ("SAVINGS", 100_000)]
                        tenure = 1.5

                    is_unscored = (i >= n - unscored_target) and agg_unscored
                    cust = CustomerForCLV(
                        customer_id=f"AGG_C{i:03d}",
                        cif_id=f"CIF_AGG_{i:03d}",
                        tenure_years=None if is_unscored else _D_agg(str(tenure)),
                        holdings=[
                            ProductHolding(f"AGG_H{i:03d}_{j}",
                                            f"AGG_C{i:03d}",
                                            ptype, _D_agg(str(bal)))
                            for j, (ptype, bal) in enumerate(profile)
                        ],
                    )
                    customers_agg.append(cust)

                r = CustomerLifetimeValueEngine.clv_aggregate(
                    customers_agg,
                    horizon_years=int(agg_horizon),
                    discount_rate_pct=_D_agg(str(agg_discount)),
                )

                scored = int(r["scored_count"])
                unscored = int(r["unscored_count"])
                total_clv = float(_D_agg(str(r["total_clv_npv_kes"])))
                median_clv = float(_D_agg(str(r["median_clv_kes"])))
                seg_dist = r.get("segment_distribution", {})

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Portfolio size", n)
                k2.metric("Scored", scored)
                k3.metric("Total CLV NPV", f"{currency_symbol()} {total_clv:,.0f}")
                k4.metric("Median CLV", f"{currency_symbol()} {median_clv:,.0f}")

                if unscored > 0:
                    st.warning(
                        f"⚠ **{unscored} customer(s) unscored** "
                        "(no tenure_years) per Rule 6 transparency. "
                        "Production deployment must ensure customer master "
                        "data has tenure populated.")

                st.markdown("**Profitability segment distribution:**")
                seg_emoji = {"HIGH_VALUE": "💎", "MEDIUM": "🟢",
                              "LOW": "🟡", "UNPROFITABLE": "🔴"}
                seg_rows = []
                for seg in PROFITABILITY_SEGMENTS:
                    count = int(seg_dist.get(seg, 0))
                    seg_rows.append({
                        "Segment": f"{seg_emoji.get(seg, '⚪')} {seg}",
                        "Count": count,
                        "% of scored": (f"{count/scored*100:.1f}%"
                                          if scored else "—"),
                    })
                st.dataframe(pd.DataFrame(seg_rows),
                             use_container_width=True, hide_index=True)

                chart_data_agg = pd.DataFrame({
                    "Customers": [int(seg_dist.get(s, 0))
                                    for s in PROFITABILITY_SEGMENTS]
                }, index=list(PROFITABILITY_SEGMENTS))
                st.markdown("**Segment distribution (bar):**")
                st.bar_chart(chart_data_agg)

                high_val = int(seg_dist.get("HIGH_VALUE", 0))
                unprof = int(seg_dist.get("UNPROFITABLE", 0))
                if scored > 0:
                    if high_val / scored >= 0.2:
                        st.info(
                            f"💎 **{high_val/scored*100:.0f}% HIGH_VALUE "
                            "concentration** — strong portfolio quality. "
                            "Maintain via retention focus.")
                    if unprof / scored >= 0.2:
                        st.warning(
                            f"🔴 **{unprof/scored*100:.0f}% UNPROFITABLE** — "
                            "consider tier-shift programs or relationship "
                            "review for these customers.")

                with st.expander("Engine constants reference"):
                    st.markdown(f"""
                    - **HIGH_VALUE**: CLV ≥ {currency_symbol()} {int(CLV_HIGH_VALUE_MIN):,}
                    - **MEDIUM**: CLV ≥ {currency_symbol()} {int(CLV_MEDIUM_MIN):,}
                    - **LOW**: CLV ≥ 0
                    - **UNPROFITABLE**: CLV < 0
                    - **DEFAULT_HORIZON_YEARS**: {DEFAULT_HORIZON_YEARS}
                    - **DEFAULT_DISCOUNT_RATE_PCT**: {DEFAULT_DISCOUNT_RATE_PCT}%
                    """)

                _audit_log_agg("IFRS_ENGINE_USED", uname,
                                f"CLV #95: aggregate scored={scored} "
                                f"unscored={unscored} total={total_clv:.0f} "
                                f"median={median_clv:.0f} "
                                f"seg={dict(seg_dist)}")

            st.caption(
                "💡 **v5.95 deepens v5.75 CLV integration**: v5.75 shipped "
                "`clv_npv` per-customer + product yield reference + portfolio "
                "scan by segment. v5.95 adds the 3 engine paths v5.75 didn't "
                "surface — `product_revenue` (per-holding annual revenue), "
                "sensitivity analysis (horizon/discount/margin variations), "
                "and `clv_aggregate` (portfolio NPV roll-up).")

    # ════════════════════════════════════════════════════════════════
# TAB 7: IFRS 7 / IAS 24 Disclosures (Standards #110 + #116, integrated v5.75)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.ifrs7_disclosures import (
        IFRS7DisclosureEngine, MATURITY_BUCKETS, RISK_TYPES,
        MARKET_RISK_VARIABLES, CREDIT_QUALITY_BANDS,
        INDUSTRY_CONCENTRATION_PCT_THRESHOLD,
        SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD,
    )
    from utils.related_party import (
        RelatedPartyEngine, RELATED_PARTY_CATEGORIES, KMP_CRITERIA,
        CLOSE_FAMILY_MEMBERS, REQUIRED_DISCLOSURES,
    )
    from decimal import Decimal as _D_disc
    # audit_log already imported above

    st.markdown(
        "**Statutory disclosure engines** — IFRS 7 (financial instruments) "
        "and IAS 24 (related parties). Both apply at year-end and to "
        "interim financials."
    )

    disc_top_tabs = st.tabs([
        "📊 IFRS 7 — Financial Instruments (#110)",
        "👥 IAS 24 — Related Parties (#116)",
    ])

    # ──────────── IFRS 7 ────────────
    with disc_top_tabs[0]:
        st.markdown(
            f"**IFRS 7 — Financial Instruments Disclosure**. "
            f"Risk types covered: {', '.join(RISK_TYPES)}. "
            f"Concentration thresholds: single counterparty "
            f"≥{SINGLE_COUNTERPARTY_CONCENTRATION_PCT_THRESHOLD}%, "
            f"industry ≥{INDUSTRY_CONCENTRATION_PCT_THRESHOLD}%."
        )

        ifrs7_sub_tabs = st.tabs([
            "🪣 Maturity Bucket Classifier",
            "⚠️ Concentration Check",
            "📈 Market Risk Sensitivity",
            "✅ Disclosure Completeness",
        ])

        # Maturity bucket
        with ifrs7_sub_tabs[0]:
            st.markdown(
                "**IFRS 7.39 Maturity Bucket** for a single contractual cash flow."
            )
            c1, c2 = st.columns(2)
            with c1:
                days = st.number_input("Days to maturity",
                                         min_value=0, value=180, step=30,
                                         key="ifrs7_days")
            with c2:
                on_demand = st.checkbox("On demand (callable any time)",
                                          key="ifrs7_on_demand")
            if st.button("Classify maturity", key="ifrs7_mat_btn",
                          type="primary"):
                bucket = IFRS7DisclosureEngine.classify_maturity_bucket(
                    days_to_maturity=int(days), on_demand=on_demand)
                if bucket:
                    st.success(f"✅ Bucket: **{bucket}**")
                    bucket_idx = list(MATURITY_BUCKETS).index(bucket) if bucket in MATURITY_BUCKETS else -1
                    st.caption(
                        f"Bucket {bucket_idx + 1} of "
                        f"{len(MATURITY_BUCKETS)} per IFRS 7.39: "
                        f"{' → '.join(MATURITY_BUCKETS)}")
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IFRS7 #110: Maturity {days}d / on_demand={on_demand} "
                                    f"→ {bucket}")
                else:
                    st.error("Could not classify (invalid input).")

        # Concentration check
        with ifrs7_sub_tabs[1]:
            st.markdown("**Credit Risk Concentration** — single-counterparty + industry")
            c1, c2, c3 = st.columns(3)
            with c1:
                conc_type = st.selectbox(
                    "Concentration type",
                    ["SINGLE_COUNTERPARTY", "INDUSTRY"],
                    key="ifrs7_conc_type")
            with c2:
                conc_exp = st.number_input("Exposure (KES M)",
                                             min_value=0.0, value=300.0,
                                             step=10.0, key="ifrs7_conc_exp")
            with c3:
                conc_total = st.number_input("Total exposure (KES M)",
                                                min_value=0.0, value=2000.0,
                                                step=100.0,
                                                key="ifrs7_conc_total")
            if st.button("Check concentration", key="ifrs7_conc_btn",
                          type="primary"):
                r = IFRS7DisclosureEngine.credit_risk_concentration(
                    exposure_amount=_D_disc(str(conc_exp)) * _D_disc("1000000"),
                    total_exposure=_D_disc(str(conc_total)) * _D_disc("1000000"),
                    concentration_type=conc_type)
                if r.get("computed"):
                    pct = r.get("concentration_pct")
                    threshold = r.get("threshold_pct")
                    is_conc = r.get("is_concentrated")
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Concentration %", f"{pct}%")
                    k2.metric("Threshold", f"{threshold}%")
                    if is_conc:
                        k3.markdown(
                            "<div style='padding:8px 12px;background:#DC262622;"
                            "border-left:4px solid #DC2626;border-radius:8px;text-align:center'>"
                            "<div style='font-size:18px;font-weight:800;color:#DC2626'>"
                            "DISCLOSURE REQUIRED</div></div>",
                            unsafe_allow_html=True)
                        st.error(
                            f"⛔ Concentration of **{pct}%** exceeds "
                            f"{threshold}% threshold — disclosure required per IFRS 7.34.")
                    else:
                        k3.markdown(
                            "<div style='padding:8px 12px;background:#10B98122;"
                            "border-left:4px solid #10B981;border-radius:8px;text-align:center'>"
                            "<div style='font-size:18px;font-weight:800;color:#10B981'>"
                            "WITHIN THRESHOLD</div></div>",
                            unsafe_allow_html=True)
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IFRS7 #110: Concentration {conc_type} "
                                    f"{conc_exp}M/{conc_total}M = {pct}%, conc={is_conc}")
                else:
                    st.error(f"Could not compute. Reason: {r.get('reason', 'inputs missing')}")

        # Market risk sensitivity
        with ifrs7_sub_tabs[2]:
            st.markdown(
                "**Market Risk Sensitivity** — IFRS 7.40. "
                f"Risk variables: {', '.join(MARKET_RISK_VARIABLES)}.")
            c1, c2, c3 = st.columns(3)
            with c1:
                mkt_var = st.selectbox("Risk variable",
                                         list(MARKET_RISK_VARIABLES),
                                         key="ifrs7_mkt_var")
            with c2:
                mkt_exp = st.number_input("Exposure (KES M)",
                                            min_value=0.0, value=10000.0,
                                            step=500.0, key="ifrs7_mkt_exp")
            with c3:
                mkt_chg = st.number_input("Sensitivity Δ (%)",
                                            min_value=0.0, value=1.0, step=0.25,
                                            key="ifrs7_mkt_chg")
            if st.button("Compute sensitivity", key="ifrs7_mkt_btn",
                          type="primary"):
                r = IFRS7DisclosureEngine.market_risk_sensitivity(
                    risk_variable=mkt_var,
                    exposure=_D_disc(str(mkt_exp)) * _D_disc("1000000"),
                    sensitivity_change_pct=_D_disc(str(mkt_chg)))
                if r.get("computed"):
                    impact = _D_disc(str(r.get("impact", 0)))
                    k1, k2 = st.columns(2)
                    k1.metric("Risk variable", mkt_var)
                    k2.metric(f"Impact for {mkt_chg}% change",
                               f"{currency_symbol()} {impact/_D_disc('1000000'):,.2f}M")
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IFRS7 #110: Mkt risk {mkt_var} "
                                    f"{mkt_exp}M @ {mkt_chg}% = {impact/_D_disc('1000000')}M")
                else:
                    st.error(f"Could not compute. Reason: {r.get('reason')}")

        # Disclosure completeness
        with ifrs7_sub_tabs[3]:
            st.markdown(
                "**Disclosure Completeness** — confirm all required IFRS 7 disclosures provided.")
            required = ["CREDIT_RISK_CLASSES", "MAX_EXPOSURE", "COLLATERAL",
                         "AGING", "CONCENTRATION", "FAIR_VALUE_HIERARCHY",
                         "RISK_MANAGEMENT_OBJECTIVES"]
            st.caption(
                f"Required disclosures: {len(required)}. Tick those provided.")
            provided = []
            for req in required:
                if st.checkbox(req.replace("_", " ").title(),
                                value=(req in required[:3]),
                                key=f"ifrs7_disc_{req}"):
                    provided.append(req)
            if st.button("Check completeness", key="ifrs7_disc_btn",
                          type="primary"):
                r = IFRS7DisclosureEngine.disclosure_completeness(
                    required_set=required, provided_set=provided)
                if r.get("computed"):
                    complete = r.get("complete")
                    pct = r.get("completeness_pct")
                    missing = r.get("missing", [])
                    k1, k2 = st.columns(2)
                    k1.metric("Completeness", f"{pct}%")
                    if complete:
                        k2.success("✅ All disclosures provided")
                    else:
                        k2.error(f"⛔ {len(missing)} missing")
                    if missing:
                        st.markdown(
                            "**Missing disclosures:** "
                            + ", ".join(m.replace("_", " ").title()
                                         for m in missing))
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IFRS7 #110: Disclosure check "
                                    f"{len(provided)}/{len(required)} "
                                    f"complete={complete}")

    # ──────────── IAS 24 ────────────
    with disc_top_tabs[1]:
        st.markdown(
            f"**IAS 24 — Related Party Disclosures**. "
            f"7 related party categories. {len(KMP_CRITERIA)} KMP criteria. "
            f"{len(REQUIRED_DISCLOSURES)} required disclosures per material transaction."
        )

        ias24_sub_tabs = st.tabs([
            "👤 KMP Identification",
            "🏷️ Category Classifier",
            "👨‍👩‍👧 Close Family Check",
            "✅ Disclosure Completeness",
            "🏛️ Government Relief",
        ])

        # KMP identification
        with ias24_sub_tabs[0]:
            st.markdown(
                "**Key Management Personnel Identification** (IAS 24.9). "
                "KMP requires BOTH planning/directing/controlling authority "
                "AND inclusion as a director or senior management member.")
            st.caption(f"Criteria: {', '.join(KMP_CRITERIA)}")
            kmp_flags = {}
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Authority criteria** (any one):")
                for crit in KMP_CRITERIA[:3]:
                    kmp_flags[crit] = st.checkbox(
                        crit.replace("_", " ").title(),
                        key=f"ias24_kmp_{crit}")
            with c2:
                st.markdown("**Role criteria** (any one):")
                for crit in KMP_CRITERIA[3:]:
                    kmp_flags[crit] = st.checkbox(
                        crit.replace("_", " ").title(),
                        key=f"ias24_kmp_{crit}")

            if st.button("Test KMP status", key="ias24_kmp_btn",
                          type="primary"):
                r = RelatedPartyEngine.identify_kmp(kmp_flags)
                if r.get("computed"):
                    is_kmp = r.get("is_kmp")
                    has_auth = r.get("has_authority")
                    is_role = r.get("is_director_or_senior_management")
                    if is_kmp:
                        st.success(
                            "✅ **CONFIRMED KMP** — both authority AND role criteria met. "
                            "Disclosure obligations apply per IAS 24.17.")
                    else:
                        rationale = r.get("rationale", "criteria_not_met")
                        st.warning(
                            f"⚠ **NOT KMP** — {rationale.replace('_', ' ')}. "
                            f"has_authority={has_auth}, is_director_or_senior={is_role}.")
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IAS24 #116: KMP test → is_kmp={is_kmp}")
                else:
                    st.error(f"Could not compute. Reason: {r.get('reason')}")

        # Category classifier
        with ias24_sub_tabs[1]:
            st.markdown("**Related Party Category Classifier** (IAS 24.9)")
            cat = st.selectbox("Select category",
                                 list(RELATED_PARTY_CATEGORIES),
                                 key="ias24_cat")
            if st.button("Validate category", key="ias24_cat_btn",
                          type="primary"):
                r = RelatedPartyEngine.classify_related_party(cat)
                if r.get("valid"):
                    st.success(f"✅ Valid related party category: **{cat}**")
                    st.caption(
                        "All transactions with this party type require disclosure "
                        "per IAS 24.18.")
                else:
                    st.error(f"⛔ Invalid: {r.get('reason')}")
                audit_log("IFRS_ENGINE_USED", uname,
                                f"IAS24 #116: Classify {cat} → valid={r.get('valid')}")

        # Close family check
        with ias24_sub_tabs[2]:
            st.markdown("**Close Family Member Check** (IAS 24.9)")
            st.caption(
                "Close family members may be expected to influence, or be "
                "influenced by, that person. The IFRS-defined list is "
                "narrower than colloquial usage.")
            rel = st.selectbox(
                "Relationship",
                list(CLOSE_FAMILY_MEMBERS) + ["PARENT", "SIBLING",
                                                "UNCLE", "COUSIN", "FRIEND"],
                key="ias24_rel")
            if st.button("Check relationship", key="ias24_fam_btn",
                          type="primary"):
                r = RelatedPartyEngine.close_family_member_check(rel)
                if r.get("is_close_family"):
                    st.success(
                        f"✅ **{rel.replace('_', ' ').title()}** is a CLOSE FAMILY MEMBER "
                        "per IAS 24.9. Transactions with their related parties "
                        "require disclosure.")
                else:
                    st.warning(
                        f"⚠ **{rel.replace('_', ' ').title()}** is NOT in the IAS 24.9 "
                        "close family definition. "
                        "(Note: this is the IFRS-defined narrow list — "
                        "the colloquial sense of 'family' is wider.)")
                audit_log("IFRS_ENGINE_USED", uname,
                                f"IAS24 #116: Close family {rel} → "
                                f"{r.get('is_close_family')}")

        # Disclosure completeness
        with ias24_sub_tabs[3]:
            st.markdown(
                "**IAS 24.18 Disclosure Completeness Check** — "
                f"all {len(REQUIRED_DISCLOSURES)} required disclosures must "
                "be provided for material related-party transactions.")
            disc_provided = {}
            for req in REQUIRED_DISCLOSURES:
                disc_provided[req] = st.checkbox(
                    req.replace("_", " ").title(),
                    value=False, key=f"ias24_disc_{req}")
            if st.button("Check IAS 24.18 compliance",
                          key="ias24_disc_btn", type="primary"):
                r = RelatedPartyEngine.validate_disclosure_completeness(
                    disc_provided)
                if r.get("computed"):
                    complete = r.get("complete")
                    compliant = r.get("compliant")
                    missing = r.get("missing_disclosures", [])
                    if complete and compliant:
                        st.success(
                            "✅ **COMPLIANT** — all 5 required disclosures provided "
                            "per IAS 24.18.")
                    else:
                        st.error(
                            f"⛔ **NON-COMPLIANT** — {len(missing)} disclosure(s) missing: "
                            + ", ".join(m.replace("_", " ").title() for m in missing))
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IAS24 #116: Disclosure completeness "
                                    f"complete={complete} compliant={compliant}")

        # Government relief
        with ias24_sub_tabs[4]:
            st.markdown(
                "**Government-Related Entity Relief** (IAS 24.25-27). "
                "Government-related entities have partial disclosure relief — "
                "but must still disclose individually significant transactions.")
            is_gov = st.checkbox(
                "Entity is government-controlled", value=False, key="ias24_gov")
            if st.button("Check relief eligibility",
                          key="ias24_gov_btn", type="primary"):
                r = RelatedPartyEngine.government_related_entity_relief(
                    is_government_controlled=is_gov)
                if r.get("computed"):
                    applies = r.get("applies")
                    level = r.get("disclosure_level", "—")
                    if applies:
                        st.info(
                            f"ℹ Partial exemption applies per IAS 24.25-27. "
                            f"Disclosure level: **{level}**. "
                            "Individually significant transactions still require "
                            "full disclosure.")
                    else:
                        st.warning(
                            "⚠ No relief — entity is NOT government-related. "
                            "Full disclosure required per IAS 24.18.")
                    audit_log("IFRS_ENGINE_USED", uname,
                                    f"IAS24 #116: Gov relief is_gov={is_gov} → "
                                    f"applies={applies}")
