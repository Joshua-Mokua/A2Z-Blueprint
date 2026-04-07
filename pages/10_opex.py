"""pages/10_opex.py — Operating Leverage: CIR, SBU P&L, Branch P&L, Industry benchmarking."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from utils.core import *
from pages._shared import load_shared_state

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

# ── Session data from BSC upload ─────────────────────────────────────
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

st.markdown(
    "<div style='padding:14px 20px;background:#C0392B;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:16px;font-weight:500'>Operating Leverage & CIR Analysis</div>"
    "<div style='color:rgba(255,255,255,0.75);font-size:11px;margin-top:2px'>"
    "Cost-to-income · Branch P&L · Industry benchmarking · Turnaround propositions"
    "</div></div>", unsafe_allow_html=True)

# ── INDUSTRY DATA UPLOAD (optional — enables benchmarking) ───────────
with st.sidebar:
    st.markdown("---")
    st.markdown("**Industry benchmark data**")
    ind_file = st.file_uploader(
        "Industry_Financial_Review.xlsx",
        type=["xlsx","xls"], key="ind_upload_opex",
        help="Upload for CIR, NIM, LDR industry comparisons")

ind_raw = cache_upload(ind_file, "_ind_raw_bytes_opex")

# ── FINANCIALS FILE (optional — enables SBU P&L) ─────────────────────
with st.sidebar:
    fin_file = st.file_uploader(
        "SBU Profitability Excel (optional)",
        type=["xlsx","xls"], key="fin_upload",
        help="Upload SBU profitability file for detailed P&L")

fin_raw = cache_upload(fin_file, "_fin_raw_bytes")

# ════════════════════════════════════════════════════════════════
# DATA LOADING FUNCTIONS
# ════════════════════════════════════════════════════════════════
@st.cache_data(show_spinner=False)
def load_industry(_raw: bytes):
    try:
        df = pd.read_excel(io.BytesIO(_raw), header=2)
        df.columns = [str(c).strip() for c in df.columns]
        for col in df.columns:
            if col not in ('Size','Bank','Ownership','Period'):
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_sbu_pnl(_raw: bytes):
    try:
        xl = pd.ExcelFile(io.BytesIO(_raw))
        results = {}
        # Try 'summary' sheet first
        if 'summary' in xl.sheet_names:
            df = pd.read_excel(io.BytesIO(_raw), sheet_name='summary', header=0)
            df.columns = [str(c).strip() for c in df.columns]
            results['summary'] = df
        # Try 'Main Segments'
        if 'Main Segments' in xl.sheet_names:
            df = pd.read_excel(io.BytesIO(_raw), sheet_name='Main Segments', header=0)
            df.columns = [str(c).strip() for c in df.columns]
            results['segments'] = df
        return results
    except Exception:
        return {}

# Load data
ind_df  = load_industry(ind_raw)   if ind_raw  else pd.DataFrame()
sbu_data = load_sbu_pnl(fin_raw)  if fin_raw  else {}

# ════════════════════════════════════════════════════════════════
# BUILD BSC-DERIVED BRANCH METRICS (always available)
# ════════════════════════════════════════════════════════════════
def build_branch_pnl_from_bsc():
    """Derive branch P&L proxy from BSC KPI actuals."""
    if df_proc.empty or 'Unit' not in df_proc.columns:
        return pd.DataFrame()

    branch_data = df_proc[df_proc.get('Category', pd.Series('Branch', index=df_proc.index)) == 'Branch'] \
        if 'Category' in df_proc.columns else df_proc

    branches = branch_data['Unit'].dropna().unique()
    rows = []
    for branch in branches:
        bdf = branch_data[branch_data['Unit'] == branch]

        def get_kpi_actual(kpi_name):
            k = bdf[bdf['KPI'] == kpi_name]
            if k.empty: return 0.0
            return float(k['YTD_Actual'].sum() if 'YTD_Actual' in k.columns else 0)

        def get_kpi_target(kpi_name):
            k = bdf[bdf['KPI'] == kpi_name]
            if k.empty: return 0.0
            return float(k['Annual Target'].sum() if 'Annual Target' in k.columns else 0)

        pbt          = get_kpi_actual('PBT')
        pbt_target   = get_kpi_target('PBT')
        deposits     = get_kpi_actual('Deposit Growth')
        loans        = get_kpi_actual('Loan Book Growth')
        fees         = get_kpi_actual('Fees and Commission')
        dfs          = get_kpi_actual('DFS Revenue')
        banc         = get_kpi_actual('Bancassurance')
        nii          = get_kpi_actual('Net Interest Income') or (loans * 0.13 / 4)
        nfi          = fees + dfs + banc
        total_income = (nii + nfi) if (nii + nfi) > 0 else (pbt * 3.5 if pbt > 0 else 0)
        npl_ratio    = get_kpi_actual('NPL Ratio')

        # Derive opex: PBT = Income - Opex - Provisions => Opex = Income - PBT - Provisions
        provisions   = loans * max(npl_ratio, 0.02) * 0.5 if loans > 0 else 0
        opex         = total_income - pbt - provisions if total_income > 0 else 0
        cir          = (opex / total_income * 100) if total_income > 0 else 0

        region = BRANCH_REGION.get(branch, 'Central')

        # BSC metrics
        bsc_scores = staff_scores[staff_scores['Unit'] == branch]['Final_BSC_Score'] \
            if len(staff_scores) and 'Unit' in staff_scores.columns else pd.Series()
        avg_bsc = float(bsc_scores.mean()) if len(bsc_scores) else 0

        rows.append({
            'Branch':           branch,
            'Region':           region,
            'Deposits (M)':     round(deposits/1e6, 1),
            'Loans (M)':        round(loans/1e6, 1),
            'NII (M)':          round(nii/1e6, 2),
            'NFI (M)':          round(nfi/1e6, 2),
            'Total Income (M)': round(total_income/1e6, 2),
            'Opex (M)':         round(opex/1e6, 2),
            'PBT (M)':          round(pbt/1e6, 2),
            'PBT Target (M)':   round(pbt_target/1e6, 2),
            'CIR %':            round(cir, 1),
            'NPL %':            round(npl_ratio*100, 2) if npl_ratio < 1 else round(npl_ratio, 2),
            'Avg BSC':          round(avg_bsc, 2),
            'Status':           ('🔴 Loss' if pbt < 0 else
                                 ('🟠 Below target' if pbt < pbt_target*0.7 else
                                  ('🟡 On track' if pbt < pbt_target else '🟢 Exceeding'))),
        })

    df = pd.DataFrame(rows)
    if not df.empty and 'PBT (M)' in df.columns:
        df = df.sort_values('PBT (M)')
    return df

# ════════════════════════════════════════════════════════════════
# INDUSTRY BENCHMARK HELPER
# ════════════════════════════════════════════════════════════════
ECO_BENCHMARKS = {
    'Cost-to-Income Ratio (CIR)': {'eco': 80.6, 'median': 69.6, 'top_q': 55.2,
                                     'unit':'%', 'lower_better': True},
    'Loans-to-Deposit Ratio (LDR)': {'eco': 21.8, 'median': 63.2, 'top_q': 82.4,
                                      'unit':'%', 'lower_better': False},
    'Return on Equity (ROE)':       {'eco': 39.5, 'median': 52.1, 'top_q': 65.5,
                                      'unit':'%', 'lower_better': False},
    'Net Interest Margin (NIM)':    {'eco': 7.8,  'median': 9.2,  'top_q': 12.4,
                                      'unit':'%', 'lower_better': False},
    'NPL Ratio':                    {'eco': 14.5, 'median': 18.4, 'top_q': 8.2,
                                      'unit':'%', 'lower_better': True},
}
if not ind_df.empty:
    latest_period = ind_df['Period'].dropna().iloc[-1] if 'Period' in ind_df.columns else None
    if latest_period:
        latest = ind_df[ind_df['Period'] == latest_period]
        for metric, vals in ECO_BENCHMARKS.items():
            if metric in latest.columns:
                col_data = latest[metric].dropna()
                if len(col_data) > 5:
                    vals['median'] = round(float(col_data.median()), 1)
                    vals['top_q']  = round(float(col_data.quantile(0.25 if vals['lower_better'] else 0.75)), 1)
                    eco_row = ind_df[ind_df['Bank'].str.contains('Ecobank', case=False, na=False)]
                    if len(eco_row):
                        eco_latest = eco_row[eco_row['Period']==latest_period]
                        if len(eco_latest) and not pd.isna(eco_latest[metric].values[0]):
                            vals['eco'] = round(float(eco_latest[metric].values[0]), 1)

branch_pnl = build_branch_pnl_from_bsc()

# ════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════
tabs = st.tabs([
    "📊 Operating leverage",
    "🏦 SBU P&L",
    "🏢 Branch P&L",
    "📉 Cost-to-income",
    "🌍 Industry benchmarks",
    "💡 Turnaround propositions",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — OPERATING LEVERAGE
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Operating leverage — Revenue vs Cost growth")
    st.caption("Operating leverage = Revenue growth rate ÷ Cost growth rate. "
               "Positive leverage (>1) means revenue growing faster than costs.")

    if not branch_pnl.empty:
        total_income = branch_pnl['Total Income (M)'].sum()
        total_opex   = branch_pnl['Opex (M)'].sum()
        total_pbt    = branch_pnl['PBT (M)'].sum()
        total_dep    = branch_pnl['Deposits (M)'].sum()
        blended_cir  = (total_opex / total_income * 100) if total_income > 0 else 0

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Total income (YTD)", f"KES {total_income:.0f}M")
        c2.metric("Total opex (YTD)",   f"KES {total_opex:.0f}M")
        c3.metric("Network PBT",        f"KES {total_pbt:.0f}M")
        c4.metric("Blended CIR",        f"{blended_cir:.1f}%",
                  delta=f"vs 69.6% industry median",
                  delta_color="inverse" if blended_cir > 69.6 else "normal")
        c5.metric("Total deposits",     f"KES {total_dep:.0f}M")

        # Operating leverage waterfall by region
        reg = branch_pnl.groupby('Region').agg(
            Income=('Total Income (M)','sum'),
            Opex=('Opex (M)','sum'),
            PBT=('PBT (M)','sum'),
        ).reset_index()
        reg['CIR %']  = (reg['Opex'] / reg['Income'] * 100).round(1)
        reg['OL']     = (reg['Income'] / reg['Opex']).round(2)

        fc1, fc2 = st.columns(2)
        with fc1:
            fig_reg = px.bar(reg, x='Region', y=['Income','Opex','PBT'],
                              barmode='group', title='Income vs Opex vs PBT by region (KES M)',
                              color_discrete_map={'Income':'#006B3F','Opex':'#E24B4A','PBT':'#F5A623'})
            fig_reg.update_layout(height=320, legend=dict(orientation='h', y=-0.2),
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_reg, use_container_width=True)

        with fc2:
            fig_cir_reg = px.bar(reg, x='Region', y='CIR %',
                                  text='CIR %', color='CIR %',
                                  title='Blended CIR by region (%)',
                                  color_continuous_scale=['#006B3F','#F5A623','#E24B4A'],
                                  range_color=[40, 100])
            fig_cir_reg.add_hline(y=69.6, line_dash='dash', line_color='#185FA5',
                                   annotation_text='Industry median 69.6%')
            fig_cir_reg.add_hline(y=80.6, line_dash='dot', line_color='#E24B4A',
                                   annotation_text='Ecobank current 80.6%')
            fig_cir_reg.update_traces(texttemplate='%{y:.1f}%', textposition='outside')
            fig_cir_reg.update_layout(height=320,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_cir_reg, use_container_width=True)

        # CIR insight box
        gap = blended_cir - 69.6
        saving = abs(gap) / 100 * total_income
        st.markdown(
            f"<div style='padding:12px 16px;background:#FFFBF0;"
            f"border-left:4px solid #F5A623;border-radius:0 8px 8px 0;margin:8px 0'>"
            f"<b>💡 CIR gap insight:</b> Ecobank's branch network CIR of <b>{blended_cir:.1f}%</b> "
            f"is <b>{gap:.1f} percentage points</b> above the industry median of 69.6%. "
            f"Closing this gap would generate an additional <b>KES {saving:.0f}M</b> in PBT "
            f"on the current income base — without growing revenue at all."
            f"</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — SBU P&L
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("SBU P&L summary")

    # Try actual SBU file first
    sbu_summary = sbu_data.get('summary', pd.DataFrame())
    if not sbu_summary.empty:
        st.caption("Data from uploaded SBU profitability file.")
        # Parse the summary structure: rows = metrics, cols = SBUs
        try:
            # Row 0 = headers, rows 1+ = data
            sbu_summary.columns = sbu_summary.iloc[0]
            sbu_summary = sbu_summary.drop(0).reset_index(drop=True)
            sbu_summary.columns = [str(c).strip() for c in sbu_summary.columns]

            sbus = ['CORPORATE', 'GIB', 'MSME', 'RETAIL BANKING', 'BANK']
            sbus = [s for s in sbus if s in sbu_summary.columns]

            if sbus:
                pbt_row    = sbu_summary[sbu_summary.iloc[:,0].astype(str).str.contains('PBT', case=False, na=False)]
                target_row = sbu_summary[sbu_summary.iloc[:,0].astype(str).str.contains('Target|Budget', case=False, na=False)]

                if len(pbt_row):
                    pbt_vals = {s: float(pbt_row[s].values[0]) for s in sbus if s in pbt_row.columns and pd.notna(pbt_row[s].values[0])}
                    pbt_df = pd.DataFrame(list(pbt_vals.items()), columns=['SBU','PBT'])

                    fig_sbu = px.bar(pbt_df, x='SBU', y='PBT',
                                      title='PBT by SBU (KES)',
                                      color='PBT',
                                      color_continuous_scale=['#E24B4A','#F5A623','#006B3F'],
                                      text='PBT')
                    fig_sbu.update_traces(texttemplate='%{y:,.0f}', textposition='outside')
                    fig_sbu.update_layout(height=360,
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                    st.plotly_chart(fig_sbu, use_container_width=True)

                    if len(target_row):
                        ach_row = sbu_summary[sbu_summary.iloc[:,0].astype(str).str.contains('Achievement|Achiev', case=False, na=False)]
                        if len(ach_row):
                            ach_vals = {s: float(ach_row[s].values[0]) for s in sbus if s in ach_row.columns and pd.notna(ach_row[s].values[0])}
                            st.markdown("**Achievement vs target:**")
                            ac_cols = st.columns(len(ach_vals))
                            for i, (sbu, ach) in enumerate(ach_vals.items()):
                                pct = ach * 100
                                clr = '#006B3F' if pct >= 90 else ('#F5A623' if pct >= 60 else '#E24B4A')
                                ac_cols[i].markdown(
                                    f"<div style='padding:10px;background:var(--color-background-secondary);"
                                    f"border-radius:8px;text-align:center;border-top:3px solid {clr}'>"
                                    f"<div style='font-size:20px;font-weight:700;color:{clr}'>{pct:.0f}%</div>"
                                    f"<div style='font-size:10px;color:#888;margin-top:2px'>{sbu}</div>"
                                    f"</div>", unsafe_allow_html=True)
        except Exception as ex:
            st.warning(f"Could not parse SBU file: {ex}")
            sbu_summary = pd.DataFrame()

    if sbu_summary.empty:
        # Fallback: derive from BSC data
        st.caption("Derived from BSC KPI actuals. Upload SBU Profitability Excel for exact figures.")
        if not df_proc.empty and 'Category' in df_proc.columns:
            ho_kpis = df_proc[df_proc['Category']=='Head Office']
            sbu_map = {
                'Retail Banking':   ['Director Retail Banking','Regional Head','Branch Manager'],
                'Commercial & SME': ['Director Commercial Banking','Head Of SME','Relationship Manager SME'],
                'Corporate & CIB':  ['Head Of Corporate','Relationship Manager Corporate','Head Of Digital Innovation'],
            }
            sbu_rows = []
            for sbu_name, roles in sbu_map.items():
                sdf = df_proc[df_proc['Role'].isin(roles)] if 'Role' in df_proc.columns else pd.DataFrame()
                pbt = float(sdf[sdf['KPI']=='PBT']['YTD_Actual'].sum()) if not sdf.empty and 'YTD_Actual' in sdf.columns else 0
                dep = float(sdf[sdf['KPI']=='Deposit Growth']['YTD_Actual'].sum()) if not sdf.empty else 0
                loans = float(sdf[sdf['KPI']=='Loan Book Growth']['YTD_Actual'].sum()) if not sdf.empty else 0
                sbu_rows.append({'SBU':sbu_name,'PBT (M)':round(pbt/1e6,1),
                                  'Deposits (M)':round(dep/1e6,1),'Loans (M)':round(loans/1e6,1)})

            if sbu_rows:
                sbu_df = pd.DataFrame(sbu_rows)
                fig_s = px.bar(sbu_df, x='SBU', y='PBT (M)',
                                color='PBT (M)',
                                color_continuous_scale=['#E24B4A','#F5A623','#006B3F'],
                                title='PBT by SBU — derived from BSC actuals (KES M)')
                fig_s.update_layout(height=340,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_s, use_container_width=True)
                st.dataframe(sbu_df, use_container_width=True, hide_index=True)
        else:
            st.info("Upload BSC data from the sidebar to see SBU performance.")

# ════════════════════════════════════════════════════════════════
# TAB 3 — BRANCH P&L
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Branch P&L — derived from BSC KPI actuals")
    st.caption(
        "Income, opex, and PBT estimated from BSC actuals. "
        "NII = loan book × 13% NIM ÷ 4 (Q1 annualised). "
        "Opex = Total Income − PBT − Provisions.")

    if branch_pnl.empty:
        st.info("Upload BSC data from the sidebar to see branch P&L.")
    else:
        # Summary metrics
        total_branches = len(branch_pnl)
        loss_branches  = int((branch_pnl['PBT (M)'] < 0).sum())
        strong_branches= int((branch_pnl['Status'] == '🟢 Exceeding').sum())
        avg_cir        = branch_pnl['CIR %'].replace(0, np.nan).mean()

        bc1,bc2,bc3,bc4 = st.columns(4)
        bc1.metric("Total branches",   total_branches)
        bc2.metric("Loss-making",      loss_branches,
                   delta=f"-{loss_branches}" if loss_branches else "0", delta_color="inverse")
        bc3.metric("Exceeding target", strong_branches)
        bc4.metric("Avg branch CIR",   f"{avg_cir:.1f}%" if not np.isnan(avg_cir) else "—",
                   delta=f"vs 69.6% median", delta_color="inverse" if avg_cir > 69.6 else "normal")

        # Filters
        fc1, fc2, fc3 = st.columns(3)
        reg_f  = fc1.selectbox("Region", ["All","Central","North","South"], key="br_reg")
        stat_f = fc2.selectbox("Status",
            ["All","🔴 Loss","🟠 Below target","🟡 On track","🟢 Exceeding"], key="br_stat")
        sort_f = fc3.selectbox("Sort by",
            ["PBT (M)","CIR %","Deposits (M)","Loans (M)","Avg BSC"], key="br_sort")

        view = branch_pnl.copy()
        if reg_f  != "All": view = view[view['Region'] == reg_f]
        if stat_f != "All": view = view[view['Status'] == stat_f]
        view = view.sort_values(sort_f, ascending=(sort_f == 'CIR %'))

        # PBT chart — colour by status
        pbt_colors = {
            '🔴 Loss':         '#E24B4A',
            '🟠 Below target': '#E67E22',
            '🟡 On track':     '#F5A623',
            '🟢 Exceeding':    '#006B3F',
        }
        bar_colors = [pbt_colors.get(s,'#888') for s in view['Status']]
        fig_br = go.Figure()
        fig_br.add_bar(
            x=view['Branch'], y=view['PBT (M)'],
            marker_color=bar_colors,
            text=[f"{v:.1f}M" for v in view['PBT (M)']],
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>PBT: KES %{y:.1f}M<extra></extra>')
        fig_br.add_hline(y=0, line_color='#E24B4A', line_dash='dash',
                          line_width=1.5, annotation_text='Break-even')
        fig_br.update_layout(
            height=380, title='Branch PBT — YTD (KES millions)',
            xaxis_tickangle=-35, yaxis_title='KES millions',
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_br, use_container_width=True)

        # CIR scatter: efficiency vs profitability
        view_nonzero = view[view['CIR %'] > 0].copy()
        if len(view_nonzero) > 0:
            view_nonzero['Region_clr'] = view_nonzero['Region']
            fig_sc = px.scatter(
                view_nonzero,
                x='CIR %', y='PBT (M)',
                color='Region_clr',
                size=view_nonzero['Deposits (M)'].clip(lower=1),
                hover_name='Branch',
                hover_data={'CIR %':':.1f','PBT (M)':':.1f',
                            'Avg BSC':':.2f','Status':True,'Region_clr':False},
                title='Cost efficiency vs profitability (bubble = deposits)',
                color_discrete_map={'Central':'#006B3F','North':'#185FA5','South':'#F5A623'},
                labels={'Region_clr':'Region','CIR %':'CIR (%)','PBT (M)':'PBT (KES M)'})
            fig_sc.add_vline(x=69.6, line_color='#185FA5', line_dash='dash',
                              annotation_text='Industry median 69.6%')
            fig_sc.add_vline(x=80.6, line_color='#E24B4A', line_dash='dot',
                              annotation_text='Ecobank avg 80.6%')
            fig_sc.add_hline(y=0, line_color='#E24B4A', line_dash='dash')
            fig_sc.update_layout(height=380,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(orientation='h', y=-0.15))
            st.plotly_chart(fig_sc, use_container_width=True)

        # Table
        disp_cols = ['Branch','Region','Status','Deposits (M)','Loans (M)',
                     'Total Income (M)','Opex (M)','PBT (M)','CIR %','Avg BSC']
        disp_cols = [c for c in disp_cols if c in view.columns]
        disp_br = view[disp_cols].copy()

        def hl_pbt(v):
            try:
                if float(v) < 0: return 'color:#E24B4A;font-weight:600'
                if float(v) > 5: return 'color:#006B3F;font-weight:600'
            except: pass
            return ''

        def hl_cir(v):
            try:
                fv = float(v)
                if fv > 80:  return 'color:#E24B4A;font-weight:600'
                if fv > 65:  return 'color:#F5A623'
                if fv < 55:  return 'color:#006B3F;font-weight:600'
            except: pass
            return ''

        st.dataframe(
            disp_br.style
                .map(hl_pbt, subset=['PBT (M)'] if 'PBT (M)' in disp_br.columns else [])
                .map(hl_cir, subset=['CIR %']   if 'CIR %'   in disp_br.columns else []),
            use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 4 — COST-TO-INCOME DEEP DIVE
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Cost-to-income ratio analysis")
    st.caption(
        "CIR = Total operating costs ÷ Total operating income × 100. "
        "Best practice: < 55% excellent · 55–65% acceptable · 65–80% action required · > 80% critical.")

    if not branch_pnl.empty:
        valid_cir = branch_pnl[branch_pnl['CIR %'] > 0].copy()

        # Summary benchmarks
        eco_cir      = ECO_BENCHMARKS['Cost-to-Income Ratio (CIR)']['eco']
        ind_median   = ECO_BENCHMARKS['Cost-to-Income Ratio (CIR)']['median']
        top_quartile = ECO_BENCHMARKS['Cost-to-Income Ratio (CIR)']['top_q']
        gap_to_med   = eco_cir - ind_median
        gap_to_top   = eco_cir - top_quartile

        cc1,cc2,cc3,cc4 = st.columns(4)
        cc1.metric("Ecobank CIR",       f"{eco_cir:.1f}%",
                   delta=f"+{gap_to_med:.1f}pp vs industry", delta_color="inverse")
        cc2.metric("Industry median",   f"{ind_median:.1f}%")
        cc3.metric("Top quartile",      f"{top_quartile:.1f}%")
        cc4.metric("Gap to top quartile",f"{gap_to_top:.1f}pp",
                   delta="Cost reduction opportunity", delta_color="inverse")

        # KES impact of closing the gap
        total_inc = branch_pnl['Total Income (M)'].sum()
        saving_to_med = gap_to_med / 100 * total_inc
        saving_to_top = gap_to_top / 100 * total_inc
        st.markdown(
            f"<div style='padding:12px 16px;background:#E8F5EE;"
            f"border-left:4px solid #006B3F;border-radius:0 8px 8px 0;margin:8px 0'>"
            f"<b>CIR opportunity sizing:</b> Matching the industry median CIR of {ind_median:.1f}% "
            f"would save <b>KES {saving_to_med:.0f}M</b> per quarter. "
            f"Reaching top-quartile efficiency ({top_quartile:.1f}%) would add "
            f"<b>KES {saving_to_top:.0f}M</b> to PBT — with zero revenue growth needed."
            f"</div>", unsafe_allow_html=True)

        # CIR distribution across branches
        fig_cir_dist = px.histogram(
            valid_cir, x='CIR %', nbins=15,
            title='CIR distribution — branch network',
            color_discrete_sequence=['#185FA5'])
        for threshold, color, label in [
            (55, '#006B3F', 'Excellent <55%'),
            (65, '#F5A623', 'Target <65%'),
            (80, '#E24B4A', 'Critical >80%'),
        ]:
            fig_cir_dist.add_vline(x=threshold, line_dash='dash',
                                    line_color=color, annotation_text=label,
                                    annotation_position='top right')
        fig_cir_dist.add_vline(x=ind_median, line_dash='dot',
                                line_color='#185FA5', line_width=2,
                                annotation_text=f'Industry median {ind_median:.1f}%')
        fig_cir_dist.update_layout(height=300,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_cir_dist, use_container_width=True)

        # CIR band breakdown
        bands = {
            '🟢 Excellent (<55%)':  int((valid_cir['CIR %'] < 55).sum()),
            '🟡 Good (55–65%)':     int(((valid_cir['CIR %'] >= 55) & (valid_cir['CIR %'] < 65)).sum()),
            '🟠 High (65–80%)':     int(((valid_cir['CIR %'] >= 65) & (valid_cir['CIR %'] < 80)).sum()),
            '🔴 Critical (>80%)':   int((valid_cir['CIR %'] >= 80).sum()),
        }
        band_df = pd.DataFrame(list(bands.items()), columns=['Band','Branches'])
        bc1, bc2 = st.columns(2)
        with bc1:
            fig_band = px.pie(band_df, names='Band', values='Branches',
                               title='Branches by CIR band',
                               color='Band',
                               color_discrete_map={
                                   '🟢 Excellent (<55%)':'#006B3F',
                                   '🟡 Good (55–65%)':'#F5A623',
                                   '🟠 High (65–80%)':'#E67E22',
                                   '🔴 Critical (>80%)':'#E24B4A',
                               })
            fig_band.update_layout(height=300, legend=dict(orientation='h', y=-0.2))
            st.plotly_chart(fig_band, use_container_width=True)

        with bc2:
            # CIR vs BSC scatter
            if 'Avg BSC' in valid_cir.columns:
                fig_cv = px.scatter(
                    valid_cir, x='CIR %', y='Avg BSC',
                    color='Region', hover_name='Branch',
                    title='CIR vs BSC performance correlation',
                    labels={'Avg BSC':'Average BSC score','CIR %':'CIR (%)'},
                    color_discrete_map={'Central':'#006B3F','North':'#185FA5','South':'#F5A623'})
                fig_cv.add_vline(x=ind_median, line_dash='dash',
                                  line_color='#888', annotation_text='Industry median')
                fig_cv.add_hline(y=3.0, line_dash='dash',
                                  line_color='#F5A623', annotation_text='BSC target 3.0')
                fig_cv.update_layout(height=300,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', y=-0.2))
                st.plotly_chart(fig_cv, use_container_width=True)

        # Worst CIR branches — action list
        worst = valid_cir.nlargest(5, 'CIR %')[['Branch','Region','CIR %','PBT (M)','Status']]
        st.markdown("#### Highest CIR branches — immediate review needed")
        for _, row in worst.iterrows():
            gap_pp = row['CIR %'] - ind_median
            rev_opp = gap_pp / 100 * max(row.get('Total Income (M)', 10) if 'Total Income (M)' in row.index else 10, 1)
            st.markdown(
                f"<div style='padding:8px 14px;background:#FFF0F0;"
                f"border-left:4px solid #E24B4A;border-radius:0 6px 6px 0;margin:3px 0;font-size:12px'>"
                f"<b>{row['Branch']}</b> ({row['Region']}) — CIR: <b style='color:#E24B4A'>{row['CIR %']:.1f}%</b> "
                f"| {gap_pp:.1f}pp above industry median "
                f"| PBT: KES {row['PBT (M)']:.1f}M"
                f"</div>", unsafe_allow_html=True)

    else:
        st.info("Upload BSC data to see cost-to-income analysis.")

# ════════════════════════════════════════════════════════════════
# TAB 5 — INDUSTRY BENCHMARKS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Industry benchmarking — Ecobank vs Kenya banking sector")
    st.caption(
        "Comparing Ecobank Kenya against all 39 licensed commercial banks. "
        "Source: CBK Quarterly data 2021 Q1 – 2025 Q3." +
        (" Industry data loaded. ✅" if not ind_df.empty else
         " Upload Industry_Financial_Review.xlsx for live data — using embedded 2025 Q3 benchmarks."))

    # ── BENCHMARK CARDS ──────────────────────────────────────
    st.markdown("#### Key ratio benchmarks — Ecobank vs industry")
    card_cols = st.columns(len(ECO_BENCHMARKS))
    for i, (metric, vals) in enumerate(ECO_BENCHMARKS.items()):
        eco   = vals['eco']
        med   = vals['median']
        topq  = vals['top_q']
        lb    = vals['lower_better']
        unit  = vals['unit']
        short = metric.split('(')[0].strip()[:16]

        if lb:
            vs_med = eco - med
            vs_top = eco - topq
            clr = '#006B3F' if eco < topq else ('#F5A623' if eco < med else '#E24B4A')
            pos = 'below' if vs_med < 0 else 'above'
            icon = '✅' if eco < topq else ('⚠️' if eco < med else '🔴')
        else:
            vs_med = eco - med
            clr = '#006B3F' if eco > topq else ('#F5A623' if eco > med else '#E24B4A')
            pos = 'above' if vs_med > 0 else 'below'
            icon = '✅' if eco > topq else ('⚠️' if eco > med else '🔴')

        card_cols[i].markdown(
            f"<div style='padding:12px 10px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-top:3px solid {clr};text-align:center;height:160px'>"
            f"<div style='font-size:9px;color:#888;text-transform:uppercase;margin-bottom:4px'>{short}</div>"
            f"<div style='font-size:22px;font-weight:700;color:{clr}'>{eco:.1f}{unit}</div>"
            f"<div style='font-size:10px;color:#888;margin-top:6px'>Median: {med:.1f}{unit}</div>"
            f"<div style='font-size:10px;color:#888'>Top Q: {topq:.1f}{unit}</div>"
            f"<div style='font-size:11px;margin-top:6px'>{icon} {abs(vs_med):.1f}pp {pos} median</div>"
            f"</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── LIVE INDUSTRY DATA ────────────────────────────────────
    if not ind_df.empty and 'Bank' in ind_df.columns and 'Period' in ind_df.columns:
        latest_p = ind_df['Period'].dropna().unique()[-1]
        latest   = ind_df[ind_df['Period'] == latest_p].copy()
        eco_row  = latest[latest['Bank'].str.contains('Ecobank', case=False, na=False)]

        # Select metric to chart
        chartable = [c for c in ind_df.columns
                     if c not in ('Size','Bank','Ownership','Period')
                     and ind_df[c].notna().sum() > 10]
        sel_metric = st.selectbox("Select metric to benchmark", chartable,
                                   index=chartable.index('Cost-to-Income Ratio (CIR)')
                                   if 'Cost-to-Income Ratio (CIR)' in chartable else 0,
                                   key="ind_metric_opex")

        metric_data = latest[['Bank', sel_metric]].dropna().sort_values(sel_metric)
        if len(metric_data) > 3:
            median_v  = float(metric_data[sel_metric].median())
            topq_v    = float(metric_data[sel_metric].quantile(0.25
                               if ECO_BENCHMARKS.get(sel_metric, {}).get('lower_better') else 0.75))
            eco_v     = float(eco_row[sel_metric].values[0]) if len(eco_row) and not pd.isna(eco_row[sel_metric].values[0]) else None

            # Highlight Ecobank
            metric_data['_is_eco'] = metric_data['Bank'].str.contains('Ecobank', case=False, na=False)
            colors = ['#E24B4A' if is_eco else '#185FA5' for is_eco in metric_data['_is_eco']]

            fig_ind = go.Figure()
            fig_ind.add_bar(
                x=metric_data[sel_metric],
                y=metric_data['Bank'],
                orientation='h',
                marker_color=colors,
                hovertemplate='<b>%{y}</b>: %{x:.1f}<extra></extra>')
            fig_ind.add_vline(x=median_v, line_dash='dash',
                               line_color='#F5A623', line_width=2,
                               annotation_text=f'Median {median_v:.1f}',
                               annotation_position='top left')
            fig_ind.add_vline(x=topq_v, line_dash='dot',
                               line_color='#006B3F', line_width=2,
                               annotation_text=f'Top quartile {topq_v:.1f}',
                               annotation_position='top right')
            fig_ind.update_layout(
                height=max(500, len(metric_data)*18),
                title=f'{sel_metric} — All Kenya banks ({latest_p})',
                xaxis_title=sel_metric,
                yaxis={'categoryorder':'total ascending'},
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_ind, use_container_width=True)

            # Ecobank vs peers summary
            if eco_v is not None:
                rank = int((metric_data[sel_metric] <= eco_v).sum()) \
                       if ECO_BENCHMARKS.get(sel_metric,{}).get('lower_better') \
                       else int((metric_data[sel_metric] >= eco_v).sum())
                total = len(metric_data)
                st.markdown(
                    f"<div style='padding:10px 14px;background:#E8F5EE;"
                    f"border-left:4px solid #006B3F;font-size:12px;margin:8px 0'>"
                    f"Ecobank ranks <b>#{rank} of {total}</b> banks on {sel_metric}: "
                    f"<b>{eco_v:.1f}</b> vs median <b>{median_v:.1f}</b> and top-quartile <b>{topq_v:.1f}</b>."
                    f"</div>", unsafe_allow_html=True)

        # ── TIME SERIES ──────────────────────────────────────
        st.markdown("---")
        st.markdown("#### Ecobank trend vs industry median — over time")
        eco_ts  = ind_df[ind_df['Bank'].str.contains('Ecobank', case=False, na=False)].copy()
        if not eco_ts.empty and sel_metric in eco_ts.columns:
            ind_med_ts = ind_df.groupby('Period')[sel_metric].median().reset_index()
            ind_med_ts.columns = ['Period','Industry Median']
            eco_ts2 = eco_ts[['Period', sel_metric]].rename(columns={sel_metric:'Ecobank'})
            merged_ts = eco_ts2.merge(ind_med_ts, on='Period', how='inner').dropna()

            if len(merged_ts) > 1:
                fig_ts = go.Figure()
                fig_ts.add_scatter(x=merged_ts['Period'], y=merged_ts['Ecobank'],
                                    name='Ecobank', line=dict(color='#E24B4A', width=3),
                                    mode='lines+markers', marker=dict(size=8))
                fig_ts.add_scatter(x=merged_ts['Period'], y=merged_ts['Industry Median'],
                                    name='Industry Median', line=dict(color='#185FA5', width=2, dash='dash'),
                                    mode='lines+markers', marker=dict(size=6))
                fig_ts.update_layout(
                    height=320, title=f'{sel_metric} — Ecobank vs industry median over time',
                    legend=dict(orientation='h', y=-0.2),
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_ts, use_container_width=True)

    else:
        # Static benchmarks when no industry file
        st.markdown("#### Ecobank vs industry — key gaps")
        gap_data = []
        for metric, vals in ECO_BENCHMARKS.items():
            lb = vals['lower_better']
            eco, med, topq = vals['eco'], vals['median'], vals['top_q']
            gap = eco - med
            status = ('🔴 Needs attention' if (lb and eco > med) or (not lb and eco < med) else '✅ Above median')
            impact = '🔥 Critical gap' if abs(gap) > 15 else ('⚠️ Moderate gap' if abs(gap) > 5 else '✅ Small gap')
            gap_data.append({
                'Metric': metric.split('(')[0].strip(),
                'Ecobank': f"{eco:.1f}%",
                'Industry Median': f"{med:.1f}%",
                'Top Quartile': f"{topq:.1f}%",
                'Gap vs Median': f"{gap:+.1f}pp",
                'Status': status,
                'Priority': impact,
            })
        gap_df = pd.DataFrame(gap_data)
        def hl_status(v):
            if '🔴' in str(v) or '🔥' in str(v): return 'color:#E24B4A;font-weight:600'
            if '⚠️' in str(v): return 'color:#F5A623'
            return 'color:#006B3F;font-weight:500'
        st.dataframe(
            gap_df.style.map(hl_status, subset=['Status','Priority']),
            use_container_width=True, hide_index=True)

        st.markdown(
            "<div style='padding:12px 16px;background:#FFFBF0;"
            "border-left:4px solid #F5A623;border-radius:0 8px 8px 0;margin:12px 0'>"
            "<b>💡 The LDR opportunity:</b> Ecobank's LDR of 21.8% vs industry median of 63.2% "
            "is the most significant strategic gap. The bank has KES 90B+ in deposits but deploys "
            "less than a quarter into loans. Every 10pp increase in LDR at a 13% lending rate "
            "adds approximately KES 1.2B in annual NII — without acquiring a single new customer."
            "</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — TURNAROUND PROPOSITIONS
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Turnaround propositions")
    st.caption("Data-driven recommendations based on branch P&L position and industry benchmarks.")

    if not branch_pnl.empty:
        loss_br = branch_pnl[branch_pnl['PBT (M)'] < 0]
        high_cir = branch_pnl[(branch_pnl['CIR %'] > 80) & (branch_pnl['PBT (M)'] >= 0)]

        if len(loss_br):
            st.markdown(f"#### 🔴 Loss-making branches ({len(loss_br)})")
            for _, row in loss_br.iterrows():
                pbt_gap = abs(row['PBT (M)'])
                cir_v   = row.get('CIR %', 0)
                st.markdown(
                    f"<div style='padding:10px 14px;background:#FFF0F0;"
                    f"border-left:5px solid #E24B4A;border-radius:0 8px 8px 0;margin:6px 0'>"
                    f"<b>{row['Branch']}</b> ({row['Region']}) — "
                    f"PBT: <b style='color:#E24B4A'>−KES {pbt_gap:.1f}M</b> | "
                    f"CIR: {cir_v:.1f}% | Avg BSC: {row.get('Avg BSC',0):.2f}<br>"
                    f"<span style='font-size:11px;color:#666'>"
                    f"<b>Recommended actions:</b> (1) Urgent CIR review — identify top 3 opex lines. "
                    f"(2) Revenue sprint: DSO activation drive targeting deposits and fees. "
                    f"(3) BSC review for BM and BCM — link recovery to performance plan. "
                    f"(4) Consider loan push campaign — LDR likely below 30%."
                    f"</span></div>", unsafe_allow_html=True)

        if len(high_cir):
            st.markdown(f"#### 🟠 High CIR branches — profitable but inefficient ({len(high_cir)})")
            for _, row in high_cir.iterrows():
                saving = (row['CIR %'] - 69.6) / 100 * max(row.get('Total Income (M)', 10), 1)
                st.markdown(
                    f"<div style='padding:8px 14px;background:#FFFBF0;"
                    f"border-left:4px solid #F5A623;border-radius:0 6px 6px 0;margin:4px 0;font-size:12px'>"
                    f"<b>{row['Branch']}</b> — CIR: {row['CIR %']:.1f}% | "
                    f"Closing to industry median would add ~KES {saving:.1f}M to PBT. "
                    f"Review: staff cost ratio, premises cost, digital migration rate."
                    f"</div>", unsafe_allow_html=True)

        # Strategic turnaround playbook from industry insights
        st.markdown("---")
        st.markdown("#### Industry-informed turnaround playbook")
        playbook = [
            ("1", "Loan book deployment", "🔥 Critical",
             f"LDR at 21.8% vs industry median 63.2% — the most urgent gap. "
             "Deploy KES 4–6B in new loans over 6 months targeting mid-market SME and mortgage. "
             "Every KES 1B deployed at 13% NIM generates KES 32.5M per quarter in NII."),
            ("2", "CIR reduction programme", "🔥 Critical",
             f"At 80.6% CIR vs {ECO_BENCHMARKS['Cost-to-Income Ratio (CIR)']['median']:.1f}% median, "
             "a 10pp CIR reduction on the current income base saves ~KES 124M quarterly. "
             "Focus: technology spend rationalisation, staff productivity uplift, digital migration."),
            ("3", "Digital revenue acceleration", "⚠️ High",
             "DFS Revenue and Digital Acquiring are underpenetrated relative to customer base. "
             "A 6-week DFS activation campaign targeting inactive digital customers "
             "historically yields 15–25% reactivation at near-zero marginal cost."),
            ("4", "Fee income optimisation", "⚠️ High",
             "Fees & Commissions and Trade Finance are below peer median relative to loan book size. "
             "Introduce value-added bundles (insurance + account + DFS) to cross-sell on existing customers. "
             "Target: NFI/Total Income ratio from current level to 45% (industry median: 52%)."),
            ("5", "NPL containment", "✅ Maintain",
             f"NPL at 14.5% is better than industry median of {ECO_BENCHMARKS['NPL Ratio']['median']:.1f}%. "
             "Maintain DRU capacity and early-warning system. "
             "Avoid aggressive loan push without adequate credit underwriting — "
             "LDR uplift must not sacrifice asset quality."),
        ]
        for num, title, priority, desc in playbook:
            pclr = '#E24B4A' if '🔥' in priority else ('#F5A623' if '⚠️' in priority else '#006B3F')
            st.markdown(
                f"<div style='padding:10px 14px;background:var(--color-background-secondary);"
                f"border-left:5px solid {pclr};border-radius:0 8px 8px 0;margin:6px 0'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<b style='font-size:13px'>{num}. {title}</b>"
                f"<span style='font-size:11px;color:{pclr};font-weight:600'>{priority}</span>"
                f"</div>"
                f"<div style='font-size:12px;color:#555;margin-top:4px'>{desc}</div>"
                f"</div>", unsafe_allow_html=True)
    else:
        st.info("Upload BSC data to see turnaround propositions.")
