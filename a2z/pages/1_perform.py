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
um, ud, uname, em, ri_pm, prod_m, pm, vm_obj, lm, ssm = load_shared_state()

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

st.subheader("Performance rankings")

# Region quick filter in sidebar
if _has_region and len(filtered) > 0:
    all_regions = sorted(filtered["Region"].dropna().unique().tolist())
    if len(all_regions) > 1:
        sel_reg = st.sidebar.selectbox("Region", ["All"] + all_regions, key="reg_f")
        if sel_reg != "All":
            filtered = filtered[filtered["Region"] == sel_reg].copy()

fc1, fc2, fc3 = st.columns(3)
with fc1:
    roles_opts = ['All roles'] + sorted(filtered['Role'].unique().tolist())
    sel_role = st.selectbox("Role", roles_opts)
with fc2:
    units_opts = ['All units'] + (sorted(filtered['Unit'].unique().tolist()) if 'Unit' in filtered.columns else [])
    sel_unit = st.selectbox("Unit", units_opts)
with fc3:
    perf_opts = ['All','Exceeded By Far','Exceeded','Met','Partially Met','Unmet']
    sel_perf = st.selectbox("Performance", perf_opts)

view = filtered.copy()
if sel_role != 'All roles': view = view[view['Role'] == sel_role]
if sel_unit != 'All units' and 'Unit' in view.columns: view = view[view['Unit'] == sel_unit]
if sel_perf != 'All': view = view[view['Performance_Remark'] == sel_perf]

show_cols = [c for c in ['Overall_Rank','Staff Name','Role','Unit','Staff Status',
                          'Final_BSC_Score','Avg_Achievement_Pct','Performance_Remark','Percentile']
             if c in view.columns]
disp = view[show_cols].copy()
if 'Final_BSC_Score'     in disp.columns: disp['Final_BSC_Score']     = disp['Final_BSC_Score'].apply(fmt_score)
if 'Avg_Achievement_Pct' in disp.columns: disp['Avg_Achievement_Pct'] = disp['Avg_Achievement_Pct'].apply(fmt_pct)
if 'Percentile'          in disp.columns: disp['Percentile']          = disp['Percentile'].apply(fmt_pct)
disp.columns = [c.replace('_',' ') for c in disp.columns]
disp = disp.rename(columns={'Avg Achievement Pct':'Avg Achievement %','Final BSC Score':'BSC Score'})
st.dataframe(disp.style.map(highlight_performance, subset=['Performance Remark']),
             use_container_width=True, hide_index=True)

c1, c2 = st.columns(2)
with c1:
    top10 = view.assign(_or=view['Overall_Rank'].astype(float)).nsmallest(10,'_or')
    fig = px.bar(top10, x='Staff Name', y='Final_BSC_Score', color='Performance_Remark',
                 title='Top 10 performers', text='Final_BSC_Score',
                 color_discrete_map={'Exceeded By Far':'#2ECC71','Exceeded':'#58D68D',
                                     'Met':'#F39C12','Partially Met':'#E67E22','Unmet':'#E74C3C'})
    fig.update_traces(textposition='outside')
    fig.update_layout(showlegend=False, xaxis_tickangle=-30, height=350)
    st.plotly_chart(fig, use_container_width=True)
with c2:
    dist = view['Performance_Remark'].value_counts().reset_index()
    dist.columns = ['Status','Count']
    fig2 = px.pie(dist, names='Status', values='Count', title='Distribution',
                  color='Status', color_discrete_map={
                      'Exceeded By Far':'#2ECC71','Exceeded':'#58D68D','Met':'#F39C12',
                      'Partially Met':'#E67E22','Unmet':'#E74C3C','No Data':'#BDC3C7'})
    fig2.update_layout(height=350)
    st.plotly_chart(fig2, use_container_width=True)

# ── TAB 2: INDIVIDUAL ────────────────────────────────────────────────────
# with tabs[1]:
st.subheader("Individual performance")
selected = st.selectbox("Select staff member", sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else [])

if selected:
    row  = filtered[filtered['Staff Name'] == selected].iloc[0]
    kpis = df_proc[df_proc['Staff Name'] == selected]

    # ── Top metrics ──────────────────────────────────────────────
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Overall rank",   f"#{row['Overall_Rank']}")
    m2.metric("Role rank",      f"#{row['Role_Rank']} / {row['Role_Total']}")
    m3.metric("BSC score",      fmt_score(row['Final_BSC_Score']))
    m4.metric("Avg achievement", fmt_pct(row.get('Avg_Achievement_Pct', 0)))
    m5.metric("Percentile",       f"{row['Percentile']:.0f}th")

    # ── Performance status banner ─────────────────────────────────
    status = row['Performance_Remark']
    colour = {'Exceeded By Far':'#2ECC71','Exceeded':'#58D68D','Met':'#F39C12',
              'Partially Met':'#E67E22','Unmet':'#E74C3C'}.get(status,'#BDC3C7')
    remark_detail = {
        'Exceeded By Far': 'Outstanding performance — significantly above target across most KPIs.',
        'Exceeded':        'Strong performance — above target in the majority of KPIs.',
        'Met':             'Performance on target — meeting expectations.',
        'Partially Met':   'Performance below target — improvement needed in key areas.',
        'Unmet':           'Performance significantly below target — immediate action required.',
        'No Data':         'Insufficient data to assess performance.',
    }.get(status, '')
    st.markdown(
        f"<div style='padding:12px 18px;background:{colour}22;border-left:5px solid {colour};"
        f"border-radius:6px;margin:8px 0'>"
        f"<span style='font-size:17px;font-weight:700'>{status}</span><br>"
        f"<span style='font-size:13px;color:#555'>{remark_detail}</span></div>",
        unsafe_allow_html=True)

    # Staff status badge
    if 'Staff Status' in row.index:
        s_status = row.get('Staff Status','Existing')
        if str(s_status).strip().lower() in ('new','new 2026'):
            st.info("🆕 New staff — may be on probation")

    # ── Monthly weighted score trend ──────────────────────────────
    if active_months:
        monthly_trend = []
        for col in active_months:
            if col in kpis.columns:
                dt = parse_month_column(col)
                label = dt.strftime("%b %Y") if dt else str(col)
                # weighted score for that month: score × weight, summed across KPIs
                # approximate: ratio of that month actual to annual target × weight → score
                # simpler & correct: recalc weighted score using only that month's actual
                month_rows = kpis.copy()
                month_rows['_m_actual'] = month_rows[col]
                month_ws = []
                for _, kr in month_rows.iterrows():
                    t = kr.get('Annual Target', np.nan)
                    a = kr.get('_m_actual', 0)
                    w = kr.get('Weight', 0)
                    kpi_name = str(kr.get('KPI','')).upper()
                    rev = any(x in kpi_name for x in ['PAR','NPL','DELINQUENCY','COST','EXPENSE'])
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
            fig_line = px.line(mdf, x='Month', y='Weighted Score',
                               title=f"{selected} — monthly BSC weighted score", markers=True,
                               color_discrete_sequence=['#2980B9'])
            fig_line.add_hline(y=3.0, line_dash='dash', line_color='orange',
                               annotation_text='Target (3.0)')
            fig_line.update_traces(marker=dict(size=9))
            fig_line.update_layout(height=280, yaxis_range=[0,5.5])
            st.plotly_chart(fig_line, use_container_width=True)

    # ── Pillar radar ──────────────────────────────────────────────
    if 'Pillar' in kpis.columns and kpis['Pillar'].nunique() > 1:
        ps = kpis.groupby('Pillar')['Weighted_Score'].sum().reset_index()
        fig_r = go.Figure(go.Scatterpolar(
            r=ps['Weighted_Score'], theta=ps['Pillar'],
            fill='toself', fillcolor='rgba(52,152,219,0.2)',
            line=dict(color='#2980B9')))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0,2])),
            title=f"{selected} — pillar scores", height=320)
        st.plotly_chart(fig_r, use_container_width=True)

    # ── Performance insight card ─────────────────────────────────────
    st.markdown("#### Performance insights")
    insights = get_kpi_insights(kpis)
    render_insight_card(insights)

    # ── KPI breakdown — filterable by pillar ─────────────────────
    st.markdown("#### KPI detail")
    pillar_opts = ['All pillars'] + (sorted(kpis['Pillar'].unique().tolist()) if 'Pillar' in kpis.columns else [])
    sel_pillar = st.selectbox("Filter by pillar", pillar_opts, key="kpi_pillar_filter")
    kpi_view = kpis if sel_pillar == 'All pillars' else kpis[kpis['Pillar'] == sel_pillar]

    kpi_disp = kpi_view[['KPI','Pillar','Annual Target','YTD_Actual',
                          'Percent_Achieved','Score','Weight','Weighted_Score']].copy()
    kpi_disp['Annual Target']    = kpi_disp['Annual Target'].apply(fmt_num)
    kpi_disp['YTD_Actual']       = kpi_disp['YTD_Actual'].apply(fmt_num)
    kpi_disp['Percent_Achieved'] = kpi_disp['Percent_Achieved'].apply(fmt_pct)
    kpi_disp['Weight']           = kpi_disp['Weight'].apply(lambda x: f"{x*100:.0f}%")
    kpi_disp['Score']            = kpi_disp['Score'].apply(fmt_score)
    kpi_disp.columns = ['KPI','Pillar','Annual Target','YTD Actual','Achievement %','Score','Weight','Wtd Score']

    def color_score_cell(v):
        try:
            s = float(v)
            if s >= 4:   return 'background-color:#90EE90'
            elif s >= 3: return 'background-color:#FFE4B5'
            elif s >= 2: return 'background-color:#FFD700'
            else:        return 'background-color:#FFB6C1'
        except: return ''

    st.dataframe(
        kpi_disp.style.map(color_score_cell, subset=['Score']),
        use_container_width=True, hide_index=True)


    # Validation badge on individual view
    period = datetime.now().strftime("%b %Y")
    existing_val = vm.get(selected, period)
    if existing_val:
        st.success(f"✅ Validated by {existing_val['manager']} on "
                   f"{existing_val['validated_at'][:10]} — {existing_val['status']}")

# ── TAB 3: VALIDATION ────────────────────────────────────────────────────
# with tabs[2]:
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

# ── TAB 4: ANALYTICS ─────────────────────────────────────────────────────
# with tabs[3]:
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

# ── TAB 5: STAFF REGISTER ───────────────────────────────────────────────
# with tabs[4]:
st.subheader("Staff register")
st.caption("Live view of all staff in the system — probation, transfers, and employment status.")

reg = st.session_state.get('staff_registry', {})

if not reg:
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

# ── TAB 6: LEAVE MANAGEMENT ──────────────────────────────────────────────
# with tabs[5]:
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
                    value=datetime.now().date() + timedelta(days=LEAVE_TYPES.get(leave_type,{}).get('max_days',21)))
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
            f"{icon} <strong>{lt}</strong> (max {rules['max_days']} days) — "
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

# ── TAB 7: TEAM INSIGHTS ─────────────────────────────────────────────────
