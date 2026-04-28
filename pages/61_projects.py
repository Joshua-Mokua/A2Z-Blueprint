"""pages/61_projects.py — Project Management & Execution Tracking.
Full project lifecycle: assignment → milestones → action items → BSC auto-scoring.
Every milestone/action completed automatically updates the owner's BSC.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict
from decimal import Decimal
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.core import get_org_config

require_access("projects")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role      = str(ud.get("role", "")).lower()
full_name = ud.get("full_name", uname)
dept      = ud.get("department", "")
is_admin  = ud.get("is_admin", False)
is_exec   = any(x in role for x in ("director","chief","head of","managing","md","ceo"))
is_pm     = any(x in role for x in ("manager","head","director","officer","analyst","specialist"))
sc        = str(ud.get("staff_code", ""))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 Project Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Assign · Track milestones · Action items · BSC auto-scoring</span></div>",
    unsafe_allow_html=True)

# ── Loaders ───────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def _load_projects():
    p = DATA / "projects.json"
    raw = a2z_db.load_json(p) if p.exists() else []
    return raw if isinstance(raw, list) else raw.get("projects", [])

@st.cache_data(ttl=300)
def _load_users():
    p = DATA / "users.json"
    return a2z_db.load_json(p) if p.exists() else {}

def _save_projects(projects):
    (DATA / "projects.json").write_text(json.dumps(projects, indent=2))
    st.cache_data.clear()

def _trigger_bsc_update(username, action_desc):
    """Update BSC scores when project work is completed."""
    try:
        from utils.core import update_bsc_from_modules
        update_bsc_from_modules(username)
        audit_log("BSC_AUTO_UPDATE", username, f"Projects: {action_desc}")
    except Exception as e:
        pass  # Never crash the UI for BSC updates

projects  = _load_projects()
all_users = _load_users()

# ── Build user lookup ─────────────────────────────────────────────
user_options = {u: d.get("full_name", u) for u, d in all_users.items()
                if d.get("active", True) and d.get("is_admin") is not True}
user_display = {v: k for k, v in user_options.items()}

# ── Filter projects by role ───────────────────────────────────────
if is_exec or is_admin:
    visible = projects
    my_projects    = [p for p in projects if p.get("owner_username") == uname]
    my_milestones  = [(p, ms) for p in projects for ms in p.get("milestones",[])
                      if ms.get("owner_username") == uname]
    my_actions     = [(p, a) for p in projects for a in p.get("action_items",[])
                      if a.get("owner_username") == uname]
else:
    visible = [p for p in projects
               if p.get("owner_username") == uname
               or p.get("department") == dept
               or any(ms.get("owner_username") == uname for ms in p.get("milestones",[]))
               or any(a.get("owner_username") == uname for a in p.get("action_items",[]))]
    my_projects   = [p for p in projects if p.get("owner_username") == uname]
    my_milestones = [(p, ms) for p in projects for ms in p.get("milestones",[])
                     if ms.get("owner_username") == uname]
    my_actions    = [(p, a) for p in projects for a in p.get("action_items",[])
                     if a.get("owner_username") == uname]

# ── Summary strip ─────────────────────────────────────────────────
total_ms_due  = sum(1 for _,ms in my_milestones if ms.get("status") != "Complete"
                    and ms.get("due_date","") <= str(today + timedelta(days=14)))
total_act_due = sum(1 for _,a in my_actions if a.get("status") == "Open"
                    and a.get("due_date","") <= str(today))
overdue_ms    = sum(1 for _,ms in my_milestones if ms.get("status") != "Complete"
                    and ms.get("due_date","") < str(today))

if overdue_ms: st.error(f"🔴 {overdue_ms} overdue milestone(s) assigned to you")
if total_act_due: st.warning(f"⚠️ {total_act_due} action item(s) overdue")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total projects",       len(visible))
m2.metric("My projects",          len(my_projects))
m3.metric("My milestones",        len(my_milestones))
m4.metric("My actions",           len(my_actions))
m5.metric("Due this fortnight",   total_ms_due + total_act_due,
          delta_color="normal" if not (total_ms_due + total_act_due) else "inverse")

tabs = st.tabs(["📊 Dashboard","📋 All Projects","🎯 My Work","➕ New Project",
                "🔧 Assign Work","📈 BSC Impact"])

# ══════════════════════════════════════════════════════════════════
# TAB 0 — Dashboard
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    # Portfolio summary
    by_status  = defaultdict(int)
    by_rag     = defaultdict(int)
    total_budget = 0.0
    total_spent  = 0.0
    for p in visible:
        by_status[p.get("status","Unknown")] += 1
        by_rag[p.get("rag_status","Green")] += 1
        total_budget += float(p.get("budget_m", 0) or 0)
        total_spent  += float(p.get("spent_m", 0) or 0)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Active projects",  by_status.get("Active",0) + by_status.get("In Progress",0))
    c2.metric("Budget (KES M)",   f"{total_budget:.1f}")
    c3.metric("Spent (KES M)",    f"{total_spent:.1f}")
    c4.metric("Budget used",      f"{total_spent/max(total_budget,1)*100:.0f}%")

    # RAG summary
    col_r, col_a, col_g = st.columns(3)
    col_r.metric("🔴 Red",    by_rag.get("Red",0))
    col_a.metric("🟡 Amber",  by_rag.get("Amber",0))
    col_g.metric("🟢 Green",  by_rag.get("Green",0))

    # Upcoming milestones across all projects
    st.markdown("**Milestones due in next 30 days:**")
    upcoming = []
    for p in visible:
        for ms in p.get("milestones",[]):
            if ms.get("status") != "Complete":
                due = ms.get("due_date","")
                if due and due <= str(today + timedelta(days=30)):
                    owner_name = user_options.get(ms.get("owner_username",""), ms.get("owner_username",""))
                    upcoming.append({
                        "Project": p["name"][:30],
                        "Milestone": ms.get("name","")[:30],
                        "Owner": owner_name[:20],
                        "Due": due[:10],
                        "Status": ms.get("status",""),
                        "Overdue": "🔴" if due < str(today) else "🟡" if due <= str(today+timedelta(days=7)) else ""
                    })

    if upcoming:
        st.dataframe(pd.DataFrame(sorted(upcoming, key=lambda x:x["Due"])),
                    use_container_width=True, hide_index=True)
    else:
        st.info("No milestones due in the next 30 days.")

# ══════════════════════════════════════════════════════════════════
# TAB 1 — All Projects
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    f1,f2,f3 = st.columns(3)
    fstatus = f1.selectbox("Status",["All","Planning","Active","On Hold","Completed","Cancelled"],key="proj_fstat")
    frag    = f2.selectbox("RAG",["All","Green","Amber","Red"],key="proj_frag")
    fdept   = f3.selectbox("Department",["All"]+sorted(set(p.get("department","") for p in visible)),key="proj_fdept")

    vis = [p for p in visible
           if (fstatus=="All" or p.get("status","")==fstatus)
           and (frag=="All" or p.get("rag_status","")==frag)
           and (fdept=="All" or p.get("department","")==fdept)]

    rows = []
    for p in sorted(vis, key=lambda x: x.get("rag_status","Green")):
        ms_total = len(p.get("milestones",[]))
        ms_done  = sum(1 for ms in p.get("milestones",[]) if ms.get("status")=="Complete")
        act_open = sum(1 for a in p.get("action_items",[]) if a.get("status")=="Open")
        rag_icon = {"Red":"🔴","Amber":"🟡","Green":"🟢"}.get(p.get("rag_status","Green"),"🟢")
        owner_name = user_options.get(p.get("owner_username",""), p.get("project_manager",""))
        rows.append({
            "RAG": rag_icon,
            "Project": p["name"][:35],
            "Dept": p.get("department","")[:15],
            "PM": owner_name[:18],
            "Status": p.get("status",""),
            "Progress": f"{p.get('pct_complete',0)}%",
            "Budget (M)": float(p.get("budget_m",0) or 0),
            "Spent (M)": float(p.get("spent_m",0) or 0),
            "Milestones": f"{ms_done}/{ms_total}",
            "Open Actions": act_open,
            "End Date": p.get("planned_end_date","")[:10],
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # Project detail expander
    if vis:
        sel = st.selectbox("View project detail", [p["id"]+" — "+p["name"][:40] for p in vis], key="proj_detail_sel")
        proj_id = sel.split(" — ")[0]
        proj = next((p for p in vis if p["id"]==proj_id), {})

        if proj:
            with st.expander(f"📄 {proj['name']}", expanded=True):
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Progress", f"{proj.get('pct_complete',0)}%")
                c2.metric("Budget", f"KES {proj.get('budget_m',0):.1f}M")
                c3.metric("Spent", f"KES {proj.get('spent_m',0):.1f}M")
                c4.metric("RAG", {"Red":"🔴 Red","Amber":"🟡 Amber","Green":"🟢 Green"}.get(proj.get("rag_status","Green"),""))

                owner_nm = user_options.get(proj.get("owner_username",""), proj.get("project_manager",""))
                st.markdown(f"**PM:** {owner_nm} | **Dept:** {proj.get('department','')} | "
                           f"**Start:** {proj.get('start_date','')[:10]} | **End:** {proj.get('planned_end_date','')[:10]}")
                st.markdown(f"**Description:** {proj.get('description','—')}")

                # Milestones
                st.markdown("**Milestones:**")
                for ms in proj.get("milestones",[]):
                    icon = "✅" if ms.get("status")=="Complete" else "🔄" if ms.get("status")=="In Progress" else "⏳"
                    ov   = "🔴" if ms.get("due_date","") < str(today) and ms.get("status")!="Complete" else ""
                    ms_owner = user_options.get(ms.get("owner_username",""), ms.get("owner_username",""))
                    st.markdown(f"  {icon}{ov} **{ms.get('name','')}** — Due: {ms.get('due_date','')[:10]} | "
                               f"Owner: {ms_owner} | {ms.get('status','')}")

                # Action items
                open_acts = [a for a in proj.get("action_items",[]) if a.get("status")=="Open"]
                if open_acts:
                    st.markdown(f"**Open action items ({len(open_acts)}):**")
                    for a in open_acts:
                        a_owner = user_options.get(a.get("owner_username",""), a.get("owner_username",""))
                        ov = "🔴" if a.get("due_date","") < str(today) else ""
                        st.markdown(f"  {ov} [{a.get('priority','')}] {a.get('description','')} — "
                                   f"Owner: {a_owner} | Due: {a.get('due_date','')[:10]}")

# ══════════════════════════════════════════════════════════════════
# TAB 2 — My Work
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown(f"**Your assigned work — {full_name}:**")

    sub = st.tabs(["🎯 My Milestones","📌 My Actions","✅ Mark Complete"])

    with sub[0]:
        if my_milestones:
            ms_rows = []
            for proj, ms in sorted(my_milestones, key=lambda x: x[1].get("due_date","")):
                overdue = ms.get("due_date","") < str(today) and ms.get("status") != "Complete"
                ms_rows.append({
                    "Project": proj["name"][:28],
                    "Milestone": ms.get("name","")[:28],
                    "Due": ms.get("due_date","")[:10],
                    "Status": ms.get("status",""),
                    "Complete %": ms.get("completion_pct",0),
                    "BSC Scored": "✅" if ms.get("bsc_scored") else "",
                    "Overdue": "🔴" if overdue else "",
                })
            st.dataframe(pd.DataFrame(ms_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No milestones assigned to you.")

    with sub[1]:
        if my_actions:
            act_rows = []
            for proj, a in sorted(my_actions, key=lambda x: x[1].get("due_date","")):
                overdue = a.get("due_date","") < str(today) and a.get("status") != "Closed"
                act_rows.append({
                    "Project": proj["name"][:28],
                    "Action": a.get("description","")[:35],
                    "Priority": a.get("priority",""),
                    "Due": a.get("due_date","")[:10],
                    "Status": a.get("status",""),
                    "Overdue": "🔴" if overdue else "",
                })
            st.dataframe(pd.DataFrame(act_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No action items assigned to you.")

    with sub[2]:
        st.markdown("**Mark your work as complete — this updates your BSC automatically:**")

        # Milestones to complete
        pending_ms = [(p,ms) for p,ms in my_milestones if ms.get("status") != "Complete"]
        if pending_ms:
            st.markdown("**Pending milestones:**")
            for proj, ms in pending_ms:
                with st.expander(f"🎯 {ms.get('name','')} — {proj['name'][:30]}"):
                    c1,c2 = st.columns(2)
                    pct = c1.slider("Completion %", 0, 100, ms.get("completion_pct",0),
                                   key=f"ms_pct_{ms['id']}")
                    note = c2.text_input("Update note", key=f"ms_note_{ms['id']}")
                    mark_done = st.checkbox("Mark as Complete", key=f"ms_done_{ms['id']}")

                    if st.button("💾 Save update", key=f"ms_save_{ms['id']}", type="primary"):
                        all_projs = _load_projects()
                        for p2 in all_projs:
                            for m2 in p2.get("milestones",[]):
                                if m2.get("id") == ms["id"]:
                                    m2["completion_pct"] = pct
                                    if note: m2["notes"] = note
                                    if mark_done:
                                        m2["status"] = "Complete"
                                        m2["completed_date"] = str(today)
                                        m2["bsc_scored"] = True
                                    break
                        _save_projects(all_projs)
                        audit_log("MILESTONE_UPDATED", uname,
                                 f"{ms.get('name','')} in {proj['name']}: {pct}% complete")
                        if mark_done:
                            _trigger_bsc_update(uname, f"Milestone completed: {ms.get('name','')}")
                            st.success("✅ Milestone marked complete — your BSC has been updated!")
                        else:
                            st.success(f"✅ Progress updated to {pct}%")
                        st.rerun()

        # Action items to close
        open_acts = [(p,a) for p,a in my_actions if a.get("status") == "Open"]
        if open_acts:
            st.markdown("**Open action items:**")
            for proj, act in open_acts:
                with st.expander(f"📌 {act.get('description','')[:50]} — {proj['name'][:25]}"):
                    outcome = st.text_area("Outcome / resolution", key=f"act_out_{act['id']}")
                    close_it = st.checkbox("Close this action item", key=f"act_close_{act['id']}")
                    if st.button("💾 Save", key=f"act_save_{act['id']}", type="primary"):
                        all_projs = _load_projects()
                        for p2 in all_projs:
                            for a2 in p2.get("action_items",[]):
                                if a2.get("id") == act["id"]:
                                    a2["notes"] = outcome
                                    if close_it:
                                        a2["status"] = "Closed"
                                        a2["closed_date"] = str(today)
                                        a2["bsc_scored"] = True
                                    break
                        _save_projects(all_projs)
                        audit_log("ACTION_CLOSED", uname, f"Action closed in {proj['name']}")
                        if close_it:
                            _trigger_bsc_update(uname, f"Action item closed in {proj['name']}")
                            st.success("✅ Action item closed — your BSC has been updated!")
                        else:
                            st.success("✅ Notes saved")
                        st.rerun()

# ══════════════════════════════════════════════════════════════════
# TAB 3 — New Project
# ══════════════════════════════════════════════════════════════════
with tabs[3]:
    if is_pm or is_admin:
        org_cfg = get_org_config()
        depts   = [d["name"] for d in org_cfg.get("departments",[]) if d.get("active",True)]
        pm_users = [(k, v) for k,v in user_options.items()
                    if any(x in all_users.get(k,{}).get("role","").lower()
                           for x in ("manager","head","officer","analyst"))]

        c1,c2 = st.columns(2)
        _pname  = st.text_input("Project name *", key="np_name")
        _pdesc  = st.text_area("Description", key="np_desc")
        _pdept  = c1.selectbox("Department", depts, key="np_dept")
        _pcat   = c2.selectbox("Category",
                               ["Strategic","Technology","Operations","Compliance",
                                "Customer Experience","Infrastructure","HR","Finance","Other"],
                               key="np_cat")
        _ppm_display = c1.selectbox("Project Manager *",
                                    [f"{v} ({k})" for k,v in pm_users[:50]], key="np_pm")
        _pprio  = c2.selectbox("Priority", ["High","Medium","Low"], key="np_prio")
        _pstart = c1.date_input("Start date", key="np_start")
        _pend   = c2.date_input("Planned end date", key="np_end")
        _pbudget= st.number_input("Budget (KES M)", 0.0, 10000.0, 1.0, key="np_budget")
        _pspon  = st.text_input("Project sponsor", key="np_spon")

        if st.button("💾 Create project", key="np_create", type="primary"):
            if _pname.strip() and _ppm_display:
                pm_username = _ppm_display.split("(")[-1].rstrip(")")
                all_projs = _load_projects()
                new_proj = {
                    "id":              f"PROJ{len(all_projs)+1:04d}",
                    "name":            _pname.strip(),
                    "description":     _pdesc.strip(),
                    "department":      _pdept,
                    "category":        _pcat,
                    "priority":        _pprio,
                    "status":          "Planning",
                    "owner_username":  pm_username,
                    "project_manager": user_options.get(pm_username, pm_username),
                    "sponsor":         _pspon.strip(),
                    "start_date":      str(_pstart),
                    "planned_end_date":str(_pend),
                    "actual_end_date": "",
                    "budget_m":        _pbudget,
                    "spent_m":         0.0,
                    "pct_complete":    0,
                    "pct_budget_used": 0.0,
                    "rag_status":      "Green",
                    "risks":           0,
                    "open_issues":     0,
                    "milestones":      [],
                    "action_items":    [],
                    "stakeholders":    [],
                    "linked_modules":  [],
                    "last_updated":    str(today),
                    "notes":           "",
                    "created_by":      uname,
                    "created_at":      str(today),
                }
                all_projs.append(new_proj)
                _save_projects(all_projs)
                audit_log("PROJECT_CREATED", uname, f"{_pname}: PM={pm_username}")
                st.success(f"✅ Project created — notify {user_options.get(pm_username,pm_username)} to add milestones")
                st.rerun()
            else:
                st.error("Project name and PM required.")
    else:
        st.info("Project creation available to managers and above.")

# ══════════════════════════════════════════════════════════════════
# TAB 4 — Assign Work (line managers)
# ══════════════════════════════════════════════════════════════════
with tabs[4]:
    if is_pm or is_admin:
        my_proj_ids = [p["id"] for p in (projects if is_admin else my_projects)]
        if not my_proj_ids and not is_admin:
            st.info("You need to be assigned as PM to a project before you can assign work.")
        else:
            sel_proj_id = st.selectbox(
                "Select project",
                [p["id"]+" — "+p["name"][:40] for p in (projects if is_admin else my_projects)],
                key="assign_proj_sel"
            )
            if sel_proj_id:
                proj_id_sel = sel_proj_id.split(" — ")[0]
                proj_sel = next((p for p in projects if p["id"]==proj_id_sel), {})

                assign_tab = st.tabs(["➕ Add Milestone","➕ Add Action Item",
                                      "✏️ Update Progress","📊 Team Workload"])

                # Add Milestone
                with assign_tab[0]:
                    st.markdown(f"**Add milestone to: {proj_sel.get('name','')}**")
                    ms_name  = st.text_input("Milestone name *", key="ms_add_name")
                    ms_desc  = st.text_area("Description", key="ms_add_desc")
                    ms_owner_display = st.selectbox(
                        "Assign to *",
                        [f"{v} ({k})" for k,v in list(user_options.items())[:100]],
                        key="ms_add_owner"
                    )
                    ms_due   = st.date_input("Due date", key="ms_add_due")

                    if st.button("➕ Add milestone", key="ms_add_btn", type="primary"):
                        if ms_name.strip():
                            ms_owner_un = ms_owner_display.split("(")[-1].rstrip(")")
                            all_projs   = _load_projects()
                            for p2 in all_projs:
                                if p2["id"] == proj_id_sel:
                                    p2.setdefault("milestones", []).append({
                                        "id":             f"{proj_id_sel}_MS{len(p2.get('milestones',[]))+1:02d}",
                                        "name":           ms_name.strip(),
                                        "description":    ms_desc.strip(),
                                        "due_date":       str(ms_due),
                                        "status":         "Pending",
                                        "owner_username": ms_owner_un,
                                        "owner_name":     user_options.get(ms_owner_un,""),
                                        "completion_pct": 0,
                                        "completed_date": "",
                                        "bsc_scored":     False,
                                        "created_by":     uname,
                                        "created_at":     str(today),
                                    })
                                    break
                            _save_projects(all_projs)
                            audit_log("MILESTONE_ADDED", uname,
                                     f"{ms_name} → {ms_owner_un} in {proj_id_sel}")
                            st.success(f"✅ Milestone added — {user_options.get(ms_owner_un,ms_owner_un)} notified")
                            st.rerun()

                # Add Action Item
                with assign_tab[1]:
                    st.markdown(f"**Add action item to: {proj_sel.get('name','')}**")
                    a_desc  = st.text_area("Action description *", key="act_add_desc")
                    a_cat   = st.selectbox("Category",
                                          ["Risk","Issue","Decision","Follow-up","Approval","Review"],
                                          key="act_add_cat")
                    a_prio  = st.selectbox("Priority", ["High","Medium","Low"], key="act_add_prio")
                    a_owner_display = st.selectbox(
                        "Assign to *",
                        [f"{v} ({k})" for k,v in list(user_options.items())[:100]],
                        key="act_add_owner"
                    )
                    a_due   = st.date_input("Due date", key="act_add_due")

                    if st.button("➕ Add action item", key="act_add_btn", type="primary"):
                        if a_desc.strip():
                            a_owner_un = a_owner_display.split("(")[-1].rstrip(")")
                            all_projs  = _load_projects()
                            for p2 in all_projs:
                                if p2["id"] == proj_id_sel:
                                    p2.setdefault("action_items", []).append({
                                        "id":             f"{proj_id_sel}_ACT{len(p2.get('action_items',[]))+1:02d}",
                                        "description":    a_desc.strip(),
                                        "category":       a_cat,
                                        "priority":       a_prio,
                                        "owner_username": a_owner_un,
                                        "due_date":       str(a_due),
                                        "status":         "Open",
                                        "created_by":     uname,
                                        "created_date":   str(today),
                                        "closed_date":    "",
                                        "bsc_scored":     False,
                                        "notes":          "",
                                    })
                                    break
                            _save_projects(all_projs)
                            audit_log("ACTION_ADDED", uname,
                                     f"{a_desc[:40]} → {a_owner_un} in {proj_id_sel}")
                            st.success(f"✅ Action item assigned to {user_options.get(a_owner_un,a_owner_un)}")
                            st.rerun()

                # Update Progress
                with assign_tab[2]:
                    st.markdown(f"**Update project progress: {proj_sel.get('name','')}**")
                    new_pct   = st.slider("Overall % complete", 0, 100, proj_sel.get("pct_complete",0), key="upd_pct")
                    new_rag   = st.selectbox("RAG status", ["Green","Amber","Red"],
                                            index=["Green","Amber","Red"].index(proj_sel.get("rag_status","Green")),
                                            key="upd_rag")
                    new_spent = st.number_input("Spent to date (KES M)", 0.0, 10000.0,
                                               float(proj_sel.get("spent_m",0) or 0), key="upd_spent")
                    new_status= st.selectbox("Status",
                                            ["Planning","Active","On Hold","Completed","Cancelled"],
                                            index=["Planning","Active","On Hold","Completed","Cancelled"].index(
                                                proj_sel.get("status","Active") if proj_sel.get("status","Active")
                                                in ["Planning","Active","On Hold","Completed","Cancelled"] else "Active"),
                                            key="upd_status")
                    new_notes = st.text_area("Progress notes", key="upd_notes")

                    if st.button("💾 Update project", key="upd_proj_btn", type="primary"):
                        all_projs = _load_projects()
                        for p2 in all_projs:
                            if p2["id"] == proj_id_sel:
                                p2["pct_complete"]    = new_pct
                                p2["rag_status"]      = new_rag
                                p2["spent_m"]         = new_spent
                                p2["pct_budget_used"] = round(new_spent/max(float(p2.get("budget_m",1) or 1),0.001)*100, 1)
                                p2["status"]          = new_status
                                p2["last_updated"]    = str(today)
                                if new_notes: p2["notes"] = new_notes
                                if new_status == "Completed":
                                    p2["actual_end_date"] = str(today)
                                break
                        _save_projects(all_projs)
                        audit_log("PROJECT_UPDATED", uname,
                                 f"{proj_sel['name']}: {new_pct}% {new_rag}")
                        if new_status == "Completed":
                            _trigger_bsc_update(proj_sel.get("owner_username",""), "Project completed")
                        st.success("✅ Project updated")
                        st.rerun()

                # Team Workload
                with assign_tab[3]:
                    st.markdown("**Team workload for this project:**")
                    workload = defaultdict(lambda: {"milestones":0,"actions":0,"overdue":0})
                    for ms in proj_sel.get("milestones",[]):
                        ow = ms.get("owner_username","")
                        workload[ow]["milestones"] += 1
                        if ms.get("due_date","") < str(today) and ms.get("status") != "Complete":
                            workload[ow]["overdue"] += 1
                    for a in proj_sel.get("action_items",[]):
                        ow = a.get("owner_username","")
                        workload[ow]["actions"] += 1
                        if a.get("due_date","") < str(today) and a.get("status") == "Open":
                            workload[ow]["overdue"] += 1

                    wl_rows = [{"Team member": user_options.get(ow,ow)[:25],
                                "Milestones": v["milestones"],
                                "Action items": v["actions"],
                                "Overdue": v["overdue"]}
                               for ow, v in workload.items()]
                    if wl_rows:
                        st.dataframe(pd.DataFrame(wl_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Work assignment available to project managers.")

# ══════════════════════════════════════════════════════════════════
# TAB 5 — BSC Impact
# ══════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown("**How your project work scores on your BSC:**")
    st.info(
        "Every milestone you complete and every action item you close automatically "
        "updates your BSC scores for: **Projects On-Time Delivery (K036)**, "
        "**Milestones Completed (K037)**, **Project Budget Adherence (K038)**. "
        "These update in real time — no manual entry needed."
    )

    # Show my BSC operational scores
    scores_file = DATA / "feb_2026_staff_scores.json"
    if scores_file.exists():
        scores = a2z_db.load_json(scores_file)
        my_score = scores.get(uname, {})
        kpi_scores = my_score.get("kpi_scores", {})

        project_kpis = ["K036","K037","K038"]
        kpi_lib = json.loads((DATA/"kpi_library.json").read_text(encoding="utf-8"))
        kpi_names = {k["id"]:k["name"] for k in kpi_lib.get("kpis",[])}

        bsc_rows = []
        for kid in project_kpis:
            ks = kpi_scores.get(kid,{})
            if ks:
                bsc_rows.append({
                    "KPI": kpi_names.get(kid, kid),
                    "Target": ks.get("target","—"),
                    "Actual": ks.get("actual","—"),
                    "Achievement": f"{ks.get('achievement_pct',0):.0f}%",
                    "Score": ks.get("score","—"),
                    "Auto-sourced": "✅" if ks.get("auto_updated") else "Manual",
                })

        if bsc_rows:
            st.dataframe(pd.DataFrame(bsc_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No project KPIs in your BSC yet. Your line manager needs to include them in your scorecard.")

    # Trigger manual refresh
    if st.button("🔄 Refresh my BSC from modules", key="bsc_refresh_proj"):
        with st.spinner("Computing your scores from all modules..."):
            try:
                from utils.core import update_bsc_from_modules
                result = update_bsc_from_modules(uname)
                st.success(f"✅ BSC updated — final score: {result.get('final_score','—')}")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
