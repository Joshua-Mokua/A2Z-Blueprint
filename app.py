"""app.py — A2Z Platform entry point. Run: streamlit run app.py"""
import streamlit as st
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


st.set_page_config(
    page_title="A2Z — Perform · Execute · Integrate",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

# ── Session state bootstrap ────────────────────────────────────────────
def _init_managers():
    if "user_manager"        not in st.session_state:
        st.session_state["user_manager"]        = UserManager()
    if "leave_manager"       not in st.session_state:
        st.session_state["leave_manager"]       = LeaveManager()
    if "pipeline_manager"    not in st.session_state:
        st.session_state["pipeline_manager"]    = PipelineManager()
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
    if "cascade_manager" not in st.session_state:
        try:
            st.session_state["cascade_manager"] = CascadeManager()
        except Exception:
            pass
    # Always recreate ExecuteManager so new methods are picked up after updates
    st.session_state["execute_manager"] = ExecuteManager()
    # Refresh execute data from disk each load
    em = st.session_state["execute_manager"]
    em.initiatives = em._load_list(em.init_file)
    em.ideas       = em._load_list(em.ideas_file)
    em.workstreams = em._load_dict(em.ws_file)

_init_managers()

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

# ── Page routing via st.navigation ────────────────────────────────────
# Streamlit >=1.29 multipage navigation
pg = st.navigation([
    # ── PERFORM ───────────────────────────────────────────────────────
    st.Page("pages/1_perform.py",    title="Perform",            icon="🏆"),
    st.Page("pages/9_sbu.py",        title="SBU Performance",    icon="🏦"),
    st.Page("pages/10_opex.py",      title="Operating Leverage", icon="📉"),
    st.Page("pages/12_cascade.py",    title="Target Cascade",     icon="🎯"),
    # ── PEOPLE & PIPELINE ─────────────────────────────────────────────
    st.Page("pages/2_people.py",     title="People",             icon="👥"),
    st.Page("pages/3_pipeline.py",   title="Pipeline",           icon="💼"),
    # ── EXECUTE ───────────────────────────────────────────────────────
    st.Page("pages/4_execute.py",    title="Execute",            icon="⚡"),
    # ── PRODUCTS ──────────────────────────────────────────────────────
    st.Page("pages/5_products.py",   title="Products",           icon="🏷️"),
    # ── INTEGRATE (MD & Executive view) ───────────────────────────────
    st.Page("pages/6_integrate.py",  title="Integrate",          icon="🔗"),
    st.Page("pages/11_competitor.py", title="Competitor Intel",   icon="🔍"),
    # ── ADMIN & EXPORT ────────────────────────────────────────────────
    # ── BRANCH OPERATIONS ────────────────────────────────────────────
    st.Page("pages/13_sla.py",         title="SLA Tracker",        icon="🎯"),
    st.Page("pages/14_branch_log.py",  title="Branch Daily Log",   icon="📝"),
    st.Page("pages/15_optimize.py",    title="Branch Optimizer",   icon="🏦"),
    st.Page("pages/16_commission.py",  title="Commission",         icon="💰"),
    st.Page("pages/17_campaigns.py",   title="Campaigns",          icon="🚀"),
    st.Page("pages/18_cims.py",         title="CIMS",               icon="📨"),
    # ── ADMIN & EXPORT ────────────────────────────────────────────────
    st.Page("pages/7_admin.py",        title="Admin",              icon="⚙️"),
    st.Page("pages/8_export.py",       title="Export",             icon="📥"),
])
pg.run()
