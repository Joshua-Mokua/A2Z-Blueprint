"""pages/41_budget.py — Budget vs Actual Engine.
Department-level budget tracking, monthly actuals vs budget, variance analysis.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("budget")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
is_finance = any(x in role.lower() for x in ("financial","finance","cfo","chief","controller"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📊 Budget vs Actual</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Department budgets · Monthly actuals · Variance analysis · Reforecast</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"budget_data.json"
    return json.loads(p.read_text()) if p.exists() else {}

data = _load()
if not data: st.info("Budget data not available."); st.stop()

bt  = data.get("bank_totals",{})
dep = data.get("by_department",[])
mon = data.get("monthly",[])

# Bank-level summary
inc_ach = bt.get("income_actual_b",0)/max(bt.get("income_budget_b",1),0.01)*100
pbt_ach = bt.get("pbt_actual_b",0)/max(bt.get("pbt_budget_b",1),0.01)*100

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Income Budget",  f"KES {bt.get('income_budget_b',0):.1f}B")
m2.metric("Income Actual",  f"KES {bt.get('income_actual_b',0):.1f}B",
          f"{inc_ach-100:+.1f}%", delta_color="normal" if inc_ach>=cfg("budget_income_warning",100) else "inverse")
m3.metric("OpEx Budget",    f"KES {bt.get('opex_budget_b',0):.1f}B")
m4.metric("OpEx Actual",    f"KES {bt.get('opex_actual_b',0):.1f}B",
          f"{bt.get('opex_actual_b',0)/bt.get('opex_budget_b',1)*100-100:+.1f}%",
          delta_color="normal" if bt.get("opex_actual_b",0)<=bt.get("opex_budget_b",1) else "inverse")
m5.metric("PBT Achievement",f"{pbt_ach:.0f}%",
          delta_color="normal" if pbt_ach>=100 else "inverse")

tabs = st.tabs(["🏢 By Department","📅 Monthly Trend","⚠️ Variances","📥 Export"])

with tabs[0]:
    st.markdown("**Budget performance by department:**")
    d_rows=[{"Department":d["department"],"Income Budget (M)":d["income_budget_m"],
              "Income Actual (M)":d["income_actual_m"],"Variance (M)":d["variance_income_m"],
              "Income Achv%":f"{d['income_achv_pct']:.0f}%",
              "OpEx Budget (M)":d["opex_budget_m"],"OpEx Actual (M)":d["opex_actual_m"],
              "OpEx Var (M)":d["variance_opex_m"],
              "HC Budget":d["headcount_budget"],"HC Actual":d["headcount_actual"],
              "Status":("✅" if d["income_achv_pct"]>=cfg("budget_achv_good",95) else "🟡" if d["income_achv_pct"]>=cfg("budget_achv_warn",80) else "🔴")}
             for d in sorted(dep,key=lambda x:-x["income_achv_pct"])]
    st.dataframe(pd.DataFrame(d_rows),use_container_width=True,hide_index=True)
    below = [d for d in dep if d["income_achv_pct"]<cfg("budget_achv_warn",80)]
    if below:
        st.warning(f"⚠️ {len(below)} department(s) below 80% income achievement: {[d['department'][:15] for d in below]}")

with tabs[1]:
    if mon:
        st.markdown("**Monthly income vs budget:**")
        months = [m["month"] for m in mon]
        st.line_chart(pd.DataFrame({"Budget":    [m["income_budget_m"] for m in mon],
                                      "Actual":   [m["income_actual_m"] for m in mon]},
                                    index=months))
        st.markdown("**Monthly OpEx vs budget:**")
        st.line_chart(pd.DataFrame({"Budget":   [m["opex_budget_m"] for m in mon],
                                      "Actual":  [m["opex_actual_m"] for m in mon]},
                                    index=months))

with tabs[2]:
    st.markdown("**Significant variances (>10% over/under budget):**")
    var_rows=[d for d in dep if abs(d["income_achv_pct"]-100)>10 or abs(d["variance_opex_m"]/max(d["opex_budget_m"],0.01)*100)>10]
    if var_rows:
        for d in var_rows:
            clr = "#DC2626" if d["income_achv_pct"]<cfg("budget_achv_warn",80) else "#D97706"
            st.markdown(
                f"<div style='border-left:3px solid {clr};padding:6px 12px;margin:3px;background:{clr}08'>"
                f"<b>{d['department']}</b>: Income {d['income_achv_pct']:.0f}% of budget · "
                f"OpEx variance KES {d['variance_opex_m']:+.1f}M</div>", unsafe_allow_html=True)
    else:
        st.success("All departments within 10% of budget targets.")

with tabs[3]:
    if is_finance or is_admin:
        import io
        buf = io.BytesIO()
        pd.DataFrame(d_rows).to_excel(buf,index=False,engine="openpyxl")
        buf.seek(0)
        st.download_button("📥 Download Budget Report",data=buf.getvalue(),
                            file_name=f"Budget_vs_Actual_{today}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="bvs_dl")
    else:
        st.info("Export available to Finance team and Admin.")
