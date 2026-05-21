"""utils.api_treasury — FastAPI router for the Treasury arc (v10.154).

Exposes the 12 Treasury-arc engines (ENH-231..240, ENH-LR-001, ENH-TRS-R1..R6,
CBK-PG-05-LCR) as JSON-serializable HTTP endpoints with JWT authentication.
Provides the React-ready surface for the planned frontend.

DESIGN CONTRACT (mirrors utils/api_strategy.py from v10.141 and
utils/api_product.py from v10.151)
-----------------------------------------------------------------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Each endpoint calls a single engine method and returns a dict
3. Engine is the source of truth for both this API and the
   Streamlit cockpit (v10.155 will ship pages/26_treasury_arc_cockpit.py)
4. Audit logging via `_audit_treasury(action, user, detail)` after
   every successful endpoint call — same pattern as api_product / api_strategy
5. Read-only contract — no endpoint mutates engine state in v10.154.
   State-changing methods (register_*, run_*, mark_executed) become
   explicit POST endpoints in v10.155 closure batch with proper Pydantic
   request models

V10.154 SCOPE — READ-ONLY GET ENDPOINTS ONLY
---------------------------------------------
The honest scope decision: every Treasury engine has a zero-arg
`board_summary()` method that returns a dict — that's the safe,
verified surface for the read API. State-required methods (taking
dataclass tuples like `Tuple[HQLAHolding, ...]` or requiring prior
register_* calls to populate engine state) are NOT exposed as
endpoints in v10.154 because:

  (a) they require typed payload validation that needs proper Pydantic
      model definitions matching the engine's frozen dataclasses
  (b) request → engine state → query is multi-step, needs careful
      session/persistence design
  (c) shipping POST endpoints with placeholder validation would risk
      the same v10.153.1-style runtime errors that would only surface
      in real testing

V10.155 (closure) ships POST endpoints alongside the cockpit, with
the engine-state design solidified by then.

ENDPOINT MAP (all GET, all JWT-protected)
------------------------------------------
  GET /api/treasury/board                          # cross-engine board pack
  GET /api/treasury/intelligence/yield-curve       ENH-231 yield_curve
  GET /api/treasury/intelligence/liquidity         ENH-232 liquidity_metrics
  GET /api/treasury/intelligence/income            ENH-234/236 income_by_instrument
  GET /api/treasury/intelligence/alm-dashboard     ENH-233 alm_dashboard_data
  GET /api/treasury/alm/board                      ENH-233 board_summary
  GET /api/treasury/alm/outlier-scenarios          ENH-233 outlier_scenarios
  GET /api/treasury/products/board                 ENH-234 board_summary
  GET /api/treasury/agents/board                   ENH-240 board_summary
  GET /api/treasury/connectivity/board             ENH-TRS-R1 board_summary
  GET /api/treasury/digital-assets/board           ENH-TRS-R2 board_summary
  GET /api/treasury/dashboard/board                ENH-238 board_summary
  GET /api/treasury/unified/board                  ENH-TRS-R4 board_summary
  GET /api/treasury/unified/positions              ENH-TRS-R4 positions
  GET /api/treasury/liquidity-risk/lcr             CBK-PG-05-LCR (placeholder)
  GET /api/treasury/islamic/board                  ENH-239 board_summary
  GET /api/treasury/islamic/non-compliant          ENH-239 non_compliant_products
  GET /api/treasury/climate/board                  ENH-TRS-R6 board_summary
  GET /api/treasury/climate/all-limits             ENH-TRS-R6 compute_all_limits

USAGE
-----
Mount in parent FastAPI app via:
    from utils.api_treasury import router as treasury_router
    app.include_router(treasury_router)

A React frontend can fetch any endpoint with:
    fetch('/api/treasury/dashboard/board', {
      headers: { Authorization: `Bearer ${jwt}` }
    })
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict

try:
    from fastapi import APIRouter, Depends, HTTPException, Query
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    Depends = None  # type: ignore
    HTTPException = Exception  # type: ignore
    Query = lambda *a, **kw: None  # type: ignore

from utils.treasury_intelligence import TreasuryIntelligenceEngine
from utils.treasury_alm import TreasuryALMEngine
from utils.treasury_dashboard import TreasuryDashboardEngine
from utils.treasury_products import TreasuryProductsEngine
from utils.treasury_agents import AgentOrchestrator
from utils.treasury_connectivity import TreasuryConnectivityEngine
from utils.treasury_digital_assets import DigitalAssetTreasuryEngine
from utils.treasury_unified_platform import UnifiedTreasuryPlatform
from utils.liquidity_risk import LiquidityRiskEngine
from utils.liquidity_stress import LiquidityStressEngine
from utils.islamic_treasury import IslamicTreasuryEngine
from utils.climate_treasury_limits import ClimateTreasuryLimitsEngine

try:
    from utils.api_auth import get_current_user
except ImportError:
    def get_current_user():
        return {"username": "test", "role": "admin"}

try:
    from utils.core_audit import audit_log
except ImportError:
    def audit_log(action: str, username: str, detail: str = "",
                    module: str = "", before: str = "",
                    after: str = ""):
        pass


# ---------------------------------------------------------------------------
# Audit helper (matches the real audit_log signature, unlike v10.153.1)
# ---------------------------------------------------------------------------

def _audit_treasury(action: str, user: Dict[str, Any],
                      detail: str = "") -> None:
    """Wrapper around audit_log using the real signature.

    Real signature: audit_log(action, username, detail, module, before, after).
    Verified against utils/core_audit.py — NOT inventing kwargs this time.
    """
    try:
        audit_log(
            action=f"api_treasury.{action}",
            username=(user.get("username", "unknown")
                       if user else "unknown"),
            detail=detail,
            module="treasury")
    except Exception:
        # Audit failure must never crash an API response
        pass


# ---------------------------------------------------------------------------
# Today helper for default date params
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Router (only when FastAPI is available)
# ---------------------------------------------------------------------------

if FASTAPI_AVAILABLE:
    from pydantic import BaseModel, Field
    from typing import List, Optional

    router = APIRouter(prefix="/api/treasury", tags=["treasury"])

    # Engine instances at module load (DI pattern)
    _intel = TreasuryIntelligenceEngine()
    _alm = TreasuryALMEngine()
    _dashboard = TreasuryDashboardEngine()
    _products = TreasuryProductsEngine()
    _agents = AgentOrchestrator()
    _connectivity = TreasuryConnectivityEngine()
    _digital_assets = DigitalAssetTreasuryEngine()
    _unified = UnifiedTreasuryPlatform()
    # liquidity_risk uses static-style methods; no instance needed
    _liquidity_stress = LiquidityStressEngine()
    _islamic = IslamicTreasuryEngine()
    _climate = ClimateTreasuryLimitsEngine()

    # ----------------------------------------------------------------
    # Cross-engine board endpoint — top-level summary
    # ----------------------------------------------------------------

    @router.get("/board")
    def treasury_board(user=Depends(get_current_user)):
        """Cross-engine Treasury board pack — composes board_summary
        from every engine that exposes it. Honest engine_status map
        (mirrors v10.151 ProductAnalyticsDashboard pattern) so partial
        failure surfaces with reason rather than blanking the response."""
        engine_status: Dict[str, Dict[str, Any]] = {}
        sections: Dict[str, Any] = {}
        for label, fn in (
            ("alm", _alm.board_summary),
            ("dashboard", _dashboard.board_summary),
            ("products", _products.board_summary),
            ("agents", _agents.board_summary),
            ("connectivity", _connectivity.board_summary),
            ("unified", _unified.board_summary),
            ("islamic", _islamic.board_summary),
            ("climate", _climate.board_summary),
        ):
            try:
                sections[label] = fn()
                engine_status[label] = {"ok": True}
            except Exception as e:
                sections[label] = None
                engine_status[label] = {
                    "ok": False,
                    "error_type": type(e).__name__,
                    "error_msg": str(e)[:200],
                }
        all_healthy = all(s.get("ok") for s in engine_status.values())
        result = {
            "generated_at_utc": datetime.now(
                timezone.utc).isoformat(),
            "all_healthy": all_healthy,
            "sections": sections,
            "engine_status": engine_status,
        }
        _audit_treasury("board", user,
                          f"all_healthy={all_healthy}")
        return result

    # ----------------------------------------------------------------
    # ENH-231/232/233/234/236 Treasury Intelligence
    # ----------------------------------------------------------------

    @router.get("/intelligence/yield-curve")
    def intel_yield_curve(
        as_of_date: str = Query(default=None,
                                  description="YYYY-MM-DD; "
                                              "defaults to today"),
        currency: str = Query(default="KES"),
        user=Depends(get_current_user),
    ):
        as_of = as_of_date or _today()
        result = _intel.yield_curve(as_of_date=as_of,
                                       currency=currency)
        _audit_treasury("intel.yield_curve", user,
                          f"as_of={as_of} ccy={currency}")
        return result

    @router.get("/intelligence/liquidity")
    def intel_liquidity(
        as_of_date: str = Query(default=None),
        user=Depends(get_current_user),
    ):
        as_of = as_of_date or _today()
        result = _intel.liquidity_metrics(as_of_date=as_of)
        _audit_treasury("intel.liquidity", user, f"as_of={as_of}")
        return result

    @router.get("/intelligence/income")
    def intel_income(
        period: str = Query(default=None,
                              description="YYYY-MM; "
                                            "defaults to current month"),
        user=Depends(get_current_user),
    ):
        p = period or datetime.now(timezone.utc).strftime("%Y-%m")
        result = _intel.income_by_instrument(period=p)
        _audit_treasury("intel.income", user, f"period={p}")
        return result

    @router.get("/intelligence/alm-dashboard")
    def intel_alm_dashboard(
        as_of_date: str = Query(default=None),
        user=Depends(get_current_user),
    ):
        as_of = as_of_date or _today()
        result = _intel.alm_dashboard_data(as_of_date=as_of)
        _audit_treasury("intel.alm_dashboard", user,
                          f"as_of={as_of}")
        return result

    # ----------------------------------------------------------------
    # ENH-233 ALM
    # ----------------------------------------------------------------

    @router.get("/alm/board")
    def alm_board(user=Depends(get_current_user)):
        result = _alm.board_summary()
        _audit_treasury("alm.board", user, "")
        return result

    @router.get("/alm/outlier-scenarios")
    def alm_outliers(user=Depends(get_current_user)):
        result = _alm.outlier_scenarios()
        # Engine returns Tuple[...] of frozen dataclasses; convert to
        # plain dicts for JSON. Use vars() since these are slots/dataclasses.
        if isinstance(result, tuple):
            try:
                result_json = [
                    {k: getattr(item, k) for k in
                       getattr(item, "__dataclass_fields__", {}).keys()}
                    for item in result]
            except Exception:
                result_json = [str(item) for item in result]
        else:
            result_json = result
        _audit_treasury("alm.outliers", user,
                          f"n={len(result_json) if hasattr(result_json,'__len__') else 0}")
        return {"outlier_scenarios": result_json}

    # ----------------------------------------------------------------
    # ENH-234 Products
    # ----------------------------------------------------------------

    @router.get("/products/board")
    def products_board(user=Depends(get_current_user)):
        result = _products.board_summary()
        _audit_treasury("products.board", user, "")
        return result

    # ----------------------------------------------------------------
    # ENH-240 Agents
    # ----------------------------------------------------------------

    @router.get("/agents/board")
    def agents_board(user=Depends(get_current_user)):
        result = _agents.board_summary()
        _audit_treasury("agents.board", user, "")
        return result

    # ----------------------------------------------------------------
    # ENH-TRS-R1 Connectivity
    # ----------------------------------------------------------------

    @router.get("/connectivity/board")
    def connectivity_board(user=Depends(get_current_user)):
        result = _connectivity.board_summary()
        _audit_treasury("connectivity.board", user, "")
        return result

    # ----------------------------------------------------------------
    # ENH-TRS-R2 Digital Assets
    # ----------------------------------------------------------------

    @router.get("/digital-assets/board")
    def digital_assets_board(user=Depends(get_current_user)):
        # board_summary may not exist on this engine — fall back to
        # health probe if missing
        if hasattr(_digital_assets, "board_summary"):
            result = _digital_assets.board_summary()
        else:
            result = {
                "ok": False,
                "fallback_reason": "engine_lacks_board_summary",
                "engine": "DigitalAssetTreasuryEngine",
            }
        _audit_treasury("digital_assets.board", user, "")
        return result

    # ----------------------------------------------------------------
    # ENH-238 Dashboard
    # ----------------------------------------------------------------

    @router.get("/dashboard/board")
    def dashboard_board(user=Depends(get_current_user)):
        result = _dashboard.board_summary()
        _audit_treasury("dashboard.board", user, "")
        return result

    # ----------------------------------------------------------------
    # ENH-TRS-R4 Unified Platform
    # ----------------------------------------------------------------

    @router.get("/unified/board")
    def unified_board(user=Depends(get_current_user)):
        result = _unified.board_summary()
        _audit_treasury("unified.board", user, "")
        return result

    @router.get("/unified/positions")
    def unified_positions(user=Depends(get_current_user)):
        positions = _unified.positions()
        # Convert tuple of dataclasses to list of dicts
        if isinstance(positions, tuple):
            try:
                positions_json = [
                    {k: getattr(p, k) for k in
                       getattr(p, "__dataclass_fields__", {}).keys()}
                    for p in positions]
            except Exception:
                positions_json = [str(p) for p in positions]
        else:
            positions_json = positions
        _audit_treasury(
            "unified.positions", user,
            f"n={len(positions_json) if hasattr(positions_json,'__len__') else 0}")
        return {"positions": positions_json}

    # ----------------------------------------------------------------
    # CBK-PG-05-LCR Liquidity Risk
    # NOTE: liquidity_risk methods take Lists of dataclasses; v10.154
    # exposes a placeholder that returns the available methods + their
    # parameter shapes. Real LCR computation needs typed Pydantic models
    # and posted state — comes in v10.155 with proper request models.
    # ----------------------------------------------------------------

    @router.get("/liquidity-risk/methods")
    def liquidity_risk_methods(user=Depends(get_current_user)):
        """Surface the available state-loading + compute endpoints
        and any remaining deferred methods. v10.157 update: the
        register_yield_curve / register_bond_position /
        register_mm_position / register_connector / register_mmf
        endpoints ARE NOW LIVE alongside MTM compute endpoints
        (mtm_fx_position, mtm_bond, net_fx_exposure, get_yield_curve).
        Phase 2 Treasury write-side surface is COMPLETE.
        """
        result = {
            "engine_layer": "TreasuryProductsEngine + "
                              "TreasuryConnectivityEngine + "
                              "TreasuryALMEngine + "
                              "LiquidityRiskEngine + "
                              "ClimateTreasuryLimitsEngine + "
                              "AgentOrchestrator",
            "live_state_loaders": [
                # v10.156 — simple-shape state loaders
                {"endpoint": "POST /api/treasury/alm/register-hqla",
                 "input_shape": "RegisterHQLARequest",
                 "shipped_in": "v10.156"},
                {"endpoint": "POST /api/treasury/alm/add-inflow",
                 "input_shape": "CashFlowRequest",
                 "shipped_in": "v10.156"},
                {"endpoint": "POST /api/treasury/alm/add-outflow",
                 "input_shape": "CashFlowRequest",
                 "shipped_in": "v10.156"},
                {"endpoint": "POST /api/treasury/alm/register-deposit",
                 "input_shape": "RegisterDepositRequest",
                 "shipped_in": "v10.156"},
                {"endpoint": "POST /api/treasury/alm/register-rates-position",
                 "input_shape": "RegisterRatesPositionRequest",
                 "shipped_in": "v10.156"},
                {"endpoint": "POST /api/treasury/products/register-fx-position",
                 "input_shape": "RegisterFXPositionRequest",
                 "shipped_in": "v10.156"},
                # v10.157 — complex-shape state loaders
                {"endpoint": "POST /api/treasury/products/register-yield-curve",
                 "input_shape": "RegisterYieldCurveRequest "
                                  "(nested YieldCurvePointModel list)",
                 "shipped_in": "v10.157"},
                {"endpoint": "POST /api/treasury/products/register-bond-position",
                 "input_shape": "RegisterBondPositionRequest "
                                  "(IFRS9 classification enum)",
                 "shipped_in": "v10.157"},
                {"endpoint": "POST /api/treasury/products/register-mm-position",
                 "input_shape": "RegisterMMPositionRequest",
                 "shipped_in": "v10.157"},
                {"endpoint": "POST /api/treasury/connectivity/register-connector",
                 "input_shape": "RegisterConnectorRequest "
                                  "(supported_formats list converted "
                                  "to FrozenSet[MessageFormat])",
                 "shipped_in": "v10.157"},
                {"endpoint": "POST /api/treasury/connectivity/register-mmf",
                 "input_shape": "RegisterMMFRequest",
                 "shipped_in": "v10.157"},
            ],
            "live_compute_endpoints": [
                {"endpoint": "POST /api/treasury/alm/run-lcr",
                 "shipped_in": "v10.155"},
                {"endpoint": "POST /api/treasury/alm/run-repricing-gap",
                 "shipped_in": "v10.155"},
                {"endpoint": "POST /api/treasury/alm/run-decay",
                 "shipped_in": "v10.155"},
                {"endpoint": "POST /api/treasury/agents/approve",
                 "shipped_in": "v10.155"},
                {"endpoint": "POST /api/treasury/agents/reject",
                 "shipped_in": "v10.155"},
                {"endpoint": "POST /api/treasury/climate/check-breach",
                 "shipped_in": "v10.155"},
                {"endpoint": "POST /api/treasury/products/mtm-fx",
                 "shipped_in": "v10.157"},
                {"endpoint": "POST /api/treasury/products/mtm-bond",
                 "shipped_in": "v10.157"},
                {"endpoint": "GET /api/treasury/products/net-fx-exposure",
                 "shipped_in": "v10.157"},
                {"endpoint": "GET /api/treasury/products/yield-curve/{id}",
                 "shipped_in": "v10.157"},
                {"endpoint": "POST /api/treasury/liquidity-risk/lcr",
                 "shipped_in": "v10.158"},
                {"endpoint": "POST /api/treasury/liquidity-risk/nsfr",
                 "shipped_in": "v10.158"},
                {"endpoint": "POST /api/treasury/liquidity-risk/hqla-value",
                 "shipped_in": "v10.158"},
            ],
            "remaining_deferred": [
                {"name": "register_agent",
                 "engine": "AgentOrchestrator",
                 "input": "Agent (engine-specific class with custom "
                            "__call__ contract)",
                 "deferred_to": "v10.159+",
                 "reason": ("Agents are Python objects with custom "
                              "behavior, not data. Registration via "
                              "API would require code-mobility design "
                              "(not currently in scope).")},
                {"name": "register_product (Islamic)",
                 "engine": "IslamicTreasuryEngine",
                 "input": "IslamicProduct with Sharia-compliance "
                            "metadata",
                 "deferred_to": "v10.159+",
                 "reason": ("Islamic product schema is more "
                              "elaborate than the bond/fx/mm shapes; "
                              "deferred for dedicated review with "
                              "Sharia-board input on which fields "
                              "the API surface should accept.")},
                {"name": "Digital Assets state loaders",
                 "engine": "DigitalAssetTreasuryEngine",
                 "input": "DigitalAssetHolding, Wallet, etc.",
                 "deferred_to": "v10.159+",
                 "reason": ("DigitalAssetTreasuryEngine doesn't "
                              "expose a board_summary in v10.155; "
                              "engine integration pattern still "
                              "evolving.")},
            ],
            "phase_2_status": ("WRITE-SIDE COMPLETE for the core "
                                  "Treasury workflow (ALM, Products, "
                                  "Connectivity, LCR, NSFR). Islamic, "
                                  "Digital Assets, and Agent state "
                                  "loaders defer to v10.159+ for "
                                  "design reasons noted above, not "
                                  "bandwidth reasons."),
        }
        _audit_treasury("liquidity_risk.methods", user, "")
        return result

    # ----------------------------------------------------------------
    # ENH-239 Islamic Treasury
    # ----------------------------------------------------------------

    @router.get("/islamic/board")
    def islamic_board(user=Depends(get_current_user)):
        result = _islamic.board_summary()
        _audit_treasury("islamic.board", user, "")
        return result

    @router.get("/islamic/non-compliant")
    def islamic_non_compliant(user=Depends(get_current_user)):
        result = _islamic.non_compliant_products()
        if isinstance(result, tuple):
            try:
                result_json = [
                    {k: getattr(p, k) for k in
                       getattr(p, "__dataclass_fields__", {}).keys()}
                    for p in result]
            except Exception:
                result_json = [str(p) for p in result]
        else:
            result_json = result
        _audit_treasury("islamic.non_compliant", user,
                          f"n={len(result_json) if hasattr(result_json,'__len__') else 0}")
        return {"non_compliant_products": result_json}

    # ----------------------------------------------------------------
    # ENH-TRS-R6 Climate Limits
    # ----------------------------------------------------------------

    @router.get("/climate/board")
    def climate_board(user=Depends(get_current_user)):
        result = _climate.board_summary()
        _audit_treasury("climate.board", user, "")
        return result

    @router.get("/climate/all-limits")
    def climate_all_limits(user=Depends(get_current_user)):
        result = _climate.compute_all_limits()
        if isinstance(result, tuple):
            try:
                result_json = [
                    {k: getattr(p, k) for k in
                       getattr(p, "__dataclass_fields__", {}).keys()}
                    for p in result]
            except Exception:
                result_json = [str(p) for p in result]
        else:
            result_json = result
        _audit_treasury("climate.all_limits", user,
                          f"n={len(result_json) if hasattr(result_json,'__len__') else 0}")
        return {"climate_adjusted_limits": result_json}

    # ----------------------------------------------------------------
    # POST endpoints — state-mutating workflows (v10.155 closure)
    #
    # The v10.154 deferral was honored: typed Pydantic models match the
    # engines' frozen input dataclass shapes. Real signatures verified
    # via inspect.signature before writing endpoints (v10.153.1 lesson).
    #
    # State persistence model: engines hold state in process memory
    # for the API session. For production this needs to be backed by
    # the DB (engine state mirrors data/treasury_*.json). Out of scope
    # for v10.155; flagged in the closure changelog as future work.
    # ----------------------------------------------------------------

    class AgentApprovalRequest(BaseModel):
        recommendation_id: str = Field(...,
            description="Recommendation ID to approve")
        approver: str = Field(...,
            description="Approver username")

    class AgentRejectionRequest(BaseModel):
        recommendation_id: str
        approver: str
        rejection_reason: str

    @router.post("/agents/approve")
    def agents_approve(req: AgentApprovalRequest,
                          user=Depends(get_current_user)):
        """Approve an agent recommendation."""
        try:
            now = datetime.now(timezone.utc)
            result = _agents.approve(
                recommendation_id=req.recommendation_id,
                approver=req.approver,
                approved_at=now)
            _audit_treasury(
                "agents.approve", user,
                f"rec_id={req.recommendation_id} "
                f"approver={req.approver}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"approve_failed: {type(e).__name__}: {e}")

    @router.post("/agents/reject")
    def agents_reject(req: AgentRejectionRequest,
                         user=Depends(get_current_user)):
        """Reject an agent recommendation."""
        try:
            now = datetime.now(timezone.utc)
            result = _agents.reject(
                recommendation_id=req.recommendation_id,
                approver=req.approver,
                rejection_reason=req.rejection_reason,
                at=now)
            _audit_treasury(
                "agents.reject", user,
                f"rec_id={req.recommendation_id} "
                f"reason={req.rejection_reason[:80]}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"reject_failed: {type(e).__name__}: {e}")

    class RunLCRRequest(BaseModel):
        result_id: str
        as_of_date: str
        horizon_days: int = Field(default=30)

    class RunRepricingGapRequest(BaseModel):
        result_id: str
        as_of_date: str

    @router.post("/alm/run-lcr")
    def alm_run_lcr(req: RunLCRRequest,
                      user=Depends(get_current_user)):
        """Run LCR computation against engine's currently-registered
        HQLA + cash-flow state. State-loading endpoints land in v10.156.
        """
        try:
            result = _alm.run_lcr(
                result_id=req.result_id,
                as_of_date=req.as_of_date,
                horizon_days=req.horizon_days)
            _audit_treasury(
                "alm.run_lcr", user,
                f"result_id={req.result_id} as_of={req.as_of_date}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"run_lcr_failed: {type(e).__name__}: {e}")

    @router.post("/alm/run-repricing-gap")
    def alm_run_repricing_gap(
        req: RunRepricingGapRequest,
        user=Depends(get_current_user),
    ):
        """Run interest rate repricing gap analysis."""
        try:
            result = _alm.run_repricing_gap(
                result_id=req.result_id,
                as_of_date=req.as_of_date)
            _audit_treasury(
                "alm.run_repricing_gap", user,
                f"result_id={req.result_id} as_of={req.as_of_date}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"run_repricing_gap_failed: "
                          f"{type(e).__name__}: {e}"))

    class ClimateBreachCheckRequest(BaseModel):
        asset_class: str
        actual_exposure_pct: float

    @router.post("/climate/check-breach")
    def climate_check_breach(
        req: ClimateBreachCheckRequest,
        user=Depends(get_current_user),
    ):
        """Check if a given exposure breaches the climate-adjusted
        limit for the asset class."""
        try:
            from utils.climate_treasury_limits import (
                TreasuryAssetClass)
            from decimal import Decimal as _Dec
            try:
                ac = TreasuryAssetClass(req.asset_class)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"invalid asset_class: {req.asset_class}; "
                        f"valid: "
                        f"{[v.value for v in TreasuryAssetClass]}"))
            result = _climate.check_breach(
                asset_class=ac,
                actual_exposure_pct=_Dec(
                    str(req.actual_exposure_pct)))
            _audit_treasury(
                "climate.check_breach", user,
                f"ac={req.asset_class} "
                f"exposure={req.actual_exposure_pct}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"check_breach_failed: {type(e).__name__}: {e}")

    # ----------------------------------------------------------------
    # v10.156 — State-loading POST endpoints
    #
    # Per v10.155 deferral, these endpoints accept Pydantic models that
    # match the engines' frozen input dataclass shapes. Each request
    # model maps 1:1 to the engine's @dataclass(frozen=True) constructor
    # arguments. Endpoint converts Pydantic → engine dataclass → calls
    # register_* / add_*.
    #
    # Six endpoints in v10.156 (the simple-shape ones):
    #   POST /api/treasury/alm/register-deposit
    #   POST /api/treasury/alm/register-hqla
    #   POST /api/treasury/alm/add-inflow
    #   POST /api/treasury/alm/add-outflow
    #   POST /api/treasury/alm/register-rates-position
    #   POST /api/treasury/products/register-fx-position
    #
    # Deferred to v10.157:
    #   - register_yield_curve (nested YieldCurvePoint tuple)
    #   - register_bond_position (full coupon/maturity/rating shape)
    #   - register_mm_position (similar complexity)
    #   - register_connector / register_mmf (multiple frozen sub-types)
    #   - register_agent / register_product (Islamic) (engine-specific
    #     classes)
    #
    # Honest deferral surface still exposed via /api/treasury/
    # liquidity-risk/methods (now updated to deferred_to='v10.157').
    # ----------------------------------------------------------------

    class RegisterDepositRequest(BaseModel):
        deposit_id: str
        cif: str
        category: str = Field(...,
            description="One of: RETAIL_STABLE, RETAIL_LESS_STABLE, "
                         "SME_OPERATIONAL, CORPORATE_OPERATIONAL, "
                         "CORPORATE_NON_OPERATIONAL, "
                         "INSTITUTIONAL_NON_OPERATIONAL, PUBLIC_SECTOR")
        balance: float
        currency: str = Field(default="KES")
        open_date: str = Field(...,
            description="YYYY-MM-DD")
        last_movement_date: Optional[str] = None
        is_insured: bool = False
        is_operational: bool = False
        notes: str = ""

    @router.post("/alm/register-deposit")
    def alm_register_deposit(req: RegisterDepositRequest,
                                user=Depends(get_current_user)):
        """Register a non-maturity deposit for NMD behavioral
        modeling + LCR computation.

        The engine validates category against NMDDepositCategory enum.
        Bad category → HTTP 400.
        """
        try:
            from utils.treasury_alm import (NMDDeposit,
                                              NMDDepositCategory)
            from decimal import Decimal as _Dec

            try:
                cat = NMDDepositCategory(req.category)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid category: {req.category}; "
                              f"valid: "
                              f"{[v.value for v in NMDDepositCategory]}"))

            d = NMDDeposit(
                deposit_id=req.deposit_id,
                cif=req.cif,
                category=cat,
                balance=_Dec(str(req.balance)),
                currency=req.currency,
                open_date=req.open_date,
                last_movement_date=req.last_movement_date,
                is_insured=req.is_insured,
                is_operational=req.is_operational,
                notes=req.notes)
            _alm.register_deposit(d)
            _audit_treasury(
                "alm.register_deposit", user,
                f"deposit_id={req.deposit_id} "
                f"cat={req.category} balance={req.balance}")
            return {"ok": True, "deposit_id": req.deposit_id,
                      "category": req.category}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_deposit_failed: "
                          f"{type(e).__name__}: {e}"))

    class RegisterHQLARequest(BaseModel):
        position_id: str
        asset_class: str = Field(...,
            description="Free-form asset class label (e.g. 'CBK_BILL', "
                         "'GOK_BOND', 'CORPORATE_BOND_AAA')")
        level: str = Field(...,
            description="One of: LEVEL_1, LEVEL_2A, LEVEL_2B, NOT_HQLA")
        notional: float
        currency: str = Field(default="KES")
        notes: str = ""

    @router.post("/alm/register-hqla")
    def alm_register_hqla(req: RegisterHQLARequest,
                            user=Depends(get_current_user)):
        """Register a High-Quality Liquid Asset position for LCR
        numerator computation.
        """
        try:
            from utils.treasury_alm import HQLAPosition, HQLALevel
            from decimal import Decimal as _Dec

            try:
                lvl = HQLALevel(req.level)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid level: {req.level}; "
                              f"valid: "
                              f"{[v.value for v in HQLALevel]}"))

            h = HQLAPosition(
                position_id=req.position_id,
                asset_class=req.asset_class,
                level=lvl,
                notional=_Dec(str(req.notional)),
                currency=req.currency,
                notes=req.notes)
            _alm.register_hqla(h)
            _audit_treasury(
                "alm.register_hqla", user,
                f"position_id={req.position_id} "
                f"level={req.level} notional={req.notional}")
            return {"ok": True, "position_id": req.position_id,
                      "level": req.level}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_hqla_failed: "
                          f"{type(e).__name__}: {e}"))

    class CashFlowRequest(BaseModel):
        flow_id: str
        direction: str = Field(...,
            description="INFLOW or OUTFLOW")
        amount: float
        bucket_days: int = Field(...,
            description="Days from today; LCR uses 0..30")
        counterparty_category: str = ""
        notes: str = ""

    @router.post("/alm/add-inflow")
    def alm_add_inflow(req: CashFlowRequest,
                          user=Depends(get_current_user)):
        """Add a cash inflow item for LCR denominator computation."""
        try:
            from utils.treasury_alm import CashFlow
            from decimal import Decimal as _Dec
            c = CashFlow(
                flow_id=req.flow_id,
                direction="INFLOW",  # endpoint-determined, ignore req
                amount=_Dec(str(req.amount)),
                bucket_days=req.bucket_days,
                counterparty_category=req.counterparty_category,
                notes=req.notes)
            _alm.add_inflow(c)
            _audit_treasury(
                "alm.add_inflow", user,
                f"flow_id={req.flow_id} amount={req.amount} "
                f"bucket={req.bucket_days}d")
            return {"ok": True, "flow_id": req.flow_id,
                      "direction": "INFLOW"}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"add_inflow_failed: {type(e).__name__}: {e}")

    @router.post("/alm/add-outflow")
    def alm_add_outflow(req: CashFlowRequest,
                           user=Depends(get_current_user)):
        """Add a cash outflow item for LCR denominator computation."""
        try:
            from utils.treasury_alm import CashFlow
            from decimal import Decimal as _Dec
            c = CashFlow(
                flow_id=req.flow_id,
                direction="OUTFLOW",  # endpoint-determined
                amount=_Dec(str(req.amount)),
                bucket_days=req.bucket_days,
                counterparty_category=req.counterparty_category,
                notes=req.notes)
            _alm.add_outflow(c)
            _audit_treasury(
                "alm.add_outflow", user,
                f"flow_id={req.flow_id} amount={req.amount} "
                f"bucket={req.bucket_days}d")
            return {"ok": True, "flow_id": req.flow_id,
                      "direction": "OUTFLOW"}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"add_outflow_failed: {type(e).__name__}: {e}")

    class RegisterRatesPositionRequest(BaseModel):
        position_id: str
        bucket: str = Field(...,
            description="One of: OVERNIGHT, 2D_7D, 8D_1M, 1M_3M, "
                         "3M_6M, 6M_1Y, 1Y_2Y, 2Y_5Y, 5Y+")
        is_asset: bool = Field(...,
            description="True for assets, False for liabilities")
        notional: float
        currency: str = Field(default="KES")
        notes: str = ""

    @router.post("/alm/register-rates-position")
    def alm_register_rates_position(
        req: RegisterRatesPositionRequest,
        user=Depends(get_current_user),
    ):
        """Register a rate-sensitive position for IRRBB repricing
        gap analysis."""
        try:
            from utils.treasury_alm import (RatesGapPosition,
                                              MaturityBucket)
            from decimal import Decimal as _Dec

            try:
                bk = MaturityBucket(req.bucket)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid bucket: {req.bucket}; "
                              f"valid: "
                              f"{[v.value for v in MaturityBucket]}"))

            p = RatesGapPosition(
                position_id=req.position_id,
                bucket=bk,
                is_asset=req.is_asset,
                notional=_Dec(str(req.notional)),
                currency=req.currency,
                notes=req.notes)
            _alm.register_rates_position(p)
            _audit_treasury(
                "alm.register_rates_position", user,
                f"position_id={req.position_id} "
                f"bucket={req.bucket} is_asset={req.is_asset}")
            return {"ok": True, "position_id": req.position_id,
                      "bucket": req.bucket}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_rates_position_failed: "
                          f"{type(e).__name__}: {e}"))

    class RegisterFXPositionRequest(BaseModel):
        position_id: str
        instrument_type: str = Field(...,
            description="One of: FX_SPOT, FX_FORWARD, FX_SWAP")
        base_currency: str
        quote_currency: str
        notional_base: float
        contract_rate: float
        value_date: str = Field(..., description="YYYY-MM-DD")
        maturity_date: Optional[str] = None
        is_long_base: bool = Field(default=True,
            description="True = long the base currency")
        notes: str = ""

    @router.post("/products/register-fx-position")
    def products_register_fx_position(
        req: RegisterFXPositionRequest,
        user=Depends(get_current_user),
    ):
        """Register an FX position for MTM and net exposure computation."""
        try:
            from utils.treasury_products import (FXPosition,
                                                    InstrumentType)
            from decimal import Decimal as _Dec

            try:
                it = InstrumentType(req.instrument_type)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"invalid instrument_type: "
                        f"{req.instrument_type}; "
                        f"valid for FX: FX_SPOT, FX_FORWARD, "
                        f"FX_SWAP"))

            if it not in (InstrumentType.FX_SPOT,
                            InstrumentType.FX_FORWARD,
                            InstrumentType.FX_SWAP):
                raise HTTPException(
                    status_code=400,
                    detail=(f"instrument_type must be FX_*, got "
                              f"{req.instrument_type}"))

            p = FXPosition(
                position_id=req.position_id,
                instrument_type=it,
                base_currency=req.base_currency,
                quote_currency=req.quote_currency,
                notional_base=_Dec(str(req.notional_base)),
                contract_rate=_Dec(str(req.contract_rate)),
                value_date=req.value_date,
                maturity_date=req.maturity_date,
                is_long_base=req.is_long_base,
                notes=req.notes)
            _products.register_fx_position(p)
            _audit_treasury(
                "products.register_fx_position", user,
                f"position_id={req.position_id} "
                f"{req.base_currency}/{req.quote_currency} "
                f"notional={req.notional_base}")
            return {"ok": True, "position_id": req.position_id,
                      "pair": f"{req.base_currency}/{req.quote_currency}"}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_fx_position_failed: "
                          f"{type(e).__name__}: {e}"))

    # ----------------------------------------------------------------
    # v10.157 — Remaining state-loading endpoints (complex shapes) +
    # MTM compute endpoints + query endpoints
    #
    # Per v10.156 deferral, these endpoints carry the complex-shape
    # frozen dataclasses: nested tuples (YieldCurve), full-shape
    # bonds with classification enum, money-market positions,
    # connectors with FrozenSet[MessageFormat], MMF counterparties.
    # All field names + enum vocabularies verified via inspect before
    # writing (v10.153.1 / v10.156 discipline).
    #
    # Plus 4 endpoints that need state to work: mtm_fx_position,
    # mtm_bond, get_yield_curve, net_fx_exposure.
    #
    # NOT shipped (don't exist on the engine):
    #   - set_spot_rate — the engine's MTM methods take spot_rate as
    #     a per-call argument; there's no separate state-loading step.
    #     Inventing one would re-create the v10.153.1 bug class.
    #
    # After v10.157, Phase 2 Treasury is fully complete on read+write.
    # ----------------------------------------------------------------

    class YieldCurvePointModel(BaseModel):
        """Single point on a yield curve. Multiple of these compose
        a YieldCurve via nested Pydantic."""
        tenor_years: float = Field(...,
            description="Tenor in years (e.g. 0.25 for 3M, 1.0 for 1Y)")
        rate_pct: float = Field(...,
            description="Annualized rate, percent (e.g. 12.5 for 12.5%)")
        notes: str = ""

    class RegisterYieldCurveRequest(BaseModel):
        curve_id: str
        currency: str = Field(default="KES")
        as_of_date: str = Field(..., description="YYYY-MM-DD")
        points: List[YieldCurvePointModel] = Field(...,
            description="Curve points; min 2 for interpolation")
        notes: str = ""

    @router.post("/products/register-yield-curve")
    def products_register_yield_curve(
        req: RegisterYieldCurveRequest,
        user=Depends(get_current_user),
    ):
        """Register a yield curve for MTM and discounting computations.

        Operator must supply >=2 points for the engine's linear
        interpolation logic to work; engine flat-extrapolates beyond
        the curve's tenor range.
        """
        try:
            from utils.treasury_products import (YieldCurve,
                                                    YieldCurvePoint)
            from decimal import Decimal as _Dec

            if len(req.points) < 2:
                raise HTTPException(
                    status_code=400,
                    detail=(f"yield curve needs >=2 points for "
                              f"interpolation; got {len(req.points)}"))

            points_tuple = tuple(
                YieldCurvePoint(
                    tenor_years=_Dec(str(pt.tenor_years)),
                    rate_pct=_Dec(str(pt.rate_pct)),
                    notes=pt.notes)
                for pt in req.points)

            curve = YieldCurve(
                curve_id=req.curve_id,
                currency=req.currency,
                as_of_date=req.as_of_date,
                points=points_tuple,
                notes=req.notes)
            _products.register_yield_curve(curve)
            _audit_treasury(
                "products.register_yield_curve", user,
                f"curve_id={req.curve_id} ccy={req.currency} "
                f"n_points={len(req.points)}")
            return {"ok": True, "curve_id": req.curve_id,
                      "n_points": len(req.points)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_yield_curve_failed: "
                          f"{type(e).__name__}: {e}"))

    @router.get("/products/yield-curve/{curve_id}")
    def products_get_yield_curve(curve_id: str,
                                    user=Depends(get_current_user)):
        """Retrieve a registered yield curve by id."""
        try:
            curve = _products.get_yield_curve(curve_id)
            # Convert frozen dataclass to JSON-friendly dict
            result = {
                "curve_id": curve.curve_id,
                "currency": curve.currency,
                "as_of_date": curve.as_of_date,
                "points": [
                    {"tenor_years": str(p.tenor_years),
                       "rate_pct": str(p.rate_pct),
                       "notes": p.notes}
                    for p in curve.points],
                "notes": curve.notes,
            }
            _audit_treasury("products.get_yield_curve", user,
                              f"curve_id={curve_id}")
            return result
        except KeyError:
            raise HTTPException(
                status_code=404,
                detail=f"curve_id not found: {curve_id}")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"get_yield_curve_failed: "
                          f"{type(e).__name__}: {e}"))

    class RegisterBondPositionRequest(BaseModel):
        position_id: str
        instrument_type: str = Field(...,
            description="One of: GOVT_BOND, CORPORATE_BOND")
        isin: str
        issuer: str
        currency: str = Field(default="KES")
        face_value: float
        coupon_pct: float
        coupon_freq_per_year: int = 2
        issue_date: str = Field(..., description="YYYY-MM-DD")
        maturity_date: str = Field(..., description="YYYY-MM-DD")
        purchase_price: float = Field(default=0.0,
            description="Clean price at purchase (0 = use face value)")
        purchase_date: str = ""
        classification: str = Field(default="HTM",
            description="IFRS 9: HFT, AFS, HTM, LAR, "
                          "DESIGNATED_FVTPL")
        notes: str = ""

    @router.post("/products/register-bond-position")
    def products_register_bond(
        req: RegisterBondPositionRequest,
        user=Depends(get_current_user),
    ):
        """Register a bond position for MTM, accrual, and IFRS 9
        classification reporting."""
        try:
            from utils.treasury_products import (BondPosition,
                                                    InstrumentType,
                                                    IFRS9Classification)
            from decimal import Decimal as _Dec

            try:
                it = InstrumentType(req.instrument_type)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid instrument_type: "
                              f"{req.instrument_type}; valid for "
                              f"bonds: GOVT_BOND, CORPORATE_BOND"))

            if it not in (InstrumentType.GOVT_BOND,
                            InstrumentType.CORPORATE_BOND):
                raise HTTPException(
                    status_code=400,
                    detail=(f"instrument_type must be GOVT_BOND or "
                              f"CORPORATE_BOND, got "
                              f"{req.instrument_type}"))

            try:
                cls = IFRS9Classification(req.classification)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid classification: "
                              f"{req.classification}; valid: "
                              f"{[v.value for v in IFRS9Classification]}"))

            purchase_price = (_Dec(str(req.purchase_price))
                                if req.purchase_price > 0
                                else _Dec(str(req.face_value)))

            b = BondPosition(
                position_id=req.position_id,
                instrument_type=it,
                isin=req.isin,
                issuer=req.issuer,
                currency=req.currency,
                face_value=_Dec(str(req.face_value)),
                coupon_pct=_Dec(str(req.coupon_pct)),
                coupon_freq_per_year=req.coupon_freq_per_year,
                issue_date=req.issue_date,
                maturity_date=req.maturity_date,
                purchase_price=purchase_price,
                purchase_date=req.purchase_date or req.issue_date,
                classification=cls,
                notes=req.notes)
            _products.register_bond_position(b)
            _audit_treasury(
                "products.register_bond_position", user,
                f"position_id={req.position_id} isin={req.isin} "
                f"face={req.face_value} cls={req.classification}")
            return {"ok": True, "position_id": req.position_id,
                      "isin": req.isin,
                      "classification": req.classification}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_bond_position_failed: "
                          f"{type(e).__name__}: {e}"))

    class RegisterMMPositionRequest(BaseModel):
        position_id: str
        instrument_type: str = Field(...,
            description="One of: MM_TERM_DEPOSIT, MM_BORROWING, "
                          "CD, COMMERCIAL_PAPER, REPO, REVERSE_REPO")
        currency: str = Field(default="KES")
        principal: float
        contract_rate_pct: float
        issue_date: str = Field(..., description="YYYY-MM-DD")
        maturity_date: str = Field(..., description="YYYY-MM-DD")
        is_asset: bool = Field(default=True,
            description="True = lending; False = borrowing")
        notes: str = ""

    @router.post("/products/register-mm-position")
    def products_register_mm(
        req: RegisterMMPositionRequest,
        user=Depends(get_current_user),
    ):
        """Register a money-market position (term deposit, borrowing,
        CD, commercial paper, repo, reverse repo)."""
        try:
            from utils.treasury_products import (MoneyMarketPosition,
                                                    InstrumentType)
            from decimal import Decimal as _Dec

            try:
                it = InstrumentType(req.instrument_type)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid instrument_type: "
                              f"{req.instrument_type}; valid for MM: "
                              f"MM_TERM_DEPOSIT, MM_BORROWING, CD, "
                              f"COMMERCIAL_PAPER, REPO, REVERSE_REPO"))

            mm_types = {InstrumentType.MM_TERM_DEPOSIT,
                          InstrumentType.MM_BORROWING,
                          InstrumentType.CD,
                          InstrumentType.COMMERCIAL_PAPER,
                          InstrumentType.REPO,
                          InstrumentType.REVERSE_REPO}
            if it not in mm_types:
                raise HTTPException(
                    status_code=400,
                    detail=(f"instrument_type must be MM-family, got "
                              f"{req.instrument_type}"))

            p = MoneyMarketPosition(
                position_id=req.position_id,
                instrument_type=it,
                currency=req.currency,
                principal=_Dec(str(req.principal)),
                contract_rate_pct=_Dec(str(req.contract_rate_pct)),
                issue_date=req.issue_date,
                maturity_date=req.maturity_date,
                is_asset=req.is_asset,
                notes=req.notes)
            _products.register_mm_position(p)
            _audit_treasury(
                "products.register_mm_position", user,
                f"position_id={req.position_id} "
                f"type={req.instrument_type} "
                f"principal={req.principal} "
                f"is_asset={req.is_asset}")
            return {"ok": True, "position_id": req.position_id,
                      "instrument_type": req.instrument_type}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_mm_position_failed: "
                          f"{type(e).__name__}: {e}"))

    class RegisterConnectorRequest(BaseModel):
        connector_id: str
        connector_type: str = Field(...,
            description="One of: BANK_PARTNER, MMF_COUNTERPARTY, "
                          "ERP_SYSTEM, CENTRAL_BANK, CARD_NETWORK, "
                          "OTHER")
        counterparty_name: str
        region: str = Field(default="KE")
        supported_formats: List[str] = Field(...,
            description="List of message format strings; engine "
                          "stores as FrozenSet[MessageFormat]")
        endpoint_url: str = ""
        swift_bic: str = ""
        iban: str = ""
        notes: str = ""

    @router.post("/connectivity/register-connector")
    def connectivity_register_connector(
        req: RegisterConnectorRequest,
        user=Depends(get_current_user),
    ):
        """Register a connector (bank partner, MMF, ERP, etc.) into
        the Treasury connectivity engine."""
        try:
            from utils.treasury_connectivity import (Connector,
                                                       ConnectorType,
                                                       MessageFormat)

            try:
                ct = ConnectorType(req.connector_type)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid connector_type: "
                              f"{req.connector_type}; valid: "
                              f"{[v.value for v in ConnectorType]}"))

            try:
                fmts = frozenset(
                    MessageFormat(fmt) for fmt in req.supported_formats)
            except (ValueError, KeyError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid supported_formats: "
                              f"{req.supported_formats}; valid: "
                              f"{[v.value for v in MessageFormat]}; "
                              f"first bad value: {e}"))

            c = Connector(
                connector_id=req.connector_id,
                connector_type=ct,
                counterparty_name=req.counterparty_name,
                region=req.region,
                supported_formats=fmts,
                endpoint_url=req.endpoint_url,
                swift_bic=req.swift_bic,
                iban=req.iban,
                notes=req.notes)
            _connectivity.register_connector(c)
            _audit_treasury(
                "connectivity.register_connector", user,
                f"connector_id={req.connector_id} "
                f"type={req.connector_type} "
                f"counterparty={req.counterparty_name}")
            return {"ok": True, "connector_id": req.connector_id,
                      "connector_type": req.connector_type,
                      "n_formats": len(req.supported_formats)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_connector_failed: "
                          f"{type(e).__name__}: {e}"))

    class RegisterMMFRequest(BaseModel):
        counterparty_id: str
        fund_name: str
        manager: str
        fund_size_kes: float
        current_yield_pct: float
        minimum_investment_kes: float
        same_day_settlement: bool = True
        rating: str = Field(default="UNRATED",
            description="Free-form rating label (e.g. 'AA', 'A+')")

    @router.post("/connectivity/register-mmf")
    def connectivity_register_mmf(
        req: RegisterMMFRequest,
        user=Depends(get_current_user),
    ):
        """Register an MMF (money market fund) counterparty for
        treasury investment."""
        try:
            from utils.treasury_connectivity import MMFCounterparty
            from decimal import Decimal as _Dec

            mmf = MMFCounterparty(
                counterparty_id=req.counterparty_id,
                fund_name=req.fund_name,
                manager=req.manager,
                fund_size_kes=_Dec(str(req.fund_size_kes)),
                current_yield_pct=_Dec(str(req.current_yield_pct)),
                minimum_investment_kes=_Dec(
                    str(req.minimum_investment_kes)),
                same_day_settlement=req.same_day_settlement,
                rating=req.rating)
            _connectivity.register_mmf(mmf)
            _audit_treasury(
                "connectivity.register_mmf", user,
                f"counterparty_id={req.counterparty_id} "
                f"fund={req.fund_name} "
                f"yield={req.current_yield_pct}")
            return {"ok": True,
                      "counterparty_id": req.counterparty_id,
                      "fund_name": req.fund_name}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"register_mmf_failed: "
                          f"{type(e).__name__}: {e}"))

    # ----------------------------------------------------------------
    # MTM compute endpoints — require positions registered first
    # ----------------------------------------------------------------

    class MTMFXRequest(BaseModel):
        position_id: str
        spot_rate: float = Field(...,
            description="Current spot rate (quote/base)")
        base_curve_id: Optional[str] = None
        quote_curve_id: Optional[str] = None
        as_of_date: str = Field(..., description="YYYY-MM-DD")

    @router.post("/products/mtm-fx")
    def products_mtm_fx(req: MTMFXRequest,
                          user=Depends(get_current_user)):
        """Mark-to-market an FX position. Position must already be
        registered via POST /products/register-fx-position. For
        forwards/swaps, supply yield curve IDs that are also
        registered (POST /products/register-yield-curve)."""
        try:
            from decimal import Decimal as _Dec
            result = _products.mtm_fx_position(
                position_id=req.position_id,
                spot_rate=_Dec(str(req.spot_rate)),
                base_curve_id=req.base_curve_id,
                quote_curve_id=req.quote_curve_id,
                as_of_date=req.as_of_date)
            _audit_treasury(
                "products.mtm_fx_position", user,
                f"position_id={req.position_id} "
                f"spot={req.spot_rate} as_of={req.as_of_date}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except KeyError as e:
            raise HTTPException(
                status_code=404,
                detail=f"position or curve not found: {e}")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"mtm_fx_failed: {type(e).__name__}: {e}")

    class MTMBondRequest(BaseModel):
        position_id: str
        yield_pct: float = Field(...,
            description="Current yield to maturity, percent")
        last_coupon_date: str = Field(...,
            description="YYYY-MM-DD; date of most recent coupon "
                          "for accrual")
        as_of_date: str = Field(..., description="YYYY-MM-DD")
        fair_value_level: str = Field(default="LEVEL_2",
            description="IFRS 13 fair value hierarchy: "
                          "LEVEL_1, LEVEL_2, LEVEL_3")

    @router.post("/products/mtm-bond")
    def products_mtm_bond(req: MTMBondRequest,
                            user=Depends(get_current_user)):
        """Mark-to-market a bond position. Position must already be
        registered via POST /products/register-bond-position."""
        try:
            from utils.treasury_products import FairValueLevel
            from decimal import Decimal as _Dec

            try:
                fvl = FairValueLevel(req.fair_value_level)
            except (ValueError, KeyError):
                raise HTTPException(
                    status_code=400,
                    detail=(f"invalid fair_value_level: "
                              f"{req.fair_value_level}; valid: "
                              f"{[v.value for v in FairValueLevel]}"))

            result = _products.mtm_bond(
                position_id=req.position_id,
                yield_pct=_Dec(str(req.yield_pct)),
                last_coupon_date=req.last_coupon_date,
                as_of_date=req.as_of_date,
                fair_value_level=fvl)
            _audit_treasury(
                "products.mtm_bond", user,
                f"position_id={req.position_id} "
                f"yield={req.yield_pct} as_of={req.as_of_date}")
            if hasattr(result, "__dataclass_fields__"):
                return {k: getattr(result, k)
                        for k in result.__dataclass_fields__.keys()}
            return result if isinstance(result, dict) \
                else {"result": str(result)}
        except HTTPException:
            raise
        except KeyError as e:
            raise HTTPException(
                status_code=404,
                detail=f"position not found: {e}")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"mtm_bond_failed: {type(e).__name__}: {e}")

    @router.get("/products/net-fx-exposure")
    def products_net_fx_exposure(
        base_currency: str = Query(default="USD",
            description="Currency to compute net exposure for"),
        user=Depends(get_current_user),
    ):
        """Compute net FX exposure in the requested base currency
        across all registered FX positions."""
        try:
            result = _products.net_fx_exposure(
                base_currency=base_currency)
            _audit_treasury("products.net_fx_exposure", user,
                              f"base={base_currency}")
            return {"base_currency": base_currency,
                      "net_exposure": str(result)}
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=(f"net_fx_exposure_failed: "
                          f"{type(e).__name__}: {e}"))

    # ----------------------------------------------------------------
    # v10.158 — LCR + NSFR per-call computation endpoints
    #
    # Closes the v10.157 deferred item. Honest design decision:
    # LiquidityRiskEngine has STATIC methods (no engine state),
    # so the per-call payload model is the right shape — operator
    # POSTs the full HQLA / flow / funding / asset list with the
    # request, engine computes the ratio, returns it. This is
    # different from TreasuryALMEngine where state accumulates
    # across calls (register_hqla → add_inflow → run_lcr).
    #
    # Both patterns coexist:
    # - /alm/run-lcr (v10.155) uses TreasuryALMEngine state
    # - /liquidity-risk/lcr (v10.158) is per-call against
    #   LiquidityRiskEngine static methods
    #
    # Operator picks based on workflow: incremental loading favors
    # the ALM engine; one-shot regulatory submission favors the
    # static per-call endpoint.
    # ----------------------------------------------------------------

    class HqlaHoldingModel(BaseModel):
        asset_id: str
        level: str = Field(...,
            description="LEVEL_1, LEVEL_2A, LEVEL_2B, or NOT_HQLA")
        market_value_kes: float

    class CashFlowItemModel(BaseModel):
        item_id: str
        category: str = Field(...,
            description="LCR run-off category — engine maps to "
                          "weighting; unknown → reason='no_data'")
        direction: str = Field(...,
            description="INFLOW or OUTFLOW")
        balance_kes: float

    class FundingItemModel(BaseModel):
        item_id: str
        category: str = Field(...,
            description="ASF category (retail_stable, "
                          "retail_less_stable, wholesale, etc.)")
        balance_kes: float

    class AssetItemModel(BaseModel):
        item_id: str
        category: str = Field(...,
            description="RSF category (cash, loans_residential, "
                          "corporate_loans, etc.)")
        balance_kes: float

    class LCRRequest(BaseModel):
        hqla_holdings: List[HqlaHoldingModel] = Field(...,
            description="HQLA portfolio at as-of date")
        cash_flows: List[CashFlowItemModel] = Field(...,
            description="30-day cash flow items")

    class NSFRRequest(BaseModel):
        funding: List[FundingItemModel] = Field(...,
            description="Available stable funding items")
        assets: List[AssetItemModel] = Field(...,
            description="Required stable funding asset items")

    @router.post("/liquidity-risk/lcr")
    def liquidity_risk_lcr(req: LCRRequest,
                              user=Depends(get_current_user)):
        """Per-call LCR computation against LiquidityRiskEngine
        static method. Returns ratio, hqla_total, net_outflows, and
        engine's own status/reason if categories don't map.

        Different from /alm/run-lcr which uses TreasuryALMEngine
        accumulated state. Use this for one-shot regulatory
        submission; use /alm/run-lcr for incremental workflow."""
        try:
            from utils.liquidity_risk import (LiquidityRiskEngine,
                                                HqlaHolding,
                                                CashFlowItem)
            from decimal import Decimal as _Dec

            holdings = [
                HqlaHolding(
                    asset_id=h.asset_id,
                    level=h.level,
                    market_value_kes=_Dec(str(h.market_value_kes)))
                for h in req.hqla_holdings
            ]
            flows = [
                CashFlowItem(
                    item_id=f.item_id,
                    category=f.category,
                    direction=f.direction,
                    balance_kes=_Dec(str(f.balance_kes)))
                for f in req.cash_flows
            ]
            result = LiquidityRiskEngine.lcr(
                hqla_holdings=holdings, cash_flows=flows)
            _audit_treasury(
                "liquidity_risk.lcr", user,
                f"n_holdings={len(holdings)} "
                f"n_flows={len(flows)} "
                f"status={result.get('status', 'unknown')}")
            return result
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"lcr_failed: {type(e).__name__}: {e}")

    @router.post("/liquidity-risk/nsfr")
    def liquidity_risk_nsfr(req: NSFRRequest,
                                user=Depends(get_current_user)):
        """Per-call NSFR computation. Returns ratio + ASF/RSF
        breakdown.

        Engine returns status='NO_DATA' with reason when categories
        don't map to weighting tables — operator should fix
        category vocabulary rather than treat NO_DATA as a passing
        ratio."""
        try:
            from utils.liquidity_risk import (LiquidityRiskEngine,
                                                FundingItem,
                                                AssetItem)
            from decimal import Decimal as _Dec

            funding = [
                FundingItem(
                    item_id=f.item_id,
                    category=f.category,
                    balance_kes=_Dec(str(f.balance_kes)))
                for f in req.funding
            ]
            assets = [
                AssetItem(
                    item_id=a.item_id,
                    category=a.category,
                    balance_kes=_Dec(str(a.balance_kes)))
                for a in req.assets
            ]
            result = LiquidityRiskEngine.nsfr(
                funding=funding, assets=assets)
            _audit_treasury(
                "liquidity_risk.nsfr", user,
                f"n_funding={len(funding)} "
                f"n_assets={len(assets)} "
                f"status={result.get('status', 'unknown')}")
            return result
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"nsfr_failed: {type(e).__name__}: {e}")

    # ----------------------------------------------------------------
    # v10.159 — Category vocabulary discovery endpoint
    #
    # The v10.158 endpoints (lcr, nsfr, hqla_value) accept category
    # strings that map to Basel III standardised weighting tables in
    # utils/liquidity_risk.py. Without this endpoint, an operator
    # building a request payload had to read the engine source code
    # to know which category strings to use — when the engine returned
    # status='NO_DATA' with reason='unknown category', the only fix
    # was 'go read the file'.
    #
    # This endpoint publishes the full vocabulary as structured JSON.
    # Operator: GET /api/treasury/liquidity-risk/vocabulary →
    # discovers the 8 outflow categories, 4 inflow categories, 6 ASF
    # categories, 11 RSF categories, 3 HQLA levels, and their weights.
    # Build LCR/NSFR/HQLA requests against the published vocabulary
    # and the engine returns COMPUTED ratios, not NO_DATA.
    #
    # This is the discipline that turns v10.158's endpoints from
    # "demoable when the operator reads the code" to "demoable
    # standalone." Same pattern as ENH-138's no_product_resolution
    # surfaces — engine state should be discoverable, not implicit.
    # ----------------------------------------------------------------

    @router.get("/liquidity-risk/vocabulary")
    def liquidity_risk_vocabulary(user=Depends(get_current_user)):
        """Publish the full Basel III category vocabulary that the
        engine's LCR/NSFR/HQLA computations recognise.

        Use this to discover which `category` strings to put in your
        LCR/NSFR request payloads. Categories not in this vocabulary
        will be silently excluded from the computation (the engine
        reports excluded_count in its response).

        Reflects the actual constants in utils/liquidity_risk.py at
        the time of the request — not a stale documentation snapshot.
        """
        try:
            from utils.liquidity_risk import (
                HQLA_HAIRCUT_PCT,
                LEVEL_2_TOTAL_CAP_PCT,
                LEVEL_2B_CAP_PCT,
                LCR_MIN_PCT,
                NSFR_MIN_PCT,
                OUTFLOW_RATES_PCT,
                INFLOW_RATES_PCT,
                INFLOW_CAP_PCT_OF_OUTFLOWS,
                ASF_FACTORS_PCT,
                RSF_FACTORS_PCT,
            )

            result = {
                "engine": "LiquidityRiskEngine",
                "basel_version": "Basel III standardised approach",
                "thresholds": {
                    "lcr_min_pct": str(LCR_MIN_PCT),
                    "nsfr_min_pct": str(NSFR_MIN_PCT),
                    "level_2_total_cap_pct": str(
                        LEVEL_2_TOTAL_CAP_PCT),
                    "level_2b_cap_pct": str(LEVEL_2B_CAP_PCT),
                    "inflow_cap_pct_of_outflows": str(
                        INFLOW_CAP_PCT_OF_OUTFLOWS),
                },
                "hqla_levels": {
                    "endpoint_field": "level (in HqlaHoldingModel)",
                    "valid_values": list(HQLA_HAIRCUT_PCT.keys()),
                    "haircut_pct_by_level": {
                        k: str(v) for k, v in HQLA_HAIRCUT_PCT.items()
                    },
                },
                "lcr_outflow_categories": {
                    "endpoint_field": ("category in CashFlowItemModel "
                                          "with direction=OUTFLOW"),
                    "valid_values": list(OUTFLOW_RATES_PCT.keys()),
                    "run_off_rate_pct_by_category": {
                        k: str(v) for k, v in OUTFLOW_RATES_PCT.items()
                    },
                },
                "lcr_inflow_categories": {
                    "endpoint_field": ("category in CashFlowItemModel "
                                          "with direction=INFLOW"),
                    "valid_values": list(INFLOW_RATES_PCT.keys()),
                    "rate_pct_by_category": {
                        k: str(v) for k, v in INFLOW_RATES_PCT.items()
                    },
                    "cap_note": (f"Total inflows capped at "
                                   f"{INFLOW_CAP_PCT_OF_OUTFLOWS}% "
                                   f"of total outflows per Basel III"),
                },
                "nsfr_asf_categories": {
                    "endpoint_field": "category in FundingItemModel",
                    "valid_values": list(ASF_FACTORS_PCT.keys()),
                    "asf_factor_pct_by_category": {
                        k: str(v) for k, v in ASF_FACTORS_PCT.items()
                    },
                },
                "nsfr_rsf_categories": {
                    "endpoint_field": "category in AssetItemModel",
                    "valid_values": list(RSF_FACTORS_PCT.keys()),
                    "rsf_factor_pct_by_category": {
                        k: str(v) for k, v in RSF_FACTORS_PCT.items()
                    },
                },
                "behavior_on_unknown_category": (
                    "Items with unknown category are excluded from "
                    "the computation. The engine reports "
                    "excluded_count in its response. NO data is "
                    "fabricated for unknown categories — operator "
                    "should fix the category vocabulary in the "
                    "request payload."),
                "honest_design_note": (
                    "This vocabulary is the Basel III standardised "
                    "approach. It does NOT yet include CBK-specific "
                    "category extensions (e.g. KEPSS-settled "
                    "wholesale, M-Pesa float deposits). Adding "
                    "Kenya-specific categories is a deliberate "
                    "extension that requires regulatory review and "
                    "weight calibration — out of scope for v10.159; "
                    "tracked as future work."),
            }
            _audit_treasury("liquidity_risk.vocabulary", user,
                              f"published "
                              f"{len(OUTFLOW_RATES_PCT)+len(INFLOW_RATES_PCT)+len(ASF_FACTORS_PCT)+len(RSF_FACTORS_PCT)} "
                              f"category entries")
            return result
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=(f"vocabulary_load_failed: "
                          f"{type(e).__name__}: {e}"))

    @router.post("/liquidity-risk/hqla-value")
    def liquidity_risk_hqla_value(
        req: LCRRequest,
        user=Depends(get_current_user),
    ):
        """Compute HQLA total value with Basel III haircuts applied
        per level. Reuses LCRRequest payload because HQLA is one of
        its two components — operator already has the data shaped
        for LCR.
        """
        try:
            from utils.liquidity_risk import (LiquidityRiskEngine,
                                                HqlaHolding)
            from decimal import Decimal as _Dec

            holdings = [
                HqlaHolding(
                    asset_id=h.asset_id,
                    level=h.level,
                    market_value_kes=_Dec(str(h.market_value_kes)))
                for h in req.hqla_holdings
            ]
            result = LiquidityRiskEngine.hqla_value(holdings=holdings)
            _audit_treasury(
                "liquidity_risk.hqla_value", user,
                f"n_holdings={len(holdings)}")
            return result
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"hqla_value_failed: {type(e).__name__}: {e}")

else:
    # FastAPI not installed — placeholder so import doesn't fail
    router = None
