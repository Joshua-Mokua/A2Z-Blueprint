"""pages/34_customer360.py — Customer 360 Intelligence.
Full customer view: products, propensity scores, churn risk,
next best action, relationship history, digital engagement.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access
import requests, re

require_access("customer360")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

@st.cache_data(ttl=60, show_spinner=False)
def _load(fname):
    p = DATA / fname
    if not p.exists(): return {}
    d = json.loads(p.read_text())
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

tabs = st.tabs([
    "🔍 Customer Lookup",
    "📊 Portfolio Intelligence",
    "⚠️ Churn Risk",
    "💡 Next Best Action",
    "📈 Segment Analytics",
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
                f"CLV: KES {info.get('clv_estimate',0)/1e3:.0f}K</div></div>"
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
                                "system":"You are a Kenyan bank relationship manager. Write a concise 3-sentence customer intelligence note for an RM brief.",
                                "messages":[{"role":"user","content":
                                    f"Customer profile: CIF {sel_cif}, Segment {segment}, "
                                    f"Products held {info.get('products_held',1)}, "
                                    f"Digital engagement {info.get('digital_engagement','Medium')}, "
                                    f"Churn risk {churn*100:.0f}%, NPS {info.get('nps_score',5)}/10, "
                                    f"Top propensity: {nba} ({nba_score*100:.0f}%), "
                                    f"CLV KES {info.get('clv_estimate',0)/1e3:.0f}K. "
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
    c2.metric("Total CLV (est.)",f"KES {total_clv/1e9:.1f}B")
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
    st.markdown("**High churn risk customers — prioritise retention:**")
    high_risk = [(cif,info) for cif,info in ci_raw.items() if info.get("churn_risk",0)>0.25]
    high_risk.sort(key=lambda x:-x[1].get("churn_risk",0))

    c1,c2,c3 = st.columns(3)
    c1.metric("High Risk (>25%)",f"{len(high_risk):,}")
    c2.metric("Potential CLV at risk",f"KES {sum(i.get('clv_estimate',0) for _,i in high_risk)/1e6:.0f}M")
    c3.metric("Avg churn risk",f"{sum(i.get('churn_risk',0) for _,i in high_risk)/max(len(high_risk),1)*100:.0f}%")

    df_ch = pd.DataFrame([{
        "CIF":cif,"Segment":info.get("segment",""),"Churn Risk":f"{info.get('churn_risk',0)*100:.0f}%",
        "CLV (KES K)":round(info.get("clv_estimate",0)/1e3,0),
        "Last Contact":f"{info.get('last_contact_days',0)}d",
        "NBA":info.get("nba",""),"NPS":info.get("nps_score",""),
    } for cif,info in high_risk[:50]])
    st.dataframe(df_ch, use_container_width=True, hide_index=True)

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
                f"total CLV KES {total_clv_prod:.0f}M")

# ── TAB 5: Segment Analytics ────────────────────────────────────────
with tabs[4]:
    st.markdown("**Segment-level analytics:**")
    seg_agg = defaultdict(lambda:{"count":0,"clv":0,"churn":0,"nps":0})
    for info in ci_raw.values():
        s = info.get("segment","Mass")
        seg_agg[s]["count"]+=1; seg_agg[s]["clv"]+=info.get("clv_estimate",0)
        seg_agg[s]["churn"]+=info.get("churn_risk",0); seg_agg[s]["nps"]+=info.get("nps_score",5)
    df_sa = pd.DataFrame([{
        "Segment":s,"Customers":v["count"],
        "Avg CLV (KES K)":round(v["clv"]/v["count"]/1e3,0),
        "Avg Churn Risk%":round(v["churn"]/v["count"]*100,1),
        "Avg NPS":round(v["nps"]/v["count"],1),
    } for s,v in seg_agg.items()])
    st.dataframe(df_sa, use_container_width=True, hide_index=True)
