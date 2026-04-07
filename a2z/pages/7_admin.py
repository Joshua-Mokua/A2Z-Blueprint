"""pages/7_admin.py — Administration: users, permissions, audit, email, Execute roles."""
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state

um, ud, uname, em, ri_pm, prod_m, pm, vm_obj, lm, ssm = load_shared_state()

role_low = str(ud.get("role","")).lower()
if not (ud.get("can_view_all") or "admin" in role_low):
    st.error("⛔ Access restricted to administrators.")
    st.stop()

staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
avail_roles  = sorted(staff_scores["Role"].unique().tolist()) if len(staff_scores) > 0 and "Role" in staff_scores.columns else []
avail_units  = sorted(staff_scores["Unit"].unique().tolist()) if len(staff_scores) > 0 and "Unit" in staff_scores.columns else []
avail_regions = ["South", "Central", "North", "Head Office"]

t1, t2, t3, t4 = st.tabs(["👤 Create / edit user", "🔑 Permissions", "📋 Audit log", "📧 Email settings"])

# ════════════════════════════════════════════════════════════════
# TAB 1 — CREATE / EDIT USER (fully re-engineered with Execute roles)
# ════════════════════════════════════════════════════════════════
with t1:
    st.subheader("Create or edit user")

    mode = st.radio("Action", ["Create new user", "Edit existing user"],
                    horizontal=True, key="admin_mode")

    # ── Edit existing ─────────────────────────────────────────────
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
                e_active = st.checkbox("Active", value=eu.get("active", True))

                st.markdown("---")
                st.markdown("**Execute module roles**")
                xc1, xc2 = st.columns(2)
                e_is_sponsor = xc1.checkbox("Sponsor (Director / ExCo)",
                    value=eu.get("is_sponsor", False))
                e_is_lead    = xc2.checkbox("Workstream lead",
                    value=eu.get("is_workstream_lead", False))
                e_is_io      = xc1.checkbox("Can be Initiative Owner",
                    value=eu.get("can_be_io", True))
                e_is_finance = xc2.checkbox("Finance approver",
                    value=eu.get("is_finance_approver", False))
                e_ws_scope   = st.multiselect("Workstream scope (leads/sponsors)",
                    list(em.workstreams.keys()) if em else [],
                    default=eu.get("workstream_scope", []))

                if st.form_submit_button("Save changes", type="primary"):
                    um.users[sel_user].update({
                        "full_name": e_fname, "email": e_email,
                        "role": e_role, "unit": e_unit, "active": e_active,
                        "is_sponsor": e_is_sponsor,
                        "is_workstream_lead": e_is_lead,
                        "can_be_io": e_is_io,
                        "is_finance_approver": e_is_finance,
                        "workstream_scope": e_ws_scope,
                    })
                    um._save()
                    audit_log("USER_EDITED", uname, sel_user)
                    st.success(f"User {sel_user} updated.")
                    st.rerun()

    # ── Create new user ───────────────────────────────────────────
    else:
        st.markdown("#### Step 1 — Staff identity")
        with st.form("create_user_form"):
            cc1, cc2 = st.columns(2)
            with cc1:
                staff_code_raw = st.text_input("Staff code *",
                    help="Type the staff code — name, role, unit, email auto-fill from the register")
                email_in  = st.text_input("Email *")
                role_in   = st.selectbox("Role *", [""] + avail_roles)
            with cc2:
                fname_in  = st.text_input("Full name *")
                unit_in   = st.selectbox("Unit *", [""] + avail_units)
                cat_in    = st.selectbox("Category",
                    ["Branch","Head Office","Executive","Other"])

            st.markdown("#### Step 2 — Execute module roles")
            st.caption("Assign what this user can do in the strategy execution module.")
            xr1, xr2, xr3 = st.columns(3)
            is_sponsor    = xr1.checkbox("Sponsor (Director / ExCo)",
                help="Sponsors approve gate submissions and receive escalation alerts")
            is_lead       = xr2.checkbox("Workstream lead",
                help="Leads review milestones and approve G1→G2 transitions")
            is_io         = xr3.checkbox("Can be Initiative Owner",
                value=True,
                help="All staff can own initiatives by default — uncheck to restrict")
            is_finance    = xr1.checkbox("Finance approver",
                help="Finance team validates business cases at G2 and impact at G4")
            is_ms_owner   = xr2.checkbox("Can be Milestone Owner",
                value=True,
                help="Can be assigned milestones within initiatives")
            ws_scope      = st.multiselect(
                "Workstream scope (for leads and sponsors)",
                list(em.workstreams.keys()) if em else [],
                help="Which workstreams this user leads or sponsors")

            st.markdown("#### Step 3 — System access")
            pc1, pc2 = st.columns(2)
            can_view_all = pc1.checkbox("Can view all staff data",
                help="Admin-level data access — all branches and departments")
            send_email_cb = pc2.checkbox("Send welcome email with temp password",
                value=True)

            st.markdown("#### Step 4 — Permissions")
            st.caption("Which modules this user can access.")
            pm1,pm2,pm3,pm4 = st.columns(4)
            perm_perform  = pm1.checkbox("Perform",     value=True)
            perm_execute  = pm2.checkbox("Execute",     value=True)
            perm_pipeline = pm3.checkbox("Pipeline",    value=True)
            perm_products = pm4.checkbox("Products",    value=True)
            perm_integrate= pm1.checkbox("Integrate",   value=False)
            perm_admin    = pm2.checkbox("Admin panel",  value=False)

            submitted = st.form_submit_button("✅ Create user", type="primary")

        if submitted:
            sc = clean_code(staff_code_raw)
            if not sc or not fname_in or not email_in or not role_in or not unit_in:
                st.error("Staff code, name, email, role and unit are all required.")
            elif sc in um.users:
                st.error(f"User {sc} already exists.")
            else:
                import secrets as _sec
                temp_pw = (
                    _sec.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") +
                    _sec.choice("abcdefghjkmnpqrstuvwxyz") +
                    _sec.choice("0123456789") +
                    _sec.choice("!@#$%") +
                    "".join(_sec.choice(
                        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz0123456789"
                    ) for _ in range(6))
                )
                import hashlib as _hl
                um.users[sc] = {
                    "full_name":           fname_in,
                    "email":               email_in,
                    "role":                role_in,
                    "unit":                unit_in,
                    "category":            cat_in,
                    "staff_code":          sc,
                    "password_hash":       _hl.sha256(temp_pw.encode()).hexdigest(),
                    "must_change_password":True,
                    "active":              True,
                    "can_view_all":        can_view_all,
                    # Execute roles
                    "is_sponsor":          is_sponsor,
                    "is_workstream_lead":  is_lead,
                    "can_be_io":           is_io,
                    "is_finance_approver": is_finance,
                    "can_be_ms_owner":     is_ms_owner,
                    "workstream_scope":    ws_scope,
                    # Module permissions
                    "permissions": {
                        "perform":   perm_perform,
                        "execute":   perm_execute,
                        "pipeline":  perm_pipeline,
                        "products":  perm_products,
                        "integrate": perm_integrate,
                        "admin":     perm_admin,
                    },
                    "created_by":   uname,
                    "created_at":   datetime.now().isoformat(),
                }
                um._save()
                audit_log("USER_CREATED", uname, f"{sc}:{fname_in}:{role_in}")

                if send_email_cb:
                    ok_e, msg_e = send_welcome_email(email_in, fname_in, sc, temp_pw)
                    if ok_e:
                        st.success(f"User {sc} created. Welcome email sent to {email_in}.")
                    else:
                        st.warning(f"User created but email failed: {msg_e}")
                        st.info(f"Temporary password (share securely): `{temp_pw}`")
                else:
                    st.success(f"User {sc} created.")
                    st.info(f"Temporary password (share securely): `{temp_pw}`")
                st.rerun()

    # ── Execute roles summary table ───────────────────────────────
    st.markdown("---")
    st.markdown("#### Execute roles across all users")
    role_rows = []
    for uid, u in um.users.items():
        if not u.get("active", True): continue
        roles_assigned = []
        if u.get("is_sponsor"):          roles_assigned.append("Sponsor")
        if u.get("is_workstream_lead"):  roles_assigned.append("Workstream Lead")
        if u.get("is_finance_approver"): roles_assigned.append("Finance Approver")
        if u.get("can_be_io", True):     roles_assigned.append("Initiative Owner")
        if u.get("can_be_ms_owner", True): roles_assigned.append("Milestone Owner")
        role_rows.append({
            "Username": uid,
            "Name":     u.get("full_name",""),
            "Role":     u.get("role",""),
            "Unit":     u.get("unit",""),
            "Execute roles": " · ".join(roles_assigned),
            "WS scope": ", ".join(u.get("workstream_scope",[])),
        })
    if role_rows:
        st.dataframe(pd.DataFrame(role_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No users yet.")

# ════════════════════════════════════════════════════════════════
# TAB 2 — PERMISSIONS
# ════════════════════════════════════════════════════════════════
with t2:
    st.subheader("Edit permissions")
    users_list = list(um.users.keys())
    if not users_list:
        st.info("No users to configure.")
    else:
        sel = st.selectbox("Select user", users_list, key="perm_sel")
        u   = um.users[sel]
        st.markdown(f"**{u.get('full_name',sel)}** — {u.get('role','')} · {u.get('unit','')}")
        with st.form("perm_form"):
            st.markdown("**Module access**")
            perms = u.get("permissions", {})
            pc1,pc2,pc3 = st.columns(3)
            p_perform  = pc1.checkbox("Perform",   value=perms.get("perform", True))
            p_execute  = pc2.checkbox("Execute",   value=perms.get("execute", True))
            p_pipeline = pc3.checkbox("Pipeline",  value=perms.get("pipeline", True))
            p_products = pc1.checkbox("Products",  value=perms.get("products", True))
            p_integrate= pc2.checkbox("Integrate", value=perms.get("integrate", False))
            p_admin    = pc3.checkbox("Admin",     value=perms.get("admin", False))
            p_view_all = st.checkbox("View all staff data", value=u.get("can_view_all", False))

            st.markdown("**Execute module roles**")
            xc1,xc2,xc3 = st.columns(3)
            p_sponsor  = xc1.checkbox("Sponsor",           value=u.get("is_sponsor", False))
            p_lead     = xc2.checkbox("Workstream lead",   value=u.get("is_workstream_lead", False))
            p_finance  = xc3.checkbox("Finance approver",  value=u.get("is_finance_approver", False))
            p_io       = xc1.checkbox("Initiative owner",  value=u.get("can_be_io", True))
            p_ms       = xc2.checkbox("Milestone owner",   value=u.get("can_be_ms_owner", True))
            p_ws_scope = st.multiselect("Workstream scope",
                list(em.workstreams.keys()) if em else [],
                default=u.get("workstream_scope", []))

            if st.form_submit_button("Save permissions", type="primary"):
                um.users[sel].update({
                    "can_view_all":        p_view_all,
                    "is_sponsor":          p_sponsor,
                    "is_workstream_lead":  p_lead,
                    "is_finance_approver": p_finance,
                    "can_be_io":           p_io,
                    "can_be_ms_owner":     p_ms,
                    "workstream_scope":    p_ws_scope,
                    "permissions": {
                        "perform":   p_perform,
                        "execute":   p_execute,
                        "pipeline":  p_pipeline,
                        "products":  p_products,
                        "integrate": p_integrate,
                        "admin":     p_admin,
                    },
                })
                um._save()
                audit_log("PERMS_UPDATED", uname, sel)
                st.success("Permissions saved.")
                st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 3 — AUDIT LOG
# ════════════════════════════════════════════════════════════════
with t3:
    st.subheader("Audit log")
    from pathlib import Path
    import json as _json
    al_path = Path("data/audit_log.json")
    if al_path.exists():
        try:
            al = _json.loads(al_path.read_text()) or []
        except Exception:
            al = []
        if al:
            al_df = pd.DataFrame(reversed(al)).head(200)
            al_df.columns = [c.title() for c in al_df.columns]
            st.dataframe(al_df, use_container_width=True, hide_index=True)
        else:
            st.info("No audit entries yet.")
    else:
        st.info("Audit log file not found.")

# ════════════════════════════════════════════════════════════════
# TAB 4 — EMAIL SETTINGS
# ════════════════════════════════════════════════════════════════
with t4:
    st.subheader("Email configuration")
    cfg = load_email_config()
    with st.form("email_cfg"):
        ec1,ec2 = st.columns(2)
        smtp_host = ec1.text_input("SMTP host", value=cfg.get("smtp_host","smtp.gmail.com"))
        smtp_port = ec2.text_input("SMTP port", value=str(cfg.get("smtp_port","587")))
        sender    = ec1.text_input("Sender email", value=cfg.get("sender_email",""))
        password  = ec2.text_input("App password", type="password",
                        value=cfg.get("sender_password",""))
        if st.form_submit_button("Save email settings", type="primary"):
            save_email_config({"smtp_host": smtp_host, "smtp_port": smtp_port,
                               "sender_email": sender, "sender_password": password})
            st.success("Email settings saved.")
    st.markdown("---")
    test_addr = st.text_input("Send test email to")
    if st.button("Send test"):
        ok_t, msg_t = send_welcome_email(test_addr, "Test User", "testuser", "Test@1234!")
        if ok_t: st.success("Test email sent!")
        else:    st.error(f"Failed: {msg_t}")
