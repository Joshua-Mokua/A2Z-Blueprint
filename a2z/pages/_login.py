"""pages/_login.py — Authentication page."""
import streamlit as st
try:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from utils.core import get_org_config as _goc_login
    _bank_login = _goc_login().get("bank_name","Your Bank")
    _app_login  = _goc_login().get("app_name","A2Z Blueprint")
except: _bank_login = "Your Bank"; _app_login = "A2Z Blueprint"

import hashlib
import base64
from pathlib import Path
from utils.core import UserManager, audit_log

def _get_logo_svg():
    p = Path(__file__).parent.parent / "assets" / "logo.svg"
    if p.exists():
        svg = p.read_text(encoding="utf-8")
        b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    return ""

def show_login():
    um = st.session_state.get("user_manager")
    if um is None:
        um = UserManager()
        st.session_state["user_manager"] = um

    # ── Centred login card ────────────────────────────────────────────
    st.markdown(f"""
    <style>
    [data-testid="stAppViewContainer"] > .main {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 100vh;
        background: linear-gradient(135deg, #004A2B 0%, var(--brand-primary,#006B3F) 50%, #1D9E75 100%);
    }
    .block-container {
        max-width: 440px !important;
        padding: 0 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    _logo_svg = _get_logo_svg()
    _logo_html = (
        f"<img src='{_logo_svg}' width='200' style='display:block;margin:0 auto 12px'/>"
        if _logo_svg else
        "<div style='font-size:32px;font-weight:900;color:var(--brand-primary,#006B3F);letter-spacing:-1px'>A2Z</div>"
    )
    st.markdown(f"""
    <div style='
        background: white;
        border-radius: 20px;
        padding: 40px 40px 32px;
        box-shadow: 0 24px 64px rgba(0,0,0,0.2);
        text-align: center;
        margin-top: 20px;
    '>
        {_logo_html}
        <div style='font-size:11px;color:var(--color-text-tertiary);letter-spacing:2px;font-weight:600;
                    text-transform:uppercase;margin-bottom:28px'>
            {_bank_login}
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.container():
        mode = st.session_state.get("login_mode", "login")

        if mode == "login":
            with st.form("login_form", clear_on_submit=False):
                st.markdown("#### Sign in to your account")
                username = st.text_input("Username", placeholder="Enter your username")
                password = st.text_input("Password", type="password",
                                          placeholder="Enter your password")
                col1, col2 = st.columns([1, 1])
                submitted = col1.form_submit_button("Sign in", type="primary",
                                                     use_container_width=True)
                if col2.form_submit_button("Change password", use_container_width=True):
                    st.session_state["login_mode"] = "change_pw"
                    st.rerun()

                if submitted:
                    if not username or not password:
                        st.error("Please enter both username and password.")
                    else:
                        ok, user_data = um.authenticate(username, password)
                        if ok:
                            if user_data.get("must_change_password"):
                                # Force password change before logging in
                                st.session_state["pending_pw_change"] = username
                                st.session_state["login_mode"] = "force_change_pw"
                                audit_log("LOGIN_FORCE_PW", username, "Must change password")
                                st.rerun()
                            else:
                                st.session_state["logged_in"]  = True
                                st.session_state["username"]   = username
                                st.session_state["user_data"]  = user_data
                                audit_log("LOGIN", username, "Success")
                                st.rerun()
                        else:
                            audit_log("LOGIN_FAIL", username, "Invalid credentials")
                            st.error("Invalid username or password.")

        elif mode == "change_pw":
            with st.form("change_pw_form"):
                st.markdown("#### Change your password")
                cp_user    = st.text_input("Username")
                cp_current = st.text_input("Current password", type="password")
                cp_new     = st.text_input("New password", type="password",
                                            placeholder="At least 8 characters")
                cp_confirm = st.text_input("Confirm new password", type="password")
                c1, c2     = st.columns(2)
                if c1.form_submit_button("Update password", type="primary",
                                          use_container_width=True):
                    ok, _ = um.authenticate(cp_user, cp_current)
                    if not ok:
                        st.error("Current password is incorrect.")
                    elif cp_new != cp_confirm:
                        st.error("New passwords do not match.")
                    elif len(cp_new) < 8:
                        st.error("Password must be at least 8 characters.")
                    else:
                        um.change_password(cp_user, cp_new)
                        st.success("Password updated. Please sign in.")
                        st.session_state["login_mode"] = "login"
                        st.rerun()
                if c2.form_submit_button("Back to sign in", use_container_width=True):
                    st.session_state["login_mode"] = "login"
                    st.rerun()

        elif mode == "force_change_pw":
            # Forced password change — user cannot proceed without setting a new one
            _fc_user = st.session_state.get("pending_pw_change","")
            st.markdown(
                "<div style='background:#FEF3C7;border:1px solid #FDE68A;"
                "border-radius:8px;padding:12px 16px;margin-bottom:12px;font-size:12px'>"
                "🔑 <b>You must set a new password before continuing.</b><br>"
                "Your account was created with a temporary password. Please choose a new one."
                "</div>", unsafe_allow_html=True)
            with st.form("force_pw_form"):
                st.markdown(f"#### Set your password — {_fc_user}")
                fp_new     = st.text_input("New password", type="password",
                                            placeholder="At least 8 characters")
                fp_confirm = st.text_input("Confirm new password", type="password")
                if st.form_submit_button("Set password & sign in", type="primary",
                                          use_container_width=True):
                    if fp_new != fp_confirm:
                        st.error("Passwords do not match.")
                    elif len(fp_new) < 8:
                        st.error("Password must be at least 8 characters.")
                    else:
                        um.change_password(_fc_user, fp_new)
                        # Now log them in
                        _, user_data2 = um.authenticate(_fc_user, fp_new)
                        if user_data2:
                            st.session_state["logged_in"]  = True
                            st.session_state["username"]   = _fc_user
                            st.session_state["user_data"]  = user_data2
                            st.session_state.pop("pending_pw_change", None)
                            audit_log("PASSWORD_CHANGED", _fc_user, "Forced change")
                            st.rerun()

    st.markdown(
        "<div style='text-align:center;color:var(--color-text-tertiary);font-size:11px;margin-top:24px'>"
        f"{_bank_login} · Confidential · Authorised users only"
        "</div>", unsafe_allow_html=True)
