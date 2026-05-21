"""pages/113_branch_ranking.py — v10.331

Branch Ranking Report — 94-branch comparison view across the 21-KPI
scorecard. Per banking convention, branch performance IS the Branch
Manager's performance, so this page is the ranking of Branch Managers
by their branch's BSC.

Drill-down flow:
    Chief Retail (3.36)
      → Head of Branches (3.36)
          → 10 Area Managers (3.02 – 3.74)
              → 94 Branch Managers (this page)

Sort/filter by any of the 21 KPIs. Group by Area Manager. Highlight
top/bottom quartile. Click a row to see the full per-BM scorecard.

Tabs (≤7, G4-compliant):
    1. Overall ranking
    2. By Area Manager
    3. KPI heatmap
    4. Bottom-quartile attention
    5. Trend across quarters
    6. KPI distribution
    7. Drill-down

Audit: G130 (UI integration), G160 (manifest), G220 (BM gen).
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from utils.core import *
from pages._shared import load_shared_state
from pages._access import require_access

require_access("sales_customer.branch_log")  # piggyback existing scope

# ── Page header ────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏆 Branch Ranking</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "94 branches scored across the 21-KPI BSC scorecard</span></div>",
    unsafe_allow_html=True,
)
st.caption(
    "Branch performance IS the Branch Manager's performance. "
    "Strategic financial (PBT, NFI, CASA, growth), credit quality "
    "(NPL, PAR, loan growth), customer engagement (new accounts, "
    "dormancy, top-100 deposits), operational excellence (audit, "
    "compliance, CX, productivity)."
)

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = (
    load_shared_state()
)

# ── Period selector ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
periods_available = sorted(
    [p.stem.replace("cascade_scores_", "")
     for p in (ROOT / "data").glob("cascade_scores_*.json")],
    reverse=True,
)
period = st.selectbox(
    "Reporting period",
    periods_available,
    index=0,
    help="Cascade scores are pre-computed per quarter",
)

# ── Load cascade scores + BSC actuals ──────────────────────────────
@st.cache_data(ttl=120)
def _load_branch_data(_period: str):
    """Build the per-branch dataset for the ranking view."""
    from utils.virtual_bank import staff_universe
    from utils.db import db as _db

    u = staff_universe()
    cs = _db.load_json(f"cascade_scores_{_period}.json") or {}
    actuals = _db.load_json(f"bsc_actuals_{_period}.json") or []

    if not cs and not actuals:
        return pd.DataFrame(), pd.DataFrame()

    scores = cs.get("scores", {}) if isinstance(cs, dict) else {}
    if isinstance(actuals, dict):
        actuals = actuals.get("actuals", [])

    # Index BSC actuals by (staff_code, kpi_id)
    actuals_by_bm: dict = {}
    for a in actuals:
        if a.get("source_module") == "branch_manager_generator":
            actuals_by_bm.setdefault(a["staff_code"], {})[
                a["kpi_id"]
            ] = a.get("value")

    # Find all BMs
    bm_records = [
        r for r in u.values()
        if "Branch Manager" in r.role
        and "Assistant" not in r.role
        and "Asst" not in r.role
        and r.active
    ]

    # Build Area Manager lookup
    am_lookup = {
        r.staff_code: r.full_name
        for r in u.values() if r.role == "Area Manager"
    }

    rows = []
    for bm in bm_records:
        score = scores.get(bm.staff_code)
        am_code = bm.manager_code
        am_name = am_lookup.get(am_code, "—")
        kpis = actuals_by_bm.get(bm.staff_code, {})
        rows.append({
            "Staff Code": bm.staff_code,
            "Branch Manager": bm.full_name,
            "Role": bm.role,
            "Area Manager": am_name,
            "AM Code": am_code,
            "Overall Score": score,
            "PBT (M)": kpis.get("PBT", 0) / 1_000_000
                          if kpis.get("PBT") else None,
            "Total NFI (M)": kpis.get("Total NFI", 0) / 1_000_000
                                 if kpis.get("Total NFI") else None,
            "CASA Ratio (%)": kpis.get("CASA Ratio"),
            "Loan Book Growth (%)": kpis.get("Loan Book Growth"),
            "NPL Ratio (%)": kpis.get("NPL_RATIO"),
            "PAR (%)": kpis.get("PAR"),
            "New Accounts": kpis.get("NEW_ACCOUNTS"),
            "CX Score": kpis.get("CX Score"),
            "Audit Score": kpis.get("Audit Score"),
            "Compliance": kpis.get("COMPLIANCE_SCORE"),
            "Staff Productivity": kpis.get("Staff Productivity"),
        })

    df = pd.DataFrame(rows)
    # Add quartile labels
    if not df.empty and df["Overall Score"].notna().any():
        q1, q3 = df["Overall Score"].quantile([0.25, 0.75])
        def _band(s):
            if pd.isna(s):
                return "—"
            if s >= q3:
                return "🟢 Top quartile"
            if s <= q1:
                return "🔴 Bottom quartile"
            return "🟡 Middle"
        df["Band"] = df["Overall Score"].apply(_band)

    # Per-AM aggregate
    if not df.empty:
        am_agg = (
            df.groupby(["AM Code", "Area Manager"], dropna=False)
            .agg(
                Branches=("Staff Code", "count"),
                AM_Mean_Score=("Overall Score", "mean"),
                AM_Min_Score=("Overall Score", "min"),
                AM_Max_Score=("Overall Score", "max"),
                Avg_PBT_M=("PBT (M)", "mean"),
                Avg_NPL=("NPL Ratio (%)", "mean"),
            )
            .reset_index()
            .sort_values("AM_Mean_Score", ascending=False)
        )
    else:
        am_agg = pd.DataFrame()

    return df, am_agg


df, am_agg = _load_branch_data(period)

# v10.331 — currency label sourced from org_config (G162)
try:
    _CCY = get_currency()
except Exception:
    _CCY = ""
if _CCY:
    df = df.rename(columns={
        "PBT (M)": f"PBT ({_CCY} M)",
        "Total NFI (M)": f"Total NFI ({_CCY} M)",
    })

if df.empty:
    st.warning(
        f"No branch data for {period}. The Branch Manager generator "
        "(v10.329) must have submitted actuals for this period and "
        "cascade scores must be pre-computed (v10.330)."
    )
    st.stop()

# ── Top metrics row ────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Branches", len(df))
m2.metric(
    "Mean score",
    f"{df['Overall Score'].mean():.2f}/5.0"
    if df["Overall Score"].notna().any() else "—",
)
m3.metric(
    "Top branch",
    f"{df['Overall Score'].max():.2f}/5.0"
    if df["Overall Score"].notna().any() else "—",
)
m4.metric(
    "Bottom branch",
    f"{df['Overall Score'].min():.2f}/5.0"
    if df["Overall Score"].notna().any() else "—",
)

# ── Tabs ───────────────────────────────────────────────────────────
tabs = st.tabs([
    "🏅 Overall ranking",
    "📍 By Area Manager",
    "🔥 KPI heatmap",
    "⚠️ Bottom-quartile",
    "📈 Trend",
    "📊 KPI distribution",
    "🔍 Drill-down",
])

# Tab 1 — Overall ranking
with tabs[0]:
    st.markdown(
        "**All 94 branches ranked by overall BSC score.** Sort/filter "
        "by any KPI column. Top quartile (≥75th pct) shows green; "
        "bottom quartile (≤25th pct) shows red."
    )
    ranked = df.sort_values(
        "Overall Score", ascending=False, na_position="last"
    ).reset_index(drop=True)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))
    st.dataframe(
        ranked.drop(columns=["AM Code"]),
        use_container_width=True,
        hide_index=True,
        height=520,
    )

# Tab 2 — By Area Manager
with tabs[1]:
    st.markdown(
        "**Area Managers ranked by mean branch score.** Area Manager "
        "BSC IS the aggregate of branches reporting to them."
    )
    if not am_agg.empty:
        display_am = am_agg.copy()
        for col in ("AM_Mean_Score", "AM_Min_Score", "AM_Max_Score"):
            display_am[col] = display_am[col].round(2)
        display_am["Avg_PBT_M"] = display_am["Avg_PBT_M"].round(1)
        display_am["Avg_NPL"] = display_am["Avg_NPL"].round(2)
        st.dataframe(
            display_am,
            use_container_width=True,
            hide_index=True,
        )
        st.markdown("**BM-level view by Area Manager:**")
        for _, am_row in display_am.iterrows():
            with st.expander(
                f"{am_row['Area Manager']} "
                f"({am_row['Branches']} branches, "
                f"score {am_row['AM_Mean_Score']:.2f})"
            ):
                sub = df[df["AM Code"] == am_row["AM Code"]].sort_values(
                    "Overall Score", ascending=False
                )
                st.dataframe(
                    sub.drop(columns=["AM Code", "Area Manager"]),
                    use_container_width=True,
                    hide_index=True,
                )

# Tab 3 — KPI heatmap
with tabs[2]:
    st.markdown(
        "**KPI performance heatmap.** Each cell shows the BM's value "
        "for a KPI; colours indicate quartile (green/yellow/red)."
    )
    pbt_col = f"PBT ({_CCY} M)" if _CCY else "PBT (M)"
    nfi_col = f"Total NFI ({_CCY} M)" if _CCY else "Total NFI (M)"
    kpi_cols = [
        pbt_col, nfi_col, "CASA Ratio (%)",
        "Loan Book Growth (%)", "NPL Ratio (%)", "PAR (%)",
        "New Accounts", "CX Score", "Audit Score",
        "Compliance", "Staff Productivity",
    ]
    heat = df[["Branch Manager", "Overall Score"] + kpi_cols].copy()
    heat = heat.sort_values("Overall Score", ascending=False).head(30)
    st.dataframe(
        heat.style.background_gradient(
            subset=[c for c in kpi_cols if c not in (
                "NPL Ratio (%)", "PAR (%)"
            )],
            cmap="RdYlGn",
        ).background_gradient(
            subset=["NPL Ratio (%)", "PAR (%)"],
            cmap="RdYlGn_r",
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Top 30 branches shown. PBT, NFI, growth, CASA, new accounts, "
        "CX, audit, compliance: green = higher is better. NPL Ratio "
        "and PAR: green = lower is better (inverted scale)."
    )

# Tab 4 — Bottom-quartile attention
with tabs[3]:
    st.markdown(
        "**Bottom-quartile branches — leadership attention needed.** "
        "These branches scored in the bottom 25% across the bank. "
        "Common patterns: NPL ratio breach, audit findings, low "
        "deposit growth, or weak CX."
    )
    bottom = df[df["Band"] == "🔴 Bottom quartile"].sort_values(
        "Overall Score"
    )
    st.dataframe(
        bottom.drop(columns=["AM Code"]),
        use_container_width=True,
        hide_index=True,
    )
    if not bottom.empty:
        # Show the top failing KPIs
        st.markdown("**Common failure patterns in bottom quartile:**")
        check_cols = {
            "NPL Ratio (%)": ("Over target", lambda s: s > 8.0),
            "PAR (%)": ("Over target", lambda s: s > 6.0),
            "Audit Score": ("Below 70", lambda s: s < 70),
            "CASA Ratio (%)": ("Below 55", lambda s: s < 55),
        }
        for col, (label, fn) in check_cols.items():
            if col in bottom.columns:
                count = bottom[col].apply(
                    lambda x: fn(x) if pd.notna(x) else False
                ).sum()
                if count > 0:
                    st.markdown(
                        f"- **{count} of {len(bottom)} bottom-quartile "
                        f"branches**: {col} {label.lower()}"
                    )

# Tab 5 — Trend across quarters
with tabs[4]:
    st.markdown(
        "**Branch score trends across the last 4 quarters.** Tracks "
        "improvement/decline at branch and Area Manager level."
    )
    trend_periods = sorted(periods_available)[-4:]
    trend_rows = []
    from utils.virtual_bank import staff_universe as _su
    u_trend = _su()
    bm_codes = [
        r.staff_code for r in u_trend.values()
        if "Branch Manager" in r.role
        and "Assistant" not in r.role
        and "Asst" not in r.role
        and r.active
    ]
    for tp in trend_periods:
        from utils.db import db as _db_t
        s_data = _db_t.load_json(f"cascade_scores_{tp}") or {}
        if not s_data:
            continue
        s = s_data.get("scores", {}) if isinstance(s_data, dict) else {}
        bm_scores = [
            s[c] for c in bm_codes
            if c in s and s[c] is not None
        ]
        if bm_scores:
            trend_rows.append({
                "Period": tp,
                "BMs scoring": len(bm_scores),
                "Mean": round(sum(bm_scores) / len(bm_scores), 2),
                "Min": round(min(bm_scores), 2),
                "Max": round(max(bm_scores), 2),
            })
    if trend_rows:
        tdf = pd.DataFrame(trend_rows)
        st.dataframe(tdf, use_container_width=True, hide_index=True)
        st.line_chart(
            tdf.set_index("Period")[["Mean", "Min", "Max"]],
            height=320,
        )

# Tab 6 — KPI distribution
with tabs[5]:
    st.markdown(
        "**KPI value distributions across the 94-branch network.** "
        "Shows where the network is healthy vs concentrated risk."
    )
    pbt_col_d = f"PBT ({_CCY} M)" if _CCY else "PBT (M)"
    dist_cols = [
        pbt_col_d, "NPL Ratio (%)", "PAR (%)",
        "CASA Ratio (%)", "Audit Score", "CX Score",
    ]
    cols = st.columns(2)
    for i, col_name in enumerate(dist_cols):
        if col_name in df.columns:
            col_data = df[col_name].dropna()
            if len(col_data) > 0:
                with cols[i % 2]:
                    st.markdown(f"**{col_name}**")
                    summary = pd.DataFrame({
                        "Metric": ["Mean", "Median", "Min", "Max", "Std"],
                        "Value": [
                            round(col_data.mean(), 2),
                            round(col_data.median(), 2),
                            round(col_data.min(), 2),
                            round(col_data.max(), 2),
                            round(col_data.std(), 2),
                        ],
                    })
                    st.dataframe(
                        summary,
                        hide_index=True,
                        use_container_width=True,
                    )

# Tab 7 — Drill-down
with tabs[6]:
    st.markdown("**Drill into a single branch's full 21-KPI scorecard.**")
    bm_options = sorted(df["Branch Manager"].tolist())
    if bm_options:
        choice = st.selectbox(
            "Select Branch Manager",
            bm_options,
            key="bm_drilldown",
        )
        bm_row = df[df["Branch Manager"] == choice].iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric("Overall Score", f"{bm_row['Overall Score']}/5.0")
        c2.metric("Role", bm_row["Role"])
        c3.metric("Area Manager", bm_row["Area Manager"])

        # Show all KPIs
        st.markdown("**Full KPI scorecard:**")
        kpi_data = []
        for col in df.columns:
            if col not in (
                "Staff Code", "Branch Manager", "Role",
                "Area Manager", "AM Code", "Overall Score", "Band",
            ):
                val = bm_row[col]
                if pd.notna(val):
                    kpi_data.append({"KPI": col, "Value": val})
        st.dataframe(
            pd.DataFrame(kpi_data),
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            f"Staff Code: {bm_row['Staff Code']} · "
            f"Band: {bm_row.get('Band', '—')} · "
            f"Reports to: {bm_row['Area Manager']} "
            f"({bm_row['AM Code']})"
        )

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

