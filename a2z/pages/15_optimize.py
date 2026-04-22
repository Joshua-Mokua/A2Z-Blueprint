"""pages/15_optimize.py — Branch Optimization Engine."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope
require_access("optimize")


um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

BUSINESS_ROLES = {
    "Branch Manager","Direct Sales Officer","Relationship Officer Personal Banking",
    "Branch Credit Manager","Relationship Manager SME","Relationship Manager Corporate",
    "Regional Head",
}
SUPPORT_ROLES = {
    "Teller","Customer Service Officer","Branch Operations Manager",
}

# ── OPTIMIZATION SCORING ──────────────────────────────────────────────
OPTIMIZATION_WEIGHTS = {
    "bsc_score":          0.25,  # BSC performance
    "log_compliance":     0.15,  # Daily log submission rate
    "sla_adherence":      0.15,  # SLA score from SLA tracker
    "cross_sell_rate":    0.15,  # Cross-sell successes from log
    "revenue_per_staff":  0.20,  # Revenue / staff (from BSC data)
    "business_ratio":     0.10,  # Business staff / total staff ratio
}

st.markdown(
    "<div style=\'padding:16px 22px;background:#8E44AD;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>Branch Optimization Engine</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Staff mix analysis · Revenue efficiency · Cross-sell scoring · Network benchmarking</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)

tabs = st.tabs([
    "🏦 Branch scores",
    "👥 Staff mix analysis",
    "💰 Revenue efficiency",
    "🔄 Cross-sell engine",
    "📊 Network comparison",
])

# ════════════════════════════════════════════════════════════════
# BUILD BRANCH METRICS
# ════════════════════════════════════════════════════════════════
def build_branch_metrics():
    if len(staff_scores) == 0:
        return pd.DataFrame()

    blm = st.session_state.get("branch_log_manager")
    slm = st.session_state.get("sla_manager")

    branch_staff = staff_scores[staff_scores["Category"]=="Branch"].copy()
    branches = sorted(branch_staff["Unit"].unique())
    rows = []

    for branch in branches:
        bdf = branch_staff[branch_staff["Unit"]==branch]
        total_staff  = len(bdf)
        biz_staff    = len(bdf[bdf["Role"].isin(BUSINESS_ROLES)])
        sup_staff    = len(bdf[bdf["Role"].isin(SUPPORT_ROLES)])
        biz_ratio    = biz_staff / max(total_staff, 1)

        avg_bsc      = bdf["Final_BSC_Score"].mean() if "Final_BSC_Score" in bdf.columns else 0
        exceeded     = (bdf["Final_BSC_Score"] >= 3.1).sum() if "Final_BSC_Score" in bdf.columns else 0
        at_risk      = (bdf["Final_BSC_Score"] < 2.5).sum() if "Final_BSC_Score" in bdf.columns else 0

        # Revenue from BSC KPIs
        branch_kpis = df_proc[df_proc["Unit"]==branch] if not df_proc.empty else pd.DataFrame()
        deposit_act = 0; loan_act = 0; rev_act = 0
        if not branch_kpis.empty:
            dep_rows = branch_kpis[branch_kpis["KPI"]=="Deposit Growth"]
            loan_rows = branch_kpis[branch_kpis["KPI"].isin(["Loan Book Growth","Loans Disbursement"])]
            rev_rows  = branch_kpis[branch_kpis["KPI"].isin(["Fees and Commission","DFS Revenue","PBT"])]
            if len(dep_rows):  deposit_act = dep_rows["YTD_Actual"].sum() if "YTD_Actual" in dep_rows.columns else 0
            if len(loan_rows): loan_act    = loan_rows["YTD_Actual"].sum() if "YTD_Actual" in loan_rows.columns else 0
            if len(rev_rows):  rev_act     = rev_rows["YTD_Actual"].sum()  if "YTD_Actual" in rev_rows.columns else 0

        rev_per_staff = rev_act / max(total_staff, 1)
        rev_per_biz   = rev_act / max(biz_staff, 1)

        # SLA score
        sla_score = 1.0
        if slm:
            sla_score, _, _ = slm.sla_score(unit=branch, days_back=30)

        # Log compliance
        log_compliance = 0.0
        if blm:
            submitters, _ = blm.submission_rate(branch, days=7)
            log_compliance = submitters / max(total_staff, 1)

        # Cross-sell from logs
        cross_sell = 0
        if blm:
            hist = blm.get_history(unit=branch, days=30)
            validated = [l for l in hist if l.get("validated")]
            cross_sell = sum(int(l.get("cross_sell_success",0) or 0) for l in validated)

        # Composite optimization score (0-100)
        opt_score = (
            OPTIMIZATION_WEIGHTS["bsc_score"]        * (avg_bsc/5.0) +
            OPTIMIZATION_WEIGHTS["log_compliance"]    * log_compliance +
            OPTIMIZATION_WEIGHTS["sla_adherence"]     * sla_score +
            OPTIMIZATION_WEIGHTS["cross_sell_rate"]   * min(cross_sell/max(total_staff,1)/5, 1.0) +
            OPTIMIZATION_WEIGHTS["revenue_per_staff"]  * min(rev_per_staff/1e7, 1.0) +
            OPTIMIZATION_WEIGHTS["business_ratio"]    * min(biz_ratio/0.6, 1.0)
        ) * 100

        region = BRANCH_REGION.get(branch, "Head Office")
        rows.append({
            "Branch":          branch,
            "Region":          region,
            "Total Staff":     total_staff,
            "Business Staff":  biz_staff,
            "Support Staff":   sup_staff,
            "Business Ratio":  round(biz_ratio, 3),
            "Avg BSC":         round(avg_bsc, 2),
            "Exceeded":        int(exceeded),
            "At Risk":         int(at_risk),
            "Deposit YTD":     round(deposit_act/1e6, 2),
            "Loan YTD":        round(loan_act/1e6, 2),
            "Revenue YTD":     round(rev_act/1e6, 2),
            "Rev/Staff (M)":   round(rev_per_staff/1e6, 3),
            "Rev/Biz Staff":   round(rev_per_biz/1e6, 3),
            "SLA Score":       round(sla_score, 3),
            "Log Compliance":  round(log_compliance, 3),
            "Cross-sells":     cross_sell,
            "Opt Score":       round(opt_score, 1),
        })

    return pd.DataFrame(rows).sort_values("Opt Score", ascending=False)

bm_df = build_branch_metrics()

# ════════════════════════════════════════════════════════════════
# TAB 1 — BRANCH SCORES
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Branch optimization scores")
    st.caption("Composite score 0–100 combining BSC performance, SLA adherence, log compliance, revenue efficiency, and staff mix.")

    if bm_df.empty:
        st.info("Upload BSC data to see branch scores.")
    else:
        # Top/bottom
        sc1,sc2,sc3,sc4 = st.columns(4)
        sc1.metric("Best branch",   bm_df.iloc[0]["Branch"], f"{bm_df.iloc[0]['Opt Score']:.0f}/100")
        sc2.metric("Worst branch",  bm_df.iloc[-1]["Branch"], f"{bm_df.iloc[-1]['Opt Score']:.0f}/100")
        sc3.metric("Network avg",   f"{bm_df['Opt Score'].mean():.1f}/100")
        sc4.metric("Branches below 50", int((bm_df["Opt Score"]<50).sum()),
                   delta_color="inverse")

        # Color by score
        bm_df["Color"] = bm_df["Opt Score"].apply(
            lambda x: "var(--brand-primary,#006B3F)" if x>=70 else ("#F5A623" if x>=50 else "#E24B4A"))

        fig_opt = go.Figure()
        for _, row in bm_df.iterrows():
            fig_opt.add_bar(
                x=[row["Opt Score"]], y=[row["Branch"]],
                orientation="h",
                marker_color=row["Color"],
                name=row["Branch"], showlegend=False,
                text=[f"{row['Opt Score']:.0f}"],
                textposition="outside",
                hovertemplate=(
                    f"<b>{row['Branch']}</b><br>"
                    f"Score: {row['Opt Score']:.1f}<br>"
                    f"BSC: {row['Avg BSC']:.2f} | SLA: {row['SLA Score']:.1%}<br>"
                    f"Staff: {row['Total Staff']} | Biz ratio: {row['Business Ratio']:.0%}"
                    "<extra></extra>"))

        fig_opt.add_vline(x=70, line_dash="dash", line_color="var(--brand-primary,#006B3F)",
                           annotation_text="Target: 70")
        fig_opt.add_vline(x=50, line_dash="dot", line_color="#E24B4A",
                           annotation_text="Minimum: 50")
        fig_opt.update_layout(
            height=max(400, len(bm_df)*22),
            xaxis_range=[0,110], xaxis_title="Optimization Score",
            yaxis={"categoryorder":"total ascending"},
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=0,r=60,t=20,b=0))
        st.plotly_chart(fig_opt, use_container_width=True)

        # Full table
        disp = bm_df[["Branch","Region","Opt Score","Avg BSC","SLA Score",
                       "Log Compliance","Business Ratio","Total Staff"]].copy()
        disp["SLA Score"]      = disp["SLA Score"].apply(lambda x: f"{x:.1%}")
        disp["Log Compliance"] = disp["Log Compliance"].apply(lambda x: f"{x:.1%}")
        disp["Business Ratio"] = disp["Business Ratio"].apply(lambda x: f"{x:.1%}")

        def hl_score(v):
            try:
                fv = float(str(v).replace('%',''))
                if fv >= 70 or fv >= 0.85: return 'color:var(--brand-primary,#006B3F);font-weight:500'
                if fv >= 50 or fv >= 0.70: return 'color:#F5A623'
                return 'color:#E24B4A'
            except: return ''

        st.dataframe(disp.style.map(hl_score, subset=["Opt Score","Avg BSC"]),
                     use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — STAFF MIX ANALYSIS
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Staff mix — Business vs Support")
    st.markdown(
        "<div style='padding:10px 14px;background:#F2EBF7;"
        "border-left:4px solid #8E44AD;border-radius:0 6px 6px 0;margin-bottom:12px'>"
        "<b>Industry benchmark:</b> A well-optimised branch targets "
        "<b>60% Business roles</b> (revenue-generating) vs 40% Support roles. "
        "Below 50% business ratio signals underutilisation of staff capacity — "
        "you may have sufficient people but insufficient business coverage.</div>",
        unsafe_allow_html=True)

    if bm_df.empty:
        st.info("Upload BSC data.")
    else:
        network_biz = bm_df["Business Staff"].sum()
        network_sup = bm_df["Support Staff"].sum()
        network_total = bm_df["Total Staff"].sum()
        network_ratio = network_biz / max(network_total, 1)

        mc1,mc2,mc3,mc4 = st.columns(4)
        mc1.metric("Total branch staff",  network_total)
        mc2.metric("Business roles",      network_biz, f"{network_ratio:.1%}")
        mc3.metric("Support roles",       network_sup, f"{1-network_ratio:.1%}")
        clr = "normal" if network_ratio >= 0.55 else "inverse"
        mc4.metric("Network biz ratio",   f"{network_ratio:.1%}",
                   "✅ Healthy" if network_ratio>=0.55 else "⚠️ Review staffing",
                   delta_color=clr)

        # Scatter: business ratio vs BSC performance
        fig_sc = px.scatter(bm_df, x="Business Ratio", y="Avg BSC",
                             size="Total Staff", color="Opt Score",
                             text="Branch",
                             color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                             title="Business ratio vs BSC performance — bubble = total staff",
                             labels={"Business Ratio":"Business staff %","Avg BSC":"Avg BSC score"})
        fig_sc.add_vline(x=0.60, line_dash="dash", line_color="#8E44AD",
                          annotation_text="60% target")
        fig_sc.update_traces(textposition="top center", textfont_size=9)
        fig_sc.update_xaxes(tickformat=".0%")
        fig_sc.update_layout(height=400,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_sc, use_container_width=True)

        # Flag branches with poor mix
        poor_mix = bm_df[bm_df["Business Ratio"] < 0.50].sort_values("Business Ratio")
        if len(poor_mix):
            st.markdown("#### ⚠️ Branches with sub-optimal staff mix (< 50% business roles)")
            for _, row in poor_mix.iterrows():
                gap_staff = int(row["Total Staff"] * 0.60 - row["Business Staff"])
                st.markdown(
                    f"<div style='padding:7px 12px;background:#FDEDEC;"
                    f"border-left:3px solid #E24B4A;font-size:12px;margin:2px 0'>"
                    f"<b>{row['Branch']}</b> — {row['Business Staff']} business / "
                    f"{row['Total Staff']} total = {row['Business Ratio']:.0%}. "
                    f"Needs ~{gap_staff} more business-role staff to reach 60% target."
                    f"</div>", unsafe_allow_html=True)

        # Role breakdown by branch
        if len(staff_scores):
            st.markdown("---")
            st.markdown("#### Role breakdown by branch")
            role_branch = staff_scores[staff_scores["Category"]=="Branch"].groupby(
                ["Unit","Role"]).size().reset_index(name="Count")
            fig_rb = px.bar(role_branch, x="Unit", y="Count", color="Role",
                             title="Staff count by role per branch",
                             barmode="stack")
            fig_rb.update_layout(height=360, xaxis_tickangle=-35,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_rb, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 3 — REVENUE EFFICIENCY
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Revenue efficiency per staff")
    st.caption("Revenue per staff = sum of financial KPI actuals ÷ branch headcount. "
               "Higher = more revenue generated per employee.")

    if bm_df.empty:
        st.info("Upload BSC data.")
    else:
        ef_df = bm_df.sort_values("Rev/Staff (M)", ascending=False)

        fig_eff = px.bar(ef_df, x="Branch", y="Rev/Staff (M)",
                         color="Rev/Staff (M)",
                         color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                         title="Revenue per staff member (KES Millions)")
        median_rev = ef_df["Rev/Staff (M)"].median()
        fig_eff.add_hline(y=median_rev, line_dash="dash", line_color="#185FA5",
                           annotation_text=f"Median: {median_rev:.2f}M")
        fig_eff.update_layout(height=340, xaxis_tickangle=-30,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_eff, use_container_width=True)

        # Heatmap: branch vs KPI achievement
        if not df_proc.empty:
            fin_kpis = ["Deposit Growth","Loan Book Growth","Fees and Commission","DFS Revenue"]
            heat_rows = []
            for branch in bm_df["Branch"].tolist():
                row = {"Branch": branch}
                bkpis = df_proc[df_proc["Unit"]==branch]
                for kpi in fin_kpis:
                    kdf = bkpis[bkpis["KPI"]==kpi]
                    if len(kdf) and "Percent_Achieved" in kdf.columns:
                        row[kpi] = round(kdf["Percent_Achieved"].mean(), 1)
                    else:
                        row[kpi] = 0
                heat_rows.append(row)

            if heat_rows:
                heat_df = pd.DataFrame(heat_rows).set_index("Branch")
                fig_h = px.imshow(heat_df,
                    color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                    title="KPI achievement % by branch (Financial pillar)",
                    aspect="auto", text_auto=".0f")
                fig_h.update_layout(height=max(300, len(heat_df)*22))
                st.plotly_chart(fig_h, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 4 — CROSS-SELL ENGINE
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Cross-sell engine")
    st.caption("Track cross-sell performance from daily logs. "
               "Identify top cross-sellers and under-utilised capacity.")

    blm = st.session_state.get("branch_log_manager")
    if not blm or not blm.logs:
        st.info("No daily logs yet. Staff must submit daily logs to track cross-sell.")
    else:
        hist_xs = blm.get_history(days=30)
        val_xs  = [l for l in hist_xs if l.get("validated")]

        if not val_xs:
            st.info("No validated logs yet.")
        else:
            xs_rows = []
            for l in val_xs:
                xs_rows.append({
                    "Staff":      l["staff_name"],
                    "Unit":       l["unit"],
                    "Role":       l["role"],
                    "Date":       l["log_date"],
                    "Cross-sells":int(l.get("cross_sell_success",0) or 0),
                    "Accounts":   int(l.get("accounts_opened",0) or 0),
                    "DFS":        int(l.get("dfs_registrations",0) or 0),
                    "Bancassurance": int(l.get("bancassurance_sold",0) or 0),
                })

            xs_df = pd.DataFrame(xs_rows)
            staff_xs = xs_df.groupby(["Staff","Unit","Role"]).agg(
                Total_XS   = ("Cross-sells","sum"),
                Days_logged= ("Date","nunique"),
                Accounts   = ("Accounts","sum"),
                DFS        = ("DFS","sum"),
            ).reset_index()
            staff_xs["XS per day"] = (staff_xs["Total_XS"] / staff_xs["Days_logged"]).round(2)
            staff_xs = staff_xs.sort_values("Total_XS", ascending=False)

            xc1,xc2,xc3 = st.columns(3)
            xc1.metric("Total cross-sells (30d)", int(staff_xs["Total_XS"].sum()))
            xc2.metric("Top performer",           staff_xs.iloc[0]["Staff"] if len(staff_xs) else "—")
            xc3.metric("Avg XS/staff/day",        f"{staff_xs['XS per day'].mean():.2f}")

            fig_xs = px.bar(staff_xs.head(15), x="Staff", y="Total_XS",
                             color="Unit", title="Cross-sells by staff (last 30 days)",
                             labels={"Total_XS":"Total cross-sells"})
            fig_xs.update_layout(height=300, xaxis_tickangle=-30,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_xs, use_container_width=True)

            st.dataframe(staff_xs, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — NETWORK COMPARISON
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Network benchmarking")
    st.caption("Compare branches within the same region and across the network.")

    if bm_df.empty:
        st.info("Upload BSC data.")
    else:
        # Region comparison
        reg_df = bm_df.groupby("Region").agg(
            Branches      = ("Branch","count"),
            Avg_Opt_Score = ("Opt Score","mean"),
            Avg_BSC       = ("Avg BSC","mean"),
            Total_Staff   = ("Total Staff","sum"),
            Biz_Staff     = ("Business Staff","sum"),
            Rev_Total     = ("Revenue YTD","sum"),
        ).reset_index()
        reg_df["Biz Ratio"]      = reg_df["Biz_Staff"] / reg_df["Total_Staff"]
        reg_df["Rev/Staff"]      = reg_df["Rev_Total"]  / reg_df["Total_Staff"]
        reg_df["Avg Opt Score"]  = reg_df["Avg_Opt_Score"].round(1)
        reg_df["Avg BSC"]        = reg_df["Avg_BSC"].round(2)

        nc1, nc2 = st.columns(2)
        with nc1:
            fig_reg = px.bar(reg_df, x="Region", y="Avg Opt Score",
                              color="Region", title="Average optimization score by region",
                              text="Avg Opt Score",
                              color_discrete_sequence=["var(--brand-primary,#006B3F)","#F5A623","#185FA5"])
            fig_reg.update_layout(height=280, showlegend=False,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_reg, use_container_width=True)

        with nc2:
            fig_biz = px.bar(reg_df, x="Region", y="Biz Ratio",
                              color="Region", title="Business staff ratio by region",
                              text=reg_df["Biz Ratio"].apply(lambda x: f"{x:.0%}"),
                              color_discrete_sequence=["var(--brand-primary,#006B3F)","#F5A623","#185FA5"])
            fig_biz.add_hline(y=0.60, line_dash="dash", line_color="#8E44AD",
                               annotation_text="60% target")
            fig_biz.update_yaxes(tickformat=".0%")
            fig_biz.update_layout(height=280, showlegend=False,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_biz, use_container_width=True)

        # Radar comparison — top 3 vs bottom 3
        top3    = bm_df.head(3)["Branch"].tolist()
        bottom3 = bm_df.tail(3)["Branch"].tolist()
        sel_branches = st.multiselect("Compare branches",
            bm_df["Branch"].tolist(), default=top3[:2]+bottom3[:1], key="cmp_br")

        if sel_branches:
            radar_metrics = ["Avg BSC","SLA Score","Log Compliance",
                              "Business Ratio","Rev/Staff (M)"]
            fig_r = go.Figure()
            for branch in sel_branches:
                row = bm_df[bm_df["Branch"]==branch].iloc[0]
                # Normalise for radar
                vals = [
                    row["Avg BSC"]/5.0,
                    row["SLA Score"],
                    row["Log Compliance"],
                    min(row["Business Ratio"]/0.6, 1.0),
                    min(row["Rev/Staff (M)"]/10, 1.0),
                ]
                fig_r.add_scatterpolar(
                    r=vals+[vals[0]], theta=radar_metrics+[radar_metrics[0]],
                    fill="toself", name=branch)
            fig_r.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0,1])),
                height=380, title="Branch performance radar",
                legend=dict(orientation='h', y=-0.15))
            st.plotly_chart(fig_r, use_container_width=True)

        # Full comparison table
        st.markdown("#### Full network comparison table")
        cmp_cols = ["Branch","Region","Opt Score","Avg BSC","SLA Score",
                    "Business Ratio","Total Staff","Rev/Staff (M)","Cross-sells"]
        cmp_df = bm_df[cmp_cols].copy()
        cmp_df["SLA Score"]      = cmp_df["SLA Score"].apply(lambda x: f"{x:.1%}")
        cmp_df["Business Ratio"] = cmp_df["Business Ratio"].apply(lambda x: f"{x:.1%}")
        st.dataframe(cmp_df, use_container_width=True, hide_index=True)
