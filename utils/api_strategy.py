"""utils.api_strategy — FastAPI router for the Strategy module (v10.141).

Exposes each of the 15 Strategy engines (ENH-141..155) as JSON-
serializable HTTP endpoints with JWT authentication. This is the
**React-ready surface** that the planned React frontend will consume.

DESIGN CONTRACT
---------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Each endpoint calls a single engine method and returns the dict
   directly. No transformation. The engine is the source of truth
   for both this API and the Streamlit cockpit (`pages/15_strategy_arc_cockpit.py`).
3. Pydantic models enforce request payload shapes
4. Engine results are already JSON-serializable (verified by the
   v10.135-v10.140 test suites)
5. Read-only contract honoured — no endpoint writes to performance.*
   tables; writes that engines do (e.g. `store_lessons` for ENH-148)
   go to JSON files isolated to the strategy module
6. Audit logging via `_audit_strategy(action, user, detail)` after
   every successful endpoint call — same pattern as utils/api.py

ENDPOINT MAP (one per Strategy standard)
-----------------------------------------
  POST /api/strategy/swot                   ENH-141 generate_swot
  POST /api/strategy/options                ENH-142 generate_options
  POST /api/strategy/pillars                ENH-143 define_strategic_pillars
  POST /api/strategy/portfolio/optimize     ENH-144 knapsack_optimize
  POST /api/strategy/cascade                ENH-145 cascade_with_engagement
  GET  /api/strategy/scorecard/{username}   ENH-153 create_personal_strategy_scorecard
  POST /api/strategy/gap                    ENH-146 analyze_gaps
  POST /api/strategy/corrective-actions     ENH-147 generate_corrective_actions
  POST /api/strategy/lessons                ENH-148 capture_lessons_learned
  GET  /api/strategy/pulse                  ENH-149 run_engagement_pulse
  POST /api/strategy/campaign               ENH-149 run_strategy_contribution_campaign
  GET  /api/strategy/health                 ENH-150 build_dashboard_payload
  POST /api/strategy/simulate               ENH-151 simulate_resource_reallocation
  POST /api/strategy/whatif                 ENH-151 what_if_scenario
  POST /api/strategy/communication          ENH-152 distribute_strategy_update
  GET  /api/strategy/sto                    ENH-154 get_full_toolkit_payload
  POST /api/strategy/sto/review-pack        ENH-154 generate_review_pack
  POST /api/strategy/roi                    ENH-155 calculate_strategy_roi

USAGE
-----
The router is mounted at `/api/strategy/*` from the parent FastAPI
app via:

    from utils.api_strategy import router as strategy_router
    app.include_router(strategy_router)

A React frontend can fetch any endpoint with:

    fetch('/api/strategy/health', {
      headers: { Authorization: `Bearer ${jwt}` }
    })

and receive the same dict the Streamlit cockpit renders.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from utils.auth_jwt import get_current_user
from utils.strategy_formulation import StrategyFormulationEngine
from utils.strategic_options import StrategicOptionsGenerator
from utils.strategy_decomposition import StrategyDecompositionEngine
from utils.initiative_portfolio import StrategicInitiativePortfolio
from utils.enhanced_cascade import EnhancedCascadeEngine
from utils.daily_strategy_integration import DailyStrategyIntegration
from utils.gap_analyzer import StrategyGapAnalyzer
from utils.corrective_actions import CorrectiveActionGenerator
from utils.strategy_learning import StrategyLearningLoop
from utils.stakeholder_engagement import StakeholderEngagementEngine
from utils.strategy_health import StrategyHealthEngine
from utils.strategy_simulator import StrategySimulator
from utils.strategy_communication import StrategyCommunicationEngine
from utils.sto_toolkit import STOToolkit
from utils.strategy_roi import StrategyROIAnalytics


logger = logging.getLogger("a2z.api.strategy")

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


# ════════════════════════════════════════════════════════════════════
# Audit helper
# ════════════════════════════════════════════════════════════════════

def _audit_strategy(action: str, user: dict, detail: str = "") -> None:
    """Best-effort audit emit — same shape as utils.api._audit."""
    try:
        from utils.core_audit import audit_log
        audit_log(
            user.get("username") or user.get("staff_code") or "api",
            f"strategy_api/{action}",
            detail)
    except Exception as e:
        logger.warning(f"audit_log failed: {e}")


# ════════════════════════════════════════════════════════════════════
# Pydantic request models
# ════════════════════════════════════════════════════════════════════

class SWOTRequest(BaseModel):
    steep_context: str = Field(
        ...,
        description=("STEEP narrative — Social/Tech/Economic/"
                     "Environmental/Political signals."))


class PillarRequest(BaseModel):
    intent: str = Field(...,
                         description="Strategic intent text.")


class PortfolioOptimizeRequest(BaseModel):
    budget_kes: float = Field(...,
                                gt=0,
                                description="Budget cap in KES.")
    pillar_intent: str = Field(
        default="digital growth",
        description="Strategic intent for pillar generation.")


class CascadeRequest(BaseModel):
    department: str
    pillar_okrs: List[Dict[str, Any]]
    feedback: Optional[List[Dict[str, Any]]] = None


class GapAnalyzeRequest(BaseModel):
    pillars: List[Dict[str, Any]]
    current_performance: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description=("Per-pillar performance signals — keyed by "
                     "pillar name."))


class CorrectiveActionRequest(BaseModel):
    gap: Dict[str, Any] = Field(
        ...,
        description=("Gap dict from StrategyGapAnalyzer — must include "
                     "root_cause.category, severity, gap, pillar, "
                     "metric."))


class LessonsRequest(BaseModel):
    strategy_cycle_id: str = Field(default="current")


class CampaignRequest(BaseModel):
    pillar_name: str
    submission_period_days: int = Field(default=30, ge=1, le=365)


class SimulateRequest(BaseModel):
    from_pillar: str
    to_pillar: str
    amount_kes: float = Field(..., gt=0)


class WhatIfRequest(BaseModel):
    name: str
    description: str = ""
    changes: List[Dict[str, Any]]
    horizon_months: int = Field(default=24, ge=1, le=120)


class CommunicationRequest(BaseModel):
    update_id: str
    title: str
    executive_summary: str = ""
    manager_summary: str = ""
    staff_summary: str = ""
    detailed_report_path: Optional[str] = None
    dashboard_link: Optional[str] = None


class ROIRequest(BaseModel):
    strategy_cycle_id: str = Field(default="current")
    cycle_duration_months: int = Field(default=12, ge=1, le=120)


# ════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════

@router.post("/swot")
def post_swot(req: SWOTRequest,
              user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """ENH-141 — Generate SWOT from STEEP context."""
    try:
        result = StrategyFormulationEngine().generate_swot(
            req.steep_context)
        _audit_strategy("swot_generated", user,
                         f"steep_len={len(req.steep_context)}")
        return result
    except Exception as e:
        logger.exception("swot endpoint failed")
        raise HTTPException(500, f"SWOT generation failed: {e}")


@router.post("/options")
def post_options(user: dict = Depends(get_current_user)
                  ) -> Dict[str, Any]:
    """ENH-142 — Generate ranked strategic options."""
    try:
        opts = StrategicOptionsGenerator().generate_options(
            swot=None, market_intel=None, competitor_intel=None)
        _audit_strategy("options_generated", user,
                         f"n={len(opts) if isinstance(opts, list) else 0}")
        return {"options": opts,
                "n_options": len(opts) if isinstance(opts, list) else 0}
    except Exception as e:
        logger.exception("options endpoint failed")
        raise HTTPException(500, f"Options generation failed: {e}")


@router.post("/pillars")
def post_pillars(req: PillarRequest,
                  user: dict = Depends(get_current_user)
                  ) -> Dict[str, Any]:
    """ENH-143 — Decompose strategic intent into pillars."""
    try:
        pillars = StrategyDecompositionEngine(
            ).define_strategic_pillars(req.intent)
        _audit_strategy("pillars_defined", user, f"n={len(pillars)}")
        return {"pillars": pillars, "n_pillars": len(pillars)}
    except Exception as e:
        logger.exception("pillars endpoint failed")
        raise HTTPException(500, f"Pillar decomposition failed: {e}")


@router.post("/portfolio/optimize")
def post_portfolio_optimize(req: PortfolioOptimizeRequest,
                              user: dict = Depends(get_current_user)
                              ) -> Dict[str, Any]:
    """ENH-144 — Knapsack-optimize initiative portfolio under budget."""
    try:
        portfolio = StrategicInitiativePortfolio()
        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            req.pillar_intent)
        initiatives = portfolio.get_proposed_initiatives(pillars)
        if not initiatives:
            return {"selected": [], "deferred": [],
                    "n_selected": 0, "n_deferred": 0,
                    "fallback_reason": "No initiatives in seed."}
        selected, deferred = portfolio.knapsack_optimize(
            initiatives, budget=req.budget_kes)
        _audit_strategy("portfolio_optimized", user,
                         f"selected={len(selected)} "
                         f"budget_kes={req.budget_kes}")
        return {
            "selected":    selected,
            "deferred":    deferred,
            "n_selected":  len(selected),
            "n_deferred":  len(deferred),
            "budget_kes":  req.budget_kes,
        }
    except Exception as e:
        logger.exception("portfolio endpoint failed")
        raise HTTPException(500, f"Portfolio optimization failed: {e}")


@router.post("/cascade")
def post_cascade(req: CascadeRequest,
                  user: dict = Depends(get_current_user)
                  ) -> Dict[str, Any]:
    """ENH-145 — Cascade pillar OKRs through E/M/A bands."""
    try:
        pillars = StrategyDecompositionEngine(
            ).define_strategic_pillars("digital growth")
        result = EnhancedCascadeEngine().cascade_with_engagement(
            pillar_okrs=req.pillar_okrs,
            department=req.department,
            feedback=req.feedback,
            strategic_pillars=pillars)
        _audit_strategy("cascade_built", user,
                         f"dept={req.department}")
        return result
    except Exception as e:
        logger.exception("cascade endpoint failed")
        raise HTTPException(500, f"Cascade build failed: {e}")


@router.get("/scorecard/{username}")
def get_personal_scorecard(username: str,
                             user: dict = Depends(get_current_user)
                             ) -> Dict[str, Any]:
    """ENH-153 — Personal strategy scorecard for a user."""
    try:
        scorecard = DailyStrategyIntegration(
            ).create_personal_strategy_scorecard(username)
        _audit_strategy("scorecard_viewed", user,
                         f"target_user={username}")
        return scorecard
    except Exception as e:
        logger.exception("scorecard endpoint failed")
        raise HTTPException(500, f"Scorecard fetch failed: {e}")


@router.post("/gap")
def post_gap_analyze(req: GapAnalyzeRequest,
                       user: dict = Depends(get_current_user)
                       ) -> Dict[str, Any]:
    """ENH-146 — Run gap analysis with decision-tree root-cause."""
    try:
        result = StrategyGapAnalyzer().analyze_gaps(
            req.pillars, req.current_performance)
        _audit_strategy("gap_analyzed", user,
                         f"high={result.get('n_high', 0)}")
        return result
    except Exception as e:
        logger.exception("gap endpoint failed")
        raise HTTPException(500, f"Gap analysis failed: {e}")


@router.post("/corrective-actions")
def post_corrective_actions(req: CorrectiveActionRequest,
                              user: dict = Depends(get_current_user)
                              ) -> Dict[str, Any]:
    """ENH-147 — Generate corrective actions for a gap."""
    try:
        result = CorrectiveActionGenerator().generate_corrective_actions(
            req.gap)
        _audit_strategy("actions_generated", user,
                         f"gap_id={req.gap.get('gap_id', '?')}")
        return result
    except Exception as e:
        logger.exception("corrective-actions endpoint failed")
        raise HTTPException(500, f"Action generation failed: {e}")


@router.post("/lessons")
def post_lessons(req: LessonsRequest,
                   user: dict = Depends(get_current_user)
                   ) -> Dict[str, Any]:
    """ENH-148 — Capture lessons learned from a strategy cycle."""
    try:
        result = StrategyLearningLoop().capture_lessons_learned(
            req.strategy_cycle_id)
        _audit_strategy("lessons_captured", user,
                         f"cycle={req.strategy_cycle_id} "
                         f"successful={result.get('n_successful', 0)}")
        return result
    except Exception as e:
        logger.exception("lessons endpoint failed")
        raise HTTPException(500, f"Lessons capture failed: {e}")


@router.get("/pulse")
def get_pulse(department: Optional[str] = None,
                period: Optional[str] = None,
                user: dict = Depends(get_current_user)
                ) -> Dict[str, Any]:
    """ENH-149 — Run engagement pulse, optionally filtered."""
    try:
        result = StakeholderEngagementEngine().run_engagement_pulse(
            department=department, period=period)
        _audit_strategy("pulse_run", user,
                         f"score={result.get('score')}")
        return result
    except Exception as e:
        logger.exception("pulse endpoint failed")
        raise HTTPException(500, f"Pulse failed: {e}")


@router.post("/campaign")
def post_campaign(req: CampaignRequest,
                    user: dict = Depends(get_current_user)
                    ) -> Dict[str, Any]:
    """ENH-149 — Create a strategy contribution campaign."""
    try:
        result = StakeholderEngagementEngine(
            ).run_strategy_contribution_campaign(
                {"name": req.pillar_name},
                submission_period_days=req.submission_period_days)
        _audit_strategy("campaign_created", user,
                         f"pillar={req.pillar_name}")
        return result
    except Exception as e:
        logger.exception("campaign endpoint failed")
        raise HTTPException(500, f"Campaign creation failed: {e}")


@router.get("/health")
def get_health(user: dict = Depends(get_current_user)
                 ) -> Dict[str, Any]:
    """ENH-150 — Strategy health dashboard payload."""
    try:
        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            "digital growth")
        pulse = StakeholderEngagementEngine().run_engagement_pulse()
        perf = {p["name"]: {"_signals": {}} for p in pillars}
        gap = StrategyGapAnalyzer().analyze_gaps(pillars, perf)
        result = StrategyHealthEngine().build_dashboard_payload(
            pillars=pillars,
            gap_result=gap,
            engagement_pulse=pulse if pulse.get("score") is not None
            else None)
        _audit_strategy("health_viewed", user,
                         f"score={result.get('overall_score')}")
        return result
    except Exception as e:
        logger.exception("health endpoint failed")
        raise HTTPException(500, f"Health dashboard failed: {e}")


@router.post("/simulate")
def post_simulate(req: SimulateRequest,
                    user: dict = Depends(get_current_user)
                    ) -> Dict[str, Any]:
    """ENH-151 — Simulate resource reallocation between pillars."""
    try:
        result = StrategySimulator().simulate_resource_reallocation(
            req.from_pillar, req.to_pillar, req.amount_kes)
        _audit_strategy("simulation_run", user,
                         f"from={req.from_pillar} to={req.to_pillar} "
                         f"amount_kes={req.amount_kes}")
        return result
    except Exception as e:
        logger.exception("simulate endpoint failed")
        raise HTTPException(500, f"Simulation failed: {e}")


@router.post("/whatif")
def post_whatif(req: WhatIfRequest,
                  user: dict = Depends(get_current_user)
                  ) -> Dict[str, Any]:
    """ENH-151 — Run a what-if scenario."""
    try:
        result = StrategySimulator().what_if_scenario(
            {
                "name":         req.name,
                "description":  req.description,
                "changes":      req.changes,
            },
            horizon_months=req.horizon_months)
        _audit_strategy("whatif_run", user,
                         f"name={req.name} "
                         f"changes={len(req.changes)}")
        return result
    except Exception as e:
        logger.exception("whatif endpoint failed")
        raise HTTPException(500, f"What-if failed: {e}")


@router.post("/communication")
def post_communication(req: CommunicationRequest,
                          user: dict = Depends(get_current_user)
                          ) -> Dict[str, Any]:
    """ENH-152 — Distribute a strategy update (dry-run unless adapters
    are configured at deployment).

    Note: this endpoint does NOT pretend messages were sent. When no
    channel adapters are injected at deployment, delivery_status will
    be DELIVERY_PREPARED for all recipients."""
    try:
        update = {
            "id":                  req.update_id,
            "title":               req.title,
            "executive_summary":   req.executive_summary,
            "manager_summary":     req.manager_summary,
            "staff_summary":       req.staff_summary,
            "detailed_report_path": req.detailed_report_path,
            "dashboard_link":      req.dashboard_link,
        }
        result = StrategyCommunicationEngine(
            ).distribute_strategy_update(update)
        _audit_strategy("comm_distribute", user,
                         f"id={req.update_id} "
                         f"total={result.get('n_total_recipients', 0)}")
        return result
    except Exception as e:
        logger.exception("communication endpoint failed")
        raise HTTPException(500, f"Distribution failed: {e}")


@router.get("/sto")
def get_sto_payload(user: dict = Depends(get_current_user)
                      ) -> Dict[str, Any]:
    """ENH-154 — Full STO command-centre payload (6 sections)."""
    try:
        result = STOToolkit().get_full_toolkit_payload()
        _audit_strategy("sto_viewed", user, "")
        return result
    except Exception as e:
        logger.exception("sto endpoint failed")
        raise HTTPException(500, f"STO toolkit fetch failed: {e}")


@router.post("/sto/review-pack")
def post_review_pack(user: dict = Depends(get_current_user)
                       ) -> Dict[str, Any]:
    """ENH-154 — Assemble structured strategy review pack payload."""
    try:
        result = STOToolkit().generate_review_pack()
        _audit_strategy("review_pack_generated", user,
                         f"basis={result.get('basis')}")
        return result
    except Exception as e:
        logger.exception("review-pack endpoint failed")
        raise HTTPException(500, f"Review pack assembly failed: {e}")


@router.post("/roi")
def post_roi(req: ROIRequest,
              user: dict = Depends(get_current_user)
              ) -> Dict[str, Any]:
    """ENH-155 — Calculate strategy ROI for a cycle."""
    try:
        result = StrategyROIAnalytics().calculate_strategy_roi(
            req.strategy_cycle_id,
            cycle_duration_months=req.cycle_duration_months)
        _audit_strategy("roi_calculated", user,
                         f"cycle={req.strategy_cycle_id} "
                         f"roi_pct={result.get('roi_percentage')}")
        return result
    except Exception as e:
        logger.exception("roi endpoint failed")
        raise HTTPException(500, f"ROI calculation failed: {e}")


# ════════════════════════════════════════════════════════════════════
# Module discovery (for React frontend)
# ════════════════════════════════════════════════════════════════════

@router.get("/_meta")
def get_strategy_meta(user: dict = Depends(get_current_user)
                        ) -> Dict[str, Any]:
    """Module metadata — useful for React frontend route discovery."""
    return {
        "module":         "strategy",
        "version":        "v10.141",
        "n_standards":    15,
        "standards":      [f"ENH-{n}" for n in range(141, 156)],
        "endpoints": [
            {"method": "POST", "path": "/api/strategy/swot",
              "standard": "ENH-141"},
            {"method": "POST", "path": "/api/strategy/options",
              "standard": "ENH-142"},
            {"method": "POST", "path": "/api/strategy/pillars",
              "standard": "ENH-143"},
            {"method": "POST", "path": "/api/strategy/portfolio/optimize",
              "standard": "ENH-144"},
            {"method": "POST", "path": "/api/strategy/cascade",
              "standard": "ENH-145"},
            {"method": "GET",  "path": "/api/strategy/scorecard/{username}",
              "standard": "ENH-153"},
            {"method": "POST", "path": "/api/strategy/gap",
              "standard": "ENH-146"},
            {"method": "POST", "path": "/api/strategy/corrective-actions",
              "standard": "ENH-147"},
            {"method": "POST", "path": "/api/strategy/lessons",
              "standard": "ENH-148"},
            {"method": "GET",  "path": "/api/strategy/pulse",
              "standard": "ENH-149"},
            {"method": "POST", "path": "/api/strategy/campaign",
              "standard": "ENH-149"},
            {"method": "GET",  "path": "/api/strategy/health",
              "standard": "ENH-150"},
            {"method": "POST", "path": "/api/strategy/simulate",
              "standard": "ENH-151"},
            {"method": "POST", "path": "/api/strategy/whatif",
              "standard": "ENH-151"},
            {"method": "POST", "path": "/api/strategy/communication",
              "standard": "ENH-152"},
            {"method": "GET",  "path": "/api/strategy/sto",
              "standard": "ENH-154"},
            {"method": "POST", "path": "/api/strategy/sto/review-pack",
              "standard": "ENH-154"},
            {"method": "POST", "path": "/api/strategy/roi",
              "standard": "ENH-155"},
        ],
        "auth":           "JWT Bearer (Depends(get_current_user))",
        "honesty_notes": [
            "All endpoints return engine-native dicts — no transformation",
            "ENH-152 returns DELIVERY_PREPARED status when no adapter "
            "(does NOT pretend messages were sent)",
            "ENH-150 weights re-normalize transparently on missing components",
            "ENH-155 indirect benefits LABELED is_estimate=True with ±20% band",
            "All AI hooks tagged basis='llm'; rule-based fallback transparent",
        ],
        "generated_at":   datetime.now(timezone.utc).isoformat(),
    }
