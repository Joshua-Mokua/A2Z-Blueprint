"""pages/8_export.py — Export module."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *

from pages._shared import load_shared_state

# Load session state
um, ud, uname, em, ri_pm, prod_m, pm, vm_obj, lm, ssm = load_shared_state()

# Shared data
uploaded_file = st.session_state.get("uploaded_file")
staff_scores  = st.session_state.get("staff_scores", pd.DataFrame())
df_proc       = st.session_state.get("df_processed", pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
all_months    = st.session_state.get("all_months", [])

st.subheader("Export reports")
report_type = st.selectbox("Report type",
    ["Staff Rankings","Detailed KPIs","Monthly Data","Validation Summary"])
stamp = datetime.now().strftime('%Y%m%d_%H%M')

if report_type == "Staff Rankings":
    exp = filtered[['Overall_Rank','Staff Name','Role','Unit','Final_BSC_Score',
                     'Avg_Achievement_Pct','Performance_Remark','Percentile']].copy()
    exp.columns = ['Rank','Name','Role','Unit','BSC Score','Avg Achievement %','Status','Percentile']
    fname = f"A2Z_Rankings_{stamp}.csv"

elif report_type == "Detailed KPIs":
    exp = df_proc[df_proc['Staff Name'].isin(filtered['Staff Name'])][
        ['Staff Name','Role','KPI','Pillar','Annual Target','YTD_Actual',
         'Percent_Achieved','Score','Weight','Weighted_Score']].copy()
    fname = f"A2Z_KPIs_{stamp}.csv"

elif report_type == "Monthly Data":
    rows = []
    filt_names = filtered['Staff Name'].tolist()
    for _, r in df_proc[df_proc['Staff Name'].isin(filt_names)].iterrows():
        for col in all_months:
            if col in r.index:
                dt = parse_month_column(col)
                rows.append({"Staff Name": r['Staff Name'], "Role": r['Role'],
                             "KPI": r['KPI'],
                             "Month": dt.strftime("%b %Y") if dt else col,
                             "Actual": r[col]})
    exp = pd.DataFrame(rows) if rows else pd.DataFrame()
    fname = f"A2Z_Monthly_{stamp}.csv"

else:  # Validation Summary
    vrows = []
    for name in filtered['Staff Name'].tolist():
        v  = vm.get(name, datetime.now().strftime("%b %Y"))
        sc = filtered[filtered['Staff Name']==name]['Final_BSC_Score'].values[0]
        vrows.append({
            "Staff": name, "BSC Score": fmt_score(sc),
            "Validation Status": v['status'] if v else "Pending",
            "Action Plan": v.get('action_plan','') if v else "",
            "Comments": v.get('comments','') if v else "",
            "Validated By": v['manager'] if v else "",
            "Date": v['validated_at'][:10] if v else "",
        })
    exp = pd.DataFrame(vrows)
    fname = f"A2Z_Validation_{stamp}.csv"

if not exp.empty:
    st.dataframe(exp, use_container_width=True, hide_index=True)
    st.download_button(f"⬇️ Download {report_type}", exp.to_csv(index=False).encode('utf-8'),
                       fname, "text/csv")
else:
    st.info("No data to export for the selected report type.")

