"""pages/2_people.py — People module."""
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
staff_scores  = st.session_state.get("staff_scores", pd.DataFrame())
df_proc       = st.session_state.get("df_processed", pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
all_months    = st.session_state.get("all_months", [])

if len(staff_scores) == 0:
    st.info("📊 Upload your BSC Excel file in the sidebar to view this module.")
    st.stop()

st.subheader("Team insights")
st.caption("Rolled-up view of your team's strengths and weaknesses — designed for focused performance discussions.")

# Determine scope: managers see their filtered staff, admins can pick a unit
team_df = filtered.copy()
all_names = sorted(team_df['Staff Name'].tolist())

if len(all_names) == 0:
    st.info("No team data available for your view.")
else:
    # ── Team-level summary ───────────────────────────────────────
    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    tc1.metric("Team size",        len(team_df))
    tc2.metric("Avg BSC score",    fmt_score(team_df['Final_BSC_Score'].mean()))
    tc3.metric("Exceeded",         int((team_df['Final_BSC_Score'] >= 3.1).sum()))
    tc4.metric("Below target",     int((team_df['Final_BSC_Score'] < 3.0).sum()))
    tc5.metric("Critical (<2.5)",  int((team_df['Final_BSC_Score'] < 2.5).sum()))

    # ── KPI-level team aggregation ───────────────────────────────
    team_kpis = df_proc[df_proc['Staff Name'].isin(all_names)].copy()

    if not team_kpis.empty and 'KPI' in team_kpis.columns:
        kpi_summary = team_kpis.groupby(['KPI','Pillar']).agg(
            Avg_Score       = ('Score','mean'),
            Avg_Achievement = ('Percent_Achieved','mean'),
            Staff_Count     = ('Staff Name','nunique'),
            Below_Target    = ('Score', lambda x: (x < 3.0).sum()),
            Critical        = ('Score', lambda x: (x < 2.5).sum()),
        ).reset_index()
        kpi_summary['Below_Target_Pct'] = (kpi_summary['Below_Target'] / kpi_summary['Staff_Count'] * 100).round(0)
        kpi_summary = kpi_summary.sort_values(by='Avg_Score')

        # Top weaknesses across team
        st.markdown("---")
        st.markdown("### 🔴 Team-wide weaknesses")
        st.caption("KPIs where the most staff are underperforming — highest priority for team discussion.")
        team_weak = kpi_summary[kpi_summary['Avg_Score'] < 3.0].head(8)
        if len(team_weak):
            for _, r in team_weak.iterrows():
                pct_below = int(r['Below_Target_Pct'])
                crit = int(r['Critical'])
                colour = "#E74C3C" if r['Avg_Score'] < 2.5 else "#F39C12"
                st.markdown(
                    f"<div style='padding:9px 14px;background:{colour}15;border-left:4px solid {colour};"
                    f"border-radius:5px;margin:4px 0'>"
                    f"<strong>{r['KPI']}</strong> <span style='color:#888;font-size:12px'>({r['Pillar']})</span><br>"
                    f"Avg score: <strong>{r['Avg_Score']:.2f}</strong> | "
                    f"Avg achievement: <strong>{r['Avg_Achievement']:.1f}%</strong> | "
                    f"{pct_below}% of team below target"
                    f"{f' | <span style="color:#E74C3C">{crit} critical</span>' if crit else ''}"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.success("No team-wide KPI weaknesses — all KPIs averaging above 3.0")

        # Top strengths across team
        st.markdown("### 🟢 Team-wide strengths")
        team_strong = kpi_summary[kpi_summary['Avg_Score'] >= 3.5].sort_values('Avg_Score', ascending=False).head(5)
        if len(team_strong):
            for _, r in team_strong.iterrows():
                st.markdown(
                    f"<div style='padding:9px 14px;background:#2ECC7115;border-left:4px solid #2ECC71;"
                    f"border-radius:5px;margin:4px 0'>"
                    f"<strong>{r['KPI']}</strong> <span style='color:#888;font-size:12px'>({r['Pillar']})</span> — "
                    f"Avg score: <strong>{r['Avg_Score']:.2f}</strong> | {r['Avg_Achievement']:.1f}% avg achievement"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.info("No KPIs averaging above 3.5 across the team yet.")

    # ── Individual staff cards ────────────────────────────────────
    st.markdown("---")
    st.markdown("### Individual focus areas")
    st.caption("Click a staff member to see their specific strengths and areas needing attention.")

    # Sort: worst performers first (most discussion needed)
    team_sorted = team_df.sort_values(by='Final_BSC_Score')

    for _, staff_row in team_sorted.iterrows():
        sname = staff_row['Staff Name']
        score = staff_row['Final_BSC_Score']
        remark = staff_row['Performance_Remark']
        rank = staff_row['Overall_Rank']
        colour = {'Exceeded By Far':'#2ECC71','Exceeded':'#58D68D','Met':'#F39C12',
                  'Partially Met':'#E67E22','Unmet':'#E74C3C'}.get(remark,'#BDC3C7')

        with st.expander(
            f"{'🔴' if score < 2.5 else '🟡' if score < 3.0 else '🟢'} "
            f"{sname}  —  {fmt_score(score)}  |  {remark}  |  Rank #{rank}",
            expanded=(score < 2.5)):  # auto-expand critical staff

            s_kpis = df_proc[df_proc['Staff Name'] == sname]
            s_insights = get_kpi_insights(s_kpis)
            render_insight_card(s_insights, sname)

            # On leave check
            s_code = str(staff_row.get('Staff Code',''))
            if lm.is_on_leave(s_code):
                leave_rec = lm.get_active_leave(s_code)
                st.warning(f"🏖️ Currently on {leave_rec[0]['leave_type']} until {leave_rec[0]['end_date']}")

    # ── Pillar breakdown heatmap ──────────────────────────────────
    if not team_kpis.empty and 'Pillar' in team_kpis.columns:
        st.markdown("---")
        st.markdown("### Pillar heatmap")
        pillar_staff = team_kpis.groupby(['Staff Name','Pillar'])['Score'].mean().reset_index()
        pivot = pillar_staff.pivot(index='Staff Name', columns='Pillar', values='Score').fillna(0)

        fig_heat = px.imshow(
            pivot,
            color_continuous_scale=[[0,"#E74C3C"],[0.5,"#F39C12"],[0.6,"#FFE4B5"],[1,"#2ECC71"]],
            zmin=1, zmax=5,
            title="Average score per pillar per staff member",
            aspect="auto",
            text_auto=".2f")
        fig_heat.update_layout(height=max(300, len(pivot)*28))
        st.plotly_chart(fig_heat, use_container_width=True)

# ── TAB 8: PIPELINE & ACTIVITY TRACKER ──────────────────────────────────
