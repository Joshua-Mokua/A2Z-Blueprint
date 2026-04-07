"""pages/16_commission.py — DSO Commission Model & Pipeline Rankings."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

# ── COMMISSION TIERS ─────────────────────────────────────────────────
COMMISSION_TIERS = {
    "Loans Disbursement": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0.0000, "label": "Below 50% — no commission"},
        {"min_pct": 50,  "max_pct": 70,  "rate": 0.0005, "label": "50–70% — 0.05% of disbursed"},
        {"min_pct": 70,  "max_pct": 90,  "rate": 0.0010, "label": "70–90% — 0.10% of disbursed"},
        {"min_pct": 90,  "max_pct": 100, "rate": 0.0015, "label": "90–100% — 0.15% of disbursed"},
        {"min_pct": 100, "max_pct": 110, "rate": 0.0020, "label": "100–110% — 0.20% of disbursed"},
        {"min_pct": 110, "max_pct": 999, "rate": 0.0025, "label": ">110% — 0.25% of disbursed"},
    ],
    "Deposit Growth": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0.0000, "label": "Below 50% — no commission"},
        {"min_pct": 50,  "max_pct": 70,  "rate": 0.0003, "label": "50–70% — 0.03%"},
        {"min_pct": 70,  "max_pct": 90,  "rate": 0.0005, "label": "70–90% — 0.05%"},
        {"min_pct": 90,  "max_pct": 100, "rate": 0.0008, "label": "90–100% — 0.08%"},
        {"min_pct": 100, "max_pct": 110, "rate": 0.0010, "label": "100–110% — 0.10%"},
        {"min_pct": 110, "max_pct": 999, "rate": 0.0015, "label": ">110% — 0.15%"},
    ],
    "New Customer Acquisition": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0,    "label": "Below 50% — no commission", "per_unit": 0},
        {"min_pct": 50,  "max_pct": 70,  "rate": 0,    "label": "50–70% — KES 200/customer",   "per_unit": 200},
        {"min_pct": 70,  "max_pct": 90,  "rate": 0,    "label": "70–90% — KES 350/customer",   "per_unit": 350},
        {"min_pct": 90,  "max_pct": 100, "rate": 0,    "label": "90–100% — KES 500/customer",  "per_unit": 500},
        {"min_pct": 100, "max_pct": 110, "rate": 0,    "label": "100–110% — KES 750/customer", "per_unit": 750},
        {"min_pct": 110, "max_pct": 999, "rate": 0,    "label": ">110% — KES 1,000/customer",  "per_unit": 1000},
    ],
    "DFS Revenue": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0.00,  "label": "Below 50% — no commission"},
        {"min_pct": 50,  "max_pct": 100, "rate": 0.005, "label": "50–100% — 0.5% of DFS revenue"},
        {"min_pct": 100, "max_pct": 999, "rate": 0.010, "label": ">100% — 1.0% of DFS revenue"},
    ],
    "Bancassurance": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0.00,  "label": "Below 50% — no commission"},
        {"min_pct": 50,  "max_pct": 100, "rate": 0.020, "label": "50–100% — 2% of premiums"},
        {"min_pct": 100, "max_pct": 999, "rate": 0.030, "label": ">100% — 3% of premiums"},
    ],
}

DSO_ROLES = ["Direct Sales Officer","Relationship Officer Personal Banking",
             "Relationship Manager SME","Relationship Manager Corporate"]

BONUS_MULTIPLIERS = {
    "Exceeded By Far": 1.5,
    "Exceeded":        1.2,
    "Met":             1.0,
    "Partially Met":   0.0,
    "Unmet":           0.0,
}

LEADERBOARD_TIERS = [
    {"rank_min":1,  "rank_max":1,   "badge":"🥇 Champion",  "bonus_pct":20, "color":"#FFD700"},
    {"rank_min":2,  "rank_max":3,   "badge":"🥈 Elite",     "bonus_pct":15, "color":"#C0C0C0"},
    {"rank_min":4,  "rank_max":5,   "badge":"🥉 Star",      "bonus_pct":10, "color":"#CD7F32"},
    {"rank_min":6,  "rank_max":10,  "badge":"⭐ Performer", "bonus_pct":5,  "color":"#185FA5"},
    {"rank_min":11, "rank_max":999, "badge":"👤 Active",    "bonus_pct":0,  "color":"#888"},
]

def compute_commission(kpi, actual, target, remark):
    """Compute commission for a single KPI achievement."""
    if target == 0 or actual <= 0:
        return 0.0
    pct = actual / target * 100
    tiers = COMMISSION_TIERS.get(kpi, [])
    if not tiers:
        return 0.0
    comm = 0.0
    for tier in tiers:
        if tier["min_pct"] <= pct < tier["max_pct"]:
            if "per_unit" in tier:
                comm = actual * tier["per_unit"]
            else:
                comm = actual * tier["rate"]
            break
    # BSC performance multiplier
    mult = BONUS_MULTIPLIERS.get(remark, 1.0)
    return round(comm * mult, 2)

# ── HEADER ───────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:14px 20px;background:#1D4D35;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:16px;font-weight:500'>Commission Model & Sales Rankings</div>"
    "<div style='color:#9FE1CB;font-size:11px;margin-top:2px'>"
    "Direct Sales Officers · Relationship Managers · Tier-based commissions · Leaderboard"
    "</div></div>", unsafe_allow_html=True)

tabs = st.tabs([
    "💰 Commission calculator",
    "🏆 Leaderboard",
    "📊 Commission payroll",
    "📋 Tier structure",
    "🎯 Targets vs actuals",
])

# ════════════════════════════════════════════════════════════════
# BUILD COMMISSION DATA
# ════════════════════════════════════════════════════════════════
def build_commission_df():
    if len(staff_scores) == 0 or df_proc.empty:
        return pd.DataFrame()

    sales_staff = staff_scores[staff_scores["Role"].isin(DSO_ROLES)].copy()
    rows = []

    for _, sr in sales_staff.iterrows():
        name   = sr["Staff Name"]
        sc     = str(sr["Staff Code"])
        role   = sr["Role"]
        unit   = sr["Unit"]
        remark = sr.get("Performance_Remark","Met")
        bsc    = sr.get("Final_BSC_Score", 0)

        total_comm = 0
        kpi_comms  = {}

        for kpi in COMMISSION_TIERS.keys():
            kdf = df_proc[(df_proc["Staff Name"]==name) & (df_proc["KPI"]==kpi)]
            if len(kdf) == 0:
                continue
            actual = float(kdf["YTD_Actual"].values[0]) if "YTD_Actual" in kdf.columns else 0
            target = float(kdf["Annual Target"].values[0])
            comm   = compute_commission(kpi, actual, target, remark)
            if comm > 0:
                kpi_comms[kpi] = comm
                total_comm += comm

        rows.append({
            "Staff Name":    name,
            "Staff Code":    sc,
            "Role":          role,
            "Unit":          unit,
            "BSC Score":     round(bsc, 2),
            "Performance":   remark,
            "Total Commission": round(total_comm),
            **{f"Comm_{k}": round(v) for k,v in kpi_comms.items()},
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("Total Commission", ascending=False)
    df = df.reset_index(drop=True)
    df["Rank"] = df.index + 1

    # Assign leaderboard tier
    def get_tier(rank):
        for t in LEADERBOARD_TIERS:
            if t["rank_min"] <= rank <= t["rank_max"]:
                return t["badge"]
        return "👤 Active"

    df["Tier"] = df["Rank"].apply(get_tier)
    return df

comm_df = build_commission_df()

# ════════════════════════════════════════════════════════════════
# TAB 1 — COMMISSION CALCULATOR
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Individual commission calculator")

    if len(staff_scores) == 0:
        st.info("Upload BSC data to use the commission calculator.")
    else:
        sales_staff_list = staff_scores[staff_scores["Role"].isin(DSO_ROLES)]["Staff Name"].tolist()
        if not sales_staff_list:
            st.info("No DSO/RM staff found in current data.")
        else:
            sel_staff = st.selectbox("Select staff", sorted(sales_staff_list), key="cc_staff")
            staff_row = staff_scores[staff_scores["Staff Name"]==sel_staff]
            if len(staff_row):
                sr       = staff_row.iloc[0]
                remark   = sr.get("Performance_Remark","Met")
                bsc      = sr.get("Final_BSC_Score", 0)
                mult     = BONUS_MULTIPLIERS.get(remark, 0.0)

                cc1,cc2,cc3 = st.columns(3)
                cc1.metric("BSC Score",    f"{bsc:.2f}")
                cc2.metric("Performance",  remark)
                cc3.metric("BSC multiplier", f"{mult:.1f}×")

                total_comm = 0
                comm_breakdown = []

                for kpi, tiers in COMMISSION_TIERS.items():
                    kdf = df_proc[(df_proc["Staff Name"]==sel_staff) & (df_proc["KPI"]==kpi)] if not df_proc.empty else pd.DataFrame()
                    if len(kdf) == 0:
                        continue
                    actual = float(kdf["YTD_Actual"].values[0]) if "YTD_Actual" in kdf.columns else 0
                    target = float(kdf["Annual Target"].values[0])
                    pct    = actual/target*100 if target else 0
                    comm   = compute_commission(kpi, actual, target, remark)
                    total_comm += comm

                    tier_label = next((t["label"] for t in tiers
                                       if t["min_pct"]<=pct<t["max_pct"]), "—")

                    comm_breakdown.append({
                        "KPI":           kpi,
                        "Target":        fmt_num(target, True),
                        "Actual":        fmt_num(actual, True),
                        "Achievement":   f"{pct:.1f}%",
                        "Rate applied":  tier_label,
                        "Commission (KES)": f"{comm:,.0f}",
                    })

                if comm_breakdown:
                    cbd_df = pd.DataFrame(comm_breakdown)
                    st.dataframe(cbd_df, use_container_width=True, hide_index=True)

                    st.markdown(
                        f"<div style='padding:14px 18px;background:#E8F5EE;"
                        f"border-radius:8px;text-align:center;margin-top:12px'>"
                        f"<div style='font-size:28px;font-weight:700;color:#006B3F'>"
                        f"KES {total_comm:,.0f}</div>"
                        f"<div style='font-size:13px;color:#444;margin-top:4px'>"
                        f"Total commission earned (YTD) · {remark} · BSC {bsc:.2f}</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.info("No commission-eligible KPIs found for this staff member.")

# ════════════════════════════════════════════════════════════════
# TAB 2 — LEADERBOARD
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Sales leaderboard")
    st.caption("Rankings based on total commission earned YTD. Refreshes automatically as BSC data is uploaded.")

    if comm_df.empty:
        st.info("No commission data yet. Upload BSC data with DSO/RM staff to populate.")
    else:
        # Summary metrics
        lc1,lc2,lc3,lc4 = st.columns(4)
        lc1.metric("Total commission pool", f"KES {comm_df['Total Commission'].sum():,.0f}")
        lc2.metric("Top earner",            comm_df.iloc[0]["Staff Name"])
        lc3.metric("Top earning",           f"KES {comm_df.iloc[0]['Total Commission']:,.0f}")
        lc4.metric("Avg commission",        f"KES {comm_df['Total Commission'].mean():,.0f}")

        # Visual leaderboard
        for _, row in comm_df.head(10).iterrows():
            tier = next((t for t in LEADERBOARD_TIERS
                         if t["rank_min"]<=row["Rank"]<=t["rank_max"]), LEADERBOARD_TIERS[-1])
            bar_w = int(row["Total Commission"] / max(comm_df["Total Commission"].max(),1) * 100)

            st.markdown(
                f"<div style='padding:10px 14px;background:var(--color-background-secondary);"
                f"border-left:5px solid {tier['color']};"
                f"border-radius:0 8px 8px 0;margin:4px 0'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<div><span style='font-size:20px;font-weight:700;color:{tier['color']}'>"
                f"#{row['Rank']}</span> "
                f"<b style='font-size:14px'>{row['Staff Name']}</b> "
                f"<span style='color:#888;font-size:11px'>{row['Role']} · {row['Unit']}</span> "
                f"<span style='background:{tier['color']};color:white;padding:2px 8px;"
                f"border-radius:10px;font-size:10px'>{row['Tier']}</span></div>"
                f"<div style='text-align:right'>"
                f"<div style='font-size:16px;font-weight:700;color:#006B3F'>"
                f"KES {row['Total Commission']:,.0f}</div>"
                f"<div style='font-size:10px;color:#888'>BSC {row['BSC Score']:.2f} · {row['Performance']}</div>"
                f"</div></div>"
                f"<div style='margin-top:6px;height:4px;background:#EEE;border-radius:2px'>"
                f"<div style='width:{bar_w}%;height:100%;background:{tier['color']};border-radius:2px'></div>"
                f"</div></div>", unsafe_allow_html=True)

        # Full table
        st.markdown("---")
        st.markdown("#### Full rankings table")
        disp_cols = ["Rank","Tier","Staff Name","Unit","BSC Score",
                     "Performance","Total Commission"]
        disp_comm = comm_df[disp_cols].copy()
        disp_comm["Total Commission"] = disp_comm["Total Commission"].apply(lambda x: f"KES {x:,.0f}")
        st.dataframe(disp_comm, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 3 — COMMISSION PAYROLL
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Commission payroll summary")
    st.caption("Download-ready commission summary for payroll processing.")

    if comm_df.empty:
        st.info("No commission data yet.")
    else:
        payroll_df = comm_df[["Staff Code","Staff Name","Unit","Role",
                               "BSC Score","Performance","Total Commission","Tier"]].copy()
        payroll_df["Month"] = datetime.now().strftime("%B %Y")
        payroll_df["Total Commission"] = payroll_df["Total Commission"].apply(lambda x: f"KES {x:,.0f}")

        st.dataframe(payroll_df, use_container_width=True, hide_index=True)

        # Region summary
        if len(comm_df):
            comm_df2 = comm_df.copy()
            if "Unit" in comm_df2.columns:
                comm_df2["Region"] = comm_df2["Unit"].map(BRANCH_REGION).fillna("Head Office")
                reg_comm = comm_df2.groupby("Region")["Total Commission"].agg(
                    ["sum","mean","count"]).reset_index()
                reg_comm.columns = ["Region","Total","Average","Headcount"]
                reg_comm["Total"] = reg_comm["Total"].apply(lambda x: f"KES {x:,.0f}")
                reg_comm["Average"] = reg_comm["Average"].apply(lambda x: f"KES {x:,.0f}")
                st.markdown("**Commission by region**")
                st.dataframe(reg_comm, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 4 — TIER STRUCTURE
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Commission tier structure")
    st.caption("Rates are applied to the YTD actual, multiplied by the BSC performance band.")

    for kpi, tiers in COMMISSION_TIERS.items():
        st.markdown(f"**{kpi}**")
        tier_rows = [{"Achievement band": t["label"],
                      "Rate": f"{t['rate']*100:.2f}%" if t.get('rate',0)>0
                               else (f"KES {t.get('per_unit',0):,}/unit" if t.get('per_unit',0)>0
                                     else "No commission")}
                     for t in tiers]
        st.dataframe(pd.DataFrame(tier_rows), use_container_width=True, hide_index=True, height=230)

    st.markdown("---")
    st.markdown("**BSC performance multipliers**")
    mult_rows = [{"Performance band": k, "Commission multiplier": f"{v:.1f}×",
                  "Effect": "Full commission" if v>=1 else ("Reduced" if v>0 else "No commission")}
                 for k,v in BONUS_MULTIPLIERS.items()]
    st.dataframe(pd.DataFrame(mult_rows), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Leaderboard tiers & bonuses**")
    lb_rows = [{"Rank":"#"+str(t["rank_min"]) if t["rank_min"]==t["rank_max"] else f"#{t['rank_min']}–{t['rank_max']}",
                "Badge":t["badge"],"Bonus":f"+{t['bonus_pct']}% recognition bonus"}
               for t in LEADERBOARD_TIERS]
    st.dataframe(pd.DataFrame(lb_rows), use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — TARGETS VS ACTUALS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("DSO / RM targets vs actuals")
    st.caption("Month-by-month tracking for all commission-eligible KPIs.")

    if df_proc.empty or len(staff_scores)==0:
        st.info("Upload BSC data.")
    else:
        sel_kpi = st.selectbox("KPI", list(COMMISSION_TIERS.keys()), key="ta_kpi")
        sales_df = staff_scores[staff_scores["Role"].isin(DSO_ROLES)].copy()
        kpi_data = df_proc[df_proc["KPI"]==sel_kpi]
        merged   = sales_df.merge(
            kpi_data[["Staff Name","Annual Target","YTD_Actual","Percent_Achieved","Score",
                       *[c for c in kpi_data.columns if any(m in c for m in
                         ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"])
                         and "Target" not in c]]],
            on="Staff Name", how="inner")

        if len(merged):
            merged["Commission"] = merged.apply(
                lambda r: compute_commission(sel_kpi,
                    float(r.get("YTD_Actual",0)),
                    float(r.get("Annual Target",0)),
                    r.get("Performance_Remark","Met")), axis=1)

            month_cols = [c for c in merged.columns
                          if any(m in c for m in ["Jan","Feb","Mar","Apr","May","Jun",
                                                   "Jul","Aug","Sep","Oct","Nov","Dec"])
                          and "Target" not in c]

            # Convert to long-form for plotly (avoids mixed-type wide-form error)
            _plot_df = merged.sort_values("Percent_Achieved", ascending=False).copy()
            _plot_df["Annual Target"] = pd.to_numeric(_plot_df["Annual Target"], errors="coerce").fillna(0)
            _plot_df["YTD_Actual"]    = pd.to_numeric(_plot_df["YTD_Actual"],    errors="coerce").fillna(0)
            _long = pd.melt(_plot_df, id_vars=["Staff Name"],
                             value_vars=["Annual Target","YTD_Actual"],
                             var_name="Metric", value_name="Value")
            fig_tv = px.bar(_long, x="Staff Name", y="Value", color="Metric",
                             barmode="group",
                             title=f"{sel_kpi} — target vs actual",
                             color_discrete_map={"Annual Target":"#CCCCCC","YTD_Actual":"#006B3F"})
            fig_tv.update_layout(height=320, xaxis_tickangle=-30,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_tv, use_container_width=True)

            # Monthly trend for top 5
            if month_cols:
                top5 = merged.nlargest(5, "YTD_Actual")["Staff Name"].tolist()
                trend_rows = []
                for _, r in merged[merged["Staff Name"].isin(top5)].iterrows():
                    for mc in month_cols:
                        trend_rows.append({
                            "Staff": r["Staff Name"],
                            "Month": mc,
                            "Actual": float(r.get(mc,0) or 0),
                        })
                if trend_rows:
                    tr_df = pd.DataFrame(trend_rows)
                    fig_mt = px.line(tr_df, x="Month", y="Actual", color="Staff",
                                     title=f"{sel_kpi} — monthly trend (top 5)",
                                     markers=True)
                    fig_mt.update_layout(height=300,
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_mt, use_container_width=True)

            disp_tv = merged[["Staff Name","Unit","Annual Target","YTD_Actual",
                               "Percent_Achieved","Score","Commission"]].copy()
            disp_tv["Annual Target"]    = disp_tv["Annual Target"].apply(lambda x: fmt_num(x,True))
            disp_tv["YTD_Actual"]       = disp_tv["YTD_Actual"].apply(lambda x: fmt_num(x,True))
            disp_tv["Percent_Achieved"] = disp_tv["Percent_Achieved"].apply(lambda x: f"{x:.1f}%")
            disp_tv["Commission"]       = disp_tv["Commission"].apply(lambda x: f"KES {x:,.0f}")
            st.dataframe(disp_tv, use_container_width=True, hide_index=True)
        else:
            st.info(f"No {sel_kpi} data found for DSO/RM staff.")
