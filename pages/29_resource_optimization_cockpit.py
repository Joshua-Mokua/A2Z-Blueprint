"""pages/29_resource_optimization_cockpit.py — Resource
Optimization Arc Cockpit (v10.190).

Phase 5 Resource Optimization Module closure — 13th module
closure in platform history (after Treasury v10.155, AML/
Compliance v10.169, Legal v10.179). Locks all 10 Resource
Optimization arc standards (ENH-156..ENH-165) and ratchets the
cluster against regression.

The page makes the 10 Resource Optimization arc engines
operator-driveable from the browser through 7 thematic tabs
grouping engines per workflow logic (G4 7-tab limit).

The companion FastAPI router `utils/api_resource_optimization.py`
exposes the same engine methods over JSON for the planned React
frontend. Cockpit and API share the engine layer as the source
of truth — same pattern as Treasury v10.155, Compliance v10.169,
and Legal v10.179.

DESIGN DISCIPLINE (carried forward from v10.179 Legal closure)
--------------------------------------------------------------
1. Streamlit/import fallback at top so module loads even when
   Streamlit isn't installed (sandbox-friendly)
2. require_access uses REAL signature: require_access(module: str,
   silent: bool = False). Module ID is "resource_optimization".
3. audit_log uses REAL signature: action, username, detail, module
4. @st.cache_resource caches engine instances at session level
5. Read-only display except for state-mutating actions which go
   through the explicit FastAPI POST endpoints (planned)

7 THEMATIC TAB STRUCTURE (G4 7-tab limit)
-----------------------------------------
1. 📊 Executive       — ExecutiveResourceDashboard (capstone)
2. 🏠 Work Mode       — WorkModeDeclarationEngine (ENH-156)
3. 📈 Forecast+TSL    — WorkloadForecasting + TSLOptimization
4. ⚖️ Balancing+Util  — CrossChannelBalancing + UtilizationDashboard
5. 💚 Wellbeing       — WellbeingIntegrationEngine (ENH-161)
6. 🧪 What-If+Invest  — HybridSchedulingSimulator + InvestmentCase
7. 🌱 Culture         — IntegrityCultureEngine (ENH-164)

This grouping reflects operational adjacency: Forecast pairs with
TSL because forecasts feed staffing plans; Balancing pairs with
Utilisation because balancing reads util observations; What-If
pairs with Investment Case because scenario projections feed the
NPV math.
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    import streamlit as st
    import pandas as pd
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None  # type: ignore
    pd = None  # type: ignore

# Engines — 10 Resource Optimization arc engines
from utils.work_mode_declaration import WorkModeDeclarationEngine
from utils.workload_forecasting import WorkloadForecastingEngine
from utils.tsl_optimization import TSLOptimizationEngine
from utils.cross_channel_balancing import CrossChannelBalancingEngine
from utils.utilization_dashboard import UtilizationDashboardEngine
from utils.wellbeing_integration import WellbeingIntegrationEngine
from utils.hybrid_scheduling_simulator import HybridSchedulingSimulator
from utils.resource_investment_case import (
    ResourceInvestmentCaseEngine)
from utils.integrity_culture import IntegrityCultureEngine
from utils.executive_resource_dashboard import (
    ExecutiveResourceDashboard)

try:
    from pages._shared import load_shared_state
    from pages._access import require_access
    from utils.core_audit import audit_log
    SHARED_AVAILABLE = True
except ImportError:
    SHARED_AVAILABLE = False

    def load_shared_state():
        return {}

    def require_access(module: str, silent: bool = False):
        return True

    def audit_log(action: str = "", username: str = "",
                  detail: str = "", module: str = ""):
        pass


# ---------------------------------------------------------------------------
# Engine factories — module-level singletons (cached when Streamlit
# is available)
# ---------------------------------------------------------------------------

def _build_engines():
    """Construct the 10 engines with their composition wiring."""
    work_mode = WorkModeDeclarationEngine()
    forecast = WorkloadForecastingEngine()
    tsl = TSLOptimizationEngine()
    balance = CrossChannelBalancingEngine(tsl_engine=tsl)
    util = UtilizationDashboardEngine()
    wellbeing = WellbeingIntegrationEngine(
        wellness_assessor=lambda staff: {},
        utilization_engine=util,
    )
    hybrid = HybridSchedulingSimulator(
        tsl_engine=tsl, utilization_engine=util,
        balancing_engine=balance,
    )
    invest = ResourceInvestmentCaseEngine()
    culture = IntegrityCultureEngine()
    executive = ExecutiveResourceDashboard(
        work_mode_engine=work_mode,
        workload_forecasting_engine=forecast,
        tsl_engine=tsl,
        balancing_engine=balance,
        utilization_engine=util,
        wellbeing_engine=wellbeing,
        hybrid_simulator=hybrid,
        investment_case_engine=invest,
        integrity_culture_engine=culture,
    )
    return {
        "work_mode": work_mode, "forecast": forecast,
        "tsl": tsl, "balance": balance, "util": util,
        "wellbeing": wellbeing, "hybrid": hybrid,
        "invest": invest, "culture": culture,
        "executive": executive,
    }


if STREAMLIT_AVAILABLE:
    @st.cache_resource
    def _engines():
        return _build_engines()
else:
    def _engines():
        return _build_engines()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def _render_summary(summary: dict, *, exclude: tuple = ()) -> None:
    """Thin wrapper kept for module-local naming compatibility — the
    real implementation lives in pages/_cockpit_render.py and is shared
    across all module-arc cockpits."""
    from pages._cockpit_render import render_summary
    render_summary(summary, exclude=exclude)


def render_executive_tab(engines):
    """Tab 1 — Executive Dashboard capstone (ENH-165)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("📊 Executive Resource Optimization Dashboard")
    snap = engines["executive"].snapshot(
        snapshot_id=f"cockpit_{datetime.now(timezone.utc).isoformat()}"
    )
    composite = snap.resource_optimization_health_index
    cols = st.columns(3)
    cols[0].metric("Composite Health Index",
                   f"{composite:.1f}" if composite else "n/a")
    cols[1].metric("Engines Attached", snap.n_engines_attached)
    cols[2].metric("Engines Available", snap.n_engines_available)

    st.markdown("##### Sub-index components")
    if snap.health_index_components:
        comp = snap.health_index_components
        if isinstance(comp, dict) and comp:
            for i in range(0, len(comp), 4):
                row = list(comp.items())[i:i + 4]
                cs = st.columns(len(row))
                for c, (k, v) in zip(cs, row):
                    label = k.replace("_", " ").title()
                    val = f"{v:.1f}" if isinstance(v, (int, float)) else str(v)
                    c.metric(label, val)
        else:
            st.info("No sub-index components available.")
    else:
        st.info("Insufficient signal coverage — composite "
                "index requires ≥2 sub-indices.")

    st.markdown("##### Sections")
    for section in snap.sections:
        marker = "✅ available" if section.available else "⚠️ unavailable"
        with st.expander(f"{section.title} — {marker}"):
            st.caption(section.notes)
            if section.payload:
                _render_summary(section.payload)


def render_work_mode_tab(engines):
    """Tab 2 — Work Mode Declarations (ENH-156)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("🏠 Work Mode Declarations")
    _render_summary(engines["work_mode"].board_summary())


def render_forecast_tsl_tab(engines):
    """Tab 3 — Forecasting + TSL (ENH-157, ENH-158)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("📈 Workload Forecasting & Service-Level "
                 "Optimization")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Forecasting (ENH-157)**")
        _render_summary(engines["forecast"].board_summary())
    with col2:
        st.markdown("**TSL Optimization (ENH-158)**")
        _render_summary(engines["tsl"].board_summary())


def render_balancing_util_tab(engines):
    """Tab 4 — Balancing + Utilisation (ENH-159, ENH-160)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("⚖️ Cross-Channel Balancing & Utilization "
                 "Dashboard")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Cross-Channel Balancing (ENH-159)**")
        _render_summary(engines["balance"].board_summary())
    with col2:
        st.markdown("**Utilization (ENH-160)**")
        _render_summary(engines["util"].board_summary())


def render_wellbeing_tab(engines):
    """Tab 5 — Wellbeing Integration (ENH-161)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("💚 Wellbeing Early-Warning Integration")
    st.caption(
        "Privacy posture: n_respondents < 5 → suppressed; no "
        "individual names ever appear in team outputs; opt-out "
        "respected and counted as absent. No clinical claims.")
    _render_summary(engines["wellbeing"].board_summary())


def render_whatif_invest_tab(engines):
    """Tab 6 — What-If + Investment Case (ENH-162, ENH-163)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("🧪 What-If Scenarios & Investment Case "
                 "Generator")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Hybrid Scheduling Simulator (ENH-162)**")
        _render_summary(engines["hybrid"].board_summary())
    with col2:
        st.markdown("**Investment Case Generator (ENH-163)**")
        _render_summary(engines["invest"].board_summary())


def render_culture_tab(engines):
    """Tab 7 — Integrity Culture (ENH-164)."""
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("🌱 Integrity Culture Score & Benchmarking")
    st.caption(
        "Operator-supplied indicators only — no NLP on emails/"
        "chat, no behavioural telemetry, no automated surveys.")
    _render_summary(engines["culture"].board_summary())


def main():
    if not STREAMLIT_AVAILABLE:
        return

    st.set_page_config(
        page_title="Resource Optimization Arc Cockpit",
        page_icon="🎯", layout="wide",
    )

    if SHARED_AVAILABLE:
        load_shared_state()
        if not require_access("resource_optimization", silent=True):
            st.error("Access denied — Resource Optimization role "
                     "required.")
            return

    st.title("🎯 Resource Optimization Arc Cockpit")
    st.caption(
        "Phase 5 Module — 10 standards (ENH-156..165). Capstone "
        "engine: ExecutiveResourceDashboard. Closure: v10.190."
    )

    audit_log(
        action="open_resource_optimization_cockpit",
        username="cockpit_user",
        detail="page load",
        module="resource_optimization",
    )

    engines = _engines()

    tabs = st.tabs([
        "📊 Executive", "🏠 Work Mode", "📈 Forecast+TSL",
        "⚖️ Balancing+Util", "💚 Wellbeing", "🧪 What-If+Invest",
        "🌱 Culture",
    ])

    with tabs[0]:
        render_executive_tab(engines)
    with tabs[1]:
        render_work_mode_tab(engines)
    with tabs[2]:
        render_forecast_tsl_tab(engines)
    with tabs[3]:
        render_balancing_util_tab(engines)
    with tabs[4]:
        render_wellbeing_tab(engines)
    with tabs[5]:
        render_whatif_invest_tab(engines)
    with tabs[6]:
        render_culture_tab(engines)


# Streamlit page protocol
if STREAMLIT_AVAILABLE:
    main()
