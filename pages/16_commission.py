"""pages/16_commission.py — DSO Commission Model & Pipeline Rankings."""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
try:
    from utils.core import get_fiscal_year as _gfy
except: _gfy = lambda: _gfy()

from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope
require_access("products_pricing.commission")
DATA = Path(__file__).parent.parent / "data"
um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
role     = str(ud.get("role", "")).lower()
is_admin = ud.get("is_admin", False)
sc       = str(ud.get("staff_code", ""))
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

# ── COMMISSION TIERS ─────────────────────────────────────────────────
COMMISSION_TIERS = {
    "Disbursements Retail Loans": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0.0000, "label": "Below 50% — no commission"},
        {"min_pct": 50,  "max_pct": 70,  "rate": 0.0005, "label": "50–70% — 0.05% of disbursed"},
        {"min_pct": 70,  "max_pct": 90,  "rate": 0.0010, "label": "70–90% — 0.10% of disbursed"},
        {"min_pct": 90,  "max_pct": 100, "rate": 0.0015, "label": "90–100% — 0.15% of disbursed"},
        {"min_pct": 100, "max_pct": 110, "rate": 0.0020, "label": "100–110% — 0.20% of disbursed"},
        {"min_pct": 110, "max_pct": 999, "rate": 0.0025, "label": ">110% — 0.25% of disbursed"},
    ],
    "Retail & MSME Deposit Growth": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0.0000, "label": "Below 50% — no commission"},
        {"min_pct": 50,  "max_pct": 70,  "rate": 0.0003, "label": "50–70% — 0.03%"},
        {"min_pct": 70,  "max_pct": 90,  "rate": 0.0005, "label": "70–90% — 0.05%"},
        {"min_pct": 90,  "max_pct": 100, "rate": 0.0008, "label": "90–100% — 0.08%"},
        {"min_pct": 100, "max_pct": 110, "rate": 0.0010, "label": "100–110% — 0.10%"},
        {"min_pct": 110, "max_pct": 999, "rate": 0.0015, "label": ">110% — 0.15%"},
    ],
    "New Accounts": [
        {"min_pct": 0,   "max_pct": 50,  "rate": 0,    "label": "Below 50% — no commission", "per_unit": 0},
        {"min_pct": 50,  "max_pct": 70,  "rate": 0,    "label": "50–70% — KES 200/customer",   "per_unit": 200},
        {"min_pct": 70,  "max_pct": 90,  "rate": 0,    "label": "70–90% — KES 350/customer",   "per_unit": 350},
        {"min_pct": 90,  "max_pct": 100, "rate": 0,    "label": "90–100% — KES 500/customer",  "per_unit": 500},
        {"min_pct": 100, "max_pct": 110, "rate": 0,    "label": "100–110% — KES 750/customer", "per_unit": 750},
        {"min_pct": 110, "max_pct": 999, "rate": 0,    "label": ">110% — KES 1,000/customer",  "per_unit": 1000},
    ],
    "Collection Throughput": [
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

DSO_ROLES = ["Direct Sales Agent","Relationship Officer Personal Banking",
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
        if tier.get("min_pct", 0) <= pct < tier.get("max_pct", 0):
            if "per_unit" in tier:
                comm = actual * tier.get("per_unit", 0)
            else:
                comm = actual * tier.get("rate", 0)
            break
    # BSC performance multiplier
    mult = BONUS_MULTIPLIERS.get(remark, 1.0)
    return round(comm * mult, 2)

# ── HEADER ───────────────────────────────────────────────────────────

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💰 Commission</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "RM incentives · Tier calculation</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💰 Commission</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "RM incentives · Tier calculation · Payouts</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💰 Commission</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "RM incentives · Tier calculation · Payouts</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💰 Commission</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "RM incentives · Tier calculation · Payroll</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style=\'padding:16px 22px;background:#1D4D35;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>Commission Model & Sales Rankings</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Direct Sales Agents · Relationship Managers · Tier-based commissions · Leaderboard</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)

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

                # Try to get cascade targets for accuracy
                _casc_inst_c = st.session_state.get("cascade_manager")
                _staff_code_c = str(sr.get("Staff Code","") or "")
                _casc_given_c = (_casc_inst_c.get_what_i_was_given(
                    _staff_code_c, _gfy(), sel_staff) if _casc_inst_c else [])
                _casc_tgt_map = {g["kpi"]: float(g["amount"]) for g in _casc_given_c}

                for kpi, tiers in COMMISSION_TIERS.items():
                    kdf = (df_proc[(df_proc["Staff Name"]==sel_staff) & (df_proc["KPI"]==kpi)]
                           if not df_proc.empty else pd.DataFrame())
                    actual = float(kdf["YTD_Actual"].values[0]) if (len(kdf) and "YTD_Actual" in kdf.columns) else 0

                    # Use cascade target if available, else KPI data target
                    if kpi in _casc_tgt_map and _casc_tgt_map[kpi]:
                        target = _casc_tgt_map[kpi]
                        tgt_src = "📊 cascade"
                    elif len(kdf):
                        target = float(kdf["Annual Target"].values[0])
                        tgt_src = "📁 uploaded"
                    else:
                        continue

                    if target == 0: continue
                    pct    = actual/target*100
                    comm   = compute_commission(kpi, actual, target, remark)
                    total_comm += comm
                    tier_label = next((t["label"] for t in tiers
                                       if t["min_pct"]<=pct<t["max_pct"]), "—")
                    comm_breakdown.append({
                        "KPI":              kpi,
                        "Target":           fmt_num(target, True),
                        "Source":           tgt_src,
                        "YTD Actual":       fmt_num(actual, True),
                        "Achievement":      f"{pct:.1f}%",
                        "Tier":             tier_label.split("—")[0].strip(),
                        "Commission (KES)": f"KES {comm:,.0f}",
                    })

                if comm_breakdown:
                    cbd_df = pd.DataFrame(comm_breakdown)
                    st.dataframe(cbd_df, use_container_width=True, hide_index=True)

                    st.markdown(
                        f"<div style='padding:14px 18px;background:var(--brand-light,#E8F5EE);"
                        f"border-radius:8px;text-align:center;margin-top:12px'>"
                        f"<div style='font-size:28px;font-weight:700;color:var(--brand-primary,#006B3F)'>"
                        f"KES {total_comm:,.0f}</div>"
                        f"<div style='font-size:13px;color:#444;margin-top:4px'>"
                        f"Total commission earned (YTD) · {remark} · BSC {bsc:.2f}</div>"
                        f"</div>", unsafe_allow_html=True)
                else:
                    st.info("No commission-eligible KPIs found for this staff member. "
                            "Ensure cascade targets are set and BSC data is uploaded.")

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
                f"<span style='background:{tier['color']};color:var(--color-background-primary);padding:2px 8px;"
                f"border-radius:10px;font-size:10px'>{row['Tier']}</span></div>"
                f"<div style='text-align:right'>"
                f"<div style='font-size:16px;font-weight:700;color:var(--brand-primary,#006B3F)'>"
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
                             color_discrete_map={"Annual Target":"#CCCCCC","YTD_Actual":"var(--brand-primary,#006B3F)"})
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

# ── Tier Calculator ───────────────────────────────────────────────
with st.expander("🧮 Commission Tier Calculator", expanded=False):
    st.markdown("**Compute commission for any BSC score and role:**")
    _cc1,_cc2,_cc3 = st.columns(3)
    _sim_score = _cc1.number_input("BSC Score", 1.0, 5.0, 3.5, 0.1, key="cc_score")
    _sim_grade = _cc2.selectbox("Role Grade", ["G1","G2","G3","G4","G5","G6"], key="cc_grade", index=2)
    _sim_base  = _cc3.number_input("Gross Salary (KES)", 30000.0, 500000.0, 80000.0, 5000.0, key="cc_base")
    
    _TIERS = {
        "Exceeds Exceptional (≥4.5)":   (4.5, 0.25),
        "Exceeds Expectations (4.0–4.4)":(4.0, 0.20),
        "Meets Plus (3.5–3.9)":          (3.5, 0.15),
        "Meets Expectations (3.0–3.4)":  (3.0, 0.10),
        "Developing (2.5–2.9)":          (2.5, 0.05),
        "Below Expectations (<2.5)":     (0.0, 0.00),
    }
    _tier_name = next((t for t,(mn,_) in _TIERS.items() if _sim_score>=mn), "Below Expectations")
    _tier_pct  = next((p for _,(mn,p) in _TIERS.items() if _sim_score>=mn), 0)
    _comm_amt  = round(_sim_base * _tier_pct, 0)
    st.markdown(
        f"**Result:** {_tier_name} — **{_tier_pct*100:.0f}% of gross salary** = **KES {_comm_amt:,.0f}**")
    
    st.markdown("**Tier schedule:**")
    for tier,(min_score,pct) in _TIERS.items():
        active = "→ **YOU**" if tier==_tier_name else ""
        st.markdown(f"  {'🟢' if pct>=0.15 else '🟡' if pct>0 else '🔴'} "
                    f"{tier}: **{pct*100:.0f}%** of salary {active}")

# ── Manager team view ─────────────────────────────────────────────
_is_manager = any(x in role.lower() for x in ("manager","director","head","chief","area"))
if _is_manager or is_admin:
    with st.expander("👥 My Team Commission Summary", expanded=False):
        import pandas as _pd_tc
        _comm_all = json.loads((DATA/"commission_records.json").read_text()) if (DATA/"commission_records.json").exists() else []
        _scores_all = json.loads((DATA/"feb_2026_staff_scores.json").read_text()) if (DATA/"feb_2026_staff_scores.json").exists() else {}
        
        # Filter to unit if branch manager
        _unit = ud.get("unit","")
        if _unit and not is_admin:
            _team_comm = [c for c in _comm_all if c.get("unit","")==_unit]
        else:
            _team_comm = _comm_all[:50]  # top 50 for HO managers
        
        if _team_comm:
            _tc_rows = [{"Staff":c.get("staff_name","")[:22],"Tier":c.get("tier","—"),
                          "BSC Score":c.get("bsc_score",0),"Commission (KES)":c.get("total_commission",0),
                          "Status":c.get("status","Pending")}
                         for c in sorted(_team_comm,key=lambda x:-x.get("total_commission",0))[:20]]
            st.dataframe(_pd_tc.DataFrame(_tc_rows), use_container_width=True, hide_index=True)
            _team_total = sum(c.get("total_commission",0) for c in _team_comm)
            st.caption(f"Team total commission: KES {_team_total:,.0f}")
        else:
            st.info("No commission records found for your team.")

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

