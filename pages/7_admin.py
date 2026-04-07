"""pages/7_admin.py — Administration: users, permissions, reporting lines, audit."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

role_low = str(ud.get("role","")).lower()
if not (ud.get("can_view_all") or "admin" in role_low):
    st.error("⛔ Access restricted to administrators.")
    st.stop()

staff_scores = st.session_state.get("staff_scores",  pd.DataFrame())
registry     = st.session_state.get("staff_registry", pd.DataFrame())
avail_roles  = sorted(staff_scores["Role"].unique().tolist()) if len(staff_scores) and "Role" in staff_scores.columns else []
avail_units  = sorted(staff_scores["Unit"].unique().tolist()) if len(staff_scores) and "Unit" in staff_scores.columns else []

st.markdown(
    "<div style='padding:14px 20px;background:#006B3F;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:16px;font-weight:500'>System Administration</div>"
    "<div style='color:#9FE1CB;font-size:11px;margin-top:2px'>"
    "Users · Permissions · Reporting lines · Audit · Upload format</div>"
    "</div>", unsafe_allow_html=True)

tabs = st.tabs([
    "👤 Users",
    "🔑 Permissions",
    "🗂️ Reporting lines",
    "🔄 Transfers & remaps",
    "🌳 Org tree",
    "📋 Audit log",
    "📤 Upload format",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — USERS
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("User management")
    mode = st.radio("Action", ["Create new user","Edit existing user"],
                    horizontal=True, key="admin_mode")

    if mode == "Edit existing user":
        existing = list(um.users.keys())
        if not existing:
            st.info("No users yet.")
        else:
            sel_user = st.selectbox("Select user", existing, key="edit_sel")
            eu = um.users.get(sel_user, {})
            with st.form("edit_user_form"):
                ec1, ec2 = st.columns(2)
                e_fname  = ec1.text_input("Full name",  value=eu.get("full_name",""))
                e_email  = ec2.text_input("Email",      value=eu.get("email",""))
                e_role   = ec1.selectbox("Role", avail_roles,
                    index=avail_roles.index(eu["role"]) if eu.get("role") in avail_roles else 0)
                e_unit   = ec2.selectbox("Unit", avail_units,
                    index=avail_units.index(eu["unit"]) if eu.get("unit") in avail_units else 0)
                e_sc     = ec1.text_input("Staff Code", value=str(eu.get("staff_code","")))
                e_active = ec2.checkbox("Active", value=eu.get("active", True))

                st.markdown("**Permissions**")
                pc1,pc2,pc3 = st.columns(3)
                e_all    = pc1.checkbox("Can view all staff", value=eu.get("can_view_all",False))
                e_exec   = pc2.checkbox("Can manage Execute",  value=eu.get("can_execute",False))
                e_admin  = pc3.checkbox("Admin privileges",    value=eu.get("is_admin",False))

                if st.form_submit_button("Save changes", type="primary"):
                    um.users[sel_user].update({
                        "full_name":    e_fname,
                        "email":        e_email,
                        "role":         e_role,
                        "unit":         e_unit,
                        "staff_code":   e_sc,
                        "active":       e_active,
                        "can_view_all": e_all,
                        "can_execute":  e_exec,
                        "is_admin":     e_admin,
                    })
                    um.save()
                    audit_log("USER_EDITED", uname, sel_user)
                    st.success(f"User '{sel_user}' updated.")
                    st.rerun()
    else:
        # Create new user
        with st.form("create_user_form"):
            nc1, nc2 = st.columns(2)
            n_user   = nc1.text_input("Username *")
            n_pass   = nc2.text_input("Password *", type="password")
            n_fname  = nc1.text_input("Full name *")
            n_email  = nc2.text_input("Email")
            n_role   = nc1.selectbox("Role", avail_roles) if avail_roles else nc1.text_input("Role")
            n_unit   = nc2.selectbox("Unit", avail_units) if avail_units else nc2.text_input("Unit")
            n_sc     = nc1.text_input("Staff Code")
            st.markdown("**Permissions**")
            pc1,pc2,pc3 = st.columns(3)
            n_all    = pc1.checkbox("Can view all staff")
            n_exec   = pc2.checkbox("Can manage Execute")
            n_admin  = pc3.checkbox("Admin privileges")

            if st.form_submit_button("Create user", type="primary"):
                if n_user and n_pass and n_fname:
                    if n_user in um.users:
                        st.error("Username already exists.")
                    else:
                        um.add_user(n_user, n_pass, n_fname, n_email, n_role,
                                    n_unit, n_sc, n_all, n_exec, n_admin)
                        audit_log("USER_CREATED", uname, n_user)
                        st.success(f"User '{n_user}' created.")
                        st.rerun()
                else:
                    st.error("Username, password and full name are required.")

    st.markdown("---")
    st.markdown("#### All users")
    if um.users:
        udf = pd.DataFrame([{
            "Username":   u,
            "Full name":  d.get("full_name",""),
            "Role":       d.get("role",""),
            "Unit":       d.get("unit",""),
            "Staff Code": d.get("staff_code",""),
            "Active":     "✅" if d.get("active",True) else "❌",
            "View all":   "✅" if d.get("can_view_all") else "—",
            "Admin":      "✅" if d.get("is_admin") else "—",
        } for u,d in um.users.items()])
        st.dataframe(udf, use_container_width=True, hide_index=True)

        with st.expander("⚠️ Delete user"):
            del_sel = st.selectbox("User to delete", list(um.users.keys()), key="del_sel")
            if st.button("Delete permanently", type="secondary", key="del_btn"):
                um.users.pop(del_sel, None)
                um.save()
                audit_log("USER_DELETED", uname, del_sel)
                st.success(f"User '{del_sel}' deleted.")
                st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 2 — PERMISSIONS
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Role-based access control")
    st.caption("Define what each system role can see and do. Changes take effect on next login.")

    PERM_MATRIX = {
        "Admin":               dict(view_all=True,  execute=True,  admin=True,  validate=True,  hr=True,   cascade=True),
        "Managing Director":   dict(view_all=True,  execute=True,  admin=False, validate=True,  hr=True,   cascade=True),
        "Director":            dict(view_all=True,  execute=True,  admin=False, validate=True,  hr=True,   cascade=True),
        "Regional Head":       dict(view_all=False, execute=False, admin=False, validate=True,  hr=False,  cascade=True),
        "Branch Manager":      dict(view_all=False, execute=False, admin=False, validate=True,  hr=False,  cascade=True),
        "Head Of":             dict(view_all=False, execute=True,  admin=False, validate=True,  hr=False,  cascade=True),
        "Manager":             dict(view_all=False, execute=False, admin=False, validate=True,  hr=False,  cascade=False),
        "HR":                  dict(view_all=True,  execute=False, admin=False, validate=False, hr=True,   cascade=False),
        "Staff":               dict(view_all=False, execute=False, admin=False, validate=False, hr=False,  cascade=False),
    }
    perm_df = pd.DataFrame([{"Role":k, **{cap.replace("_"," ").title():("✅" if v else "—")
                                           for cap,v in perms.items()}}
                              for k,perms in PERM_MATRIX.items()])
    st.dataframe(perm_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Override permissions for a specific user")
    if um.users:
        with st.form("perm_override_form"):
            pu_sel = st.selectbox("User", list(um.users.keys()), key="perm_sel")
            pu = um.users.get(pu_sel, {})
            pc1,pc2,pc3,pc4,pc5 = st.columns(5)
            p_all  = pc1.checkbox("View all",  value=pu.get("can_view_all",False))
            p_exec = pc2.checkbox("Execute",   value=pu.get("can_execute",False))
            p_adm  = pc3.checkbox("Admin",     value=pu.get("is_admin",False))
            p_val  = pc4.checkbox("Validate",  value=pu.get("can_validate",False))
            p_hr   = pc5.checkbox("HR access", value=pu.get("can_hr",False))
            if st.form_submit_button("Save permissions", type="primary"):
                um.users[pu_sel].update({
                    "can_view_all": p_all, "can_execute": p_exec,
                    "is_admin": p_adm, "can_validate": p_val, "can_hr": p_hr,
                })
                um.save()
                audit_log("PERM_CHANGED", uname, pu_sel)
                st.success("Permissions updated.")
                st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 3 — REPORTING LINES
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Reporting line management")
    st.caption(
        "Override the reporting lines from the uploaded data. "
        "Use this when an org structure changes, staff are promoted, or a position is vacated. "
        "Overrides take effect immediately — no re-upload needed.")

    if rlm is None:
        st.error("ReportingLineManager not available. Delete __pycache__ and restart.")
        st.stop()

    ov_summary = rlm.summary()
    oc1,oc2,oc3 = st.columns(3)
    oc1.metric("Active overrides",   ov_summary["total_overrides"])
    oc2.metric("Transfer overrides", ov_summary["total_transfers"])
    oc3.metric("Last change",        ov_summary["last_updated"][:10] if ov_summary["last_updated"]!='Never' else "Never")

    st.markdown("---")
    st.markdown("#### Remap a staff member's line manager")
    st.caption("Select any staff member and assign them a new reporting manager instantly.")

    if len(staff_scores) == 0:
        st.info("Upload BSC data first to see staff.")
    else:
        all_staff = sorted(staff_scores["Staff Name"].tolist())
        all_staff_opts = {
            f"{row['Staff Name']} ({row['Staff Code']}) — {row.get('Role','')} · {row.get('Unit','')}": str(row['Staff Code'])
            for _, row in staff_scores.iterrows()
        }

        with st.form("remap_form"):
            rl1, rl2 = st.columns(2)
            staff_sel_label = rl1.selectbox(
                "Staff member to remap",
                list(all_staff_opts.keys()), key="remap_staff")
            mgr_sel_label = rl2.selectbox(
                "New line manager",
                list(all_staff_opts.keys()), key="remap_mgr")
            remap_reason = st.text_input("Reason for change",
                placeholder="e.g. Promotion of previous manager, restructure, acting appointment")

            if st.form_submit_button("✅ Apply remap", type="primary"):
                staff_code = all_staff_opts[staff_sel_label]
                mgr_code   = all_staff_opts[mgr_sel_label]
                if staff_code == mgr_code:
                    st.error("Staff and manager cannot be the same person.")
                else:
                    rlm.remap(staff_code, mgr_code, uname, remap_reason)
                    audit_log("REPORTING_LINE_REMAP", uname,
                              f"{staff_sel_label.split('(')[0].strip()} → {mgr_sel_label.split('(')[0].strip()}")
                    st.success(
                        f"✅ {staff_sel_label.split('(')[0].strip()} now reports to "
                        f"{mgr_sel_label.split('(')[0].strip()}")
                    st.rerun()

    st.markdown("---")
    st.markdown("#### Current overrides")
    overrides = rlm.get_all_overrides()
    if not overrides:
        st.info("No overrides active. All reporting lines follow the uploaded data.")
    else:
        # Enrich with names
        code_to_name = {}
        if len(staff_scores) and "Staff Code" in staff_scores.columns:
            for _, r in staff_scores.iterrows():
                code_to_name[str(r["Staff Code"])] = r["Staff Name"]

        ov_rows = []
        for ov in overrides:
            sc   = ov.get("staff_code","")
            mc   = ov.get("manager_code","")
            ov_rows.append({
                "Staff Code":      sc,
                "Staff Name":      code_to_name.get(sc, sc),
                "New Manager":     code_to_name.get(mc, mc),
                "Unit override":   ov.get("unit","—") if "unit" in ov else "—",
                "Reason":          ov.get("reason",""),
                "Changed by":      ov.get("updated_by",""),
                "Changed at":      ov.get("updated_at","")[:16] if ov.get("updated_at") else "",
            })

        ov_df = pd.DataFrame(ov_rows)
        st.dataframe(ov_df, use_container_width=True, hide_index=True)

        # Clear a specific override
        st.markdown("**Remove an override** (reverts to uploaded data):")
        if ov_rows:
            clear_opts = {f"{r['Staff Name']} ({r['Staff Code']})": r['Staff Code']
                          for r in ov_rows}
            cc1, cc2 = st.columns([3,1])
            clear_sel = cc1.selectbox("Select override to remove", list(clear_opts.keys()), key="clear_ov")
            if cc2.button("Remove override", type="secondary", key="clear_btn"):
                rlm.clear_override(clear_opts[clear_sel], uname)
                audit_log("OVERRIDE_CLEARED", uname, clear_sel)
                st.success("Override removed. Staff reverts to uploaded reporting line.")
                st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 4 — TRANSFERS
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Staff transfers & unit reassignment")
    st.caption(
        "Use for branch-to-HO transfers, inter-department moves, "
        "or any structural change. The override updates the staff's unit, "
        "region AND manager simultaneously.")

    if len(staff_scores) == 0:
        st.info("Upload BSC data first.")
    else:
        all_staff_opts2 = {
            f"{row['Staff Name']} ({row['Staff Code']}) — {row.get('Role','')} · {row.get('Unit','')}": {
                "code": str(row['Staff Code']),
                "current_unit": row.get('Unit',''),
                "current_region": row.get('Region',''),
            }
            for _, row in staff_scores.iterrows()
        }

        mgr_opts = {
            f"{row['Staff Name']} ({row['Staff Code']}) — {row.get('Role','')} · {row.get('Unit','')}": str(row['Staff Code'])
            for _, row in staff_scores.iterrows()
            if any(k in str(row.get('Role','')).lower()
                   for k in ('manager','director','head','officer in charge','regional','chief'))
        }

        all_units_tr = sorted(set(
            staff_scores['Unit'].tolist() +
            ['Finance','Risk','Credit','Operations','ICT','Human Resources',
             'Compliance & Legal','Internal Audit','Strategy','Marketing','Procurement',
             'SME Banking','Corporate Banking','Retail Banking','Digital & Channels','Treasury']
        ))

        with st.form("transfer_full_form"):
            st.markdown("**Staff to transfer**")
            tr_staff_lbl = st.selectbox("Select staff", list(all_staff_opts2.keys()), key="tr_staff2")
            tr_info      = all_staff_opts2[tr_staff_lbl]

            st.markdown(
                f"<div style='padding:8px 12px;background:#E8F5EE;"
                f"border-left:3px solid #006B3F;font-size:12px;margin:6px 0'>"
                f"Current unit: <b>{tr_info['current_unit']}</b> | "
                f"Current region: <b>{tr_info['current_region']}</b></div>",
                unsafe_allow_html=True)

            st.markdown("**New posting**")
            tc1, tc2 = st.columns(2)
            new_unit   = tc1.selectbox("New unit / branch", all_units_tr, key="tr_unit")
            new_region = tc2.selectbox("New region", ["Central","North","South","Head Office"], key="tr_region")
            new_mgr_lbl= st.selectbox("New line manager", list(mgr_opts.keys()), key="tr_mgr")
            tr_reason  = st.text_area("Transfer reason / notes",
                placeholder="e.g. Branch to HO transfer — Credit Analyst role. Effective 1 May 2026.",
                height=60)

            tc3, tc4 = st.columns(2)
            also_hr    = tc3.checkbox("Also record in HR Transfers module", value=True)

            if st.form_submit_button("✅ Execute transfer", type="primary"):
                sc       = tr_info["code"]
                mgr_code = mgr_opts[new_mgr_lbl]
                rlm.transfer(sc, new_unit, new_region, mgr_code, uname, tr_reason)
                audit_log("TRANSFER_EXECUTED", uname,
                          f"{tr_staff_lbl.split('(')[0].strip()} → {new_unit}")

                if also_hr and hr_m:
                    try:
                        hr_m.record_transfer({
                            "staff_code": sc,
                            "staff_name": tr_staff_lbl.split('(')[0].strip(),
                            "from_unit":  tr_info["current_unit"],
                            "to_unit":    new_unit,
                            "from_region":tr_info["current_region"],
                            "to_region":  new_region,
                            "transfer_date": date.today(),
                            "reason":     tr_reason,
                            "initiated_by": uname,
                        })
                    except Exception:
                        pass

                st.success(
                    f"✅ Transfer executed: {tr_staff_lbl.split('(')[0].strip()} → "
                    f"{new_unit} reporting to {new_mgr_lbl.split('(')[0].strip()}")
                st.rerun()

    st.markdown("---")
    st.markdown("#### Bulk manager reassignment")
    st.caption("When a manager leaves or is promoted, reassign all their direct reports at once.")

    if len(staff_scores):
        with st.form("bulk_remap_form"):
            bk1, bk2 = st.columns(2)
            mgr_all_opts = {
                f"{row['Staff Name']} ({row['Staff Code']})": str(row['Staff Code'])
                for _, row in staff_scores.iterrows()
            }
            old_mgr_lbl = bk1.selectbox("Departing / changed manager", list(mgr_all_opts.keys()), key="bk_old")
            new_mgr_lbl2= bk2.selectbox("New manager for all their reports", list(mgr_all_opts.keys()), key="bk_new")
            bk_reason   = st.text_input("Reason", key="bk_reason",
                placeholder="e.g. Branch Manager transferred to Head Office — acting appointment")

            if st.form_submit_button("Bulk reassign", type="secondary"):
                old_code = mgr_all_opts[old_mgr_lbl]
                new_code = mgr_all_opts[new_mgr_lbl2]
                if old_code == new_code:
                    st.error("Old and new manager must be different.")
                else:
                    # Find direct reports from registry or staff_scores
                    reg = st.session_state.get("staff_registry", pd.DataFrame())
                    if hasattr(reg,"columns") and len(reg) and "Reports_To" in reg.columns:
                        direct = reg[reg["Reports_To"].astype(str) == old_code]["Staff Code"].tolist()
                    else:
                        direct = []
                    if not direct:
                        st.warning("No direct reports found in registry. Remap may need to be done individually.")
                    else:
                        rlm.bulk_remap_unit(old_code, new_code, [str(c) for c in direct], uname, bk_reason)
                        audit_log("BULK_REMAP", uname, f"{len(direct)} staff → {new_mgr_lbl2.split('(')[0].strip()}")
                        st.success(f"✅ {len(direct)} direct reports remapped to {new_mgr_lbl2.split('(')[0].strip()}")
                        st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 5 — ORG TREE
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Organisation chart")
    st.caption("Live org tree combining uploaded data and all active overrides.")

    reg = st.session_state.get("staff_registry", pd.DataFrame())
    if rlm and len(reg):
        applied = rlm.apply_to_registry(reg)
        tree    = rlm.get_org_tree(applied)

        # Build code → name map
        code_name = {}
        code_role = {}
        code_unit = {}
        if "Staff Code" in applied.columns:
            for _, r in applied.iterrows():
                sc = str(r["Staff Code"])
                code_name[sc] = r.get("Staff Name", sc)
                code_role[sc] = r.get("Role","")
                code_unit[sc] = r.get("Unit","")

        # Build Plotly org chart
        def flatten_tree(node_code, depth=0, parent_idx=None, rows=None, edges=None):
            if rows is None: rows=[]; edges=[]
            idx = len(rows)
            name = code_name.get(node_code, node_code)
            role = code_role.get(node_code,"")
            unit = code_unit.get(node_code,"")
            rows.append({'id':node_code,'name':name,'role':role,'unit':unit,'depth':depth,'idx':idx})
            if parent_idx is not None:
                edges.append((parent_idx, idx))
            for child in tree.get(node_code,[]):
                flatten_tree(child, depth+1, idx, rows, edges)
            return rows, edges

        # Find roots (no parent in tree values)
        all_children = set(c for children in tree.values() for c in children)
        roots = [sc for sc in tree.keys() if sc not in all_children]
        if not roots and tree:
            roots = [list(tree.keys())[0]]

        # Org view filters
        ot1, ot2 = st.columns(2)
        view_unit = ot1.selectbox("Filter by unit", ["All"] + sorted(set(code_unit.values())), key="org_unit")
        max_depth = ot2.slider("Max depth shown", 1, 6, 3, key="org_depth")

        all_rows, all_edges = [], []
        for root in roots:
            flatten_tree(root, 0, None, all_rows, all_edges)

        if all_rows:
            # Filter by unit
            if view_unit != "All":
                keep_ids = {r['id'] for r in all_rows if r['unit']==view_unit}
                all_rows = [r for r in all_rows if r['id'] in keep_ids]

            # Filter by depth
            all_rows = [r for r in all_rows if r['depth'] <= max_depth]

            # Summary stats
            total_mapped = len(all_rows)
            n_overrides  = len(rlm.get_all_overrides())

            os1, os2, os3 = st.columns(3)
            os1.metric("Staff in tree", total_mapped)
            os2.metric("Active overrides", n_overrides)
            os3.metric("Depth levels", max_depth)

            # Render as collapsible tree rows
            DEPTH_COLORS = ['#006B3F','#F5A623','#185FA5','#7F8C8D','#9B59B6','#E24B4A']
            for row in all_rows[:100]:  # cap at 100 for performance
                indent  = '&nbsp;' * (row['depth'] * 5)
                clr     = DEPTH_COLORS[min(row['depth'], 5)]
                border  = 2 + row['depth']
                is_mgr  = row['id'] in tree
                icon    = '👔' if row['depth']==0 else ('📋' if is_mgr else '👤')
                has_ov  = row['id'] in rlm.overrides
                ov_badge= "<span style='background:#F5A623;color:white;padding:1px 5px;border-radius:8px;font-size:9px;margin-left:4px'>override</span>" if has_ov else ''

                st.markdown(
                    f"<div style='padding:5px 10px;background:var(--color-background-secondary);"
                    f"border-left:{border}px solid {clr};"
                    f"margin:1px 0;border-radius:0 3px 3px 0;font-size:11px'>"
                    f"{indent}{icon} <b>{row['name']}</b> "
                    f"<span style='color:#888;font-size:10px'>{row['role']}</span> "
                    f"<span style='color:#aaa;font-size:10px'>· {row['unit']}</span>"
                    f"{ov_badge}</div>",
                    unsafe_allow_html=True)

            if len(all_rows) > 100:
                st.caption(f"Showing 100 of {len(all_rows)} staff. Use the unit filter to narrow down.")
        else:
            st.info("No org tree data available. Upload BSC data with Staff Register sheet.")
    elif len(staff_scores):
        # Build from staff_scores directly
        st.info("Load the Staff Register (upload BSC Excel with Staff Register sheet) for the full org tree.")
        # Show a simple role hierarchy
        role_counts = staff_scores.groupby(['Role','Unit'])['Staff Name'].count().reset_index()
        role_counts.columns = ['Role','Unit','Count']
        fig = px.treemap(role_counts, path=['Unit','Role'], values='Count',
                          title='Staff distribution by unit and role')
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Upload BSC data to view the organisation chart.")

# ════════════════════════════════════════════════════════════════
# TAB 6 — AUDIT LOG
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Audit trail")
    log_path = DATA_DIR / "audit.log"
    if log_path.exists():
        lines = log_path.read_text().strip().split("\n")[-200:]  # last 200 lines
        lines.reverse()  # newest first
        audit_rows = []
        for line in lines:
            parts = line.split("|")
            if len(parts) >= 3:
                audit_rows.append({
                    "Timestamp": parts[0].strip(),
                    "User":      parts[1].strip(),
                    "Action":    parts[2].strip(),
                    "Detail":    parts[3].strip() if len(parts)>3 else "",
                })
        if audit_rows:
            af1, af2 = st.columns(2)
            filter_user   = af1.selectbox("Filter by user", ["All"] +
                list(dict.fromkeys(r["User"] for r in audit_rows)), key="aud_u")
            filter_action = af2.selectbox("Filter by action", ["All"] +
                list(dict.fromkeys(r["Action"] for r in audit_rows)), key="aud_a")

            disp = audit_rows
            if filter_user   != "All": disp = [r for r in disp if r["User"]==filter_user]
            if filter_action != "All": disp = [r for r in disp if r["Action"]==filter_action]

            st.dataframe(pd.DataFrame(disp), use_container_width=True, hide_index=True)
        else:
            st.info("No audit entries yet.")
    else:
        st.info("Audit log will appear here once actions are performed.")

# ════════════════════════════════════════════════════════════════
# TAB 7 — UPLOAD FORMAT
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Upload format guide")
    st.caption("The system accepts two upload modes: Full BSC (targets + actuals) and Actuals-only (monthly update).")

    mode_tabs = st.tabs(["📊 Full BSC upload","📥 Actuals-only upload","📋 Column reference","✅ Validation rules"])

    with mode_tabs[0]:
        st.markdown("#### Full BSC upload — KPI Data sheet")
        st.markdown(
            "Use this when setting up the system or updating targets. "
            "The file must have two sheets: **KPI Data** and **Staff Register**.")

        full_cols = pd.DataFrame([
            {"Column":"Unit","Required":"✅","Type":"Text","Example":"Nairobi CBD Branch","Notes":"Branch name or HO department"},
            {"Column":"Category","Required":"✅","Type":"Text","Example":"Branch","Notes":"Branch or Head Office"},
            {"Column":"Staff Code","Required":"✅","Type":"Number","Example":"300130","Notes":"Unique employee ID. No apostrophe prefix."},
            {"Column":"Staff Name","Required":"✅","Type":"Text","Example":"Grace K. Kamau","Notes":"Full name as registered"},
            {"Column":"Role","Required":"✅","Type":"Text","Example":"Teller","Notes":"Must match role map exactly"},
            {"Column":"Role Function","Required":"✅","Type":"Text","Example":"Support","Notes":"Business / Support / Executive"},
            {"Column":"Pillar","Required":"✅","Type":"Text","Example":"Financial","Notes":"Financial | Customer Focus | Operational Excellence"},
            {"Column":"KPI","Required":"✅","Type":"Text","Example":"Deposit Growth","Notes":"KPI name — must be consistent per role"},
            {"Column":"Annual Target","Required":"✅","Type":"Number","Example":"130000000","Notes":"Full year target in KES (no commas)"},
            {"Column":"Annual Actual","Required":"✅","Type":"Number","Example":"45000000","Notes":"YTD actual to date"},
            {"Column":"Weight","Required":"✅","Type":"Decimal","Example":"0.08","Notes":"Decimal. All weights per staff must sum to exactly 1.00"},
            {"Column":"Jan-26 Actual","Required":"✅","Type":"Number","Example":"15000000","Notes":"Month name + hyphen + 2-digit year + ' Actual'"},
            {"Column":"Feb-26 Actual","Required":"⬜","Type":"Number","Example":"14500000","Notes":"Add new month columns as year progresses"},
            {"Column":"Mar-26 Actual","Required":"⬜","Type":"Number","Example":"15500000","Notes":"System auto-detects all month columns"},
        ])
        st.dataframe(full_cols, use_container_width=True, hide_index=True)

        st.markdown("#### Staff Register sheet")
        reg_cols = pd.DataFrame([
            {"Column":"Staff Code","Required":"✅","Example":"300130"},
            {"Column":"Staff Name","Required":"✅","Example":"Grace K. Kamau"},
            {"Column":"Email","Required":"⬜","Example":"g.kamau@ecobank.co.ke"},
            {"Column":"Phone","Required":"⬜","Example":"0712345678"},
            {"Column":"Role","Required":"✅","Example":"Teller"},
            {"Column":"Role Function","Required":"✅","Example":"Support"},
            {"Column":"Unit","Required":"✅","Example":"Nairobi CBD Branch"},
            {"Column":"Category","Required":"✅","Example":"Branch"},
            {"Column":"Staff Status","Required":"✅","Example":"Existing | New | Probation"},
            {"Column":"Hire Date","Required":"✅","Example":"01/01/2022"},
            {"Column":"Reports To Code","Required":"✅","Example":"300105","Notes":"Staff Code of direct line manager"},
            {"Column":"Region","Required":"⬜","Example":"Central","Notes":"Auto-derived from unit if blank"},
        ])
        st.dataframe(reg_cols, use_container_width=True, hide_index=True)

    with mode_tabs[1]:
        st.markdown("#### Actuals-only upload — monthly update format")
        st.markdown(
            "Once targets are set (via full upload or cascade), use this lighter format "
            "to upload monthly actuals only. The system merges actuals into the existing targets.")

        st.markdown(
            "<div style='padding:12px 16px;background:#E8F5EE;"
            "border-left:4px solid #006B3F;border-radius:0 6px 6px 0;margin:8px 0'>"
            "<b>How it works:</b> Targets come from the cascade allocation or the last full upload. "
            "Each month you upload a file with only Staff Code, KPI, and the month's actual. "
            "The system matches on Staff Code + KPI and updates that month's column."
            "</div>", unsafe_allow_html=True)

        actuals_cols = pd.DataFrame([
            {"Column":"Staff Code","Required":"✅","Example":"300130","Notes":"Must match exactly"},
            {"Column":"KPI","Required":"✅","Example":"Deposit Growth","Notes":"Must match exactly"},
            {"Column":"Apr-26 Actual","Required":"✅","Example":"18500000","Notes":"The column header drives which month is updated"},
            {"Column":"Staff Name","Required":"⬜","Example":"Grace K. Kamau","Notes":"Optional — used for validation only"},
            {"Column":"Unit","Required":"⬜","Example":"Nairobi CBD Branch","Notes":"Optional — used for validation only"},
        ])
        st.dataframe(actuals_cols, use_container_width=True, hide_index=True)

        st.markdown("#### Sample actuals file (copy this format)")
        sample_actuals = pd.DataFrame({
            "Staff Code": [300130,300131,300132],
            "Staff Name":  ["Grace K. Kamau","John M. Otieno","Mary A. Wanjiku"],
            "KPI":         ["Deposit Growth","Deposit Growth","New Customer Acquisition"],
            "Apr-26 Actual":[16500000, 19200000, 38],
            "Unit":        ["Nairobi CBD Branch","Westlands Branch","Kisumu Branch"],
        })
        st.dataframe(sample_actuals, use_container_width=True, hide_index=True)

        st.markdown(
            "<div style='padding:10px 14px;background:#FFFBF0;"
            "border-left:3px solid #F5A623;font-size:12px;margin-top:8px'>"
            "⚠️ <b>For KPIs auto-calculated by the system</b> (Diligence Score, Initiative Score, "
            "SLA Adherence Score, Branch Optimization Score, CX Score, Diligence Score) — "
            "do NOT include these in the actuals upload. The system computes them automatically "
            "from Execute, Daily Log, and SLA modules. Including them will overwrite the system calculation."
            "</div>", unsafe_allow_html=True)

        st.markdown("#### Auto-calculated KPIs — source modules")
        auto_kpis = pd.DataFrame([
            {"KPI":"Diligence Score","Source module":"Execute → milestones + People → discipline/PIP","Frequency":"Real-time"},
            {"KPI":"Initiative Score","Source module":"Execute → gate progression","Frequency":"Real-time"},
            {"KPI":"SLA Adherence Score","Source module":"SLA Tracker (coming)","Frequency":"Daily"},
            {"KPI":"CX Score","Source module":"Daily Branch Log validation + SLA","Frequency":"Daily"},
            {"KPI":"Branch Optimization Score","Source module":"Branch Optimization Engine (coming)","Frequency":"Daily"},
            {"KPI":"Campaign Conversion Rate","Source module":"Campaigns module (coming)","Frequency":"Per campaign"},
            {"KPI":"Digital Acquiring","Source module":"Daily Branch Log","Frequency":"Daily"},
            {"KPI":"Digital Transaction Migration","Source module":"Daily Branch Log","Frequency":"Daily"},
            {"KPI":"Transactions","Source module":"Daily Branch Log","Frequency":"Daily"},
        ])
        st.dataframe(auto_kpis, use_container_width=True, hide_index=True)

    with mode_tabs[2]:
        st.markdown("#### Full column reference — all supported KPIs")
        st.caption("These are all KPIs currently mapped in the system with their BSC pillar and role mapping.")

        kpi_ref = pd.DataFrame([
            {"KPI":"Deposit Growth","Pillar":"Financial","Roles":"All business roles","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"Loan Book Growth","Pillar":"Financial","Roles":"Business roles","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"Loans Disbursement","Pillar":"Financial","Roles":"RM, DSO, BCM","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"Fees and Commission","Pillar":"Financial","Roles":"All business","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"DFS Revenue","Pillar":"Financial","Roles":"Business + Digital","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"Digital Acquiring","Pillar":"Financial/Customer","Roles":"Branch staff","Type":"Count","Unit":"Accounts"},
            {"KPI":"Transactions","Pillar":"Financial","Roles":"Tellers, CSO","Type":"Count","Unit":"Count"},
            {"KPI":"Trade Finance","Pillar":"Financial","Roles":"Corporate, SME","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"Treasury","Pillar":"Financial","Roles":"Corporate, Treasury","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"PBT","Pillar":"Financial","Roles":"Managers/Directors","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"Bancassurance","Pillar":"Financial","Roles":"Branch, DSO","Type":"Amount (KES)","Unit":"KES 000"},
            {"KPI":"NPL Ratio","Pillar":"Financial","Roles":"Credit, Business","Type":"Ratio","Unit":"Decimal (0.05 = 5%)"},
            {"KPI":"PAR","Pillar":"Financial","Roles":"Credit, BCM","Type":"Ratio","Unit":"Decimal"},
            {"KPI":"CIR","Pillar":"Financial","Roles":"Directors, CFO","Type":"Ratio","Unit":"Decimal (0.65 = 65%)"},
            {"KPI":"ROE","Pillar":"Financial","Roles":"MD, Directors","Type":"Ratio","Unit":"Decimal"},
            {"KPI":"New Customer Acquisition","Pillar":"Customer Focus","Roles":"All business","Type":"Count","Unit":"Customers"},
            {"KPI":"Dormancy Reactivation","Pillar":"Customer Focus","Roles":"Branch, DSO","Type":"Count","Unit":"Accounts"},
            {"KPI":"CX Score","Pillar":"Customer Focus","Roles":"All staff","Type":"Score","Unit":"0.00–1.00"},
            {"KPI":"SLA Adherence Score","Pillar":"Customer Focus","Roles":"All staff","Type":"Score","Unit":"0.00–1.00 (auto)"},
            {"KPI":"Credit TAT Score","Pillar":"Customer Focus","Roles":"Credit staff","Type":"Score","Unit":"0.00–1.00"},
            {"KPI":"Diligence Score","Pillar":"Operational Excellence","Roles":"All staff","Type":"Score","Unit":"0–100 (auto)"},
            {"KPI":"Initiative Score","Pillar":"Operational Excellence","Roles":"All staff","Type":"Score","Unit":"0.00–1.00 (auto)"},
            {"KPI":"Compliance","Pillar":"Operational Excellence","Roles":"All staff","Type":"Score","Unit":"0.00–1.00"},
            {"KPI":"Audit Closure","Pillar":"Operational Excellence","Roles":"All staff","Type":"Score","Unit":"0.00–1.00"},
            {"KPI":"Timely Reconciliations","Pillar":"Operational Excellence","Roles":"Ops, Tellers","Type":"Score","Unit":"0.00–1.00"},
            {"KPI":"Branch Optimization Score","Pillar":"Operational Excellence","Roles":"BOM, BM","Type":"Score","Unit":"0.00–1.00 (auto)"},
            {"KPI":"Campaign Conversion Rate","Pillar":"Operational Excellence","Roles":"Marketing, DSO","Type":"Score","Unit":"0.00–1.00 (auto)"},
            {"KPI":"Recovery Rate","Pillar":"Financial","Roles":"DRU","Type":"Score","Unit":"0.00–1.00"},
            {"KPI":"Loan Recovery Amount","Pillar":"Financial","Roles":"DRU, Recovery Officer","Type":"Amount (KES)","Unit":"KES 000"},
        ])
        st.dataframe(kpi_ref, use_container_width=True, hide_index=True)

    with mode_tabs[3]:
        st.markdown("#### Validation rules — what the system checks on upload")
        rules = [
            ("✅","Weights sum to 1.00","Per staff member, all KPI weights must sum to exactly 1.00 (±0.005 tolerance)"),
            ("✅","No duplicate KPI rows","Each staff + KPI combination must appear only once"),
            ("✅","Valid pillar names","Pillar must be exactly: Financial, Customer Focus, Operational Excellence"),
            ("✅","Staff Code format","Staff codes must be numeric, no leading apostrophe, no spaces"),
            ("✅","Month column format","Month columns must be: Mon-YY Actual (e.g. Apr-26 Actual)"),
            ("✅","Target not zero","Annual Target must be > 0 for all rows"),
            ("✅","Weight > 0","Each KPI weight must be > 0"),
            ("✅","Role Function","Must be: Business, Support, or Executive"),
            ("⚠️","Auto-KPIs excluded","Diligence Score, SLA Adherence, etc. should not be in actuals upload"),
            ("⚠️","Reports To Code","Must match an existing Staff Code in the same file or overridden in Admin"),
            ("⚠️","Category","Must be: Branch or Head Office"),
        ]
        rules_df = pd.DataFrame(rules, columns=["Status","Rule","Detail"])
        st.dataframe(rules_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### Live validation check")
        st.caption("Upload your file here to check for errors before the main upload.")

        check_file = st.file_uploader("Upload file to validate", type=["xlsx","xls"], key="val_upload")
        if check_file:
            raw_chk = check_file.getvalue()
            try:
                chk_df = pd.read_excel(io.BytesIO(raw_chk), sheet_name='KPI Data', header=1)
                errors = []
                warnings = []

                # Weight check
                chk_df['Weight'] = pd.to_numeric(chk_df['Weight'], errors='coerce').fillna(0)
                chk_df['Weight'] = chk_df['Weight'].apply(lambda x: x/100 if x > 1 else x)
                wt_sums = chk_df.groupby('Staff Code')['Weight'].sum()
                bad_wt  = wt_sums[(wt_sums - 1.0).abs() > 0.005]
                if len(bad_wt):
                    errors.append(f"❌ {len(bad_wt)} staff have weights not summing to 1.00: {bad_wt.index.tolist()[:5]}")
                else:
                    st.success(f"✅ Weights: all {len(wt_sums)} staff sum to 1.00")

                # Pillar check
                valid_pillars = {'Financial','Customer Focus','Operational Excellence'}
                bad_pillars = chk_df[~chk_df['Pillar'].isin(valid_pillars)]['Pillar'].unique()
                if len(bad_pillars):
                    errors.append(f"❌ Invalid pillars: {bad_pillars.tolist()}")
                else:
                    st.success("✅ Pillars: all valid")

                # Duplicates
                dups = chk_df.duplicated(subset=['Staff Code','KPI'])
                if dups.sum():
                    errors.append(f"❌ {dups.sum()} duplicate Staff Code + KPI rows")
                else:
                    st.success(f"✅ No duplicates: {len(chk_df)} unique rows")

                # Zero targets
                zero_tgt = (pd.to_numeric(chk_df['Annual Target'], errors='coerce') == 0).sum()
                if zero_tgt:
                    warnings.append(f"⚠️ {zero_tgt} rows with zero Annual Target")

                st.metric("Total rows",    len(chk_df))
                st.metric("Unique staff",  chk_df['Staff Code'].nunique())
                st.metric("Unique KPIs",   chk_df['KPI'].nunique())
                st.metric("Errors",        len(errors),   delta=f"-{len(errors)}" if errors else "0", delta_color="inverse")
                st.metric("Warnings",      len(warnings), delta=f"-{len(warnings)}" if warnings else "0", delta_color="inverse")

                for e in errors:
                    st.error(e)
                for w in warnings:
                    st.warning(w)
                if not errors and not warnings:
                    st.success("✅ File passed all validation checks. Ready to upload via the sidebar.")
            except Exception as ex:
                st.error(f"Could not read file: {ex}")
