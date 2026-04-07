"""pages/1_perform.py — Perform module."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *

from pages._shared import load_shared_state

# Load session state
um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

# Shared data
staff_scores  = st.session_state.get("staff_scores", pd.DataFrame())
df_proc       = st.session_state.get("df_processed", pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
all_months    = st.session_state.get("all_months", [])
active_months = st.session_state.get("active_months", all_months)

# Guard — no file uploaded yet
if len(staff_scores) == 0:
    st.markdown(
        f"<div style='padding:40px;text-align:center;background:#E8F5EE;"
        f"border-radius:12px;border:1px solid #006B3F33'>"
        f"<div style='font-size:32px;margin-bottom:12px'>📊</div>"
        f"<div style='font-size:18px;font-weight:500;color:#006B3F'>Upload your BSC data to begin</div>"
        f"<div style='color:#666;margin-top:8px;font-size:14px'>"
        f"Use the file uploader in the sidebar to load the Excel file.</div>"
        f"</div>",
        unsafe_allow_html=True)
    st.stop()

# Safe access helpers
_has_role  = "Role" in filtered.columns
_has_name  = "Staff Name" in filtered.columns
_has_unit  = "Unit" in filtered.columns
_has_region = "Region" in filtered.columns

# ════════════════════════════════════════════════════════════════
# BSC SCORECARD SUMMARY — shown first before deep-dive
# ════════════════════════════════════════════════════════════════
def render_bsc_scorecard(staff_df, df_kpi):
    """Compact BSC scorecard table — pillar | KPI | weight | target | actual | ach% | monthly | score."""
    st.markdown(
        "<div style='padding:12px 18px;background:#006B3F;border-radius:8px;margin-bottom:12px'>"
        "<div style='color:white;font-size:15px;font-weight:500'>BSC Scorecard</div>"
        "<div style='color:#9FE1CB;font-size:11px'>"
        "All KPIs at a glance — Target · Achievement · Score</div>"
        "</div>", unsafe_allow_html=True)

    if staff_df.empty or len(staff_df) == 0:
        st.info("No staff data loaded.")
        return

    # ── Grouped searchable selector ───────────────────────────
    search_sc = st.text_input(
        "🔍 Search by name or role",
        placeholder="Type to filter staff...",
        key="sc_search"
    ).strip().lower()

    # Build full name list — filtered if search active, grouped if not
    has_role_col = "Role" in staff_df.columns
    if search_sc:
        mask = staff_df["Staff Name"].str.lower().str.contains(search_sc, na=False)
        if has_role_col:
            mask |= staff_df["Role"].str.lower().str.contains(search_sc, na=False)
        candidates = staff_df[mask]
        if candidates.empty:
            st.caption(f"No staff match '{search_sc}' — clear search to browse all")
            return None
        name_options = sorted(candidates["Staff Name"].tolist())
        sel = st.selectbox(
            f"Select ({len(name_options)} match{'es' if len(name_options)!=1 else ''})",
            name_options, key="sc_select")
        return sel
    elif "Unit" in staff_df.columns:
        # Grouped by unit
        groups = {}
        for _, row in staff_df.sort_values(["Unit","Staff Name"]).iterrows():
            unit = str(row.get("Unit","—"))
            name = row["Staff Name"]
            perf = row.get("Performance_Remark","")
            icon = "🟢" if perf in ("Exceeded By Far","Exceeded") else ("🔴" if perf in ("Partially Met","Unmet") else "🟡")
            groups.setdefault(unit, []).append((f"   {icon} {name}", name))

        options = []
        lookup  = {}
        for unit in sorted(groups.keys()):
            options.append(f"── {unit} ──")
            for display, real in groups[unit]:
                options.append(display)
                lookup[display] = real

        sel_disp = st.selectbox(
            f"Select staff member ({len(staff_df)} staff)",
            options, key="sc_select",
            help="Grouped by unit · 🟢 Exceeded · 🟡 Met · 🔴 Below target")
        if not sel_disp or sel_disp.startswith("──"):
            return
        sel = lookup.get(sel_disp, sel_disp.strip().lstrip("🟢🟡🔴⚪ "))
    else:
        sel = st.selectbox(
            f"Select staff member ({len(staff_df)} staff)",
            sorted(staff_df["Staff Name"].tolist()),
            key="sc_select")
    staff_row = staff_df[staff_df['Staff Name'] == sel]
    if len(staff_row) == 0:
        return
    staff_row = staff_row.iloc[0]

    # ── Header summary cards ──────────────────────────────────────────
    bsc    = staff_row.get('Final_BSC_Score', 0)
    rank   = staff_row.get('Overall_Rank', '—')
    rem    = staff_row.get('Performance_Remark', '—')
    unit   = staff_row.get('Unit', '—')
    role   = staff_row.get('Role', '—')
    clr_map = {
        'Exceeded By Far': '#006B3F', 'Exceeded': '#1D9E75',
        'Met': '#F5A623', 'Partially Met': '#E67E22', 'Unmet': '#E24B4A',
    }
    bsc_clr = clr_map.get(rem, '#888')

    hc1, hc2, hc3, hc4 = st.columns(4)
    hc1.markdown(
        f"<div style='padding:12px;background:#E8F5EE;border-radius:8px;text-align:center'>"
        f"<div style='font-size:28px;font-weight:700;color:{bsc_clr}'>{bsc:.2f}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>BSC Score / 5.0</div></div>",
        unsafe_allow_html=True)
    hc2.markdown(
        f"<div style='padding:12px;background:var(--color-background-secondary);"
        f"border-radius:8px;text-align:center'>"
        f"<div style='font-size:22px;font-weight:600'>#{rank}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>Overall rank</div></div>",
        unsafe_allow_html=True)
    hc3.markdown(
        f"<div style='padding:12px;background:var(--color-background-secondary);"
        f"border-radius:8px;text-align:center'>"
        f"<div style='font-size:14px;font-weight:600;color:{bsc_clr}'>{rem}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>Performance band</div></div>",
        unsafe_allow_html=True)
    hc4.markdown(
        f"<div style='padding:12px;background:var(--color-background-secondary);"
        f"border-radius:8px;text-align:center'>"
        f"<div style='font-size:12px;font-weight:600'>{unit}</div>"
        f"<div style='font-size:10px;color:#666;margin-top:2px'>{role}</div></div>",
        unsafe_allow_html=True)

    st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    # ── KPI rows ──────────────────────────────────────────────────────
    kpi_rows = df_kpi[df_kpi['Staff Name'] == sel].copy()
    if kpi_rows.empty:
        st.info("No KPI data found for this staff member.")
        return

    # Sort by pillar (Financial first, then Customer Focus, then Operational)
    # and filter any row where KPI text equals Pillar text (subtotal artefacts)
    PILLAR_ORDER = {'Financial': 0, 'Customer Focus': 1, 'Operational Excellence': 2}
    kpi_rows['_p_ord'] = kpi_rows['Pillar'].map(PILLAR_ORDER).fillna(99)
    # Remove rows where KPI name is the same as the Pillar name
    kpi_rows = kpi_rows[
        kpi_rows['KPI'].astype(str).str.strip() !=
        kpi_rows['Pillar'].astype(str).str.strip()
    ]
    kpi_rows = kpi_rows.sort_values(['_p_ord', 'Weight'], ascending=[True, False])

    # Detect monthly columns present in the data
    month_cols = [c for c in kpi_rows.columns
                  if any(c.startswith(m) for m in
                         ['Jan','Feb','Mar','Apr','May','Jun',
                          'Jul','Aug','Sep','Oct','Nov','Dec'])
                  and 'Target' not in str(c) and 'target' not in str(c)]

    # Count consecutive rows per pillar for rowspan
    pillar_counts = {}
    for _, r in kpi_rows.iterrows():
        p = str(r.get('Pillar', ''))
        pillar_counts[p] = pillar_counts.get(p, 0) + 1

    def score_clr(s):
        if s >= 3.5:   return '#006B3F'
        if s >= 3.0:   return '#1D9E75'
        if s >= 2.5:   return '#F5A623'
        return '#E24B4A'

    def ach_clr(p):
        if p >= 100: return '#006B3F'
        if p >= 90:  return '#1D9E75'
        if p >= 70:  return '#F5A623'
        return '#E24B4A'

    # Build HTML rows
    rows_html  = ''
    prev_pillar = None
    total_wt   = 0.0
    total_ws   = 0.0

    for _, r in kpi_rows.iterrows():
        kpi    = str(r.get('KPI', '—'))
        pillar = str(r.get('Pillar', '—'))
        tgt    = float(pd.to_numeric(r.get('Annual Target', 0), errors='coerce') or 0)
        act    = float(pd.to_numeric(r.get('YTD_Actual',
                        r.get('Annual Actual', 0)), errors='coerce') or 0)
        wt     = float(pd.to_numeric(r.get('Weight', 0), errors='coerce') or 0)
        sc     = float(pd.to_numeric(r.get('Score', 0), errors='coerce') or 0)
        pct    = round(act / tgt * 100, 1) if tgt else 0.0

        total_wt += wt
        total_ws += sc * wt

        # Monthly actuals string
        monthly_vals = []
        for mc in month_cols[:3]:
            v = pd.to_numeric(r.get(mc, 0), errors='coerce') or 0
            monthly_vals.append(fmt_num(v, short=True))
        monthly_str = ' · '.join(monthly_vals) if monthly_vals else '—'

        # Colour helpers (no nested quotes inside f-string)
        sc_c  = score_clr(sc)
        ac_c  = ach_clr(pct)
        bar_w = int(min(100, max(0, pct)))

        # Pillar cell — only emit on first row of each pillar group
        if pillar != prev_pillar:
            cnt = pillar_counts.get(pillar, 1)
            pillar_td = (
                f"<td rowspan='{cnt}' style='"
                f"background:#E8F5EE;font-weight:700;color:#006B3F;"
                f"font-size:10px;text-align:center;vertical-align:middle;"
                f"padding:6px 4px;white-space:nowrap'>"
                f"{pillar}</td>"
            )
            prev_pillar = pillar
        else:
            pillar_td = ''

        # Achievement bar cell — build without nested f-string quotes
        bar_bg   = '#EEEEEE'
        ach_html = (
            "<div style='display:flex;align-items:center;gap:5px'>"
            f"<div style='width:48px;height:5px;background:{bar_bg};border-radius:3px;flex-shrink:0'>"
            f"<div style='width:{bar_w}%;height:100%;background:{ac_c};border-radius:3px'></div>"
            "</div>"
            f"<span style='color:{ac_c};font-weight:600;font-size:11px'>{pct:.1f}%</span>"
            "</div>"
        )

        rows_html += (
            "<tr>"
            + pillar_td
            + f"<td style='font-size:12px;padding:5px 8px'>{kpi}</td>"
            + f"<td style='text-align:center;font-size:11px;color:#555'>{wt*100:.0f}%</td>"
            + f"<td style='text-align:right;font-size:12px;padding:5px 8px'>{fmt_num(tgt, short=True)}</td>"
            + f"<td style='text-align:right;font-size:12px;font-weight:600;padding:5px 8px'>{fmt_num(act, short=True)}</td>"
            + f"<td style='padding:4px 8px'>{ach_html}</td>"
            + f"<td style='font-size:10px;color:#888;text-align:center'>{monthly_str}</td>"
            + f"<td style='text-align:center;font-weight:700;color:{sc_c};font-size:12px'>{sc:.2f}</td>"
            + "</tr>"
        )

    # Totals row
    rows_html += (
        "<tr style='background:#E8F5EE;border-top:2px solid #006B3F'>"
        "<td colspan='2' style='padding:8px;font-size:12px;font-weight:700;"
        "color:#006B3F'>Weighted BSC total</td>"
        f"<td style='text-align:center;font-weight:600'>{total_wt*100:.0f}%</td>"
        "<td colspan='3'></td>"
        "<td></td>"
        f"<td style='text-align:center;font-weight:700;color:{score_clr(bsc)};font-size:15px'>{bsc:.2f}</td>"
        "</tr>"
    )

    month_label = ' · '.join(month_cols[:3]) if month_cols else 'Monthly'

    table_html = (
        "<div style='overflow-x:auto;border-radius:8px;border:1px solid #D0D0D0;"
        "box-shadow:0 1px 4px rgba(0,0,0,0.06)'>"
        "<table style='width:100%;border-collapse:collapse;font-size:12px'>"
        "<thead>"
        "<tr style='background:#006B3F;color:white'>"
        "<th style='padding:9px 6px;min-width:80px;text-align:center'>Pillar</th>"
        "<th style='padding:9px 8px;text-align:left;min-width:160px'>KPI</th>"
        "<th style='padding:9px 6px;text-align:center'>Wt</th>"
        "<th style='padding:9px 8px;text-align:right;min-width:90px'>Annual Target</th>"
        "<th style='padding:9px 8px;text-align:right;min-width:90px'>YTD Actual</th>"
        "<th style='padding:9px 8px;text-align:center;min-width:120px'>Achievement</th>"
        f"<th style='padding:9px 6px;text-align:center;min-width:130px'>{month_label}</th>"
        "<th style='padding:9px 6px;text-align:center;min-width:60px'>Score</th>"
        "</tr>"
        "</thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# GROUPED STAFF SELECTOR — HELPER
# ════════════════════════════════════════════════════════════════
def build_staff_selector(df, key_prefix="main"):
    """
    Grouped, searchable staff selector.
    Groups by Unit then shows staff within it.
    Returns (selected_name, col_used) or (None, None).
    """
    if df.empty or "Staff Name" not in df.columns:
        return None

    # ── Search box ────────────────────────────────────────────
    search_q = st.text_input(
        "🔍 Search by name or role",
        placeholder="Type a name or role to filter...",
        key=f"{key_prefix}_search"
    ).strip().lower()

    # ── Build grouped options ──────────────────────────────────
    has_unit = "Unit" in df.columns
    has_role = "Role" in df.columns

    # Build a SINGLE list of options regardless of search/browse mode.
    # Using one consistent key avoids Streamlit's widget-reuse conflict
    # which causes the empty dropdown when switching between modes.

    if search_q:
        mask = df["Staff Name"].str.lower().str.contains(search_q, na=False)
        if has_role:
            mask |= df["Role"].str.lower().str.contains(search_q, na=False)
        filtered_df = df[mask]
        if filtered_df.empty:
            st.caption(f"No match for '{search_q}' — clear search to browse all")
            # Still show full selectbox so widget key stays alive
            return st.selectbox(
                "No results — clear search above",
                ["— no match —"],
                key=f"{key_prefix}_sel")
        name_opts = sorted(filtered_df["Staff Name"].tolist())
        return st.selectbox(
            f"Select ({len(name_opts)} result{'s' if len(name_opts)!=1 else ''})",
            name_opts,
            key=f"{key_prefix}_sel")

    # Browse mode — flat list grouped by unit via display labels
    if has_unit:
        groups = {}
        for _, row in df.sort_values(["Unit","Staff Name"]).iterrows():
            unit = str(row.get("Unit","—"))
            name = str(row["Staff Name"])
            perf = str(row.get("Performance_Remark",""))
            icon = ("🟢" if perf in ("Exceeded By Far","Exceeded")
                    else ("🟡" if perf == "Met"
                    else ("🔴" if perf in ("Partially Met","Unmet") else "⚪")))
            groups.setdefault(unit, []).append((name, f"{icon} {name}"))

        # Build two parallel lists: display labels (with icons) and real names
        # We store "── UNIT ──" in display but map it to "" in real names
        # so the selectbox works and we can detect header rows
        display_labels = []
        real_names     = []
        for unit in sorted(groups.keys()):
            header = f"── {unit} ({len(groups[unit])}) ──"
            display_labels.append(header)
            real_names.append("")
            for real, display in groups[unit]:
                display_labels.append(f"    {display}")
                real_names.append(real)

        sel_disp = st.selectbox(
            f"Select staff member ({len(df)} total)",
            display_labels,
            key=f"{key_prefix}_sel",
            help="Grouped by unit · 🟢 Exceeded · 🟡 Met · 🔴 Below target")

        if not sel_disp:
            return None
        # Find matching real name
        try:
            idx = display_labels.index(sel_disp)
            real = real_names[idx]
            if not real:  # header row
                st.caption("↑ Select a staff member, not a unit header")
                return None
            return real
        except ValueError:
            return None
    else:
        names = sorted(df["Staff Name"].tolist())
        return st.selectbox(
            f"Select staff member ({len(names)})",
            names,
            key=f"{key_prefix}_sel")


# ════════════════════════════════════════════════════════════════
# PAGE HEADER
# ════════════════════════════════════════════════════════════════
st.markdown(
    "<div style='padding:14px 20px;background:#006B3F;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:16px;font-weight:500'>Perform — BSC Performance Management</div>"
    "<div style='color:#9FE1CB;font-size:11px;margin-top:2px'>"
    "Scorecard · Rankings · Individual view · Validation · Analytics · Leave"
    "</div></div>", unsafe_allow_html=True)

# ── Region filter in sidebar ──────────────────────────────────
if _has_region and len(filtered) > 0:
    all_regions = sorted(filtered["Region"].dropna().unique().tolist())
    if len(all_regions) > 1:
        sel_reg = st.sidebar.selectbox("Region", ["All"] + all_regions, key="reg_f")
        if sel_reg != "All":
            filtered = filtered[filtered["Region"] == sel_reg].copy()

# ════════════════════════════════════════════════════════════════
# TABS — AT THE TOP, ALWAYS VISIBLE
# ════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📊 My Scorecard",
    "🏆 Rankings",
    "👤 Individual view",
    "✅ Validation",
    "📈 Analytics",
    "📋 Staff register",
    "🏖️ Leave",
    "💡 Team insights",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — BSC SCORECARD
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.caption("Select any staff member to view their full BSC scorecard — KPIs grouped by pillar with achievement and score.")
    render_bsc_scorecard(filtered, df_proc)

# ════════════════════════════════════════════════════════════════
# TAB 2 — RANKINGS
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    # Quick summary row
    if len(filtered):
        rc1,rc2,rc3,rc4,rc5 = st.columns(5)
        rc1.metric("Staff in view",     len(filtered))
        rc2.metric("Avg BSC",           fmt_score(filtered["Final_BSC_Score"].mean()))
        rc3.metric("Exceeded",          int((filtered["Final_BSC_Score"]>=3.1).sum()))
        rc4.metric("Met (3.0)",         int(((filtered["Final_BSC_Score"]>=2.95)&(filtered["Final_BSC_Score"]<3.1)).sum()))
        rc5.metric("At risk (<2.5)",    int((filtered["Final_BSC_Score"]<2.5).sum()),
                   delta_color="inverse")

    # Filters
    st.markdown("<div style='margin:8px 0'>", unsafe_allow_html=True)
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        roles_opts = ["All roles"] + sorted(filtered["Role"].unique().tolist()) if _has_role else ["All roles"]
        sel_role = st.selectbox("Role", roles_opts, key="rank_role")
    with fc2:
        units_opts = ["All units"] + (sorted(filtered["Unit"].unique().tolist()) if _has_unit else [])
        sel_unit = st.selectbox("Unit", units_opts, key="rank_unit")
    with fc3:
        perf_opts = ["All","Exceeded By Far","Exceeded","Met","Partially Met","Unmet"]
        sel_perf = st.selectbox("Performance band", perf_opts, key="rank_perf")

    view = filtered.copy()
    if sel_role != "All roles": view = view[view["Role"] == sel_role]
    if sel_unit != "All units" and _has_unit: view = view[view["Unit"] == sel_unit]
    if sel_perf != "All": view = view[view["Performance_Remark"] == sel_perf]

    show_cols = [c for c in ["Overall_Rank","Staff Name","Role","Unit","Staff Status",
                               "Final_BSC_Score","Avg_Achievement_Pct","Performance_Remark","Percentile"]
                 if c in view.columns]
    disp = view[show_cols].copy()
    if "Final_BSC_Score"     in disp.columns: disp["Final_BSC_Score"]     = disp["Final_BSC_Score"].apply(fmt_score)
    if "Avg_Achievement_Pct" in disp.columns: disp["Avg_Achievement_Pct"] = disp["Avg_Achievement_Pct"].apply(fmt_pct)
    if "Percentile"          in disp.columns: disp["Percentile"]          = disp["Percentile"].apply(fmt_pct)
    disp.columns = [c.replace("_"," ") for c in disp.columns]
    disp = disp.rename(columns={"Avg Achievement Pct":"Avg Achievement %","Final BSC Score":"BSC Score"})

    def highlight_performance(v):
        colors = {"Exceeded By Far":"background-color:#C6EFCE;color:#276221",
                  "Exceeded":        "background-color:#DDEBF7;color:#1F497D",
                  "Met":             "background-color:#FFEB9C;color:#9C5700",
                  "Partially Met":   "background-color:#FFDDB3;color:#974706",
                  "Unmet":           "background-color:#FFC7CE;color:#9C0006"}
        return colors.get(str(v), "")

    st.dataframe(disp.style.map(highlight_performance, subset=["Performance Remark"]),
                 use_container_width=True, hide_index=True, height=420)

    # Charts
    c1, c2 = st.columns(2)
    with c1:
        top10 = view.assign(_or=view["Overall_Rank"].astype(float)).nsmallest(10,"_or")
        fig = px.bar(top10, x="Staff Name", y="Final_BSC_Score", color="Performance_Remark",
                     title="Top 10 performers", text="Final_BSC_Score",
                     color_discrete_map={"Exceeded By Far":"#006B3F","Exceeded":"#1D9E75",
                                         "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"})
        fig.update_traces(textposition="outside", texttemplate="%{y:.2f}")
        fig.update_layout(showlegend=False, xaxis_tickangle=-30, height=320,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        dist = view["Performance_Remark"].value_counts().reset_index()
        dist.columns = ["Status","Count"]
        fig2 = px.pie(dist, names="Status", values="Count", title="Performance distribution",
                      color="Status",
                      color_discrete_map={"Exceeded By Far":"#006B3F","Exceeded":"#1D9E75",
                                          "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"})
        fig2.update_layout(height=320, legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig2, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 3 — INDIVIDUAL VIEW
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.caption("Grouped by unit · 🟢 Exceeded · 🟡 Met/Exceeded · 🔴 Below target")
    selected = build_staff_selector(filtered, "ind")

    if selected:
        sel_rows = filtered[filtered["Staff Name"] == selected]
        if sel_rows.empty:
            st.warning("Staff member not found in current view.")
            st.stop()
        row  = sel_rows.iloc[0]
        kpis = df_proc[df_proc["Staff Name"] == selected] if not df_proc.empty else pd.DataFrame()

        # ── Header card ──────────────────────────────────────
        status = row.get("Performance_Remark","—")
        bsc    = row.get("Final_BSC_Score", 0)
        clr_map = {"Exceeded By Far":"#006B3F","Exceeded":"#1D9E75",
                   "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"}
        bsc_clr = clr_map.get(status,"#888")
        remark_detail = {
            "Exceeded By Far":"Outstanding performance — significantly above target across most KPIs.",
            "Exceeded":       "Strong performance — above target in the majority of KPIs.",
            "Met":            "Performance on target — meeting expectations across all pillars.",
            "Partially Met":  "Below target in key areas — a focused improvement plan is recommended.",
            "Unmet":          "Significantly below target — immediate management intervention required.",
        }.get(status,"")

        st.markdown(
            f"<div style='padding:14px 18px;background:{bsc_clr}22;"
            f"border-left:5px solid {bsc_clr};border-radius:6px;margin-bottom:12px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<div><span style='font-size:22px;font-weight:700;color:{bsc_clr}'>{bsc:.2f}</span>"
            f"<span style='color:#666;font-size:13px;margin-left:8px'>/ 5.0  ·  {status}</span></div>"
            f"<div style='text-align:right;font-size:12px;color:#555'>"
            f"Rank #{row.get('Overall_Rank','—')}  ·  {row.get('Role','')}  ·  {row.get('Unit','')}"
            f"</div></div>"
            f"<div style='font-size:12px;color:#555;margin-top:4px'>{remark_detail}</div>"
            f"</div>", unsafe_allow_html=True)

        # ── 5 metrics ────────────────────────────────────────
        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("BSC Score",       fmt_score(bsc))
        m2.metric("Overall rank",    f"#{row.get('Overall_Rank','—')}")
        m3.metric("Role rank",       f"#{row.get('Role_Rank','—')} / {row.get('Role_Total','—')}")
        m4.metric("Avg achievement", fmt_pct(row.get("Avg_Achievement_Pct",0)))
        m5.metric("Percentile",      f"{row.get('Percentile',0):.0f}th")

        if row.get("Staff Status","") in ("New","New 2026"):
            st.info("🆕 New staff — may be on probation. Confirm status in Staff Register tab.")

        # ── Validation badge ──────────────────────────────────
        period = datetime.now().strftime("%b %Y")
        if vm:
            existing_val = vm.get(selected, period)
            if existing_val:
                st.success(f"✅ Validated by **{existing_val['manager']}** on "
                           f"{existing_val['validated_at'][:10]} — {existing_val['status']}")

        st.markdown("---")
        col_a, col_b = st.columns(2)

        # ── Monthly trend ─────────────────────────────────────
        with col_a:
            if not kpis.empty and active_months:
                monthly_trend = []
                for col in active_months:
                    if col in kpis.columns:
                        dt = parse_month_column(col)
                        label = dt.strftime("%b %Y") if dt else str(col)
                        month_rows = kpis.copy()
                        month_rows["_m_actual"] = month_rows[col]
                        month_ws = []
                        for _, kr in month_rows.iterrows():
                            t = kr.get("Annual Target", np.nan)
                            a = kr.get("_m_actual", 0)
                            w = kr.get("Weight", 0)
                            kpi_name = str(kr.get("KPI","")).upper()
                            rev = any(x in kpi_name for x in ["PAR","NPL","DELINQUENCY","COST","EXPENSE"])
                            if pd.isna(t) or t == 0: ach = np.nan
                            elif rev: ach = max(0, min(1.5, t/a)) if a > 0 else 0
                            else: ach = max(0, min(1.5, a/t))
                            if pd.isna(ach): s = np.nan
                            elif ach < 0.30: s=1.0
                            elif ach<=0.50:  s=1.5
                            elif ach<=0.60:  s=2.0
                            elif ach<=0.90:  s=2.5
                            elif ach<=1.00:  s=3.0
                            elif ach<=1.10:  s=3.5
                            elif ach<=1.20:  s=4.0
                            elif ach<=1.30:  s=4.5
                            else:            s=5.0
                            month_ws.append(s * w if pd.notna(s) else 0)
                        monthly_trend.append({"Month": label, "Weighted Score": round(sum(month_ws),2)})

                if monthly_trend:
                    mdf = pd.DataFrame(monthly_trend)
                    fig_line = px.line(mdf, x="Month", y="Weighted Score",
                                       title="Monthly BSC trend", markers=True,
                                       color_discrete_sequence=["#006B3F"])
                    fig_line.add_hline(y=3.0, line_dash="dash", line_color="#F5A623",
                                       annotation_text="Target 3.0")
                    fig_line.update_traces(marker=dict(size=10))
                    fig_line.update_layout(height=260, yaxis_range=[0,5.5],
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_line, use_container_width=True)

        # ── Pillar radar ──────────────────────────────────────
        with col_b:
            if not kpis.empty and "Pillar" in kpis.columns and kpis["Pillar"].nunique() > 1:
                ps = kpis.groupby("Pillar")["Weighted_Score"].sum().reset_index()
                fig_r = go.Figure(go.Scatterpolar(
                    r=ps["Weighted_Score"], theta=ps["Pillar"],
                    fill="toself", fillcolor="rgba(0,107,63,0.15)",
                    line=dict(color="#006B3F", width=2)))
                fig_r.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0,2])),
                    title="Pillar scores", height=260,
                    paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_r, use_container_width=True)

        # ── Performance insights ──────────────────────────────
        if not kpis.empty:
            st.markdown("#### Performance insights")
            insights = get_kpi_insights(kpis)
            render_insight_card(insights)

            # ── KPI breakdown ────────────────────────────────
            st.markdown("#### KPI detail")
            pillar_opts = ["All pillars"] + (sorted(kpis["Pillar"].unique().tolist()) if "Pillar" in kpis.columns else [])
            sel_pillar = st.selectbox("Filter by pillar", pillar_opts, key="kpi_pillar_ind")
            kpi_view = kpis if sel_pillar == "All pillars" else kpis[kpis["Pillar"] == sel_pillar]

            kpi_disp = kpi_view[["KPI","Pillar","Annual Target","YTD_Actual",
                                  "Percent_Achieved","Score","Weight","Weighted_Score"]].copy()
            kpi_disp["Annual Target"]    = kpi_disp["Annual Target"].apply(fmt_num)
            kpi_disp["YTD_Actual"]       = kpi_disp["YTD_Actual"].apply(fmt_num)
            kpi_disp["Percent_Achieved"] = kpi_disp["Percent_Achieved"].apply(fmt_pct)
            kpi_disp["Weight"]           = kpi_disp["Weight"].apply(lambda x: f"{x*100:.0f}%")
            kpi_disp["Score"]            = kpi_disp["Score"].apply(fmt_score)
            kpi_disp.columns = ["KPI","Pillar","Annual Target","YTD Actual","Achievement %","Score","Weight","Wtd Score"]

            def color_score_cell(v):
                try:
                    s = float(v)
                    if s >= 4:   return "background-color:#C6EFCE;color:#276221"
                    elif s >= 3: return "background-color:#FFEB9C;color:#9C5700"
                    elif s >= 2: return "background-color:#FFDDB3;color:#974706"
                    else:        return "background-color:#FFC7CE;color:#9C0006"
                except: return ""

            st.dataframe(kpi_disp.style.map(color_score_cell, subset=["Score"]),
                         use_container_width=True, hide_index=True)
    else:
        st.info("Use the search box above or select a staff member from the grouped dropdown.")

# ════════════════════════════════════════════════════════════════
# TAB 4 — VALIDATION
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Performance validation")
    st.caption("Managers review and sign off on staff performance for each period.")

    val_role = str(ud.get('role','')).lower()
    if val_role not in ('admin','director','manager','branch manager','department head'):
        st.info("Validation is available to managers and above. Contact your manager to validate your performance.")
    else:
        period = datetime.now().strftime("%b %Y")
        val_staff = sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else []
        val_sel = st.selectbox("Select staff to validate", val_staff, key="val_sel")

        if val_sel:
            vrow = filtered[filtered['Staff Name'] == val_sel].iloc[0]
            existing = vm.get(val_sel, period)

            c1, c2, c3 = st.columns(3)
            c1.metric("BSC Score",   fmt_score(vrow['Final_BSC_Score']))
            c2.metric("Performance", vrow['Performance_Remark'])
            c3.metric("Percentile",  f"{vrow['Percentile']:.0f}th")

            if existing and not st.session_state.get('revalidate'):
                st.success(f"Already validated: **{existing['status']}** by {existing['manager']} on {existing['validated_at'][:10]}")
                st.write("**Action plan:**", existing.get('action_plan','—'))
                st.write("**Comments:**",    existing.get('comments','—'))
                if st.button("Re-validate", key="reval_btn"):
                    st.session_state['revalidate'] = True
                    st.rerun()
            else:
                with st.form("validation_form"):
                    vstatus = st.selectbox("Validation status",
                        ["Confirmed","Partially Confirmed","Requires Review","Disputed"])
                    action_plan = st.text_area("Action plan / next steps",
                        value=existing.get('action_plan','') if existing else '')
                    comments = st.text_area("Comments",
                        value=existing.get('comments','') if existing else '')
                    if st.form_submit_button("Submit validation", type="primary"):
                        vm.validate(uname, val_sel, period, vstatus, action_plan, comments)
                        audit_log("VALIDATE", uname, f"{val_sel} | {period} | {vstatus}")
                        st.success(f"Validation submitted for {val_sel}!")
                        st.session_state.pop('revalidate', None)
                        st.rerun()

        st.markdown("---")
        st.subheader(f"Validation summary — {period}")
        val_rows = []
        for name in sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else []:
            v = vm.get(name, period)
            sc = filtered[filtered['Staff Name']==name]['Final_BSC_Score'].values[0]
            val_rows.append({
                "Staff": name,
                "BSC Score": fmt_score(sc),
                "Status": v['status'] if v else "⏳ Pending",
                "Validated by": v['manager'] if v else "—",
                "Date": v['validated_at'][:10] if v else "—",
            })
        if val_rows:
            vdf = pd.DataFrame(val_rows)
            def hl_val(v):
                if 'Confirmed' in str(v): return 'background-color:#C1E1C1'
                if 'Pending'   in str(v): return 'background-color:#FFE4B5'
                if 'Disputed'  in str(v): return 'background-color:#FFB6C1'
                return ''
            st.dataframe(vdf.style.map(hl_val, subset=['Status']),
                         use_container_width=True, hide_index=True)
            done  = sum(1 for r in val_rows if '⏳' not in r['Status'])
            total = len(val_rows)
            st.progress(done/total if total else 0, text=f"Validated: {done}/{total}")

# ════════════════════════════════════════════════════════════════
# TAB 5 — ANALYTICS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Analytics dashboard")
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Staff in view",     len(filtered))
    m2.metric("Avg BSC score",     fmt_score(filtered['Final_BSC_Score'].mean()))
    m3.metric("High performers",   int((filtered['Final_BSC_Score'] >= 3.5).sum()))
    m4.metric("Needs improvement", int((filtered['Final_BSC_Score'] < 2.5).sum()))

    c1, c2 = st.columns(2)
    with c1:
        fig_h = px.histogram(filtered, x='Final_BSC_Score', nbins=20,
                             title='Score distribution', color_discrete_sequence=['#2980B9'])
        fig_h.add_vline(x=3.0, line_dash='dash', line_color='orange', annotation_text='Target (3.0)')
        fig_h.update_layout(height=320)
        st.plotly_chart(fig_h, use_container_width=True)
    with c2:
        if 'Unit' in filtered.columns and filtered['Unit'].nunique() > 1:
            ua = filtered.groupby('Unit')['Final_BSC_Score'].mean().sort_values(ascending=False).reset_index()
            fig_u = px.bar(ua, x='Final_BSC_Score', y='Unit', orientation='h',
                           title='Average score by unit', color='Final_BSC_Score',
                           color_continuous_scale='RdYlGn', range_color=[1,5])
            fig_u.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig_u, use_container_width=True)

    # Score spread by role, split by Head Office vs Branch
    if 'Role' in filtered.columns and filtered['Role'].nunique() > 1:
        cat_col = 'Category' if 'Category' in filtered.columns else None
        has_cats = cat_col and filtered[cat_col].nunique() > 1

        if has_cats:
            categories = sorted(filtered[cat_col].unique().tolist())
            cat_tabs = st.tabs([f"📍 {c}" for c in categories])
            for ct, cat in zip(cat_tabs, categories):
                with ct:
                    cat_data = filtered[filtered[cat_col] == cat]
                    if cat_data['Role'].nunique() > 1:
                        fig_box = px.box(cat_data, x='Role', y='Final_BSC_Score',
                                         title=f'Score spread by role — {cat}', color='Role')
                        fig_box.add_hline(y=3.0, line_dash='dash', line_color='orange',
                                          annotation_text='Target')
                        fig_box.update_layout(showlegend=False, xaxis_tickangle=-25, height=360)
                        st.plotly_chart(fig_box, use_container_width=True)

                        role_avg = cat_data.groupby('Role')['Final_BSC_Score'].agg(
                            ['mean','count','min','max']).round(2).reset_index()
                        role_avg.columns = ['Role','Avg Score','# Staff','Min','Max']
                        st.dataframe(role_avg, use_container_width=True, hide_index=True)
                    else:
                        st.info(f"Only one role in {cat} — no spread chart needed.")
        else:
            fig_box = px.box(filtered, x='Role', y='Final_BSC_Score',
                             title='Score spread by role', color='Role')
            fig_box.add_hline(y=3.0, line_dash='dash', line_color='orange', annotation_text='Target')
            fig_box.update_layout(showlegend=False, xaxis_tickangle=-20, height=320)
            st.plotly_chart(fig_box, use_container_width=True)

    if 'Pillar' in df_proc.columns:
        pa = df_proc.groupby('Pillar')['Weighted_Score'].mean().reset_index()
        fig_p = px.bar(pa, x='Pillar', y='Weighted_Score',
                       title='Average weighted score by pillar', color='Pillar')
        fig_p.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig_p, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — STAFF REGISTER
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Staff register")
    st.caption("Live view of all staff in the system — probation, transfers, and employment status.")

    reg = st.session_state.get('staff_registry', pd.DataFrame())

    if reg is None or (hasattr(reg,'empty') and reg.empty) or (isinstance(reg,dict) and not reg):
        st.info("No staff registry data found. Upload a file that includes 'Hire Date', 'Staff Status', and 'Email' columns (e.g. your Sheet1).")
    else:
        # Build display table
        reg_rows = []
        for code_val, info in reg.items():
            score_row = staff_scores[staff_scores['Staff Code'].astype(str) == str(code_val)]
            score = fmt_score(score_row['Final_BSC_Score'].values[0]) if len(score_row) else '—'
            remark = score_row['Performance_Remark'].values[0] if len(score_row) else '—'
            reg_rows.append({
                'Staff Code':   code_val,
                'Name':         info.get('Staff Name',''),
                'Role':         info.get('Role',''),
                'Unit':         info.get('Unit',''),
                'Category':     info.get('Category',''),
                'Email':        info.get('Email',''),
                'Hire Date':    info.get('Hire Date Str','—'),
                'Status':       info.get('Employment Status','Existing'),
                'BSC Score':    score,
                'Performance':  remark,
            })
        reg_df = pd.DataFrame(reg_rows)

        # Filters
        fr1, fr2, fr3 = st.columns(3)
        with fr1:
            status_opts = ['All statuses'] + sorted(reg_df['Status'].unique().tolist())
            sel_status = st.selectbox("Employment status", status_opts, key="reg_status")
        with fr2:
            unit_opts = ['All units'] + sorted(reg_df['Unit'].dropna().unique().tolist())
            sel_runit = st.selectbox("Unit / Branch", unit_opts, key="reg_unit")
        with fr3:
            search = st.text_input("Search name or code", key="reg_search", placeholder="Type to search...")

        reg_view = reg_df.copy()
        if sel_status != 'All statuses': reg_view = reg_view[reg_view['Status'] == sel_status]
        if sel_runit  != 'All units':    reg_view = reg_view[reg_view['Unit']   == sel_runit]
        if search.strip():
            s = search.strip().lower()
            reg_view = reg_view[
                reg_view['Name'].str.lower().str.contains(s, na=False) |
                reg_view['Staff Code'].str.lower().str.contains(s, na=False)]

        # Colour status column
        def hl_status(v):
            if 'Probation' in str(v): return 'background-color:#FFF3CD;color:#856404'
            if v == 'Confirmed':      return 'background-color:#D4EDDA;color:#155724'
            if v == 'New':            return 'background-color:#CCE5FF;color:#004085'
            return ''
        def hl_perf(v):
            return highlight_performance(v)

        st.dataframe(
            reg_view.style
                .map(hl_status,   subset=['Status'])
                .map(hl_perf,     subset=['Performance']),
            use_container_width=True, hide_index=True)

        # Summary cards
        st.markdown("---")
        probation_count  = reg_df['Status'].str.contains('Probation', na=False).sum()
        confirmed_count  = (reg_df['Status'] == 'Confirmed').sum()
        new_count        = (reg_df['Status'] == 'New').sum()
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Total staff", len(reg_df))
        sc2.metric("On probation", int(probation_count))
        sc3.metric("Confirmed", int(confirmed_count))
        sc4.metric("New (no hire date)", int(new_count))

        # ── TRANSFERS ────────────────────────────────────────────────────
        st.markdown("---")
        st.subheader("Record a transfer")
        st.caption("When a staff member moves between branches or units, record it here. This updates their unit and logs the movement.")

        transfer_file = DATA_DIR / "transfers.json"
        if not transfer_file.exists(): transfer_file.write_text("[]")
        try:
            transfers = json.loads(transfer_file.read_text())
            if not isinstance(transfers, list): transfers = []
        except: transfers = []

        with st.form("transfer_form"):
            tc1, tc2 = st.columns(2)
            with tc1:
                t_code = st.text_input("Staff code", placeholder="e.g. 300130")
                # Auto-show name
                t_name = reg.get(t_code.strip(), {}).get('Staff Name', '') if t_code.strip() in reg else ''
                if t_name: st.caption(f"Staff: **{t_name}**")
                t_from = st.text_input("Transferring FROM (current unit)",
                    value=reg.get(clean_code(t_code), {}).get('Unit','') if clean_code(t_code) in reg else '')
            with tc2:
                t_to   = st.text_input("Transferring TO (new unit)")
                t_date: date = st.date_input("Effective date", value=datetime.now().date())  # type: ignore[assignment]
                t_reason = st.selectbox("Reason", ["Branch Transfer","Department Transfer",
                                                     "Promotion","Role Change","Secondment","Other"])
            t_notes = st.text_area("Notes (optional)", height=70)
            if st.form_submit_button("📋 Record transfer", type="primary"):
                if t_code.strip() and t_to.strip():
                    entry = {
                        "staff_code": t_code.strip(), "staff_name": t_name,
                        "from_unit": t_from, "to_unit": t_to,
                        "effective_date": str(t_date), "reason": t_reason,
                        "notes": t_notes,
                        "recorded_by": st.session_state.get('username',''),
                        "recorded_at": datetime.now().isoformat(),
                    }
                    transfers.append(entry)
                    transfer_file.write_text(json.dumps(transfers, indent=2))
                    audit_log("TRANSFER", st.session_state.get('username',''),
                              f"{t_code} from {t_from} to {t_to} ({t_reason})")
                    st.success(f"Transfer recorded for {t_name or t_code}!")
                    st.rerun()
                else:
                    st.error("Staff code and destination unit are required.")

        # Transfer history
        if transfers:
            st.markdown("#### Transfer history")
            t_df = pd.DataFrame(reversed(transfers))
            st.dataframe(t_df, use_container_width=True, hide_index=True)

        # ── PROBATION TRACKER ────────────────────────────────────────────
        prob_staff = reg_df[reg_df['Status'].str.contains('Probation', na=False)].copy()
        if len(prob_staff):
            st.markdown("---")
            st.subheader(f"⚠️ Probation tracker ({len(prob_staff)} staff)")
            st.caption("Staff currently within their 6-month probation window.")
            st.dataframe(
                prob_staff[['Staff Code','Name','Role','Unit','Hire Date','Status','BSC Score','Performance']]
                    .style.map(hl_status, subset=['Status']),
                use_container_width=True, hide_index=True)
            st.info("💡 Probation sign-off: Go to the Validation tab to formally confirm or flag any probationary staff.")

# ════════════════════════════════════════════════════════════════
# TAB 7 — LEAVE
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Leave management")
    st.caption("Record staff leave, suppress notifications, and apply performance compensation for extended absences.")

    leave_role = str(ud.get('role','')).lower()
    can_approve = leave_role in ('admin','director','manager','branch manager','department head')

    # ── On leave right now — always visible at top ─────────────────
    active_now = lm.get_active_leave()
    if active_now:
        st.error(f"🔴 **{len(active_now)} staff currently on leave** — notifications suppressed")
        for r in active_now:
            end_d = datetime.strptime(r['end_date'], "%Y-%m-%d").date()
            days_left = (end_d - datetime.now().date()).days
            col1, col2, col3 = st.columns([2,2,1])
            col1.markdown(f"**{r['staff_name']}** — {r['leave_type']}")
            col2.markdown(f"Returns: {r['end_date']}  ({days_left}d remaining)")
            col3.markdown(f"{'⚠️ Affects score' if r['affects_perf'] else '✅ No impact'}")
        st.markdown("---")

    # ── Two sub-sections ───────────────────────────────────────────
    lv1, lv2, lv3 = st.tabs(["📋 Record Leave", "📊 Leave Overview", "⚖️ Performance Compensation"])

    with lv1:
        st.subheader("Record new leave")
        if not can_approve:
            st.info("Please contact your manager to record leave.")
        else:
            reg = st.session_state.get('staff_registry', {})

            # Staff lookup
            lv_code = st.text_input("Staff code", placeholder="e.g. 300130", key="lv_code")
            lv_clean = clean_code(lv_code) if lv_code.strip() else ""
            lv_info  = reg.get(lv_clean, {})
            lv_name  = lv_info.get('Staff Name', '')

            if lv_clean and lv_name:
                st.success(f"✅ {lv_name} — {lv_info.get('Role','')} | {lv_info.get('Unit','')}")
                # Show if already on leave
                if lm.is_on_leave(lv_clean):
                    existing = lm.get_active_leave(lv_clean)
                    st.warning(f"⚠️ Already on {existing[0]['leave_type']} until {existing[0]['end_date']}")
            elif lv_clean:
                lv_name = st.text_input("Staff name (not in registry — enter manually)", key="lv_name_manual")

            with st.form("leave_form"):
                lc1, lc2 = st.columns(2)
                with lc1:
                    leave_type = st.selectbox("Leave type", list(LEAVE_TYPES.keys()))
                    start_date: date = st.date_input("Start date", value=datetime.now().date())  # type: ignore[assignment]
                    suppress   = st.checkbox("Suppress email notifications during leave", value=True,
                        help="When ticked, no performance emails or review prompts sent to this staff member")
                with lc2:
                    end_date  = st.date_input("End date",
                        value=datetime.now().date() + timedelta(days=LEAVE_TYPES.get(leave_type,{}).get('days_entitled',21) or 21))
                    reason    = st.text_area("Reason / notes", height=68)

                # Show compensation info dynamically
                lt_info  = LEAVE_TYPES.get(leave_type, {})
                comp_lbl = COMPENSATION_LABELS.get(lt_info.get('compensation'))
                if lt_info.get('affects_performance'):
                    st.warning(f"⚠️ **Performance impact:** {comp_lbl}")
                else:
                    st.success(f"✅ **Performance impact:** {comp_lbl}")

                if st.form_submit_button("✅ Submit leave record", type="primary"):
                    name_to_save = lv_name or "Unknown"
                    if not lv_clean:
                        st.error("Staff code required.")
                    elif start_date > end_date:
                        st.error("End date must be after start date.")
                    else:
                        record = lm.add_leave(
                            lv_clean, name_to_save, leave_type,
                            start_date, end_date, reason,
                            approved_by=uname, notify_suppress=suppress)
                        audit_log("LEAVE_RECORDED", uname,
                                  f"{name_to_save} | {leave_type} | {start_date} to {end_date}")
                        days = record['days']
                        st.success(f"Leave recorded: {name_to_save} — {leave_type} ({days} days)")
                        if record['affects_perf']:
                            st.info(f"📊 Score adjustment: {comp_lbl}")
                        st.rerun()

    with lv2:
        st.subheader("Leave overview")
        all_records = lm.records
        if not all_records:
            st.info("No leave records yet.")
        else:
            lv_df = pd.DataFrame(all_records)
            # Filters
            fc1, fc2, fc3 = st.columns(3)
            with fc1:
                status_f = st.selectbox("Status", ['All','Active','Upcoming','Completed'], key="lvf_status")
            with fc2:
                type_f = st.selectbox("Leave type", ['All'] + list(LEAVE_TYPES.keys()), key="lvf_type")
            with fc3:
                name_f = st.text_input("Search name", key="lvf_name")

            lv_view = lv_df.copy()
            if status_f != 'All': lv_view = lv_view[lv_view['status'] == status_f]
            if type_f  != 'All':  lv_view = lv_view[lv_view['leave_type'] == type_f]
            if name_f.strip():    lv_view = lv_view[lv_view['staff_name'].str.lower().str.contains(name_f.lower(), na=False)]

            def hl_leave(v):
                if v == 'Active':    return 'background-color:#FFE4B5;color:#856404'
                if v == 'Upcoming':  return 'background-color:#CCE5FF;color:#004085'
                if v == 'Completed': return 'background-color:#D4EDDA;color:#155724'
                return ''
            def hl_perf_impact(v):
                if v == True: return 'background-color:#FFB6C1'
                return ''

            show_cols = ['staff_name','leave_type','start_date','end_date','days',
                         'status','affects_perf','compensation','notify_suppress','approved_by']
            show_cols = [c for c in show_cols if c in lv_view.columns]
            display_lv = lv_view[show_cols].copy()
            display_lv.columns = [c.replace('_',' ').title() for c in show_cols]

            st.dataframe(
                display_lv.style
                    .map(hl_leave, subset=['Status'])
                    .map(hl_perf_impact, subset=['Affects Perf'] if 'Affects Perf' in display_lv.columns else []),
                use_container_width=True, hide_index=True)

            # Summary stats
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.metric("Total records", len(lv_df))
            sc2.metric("Currently active", len(lv_df[lv_df['status']=='Active']))
            sc3.metric("Upcoming", len(lv_df[lv_df['status']=='Upcoming']))
            sc4.metric("Affects performance", int(lv_df['affects_perf'].sum()))

    with lv3:
        st.subheader("Performance compensation rules")
        st.caption("How BSC scores are adjusted when staff take extended or statutory leave.")

        for lt, rules in LEAVE_TYPES.items():
            comp = rules['compensation']
            affects = rules['affects_performance']
            icon = "⚠️" if affects else "✅"
            colour = "#FFF3CD" if affects else "#D4EDDA"
            border = "#F0AD4E" if affects else "#28A745"
            st.markdown(
                f"<div style='padding:10px 14px;background:{colour};border-left:4px solid {border};"
                f"border-radius:4px;margin:4px 0'>"
                f"{icon} <strong>{lt}</strong> (max {rules.get('days_entitled',0)} days) — "
                f"{COMPENSATION_LABELS.get(comp)}</div>",
                unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### Check a staff member's adjusted score")
        chk_code = st.text_input("Staff code", key="comp_check_code")
        chk_clean = clean_code(chk_code) if chk_code.strip() else ""
        if chk_clean:
            staff_leave = lm.get_staff_leave(chk_clean)
            if not staff_leave:
                st.info("No leave records for this staff member — full score applies.")
            else:
                aff = [r for r in staff_leave if r['affects_perf']]
                if not aff:
                    st.success("Leave on record but none affects performance score.")
                else:
                    for r in aff:
                        st.warning(
                            f"**{r['leave_type']}** — {r['start_date']} to {r['end_date']} "
                            f"({r['days']} days) | Adjustment: {COMPENSATION_LABELS.get(r['compensation'])}")

                # If we have their score data
                sc_row = staff_scores[staff_scores['Staff Code'].astype(str).apply(clean_code) == chk_clean]
                if len(sc_row):
                    reg = st.session_state.get('staff_registry',{})
                    name = reg.get(chk_clean,{}).get('Staff Name', chk_clean)
                    raw_score = sc_row['Final_BSC_Score'].values[0]
                    st.metric(f"{name} — current BSC score", fmt_score(raw_score))
                    st.caption("Note: Automatic monthly pro-rata compensation is applied when you have monthly-level scores per staff. Contact admin to manually adjust if needed.")

# ════════════════════════════════════════════════════════════════
# TAB 8 — TEAM INSIGHTS
# ════════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Team insights")
    st.caption("Pillar heatmap, role distribution, and team performance patterns.")

    if not df_proc.empty and "Pillar" in df_proc.columns:
        pa = df_proc.groupby("Pillar")["Weighted_Score"].mean().reset_index()
        fig_p = px.bar(pa, x="Pillar", y="Weighted_Score",
                       title="Average weighted score by pillar",
                       color="Pillar",
                       color_discrete_map={"Financial":"#006B3F",
                                           "Customer Focus":"#185FA5",
                                           "Operational Excellence":"#F5A623"})
        fig_p.update_layout(showlegend=False, height=280,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_p, use_container_width=True)

    if len(filtered):
        ic1, ic2 = st.columns(2)
        with ic1:
            if "Role" in filtered.columns and filtered["Role"].nunique() > 1:
                role_avg = filtered.groupby("Role")["Final_BSC_Score"].agg(
                    ["mean","count"]).round(2).reset_index()
                role_avg.columns = ["Role","Avg BSC","Count"]
                role_avg = role_avg.sort_values("Avg BSC", ascending=False)
                fig_ra = px.bar(role_avg, x="Avg BSC", y="Role",
                                orientation="h", title="Avg BSC by role",
                                color="Avg BSC", color_continuous_scale="RdYlGn",
                                range_color=[1,5], text="Avg BSC")
                fig_ra.update_traces(texttemplate="%{x:.2f}", textposition="outside")
                fig_ra.update_layout(height=max(300, len(role_avg)*28),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ra, use_container_width=True)

        with ic2:
            if "Category" in filtered.columns and filtered["Category"].nunique() > 1:
                cat = filtered.groupby("Category")["Final_BSC_Score"].mean().reset_index()
                cat.columns = ["Category","Avg BSC"]
                fig_c = px.bar(cat, x="Category", y="Avg BSC",
                               title="Avg BSC — Branch vs Head Office",
                               color="Category",
                               color_discrete_sequence=["#006B3F","#185FA5"])
                fig_c.add_hline(y=3.0, line_dash="dash", line_color="#F5A623")
                fig_c.update_layout(showlegend=False, height=300,
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_c, use_container_width=True)

        # Performance band table by role
        if "Role" in filtered.columns and "Performance_Remark" in filtered.columns:
            st.markdown("#### Performance bands by role")
            band_df = filtered.groupby(["Role","Performance_Remark"]).size().reset_index(name="Count")
            band_pivot = band_df.pivot(index="Role", columns="Performance_Remark",
                                       values="Count").fillna(0).astype(int)
            st.dataframe(band_pivot, use_container_width=True)
    else:
        st.info("Upload BSC data to see team insights.")
