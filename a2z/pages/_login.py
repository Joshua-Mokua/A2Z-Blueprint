"""pages/_login.py — Login and force-password-change screens."""
import streamlit as st
import hashlib
from utils.core import (UserManager, audit_log, check_password_strength,
                         ValidationManager, StaffStatusManager, LeaveManager,
                         PipelineManager, RIPipelineManager, ProductManager,
                         ExecuteManager)


def show_login():
    # Ecobank branded header
    st.markdown(
        f"<div style='text-align:center;padding:32px 0 16px'>"
        f"<div style='display:inline-block;background:#006B3F;color:white;"
        f"padding:10px 28px;border-radius:8px;font-size:28px;font-weight:500;"
        f"letter-spacing:1px;margin-bottom:12px'>A2Z Blueprint</div>"
        f"<div style='color:#006B3F;font-size:15px;font-weight:500;letter-spacing:2px'>"
        f"PERFORM · EXECUTE · INTEGRATE</div>"
        f"<div style='color:#888;font-size:12px;margin-top:6px'>"
        f"Strategy Execution Management System</div>"
        f"</div>",
        unsafe_allow_html=True)
    st.markdown("---")
    _, c2, _ = st.columns([1, 2, 1])
    with c2:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            _um = UserManager()
            ok, udata = _um.authenticate(username, password)
            if ok:
                st.session_state.update({
                    "logged_in":           True,
                    "username":            username,
                    "user_data":           udata,
                    "user_manager":        _um,
                    "validation_manager":  ValidationManager(),
                    "staff_status_manager": StaffStatusManager(),
                    "leave_manager":       LeaveManager(),
                    "pipeline_manager":    PipelineManager(),
                    "ri_pipeline_manager": RIPipelineManager(),
                    "product_manager":     ProductManager(),
                    "execute_manager":     ExecuteManager(),
                })
                audit_log("LOGIN", username)
                st.rerun()
            else:
                st.error("Invalid username or password.")
        st.caption("Demo: admin / admin123")


def show_force_pw_change(um, uname, ud):
    name = ud.get("full_name", uname)
    st.markdown("<h2 style='color:#1B4F72'>Set your new password</h2>",
                unsafe_allow_html=True)
    st.info(f"Welcome {name} — please set a new password to continue.")
    st.markdown("""
**Password requirements:**
- At least 8 characters
- One uppercase letter (A-Z)
- One lowercase letter (a-z)
- One number (0-9)
- One special character (!@#$%^&*)
""")
    with st.form("force_pw_form"):
        new_pw  = st.text_input("New password",     type="password")
        new_pw2 = st.text_input("Confirm password", type="password")
        if st.form_submit_button("Set password and continue", type="primary"):
            if not new_pw:
                st.error("Enter a password.")
            elif new_pw != new_pw2:
                st.error("Passwords do not match.")
            else:
                ok, issues = check_password_strength(new_pw)
                if not ok:
                    for issue in issues:
                        st.markdown(f"  {issue}")
                else:
                    um.change_password(uname, new_pw)
                    st.session_state["user_data"]["must_change_password"] = False
                    audit_log("PASSWORD_CHANGED", uname)
                    st.success("Password set successfully!")
                    st.rerun()
