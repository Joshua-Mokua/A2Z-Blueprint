"""pages/58_workforce.py — Workforce Planning.
Headcount, attrition, succession depth, open positions. Thresholds via Admin.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("people_hr.workforce_planning")
DATA  = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()[:12]
is_admin = ud.get("is_admin",False)
is_hr    = any(x in ud.get("role","").lower() for x in ("human resource","hr","chief human"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>📋 Workforce Planning</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Headcount · Attrition · Succession · Open positions · Gender ratio</span></div>",
            unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"workforce_planning.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("Workforce data not available."); st.stop()

summary = data.get("summary",{})
depts   = data.get("by_department",[])
attr_w  = cfg("workforce_attrition_warning_pct", 12.0)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Headcount", summary.get("total_headcount",0))
m2.metric("Budgeted",        summary.get("total_budget",0))
m3.metric("Open Positions",  summary.get("total_open",0), delta_color="normal")
m4.metric("Attrition YTD",   f"{summary.get('overall_attrition_pct',0):.1f}%",
          delta_color="normal" if summary.get("overall_attrition_pct",0)<=attr_w else "inverse")
m5.metric("Female %",        f"{summary.get('gender_f_pct',0):.0f}%")

tabs = st.tabs(["🏢 By Department","⚠️ Alerts","👥 Succession","📊 Analytics"])

with tabs[0]:
    d_rows=[{"Department":d["department"][:28],"Actual HC":d["actual_headcount"],
              "Budget HC":d["budgeted_headcount"],
              "Variance":d["actual_headcount"]-d["budgeted_headcount"],
              "Open":d["open_positions"],"Attrition %":d["attrition_rate_pct"],
              "Avg Tenure":f"{d['avg_tenure_years']:.1f}y",
              "Female %":d["gender_ratio_f_pct"],
              "Succession":d["succession_depth"]}
             for d in sorted(depts,key=lambda x:-x["actual_headcount"])]
    st.dataframe(pd.DataFrame(d_rows),use_container_width=True,hide_index=True)

with tabs[1]:
    high_attr = [d for d in depts if d.get("attrition_rate_pct",0)>attr_w]
    critical  = [d for d in depts if d.get("succession_depth")=="Critical"]
    if high_attr:
        st.warning(f"⚠️ {len(high_attr)} department(s) with attrition above {attr_w}%:")
        for d in high_attr: st.markdown(f"  • {d['department']}: {d['attrition_rate_pct']:.1f}%")
    if critical:
        st.error(f"🔴 {len(critical)} department(s) with critical succession depth:")
        for d in critical: st.markdown(f"  • {d['department']}: {d['critical_roles']} critical roles, {d['critical_roles_covered']} covered")
    if not high_attr and not critical:
        st.success("✅ No workforce alerts.")

with tabs[2]:
    succ = {"Strong":0,"Adequate":0,"Thin":0,"Critical":0}
    for d in depts: succ[d.get("succession_depth","Adequate")] = succ.get(d.get("succession_depth","Adequate"),0)+1
    st.markdown("**Succession depth distribution:**")
    for s,n in succ.items():
        clr={"Strong":"#16A34A","Adequate":"#3B82F6","Thin":"#D97706","Critical":"#DC2626"}.get(s,"#6B7280")
        pct=n/max(len(depts),1)*100
        st.markdown(f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                    f"<div style='width:70px;font-size:12px'>{s}</div>"
                    f"<div style='background:{clr};height:16px;width:{pct:.0f}%;border-radius:3px'></div>"
                    f"<div style='font-size:12px'>{n} depts</div></div>",unsafe_allow_html=True)

with tabs[3]:
    st.markdown("**Headcount vs budget by department:**")
    top10 = sorted(depts,key=lambda x:-x["actual_headcount"])[:10]
    st.bar_chart(pd.DataFrame({"Actual":[d["actual_headcount"] for d in top10],
                                "Budget":[d["budgeted_headcount"] for d in top10]},
                               index=[d["department"][:18] for d in top10]))
