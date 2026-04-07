"""pages/6_integrate.py — Integrate: MD & Executive Command Centre."""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state
try:
    _ = LEAVE_TYPES
except NameError:
    LEAVE_TYPES = {}

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores",  pd.DataFrame())
df_proc      = st.session_state.get("df_processed",  pd.DataFrame())
filtered     = st.session_state.get("filtered_staff", pd.DataFrame())
all_months   = st.session_state.get("all_months",    [])
active_months= st.session_state.get("active_months", [])

now          = datetime.now()
month_label  = now.strftime('%B %Y')
m_elapsed    = max(1, now.month)
m_remaining  = max(1, 12 - now.month)

# ── HELPERS ──────────────────────────────────────────────────────────
def fmt_pct(p): return f"{p:.1f}%"

# ── LOCAL HELPERS (depend on df_proc session state) ─────────────────
def kpi_total(names, field='YTD_Actual'):
    """Sum a KPI field across all rows matching names."""
    if df_proc.empty: return 0.0
    col = field if field in df_proc.columns else ('Annual Actual' if field == 'YTD_Actual' else field)
    if col not in df_proc.columns: return 0.0
    return float(df_proc[df_proc['KPI'].isin(names)][col].sum())

def ach(act, tgt):
    return round(act / tgt * 100, 1) if tgt else 0.0

def traffic(pct):
    if pct >= 90: return '#006B3F', '🟢'
    if pct >= 70: return '#BA7517', '🟡'
    return '#E24B4A', '🔴'

def eoy_est(act):
    return round((act / m_elapsed) * 12, 0) if m_elapsed else 0

# ── PERFORM DATA ──────────────────────────────────────────────────────
total_staff  = len(staff_scores) if len(staff_scores) else 0
avg_bsc      = round(staff_scores['Final_BSC_Score'].mean(), 2) if len(staff_scores) else 0
exceeded     = int((staff_scores['Final_BSC_Score'] >= 3.1).sum()) if len(staff_scores) else 0
at_risk      = int((staff_scores['Final_BSC_Score'] <  2.5).sum()) if len(staff_scores) else 0
below_target = int(staff_scores['Final_BSC_Score'].between(2.5, 3.0).sum()) if len(staff_scores) else 0
on_target    = int(staff_scores['Final_BSC_Score'].between(3.0, 3.1).sum()) if len(staff_scores) else 0

# Region performance
has_region  = 'Region' in staff_scores.columns
region_bsc  = {}
if has_region:
    for rgn in REGIONS:
        rg_df = staff_scores[staff_scores['Region'] == rgn]
        region_bsc[rgn] = round(rg_df['Final_BSC_Score'].mean(), 2) if len(rg_df) else 0

# ── KPI FINANCIAL TOTALS ──────────────────────────────────────────────
dep_act  = kpi_total(['Deposit Growth'])
dep_tgt  = kpi_total(['Deposit Growth'],              'Annual Target')
loan_act = kpi_total(['Loans Disbursement','Loan Book Growth'])
loan_tgt = kpi_total(['Loans Disbursement','Loan Book Growth'], 'Annual Target')
nfi_act  = kpi_total(['Fees and Commission','Bancassurance','DFS Revenue','Treasury'])
nfi_tgt  = kpi_total(['Fees and Commission','Bancassurance','DFS Revenue','Treasury'], 'Annual Target')
pbt_act  = kpi_total(['PBT'])
pbt_tgt  = kpi_total(['PBT'],                         'Annual Target')
cust_act = kpi_total(['Customer Growth'])
cust_tgt = kpi_total(['Customer Growth'],             'Annual Target')
dfs_act  = kpi_total(['DFS Revenue'])
dfs_tgt  = kpi_total(['DFS Revenue'],                 'Annual Target')

# ── EXECUTE DATA ──────────────────────────────────────────────────────
all_inits    = em.get_initiatives(status='All')
g_counts     = em.gate_counts()
g3_inits     = [i for i in all_inits if i.get('gate')=='G3']
g4_inits     = [i for i in all_inits if i.get('gate')=='G4']
g5_inits     = [i for i in all_inits if i.get('gate')=='G5']
all_ms       = [m for i in g3_inits for m in i.get('milestones',[])]
ms_done      = sum(1 for m in all_ms if m.get('status')=='Complete')
ms_critical  = sum(1 for m in all_ms if ExecuteManager._escalation_level(m) >= 3)
esc_buckets  = em.get_escalation_dashboard(all_inits)
critical_esc = len(esc_buckets.get(4,[])) + len(esc_buckets.get(3,[]))
exec_health  = round(ms_done / len(all_ms) * 100, 0) if all_ms else 100

# Execute: turnaround initiatives (from SBU page)
turnaround_inits = [i for i in all_inits
                    if any(t in i.get('tags',[]) for t in ('turnaround','operating-leverage','cir'))]

# ── PIPELINE DATA ─────────────────────────────────────────────────────
ri_deals   = ri_pm.get_deals()
ri_summary = ri_pm.category_summary(
    ri_deals,
    {cat: kpi_total(cfg['kpis'])                for cat, cfg in RI_CATEGORIES.items()},
    {cat: kpi_total(cfg['kpis'],'Annual Target') for cat, cfg in RI_CATEGORIES.items()},
)
total_pip_wtd = sum(s['pipeline_wtd']  for s in ri_summary.values())
total_won_ytd = sum(s['won_ytd']       for s in ri_summary.values())

# ── SBU DATA (from session if financials were uploaded) ───────────────
sbu_pnl_cached = st.session_state.get('sbu_pnl_data', pd.DataFrame())

# ── PRODUCT DATA ──────────────────────────────────────────────────────
all_products  = prod_m.get_products()
at_risk_prods = [p for p in all_products if p.get('health') == 'At risk']
pilot_prods   = [p for p in all_products if p.get('lifecycle_stage') == 'Pilot']
active_prods  = [p for p in all_products if p.get('lifecycle_stage') in
                 ('Active','Growth','Optimising','Launch')]

# ── INTEGRATION SIGNALS ───────────────────────────────────────────────
rev_kpi_names = {k for cfg in RI_CATEGORIES.values() for k in cfg['kpis']}
rev_linked    = [i for i in g4_inits+g5_inits
                 if any(k in rev_kpi_names for k in i.get('impact_kpis',[]))]

if len(staff_scores) and 'Unit' in staff_scores.columns:
    weak_units: set  = set(str(u) for u in staff_scores[staff_scores['Final_BSC_Score']<2.5]['Unit'].dropna().unique())
    delayed_ws: set  = set(str(i.get('workstream','')).split('—')[-1].strip()
                       for i in all_inits if any(m.get('status')=='Delayed' for m in i.get('milestones',[])))
    double_risk: set = weak_units & delayed_ws
else:
    double_risk: set = set()

# Branch profitability signal (from SBU page action plans)
action_plans  = st.session_state.get('sbu_action_plans', {})
branches_with_plans  = len([k for k,v in action_plans.items() if v])
open_actions  = sum(1 for plans in action_plans.values()
                    for a in plans if a.get('status') not in ('Complete',))
overdue_actions = sum(1 for plans in action_plans.values()
                      for a in plans
                      if a.get('due','9999') < str(date.today()) and
                      a.get('status') not in ('Complete',))

# ════════════════════════════════════════════════════════════════
# HEADER — Ecobank branded command centre
# ════════════════════════════════════════════════════════════════
clr_pbt, ico_pbt = traffic(ach(pbt_act, pbt_tgt))
clr_dep, ico_dep = traffic(ach(dep_act, dep_tgt))
clr_loan,ico_loan= traffic(ach(loan_act,loan_tgt))

st.markdown(
    f"<div style='padding:18px 24px;background:#006B3F;"
    f"border-radius:12px;margin-bottom:20px;"
    f"display:flex;justify-content:space-between;align-items:center'>"
    f"<div>"
    f"<div style='color:white;font-size:20px;font-weight:500'>A2Z Blueprint — Executive Command Centre</div>"
    f"<div style='color:#9FE1CB;font-size:12px;margin-top:4px'>"
    f"Perform · SBU · Execute · Pipeline · Products &nbsp;|&nbsp; {month_label} &nbsp;|&nbsp; "
    f"{total_staff} staff · {len(all_inits)} initiatives · {len(ri_deals)} pipeline deals · "
    f"{len(all_products)} products registered</div>"
    f"</div>"
    f"<div style='display:flex;gap:18px;font-size:13px;align-items:center'>"
    f"<span style='color:white'>{ico_dep} Deposits <b>{ach(dep_act,dep_tgt):.0f}%</b></span>"
    f"<span style='color:white'>{ico_loan} Loans <b>{ach(loan_act,loan_tgt):.0f}%</b></span>"
    f"<span style='color:white'>{ico_pbt} PBT <b>{ach(pbt_act,pbt_tgt):.0f}%</b></span>"
    f"<span style='background:#F5A623;color:#3D2600;padding:4px 10px;"
    f"border-radius:6px;font-weight:500;font-size:12px'>"
    f"{'🚨 ' + str(critical_esc) + ' escalation(s)' if critical_esc else '✅ No escalations'}</span>"
    f"</div></div>",
    unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# DASHBOARD TABS
# ════════════════════════════════════════════════════════════════
dash_tabs = st.tabs([
    "📊 P&L overview",
    "🏦 SBU performance",
    "👥 People & execution",
    "💼 Pipeline & products",
    "🔗 Live signals",
    "📋 Board pack",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — P&L OVERVIEW
# ════════════════════════════════════════════════════════════════
with dash_tabs[0]:
    st.markdown("#### P&L & balance sheet — institution wide")

    def kpi_card(label, actual, target, unit='KES', sub=None):
        pct = ach(actual, target)
        clr, ico = traffic(pct)
        gap = max(0, target - actual)
        bar = min(100, pct)
        eoy = eoy_est(actual)
        sub_html = f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:2px'>{sub}</div>" if sub else ""
        return (
            f"<div style='padding:14px 16px;background:var(--color-background-secondary);"
            f"border-radius:10px;border:0.5px solid var(--color-border-tertiary);height:100%'>"
            f"<div style='font-size:10px;color:var(--color-text-tertiary);text-transform:uppercase;"
            f"letter-spacing:.6px;margin-bottom:6px'>{label}</div>"
            f"<div style='font-size:22px;font-weight:500'>{ico} {fmt_num(actual,True)}</div>"
            f"<div style='font-size:11px;color:var(--color-text-secondary);margin:2px 0'>"
            f"Target: {fmt_num(target,True)} {unit}</div>"
            f"{sub_html}"
            f"<div style='height:5px;background:var(--color-border-tertiary);"
            f"border-radius:3px;margin:8px 0 4px'>"
            f"<div style='width:{bar:.0f}%;height:100%;background:{clr};border-radius:3px'></div></div>"
            f"<div style='display:flex;justify-content:space-between;font-size:11px'>"
            f"<span style='color:{clr};font-weight:500'>{pct:.1f}%</span>"
            f"<span style='color:var(--color-text-tertiary)'>EOY: {fmt_num(eoy,True)}</span></div>"
            f"{'<div style=\"font-size:11px;color:#E24B4A;margin-top:3px\">Gap: '+fmt_num(gap,True)+'</div>' if gap>0 else ''}"
            f"</div>")

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.markdown(kpi_card("Deposits", dep_act,  dep_tgt,  sub=f"SBU: Retail Banking"), unsafe_allow_html=True)
    c2.markdown(kpi_card("Loans",    loan_act, loan_tgt, sub=f"SBU: SME + Corporate"), unsafe_allow_html=True)
    c3.markdown(kpi_card("NFI",      nfi_act,  nfi_tgt,  sub="Fees + DFS + Banca"), unsafe_allow_html=True)
    c4.markdown(kpi_card("DFS revenue", dfs_act, dfs_tgt, sub="Digital & Channels SBU"), unsafe_allow_html=True)
    c5.markdown(kpi_card("PBT",      pbt_act,  pbt_tgt,  sub="All SBUs combined"), unsafe_allow_html=True)
    c6.markdown(kpi_card("Customers",cust_act, cust_tgt, unit='', sub="New accounts opened"), unsafe_allow_html=True)

    st.markdown("---")

    # Revenue vs target waterfall per KPI category
    chart_data = [
        {'KPI':'Deposits','Actual':dep_act,'Target':dep_tgt,'EOY':eoy_est(dep_act)},
        {'KPI':'Loans',   'Actual':loan_act,'Target':loan_tgt,'EOY':eoy_est(loan_act)},
        {'KPI':'NFI',     'Actual':nfi_act,'Target':nfi_tgt,'EOY':eoy_est(nfi_act)},
        {'KPI':'DFS',     'Actual':dfs_act,'Target':dfs_tgt,'EOY':eoy_est(dfs_act)},
        {'KPI':'PBT',     'Actual':pbt_act,'Target':pbt_tgt,'EOY':eoy_est(pbt_act)},
    ]
    ch_df = pd.DataFrame(chart_data)
    ch1, ch2 = st.columns(2)
    with ch1:
        fig = px.bar(ch_df.melt(id_vars='KPI',value_vars=['Actual','Target','EOY'],
                                var_name='Type',value_name='Value'),
                     x='KPI', y='Value', color='Type', barmode='group',
                     title='Actual vs target vs EOY forecast',
                     color_discrete_map={'Actual':'#006B3F','Target':'#D3D1C7','EOY':'#F5A623'})
        fig.update_layout(height=300, showlegend=True,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            yaxis_tickformat=',.0f', margin=dict(l=0,r=0,t=40,b=0))
        st.plotly_chart(fig, use_container_width=True)

    with ch2:
        # Gap coverage stacked bar
        gap_rows = []
        for _, r in ch_df.iterrows():
            tgt = r['Target']
            if tgt <= 0: continue
            done  = min(100, ach(r['Actual'], tgt))
            pip   = min(100-done, ach(total_pip_wtd/max(1,len(chart_data)), tgt))
            gap   = max(0, 100 - done - pip)
            gap_rows.append({'KPI':r['KPI'],'Achieved':done,'Pipeline':pip,'Gap':gap})
        if gap_rows:
            gdf = pd.DataFrame(gap_rows)
            fig2 = px.bar(gdf, x='KPI', y=['Achieved','Pipeline','Gap'],
                          title='Gap coverage (% of annual target)',
                          color_discrete_map={'Achieved':'#006B3F','Pipeline':'#85B7EB','Gap':'#E24B4A'},
                          barmode='stack')
            fig2.update_layout(height=300, yaxis_title='% of target', yaxis_range=[0,110],
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0,r=0,t=40,b=0), showlegend=True)
            st.plotly_chart(fig2, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — SBU PERFORMANCE
# ════════════════════════════════════════════════════════════════
with dash_tabs[1]:
    st.markdown("#### SBU performance — four business units")
    st.caption("Based on BSC KPI actuals mapped to each SBU. "
               "Upload the Financials Excel in Operating Leverage for full P&L.")

    SBU_MAP = {
        'Retail Banking': {
            'kpis':['Deposit Growth','Customer Growth','Bancassurance'],
            'head':'Director Retail','color':'#006B3F','bg':'#E8F5EE',
            'branches': [u for u,r in BRANCH_REGION.items()],
        },
        'SME & Commercial': {
            'kpis':['Loans Disbursement','Loan Book Growth','Fees and Commission'],
            'head':'Director Commercial Banking','color':'#185FA5','bg':'#E6F1FB',
            'branches':[],
        },
        'Corporate & Institutional': {
            'kpis':['Trade Finance','Treasury'],
            'head':'Head of Corporate','color':'#534AB7','bg':'#EEEDFE',
            'branches':[],
        },
        'Digital & Channels (DFS)': {
            'kpis':['DFS Revenue','Digital Transaction Migration'],
            'head':'Head of Digital Innovation','color':'#BA7517','bg':'#FAEEDA',
            'branches':[],
        },
    }

    sbu_cols = st.columns(4)
    for ci, (sbu_name, sbu_cfg) in enumerate(SBU_MAP.items()):
        kpi_rows = df_proc[df_proc['KPI'].isin(sbu_cfg['kpis'])] if not df_proc.empty else pd.DataFrame()
        sbu_act = float(kpi_rows['YTD_Actual'].sum()) if len(kpi_rows) else 0
        sbu_tgt = float(kpi_rows['Annual Target'].sum()) if len(kpi_rows) else 0
        sbu_pct = ach(sbu_act, sbu_tgt)
        clr, ico = traffic(sbu_pct)

        # PBT for this SBU's branches
        if sbu_name == 'Retail Banking' and 'Unit' in df_proc.columns:
            br_units = list(BRANCH_REGION.keys())
            pbt_rows = df_proc[(df_proc['Unit'].isin(br_units)) & (df_proc['KPI']=='PBT')]
            sbu_pbt  = float(pbt_rows['YTD_Actual'].sum())
        else:
            pbt_rows = df_proc[df_proc['KPI']=='PBT'] if not df_proc.empty else pd.DataFrame()
            sbu_pbt  = 0

        with sbu_cols[ci]:
            st.markdown(
                f"<div style='padding:14px;background:{sbu_cfg['bg']};"
                f"border-left:4px solid {sbu_cfg['color']};border-radius:0 8px 8px 0;"
                f"margin-bottom:8px'>"
                f"<div style='font-size:11px;color:{sbu_cfg['color']};font-weight:500;"
                f"margin-bottom:6px'>{sbu_name}</div>"
                f"<div style='font-size:10px;color:var(--color-text-tertiary);margin-bottom:8px'>"
                f"{sbu_cfg['head']}</div>"
                f"<div style='font-size:20px;font-weight:500'>{ico} {sbu_pct:.0f}%</div>"
                f"<div style='font-size:11px;color:var(--color-text-secondary)'>"
                f"{fmt_num(sbu_act,True)} / {fmt_num(sbu_tgt,True)}</div>"
                f"<div style='height:4px;background:var(--color-border-tertiary);"
                f"border-radius:2px;margin:8px 0 4px'>"
                f"<div style='width:{min(100,sbu_pct):.0f}%;height:100%;"
                f"background:{clr};border-radius:2px'></div></div>"
                f"<div style='font-size:10px;color:var(--color-text-tertiary)'>"
                f"KPIs: {', '.join(sbu_cfg['kpis'][:2])}"
                f"{'...' if len(sbu_cfg['kpis'])>2 else ''}</div>"
                f"</div>",
                unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("#### Branch profitability — Retail SBU")

    # Region rollup
    if has_region and not df_proc.empty and 'Unit' in df_proc.columns:
        region_cols = st.columns(3)
        for ri, rgn in enumerate(REGIONS):
            rgn_branches = [u for u,r in BRANCH_REGION.items() if r==rgn]
            rgn_pbt = df_proc[(df_proc['Unit'].isin(rgn_branches)) & (df_proc['KPI']=='PBT')]
            rgn_dep = df_proc[(df_proc['Unit'].isin(rgn_branches)) & (df_proc['KPI']=='Deposit Growth')]
            pbt_v   = float(rgn_pbt['YTD_Actual'].sum())
            pbt_t   = float(rgn_pbt['Annual Target'].sum())
            dep_v   = float(rgn_dep['YTD_Actual'].sum())
            n_branches = len(rgn_branches)
            pbt_pct = ach(pbt_v, pbt_t)
            rclr, rico = traffic(pbt_pct)
            # Regional head BSC
            rh_bsc = region_bsc.get(rgn, 0)
            with region_cols[ri]:
                st.markdown(
                    f"<div style='padding:12px 14px;background:var(--color-background-secondary);"
                    f"border-radius:8px;border:0.5px solid var(--color-border-tertiary)'>"
                    f"<div style='font-weight:500;font-size:13px;color:#006B3F'>{rgn} Region</div>"
                    f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-bottom:8px'>"
                    f"{n_branches} branches</div>"
                    f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>"
                    f"<div><div style='font-size:16px;font-weight:500'>{rico} {pbt_pct:.0f}%</div>"
                    f"<div style='font-size:10px;color:var(--color-text-tertiary)'>PBT achievement</div></div>"
                    f"<div><div style='font-size:16px;font-weight:500'>{rh_bsc:.2f}</div>"
                    f"<div style='font-size:10px;color:var(--color-text-tertiary)'>Reg. Head BSC</div></div>"
                    f"<div><div style='font-size:14px'>{fmt_num(pbt_v,True)}</div>"
                    f"<div style='font-size:10px;color:var(--color-text-tertiary)'>PBT actual</div></div>"
                    f"<div><div style='font-size:14px'>{fmt_num(dep_v,True)}</div>"
                    f"<div style='font-size:10px;color:var(--color-text-tertiary)'>Deposits</div></div>"
                    f"</div></div>",
                    unsafe_allow_html=True)

    # Branch P&L heatmap
    if not df_proc.empty and 'Unit' in df_proc.columns:
        branch_kpis = ['Deposit Growth','Loans Disbursement','Fees and Commission','PBT']
        br_pivot = {}
        for branch in BRANCH_REGION:
            br_rows = df_proc[df_proc['Unit']==branch]
            row = {}
            for kpi in branch_kpis:
                k = br_rows[br_rows['KPI']==kpi]
                if len(k):
                    tgt = float(k['Annual Target'].values[0])
                    act = float(k['YTD_Actual'].values[0])
                    row[kpi] = round(act/tgt*100,1) if tgt else 0
                else:
                    row[kpi] = 0
            br_pivot[branch] = row
        if br_pivot:
            hm = pd.DataFrame(br_pivot).T
            hm.columns = ['Deposits %','Loans %','NFI %','PBT %']
            fig_hm = px.imshow(hm.T,
                color_continuous_scale=[[0,'#E24B4A'],[0.5,'#F5A623'],[1,'#006B3F']],
                text_auto='.0f', aspect='auto',
                title='Branch performance heatmap — % of annual target')
            fig_hm.update_layout(height=220, margin=dict(l=0,r=0,t=40,b=0),
                coloraxis_colorbar_title='%')
            st.plotly_chart(fig_hm, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 3 — PEOPLE & EXECUTION
# ════════════════════════════════════════════════════════════════
with dash_tabs[2]:
    st.markdown("#### People Intelligence & Target Cascade — MD View")
    st.caption(f"As at {datetime.now().strftime('%d %b %Y')} · Upload BSC data to refresh")

    # ── TOP SUMMARY ROW ──────────────────────────────────────────
    hr_exits_12m   = len(hr_m.get_exits(12))    if hr_m else 0
    hr_pips        = len(hr_m.get_active_pips()) if hr_m else 0
    hr_disc        = len(hr_m.get_active_cases()) if hr_m else 0
    hr_on_leave    = len(lm.get_active_leave())  if lm  else 0

    sc1,sc2,sc3,sc4,sc5,sc6,sc7,sc8 = st.columns(8)
    sc1.metric("Total staff",     total_staff)
    sc2.metric("Avg BSC",         f"{avg_bsc:.2f}")
    sc3.metric("Exceeded",        exceeded)
    sc4.metric("At risk (<2.5)",  at_risk,
               delta=f"-{at_risk}" if at_risk else "0", delta_color="inverse")
    sc5.metric("On leave",        hr_on_leave)
    sc6.metric("Exits (12m)",     hr_exits_12m,
               delta=f"-{hr_exits_12m}" if hr_exits_12m else "0", delta_color="inverse")
    sc7.metric("Active PIPs",     hr_pips,
               delta=f"-{hr_pips}" if hr_pips else "0", delta_color="inverse")
    sc8.metric("Disc. cases",     hr_disc,
               delta=f"-{hr_disc}" if hr_disc else "0", delta_color="inverse")

    st.markdown("---")
    pa_col, pb_col = st.columns(2)

    # ── LEFT: PERFORMANCE DISTRIBUTION + REGION BSC ──────────────
    with pa_col:
        st.markdown("**Performance distribution**")
        if len(staff_scores):
            bands = pd.DataFrame([
                {'Band':'Exceeded (≥3.1)', 'Count': exceeded,     'Color':'#006B3F'},
                {'Band':'On target (3.0)', 'Count': on_target,    'Color':'#1D9E75'},
                {'Band':'Below (2.5–3.0)', 'Count': below_target, 'Color':'#F5A623'},
                {'Band':'At risk (<2.5)',  'Count': at_risk,       'Color':'#E24B4A'},
            ])
            fig_b = px.bar(bands, x='Count', y='Band', orientation='h',
                           color='Band', title='Staff performance bands',
                           color_discrete_map={r['Band']:r['Color'] for _,r in bands.iterrows()})
            fig_b.update_layout(height=200, showlegend=False,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0,r=0,t=36,b=0))
            st.plotly_chart(fig_b, use_container_width=True)

        if region_bsc:
            st.markdown("**BSC by region**")
            for rgn, score in region_bsc.items():
                rclr, _ = traffic(score/5*100)
                bar_w = min(100, score/5*100)
                st.markdown(
                    f"<div style='display:flex;justify-content:space-between;"
                    f"align-items:center;padding:5px 0;font-size:12px'>"
                    f"<span style='min-width:100px'>{rgn} Region</span>"
                    f"<div style='flex:1;margin:0 10px;height:6px;"
                    f"background:#EEE;border-radius:3px'>"
                    f"<div style='width:{bar_w:.0f}%;height:100%;"
                    f"background:{rclr};border-radius:3px'></div></div>"
                    f"<span style='color:{rclr};font-weight:600;min-width:36px'>"
                    f"{score:.2f}</span></div>",
                    unsafe_allow_html=True)

        # HR alerts
        hr_alerts = []
        if hr_pips:
            for pip in hr_m.get_active_pips():
                days_left = hr_m.pip_days_remaining(pip)
                if days_left <= 14:
                    hr_alerts.append(f"🚨 PIP deadline: {pip['staff_name']} — {days_left}d left")
        if hr_disc:
            for case in hr_m.get_active_cases():
                try:
                    days_open = (datetime.now()-datetime.fromisoformat(case['recorded_at'])).days
                    if days_open > 30:
                        hr_alerts.append(f"⚠️ Stalled case: {case['staff_name']} ({days_open}d open)")
                except: pass
        if hr_alerts:
            st.markdown("**HR alerts**")
            for a in hr_alerts[:4]:
                st.markdown(
                    f"<div style='padding:5px 10px;background:#FFFBF0;"
                    f"border-left:3px solid #F5A623;font-size:11px;margin:2px 0'>"
                    f"{a}</div>", unsafe_allow_html=True)

    # ── RIGHT: TARGET CASCADE STATUS ─────────────────────────────
    with pb_col:
        st.markdown("**Target cascade status**")
        if casc and casc.cascade:
            # Build cascade summary per level
            cascade_summary = {}
            for key, entry in casc.cascade.items():
                from_code = entry['from_code']
                name_row  = staff_scores[staff_scores['Staff Code'].astype(str)==from_code] if len(staff_scores) else pd.DataFrame()
                from_name = name_row['Staff Name'].values[0] if len(name_row) else from_code
                from_role = name_row['Role'].values[0] if len(name_row) else '—'
                total     = entry['total_target']
                alloc     = entry['allocated_sum']
                cov       = round(alloc/total*100,1) if total else 0
                n_rpt     = len(entry['allocations'])
                kpi       = entry['kpi']

                if from_name not in cascade_summary:
                    cascade_summary[from_name] = {
                        'role': from_role, 'kpis': [], 'min_cov': 100}
                cascade_summary[from_name]['kpis'].append({'kpi':kpi,'cov':cov,'rpts':n_rpt})
                cascade_summary[from_name]['min_cov'] = min(
                    cascade_summary[from_name]['min_cov'], cov)

            # Show each manager's cascade coverage
            for mgr_name, info in list(cascade_summary.items())[:8]:
                min_cov = info['min_cov']
                clr = '#006B3F' if min_cov >= 95 else ('#F5A623' if min_cov >= 50 else '#E24B4A')
                icon = '✅' if min_cov >= 95 else ('⚠️' if min_cov >= 50 else '❌')
                kpi_summary = ', '.join([f"{k['kpi']} {k['cov']:.0f}%"
                                          for k in info['kpis'][:2]])
                st.markdown(
                    f"<div style='padding:7px 10px;background:var(--color-background-secondary);"
                    f"border-left:4px solid {clr};"
                    f"border-radius:0 4px 4px 0;margin:3px 0;font-size:11px'>"
                    f"<div style='display:flex;justify-content:space-between'>"
                    f"<span><b>{mgr_name}</b> "
                    f"<span style='color:#888;font-size:10px'>{info['role']}</span></span>"
                    f"<span style='color:{clr};font-weight:600'>{icon} {min_cov:.0f}% min coverage</span>"
                    f"</div>"
                    f"<div style='color:#888;margin-top:2px'>{kpi_summary}</div>"
                    f"</div>",
                    unsafe_allow_html=True)

            # Managers with no cascade at all
            if len(staff_scores):
                mgr_roles = ['Director Retail','Director Commercial Banking',
                             'Head Of Corporate','Head Of Digital Innovation',
                             'Regional Head','Branch Manager','Head Of SME','Head Of Retail']
                all_mgrs  = staff_scores[staff_scores['Role'].isin(mgr_roles)]['Staff Name'].tolist()
                who_alloc = set(v['from_code'] for v in casc.cascade.values())
                not_alloc = [m for m in all_mgrs
                             if len(staff_scores[staff_scores['Staff Name']==m]) > 0
                             and str(staff_scores[staff_scores['Staff Name']==m]['Staff Code'].values[0])
                             not in who_alloc]
                if not_alloc:
                    st.markdown(
                        f"<div style='padding:8px 10px;background:#FFFBF0;"
                        f"border-left:3px solid #F5A623;font-size:11px;margin-top:8px'>"
                        f"⚠️ <b>{len(not_alloc)} manager(s) not yet cascaded:</b> "
                        f"{', '.join(not_alloc[:5])}"
                        f"{'...' if len(not_alloc)>5 else ''}</div>",
                        unsafe_allow_html=True)

            # Overall cascade coverage chart
            cov_data = []
            for mgr_name, info in cascade_summary.items():
                for k in info['kpis']:
                    cov_data.append({'Manager': mgr_name[:14], 'KPI': k['kpi'],
                                     'Coverage': k['cov']})
            if cov_data:
                cov_df = pd.DataFrame(cov_data)
                fig_cov = px.bar(cov_df, x='Manager', y='Coverage', color='KPI',
                                 barmode='group',
                                 title='Cascade coverage % by manager',
                                 color_discrete_sequence=px.colors.qualitative.Set2)
                fig_cov.add_hline(y=100, line_dash='dot',
                                   line_color='#006B3F', line_width=1)
                fig_cov.update_layout(height=230, yaxis_range=[0,115],
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0,r=0,t=36,b=40), legend=dict(
                        orientation='h', y=-0.25, font=dict(size=9)))
                st.plotly_chart(fig_cov, use_container_width=True)
        else:
            st.info("No cascade allocations recorded yet. "
                    "Line managers should allocate in the Target Cascade page.")

    # ── BOTTOM: EXECUTION + HR TABLE ────────────────────────────
    st.markdown("---")
    ea_col, eb_col = st.columns(2)

    with ea_col:
        st.markdown("**Strategy execution**")
        e1,e2,e3,e4 = st.columns(4)
        e1.metric("Initiatives",   len(all_inits))
        e2.metric("Executing (G3)",len(g3_inits))
        e3.metric("Embedded (G5)", len(g5_inits))
        e4.metric("Critical esc.", critical_esc,
                  delta=f"-{critical_esc}" if critical_esc else "0",
                  delta_color="inverse")

        if any(g_counts.values()):
            gf = pd.DataFrame([
                {'Gate':g,'Count':g_counts.get(g,0),'Color':EXECUTE_GATES[g]['color']}
                for g in GATE_ORDER])
            fig_gf = px.bar(gf, x='Gate', y='Count', color='Gate',
                            title='Initiative gate distribution',
                            color_discrete_map={g:EXECUTE_GATES[g]['color'] for g in GATE_ORDER})
            fig_gf.update_layout(height=180, showlegend=False,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0,r=0,t=36,b=0))
            st.plotly_chart(fig_gf, use_container_width=True)

        if all_ms:
            ms_del = sum(1 for m in all_ms if ExecuteManager._escalation_level(m)>=2)
            st.progress(ms_done/len(all_ms),
                        text=f"{ms_done}/{len(all_ms)} milestones complete · {ms_del} at risk")

        if overdue_actions:
            st.markdown(
                f"<div style='padding:8px 12px;background:#FFFBF0;"
                f"border-left:3px solid #F5A623;border-radius:0 4px 4px 0;font-size:12px'>"
                f"⚠️ <b>{overdue_actions}</b> branch action item(s) overdue</div>",
                unsafe_allow_html=True)

        st.markdown(
            "<div style='padding:10px 14px;background:var(--color-background-secondary);"
            "border-radius:8px;border:0.5px solid var(--color-border-tertiary);margin-top:8px'>"
            "<div style='font-weight:500;font-size:12px;margin-bottom:4px'>"
            "🔍 Competitor Intelligence</div>"
            "<div style='font-size:11px;color:var(--color-text-secondary)'>"
            "Full Kenya banking industry analysis available in Competitor Intel page — "
            "market position, watch list, strategic gaps and board brief."
            "</div></div>",
            unsafe_allow_html=True)

    with eb_col:
        st.markdown("**HR snapshot**")
        # Exits by reason (last 12 months)
        analytics = hr_m.exit_analytics() if hr_m else {}
        if analytics.get('total',0):
            by_r = analytics.get('by_reason',{})
            if by_r:
                ex_df = pd.DataFrame(list(by_r.items()),
                                     columns=['Reason','Count']).sort_values('Count',ascending=False)
                fig_ex = px.bar(ex_df.head(6), x='Count', y='Reason',
                                orientation='h', title='Exits by reason (all time)',
                                color='Count',
                                color_continuous_scale=['#E8F5EE','#006B3F'])
                fig_ex.update_layout(height=200, showlegend=False,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0,r=0,t=36,b=0))
                st.plotly_chart(fig_ex, use_container_width=True)

        # Active PIPs
        if hr_pips:
            st.markdown(f"**Active PIPs ({hr_pips})**")
            for pip in hr_m.get_active_pips():
                days_left = hr_m.pip_days_remaining(pip)
                pct_elapsed = max(0, round((pip['duration_days']-days_left)/pip['duration_days']*100))
                clr = '#E24B4A' if days_left<=7 else ('#F5A623' if days_left<=14 else '#006B3F')
                st.markdown(
                    f"<div style='padding:6px 10px;background:var(--color-background-secondary);"
                    f"border-left:3px solid {clr};border-radius:0 4px 4px 0;"
                    f"font-size:11px;margin:2px 0'>"
                    f"<b>{pip['staff_name']}</b> · {pip['unit']} · "
                    f"{days_left}d remaining ({pct_elapsed}% elapsed)"
                    f"</div>", unsafe_allow_html=True)

        # Currently on leave
        on_leave_now = lm.get_active_leave() if lm else []
        if on_leave_now:
            st.markdown(f"**On leave now ({len(on_leave_now)})**")
            for r in on_leave_now[:5]:
                lt_clr = LEAVE_TYPES.get(r.get('leave_type',''),{}).get('color','#888')
                st.markdown(
                    f"<div style='padding:4px 10px;border-left:3px solid {lt_clr};"
                    f"font-size:11px;margin:2px 0'>"
                    f"<b>{r['staff_name']}</b> — {r['leave_type']} "
                    f"(until {r['end_date']})</div>",
                    unsafe_allow_html=True)

# TAB 4 — PIPELINE & PRODUCTS
# ════════════════════════════════════════════════════════════════
with dash_tabs[3]:
    pp1, pp2 = st.columns(2)

    with pp1:
        st.markdown("#### Revenue pipeline")
        p1,p2,p3 = st.columns(3)
        p1.metric("Active deals",       len(ri_deals))
        p2.metric("Weighted pipeline",  fmt_num(total_pip_wtd, short=True))
        p3.metric("Won YTD",            fmt_num(total_won_ytd, short=True))

        # Category coverage bars
        cat_rows = []
        for cat, s in ri_summary.items():
            if s['annual_target'] > 0:
                pct_a = ach(s['ytd_actual'], s['annual_target'])
                pct_p = min(100-pct_a, ach(s['pipeline_wtd'], s['annual_target']))
                cat_rows.append({
                    'Category': RI_CATEGORIES[cat]['label'][:14],
                    'Achieved': pct_a,
                    'Pipeline': pct_p,
                    'Gap':      max(0, 100-pct_a-pct_p),
                })
        if cat_rows:
            cat_df = pd.DataFrame(cat_rows)
            fig_cat = px.bar(cat_df, x='Category', y=['Achieved','Pipeline','Gap'],
                             title='Pipeline coverage by category',
                             color_discrete_map={'Achieved':'#006B3F','Pipeline':'#85B7EB','Gap':'#E24B4A'},
                             barmode='stack')
            fig_cat.add_hline(y=100, line_dash='dash', line_color='#F5A623',
                               annotation_text='100% target')
            fig_cat.update_layout(height=280, yaxis_title='% of target',
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0,r=0,t=40,b=0), showlegend=True)
            st.plotly_chart(fig_cat, use_container_width=True)

    with pp2:
        st.markdown("#### Product portfolio")
        q1,q2,q3,q4 = st.columns(4)
        q1.metric("Total products",  len(all_products))
        q2.metric("Active",          len(active_prods))
        q3.metric("In pilot",        len(pilot_prods))
        q4.metric("At risk",         len(at_risk_prods),
                  delta=f"-{len(at_risk_prods)}" if at_risk_prods else "0",
                  delta_color="inverse")

        # Category breakdown
        cat_summary = prod_m.category_summary()
        prod_rows = [
            {'Category':cat,'Count':s['count'],'Active':s['active'],
             'At risk':s['at_risk'],'Pilot':s['in_pilot']}
            for cat, s in cat_summary.items() if s['count'] > 0
        ]
        if prod_rows:
            pr_df = pd.DataFrame(prod_rows)
            fig_pr = px.bar(pr_df, x='Category', y=['Active','Pilot','At risk'],
                            title='Product portfolio by category',
                            color_discrete_map={'Active':'#006B3F','Pilot':'#F5A623','At risk':'#E24B4A'},
                            barmode='stack')
            fig_pr.update_layout(height=280,
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                margin=dict(l=0,r=0,t=40,b=0), showlegend=True)
            st.plotly_chart(fig_pr, use_container_width=True)
        else:
            st.info("No products registered yet — add them in the Products module.")

        # At-risk products
        if at_risk_prods:
            st.markdown("**Products requiring attention:**")
            for p in at_risk_prods[:3]:
                st.markdown(
                    f"<div style='font-size:12px;padding:4px 0;"
                    f"color:var(--color-text-secondary)'>"
                    f"⚠️ {p['name']} ({p['category']} · {p.get('lifecycle_stage','')}) "
                    f"— owner: {p.get('owner','—')}</div>",
                    unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — INTEGRATION SIGNALS
# ════════════════════════════════════════════════════════════════
with dash_tabs[4]:
    st.markdown("#### Integration signals — live cross-module intelligence")
    st.caption("Real-time signals from all 17 modules. Amber/red items require MD attention.")

    # ── NEW MODULE SIGNALS ────────────────────────────────────────
    # CIMS signal
    cims_mgr = st.session_state.get("cims_manager")
    if cims_mgr:
        cims_open    = len([t for t in cims_mgr.tickets if t.get("status") not in ("Resolved","Cancelled")])
        cims_overdue = 0
        now_dt = datetime.now()
        for t in cims_mgr.tickets:
            if t.get("status") not in ("Resolved","Cancelled") and t.get("due_at"):
                try:
                    if now_dt > datetime.fromisoformat(t["due_at"][:19]): cims_overdue += 1
                except: pass
        cims_resolved = [t for t in cims_mgr.tickets if t.get("status")=="Resolved"]
        cims_breached = sum(1 for t in cims_resolved if t.get("breached"))
        cims_score    = (len(cims_resolved)-cims_breached)/max(len(cims_resolved),1)
        cims_clr = '#006B3F' if cims_score>=0.9 else ('#F5A623' if cims_score>=0.75 else '#E24B4A')
        st.markdown(
            f"<div style='padding:8px 14px;background:var(--color-background-secondary);"
            f"border-left:4px solid {cims_clr};border-radius:0 6px 6px 0;margin:3px 0'>"
            f"<div style='display:flex;justify-content:space-between;font-size:12px'>"
            f"<span>📨 <b>CIMS</b> — TAT Score: <b style='color:{cims_clr}'>{cims_score:.1%}</b> | "
            f"Open: <b>{cims_open}</b> | Overdue: <b style='color:#E24B4A'>{cims_overdue}</b></span>"
            f"<span style='color:{cims_clr}'>{'✅ On track' if cims_score>=0.90 else '⚠️ Below 90% target'}</span>"
            f"</div></div>", unsafe_allow_html=True)

    # SLA Tracker signal
    slm = st.session_state.get("sla_manager")
    if slm:
        sla_anl = slm.analytics()
        sla_open    = sla_anl.get("open", 0)
        sla_score   = sla_anl.get("sla_score", 1.0)
        sla_breached= sla_anl.get("breached", 0)
        sla_clr     = '#006B3F' if sla_score>=0.90 else ('#F5A623' if sla_score>=0.75 else '#E24B4A')
        st.markdown(
            f"<div style='padding:8px 14px;background:var(--color-background-secondary);"
            f"border-left:4px solid {sla_clr};border-radius:0 6px 6px 0;margin:3px 0'>"
            f"<div style='display:flex;justify-content:space-between;font-size:12px'>"
            f"<span>🎯 <b>SLA Tracker</b> — Score: <b style='color:{sla_clr}'>{sla_score:.1%}</b> | "
            f"Open tickets: <b>{sla_open}</b> | Breached: <b>{sla_breached}</b></span>"
            f"<span style='color:{sla_clr}'>"
            f"{'✅ On track' if sla_score>=0.90 else '⚠️ Below 90% target'}</span>"
            f"</div></div>", unsafe_allow_html=True)

    # Branch Daily Log signal
    blm = st.session_state.get("branch_log_manager")
    if blm:
        today_logs  = blm.get_today()
        submitted   = len(today_logs)
        validated   = len([l for l in today_logs if l.get("validated")])
        pending_val = len([l for l in today_logs if not l.get("validated") and not l.get("rejected",False)])
        log_clr     = '#006B3F' if submitted > 0 else '#F5A623'
        st.markdown(
            f"<div style='padding:8px 14px;background:var(--color-background-secondary);"
            f"border-left:4px solid {log_clr};border-radius:0 6px 6px 0;margin:3px 0'>"
            f"<div style='font-size:12px'>"
            f"📝 <b>Branch Daily Log</b> — Today: <b>{submitted}</b> submitted | "
            f"<b>{validated}</b> validated | "
            f"<span style='color:#F5A623'><b>{pending_val}</b> awaiting manager validation</span>"
            f"</div></div>", unsafe_allow_html=True)

    # Campaign signal
    cpm = st.session_state.get("campaign_manager")
    if cpm:
        active_camps = cpm.get_active()
        if active_camps:
            for camp in active_camps:
                total, target, pct = cpm.campaign_progress(camp["id"])
                camp_clr = '#006B3F' if pct>=80 else ('#F5A623' if pct>=50 else '#E24B4A')
                days_left = (date.fromisoformat(camp["end_date"]) - date.today()).days
                st.markdown(
                    f"<div style='padding:8px 14px;background:var(--color-background-secondary);"
                    f"border-left:4px solid {camp_clr};border-radius:0 6px 6px 0;margin:3px 0'>"
                    f"<div style='font-size:12px'>"
                    f"🚀 <b>Campaign: {camp['name']}</b> — {pct:.0f}% of target | "
                    f"{days_left}d remaining | KPI: {camp.get('kpi_linked','')}"
                    f"</div></div>", unsafe_allow_html=True)
    st.caption("These signals only appear here — they require all three pillars (Perform, Execute, Pipeline) to be active.")

    sig_cols = st.columns(3)

    # Signal 1: Execution → Revenue linkage
    with sig_cols[0]:
        linked_pct = len(rev_linked)/max(1,len(g4_inits)+len(g5_inits))*100
        s_clr = '#006B3F' if linked_pct>=70 else ('#BA7517' if linked_pct>=40 else '#E24B4A')
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {s_clr};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
            f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
            f"Execute → revenue linkage</div>"
            f"<div style='font-size:28px;font-weight:500;color:{s_clr}'>{len(rev_linked)}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"of {len(g4_inits)+len(g5_inits)} active initiatives linked to revenue KPIs</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:6px'>"
            f"{'Good — strategy driving measurable revenue' if linked_pct>=70 else 'Map more initiatives to revenue KPIs'}"
            f"</div></div>",
            unsafe_allow_html=True)

    # Signal 2: Double-risk (low BSC + stalled execution)
    with sig_cols[1]:
        dr_clr = '#E24B4A' if double_risk else '#006B3F'
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {dr_clr};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
            f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
            f"Double-risk units</div>"
            f"<div style='font-size:28px;font-weight:500;color:{dr_clr}'>{len(double_risk)}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"units with low BSC AND stalled execution milestones</div>"
            f"{'<div style=\"font-size:11px;color:#E24B4A;margin-top:4px\">' + ', '.join(str(x) for x in list(double_risk)[:3]) + '</div>' if double_risk else ''}"
            f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:4px'>"
            f"{'Urgent — poor performance and stalled execution' if double_risk else 'No double-risk units'}"
            f"</div></div>",
            unsafe_allow_html=True)

    # Signal 3: SBU action plans vs BSC performance
    with sig_cols[2]:
        ap_clr = '#E24B4A' if overdue_actions>0 else '#006B3F'
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {ap_clr};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
            f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
            f"SBU turnaround tracker</div>"
            f"<div style='font-size:28px;font-weight:500;color:{ap_clr}'>{open_actions}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"open branch action items · {overdue_actions} overdue</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:6px'>"
            f"{branches_with_plans} branches have active turnaround plans</div>"
            f"</div>",
            unsafe_allow_html=True)

    # Row 2 of signals
    st.markdown("---")
    sig2 = st.columns(3)

    # Signal 4: Products linked to initiatives
    prods_with_init = len([p for p in all_products if p.get('linked_initiatives')])
    with sig2[0]:
        p_clr = '#006B3F' if prods_with_init > 0 else '#BA7517'
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {p_clr};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
            f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
            f"Products ↔ initiatives linked</div>"
            f"<div style='font-size:28px;font-weight:500;color:{p_clr}'>{prods_with_init}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"of {len(all_products)} products linked to an Execute initiative</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:6px'>"
            f"{'Link products to initiatives in the Products module' if prods_with_init==0 else 'Execution is connected to product delivery'}"
            f"</div></div>",
            unsafe_allow_html=True)

    # Signal 5: Pipeline vs BSC performance gap
    with sig2[1]:
        low_bsc_units = set(str(u) for u in staff_scores[staff_scores['Final_BSC_Score']<2.8]['Unit'].dropna().unique()) if len(staff_scores) else set()
        conv_gap = len(low_bsc_units)
        cg_clr = '#E24B4A' if conv_gap > 5 else ('#BA7517' if conv_gap > 0 else '#006B3F')
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {cg_clr};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
            f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
            f"Performance conversion gap</div>"
            f"<div style='font-size:28px;font-weight:500;color:{cg_clr}'>{conv_gap}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"units below 2.8 BSC — pipeline not converting to performance</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:6px'>"
            f"{'Review coaching and conversion quality' if conv_gap else 'Performance aligned with activity'}"
            f"</div></div>",
            unsafe_allow_html=True)

    # Signal 6: Operating leverage (from session if loaded)
    with sig2[2]:
        fin_loaded = not sbu_pnl_cached.empty
        ol_clr = '#006B3F' if fin_loaded else '#888780'
        st.markdown(
            f"<div style='padding:14px;background:var(--color-background-secondary);"
            f"border-radius:8px;border-left:4px solid {ol_clr};"
            f"border-top:0.5px solid var(--color-border-tertiary);"
            f"border-right:0.5px solid var(--color-border-tertiary);"
            f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
            f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
            f"Operating leverage status</div>"
            f"<div style='font-size:14px;color:{ol_clr};margin-bottom:6px'>"
            f"{'✅ Financials loaded — view in Operating Leverage page' if fin_loaded else '⏳ Upload SBU Financials Excel to see cost vs revenue growth'}"
            f"</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary)'>"
            f"CIR benchmarks: &lt;55% excellent · 55-65% acceptable · &gt;65% action needed"
            f"</div></div>",
            unsafe_allow_html=True)

    # Critical escalations surface
    if critical_esc > 0 or double_risk or overdue_actions > 0:
        st.markdown("---")
        st.markdown("#### Requires executive attention now")

        if critical_esc > 0:
            st.markdown(
                f"<div style='padding:10px 14px;background:#FFF0F0;"
                f"border-left:4px solid #A32D2D;border-radius:0 6px 6px 0;margin:4px 0'>"
                f"🚨 <b>{critical_esc} milestone(s)</b> at critical escalation — "
                f">7 days overdue or structural delay. Sponsor intervention required.</div>",
                unsafe_allow_html=True)
            for ms in (esc_buckets.get(4,[]) + esc_buckets.get(3,[]))[:4]:
                st.markdown(
                    f"<div style='font-size:12px;padding:4px 12px 4px 24px;"
                    f"color:var(--color-text-secondary);border-left:2px solid #E24B4A;margin:2px 0'>"
                    f"<b>{ms.get('initiative_name','')}</b> → {ms.get('name','')} | "
                    f"Owner: {ms.get('owner','')} | {ms.get('overdue_days',0)}d overdue</div>",
                    unsafe_allow_html=True)

        if overdue_actions > 0:
            st.markdown(
                f"<div style='padding:10px 14px;background:#FFFBF0;"
                f"border-left:4px solid #F5A623;border-radius:0 6px 6px 0;margin:4px 0'>"
                f"⚠️ <b>{overdue_actions} branch action item(s)</b> overdue — "
                f"review in SBU Performance → Action Plans.</div>",
                unsafe_allow_html=True)

        st.markdown("---")
        st.markdown(
            "<div style='padding:12px 16px;background:var(--color-background-secondary);"
            "border-radius:8px;border:0.5px solid var(--color-border-tertiary)'>"
            "<div style='font-weight:500;margin-bottom:6px'>🔍 Competitor Intelligence</div>"
            "<div style='font-size:12px;color:var(--color-text-secondary)'>"
            "Full Kenya banking industry analysis is available in the "
            "<b>Competitor Intel</b> page — market position, watch list, "
            "strategic gaps, and board brief. Upload the Industry Financial "
            "Review Excel to activate."
            "</div></div>",
            unsafe_allow_html=True)

        if double_risk:
            st.markdown(
                f"<div style='padding:10px 14px;background:#FFF0F0;"
                f"border-left:4px solid #E24B4A;border-radius:0 6px 6px 0;margin:4px 0'>"
                f"🔴 <b>Double-risk units: {', '.join(str(x) for x in double_risk)}</b> — "
                f"low BSC AND stalled execution. Urgent review required.</div>",
                unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — BOARD PACK
# ════════════════════════════════════════════════════════════════
with dash_tabs[5]:
    st.markdown("#### Board pack export")
    st.caption("One-click snapshot of all executive metrics for board reporting.")

    # Live preview
    st.markdown("**Q1 2026 — Executive summary preview**")
    preview_data = {
        'Category': ['Financial','Financial','Financial','Financial','Financial',
                     'People','People','People',
                     'Execution','Execution','Execution',
                     'Products','Products'],
        'Metric':   ['Deposits YTD','Loans YTD','NFI YTD','DFS Revenue YTD','PBT YTD',
                     'Total Staff','Avg BSC Score','At-risk staff',
                     'Total Initiatives','Executing (G3)','Embedded (G5)',
                     'Total Products','At-risk Products'],
        'Value':    [fmt_num(dep_act,True), fmt_num(loan_act,True), fmt_num(nfi_act,True),
                     fmt_num(dfs_act,True), fmt_num(pbt_act,True),
                     str(total_staff), f"{avg_bsc:.2f}", str(at_risk),
                     str(len(all_inits)), str(len(g3_inits)), str(len(g5_inits)),
                     str(len(all_products)), str(len(at_risk_prods))],
        'Target':   [fmt_num(dep_tgt,True), fmt_num(loan_tgt,True), fmt_num(nfi_tgt,True),
                     fmt_num(dfs_tgt,True), fmt_num(pbt_tgt,True),
                     '—','3.00','0',
                     '—','—','—',
                     '—','0'],
        'Achievement': [f"{ach(dep_act,dep_tgt):.1f}%", f"{ach(loan_act,loan_tgt):.1f}%",
                        f"{ach(nfi_act,nfi_tgt):.1f}%", f"{ach(dfs_act,dfs_tgt):.1f}%",
                        f"{ach(pbt_act,pbt_tgt):.1f}%",
                        '—',f"{avg_bsc/3*100:.0f}%",
                        '—','—','—','—','—','—'],
    }
    prev_df = pd.DataFrame(preview_data)

    def hl_cat(v):
        if v == 'Financial': return 'background-color:#E8F5EE;color:#006B3F;font-weight:500'
        if v == 'People':    return 'background-color:#E6F1FB;color:#185FA5;font-weight:500'
        if v == 'Execution': return 'background-color:#FAEEDA;color:#BA7517;font-weight:500'
        if v == 'Products':  return 'background-color:#EEEDFE;color:#534AB7;font-weight:500'
        return ''

    st.dataframe(prev_df.style.map(hl_cat, subset=['Category']),
                 use_container_width=True, hide_index=True)

    if st.button("⬇️ Download board pack CSV", type="primary"):
        board_rows = []
        for kpi_name, act, tgt in [
            ('Deposit Growth', dep_act, dep_tgt),
            ('Loans (Disbursements + Book)', loan_act, loan_tgt),
            ('Non-Funded Income', nfi_act, nfi_tgt),
            ('DFS Revenue', dfs_act, dfs_tgt),
            ('Profit Before Tax', pbt_act, pbt_tgt),
            ('New Customers', cust_act, cust_tgt),
        ]:
            board_rows.append({
                'Section':'Financial','Metric':kpi_name,
                'YTD Actual':fmt_num(act),'Annual Target':fmt_num(tgt),
                'Achievement':f"{ach(act,tgt):.1f}%",
                'EOY Forecast':fmt_num(eoy_est(act)),
            })
        for metric, val, tgt in [
            ('Total Staff', total_staff, '—'),
            ('Avg BSC Score', f"{avg_bsc:.2f}", '3.00'),
            ('Exceeded Target (≥3.1)', exceeded, '—'),
            ('At Risk (<2.5)', at_risk, '0'),
        ]:
            board_rows.append({'Section':'People','Metric':metric,
                                'YTD Actual':str(val),'Annual Target':tgt,
                                'Achievement':'—','EOY Forecast':'—'})
        for metric, val in [
            ('Total Initiatives', len(all_inits)),
            ('In Execution (G3)', len(g3_inits)),
            ('Impact Tracking (G4)', len(g4_inits)),
            ('Embedded (G5)', len(g5_inits)),
            ('Critical Escalations', critical_esc),
            ('Turnaround Initiatives', len(turnaround_inits)),
        ]:
            board_rows.append({'Section':'Execution','Metric':metric,
                                'YTD Actual':str(val),'Annual Target':'—',
                                'Achievement':'—','EOY Forecast':'—'})
        for metric, val in [
            ('Products Registered', len(all_products)),
            ('Active Products', len(active_prods)),
            ('In Pilot', len(pilot_prods)),
            ('At Risk', len(at_risk_prods)),
        ]:
            board_rows.append({'Section':'Products','Metric':metric,
                                'YTD Actual':str(val),'Annual Target':'—',
                                'Achievement':'—','EOY Forecast':'—'})
        bp_df = pd.DataFrame(board_rows)
        bp_csv = bp_df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", bp_csv,
                           f"A2Z_BoardPack_{now.strftime('%Y%m%d')}.csv","text/csv")
