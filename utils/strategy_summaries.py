"""utils/strategy_summaries.py — v10.191

Adapter module producing a unified summary shape for the 15 Strategy
module engines (ENH-141..ENH-155).

The Strategy engines pre-date the `board_summary()` contract that
later modules (Treasury, Compliance, Legal, Resource Optimization)
adopted. They expose transformation methods rather than
state-observer summaries. This adapter wraps each engine and produces
a normalized dict shape suitable for cockpit display and REST API
exposure:

    {
        "engine":         <module name>,
        "engine_class":   <class name>,
        "module":         "strategy",
        "standard_id":    "ENH-XXX",
        "n_records":      <count of records in data_dir, where applicable>,
        "regulatory_basis": <reference framework>,
        "deferrals":      [<honest deferral 1>, ...],
        "config":         {<engine-specific knobs>},
    }

The adapters read counts from JSON files in `data_dir` (e.g.,
strategic_initiatives.json, strategy_lessons.json) so the summaries
reflect real platform state when data has been loaded, and degrade
gracefully to zero-count when files are absent.

Used by:
    - utils/api_strategy.py (REST API)
    - pages/30_strategy_arc_cockpit.py (Streamlit cockpit)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def _count_records(data_dir: Path, filename: str) -> int:
    """Count records in a JSON file in data_dir. Returns 0 on any failure
    (file missing, malformed, non-list/dict). Never raises."""
    try:
        path = Path(data_dir) / filename
        if not path.exists():
            return 0
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return len(data)
        return 0
    except Exception:
        return 0


def _data_dir(engine: Any) -> Path:
    """Extract data_dir from an engine instance, defaulting to ./data."""
    return Path(getattr(engine, "data_dir", Path("data")))


# ─────────────────────────────────────────────────────────────────
# ENH-141  StrategyFormulationEngine
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_formulation(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-141 Strategy Formulation Intelligence."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_formulation",
        "engine_class": "StrategyFormulationEngine",
        "module": "strategy",
        "standard_id": "ENH-141",
        "n_swot_records":   _count_records(dd, "strategy_swot.json"),
        "n_market_research": _count_records(dd, "market_research.json"),
        "regulatory_basis": "BSC strategic alignment + ICAAP strategic risk",
        "deferrals": [
            "AI synthesis hook present but production LLM not wired",
            "Competitor data ingestion limited to manual upload",
            "Macro factor sensitivity model not yet calibrated",
            "Vision-to-pillar traceability shown but not enforced",
        ],
        "config": {
            "ai_insight_fn_wired": getattr(engine, "ai_insight_fn", None) is not None,
            "data_dir": str(dd),
        },
    }


# ─────────────────────────────────────────────────────────────────
# ENH-142  StrategicOptionsGenerator
# ─────────────────────────────────────────────────────────────────
def summarize_strategic_options(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-142 Strategic Options Generator."""
    dd = _data_dir(engine)
    return {
        "engine": "strategic_options",
        "engine_class": "StrategicOptionsGenerator",
        "module": "strategy",
        "standard_id": "ENH-142",
        "n_options": _count_records(dd, "strategic_options.json"),
        "regulatory_basis": "Strategy options analysis (Porter / Ansoff)",
        "deferrals": [
            "Quantitative impact model uses linear assumptions",
            "Comparison matrix weights not learned from outcomes",
            "Competitor response simulation deferred",
            "Cost-of-delay scoring not yet integrated",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-143  StrategyDecompositionEngine
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_decomposition(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-143 Strategic Pillars & Workstream Mapping."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_decomposition",
        "engine_class": "StrategyDecompositionEngine",
        "module": "strategy",
        "standard_id": "ENH-143",
        "n_pillars":      _count_records(dd, "strategic_pillars.json"),
        "n_workstreams":  _count_records(dd, "workstream_mapping.json"),
        "n_role_maps":    _count_records(dd, "role_contributions.json"),
        "regulatory_basis": "BSC pillar decomposition standard",
        "deferrals": [
            "Department-to-pillar mapping requires manual seed",
            "Role contribution weights not auto-derived",
            "Pillar overlap detection limited to set intersection",
            "Workstream KPI inheritance one-level only",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-144  StrategicInitiativePortfolio
# ─────────────────────────────────────────────────────────────────
def summarize_initiative_portfolio(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-144 Strategic Initiative & Portfolio Management."""
    dd = _data_dir(engine)
    return {
        "engine": "initiative_portfolio",
        "engine_class": "StrategicInitiativePortfolio",
        "module": "strategy",
        "standard_id": "ENH-144",
        "n_initiatives": _count_records(dd, "strategic_initiatives.json"),
        "n_in_execution": _count_records(dd, "execute_initiatives.json"),
        "regulatory_basis": "Portfolio management / capital allocation governance",
        "deferrals": [
            "Knapsack optimizer uses greedy approximation",
            "Risk-adjusted ROI uses single discount rate",
            "Resource leveling across phases not enforced",
            "Stage-gate kill criteria require manual review",
        ],
        "config": {
            "ai_proposer_wired": getattr(engine, "ai_proposer_fn", None) is not None,
            "ai_scorer_wired":   getattr(engine, "ai_scorer_fn", None) is not None,
            "data_dir": str(dd),
        },
    }


# ─────────────────────────────────────────────────────────────────
# ENH-145  EnhancedCascadeEngine
# ─────────────────────────────────────────────────────────────────
def summarize_enhanced_cascade(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-145 OKR/BSC Cascade Engine (Enhanced)."""
    dd = _data_dir(engine)
    return {
        "engine": "enhanced_cascade",
        "engine_class": "EnhancedCascadeEngine",
        "module": "strategy",
        "standard_id": "ENH-145",
        "n_cascade_links": _count_records(dd, "cascade_links.json"),
        "n_okrs":          _count_records(dd, "okr_records.json"),
        "regulatory_basis": "OKR cascade + BSC visibility standard",
        "deferrals": [
            "Cross-functional cascade requires manual approval",
            "Stretch vs commit OKR distinction not auto-classified",
            "Cascade drift detection runs on demand only",
            "Visibility dashboard is read-only (no inline edit)",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-146  StrategyGapAnalyzer
# ─────────────────────────────────────────────────────────────────
def summarize_gap_analyzer(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-146 Strategy Execution Gap Analyzer."""
    dd = _data_dir(engine)
    return {
        "engine": "gap_analyzer",
        "engine_class": "StrategyGapAnalyzer",
        "module": "strategy",
        "standard_id": "ENH-146",
        "n_gap_records":     _count_records(dd, "strategy_gaps.json"),
        "n_root_causes":     _count_records(dd, "gap_root_causes.json"),
        "regulatory_basis": "Strategy execution governance",
        "deferrals": [
            "Root cause analysis uses fishbone heuristic only",
            "Systemic vs local gap classification thresholds static",
            "Pillar gap detection requires complete cascade",
            "Closure plan validation is advisory not enforced",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-147  CorrectiveActionGenerator
# ─────────────────────────────────────────────────────────────────
def summarize_corrective_actions(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-147 Corrective Action Generator."""
    dd = _data_dir(engine)
    return {
        "engine": "corrective_actions",
        "engine_class": "CorrectiveActionGenerator",
        "module": "strategy",
        "standard_id": "ENH-147",
        "n_actions": _count_records(dd, "corrective_actions.json"),
        "regulatory_basis": "Strategy execution governance",
        "deferrals": [
            "Action prioritization uses fixed weight scheme",
            "Resource availability check not auto-validated",
            "Auto-assignment to RACI not yet wired",
            "Effectiveness tracking requires post-hoc review",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-148  StrategyLearningLoop
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_learning(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-148 Strategy Learning Loop & Next Planning."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_learning",
        "engine_class": "StrategyLearningLoop",
        "module": "strategy",
        "standard_id": "ENH-148",
        "n_lessons":  _count_records(dd, "strategy_lessons.json"),
        "n_insights": _count_records(dd, "strategy_insights.json"),
        "regulatory_basis": "Learning organization / continuous improvement",
        "deferrals": [
            "Pattern detection across cycles requires manual review",
            "Failure factor extraction uses keyword heuristic",
            "Cross-org lesson sharing not automated",
            "Insight ranking weights not adaptive",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-149  StakeholderEngagementEngine
# ─────────────────────────────────────────────────────────────────
def summarize_stakeholder_engagement(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-149 Stakeholder Engagement & Pulse Engine."""
    dd = _data_dir(engine)
    return {
        "engine": "stakeholder_engagement",
        "engine_class": "StakeholderEngagementEngine",
        "module": "strategy",
        "standard_id": "ENH-149",
        "n_pulse_records":     _count_records(dd, "engagement_pulse.json"),
        "n_campaign_submissions": _count_records(dd, "campaign_submissions.json"),
        "regulatory_basis": "Internal communications + change management",
        "deferrals": [
            "Pulse score weights not validated against outcomes",
            "Campaign submission ranking is rule-based",
            "Engagement classification thresholds static",
            "Cross-segment pulse aggregation deferred",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-150  StrategyHealthEngine
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_health(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-150 Strategy Review & Health Dashboard."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_health",
        "engine_class": "StrategyHealthEngine",
        "module": "strategy",
        "standard_id": "ENH-150",
        "n_reviews": _count_records(dd, "strategy_reviews.json"),
        "regulatory_basis": "Board oversight / strategy review governance",
        "deferrals": [
            "Health composite uses static weight scheme",
            "Trend analysis requires ≥3 review cycles",
            "Comparative health (peer banks) not integrated",
            "Drill-down to root metric requires manual query",
        ],
        "config": {
            "ai_insight_fn_wired": getattr(engine, "ai_insight_fn", None) is not None,
            "data_dir": str(dd),
        },
    }


# ─────────────────────────────────────────────────────────────────
# ENH-151  StrategySimulator
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_simulator(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-151 Strategy Simulation & What-If Analyzer."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_simulator",
        "engine_class": "StrategySimulator",
        "module": "strategy",
        "standard_id": "ENH-151",
        "n_scenarios": _count_records(dd, "strategy_scenarios.json"),
        "regulatory_basis": "Scenario analysis / strategic risk",
        "deferrals": [
            "Resource reallocation model uses linear elasticity",
            "Risk assessment fixed parameter set",
            "Multi-scenario comparison limited to 4 scenarios",
            "Pillar interaction effects not modeled",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-152  StrategyCommunicationEngine
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_communication(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-152 Strategy Communication Engine."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_communication",
        "engine_class": "StrategyCommunicationEngine",
        "module": "strategy",
        "standard_id": "ENH-152",
        "n_distributions": _count_records(dd, "strategy_communications.json"),
        "n_feedback":       _count_records(dd, "communication_feedback.json"),
        "regulatory_basis": "Internal communications standards",
        "deferrals": [
            "Sentiment analysis uses rule-based scoring",
            "Audience segmentation static (exec/manager/staff)",
            "Multi-channel orchestration not yet wired",
            "Feedback closure loop requires manual triage",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-153  DailyStrategyIntegration
# ─────────────────────────────────────────────────────────────────
def summarize_daily_strategy_integration(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-153 Strategy to BSC Daily Integration."""
    dd = _data_dir(engine)
    return {
        "engine": "daily_strategy_integration",
        "engine_class": "DailyStrategyIntegration",
        "module": "strategy",
        "standard_id": "ENH-153",
        "n_daily_pulls": _count_records(dd, "daily_strategy_pulls.json"),
        "regulatory_basis": "BSC daily integration + strategy linkage",
        "deferrals": [
            "Daily refresh uses synchronous pull (no streaming)",
            "Drift alerts threshold static (5pp band)",
            "Strategy-BSC reconciliation requires nightly batch",
            "Backfill of historical periods runs on demand",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-154  STOToolkit
# ─────────────────────────────────────────────────────────────────
def summarize_sto_toolkit(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-154 Strategy Transformation Office Toolkit."""
    dd = _data_dir(engine)
    return {
        "engine": "sto_toolkit",
        "engine_class": "STOToolkit",
        "module": "strategy",
        "standard_id": "ENH-154",
        "n_minutes":  _count_records(dd, "strategy_minutes.json"),
        "n_risks":    _count_records(dd, "strategy_risks.json"),
        "n_training": _count_records(dd, "strategy_training.json"),
        "regulatory_basis": "Strategy transformation governance / PMO",
        "deferrals": [
            "Review pack generation uses fixed template",
            "Risk register lacks Monte Carlo aggregation",
            "Training competency mapping static",
            "Toolkit payload size not paginated",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# ENH-155  StrategyROIAnalytics
# ─────────────────────────────────────────────────────────────────
def summarize_strategy_roi(engine: Any) -> Dict[str, Any]:
    """Adapter for ENH-155 Strategy ROI & Impact Analytics."""
    dd = _data_dir(engine)
    return {
        "engine": "strategy_roi",
        "engine_class": "StrategyROIAnalytics",
        "module": "strategy",
        "standard_id": "ENH-155",
        "n_roi_records": _count_records(dd, "strategy_roi_records.json"),
        "regulatory_basis": "Capital allocation governance + ICAAP",
        "deferrals": [
            "Payback model uses simple cumulative cash flow",
            "Customer impact uses static elasticity",
            "Risk reduction quantification heuristic-based",
            "Employee impact composite not validated against engagement",
        ],
        "config": {"data_dir": str(dd)},
    }


# ─────────────────────────────────────────────────────────────────
# Cross-engine snapshot
# ─────────────────────────────────────────────────────────────────
ADAPTERS = {
    "strategy_formulation":        summarize_strategy_formulation,
    "strategic_options":           summarize_strategic_options,
    "strategy_decomposition":      summarize_strategy_decomposition,
    "initiative_portfolio":        summarize_initiative_portfolio,
    "enhanced_cascade":            summarize_enhanced_cascade,
    "gap_analyzer":                summarize_gap_analyzer,
    "corrective_actions":          summarize_corrective_actions,
    "strategy_learning":           summarize_strategy_learning,
    "stakeholder_engagement":      summarize_stakeholder_engagement,
    "strategy_health":             summarize_strategy_health,
    "strategy_simulator":          summarize_strategy_simulator,
    "strategy_communication":      summarize_strategy_communication,
    "daily_strategy_integration":  summarize_daily_strategy_integration,
    "sto_toolkit":                 summarize_sto_toolkit,
    "strategy_roi":                summarize_strategy_roi,
}
