"""pages/3_pipeline.py — Pipeline module."""
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

st.markdown(
    "<div style='padding:14px 20px;background:#185FA5;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:16px;font-weight:500'>Pipeline & Revenue Intelligence</div>"
    "<div style='color:rgba(255,255,255,0.75);font-size:11px;margin-top:2px'>CRM deal board · Revenue intelligence · Activity tracking</div>"
    "</div>", unsafe_allow_html=True)


# Shared data
staff_scores  = st.session_state.get("staff_scores", pd.DataFrame())
df_proc       = st.session_state.get("df_processed", pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
all_months    = st.session_state.get("all_months", [])

if len(staff_scores) == 0:
    st.info("📊 Upload your BSC Excel file in the sidebar to view this module.")
    st.stop()

st.subheader("💼 Sales Pipeline & Activity Tracker")
st.caption("Track deals from first contact to closure. Built on banking industry CRM best practice.")

# Only business & branch staff see this — support roles see read-only summary
user_role_fn = get_role_function(ud.get('role',''), ud.get('department',''))
is_business  = user_role_fn in ('Business','Branch Management')
is_mgr       = str(ud.get('role','')).lower() in ('admin','director','manager','branch manager',
                                                    'department head','head of sme','head of retail',
                                                    'head of corporate','director retail',
                                                    'director commercial banking')

# ── Stage funnel metrics ─────────────────────────────────────────
all_deals = pm.get_deals()
my_code   = clean_code(ud.get('staff_code',''))

# Managers see their team; staff see their own
if is_mgr or ud.get('can_view_all'):
    view_deals = [d for d in all_deals if d['staff_name'] in filtered['Staff Name'].tolist()] if all_deals else []
    scope_label = "Team pipeline"
else:
    view_deals = pm.get_deals(staff_code=my_code)
    scope_label = "My pipeline"

active_deals = [d for d in view_deals if d['stage'] in ACTIVE_STAGES]
won_deals    = [d for d in view_deals if d['stage'] == 'Closed Won']
lost_deals   = [d for d in view_deals if d['stage'] == 'Closed Lost']

pip_val  = pm.pipeline_value(active_deals)
wt_val   = pm.weighted_pipeline(active_deals)
won_val  = sum(float(d.get('deal_value',0)) for d in won_deals)

fc1,fc2,fc3,fc4,fc5 = st.columns(5)
fc1.metric(f"{scope_label}",    len(active_deals), help="Active deals")
fc2.metric("Pipeline value",    fmt_num(pip_val, short=True), help="Total value of active deals")
fc3.metric("Weighted value",    fmt_num(wt_val, short=True),  help="Probability-weighted pipeline")
fc4.metric("Closed won",        len(won_deals))
fc5.metric("Won value",         fmt_num(won_val, short=True))

# ── Visual funnel ────────────────────────────────────────────────
if view_deals:
    stage_counts = {}
    stage_values = {}
    for st_info in PIPELINE_STAGES:
        sn = st_info['stage']
        sd = [d for d in view_deals if d['stage'] == sn]
        stage_counts[sn] = len(sd)
        stage_values[sn] = sum(float(d.get('deal_value',0)) for d in sd)

    funnel_data = pd.DataFrame([{
        'Stage': s['stage'],
        'Count': stage_counts.get(s['stage'],0),
        'Value': stage_values.get(s['stage'],0),
    } for s in PIPELINE_STAGES if s['stage'] not in ('Closed Lost',)])

    col_f, col_b = st.columns([1,1])
    with col_f:
        fig_funnel = px.funnel(funnel_data, x='Count', y='Stage',
                               title='Deal funnel (count)', color_discrete_sequence=['#2980B9'])
        fig_funnel.update_layout(height=360, margin=dict(l=10,r=10,t=40,b=10))
        st.plotly_chart(fig_funnel, use_container_width=True)
    with col_b:
        fig_bar = px.bar(funnel_data[funnel_data['Value']>0],
                         x='Value', y='Stage', orientation='h',
                         title='Pipeline value by stage (KES)',
                         color='Value', color_continuous_scale='Blues')
        fig_bar.update_traces(texttemplate='%{x:,.0f}', textposition='outside')
        fig_bar.update_layout(height=360, showlegend=False,
                              margin=dict(l=10,r=80,t=40,b=10))
        st.plotly_chart(fig_bar, use_container_width=True)

pl1, pl2, pl3 = st.tabs(["📋 Deal Board", "➕ New Deal / Activity", "📈 My Performance"])

# ── DEAL BOARD ────────────────────────────────────────────────────
with pl1:
    st.subheader("Deal board")

    # Stage filter
    stage_filter = st.multiselect("Filter by stage", STAGE_NAMES,
                                   default=ACTIVE_STAGES, key="pl_stage_filter")
    board_deals  = [d for d in view_deals if d['stage'] in stage_filter]

    if not board_deals:
        st.info("No deals in the selected stages. Add your first deal in 'New Deal / Activity'.")
    else:
        bd_df = pd.DataFrame(board_deals)
        # Format for display
        disp_cols = [c for c in ['id','staff_name','client_name','product_type','deal_value',
                                  'stage','next_action','next_action_date','created_at']
                     if c in bd_df.columns]
        bd_disp = bd_df[disp_cols].copy()
        if 'deal_value' in bd_disp.columns:
            bd_disp['deal_value'] = bd_disp['deal_value'].apply(lambda x: fmt_num(float(x) if x else 0))
        bd_disp.columns = [c.replace('_',' ').title() for c in bd_disp.columns]

        def hl_stage(v):
            colours = {
                'Lead':'#CCE5FF','Contacted':'#D4EDDA','Qualified':'#FFF3CD',
                'Proposal':'#FFE4B5','Negotiation':'#FFDAB9',
                'Compliance':'#E8D5FF','Closed Won':'#90EE90','Closed Lost':'#FFB6C1'
            }
            return f"background-color:{colours.get(v,'')}"

        st.dataframe(bd_disp.style.map(hl_stage, subset=['Stage'] if 'Stage' in bd_disp.columns else []),
                     use_container_width=True, hide_index=True)

        # Stage update
        st.markdown("#### Move a deal to next stage")
        deal_opts = {f"{d['id']} — {d.get('client_name','')} ({d['stage']})": d['id']
                     for d in board_deals}
        sel_deal_label = st.selectbox("Select deal", list(deal_opts.keys()), key="pl_sel_deal")
        if sel_deal_label:
            sel_deal_id = deal_opts[sel_deal_label]
            sel_deal    = next(d for d in board_deals if d['id'] == sel_deal_id)
            cur_stage_i = STAGE_NAMES.index(sel_deal['stage']) if sel_deal['stage'] in STAGE_NAMES else 0
            new_stage_opts = STAGE_NAMES[max(0, cur_stage_i-1):]

            nc1, nc2 = st.columns([1,2])
            with nc1:
                new_stage = st.selectbox("New stage", new_stage_opts, key="pl_new_stage")
                loss_reason = ""
                if new_stage == "Closed Lost":
                    loss_reason = st.selectbox("Loss reason", LOSS_REASONS, key="pl_loss_reason")
            with nc2:
                stage_note = st.text_area("Note / update", height=80, key="pl_stage_note")

            if st.button("✅ Update stage", type="primary", key="pl_update_btn"):
                note_full = stage_note
                if loss_reason: note_full = f"Loss reason: {loss_reason}. {stage_note}"
                pm.update_stage(sel_deal_id, new_stage, note_full, uname)
                audit_log("DEAL_UPDATE", uname, f"{sel_deal_id} → {new_stage}")
                st.success(f"Deal {sel_deal_id} moved to {new_stage}!")
                st.rerun()

# ── NEW DEAL / ACTIVITY ───────────────────────────────────────────
with pl2:
    entry_type = st.radio("What are you recording?",
                          ["New Deal", "Activity on existing deal"], horizontal=True, key="pl_entry_type")

    if entry_type == "New Deal":
        st.subheader("Add new deal")
        with st.form("new_deal_form"):
            dc1, dc2 = st.columns(2)
            with dc1:
                client_name  = st.text_input("Client name *")
                client_type  = st.selectbox("Client type", ["Individual","SME","Corporate","Institutional"])
                product_type = st.selectbox("Product / facility type", PRODUCT_TYPES)
                deal_value   = st.number_input("Deal value (KES)", min_value=0.0, step=100000.0, format="%.2f")
            with dc2:
                stage        = st.selectbox("Current stage", ACTIVE_STAGES)
                next_action  = st.text_input("Next action", placeholder="e.g. Follow-up call Monday")
                next_date    = st.date_input("Next action date")
                source       = st.selectbox("Lead source",
                    ["Referral","Walk-in","Cold call","Existing client","Digital","Branch campaign","Other"])
            notes = st.text_area("Notes / context", height=80)

            # If manager, can assign to team member
            if is_mgr:
                assign_opts = ["Myself"] + sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else []
                assignee    = st.selectbox("Assign to", assign_opts, key="pl_assignee")
            else:
                assignee = "Myself"

            if st.form_submit_button("✅ Add deal", type="primary"):
                if not client_name:
                    st.error("Client name required.")
                else:
                    # Resolve assignee staff code
                    if assignee == "Myself":
                        a_code = my_code
                        a_name = ud.get('full_name','')
                    else:
                        row_a = filtered[filtered['Staff Name'] == assignee]
                        a_code = clean_code(row_a['Staff Code'].values[0]) if len(row_a) else my_code
                        a_name = assignee

                    deal_id = pm.add_deal({
                        'client_name': client_name, 'client_type': client_type,
                        'product_type': product_type, 'deal_value': deal_value,
                        'stage': stage, 'next_action': next_action,
                        'next_action_date': str(next_date), 'lead_source': source,
                        'notes': notes, 'staff_code': a_code, 'staff_name': a_name,
                        'created_by': uname,
                    })
                    pm.add_activity({
                        'deal_id': deal_id, 'staff_code': a_code, 'staff_name': a_name,
                        'activity_type': 'Deal Created', 'note': notes, 'outcome': stage,
                    })
                    audit_log("DEAL_CREATED", uname, f"{deal_id} | {client_name} | {product_type} | KES {deal_value:,.0f}")
                    st.success(f"Deal {deal_id} added for {client_name}!")
                    st.rerun()

    else:  # Activity log
        st.subheader("Log an activity")
        my_active = pm.get_deals(
            staff_code=my_code if not is_mgr else None, active_only=True)
        my_active = [d for d in my_active if d['staff_name'] in filtered['Staff Name'].tolist()] if is_mgr else my_active

        if not my_active:
            st.info("No active deals to log activity against. Add a deal first.")
        else:
            deal_opts2 = {f"{d['id']} — {d.get('client_name','')} ({d['stage']})": d
                          for d in my_active}
            sel_lbl = st.selectbox("Select deal", list(deal_opts2.keys()), key="pl_act_deal")
            sel_d   = deal_opts2[sel_lbl]

            with st.form("activity_form"):
                ac1, ac2 = st.columns(2)
                with ac1:
                    act_type = st.selectbox("Activity type", ACTIVITY_TYPES)
                    act_date = st.date_input("Date", value=datetime.now().date())
                with ac2:
                    outcome  = st.selectbox("Outcome", ["Positive","Neutral","Objection","Needs follow-up","Escalate"])
                    next_act = st.text_input("Next action", placeholder="What happens next?")
                act_note = st.text_area("Notes", height=80)

                if st.form_submit_button("📋 Log activity", type="primary"):
                    pm.add_activity({
                        'deal_id':       sel_d['id'],
                        'staff_code':    sel_d['staff_code'],
                        'staff_name':    sel_d['staff_name'],
                        'activity_type': act_type,
                        'activity_date': str(act_date),
                        'outcome':       outcome,
                        'next_action':   next_act,
                        'note':          act_note,
                    })
                    # Update next action on deal
                    for d in pm.deals:
                        if d['id'] == sel_d['id']:
                            d['next_action']      = next_act
                            d['next_action_date'] = str(act_date + timedelta(days=3))
                            d['updated_at']       = datetime.now().isoformat()
                    pm._save_deals()
                    audit_log("ACTIVITY_LOGGED", uname, f"{sel_d['id']} | {act_type} | {outcome}")
                    st.success("Activity logged!")
                    st.rerun()

# ── MY PERFORMANCE ────────────────────────────────────────────────
with pl3:
    st.subheader("Pipeline performance")
    perf_code  = my_code if not is_mgr else None
    perf_deals = pm.get_deals(staff_code=perf_code) if perf_code else view_deals

    if not perf_deals:
        st.info("No deals recorded yet.")
    else:
        # Conversion metrics
        total   = len(perf_deals)
        won     = len([d for d in perf_deals if d['stage']=='Closed Won'])
        lost    = len([d for d in perf_deals if d['stage']=='Closed Lost'])
        active  = total - won - lost
        conv_r  = won / (won + lost) * 100 if (won+lost) > 0 else 0

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total deals",      total)
        m2.metric("Active",           active)
        m3.metric("Win rate",         f"{conv_r:.1f}%")
        m4.metric("Won value",        fmt_num(sum(float(d.get('deal_value',0)) for d in perf_deals if d['stage']=='Closed Won'), short=True))

        # Pipeline by product
        prod_df = pd.DataFrame(perf_deals)
        if 'product_type' in prod_df.columns:
            prod_grp = prod_df.groupby('product_type').agg(
                Deals=('id','count'),
                Value=('deal_value', lambda x: sum(float(v) for v in x))
            ).reset_index().sort_values('Value', ascending=False)
            fig_prod = px.bar(prod_grp, x='product_type', y='Value',
                              title='Pipeline by product type', color='Deals',
                              color_continuous_scale='Blues')
            fig_prod.update_layout(height=300, showlegend=False)
            st.plotly_chart(fig_prod, use_container_width=True)

        # Recent activities
        st.markdown("#### Recent activity log")
        acts = pm.get_activities(staff_code=perf_code if perf_code else None, limit=20)
        if acts:
            act_df = pd.DataFrame(acts)
            show_act = [c for c in ['staff_name','deal_id','activity_type','outcome','note','recorded_at']
                        if c in act_df.columns]
            st.dataframe(act_df[show_act], use_container_width=True, hide_index=True)

# ── TAB 9: REVENUE INTELLIGENCE ──────────────────────────────────────────
# with tabs[8]:
st.subheader("Revenue intelligence")
st.caption("Performance vs pipeline vs forecast — Deposits · Loans · NFI · New Customers")

# ── Scope: who are we looking at? ────────────────────────────────
role_lower = str(ud.get('role','')).lower()
is_mgr_ri  = (ud.get('can_view_all') or
              role_lower in ('admin','director','manager','branch manager',
                             'department head','head of sme','head of retail',
                             'head of corporate','director retail','director commercial banking'))

team_names = filtered['Staff Name'].tolist()
my_code    = clean_code(ud.get('staff_code',''))

if is_mgr_ri:
    scope_deals = ri_pm.get_deals(team_names=team_names)
    scope_label = f"Team view — {len(team_names)} staff"
else:
    scope_deals = ri_pm.get_deals(staff_code=my_code)
    scope_label = f"My view — {ud.get('full_name','')}"

# ── Compute KPI actuals and targets from BSC data ─────────────
scope_kpis = df_proc[df_proc['Staff Name'].isin(
    team_names if is_mgr_ri else [ud.get('full_name','')])]

kpi_actuals = {}
kpi_targets = {}
for cat, cfg in RI_CATEGORIES.items():
    cat_rows = scope_kpis[scope_kpis['KPI'].isin(cfg['kpis'])]
    # Sum actuals; for customers use count (target is numbers not KES)
    kpi_actuals[cat] = float(cat_rows['YTD_Actual'].sum()) if len(cat_rows) else 0
    kpi_targets[cat] = float(cat_rows['Annual Target'].sum()) if len(cat_rows) else 0

summary = ri_pm.category_summary(scope_deals, kpi_actuals, kpi_targets)

st.caption(f"Scope: {scope_label}  |  {datetime.now().strftime('%B %Y')}")

# ════════════════════════════════════════════════════════════════
# SECTION 1 — THE FOUR CATEGORY CARDS (single view)
# ════════════════════════════════════════════════════════════════
st.markdown("### Performance vs pipeline snapshot")

cols = st.columns(4)
cat_order = ['Deposits','Loans','NFI','Customers']

for ci, cat in enumerate(cat_order):
    s   = summary[cat]
    cfg = RI_CATEGORIES[cat]
    clr = cfg['color']
    bg  = cfg['bg']

    tgt  = s['annual_target']
    act  = s['ytd_actual']
    pip  = s['pipeline_wtd']
    fore = s['forecast_eoy']
    gap  = s['gap_to_target']
    cov  = s['coverage_pct']
    unit = s['unit']

    ach_pct  = (act / tgt * 100) if tgt > 0 else 0
    fore_pct = (fore / tgt * 100) if tgt > 0 else 0

    # Traffic light
    if ach_pct >= 90:   light = "🟢"
    elif ach_pct >= 60: light = "🟡"
    else:               light = "🔴"

    with cols[ci]:
        st.markdown(
            f"<div style='padding:14px;background:{bg};border-left:4px solid {clr};"
            f"border-radius:8px;margin-bottom:4px'>"
            f"<div style='font-size:11px;color:{clr};font-weight:500;text-transform:uppercase;"
            f"letter-spacing:.5px'>{cfg['label']}</div>"
            f"<div style='font-size:20px;font-weight:500;margin:4px 0;color:var(--color-text-primary)'>"
            f"{light} {fmt_num(act, short=True)}</div>"
            f"<div style='font-size:11px;color:var(--color-text-secondary)'>"
            f"Target: {fmt_num(tgt, short=True)} {unit}</div>"
            f"<div style='margin:8px 0 4px;background:var(--color-background-primary);"
            f"border-radius:4px;height:6px;overflow:hidden'>"
            f"<div style='width:{min(100,ach_pct):.0f}%;height:100%;background:{clr};border-radius:4px'></div>"
            f"</div>"
            f"<div style='font-size:11px;color:var(--color-text-secondary)'>{ach_pct:.1f}% achieved</div>"
            f"</div>",
            unsafe_allow_html=True)

        # Pipeline overlay
        st.markdown(
            f"<div style='padding:10px 14px;border:0.5px solid {clr}33;"
            f"border-radius:6px;font-size:12px;margin-bottom:4px'>"
            f"<b>Pipeline (wtd):</b> {fmt_num(pip, short=True)}<br>"
            f"<b>Gap to target:</b> {fmt_num(gap, short=True)}<br>"
            f"<b>Coverage:</b> {fmt_pct(cov)}<br>"
            f"<b>Forecast EOY:</b> {fmt_num(fore, short=True)} "
            f"({fore_pct:.0f}% of target)</div>",
            unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SECTION 2 — FORECAST & RECOMMENDATION
# ════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Year-end forecast & recommended actions")

for cat in cat_order:
    s   = summary[cat]
    cfg = RI_CATEGORIES[cat]
    clr = cfg['color']
    bg  = cfg['bg']
    tgt = s['annual_target']
    act = s['ytd_actual']
    pip = s['pipeline_wtd']
    pip_raw = s['pipeline_raw']
    fore = s['forecast_eoy']
    gap  = s['gap_to_target']
    cov  = s['coverage_pct']
    conv = s['conv_needed']
    curr_c = s['curr_conv']
    m_rem = months_remaining()
    m_ela = months_elapsed()
    unit  = s['unit']

    if tgt == 0:
        continue

    # Build narrative recommendation
    ach_pct  = (act / tgt * 100) if tgt else 0
    fore_pct = (fore / tgt * 100) if tgt else 0

    if fore_pct >= 100:
        verdict = "On track to achieve"
        v_color = "#0F6E56"
    elif fore_pct >= 85:
        verdict = "At risk — intervention needed"
        v_color = "#BA7517"
    else:
        verdict = "Significant shortfall — urgent action"
        v_color = "#A32D2D"

    # Monthly run rate needed
    monthly_needed = gap / m_rem if m_rem > 0 and gap > 0 else 0
    monthly_actual = act / m_ela if m_ela > 0 else 0
    rate_uplift    = ((monthly_needed / monthly_actual) - 1) * 100 if monthly_actual > 0 else None

    rec_parts = []
    if gap > 0:
        rec_parts.append(f"Need {fmt_num(gap, short=True)} more in {m_rem} months "
                         f"({fmt_num(monthly_needed, short=True)}/month vs current "
                         f"{fmt_num(monthly_actual, short=True)}/month)")
    if conv is not None and pip_raw > 0:
        if conv <= 100:
            rec_parts.append(f"Convert {conv:.0f}% of active pipeline to close gap")
        else:
            shortfall = gap - pip_raw
            rec_parts.append(f"Pipeline insufficient — need {fmt_num(shortfall, short=True)} more in pipeline")
    if curr_c is not None:
        rec_parts.append(f"Current win rate: {curr_c:.0f}%")
    if rate_uplift is not None and rate_uplift > 0:
        rec_parts.append(f"Increase monthly run rate by {rate_uplift:.0f}%")

    recs_html = "".join(f"<li style='margin:2px 0'>{r}</li>" for r in rec_parts) if rec_parts else ""

    st.markdown(
        f"<div style='padding:12px 16px;border-left:4px solid {clr};"
        f"border-radius:0 6px 6px 0;margin:6px 0;background:var(--color-background-secondary)'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<span style='font-weight:500;color:var(--color-text-primary)'>{cfg['label']}</span>"
        f"<span style='font-size:12px;font-weight:500;color:{v_color}'>{verdict}</span></div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary);margin-top:4px'>"
        f"Forecast: <b>{fmt_num(fore, short=True)}</b> ({fore_pct:.0f}% of target) | "
        f"Active pipeline: <b>{s['active_deals']} deals</b> | "
        f"Won YTD: <b>{fmt_num(s['won_ytd'], short=True)}</b></div>"
        f"{'<ul style="font-size:12px;color:var(--color-text-secondary);margin:6px 0 0 16px;padding:0">' + recs_html + '</ul>' if recs_html else ''}"
        f"</div>",
        unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# SECTION 3 — DEAL BOARD (sub-tabs per category)
# ════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Pipeline deal board")

cat_tabs = st.tabs([f"{cfg['label']}" for cat,cfg in RI_CATEGORIES.items()])

for ci, (cat, cfg) in enumerate(RI_CATEGORIES.items()):
    with cat_tabs[ci]:
        clr    = cfg['color']
        stages = cfg['stages'] + [cfg['closed_won'], cfg['closed_lost']]
        cat_deals = ri_pm.get_deals(
            team_names=team_names if is_mgr_ri else None,
            staff_code=my_code if not is_mgr_ri else None,
            category=cat)

        # Add new deal
        with st.expander("+ Add new deal", expanded=False):
            with st.form(f"ri_new_{cat}"):
                fc1, fc2 = st.columns(2)
                with fc1:
                    r_client   = st.text_input("Client / prospect name", key=f"rc_{cat}")
                    r_product  = st.selectbox("Product type",
                        cfg['pipeline_product_types'], key=f"rp_{cat}")
                    r_value    = st.number_input(
                        f"Deal value ({cfg['unit']})",
                        min_value=0.0, step=100000.0 if cfg['unit']=='KES' else 1.0,
                        format="%.0f", key=f"rv_{cat}")
                with fc2:
                    r_stage    = st.selectbox("Current stage",
                        cfg['stages'], key=f"rs_{cat}")
                    r_next     = st.text_input("Next action", key=f"rn_{cat}")
                    r_date     = st.date_input("Next action date", key=f"rd_{cat}")

                if is_mgr_ri:
                    assign_opts = ["Myself"] + sorted(filtered["Staff Name"].tolist()) if len(filtered) > 0 and "Staff Name" in filtered.columns else [] if len(filtered) > 0 and "Staff Name" in filtered.columns else []
                    r_assign = st.selectbox("Assign to", assign_opts, key=f"ra_{cat}")
                else:
                    r_assign = "Myself"

                r_notes = st.text_area("Notes", height=60, key=f"rno_{cat}")

                if st.form_submit_button(f"Add {cfg['label']} deal", type="primary"):
                    if r_client:
                        if r_assign == "Myself":
                            a_code = my_code
                            a_name = ud.get('full_name','')
                        else:
                            row_a = filtered[filtered['Staff Name'] == r_assign]
                            a_code = clean_code(row_a['Staff Code'].values[0]) if len(row_a) else my_code
                            a_name = r_assign

                        ri_pm.add_deal({
                            'category': cat, 'client_name': r_client,
                            'product_type': r_product, 'deal_value': r_value,
                            'stage': r_stage, 'next_action': r_next,
                            'next_action_date': str(r_date), 'notes': r_notes,
                            'staff_code': a_code, 'staff_name': a_name,
                            'created_by': uname,
                        })
                        audit_log("RI_DEAL", uname, f"{cat}|{r_client}|{r_product}|{r_value}")
                        st.success(f"Deal added: {r_client}")
                        st.rerun()
                    else:
                        st.error("Client name required.")

        if not cat_deals:
            st.info(f"No {cfg['label']} deals yet. Add your first deal above.")
        else:
            # Stage summary bar
            stage_counts = {s: 0 for s in stages}
            stage_values = {s: 0.0 for s in stages}
            for d in cat_deals:
                s = d.get('stage','')
                if s in stage_counts:
                    stage_counts[s] += 1
                    stage_values[s] += float(d.get('deal_value',0))

            # Funnel pills
            pill_html = "<div style='display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px'>"
            for s in cfg['stages']:
                cnt = stage_counts.get(s,0)
                val = stage_values.get(s,0)
                wt  = cfg['stage_weights'].get(s,0)
                pill_html += (
                    f"<div style='padding:6px 10px;background:{cfg['bg']};"
                    f"border:1px solid {clr}44;border-radius:6px;font-size:11px'>"
                    f"<b style='color:{clr}'>{s}</b> ({wt*100:.0f}%)<br>"
                    f"{cnt} deals · {fmt_num(val, short=True)}</div>")
            pill_html += "</div>"
            st.markdown(pill_html, unsafe_allow_html=True)

            # Deal table
            bd_df = pd.DataFrame(cat_deals)
            show_c = [c for c in ['id','staff_name','client_name','product_type',
                                   'deal_value','stage','next_action','next_action_date']
                      if c in bd_df.columns]
            bd_disp = bd_df[show_c].copy()
            if 'deal_value' in bd_disp.columns:
                bd_disp['deal_value'] = bd_disp['deal_value'].apply(
                    lambda x: fmt_num(float(x) if x else 0))
            bd_disp.columns = [c.replace('_',' ').title() for c in bd_disp.columns]

            def hl_stage_ri(v):
                if v in (cfg['closed_won'],):  return 'background-color:#D4EDDA'
                if v in (cfg['closed_lost'],):  return 'background-color:#FFB6C1'
                if v in cfg['stages'][-2:]:     return 'background-color:#FFF3CD'
                return ''

            st.dataframe(
                bd_disp.style.map(hl_stage_ri, subset=['Stage'] if 'Stage' in bd_disp.columns else []),
                use_container_width=True, hide_index=True)

            # Stage mover
            st.markdown("**Move deal to next stage**")
            mc1, mc2, mc3 = st.columns([2,1,2])
            with mc1:
                move_opts = {f"{d['id']} — {d.get('client_name','')} ({d.get('stage','')})": d['id']
                             for d in cat_deals}
                sel_lbl = st.selectbox("Deal", list(move_opts.keys()), key=f"mv_{cat}")
            with mc2:
                sel_id  = move_opts.get(sel_lbl,'')
                sel_d   = next((d for d in cat_deals if d['id']==sel_id), {})
                cur_i   = cfg['stages'].index(sel_d.get('stage','')) if sel_d.get('stage','') in cfg['stages'] else 0
                new_stage_opts = cfg['stages'][cur_i:] + [cfg['closed_won'], cfg['closed_lost']]
                new_st = st.selectbox("New stage", new_stage_opts, key=f"ns_{cat}")
            with mc3:
                mv_note = st.text_input("Note", key=f"mn_{cat}")

            if st.button(f"Move", key=f"mb_{cat}", type="primary"):
                ri_pm.update_stage(sel_id, new_st, mv_note, uname)
                audit_log("RI_STAGE", uname, f"{sel_id}→{new_st}")
                st.success(f"Moved to {new_st}!")
                st.rerun()

# ════════════════════════════════════════════════════════════════
# SECTION 4 — PERFORMANCE vs PIPELINE CHARTS
# ════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("### Visual analysis")

v1, v2 = st.columns(2)

with v1:
    # Bar: actual vs target vs forecast per category
    chart_data = []
    for cat in cat_order:
        s = summary[cat]
        if s['annual_target'] > 0:
            chart_data.append({'Category': RI_CATEGORIES[cat]['label'],
                               'Type': 'YTD Actual',   'Value': s['ytd_actual']})
            chart_data.append({'Category': RI_CATEGORIES[cat]['label'],
                               'Type': 'Annual Target', 'Value': s['annual_target']})
            chart_data.append({'Category': RI_CATEGORIES[cat]['label'],
                               'Type': 'EOY Forecast',  'Value': s['forecast_eoy']})

    if chart_data:
        cd_df = pd.DataFrame(chart_data)
        fig_bar = px.bar(cd_df, x='Category', y='Value', color='Type', barmode='group',
                         title='Actual vs target vs forecast',
                         color_discrete_map={'YTD Actual':'#1D9E75',
                                              'Annual Target':'#BDC3C7',
                                              'EOY Forecast':'#378ADD'})
        fig_bar.update_layout(height=340, legend_title='',
                               yaxis_tickformat=',.0f')
        st.plotly_chart(fig_bar, use_container_width=True)

with v2:
    # Waterfall: gap analysis — what's done, what's in pipeline, what's missing
    wf_data = []
    for cat in cat_order:
        s = summary[cat]
        if s['annual_target'] > 0:
            done_pct  = (s['ytd_actual'] / s['annual_target'] * 100)
            pip_pct   = min(100 - done_pct, s['pipeline_wtd'] / s['annual_target'] * 100)
            miss_pct  = max(0, 100 - done_pct - pip_pct)
            wf_data.append({'Category': RI_CATEGORIES[cat]['label'],
                            'Achieved': done_pct,
                            'In pipeline (wtd)': pip_pct,
                            'Still needed': miss_pct})

    if wf_data:
        wf_df = pd.DataFrame(wf_data)
        fig_wf = px.bar(wf_df, x='Category',
                        y=['Achieved','In pipeline (wtd)','Still needed'],
                        title='Gap coverage (% of annual target)',
                        color_discrete_map={'Achieved':'#1D9E75',
                                             'In pipeline (wtd)':'#378ADD',
                                             'Still needed':'#E24B4A'},
                        barmode='stack')
        fig_wf.update_layout(height=340, legend_title='',
                               yaxis_title='% of target', yaxis_range=[0,110])
        st.plotly_chart(fig_wf, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# SECTION 5 — TEAM LEADERBOARD (managers only)
# ════════════════════════════════════════════════════════════════
if is_mgr_ri and len(team_names) > 1:
    st.markdown("---")
    st.markdown("### Team revenue leaderboard")
    st.caption("Each staff member's contribution across all four revenue categories.")

    leaderboard = []
    for name in team_names:
        staff_row = filtered[filtered['Staff Name'] == name]
        if len(staff_row) == 0: continue
        scode = clean_code(staff_row['Staff Code'].values[0])

        staff_kpi_rows = df_proc[df_proc['Staff Name'] == name]
        staff_deals    = ri_pm.get_deals(staff_code=scode)

        row = {'Staff': name, 'Role': staff_row['Role'].values[0]}
        total_act = 0
        total_tgt = 0

        for cat, cfg in RI_CATEGORIES.items():
            cat_rows = staff_kpi_rows[staff_kpi_rows['KPI'].isin(cfg['kpis'])]
            act = float(cat_rows['YTD_Actual'].sum()) if len(cat_rows) else 0
            tgt = float(cat_rows['Annual Target'].sum()) if len(cat_rows) else 0
            pip = ri_pm.weighted_value(ri_pm.get_deals(staff_code=scode, category=cat))
            row[f'{cfg["label"]} %'] = fmt_pct((act/tgt*100) if tgt else 0)
            row[f'{cfg["label"]} pipeline'] = fmt_num(pip, short=True)
            total_act += act
            total_tgt += tgt

        row['Overall %'] = fmt_pct((total_act/total_tgt*100) if total_tgt else 0)
        row['_sort'] = (total_act/total_tgt) if total_tgt else 0
        leaderboard.append(row)

    lb_df = pd.DataFrame(leaderboard).sort_values('_sort', ascending=False).drop(columns=['_sort'])
    st.dataframe(lb_df, use_container_width=True, hide_index=True)


# ── TAB 10: EXECUTE ───────────────────────────────────────────────────────
