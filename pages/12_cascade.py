"""pages/12_cascade.py — Target Cascading: MD → Director → Manager → Staff."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date
from utils.core import *
from pages._shared import load_shared_state

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores",  pd.DataFrame())
df_proc      = st.session_state.get("df_processed",  pd.DataFrame())
registry     = st.session_state.get("staff_registry", pd.DataFrame())

role_l   = str(ud.get("role","")).lower()
my_code  = ud.get("staff_code","") or uname
my_unit  = ud.get("unit","")
can_all  = ud.get("can_view_all",False) or any(k in role_l for k in ("admin","md","ceo","director"))
is_mgr   = can_all or any(k in role_l for k in ("head of","head_of","manager","regional"))

if len(staff_scores) == 0:
    st.markdown(
        "<div style='padding:40px;text-align:center;background:#E8F5EE;"
        "border-radius:12px;border:1px solid #006B3F33'>"
        "<div style='font-size:32px;margin-bottom:12px'>🎯</div>"
        "<div style='font-size:18px;font-weight:500;color:#006B3F'>"
        "Upload BSC data to activate Target Cascading</div>"
        "</div>", unsafe_allow_html=True)
    st.stop()

if casc is None:
    try:
        from utils.core import CascadeManager
        casc = CascadeManager()
        st.session_state["cascade_manager"] = casc
    except Exception:
        st.error("CascadeManager not available — please update utils/core.py and restart.")
        st.stop()

# ── BUILD HIERARCHY FROM DATA ─────────────────────────────────────────
HIERARCHY = {
    'MD / CEO':            ['Director Retail','Director Commercial Banking','Head Of Corporate',
                            'Head Of Digital Innovation'],
    'Director Retail':     ['Regional Head','Head Of Retail'],
    'Director Commercial Banking': ['Head Of SME','Head Of Commercial'],
    'Head Of Corporate':   ['Relationship Manager Corporate'],
    'Head Of Digital Innovation': ['Digital Innovation Manager'],
    'Regional Head':       ['Branch Manager'],
    'Branch Manager':      ['Branch Operations Manager','Direct Sales Officer',
                            'Relationship Officer Personal Banking','Teller',
                            'Customer Service Officer'],
    'Head Of SME':         ['Relationship Manager SME'],
    'Head Of Retail':      ['Direct Sales Officer','Relationship Officer Personal Banking'],
}

def get_direct_reports(role_name: str, unit: str = None) -> pd.DataFrame:
    """Get staff who report to a given role, optionally filtered by unit."""
    sub_roles = HIERARCHY.get(role_name, [])
    if not sub_roles or len(staff_scores) == 0:
        return pd.DataFrame()
    mask = staff_scores['Role'].isin(sub_roles)
    if unit:
        mask = mask & (staff_scores['Unit'] == unit)
    return staff_scores[mask].copy()

def get_my_role_level():
    for level, subs in HIERARCHY.items():
        if any(k in role_l for k in level.lower().split()):
            return level
    if 'director' in role_l: return 'Director Retail'
    if 'head of' in role_l or 'head_of' in role_l:
        for k in ['retail','sme','corporate','digital']:
            if k in role_l: return f"Head Of {k.title()}"
    if 'regional' in role_l: return 'Regional Head'
    if 'branch manager' in role_l: return 'Branch Manager'
    return 'MD / CEO' if can_all else None

# KPIs from data
all_kpis = sorted(df_proc['KPI'].unique().tolist()) if not df_proc.empty and 'KPI' in df_proc.columns else []
period   = "2026"

# ═══════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════
st.markdown(
    "<div style='padding:16px 20px;background:#006B3F;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:18px;font-weight:500'>Target Cascading</div>"
    "<div style='color:#9FE1CB;font-size:12px;margin-top:2px'>"
    "MD → Directors → Heads → Managers → Staff | Top-down target allocation with coverage tracking"
    "</div></div>", unsafe_allow_html=True)

tabs = st.tabs([
    "🌳 Cascade tree",
    "🎯 Allocate targets",
    "📊 My targets",
    "✅ Coverage dashboard",
])

# ═══════════════════════════════════════════════════════════════════════
# TAB 1 — CASCADE TREE
# ═══════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Target cascade tree")
    st.caption("See how targets flow from the top. Select a KPI to view allocations at each level.")

    sel_kpi_tree = st.selectbox("KPI", all_kpis, key="tree_kpi") if all_kpis else None
    if not sel_kpi_tree:
        st.info("No KPI data available.")
        st.stop()

    # Build tree data
    def build_tree_level(role_level, depth=0, unit=None):
        items = []
        # Find people at this level in staff_scores
        sub_roles = HIERARCHY.get(role_level, [])
        level_staff = staff_scores[staff_scores['Role'] == role_level] if len(staff_scores) else pd.DataFrame()
        if unit:
            level_staff = level_staff[level_staff['Unit']==unit]

        for _, person in level_staff.iterrows():
            sc   = str(person.get('Staff Code',''))
            name = person.get('Staff Name','')
            unit_p = person.get('Unit','')
            bsc  = person.get('Final_BSC_Score', 0)

            # Get KPI target from df_proc
            kpi_rows = df_proc[(df_proc['Staff Name']==name) & (df_proc['KPI']==sel_kpi_tree)] if not df_proc.empty else pd.DataFrame()
            tgt = float(kpi_rows['Annual Target'].values[0]) if len(kpi_rows) else 0
            act = float(kpi_rows['YTD_Actual'].values[0]) if len(kpi_rows) and 'YTD_Actual' in kpi_rows.columns else 0

            # Check cascade allocation
            alloc_entry = casc.get_allocation(sc, sel_kpi_tree, period)
            alloc_sum, total_tgt, cov_pct, unalloc = casc.cascade_coverage(sc, sel_kpi_tree, period)

            items.append({
                'depth': depth, 'name': name, 'role': role_level,
                'unit': unit_p, 'sc': sc,
                'target': tgt, 'actual': act,
                'ach': round(act/tgt*100,1) if tgt else 0,
                'bsc': bsc,
                'cascade_pct': cov_pct,
                'allocations': alloc_entry['allocations'] if alloc_entry else [],
            })

            # Recurse into sub-roles
            for sub_role in sub_roles:
                items.extend(build_tree_level(sub_role, depth+1, unit_p))

        return items

    # Start tree from MD level
    tree_items = build_tree_level('MD / CEO')

    if not tree_items:
        st.info("No hierarchy data found. Ensure BSC data is uploaded.")
    else:
        for item in tree_items[:30]:  # cap at 30 rows
            indent = '&nbsp;' * (item['depth'] * 6)
            ach_clr = '#006B3F' if item['ach']>=100 else ('#F5A623' if item['ach']>=70 else '#E24B4A')
            casc_clr = '#006B3F' if item['cascade_pct']>=95 else ('#F5A623' if item['cascade_pct']>=50 else '#E24B4A')
            casc_badge = (f"<span style='background:{casc_clr};color:white;padding:1px 6px;"
                          f"border-radius:10px;font-size:10px'>{item['cascade_pct']:.0f}% cascaded</span>"
                          if item['target'] > 0 else '')

            # Performance band colour
            if item['ach'] >= 100: perf_status = '🟢 On target'
            elif item['ach'] >= 70: perf_status = '🟡 Below target'
            else: perf_status = '🔴 At risk'

            # Cascade status
            if item['target'] == 0:
                casc_status = ''
            elif item['cascade_pct'] >= 95:
                casc_status = f"<span style='background:#006B3F;color:white;padding:1px 6px;border-radius:10px;font-size:10px'>✓ {item['cascade_pct']:.0f}% cascaded</span>"
            elif item['cascade_pct'] > 0:
                casc_status = f"<span style='background:#F5A623;color:white;padding:1px 6px;border-radius:10px;font-size:10px'>⚠ {item['cascade_pct']:.0f}% cascaded</span>"
            else:
                casc_status = "<span style='background:#E24B4A;color:white;padding:1px 6px;border-radius:10px;font-size:10px'>✗ Not cascaded</span>"

            border_clr = ['#006B3F','#F5A623','#185FA5','#7F8C8D'][min(item['depth'],3)]

            st.markdown(
                f"<div style='padding:7px 12px;background:var(--color-background-secondary);"
                f"border-left:{3+item['depth']}px solid {border_clr};"
                f"margin:2px 0;border-radius:0 4px 4px 0;font-size:12px'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<div>{indent}<b>{item['name']}</b> "
                f"<span style='color:#888;font-size:10px'>({item['role']} · {item['unit']})</span></div>"
                f"<div style='display:flex;gap:12px;align-items:center;font-size:11px'>"
                f"<span>Target: <b>{fmt_num(item['target'],True)}</b></span>"
                f"<span style='color:{ach_clr}'>Actual: <b>{fmt_num(item['actual'],True)}</b> ({item['ach']:.0f}%)</span>"
                f"<span>BSC: <b>{item['bsc']:.2f}</b></span>"
                f"<span>{perf_status}</span>"
                f"{casc_status}"
                f"</div></div>"
                f"{_render_allocs(item['allocations'], item['depth'])}"
                f"</div>",
                unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# TAB 2 — ALLOCATE TARGETS
# ═══════════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Allocate targets to your team")
    st.caption("As a line manager, distribute your target among your direct reports. "
               "Targets flow from your allocation downward.")

    if not is_mgr:
        st.info("Target allocation is available to managers and above.")
    else:
        my_role = get_my_role_level()
        direct_reports = get_direct_reports(my_role or '', my_unit if not can_all else None)

        ac1, ac2 = st.columns(2)
        alloc_kpi  = ac1.selectbox("KPI to allocate", all_kpis, key="alloc_kpi")
        alloc_year = ac2.selectbox("Period", ["2026","2025"], key="alloc_yr")

        # My own target for this KPI
        my_kpi_rows = df_proc[(df_proc['Staff Name']==ud.get('full_name','')) &
                               (df_proc['KPI']==alloc_kpi)] if not df_proc.empty else pd.DataFrame()
        my_target = float(my_kpi_rows['Annual Target'].values[0]) if len(my_kpi_rows) else 0

        st.markdown(
            f"<div style='padding:10px 14px;background:#E8F5EE;"
            f"border-left:3px solid #006B3F;border-radius:0 6px 6px 0;margin:8px 0'>"
            f"Your target for <b>{alloc_kpi}</b>: <b>{fmt_num(my_target,True)}</b>"
            f"</div>", unsafe_allow_html=True)

        if len(direct_reports) == 0:
            st.info(f"No direct reports found for role '{my_role}'. "
                    "Ensure staff data is loaded with the correct role hierarchy.")
        else:
            st.markdown(f"**Allocate to {len(direct_reports)} direct report(s):**")

            # Existing allocations
            existing = casc.get_allocation(my_code, alloc_kpi, alloc_year)
            existing_map = {a['to_code']: a['amount']
                            for a in (existing['allocations'] if existing else [])}

            with st.form("cascade_alloc_form"):
                allocations  = []
                total_alloc  = 0

                for _, dr in direct_reports.iterrows():
                    dr_code = str(dr.get('Staff Code',''))
                    dr_name = dr.get('Staff Name','')
                    dr_role = dr.get('Role','')
                    dr_unit = dr.get('Unit','')
                    dr_bsc  = dr.get('Final_BSC_Score',0)

                    # Get dr's current BSC target from data
                    dr_kpi = df_proc[(df_proc['Staff Name']==dr_name) &
                                      (df_proc['KPI']==alloc_kpi)] if not df_proc.empty else pd.DataFrame()
                    dr_current_tgt = float(dr_kpi['Annual Target'].values[0]) if len(dr_kpi) else 0
                    default_val    = existing_map.get(dr_code, dr_current_tgt)

                    fc1,fc2,fc3 = st.columns([3,2,2])
                    fc1.markdown(
                        f"<div style='padding:4px 0;font-size:12px'>"
                        f"<b>{dr_name}</b><br>"
                        f"<span style='color:#888;font-size:10px'>{dr_role} · {dr_unit} · BSC {dr_bsc:.2f}</span>"
                        f"</div>", unsafe_allow_html=True)
                    amount = fc2.number_input(
                        f"Amount", value=float(default_val), min_value=0.0,
                        step=1_000_000.0, key=f"alloc_{dr_code}",
                        label_visibility="collapsed")
                    pct_of_my = round(amount/my_target*100,1) if my_target else 0
                    fc3.markdown(
                        f"<div style='padding:8px 0;font-size:12px;color:#666'>"
                        f"{pct_of_my:.1f}% of my target</div>",
                        unsafe_allow_html=True)

                    allocations.append({'to_code': dr_code, 'to_name': dr_name,
                                        'to_role': dr_role, 'to_unit': dr_unit, 'amount': amount})
                    total_alloc += amount

                # Summary
                remaining = my_target - total_alloc
                rem_clr = '#E24B4A' if remaining < 0 else ('#F5A623' if remaining > 0 else '#006B3F')
                st.markdown(
                    f"<div style='padding:10px 14px;background:var(--color-background-secondary);"
                    f"border-radius:6px;margin:8px 0;display:flex;gap:24px;font-size:13px'>"
                    f"<span>Total allocated: <b>{fmt_num(total_alloc,True)}</b></span>"
                    f"<span>My target: <b>{fmt_num(my_target,True)}</b></span>"
                    f"<span style='color:{rem_clr}'>Unallocated: <b>{fmt_num(remaining,True)}</b></span>"
                    f"<span>Coverage: <b>{round(total_alloc/my_target*100,1) if my_target else 0}%</b></span>"
                    f"</div>", unsafe_allow_html=True)

                if st.form_submit_button("💾 Save allocations", type="primary"):
                    if my_target == 0:
                        st.error("You don't have a target set for this KPI yet.")
                    else:
                        casc.set_allocation(my_code, alloc_kpi, alloc_year,
                                            allocations, my_target)
                        audit_log("CASCADE_ALLOC", uname,
                                  f"{alloc_kpi}:{alloc_year}:{len(allocations)} reports")
                        st.success(f"Targets allocated to {len(allocations)} staff for {alloc_kpi} {alloc_year}")
                        st.rerun()

# ═══════════════════════════════════════════════════════════════════════
# TAB 3 — MY TARGETS (what was given to me)
# ═══════════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("My cascaded targets")
    st.caption("Targets that have been allocated to you from above, alongside your BSC actuals.")

    my_name = ud.get('full_name','')
    my_given = casc.get_what_i_was_given(my_code, period) if casc else []

    # BSC scorecard (my own)
    if my_name and not df_proc.empty:
        my_kpis = df_proc[df_proc['Staff Name']==my_name].copy()
        if not my_kpis.empty:
            st.markdown("#### Your BSC targets vs actuals")
            my_bsc_row = staff_scores[staff_scores['Staff Name']==my_name]
            if len(my_bsc_row):
                mbr = my_bsc_row.iloc[0]
                mc1,mc2,mc3 = st.columns(3)
                mc1.metric("BSC Score", f"{mbr['Final_BSC_Score']:.2f}/5.0")
                mc2.metric("Rank",      f"#{mbr['Overall_Rank']}")
                mc3.metric("Performance", mbr['Performance_Remark'])

            # Full KPI table
            kpi_display = []
            for _, r in my_kpis.iterrows():
                tgt = pd.to_numeric(r.get('Annual Target',0), errors='coerce') or 0
                act = pd.to_numeric(r.get('YTD_Actual', r.get('Annual Actual',0)), errors='coerce') or 0
                wt  = pd.to_numeric(r.get('Weight',0), errors='coerce') or 0
                sc  = pd.to_numeric(r.get('Score',0), errors='coerce') or 0
                pct = round(act/tgt*100,1) if tgt else 0

                # Check if there's a cascaded target different from BSC target
                cascade_tgt = next((g['amount'] for g in my_given if g['kpi']==r.get('KPI','')), None)

                kpi_display.append({
                    'Pillar':  r.get('Pillar',''),
                    'KPI':     r.get('KPI',''),
                    'Weight':  f"{wt*100:.0f}%",
                    'BSC Target': fmt_num(tgt, True),
                    'Cascaded Target': fmt_num(cascade_tgt, True) if cascade_tgt else '—',
                    'YTD Actual': fmt_num(act, True),
                    'Achievement': f"{pct:.1f}%",
                    'Score': f"{sc:.2f}",
                })

            disp_df = pd.DataFrame(kpi_display)

            def hl_ach(v):
                try:
                    p = float(str(v).replace('%',''))
                    if p >= 100: return 'color:#006B3F;font-weight:500'
                    if p >= 70:  return 'color:#F5A623'
                    return 'color:#E24B4A'
                except: return ''

            st.dataframe(
                disp_df.style.map(hl_ach, subset=['Achievement']),
                use_container_width=True, hide_index=True)

    # Cascade details
    if my_given:
        st.markdown("---")
        st.markdown("#### Targets allocated to you")
        for g in my_given:
            st.markdown(
                f"<div style='padding:8px 12px;background:var(--color-background-secondary);"
                f"border-left:3px solid #006B3F;border-radius:0 4px 4px 0;font-size:12px;margin:3px 0'>"
                f"<b>{g['kpi']}</b> — allocated: <b>{fmt_num(g['amount'],True)}</b> "
                f"({g['my_share']:.1f}% of {fmt_num(g['total_pool'],True)} pool) "
                f"by {g['from_code']}</div>",
                unsafe_allow_html=True)
    else:
        st.info("No targets have been cascaded to you yet. Ask your manager to allocate in this module.")

# ═══════════════════════════════════════════════════════════════════════
# TAB 4 — COVERAGE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Target cascade coverage dashboard")
    st.caption("See who has cascaded their targets and who hasn't. Managers with 0% coverage haven't allocated.")

    if not casc.cascade or len(casc.cascade) == 0:
        st.info("No cascade allocations recorded yet. Line managers should use the 'Allocate targets' tab.")
    else:
        # Build coverage summary
        cov_rows = []
        for key, entry in casc.cascade.items():
            from_code = entry['from_code']
            # Find name
            name_row = staff_scores[staff_scores['Staff Code'].astype(str)==from_code]
            from_name = name_row['Staff Name'].values[0] if len(name_row) else from_code
            from_role = name_row['Role'].values[0] if len(name_row) else '—'

            total = entry['total_target']
            alloc = entry['allocated_sum']
            cov   = round(alloc/total*100,1) if total else 0
            n_rpt = len(entry['allocations'])

            cov_rows.append({
                'Manager':         from_name,
                'Role':            from_role,
                'KPI':             entry['kpi'],
                'Period':          entry['period'],
                'My Target':       fmt_num(total, True),
                'Total Allocated': fmt_num(alloc, True),
                'Coverage %':      f"{cov:.1f}%",
                'Reports':         n_rpt,
                '_cov':            cov,
            })

        if cov_rows:
            cov_df = pd.DataFrame(cov_rows)

            # Chart
            fig = px.bar(cov_df, x='Manager', y='_cov', color='KPI',
                         barmode='group',
                         title='Cascade coverage % by manager and KPI',
                         labels={'_cov':'Coverage %','Manager':'Manager'})
            fig.add_hline(y=95, line_dash='dash', line_color='#006B3F',
                           annotation_text='95% — full coverage')
            fig.add_hline(y=100, line_dash='dot', line_color='#F5A623',
                           annotation_text='100%')
            fig.update_layout(height=360, yaxis_range=[0,115],
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

            # Table
            display_df = cov_df.drop(columns=['_cov'])
            def hl_cov(v):
                try:
                    p = float(str(v).replace('%',''))
                    if p >= 95:  return 'color:#006B3F;font-weight:500'
                    if p >= 50:  return 'color:#F5A623'
                    return 'color:#E24B4A;font-weight:500'
                except: return ''
            st.dataframe(
                display_df.style.map(hl_cov, subset=['Coverage %']),
                use_container_width=True, hide_index=True)

        # Managers who haven't cascaded
        if len(staff_scores):
            mgr_roles = ['Director Retail','Director Commercial Banking','Head Of Corporate',
                         'Head Of Digital Innovation','Regional Head','Branch Manager',
                         'Head Of SME','Head Of Retail']
            managers = staff_scores[staff_scores['Role'].isin(mgr_roles)]['Staff Name'].tolist()
            who_allocated = set(v['from_code'] for v in casc.cascade.values())
            who_has_code  = set(str(r) for r in staff_scores[staff_scores['Staff Name'].isin(managers)]['Staff Code'].tolist())
            not_allocated = [m for m in managers
                             if str(staff_scores[staff_scores['Staff Name']==m]['Staff Code'].values[0])
                             not in who_allocated] if managers else []

            if not_allocated:
                st.markdown("---")
                st.markdown(
                    f"<div style='padding:10px 14px;background:#FFFBF0;"
                    f"border-left:3px solid #F5A623;border-radius:0 6px 6px 0'>"
                    f"⚠️ <b>{len(not_allocated)} manager(s)</b> have not cascaded any targets yet: "
                    f"{', '.join(not_allocated[:8])}"
                    f"{'...' if len(not_allocated)>8 else ''}</div>",
                    unsafe_allow_html=True)
