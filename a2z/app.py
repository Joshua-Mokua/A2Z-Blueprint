"""app.py — A2Z Platform entry point. Run: streamlit run app.py"""
import streamlit as st
from pathlib import Path

# ── Version stamp — wipes only manager objects when code is updated ──
_APP_VERSION = "2026.04.14.v3"
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
from utils.core import (
    UserManager, ExecuteManager, LeaveManager,
    PipelineManager, RIPipelineManager, ProductManager,
    run_escalation_scan, should_run_scan,
    audit_log, DATA_DIR, clean_code,
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
    initial_sidebar_state="expanded",
)

# ── Session state bootstrap ────────────────────────────────────────────
def _auto_load_cbs_data():
    """Load CBS actuals automatically at app startup — no upload needed."""
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

_init_managers()

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
    show_login()
    st.stop()

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

# ── Sidebar ────────────────────────────────────────────────────────────
from pages._sidebar import show_sidebar
show_sidebar()

# ── One-time permission safety migration ──────────────────────────
# Strips can_view_all from any account that isn't MD/Admin
# Runs on every app start but is effectively a no-op after first run
try:
    from utils.core import fix_view_all_permissions
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
    from utils.core import check_access as _ca
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
        "letter-spacing:0.6px;font-weight:500'>ECOBANK KENYA</div>"
        "</div>",
        unsafe_allow_html=True)


# Render on every page load
render_topbar()

# Store notifications in session_state so all pages can read them
if st.session_state.get("logged_in"):
    try:
        st.session_state["notifications"] = _build_notifications()
    except:
        st.session_state["notifications"] = []

# ── Build navigation dynamically based on user permissions ──────────
from utils.core import check_access

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

def _pg(path, title, icon, module):
    _ok, _ = check_access(_ud, module)
    return _Page(path, title=title, icon=icon) if _ok else None

# ── A2Z Perform ──────────────────────────────────────────────────────
_perform_group = [p for p in [
    _pg("pages/0_home.py",       "Home",             "🏠", "perform"),
    _pg("pages/12_cascade.py",   "Target Cascade",   "🎯", "cascade"),
    _pg("pages/1_perform.py",    "Perform",          "🏆", "perform"),
    _pg("pages/5_products.py",   "Products",         "🏷️",  "products"),
    _pg("pages/15_optimize.py",  "Branch Optimizer", "📐", "optimize"),
    _pg("pages/14_branch_log.py","Branch Daily Log", "📝", "branch_log"),
] if p]

# ── A2Z Execute ──────────────────────────────────────────────────────
_execute_group = [p for p in [
    _pg("pages/4_execute.py",    "Execute",          "⚡", "execute"),
    _pg("pages/3_pipeline.py",   "Pipeline",         "💼", "pipeline"),
    _pg("pages/13_sla.py",       "SLA Tracker",      "📋", "sla"),
    _pg("pages/17_campaigns.py", "Campaigns",        "🚀", "campaigns"),
    _pg("pages/18_cims.py",      "CIMS",             "📨", "cims"),
    _pg("pages/16_commission.py","Commission",       "💰", "commission"),
] if p]

# ── A2Z Integrate ────────────────────────────────────────────────────
_integrate_group = [p for p in [
    _pg("pages/6_integrate.py",  "Integrate",        "🔗", "integrate"),
    _pg("pages/11_competitor.py","Competitor Intel", "🔍", "competitor"),
    _pg("pages/9_sbu.py",        "SBU Performance",  "🏦", "sbu"),
    _pg("pages/10_opex.py",      "Operating Leverage","📉","opex"),
    _pg("pages/2_people.py",     "People",           "👥", "people"),
    _pg("pages/15_cbs.py",       "CBS Explorer",     "🏦", "perform"),
    _pg("pages/8_export.py",     "Export",           "📥", "export"),
] if p]

# ── Admin ─────────────────────────────────────────────────────────────
_admin_group = [p for p in [
    _pg("pages/7_admin.py",      "Admin",            "⚙️", "admin"),
] if p]

# ── Full navigation — all accessible modules always visible ──────────
_nav_sections = {}
if _perform_group:   _nav_sections["🏆 A2Z Perform"]   = _perform_group
if _execute_group:   _nav_sections["⚡ A2Z Execute"]   = _execute_group
if _integrate_group: _nav_sections["🔗 A2Z Integrate"] = _integrate_group
if _admin_group:     _nav_sections["⚙️ Admin"]          = _admin_group

if not _nav_sections:
    _visible_pages = [st.Page("pages/0_home.py", title="Home", icon="🏠")]
else:
    _visible_pages = [p for pages in _nav_sections.values() for p in pages]

try:
    pg = st.navigation(_nav_sections)
except TypeError:
    pg = st.navigation(_visible_pages)

# Ensure first-time visitors land on Home (not last visited page)
if "nav_initialized" not in st.session_state:
    st.session_state["nav_initialized"] = True



pg.run()
