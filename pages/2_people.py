"""pages/2_people.py — People & HR Intelligence Module."""
import streamlit as st
from pathlib import Path
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()


require_access("people")
DATA = Path(__file__).parent.parent / "data"


# Fallbacks in case core.py hasn't been updated yet on this machine
try:
    _ = LEAVE_TYPES
except NameError:
    LEAVE_TYPES = {"Annual Leave":{"days_entitled":21,"description":"21 days","paid":True,"affects_performance":False,"compensation":"pro_rata","color":"var(--brand-primary,#006B3F)"},"Sick Leave":{"days_entitled":14,"description":"14 days","paid":True,"affects_performance":True,"compensation":"exclude_month","color":"#E24B4A"}}
    EXIT_REASONS = ["Resignation — Better opportunity","Resignation — Salary/compensation","Dismissal — Gross misconduct","Dismissal — Performance","Retirement — Mandatory","Contract end — Not renewed","Mutual separation"]
    TRANSFER_REASONS = ["Performance improvement","Branch need","Staff request","Rotational development","Promotion transfer"]
    DISCIPLINARY_CATEGORIES = ["Gross misconduct","Insubordination","Absenteeism","Fraud","Policy violation","Performance negligence"]
    DISCIPLINARY_STAGES = ["Verbal warning","Written warning (1st)","Written warning (final)","Show cause notice","Suspension pending investigation","Disciplinary hearing scheduled","Disciplinary hearing held","Decision — Dismissed","Decision — Exonerated"]
    PIP_DURATIONS = [30, 60, 90]
    PIP_OUTCOMES = ["In progress","Successfully completed","Extended","Terminated — dismissal","Converted to final warning"]
    PIP_REVIEW_FREQUENCIES = ["Weekly","Fortnightly","Monthly"]


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>👥 People</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "HR · Leave management · Performance · Succession planning</span></div>",
    unsafe_allow_html=True)

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores  = st.session_state.get("staff_scores",  pd.DataFrame())
df_proc       = st.session_state.get("df_processed",  pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
action_plans  = st.session_state.get("sbu_action_plans", {})

role_l  = str(ud.get("role","")).lower()
can_all = ud.get("can_view_all", False) or any(k in role_l for k in ("admin","director","md","hr"))

if len(staff_scores) == 0:
    st.markdown(
        "<div style='padding:40px;text-align:center;background:var(--brand-light,#E8F5EE);"
        "border-radius:12px;border:1px solid var(--brand-primary,#006B3F)33'>"
        "<div style='font-size:32px;margin-bottom:12px'>👥</div>"
        "<div style='font-size:18px;font-weight:500;color:var(--brand-primary,#006B3F)'>Upload BSC data to activate People module</div>"
        "</div>", unsafe_allow_html=True)
    st.stop()

# Header
st.markdown(
    "<div style=\'padding:16px 22px;background:#2C3E50;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>People & HR Intelligence</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Leave · Exits · Disciplinary · PIP · Diligence scores</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# Restructured: 2-level navigation for clarity
# ─────────────────────────────────────────────────────────────────
sections = st.tabs([
    "📊 Insights",
    "👥 Records",
    "🏖️ Leave",
    "📋 Discipline & Dev",
])

# ── Section 0: 📊 Insights ─────────────────────────────
with sections[0]:
    sub = st.tabs([
        "📊 HR overview",
        "📈 Team insights",
    ])
    with sub[0]:
        total_staff  = len(staff_scores)
        on_leave     = len(lm.get_active_leave()) if lm else 0
        exits_12m    = len(hr_m.get_exits(12))    if hr_m else 0
        active_pips  = len(hr_m.get_active_pips()) if hr_m else 0
        disc_cases   = len(hr_m.get_active_cases()) if hr_m else 0
        at_risk      = int((staff_scores['Final_BSC_Score'] < 2.5).sum()) if len(staff_scores) else 0

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("Total staff",     total_staff)
        c2.metric("Currently on leave", on_leave,
                  delta=f"{on_leave/total_staff*100:.1f}%" if total_staff else "0%")
        c3.metric("Exits (12 months)", exits_12m,
                  delta=f"-{exits_12m}" if exits_12m else "0", delta_color="inverse")
        c4.metric("Staff on PIP",    active_pips,
                  delta=f"-{active_pips}" if active_pips else "0", delta_color="inverse")
        c5.metric("Open disc. cases",disc_cases,
                  delta=f"-{disc_cases}" if disc_cases else "0", delta_color="inverse")
        c6.metric("At-risk BSC <2.5",at_risk,
                  delta=f"-{at_risk}" if at_risk else "0", delta_color="inverse")

        st.markdown("---")
        ov1, ov2 = st.columns(2)

        with ov1:
            # BSC distribution
            if len(staff_scores):
                bands = pd.DataFrame([
                    {'Band':'Exceeded (≥3.1)','Count':int((staff_scores['Final_BSC_Score']>=3.1).sum()),'Color':'var(--brand-primary,#006B3F)'},
                    {'Band':'Met (3.0–3.1)',  'Count':int(staff_scores['Final_BSC_Score'].between(3.0,3.1).sum()),'Color':'var(--brand-mid,#1D9E75)'},
                    {'Band':'Below (2.5–3.0)','Count':int(staff_scores['Final_BSC_Score'].between(2.5,3.0).sum()),'Color':'#F5A623'},
                    {'Band':'At risk (<2.5)', 'Count':int((staff_scores['Final_BSC_Score']<2.5).sum()),'Color':'#E24B4A'},
                ])
                fig = px.bar(bands, x='Band', y='Count', color='Band',
                             color_discrete_map={r['Band']:r['Color'] for _,r in bands.iterrows()},
                             title='Performance distribution')
                fig.update_layout(height=260, showlegend=False,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig, use_container_width=True)

        with ov2:
            # Leave types in use
            if lm and lm.records:
                lt_counts = {}
                for r in lm.records:
                    lt = r.get('leave_type','Unknown')
                    lt_counts[lt] = lt_counts.get(lt,0) + 1
                lt_df = pd.DataFrame(list(lt_counts.items()), columns=['Leave type','Count'])
                lt_df['Color'] = lt_df['Leave type'].map(lambda x: LEAVE_TYPES.get(x,{}).get('color','#888'))
                fig2 = px.pie(lt_df, names='Leave type', values='Count',
                              title='Leave types (all records)',
                              color='Leave type',
                              color_discrete_map={r['Leave type']:r['Color'] for _,r in lt_df.iterrows()})
                fig2.update_layout(height=260, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No leave records yet.")

        # Trend alerts
        st.markdown("#### HR Alerts")
        alerts = []

        # Declining performance — within band but trending down
        if len(df_proc) and 'Staff Name' in df_proc.columns:
            month_cols = [c for c in df_proc.columns
                          if any(m in str(c) for m in ['Jan','Feb','Mar','Apr','May','Jun',
                                                         'Jul','Aug','Sep','Oct','Nov','Dec'])
                          and 'Target' not in str(c)]
            if len(month_cols) >= 3:
                for name in staff_scores['Staff Name'].tolist():
                    rows = df_proc[df_proc['Staff Name']==name]
                    if len(rows)==0: continue
                    monthly_avgs = []
                    for mc in month_cols[-3:]:
                        if mc in rows.columns:
                            tgt_col = mc.replace(' Actual','') + ' Target' if ' Actual' in mc else None
                            act_vals = pd.to_numeric(rows[mc], errors='coerce').dropna()
                            if len(act_vals): monthly_avgs.append(act_vals.mean())
                    if len(monthly_avgs) == 3 and monthly_avgs[2] < monthly_avgs[0]:
                        drop = monthly_avgs[0] - monthly_avgs[2]
                        if drop / max(monthly_avgs[0], 1) > 0.1:
                            bsc_row = staff_scores[staff_scores['Staff Name']==name]
                            bsc_score = bsc_row['Final_BSC_Score'].values[0] if len(bsc_row) else 0
                            if 2.5 <= bsc_score < 3.2:  # within band but declining
                                alerts.append({
                                    'type':'⚠️ Declining trend',
                                    'staff': name,
                                    'detail': f"BSC {bsc_score:.2f} — performance declining over last 3 months",
                                    'color':'#FAEEDA','border':'#F5A623'
                                })

        # PIP nearing deadline
        if hr_m:
            for pip in hr_m.get_active_pips():
                days_left = hr_m.pip_days_remaining(pip)
                if days_left <= 14:
                    alerts.append({
                        'type':'🚨 PIP deadline',
                        'staff': pip['staff_name'],
                        'detail': f"PIP ends in {days_left} day(s) — review required",
                        'color':'#FDEDEC','border':'#E24B4A'
                    })

        # Disc cases open > 30 days
        if hr_m:
            for case in hr_m.get_active_cases():
                try:
                    opened = datetime.fromisoformat(case['recorded_at'])
                    days_open = (datetime.now() - opened).days
                    if days_open > 30:
                        alerts.append({
                            'type':'🔴 Stalled case',
                            'staff': case['staff_name'],
                            'detail': f"Disciplinary case {case['id']} open for {days_open} days — no resolution",
                            'color':'#FDEDEC','border':'#E24B4A'
                        })
                except: pass

        if not alerts:
            st.success("No HR alerts at this time.")
        else:
            for a in alerts[:10]:
                st.markdown(
                    f"<div style='padding:8px 12px;background:{a['color']};"
                    f"border-left:3px solid {a['border']};border-radius:0 4px 4px 0;"
                    f"font-size:12px;margin:3px 0'>"
                    f"<b>{a['type']}</b> — {a['staff']}: {a['detail']}</div>",
                    unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════
        # ════════════════════════════════════════════════════════════════
        # TAB 2 — STAFF DIRECTORY
        # ════════════════════════════════════════════════════════════════
    with sub[1]:
        st.subheader("Team performance insights")
        team_df = filtered.copy()
        all_names = sorted(team_df['Staff Name'].tolist()) if len(team_df) else []

        if not all_names:
            st.info("No team data available.")
        else:
            tc1,tc2,tc3,tc4,tc5 = st.columns(5)
            tc1.metric("Team size",       len(team_df))
            tc2.metric("Avg BSC",         fmt_score(team_df['Final_BSC_Score'].mean()))
            tc3.metric("Exceeded",        int((team_df['Final_BSC_Score']>=3.1).sum()))
            tc4.metric("Below target",    int((team_df['Final_BSC_Score']<3.0).sum()))
            tc5.metric("Critical (<2.5)", int((team_df['Final_BSC_Score']<2.5).sum()))

            team_kpis = df_proc[df_proc['Staff Name'].isin(all_names)].copy()

            if not team_kpis.empty and 'KPI' in team_kpis.columns:
                kpi_summary = team_kpis.groupby(['KPI','Pillar']).agg(
                    Avg_Score=('Score','mean'), Avg_Achievement=('Percent_Achieved','mean'),
                    Staff_Count=('Staff Name','nunique'),
                    Below_Target=('Score', lambda x: (x < 3.0).sum()),
                    Critical=('Score', lambda x: (x < 2.5).sum()),
                ).reset_index()
                kpi_summary['Below_Target_Pct'] = (kpi_summary['Below_Target']/kpi_summary['Staff_Count']*100).round(0)
                kpi_summary = kpi_summary.sort_values('Avg_Score')

                st.markdown("---")
                st.markdown("### Team-wide weaknesses")
                team_weak = kpi_summary[kpi_summary['Avg_Score'] < 3.0].head(8)
                for _, r in team_weak.iterrows():
                    colour = "#E74C3C" if r['Avg_Score'] < 2.5 else "#F39C12"
                    st.markdown(
                        f"<div style='padding:9px 14px;background:{colour}15;"
                        f"border-left:4px solid {colour};border-radius:5px;margin:4px 0'>"
                        f"<strong>{r['KPI']}</strong> <span style='color:#888;font-size:12px'>({r['Pillar']})</span><br>"
                        f"Avg: <strong>{r['Avg_Score']:.2f}</strong> | {r['Avg_Achievement']:.1f}% achieved | "
                        f"{int(r['Below_Target_Pct'])}% of team below target</div>",
                        unsafe_allow_html=True)

                st.markdown("### Team-wide strengths")
                team_strong = kpi_summary[kpi_summary['Avg_Score']>=3.5].sort_values('Avg_Score', ascending=False).head(5)
                for _, r in team_strong.iterrows():
                    st.markdown(
                        f"<div style='padding:9px 14px;background:#2ECC7115;"
                        f"border-left:4px solid #2ECC71;border-radius:5px;margin:4px 0'>"
                        f"<strong>{r['KPI']}</strong> ({r['Pillar']}) — "
                        f"Avg: <strong>{r['Avg_Score']:.2f}</strong> | {r['Avg_Achievement']:.1f}%"
                        f"</div>", unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("### Individual focus areas")
            for _, staff_row in team_df.sort_values('Final_BSC_Score').iterrows():
                sname = staff_row['Staff Name']
                score = staff_row['Final_BSC_Score']
                remark = staff_row['Performance_Remark']
                rank = staff_row['Overall_Rank']
                with st.expander(
                    f"{'🔴' if score<2.5 else '🟡' if score<3.0 else '🟢'} "
                    f"{sname} — {fmt_score(score)} | {remark} | Rank #{rank}",
                    expanded=(score<2.5)):
                    s_kpis = df_proc[df_proc['Staff Name']==sname]
                    s_insights = get_kpi_insights(s_kpis)
                    render_insight_card(s_insights, sname)

            if not team_kpis.empty and 'Pillar' in team_kpis.columns:
                st.markdown("---")
                st.markdown("### Pillar heatmap")
                pillar_staff = team_kpis.groupby(['Staff Name','Pillar'])['Score'].mean().reset_index()
                pivot = pillar_staff.pivot(index='Staff Name', columns='Pillar', values='Score').fillna(0)
                fig_heat = px.imshow(pivot,
                    color_continuous_scale=[[0,"#E74C3C"],[0.5,"#F39C12"],[0.6,"#FFE4B5"],[1,"#2ECC71"]],
                    zmin=1, zmax=5, title="Score per pillar per staff", aspect="auto", text_auto=".2f")
                fig_heat.update_layout(height=max(300, len(pivot)*28))
                st.plotly_chart(fig_heat, use_container_width=True)

        # ── Payroll Export (end-of-month) ─────────────────────────────────
        # This is in a new sub-tab of the BSC section — add to end of page
        _payroll_expander = st.expander("💰 Payroll Export — BSC scores + commission for payroll", expanded=False)

# ── Section 1: 👥 Records ─────────────────────────────
with sections[1]:
    sub = st.tabs([
        "👤 Staff directory",
        "🚪 Exits & attrition",
        "🔄 Transfers",
    ])
    with sub[0]:
        st.subheader("Staff directory")

        if len(staff_scores) == 0:
            st.info("Upload BSC data to view staff directory.")
        else:
            _vis_dir = staff_scores.copy()
            if not can_all:
                from utils.core_audit import get_visible_staff as _gvs2
                _vis_dir = _gvs2(ud, staff_scores)

            # Search and filter
            d1, d2, d3 = st.columns([2, 1, 1])
            _dsearch = d1.text_input("🔍 Search name or unit", key="dir_search")
            _drole   = d2.selectbox("Role", ["All roles"] + sorted(_vis_dir["Role"].unique().tolist()), key="dir_role")
            _dunit   = d3.selectbox("Unit", ["All units"] + sorted(_vis_dir["Unit"].unique().tolist()), key="dir_unit")

            _dir_df = _vis_dir.copy()
            if _dsearch:
                _dir_df = _dir_df[_dir_df["Staff Name"].str.contains(_dsearch, case=False, na=False) |
                                   _dir_df["Unit"].str.contains(_dsearch, case=False, na=False)]
            if _drole != "All roles":
                _dir_df = _dir_df[_dir_df["Role"] == _drole]
            if _dunit != "All units":
                _dir_df = _dir_df[_dir_df["Unit"] == _dunit]

            st.caption(f"Showing {len(_dir_df)} of {len(_vis_dir)} staff")

            # Card grid — 3 per row
            _dir_rows = [_dir_df.iloc[i:i+3] for i in range(0, len(_dir_df), 3)]
            for _drow in _dir_rows:
                _dcols = st.columns(3)
                for _dci, (_, _dr) in enumerate(zip(_dcols, _drow.iterrows())):
                    _dc  = _dcols[_dci]
                    _, _dr = _dr
                    _name = _dr.get("Staff Name","")
                    _role = _dr.get("Role","")
                    _unit = _dr.get("Unit","")
                    _code = str(_dr.get("Staff Code",""))
                    _bsc  = float(_dr.get("Final_BSC_Score",0) or 0)
                    _rem  = _dr.get("Performance_Remark","—")
                    _clr_map = {"Exceeded By Far":"var(--brand-primary,#006B3F)","Exceeded":"var(--brand-mid,#1D9E75)",
                                "Met":"#F5A623","Partially Met":"#E67E22","Unmet":"#E24B4A"}
                    _bclr = _clr_map.get(_rem,"#9CA3AF")
                    _init = "".join(p[0].upper() for p in _name.split()[:2]) if _name else "?"
                    # Check if on leave
                    _on_lv = ""
                    if lm:
                        _lv_active = [l for l in lm.get_active_leave()
                                      if l.get("staff_name","").lower() == _name.lower()]
                        if _lv_active:
                            _on_lv = f"<span style='background:#FEF3C7;color:#92400E;font-size:9px;padding:1px 5px;border-radius:8px;margin-left:4px'>🏖️ On leave</span>"

                    _dc.markdown(
                        f"<div style='padding:14px;background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);"
                        f"border-radius:10px;margin-bottom:8px;'>"
                        f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px'>"
                        f"<div style='width:38px;height:38px;border-radius:50%;background:{_bclr}20;"
                        f"border:2px solid {_bclr};display:flex;align-items:center;justify-content:center;"
                        f"font-size:13px;font-weight:700;color:{_bclr};flex-shrink:0'>{_init}</div>"
                        f"<div><div style='font-weight:700;font-size:12px;color:var(--color-text-primary)'>{_name}{_on_lv}</div>"
                        f"<div style='font-size:10px;color:var(--color-text-secondary)'>{_role}</div></div></div>"
                        f"<div style='font-size:10px;color:var(--color-text-tertiary);margin-bottom:4px'>📍 {_unit}</div>"
                        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                        f"<span style='font-size:10px;font-weight:600;color:{_bclr}'>BSC {_bsc:.2f}</span>"
                        f"<span style='font-size:9px;background:{_bclr}15;color:{_bclr};"
                        f"padding:2px 7px;border-radius:8px;font-weight:600'>{_rem}</span>"
                        f"</div></div>",
                        unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════
        # TAB 3 — LEAVE MANAGEMENT (was TAB 2)
        # ════════════════════════════════════════════════════════════════
        # TAB 2 — LEAVE MANAGEMENT
        # ════════════════════════════════════════════════════════════════
    with sub[1]:
        st.subheader("Staff exits & attrition analysis")

        ex1, ex2 = st.columns([2,3])

        with ex1:
            st.markdown("#### Record exit")
            with st.form("exit_form"):
                all_staff_names_ex = sorted(staff_scores['Staff Name'].tolist()) if len(staff_scores) else []
                exit_staff  = st.selectbox("Staff member", [""] + all_staff_names_ex, key="ex_staff")
                exit_date   = st.date_input("Exit date", value=date.today(), key="ex_date")
                exit_reason = st.selectbox("Primary reason", EXIT_REASONS, key="ex_reason")
                exit_detail = st.text_area("Detail / exit interview notes", height=80, key="ex_detail")
                ec1, ec2   = st.columns(2)
                tenure     = ec1.number_input("Tenure (years)", min_value=0.0, step=0.5, key="ex_tenure")
                rehire     = ec2.checkbox("Eligible for rehire", value=True, key="ex_rehire")

                if st.form_submit_button("Record exit", type="primary"):
                    if exit_staff:
                        sc_row = staff_scores[staff_scores['Staff Name']==exit_staff]
                        sc  = str(sc_row['Staff Code'].values[0]) if len(sc_row) and 'Staff Code' in sc_row.columns else ''
                        unit = str(sc_row['Unit'].values[0]) if len(sc_row) and 'Unit' in sc_row.columns else ''
                        bsc  = float(sc_row['Final_BSC_Score'].values[0]) if len(sc_row) else None
                        hr_m.record_exit({
                            'staff_code': sc, 'staff_name': exit_staff, 'unit': unit,
                            'exit_date': exit_date, 'reason': exit_reason,
                            'reason_detail': exit_detail, 'final_bsc': bsc,
                            'tenure_years': tenure, 'rehire_eligible': rehire,
                            'recorded_by': uname,
                        })
                        audit_log("EXIT_RECORDED", uname, f"{exit_staff}:{exit_reason}")
                        st.success(f"Exit recorded for {exit_staff}")
                        st.rerun()

        with ex2:
            st.markdown("#### Attrition analytics")
            analytics = hr_m.exit_analytics() if hr_m else {}

            if not analytics or analytics.get('total',0) == 0:
                st.info("No exit records yet. Record exits to see analytics.")
            else:
                ec1,ec2,ec3 = st.columns(3)
                ec1.metric("Total exits (all time)", analytics['total'])
                ec2.metric("Avg tenure at exit", f"{analytics['avg_tenure']:.1f} yrs")
                if analytics.get('avg_bsc_at_exit'):
                    ec3.metric("Avg BSC at exit", f"{analytics['avg_bsc_at_exit']:.2f}")

                if analytics.get('by_reason'):
                    by_r = pd.DataFrame(list(analytics['by_reason'].items()),
                                        columns=['Reason','Count']).sort_values('Count', ascending=False)
                    fig = px.bar(by_r, x='Count', y='Reason', orientation='h',
                                 title='Exits by reason', color='Count',
                                 color_continuous_scale=['#E8F5EE','var(--brand-primary,#006B3F)'])
                    fig.update_layout(height=300, showlegend=False,
                        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig, use_container_width=True)

                if analytics.get('by_unit'):
                    by_u = pd.DataFrame(list(analytics['by_unit'].items()),
                                        columns=['Unit','Exits']).sort_values('Exits', ascending=False)
                    st.markdown("**Exits by unit (top 10)**")
                    st.dataframe(by_u.head(10), hide_index=True, use_container_width=True)

        # Exit records table
        st.markdown("---")
        st.markdown("#### Exit records")
        exits_list = hr_m.exits if hr_m else []
        if exits_list:
            ex_df = pd.DataFrame([{
                'ID': e['id'], 'Name': e['staff_name'], 'Unit': e['unit'],
                'Exit date': e['exit_date'], 'Reason': e['reason'],
                'Tenure': f"{e.get('tenure_years',0):.1f}y",
                'BSC': f"{e['final_bsc']:.2f}" if e.get('final_bsc') else '—',
                'Rehire': '✅' if e.get('rehire_eligible') else '❌',
            } for e in exits_list])
            st.dataframe(ex_df, use_container_width=True, hide_index=True)

        # ════════════════════════════════════════════════════════════════
        # TAB 4 — TRANSFERS
        # ════════════════════════════════════════════════════════════════
    with sub[2]:
        st.subheader("Staff transfers")
        st.caption("Track transfers and analyse their impact on performance.")

        tr1, tr2 = st.columns([2,3])

        with tr1:
            st.markdown("#### Record transfer")
            all_units = sorted(set(
                list(BRANCH_REGION.keys()) +
                ['ICT','HR','Finance','Operations','Products','DFS','SME Banking',
                 'Corporate Banking','Commercial Banking','Procurement']
            ))
            with st.form("transfer_form"):
                tr_staff   = st.selectbox("Staff member", [""] + sorted(staff_scores['Staff Name'].tolist() if len(staff_scores) else []))
                tc1, tc2   = st.columns(2)
                tr_from    = tc1.selectbox("From unit", [""] + all_units, key="tr_from")
                tr_to      = tc2.selectbox("To unit",   [""] + all_units, key="tr_to")
                tr_date    = st.date_input("Transfer date", value=date.today())
                tr_reason  = st.selectbox("Reason", TRANSFER_REASONS)
                tc3, tc4   = st.columns(2)
                bsc_before = tc3.number_input("BSC score before", min_value=0.0, max_value=5.0, step=0.01, value=0.0)
                bsc_after  = tc4.number_input("BSC score after (if known)", min_value=0.0, max_value=5.0, step=0.01, value=0.0)

                if st.form_submit_button("Record transfer", type="primary"):
                    if tr_staff and tr_from and tr_to:
                        sc_row = staff_scores[staff_scores['Staff Name']==tr_staff]
                        sc = str(sc_row['Staff Code'].values[0]) if len(sc_row) and 'Staff Code' in sc_row.columns else ''
                        hr_m.record_transfer({
                            'staff_code': sc, 'staff_name': tr_staff,
                            'from_unit': tr_from, 'to_unit': tr_to,
                            'from_region': BRANCH_REGION.get(tr_from,'Head Office'),
                            'to_region': BRANCH_REGION.get(tr_to,'Head Office'),
                            'transfer_date': tr_date, 'reason': tr_reason,
                            'bsc_before': bsc_before or None,
                            'bsc_after': bsc_after or None,
                            'initiated_by': uname,
                        })
                        audit_log("TRANSFER_RECORDED", uname, f"{tr_staff}:{tr_from}→{tr_to}")
                        st.success(f"Transfer recorded for {tr_staff}")
                        st.rerun()
                    else:
                        st.error("Staff, from unit and to unit are required.")

        with tr2:
            st.markdown("#### Transfer impact analysis")
            transfers = hr_m.get_transfers(24) if hr_m else []

            if not transfers:
                st.info("No transfer records yet.")
            else:
                # Impact: BSC before vs after
                impact_data = [t for t in transfers
                               if t.get('bsc_before') and t.get('bsc_after')]
                if impact_data:
                    impact_df = pd.DataFrame([{
                        'Staff': t['staff_name'],
                        'From': t['from_unit'],'To': t['to_unit'],
                        'Reason': t['reason'],
                        'BSC before': t['bsc_before'],
                        'BSC after': t['bsc_after'],
                        'Change': round(float(t['bsc_after'])-float(t['bsc_before']),2),
                    } for t in impact_data])
                    impact_df['Outcome'] = impact_df['Change'].apply(
                        lambda x: '✅ Improved' if x > 0.1 else ('❌ Declined' if x < -0.1 else '➡️ Neutral'))
                    st.dataframe(impact_df, use_container_width=True, hide_index=True)

                    avg_change = impact_df['Change'].mean()
                    pos = (impact_df['Change'] > 0.1).sum()
                    neg = (impact_df['Change'] < -0.1).sum()
                    tc1,tc2,tc3 = st.columns(3)
                    tc1.metric("Avg BSC change", f"{avg_change:+.2f}")
                    tc2.metric("Improved after transfer", pos)
                    tc3.metric("Declined after transfer", neg)
                else:
                    tr_df = pd.DataFrame([{
                        'Staff': t['staff_name'], 'From': t['from_unit'],
                        'To': t['to_unit'], 'Date': t['transfer_date'],
                        'Reason': t['reason'],
                    } for t in transfers])
                    st.dataframe(tr_df, use_container_width=True, hide_index=True)

        # ════════════════════════════════════════════════════════════════
        # TAB 5 — DISCIPLINARY
        # ════════════════════════════════════════════════════════════════

# ── Section 2: 🏖️ Leave ─────────────────────────────
with sections[2]:
    sub = st.tabs([
        "🏖️ Leave management",
        "📅 Leave calendar",
    ])
    with sub[0]:
        st.subheader("Leave management")

        # ── Who can do what ───────────────────────────────────────────────
        _lv_role     = str(ud.get("role","")).lower()
        _lv_is_mgr   = (ud.get("is_admin") or
                        any(k in _lv_role for k in ("manager","director","head of","regional","hr","admin")))
        _lv_my_name  = ud.get("full_name","")
        _lv_my_sc    = str(ud.get("staff_code","") or uname)
        _lv_my_unit  = ud.get("unit","")
        _lv_my_role  = ud.get("role","")

        lv_tabs = st.tabs(["📝 Apply for leave",
                           "✅ Manager approvals" if _lv_is_mgr else "📋 My leave",
                           "📊 Team overview",
                           "📜 All records (HR)"])

        # ── TAB A: Staff applies for leave ────────────────────────────────
        with lv_tabs[0]:
            st.markdown("#### Apply for leave")
            st.caption("Submit a leave application. Your line manager will receive it for approval.")

            with st.form("leave_apply_form"):
                la1, la2 = st.columns(2)
                la_type   = la1.selectbox("Leave type", list(LEAVE_TYPES.keys()))
                la_relief = la2.text_input("Relief staff (optional)",
                    placeholder="Who covers your duties?")
                la_start  = la1.date_input("From", value=date.today())
                la_end    = la2.date_input("To", value=date.today())
                la_reason = st.text_area("Reason *", height=70,
                    placeholder="Please provide a brief reason for your leave request")

                lt_info = LEAVE_TYPES.get(la_type, {})
                _entitled = lt_info.get('days_entitled', 0) or 0
                # Calculate days already taken this year
                _yr_taken = sum(r.get("days",0) for r in lm.records
                               if r.get("staff_code")==_lv_my_sc
                               and r.get("leave_type")==la_type
                               and str(r.get("start_date",""))[:4] == str(date.today().year)
                               and r.get("approved") is not False)
                _balance = max(0, _entitled - _yr_taken)
                _req_days = (la_end - la_start).days + 1 if la_end >= la_start else 0

                st.markdown(
                    f"<div style='padding:8px 12px;background:var(--brand-light,#E8F5EE);"
                    f"border-left:3px solid var(--brand-primary,#006B3F);border-radius:0 6px 6px 0;"
                    f"font-size:11px;margin:4px 0'>"
                    f"<b>{la_type}</b> · {lt_info.get('description','')} · "
                    f"Paid: {'✅' if lt_info.get('paid') else '❌'} · "
                    f"Balance: <b>{_balance}/{_entitled} days</b> remaining · "
                    f"Requesting: <b>{_req_days} day(s)</b>"
                    f"{'<span style="color:#E24B4A"> ⚠️ Exceeds balance</span>' if _req_days > _balance and _entitled > 0 else ''}"
                    f"</div>", unsafe_allow_html=True)

                if st.form_submit_button("📤 Submit leave application", type="primary",
                                          use_container_width=True):
                    if not la_reason.strip():
                        st.error("Please provide a reason.")
                    elif la_end < la_start:
                        st.error("End date must be on or after start date.")
                    else:
                        lid = lm.apply_leave(
                            _lv_my_sc, _lv_my_name, _lv_my_role, _lv_my_unit,
                            la_type, la_start, la_end, la_reason, la_relief)
                        audit_log("LEAVE_APPLIED", uname, f"{la_type}:{la_start}:{la_end}")
                        st.success(f"✅ Leave application {lid} submitted. "
                                   "Your manager will review and approve it.")
                        st.rerun()

            # Show my own pending/approved leaves
            st.markdown("#### My recent leave requests")
            _my_leaves = lm.get_staff_leave(_lv_my_sc)
            if _my_leaves:
                for _lr in sorted(_my_leaves, key=lambda x: x.get("applied_at",""), reverse=True)[:8]:
                    _st  = _lr.get("status","")
                    _clr = {"Approved":"var(--brand-primary,#006B3F)","Rejected":"#E24B4A","Pending":"#F5A623"}.get(_st,"#9CA3AF")
                    _bg  = {"Approved":"#F0FDF4","Rejected":"#FEF2F2","Pending":"#FFFBEB"}.get(_st,"#F9FAFB")
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{_bg};"
                        f"border-left:3px solid {_clr};border-radius:0 6px 6px 0;margin:4px 0;font-size:11px'>"
                        f"<b>{_lr.get('leave_type','')}</b> · "
                        f"{_lr.get('start_date','')} → {_lr.get('end_date','')} ({_lr.get('days',0)}d) · "
                        f"<span style='color:{_clr};font-weight:700'>{_st}</span>"
                        f"{'  ·  Reason: ' + _lr.get('rejection_reason','') if _st=='Rejected' else ''}"
                        f"</div>", unsafe_allow_html=True)
            else:
                st.info("No leave records yet.")

            st.markdown("#### Leave entitlements (Kenya Employment Act 2007)")
            ent_data = [[lt, info.get('days_entitled','Discretionary') or 'Discretionary',
                         '✅' if info.get('paid') else '❌',
                         info.get('description','')]
                        for lt, info in LEAVE_TYPES.items() if lt != 'Public Holiday']
            st.dataframe(pd.DataFrame(ent_data, columns=['Leave type','Days','Paid','Notes']),
                         hide_index=True, use_container_width=True)

        # ── TAB B: Manager approval queue ────────────────────────────────
        with lv_tabs[1]:
            if _lv_is_mgr:
                st.markdown("#### Pending leave approvals")
                _pending = lm.get_pending_approvals(manager_unit=_lv_my_unit if not can_all else None)
                if not _pending:
                    st.success("✅ No pending leave requests.")
                else:
                    st.info(f"**{len(_pending)} request(s) awaiting your approval.**")
                    for _pr in _pending:
                        _pr_id = str(_pr.get("id",""))
                        with st.expander(
                                f"{'🕐'} {_pr.get('staff_name','')} — {_pr.get('leave_type','')} · "
                                f"{_pr.get('start_date','')} to {_pr.get('end_date','')} ({_pr.get('days',0)}d)",
                                expanded=True):
                            pa1, pa2 = st.columns(2)
                            pa1.markdown(
                                "**Staff:** " + _pr.get("staff_name","") + "  \n"
                                "**Role:** " + _pr.get("staff_role","") + "  \n"
                                "**Unit:** " + _pr.get("staff_unit","") + "  \n"
                                "**Applied:** " + str(_pr.get("applied_at",""))[:10])
                            pa2.markdown(
                                "**Leave type:** " + _pr.get("leave_type","") + "  \n"
                                "**Period:** " + _pr.get("start_date","") + " to " + _pr.get("end_date","") + "  \n"
                                "**Days:** " + str(_pr.get("days",0)) + "  \n"
                                "**Relief:** " + (_pr.get("relief_staff","—") or "—"))
                            st.markdown(f"**Reason:** {_pr.get('reason','')}")

                            _rej_key = f"rej_reason_{_pr_id}"
                            _rej_txt = st.text_input("Rejection reason (if rejecting)",
                                                       key=_rej_key, placeholder="Optional")
                            _ab1, _ab2 = st.columns(2)
                            if _ab1.button("✅ Approve", key=f"appr_{_pr_id}",
                                           type="primary", use_container_width=True):
                                lm.approve_leave(_pr_id, uname, approve=True)
                                audit_log("LEAVE_APPROVED", uname,
                                          f"{_pr.get('staff_name','')}:{_pr.get('leave_type','')}")
                                st.toast("✅ Leave approved", icon="✅")
                                st.rerun()
                            if _ab2.button("❌ Reject", key=f"rejt_{_pr_id}",
                                           use_container_width=True):
                                lm.approve_leave(_pr_id, uname, approve=False,
                                                reason=st.session_state.get(_rej_key,""))
                                audit_log("LEAVE_REJECTED", uname,
                                          f"{_pr.get('staff_name','')}")
                                st.toast("❌ Leave rejected", icon="❌")
                                st.rerun()

                # HR record: recently approved (auto-populates)
                st.markdown("---")
                st.markdown("#### Recently approved (HR auto-record)")
                _recent_appr = [r for r in lm.records
                                if r.get("approved") is True
                                and r.get("hr_notified")]
                if _recent_appr:
                    _hr_df = pd.DataFrame([{
                        "ID": r.get("id",""), "Staff": r.get("staff_name",""),
                        "Type": r.get("leave_type",""),
                        "From": r.get("start_date",""), "To": r.get("end_date",""),
                        "Days": r.get("days",0), "Approved by": r.get("approved_by",""),
                    } for r in sorted(_recent_appr,
                                      key=lambda x: x.get("approved_at",""), reverse=True)[:20]])
                    st.dataframe(_hr_df, hide_index=True, use_container_width=True)
                else:
                    st.info("No approved leaves yet.")
            else:
                # Non-manager: show their own leave history
                st.markdown("#### My leave history")
                _my_all = lm.get_staff_leave(_lv_my_sc)
                if _my_all:
                    _mh_df = pd.DataFrame([{
                        "Type": r.get("leave_type",""),
                        "From": r.get("start_date",""), "To": r.get("end_date",""),
                        "Days": r.get("days",0),
                        "Status": r.get("status","Pending"),
                        "Approved by": r.get("approved_by","—"),
                    } for r in _my_all])
                    def _hl_st(v):
                        if v=="Approved": return "color:var(--brand-primary,#006B3F);font-weight:600"
                        if v=="Rejected": return "color:#E24B4A"
                        return "color:#F5A623"
                    st.dataframe(_mh_df.style.map(_hl_st, subset=["Status"]),
                                 hide_index=True, use_container_width=True)
                else:
                    st.info("No leave history.")

        with lv_tabs[2]:
            st.markdown("#### Leave register")
            all_leave = lm.records if lm else []

            # Filter options
            fc1, fc2 = st.columns(2)
            filter_type   = fc1.selectbox("Filter by type", ["All"] + list(LEAVE_TYPES.keys()), key="lv_type")
            filter_status = fc2.selectbox("Status", ["All","Active","Upcoming","Completed"], key="lv_status")

            disp_leave = all_leave.copy()
            if filter_type   != "All": disp_leave = [r for r in disp_leave if r.get('leave_type')==filter_type]
            if filter_status != "All": disp_leave = [r for r in disp_leave if r.get('status')==filter_status]

            if not disp_leave:
                st.info("No leave records matching filter.")
            else:
                leave_df = pd.DataFrame([{
                    'Staff':      r.get('staff_name',''),
                    'Type':       r.get('leave_type',''),
                    'Start':      r.get('start_date',''),
                    'End':        r.get('end_date',''),
                    'Days':       r.get('days',0),
                    'Status':     r.get('status',''),
                    'Approved by':r.get('approved_by',''),
                } for r in disp_leave])
                st.dataframe(leave_df, use_container_width=True, hide_index=True)

            # Currently on leave highlight
            active_now = lm.get_active_leave() if lm else []
            if active_now:
                st.markdown(f"**{len(active_now)} staff currently on leave:**")
                for r in active_now:
                    lt_color = LEAVE_TYPES.get(r.get('leave_type',''),{}).get('color','#888')
                    st.markdown(
                        f"<div style='padding:5px 10px;background:#F8F8F8;"
                        f"border-left:4px solid {lt_color};font-size:12px;margin:2px 0'>"
                        f"<b>{r['staff_name']}</b> — {r['leave_type']} "
                        f"({r['start_date']} to {r['end_date']}, {r['days']} days)"
                        f"</div>", unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════════════
        # ════════════════════════════════════════════════════════════════
        # TAB 4 — LEAVE CALENDAR
        # ════════════════════════════════════════════════════════════════
    with sub[1]:
        st.subheader("Leave calendar")
        if not lm or not lm.records:
            st.info("No leave records yet.")
        else:
            import calendar as _cal
            _today_lc = date.today()
            _lc1, _lc2 = st.columns([1, 3])
            _sel_month = _lc1.selectbox("Month", list(range(1,13)),
                index=_today_lc.month-1, format_func=lambda m: _cal.month_name[m], key="lc_month")
            _sel_year  = _lc1.selectbox("Year", [2025, 2026, 2027],
                index=1, key="lc_year")

            # Get leave in this month
            _mo_start = date(_sel_year, _sel_month, 1)
            _mo_end   = date(_sel_year, _sel_month, _cal.monthrange(_sel_year, _sel_month)[1])

            _mo_leaves = []
            for _r in lm.records:
                try:
                    _s = _safe_date(str(_r.get("start_date",""))[:10])
                    _e = _safe_date(str(_r.get("end_date",""))[:10])
                    if _s <= _mo_end and _e >= _mo_start:
                        _mo_leaves.append(_r)
                except: pass

            # Build a simple calendar grid
            _days_in_month = _cal.monthrange(_sel_year, _sel_month)[1]
            # Show coloured leave bars per staff
            if _mo_leaves:
                _lc_staff = sorted(set(l.get("staff_name","") for l in _mo_leaves))
                _lc2.caption(f"{len(_mo_leaves)} leave record(s) · {len(_lc_staff)} staff on leave this month")

                # Simple table: rows = staff, columns = day numbers
                _lcols_hdr = ["Staff","Role"] + [str(d) for d in range(1, _days_in_month+1)]
                _lc_rows = []
                for _snm in _lc_staff:
                    _snm_leaves = [l for l in _mo_leaves if l.get("staff_name","")==_snm]
                    _row = {"Staff":_snm,
                            "Role":_snm_leaves[0].get("role","") if _snm_leaves else ""}
                    for _d in range(1, _days_in_month+1):
                        _dt = date(_sel_year, _sel_month, _d)
                        _on = any(_safe_date(str(l.get("start_date",""))[:10]) <= _dt <=
                                  _safe_date(str(l.get("end_date",""))[:10])
                                  for l in _snm_leaves)
                        _row[str(_d)] = "●" if _on else ""
                    _lc_rows.append(_row)

                if _lc_rows:
                    _lc_df = pd.DataFrame(_lc_rows)
                    def _lc_hl(v):
                        return "color:var(--brand-primary,#006B3F);font-weight:700" if v=="●" else ""
                    day_cols = [str(d) for d in range(1,_days_in_month+1)]
                    _lc2.dataframe(
                        _lc_df.style.map(_lc_hl, subset=day_cols),
                        use_container_width=True, hide_index=True, height=350)
            else:
                _lc2.info(f"No leave records for {_cal.month_name[_sel_month]} {_sel_year}.")

            # Summary stats
            _lc_st1, _lc_st2, _lc_st3 = st.columns(3)
            _lc_st1.metric("On leave this month", len(_mo_leaves))
            _lc_st2.metric("Total leave days", sum(
                (min(_mo_end, _safe_date(str(l.get("end_date",""))[:10])) -
                 max(_mo_start, _safe_date(str(l.get("start_date",""))[:10]))).days + 1
                for l in _mo_leaves
                if l.get("start_date") and l.get("end_date")))
            _approved = sum(1 for l in _mo_leaves if l.get("approved"))
            _lc_st3.metric("Approved", _approved)

        # TAB 3 — EXITS & ATTRITION (now TAB 5)
        # TAB 3 — EXITS & ATTRITION
        # ════════════════════════════════════════════════════════════════

# ── Section 3: 📋 Discipline & Dev ─────────────────────────────
with sections[3]:
    sub = st.tabs([
        "⚖️ Disciplinary",
        "📋 PIP management",
        "🎯 Diligence scores",
    ])
    with sub[0]:
        st.subheader("Disciplinary case management")
        st.caption("All cases are confidential. Access controlled by HR and administration roles.")

        if not can_all:
            st.warning("Disciplinary records are restricted to HR and administration.")
            st.stop()

        dc1, dc2 = st.columns([2,3])

        with dc1:
            st.markdown("#### Open new case")
            with st.form("disc_form"):
                dc_staff  = st.selectbox("Staff member", [""] + sorted(staff_scores['Staff Name'].tolist() if len(staff_scores) else []))
                dc_cat    = st.selectbox("Category", DISCIPLINARY_CATEGORIES)
                dc_date   = st.date_input("Incident date", value=date.today())
                dc_desc   = st.text_area("Description of incident", height=100)

                if st.form_submit_button("Open case", type="primary"):
                    if dc_staff and dc_desc:
                        sc_row = staff_scores[staff_scores['Staff Name']==dc_staff]
                        sc   = str(sc_row['Staff Code'].values[0]) if len(sc_row) and 'Staff Code' in sc_row.columns else ''
                        unit = str(sc_row['Unit'].values[0]) if len(sc_row) and 'Unit' in sc_row.columns else ''
                        hr_m.open_case({
                            'staff_code': sc, 'staff_name': dc_staff,
                            'unit': unit, 'category': dc_cat,
                            'incident_date': dc_date,
                            'description': dc_desc, 'opened_by': uname,
                        })
                        audit_log("DISC_CASE_OPENED", uname, f"{dc_staff}:{dc_cat}")
                        st.success(f"Case opened for {dc_staff}")
                        st.rerun()
                    else:
                        st.error("Staff and description are required.")

        with dc2:
            st.markdown("#### Active cases")
            active_cases = hr_m.get_active_cases() if hr_m else []

            if not active_cases:
                st.success("No open disciplinary cases.")
            else:
                for case in active_cases:
                    opened  = datetime.fromisoformat(case['recorded_at'])
                    days_open = (datetime.now() - opened).days
                    urgency = '🔴' if days_open > 30 else ('🟡' if days_open > 14 else '🟢')

                    with st.expander(
                        f"{urgency} {case['id']} — {case['staff_name']} | {case['category']} | "
                        f"Stage: {case['stage']} | {days_open}d open", expanded=(days_open>30)):

                        st.caption(f"Unit: {case['unit']} | Incident: {case['incident_date']}")
                        st.markdown(f"**Incident:** {case['description']}")

                        # Stage progression
                        st.markdown("**Advance stage:**")
                        with st.form(f"disc_advance_{case['id']}"):
                            cur_idx = DISCIPLINARY_STAGES.index(case['stage']) if case['stage'] in DISCIPLINARY_STAGES else 0
                            next_stages = DISCIPLINARY_STAGES[cur_idx+1:] if cur_idx+1 < len(DISCIPLINARY_STAGES) else []
                            if next_stages:
                                new_stage = st.selectbox("Next stage", next_stages, key=f"ns_{case['id']}")
                                stage_note= st.text_input("Note", key=f"sn_{case['id']}")
                                if st.form_submit_button("Advance", type="primary"):
                                    hr_m.advance_stage(case['id'], new_stage, stage_note, uname)
                                    audit_log("DISC_STAGE", uname, f"{case['id']}:{new_stage}")
                                    st.success("Stage updated")
                                    st.rerun()
                            else:
                                st.info("Case is at final stage.")

                        # Stage history
                        if case.get('stage_history'):
                            st.markdown("**Stage history:**")
                            for s in case['stage_history']:
                                st.caption(f"  {s['date']} — {s['stage']} (by {s['by']})")

        # All cases table
        st.markdown("---")
        all_cases = hr_m.disciplinary if hr_m else []
        if all_cases:
            cases_df = pd.DataFrame([{
                'ID': c['id'], 'Staff': c['staff_name'], 'Unit': c['unit'],
                'Category': c['category'], 'Stage': c['stage'],
                'Status': c['status'], 'Incident date': c['incident_date'],
                'Outcome': c.get('outcome','—'),
            } for c in all_cases])
            st.dataframe(cases_df, use_container_width=True, hide_index=True)

        # ════════════════════════════════════════════════════════════════
        # TAB 6 — PIP MANAGEMENT
        # ════════════════════════════════════════════════════════════════
    with sub[1]:
        st.subheader("Performance Improvement Plan (PIP) management")
        st.caption("Structured, time-bound improvement plans with milestone tracking and HR discussion support.")

        pip_tabs = st.tabs(["📋 Active PIPs", "➕ Open new PIP", "📊 PIP analytics"])

        with pip_tabs[0]:
            active_pips = hr_m.get_active_pips() if hr_m else []
            if not active_pips:
                st.success("No active PIPs. All staff are performing within expectations.")
            else:
                for pip in active_pips:
                    days_left = hr_m.pip_days_remaining(pip)
                    urgency   = '🔴' if days_left <= 7 else ('🟡' if days_left <= 14 else '🟢')
                    prog_pct  = max(0, round((pip['duration_days']-days_left)/pip['duration_days']*100,0))

                    with st.expander(
                        f"{urgency} {pip['id']} — {pip['staff_name']} | {pip['unit']} | "
                        f"{days_left}d remaining | {prog_pct:.0f}% elapsed",
                        expanded=(days_left <= 14)):

                        pc1, pc2, pc3 = st.columns(3)
                        pc1.metric("Days remaining", days_left)
                        pc2.metric("Current BSC",
                                   f"{pip['current_bsc']:.2f}" if pip.get('current_bsc') else '—')
                        pc3.metric("Target BSC",
                                   f"{pip['target_bsc']:.2f}" if pip.get('target_bsc') else '3.00')

                        st.progress(prog_pct/100, text=f"PIP progress: {prog_pct:.0f}%")

                        # Performance gaps
                        if pip.get('performance_gaps'):
                            st.markdown("**Performance gaps addressed:**")
                            for g in pip['performance_gaps']:
                                st.markdown(f"  • {g}")

                        # Objectives
                        if pip.get('objectives'):
                            st.markdown("**SMART objectives:**")
                            for o in pip['objectives']:
                                st.markdown(f"  ✓ {o}")

                        # Support offered
                        if pip.get('support_offered'):
                            st.markdown(f"**Support offered:** {pip['support_offered']}")

                        # Review history
                        if pip.get('reviews'):
                            st.markdown(f"**Review history ({len(pip['reviews'])} reviews):**")
                            for rv in pip['reviews'][-3:]:
                                status_ico = '✅' if rv.get('score',0) >= float(pip.get('target_bsc',3)) else '⚠️'
                                st.markdown(
                                    f"<div style='padding:6px 10px;background:#F8F8F8;"
                                    f"border-left:3px solid var(--brand-primary,#006B3F);font-size:12px;margin:2px 0'>"
                                    f"{status_ico} <b>{rv['date']}</b> — Score: {rv.get('score','—')} | "
                                    f"{rv.get('progress','')} (by {rv.get('by','')})</div>",
                                    unsafe_allow_html=True)

                        # Discussion helper
                        with st.expander("💬 HR discussion guide for this PIP review"):
                            st.markdown("""
        **Opening the review:**
        - "This is a safe space to discuss your progress and challenges."
        - "I want to start by acknowledging what you've achieved since our last meeting."

        **Progress assessment:**
        - "Walk me through your performance against each objective."
        - "What has worked well? What has been most challenging?"
        - "Are there any barriers I haven't addressed that are preventing your progress?"

        **If progressing well:**
        - "Your improvement shows real commitment. Let's talk about sustaining this."
        - "What support do you need to maintain this trajectory?"

        **If not progressing:**
        - "I'm concerned about [specific gap]. What's your perspective on why this is happening?"
        - "What would need to change for you to meet this objective?"
        - "I want to be honest — if we don't see improvement in [specific area] by [date], we'll need to discuss next steps."

        **Closing:**
        - "Let's agree on the specific actions between now and our next review."
        - "My door is always open — please reach out if you hit a wall before our next meeting."
                            """)

                        # Add review
                        st.markdown("---")
                        st.markdown("**Add review entry:**")
                        with st.form(f"pip_review_{pip['id']}"):
                            rv1, rv2 = st.columns(2)
                            rv_score    = rv1.number_input("BSC score at review", 0.0, 5.0, step=0.01, key=f"rvs_{pip['id']}")
                            rv_outcome  = rv2.selectbox("Outcome", PIP_OUTCOMES, key=f"rvo_{pip['id']}")
                            rv_progress = st.text_area("Progress notes", height=60, key=f"rvp_{pip['id']}")
                            rv_concerns = st.text_area("Concerns / support needed", height=60, key=f"rvc_{pip['id']}")

                            if st.form_submit_button("Save review", type="primary"):
                                hr_m.add_pip_review(pip['id'], {
                                    'score': rv_score, 'outcome': rv_outcome,
                                    'progress': rv_progress, 'concerns': rv_concerns,
                                    'by': uname,
                                })
                                audit_log("PIP_REVIEW", uname, f"{pip['id']}:{rv_outcome}")
                                st.success("Review recorded")
                                st.rerun()

        with pip_tabs[1]:
            st.markdown("#### Open a new Performance Improvement Plan")
            all_staff_pip = sorted(staff_scores['Staff Name'].tolist()) if len(staff_scores) else []

            # Pre-fill with at-risk staff
            at_risk_staff = staff_scores[staff_scores['Final_BSC_Score'] < 2.8]['Staff Name'].tolist() if len(staff_scores) else []
            if at_risk_staff:
                st.markdown(
                    f"<div style='padding:8px 12px;background:#FFFBF0;"
                    f"border-left:3px solid #F5A623;font-size:12px;margin:4px 0'>"
                    f"⚠️ <b>{len(at_risk_staff)} staff</b> scoring below 2.8 — consider PIP: "
                    f"{', '.join(at_risk_staff[:5])}"
                    f"{'...' if len(at_risk_staff)>5 else ''}</div>",
                    unsafe_allow_html=True)

            with st.form("pip_open_form"):
                pip_staff   = st.selectbox("Staff member *", [""] + all_staff_pip)
                pp1, pp2, pp3 = st.columns(3)
                pip_start   = pp1.date_input("PIP start date", value=date.today())
                pip_dur     = pp2.selectbox("Duration (days)", PIP_DURATIONS)
                pip_freq    = pp3.selectbox("Review frequency", PIP_REVIEW_FREQUENCIES)

                pip_reason  = st.text_area("Reason for PIP *",
                    placeholder="Describe the performance gaps that necessitate this PIP", height=80)

                st.markdown("**Performance gaps (one per line)**")
                pip_gaps_text = st.text_area("Gaps", height=80, placeholder="e.g. Deposit growth at 45% of target for 3 consecutive months")

                st.markdown("**SMART objectives (one per line)**")
                pip_obj_text = st.text_area("Objectives", height=80,
                    placeholder="e.g. Achieve minimum 70% deposit target by end of PIP period")

                pip_support = st.text_area("Support and resources offered",
                    placeholder="e.g. Weekly coaching with Branch Manager, sales training, paired with top performer", height=60)

                pip_manager = st.text_input("PIP manager (reviewing manager)", value=uname)
                pip_hr      = st.text_input("HR officer", value="")

                sc_row = staff_scores[staff_scores['Staff Name']==pip_staff] if pip_staff else pd.DataFrame()
                current_bsc = float(sc_row['Final_BSC_Score'].values[0]) if len(sc_row) else None

                if st.form_submit_button("Open PIP", type="primary"):
                    if pip_staff and pip_reason:
                        sc = str(sc_row['Staff Code'].values[0]) if len(sc_row) and 'Staff Code' in sc_row.columns else ''
                        unit = str(sc_row['Unit'].values[0]) if len(sc_row) and 'Unit' in sc_row.columns else ''
                        role = str(sc_row['Role'].values[0]) if len(sc_row) and 'Role' in sc_row.columns else ''
                        hr_m.open_pip({
                            'staff_code': sc, 'staff_name': pip_staff, 'unit': unit, 'role': role,
                            'manager': pip_manager, 'hr_officer': pip_hr,
                            'start_date': pip_start, 'duration_days': pip_dur,
                            'reason': pip_reason,
                            'performance_gaps': [g.strip() for g in pip_gaps_text.split('\n') if g.strip()],
                            'objectives':       [o.strip() for o in pip_obj_text.split('\n') if o.strip()],
                            'support_offered':  pip_support,
                            'review_frequency': pip_freq,
                            'current_bsc': current_bsc,
                            'target_bsc': 3.0,
                            'opened_by': uname,
                        })
                        audit_log("PIP_OPENED", uname, f"{pip_staff}")
                        st.success(f"PIP opened for {pip_staff}. Duration: {pip_dur} days.")
                        st.rerun()
                    else:
                        st.error("Staff member and reason are required.")

        with pip_tabs[2]:
            all_pips = hr_m.pips if hr_m else []
            if not all_pips:
                st.info("No PIP records yet.")
            else:
                p1,p2,p3,p4 = st.columns(4)
                completed = [p for p in all_pips if p['outcome']=='Successfully completed']
                dismissed = [p for p in all_pips if 'dismissal' in p['outcome'].lower()]
                extended  = [p for p in all_pips if p['outcome']=='Extended']
                p1.metric("Total PIPs", len(all_pips))
                p2.metric("Completed successfully", len(completed))
                p3.metric("Terminated/dismissed", len(dismissed))
                p4.metric("Extended", len(extended))

                outcomes = {}
                for p in all_pips:
                    o = p['outcome']; outcomes[o] = outcomes.get(o,0)+1
                out_df = pd.DataFrame(list(outcomes.items()), columns=['Outcome','Count'])
                fig = px.pie(out_df, names='Outcome', values='Count', title='PIP outcomes')
                fig.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig, use_container_width=True)

        # ════════════════════════════════════════════════════════════════
        # TAB 7 — DILIGENCE SCORES
        # ════════════════════════════════════════════════════════════════
    with sub[2]:
        st.subheader("Staff diligence scores")
        st.caption("Composite score (0–100) measuring execution, accountability, conduct, and attendance.")

        st.markdown(
            "<div style='padding:10px 14px;background:var(--brand-light,#E8F5EE);"
            "border-left:3px solid var(--brand-primary,#006B3F);font-size:12px;margin-bottom:12px'>"
            "<b>Diligence score components:</b> "
            "Milestone on-time rate (30%) · Action plan acceptance (20%) · "
            "Leave compliance (15%) · Disciplinary clean (20%) · Not on PIP (15%)"
            "</div>", unsafe_allow_html=True)

        # Compute for all visible staff
        diligence_rows = []
        for _, staff_row in filtered.iterrows():
            sc = str(staff_row.get('Staff Code',''))
            name = staff_row.get('Staff Name','')
            score = hr_m.compute_diligence(sc, em, action_plans) if hr_m else 100.0
            bsc   = staff_row.get('Final_BSC_Score', 0)
            on_pip = hr_m.staff_on_pip(sc) if hr_m else False
            has_disc = hr_m.staff_has_active_case(sc) if hr_m else False
            on_leave = lm.is_on_leave(sc) if lm else False

            diligence_rows.append({
                'Staff Name':  name,
                'Unit':        staff_row.get('Unit',''),
                'BSC Score':   round(bsc, 2),
                'Diligence':   score,
                'On PIP':      '⚠️ Yes' if on_pip else '✅ No',
                'Disc. case':  '🔴 Active' if has_disc else '✅ Clear',
                'On leave':    '🏖️ Yes' if on_leave else '—',
            })

        if diligence_rows:
            dil_df = pd.DataFrame(diligence_rows).sort_values('Diligence')

            # Chart
            dil_df['Color'] = dil_df['Diligence'].apply(
                lambda x: '#E24B4A' if x < 50 else ('#F5A623' if x < 75 else 'var(--brand-primary,#006B3F)'))
            fig = go.Figure()
            fig.add_bar(x=dil_df['Staff Name'], y=dil_df['Diligence'],
                        marker_color=dil_df['Color'],
                        text=[f"{v:.0f}" for v in dil_df['Diligence']],
                        textposition='outside')
            fig.add_hline(y=75, line_dash='dash', line_color='#F5A623',
                           annotation_text='75 — target')
            fig.update_layout(height=350, xaxis_tickangle=-35, yaxis_range=[0,110],
                yaxis_title='Diligence score', title='Staff diligence scores',
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)

            # Table
            disp_cols = ['Staff Name','Unit','BSC Score','Diligence','On PIP','Disc. case','On leave']
            st.dataframe(dil_df[disp_cols].sort_values('Diligence'),
                         use_container_width=True, hide_index=True)

        # ════════════════════════════════════════════════════════════════
        # TAB 8 — TEAM INSIGHTS (existing, preserved)
        # ════════════════════════════════════════════════════════════════

with _payroll_expander:
    st.markdown("**Month-end payroll export — download BSC score + commission tier for payroll processing:**")
    try:
        import io as _io_pr, pandas as _pd_pr
        _scores_pr = json.loads((DATA/"feb_2026_staff_scores.json").read_text()) if (DATA/"feb_2026_staff_scores.json").exists() else {}
        _comm_pr   = json.loads((DATA/"commission_records.json").read_text()) if (DATA/"commission_records.json").exists() else []
        _comm_map  = {str(c.get("staff_code","")): c for c in _comm_pr}
        _payroll_rows = []
        for sc_v, s in _scores_pr.items():
            c = _comm_map.get(str(sc_v), {})
            _payroll_rows.append({
                "Staff Code":    sc_v,
                "Full Name":     s.get("name","")[:30],
                "Role":          s.get("role","")[:30],
                "Unit":          s.get("unit","")[:25],
                "BSC Score":     s.get("final_score",0),
                "Tier":          c.get("tier","—"),
                "Commission (KES)": c.get("total_commission",0),
                "Payment Status":   c.get("status","Pending"),
            })
        _df_pr = _pd_pr.DataFrame(_payroll_rows)
        st.dataframe(_df_pr.head(20), use_container_width=True, hide_index=True)
        st.caption(f"{len(_payroll_rows):,} staff in payroll export")
        _buf_pr = _io_pr.BytesIO()
        _df_pr.to_excel(_buf_pr, index=False, sheet_name="Payroll", engine="openpyxl")
        _buf_pr.seek(0)
        st.download_button("📥 Download Payroll File",
                            data=_buf_pr.getvalue(),
                            file_name=f"Payroll_BSC_{date.today().strftime('%Y%m')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="payroll_dl")
    except Exception as _e:
        st.error(f"Payroll export error: {str(_e)[:80]}")
