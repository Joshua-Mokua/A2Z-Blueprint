"""pages/61_projects.py — Project Management Module.
Portfolio view, RAG status, milestones, budget tracking. Links from Execute.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("projects")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_pm    = any(x in role for x in ("project","programme","pmo","director","head of","chief"))
dept     = ud.get("department", "")

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🗂️ Project Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Project portfolio · RAG status · Milestones · Budget · Links from Execute</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA / "projects.json"
    return json.loads(p.read_text()) if p.exists() else []

projects = _load()

# Filter by dept for non-admins (PMs see all their dept; Execs see all)
if not (is_admin or is_pm):
    projects = [p for p in projects if p.get("department") == dept or p.get("project_manager") == uname]

red_p    = [p for p in projects if p.get("rag_status")=="Red" and p.get("status") not in ("Completed","Cancelled")]
on_hold  = [p for p in projects if p.get("status")=="On Hold"]
over_bud = [p for p in projects if p.get("pct_budget_used",0) > cfg("project_budget_amber_pct",85)]

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Projects",      len(projects))
m2.metric("Active",              sum(1 for p in projects if p.get("status")=="Executing"))
m3.metric("🔴 Red RAG",          len(red_p),  delta_color="normal" if not red_p else "inverse")
m4.metric("On Hold",             len(on_hold))
m5.metric("Over Budget Alert",   len(over_bud),delta_color="normal" if not over_bud else "inverse")

if red_p:
    st.error(f"🔴 {len(red_p)} project(s) at Red RAG — escalation required: {[p['name'][:30] for p in red_p[:3]]}")

tabs = st.tabs(["📋 Portfolio","🔴 RAG Report","📅 Milestones","💰 Budget","➕ New Project"])

RAG_ICON = {"Green":"🟢","Amber":"🟡","Red":"🔴"}

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    frag  = f1.selectbox("RAG",["All","Green","Amber","Red"],key="prj_rag")
    fstat = f2.selectbox("Status",["All","Initiation","Planning","Executing","Monitoring","Completed","On Hold","Cancelled"],key="prj_stat")
    fdept = f3.selectbox("Department",["All"]+sorted(set(p.get("department","") for p in projects)),key="prj_dept")
    vis   = [p for p in projects
             if (frag=="All" or p.get("rag_status")==frag)
             and (fstat=="All" or p.get("status")==fstat)
             and (fdept=="All" or p.get("department")==fdept)]
    rows  = [{
        "RAG": RAG_ICON.get(p.get("rag_status",""),""),
        "ID": p["id"], "Project": p["name"][:35],
        "Status": p.get("status","")[:15],
        "PM": p.get("project_manager","")[:20],
        "Dept": p.get("department","")[:18],
        "Priority": p.get("priority",""),
        "% Done": p.get("pct_complete",0),
        "Budget (M)": p.get("budget_m",0),
        "Spent (M)": p.get("spent_m",0),
        "Budget Used%": p.get("pct_budget_used",0),
        "Issues": p.get("open_issues",0),
        "Initiative": p.get("initiative_id",""),
    } for p in sorted(vis, key=lambda x: {"Red":0,"Amber":1,"Green":2}.get(x.get("rag_status","Green"),3))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"{len(vis)} projects shown · Click a project ID in New Project tab to view detail")

with tabs[1]:
    rag_ct = Counter(p.get("rag_status","Unknown") for p in projects if p.get("status") not in ("Completed","Cancelled"))
    c1,c2,c3 = st.columns(3)
    c1.metric("🟢 Green", rag_ct.get("Green",0))
    c2.metric("🟡 Amber", rag_ct.get("Amber",0))
    c3.metric("🔴 Red",   rag_ct.get("Red",0))
    if red_p:
        st.markdown("**Red projects — action required:**")
        for p in red_p:
            with st.expander(f"🔴 {p['name'][:50]} — {p.get('status','')}"):
                st.markdown(f"**PM:** {p.get('project_manager','')}  |  **Sponsor:** {p.get('sponsor','')}")
                st.markdown(f"**Budget:** KES {p.get('budget_m',0):.1f}M  |  **Spent:** KES {p.get('spent_m',0):.1f}M ({p.get('pct_budget_used',0):.0f}%)")
                st.markdown(f"**Open issues:** {p.get('open_issues',0)}  |  **Open risks:** {p.get('risks',0)}")
                if p.get("initiative_id"):
                    st.caption(f"Linked initiative: {p['initiative_id']} — view in Execute module")

with tabs[2]:
    st.markdown("**Milestone tracker — all active projects:**")
    ms_rows = []
    for p in [x for x in projects if x.get("status") not in ("Completed","Cancelled")]:
        for ms in p.get("milestones",[]):
            ms_rows.append({
                "Project": p["name"][:30], "Milestone": ms.get("name",""),
                "Due": ms.get("due","")[:10], "Status": ms.get("status",""),
                "Overdue": "🔴" if ms.get("status")=="Overdue" else ""
            })
    if ms_rows:
        ms_df = pd.DataFrame(ms_rows)
        overdue_ms = ms_df[ms_df["Status"]=="Overdue"]
        if not overdue_ms.empty:
            st.warning(f"⚠️ {len(overdue_ms)} overdue milestones")
        st.dataframe(ms_df.sort_values("Due"), use_container_width=True, hide_index=True)

with tabs[3]:
    bud_rows = [{
        "Project": p["name"][:30], "Budget (M)": p.get("budget_m",0),
        "Spent (M)": round(p.get("spent_m",0),2),
        "Remaining (M)": round(p.get("budget_m",0)-p.get("spent_m",0),2),
        "% Used": p.get("pct_budget_used",0),
        "Status": ("🔴 Over" if p.get("pct_budget_used",0)>100
                   else "🟡 Warning" if p.get("pct_budget_used",0)>cfg("project_budget_amber_pct",85)
                   else "🟢 OK")
    } for p in sorted(projects, key=lambda x: -x.get("pct_budget_used",0))[:20]]
    st.dataframe(pd.DataFrame(bud_rows), use_container_width=True, hide_index=True)
    total_bud = sum(p.get("budget_m",0) for p in projects)
    total_spt = sum(p.get("spent_m",0) for p in projects)
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Budget",    f"KES {total_bud:.0f}M")
    c2.metric("Total Spent",     f"KES {total_spt:.0f}M")
    c3.metric("Remaining",       f"KES {total_bud-total_spt:.0f}M")

with tabs[4]:
    if is_pm or is_admin:
        from utils.core import get_org_config as _goc2
        _depts2 = [d["name"] for d in _goc2().get("departments",[]) if d.get("active",True)]
        r1,r2,r3 = st.columns(3)
        _pname = st.text_input("Project name *", key="prj_name")
        _pcat  = r1.selectbox("Category",
            ["Technology","Operations","Business","Compliance","People","Infrastructure"], key="prj_cat")
        _ppri  = r2.selectbox("Priority",["Critical","High","Medium","Low"], key="prj_pri")
        _pdept = r3.selectbox("Department", _depts2, key="prj_dept_new")
        _pbud  = st.number_input("Budget (KES M)", 0.1, 5000.0, 10.0, key="prj_bud")
        _pinit = st.text_input("Linked initiative ID (from Execute module)", key="prj_init")
        _pdesc = st.text_area("Description", height=60, key="prj_desc")
        if st.button("➕ Create project", key="prj_create", type="primary"):
            if _pname.strip():
                all_p = json.loads((DATA/"projects.json").read_text())
                all_p.append({
                    "id": f"PRJ{len(all_p)+1:04d}", "name": _pname.strip(),
                    "description": _pdesc.strip(), "initiative_id": _pinit.strip(),
                    "category": _pcat, "priority": _ppri, "status": "Initiation",
                    "project_manager": uname, "sponsor": "",
                    "department": _pdept, "start_date": str(today),
                    "planned_end_date": "", "actual_end_date": "",
                    "budget_m": _pbud, "spent_m": 0.0, "pct_complete": 0,
                    "pct_budget_used": 0.0, "rag_status": "Green",
                    "risks": 0, "open_issues": 0, "milestones": [],
                    "stakeholders": [], "last_updated": str(today), "notes": ""
                })
                (DATA/"projects.json").write_text(json.dumps(all_p, indent=2))
                audit_log("PROJECT_CREATED", uname, f"{_pname}: KES {_pbud}M")
                st.cache_data.clear(); st.success(f"✅ Project {_pname} created"); st.rerun()
            else: st.error("Project name required.")
    else:
        st.info("Project creation available to project managers and admin.")
