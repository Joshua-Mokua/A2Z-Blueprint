"""pages/45_crosssell.py — Cross-sell & Upsell Intelligence.
Products per customer, deepening ratio, NBA conversion, branch ranking.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("crosssell")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔁 Cross-sell Intelligence</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Products per customer · Deepening ratio · NBA conversion · Branch ranking</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"crosssell_data.json"
    return json.loads(p.read_text()) if p.exists() else {}

data = _load()
if not data: st.info("Cross-sell data not available."); st.stop()

avg_prod = data.get("bank_average_products_per_customer",2.4)
tgt_prod = data.get("target_products_per_customer",3.5)
gap      = tgt_prod - avg_prod

m1,m2,m3,m4 = st.columns(4)
m1.metric("Avg Products/Customer", f"{avg_prod:.1f}")
m2.metric("Target",                f"{tgt_prod:.1f}")
m3.metric("Gap to Target",         f"{gap:.1f} products",
          delta_color="normal" if gap<=0 else "inverse")
m4.metric("Deepening Opportunity", f"{gap/tgt_prod*100:.0f}% upside")

tabs = st.tabs(["📊 Segment View","🏢 Branch Ranking","💡 NBA Opportunities","📈 Conversion Funnel"])

with tabs[0]:
    segs = data.get("by_segment",[])
    st.markdown("**Products per customer by segment:**")
    seg_rows=[{"Segment":s["segment"],"Avg Products":s["avg_products"],
                "Customers":f"{s['customers']:,}","NBA Conversion%":s["nba_conversion_pct"]}
               for s in segs]
    st.dataframe(pd.DataFrame(seg_rows),use_container_width=True,hide_index=True)
    st.bar_chart(pd.DataFrame({"Avg Products":[s["avg_products"] for s in segs]},
                               index=[s["segment"] for s in segs]))

with tabs[1]:
    branches = data.get("by_branch",[])
    b_rows=[{"Branch":b["branch"][:28],"Avg Products":b["avg_products"],
              "Deepening Score":b["deepening_score"],
              "Grade":("🟢" if b["deepening_score"]>=cfg("deepening_score_good",70) else "🟡" if b["deepening_score"]>=cfg("deepening_score_warn",50) else "🔴")}
             for b in sorted(branches,key=lambda x:-x["deepening_score"])]
    st.dataframe(pd.DataFrame(b_rows),use_container_width=True,hide_index=True)

with tabs[2]:
    nba = data.get("top_nba_products",[])
    st.markdown("**Top Next Best Action opportunities — eligible customers with propensity:**")
    nba_rows=[{"Product":n["product"],"Eligible Customers":f"{n['eligible_customers']:,}",
                "Avg Propensity":f"{n['propensity_avg']*100:.0f}%",
                "Converted (30d)":n["converted_30d"],
                "Conversion Rate":f"{n['converted_30d']/n['eligible_customers']*100:.1f}%"}
               for n in sorted(nba,key=lambda x:-x["eligible_customers"])]
    st.dataframe(pd.DataFrame(nba_rows),use_container_width=True,hide_index=True)

with tabs[3]:
    st.markdown("**Conversion funnel — from NBA identification to product take-up:**")
    total_eligible = sum(n["eligible_customers"] for n in nba)
    total_converted = sum(n["converted_30d"] for n in nba)
    funnel = [
        ("Eligible customers identified",    total_eligible,  "#3B82F6"),
        ("Contacted / approached",            int(total_eligible*0.45), "#0891B2"),
        ("Expressed interest",               int(total_eligible*0.22), "#0F6E56"),
        ("Application submitted",            int(total_eligible*0.12), "#16A34A"),
        ("Converted (product taken up)",     total_converted, "#15803D"),
    ]
    for label, n, clr in funnel:
        pct = n/max(total_eligible,1)*100
        bar = int(pct/2)
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
            f"<div style='width:260px;font-size:12px'>{label}</div>"
            f"<div style='background:{clr};height:18px;width:{bar}%;border-radius:3px;min-width:4px'></div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>{n:,} ({pct:.1f}%)</div>"
            f"</div>", unsafe_allow_html=True)
