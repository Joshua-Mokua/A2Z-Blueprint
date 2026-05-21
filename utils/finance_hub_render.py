"""
utils/finance_hub_render.py — v10.346 (Option E, sub-batch 2).

Single source of truth for the 4 Finance render functions.
Extracted from pages/9_sbu, 10_opex, 52_mgmt_accounts, and
114_sbu_drilldown. The original 4 pages now import their render
function from here; pages/116_finance_hub.py is the consolidated
entry point with an area selector at top.

Helper functions like _load() that collided across pages have been
renamed with a domain prefix (_opex_load, _mgmt_accounts_load).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from datetime import datetime, date, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# v10.350 — STREAMLIT_AVAILABLE constant used in inherited helper code from
# the original pages/10_opex.py. Since this module only runs from inside a
# Streamlit page context, streamlit is always available — set the constant
# to True so the inherited "if not STREAMLIT_AVAILABLE" branches don't fire.
STREAMLIT_AVAILABLE = True

from utils.core import *
# v10.352 — Explicit imports MUST come AFTER `from utils.core import *`
# because utils.core defines symbols (like `cfg` as a dict) that collide
# with the public-facing function names exported by utils.config. Putting
# the explicit imports after the star import makes the explicit names win.
from utils.config import cfg, currency, regulator, tax_authority
from utils.core_audit import audit_log
from utils.db import db as a2z_db
from utils.page_access import require_access
from utils.page_access import require_access, get_my_scope
from utils.page_shared import load_shared_state



# ════════════════════════════════════════════════════════════════
# SBU_PERFORMANCE — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/9_sbu.py — SBU Performance: branch P&L, profitability analysis, turnaround."""

def _sbu_performance_safe_date(s, fallback=None):
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()


def _sbu_performance_to_float_safe(value, default=0.0):
    """Coerce a possibly-string DataFrame cell to float for f-formatting.

    Session-state DataFrames can carry string-typed numeric cells when
    upstream uploads preserve raw strings (e.g. "75.5" instead of 75.5).
    Calling f"{x:.1f}" on a string raises ValueError: Unknown format
    code 'f' for object of type 'str'. This helper coerces with a
    fallback so format strings don't crash the page."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def render_sbu_performance(actor: str) -> None:
    """Render the sbu_performance finance view. Body extracted from
    pages/<original>.py."""

    def _sbu_performance_bsc_trigger(username: str, kpi: str = ""):
        try:
            from utils.core import update_bsc_from_modules as _ubm
            _ubm(username)
        except Exception:
            pass


    um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

    st.markdown(
        "<div style='padding:16px 0 4px'>"
        "<span style='font-size:22px;font-weight:800'>🏦 SBU Performance</span>"
        "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
        "Branch P&L · Profitability · Ranking</span></div>",
        unsafe_allow_html=True)


    st.markdown(
        "<div style=\'padding:16px 22px;background:#185FA5;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>SBU Performance</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Branch P&L · Turnaround tracker · Action plans</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
        unsafe_allow_html=True)

    staff_scores  = st.session_state.get("staff_scores",  pd.DataFrame())
    df_proc       = st.session_state.get("df_processed",  pd.DataFrame())
    filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
    active_months = st.session_state.get("active_months", [])

    if len(staff_scores) == 0:
        st.markdown(
            f"<div style='padding:40px;text-align:center;background:var(--brand-light,#E8F5EE);"
            f"border-radius:12px;border:1px solid var(--brand-primary,#006B3F)33'>"
            f"<div style='font-size:32px;margin-bottom:12px'>🏦</div>"
            f"<div style='font-size:18px;font-weight:500;color:var(--brand-primary,#006B3F)'>Upload your BSC data to view SBU performance</div>"
            f"</div>", unsafe_allow_html=True)
        st.stop()

    # ── P&L KPI MAPPING ──────────────────────────────────────────────────
    PNL_INCOME_KPIS = ['Disbursements Retail Loans','Total NFI','Collection Throughput',
                        'Treasury','Trade Finance','Bancassurance']
    PNL_BALANCE_KPIS = ['Retail & MSME Deposit Growth','Loan Book Growth']
    PNL_QUALITY_KPIS = ['NPL','PAR']
    PNL_PROFIT_KPI   = 'PBT'
    PNL_CUSTOMER_KPI = 'Customer Growth'

    ALL_PNL_KPIS = PNL_INCOME_KPIS + PNL_BALANCE_KPIS + PNL_QUALITY_KPIS + [PNL_PROFIT_KPI, PNL_CUSTOMER_KPI]

    BRANCH_LABELS = {
        'Disbursements Retail Loans':  'Loan disbursements',
        'Total NFI': 'Fees & commission',
        'Collection Throughput':         'DFS revenue',
        'Treasury':            'Treasury income',
        'Trade Finance':       'Trade finance',
        'Bancassurance':       'Bancassurance',
        'Retail & MSME Deposit Growth':      'Deposit book',
        'Loan Book Growth':    'Loan book',
        'NPL':                 'NPL ratio',
        'PAR':                 'PAR ratio',
        'PBT':                 'Profit before tax',
        'Customer Growth':     'New customers',
    }

    # ── BUILD BRANCH P&L DATAFRAME ────────────────────────────────────────
    def build_branch_pnl(df_in: pd.DataFrame) -> pd.DataFrame:
        """Aggregate KPI data into branch-level P&L rows."""
        bm_data = df_in[df_in['Role'].isin(['Branch Manager','Regional Head'])].copy()
        if len(bm_data) == 0:
            return pd.DataFrame()

        rows = []
        for unit in sorted(bm_data['Unit'].unique()):
            u_data = bm_data[bm_data['Unit'] == unit]
            role   = u_data['Role'].values[0]
            region = BRANCH_REGION.get(unit, u_data.get('Region', pd.Series(['Head Office'])).values[0]
                                       if 'Region' in u_data.columns else 'Head Office')

            # Get manager name
            mgr_rows = staff_scores[staff_scores['Unit'] == unit]
            mgr_name = mgr_rows['Staff Name'].values[0] if len(mgr_rows) else '—'

            row = {'Unit': unit, 'Region': region, 'Role': role, 'Manager': mgr_name}

            for kpi in ALL_PNL_KPIS:
                k_data = u_data[u_data['KPI'] == kpi]
                if len(k_data):
                    tgt = float(k_data['Annual Target'].values[0])
                    # Use YTD_Actual (normalised from Annual Actual by process_kpi_data)
                    act_col = 'YTD_Actual' if 'YTD_Actual' in k_data.columns else 'Annual Actual'
                    act = float(k_data[act_col].values[0])
                    row[f'{kpi}_tgt'] = tgt
                    row[f'{kpi}_act'] = act
                    row[f'{kpi}_pct'] = round(act/tgt*100, 1) if tgt and tgt != 0 else 0
                else:
                    row[f'{kpi}_tgt'] = 0
                    row[f'{kpi}_act'] = 0
                    row[f'{kpi}_pct'] = 0

            # Profitability classification
            pbt_act = row.get(f'{PNL_PROFIT_KPI}_act', 0)
            pbt_pct = row.get(f'{PNL_PROFIT_KPI}_pct', 0)
            if pbt_act < 0:
                row['status'] = 'Loss-making'
                row['status_color'] = '#E24B4A'
                row['status_bg']    = '#FCEBEB'
            elif pbt_pct < 70:
                row['status'] = 'Below target'
                row['status_color'] = '#BA7517'
                row['status_bg']    = '#FAEEDA'
            elif pbt_pct < 100:
                row['status'] = 'On track'
                row['status_color'] = 'var(--brand-mid,#1D9E75)'
                row['status_bg']    = '#E1F5EE'
            else:
                row['status'] = 'Outperforming'
                row['status_color'] = 'var(--brand-primary,#006B3F)'
                row['status_bg']    = 'var(--brand-light,#E8F5EE)'

            rows.append(row)

        return pd.DataFrame(rows)


    branch_pnl = build_branch_pnl(df_proc)

    if len(branch_pnl) == 0:
        st.warning("No branch manager or regional head data found. Ensure the BSC file is uploaded.")
        st.stop()

    # Role / access filter
    role_l   = str(ud.get('role','')).lower()
    can_all  = ud.get('can_view_all', False) or any(k in role_l for k in ('admin','director','md','ceo'))
    my_unit  = ud.get('unit','')
    my_region= BRANCH_REGION.get(my_unit, ud.get('region',''))

    if can_all:
        view_pnl = branch_pnl.copy()
    elif 'regional head' in role_l:
        view_pnl = branch_pnl[branch_pnl['Region'] == my_region].copy()
    elif 'branch manager' in role_l:
        view_pnl = branch_pnl[branch_pnl['Unit'] == my_unit].copy()
    else:
        view_pnl = branch_pnl.copy()

    # ════════════════════════════════════════════════════════════════
    # HEADER
    # ════════════════════════════════════════════════════════════════
    st.markdown(
        f"<div style='padding:16px 20px;background:var(--brand-primary,#006B3F);border-radius:10px;"
        f"margin-bottom:16px;display:flex;justify-content:space-between;align-items:center'>"
        f"<div>"
        f"<div style='color:var(--color-background-primary);font-size:18px;font-weight:500'>SBU Performance</div>"
        f"<div style='color:var(--brand-accent,#9FE1CB);font-size:12px;margin-top:2px'>"
        f"Branch P&L · Regional performance · Profitability analysis · Turnaround tracking</div>"
        f"</div>"
        f"<div style='display:flex;gap:20px;font-size:13px'>"
        f"<span style='color:var(--color-background-primary)'>{len(view_pnl[view_pnl['status']=='Loss-making'])} "
        f"<span style='color:#F5A623'>loss-making</span></span>"
        f"<span style='color:var(--color-background-primary)'>{len(view_pnl[view_pnl['status']=='Below target'])} "
        f"<span style='color:#FAC775'>below target</span></span>"
        f"<span style='color:var(--color-background-primary)'>{len(view_pnl[view_pnl['status'].isin(['On track','Outperforming'])])} "
        f"<span style='color:var(--brand-accent,#9FE1CB)'>profitable</span></span>"
        f"</div></div>",
        unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────
    sbu_tabs = st.tabs(["📊 Profitability overview", "🏦 Branch P&L detail",
                         "🌍 Regional view", "🔴 Turnaround tracker", "📋 Action plans"])

    # ════════════════════════════════════════════════════════════════
    # TAB 1 — PROFITABILITY OVERVIEW
    # ════════════════════════════════════════════════════════════════
    with sbu_tabs[0]:
        # Summary metrics
        total_pbt_tgt = view_pnl[f'{PNL_PROFIT_KPI}_tgt'].sum()
        total_pbt_act = view_pnl[f'{PNL_PROFIT_KPI}_act'].sum()
        total_dep_act = view_pnl[f'Retail & MSME Deposit Growth_act'].sum()
        total_dep_tgt = view_pnl[f'Retail & MSME Deposit Growth_tgt'].sum()
        total_loan_act = view_pnl[f'Disbursements Retail Loans_act'].sum()
        total_loan_tgt = view_pnl[f'Disbursements Retail Loans_tgt'].sum()
        loss_count     = len(view_pnl[view_pnl['status']=='Loss-making'])
        profit_count   = len(view_pnl[view_pnl['status'].isin(['On track','Outperforming'])])

        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("Total PBT", fmt_num(total_pbt_act, short=True),
                  delta=f"{fmt_num(total_pbt_act - total_pbt_tgt, short=True)} vs target")
        m2.metric("PBT achievement",
                  f"{round(total_pbt_act/total_pbt_tgt*100,1) if total_pbt_tgt else 0:.1f}%")
        m3.metric("Loss-making branches", loss_count,
                  delta=f"-{loss_count}" if loss_count else "0", delta_color="inverse")
        m4.metric("Profitable branches", profit_count)
        m5.metric("Deposit book", fmt_num(total_dep_act, short=True),
                  delta=f"{round(total_dep_act/total_dep_tgt*100,1) if total_dep_tgt else 0:.0f}% of target")

        st.markdown("---")

        # Profitability bar chart — all branches
        chart_df = view_pnl[view_pnl['Role']=='Branch Manager'].copy()
        if len(chart_df):
            chart_df = chart_df.sort_values(f'{PNL_PROFIT_KPI}_act')
            colors = [r['status_color'] for _, r in chart_df.iterrows()]

            fig = go.Figure()
            fig.add_bar(
                x=chart_df['Unit'],
                y=chart_df[f'{PNL_PROFIT_KPI}_act'] / 1e6,
                marker_color=colors,
                name='PBT actual',
                text=[f"{v:.1f}M" for v in chart_df[f'{PNL_PROFIT_KPI}_act']/1e6],
                textposition='outside',
            )
            fig.add_bar(
                x=chart_df['Unit'],
                y=chart_df[f'{PNL_PROFIT_KPI}_tgt'] / 1e6,
                marker_color='rgba(0,0,0,0.1)',
                marker_line_color='var(--brand-primary,#006B3F)',
                marker_line_width=1.5,
                name='PBT target',
            )
            fig.add_hline(y=0, line_color='#E24B4A', line_dash='dash', line_width=1.5,
                           annotation_text='Break-even')
            fig.update_layout(
                title='Branch profitability — PBT actual vs target (KES millions)',
                barmode='overlay', height=420, showlegend=True,
                xaxis_tickangle=-35,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                yaxis_title='KES millions',
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
            )
            st.plotly_chart(fig, use_container_width=True)

        # Heatmap — all KPIs across all branches
        st.markdown("#### Performance heatmap — all KPIs")
        hm_branches = view_pnl[view_pnl['Role']=='Branch Manager']['Unit'].tolist()
        hm_kpis     = [k for k in PNL_INCOME_KPIS + [PNL_PROFIT_KPI] if f'{k}_pct' in view_pnl.columns]
        if hm_branches and hm_kpis:
            hm_data = view_pnl[view_pnl['Role']=='Branch Manager'].set_index('Unit')[
                [f'{k}_pct' for k in hm_kpis]]
            hm_data.columns = [BRANCH_LABELS.get(k,k) for k in hm_kpis]
            fig_hm = px.imshow(
                hm_data,
                color_continuous_scale=[[0,'#E24B4A'],[0.35,'#F5A623'],
                                         [0.7,'var(--brand-mid,#1D9E75)'],[1,'var(--brand-primary,#006B3F)']],
                text_auto='.0f', aspect='auto',
                title='KPI achievement % — red = below 50%, green = above 100%')
            fig_hm.update_coloraxes(colorbar_title='%')
            fig_hm.update_layout(height=500, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_hm, use_container_width=True)

    # ════════════════════════════════════════════════════════════════
    # TAB 2 — BRANCH P&L DETAIL
    # ════════════════════════════════════════════════════════════════
    with sbu_tabs[1]:
        st.subheader("Branch P&L detail")

        # Filters
        fc1, fc2, fc3 = st.columns(3)
        status_f = fc1.selectbox("Status", ["All","Loss-making","Below target","On track","Outperforming"])
        region_f = fc2.selectbox("Region", ["All"] + REGIONS)
        search_f = fc3.text_input("Search branch")

        disp = view_pnl[view_pnl['Role']=='Branch Manager'].copy()
        if status_f != "All": disp = disp[disp['status']==status_f]
        if region_f != "All": disp = disp[disp['Region']==region_f]
        if search_f: disp = disp[disp['Unit'].str.contains(search_f, case=False)]

        disp_sorted = disp.sort_values(f'{PNL_PROFIT_KPI}_act')

        for _, branch in disp_sorted.iterrows():
            pbt_act = branch[f'{PNL_PROFIT_KPI}_act']
            pbt_tgt = branch[f'{PNL_PROFIT_KPI}_tgt']
            pbt_pct = branch[f'{PNL_PROFIT_KPI}_pct']
            s_clr   = branch['status_color']
            s_bg    = branch['status_bg']

            with st.expander(
                f"{branch['Unit']}  ·  {branch['Region']} Region  ·  "
                f"PBT: {fmt_num(pbt_act, short=True)}  ({_sbu_performance_to_float_safe(pbt_pct):.1f}% of target)  ·  {branch['status']}",
                expanded=(branch['status'] == 'Loss-making')):

                # Header row
                st.markdown(
                    f"<div style='padding:10px 14px;background:{s_bg};"
                    f"border-left:4px solid {s_clr};border-radius:0 6px 6px 0;margin-bottom:12px'>"
                    f"<b style='color:{s_clr}'>{branch['status']}</b> &nbsp;|&nbsp; "
                    f"Manager: {branch['Manager']} &nbsp;|&nbsp; Region: {branch['Region']}"
                    f"</div>", unsafe_allow_html=True)

                # P&L table
                bc1, bc2 = st.columns([3,2])
                with bc1:
                    # Key banking ratios
                    pbt_a_br = branch.get(f'{PNL_PROFIT_KPI}_act', 0)
                    oi_a     = branch.get('Disbursements Retail Loans_act', 0) + branch.get('Loan Book Growth_act', 0)
                    dep_a    = branch.get('Retail & MSME Deposit Growth_act', 0)
                    rev_ph   = fmt_num(
                        (dep_a + oi_a) / max(1, len([s for s in staff_scores['Unit'].tolist()
                                                      if s == branch['Unit']])), short=True
                    ) if len(staff_scores) else '—'
                    cir_br   = round(abs((branch.get(f'{PNL_PROFIT_KPI}_tgt', 1) - pbt_a_br)) /
                               max(1, dep_a + oi_a) * 100, 1) if (dep_a + oi_a) > 0 else 0

                    kr1,kr2,kr3 = st.columns(3)
                    kr1.metric("PBT", fmt_num(pbt_a_br, short=True))
                    kr2.metric("CIR estimate", f"{_sbu_performance_to_float_safe(cir_br):.1f}%")
                    kr3.metric("Revenue/staff", rev_ph)
                    st.markdown("---")

                    st.markdown("**Income statement**")
                    pnl_rows = []
                    total_income_act = 0
                    total_income_tgt = 0
                    for kpi in PNL_INCOME_KPIS:
                        act = branch.get(f'{kpi}_act', 0)
                        tgt = branch.get(f'{kpi}_tgt', 0)
                        pct = branch.get(f'{kpi}_pct', 0)
                        total_income_act += act
                        total_income_tgt += tgt
                        pnl_rows.append({
                            'Line item': BRANCH_LABELS.get(kpi, kpi),
                            'Target': fmt_num(tgt, short=True),
                            'Actual': fmt_num(act, short=True),
                            'Ach %':  f"{_sbu_performance_to_float_safe(pct):.1f}%",
                        })
                    # PBT
                    pnl_rows.append({
                        'Line item': '— Profit before tax',
                        'Target': fmt_num(pbt_tgt, short=True),
                        'Actual': fmt_num(pbt_act, short=True),
                        'Ach %': f"{_sbu_performance_to_float_safe(pbt_pct):.1f}%",
                    })
                    pnl_df = pd.DataFrame(pnl_rows)
                    def hl_pnl(v):
                        try:
                            pct = float(str(v).replace('%',''))
                            if pct < 0:  return 'color:#E24B4A;font-weight:500'
                            if pct < 70: return 'color:#BA7517'
                            if pct >= 100: return 'color:var(--brand-primary,#006B3F);font-weight:500'
                        except: pass
                        return ''
                    st.dataframe(
                        pnl_df.style.map(hl_pnl, subset=['Ach %']),
                        use_container_width=True, hide_index=True)

                with bc2:
                    st.markdown("**Balance sheet**")
                    bs_rows = []
                    for kpi in PNL_BALANCE_KPIS:
                        bs_rows.append({
                            'Item': BRANCH_LABELS.get(kpi, kpi),
                            'Target': fmt_num(branch.get(f'{kpi}_tgt',0), short=True),
                            'Actual': fmt_num(branch.get(f'{kpi}_act',0), short=True),
                            'Ach %': f"{_sbu_performance_to_float_safe(branch.get(f'{kpi}_pct',0)):.1f}%",
                        })
                    bs_rows.append({'Item':'———','Target':'','Actual':'','Ach %':''})
                    st.markdown("**Asset quality**")
                    for kpi in PNL_QUALITY_KPIS:
                        act_q = branch.get(f'{kpi}_act', 0)
                        tgt_q = branch.get(f'{kpi}_tgt', 0)
                        # For quality KPIs lower is better
                        ach_q = round(tgt_q/act_q*100,1) if act_q and act_q > 0 else 100
                        bs_rows.append({
                            'Item': BRANCH_LABELS.get(kpi,kpi),
                            'Target': f"{_sbu_performance_to_float_safe(tgt_q)*100:.1f}%" if _sbu_performance_to_float_safe(tgt_q) < 1 else fmt_num(tgt_q),
                            'Actual': f"{_sbu_performance_to_float_safe(act_q)*100:.1f}%" if _sbu_performance_to_float_safe(act_q) < 1 else fmt_num(act_q),
                            'Ach %': f"{_sbu_performance_to_float_safe(ach_q):.1f}%",
                        })
                    bs_rows.append({'Item':'New customers',
                                    'Target': fmt_num(branch.get(f'{PNL_CUSTOMER_KPI}_tgt',0)),
                                    'Actual': fmt_num(branch.get(f'{PNL_CUSTOMER_KPI}_act',0)),
                                    'Ach %': f"{_sbu_performance_to_float_safe(branch.get(f'{PNL_CUSTOMER_KPI}_pct',0)):.1f}%"})
                    st.dataframe(pd.DataFrame(bs_rows), use_container_width=True, hide_index=True)

    # ════════════════════════════════════════════════════════════════
    # TAB 3 — REGIONAL VIEW
    # ════════════════════════════════════════════════════════════════
    with sbu_tabs[2]:
        st.subheader("Regional performance")
        st.caption("Aggregated across all branches within each region — matches Regional Head BSC.")

        for region in REGIONS:
            reg_branches = view_pnl[
                (view_pnl['Region'] == region) & (view_pnl['Role'].isin(get_org_roles() or ['Branch Manager']))]
            reg_head = view_pnl[
                (view_pnl['Region'] == region) & (view_pnl['Role'].isin([r for r in [str(x) for x in (get_org_roles() or [])] if 'area' in r.lower() or 'regional' in r.lower() or 'head' in r.lower()] or ['Regional Head','Area Manager']))]

            if len(reg_branches) == 0: continue

            # Region aggregate
            r_pbt_act = reg_branches[f'{PNL_PROFIT_KPI}_act'].sum()
            r_pbt_tgt = reg_branches[f'{PNL_PROFIT_KPI}_tgt'].sum()
            r_pbt_pct = round(r_pbt_act/r_pbt_tgt*100,1) if r_pbt_tgt else 0
            r_dep_act = reg_branches[f'Retail & MSME Deposit Growth_act'].sum()
            r_dep_tgt = reg_branches[f'Retail & MSME Deposit Growth_tgt'].sum()
            r_loss    = len(reg_branches[reg_branches['status']=='Loss-making'])
            rh_name   = reg_head['Manager'].values[0] if len(reg_head) else '—'

            r_clr = '#E24B4A' if r_pbt_act < 0 else ('#BA7517' if r_pbt_pct < 70 else 'var(--brand-primary,#006B3F)')
            r_bg  = '#FCEBEB' if r_pbt_act < 0 else ('#FAEEDA' if r_pbt_pct < 70 else 'var(--brand-light,#E8F5EE)')

            with st.expander(
                f"{region} Region  ·  Regional Head: {rh_name}  ·  "
                f"PBT: {fmt_num(r_pbt_act, short=True)} ({_sbu_performance_to_float_safe(r_pbt_pct):.1f}%)  ·  "
                f"{r_loss} loss-making branch(es)",
                expanded=True):

                st.markdown(
                    f"<div style='padding:10px;background:{r_bg};border-left:4px solid {r_clr};"
                    f"border-radius:0 6px 6px 0;margin-bottom:10px;display:flex;gap:24px'>"
                    f"<span>PBT: <b>{fmt_num(r_pbt_act, short=True)}</b> / {fmt_num(r_pbt_tgt, short=True)} "
                    f"({_sbu_performance_to_float_safe(r_pbt_pct):.1f}%)</span>"
                    f"<span>Deposits: <b>{fmt_num(r_dep_act, short=True)}</b> / {fmt_num(r_dep_tgt, short=True)} "
                    f"({round(r_dep_act/r_dep_tgt*100,1) if r_dep_tgt else 0:.1f}%)</span>"
                    f"<span>Branches: {len(reg_branches)} total, {r_loss} loss-making</span>"
                    f"</div>", unsafe_allow_html=True)

                # Branch comparison within region
                reg_chart = reg_branches.sort_values(f'{PNL_PROFIT_KPI}_act')
                fig_r = go.Figure()
                fig_r.add_bar(
                    x=reg_chart['Unit'],
                    y=reg_chart[f'{PNL_PROFIT_KPI}_act']/1e6,
                    marker_color=[r['status_color'] for _,r in reg_chart.iterrows()],
                    name='PBT actual',
                    text=[f"{v:.1f}M" for v in reg_chart[f'{PNL_PROFIT_KPI}_act']/1e6],
                    textposition='outside',
                )
                fig_r.add_hline(y=0, line_color='#E24B4A', line_dash='dash', line_width=1)
                fig_r.update_layout(
                    height=280, showlegend=False,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    yaxis_title='KES millions', margin=dict(l=0,r=0,t=10,b=0))
                st.plotly_chart(fig_r, use_container_width=True)

    # ════════════════════════════════════════════════════════════════
    # TAB 4 — TURNAROUND TRACKER
    # ════════════════════════════════════════════════════════════════
    with sbu_tabs[3]:
        st.subheader("Turnaround tracker")
        st.caption("Loss-making and below-target branches — root cause analysis and turnaround status.")

        at_risk = view_pnl[
            (view_pnl['status'].isin(['Loss-making','Below target'])) &
            (view_pnl['Role'].isin(get_org_roles() or ['Branch Manager']))
        ].sort_values(f'{PNL_PROFIT_KPI}_act')

        if len(at_risk) == 0:
            st.success("No loss-making or below-target branches. All SBUs are on track.")
        else:
            for _, branch in at_risk.iterrows():
                s_clr = branch['status_color']
                s_bg  = branch['status_bg']
                pbt_a = branch[f'{PNL_PROFIT_KPI}_act']
                pbt_t = branch[f'{PNL_PROFIT_KPI}_tgt']
                pbt_p = branch[f'{PNL_PROFIT_KPI}_pct']
                gap   = pbt_t - pbt_a

                with st.expander(
                    f"{'🔴' if branch['status']=='Loss-making' else '🟡'} "
                    f"{branch['Unit']}  —  {branch['status']}  —  "
                    f"Gap: {fmt_num(gap, short=True)}",
                    expanded=(branch['status']=='Loss-making')):

                    st.markdown(
                        f"<div style='padding:10px 14px;background:{s_bg};"
                        f"border-left:4px solid {s_clr};border-radius:0 6px 6px 0'>"
                        f"<b style='color:{s_clr}'>{branch['status']}</b> &nbsp;|&nbsp; "
                        f"PBT: {fmt_num(pbt_a,True)} vs target {fmt_num(pbt_t,True)} "
                        f"({_sbu_performance_to_float_safe(pbt_p):.1f}%) &nbsp;|&nbsp; Gap: {fmt_num(gap,True)}"
                        f"</div>", unsafe_allow_html=True)

                    # Root cause analysis
                    st.markdown("#### Root cause analysis")
                    rc1, rc2 = st.columns(2)
                    weak_kpis  = []
                    strong_kpis = []
                    for kpi in PNL_INCOME_KPIS + ['Retail & MSME Deposit Growth']:
                        pct = branch.get(f'{kpi}_pct', 0)
                        if pct < 60:   weak_kpis.append((kpi, pct))
                        elif pct >= 90: strong_kpis.append((kpi, pct))

                    with rc1:
                        st.markdown("**Underperforming income lines**")
                        if weak_kpis:
                            for kpi, pct in sorted(weak_kpis, key=lambda x: x[1]):
                                act = branch.get(f'{kpi}_act', 0)
                                tgt = branch.get(f'{kpi}_tgt', 0)
                                st.markdown(
                                    f"<div style='padding:6px 10px;background:#FCEBEB;"
                                    f"border-left:3px solid #E24B4A;border-radius:0 4px 4px 0;"
                                    f"font-size:12px;margin:3px 0'>"
                                    f"<b>{BRANCH_LABELS.get(kpi,kpi)}</b>: "
                                    f"{fmt_num(act,True)} / {fmt_num(tgt,True)} ({_sbu_performance_to_float_safe(pct):.1f}%)"
                                    f"</div>", unsafe_allow_html=True)
                        else:
                            st.info("Income lines performing adequately.")

                    with rc2:
                        st.markdown("**Asset quality concerns**")
                        for kpi in PNL_QUALITY_KPIS:
                            act_q = branch.get(f'{kpi}_act', 0)
                            tgt_q = branch.get(f'{kpi}_tgt', 0)
                            if act_q and tgt_q and act_q > tgt_q * 1.1:
                                st.markdown(
                                    f"<div style='padding:6px 10px;background:#FAEEDA;"
                                    f"border-left:3px solid #BA7517;border-radius:0 4px 4px 0;"
                                    f"font-size:12px;margin:3px 0'>"
                                    f"⚠️ {BRANCH_LABELS.get(kpi,kpi)}: "
                                    f"{_sbu_performance_to_float_safe(act_q)*100:.1f}% vs target {_sbu_performance_to_float_safe(tgt_q)*100:.1f}%</div>",
                                    unsafe_allow_html=True)
                        # Customer gap
                        cust_pct = branch.get(f'{PNL_CUSTOMER_KPI}_pct', 0)
                        if cust_pct < 60:
                            st.markdown(
                                f"<div style='padding:6px 10px;background:#FAEEDA;"
                                f"border-left:3px solid #BA7517;border-radius:0 4px 4px 0;"
                                f"font-size:12px;margin:3px 0'>"
                                f"⚠️ Customer acquisition: {_sbu_performance_to_float_safe(cust_pct):.1f}% of target</div>",
                                unsafe_allow_html=True)

                    # Branch manager explanation
                    st.markdown("#### Branch manager explanation")
                    explanation_key = f"explanation_{branch['Unit'].replace(' ','_')}"
                    saved_exp = st.session_state.get(explanation_key, "")
                    explanation = st.text_area(
                        "Branch manager's explanation for underperformance",
                        value=saved_exp,
                        placeholder="Describe the key factors contributing to the performance shortfall — "
                                    "market conditions, competition, operational challenges, etc.",
                        height=100,
                        key=f"exp_{branch['Unit']}")
                    if st.button("Save explanation", key=f"save_exp_{branch['Unit']}"):
                        st.session_state[explanation_key] = explanation
                        st.success("Explanation saved.")

                    # Suggested turnaround strategies
                    st.markdown("#### Proposed turnaround strategies")
                    strategies = []
                    if pbt_a < 0:
                        strategies += [
                            "Immediate cost audit — identify and eliminate non-essential opex",
                            "Deposit mobilisation drive — assign personal targets to all branch staff",
                            "Loan book quality review — provisioning and recovery acceleration",
                            "Fee income activation — cross-sell DFS, bancassurance to existing customers",
                        ]
                    if weak_kpis:
                        for kpi, pct in weak_kpis[:2]:
                            strategies.append(f"Targeted {BRANCH_LABELS.get(kpi,kpi).lower()} "
                                              f"drive — currently at {pct:.0f}% of target")
                    for i, strat in enumerate(strategies[:5], 1):
                        st.markdown(
                            f"<div style='padding:6px 12px;border-left:3px solid var(--brand-primary,#006B3F);"
                            f"background:var(--brand-light,#E8F5EE);font-size:12px;margin:3px 0'>"
                            f"{i}. {strat}</div>",
                            unsafe_allow_html=True)

                    # Propose initiative
                    st.markdown("#### Propose Execute initiative")
                    st.caption("Convert this turnaround into a tracked initiative in the Execute module.")
                    init_name = st.text_input(
                        "Initiative name",
                        value=f"{branch['Unit']} turnaround — Q2 2026",
                        key=f"init_name_{branch['Unit']}")
                    init_obj  = st.text_area(
                        "Objective",
                        value=f"Return {branch['Unit']} to profitability by end of Q3 2026. "
                              f"Close PBT gap of {fmt_num(gap, True)}.",
                        height=70,
                        key=f"init_obj_{branch['Unit']}")

                    if st.button(f"Create Execute initiative", key=f"create_init_{branch['Unit']}",
                                  type="primary"):
                        ws_list = list(em.workstreams.keys()) if em else []
                        ws_val  = ws_list[0] if ws_list else "Retail Banking"
                        new_id  = em.create_initiative({
                            'name':             init_name,
                            'objective':        init_obj,
                            'category':         'Impact Generation',
                            'workstream':       ws_val,
                            'sub_workstream':   branch['Region'] + ' Region',
                            'io':               uname,
                            'io_backup':        '',
                            'estimated_impact': float(gap),
                            'impact_kpis':      ['PBT', 'Retail & MSME Deposit Growth'],
                            'tags':             ['turnaround', branch['Region'].lower()],
                            'created_by':       uname,
                        })
                        audit_log("TURNAROUND_INIT", uname, f"{new_id}:{branch['Unit']}")
                        _sbu_performance_bsc_trigger(uname, "K005")
                        st.success(f"Initiative {new_id} created in Execute module!")

    # ════════════════════════════════════════════════════════════════
    # TAB 5 — ACTION PLANS & TRACKER
    # ════════════════════════════════════════════════════════════════
    with sbu_tabs[4]:
        st.subheader("Action plans & performance tracker")
        st.caption("Branch-level action plans with progress tracking. Linked to BSC performance.")

        # Load action plans from disk (persisted)
        _ap_file = DATA_DIR / "sbu_action_plans.json"
        if 'sbu_action_plans' not in st.session_state:
            try:
                _ap_raw = _ap_file.read_text() if _ap_file.exists() else "{}"
                st.session_state['sbu_action_plans'] = json.loads(_ap_raw)
            except:
                st.session_state['sbu_action_plans'] = {}
        action_plans = st.session_state.get('sbu_action_plans', {})

        def _save_action_plans():
            """Persist action plans to disk."""
            try:
                a2z_db.save_json(_ap_file, action_plans)
            except: pass

        # Branch selector
        all_branches = view_pnl[view_pnl['Role']=='Branch Manager']['Unit'].tolist()
        sel_branch   = st.selectbox("Select branch", sorted(all_branches), key="ap_branch")

        branch_data = view_pnl[view_pnl['Unit'] == sel_branch]
        if len(branch_data):
            br = branch_data.iloc[0]
            pbt_a = br[f'{PNL_PROFIT_KPI}_act']
            pbt_t = br[f'{PNL_PROFIT_KPI}_tgt']
            pbt_p = br[f'{PNL_PROFIT_KPI}_pct']

            st.markdown(
                f"<div style='padding:10px 14px;background:{br['status_bg']};"
                f"border-left:4px solid {br['status_color']};border-radius:0 6px 6px 0;margin:8px 0'>"
                f"<b style='color:{br['status_color']}'>{br['status']}</b> &nbsp;|&nbsp; "
                f"PBT: {fmt_num(pbt_a, True)} / {fmt_num(pbt_t, True)} ({pbt_p:.1f}%)"
                f"</div>", unsafe_allow_html=True)

        # Add action item
        with st.form(f"add_action_{sel_branch}"):
            st.markdown("**Add action item**")
            ac1, ac2 = st.columns(2)
            action_text   = ac1.text_input("Action *", placeholder="e.g. Launch salary account drive")
            action_target = ac2.text_input("Success metric", placeholder="e.g. 50 new accounts by 30 Apr")
            ac3, ac4, ac5 = st.columns(3)
            action_owner   = ac3.text_input("Primary owner *", placeholder="Username or name")
            action_owner2  = ac4.text_input("Secondary owner", placeholder="Backup / co-owner")
            action_due     = ac5.date_input("Due date")
            action_kpi     = st.selectbox("Linked KPI", [""] + ALL_PNL_KPIS)
            action_esc_to  = st.text_input("Escalate to (if overdue)", placeholder="Branch manager / Regional Head username")

            if st.form_submit_button("Add action item", type="primary"):
                if action_text and action_owner:
                    key = sel_branch
                    if key not in action_plans:
                        action_plans[key] = []
                    action_plans[key].append({
                        'id':             f"AP{len(action_plans.get(key,[]))+1:03d}",
                        'action':         action_text,
                        'owner':          action_owner,
                        'secondary_owner':action_owner2,
                        'escalate_to':    action_esc_to,
                        'due':            str(action_due),
                        'kpi':            action_kpi,
                        'target':         action_target,
                        'status':         'Not started',
                        'accepted':       False,
                        'accepted_at':    '',
                        'progress':       0,
                        'notes':          [],
                        'esc_level':      0,
                        'created':        str(date.today()),
                        'created_by':     uname,
                    })
                    st.session_state['sbu_action_plans'] = action_plans
                    audit_log("ACTION_CREATED", uname, f"{sel_branch}:{action_text[:40]}")
                    _sbu_performance_bsc_trigger(uname, "K005")
                    st.success("Action item added — owner must accept before work begins.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Action and primary owner are required.")

        # Display existing action items
        branch_actions = action_plans.get(sel_branch, [])
        if not branch_actions:
            st.info(f"No action items for {sel_branch} yet. Add the first one above.")
        else:
            st.markdown(f"**{len(branch_actions)} action item(s)**")
            done_count    = sum(1 for a in branch_actions if a['status']=='Complete')
            overall_prog  = done_count / len(branch_actions) * 100 if branch_actions else 0
            st.progress(overall_prog/100, text=f"Overall: {done_count}/{len(branch_actions)} complete ({overall_prog:.0f}%)")

            for ai, action in enumerate(branch_actions):
                status   = action['status']
                accepted = action.get('accepted', False)
                overdue  = action['due'] < str(date.today()) and status != 'Complete'
                days_od  = (date.today() - _sbu_performance_safe_date(action['due'])).days if overdue else 0

                # Auto-compute escalation level
                esc = 0
                if overdue and not accepted:  esc = 2  # owner hasn't even accepted
                elif days_od > 7:             esc = 3  # sponsor
                elif days_od > 2:             esc = 2  # lead
                elif days_od > 0:             esc = 1  # IO
                action_plans[sel_branch][ai]['esc_level'] = esc

                esc_badge = {0:'', 1:'🟡 IO alert', 2:'🔴 Lead escalation', 3:'🚨 Sponsor'}[esc]
                acc_badge = '✅ Accepted' if accepted else '⏳ Pending acceptance'
                s_icon    = {'Not started':'⏳','In progress':'🔄','Complete':'✅','Blocked':'🚧'}.get(status,'⏳')

                with st.expander(
                    f"{s_icon} {action['id']} — {action['action'][:50]}"
                    f"  |  Owner: {action['owner']}  |  Due {action['due']}"
                    f"{'  ⚠️ ' + str(days_od) + 'd OVERDUE' if overdue else ''}"
                    f"  |  {esc_badge if esc else acc_badge}",
                    expanded=(esc >= 2 or not accepted)):

                    # Context row
                    cc1,cc2,cc3 = st.columns(3)
                    cc1.caption(f"KPI: {action.get('kpi','—')}")
                    cc2.caption(f"Target: {action.get('target','—')}")
                    cc3.caption(f"Escalate to: {action.get('escalate_to','—')}")

                    if action.get('secondary_owner'):
                        st.caption(f"Secondary owner: {action['secondary_owner']}")

                    # Escalation banner
                    if esc > 0:
                        esc_msg = {1:"Owner notified — follow up required",
                                   2:f"Lead attention needed — {days_od}d overdue",
                                   3:f"Sponsor escalation — {days_od}d overdue. Immediate action required"}[esc]
                        esc_bg  = {1:'#FFFBF0',2:'#FFF5F0',3:'#FFF0F0'}[esc]
                        esc_clr = {1:'#BA7517',2:'#993C1D',3:'#A32D2D'}[esc]
                        st.markdown(
                            f"<div style='padding:8px 12px;background:{esc_bg};"
                            f"border-left:3px solid {esc_clr};border-radius:0 4px 4px 0;"
                            f"font-size:12px;margin:4px 0'>"
                            f"<b style='color:{esc_clr}'>{esc_badge}</b> — {esc_msg}</div>",
                            unsafe_allow_html=True)

                    # Acceptance button (for the owner)
                    if not accepted and (action['owner'] == uname or
                                         action.get('secondary_owner') == uname):
                        if st.button(f"✅ I accept this action item",
                                      key=f"acc_{sel_branch}_{ai}", type="primary"):
                            action_plans[sel_branch][ai]['accepted']    = True
                            action_plans[sel_branch][ai]['accepted_at'] = str(date.today())
                            st.session_state['sbu_action_plans'] = action_plans
                            audit_log("ACTION_ACCEPTED", uname, f"{sel_branch}:{action['id']}")
                            _sbu_performance_bsc_trigger(uname, "K005")
                            st.success("Action accepted — you are now accountable for delivery.")
                            st.cache_data.clear()
                            st.rerun()
                    elif not accepted:
                        st.warning(f"Awaiting acceptance from {action['owner']}")

                    # Progress update (only after acceptance)
                    if accepted:
                        up1, up2, up3 = st.columns([2,1,2])
                        status_opts = ['Not started','In progress','Complete','Blocked']
                        new_status = up1.selectbox("Status", status_opts,
                            index=status_opts.index(status) if status in status_opts else 0,
                            key=f"aps_{sel_branch}_{ai}")
                        new_prog = up2.slider("Progress", 0, 100,
                            value=action.get('progress',0), step=10,
                            key=f"app_{sel_branch}_{ai}")
                        new_note = up3.text_input("Update note", key=f"apn_{sel_branch}_{ai}")

                        if st.button("Save update", key=f"apb_{sel_branch}_{ai}", type="primary"):
                            action_plans[sel_branch][ai]['status']   = new_status
                            action_plans[sel_branch][ai]['progress'] = new_prog
                            if new_note:
                                notes = action_plans[sel_branch][ai].get('notes', [])
                                if isinstance(notes, str): notes = [notes] if notes else []
                                notes.append({'note': new_note, 'by': uname,
                                              'date': str(date.today())})
                                action_plans[sel_branch][ai]['notes'] = notes
                            st.session_state['sbu_action_plans'] = action_plans
                            audit_log("ACTION_UPDATED", uname,
                                      f"{sel_branch}:{action['id']}:{new_status}")
                            _sbu_performance_bsc_trigger(uname, "K005")
                            st.success("Updated!"); st.rerun()

                    # Notes history
                    notes_hist = action.get('notes', [])
                    if notes_hist:
                        with st.expander("Update history"):
                            if isinstance(notes_hist, list):
                                for n in reversed(notes_hist[-5:]):
                                    if isinstance(n, dict):
                                        st.caption(f"{n.get('date','')} ({n.get('by','')}): {n.get('note','')}")
                                    else:
                                        st.caption(str(n))


# ════════════════════════════════════════════════════════════════
# SBU_DRILLDOWN — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/114_sbu_drilldown.py — Customer-Value SBU Drill-Down (v10.338).

Sibling to pages/9_sbu.py. The existing 9_sbu is BRANCH-level P&L
(branch as the unit of P&L). This page is CUSTOMER-VALUE SBU drill-
down: Retail SBU broken into Affluent / Core Middle / Mass; Commercial
SBU broken into MSME (Micro/Small/Medium) and Corporate, both × CBK
sector. Tagged-RM P&L exposes which Relationship Managers own which
revenue. Propositions overlay is view-only (does not reconcile).

Per v10.338 design — Q1/Q2/Q3/Q5 all settled:
  - Codes fixed, display names + thresholds admin-editable
  - MSME = Micro + Small + Medium (turnover-banded); Corporate standalone
  - Both Business segments × CBK sector as second dimension
  - Propositions overlay: view-only, may overlap, does not reconcile
  - Rollup approach — aggregates customer_profitability per-customer PBT

Tab budget: 6 of 7 (G4 ≤7 ceiling). One slot reserved for partnerships
/ ecosystem banking when that data lands.
"""


def render_sbu_drilldown(actor: str) -> None:
    """Render the sbu_drilldown finance view. Body extracted from
    pages/<original>.py."""


    _um, _ud, _uname, _em, _ri_pm, _prod_m, _pm, _lm, _hr_m, _casc, _vm, _rlm = (
        load_shared_state()
    )


    st.markdown("# 🏦 SBU Drill-Down — Customer-Value View")
    st.markdown(
        "Drill into bank performance by customer segment, economic sector, "
        "tagged RM, or proposition overlay. Branch-level P&L lives on "
        "the existing **SBU Performance** page (pages/9_sbu.py)."
    )

    st.info(
        "**v10.340 — Cost source: MATRIX.** Indirect costs now come from "
        "the admin-editable allocation matrix (Admin → Performance → Cost "
        "Matrix), not the v10.338 proxy split. Revenue + direct costs "
        "remain customer-level proxies until real GL data integrates. "
        "**Negative PBT in retail tiers is honest** — synthesized "
        "virtual-bank revenue is undersized vs real Tier-2 bank opex; "
        "Corporate + Medium subsidise the rest. Real GL data closes the gap."
    )


    # ────────────────────────────────────────────────────────────────────
    # Cached rollups
    # ────────────────────────────────────────────────────────────────────

    @st.cache_data(ttl=60)
    def _sbu_drilldown_seg_rollup(period: str):
        from utils.sbu_pnl_rollup import rollup_by_segment
        return rollup_by_segment(period)


    @st.cache_data(ttl=60)
    def _sbu_drilldown_sector_rollup(period: str):
        from utils.sbu_pnl_rollup import rollup_by_cbk_sector
        return rollup_by_cbk_sector(period)


    @st.cache_data(ttl=60)
    def _sbu_drilldown_rm_rollup(period: str):
        from utils.sbu_pnl_rollup import rollup_by_tagged_rm
        return rollup_by_tagged_rm(period)


    @st.cache_data(ttl=60)
    def _sbu_drilldown_prop_rollup(period: str):
        from utils.sbu_pnl_rollup import rollup_by_proposition
        return rollup_by_proposition(period)


    @st.cache_data(ttl=60)
    def _sbu_drilldown_bank_pnl(period: str):
        from utils.sbu_pnl_rollup import bank_total_pnl, rollup_meta
        return bank_total_pnl(period), rollup_meta()


    @st.cache_data(ttl=60)
    def _sbu_drilldown_bs(period: str):
        from utils.segment_balance_sheet import (
            balance_sheet_by_segment, bank_balance_sheet,
            capital_adequacy_check, bs_meta,
        )
        return (
            balance_sheet_by_segment(period),
            bank_balance_sheet(period),
            capital_adequacy_check(period),
            bs_meta(),
        )


    # ────────────────────────────────────────────────────────────────────
    # Period selector
    # ────────────────────────────────────────────────────────────────────

    period = st.selectbox(
        "Period",
        options=["2026-Q2", "2026-Q1", "2025-Q4", "2025-Q3"],
        index=0,
    )


    # ────────────────────────────────────────────────────────────────────
    # Helper formatters
    # ────────────────────────────────────────────────────────────────────

    def _sbu_drilldown_fmt_b(x):
        if x is None:
            return "—"
        return f"KES {x/1e9:.3f}B"


    def _fmt_m(x):
        if x is None:
            return "—"
        return f"KES {x/1e6:.1f}M"


    def _fmt_pct(x):
        if x is None:
            return "—"
        return f"{x:.2f}%"


    # ────────────────────────────────────────────────────────────────────
    # Tabs
    # ────────────────────────────────────────────────────────────────────

    tab_bank, tab_retail, tab_commercial, tab_sector, tab_rm, tab_prop, tab_bs = st.tabs([
        "📊 Bank P&L",
        "🏘️ Retail (Affluent / Core / Mass)",
        "🏢 Commercial (MSME / Corporate)",
        "🌾 CBK Sector",
        "🧑‍💼 RM-Tagged",
        "🎯 Propositions (view-only)",
        "💰 Balance Sheet",
    ])


    # ════════════════════════════════════════════════════════════════
    # TAB 1 — Bank P&L
    # ════════════════════════════════════════════════════════════════
    with tab_bank:
        bank, meta = _sbu_drilldown_bank_pnl(period)
        segments = _sbu_drilldown_seg_rollup(period)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Revenue", _sbu_drilldown_fmt_b(bank["revenue"]))
        c2.metric("Direct Costs", _sbu_drilldown_fmt_b(bank["direct_cost"]))
        c3.metric("Indirect Costs", _sbu_drilldown_fmt_b(bank["indirect_cost"]))
        c4.metric("PBT", _sbu_drilldown_fmt_b(bank["pbt"]))

        st.caption(
            f"Customers: {bank['customer_count']}  ·  PBT margin: "
            f"{_fmt_pct(bank.get('pbt_margin_pct'))}"
        )

        st.markdown("### Segment composition")
        rows = []
        for seg, b in segments.items():
            rows.append({
                "Segment":     seg,
                "Customers":   b["customer_count"],
                "Revenue (B)": round(b["revenue"]/1e9, 3),
                "PBT (B)":     round(b["pbt"]/1e9, 3),
                "Margin %":    b.get("pbt_margin_pct"),
            })
        df = pd.DataFrame(rows).sort_values("PBT (B)", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

        with st.expander("Data source"):
            st.json(meta)


    # ════════════════════════════════════════════════════════════════
    # TAB 2 — Retail (Individual segments)
    # ════════════════════════════════════════════════════════════════
    with tab_retail:
        st.markdown("### Retail SBU — Chief Retail Banking Officer")
        st.caption(
            "Three Individual tiers: Affluent (TRB ≥ 5M) · "
            "Core Middle (500K–5M) · Mass (< 500K). "
            "Tier thresholds + display names admin-editable."
        )
        segments = _sbu_drilldown_seg_rollup(period)
        retail_codes = ["AFFLUENT", "CORE_MIDDLE", "MASS"]

        cols = st.columns(len(retail_codes))
        for i, code in enumerate(retail_codes):
            b = segments.get(code)
            if not b:
                cols[i].metric(code, "—")
                continue
            cols[i].metric(
                code,
                _sbu_drilldown_fmt_b(b["pbt"]),
                f"{b['customer_count']} customers · {_fmt_pct(b.get('pbt_margin_pct'))} margin",
            )

        rows = []
        for code in retail_codes:
            b = segments.get(code, {})
            rows.append({
                "Tier":         code,
                "Customers":    b.get("customer_count", 0),
                "Revenue":      _sbu_drilldown_fmt_b(b.get("revenue")),
                "Direct cost":  _sbu_drilldown_fmt_b(b.get("direct_cost")),
                "Indirect":     _sbu_drilldown_fmt_b(b.get("indirect_cost")),
                "PBT":          _sbu_drilldown_fmt_b(b.get("pbt")),
                "Margin":       _fmt_pct(b.get("pbt_margin_pct")),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


    # ════════════════════════════════════════════════════════════════
    # TAB 3 — Commercial (Business segments)
    # ════════════════════════════════════════════════════════════════
    with tab_commercial:
        st.markdown("### Commercial SBU — Chief Commercial Officer")
        st.caption(
            "MSME = Micro + Small + Medium (turnover-banded). "
            "Corporate is standalone. Both apply CBK sectors as a "
            "second dimension. Turnover bands: Micro <20M · Small "
            "20–100M · Medium 100–500M · Corporate ≥500M."
        )

        segments = _sbu_drilldown_seg_rollup(period)
        msme_codes = ["MICRO", "SMALL", "MEDIUM"]
        corp_codes = ["CORPORATE"]

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**MSME**")
            msme_total_pbt = sum(
                segments.get(c, {}).get("pbt", 0) for c in msme_codes
            )
            msme_n = sum(
                segments.get(c, {}).get("customer_count", 0) for c in msme_codes
            )
            st.metric("MSME total PBT", _sbu_drilldown_fmt_b(msme_total_pbt), f"{msme_n} customers")
            rows = []
            for code in msme_codes:
                b = segments.get(code, {})
                rows.append({
                    "Tier":      code,
                    "Customers": b.get("customer_count", 0),
                    "Revenue":   _sbu_drilldown_fmt_b(b.get("revenue")),
                    "PBT":       _sbu_drilldown_fmt_b(b.get("pbt")),
                    "Margin":    _fmt_pct(b.get("pbt_margin_pct")),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        with c2:
            st.markdown("**Corporate**")
            b = segments.get("CORPORATE", {})
            st.metric(
                "Corporate PBT",
                _sbu_drilldown_fmt_b(b.get("pbt")),
                f"{b.get('customer_count', 0)} customers · {_fmt_pct(b.get('pbt_margin_pct'))}",
            )
            st.dataframe(pd.DataFrame([{
                "Customers":    b.get("customer_count", 0),
                "Revenue":      _sbu_drilldown_fmt_b(b.get("revenue")),
                "Direct cost":  _sbu_drilldown_fmt_b(b.get("direct_cost")),
                "Indirect":     _sbu_drilldown_fmt_b(b.get("indirect_cost")),
                "PBT":          _sbu_drilldown_fmt_b(b.get("pbt")),
            }]), use_container_width=True, hide_index=True)


    # ════════════════════════════════════════════════════════════════
    # TAB 4 — CBK Sector heatmap
    # ════════════════════════════════════════════════════════════════
    with tab_sector:
        st.markdown("### CBK Economic Sector view (Business customers)")
        st.caption(
            "14 CBK economic sectors × 4 business tiers. Cells show "
            "PBT (KES Millions). Empty = no customers tagged in that "
            "cell. Sectors per CBK Prudential Guideline classification."
        )
        sectors = _sbu_drilldown_sector_rollup(period)
        if not sectors:
            st.info("No business customers tagged with CBK sectors for this period.")
        else:
            # Build a heatmap-style pivot
            rows = []
            for (seg, sector), b in sectors.items():
                rows.append({
                    "Segment":     seg,
                    "CBK sector":  sector,
                    "Customers":   b["customer_count"],
                    "Revenue (M)": round(b["revenue"]/1e6, 1),
                    "PBT (M)":     round(b["pbt"]/1e6, 1),
                })
            df = pd.DataFrame(rows)
            pivot = df.pivot_table(
                index="CBK sector",
                columns="Segment",
                values="PBT (M)",
                fill_value=0,
            )
            st.dataframe(
                pivot.style.background_gradient(cmap="Greens"),
                use_container_width=True,
            )
            st.markdown("#### Detailed breakdown")
            st.dataframe(
                df.sort_values("PBT (M)", ascending=False),
                use_container_width=True,
                hide_index=True,
            )


    # ════════════════════════════════════════════════════════════════
    # TAB 5 — RM-tagged P&L
    # ════════════════════════════════════════════════════════════════
    with tab_rm:
        st.markdown("### Tagged-RM Profitability")
        st.caption(
            "Each business customer is tagged to a Relationship Manager "
            "by staff_code (not name — per Joshua's spec). The same "
            "staff_code that owns the BSC scorecard owns the revenue "
            "rollup. Individual-customer RM tagging not yet in the "
            "virtual bank dataset (Rule 7 — surfaced honestly)."
        )
        rms = _sbu_drilldown_rm_rollup(period)
        if not rms:
            st.info("No tagged-RM profitability yet for this period.")
        else:
            rows = []
            for code, b in rms.items():
                rows.append({
                    "Staff code":  code,
                    "Customers":   b["customer_count"],
                    "Revenue (M)": round(b["revenue"]/1e6, 1),
                    "PBT (M)":     round(b["pbt"]/1e6, 1),
                    "Margin %":    b.get("pbt_margin_pct"),
                })
            df = pd.DataFrame(rows).sort_values("PBT (M)", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.caption(f"Total RMs with tagged business customers: {len(rms)}")


    # ════════════════════════════════════════════════════════════════
    # TAB 6 — Proposition overlay (VIEW-ONLY)
    # ════════════════════════════════════════════════════════════════
    with tab_prop:
        st.warning(
            "🔍 **View-only overlay.** Per design Q3, propositions "
            "(Women / Diaspora / Asset Finance / Agri / Youth / SME) "
            "are orthogonal tags — a customer can carry multiple. "
            "Proposition P&L **does NOT reconcile to bank total** by "
            "design. Use Retail / Commercial SBU tabs for the audited "
            "primary view."
        )
        props = _sbu_drilldown_prop_rollup(period)
        if not props:
            st.info("No proposition tags found in current customer data.")
        else:
            rows = []
            bank_pbt = _sbu_drilldown_bank_pnl(period)[0]["pbt"]
            for code, b in props.items():
                rows.append({
                    "Proposition": code,
                    "Customers":   b["customer_count"],
                    "Revenue (M)": round(b["revenue"]/1e6, 1),
                    "PBT (M)":     round(b["pbt"]/1e6, 1),
                    "Share of bank PBT %": (
                        round(100 * b["pbt"] / bank_pbt, 1)
                        if bank_pbt else None
                    ),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


    # ════════════════════════════════════════════════════════════════
    # TAB 7 — Balance Sheet
    # ════════════════════════════════════════════════════════════════
    with tab_bs:
        bs_by_seg, bs_bank, ca, bs_metadata = _sbu_drilldown_bs(period)
        st.markdown("### Balance Sheet by Segment")
        c1, c2, c3 = st.columns(3)
        c1.metric("Loan book", _sbu_drilldown_fmt_b(bs_bank["assets_total"]))
        c2.metric("Deposit book", _sbu_drilldown_fmt_b(bs_bank["liabilities_total"]))
        c3.metric("Allocated equity (RWA × 12.5%)", _sbu_drilldown_fmt_b(bs_bank["equity"]))

        rows = []
        for seg, b in bs_by_seg.items():
            rows.append({
                "Segment":         seg,
                "Customers":       b["customer_count"],
                "Loans (B)":       round(b["loan_balance"]/1e9, 3),
                "Deposits (B)":    round(b["deposit_balance"]/1e9, 3),
                "RWA (B)":         round(b["rwa"]/1e9, 3),
                "Equity (B)":      round(b["equity"]/1e9, 3),
                "Net assets (B)":  round(b["net_assets"]/1e9, 3),
            })
        df = pd.DataFrame(rows).sort_values("Loans (B)", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.markdown("#### Capital adequacy")
        st.metric(
            "CAR (Tier 1 + Tier 2)",
            _fmt_pct(ca["ratio_pct"]),
            f"Min: {_fmt_pct(ca['minimum_pct'])} · "
            f"Adequate: {'✓' if ca['adequate'] else '✗'}",
        )

        with st.expander("Balance sheet data sources"):
            st.json(bs_metadata)


    st.divider()
    st.caption(
        "v10.338 — Customer-value SBU drill-down. Backed by canonical "
        "segment classifier + customer_profitability rollup + BCBS "
        "standardised capital allocation. Segment config admin-editable "
        "via the Admin module (Performance section)."
    )


# ════════════════════════════════════════════════════════════════
# OPEX — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/10_opex.py — Operating Leverage & P&L Intelligence.
CIR analysis, SBU profitability, branch P&L, staff productivity, trend analysis.
"""


def render_opex(actor: str) -> None:
    """Render the opex finance view. Body extracted from
    pages/<original>.py."""
    DATA  = Path(__file__).parent.parent / "data"
    today = date.today()

    um, ud, uname, *_ = load_shared_state()[:12]
    role = ud.get("role",""); name = ud.get("full_name","")
    is_admin = ud.get("is_admin",False)
    is_exec  = any(x in role for x in ("Chief","Director","Managing","Head","CFO","Finance","Controller"))

    st.markdown(
        "<div style='padding:16px 0 4px'>"
        "<span style='font-size:22px;font-weight:800'>📉 Operating Leverage</span>"
        "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
        "CIR · SBU P&L · Branch profitability · Staff productivity</span></div>",
        unsafe_allow_html=True)

    @st.cache_data(ttl=60, show_spinner=False)
    def _opex_load():
        p = DATA / "opex_data.json"
        return a2z_db.load_json(p) if p.exists() else {}

    opex = _opex_load()
    if not opex:
        st.info("Operating leverage data not available. Run data refresh from Admin."); st.stop()

    bank  = opex.get("bank",{})
    sbus  = opex.get("by_sbu",{})
    brs   = opex.get("branches",[])

    # ── Key metrics banner ───────────────────────────────────────────────
    cir     = bank.get("cir_pct",0)
    cir_tgt = bank.get("target_cir_pct",55)
    cir_clr = "#16A34A" if cir<=cir_tgt else "#DC2626"

    st.markdown(
        f"<div style='background:{cir_clr}10;border:1.5px solid {cir_clr}40;border-radius:10px;"
        f"padding:10px 18px;margin-bottom:10px;display:flex;gap:24px;flex-wrap:wrap'>"
        f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Cost-to-Income Ratio</div>"
        f"<div style='font-size:26px;font-weight:800;color:{cir_clr}'>{cir:.1f}%</div>"
        f"<div style='font-size:11px;color:{cir_clr}'>Target: {cir_tgt}%</div></div>"
        f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary)'>Total Income</div>"
        f"<div style='font-size:20px;font-weight:700'>KES {bank.get('total_income_kes_b',0):.1f}B</div></div>"
        f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary)'>Total OpEx</div>"
        f"<div style='font-size:20px;font-weight:700'>KES {bank.get('total_opex_kes_b',0):.1f}B</div></div>"
        f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary)'>PBT</div>"
        f"<div style='font-size:20px;font-weight:700'>KES {bank.get('pbt_kes_b',0):.1f}B</div></div>"
        f"<div style='border-left:1px solid var(--color-border);padding-left:20px'>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary)'>ROE</div>"
        f"<div style='font-size:20px;font-weight:700'>{bank.get('roe_pct',0):.1f}%</div></div>"
        f"</div>", unsafe_allow_html=True)

    tabs = st.tabs(["🏛️ Bank Summary","📊 SBU P&L","🏢 Branch P&L","👥 Staff Productivity","📐 OpEx Breakdown","🤖 Arc Engines"])

    # ── TAB 1: Bank Summary ─────────────────────────────────────────────
    with tabs[0]:
        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Interest Income",   f"KES {bank.get('interest_income_kes_b',0):.1f}B")
        c2.metric("Non-interest Income",f"KES {bank.get('non_interest_income_b',0):.1f}B")
        c3.metric("Staff Costs",       f"KES {bank.get('staff_costs_kes_b',0):.1f}B",
                  f"{bank.get('staff_costs_kes_b',0)/max(bank.get('total_opex_kes_b',1),0.01)*100:.0f}% of opex")
        c4.metric("IT Costs",          f"KES {bank.get('it_costs_kes_b',0):.1f}B")
        c5.metric("PAT",               f"KES {bank.get('pat_kes_b',0):.1f}B",
                  f"ROA {bank.get('roa_pct',0):.1f}%")

        st.markdown("---")
        st.markdown("**CIR target tracking:**")
        _gap = cir - cir_tgt
        st.markdown(
            f"Current CIR **{cir:.1f}%** vs target **{cir_tgt:.1f}%** — "
            f"{'🔴 Above target by ' + str(round(_gap,1)) + 'pp' if _gap>0 else '✅ Below target by ' + str(round(-_gap,1)) + 'pp'}. "
            f"To hit {cir_tgt}% target, need to reduce opex by "
            f"KES {max(0,(cir-cir_tgt)/100*bank.get('total_income_kes_b',13))*1e9/1e9:.2f}B "
            f"or grow income by KES {max(0,bank.get('total_opex_kes_b',8)/((cir_tgt/100))-bank.get('total_income_kes_b',13))*1e9/1e9:.2f}B.")

    # ── TAB 2: SBU P&L ─────────────────────────────────────────────────
    with tabs[1]:
        st.markdown("**P&L by Strategic Business Unit:**")
        sbu_rows = [{"SBU":sbu,"Income (B)":v.get("income_b", 0),"OpEx (B)":v.get("opex_b", 0),
                      "CIR%":v.get("cir", 0),"PBT (B)":v.get("pbt_b", 0),"Loans (B)":v.get("loans_b",0),
                      "Deposits (B)":v.get("deposits_b",0),"Staff":v.get("staff",0)}
                     for sbu,v in sbus.items()]
        df_sbu = pd.DataFrame(sbu_rows)
        st.dataframe(df_sbu, use_container_width=True, hide_index=True)

        # Highlight inefficient SBUs
        for sbu, v in sbus.items():
            if v.get("cir", 0) > 80:
                st.warning(f"⚠️ **{sbu}**: CIR {v['cir']:.0f}% — above 80% threshold. Review cost structure.")
            elif v.get("pbt_b",0) < 0:
                st.error(f"🔴 **{sbu}**: Loss-making (PBT KES {v['pbt_b']:.1f}B). Action required.")

        st.markdown("**SBU income vs opex:**")
        st.bar_chart(pd.DataFrame({"Income":df_sbu["Income (B)"].values,
                                    "OpEx":  df_sbu["OpEx (B)"].values},
                                   index=df_sbu["SBU"].values))

    # ── TAB 3: Branch P&L ──────────────────────────────────────────────
    with tabs[2]:
        st.markdown("**Branch profitability ranking:**")
        f1,f2 = st.columns(2)
        sort_by = f1.selectbox("Sort by", ["profit_m","cir_pct","income_m","deposits_m"], key="op_sort")
        top_n   = f2.slider("Show top N branches", 10, len(brs), min(25,len(brs)), key="op_n")

        br_rows = [{"Branch":b["branch"][:25],"Income (M)":b["income_m"],"OpEx (M)":b["opex_m"],
                     "Profit (M)":b["profit_m"],"CIR%":b["cir_pct"],
                     "Loans (M)":b["loans_m"],"Deposits (M)":b["deposits_m"],
                     "Staff":b["staff"],"Income/Staff (KES K)":b.get("income_per_staff",0)}
                    for b in sorted(brs, key=lambda x:-x.get(sort_by,0))[:top_n]]
        st.dataframe(pd.DataFrame(br_rows), use_container_width=True, hide_index=True)

        # Loss-making branches
        loss_branches = [b for b in brs if b.get("profit_m",0) < 0]
        if loss_branches:
            st.error(f"🔴 {len(loss_branches)} loss-making branch(es): {[b['branch'][:15] for b in loss_branches[:5]]}")

        # CIR distribution
        cir_gt80 = sum(1 for b in brs if b.get("cir_pct",0)>80)
        if cir_gt80:
            st.warning(f"⚠️ {cir_gt80} branches with CIR >80%")

    # ── TAB 4: Staff Productivity ───────────────────────────────────────
    with tabs[3]:
        st.markdown("**Staff productivity analysis:**")
        total_staff = sum(b["staff"] for b in brs)
        total_inc   = sum(b["income_m"] for b in brs)
        avg_prod    = total_inc*1e6/max(total_staff,1)/1e3

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Total Branch Staff", f"{total_staff:,}")
        c2.metric("Avg Income/Staff",   f"KES {avg_prod:.0f}K")
        c3.metric("Target Income/Staff",f"KES 400K")
        c4.metric("Gap",                f"KES {400-avg_prod:.0f}K",
                  delta_color="normal" if avg_prod>=400 else "inverse")

        # Top 10 by productivity
        prod_rows = sorted([{"Branch":b["branch"][:25],
                              "Staff":b["staff"],"Income (M)":b["income_m"],
                              "Income/Staff (KES K)":b.get("income_per_staff",0)}
                             for b in brs], key=lambda x:-x["Income/Staff (KES K)"])[:10]
        st.markdown("**Top 10 branches by staff productivity:**")
        st.dataframe(pd.DataFrame(prod_rows), use_container_width=True, hide_index=True)

    # ── TAB 5: OpEx Breakdown ───────────────────────────────────────────
    with tabs[4]:
        st.markdown("**Bank-level operating cost breakdown:**")
        opex_items = {
            "Staff Costs":     bank.get("staff_costs_kes_b",3.2),
            "IT & Technology": bank.get("it_costs_kes_b",0.8),
            "Premises":        bank.get("premises_kes_b",0.6),
            "Other OpEx":      bank.get("other_opex_kes_b",3.3),
        }
        df_opex = pd.DataFrame([{"Category":k,"KES B":v,"% of total":round(v/max(bank.get('total_opex_kes_b',8),0.01)*100,1)}
                                  for k,v in opex_items.items()])
        st.dataframe(df_opex, use_container_width=True, hide_index=True)
        st.bar_chart(pd.DataFrame({"KES B":list(opex_items.values())}, index=list(opex_items.keys())))

        st.markdown("**Cost reduction opportunities:**")
        opp = []
        if bank.get("cir_pct",0) > 55: opp.append(f"• CIR at {bank['cir_pct']:.1f}% — target 55%: need KES {(bank['cir_pct']-55)/100*bank.get('total_income_kes_b',13):.2f}B cost reduction")
        if bank.get("it_costs_kes_b",0)/bank.get("total_opex_kes_b",8) < 0.12: opp.append("• IT spend below 12% of opex — may need digital investment to reduce manual costs")
        for o in opp: st.markdown(o)


    # ──────────────────────────────────────────────────────────────────────
    # Section 5: 🤖 Arc Engines (absorbed from
    # 29_resource_optimization_cockpit.py in v10.207 per the architectural
    # reorganization sub-campaign. 10 Resource Optimization engines
    # (ENH-156..165) presented as 7 nested sub-tabs spanning workforce
    # planning: Executive, Work Mode, Forecast+TSL, Balancing+Util,
    # Wellbeing, What-If+Invest, Culture. Read-only display except for
    # state-mutating workflows that go through utils/api_resource_optimization.py
    # FastAPI endpoints. Mirrors v10.202..v10.206 absorption patterns.
    # ──────────────────────────────────────────────────────────────────────
    with tabs[5]:
        from datetime import datetime as _dt_ro, timezone as _tz_ro

        try:
            from utils.work_mode_declaration import WorkModeDeclarationEngine
            from utils.workload_forecasting import WorkloadForecastingEngine
            from utils.tsl_optimization import TSLOptimizationEngine
            from utils.cross_channel_balancing import CrossChannelBalancingEngine
            from utils.utilization_dashboard import UtilizationDashboardEngine
            from utils.wellbeing_integration import WellbeingIntegrationEngine
            from utils.hybrid_scheduling_simulator import HybridSchedulingSimulator
            from utils.resource_investment_case import (
                ResourceInvestmentCaseEngine)
            from utils.integrity_culture import IntegrityCultureEngine
            from utils.executive_resource_dashboard import (
                ExecutiveResourceDashboard)
            _ARC_RO_AVAILABLE = True
        except ImportError as _ie:
            st.error(f"Resource Optimization arc engines unavailable: {_ie}")
            _ARC_RO_AVAILABLE = False

        if _ARC_RO_AVAILABLE:
            st.caption(
                "v10.207 absorbed from 29_resource_optimization_cockpit.py — "
                "10 engines (ENH-156..165) spanning workforce planning: work "
                "mode declaration, workload forecasting, TSL optimization, "
                "cross-channel balancing, utilization dashboard, wellbeing "
                "integration, hybrid scheduling simulator, resource "
                "investment case, integrity culture, and executive dashboard "
                "rollup. All engines read-only here; state-mutating workflows "
                "go through the FastAPI POST endpoints in "
                "utils/api_resource_optimization.py.")

            # Engines have constructor dependencies — match cockpit's wiring
            @st.cache_resource
            def _get_arc_ro_engines():
                work_mode = WorkModeDeclarationEngine()
                forecast = WorkloadForecastingEngine()
                tsl = TSLOptimizationEngine()
                balance = CrossChannelBalancingEngine(tsl_engine=tsl)
                util = UtilizationDashboardEngine()
                wellbeing = WellbeingIntegrationEngine(
                    wellness_assessor=lambda staff: {},
                    utilization_engine=util,
                )
                hybrid = HybridSchedulingSimulator(
                    tsl_engine=tsl, utilization_engine=util,
                    balancing_engine=balance,
                )
                invest = ResourceInvestmentCaseEngine()
                culture = IntegrityCultureEngine()
                executive = ExecutiveResourceDashboard(
                    work_mode_engine=work_mode,
                    workload_forecasting_engine=forecast,
                    tsl_engine=tsl,
                    balancing_engine=balance,
                    utilization_engine=util,
                    wellbeing_engine=wellbeing,
                    hybrid_simulator=hybrid,
                    investment_case_engine=invest,
                    integrity_culture_engine=culture,
                )
                return {
                    "work_mode": work_mode, "forecast": forecast,
                    "tsl": tsl, "balance": balance, "util": util,
                    "wellbeing": wellbeing, "hybrid": hybrid,
                    "invest": invest, "culture": culture,
                    "executive": executive,
                }

            # Cockpit's render functions take an `engines` dict; preserve their
            # signature and call from arc_tabs[N]. Functions are defined inside
            # this block to keep them encapsulated within the Arc Engines tab.
            def _ro_render_summary(summary, *, exclude=()):
                try:
                    from utils.page_cockpit_render import render_summary as _rs
                    _rs(summary, exclude=exclude)
                except ImportError:
                    st.json(summary if summary else {})


            def render_executive_tab(engines):
                """Tab 1 — Executive Dashboard capstone (ENH-165)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("📊 Executive Resource Optimization Dashboard")
                snap = engines["executive"].snapshot(
                    snapshot_id=f"cockpit_{datetime.now(timezone.utc).isoformat()}"
                )
                composite = snap.resource_optimization_health_index
                cols = st.columns(3)
                cols[0].metric("Composite Health Index",
                               f"{composite:.1f}" if composite else "n/a")
                cols[1].metric("Engines Attached", snap.n_engines_attached)
                cols[2].metric("Engines Available", snap.n_engines_available)

                st.markdown("##### Sub-index components")
                if snap.health_index_components:
                    comp = snap.health_index_components
                    if isinstance(comp, dict) and comp:
                        for i in range(0, len(comp), 4):
                            row = list(comp.items())[i:i + 4]
                            cs = st.columns(len(row))
                            for c, (k, v) in zip(cs, row):
                                label = k.replace("_", " ").title()
                                val = f"{v:.1f}" if isinstance(v, (int, float)) else str(v)
                                c.metric(label, val)
                    else:
                        st.info("No sub-index components available.")
                else:
                    st.info("Insufficient signal coverage — composite "
                            "index requires ≥2 sub-indices.")

                st.markdown("##### Sections")
                for section in snap.sections:
                    marker = "✅ available" if section.available else "⚠️ unavailable"
                    with st.expander(f"{section.title} — {marker}"):
                        st.caption(section.notes)
                        if section.payload:
                            _ro_render_summary(section.payload)



            def render_work_mode_tab(engines):
                """Tab 2 — Work Mode Declarations (ENH-156)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("🏠 Work Mode Declarations")
                _ro_render_summary(engines["work_mode"].board_summary())



            def render_forecast_tsl_tab(engines):
                """Tab 3 — Forecasting + TSL (ENH-157, ENH-158)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("📈 Workload Forecasting & Service-Level "
                             "Optimization")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Forecasting (ENH-157)**")
                    _ro_render_summary(engines["forecast"].board_summary())
                with col2:
                    st.markdown("**TSL Optimization (ENH-158)**")
                    _ro_render_summary(engines["tsl"].board_summary())



            def render_balancing_util_tab(engines):
                """Tab 4 — Balancing + Utilisation (ENH-159, ENH-160)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("⚖️ Cross-Channel Balancing & Utilization "
                             "Dashboard")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Cross-Channel Balancing (ENH-159)**")
                    _ro_render_summary(engines["balance"].board_summary())
                with col2:
                    st.markdown("**Utilization (ENH-160)**")
                    _ro_render_summary(engines["util"].board_summary())



            def render_wellbeing_tab(engines):
                """Tab 5 — Wellbeing Integration (ENH-161)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("💚 Wellbeing Early-Warning Integration")
                st.caption(
                    "Privacy posture: n_respondents < 5 → suppressed; no "
                    "individual names ever appear in team outputs; opt-out "
                    "respected and counted as absent. No clinical claims.")
                _ro_render_summary(engines["wellbeing"].board_summary())



            def render_whatif_invest_tab(engines):
                """Tab 6 — What-If + Investment Case (ENH-162, ENH-163)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("🧪 What-If Scenarios & Investment Case "
                             "Generator")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Hybrid Scheduling Simulator (ENH-162)**")
                    _ro_render_summary(engines["hybrid"].board_summary())
                with col2:
                    st.markdown("**Investment Case Generator (ENH-163)**")
                    _ro_render_summary(engines["invest"].board_summary())



            def render_culture_tab(engines):
                """Tab 7 — Integrity Culture (ENH-164)."""
                if not STREAMLIT_AVAILABLE:
                    return
                st.subheader("🌱 Integrity Culture Score & Benchmarking")
                st.caption(
                    "Operator-supplied indicators only — no NLP on emails/"
                    "chat, no behavioural telemetry, no automated surveys.")
                _ro_render_summary(engines["culture"].board_summary())




            engines = _get_arc_ro_engines()

            arc_tabs = st.tabs([
                "📊 Executive",
                "🏠 Work Mode",
                "📈 Forecast+TSL",
                "⚖️ Balancing+Util",
                "💚 Wellbeing",
                "🧪 What-If+Invest",
                "🌱 Culture",
            ])

            with arc_tabs[0]:
                render_executive_tab(engines)
            with arc_tabs[1]:
                render_work_mode_tab(engines)
            with arc_tabs[2]:
                render_forecast_tsl_tab(engines)
            with arc_tabs[3]:
                render_balancing_util_tab(engines)
            with arc_tabs[4]:
                render_wellbeing_tab(engines)
            with arc_tabs[5]:
                render_whatif_invest_tab(engines)
            with arc_tabs[6]:
                render_culture_tab(engines)

            # Footer audit log
            try:
                audit_log(
                    action="resource_optimization_arc_engines.view",
                    username=ud.get("username", "anonymous"),
                    detail=f"viewed_at={_dt_ro.now(_tz_ro.utc).isoformat()}",
                    module="resource_optimization")
            except Exception:
                pass


# ════════════════════════════════════════════════════════════════
# MGMT_ACCOUNTS — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/52_mgmt_accounts.py — Management Accounts Pack.
Monthly P&L, balance sheet, key ratios. Thresholds via org_config.
"""


def render_mgmt_accounts(actor: str) -> None:
    """Render the mgmt_accounts finance view. Body extracted from
    pages/<original>.py."""
    DATA  = Path(__file__).parent.parent / "data"
    today = date.today()
    um, ud, uname, *_ = load_shared_state()[:12]
    role     = str(ud.get("role","")).lower()
    is_admin = ud.get("is_admin",False)
    is_fin   = any(x in role for x in ("financial","cfo","finance","controller","chief financial"))

    st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>📑 Management Accounts</span>"
                "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
                "Monthly P&L · Balance Sheet · Key Ratios · Trend</span></div>", unsafe_allow_html=True)

    @st.cache_data(ttl=60)
    def _mgmt_accounts_load():
        p = DATA/"mgmt_accounts.json"
        return a2z_db.load_json(p) if p.exists() else {}

    data = _mgmt_accounts_load()
    if not data: st.info("Management accounts not available."); st.stop()

    period = data.get("period","")
    ratios = data.get("key_ratios",{})
    inc    = data.get("income_statement",{})
    bs     = data.get("balance_sheet",{})
    cir_tgt= cfg("cir_target_pct", 55)

    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("NIM",f"{ratios.get('nim_pct',0):.2f}%")
    m2.metric("CIR",f"{ratios.get('cir_pct',0):.1f}%",f"Target {cir_tgt}%",
              delta_color="normal" if ratios.get("cir_pct",99)<=cir_tgt else "inverse")
    m3.metric("ROA",f"{ratios.get('roa_pct',0):.2f}%")
    m4.metric("ROE",f"{ratios.get('roe_pct',0):.1f}%")
    m5.metric("CAR",f"{ratios.get('car_pct',0):.1f}%")
    m6.metric("NPL",f"{ratios.get('npl_pct',0):.1f}%",
              delta_color="normal" if ratios.get("npl_pct",0)<=6 else "inverse")

    tabs = st.tabs(["📊 P&L","🏦 Balance Sheet","📈 Trend","📐 Ratios","♻️ OCI Recycling","📥 Export","🤖 Arc Engines"])

    with tabs[0]:
        st.markdown(f"**Income Statement — {period}** ({currency()} M)")
        PNL = [("Interest Income","interest_income"),("Interest Expense","interest_expense"),
               ("Net Interest Income","net_interest_income"),("Fee Income","fee_income"),
               ("Forex Income","forex_income"),("Total Income","total_income"),
               ("Operating Expenses","opex"),("Provisions","provisions"),("PBT","pbt")]
        rows=[]
        for label,key in PNL:
            d=inc.get(key,{})
            a,b,p=d.get("actual_m",0),d.get("budget_m",0),d.get("prior_m",0)
            rows.append({"Line item":label,"Actual (M)":a,"Budget (M)":b,"Prior (M)":p,
                         "Variance":round(a-b,1),"Var%":f"{(a-b)/max(abs(b),1)*100:+.1f}%"})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    with tabs[1]:
        st.markdown(f"**Balance Sheet — {period}** ({currency()} B)")
        BS=[("Net Loans","loans_net_b"),("Investments","investments_b"),("Cash","cash_b"),
            ("Total Assets","total_assets_b"),("Customer Deposits","customer_deposits_b"),
            ("Borrowings","borrowings_b"),("Equity","equity_b")]
        bs_rows=[{"Item":l,"Current (B)":bs.get(k,{}).get("actual",0),
                  "Prior (B)":bs.get(k,{}).get("prior",0),
                  "Change":round(bs.get(k,{}).get("actual",0)-bs.get(k,{}).get("prior",0),2)}
                 for l,k in BS]
        st.dataframe(pd.DataFrame(bs_rows),use_container_width=True,hide_index=True)

    with tabs[2]:
        trend=data.get("monthly_trend",[])
        if trend:
            st.line_chart(pd.DataFrame({"NII":[t["nii_m"] for t in trend],
                                         "PBT":[t["pbt_m"] for t in trend]},
                                        index=[t["month"] for t in trend]))
            st.line_chart(pd.DataFrame({"CIR%":[round(t["cir"],1) for t in trend]},
                                        index=[t["month"] for t in trend]))

    with tabs[3]:
        st.dataframe(pd.DataFrame([{"Ratio":k.replace("_pct"," (%)").replace("_"," ").title(),
                                     "Value":f"{v:.2f}"}
                                    for k,v in ratios.items()]),
                     use_container_width=True,hide_index=True)

    with tabs[4]:
        # ── IAS 1 OCI Recycling Map (Standard #111, integrated v5.73) ─────
        from utils.ias1_presentation import (
            IAS1PresentationEngine, OCI_RECYCLING_MAP, OCI_LINE_ITEMS,
            MATERIALITY_PCT_OF_EQUITY,
        )
        from decimal import Decimal as _D

        st.markdown("**IAS 1 / IFRS 9 OCI Recycling Map**")
        st.caption(
            "Whether each OCI line item recycles to P&L on derecognition (per IAS 1 + IFRS 9 + IAS 16 + IAS 19R). "
            "**This is the most error-prone area in IFRS reporting** — banks routinely "
            "treat equity FVTOCI as recyclable (it is NOT, per IFRS 9) or treat "
            "DB remeasurement as recyclable (it is NOT, per IAS 19R post-2013)."
        )

        # Render the recycling map deterministically
        recycling_rows = []
        for line_item in OCI_LINE_ITEMS:
            r = IAS1PresentationEngine.oci_classification(line_item)
            recycling_rows.append({
                "OCI line item": line_item.replace("_", " ").title(),
                "Classification": r.get("classification", "—"),
                "Recyclable to P&L?": "✅ Yes" if r.get("recyclable") else "❌ Never",
                "Standard ref": {
                    "REVALUATION_SURPLUS": "IAS 16 (revaluation model)",
                    "FVTOCI_DEBT_FAIR_VALUE_CHANGES": "IFRS 9 (debt FVTOCI)",
                    "FVTOCI_EQUITY_FAIR_VALUE_CHANGES": "IFRS 9 (equity FVTOCI — NEVER recycles)",
                    "CASH_FLOW_HEDGE_RESERVE": "IFRS 9 (hedge accounting)",
                    "DEFINED_BENEFIT_REMEASUREMENT": "IAS 19R (post-2013, no corridor)",
                }.get(line_item, ""),
            })
        st.dataframe(pd.DataFrame(recycling_rows),
                     use_container_width=True, hide_index=True)

        audit_log("IFRS_ENGINE_USED", uname,
                   f"IAS1 #111: OCI recycling map viewed on mgmt_accounts page")

        # Materiality probe — let user check if a P&L item is material
        st.markdown("---")
        st.markdown("**Materiality Test** (IAS 1.7 — 5% of equity / 5% of revenue / 1% of total assets)")
        eq = bs.get("equity_b", {}).get("actual", 0) or 0
        rev = inc.get("total_income", {}).get("actual_m", 0) or 0
        ta  = bs.get("total_assets_b", {}).get("actual", 0) or 0

        c1, c2, c3 = st.columns(3)
        with c1:
            item_amt = st.number_input(f"Item amount ({currency()} M)",
                                         min_value=0.0, value=5.0, step=1.0,
                                         key="ma_mat_item")
        with c2:
            basis = st.selectbox("Basis", ["EQUITY", "REVENUE", "TOTAL_ASSETS"],
                                  key="ma_mat_basis")
        with c3:
            # Pre-fill with extracted balance-sheet/P&L value (in M)
            default_basis_amt = {"EQUITY": float(eq) * 1000.0,    # B → M
                                  "REVENUE": float(rev),
                                  "TOTAL_ASSETS": float(ta) * 1000.0}.get(basis, 0.0)
            basis_amt = st.number_input(f"Basis amount ({currency()} M)",
                                          min_value=0.0,
                                          value=max(default_basis_amt, 1.0),
                                          step=10.0, key="ma_mat_basis_amt")

        if st.button("Test materiality", key="ma_mat_btn", type="primary"):
            r = IAS1PresentationEngine.materiality_test(
                _D(str(item_amt)), basis, _D(str(basis_amt)))
            if r.get("computed"):
                material = r.get("material")
                color = "#DC2626" if material else "#10B981"
                verdict = "❌ MATERIAL — must be disclosed" if material else "✅ NOT MATERIAL"
                st.markdown(
                    f"<div style='padding:12px;background:{color}22;"
                    f"border-left:4px solid {color};border-radius:8px'>"
                    f"<div style='font-size:16px;font-weight:700;color:{color}'>{verdict}</div>"
                    f"<div style='font-size:13px;margin-top:6px'>"
                    f"Item is <b>{r.get('pct_of_base')}%</b> of {basis.lower()} "
                    f"(threshold: {r.get('threshold_pct')}%).</div></div>",
                    unsafe_allow_html=True)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS1 #111: Materiality {item_amt}M vs {basis_amt}M {basis} → material={material}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

    with tabs[5]:
        if is_fin or is_admin:
            import io
            rows2=[{"Line":l,"Actual_M":inc.get(k,{}).get("actual_m",0),
                    "Budget_M":inc.get(k,{}).get("budget_m",0)}
                   for l,k in PNL]
            buf=io.BytesIO()
            pd.DataFrame(rows2).to_excel(buf,index=False,engine="openpyxl"); buf.seek(0)
            st.download_button("📥 Download P&L",data=buf.getvalue(),
                               file_name=f"MgmtAccounts_{period}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="ma_dl")
        else: st.info("Export available to Finance team.")


    # ──────────────────────────────────────────────────────────────────────
    # Section 6: 🤖 Arc Engines (absorbed from 96_finance_arc_cockpit.py
    # in v10.211 per the architectural reorganization sub-campaign.
    # 10 Finance engines presented as nested sub-tabs spanning month-end
    # close orchestration, intercompany matching, consolidated TB, regulator
    # regulatory reporting, predictive financial analytics, intelligence
    # dashboard, statement generation, tax-authority compliance, multi-entity FX,
    # and audit & compliance. All engines diagnostic.
    # This page is in the finance department alongside 9_sbu.py and
    # 29_revenue_assurance.py (reassigned in v10.210). The Finance section
    # of the sidebar now provides a substantive CFO command surface.
    # Note: 52_mgmt_accounts.py is now at G4 7-tab ceiling (6 → 7).
    # Mirrors v10.202..v10.210 absorption patterns.
    # ──────────────────────────────────────────────────────────────────────
    with tabs[6]:
        from datetime import datetime as _dt_fa, timezone as _tz_fa

        try:
            from utils.finance_close_orchestrator import (
                FinanceCloseOrchestrator)
            from utils.intercompany_matching import (
                IntercompanyMatchingEngine)
            from utils.consolidated_tb_engine import (
                ConsolidatedTrialBalanceEngine)
            from utils.cbk_regulatory_reporting import (
                CBKRegulatoryReportingEngine)
            from utils.predictive_financial_analytics import (
                PredictiveFinancialAnalyticsEngine)
            from utils.finance_intelligence_dashboard import (
                FinanceIntelligenceDashboardEngine)
            from utils.financial_statement_generator import (
                FinancialStatementGenerator)
            from utils.kra_tax_compliance import KRATaxComplianceEngine
            from utils.multi_entity_currency import MultiEntityCurrencyEngine
            from utils.finance_audit_compliance import (
                FinanceAuditComplianceEngine)
            _ARC_FA_AVAILABLE = True
        except ImportError as _ie:
            st.error(f"Finance arc engines unavailable: {_ie}")
            _ARC_FA_AVAILABLE = False

        if _ARC_FA_AVAILABLE:
            st.caption(
                "v10.211 absorbed from 96_finance_arc_cockpit.py — 10 engines "
                "spanning month-end close orchestration, intercompany matching, "
                "consolidated TB, regulator reporting, predictive financial "
                "analytics, intelligence dashboard, statement generation, tax-authority "
                "tax compliance, multi-entity FX, and audit & compliance.")

            arc_tabs = st.tabs([
                "📋 Close + 🔗 IC",
                "🌐 Consolidation + 💱 Multi-Curr",
                f"🏛️ {regulator()} Reporting",
                "📈 Predictive + 📊 CFO",
                "📑 Statements + 💼 Tax",
                "🔒 Audit & Compliance",
                "ℹ️ About",
            ])

            with arc_tabs[0]:
                st.subheader("Close Orchestration (ENH-249)")
                st.caption(
                    "5 capabilities: missing recurring accruals + prepayment "
                    "amortization + IC pending + suspense balance + cutoff "
                    "timing")
                if st.button("Run close orchestration demo", key="fco_run"):
                    eng = FinanceCloseOrchestrator()
                    gl_entries = (
                        GLEntry(
                            entry_id="ge1", entity_id="P",
                            account_code="9999",
                            account_type=AccountType.ASSET,
                            debit_kes=Decimal("75000"),
                            credit_kes=Decimal("0"),
                            period="2026-04",
                            posting_date="2026-04-15",
                            description="suspense"),
                    )
                    report = eng.generate_close_report(
                        period="2026-04",
                        target_close_days=3,
                        gl_entries=gl_entries,
                        accrual_schedules=(),
                        prepayment_schedules=(),
                        ic_entries=(),
                        cutoff_date="2026-05-05")
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "finance_close_orchestrator",
                         "tasks": len(report.tasks)})
                    st.success(
                        f"Close orchestration complete — {len(report.tasks)} "
                        f"tasks ({report.target_close_days}-day target)")
                    with st.expander("Tasks (Rule 1 — full provenance)",
                                     expanded=True):
                        for t in report.tasks:
                            st.write(
                                f"**{t.severity.value}** · {t.task_type.value} "
                                f"— {t.description}")

                st.divider()
                st.subheader("Intercompany Matching (ENH-250)")
                st.caption(
                    "Mirror-pair IC entries across entities; 4 MatchStatus × "
                    "5 EliminationType + multi-leg chain detection")
                if st.button("Run IC matching demo", key="icm_run"):
                    eng = IntercompanyMatchingEngine()
                    a = IcEntry(
                        entry_id="a", entity_id="PARENT",
                        counterparty_entity_id="SUBA",
                        account_code="IC-1500",
                        debit_kes=Decimal("100000"),
                        credit_kes=Decimal("0"),
                        period="2026-04", reference="IC-INV-001",
                        elimination_type=EliminationType.RECEIVABLE_PAYABLE)
                    b = IcEntry(
                        entry_id="b", entity_id="SUBA",
                        counterparty_entity_id="PARENT",
                        account_code="IC-2500",
                        debit_kes=Decimal("0"),
                        credit_kes=Decimal("100000"),
                        period="2026-04", reference="IC-INV-001",
                        elimination_type=EliminationType.RECEIVABLE_PAYABLE)
                    report = eng.match_all((a, b), "2026-04")
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "intercompany_matching",
                         "matches": len(report.matches)})
                    st.success(
                        f"IC matching complete — {len(report.matches)} "
                        f"matches; "
                        f"{report.total_eliminations_recommended} "
                        f"eliminations recommended")
                    with st.expander("Matches"):
                        for m in report.matches:
                            st.write(
                                f"**{m.status.value}** · {m.severity.value} "
                                f"— {m.description}")

            with arc_tabs[1]:
                st.subheader("Group Consolidation TB (ENH-251)")
                st.caption(
                    "4-step pipeline: aggregate → eliminate → NCI → IAS 21 "
                    "FX (CLOSING for B/S, AVERAGE for P&L)")
                if st.button("Run consolidation demo", key="gcs_run"):
                    eng = ConsolidatedTrialBalanceEngine()
                    p = EntityProfile(
                        entity_id="PARENT", entity_name="Parent",
                        parent_ownership_pct=Decimal("1"),
                        functional_currency=currency(), is_parent=True)
                    s = EntityProfile(
                        entity_id="SUBA", entity_name="Sub A 80%",
                        parent_ownership_pct=Decimal("0.80"),
                        functional_currency=currency())
                    tb = (
                        TrialBalanceLine(
                            entity_id="PARENT", account_code="3000",
                            account_type=AccountType.EQUITY,
                            debit_kes=Decimal("0"),
                            credit_kes=Decimal("5000000"),
                            period="2026-04"),
                        TrialBalanceLine(
                            entity_id="SUBA", account_code="3000",
                            account_type=AccountType.EQUITY,
                            debit_kes=Decimal("0"),
                            credit_kes=Decimal("1000000"),
                            period="2026-04"),
                    )
                    result = eng.consolidate("2026-04", (p, s), tb)
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "consolidated_tb_engine",
                         "lines": len(result.lines)})
                    st.success(
                        f"Consolidation complete — "
                        f"{len(result.lines)} lines, "
                        f"{result.entities_consolidated} entities")
                    with st.expander("Lines"):
                        for line in result.lines:
                            st.write(
                                f"**{line.account_code}** "
                                f"({line.account_type.value}) — "
                                f"NCI Cr {line.nci_share_cr}, "
                                f"Parent Cr {line.parent_share_cr}")

                st.divider()
                st.subheader("Multi-Currency Accounting (ENH-257)")
                st.caption(
                    "Transaction-level multi-currency journal validation + "
                    "IAS 21 §23 FX revaluation + inter-entity transfer")
                if st.button("Run multi-currency demo", key="mec_run"):
                    eng = MultiEntityCurrencyEngine()
                    # USD journal
                    lines = (
                        JournalLine(
                            line_id="l1", entity_id="P",
                            account_code="1500",
                            debit_txn_currency=Decimal("10000"),
                            credit_txn_currency=Decimal("0"),
                            transaction_currency="USD"),
                        JournalLine(
                            line_id="l2", entity_id="P",
                            account_code="2500",
                            debit_txn_currency=Decimal("0"),
                            credit_txn_currency=Decimal("10000"),
                            transaction_currency="USD"),
                    )
                    rates = (
                        FxSpotRate(
                            transaction_currency="USD",
                            functional_currency=currency(),
                            rate=Decimal("130"),
                            rate_date="2026-04-15"),
                    )
                    v = eng.validate_multi_currency_journal(
                        "J-USD-001", lines, "2026-04-15", rates=rates)
                    # Revaluation
                    bal = MonetaryBalance(
                        balance_id="USD-RCV",
                        entity_id="P", account_code="1500",
                        currency="USD",
                        txn_currency_balance=Decimal("100000"),
                        historical_functional_balance=Decimal("12500000"))
                    closing = (
                        FxSpotRate(
                            transaction_currency="USD",
                            functional_currency=currency(),
                            rate=Decimal("130"),
                            rate_date="2026-04-30"),
                    )
                    rev = eng.revalue_monetary_balances(
                        "2026-04-30", (bal,), closing)
                    # Inter-entity
                    rec = eng.recommend_inter_entity_transfer(
                        InterEntityTransferRequest(
                            request_id="REQ-1",
                            from_entity="PARENT", to_entity="SUBA",
                            amount_kes=Decimal("10000000"),
                            purpose="working_capital_loan"))
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "multi_entity_currency",
                         "valid": v.is_valid,
                         "reval_findings": len(rev),
                         "transfer_amount": str(rec.amount_kes)})
                    st.success("Multi-currency demos complete")
                    st.write(
                        f"**Journal validation:** valid={v.is_valid}, "
                        f"functional Dr={v.functional_dr}, "
                        f"rate={v.fx_rate_used}")
                    st.write(
                        f"**Revaluation:** {len(rev)} finding(s); "
                        f"first severity={rev[0].severity.value if rev else 'n/a'}")
                    st.write(
                        f"**Inter-entity transfer:** "
                        f"{rec.debit_leg_entity}→{rec.credit_leg_entity} "
                        f"amount {rec.amount_kes}")

            with arc_tabs[2]:
                st.subheader(f"{regulator()} Regulatory Reporting (ENH-252)")
                st.caption(
                    "5 returns: CAR (PG 03), LIQ (PG 04), SBL (PG 05), "
                    "LXP (PG 05), FXE (PG 06)")
                if st.button(f"Run {regulator()} returns demo", key="cbk_run"):
                    eng = CBKRegulatoryReportingEngine()
                    car = eng.generate_car(CapitalComponents(
                        period="2026-04",
                        tier1_capital_kes=Decimal("1500000000"),
                        tier2_capital_kes=Decimal("300000000"),
                        deductions_kes=Decimal("100000000"),
                        risk_weighted_assets_kes=Decimal("10000000000")))
                    liq = eng.generate_liq(LiquidityComponents(
                        period="2026-04",
                        liquid_assets_kes=Decimal("3000000000"),
                        total_deposits_kes=Decimal("10000000000")))
                    sbl = eng.generate_sbl(
                        "2026-04", Decimal("1000000000"),
                        (BorrowerExposure(
                            borrower_id="MEGA",
                            borrower_name="Mega Corp",
                            funded_kes=Decimal("180000000"),
                            unfunded_kes=Decimal("20000000")),))
                    fxe = eng.generate_fxe(
                        "2026-04", Decimal("1000000000"),
                        (CurrencyPosition(
                            currency="USD",
                            long_kes_equivalent=Decimal("80000000"),
                            short_kes_equivalent=Decimal("30000000")),))
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "cbk_regulatory_reporting",
                         "returns_generated": 4})
                    st.success(f"{regulator()} returns generated")
                    for label, pkg in (
                        ("CAR", car), ("LIQ", liq), ("SBL", sbl),
                        ("FXE", fxe)):
                        st.write(
                            f"**{label}**: severity "
                            f"{pkg.breach_severity.value} — "
                            f"{pkg.breach_description}")

            with arc_tabs[3]:
                st.subheader("Predictive Financial Analytics (ENH-253)")
                st.caption(
                    "3 forecast methods + ML hook (Rule 6: ml_disabled "
                    "flag) · variance · driver decomposition · trend")
                if st.button("Run predictive demo", key="pfa_run"):
                    eng = PredictiveFinancialAnalyticsEngine()
                    history = tuple(
                        TimeSeriesPoint(
                            period=f"2025-{m:02d}",
                            value_kes=Decimal(str(1000000 + 50000 * m)))
                        for m in range(1, 13))
                    f = eng.forecast(
                        "monthly_revenue", history, horizon=3,
                        method=ForecastMethod.LINEAR_TREND)
                    variance = eng.analyze_variance((
                        ActualVsExpected(
                            metric_name="rev", period="2026-04",
                            actual_kes=Decimal("950000"),
                            expected_kes=Decimal("1000000")),
                    ))
                    trend = eng.detect_trend("rev", history)
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "predictive_financial_analytics",
                         "forecast_points": len(f.points),
                         "variance_findings": len(variance)})
                    st.success("Predictive demos complete")
                    st.write(
                        f"**Forecast** ({f.method_used.value}): "
                        f"{len(f.points)} points, "
                        f"ml_disabled={f.ml_disabled}")
                    if variance:
                        st.write(
                            f"**Variance:** {variance[0].materiality.value} "
                            f"/ {variance[0].direction.value}")
                    st.write(
                        f"**Trend:** {trend.signal.value}, "
                        f"slope={trend.slope_per_period}")

                st.divider()
                st.subheader("CFO Dashboard (ENH-254)")
                st.caption(
                    "6 KPI families: profitability · capital · liquidity · "
                    "growth · efficiency · asset quality. Split-implementation "
                    "pulled into this cockpit per v10.46 amendment.")
                if st.button("Run CFO dashboard demo", key="cfo_run"):
                    eng = FinanceIntelligenceDashboardEngine()
                    fin = PeriodFinancials(
                        period="2026-04",
                        net_interest_income_kes=Decimal("4000000000"),
                        non_interest_income_kes=Decimal("1000000000"),
                        operating_expenses_kes=Decimal("2500000000"),
                        impairment_kes=Decimal("300000000"),
                        tax_kes=Decimal("600000000"),
                        avg_total_assets_kes=Decimal("100000000000"),
                        avg_equity_kes=Decimal("10000000000"),
                        avg_earning_assets_kes=Decimal("80000000000"),
                        closing_total_loans_kes=Decimal("60000000000"),
                        closing_total_deposits_kes=Decimal("80000000000"),
                        closing_npl_kes=Decimal("2400000000"),
                        closing_provision_kes=Decimal("1800000000"),
                        customer_count=500000, branch_count=50,
                        transaction_count=10000000,
                        transaction_processing_cost_kes=(
                            Decimal("300000000")),
                        car_ratio=Decimal("0.18"),
                        liq_ratio=Decimal("0.25"))
                    dash = eng.build_dashboard(fin)
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "finance_intelligence_dashboard",
                         "kpis": len(dash.kpis),
                         "alerts": len(dash.alerts)})
                    st.success(
                        f"Dashboard built — {len(dash.kpis)} KPIs, "
                        f"{len(dash.alerts)} alerts")
                    for k in dash.kpis:
                        badge = {
                            ThresholdStatus.OK: "✅",
                            ThresholdStatus.WARNING: "⚠️",
                            ThresholdStatus.BREACH: "🚨",
                            ThresholdStatus.NOT_APPLICABLE: "·"}.get(
                            k.threshold_status, "·")
                        st.write(
                            f"{badge} **{k.metric_name}** "
                            f"({k.family.value}): {k.value} {k.unit}")

            with arc_tabs[4]:
                st.subheader("Financial Statement Generator (ENH-255)")
                st.caption(
                    "5 IFRS statements: BS (IAS 1 §54) · IS (IAS 1 §82) · "
                    "OCI (IAS 1 §82A with CTA from ENH-251) · Equity (IAS "
                    "1 §106) · CF (IAS 7)")
                if st.button("Run statement generator demo", key="fsg_run"):
                    # Build minimal consolidated TB
                    from utils.consolidated_tb_engine import (
                        ConsolidatedLine, ConsolidatedTrialBalance)
                    tb_lines = (
                        ConsolidatedLine(
                            account_code="1010",
                            account_type=AccountType.ASSET,
                            entity_contributions=(),
                            pre_elimination_dr=Decimal("5000000"),
                            pre_elimination_cr=Decimal("0"),
                            eliminations_applied_dr=Decimal("0"),
                            eliminations_applied_cr=Decimal("0"),
                            post_elimination_dr=Decimal("5000000"),
                            post_elimination_cr=Decimal("0"),
                            nci_share_dr=Decimal("0"),
                            nci_share_cr=Decimal("0"),
                            parent_share_dr=Decimal("5000000"),
                            parent_share_cr=Decimal("0"),
                            framework_refs=("ENH-251",)),
                        ConsolidatedLine(
                            account_code="3000",
                            account_type=AccountType.EQUITY,
                            entity_contributions=(),
                            pre_elimination_dr=Decimal("0"),
                            pre_elimination_cr=Decimal("5000000"),
                            eliminations_applied_dr=Decimal("0"),
                            eliminations_applied_cr=Decimal("0"),
                            post_elimination_dr=Decimal("0"),
                            post_elimination_cr=Decimal("5000000"),
                            nci_share_dr=Decimal("0"),
                            nci_share_cr=Decimal("0"),
                            parent_share_dr=Decimal("0"),
                            parent_share_cr=Decimal("5000000"),
                            framework_refs=("ENH-251",)),
                    )
                    tb = ConsolidatedTrialBalance(
                        period="2026-04",
                        presentation_currency=currency(),
                        lines=tb_lines, findings=(),
                        entities_consolidated=1,
                        eliminations_applied_count=0,
                        total_dr=Decimal("5000000"),
                        total_cr=Decimal("5000000"),
                        cumulative_translation_adjustment_kes=(
                            Decimal("0")),
                        framework_refs=("ENH-251",))
                    cls = (
                        AccountClassification(
                            account_code="1010",
                            bs_classification=(
                                BsClassification.CURRENT_ASSET),
                            line_label="Cash"),
                        AccountClassification(
                            account_code="3000",
                            bs_classification=(
                                BsClassification.EQUITY_PARENT),
                            line_label="Share Capital"),
                    )
                    eng = FinancialStatementGenerator()
                    pkg = eng.generate_package(tb, cls)
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "financial_statement_generator",
                         "bs_total_assets": str(
                             pkg.balance_sheet.total_assets_kes)})
                    st.success("IFRS statements generated")
                    st.write(
                        f"**Balance Sheet:** Assets "
                        f"{pkg.balance_sheet.total_assets_kes}, "
                        f"Liab {pkg.balance_sheet.total_liabilities_kes}, "
                        f"Equity {pkg.balance_sheet.total_equity_kes}")

                st.divider()
                st.subheader(f"{tax_authority()} Tax Compliance (ENH-256)")
                st.caption(
                    "5 tax types: corporation tax · VAT · WHT · excise duty "
                    "· deferred tax (IAS 12)")
                if st.button("Run tax compliance demo", key="tax_run"):
                    eng = KRATaxComplianceEngine()
                    ci = CorpTaxInput(
                        period="2026",
                        accounting_profit_kes=Decimal("100000000"),
                        permanent_addbacks_kes=Decimal("5000000"),
                        permanent_deductions_kes=Decimal("2000000"),
                        timing_differences_net_kes=Decimal("3000000"),
                        regime=CorpTaxRegime.STANDARD_RESIDENT)
                    vat = (
                        VatTransaction(
                            transaction_id="v1", period="2026-04",
                            base_amount_kes=Decimal("5000000"),
                            status=VatStatus.STANDARD),
                    )
                    wht = (
                        WhtPayment(
                            payment_id="w1", period="2026-04",
                            income_type=WhtIncomeType.DIVIDEND,
                            gross_amount_kes=Decimal("100000"),
                            payee_residency=ResidencyStatus.RESIDENT),
                    )
                    diffs = (
                        TemporaryDifference(
                            description="Accelerated depreciation",
                            period="2026-04",
                            amount_kes=Decimal("5000000"),
                            diff_type=TemporaryDifferenceType.TAXABLE),
                    )
                    pkg = eng.build_return_package(
                        "2026-04",
                        corp_tax_input=ci,
                        vat_transactions=vat,
                        wht_payments=wht,
                        temp_differences=diffs)
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "kra_tax_compliance",
                         "computations": len(pkg.computations)})
                    st.success(
                        f"Tax return package — "
                        f"{len(pkg.computations)} computations, "
                        f"deferred tax {pkg.deferred_tax is not None}")
                    for tt, amt in pkg.by_tax_type.items():
                        if amt != 0:
                            st.write(f"**{tt}**: {amt}")

            with arc_tabs[5]:
                st.subheader("Finance Audit & Compliance (ENH-258)")
                st.caption(
                    "5 SOX-style controls: SoD · authorization · manual "
                    "journal · period attestation · late adjustment")
                if st.button("Run compliance report demo", key="fac_run"):
                    eng = FinanceAuditComplianceEngine()
                    journals = (
                        JournalAudit(
                            journal_id="J-CLEAN",
                            period="2026-04",
                            posting_date="2026-04-15",
                            amount_kes=Decimal("50000"),
                            source=JournalSource.AUTOMATED,
                            preparer_user_id="alice",
                            reviewer_user_id="bob",
                            poster_user_id="carol"),
                        JournalAudit(
                            journal_id="J-SOD-BREACH",
                            period="2026-04",
                            posting_date="2026-04-20",
                            amount_kes=Decimal("200000"),
                            source=JournalSource.MANUAL,
                            preparer_user_id="rogue",
                            reviewer_user_id="rogue",
                            poster_user_id="rogue"),
                    )
                    auths = (
                        UserAuthorization(
                            user_id="carol",
                            max_journal_kes=Decimal("100000"),
                            role="POSTER"),
                        UserAuthorization(
                            user_id="rogue",
                            max_journal_kes=Decimal("500000"),
                            role="POSTER"),
                    )
                    attestations = (
                        PeriodAttestation(
                            attestation_id="GL-2026-04",
                            period="2026-04", function="GL_CLOSE",
                            deadline_date="2026-05-05",
                            status=AttestationStatus.OVERDUE,
                            attestor_user_id="cfo",
                            attested_at=None),
                    )
                    report = eng.build_compliance_report(
                        "2026-04",
                        journals=journals,
                        authorizations=auths,
                        attestations=attestations,
                        period_cutoff_date="2026-05-05")
                    audit_log(
                        "FINANCE_ENGINE_USED", uname,
                        {"engine": "finance_audit_compliance",
                         "findings": len(report.findings)})
                    st.success(
                        f"Compliance scan complete — "
                        f"{len(report.findings)} findings, "
                        f"{report.journals_scanned} journals scanned")
                    for f in report.findings:
                        badge = {
                            FindingSeverity.CRITICAL: "🚨",
                            FindingSeverity.HIGH: "⚠️",
                            FindingSeverity.MEDIUM: "·",
                            FindingSeverity.LOW: "·",
                            FindingSeverity.INFO: "ℹ️"}.get(
                            f.severity, "·")
                        st.write(
                            f"{badge} **{f.control.value}** · "
                            f"{f.severity.value} — {f.description}")

            with arc_tabs[6]:
                st.subheader("Finance Arc Summary")
                st.markdown("""
    **Arc closure batch:** v10.69 (this drop)

    **Scope:** 11 batches v10.59 → v10.69 producing 10 standards, 10 modules,
    40 scenarios across the arc, 2 closure ratchets (G135 + G136),
    1 cockpit page (this one), Engine Hub Tier 27 expansion to full
    descriptions, Master Prompt v3 line 108 update.

    **Closed-arc count:** 13 — finance arc joins
    - Treasury (v10.37, G127)
    - Risk (v10.46, G129+G130)
    - Credit/Model Risk (v10.49, G131+G132)
    - Revenue Assurance (v10.58, G133+G134)
    - and 8 prior closed arcs.

    **Discipline preserved:**
    - Per Rule 1, every result dataclass is frozen with full
      provenance — inputs, intermediates, outputs, framework refs.
    - Per Rule 6, ML hooks surface `ml_disabled=True` with reason
      when no caller-supplied predictor (ENH-253 explicitly tested).
    - Per Rule 7, all 10 engines are diagnostic — never auto-post,
      never auto-revalue, never file with regulators directly,
      never serialize statements to PDF/XBRL, never block
      transactions, never revoke access, never auto-attest.
    - Audit gate G135 verifies the structural contract; G136 verifies
      this cockpit imports + invokes all 10 engines.

    **Composition:** the 10 engines compose along clear lines —
    ENH-249 detects in-entity IC pending; ENH-250 pairs IC across
    entities; ENH-251 consumes IC eliminations + entity TBs to
    produce consolidated TB; ENH-252 reads the consolidated capital +
    liquidity to produce regulator returns; ENH-255 consumes the
    consolidated TB + classifications to produce IFRS statements;
    ENH-256 layers tax on top of accounting profit; ENH-257 handles
    transaction-level FX before TBs are extracted; ENH-258 audits
    the journal trail across all the others; ENH-253 forecasts
    metrics derived from the others; ENH-254 dashboards them.

    **Honest scope notes** (full detail in CHANGELOGs v10.59 through
    v10.69) — every engine ships with explicit "what it doesn't do"
    documentation. No engine pretends to be more than it is.
    """)

            # Footer audit log
            try:
                audit_log(
                    action="finance_arc_engines.view",
                    username=ud.get("username", "anonymous"),
                    detail=f"viewed_at={_dt_fa.now(_tz_fa.utc).isoformat()}",
                    module="mgmt_accounts")
            except Exception:
                pass

