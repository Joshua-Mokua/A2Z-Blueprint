"""app.py — A2Z Platform entry point. Run: streamlit run app.py"""
import streamlit as st
from utils.core import (
    UserManager, ExecuteManager, LeaveManager, PipelineManager,
    RIPipelineManager, ValidationManager, StaffStatusManager,
    ProductManager, run_escalation_scan, should_run_scan,
    audit_log, DATA_DIR, clean_code,
    process_kpi_data, build_staff_scores, build_staff_registry,
)

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
    if "validation_manager"  not in st.session_state:
        st.session_state["validation_manager"]  = ValidationManager()
    if "staff_status_manager" not in st.session_state:
        st.session_state["staff_status_manager"] = StaffStatusManager()
    if "leave_manager"       not in st.session_state:
        st.session_state["leave_manager"]       = LeaveManager()
    if "pipeline_manager"    not in st.session_state:
        st.session_state["pipeline_manager"]    = PipelineManager()
    if "ri_pipeline_manager" not in st.session_state:
        st.session_state["ri_pipeline_manager"] = RIPipelineManager()
    if "product_manager"     not in st.session_state:
        st.session_state["product_manager"]     = ProductManager()
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
    st.Page("pages/1_perform.py",   title="Perform",            icon="🏆"),
    st.Page("pages/9_sbu.py",       title="SBU Performance",    icon="🏦"),
    st.Page("pages/2_people.py",    title="People",             icon="👥"),
    st.Page("pages/3_pipeline.py",  title="Pipeline",           icon="💼"),
    st.Page("pages/4_execute.py",   title="Execute",            icon="⚡"),
    st.Page("pages/5_products.py",  title="Products",           icon="🏷️"),
    st.Page("pages/6_integrate.py", title="Integrate",          icon="🔗"),
    st.Page("pages/7_admin.py",     title="Admin",              icon="⚙️"),
    st.Page("pages/8_export.py",    title="Export",             icon="📥"),
])
pg.run()
