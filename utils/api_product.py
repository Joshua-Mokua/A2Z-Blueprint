"""utils.api_product — FastAPI router for the Product module (v10.151).

Exposes each of the 10 Product-arc engines (ENH-131..140) as JSON-
serializable HTTP endpoints with JWT authentication. This is the
**React-ready surface** for the planned React frontend.

DESIGN CONTRACT (mirrors utils/api_strategy.py from v10.141)
------------------------------------------------------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Each endpoint calls a single engine method and returns the dict
   directly. Engine is the source of truth for both this API and the
   Streamlit cockpit (`pages/16_product_arc_cockpit.py`)
3. Pydantic models enforce request payload shapes
4. Engine results are JSON-serializable (verified by the v10.142-
   v10.150 test suites)
5. Read-only contract honoured — no endpoint writes to performance.*
   tables; lifecycle transition writes go to data/product_lifecycle.json
   isolated to the product module
6. Audit logging via `_audit_product(action, user, detail)` after
   every successful endpoint call — same pattern as utils/api_strategy.py

ENDPOINT MAP (one or more per Product standard)
------------------------------------------------
  GET  /api/product/pnl/portfolio                 ENH-131 get_bank_wide_summary
  GET  /api/product/pnl/{product_id}              ENH-131 compute_product_pnl
  POST /api/product/lifecycle/transition          ENH-132 request_stage_transition
  POST /api/product/lifecycle/approve             ENH-132 approve_transition
  POST /api/product/lifecycle/reject              ENH-132 reject_transition
  GET  /api/product/lifecycle/sunset-candidates   ENH-132 get_sunset_candidates
  GET  /api/product/needs/customer/{customer_id}  ENH-133 get_customer_needs
  GET  /api/product/needs/gap/{customer_id}       ENH-133 analyze_customer_gap
  GET  /api/product/needs/bank-wide               ENH-133 bank_wide_gap_summary
  GET  /api/product/competitive/{product_id}      ENH-134 get_competitor_landscape
  GET  /api/product/competitive/summary           ENH-134 get_competitive_summary
  GET  /api/product/cvp/{segment}                 ENH-135 generate_cvp_for_segment
  GET  /api/product/cvp/summary                   ENH-135 get_cvp_summary
  GET  /api/product/ranking/{product_id}          ENH-136 get_product_score
  GET  /api/product/ranking/distribution          ENH-136 get_score_distribution
  GET  /api/product/pricing/{product_id}          ENH-137 get_pricing_recommendation
  GET  /api/product/pricing/actionable            ENH-137 get_actionable_recommendations
  GET  /api/product/recommend/customer/{cif}      ENH-138 recommend_for_customer
  GET  /api/product/recommend/segment/{segment}   ENH-138 recommend_for_segment
  GET  /api/product/bundling/top                  ENH-139 get_top_bundles
  GET  /api/product/bundling/segment/{segment}    ENH-139 get_segment_bundles
  GET  /api/product/dashboard                     ENH-140 get_dashboard_payload
  GET  /api/product/dashboard/health              ENH-140 get_engine_health_check
  GET  /api/product/dashboard/summary             ENH-140 get_summary_metrics

USAGE
-----
The router is mounted at `/api/product/*` from the parent FastAPI
app via:

    from utils.api_product import router as product_router
    app.include_router(product_router)

A React frontend can fetch any endpoint with:

    fetch('/api/product/dashboard', {
      headers: { Authorization: `Bearer ${jwt}` }
    })

and receive the same dict the Streamlit cockpit renders.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, Depends, HTTPException
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    Depends = None  # type: ignore
    HTTPException = Exception  # type: ignore
    BaseModel = object  # type: ignore
    Field = lambda **kwargs: None  # type: ignore

from utils.product_pnl_intelligence import ProductPnLIntelligence
from utils.product_lifecycle import ProductLifecycleEngine
from utils.customer_needs_analyzer import CustomerNeedsAnalyzer
from utils.product_competitive_intel import ProductCompetitiveIntelligence
from utils.product_cvp_builder import ProductCVPBuilder
from utils.product_ranking import ProductRankingEngine
from utils.dynamic_pricing import DynamicPricingEngine
from utils.product_recommendation import ProductRecommendationEngine
from utils.product_bundling import ProductBundlingIntelligence
from utils.product_analytics_dashboard import ProductAnalyticsDashboard

try:
    from utils.api_auth import get_current_user
except ImportError:
    # Fallback for environments without API auth — engine-level testing
    def get_current_user():
        return {"username": "test", "role": "admin"}

try:
    from utils.core_audit import audit_log
except ImportError:
    def audit_log(*args, **kwargs):
        pass


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit_product(action: str, user: Dict[str, Any],
                     detail: Dict[str, Any]) -> None:
    try:
        audit_log(
            action=f"api_product.{action}",
            actor=user.get("username", "unknown") if user else "unknown",
            payload=detail)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pydantic request models (only when FastAPI available)
# ---------------------------------------------------------------------------

if FASTAPI_AVAILABLE:

    class TransitionRequest(BaseModel):
        product_id: str = Field(...,
            description="Product ID e.g. P001")
        target_stage: str = Field(...,
            description="One of IDEATION/BUSINESS_CASE/DEVELOPMENT/"
                         "LAUNCH/GROWTH/MATURITY/DECLINE/SUNSET")
        requested_by: str = Field(...,
            description="Username requesting the transition")

    class ApprovalRequest(BaseModel):
        transition_id: str
        approver_role: str
        approver_id: str

    class RejectRequest(BaseModel):
        transition_id: str
        approver_role: str
        reason: str

    # ----------------------------------------------------------------
    # Router
    # ----------------------------------------------------------------

    router = APIRouter(prefix="/api/product",
                         tags=["product"])

    # Engines instantiated once at module load
    _pnl = ProductPnLIntelligence()
    _lifecycle = ProductLifecycleEngine()
    _needs = CustomerNeedsAnalyzer()
    _competitive = ProductCompetitiveIntelligence()
    _cvp = ProductCVPBuilder()
    _ranking = ProductRankingEngine()
    _pricing = DynamicPricingEngine()
    _recommendation = ProductRecommendationEngine()
    _bundling = ProductBundlingIntelligence()
    _dashboard = ProductAnalyticsDashboard(
        pnl_engine=_pnl, lifecycle_engine=_lifecycle,
        needs_engine=_needs, competitive_engine=_competitive,
        cvp_engine=_cvp, ranking_engine=_ranking,
        pricing_engine=_pricing, recommendation_engine=_recommendation,
        bundling_engine=_bundling)

    # ENH-131 P&L
    @router.get("/pnl/portfolio")
    def pnl_portfolio(user=Depends(get_current_user)):
        result = _pnl.get_bank_wide_summary()
        _audit_product("pnl.portfolio", user,
                         {"n_products": result.get("n_products")})
        return result

    @router.get("/pnl/{product_id}")
    def pnl_product(product_id: str,
                     user=Depends(get_current_user)):
        # Find the product first
        for p in _pnl._load_products():
            if p.get("id") == product_id:
                result = _pnl.compute_product_pnl(p).as_dict()
                _audit_product("pnl.product", user,
                                 {"product_id": product_id})
                return result
        raise HTTPException(status_code=404,
                              detail=f"product_{product_id}_not_found")

    # ENH-132 Lifecycle
    @router.post("/lifecycle/transition")
    def lifecycle_transition(req: TransitionRequest,
                                 user=Depends(get_current_user)):
        result = _lifecycle.request_stage_transition(
            req.product_id, req.target_stage, req.requested_by)
        _audit_product("lifecycle.transition", user, result)
        return result

    @router.post("/lifecycle/approve")
    def lifecycle_approve(req: ApprovalRequest,
                            user=Depends(get_current_user)):
        result = _lifecycle.approve_transition(
            req.transition_id, req.approver_role, req.approver_id)
        _audit_product("lifecycle.approve", user, result)
        return result

    @router.post("/lifecycle/reject")
    def lifecycle_reject(req: RejectRequest,
                           user=Depends(get_current_user)):
        result = _lifecycle.reject_transition(
            req.transition_id, req.approver_role, req.reason)
        _audit_product("lifecycle.reject", user, result)
        return result

    @router.get("/lifecycle/sunset-candidates")
    def lifecycle_sunset(user=Depends(get_current_user)):
        result = _lifecycle.get_sunset_candidates()
        _audit_product("lifecycle.sunset_candidates", user,
                         {"n": len(result)})
        return {"sunset_candidates": result}

    # ENH-133 Needs
    @router.get("/needs/customer/{customer_id}")
    def needs_customer(customer_id: str,
                          user=Depends(get_current_user)):
        result = _needs.get_customer_needs(customer_id)
        _audit_product("needs.customer", user,
                         {"customer_id": customer_id})
        return result

    @router.get("/needs/gap/{customer_id}")
    def needs_gap(customer_id: str,
                    user=Depends(get_current_user)):
        result = _needs.analyze_customer_gap(customer_id).as_dict()
        _audit_product("needs.gap", user,
                         {"customer_id": customer_id})
        return result

    @router.get("/needs/bank-wide")
    def needs_bank_wide(user=Depends(get_current_user)):
        result = _needs.bank_wide_gap_summary()
        _audit_product("needs.bank_wide", user,
                         {"n_evaluated": result.get(
                             "n_customers_evaluated")})
        return result

    # ENH-134 Competitive
    @router.get("/competitive/summary")
    def competitive_summary(user=Depends(get_current_user)):
        result = _competitive.get_competitive_summary()
        _audit_product("competitive.summary", user, result)
        return result

    @router.get("/competitive/{product_id}")
    def competitive_landscape(product_id: str,
                                  user=Depends(get_current_user)):
        result = _competitive.get_competitor_landscape(
            product_id).as_dict()
        _audit_product("competitive.landscape", user,
                         {"product_id": product_id})
        return result

    # ENH-135 CVP
    @router.get("/cvp/summary")
    def cvp_summary(user=Depends(get_current_user)):
        result = _cvp.get_cvp_summary()
        _audit_product("cvp.summary", user, result)
        return result

    @router.get("/cvp/{segment}")
    def cvp_segment(segment: str,
                      user=Depends(get_current_user)):
        result = _cvp.generate_cvp_for_segment(segment).as_dict()
        _audit_product("cvp.segment", user, {"segment": segment})
        return result

    # ENH-136 Ranking
    @router.get("/ranking/distribution")
    def ranking_dist(user=Depends(get_current_user)):
        result = _ranking.get_score_distribution()
        _audit_product("ranking.distribution", user, result)
        return result

    @router.get("/ranking/{product_id}")
    def ranking_score(product_id: str,
                         user=Depends(get_current_user)):
        result = _ranking.get_product_score(product_id).as_dict()
        _audit_product("ranking.score", user,
                         {"product_id": product_id})
        return result

    # ENH-137 Pricing
    @router.get("/pricing/actionable")
    def pricing_actionable(user=Depends(get_current_user)):
        result = _pricing.get_actionable_recommendations()
        _audit_product("pricing.actionable", user,
                         {"n": len(result)})
        return {"actionable_recommendations": result}

    @router.get("/pricing/{product_id}")
    def pricing_product(product_id: str,
                          user=Depends(get_current_user)):
        result = _pricing.get_pricing_recommendation(
            product_id).as_dict()
        _audit_product("pricing.product", user,
                         {"product_id": product_id})
        return result

    # ENH-138 Recommendation
    @router.get("/recommend/customer/{cif}")
    def recommend_customer(cif: str, n: int = 3,
                              user=Depends(get_current_user)):
        result = _recommendation.recommend_for_customer(
            cif, n).as_dict()
        _audit_product("recommend.customer", user,
                         {"cif": cif, "n": n})
        return result

    @router.get("/recommend/segment/{segment}")
    def recommend_segment(segment: str, n: int = 3,
                             user=Depends(get_current_user)):
        result = _recommendation.recommend_for_segment(segment, n)
        _audit_product("recommend.segment", user,
                         {"segment": segment, "n": n})
        return result

    # ENH-139 Bundling
    @router.get("/bundling/top")
    def bundling_top(min_affinity: float = 0.0, top_n: int = 10,
                       user=Depends(get_current_user)):
        result = _bundling.get_top_bundles(
            min_affinity=min_affinity, top_n=top_n)
        _audit_product("bundling.top", user,
                         {"n_returned": len(result)})
        return {"bundles": result}

    @router.get("/bundling/segment/{segment}")
    def bundling_segment(segment: str, top_n: int = 5,
                            user=Depends(get_current_user)):
        result = _bundling.get_segment_bundles(segment, top_n=top_n)
        _audit_product("bundling.segment", user,
                         {"segment": segment})
        return result

    # ENH-140 Dashboard
    @router.get("/dashboard")
    def dashboard_full(include_per_customer: bool = False,
                          user=Depends(get_current_user)):
        result = _dashboard.get_dashboard_payload(
            include_per_customer=include_per_customer).as_dict()
        _audit_product("dashboard.full", user,
                         {"per_customer": include_per_customer})
        return result

    @router.get("/dashboard/health")
    def dashboard_health(user=Depends(get_current_user)):
        result = _dashboard.get_engine_health_check()
        _audit_product("dashboard.health", user,
                         {"all_healthy": result.get("all_healthy")})
        return result

    @router.get("/dashboard/summary")
    def dashboard_summary(user=Depends(get_current_user)):
        result = _dashboard.get_summary_metrics()
        _audit_product("dashboard.summary", user,
                         {"n_products": result.get("n_products")})
        return result

else:
    # FastAPI not installed — define a placeholder so import doesn't fail
    router = None
