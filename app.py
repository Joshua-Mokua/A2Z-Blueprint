"""app.py — A2Z Platform entry point. Run: streamlit run app.py"""
import streamlit as st
from pathlib import Path

# ── Version stamp — wipes only manager objects when code is updated ──
_APP_VERSION = "v10.500-phase1-closed-2026.05.26"
if st.session_state.get("_app_version") != _APP_VERSION:
    # Only remove manager objects — keep auth, data, and UI state
    _mgr_keys = [k for k in list(st.session_state.keys())
                 if any(k.endswith(s) for s in
                        ("_manager","cascade_manager","pipeline_manager",
                         "execute_manager","hr_manager","leave_manager",
                         "user_manager","ri_pipeline_manager","product_manager",
                         "reporting_line_manager","validation_manager"))]
    for _k in _mgr_keys:
        del st.session_state[_k]
    st.session_state["_app_version"] = _APP_VERSION
from utils.core_audit import audit_log
from utils.core import (
    UserManager, ExecuteManager, LeaveManager,
    PipelineManager, RIPipelineManager, ProductManager,
    run_escalation_scan, should_run_scan,
    DATA_DIR, clean_code,
    process_kpi_data, build_staff_scores, build_staff_registry,
)
try:
    from utils.core import HRManager, CascadeManager, ValidationManager, ReportingLineManager
except ImportError:
    class HRManager:
        """Fallback stub — update utils/core.py and restart."""
        def __init__(self): self.exits=[]; self.transfers=[]; self.disciplinary=[]; self.pips=[]; self.records=[]
        def get_exits(self,*a,**k): return []
        def get_active_pips(self): return []
        def get_active_cases(self): return []
        def exit_analytics(self): return {}
        def get_transfers(self,*a,**k): return []
        def record_exit(self,d): pass
        def record_transfer(self,d): pass
        def open_case(self,d): return {}
        def advance_stage(self,*a,**k): return None
        def open_pip(self,d): return {}
        def add_pip_review(self,*a,**k): return None
        def staff_on_pip(self,s): return False
        def staff_has_active_case(self,s): return False
        def pip_days_remaining(self,p): return 0
        def compute_diligence(self,*a,**k): return 100.0
        def _load(self,p): return []
        def _save(self,p,d): pass

class ReportingLineManager:
    def __init__(self): self.overrides={}; self.units={}
    def apply_to_registry(self,df): return df
    def remap(self,*a,**k): pass
    def transfer(self,*a,**k): pass
    def clear_override(self,*a,**k): pass
    def get_all_overrides(self): return []
    def get_org_tree(self,df): return {}
    def get_direct_reports(self,mc,df): return []
    def summary(self): return {'total_overrides':0,'total_transfers':0,'last_updated':'Never'}

class CascadeManager:
    def __init__(self): self.cascade={}
    def _save(self): pass
    def set_allocation(self,*a,**k): return {}
    def get_allocation(self,*a,**k): return None
    def get_my_allocations(self,*a,**k): return {}
    def get_what_i_was_given(self,*a,**k): return []
    def cascade_coverage(self,*a,**k): return 0,0,0,0



def _inject_brand_css():
    try:
        from utils.core import get_org_config as _goc_css
        _cfg_css = _goc_css()
        _brand   = _cfg_css.get("brand_color",   "#006B3F")
        _dark    = _cfg_css.get("brand_color_dark",  "#004D2E")
        _light   = _cfg_css.get("brand_color_light", "#E8F5EE")
        st.markdown(
            f"<style>:root{{--brand-primary:{_brand};"
            f"--brand-dark:{_dark};--brand-light:{_light};}}</style>",
            unsafe_allow_html=True)
    except: pass

st.set_page_config(
    page_title="A2Z — Perform · Execute · Integrate",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="collapsed",
)

# ── Session state bootstrap ────────────────────────────────────────────
def _auto_load_cbs_data():
    """Load CBS actuals automatically at app startup — no upload needed.
    On each startup, calls actuals_engine.compute_actuals_from_cbs() which
    checks if CBS data is newer than the existing actuals file and recomputes
    only when needed. Force=True on manual refresh from Admin."""
    import glob, os
    from pathlib import Path as _Path

    # Already loaded from manual upload or cache? Don't override.
    if len(st.session_state.get("staff_scores",[])) > 0:
        return
    # If a manual BSC upload was done this session, respect it
    if st.session_state.get("_last_upload","").lower().endswith((".xlsx",".xls")):
        _src = st.session_state.get("_data_source","")
        if "CBS" not in _src:
            return  # manual upload — don't overwrite

    # Look for actuals file in a2z/data/
    _root   = _Path(__file__).parent   # a2z/
    _data   = _root / "data"
    _parent = _root.parent             # project root

    # Skip CBS actuals if there is already a manually-uploaded BSC file cached
    _manual_bsc = [f for f in _data.glob("A2Z*.xlsx")]
    if _manual_bsc:
        return  # hand-built BSC file present — don't auto-load CBS

    _actuals = None
    for _folder in [_data, _parent/"cbs_data"]:
        _found = sorted(_folder.glob("actuals_*.xlsx"), reverse=True)
        if not _found:
            _found = sorted(_folder.glob("actuals_*.csv"), reverse=True)
        if _found:
            _actuals = _found[0]
            break

    if _actuals is None:
        return  # nothing to load — upload prompt will show

    # Already loaded this exact file?
    # Also check staff count — if users.json changed, reload actuals
    import json as _json
    _user_count = len(_json.loads((_data/"users.json").read_text())) if (_data/"users.json").exists() else 0
    _cache_key  = f"{_actuals}|{_user_count}"
    if st.session_state.get("_cbs_loaded_file") == _cache_key:
        return

    try:
        import pandas as _pd
        from utils.core import (process_kpi_data, build_staff_scores,
                                BRANCH_REGION, detect_month_actual_columns,
                                parse_month_column)
        from datetime import datetime as _dt

        if str(_actuals).endswith(".xlsx"):
            try:
                _df = _pd.read_excel(_actuals, header=1)
                if "KPI" not in _df.columns:
                    _df = _pd.read_excel(_actuals, header=0)
            except:
                _df = _pd.read_excel(_actuals, header=0)
        else:
            _df = _pd.read_csv(_actuals)

        _df.columns = [str(c).strip() for c in _df.columns]
        if len(_df) < 5 or "KPI" not in _df.columns:
            return

        _df_proc = process_kpi_data(_df)
        _scores  = build_staff_scores(_df_proc)
        if "Region" not in _scores.columns and "Unit" in _scores.columns:
            _scores["Region"] = _scores["Unit"].map(BRANCH_REGION).fillna("Head Office")

        _month_cols = detect_month_actual_columns(_df_proc)
        _now = _dt.now()
        _active = [c for c in _month_cols
                   if (lambda d: d and (d.year < _now.year or
                       (d.year == _now.year and d.month <= _now.month)))(parse_month_column(c))]

        # Load staff register
        _sr_df = _pd.DataFrame()
        for _sf in [_data/"staff_register.xlsx", _parent/"cbs_data"/"staff_register.xlsx",
                    _data/"staff_register.csv",   _parent/"cbs_data"/"staff_register.csv"]:
            if _sf.exists():
                try:
                    _sr_df = (_pd.read_excel(_sf) if str(_sf).endswith(".xlsx")
                              else _pd.read_csv(_sf))
                    break
                except: pass

        st.session_state.update({
            "df_processed":     _df_proc,
            "staff_scores":     _scores,
            "filtered_staff":   _scores,
            "all_months":       _month_cols,
            "active_months":    _active,
            "staff_registry":   _sr_df,
            "_cbs_loaded_file": _cache_key,
            "_data_source":     f"CBS Auto ({_actuals.name})",
            "_last_upload":     _actuals.name,
        })
    except Exception:
        pass   # silent fail — upload prompt will show


def _init_managers():
    if "user_manager"        not in st.session_state:
        st.session_state["user_manager"]        = UserManager()
    if "leave_manager"       not in st.session_state:
        st.session_state["leave_manager"]       = LeaveManager()
    # Always reload PipelineManager so new methods (get_actions_due etc.) are available
    try:
        _pm_new = PipelineManager()
        assert hasattr(_pm_new, 'get_actions_due')
        assert hasattr(_pm_new, 'update_deal')
        st.session_state["pipeline_manager"] = _pm_new
    except Exception:
        if "pipeline_manager" not in st.session_state:
            st.session_state["pipeline_manager"] = PipelineManager()
    if "ri_pipeline_manager" not in st.session_state:
        st.session_state["ri_pipeline_manager"] = RIPipelineManager()
    if "product_manager"     not in st.session_state:
        st.session_state["product_manager"]     = ProductManager()
    if "hr_manager" not in st.session_state:
        st.session_state["hr_manager"] = HRManager()
    if "reporting_line_manager" not in st.session_state:
        try:
            st.session_state["reporting_line_manager"] = ReportingLineManager()
        except Exception: pass
    if "validation_manager" not in st.session_state:
        try:
            st.session_state["validation_manager"] = ValidationManager()
        except Exception: pass
    # Always reload CascadeManager from disk — ensures bank targets,
    # fixed KPIs and cascade data are fresh after any save operation
    try:
        _cm_new = CascadeManager()
        # Always replace — guarantees fresh instance with all current methods
        st.session_state["cascade_manager"] = _cm_new
    except Exception:
        # If construction fails, patch the stale instance rather than leave it broken
        _stale = st.session_state.get("cascade_manager")
        if _stale is not None:
            # Patch every method that pages depend on
            _required = {
                "bank_targets":    {},
                "targets_locked":  False,
                "fixed_kpis":      {},
                "cascade":         {},
            }
            for _attr, _default in _required.items():
                if not hasattr(_stale, _attr):
                    setattr(_stale, _attr, _default)
            # Patch methods as no-ops if missing
            import types as _types
            if not hasattr(_stale, "get_fixed_kpis"):
                _stale.get_fixed_kpis = lambda period="": []
            if not hasattr(_stale, "get_bank_target"):
                _stale.get_bank_target = lambda kpi, period: None
            if not hasattr(_stale, "is_fixed"):
                _stale.is_fixed = lambda kpi, period: False
        elif "cascade_manager" not in st.session_state:
            try: st.session_state["cascade_manager"] = CascadeManager()
            except: pass
    # Always recreate ExecuteManager so new methods are picked up after updates
    st.session_state["execute_manager"] = ExecuteManager()
    # Refresh execute data from disk each load
    em = st.session_state["execute_manager"]
    em.initiatives = em._load_list(em.init_file)
    em.ideas       = em._load_list(em.ideas_file)
    em.workstreams = em._load_dict(em.ws_file)

# ── Notification builder ────────────────────────────────────────────────
def _build_notifications():
    """Real-time notifications: cascade deadlines, review requests, CIMS, milestones."""
    notifs = []
    _ud   = st.session_state.get("user_data", {})
    _un   = st.session_state.get("username", "")
    if not _ud: return notifs
    _sc   = str(_ud.get("staff_code","") or _un)
    _nm   = _ud.get("full_name", _un)
    import datetime as _dt3
    _today = _dt3.date.today()

    try:
        _c = st.session_state.get("cascade_manager")
        if _c:
            _dl = _c.get_cascade_deadline(_sc, _gfy(), _nm)
            if _dl and not _dl.get("confirmed"):
                _due  = _dt3.date.fromisoformat(_dl["confirm_by"])
                _days = (_due - _today).days
                if _days <= 3:
                    notifs.append({"icon":"🔴" if _days<0 else "🟡",
                        "msg":f"Targets {'overdue' if _days<0 else f'due in {_days}d'} — confirm in Cascade → My Targets",
                        "level":"urgent" if _days<0 else "warning"})
            _rrs = _c.get_review_requests(_gfy()) if hasattr(_c,"get_review_requests") else []
            _pr = [r for r in _rrs if r.get("status")=="Pending"
                   and r.get("reviewer_code","") in (_sc,_un)]
            if _pr:
                notifs.append({"icon":"📋",
                    "msg":f"{len(_pr)} review request(s) need your response",
                    "level":"info"})
    except: pass

    try:
        _em = st.session_state.get("execute_manager")
        if _em:
            _oms = [m for m in _em.get_all_milestones_for_owner(_un)
                    if m.get("days_to_due",0)<0 and m.get("status")!="Complete"]
            if _oms:
                notifs.append({"icon":"⏰",
                    "msg":f"{len(_oms)} overdue milestone(s) in Execute",
                    "level":"warning"})
    except: pass

    return notifs

# ── Login guard ────────────────────────────────────────────────────────
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    from pages._login import show_login
    # Hide sidebar entirely during login
    st.markdown("""
    <style>
    [data-testid="stSidebar"],[data-testid="stSidebarNav"],
    section[data-testid="stSidebarNavItems"]{display:none!important}
    </style>
    """, unsafe_allow_html=True)
    show_login()
    st.stop()


# ── Session expiry — 8 hours maximum ────────────────────────────────────
if st.session_state.get("logged_in"):
    import datetime as _dt_se
    _login_time = st.session_state.get("_login_time")
    if _login_time is None:
        st.session_state["_login_time"] = _dt_se.datetime.now()
    elif (_dt_se.datetime.now() - _login_time).total_seconds() > 28800:  # 8 hours
        _uname_se = st.session_state.get("username", "")
        # Clear session
        for _k in list(st.session_state.keys()):
            del st.session_state[_k]
        st.session_state["logged_in"] = False
        st.session_state["_session_expired"] = True
        st.rerun()

# Show expiry notice
if st.session_state.get("_session_expired"):
    st.session_state.pop("_session_expired", None)
    st.warning("⏰ Your session expired after 8 hours. Please sign in again.")

# ── App loading screen — shown once after login while managers init ──────
if st.session_state.get("_app_loading"):
    _ud_name  = st.session_state.get("user_data", {}).get("full_name", "")
    _ud_role  = st.session_state.get("user_data", {}).get("role", "")
    _ud_dept  = st.session_state.get("user_data", {}).get("department", "")
    _first    = _ud_name.split()[0] if _ud_name else "there"

    # ── Loading screen ──────────────────────────────────────────
    try:
        from utils.core import get_org_config as _goc_ls
        _bank_ls = _goc_ls().get("bank_name", "A2Z Blueprint")
    except Exception:
        _bank_ls = "A2Z Blueprint"

    st.markdown("""
<style>
[data-testid="stSidebar"],[data-testid="stSidebarNav"],
section[data-testid="stSidebarNavItems"],header[data-testid="stHeader"],
#MainMenu,footer,[data-testid="stToolbar"]{display:none!important}
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],
[data-testid="stAppViewContainer"]>.main{
    background:linear-gradient(145deg,#061422 0%,#0c2348 30%,#0f3370 60%,#1a52a8 100%)!important;
    min-height:100vh;
}
[data-testid="stMainBlockContainer"],.block-container,
[data-testid="stAppViewContainer"]>.main>.div,
[data-testid="stAppViewContainer"]>.main .block-container{
    max-width:480px!important;width:480px!important;
    margin-left:auto!important;margin-right:auto!important;
    padding-top:10vh!important;background:transparent!important;
}
</style>""", unsafe_allow_html=True)

    st.markdown(f"""
<div style="text-align:center;color:rgba(255,255,255,0.9);margin-bottom:32px">
  <div style="font-size:38px;font-weight:900;letter-spacing:-2px;margin-bottom:4px">A2Z</div>
  <div style="font-size:13px;color:rgba(255,255,255,0.5);letter-spacing:2px;
              text-transform:uppercase">{_bank_ls} &nbsp;·&nbsp; MIS 360</div>
</div>
<div style="background:rgba(255,255,255,0.07);border-radius:12px;padding:24px 28px;
            border:1px solid rgba(255,255,255,0.1)">
  <div style="font-size:16px;font-weight:600;color:#fff;margin-bottom:4px">
    Welcome back, {_first} 👋
  </div>
  <div style="font-size:12px;color:rgba(255,255,255,0.5);margin-bottom:20px">
    {_ud_role} &nbsp;·&nbsp; {_ud_dept}
  </div>
</div>
""", unsafe_allow_html=True)

    # Progress bar steps
    _prog_bar  = st.progress(0)
    _prog_text = st.empty()

    def _prog(pct, ico, label):
        _prog_bar.progress(pct)
        _prog_text.markdown(
            f"<div style=\'text-align:center;color:rgba(255,255,255,0.6);"
            f"font-size:13px;margin-top:10px\'>{ico} {label}…</div>",
            unsafe_allow_html=True)

    # Step 1 — bootstrap user session (instant)
    _prog(10, "🔐", "Verifying session")
    st.session_state.setdefault("user_manager", __import__("utils.core",fromlist=["UserManager"]).UserManager())

    # Step 2 — load BSC / actuals data (the real slow step)
    _prog(25, "📊", "Loading scorecard data")
    try:
        _auto_load_cbs_data()
    except Exception: pass

    # Step 3 — init pipeline + execute managers
    _prog(50, "💼", "Loading pipeline & execute data")
    try:
        from utils.core import PipelineManager, ExecuteManager, RIPipelineManager, ProductManager
        st.session_state["pipeline_manager"]    = PipelineManager()
        st.session_state["execute_manager"]     = ExecuteManager()
        st.session_state["ri_pipeline_manager"] = RIPipelineManager()
        st.session_state["product_manager"]     = ProductManager()
    except Exception: pass

    # Step 4 — init HR + cascade managers
    _prog(72, "👥", "Loading HR & cascade data")
    try:
        from utils.core import HRManager, CascadeManager, LeaveManager
        st.session_state.setdefault("hr_manager",    HRManager())
        st.session_state.setdefault("leave_manager", LeaveManager())
        st.session_state["cascade_manager"] = CascadeManager()
    except Exception: pass

    # Step 5 — load staff registry
    _prog(88, "🏦", "Building staff registry")
    try:
        from utils.core import build_staff_scores, build_staff_registry
        if len(st.session_state.get("staff_scores", [])) == 0:
            _auto_load_cbs_data()
    except Exception: pass

    # Done
    _prog(100, "✅", "Workspace ready")

    st.session_state.pop("_app_loading", None)
    st.rerun()

# ── Fast re-init for return visits (managers already in session) ──
# If user is logged in but managers aren't in session (e.g. after timeout reset)
# do a silent re-init without the loading screen
if st.session_state.get("logged_in") and "pipeline_manager" not in st.session_state:
    try:
        _init_managers()
    except Exception:
        pass

# ── Daily escalation scan ──────────────────────────────────────────────
if should_run_scan():
    _reg = {k: {"email": v.get("email",""), "full_name": v.get("full_name", k),
                "role": v.get("role","")}
            for k, v in st.session_state["user_manager"].users.items()}
    st.session_state["scan_alerts"] = run_escalation_scan(
        st.session_state["execute_manager"], _reg)

# ── Force password change ──────────────────────────────────────────────
ud = st.session_state["user_data"]
um = st.session_state["user_manager"]
uname = st.session_state["username"]

if ud.get("must_change_password"):
    from pages._login import show_force_pw_change
    show_force_pw_change(um, uname, ud)
    st.stop()

# ─── Standard #39: Streamlit Admin (Preserved) ────────────────────────
# Per master spec #39, app.py is the Admin-only Streamlit interface;
# non-Admin users go to the React SPA (#37) or Mobile (#38).
#
# The gate is FEATURE-FLAG CONTROLLED so production stays working
# during the rollout window — when the React SPA goes live, set
# `enforce_admin_only` true in data/feature_flags.json.
#
# The spec-literal pattern below is preserved BYTE-FOR-BYTE so audit
# gate G44 catches any drift. Reading from user_data.role is how the
# A2Z auth layer exposes role; spec literal `st.session_state.get('role')`
# is checked as a fallback for compatibility.
def _admin_only_enabled() -> bool:
    """Feature flag — defaults False so existing users aren't locked out
    until the React SPA is operational."""
    try:
        from utils.db import db
        flags = db.load_json(DATA_DIR / "feature_flags.json", default={})
        return bool(flags.get("enforce_admin_only", False))
    except Exception:
        return False

if _admin_only_enabled():
    # Spec-literal pattern (#39): non-Admin → access denied + stop
    if st.session_state.get('role') not in ['Admin'] \
       and ud.get('role') not in ['Admin']:
        st.error("Access denied. Admin interface only.")
        st.stop()
# Keep existing 89 admin pages unchanged

# ── Sidebar ────────────────────────────────────────────────────────────
from pages._sidebar import show_sidebar
show_sidebar()

# ── One-time permission safety migration ──────────────────────────
# Strips can_view_all from any account that isn't MD/Admin
# Runs on every app start but is effectively a no-op after first run
try:
    from utils.core_audit import fix_view_all_permissions
    _um_ref = st.session_state.get("user_manager")
    if _um_ref and hasattr(_um_ref, "users"):
        _fixed = fix_view_all_permissions(_um_ref)
        if _fixed:
            st.session_state["_filtered_for"] = None  # force re-filter
except Exception:
    pass

# ── Clear accessible_modules for MD/Admin — prevents module lockout ──
try:
    _um_ref2 = st.session_state.get("user_manager")
    if _um_ref2 and hasattr(_um_ref2, "users"):
        _fixed_mods = False
        for _uname, _udata in _um_ref2.users.items():
            _rl = str(_udata.get("role","")).lower()
            if _udata.get("is_admin") or "managing" in _rl:
                if _udata.get("accessible_modules"):
                    _udata["accessible_modules"] = []
                    _fixed_mods = True
        if _fixed_mods:
            _um_ref2.save()
except Exception:
    pass

# ── Page routing via st.navigation ────────────────────────────────────
# Streamlit >=1.29 multipage navigation
# ── Load global CSS ──────────────────────────────────────────────────
_css_path = Path(__file__).parent / ".streamlit" / "style.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text(encoding="utf-8")}</style>", unsafe_allow_html=True)

# ── Load logo SVGs ────────────────────────────────────────────────────
import base64
_logo_path       = Path(__file__).parent / "assets" / "logo.svg"
_logo_white_path = Path(__file__).parent / "assets" / "logo_white.svg"
LOGO_SVG       = _logo_path.read_text(encoding="utf-8")       if _logo_path.exists()       else ""
LOGO_WHITE_SVG = _logo_white_path.read_text(encoding="utf-8") if _logo_white_path.exists() else ""

def _logo_b64(svg_str):
    return "data:image/svg+xml;base64," + base64.b64encode(svg_str.encode()).decode()

# ── Sticky top header bar ─────────────────────────────────────────────
def render_topbar():
    """Sticky top bar with logo, user badge. Rendered on every page."""
    if not st.session_state.get("logged_in"):
        return

    ud       = st.session_state.get("user_data", {})
    uname    = st.session_state.get("username", "")
    name     = ud.get("full_name", uname) or uname
    role     = ud.get("role", "")
    parts    = name.strip().split()
    initials = ((parts[0][0] + parts[-1][0]).upper()
                if len(parts) >= 2 else (name[:2].upper() if name else "U"))

    # Use base64 data URI — avoids ALL quote-escaping issues with inline SVG
    def _img(svg, h):
        if not svg: return ''
        b64 = base64.b64encode(svg.encode('utf-8')).decode('ascii')
        return f"<img src='data:image/svg+xml;base64,{b64}' height='{h}' style='display:block'/>"

    logo_html = (
        _img(LOGO_SVG, 40) if LOGO_SVG else
        "<span style='font-size:16px;font-weight:900;color:var(--brand-primary,#006B3F);letter-spacing:-0.5px'>"
        "A2Z <span style='color:#F5A623'>Blueprint</span></span>"
    )
    logo_white_html = (
        _img(LOGO_WHITE_SVG, 36) if LOGO_WHITE_SVG else
        "<span style='font-size:14px;font-weight:900;color:white;letter-spacing:-0.5px'>"
        "A2Z Blueprint</span>"
    )

    # ── CSS — hide Streamlit header, push content below our topbar ─────
    css = (
        "<style>"
        # Hide default Streamlit header
        "header[data-testid='stHeader']{display:none!important;height:0!important;}"
        # Push main content below our topbar (topbar = 54px, group tabs = 40px = 94px total)
        "section[data-testid='stMain']>div:first-child{padding-top:90px!important;}"
        ".main .block-container{padding-top:96px!important;}"
        # Sidebar — compact, icon-first, minimal scroll
        "[data-testid='stSidebarContent']{padding-top:2px!important;}"
        # Collapse sidebar nav text labels when sidebar is narrow — show only icons
        "[data-testid='stSidebarNavLink'] span:last-child{"
        "  font-size:11px!important;}"
        # Make sidebar nav items compact
        "[data-testid='stSidebarNavLink']{"
        "  padding:4px 8px!important;min-height:32px!important;}"
        "</style>"
    )

    # ── Topbar HTML (built as plain string concatenation) ────────────
    # Build notifications before topbar and cache for all pages
    _notifs = _build_notifications() if st.session_state.get("logged_in") else []
    st.session_state["notifications"] = _notifs
    _n_count = len(_notifs)
    _n_urgent= sum(1 for n in _notifs if n.get("level")=="urgent")

    topbar = (
        "<div style='position:fixed;top:0;left:0;right:0;height:54px;"
        "background:white;border-bottom:1px solid #E5E7EB;"
        "box-shadow:0 1px 8px rgba(0,0,0,0.06);"
        "display:flex;align-items:center;padding:0 20px;"
        "z-index:999999;gap:12px;"
        "font-family:Inter,Segoe UI,sans-serif;'>"
        # Logo
        "<div style='display:flex;align-items:center;height:40px;min-width:230px;flex-shrink:0'>"
        + logo_html +
        "</div>"
        # Spacer
        "<div style='flex:1'></div>"
        # Right side
        "<div style='display:flex;align-items:center;gap:10px'>"
        # LIVE badge
        "<span style='font-size:10px;font-weight:700;letter-spacing:0.8px;"
        "background:var(--brand-light,#E8F5EE);color:var(--brand-primary,#006B3F);border:0.5px solid var(--brand-primary,#006B3F);"
        "border-radius:6px;padding:3px 8px;'>LIVE</span>"
        # Notification bell (computed before topbar)
        + (f"<div style='position:relative;margin-right:6px'>"
           f"<div style='width:30px;height:30px;border-radius:50%;background:rgba(0,0,0,0.05);"
           f"display:flex;align-items:center;justify-content:center;font-size:14px'>🔔</div>"
           f"<div style='position:absolute;top:-1px;right:-1px;"
           f"background:{'#E24B4A' if _n_urgent else '#F5A623'};"
           f"color:white;border-radius:50%;min-width:15px;height:15px;"
           f"font-size:9px;font-weight:700;display:flex;align-items:center;"
           f"justify-content:center'>{ _n_count}</div>"
           f"</div>" if _n_count else "")
        # User pill
        + "<div style='display:flex;align-items:center;gap:8px;"
        "background:#F3F4F6;border-radius:20px;padding:5px 12px 5px 6px;'>"
        # Avatar circle — initials (photo shown in sidebar)
        "<div style='width:28px;height:28px;border-radius:50%;"
        "background:linear-gradient(135deg,#006B3F,#1D9E75);"
        "display:flex;align-items:center;justify-content:center;"
        "color:white;font-size:11px;font-weight:800;flex-shrink:0;'>"
        + initials +
        "</div>"
        "<span style='font-size:13px;font-weight:600;color:#111827'>"
        + name +
        "</span>"
        "<span style='font-size:11px;color:#9CA3AF'>"
        + role +
        "</span>"
        "</div>"  # end user pill
        "</div>"  # end right side
        "</div>"  # end topbar
    )

    # ── Module group tabs bar (below topbar) ──────────────────────────
    # ud is already defined above in render_topbar
    from utils.core_audit import check_access as _ca
    _GROUP_DEFS = [
        ("🏆", "A2Z Perform",    "#006B3F",
         ["perform","cascade","products","optimize","branch_log"]),
        ("⚡", "A2Z Execute",    "#185FA5",
         ["execute","pipeline","sla","campaigns","cims","commission"]),
        ("🔗", "A2Z Integrate",  "#6B21A8",
         ["integrate","competitor","sbu","opex","people","export"]),
        ("⚙️", "Admin",           "#374151",
         ["admin"]),
    ]
    _visible_groups = [(icon, label, colour)
                       for icon, label, colour, mods in _GROUP_DEFS
                       if any(_ca(ud, m)[0] for m in mods)]

    if _visible_groups:
        _cur_grp = st.session_state.get("active_group","perform")
        _GK3 = {"🏆 A2Z Perform":"perform","⚡ A2Z Execute":"execute",
                "🔗 A2Z Integrate":"integrate","⚙️ Admin":"admin"}
        _BG3 = {"#006B3F":"rgba(0,107,63,0.08)","#185FA5":"rgba(24,95,165,0.08)",
                "#6B21A8":"rgba(107,33,168,0.08)","#374151":"rgba(55,65,81,0.06)"}
        pills_html = (
            "<div style='position:fixed;top:54px;"
            "left:var(--sidebar-width,21rem);right:0;height:36px;"
            "background:white;border-bottom:1px solid #E5E7EB;"
            "display:flex;align-items:center;gap:16px;"
            "z-index:999992;font-family:Inter,Segoe UI,sans-serif;padding:0 24px'>"
        )
        for icon, label, colour in _visible_groups:
            gk  = _GK3.get(icon+" "+label, "perform")
            act = (_cur_grp == gk)
            bg  = colour if act else _BG3.get(colour,"rgba(0,0,0,0.04)")
            fg  = "white" if act else colour
            brd = "none" if act else "1px solid "+colour+"30"
            pills_html += (
                "<div style='display:inline-flex;align-items:center;gap:5px;"
                "padding:5px 14px;background:"+bg+";border:"+brd+";"
                "border-radius:16px;font-size:11px;font-weight:"
                +("700" if act else "500")+";color:"+fg+";white-space:nowrap'>"
                "<span>"+icon+"</span><span>"+label+"</span></div>"
            )
        pills_html += "</div>"
        topbar = topbar + pills_html

    # Inject CSS to visually collapse non-active nav sections
    _ag = st.session_state.get("active_group","perform")
    _LABEL_MAP = {
        "perform":   "A2Z Perform",
        "execute":   "A2Z Execute",
        "integrate": "A2Z Integrate",
        "admin":     "Admin",
    }
    _active_label_txt = _LABEL_MAP.get(_ag, "A2Z Perform")
    # Build CSS that hides nav sections whose label doesn't match the active group
    # Streamlit nav section headers use data-testid="stSidebarNavSeparator"
    # Their text is in a span inside. We hide the whole section group.
    # Since we can't target by text in CSS alone, we use a JS-based approach
    # injected as a script tag in the markdown
    st.markdown(css + topbar, unsafe_allow_html=True)

    # ── Sidebar — group switcher FIRST, then logo ────────────────────
    # Group switcher must be added before st.navigation() to appear at top
    st.sidebar.markdown(
        "<div style='padding:10px 14px 8px;"
        "border-bottom:1px solid rgba(255,255,255,0.12);margin-bottom:6px;'>"
        "<div style='height:36px;display:flex;align-items:center'>"
        + logo_white_html +
        "</div>"
        "<div style='font-size:9px;color:rgba(255,255,255,0.4);margin-top:3px;"
        "letter-spacing:0.6px;font-weight:500'>"
        + (st.session_state.get("_bank_display","A2Z Blueprint")).upper()
        + "</div>"
        "</div>",
        unsafe_allow_html=True)


# Render on every page load
render_topbar()


# ── Session timeout enforcement (30 min idle) ─────────────────────
import datetime as _dt_timeout
if st.session_state.get("logged_in"):
    _last = st.session_state.get("last_activity", _dt_timeout.datetime.now())
    if (_dt_timeout.datetime.now() - _last).total_seconds() > 1800:  # 30 minutes
        _user_name = st.session_state.get("username","")
        for k in list(st.session_state.keys()): del st.session_state[k]
        st.session_state["_timeout_msg"] = f"Session expired after 30 minutes of inactivity."
        st.rerun()
    else:
        st.session_state["last_activity"] = _dt_timeout.datetime.now()

if st.session_state.get("_timeout_msg"):
    st.warning(f"⏱️ {st.session_state.pop('_timeout_msg')}")

# Store notifications in session_state so all pages can read them
if st.session_state.get("logged_in"):
    try:
        st.session_state["notifications"] = _build_notifications()
    except:
        st.session_state["notifications"] = []
    # ── In-app notification bell ─────────────────────────────────
    try:
        from utils.notifications import get_notifications, render_notification_bell as _rnb
        _ud_notif = st.session_state.get("user_data", {})
        _notifs   = get_notifications(
            str(_ud_notif.get("staff_code","")),
            _ud_notif.get("role",""),
            _ud_notif.get("unit",""))
        if _notifs:
            render_notification_bell(_notifs)
    except Exception: pass

# ── Build navigation dynamically based on user permissions ──────────
from utils.core_audit import check_access

_ud       = st.session_state.get("user_data", {})
_is_admin = _ud.get("is_admin", False)

# Active group — from query param (URL) or session_state
# Query param takes precedence so topbar link clicks work
_qp_group = st.query_params.get("g", "")
if _qp_group in ("perform","execute","integrate","admin"):
    st.session_state["active_group"] = _qp_group
elif "active_group" not in st.session_state:
    st.session_state["active_group"] = "perform"
_active_grp = st.session_state.get("active_group", "perform")

# ── A2Z Blueprint — Grouped Navigation ──────────────────────────────
# A2Z Perform  | A2Z Execute  | A2Z Integrate  | Admin
from streamlit import Page as _Page

# Track which page files have already been registered to ensure
# unique URL pathnames across all navigation groups.
def _pg(path, title, icon, module):
    _ok, _ = check_access(_ud, module)
    if not _ok: return None
    if not (_ud.get("is_admin") or _ud.get("can_view_all")):
        _dmods = _get_dept_modules(_ud)
        if module not in _dmods: return None
    try:
        import json as _jsnav
        from pathlib import Path as _Pnav
        _dmc_p = _Pnav("data") / "dept_module_config.json"
        if _dmc_p.exists():
            _dmc = _jsnav.loads(_dmc_p.read_text())
            _hidden = set(_dmc.get(_ud.get("department",""),{}).get("hidden_modules",[]))
            if module in _hidden: return None
    except Exception: pass
    _display_title = title
    try:
        import json as _jslbl
        from pathlib import Path as _Plbl
        _oc_p = _Plbl("data") / "org_config.json"
        if _oc_p.exists():
            _oc_lbl = _jslbl.loads(_oc_p.read_text())
            _custom = _oc_lbl.get("nav_labels", {}).get(module, "")
            if _custom: _display_title = _custom
    except Exception: pass
    return _Page(path, title=_display_title, icon=icon)

from utils.core_audit import (get_user_department as _get_dept,
                                get_dept_modules    as _get_dept_modules,
                                is_dept_super_user  as _is_dsu,
                                is_ict_admin        as _is_ict)

_dept          = _get_dept(_ud)
_is_admin_full = _ud.get("is_admin", False) or _ud.get("can_view_all", False)
_is_dsu_user   = _is_dsu(_ud)
_is_ict_user   = _is_ict(_ud)

def _dg(lst): return [p for p in lst if p]

# ── v10.199 — Manifest-driven navigation ──────────────────────────
# Replaces the v10.196-era hand-crafted 18-group structure (~390 lines)
# with manifest-derived nav (~150 lines). Source of truth is now
# pages/_manifest.json (v10.197) consumed via pages/_manifest_loader.py.
# Per master prompt v3.62 line 957: "prefer extending existing patterns
# over inventing new ones." Audit gate G160 (v10.198) locks the manifest
# completeness as permanent invariant.
try:
    from pages._manifest_loader import (
        list_departments as _list_departments,
        pages_in_department as _pages_in_department,
    )
    _MANIFEST_AVAILABLE = True
except Exception:
    _MANIFEST_AVAILABLE = False

# Map legacy user.department strings to one or more manifest dept_ids.
# Multiple manifest depts means user sees pages from all of them.
# v10.197 introduced 16 manifest dept_ids; legacy user.department strings
# are preserved for backward compat (no admin role data migration needed).
_USER_DEPT_TO_MANIFEST: Dict[str, List[str]] = {
    "Retail Banking":             ["sales_customer"],
    "Commercial & Corporate":     ["sales_customer"],
    "Credit":                     ["credit"],
    "Treasury":                   ["treasury_alm"],
    "Finance":                    ["finance"],
    "Risk & Compliance":          ["risk", "compliance_regulatory"],
    "Legal":                      ["legal"],
    "Operations":                 ["operations"],
    "People & HR":                ["people_hr"],
    "IT & Digital":               ["it_platform"],
    "Bancassurance":              ["sales_customer"],
    "Marketing":                  ["sales_customer"],
    "Internal Audit":             ["compliance_regulatory"],
    "Support Services":           ["operations"],
    "Executive":                  ["strategy_performance"],
    "Trade Finance":              ["trade_finance"],
    "Agency Banking":             ["sales_customer"],
    "Contact Centre":             ["sales_customer"],
    "Cybersecurity":              ["it_platform"],
    "Digital Financial Services": ["sales_customer"],
    "Diaspora & Special Segments":["sales_customer"],
    "Business Intelligence":      ["strategy_performance"],
}


def _build_dept_pages(dept_id: str, include_secondary: bool = True) -> list:
    """Return list of registered _Page objects for a manifest dept_id.
    Uses _pg() which enforces check_access + dept_module_config.json
    hidden-modules + org_config.json nav_labels customisation. None
    entries (denied access) are filtered."""
    if not _MANIFEST_AVAILABLE:
        return []
    pages = []
    seen_paths = set()  # de-dup within this section
    for fname, entry in _pages_in_department(dept_id, include_secondary=include_secondary):
        path = "pages/" + fname
        if path in seen_paths:
            continue
        seen_paths.add(path)
        page = _pg(path, entry["title"], entry["icon"], entry["current_module_key"])
        if page is not None:
            pages.append(page)
    return pages


# Build _nav_sections from manifest if available; fall back to a minimal
# "Home only" structure if the manifest is missing (defensive — should
# never happen in production since G160 enforces presence).
_nav_sections: Dict[str, list] = {}

if not _MANIFEST_AVAILABLE:
    # Defensive fallback — manifest missing, render only Home
    _home = _pg("pages/0_home.py", "Home", "🏠", "perform")
    if _home:
        _nav_sections["🏠 Home"] = [_home]
else:
    _depts = _list_departments()
    # Sort departments by their declared 'order' field for stable nav
    _ordered_dept_ids = sorted(_depts.keys(), key=lambda d: _depts[d].get("order", 999))

    if _is_admin_full:
        # Admin sees all 16 departments — primary-only assignment to
        # avoid same page appearing in multiple sections.
        for _dept_id in _ordered_dept_ids:
            _info = _depts[_dept_id]
            _section_label = _info["icon"] + " " + _info["label"]
            _section_pages = _build_dept_pages(_dept_id, include_secondary=False)
            if _section_pages:
                _nav_sections[_section_label] = _section_pages
    else:
        # Regular user — show Shared + their dept(s) + External + Admin (if DSU/ICT)
        # 1. Shared (always visible)
        _shared_info = _depts.get("shared")
        if _shared_info:
            _shared_pages = _build_dept_pages("shared", include_secondary=False)
            if _shared_pages:
                _nav_sections[_shared_info["icon"] + " " + _shared_info["label"]] = _shared_pages

        # 2. User's primary department(s) — include secondary visibility
        # so cross-department pages (e.g. IFRS 9, Fraud, CBK Returns)
        # appear in the user's nav per the manifest's secondary_visibility
        # field.
        _user_dept_ids = _USER_DEPT_TO_MANIFEST.get(_dept, ["sales_customer"])
        for _u_dept_id in _user_dept_ids:
            _u_info = _depts.get(_u_dept_id)
            if not _u_info:
                continue
            _u_label = _u_info["icon"] + " " + _u_info["label"]
            if _u_label in _nav_sections:
                continue  # already added (e.g. Risk & Compliance maps to 2 depts)
            _u_pages = _build_dept_pages(_u_dept_id, include_secondary=True)
            if _u_pages:
                _nav_sections[_u_label] = _u_pages

        # 3. External Intelligence (visible to all)
        _ext_info = _depts.get("external")
        if _ext_info:
            _ext_pages = _build_dept_pages("external", include_secondary=False)
            if _ext_pages:
                _nav_sections[_ext_info["icon"] + " " + _ext_info["label"]] = _ext_pages

        # 4. Admin — only for DSU/ICT users
        if _is_dsu_user or _is_ict_user:
            _admin_info = _depts.get("admin")
            if _admin_info:
                _admin_pages = _build_dept_pages("admin", include_secondary=False)
                if _admin_pages:
                    _nav_sections[_admin_info["icon"] + " " + _admin_info["label"]] = _admin_pages


# ── Deduplicate nav_sections before passing to st.navigation ────
# Belt-and-suspenders: even after removing universal pages from dept
# groups, deduplicate here using url_path to catch any remaining dupes.
_seen_urls = set()
_clean_sections = {}
for _sec_label, _sec_pages in _nav_sections.items():
    _clean_pages = []
    for _p in _sec_pages:
        if _p is None:
            continue
        _url = getattr(_p, "url_path", None)
        if _url is None:
            # Fallback: derive from the page's script path
            import os as _os_nav, re as _re_nav
            _src = str(getattr(_p, "_script_path", "") or "")
            _url = _re_nav.sub(r"^\d+_", "", _os_nav.path.basename(_src).replace(".py",""))
        if _url in _seen_urls:
            continue
        _seen_urls.add(_url)
        _clean_pages.append(_p)
    if _clean_pages:
        _clean_sections[_sec_label] = _clean_pages

if not _clean_sections:
    _clean_sections["🏠 Home"] = [st.Page("pages/0_home.py", title="Home", icon="🏠")]

try:
    pg = st.navigation(_clean_sections)
except Exception as _nav_err:
    st.error(f"Navigation error: {_nav_err}")
    pg = st.navigation({"🏠 Home": [st.Page("pages/0_home.py", title="Home", icon="🏠")]})

# Ensure first-time visitors land on Home (not last visited page)
if "nav_initialized" not in st.session_state:
    st.session_state["nav_initialized"] = True



pg.run()
