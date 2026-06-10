# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_login.py — Authentication page.
Centred white card on deep-blue background. IP notice footer.
"""
import streamlit as st
import hashlib, base64
from pathlib import Path
from utils.core_audit import audit_log
from utils.core import UserManager, validate_password_policy

try:
    from utils.core import get_org_config as _goc
    _cfg = _goc()
    _BANK = _cfg.get("bank_name", _cfg.get("app_name", "A2Z Blueprint"))
except Exception:
    _BANK = "A2Z Blueprint"


def _logo_b64():
    p = Path(__file__).parent.parent / "assets" / "logo.svg"
    if p.exists():
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f"data:image/svg+xml;base64,{b64}"
    return ""


def show_login():
    um = st.session_state.get("user_manager")
    if um is None:
        um = UserManager()
        st.session_state["user_manager"] = um

    # ── Full-page styling ─────────────────────────────────────────
    st.markdown("""
<style>
/* ── Hide all Streamlit chrome ──────────────────── */
[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
section[data-testid="stSidebarNavItems"],
div[data-testid="stSidebarNavSeparator"],
header[data-testid="stHeader"],
#MainMenu, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* ── Deep blue gradient full-page background ─────── */
.stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stAppViewContainer"] > .main {
    background: linear-gradient(145deg,
        #061422 0%, #0c2348 30%,
        #0f3370 60%, #1a52a8 100%) !important;
    min-height: 100vh;
}

/* ── Centre and constrain the content column ─────── */
[data-testid="stMainBlockContainer"],
.block-container,
[data-testid="stAppViewContainer"] > .main > div,
[data-testid="stAppViewContainer"] > .main .block-container {
    max-width: 460px !important;
    width: 460px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    padding-top: 6vh !important;
    background: transparent !important;
    box-shadow: none !important;
}

/* ── White card wrapping everything ─────────────── */
[data-testid="stForm"],
div[data-testid="stForm"] {
    background: #ffffff !important;
    border-radius: 16px !important;
    padding: 28px 32px 20px !important;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5),
                0 0 0 1px rgba(255,255,255,0.06) !important;
    border: none !important;
}

/* ── Input field polish ──────────────────────────── */
[data-testid="stTextInput"] input {
    border-radius: 8px !important;
    border: 1.5px solid #d1d9e6 !important;
    padding: 10px 14px !important;
    font-size: 14px !important;
    transition: border-color 0.2s;
}
[data-testid="stTextInput"] input:focus {
    border-color: #1a52a8 !important;
    box-shadow: 0 0 0 3px rgba(26,82,168,0.12) !important;
}

/* ── Primary button ──────────────────────────────── */
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #0f3370, #1a52a8) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    height: 42px !important;
    transition: opacity 0.2s !important;
}
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
    opacity: 0.88 !important;
}

/* ── Forgot password button ──────────────────────── */
[data-testid="stBaseButton-secondary"] {
    background: transparent !important;
    border: none !important;
    color: rgba(255,255,255,0.6) !important;
    font-size: 12px !important;
    padding: 0 !important;
    text-decoration: underline !important;
}
</style>
    """, unsafe_allow_html=True)

    # ── Logo / app banner ─────────────────────────────────────────
    _logo = _logo_b64()
    _logo_html = (
        f"<img src='{_logo}' width='160' style='display:block;margin:0 auto 10px'/>"
        if _logo else
        "<div style='font-size:38px;font-weight:900;color:#fff;text-align:center;"
        "letter-spacing:-2px;margin-bottom:6px'>A2Z</div>"
    )
    st.markdown(f"""
<div style="text-align:center; padding-bottom:20px">
  {_logo_html}
  <div style="font-size:14px; color:rgba(255,255,255,0.85); font-weight:700;
              letter-spacing:2.5px; text-transform:uppercase; margin-bottom:3px">
    {_BANK}
  </div>
  <div style="font-size:11px; color:rgba(255,255,255,0.4); letter-spacing:1px">
    MIS 360 &nbsp;·&nbsp; Management Intelligence System
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Auth forms ───────────────────────────────────────────────
    mode = st.session_state.get("login_mode", "login")

    if mode == "login":
        with st.form("login_form", clear_on_submit=False):
            st.markdown(
                "<div style=\'font-size:18px;font-weight:700;color:#0f2d5c;"
                "margin-bottom:18px\'>Sign in to your account</div>",
                unsafe_allow_html=True)
            username = st.text_input("Username", placeholder="Enter your username",
                                     label_visibility="visible")
            password = st.text_input("Password", type="password",
                                     placeholder="Enter your password",
                                     label_visibility="visible")
            st.markdown("<div style=\'height:4px\'></div>", unsafe_allow_html=True)
            col1, col2 = st.columns([3, 2])
            submitted = col1.form_submit_button("Sign in →", type="primary",
                                                 use_container_width=True)
            if col2.form_submit_button("Change password", use_container_width=True):
                st.session_state["login_mode"] = "change_pw"
                st.rerun()

            if submitted:
                import datetime as _dt
                _attempts     = st.session_state.get("login_attempts", 0)
                _locked_until = st.session_state.get("login_lockout_until")
                if _locked_until and _dt.datetime.now() < _locked_until:
                    _mins = int((_locked_until - _dt.datetime.now()).total_seconds() / 60) + 1
                    st.error(f"🔒 Account locked. Try again in {_mins} minute(s).")
                    st.stop()
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    ok, user_data = um.authenticate(username, password)
                    if ok:
                        st.session_state["login_attempts"] = 0
                        st.session_state["login_lockout_until"] = None
                        if user_data.get("must_change_password"):
                            st.session_state["pending_pw_change"] = username
                            st.session_state["login_mode"] = "force_change_pw"
                            audit_log("LOGIN_FORCE_PW", username, "Must change password")
                            st.rerun()
                        else:
                            st.session_state["logged_in"]    = True
                            st.session_state["username"]     = username
                            st.session_state["user_data"]    = user_data
                            st.session_state["_app_loading"] = True
                            audit_log("LOGIN", username, "Success")
                            st.rerun()
                    else:
                        _attempts += 1
                        st.session_state["login_attempts"] = _attempts
                        if _attempts >= 5:
                            import datetime as _dtlk
                            st.session_state["login_lockout_until"] = (
                                _dtlk.datetime.now() + _dtlk.timedelta(minutes=15))
                            audit_log("LOGIN_LOCKOUT", username,
                                      f"Locked after {_attempts} attempts")
                            st.error("🔒 Too many failed attempts. Account locked for 15 minutes.")
                        else:
                            remaining = 5 - _attempts
                            audit_log("LOGIN_FAIL", username,
                                      f"Invalid credentials (attempt {_attempts})")
                            st.error(
                                f"Invalid username or password. "
                                f"{remaining} attempt(s) remaining before lockout.")

        if st.button("🔑 Forgot password?", key="goto_forgot"):
            st.session_state["login_mode"] = "forgot_pw"
            st.rerun()

    elif mode == "change_pw":
        with st.form("change_pw_form"):
            st.markdown(
                "<div style=\'font-size:17px;font-weight:700;color:#0f2d5c;"
                "margin-bottom:16px\'>Change your password</div>",
                unsafe_allow_html=True)
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
                else:
                    # v10.501 Batch 4a — GAP-001 closure: enforce the
                    # complexity policy advertised in utils/core.py:313.
                    pw_ok, pw_reason = validate_password_policy(cp_new)
                    if not pw_ok:
                        st.error(pw_reason)
                    else:
                        um.change_password(cp_user, cp_new)
                        st.success("✅ Password updated. Please sign in.")
                        st.session_state["login_mode"] = "login"
                        st.rerun()
            if c2.form_submit_button("← Back", use_container_width=True):
                st.session_state["login_mode"] = "login"
                st.rerun()

    elif mode == "forgot_pw":
        with st.form("forgot_pw_form"):
            st.markdown(
                "<div style=\'font-size:17px;font-weight:700;color:#0f2d5c;"
                "margin-bottom:12px\'>Reset your password</div>",
                unsafe_allow_html=True)
            st.caption("Your security answer is the last 4 digits of your staff code.")
            fp_user = st.text_input("Username")
            fp_q    = st.text_input("Last 4 digits of your staff code",
                                     placeholder="e.g. 0042")
            if st.form_submit_button("Reset password", type="primary",
                                      use_container_width=True):
                _fp_u = um.users.get(fp_user.strip(), {})
                _sc   = str(_fp_u.get("staff_code", ""))
                if _fp_u and _sc and fp_q.strip() == _sc[-4:]:
                    import random, string
                    _tmp = "Temp" + "".join(random.choices(string.digits, k=6))
                    um.users[fp_user.strip()]["password"]             = _tmp
                    um.users[fp_user.strip()]["must_change_password"] = True
                    um.save()
                    audit_log("PASSWORD_RESET_SELF", fp_user.strip(), "Self-service reset")
                    st.success(
                        f"Temporary password: **{_tmp}**  ·  "
                        "You will be prompted to change it on next login.")
                else:
                    st.error(
                        "Username not found or security answer incorrect. "
                        "Contact your administrator for a manual reset.")
        if st.button("← Back to sign in", key="forgot_back"):
            st.session_state["login_mode"] = "login"
            st.rerun()

    elif mode == "force_change_pw":
        _fc_user = st.session_state.get("pending_pw_change", "")
        with st.form("force_pw_form"):
            st.markdown(
                "<div style=\'background:#FEF3C7;border:1px solid #FDE68A;"
                "border-radius:8px;padding:10px 14px;margin-bottom:14px;font-size:12px\'>"
                "🔑 <b>You must set a new password before continuing.</b></div>",
                unsafe_allow_html=True)
            st.markdown(f"**Setting password for: {_fc_user}**")
            # v10.501 Batch 4a — GAP-005 closure: require current password
            # even on forced rotation, matching the FastAPI endpoint's
            # defensive divergence. A user holding only a must_rotate
            # session can no longer set an arbitrary password without
            # proving knowledge of the current credential.
            fp_current = st.text_input("Current password", type="password",
                                        key="force_pw_current")
            fp_new     = st.text_input("New password", type="password",
                                        placeholder="At least 8 characters, uppercase, "
                                                    "lowercase, digit, special")
            fp_confirm = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Set password & sign in →", type="primary",
                                      use_container_width=True):
                # Verify current password first — defensive even for
                # forced rotation. Mirrors utils/api.py change-password
                # endpoint behaviour (Batch 3b convention).
                cur_ok, _cur_data = um.authenticate(_fc_user, fp_current)
                if not cur_ok:
                    audit_log("PASSWORD_CHANGE_FAILED", _fc_user,
                              "current_password mismatch (force_change_pw)")
                    st.error("Current password is incorrect.")
                elif fp_new != fp_confirm:
                    st.error("Passwords do not match.")
                else:
                    # v10.501 Batch 4a — GAP-001 closure: enforce the
                    # complexity policy advertised in utils/core.py:313.
                    pw_ok, pw_reason = validate_password_policy(fp_new)
                    if not pw_ok:
                        st.error(pw_reason)
                    elif fp_new == fp_current:
                        st.error("New password must differ from current password.")
                    else:
                        um.change_password(_fc_user, fp_new)
                        _, user_data2 = um.authenticate(_fc_user, fp_new)
                        if user_data2:
                            st.session_state["logged_in"]  = True
                            st.session_state["username"]   = _fc_user
                            st.session_state["user_data"]  = user_data2
                            st.session_state.pop("pending_pw_change", None)
                            audit_log("PASSWORD_CHANGED", _fc_user, "Forced change on login")
                            st.rerun()

    # ── IP / confidentiality notice ───────────────────────────────
    st.markdown(f"""
<div style="text-align:center; margin-top:24px; padding:0 4px;
            color:rgba(255,255,255,0.38); font-size:10px; line-height:1.8">
  <div style="color:rgba(255,255,255,0.55);font-weight:600;
              font-size:11px;margin-bottom:5px;letter-spacing:0.5px">
    {_BANK} &nbsp;·&nbsp; A2Z Blueprint MIS&nbsp;360
  </div>
  Confidential &nbsp;·&nbsp; Authorised users only
  &nbsp;·&nbsp; All sessions are logged<br>
  <span style="font-size:9.5px;color:rgba(255,255,255,0.28)">
    This system is protected intellectual property. Unauthorised access or
    reproduction is strictly prohibited and may be subject to legal action.
  </span>
</div>
""", unsafe_allow_html=True)
