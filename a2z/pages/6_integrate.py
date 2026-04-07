"""pages/6_integrate.py — Integrate module."""
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


# ── Data assembly ────────────────────────────────────────────
now         = datetime.now()
month_label = now.strftime('%B %Y')
m_elapsed   = max(1, now.month)
m_remaining = max(1, 12 - now.month)

perf_df  = staff_scores.copy() if 'staff_scores' in st.session_state else pd.DataFrame()
kpi_df   = st.session_state.get('df_processed', pd.DataFrame())
all_inits = em.get_initiatives(status='All')

# ── PERFORM aggregates ────────────────────────────────────────
total_staff    = len(perf_df) if len(perf_df) else 0
avg_bsc        = round(perf_df['Final_BSC_Score'].mean(), 2) if len(perf_df) else 0
exceeded       = int((perf_df['Final_BSC_Score'] >= 3.1).sum()) if len(perf_df) else 0
at_risk        = int((perf_df['Final_BSC_Score'] <  2.5).sum()) if len(perf_df) else 0
on_target      = int((perf_df['Final_BSC_Score'].between(3.0, 3.1)).sum()) if len(perf_df) else 0
below_target   = int((perf_df['Final_BSC_Score'].between(2.5, 3.0)).sum()) if len(perf_df) else 0

# ── KPI financial totals ──────────────────────────────────────
def kpi_total(kpi_names, field='YTD_Actual'):
    if kpi_df.empty: return 0
    return float(kpi_df[kpi_df['KPI'].isin(kpi_names)][field].sum())

dep_actual  = kpi_total(['Deposit Growth'])
dep_target  = kpi_total(['Deposit Growth'], 'Annual Target')
loan_actual = kpi_total(['Loans Disbursement','Loan Book Growth'])
loan_target = kpi_total(['Loans Disbursement','Loan Book Growth'], 'Annual Target')
nfi_actual  = kpi_total(['Fees and Commission','Bancassurance','DFS Revenue','Treasury'])
nfi_target  = kpi_total(['Fees and Commission','Bancassurance','DFS Revenue','Treasury'], 'Annual Target')
pbt_actual  = kpi_total(['PBT'])
pbt_target  = kpi_total(['PBT'], 'Annual Target')
cust_actual = kpi_total(['Customer Growth'])
cust_target = kpi_total(['Customer Growth'], 'Annual Target')
npl_actual  = kpi_total(['NPL','PAR'])
npl_target  = kpi_total(['NPL','PAR'], 'Annual Target')

def ach(act, tgt):
    return round(act/tgt*100, 1) if tgt else 0
def run_rate_eoy(act):
    return round((act / m_elapsed) * 12, 2) if m_elapsed else 0
def traffic(pct):
    if pct >= 90: return '#1D9E75','🟢'
    if pct >= 70: return '#BA7517','🟡'
    return '#E24B4A','🔴'

# ── EXECUTE aggregates ────────────────────────────────────────
g_counts    = em.gate_counts()
g3_inits    = [i for i in all_inits if i.get('gate')=='G3']
g4_inits    = [i for i in all_inits if i.get('gate')=='G4']
g5_inits    = [i for i in all_inits if i.get('gate')=='G5']
all_ms      = [ms for i in g3_inits for ms in i.get('milestones',[])]
ms_done     = sum(1 for m in all_ms if m.get('status')=='Complete')
ms_delayed  = sum(1 for m in all_ms if ExecuteManager._escalation_level(m) >= 2)
ms_critical = sum(1 for m in all_ms if ExecuteManager._escalation_level(m) >= 4)
esc_buckets = em.get_escalation_dashboard(all_inits)
total_esc   = sum(len(v) for v in esc_buckets.values())
critical_esc = len(esc_buckets.get(4, [])) + len(esc_buckets.get(3, []))
exec_health = round((ms_done / len(all_ms) * 100), 0) if all_ms else 100

# ── PIPELINE aggregates ───────────────────────────────────────
ri_deals   = ri_pm.get_deals()
ri_summary = ri_pm.category_summary(
    ri_deals,
    {cat: kpi_total(cfg['kpis']) for cat, cfg in RI_CATEGORIES.items()},
    {cat: kpi_total(cfg['kpis'], 'Annual Target') for cat, cfg in RI_CATEGORIES.items()},
)
total_pip_wtd = sum(s['pipeline_wtd'] for s in ri_summary.values())
total_won     = sum(s['won_ytd']      for s in ri_summary.values())
total_actual_all  = sum(s['ytd_actual']   for s in ri_summary.values()
                        if ri_summary[list(ri_summary.keys())[0]]['unit']=='KES')

# ── INTEGRATION signals ───────────────────────────────────────
# Initiatives at G4/G5 linked to revenue KPIs
revenue_kpi_names = {k for cfg in RI_CATEGORIES.values() for k in cfg['kpis']}
rev_linked = [i for i in g4_inits+g5_inits
              if any(k in revenue_kpi_names for k in i.get('impact_kpis',[]))]

# Branches with low performance AND delayed execution
if len(perf_df) and 'Unit' in perf_df.columns:
    weak_units: set = set(str(u) for u in perf_df[perf_df['Final_BSC_Score'] < 2.5]['Unit'].dropna().unique())
    delayed_ws: set = set(
        str(i.get('workstream','')).split('—')[-1].strip()
        for i in all_inits
        if any(m.get('status')=='Delayed' for m in i.get('milestones',[])))
    double_risk: set = weak_units & delayed_ws
else:
    double_risk = set()

# ════════════════════════════════════════════════════════════════
# DASHBOARD LAYOUT
# ════════════════════════════════════════════════════════════════

# ── HEADER BAR ───────────────────────────────────────────────
clr_pbt, ico_pbt = traffic(ach(pbt_actual, pbt_target))
clr_dep, ico_dep = traffic(ach(dep_actual, dep_target))
clr_loan,ico_loan= traffic(ach(loan_actual, loan_target))

st.markdown(
    f"<div style='padding:18px 22px;background:var(--color-background-secondary);"
    f"border-radius:var(--border-radius-lg);border:0.5px solid var(--color-border-tertiary);"
    f"display:flex;justify-content:space-between;align-items:center;margin-bottom:20px'>"
    f"<div>"
    f"<div style='font-size:20px;font-weight:500'>A2Z — Executive Command Centre</div>"
    f"<div style='font-size:12px;color:var(--color-text-secondary);margin-top:3px'>"
    f"Perform · Execute · Integrate &nbsp;|&nbsp; {month_label} &nbsp;|&nbsp; "
    f"{total_staff} staff &nbsp;·&nbsp; {len(all_inits)} initiatives &nbsp;·&nbsp; "
    f"{len(ri_deals)} pipeline deals</div>"
    f"</div>"
    f"<div style='display:flex;gap:16px;font-size:13px'>"
    f"<span>{ico_dep} Deposits {ach(dep_actual,dep_target):.0f}%</span>"
    f"<span>{ico_loan} Loans {ach(loan_actual,loan_target):.0f}%</span>"
    f"<span>{ico_pbt} PBT {ach(pbt_actual,pbt_target):.0f}%</span>"
    f"<span style='color:{'#E24B4A' if critical_esc else '#1D9E75'}'>"
    f"{'🚨' if critical_esc else '✅'} {critical_esc} critical escalation(s)</span>"
    f"</div></div>",
    unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ROW 1 — THE P&L SNAPSHOT (5 key numbers)
# ════════════════════════════════════════════════════════════════
st.markdown("### P&L & balance sheet snapshot")

def kpi_card(label, actual, target, unit='KES', is_reverse=False):
    pct  = ach(actual, target)
    if is_reverse:
        pct = 100 - pct if pct < 100 else 100
    clr, ico = traffic(100 - pct if is_reverse else pct)
    eoy  = run_rate_eoy(actual)
    gap  = max(0, target - actual)
    bar  = min(100, pct)
    return (
        f"<div style='padding:14px 16px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border:0.5px solid var(--color-border-tertiary);"
        f"height:100%'>"
        f"<div style='font-size:11px;color:var(--color-text-secondary);text-transform:uppercase;"
        f"letter-spacing:.5px;margin-bottom:6px'>{label}</div>"
        f"<div style='font-size:22px;font-weight:500;color:var(--color-text-primary)'>"
        f"{ico} {fmt_num(actual, short=True)}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary);margin:2px 0'>"
        f"Target {fmt_num(target, short=True)} {unit}</div>"
        f"<div style='height:5px;background:var(--color-border-tertiary);"
        f"border-radius:3px;margin:8px 0 4px'>"
        f"<div style='width:{bar:.0f}%;height:100%;background:{clr};border-radius:3px'></div>"
        f"</div>"
        f"<div style='display:flex;justify-content:space-between;font-size:11px'>"
        f"<span style='color:{clr};font-weight:500'>{pct:.1f}%</span>"
        f"<span style='color:var(--color-text-tertiary)'>EOY est. {fmt_num(eoy, short=True)}</span>"
        f"</div>"
        f"{'<div style=\"font-size:11px;color:#E24B4A;margin-top:4px\">Gap: ' + fmt_num(gap, short=True) + '</div>' if gap > 0 else ''}"
        f"</div>")

r1c1,r1c2,r1c3,r1c4,r1c5 = st.columns(5)
r1c1.markdown(kpi_card("Deposits (liabilities)", dep_actual, dep_target), unsafe_allow_html=True)
r1c2.markdown(kpi_card("Loans (assets)",         loan_actual, loan_target), unsafe_allow_html=True)
r1c3.markdown(kpi_card("Non-funded income",       nfi_actual, nfi_target), unsafe_allow_html=True)
r1c4.markdown(kpi_card("PBT",                     pbt_actual, pbt_target), unsafe_allow_html=True)
r1c5.markdown(kpi_card("New customers",           cust_actual, cust_target, unit=''), unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ROW 2 — PEOPLE · PIPELINE · EXECUTION (the three engines)
# ════════════════════════════════════════════════════════════════
st.markdown("### Three engines")

eng1, eng2, eng3 = st.columns(3)

# Engine 1 — People (Perform)
bsc_clr, bsc_ico = traffic(avg_bsc / 5 * 100)
with eng1:
    st.markdown(
        f"<div style='padding:16px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border:0.5px solid var(--color-border-tertiary)'>"
        f"<div style='font-size:13px;font-weight:500;color:#185FA5;margin-bottom:12px'>"
        f"People performance</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>"
        f"<div><div style='font-size:20px;font-weight:500'>{bsc_ico} {avg_bsc:.2f}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>avg BSC score</div></div>"
        f"<div><div style='font-size:20px;font-weight:500'>{total_staff}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>total staff</div></div>"
        f"<div><div style='font-size:18px;font-weight:500;color:#1D9E75'>{exceeded}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>exceeded target</div></div>"
        f"<div><div style='font-size:18px;font-weight:500;color:#E24B4A'>{at_risk}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>at risk (&lt;2.5)</div></div>"
        f"</div></div>",
        unsafe_allow_html=True)

    # Mini performance distribution bar
    if total_staff > 0:
        fig_mini = px.bar(
            pd.DataFrame([
                {'Band':'Exceeded','Count':exceeded,'color':'#1D9E75'},
                {'Band':'On target','Count':on_target,'color':'#F39C12'},
                {'Band':'Below','Count':below_target,'color':'#E67E22'},
                {'Band':'At risk','Count':at_risk,'color':'#E24B4A'},
            ]),
            x='Count', y='Band', orientation='h', color='Band',
            color_discrete_map={'Exceeded':'#1D9E75','On target':'#F39C12',
                                'Below':'#E67E22','At risk':'#E24B4A'},
            title='Distribution')
        fig_mini.update_layout(height=180, showlegend=False, margin=dict(l=0,r=0,t=30,b=0),
                               plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        fig_mini.update_xaxes(showgrid=False)
        st.plotly_chart(fig_mini, use_container_width=True)

# Engine 2 — Pipeline (Revenue Intelligence)
with eng2:
    pip_ach = ach(dep_actual+loan_actual+nfi_actual,
                  dep_target+loan_target+nfi_target)
    pip_clr, pip_ico = traffic(pip_ach)
    st.markdown(
        f"<div style='padding:16px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border:0.5px solid var(--color-border-tertiary)'>"
        f"<div style='font-size:13px;font-weight:500;color:#0F6E56;margin-bottom:12px'>"
        f"Revenue pipeline</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>"
        f"<div><div style='font-size:20px;font-weight:500'>{pip_ico} {pip_ach:.0f}%</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>overall achievement</div></div>"
        f"<div><div style='font-size:20px;font-weight:500'>{fmt_num(total_pip_wtd, short=True)}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>weighted pipeline</div></div>"
        f"<div><div style='font-size:18px;font-weight:500;color:#1D9E75'>{fmt_num(total_won, short=True)}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>won YTD</div></div>"
        f"<div><div style='font-size:18px;font-weight:500'>{len(ri_deals)}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>active deals</div></div>"
        f"</div></div>",
        unsafe_allow_html=True)

    # Category coverage bars
    cat_rows = []
    for cat, s in ri_summary.items():
        if s['annual_target'] > 0:
            cat_rows.append({
                'Category': RI_CATEGORIES[cat]['label'][:12],
                'Achieved': ach(s['ytd_actual'], s['annual_target']),
                'Pipeline': min(100 - ach(s['ytd_actual'], s['annual_target']),
                                ach(s['pipeline_wtd'], s['annual_target'])),
            })
    if cat_rows:
        cat_df = pd.DataFrame(cat_rows)
        fig_cat = px.bar(cat_df, x='Category', y=['Achieved','Pipeline'],
                         barmode='stack', title='Coverage vs target %',
                         color_discrete_map={'Achieved':'#1D9E75','Pipeline':'#85B7EB'})
        fig_cat.add_hline(y=100, line_dash='dash', line_color='orange',
                          annotation_text='Target')
        fig_cat.update_layout(height=180, showlegend=False, margin=dict(l=0,r=0,t=30,b=0),
                              plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                              yaxis_title='%')
        st.plotly_chart(fig_cat, use_container_width=True)

# Engine 3 — Execution (Execute)
exec_clr, exec_ico = ('#1D9E75','🟢') if exec_health>=80 else (('#BA7517','🟡') if exec_health>=60 else ('#E24B4A','🔴'))
with eng3:
    st.markdown(
        f"<div style='padding:16px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border:0.5px solid var(--color-border-tertiary)'>"
        f"<div style='font-size:13px;font-weight:500;color:#BA7517;margin-bottom:12px'>"
        f"Strategy execution</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>"
        f"<div><div style='font-size:20px;font-weight:500'>{exec_ico} {exec_health:.0f}%</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>milestone health</div></div>"
        f"<div><div style='font-size:20px;font-weight:500'>{len(all_inits)}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>total initiatives</div></div>"
        f"<div><div style='font-size:18px;font-weight:500;color:#1D9E75'>{len(g5_inits)}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>embedded (G5)</div></div>"
        f"<div><div style='font-size:18px;font-weight:500;color:#E24B4A'>{critical_esc}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>critical escalations</div></div>"
        f"</div></div>",
        unsafe_allow_html=True)

    # Gate funnel mini
    if any(g_counts.values()):
        gf_df = pd.DataFrame([
            {'Gate': g, 'Count': g_counts.get(g, 0),
             'Color': EXECUTE_GATES[g]['color']}
            for g in GATE_ORDER])
        fig_gf = px.bar(gf_df, x='Gate', y='Count', title='Initiative gates',
                        color='Gate',
                        color_discrete_map={g: EXECUTE_GATES[g]['color'] for g in GATE_ORDER})
        fig_gf.update_layout(height=180, showlegend=False, margin=dict(l=0,r=0,t=30,b=0),
                             plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_gf, use_container_width=True)
    else:
        st.caption("No initiatives yet — add them in Execute tab.")

# ════════════════════════════════════════════════════════════════
# ROW 3 — INTEGRATION SIGNALS (the unique value of this tab)
# ════════════════════════════════════════════════════════════════
st.markdown("### Integration signals")
st.caption("Where performance, pipeline, and execution intersect — the insights no single module shows alone.")

sig_cols = st.columns(3)

# Signal 1: Execution → Revenue linkage
with sig_cols[0]:
    linked_pct = len(rev_linked) / max(1, len(g4_inits)+len(g5_inits)) * 100
    s_clr = '#1D9E75' if linked_pct >= 70 else ('#BA7517' if linked_pct >= 40 else '#E24B4A')
    st.markdown(
        f"<div style='padding:14px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border-left:4px solid {s_clr};"
        f"border-top:0.5px solid var(--color-border-tertiary);"
        f"border-right:0.5px solid var(--color-border-tertiary);"
        f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
        f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
        f"Execution → revenue linkage</div>"
        f"<div style='font-size:26px;font-weight:500;color:{s_clr}'>"
        f"{len(rev_linked)}</div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
        f"of {len(g4_inits)+len(g5_inits)} active/embedded initiatives "
        f"are linked to revenue KPIs</div>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:6px'>"
        f"{'Good linkage — initiatives driving measurable revenue impact' if linked_pct>=70 else 'Review: ensure initiatives are mapped to revenue KPIs'}"
        f"</div></div>",
        unsafe_allow_html=True)

# Signal 2: Double-risk units (low performance + delayed execution)
with sig_cols[1]:
    dr_clr = '#E24B4A' if double_risk else '#1D9E75'
    st.markdown(
        f"<div style='padding:14px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border-left:4px solid {dr_clr};"
        f"border-top:0.5px solid var(--color-border-tertiary);"
        f"border-right:0.5px solid var(--color-border-tertiary);"
        f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
        f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
        f"Double-risk units</div>"
        f"<div style='font-size:26px;font-weight:500;color:{dr_clr}'>"
        f"{len(double_risk)}</div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
        f"units with low BSC score AND delayed execution milestones</div>"
        f"{'<div style=\"font-size:11px;color:#E24B4A;margin-top:6px\">' + ', '.join([str(x) for x in list(double_risk)[:3]]) + '</div>' if double_risk else ''}"
        f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:4px'>"
        f"{'These units need urgent intervention — poor performance and stalled execution' if double_risk else 'No double-risk units — performance and execution aligned'}"
        f"</div></div>",
        unsafe_allow_html=True)

# Signal 3: Pipeline vs performance gap
with sig_cols[2]:
    # Units with good pipeline but low BSC — execution not converting
    if len(perf_df) and 'Unit' in perf_df.columns:
        unit_bsc = perf_df.groupby('Unit')['Final_BSC_Score'].mean()
        low_bsc_units  = set(unit_bsc[unit_bsc < 2.8].index)
        # Any RI deals in those units?
        ri_unit_deals  = {d.get('staff_name','') for d in ri_deals if d.get('stage') in ('Proposal','Negotiation','Compliance')}
        conversion_gap = len(low_bsc_units)
    else:
        conversion_gap = 0
        low_bsc_units  = set()

    cg_clr = '#E24B4A' if conversion_gap > 3 else ('#BA7517' if conversion_gap > 0 else '#1D9E75')
    st.markdown(
        f"<div style='padding:14px;background:var(--color-background-secondary);"
        f"border-radius:var(--border-radius-lg);border-left:4px solid {cg_clr};"
        f"border-top:0.5px solid var(--color-border-tertiary);"
        f"border-right:0.5px solid var(--color-border-tertiary);"
        f"border-bottom:0.5px solid var(--color-border-tertiary)'>"
        f"<div style='font-size:12px;font-weight:500;margin-bottom:8px'>"
        f"Performance conversion gap</div>"
        f"<div style='font-size:26px;font-weight:500;color:{cg_clr}'>"
        f"{conversion_gap}</div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
        f"units below 2.8 BSC — pipeline activity may not be converting to results</div>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary);margin-top:6px'>"
        f"{'Review coaching and conversion quality in these units' if conversion_gap else 'Good — performance aligned with activity levels'}"
        f"</div></div>",
        unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ROW 4 — BRANCH HEATMAP (the MD's field view)
# ════════════════════════════════════════════════════════════════
if len(perf_df) and 'Unit' in perf_df.columns:
    st.markdown("### Branch performance heatmap")
    st.caption("Each branch scored across BSC performance, deposit achievement, loan achievement, and customer growth.")

    branch_df = perf_df[perf_df.get('Category', pd.Series(['Branch']*len(perf_df))) == 'Branch'] \
                if 'Category' in perf_df.columns else perf_df

    if len(branch_df) > 0 and 'Unit' in branch_df.columns:
        unit_scores = branch_df.groupby('Unit').agg(
            BSC_Score   = ('Final_BSC_Score','mean'),
            Staff_Count = ('Staff Name','count'),
            Exceeded    = ('Final_BSC_Score', lambda x: (x>=3.1).sum()),
            At_Risk     = ('Final_BSC_Score', lambda x: (x<2.5).sum()),
        ).reset_index()

        # Merge KPI actuals by unit
        if not kpi_df.empty and 'Unit' in kpi_df.columns:
            def unit_kpi_ach(unit, kpi_list):
                rows = kpi_df[(kpi_df['Unit']==unit) & (kpi_df['KPI'].isin(kpi_list))]
                tgt = rows['Annual Target'].sum()
                act = rows['YTD_Actual'].sum()
                return round(act/tgt*100, 1) if tgt else 0

            unit_scores['Deposit %'] = unit_scores['Unit'].apply(
                lambda u: unit_kpi_ach(u, ['Deposit Growth']))
            unit_scores['Loans %'] = unit_scores['Unit'].apply(
                lambda u: unit_kpi_ach(u, ['Loans Disbursement','Loan Book Growth']))
            unit_scores['Customer %'] = unit_scores['Unit'].apply(
                lambda u: unit_kpi_ach(u, ['Customer Growth']))

            pivot_cols = ['Deposit %','Loans %','Customer %','BSC_Score']
        else:
            pivot_cols = ['BSC_Score']

        unit_scores = unit_scores.sort_values(by='BSC_Score', ascending=False)
        display_cols = ['Unit','BSC_Score','Staff_Count','At_Risk'] + \
                       [c for c in ['Deposit %','Loans %','Customer %'] if c in unit_scores.columns]

        # Heatmap
        if len(pivot_cols) > 1:
            heat_data = unit_scores[['Unit'] + pivot_cols].set_index('Unit')
            # Normalise each column 0-100
            for col in pivot_cols:
                mn, mx = heat_data[col].min(), heat_data[col].max()
                heat_data[col] = ((heat_data[col]-mn)/(mx-mn)*100).round(1) if mx>mn else 50

            fig_heat = px.imshow(
                heat_data.T,
                color_continuous_scale=[[0,'#E24B4A'],[0.5,'#F39C12'],[1,'#1D9E75']],
                aspect='auto', title='Branch performance heatmap (normalised)',
                text_auto='.0f')
            fig_heat.update_layout(
                height=max(200, len(pivot_cols)*50 + 60),
                coloraxis_showscale=False,
                margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_heat, use_container_width=True)

        # Table
        disp = unit_scores[display_cols].copy()
        disp['BSC_Score'] = disp['BSC_Score'].round(2)
        disp.columns = [c.replace('_',' ') for c in disp.columns]
        st.dataframe(disp, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# ROW 5 — ESCALATION SURFACE (what needs MD attention NOW)
# ════════════════════════════════════════════════════════════════
if critical_esc > 0 or double_risk:
    st.markdown("### Items requiring executive attention")

    if critical_esc > 0:
        st.markdown(
            f"<div style='padding:12px 16px;background:#FCEBEB;border-left:4px solid #A32D2D;"
            f"border-radius:0 6px 6px 0;margin:6px 0'>"
            f"<b style='color:#A32D2D'>🚨 {critical_esc} milestone(s) at critical escalation level</b> — "
            f"overdue >7 days or structural delay. Sponsor intervention required."
            f"</div>", unsafe_allow_html=True)
        for ms in esc_buckets.get(4,[])[:3] + esc_buckets.get(3,[])[:3]:
            st.markdown(
                f"<div style='font-size:12px;padding:6px 12px 6px 20px;"
                f"color:var(--color-text-secondary);border-left:2px solid #E24B4A;margin:2px 0'>"
                f"<b>{ms.get('initiative_name','')}</b> → {ms.get('name','')} | "
                f"Owner: {ms.get('owner','')} | {ms.get('overdue_days',0)}d overdue | "
                f"Workstream: {ms.get('workstream','')}"
                f"</div>", unsafe_allow_html=True)

    if double_risk:
        st.markdown(
            f"<div style='padding:12px 16px;background:#FFF3CD;border-left:4px solid #BA7517;"
            f"border-radius:0 6px 6px 0;margin:6px 0'>"
            f"<b style='color:#BA7517'>⚠️ Double-risk units: {', '.join(str(x) for x in double_risk)}</b> — "
            f"low BSC performance AND stalled execution milestones. Review urgently."
            f"</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# ROW 6 — DETAILED DRILL-DOWN (expandable sections)
# ════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Drill-down")

with st.expander("Revenue intelligence — category detail", expanded=False):
    ri_cols = st.columns(4)
    for ci, (cat, s) in enumerate(ri_summary.items()):
        cfg = RI_CATEGORIES[cat]
        pct = ach(s['ytd_actual'], s['annual_target'])
        clr_r, _ = traffic(pct)
        with ri_cols[ci]:
            st.markdown(
                f"<div style='padding:12px;background:{cfg['bg']};"
                f"border-left:3px solid {cfg['color']};border-radius:0 6px 6px 0'>"
                f"<b style='color:{cfg['color']}'>{cfg['label']}</b><br>"
                f"<span style='font-size:18px;font-weight:500'>{fmt_num(s['ytd_actual'],True)}</span>"
                f"<span style='font-size:11px;color:var(--color-text-secondary)'> / {fmt_num(s['annual_target'],True)}</span><br>"
                f"<span style='color:{clr_r};font-weight:500'>{pct:.1f}%</span>"
                f"<span style='font-size:11px;color:var(--color-text-secondary)'> | Pipeline: {fmt_num(s['pipeline_wtd'],True)}</span><br>"
                f"<span style='font-size:11px;color:var(--color-text-secondary)'>EOY forecast: {fmt_num(s['forecast_eoy'],True)}</span>"
                f"</div>", unsafe_allow_html=True)

with st.expander("Strategy execution — initiative status", expanded=False):
    if all_inits:
        init_rows = []
        for i in all_inits:
            ms_all  = i.get('milestones',[])
            ms_done_i = sum(1 for m in ms_all if m.get('status')=='Complete')
            ms_del_i  = sum(1 for m in ms_all if ExecuteManager._escalation_level(m)>=2)
            init_rows.append({
                'ID':          i['id'],
                'Initiative':  i['name'][:40],
                'Category':    i.get('category',''),
                'Workstream':  i.get('workstream','')[:25],
                'Gate':        i.get('gate',''),
                'IO':          i.get('io',''),
                'Milestones':  f"{ms_done_i}/{len(ms_all)}",
                'Delayed':     ms_del_i,
            })
        init_df = pd.DataFrame(init_rows)
        def hl_gate(v):
            cfg = EXECUTE_GATES.get(v, {})
            return f"background-color:{cfg.get('bg','')};color:{cfg.get('color','')}"
        st.dataframe(
            init_df.style.map(hl_gate, subset=['Gate']),
            use_container_width=True, hide_index=True)
    else:
        st.info("No initiatives yet.")

with st.expander("People performance — top 10 and bottom 10", expanded=False):
    if len(perf_df):
        pt1, pt2 = st.columns(2)
        with pt1:
            st.markdown("**Top 10 performers**")
            top10 = perf_df.assign(_rank=perf_df['Overall_Rank'].astype(float)).nsmallest(10,'_rank')[
                ['Staff Name','Role','Unit','Final_BSC_Score','Performance_Remark']].copy()
            top10['Final_BSC_Score'] = top10['Final_BSC_Score'].apply(fmt_score)
            st.dataframe(top10.style.map(highlight_performance, subset=['Performance_Remark']),
                         use_container_width=True, hide_index=True)
        with pt2:
            st.markdown("**Bottom 10 — needs attention**")
            bot10 = perf_df.assign(_rank=perf_df['Overall_Rank'].astype(float)).nlargest(10,'_rank')[
                ['Staff Name','Role','Unit','Final_BSC_Score','Performance_Remark']].copy()
            bot10['Final_BSC_Score'] = bot10['Final_BSC_Score'].apply(fmt_score)
            st.dataframe(bot10.style.map(highlight_performance, subset=['Performance_Remark']),
                         use_container_width=True, hide_index=True)

# ── Board-pack download ───────────────────────────────────────
st.markdown("---")
st.markdown("### Board pack export")
st.caption("Generate a single CSV snapshot of the executive view for board reporting.")
if st.button("⬇️ Generate board pack snapshot", type="primary"):
    board_rows = []
    board_rows.append({'Section':'FINANCIAL PERFORMANCE','Metric':'','Value':'','Target':'','Achievement %':''})
    for label, actual, target in [
        ('Deposits',    dep_actual,  dep_target),
        ('Loans',       loan_actual, loan_target),
        ('NFI',         nfi_actual,  nfi_target),
        ('PBT',         pbt_actual,  pbt_target),
        ('Customers',   cust_actual, cust_target),
    ]:
        board_rows.append({
            'Section': 'Financial',
            'Metric':  label,
            'Value':   fmt_num(actual),
            'Target':  fmt_num(target),
            'Achievement %': f"{ach(actual,target):.1f}%",
        })
    board_rows.append({'Section':'PEOPLE','Metric':'Avg BSC Score','Value':fmt_score(avg_bsc),'Target':'3.00','Achievement %':f"{avg_bsc/3*100:.0f}%"})
    board_rows.append({'Section':'PEOPLE','Metric':'Exceeded target','Value':str(exceeded),'Target':'','Achievement %':f"{exceeded/max(1,total_staff)*100:.0f}%"})
    board_rows.append({'Section':'PEOPLE','Metric':'At risk (<2.5)','Value':str(at_risk),'Target':'0','Achievement %':''})
    board_rows.append({'Section':'EXECUTION','Metric':'Total initiatives','Value':str(len(all_inits)),'Target':'','Achievement %':''})
    board_rows.append({'Section':'EXECUTION','Metric':'Embedded (G5)','Value':str(len(g5_inits)),'Target':'','Achievement %':''})
    board_rows.append({'Section':'EXECUTION','Metric':'Critical escalations','Value':str(critical_esc),'Target':'0','Achievement %':''})
    board_rows.append({'Section':'EXECUTION','Metric':'Milestone health','Value':f"{exec_health:.0f}%",'Target':'100%','Achievement %':''})

    bp_df = pd.DataFrame(board_rows)
    bp_csv = bp_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "Download board pack CSV",
        bp_csv,
        f"A2Z_BoardPack_{now.strftime('%Y%m%d')}.csv",
        "text/csv")


