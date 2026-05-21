"""utils.api_resource_optimization — FastAPI router for the
Resource Optimization arc (v10.190).

Exposes the 10 Resource Optimization arc engines (ENH-156..165)
as JSON-serializable HTTP endpoints with JWT authentication.
React-ready surface for the planned frontend.

DESIGN CONTRACT (mirrors utils/api_legal.py from v10.179)
---------------------------------------------------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Each endpoint calls a single engine method and returns a dict
3. Engine layer is the source of truth for both this API and the
   Streamlit cockpit (pages/29_resource_optimization_cockpit.py)
4. Audit logging via `_audit_resopt(action, user, detail)` after
   every successful endpoint call
5. Read-only contract — every endpoint here is GET. State-changing
   methods (declare_*, set_target, submit_*, score_*) become
   explicit POST endpoints in future increments with proper
   Pydantic request models.

V10.190 SCOPE — READ-ONLY GET ENDPOINTS
---------------------------------------
All 10 engines fully active and have `board_summary()` returning
a JSON-serialisable dict — that's the safe verified surface for
closure. The capstone /board endpoint composes the 10
sub-summaries into a single payload via the
ExecutiveResourceDashboard aggregator (ENH-165).

ENDPOINT MAP (all GET, all JWT-protected)
-----------------------------------------
  GET /api/resource-optimization/board                  cross-engine pack
  GET /api/resource-optimization/work-mode/board        ENH-156
  GET /api/resource-optimization/forecast/board         ENH-157
  GET /api/resource-optimization/tsl/board              ENH-158
  GET /api/resource-optimization/balancing/board        ENH-159
  GET /api/resource-optimization/utilization/board      ENH-160
  GET /api/resource-optimization/wellbeing/board        ENH-161
  GET /api/resource-optimization/hybrid-sim/board       ENH-162
  GET /api/resource-optimization/investment/board       ENH-163
  GET /api/resource-optimization/culture/board          ENH-164
  GET /api/resource-optimization/executive/snapshot     ENH-165 capstone
"""
from __future__ import annotations

from typing import Any, Dict

# ---------------------------------------------------------------------------
# FastAPI import shim (mirrors api_legal pattern)
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, Depends, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

    class _DummyRouter:
        def __init__(self, **kwargs): pass
        def get(self, *a, **k):
            def _decorator(fn): return fn
            return _decorator
        def post(self, *a, **k):
            def _decorator(fn): return fn
            return _decorator

    def APIRouter(*a, **kwargs):  # type: ignore
        return _DummyRouter()

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Depends(x):  # type: ignore
        return x


# ---------------------------------------------------------------------------
# JWT auth shim (mirrors api_legal pattern)
# ---------------------------------------------------------------------------

try:
    from utils.auth_jwt import get_current_user
except ImportError:
    def get_current_user():
        return {"username": "system", "role": "admin"}


# ---------------------------------------------------------------------------
# Engine factories — module-level singletons cached for the API process
# ---------------------------------------------------------------------------

from utils.work_mode_declaration import WorkModeDeclarationEngine
from utils.workload_forecasting import WorkloadForecastingEngine
from utils.tsl_optimization import TSLOptimizationEngine
from utils.cross_channel_balancing import CrossChannelBalancingEngine
from utils.utilization_dashboard import UtilizationDashboardEngine
from utils.wellbeing_integration import WellbeingIntegrationEngine
from utils.hybrid_scheduling_simulator import HybridSchedulingSimulator
from utils.resource_investment_case import ResourceInvestmentCaseEngine
from utils.integrity_culture import IntegrityCultureEngine
from utils.executive_resource_dashboard import (
    ExecutiveResourceDashboard,
)


_work_mode = WorkModeDeclarationEngine()
_forecast = WorkloadForecastingEngine()
_tsl = TSLOptimizationEngine()
_balance = CrossChannelBalancingEngine(tsl_engine=_tsl)
_util = UtilizationDashboardEngine()
_wellbeing = WellbeingIntegrationEngine(
    wellness_assessor=lambda staff: {},
)
_hybrid = HybridSchedulingSimulator(tsl_engine=_tsl)
_invest = ResourceInvestmentCaseEngine()
_culture = IntegrityCultureEngine()
_executive = ExecutiveResourceDashboard(
    work_mode_engine=_work_mode,
    workload_forecasting_engine=_forecast,
    tsl_engine=_tsl,
    balancing_engine=_balance,
    utilization_engine=_util,
    wellbeing_engine=_wellbeing,
    hybrid_simulator=_hybrid,
    investment_case_engine=_invest,
    integrity_culture_engine=_culture,
)


# ---------------------------------------------------------------------------
# Audit logging shim
# ---------------------------------------------------------------------------

def _audit_resopt(action: str, user: Dict[str, Any],
                  detail: str = "") -> None:
    """Audit log every successful endpoint call. Module is
    'resource_optimization'."""
    try:
        from utils.audit import audit_log
        audit_log(action=action,
                  username=user.get("username", "unknown"),
                  detail=detail, module="resource_optimization")
    except Exception:
        # Audit-log failures must not break API responses; the
        # cockpit-side audit infrastructure is separately monitored.
        pass


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/resource-optimization",
    tags=["resource_optimization"],
)


# ---------- cross-engine board pack ----------

@router.get("/board")
def get_resource_optimization_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cross-engine Resource Optimization arc board pack —
    single call to fetch summaries from all 10 engines."""
    payload = {
        "work_mode":   _work_mode.board_summary(),
        "forecast":    _forecast.board_summary(),
        "tsl":         _tsl.board_summary(),
        "balancing":   _balance.board_summary(),
        "utilization": _util.board_summary(),
        "wellbeing":   _wellbeing.board_summary(),
        "hybrid_sim":  _hybrid.board_summary(),
        "investment":  _invest.board_summary(),
        "culture":     _culture.board_summary(),
        "executive":   _executive.board_summary(),
    }
    _audit_resopt(
        "GET /api/resource-optimization/board", user,
        "cross-engine board pack",
    )
    return payload


# ---------- per-engine board endpoints ----------

@router.get("/work-mode/board")
def get_work_mode_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-156 — Work Mode Declarations board."""
    _audit_resopt(
        "GET /api/resource-optimization/work-mode/board", user)
    return _work_mode.board_summary()


@router.get("/forecast/board")
def get_forecast_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-157 — Workload Forecasting board."""
    _audit_resopt(
        "GET /api/resource-optimization/forecast/board", user)
    return _forecast.board_summary()


@router.get("/tsl/board")
def get_tsl_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-158 — Service Level Optimization board."""
    _audit_resopt("GET /api/resource-optimization/tsl/board", user)
    return _tsl.board_summary()


@router.get("/balancing/board")
def get_balancing_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-159 — Cross-Channel Balancing board."""
    _audit_resopt(
        "GET /api/resource-optimization/balancing/board", user)
    return _balance.board_summary()


@router.get("/utilization/board")
def get_utilization_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-160 — Utilization Dashboard board."""
    _audit_resopt(
        "GET /api/resource-optimization/utilization/board", user)
    return _util.board_summary()


@router.get("/wellbeing/board")
def get_wellbeing_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-161 — Wellbeing Integration board."""
    _audit_resopt(
        "GET /api/resource-optimization/wellbeing/board", user)
    return _wellbeing.board_summary()


@router.get("/hybrid-sim/board")
def get_hybrid_sim_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-162 — What-If Hybrid Scheduling Simulator board."""
    _audit_resopt(
        "GET /api/resource-optimization/hybrid-sim/board", user)
    return _hybrid.board_summary()


@router.get("/investment/board")
def get_investment_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-163 — Resource Investment Case Generator board."""
    _audit_resopt(
        "GET /api/resource-optimization/investment/board", user)
    return _invest.board_summary()


@router.get("/culture/board")
def get_culture_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-164 — Integrity Culture board."""
    _audit_resopt(
        "GET /api/resource-optimization/culture/board", user)
    return _culture.board_summary()


@router.get("/executive/snapshot")
def get_executive_snapshot(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-165 — Executive Resource Optimization Dashboard
    snapshot. Composes the 9 prior arc engines into a single
    capstone view with composite health index."""
    snap = _executive.snapshot(snapshot_id="api_call")
    _audit_resopt(
        "GET /api/resource-optimization/executive/snapshot",
        user,
        f"composite={snap.resource_optimization_health_index}",
    )
    return snap.to_dict()
