"""pages/4_execute.py — Execute module."""
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

st.subheader("Execute — strategy execution tracker")
st.caption("Initiatives flow from idea (G0) through business case, milestone plan, implementation to impact (G5).")

# ── My action items (top of page — always visible) ────────────
my_actions = em.get_my_actions(uname, ud.get('role',''))
if my_actions:
    st.error(f"You have {len(my_actions)} item(s) requiring your action")
    for act in my_actions:
        if act['type'] == 'gate_approval':
            col1, col2 = st.columns([3,1])
            col1.markdown(f"**Gate approval needed:** {act['name']} → {act['gate']}")
            with col2:
                if st.button(f"Review", key=f"act_{act['init_id']}_{act['gate']}"):
                    st.session_state['execute_focus'] = act['init_id']
        elif act['type'] == 'milestone_confirm':
            col1, col2 = st.columns([3,1])
            col1.markdown(f"**Milestone confirmation:** {act['name']} — {act['ms_name']}")
            with col2:
                if st.button(f"Confirm", key=f"ms_{act['init_id']}_{act['ms_id']}"):
                    em.confirm_milestone(act['init_id'], act['ms_id'], uname)
                    audit_log("MS_CONFIRMED", uname, f"{act['init_id']}:{act['ms_id']}")
                    st.success("Milestone confirmed!")
                    st.rerun()
    st.markdown("---")

# ── Role check ────────────────────────────────────────────────
role_lower = str(ud.get('role','')).lower()
is_exec_admin = ud.get('can_view_all') or role_lower in ('admin',)
is_sponsor    = any(k in role_lower for k in ('director','sponsor'))
is_lead       = any(k in role_lower for k in ('head of','head of ','branch manager','department head','manager'))
is_finance    = 'finance' in role_lower
can_create    = True   # any active user can create an initiative or idea

# ── EXECUTE SUB-TABS ──────────────────────────────────────────
ex_tabs = st.tabs(["📊 Dashboard", "📋 Initiatives", "➕ Create", "💡 Ideation",
                    "⚙️ Workstreams", "📈 Impact tracking",
                    "🎯 My milestones", "🚨 Escalation tracker"])

# ════════════════════════════════════════════════════════════════
# EX-TAB 1: DASHBOARD
# ════════════════════════════════════════════════════════════════
with ex_tabs[0]:
    st.subheader("Execution dashboard")
    gate_counts = em.gate_counts()
    total = sum(gate_counts.values())

    # Gate funnel metrics
    cols = st.columns(len(GATE_ORDER))
    for ci, gate in enumerate(GATE_ORDER):
        cfg = EXECUTE_GATES[gate]
        cnt = gate_counts.get(gate, 0)
        pct = (cnt / total * 100) if total else 0
        cols[ci].markdown(
            f"<div style='padding:12px;background:{cfg['bg']};border-left:3px solid {cfg['color']};"
            f"border-radius:6px;text-align:center'>"
            f"<div style='font-size:11px;color:{cfg['color']};font-weight:500'>{gate}</div>"
            f"<div style='font-size:24px;font-weight:500;color:var(--color-text-primary)'>{cnt}</div>"
            f"<div style='font-size:11px;color:var(--color-text-secondary)'>{cfg['label']}</div>"
            f"</div>", unsafe_allow_html=True)

    if total == 0:
        st.info("No initiatives yet. Create your first initiative in the 'Create' tab.")
    else:
        all_inits = em.get_initiatives(status='All')

        # Funnel chart
        fc1, fc2 = st.columns(2)
        with fc1:
            funnel_df = pd.DataFrame([
                {'Gate': g, 'Count': gate_counts.get(g,0),
                 'Label': EXECUTE_GATES[g]['label']}
                for g in GATE_ORDER])
            fig_f = px.funnel(funnel_df, x='Count', y='Label',
                              title='Initiative gate funnel',
                              color_discrete_sequence=['#534AB7'])
            fig_f.update_layout(height=320)
            st.plotly_chart(fig_f, use_container_width=True)

        with fc2:
            cat_df = pd.DataFrame(all_inits)
            if 'category' in cat_df.columns:
                cat_counts = cat_df['category'].value_counts().reset_index()
                cat_counts.columns = ['Category','Count']
                fig_c = px.pie(cat_counts, names='Category', values='Count',
                               title='Initiatives by category')
                fig_c.update_layout(height=320)
                st.plotly_chart(fig_c, use_container_width=True)

        # On-hold / at-risk
        delayed = [i for i in all_inits
                   if i['gate'] in ('G3',) and
                   any(ms['status'] == 'Delayed' for ms in i.get('milestones',[]))]
        if delayed:
            st.warning(f"{len(delayed)} initiative(s) have delayed milestones")
            for i in delayed:
                st.markdown(f"- **{i['id']}** {i['name']} — {i['workstream']}")

        # Pending approvals
        pending = [i for i in all_inits if 'pending_gate' in i]
        if pending:
            st.info(f"{len(pending)} initiative(s) awaiting gate approval")
            for i in pending:
                pg = i['pending_gate']
                approvers_done = sum(1 for v in pg['approvals'].values() if v['status']=='Approved')
                approvers_total = len(pg['approvals'])
                st.markdown(f"- **{i['id']}** {i['name']} → {pg['target']} "
                            f"({approvers_done}/{approvers_total} approvals)")

# ════════════════════════════════════════════════════════════════
# EX-TAB 2: INITIATIVES LIST
# ════════════════════════════════════════════════════════════════
with ex_tabs[1]:
    st.subheader("All initiatives")

    # Filters
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        ws_opts = ['All'] + sorted(set(i.get('workstream','') for i in em.initiatives if i.get('workstream')))
        sel_ws = st.selectbox("Workstream", ws_opts, key="ex_ws_filter")
    with fc2:
        gate_opts = ['All'] + GATE_ORDER + ['On Hold','Dropped']
        sel_gate = st.selectbox("Gate", gate_opts, key="ex_gate_filter")
    with fc3:
        cat_opts = ['All'] + INITIATIVE_CATEGORIES
        sel_cat = st.selectbox("Category", cat_opts, key="ex_cat_filter")
    with fc4:
        search_ex = st.text_input("Search", placeholder="Name or IO...", key="ex_search")

    all_inits = em.get_initiatives(status='All')
    view_inits = all_inits
    if sel_ws   != 'All': view_inits = [i for i in view_inits if i.get('workstream')==sel_ws]
    if sel_gate != 'All': view_inits = [i for i in view_inits if i.get('gate')==sel_gate]
    if sel_cat  != 'All': view_inits = [i for i in view_inits if i.get('category')==sel_cat]
    if search_ex.strip():
        s = search_ex.lower()
        view_inits = [i for i in view_inits
                      if s in i.get('name','').lower() or s in i.get('io','').lower()]

    if not view_inits:
        st.info("No initiatives match the filters.")
    else:
        for init in view_inits:
            gate = init.get('gate','G0')
            cfg  = EXECUTE_GATES.get(gate, EXECUTE_GATES['G0'])
            ms_total    = len(init.get('milestones',[]))
            ms_complete = sum(1 for ms in init.get('milestones',[]) if ms['status']=='Complete')
            ms_pct      = (ms_complete/ms_total*100) if ms_total else 0
            pending_g   = init.get('pending_gate',{}).get('target','')

            with st.expander(
                f"{gate} | {init['name']}  —  {init.get('workstream','')}  |  IO: {init.get('io','')}",
                expanded=(init['id'] == st.session_state.get('execute_focus',''))):

                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(
                    f"<span style='background:{cfg['bg']};color:{cfg['color']};"
                    f"padding:3px 10px;border-radius:4px;font-size:12px;font-weight:500'>"
                    f"{gate} — {cfg['label']}</span>", unsafe_allow_html=True)
                c2.markdown(f"**Category:** {init.get('category','')}")
                c3.markdown(f"**Backup IO:** {init.get('io_backup','—')}")
                c4.markdown(f"**Created:** {init.get('created_at','')[:10]}")

                st.markdown(f"**Objective:** {init.get('objective','')}")

                if ms_total:
                    st.progress(ms_pct/100, text=f"Milestones: {ms_complete}/{ms_total} complete")

                if pending_g:
                    st.warning(f"Awaiting approval to move to {pending_g}")
                    # Show approval status
                    pg = init['pending_gate']
                    for role, appr in pg.get('approvals',{}).items():
                        icon = "✅" if appr['status']=='Approved' else ("❌" if appr['status']=='Rejected' else "⏳")
                        st.caption(f"  {icon} {role}: {appr['status']}")

                    # Approve/reject button if applicable
                    my_role_key = None
                    if is_sponsor:       my_role_key = 'sponsor'
                    elif is_lead:        my_role_key = 'workstream_lead'
                    elif is_finance:     my_role_key = 'finance'

                    if my_role_key and my_role_key in pg.get('approvals',{}):
                        if pg['approvals'][my_role_key]['status'] == 'Pending':
                            ap1, ap2, ap3 = st.columns([1,1,2])
                            appr_note = ap3.text_input("Note (optional)", key=f"apn_{init['id']}")
                            if ap1.button("✅ Approve", key=f"appr_{init['id']}"):
                                ok, msg = em.approve_gate(init['id'], my_role_key, uname, True, appr_note)
                                audit_log("GATE_APPROVED", uname, f"{init['id']}:{pending_g}")
                                st.success(msg); st.rerun()
                            if ap2.button("❌ Reject", key=f"rejt_{init['id']}"):
                                ok, msg = em.approve_gate(init['id'], my_role_key, uname, False, appr_note)
                                audit_log("GATE_REJECTED", uname, f"{init['id']}:{pending_g}")
                                st.error(msg); st.rerun()

                # Gate submission button
                gate_idx = GATE_ORDER.index(gate) if gate in GATE_ORDER else -1
                if gate_idx >= 0 and gate_idx < len(GATE_ORDER)-1 and 'pending_gate' not in init:
                    next_gate = GATE_ORDER[gate_idx+1]
                    transition = f"{gate}→{next_gate}"

                    # Special checks
                    can_submit = True
                    block_reason = ""
                    if gate == 'G2' and not em.all_milestones_confirmed(init['id']):
                        can_submit = False
                        block_reason = "All milestone owners must confirm before submitting to G3."
                    if gate == 'G3' and not em.money_step_complete(init['id']):
                        can_submit = False
                        block_reason = "Money Step milestone must be complete before submitting to G4."

                    if init.get('io') == uname or init.get('io_backup') == uname or is_exec_admin:
                        if can_submit:
                            sb1, sb2 = st.columns([2,3])
                            sub_note = sb2.text_input("Submission note", key=f"sn_{init['id']}")
                            if sb1.button(f"Submit to {next_gate}", key=f"sub_{init['id']}",
                                          type="primary"):
                                ok, msg = em.submit_for_gate(init['id'], next_gate, uname, sub_note)
                                audit_log("GATE_SUBMITTED", uname, f"{init['id']}→{next_gate}")
                                st.success(msg); st.rerun()
                        else:
                            st.warning(block_reason)

                # Milestone management (G2+)
                if gate in ('G2','G3','G4') or (gate == 'G1' and init.get('business_case')):
                    with st.expander("Milestones", expanded=(gate=='G3')):
                        if not init.get('milestones'):
                            if init.get('io') == uname or is_exec_admin:
                                st.info("No milestones yet. Add the first milestone below.")
                                with st.form(f"ms_form_{init['id']}"):
                                    m1, m2, m3 = st.columns(3)
                                    ms_name  = m1.text_input("Milestone name")
                                    ms_type  = m2.selectbox("Type", MILESTONE_TYPES)
                                    ms_owner = m3.text_input("Owner (username)")
                                    ms_due   = st.date_input("Due date")
                                    ms_desc  = st.text_area("Description", height=60)
                                    if st.form_submit_button("Add milestone"):
                                        em.add_milestone(init['id'], {
                                            'name': ms_name, 'type': ms_type,
                                            'owner': ms_owner, 'due_date': str(ms_due),
                                            'description': ms_desc,
                                        })
                                        st.success("Milestone added!"); st.rerun()
                        else:
                            for ms in init['milestones']:
                                ms_type_color = {'Implementation':'#185FA5',
                                                 'Health Check':'#0F6E56',
                                                 'Money Step':'#993C1D'}.get(ms['type'],'#888780')
                                conf_icon = "✅" if ms['confirmed'] else "⏳"
                                esc_level = ExecuteManager._escalation_level(ms)
                                esc_cfg   = ESC_CONFIG.get(esc_level, ESC_CONFIG[0])
                                try:
                                    days_diff = (date.fromisoformat(ms['due_date']) - date.today()).days
                                except: days_diff = 0
                                open_blockers = [b for b in ms.get('blockers',[]) if not b['resolved']]

                                # Milestone row
                                st.markdown(
                                    f"<div style='padding:10px 14px;border-left:4px solid {ms_type_color};"
                                    f"margin:4px 0;border-radius:0 6px 6px 0;"
                                    f"background:var(--color-background-secondary)'>"
                                    f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                                    f"<span><b>{ms['name']}</b> "
                                    f"<span style='font-size:11px;color:{ms_type_color}'>[{ms['type']}]</span></span>"
                                    f"<span>{escalation_badge(esc_level)}</span></div>"
                                    f"<div style='font-size:12px;color:var(--color-text-secondary);margin-top:4px'>"
                                    f"Owner: <b>{ms['owner']}</b>"
                                    f"{' | Co: ' + ', '.join(ms.get('co_owners',[])) if ms.get('co_owners') else ''}"
                                    f" | Due: <b>{ms['due_date']}</b> {days_label(days_diff)}"
                                    f" | Status: <b>{ms['status']}</b> {conf_icon}"
                                    f"{'<br><span style="color:#A32D2D">⚠ Delay reason: ' + ms['delay_reason'] + '</span>' if ms.get('delay_reason') else ''}"
                                    f"{'<br><span style="color:#A32D2D">🚧 ' + str(len(open_blockers)) + ' open blocker(s)</span>' if open_blockers else ''}"
                                    f"</div></div>",
                                    unsafe_allow_html=True)

                                # Status + delay reason update (G3 owners and IO)
                                can_update_ms = (ms['owner'] == uname or
                                                 uname in ms.get('co_owners',[]) or
                                                 init.get('io') == uname or is_exec_admin)
                                if gate == 'G3' and can_update_ms:
                                    with st.expander(f"Update — {ms['name']}", expanded=(esc_level>=2)):
                                        su1, su2, su3 = st.columns(3)
                                        status_opts = ['Not Started','In Progress','Complete','Delayed']
                                        new_ms_st = su1.selectbox("Status",
                                            status_opts,
                                            index=status_opts.index(ms['status']) if ms['status'] in status_opts else 0,
                                            key=f"mss_{init['id']}_{ms['id']}")
                                        ms_note = su2.text_input("Progress note",
                                            key=f"msn_{init['id']}_{ms['id']}")
                                        # Started flag
                                        has_started = ms.get('has_started', False)
                                        started_toggle = su3.checkbox(
                                            "Milestone has started",
                                            value=has_started,
                                            key=f"mst_{init['id']}_{ms['id']}",
                                            help="Tick when work has physically begun")

                                        delay_r = ""
                                        delay_cat = ""
                                        if new_ms_st == 'Delayed':
                                            dc1, dc2 = st.columns(2)
                                            delay_cat = dc1.selectbox(
                                                "Delay category *",
                                                DELAY_CATEGORIES,
                                                index=DELAY_CATEGORIES.index(ms.get('delay_category', DELAY_CATEGORIES[-1]))
                                                    if ms.get('delay_category') in DELAY_CATEGORIES else len(DELAY_CATEGORIES)-1,
                                                key=f"msc_{init['id']}_{ms['id']}",
                                                help="Structural/Regulatory = immediate Sponsor alert")
                                            delay_r = dc2.text_input(
                                                "Delay detail *",
                                                value=ms.get('delay_reason',''),
                                                key=f"msd_{init['id']}_{ms['id']}")
                                            if delay_cat in STRUCTURAL_CATEGORIES:
                                                st.error(f"⚠️ '{delay_cat}' delay — Sponsor will be notified immediately")

                                        if st.button("Save update", key=f"msb_{init['id']}_{ms['id']}",
                                                      type="primary"):
                                            em.update_milestone_status(
                                                init['id'], ms['id'], new_ms_st,
                                                ms_note, delay_r, delay_cat,
                                                uname, started=started_toggle if started_toggle != has_started else None)
                                            audit_log("MS_UPDATED", uname,
                                                f"{init['id']}:{ms['id']}:{new_ms_st}"
                                                + (f":{delay_cat}" if delay_cat else ""))
                                            st.rerun()

                                        # Raise blocker
                                        st.markdown("**Raise a blocker**")
                                        bl1, bl2 = st.columns([3,1])
                                        blocker_text = bl1.text_input("Describe blocker",
                                            key=f"blk_{init['id']}_{ms['id']}")
                                        if bl2.button("Raise", key=f"blkb_{init['id']}_{ms['id']}"):
                                            if blocker_text:
                                                em.raise_blocker(init['id'], ms['id'], blocker_text, uname)
                                                audit_log("BLOCKER_RAISED", uname,
                                                    f"{init['id']}:{ms['id']}:{blocker_text}")
                                                st.warning(f"Blocker raised — escalated to Lead")
                                                st.rerun()

                                        # Resolve open blockers
                                        if open_blockers:
                                            st.markdown("**Open blockers**")
                                            for bi, blk in enumerate(open_blockers):
                                                bl_idx = ms['blockers'].index(blk)
                                                st.markdown(
                                                    f"<div style='padding:6px 10px;background:#FCEBEB;"
                                                    f"border-left:3px solid #E24B4A;border-radius:0 4px 4px 0;"
                                                    f"font-size:12px;margin:2px 0'>"
                                                    f"🚧 {blk['blocker']} — raised by {blk['raised_by']} "
                                                    f"on {blk['raised_at'][:10]}</div>",
                                                    unsafe_allow_html=True)
                                                res_col1, res_col2 = st.columns([3,1])
                                                res_text = res_col1.text_input("Resolution",
                                                    key=f"res_{init['id']}_{ms['id']}_{bi}")
                                                if res_col2.button("Resolve",
                                                    key=f"resb_{init['id']}_{ms['id']}_{bi}"):
                                                    em.resolve_blocker(init['id'], ms['id'], bl_idx, res_text, uname)
                                                    st.success("Blocker resolved!")
                                                    st.rerun()

                            # Add more milestones
                            if (init.get('io') == uname or is_exec_admin) and gate in ('G1','G2','G3'):
                                with st.form(f"ms_add_{init['id']}"):
                                    m1,m2,m3 = st.columns(3)
                                    ms_name  = m1.text_input("Milestone name")
                                    ms_type  = m2.selectbox("Type", MILESTONE_TYPES)
                                    ms_owner = m3.text_input("Owner")
                                    ms_due   = st.date_input("Due date", key=f"msd_{init['id']}")
                                    if st.form_submit_button("+ Add milestone"):
                                        em.add_milestone(init['id'],{
                                            'name':ms_name,'type':ms_type,
                                            'owner':ms_owner,'due_date':str(ms_due),'description':''})
                                        st.rerun()

# ════════════════════════════════════════════════════════════════
# EX-TAB 3: CREATE INITIATIVE
# ════════════════════════════════════════════════════════════════
with ex_tabs[2]:
    st.subheader("Create new initiative")

    workstreams = em.workstreams
    ws_names = [f"{k} — {v['name']}" for k,v in workstreams.items()] if workstreams else []
    sub_ws_map = {f"{k} — {v['name']}": v.get('sub_workstreams',[]) for k,v in workstreams.items()}

    with st.form("create_initiative"):
        st.markdown("#### Basic details")
        c1, c2 = st.columns(2)
        with c1:
            init_name  = st.text_input("Initiative name *")
            init_cat   = st.selectbox("Category *", INITIATIVE_CATEGORIES)
            init_ws    = st.selectbox("Workstream *",
                ['-- Select --'] + ws_names if ws_names else ['-- No workstreams set up yet --'])
        with c2:
            init_obj   = st.text_area("Objective *", height=100,
                placeholder="What problem does this solve? What outcome are we driving?")
            init_impact_est = st.number_input("Estimated impact (KES or units)", min_value=0.0, step=100000.0)

        # Sub-workstream
        if init_ws and init_ws in sub_ws_map and sub_ws_map[init_ws]:
            init_sub_ws = st.selectbox("Sub-workstream", ['--'] + sub_ws_map[init_ws])
        else:
            init_sub_ws = st.text_input("Sub-workstream (if any)")

        st.markdown("#### Ownership")
        oc1, oc2 = st.columns(2)
        with oc1:
            init_io     = st.text_input("Initiative owner (username) *", value=uname)
        with oc2:
            init_io_bk  = st.text_input("Backup initiative owner (username)")

        st.markdown("#### Impact KPIs (optional — required for G2 business case)")
        kpi_selections = st.multiselect("Which KPIs will this initiative impact?",
            IMPACT_KPI_OPTIONS, key="init_kpis")
        init_tags = st.text_input("Tags (comma-separated)", placeholder="wallet share, deposits, Q1")

        if st.form_submit_button("Create initiative", type="primary"):
            if not init_name or not init_obj or init_ws.startswith('--'):
                st.error("Name, objective and workstream are required.")
            else:
                ws_key = init_ws.split(' — ')[0] if ' — ' in init_ws else init_ws
                new_id = em.create_initiative({
                    'name': init_name, 'objective': init_obj,
                    'category': init_cat,
                    'workstream': init_ws,
                    'sub_workstream': init_sub_ws,
                    'io': init_io, 'io_backup': init_io_bk,
                    'estimated_impact': init_impact_est,
                    'impact_kpis': kpi_selections,
                    'tags': [t.strip() for t in init_tags.split(',') if t.strip()],
                    'created_by': uname,
                })
                audit_log("INITIATIVE_CREATED", uname, f"{new_id}:{init_name}")
                st.success(f"Initiative {new_id} created! It is at G0. Submit it to G1 when ready.")
                st.rerun()

# ════════════════════════════════════════════════════════════════
# EX-TAB 4: IDEATION
# ════════════════════════════════════════════════════════════════
with ex_tabs[3]:
    st.subheader("Ideation pool")
    st.caption("Submit ideas for consideration. Ideas can be adopted as initiatives by a workstream lead or IO.")

    ic1, ic2 = st.columns([2,1])
    with ic1:
        with st.form("submit_idea"):
            idea_title = st.text_input("Idea title *")
            idea_desc  = st.text_area("Describe the idea", height=100,
                placeholder="What is the opportunity? What problem does it solve? Rough impact estimate?")
            idea_ws    = st.selectbox("Relevant workstream (optional)",
                ['-- Not sure yet --'] + ws_names if ws_names else ['--'])
            if st.form_submit_button("Submit idea", type="primary"):
                if idea_title:
                    idea_id = em.submit_idea({
                        'title': idea_title, 'description': idea_desc,
                        'workstream': idea_ws, 'submitted_by': uname,
                    })
                    st.success(f"Idea {idea_id} submitted!")
                    st.rerun()
                else:
                    st.error("Title required.")

    with ic2:
        st.metric("Ideas submitted", len(em.ideas))
        submitted  = sum(1 for i in em.ideas if i['status']=='Submitted')
        adopted    = sum(1 for i in em.ideas if i['status']=='Adopted')
        st.metric("Under review", submitted)
        st.metric("Adopted", adopted)

    st.markdown("---")
    st.markdown("#### Idea board")
    sort_by = st.radio("Sort by", ["Newest","Most voted"], horizontal=True, key="idea_sort")
    ideas = sorted(em.ideas,
        key=lambda x: (-len(x.get('votes',[])) if sort_by=="Most voted" else x.get('created_at','')),
        reverse=(sort_by=="Newest"))

    for idea in ideas:
        votes   = len(idea.get('votes',[]))
        adopted = idea['status'] == 'Adopted'
        colour  = "#3B6D11" if adopted else "#185FA5"
        bg      = "#EAF3DE" if adopted else "#E6F1FB"
        with st.expander(
            f"[{idea['status']}] {idea['title']}  —  {idea['submitted_by']}  |  {votes} votes"):
            st.markdown(idea.get('description',''))
            col1, col2, col3 = st.columns(3)
            col1.caption(f"Workstream: {idea.get('workstream','—')}")
            col2.caption(f"Submitted: {idea.get('created_at','')[:10]}")
            if idea['status'] == 'Adopted':
                col3.success(f"Adopted as {idea.get('adopted_as','')}")

            # Vote
            if uname not in idea.get('votes',[]):
                if st.button(f"Vote for this ({votes})", key=f"vote_{idea['id']}"):
                    em.vote_idea(idea['id'], uname)
                    st.rerun()
            else:
                st.caption(f"You voted for this ({votes} votes total)")

            # Adopt (leads/admins only)
            if (is_lead or is_exec_admin) and idea['status'] == 'Submitted':
                if st.button("Adopt as initiative", key=f"adopt_{idea['id']}"):
                    new_id = em.create_initiative({
                        'name': idea['title'], 'objective': idea['description'],
                        'category': 'Other', 'workstream': idea.get('workstream',''),
                        'sub_workstream': '', 'io': idea['submitted_by'],
                        'io_backup': '', 'created_by': uname,
                    })
                    for i in em.ideas:
                        if i['id'] == idea['id']:
                            i['status']     = 'Adopted'
                            i['adopted_as'] = new_id
                            em._save_ideas()
                            break
                    audit_log("IDEA_ADOPTED", uname, f"{idea['id']}→{new_id}")
                    st.success(f"Adopted as {new_id}!"); st.rerun()

# ════════════════════════════════════════════════════════════════
# EX-TAB 5: WORKSTREAMS SETUP
# ════════════════════════════════════════════════════════════════
with ex_tabs[4]:
    st.subheader("Workstream setup")
    st.caption("Define your workstreams (departments) and their sponsors.")

    if is_exec_admin or is_sponsor:
        with st.form("ws_setup"):
            wc1, wc2 = st.columns(2)
            with wc1:
                ws_id      = st.text_input("Workstream ID", placeholder="e.g. SME, RETAIL, HR")
                ws_name    = st.text_input("Workstream name", placeholder="e.g. SME Banking")
                ws_sponsor = st.text_input("Sponsor (Director name / username)")
            with wc2:
                sub_ws = st.text_area("Sub-workstreams (one per line)",
                    placeholder="e.g. SME Direct / SME Relationship / SME Credit")
            if st.form_submit_button("Save workstream"):
                if ws_id and ws_name:
                    sub_list = [s.strip() for s in sub_ws.splitlines() if s.strip()]
                    em.upsert_workstream(ws_id.upper(), ws_name, ws_sponsor, sub_list)
                    audit_log("WS_SAVED", uname, f"{ws_id}:{ws_name}")
                    st.success(f"Workstream {ws_id} saved!"); st.rerun()
                else:
                    st.error("ID and name required.")

    if em.workstreams:
        st.markdown("#### Current workstreams")
        for ws_id, ws in em.workstreams.items():
            with st.expander(f"{ws_id} — {ws['name']}  |  Sponsor: {ws.get('sponsor','—')}"):
                st.write("Sub-workstreams:", ", ".join(ws.get('sub_workstreams',[])) or "None")
                inits = em.get_initiatives(workstream=f"{ws_id} — {ws['name']}", status='All')
                st.caption(f"Initiatives: {len(inits)}")
                gate_dist = {}
                for i in inits:
                    g = i['gate']
                    gate_dist[g] = gate_dist.get(g,0)+1
                if gate_dist:
                    st.caption(" | ".join(f"{g}: {c}" for g,c in gate_dist.items()))
    else:
        st.info("No workstreams configured yet. Add your first workstream above.")

# ════════════════════════════════════════════════════════════════
# EX-TAB 6: IMPACT TRACKING (G4)
# ════════════════════════════════════════════════════════════════
with ex_tabs[5]:
    st.subheader("Impact tracking — G4 initiatives")
    g4_inits = em.get_initiatives(gate='G4', status='All') + em.get_initiatives(gate='G5', status='All')

    if not g4_inits:
        st.info("No initiatives at G4 (impact tracking) yet. Initiatives reach G4 when their Money Step milestone is complete.")
    else:
        sel_init = st.selectbox("Select initiative",
            [f"{i['id']} — {i['name']}" for i in g4_inits], key="it_sel")
        if sel_init:
            init_id_it = sel_init.split(' — ')[0]
            init_it    = em.get_initiative(init_id_it)

            if init_it:
                st.markdown(f"**Objective:** {init_it.get('objective','')}")
                st.markdown(f"**Impact KPIs:** {', '.join(init_it.get('impact_kpis',[]) or ['Not specified'])}")

                # Log monthly impact
                with st.form(f"impact_log_{init_id_it}"):
                    st.markdown("#### Log monthly impact")
                    lc1, lc2, lc3, lc4 = st.columns(4)
                    imp_month  = lc1.text_input("Month", value=datetime.now().strftime("%b %Y"))
                    imp_kpi    = lc2.selectbox("KPI", init_it.get('impact_kpis', IMPACT_KPI_OPTIONS))
                    imp_target = lc3.number_input("Target", min_value=0.0, step=1000.0)
                    imp_actual = lc4.number_input("Actual", min_value=0.0, step=1000.0)
                    imp_note   = st.text_area("Notes / commentary", height=60)
                    if st.form_submit_button("Record impact", type="primary"):
                        em.record_impact(init_id_it, imp_month, imp_kpi, imp_target, imp_actual, imp_note)
                        audit_log("IMPACT_LOGGED", uname, f"{init_id_it}:{imp_month}:{imp_kpi}")
                        st.success("Impact recorded!"); st.rerun()

                # Impact history
                impacts = em.get_impact(init_id_it)
                if impacts:
                    st.markdown("#### Impact history")
                    imp_df = pd.DataFrame(impacts)
                    if 'actual' in imp_df.columns and 'target' in imp_df.columns:
                        imp_df['achievement'] = (imp_df['actual'] / imp_df['target'] * 100).round(1)
                        imp_df['achievement'] = imp_df['achievement'].apply(fmt_pct)
                    show_imp = [c for c in ['month','kpi','target','actual','achievement','note'] if c in imp_df.columns]
                    imp_disp = imp_df[show_imp].copy()
                    if 'target' in imp_disp.columns: imp_disp['target'] = imp_disp['target'].apply(fmt_num)
                    if 'actual' in imp_disp.columns: imp_disp['actual'] = imp_disp['actual'].apply(fmt_num)
                    imp_disp.columns = [c.title() for c in imp_disp.columns]
                    st.dataframe(imp_disp, use_container_width=True, hide_index=True)

                    # Trend chart
                    if len(impacts) > 1:
                        for kpi_name in imp_df['kpi'].unique():
                            kpi_data = imp_df[imp_df['kpi']==kpi_name].copy()
                            kpi_data['actual_num']  = pd.to_numeric(kpi_data['actual'],  errors='coerce')
                            kpi_data['target_num']  = pd.to_numeric(kpi_data['target'],  errors='coerce')
                            fig_t = px.line(kpi_data, x='month', y=['actual_num','target_num'],
                                            title=f"{kpi_name} — actual vs target",
                                            markers=True)
                            fig_t.update_layout(height=280)
                            st.plotly_chart(fig_t, use_container_width=True)

                    # G5 submission
                    consistent_months = len(imp_df['month'].unique())
                    if consistent_months >= 3 and init_it.get('gate') == 'G4' and 'pending_gate' not in init_it:
                        st.success(f"Impact tracked for {consistent_months} months. Ready to submit to G5.")
                        if st.button("Submit to G5 — embed initiative", type="primary"):
                            ok, msg = em.submit_for_gate(init_id_it, 'G5', uname,
                                f"Impact consistent over {consistent_months} months")
                            audit_log("GATE_SUBMITTED", uname, f"{init_id_it}→G5")
                            st.success(msg); st.rerun()
                    elif consistent_months < 3:
                        st.info(f"Impact tracked for {consistent_months} month(s). Minimum 3 months required before G5 submission.")

# ════════════════════════════════════════════════════════════════
# EX-TAB 7: MY MILESTONES (Milestone Owner personal view)
# ════════════════════════════════════════════════════════════════
with ex_tabs[6]:
    st.subheader("My milestones")
    st.caption("Every milestone assigned to you across all initiatives — sorted by urgency.")

    my_mss = em.get_all_milestones_for_owner(uname)

    if not my_mss:
        st.info("No milestones currently assigned to you. "
                "When an Initiative Owner assigns you to a milestone, it will appear here.")
    else:
        # Summary metrics
        total_ms   = len(my_mss)
        overdue    = sum(1 for m in my_mss if m['days_to_due'] < 0 and m['status'] != 'Complete')
        due_soon   = sum(1 for m in my_mss if 0 <= m['days_to_due'] <= 7 and m['status'] != 'Complete')
        complete   = sum(1 for m in my_mss if m['status'] == 'Complete')
        blocked    = sum(1 for m in my_mss if any(not b['resolved'] for b in m.get('blockers',[])))

        mc1,mc2,mc3,mc4,mc5 = st.columns(5)
        mc1.metric("Total assigned", total_ms)
        mc2.metric("Complete", complete)
        mc3.metric("Due this week", due_soon)
        mc4.metric("Overdue", overdue, delta=f"-{overdue}" if overdue else None,
                   delta_color="inverse")
        mc5.metric("Blockers raised", blocked)

        # Filter
        status_filt = st.radio("Show", ["All","Not Complete","Overdue & Due Soon"],
                                horizontal=True, key="mymsfilt")

        view_mss = my_mss
        if status_filt == "Not Complete":
            view_mss = [m for m in my_mss if m['status'] != 'Complete']
        elif status_filt == "Overdue & Due Soon":
            view_mss = [m for m in my_mss if m['days_to_due'] <= 7 and m['status'] != 'Complete']

        if not view_mss:
            st.success("Nothing urgent — all milestones on track!")
        else:
            for ms in view_mss:
                esc_level = ms.get('escalation_level', 0)
                esc_cfg   = ESC_CONFIG.get(esc_level, ESC_CONFIG[0])
                days      = ms['days_to_due']
                open_blk  = [b for b in ms.get('blockers',[]) if not b['resolved']]
                ms_type_c = {'Implementation':'#185FA5','Health Check':'#0F6E56',
                             'Money Step':'#993C1D'}.get(ms.get('type',''),'#888780')

                # Card header colour by urgency
                if esc_level >= 3:   card_border = '#A32D2D'
                elif esc_level == 2: card_border = '#993C1D'
                elif esc_level == 1: card_border = '#BA7517'
                elif ms['status'] == 'Complete': card_border = '#3B6D11'
                else:               card_border = '#BDC3C7'

                with st.expander(
                    f"{esc_cfg['icon']} {ms['initiative_name']} → {ms['name']}  "
                    f"|  {ms.get('type','')}  |  Due {ms['due_date']}",
                    expanded=(esc_level >= 2)):

                    # Context row
                    ctx1, ctx2, ctx3, ctx4 = st.columns(4)
                    ctx1.markdown(f"**Initiative:** {ms['initiative_id']}")
                    ctx2.markdown(f"**Workstream:** {ms.get('workstream','—')}")
                    ctx3.markdown(f"**Gate:** {ms.get('gate','—')}")
                    ctx4.markdown(f"**IO:** {ms.get('io','—')}")

                    # Status banner
                    st.markdown(
                        f"<div style='padding:10px 14px;border-left:4px solid {card_border};"
                        f"border-radius:0 6px 6px 0;background:var(--color-background-secondary);"
                        f"margin:8px 0'>"
                        f"<div style='display:flex;justify-content:space-between'>"
                        f"<span style='font-weight:500'>{ms['status']}</span>"
                        f"{escalation_badge(esc_level)}"
                        f"</div>"
                        f"<div style='font-size:12px;color:var(--color-text-secondary);margin-top:4px'>"
                        f"{days_label(days)} | "
                        f"{'Primary owner' if ms['is_primary_owner'] else 'Co-owner'}"
                        f"{'<br><b>Delay reason:</b> ' + ms['delay_reason'] if ms.get('delay_reason') else ''}"
                        f"{'<br><span style="color:#A32D2D">🚧 ' + str(len(open_blk)) + ' open blocker(s)</span>' if open_blk else ''}"
                        f"</div></div>",
                        unsafe_allow_html=True)

                    if ms.get('description'):
                        st.caption(f"Description: {ms['description']}")

                    # Start date status — prominent if overdue start
                    if ms.get('start_date') and ms['status'] == 'Not Started':
                        try:
                            sd = date.fromisoformat(ms['start_date'])
                            days_to_start = (sd - date.today()).days
                            if days_to_start == 0:
                                st.warning("⏰ **This milestone starts today** — please mark it as In Progress once work begins.")
                            elif days_to_start < 0:
                                st.error(f"🚨 **This milestone should have started {-days_to_start} day(s) ago** "
                                         f"(start date: {ms['start_date']}). Please update status immediately.")
                            elif days_to_start <= 2:
                                st.info(f"⏰ This milestone starts in {days_to_start} day(s) ({ms['start_date']}). Prepare to begin.")
                        except: pass

                    # Escalation trail
                    if ms.get('escalation_history'):
                        with st.expander("Escalation history"):
                            for eh in ms['escalation_history']:
                                st.caption(f"{eh['date']} — Level {eh['level']}: {eh['reason']} (by {eh['by']})")

                    # Update my status from here
                    if ms['confirmed'] and ms['status'] != 'Complete':
                        with st.form(f"myms_update_{ms['initiative_id']}_{ms['id']}"):
                            u1, u2, u3 = st.columns(3)
                            status_opts = ['Not Started','In Progress','Complete','Delayed']
                            new_st    = u1.selectbox("Update status", status_opts,
                                index=status_opts.index(ms['status']) if ms['status'] in status_opts else 0)
                            note      = u2.text_input("Progress note")
                            started_v = u3.checkbox("Has started", value=ms.get('has_started',False),
                                help="Tick when work has physically begun on this milestone")

                            delay_r = delay_cat = ""
                            if new_st == 'Delayed':
                                dc1, dc2 = st.columns(2)
                                delay_cat = dc1.selectbox("Delay category *", DELAY_CATEGORIES,
                                    key=f"mymsdcat_{ms['initiative_id']}_{ms['id']}")
                                delay_r   = dc2.text_input("Delay detail *",
                                    value=ms.get('delay_reason',''),
                                    key=f"mymsdtxt_{ms['initiative_id']}_{ms['id']}")
                                if delay_cat in STRUCTURAL_CATEGORIES:
                                    st.markdown(
                                        f"<div style='padding:10px 14px;background:#FCEBEB;"
                                        f"border-left:4px solid #A32D2D;border-radius:0 6px 6px 0;font-size:13px'>"
                                        f"🚨 <b style='color:#A32D2D'>Immediate escalation</b> — "
                                        f"'{delay_cat}' delay notifies all parties (IO, Lead, Sponsor) "
                                        f"automatically when you save.</div>",
                                        unsafe_allow_html=True)
                                elif delay_cat:
                                    st.info(f"ℹ️ '{delay_cat}' delay — standard escalation applies (IO day 2, Lead day 3, Sponsor day 7).")

                            blocker_txt = st.text_input("Raise a blocker (optional)",
                                help="Escalates immediately to Lead level")

                            if st.form_submit_button("Save & update", type="primary"):
                                em.update_milestone_status(
                                    ms['initiative_id'], ms['id'], new_st, note,
                                    delay_r, delay_cat, uname,
                                    started=started_v if started_v != ms.get('has_started',False) else None)
                                if blocker_txt:
                                    em.raise_blocker(ms['initiative_id'], ms['id'], blocker_txt, uname)
                                    st.warning("Blocker raised — escalated to Lead")
                                audit_log("MS_UPDATED_BY_OWNER", uname,
                                    f"{ms['initiative_id']}:{ms['id']}:{new_st}"
                                    + (f":{delay_cat}" if delay_cat else ""))
                                st.success("Updated!")
                                st.rerun()
                    elif not ms['confirmed']:
                        if st.button(f"Confirm I accept this milestone",
                                     key=f"myms_conf_{ms['initiative_id']}_{ms['id']}",
                                     type="primary"):
                            em.confirm_milestone(ms['initiative_id'], ms['id'], uname)
                            st.success("Milestone confirmed!")
                            st.rerun()

# ════════════════════════════════════════════════════════════════
# EX-TAB 8: ESCALATION TRACKER (Management view)
# ════════════════════════════════════════════════════════════════
with ex_tabs[7]:
    st.subheader("Escalation tracker")
    st.caption("Milestones requiring management attention — sorted by severity.")

    # Scope: managers see their workstreams, admins see all
    scope_inits = em.get_initiatives(status='All')
    if not (is_exec_admin or is_sponsor or is_lead):
        # IO sees only their own initiatives
        scope_inits = [i for i in scope_inits
                       if i.get('io') == uname or i.get('io_backup') == uname]

    esc_buckets = em.get_escalation_dashboard(scope_inits)
    total_at_risk = sum(len(v) for v in esc_buckets.values())

    if total_at_risk == 0:
        st.success("No escalations — all milestones on track.")
    else:
        # Summary — banking timelines
        ec1,ec2,ec3,ec4,ec5,ec6 = st.columns(6)
        ec1.metric("Total at risk",           total_at_risk)
        ec2.metric("💥 Critical / Sponsor",   len(esc_buckets.get(4,[])))
        ec3.metric("🚨 Lead escalated",        len(esc_buckets.get(3,[])))
        ec4.metric("🔴 IO notified",           len(esc_buckets.get(2,[])))
        ec5.metric("🟡 Due soon",              len(esc_buckets.get(1,[])))
        ec6.metric("⏰ Not started",            len(esc_buckets.get(5,[])))

        # LEVEL 4 — Critical / Structural (most urgent)
        if esc_buckets.get(4):
            st.markdown("---")
            st.markdown(
                "<div style='padding:10px 16px;background:#F7C1C1;border-left:4px solid #791F1F;"
                "border-radius:0 6px 6px 0;margin-bottom:12px'>"
                "<b style='color:#791F1F'>💥 Level 4 — Sponsor / Director: immediate action</b> "
                "<span style='font-size:12px;color:#501313'>"
                "Overdue >7 days OR structural/regulatory delay. Sponsor must intervene today.</span>"
                "</div>", unsafe_allow_html=True)
            for ms in esc_buckets[4]:
                open_blk = [b for b in ms.get('blockers',[]) if not b['resolved']]
                delay_cat = ms.get('delay_category','')
                st.markdown(
                    f"<div style='padding:10px 14px;background:#F7C1C1;border-left:4px solid #791F1F;"
                    f"border-radius:0 6px 6px 0;margin:4px 0'>"
                    f"<div style='display:flex;justify-content:space-between'>"
                    f"<b>{ms['initiative_name']} → {ms['name']}</b>"
                    f"<span style='color:#791F1F;font-weight:500'>{ms['overdue_days']}d overdue</span>"
                    f"</div>"
                    f"<div style='font-size:12px;color:#501313;margin-top:4px'>"
                    f"Owner: <b>{ms['owner']}</b> | Workstream: {ms['workstream']} | "
                    f"IO: {ms['io']} | Due: {ms['due_date']}"
                    f"{'<br><b>Delay category: ' + delay_cat + '</b>' if delay_cat else '<br><b style="color:#A32D2D">⚠ Delay category not stated</b>'}"
                    f"{'<br>Detail: ' + ms['delay_reason'] if ms.get('delay_reason') else ''}"
                    f"{'<br>🚧 ' + str(len(open_blk)) + ' open blocker(s): ' + open_blk[0]['blocker'] if open_blk else ''}"
                    f"</div></div>", unsafe_allow_html=True)

        # LEVEL 5 — Not started (start date passed)
        if esc_buckets.get(5):
            st.markdown("---")
            st.markdown(
                "<div style='padding:10px 16px;background:#F1EFE8;border-left:4px solid #5F5E5A;"
                "border-radius:0 6px 6px 0;margin-bottom:12px'>"
                "<b style='color:#5F5E5A'>⏰ Level 5 — Not started (start date passed)</b> "
                "<span style='font-size:12px;color:#444441'>"
                "Milestone should have started. IO to follow up with owner immediately.</span>"
                "</div>", unsafe_allow_html=True)
            for ms in esc_buckets[5]:
                try:
                    days_late = (date.today() - date.fromisoformat(ms.get('start_date',''))).days
                except: days_late = 0
                st.markdown(
                    f"<div style='padding:8px 12px;background:#F1EFE8;border-left:3px solid #5F5E5A;"
                    f"border-radius:0 4px 4px 0;margin:3px 0;font-size:12px'>"
                    f"<b>{ms['initiative_name']} → {ms['name']}</b> "
                    f"<span style='color:#5F5E5A'>Should have started {days_late}d ago</span><br>"
                    f"Owner: {ms['owner']} | Start date: {ms.get('start_date','?')} | Due: {ms['due_date']}"
                    f"</div>", unsafe_allow_html=True)

        # LEVEL 3 — Lead escalations
        if esc_buckets.get(3):
            st.markdown("---")
            st.markdown(
                "<div style='padding:10px 16px;background:#FCEBEB;border-left:4px solid #A32D2D;"
                "border-radius:0 6px 6px 0;margin-bottom:12px'>"
                "<b style='color:#A32D2D'>🚨 Level 3 — Workstream lead: action required</b> "
                "<span style='font-size:12px;color:#791F1F'>"
                "Overdue 3–7 days or blocker raised. Lead must review and unblock today.</span>"
                "</div>", unsafe_allow_html=True)

            for ms in esc_buckets.get(3,[]):
                open_blk = [b for b in ms.get('blockers',[]) if not b['resolved']]
                st.markdown(
                    f"<div style='padding:10px 14px;background:#FCEBEB;border-left:4px solid #A32D2D;"
                    f"border-radius:0 6px 6px 0;margin:4px 0'>"
                    f"<div style='display:flex;justify-content:space-between'>"
                    f"<b>{ms['initiative_name']} — {ms['name']}</b>"
                    f"<span style='color:#A32D2D;font-weight:500'>{ms['overdue_days']}d overdue</span>"
                    f"</div>"
                    f"<div style='font-size:12px;color:#791F1F;margin-top:4px'>"
                    f"Owner: {ms['owner']} | Workstream: {ms['workstream']} | "
                    f"IO: {ms['io']} | Due: {ms['due_date']}"
                    f"{'<br><b>Delay reason:</b> ' + ms.get('delay_reason','Not stated') if ms.get('delay_reason') else '<br><b>Delay reason: Not stated</b>'}"
                    f"{'<br>🚧 ' + str(len(open_blk)) + ' unresolved blocker(s)' if open_blk else ''}"
                    f"</div></div>", unsafe_allow_html=True)

                if open_blk:
                    for blk in open_blk:
                        st.markdown(
                            f"<div style='margin-left:20px;padding:5px 10px;background:#F7C1C1;"
                            f"border-radius:4px;font-size:11px;margin-top:2px'>"
                            f"🚧 {blk['blocker']} — raised by {blk['raised_by']} "
                            f"on {blk['raised_at'][:10]}</div>",
                            unsafe_allow_html=True)

        # LEVEL 2 — Lead notifications
        if esc_buckets.get(2):
            st.markdown("---")
            st.markdown(
                "<div style='padding:10px 16px;background:#FAECE7;border-left:4px solid #993C1D;"
                "border-radius:0 6px 6px 0;margin-bottom:12px'>"
                "<b style='color:#993C1D'>🔴 Level 2 — Workstream lead attention</b> "
                "<span style='font-size:12px;color:#712B13'>"
                "Overdue 8–21 days or blocker raised.</span>"
                "</div>", unsafe_allow_html=True)

            for ms in esc_buckets.get(2,[]):
                open_blk = [b for b in ms.get('blockers',[]) if not b['resolved']]
                st.markdown(
                    f"<div style='padding:10px 14px;background:#FAECE7;border-left:3px solid #993C1D;"
                    f"border-radius:0 6px 6px 0;margin:4px 0;font-size:13px'>"
                    f"<b>{ms['initiative_name']} — {ms['name']}</b> "
                    f"<span style='color:#993C1D'>{ms['overdue_days']}d overdue</span><br>"
                    f"Owner: {ms['owner']} | Workstream: {ms['workstream']} | Due: {ms['due_date']}"
                    f"{'<br>Delay: ' + ms['delay_reason'] if ms.get('delay_reason') else ''}"
                    f"{'<br>🚧 Blocker: ' + open_blk[0]['blocker'] if open_blk else ''}"
                    f"</div>", unsafe_allow_html=True)

        # LEVEL 1 — IO notifications (due soon / just overdue)
        if esc_buckets.get(1):
            st.markdown("---")
            st.markdown(
                "<div style='padding:10px 16px;background:#FAEEDA;border-left:4px solid #BA7517;"
                "border-radius:0 6px 6px 0;margin-bottom:12px'>"
                "<b style='color:#BA7517'>🟡 Level 1 — IO awareness</b> "
                "<span style='font-size:12px;color:#854F0B'>"
                "Overdue 1–2 days. IO must follow up with milestone owner immediately.</span>"
                "</div>", unsafe_allow_html=True)

            for ms in esc_buckets.get(1,[]):
                st.markdown(
                    f"<div style='padding:8px 12px;background:#FAEEDA;border-left:3px solid #BA7517;"
                    f"border-radius:0 4px 4px 0;margin:3px 0;font-size:12px'>"
                    f"<b>{ms['initiative_name']} — {ms['name']}</b> "
                    f"<span style='color:#BA7517'>{ms['overdue_days']}d overdue</span> | "
                    f"Owner: {ms['owner']} | Due: {ms['due_date']}"
                    f"{'| Delay: ' + ms['delay_reason'] if ms.get('delay_reason') else ''}"
                    f"</div>", unsafe_allow_html=True)

        # Summary table — downloadable
        st.markdown("---")
        st.markdown("#### Full escalation register")
        all_esc = []
        for level in [4,3,2,1,5]:
            for ms in esc_buckets.get(level,[]):
                all_esc.append({
                    'Level':           f"L{level} — {ESC_CONFIG[level]['label']}",
                    'Initiative':      ms['initiative_name'],
                    'Milestone':       ms['name'],
                    'Type':            ms.get('type',''),
                    'Owner':           ms['owner'],
                    'Workstream':      ms['workstream'],
                    'IO':              ms['io'],
                    'Due Date':        ms['due_date'],
                    'Days Overdue':    ms['overdue_days'],
                    'Status':          ms['status'],
                    'Delay Reason':    ms.get('delay_reason',''),
                    'Open Blockers':   sum(1 for b in ms.get('blockers',[]) if not b['resolved']),
                })
        if all_esc:
            esc_df = pd.DataFrame(all_esc)

            def hl_esc_level(v):
                if 'L3' in str(v): return 'background-color:#FCEBEB;color:#A32D2D'
                if 'L2' in str(v): return 'background-color:#FAECE7;color:#993C1D'
                if 'L1' in str(v): return 'background-color:#FAEEDA;color:#BA7517'
                return ''

            st.dataframe(
                esc_df.style.map(hl_esc_level, subset=['Level']),
                use_container_width=True, hide_index=True)

            csv_esc = esc_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "⬇️ Download escalation register",
                csv_esc,
                f"A2Z_Escalations_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv")


# ── TAB 11: PRODUCTS — Product lifecycle registry ───────────────────────────
