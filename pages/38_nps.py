"""pages/38_nps.py — NPS & Voice of Customer.
Net Promoter Score by branch and product. Customer verbatims. Trend analysis.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import defaultdict
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("sales_customer.nps")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>⭐ NPS & Voice of Customer</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Net Promoter Score · Branch ranking · Customer verbatims · Trend</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA / "nps_data.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("NPS data not available."); st.stop()

overall = data.get("overall_nps", 0)
nps_clr = "#16A34A" if overall>=cfg("nps_good",50) else "#D97706" if overall>=30 else "#DC2626"

st.markdown(
    f"<div style='background:{nps_clr}12;border:2px solid {nps_clr}40;border-radius:12px;"
    f"padding:14px 24px;margin-bottom:12px;display:flex;align-items:center;gap:20px'>"
    f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Overall NPS</div>"
    f"<div style='font-size:36px;font-weight:800;color:{nps_clr}'>{overall}</div></div>"
    f"<div style='color:var(--color-text-secondary);font-size:12px'>"
    f"NPS = % Promoters (9-10) − % Detractors (0-6) · Industry benchmark: 35-45 · "
    f"World class: ≥70 · As at {data.get('as_at','')}</div></div>",
    unsafe_allow_html=True)

tabs = st.tabs(["🏢 Branch NPS","🏷️ Product NPS","💬 Verbatims","📈 Trend","🎯 Actions"])

with tabs[0]:
    branches = data.get("by_branch",[])
    f1,f2 = st.columns(2)
    sort_col = f1.selectbox("Sort by",["nps","promoters","responses"],key="nps_sort")
    min_resp = f2.slider("Min responses",10,200,50,key="nps_min")
    vis = [b for b in branches if b["responses"]>=min_resp]
    vis = sorted(vis, key=lambda x:-x.get(sort_col,0))

    c1,c2,c3 = st.columns(3)
    c1.metric("Branches scored", len(vis))
    c2.metric("Best NPS",  max((b["nps"] for b in vis),default=0))
    c3.metric("Worst NPS", min((b["nps"] for b in vis),default=0))

    rows = [{"Branch":b["branch"][:28],"NPS":b["nps"],"Promoters%":b["promoters"],
              "Detractors%":b["detractors"],"Responses":b["responses"],
              "Grade":("🟢 Good" if b["nps"]>=cfg("nps_good",50) else "🟡 Fair" if b["nps"]>=cfg("nps_poor",30) else "🔴 Poor")}
             for b in vis]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[1]:
    products = data.get("by_product",[])
    p_rows = [{"Product":p["product"],"NPS":p["nps"],
                "Satisfaction (1-5)":p["satisfaction"],
                "Grade":("🟢" if p["nps"]>=cfg("nps_good",50) else "🟡" if p["nps"]>=cfg("nps_poor",30) else "🔴")}
               for p in sorted(products,key=lambda x:-x["nps"])]
    st.dataframe(pd.DataFrame(p_rows), use_container_width=True, hide_index=True)
    st.caption("NPS by product highlights which products are creating advocates vs detractors.")

with tabs[2]:
    verbatims = data.get("verbatims",[])
    vf1,vf2 = st.columns(2)
    v_filter = vf1.selectbox("Filter",["All","Promoters (9-10)","Passives (7-8)","Detractors (0-6)"],key="v_filter")
    v_branch  = vf2.selectbox("Branch",["All"]+sorted(set(v["branch"] for v in verbatims)),key="v_branch")
    vis_v = verbatims
    if v_filter == "Promoters (9-10)":    vis_v = [v for v in verbatims if v["score"]>=9]
    elif v_filter == "Passives (7-8)":    vis_v = [v for v in verbatims if 7<=v["score"]<=8]
    elif v_filter == "Detractors (0-6)":  vis_v = [v for v in verbatims if v["score"]<=6]
    if v_branch != "All": vis_v = [v for v in vis_v if v["branch"]==v_branch]
    for v in vis_v[:20]:
        clr = "#16A34A" if v["score"]>=9 else "#D97706" if v["score"]>=7 else "#DC2626"
        st.markdown(
            f"<div style='border-left:3px solid {clr};padding:6px 12px;margin:3px;background:{clr}08;border-radius:0 6px 6px 0'>"
            f"<span style='font-size:10px;color:{clr};font-weight:600'>{v['score']}/10 · {v['branch'][:20]} · {v['product']} · {v['date'][:10]}</span><br>"
            f"<span style='font-size:13px'>{v['comment']}</span></div>", unsafe_allow_html=True)
    st.caption(f"Showing {min(20,len(vis_v))} of {len(vis_v)} verbatims")

with tabs[3]:
    trend = data.get("trend",[])
    if trend:
        st.markdown("**NPS trend — monthly:**")
        st.line_chart(pd.DataFrame({"NPS":[t["nps"] for t in trend]},
                                    index=[t["month"] for t in trend]))

with tabs[4]:
    detractor_branches = [b for b in data.get("by_branch",[]) if b["nps"]<cfg("nps_poor",30)]
    st.markdown(f"**{len(detractor_branches)} branch(es) with NPS below 30 — priority for action:**")
    for b in sorted(detractor_branches, key=lambda x:x["nps"])[:10]:
        st.markdown(f"  🔴 **{b['branch']}** — NPS {b['nps']} · {b['detractors']}% detractors · {b['responses']} responses")
    if not detractor_branches:
        st.success("✅ All branches above NPS threshold of 30.")

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

