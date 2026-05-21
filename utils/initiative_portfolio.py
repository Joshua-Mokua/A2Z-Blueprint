"""utils.initiative_portfolio — Strategic Initiative & Portfolio Management
(Standard ENH-144, v10.136). Phase 1 Strategy Module — fourth engine.

Per Continuation.docx §Standard #144 (Eco Bank QA spec):
    StrategicInitiativePortfolio — manage strategic initiative
    portfolio with impact scoring, ROI scoring, risk assessment, and
    knapsack-optimized budget allocation.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Initiative scoring is deterministic over rule-based heuristics
     (alignment with pillar success metrics, ROI bands, risk bands)
  2. Knapsack optimization is classical 0/1 knapsack with bounded
     budget; same input → same selection
  3. AI-recommender hook injectable (ai_proposer_fn for generating
     initiatives from pillars; ai_scorer_fn for ML-based scoring) but
     disabled by default

WHAT THIS MODULE SHIPS
----------------------
1. StrategicInitiativePortfolio class with:
   - prioritize_initiatives(pillars, budget_constraint) — full pipeline:
     proposes initiatives, scores, runs knapsack, phases output
   - get_proposed_initiatives(pillars) — generates default initiatives
     from pillar workstreams (or reads from data/strategic_initiatives.json
     if available)
   - calculate_strategic_score(initiative, pillars) — alignment with
     pillar success metrics
   - calculate_roi_score(initiative) — ROI band scoring
   - assess_risk(initiative) — risk band scoring
   - knapsack_optimize(initiatives, budget) — classical 0/1 knapsack
     using dynamic programming
   - phase_initiatives(selected) — quarterly phasing schedule

2. Initiative score formula (per Continuation.docx Standard #144):
   combined_score = (
     strategic_score × 0.5 +     # alignment with pillars
     roi_score        × 0.3 +    # expected return
     (100 - risk_score) × 0.2    # inverted risk
   )

3. Default initiative generator: produces 1 initiative per workstream
   per pillar, with cost/ROI/risk estimates derived from workstream
   archetypes (e.g., "Cloud Migration" → high cost / medium ROI /
   medium risk).

HONESTY DISCIPLINE
------------------
- Knapsack returns the OPTIMAL solution within budget (not greedy
  approximation), guaranteeing reproducibility
- When budget is exhausted with un-selected high-priority initiatives,
  the result includes a `deferred_initiatives` list with their unmet
  cost so callers see what was cut
- ROI estimates are explicit BANDS (low/medium/high) translated to
  numeric scores, NOT fabricated KES projections
- Cost estimates use archetype defaults (low/med/high tiers); banks
  with their own initiative catalog override via JSON seed

RELATED STANDARDS
-----------------
- ENH-141 SWOT engine — provides external context
- ENH-142 Strategic Options Generator — provides Ansoff option context
- ENH-143 Strategic Pillars — provides input pillars (REQUIRED)
- ENH-145 OKR/BSC Cascade (planned) — consumes selected initiatives for cascade
- ENH-146 Strategy Execution Gap Analyzer (planned) — consumes
  initiative status to detect execution drift
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger("a2z.initiative_portfolio")


# ════════════════════════════════════════════════════════════════════
# Score weights (per Continuation.docx Standard #144 spec)
# ════════════════════════════════════════════════════════════════════

WEIGHT_STRATEGIC = 0.5     # alignment with pillar success metrics
WEIGHT_ROI = 0.3            # expected return
WEIGHT_RISK_INVERSE = 0.2   # inverted risk (lower risk = higher score)


# ════════════════════════════════════════════════════════════════════
# Workstream archetype → cost/ROI/risk band defaults
# ════════════════════════════════════════════════════════════════════

# Cost bands in KES millions (caller-overridable)
COST_BAND_LOW = 5_000_000        # KES 5M
COST_BAND_MEDIUM = 50_000_000    # KES 50M
COST_BAND_HIGH = 250_000_000     # KES 250M

# ROI percentage bands
ROI_BAND_LOW = 8.0       # 8% ROI
ROI_BAND_MEDIUM = 15.0   # 15% ROI
ROI_BAND_HIGH = 25.0     # 25% ROI

# Risk score bands (0-100, higher = riskier)
RISK_BAND_LOW = 20
RISK_BAND_MEDIUM = 50
RISK_BAND_HIGH = 75


WORKSTREAM_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    # Customer Experience — generally medium cost, high ROI, low-med risk
    "Digital Onboarding": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_HIGH,
        "risk":    RISK_BAND_LOW,
        "duration_months": 9,
    },
    "Mobile App Enhancement": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_HIGH,
        "risk":    RISK_BAND_LOW,
        "duration_months": 6,
    },
    "Contact Centre Transformation": {
        "cost":    COST_BAND_HIGH,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 12,
    },

    # Digital & Data — high cost, high ROI, medium-high risk
    "Data Lake": {
        "cost":    COST_BAND_HIGH,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 18,
    },
    "AI/ML Models": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_HIGH,
        "risk":    RISK_BAND_HIGH,
        "duration_months": 12,
    },
    "API Marketplace": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 9,
    },
    "Cloud Migration": {
        "cost":    COST_BAND_HIGH,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_HIGH,
        "duration_months": 24,
    },

    # Operational Excellence — low-medium cost, high ROI, low risk
    "Process Automation": {
        "cost":    COST_BAND_LOW,
        "roi":     ROI_BAND_HIGH,
        "risk":    RISK_BAND_LOW,
        "duration_months": 6,
    },
    "Cost Optimization": {
        "cost":    COST_BAND_LOW,
        "roi":     ROI_BAND_HIGH,
        "risk":    RISK_BAND_LOW,
        "duration_months": 6,
    },
    "Branch Efficiency": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_LOW,
        "duration_months": 9,
    },
    "Shared Services Centre": {
        "cost":    COST_BAND_HIGH,
        "roi":     ROI_BAND_HIGH,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 18,
    },

    # Risk & Compliance — medium cost, low-medium ROI, low risk
    "Credit Risk Model": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 12,
    },
    "AML/KYC Enhancement": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_LOW,   # cost-avoidance not direct ROI
        "risk":    RISK_BAND_LOW,
        "duration_months": 9,
    },
    "Regulatory Reporting": {
        "cost":    COST_BAND_LOW,
        "roi":     ROI_BAND_LOW,
        "risk":    RISK_BAND_LOW,
        "duration_months": 6,
    },
    "Operational Risk Framework": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_LOW,
        "risk":    RISK_BAND_LOW,
        "duration_months": 12,
    },

    # Sustainable Growth — variable
    "ESG Framework": {
        "cost":    COST_BAND_LOW,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_LOW,
        "duration_months": 9,
    },
    "Green Products": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 12,
    },
    "Community Banking": {
        "cost":    COST_BAND_HIGH,
        "roi":     ROI_BAND_LOW,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 18,
    },
    "Diaspora Banking": {
        "cost":    COST_BAND_MEDIUM,
        "roi":     ROI_BAND_MEDIUM,
        "risk":    RISK_BAND_MEDIUM,
        "duration_months": 12,
    },
}

# Fallback archetype for unknown workstreams
DEFAULT_ARCHETYPE = {
    "cost":    COST_BAND_MEDIUM,
    "roi":     ROI_BAND_MEDIUM,
    "risk":    RISK_BAND_MEDIUM,
    "duration_months": 12,
}


# ════════════════════════════════════════════════════════════════════
# StrategicInitiativePortfolio
# ════════════════════════════════════════════════════════════════════

class StrategicInitiativePortfolio:
    """Manage strategic initiative portfolio with knapsack optimization.

    Caller pattern:

        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.initiative_portfolio import StrategicInitiativePortfolio

        decomposer = StrategyDecompositionEngine()
        pillars = decomposer.define_strategic_pillars(vision)

        portfolio = StrategicInitiativePortfolio()
        result = portfolio.prioritize_initiatives(
            pillars, budget_constraint=500_000_000)  # KES 500M
        print(result["selected_initiatives"])
        print(result["deferred_initiatives"])
        print(result["recommended_phasing"])
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 ai_proposer_fn: Optional[
                     Callable[[List[Dict]], List[Dict]]] = None,
                 ai_scorer_fn: Optional[
                     Callable[[Dict], Dict]] = None):
        """
        Args:
            data_dir: where to read strategic_initiatives.json from.
                Defaults to repo's data/ directory.
            ai_proposer_fn: optional callable(pillars) → initiatives list
                for LLM-generated initiative proposals
            ai_scorer_fn: optional callable(initiative) → {strategic, roi,
                risk} scores for ML-based scoring
        """
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.ai_proposer_fn = ai_proposer_fn
        self.ai_scorer_fn = ai_scorer_fn

    # ── Initiative generation ──

    def _normalize_initiative(
            self,
            raw: Dict[str, Any],
            counter: int) -> Dict[str, Any]:
        """Normalize an initiative dict to canonical schema regardless
        of source. Maps common alternative field names to expected
        keys (initiative_code, initiative_name, estimated_cost,
        expected_roi, risk_band, duration_months, kpi_link).

        Pre-existing data/strategic_initiatives.json uses fields like
        'id', 'name', 'budget_kes_m', 'expected_roi_pct'; this method
        translates them.
        """
        # initiative_code: prefer initiative_code → id → generated
        code = (raw.get("initiative_code")
                or raw.get("id")
                or f"INI-{counter:03d}")

        # initiative_name: prefer initiative_name → name → fallback
        name = (raw.get("initiative_name")
                or raw.get("name")
                or f"Initiative {code}")

        # estimated_cost: prefer estimated_cost (KES) → budget_kes_m × 1M
        cost = raw.get("estimated_cost")
        if cost is None:
            kes_m = raw.get("budget_kes_m")
            if isinstance(kes_m, (int, float)):
                cost = kes_m * 1_000_000
            else:
                cost = COST_BAND_MEDIUM

        # expected_roi: prefer expected_roi (%) → expected_roi_pct
        roi = raw.get("expected_roi")
        if roi is None:
            roi = raw.get("expected_roi_pct", ROI_BAND_MEDIUM)

        # duration_months: from raw or compute from dates
        duration = raw.get("duration_months")
        if duration is None:
            # Try start_date / target_end_date
            sd = raw.get("start_date", "")
            ed = raw.get("target_end_date", "")
            if sd and ed and len(sd) >= 10 and len(ed) >= 10:
                try:
                    from datetime import datetime as _dt
                    s = _dt.strptime(sd[:10], "%Y-%m-%d")
                    e = _dt.strptime(ed[:10], "%Y-%m-%d")
                    duration = max(1, int((e - s).days / 30.4375))
                except (ValueError, TypeError):
                    duration = 12
            else:
                duration = 12

        # risk_band: prefer risk_band → derive from risks_identified
        risk_band = raw.get("risk_band")
        if risk_band is None:
            risks_id = raw.get("risks_identified", 0)
            risks_mit = raw.get("risks_mitigated", 0)
            net_risk = max(0, risks_id - risks_mit)
            risk_band = (RISK_BAND_LOW if net_risk == 0
                         else RISK_BAND_MEDIUM if net_risk <= 3
                         else RISK_BAND_HIGH)

        # kpi_link: prefer kpi_link → linked_kpis + linked_bsc_kpis
        kpi_link = raw.get("kpi_link")
        if kpi_link is None:
            kpi_link = (list(raw.get("linked_kpis", []))
                        + list(raw.get("linked_bsc_kpis", [])))

        # Build canonical dict, preserving original fields
        norm = dict(raw)  # copy original
        norm.update({
            "initiative_code": code,
            "initiative_name": name,
            "estimated_cost":  cost,
            "expected_roi":    roi,
            "risk_band":       risk_band,
            "duration_months": duration,
            "kpi_link":        kpi_link,
            "pillar":          raw.get("pillar", "Unknown"),
            "workstream":      raw.get("workstream", ""),
            "status":          raw.get("status", "proposed"),
            "owner":           raw.get("owner", ""),
            "dependencies":    raw.get("dependencies", []),
            "source":          raw.get("source", "seed_normalized"),
        })
        return norm

    def get_proposed_initiatives(
            self,
            pillars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate or load proposed initiatives.

        Resolution order:
        1. If ai_proposer_fn injected: call it with pillars
        2. Else if data/strategic_initiatives.json exists: load + normalize
        3. Else: generate one initiative per workstream in each pillar
           using WORKSTREAM_ARCHETYPES
        """
        if self.ai_proposer_fn is not None:
            try:
                proposed = self.ai_proposer_fn(pillars)
                return [self._normalize_initiative(ini, idx + 1)
                        for idx, ini in enumerate(proposed)]
            except Exception as e:
                logger.warning(
                    f"ai_proposer_fn raised {type(e).__name__}: {e}; "
                    f"falling back to default generator")

        seed_path = self.data_dir / "strategic_initiatives.json"
        if seed_path.exists():
            try:
                with open(seed_path, encoding="utf-8") as f:
                    seed = json.load(f)
                raw_list = (seed if isinstance(seed, list)
                            else seed.get("initiatives", [])
                            if isinstance(seed, dict) else [])
                return [self._normalize_initiative(ini, idx + 1)
                        for idx, ini in enumerate(raw_list)]
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    f"strategic_initiatives.json unreadable: {e}; "
                    f"using default generator")

        # Default generator: one initiative per workstream
        initiatives = []
        counter = 0
        for pillar in pillars:
            pillar_name = pillar.get("name", "Unknown Pillar")
            workstreams = pillar.get("workstreams", [])
            for ws in workstreams:
                ws_name = ws if isinstance(ws, str) else ws.get("name", "")
                if not ws_name:
                    continue
                arch = WORKSTREAM_ARCHETYPES.get(
                    ws_name, DEFAULT_ARCHETYPE)
                counter += 1
                initiatives.append({
                    "initiative_code": f"INI-{counter:03d}",
                    "initiative_name": f"{ws_name} Programme",
                    "pillar":           pillar_name,
                    "workstream":       ws_name,
                    "description":
                        f"Implement {ws_name} as part of "
                        f"{pillar_name} pillar.",
                    "estimated_cost":   arch["cost"],
                    "expected_roi":     arch["roi"],
                    "risk_band":        arch["risk"],
                    "duration_months":  arch["duration_months"],
                    "owner":            pillar.get("owner"),
                    "status":           "proposed",
                    "kpi_link":         pillar.get("success_metrics", []),
                    "dependencies":     [],
                    "source":           "default_generator",
                })
        return initiatives

    # ── Scoring ──

    def calculate_strategic_score(
            self,
            initiative: Dict[str, Any],
            pillars: List[Dict[str, Any]]) -> float:
        """Strategic alignment score (0-100).

        Logic:
        - Base: how many of the initiative's kpi_links match the
          owning pillar's success_metrics (deterministic match)
        - Boost: workstream count of pillar (more workstreams →
          higher pillar weight in strategy)
        """
        pillar_name = initiative.get("pillar")
        pillar = next((p for p in pillars
                       if p.get("name") == pillar_name), None)
        if not pillar:
            return 50.0  # neutral score for orphan initiatives

        # KPI alignment
        ini_kpis = initiative.get("kpi_link", []) or []
        pillar_metrics = pillar.get("success_metrics", []) or []
        matches = sum(1 for k in ini_kpis if k in pillar_metrics)
        kpi_score = (matches / max(len(pillar_metrics), 1)) * 70.0

        # Pillar weight (more workstreams → more important)
        workstream_count = len(pillar.get("workstreams", []))
        pillar_weight = min(30.0, workstream_count * 6.0)

        return round(kpi_score + pillar_weight, 2)

    def calculate_roi_score(self, initiative: Dict[str, Any]) -> float:
        """Convert expected_roi % into a 0-100 score.

        Mapping (linear within bands):
        - 0-5%   → 0-20
        - 5-10%  → 20-40
        - 10-20% → 40-70
        - 20%+   → 70-100 (capped)
        """
        roi_pct = initiative.get("expected_roi", 0)
        if not isinstance(roi_pct, (int, float)) or roi_pct < 0:
            return 0.0
        if roi_pct <= 5:
            return roi_pct * 4.0           # 0-20
        if roi_pct <= 10:
            return 20 + (roi_pct - 5) * 4.0   # 20-40
        if roi_pct <= 20:
            return 40 + (roi_pct - 10) * 3.0  # 40-70
        return min(100.0, 70 + (roi_pct - 20) * 1.5)  # 70-100

    def assess_risk(self, initiative: Dict[str, Any]) -> float:
        """Risk score (0-100, higher = riskier).

        Uses risk_band field if present, else infers from cost +
        duration (longer + more expensive = riskier).
        """
        rb = initiative.get("risk_band")
        if isinstance(rb, (int, float)):
            return float(rb)

        # Fallback: compute from cost + duration
        cost = initiative.get("estimated_cost", 0)
        duration = initiative.get("duration_months", 12)
        risk = 30  # base
        if cost >= COST_BAND_HIGH:    risk += 25
        elif cost >= COST_BAND_MEDIUM: risk += 10
        if duration >= 18:             risk += 20
        elif duration >= 12:           risk += 10
        return min(100.0, risk)

    # ── Knapsack optimization (classical 0/1 knapsack) ──

    def knapsack_optimize(
            self,
            initiatives: List[Dict[str, Any]],
            budget: float) -> Tuple[List[Dict[str, Any]],
                                    List[Dict[str, Any]]]:
        """Classical 0/1 knapsack: maximize sum(combined_score) subject
        to sum(estimated_cost) ≤ budget.

        For practical bank initiative portfolios (typically <100
        initiatives), this DP runs in O(n × budget) where budget is
        scaled to tens of millions. We round costs to KES 1M units
        to keep DP table small.

        Returns (selected, deferred) tuple of dicts.

        Args:
            initiatives: must each have 'combined_score' and
                'estimated_cost' keys (use prioritize_initiatives()
                wrapper which calls _score_each_initiative first).
            budget: max total cost in KES.

        Returns:
            (selected_initiatives, deferred_initiatives)
        """
        if not initiatives:
            return [], []

        # Scale costs to KES 1M units for tractable DP. Use ceil rather
        # than floor so the scaled-cost total is an UPPER bound on actual
        # cost — guarantees total_cost ≤ budget after selection.
        import math
        SCALE = 1_000_000
        scaled_budget = int(budget // SCALE)
        if scaled_budget < 1:
            return [], list(initiatives)

        n = len(initiatives)
        scaled_costs = [
            max(1, math.ceil((ini.get("estimated_cost", 0) or 0) / SCALE))
            for ini in initiatives
        ]
        # Combined scores; default to 0 if missing (defensive)
        scores = [
            float(ini.get("combined_score", 0))
            for ini in initiatives
        ]

        # DP table: dp[i][b] = max score using first i initiatives within budget b
        # Use rolling 1D array to save memory
        prev = [0.0] * (scaled_budget + 1)
        keep = [[False] * (scaled_budget + 1) for _ in range(n)]

        for i in range(n):
            curr = list(prev)
            cost_i = scaled_costs[i]
            score_i = scores[i]
            for b in range(scaled_budget, cost_i - 1, -1):
                take = prev[b - cost_i] + score_i
                if take > curr[b]:
                    curr[b] = take
                    keep[i][b] = True
            prev = curr

        # Backtrack to find selected
        selected_idx = []
        b = scaled_budget
        for i in range(n - 1, -1, -1):
            if b >= 0 and keep[i][b]:
                selected_idx.append(i)
                b -= scaled_costs[i]
        selected_idx.reverse()

        selected = [initiatives[i] for i in selected_idx]
        deferred = [initiatives[i] for i in range(n)
                    if i not in selected_idx]
        return selected, deferred

    # ── Phasing ──

    def phase_initiatives(
            self,
            selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Quarterly phasing: schedule selected initiatives across
        4-quarter horizon based on dependencies + duration.

        Default scheduling:
        - Phase 1 (Q1-Q2): Quick wins — duration ≤ 6 months
        - Phase 2 (Q3-Q4): Medium-term — duration 7-12 months
        - Phase 3 (Year 2): Long-term — duration > 12 months
        """
        phases = {
            "Phase 1 (Q1-Q2)":   [],
            "Phase 2 (Q3-Q4)":   [],
            "Phase 3 (Year 2+)": [],
        }
        for idx, ini in enumerate(selected):
            duration = ini.get("duration_months", 12)
            code = ini.get("initiative_code") or f"INI-?-{idx:03d}"
            if duration <= 6:
                phases["Phase 1 (Q1-Q2)"].append(code)
            elif duration <= 12:
                phases["Phase 2 (Q3-Q4)"].append(code)
            else:
                phases["Phase 3 (Year 2+)"].append(code)
        return [{"phase": ph, "initiative_codes": codes}
                for ph, codes in phases.items()]

    # ── Main API: prioritize ──

    def prioritize_initiatives(
            self,
            pillars: List[Dict[str, Any]],
            budget_constraint: float) -> Dict[str, Any]:
        """Full pipeline: propose → score → knapsack → phase.

        Args:
            pillars: from StrategyDecompositionEngine.define_strategic_pillars()
            budget_constraint: total budget in KES

        Returns:
            {
              "selected_initiatives":      [...],
              "deferred_initiatives":      [...],
              "total_cost":                float,
              "total_expected_roi":        float,
              "weighted_strategic_score":  float,
              "recommended_phasing":       [...],
              "budget_used_pct":           float,
              "n_proposed":                int,
              "n_selected":                int,
              "n_deferred":                int,
              "generated_at":              ISO-8601,
              "basis":                     "rule_based"
            }
        """
        initiatives = self.get_proposed_initiatives(pillars)
        if not initiatives:
            return {
                "selected_initiatives": [],
                "deferred_initiatives": [],
                "total_cost": 0,
                "total_expected_roi": 0,
                "weighted_strategic_score": 0,
                "recommended_phasing": [],
                "budget_used_pct": 0,
                "n_proposed": 0, "n_selected": 0, "n_deferred": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "basis": "rule_based",
                "warning": "No initiatives proposed; verify pillars "
                           "have populated workstreams.",
            }

        # Score each
        for ini in initiatives:
            if self.ai_scorer_fn is not None:
                try:
                    scores = self.ai_scorer_fn(ini)
                    ini["strategic_score"] = scores.get("strategic", 0)
                    ini["roi_score"] = scores.get("roi", 0)
                    ini["risk_score"] = scores.get("risk", 0)
                except Exception as e:
                    logger.warning(
                        f"ai_scorer_fn failed for {ini.get('initiative_code')}: "
                        f"{e}; using rule-based")
                    ini["strategic_score"] = self.calculate_strategic_score(
                        ini, pillars)
                    ini["roi_score"] = self.calculate_roi_score(ini)
                    ini["risk_score"] = self.assess_risk(ini)
            else:
                ini["strategic_score"] = self.calculate_strategic_score(
                    ini, pillars)
                ini["roi_score"] = self.calculate_roi_score(ini)
                ini["risk_score"] = self.assess_risk(ini)

            ini["combined_score"] = round(
                ini["strategic_score"] * WEIGHT_STRATEGIC
                + ini["roi_score"] * WEIGHT_ROI
                + (100 - ini["risk_score"]) * WEIGHT_RISK_INVERSE,
                2)

        # Knapsack optimize within budget
        selected, deferred = self.knapsack_optimize(
            initiatives, budget_constraint)

        # Aggregates
        total_cost = sum(i.get("estimated_cost", 0) for i in selected)
        total_roi = sum(i.get("expected_roi", 0) for i in selected)
        avg_score = (sum(i.get("combined_score", 0) for i in selected)
                     / max(len(selected), 1))

        return {
            "selected_initiatives":      selected,
            "deferred_initiatives":      deferred,
            "total_cost":                total_cost,
            "total_expected_roi":        round(total_roi, 2),
            "weighted_strategic_score":  round(avg_score, 2),
            "recommended_phasing":       self.phase_initiatives(selected),
            "budget_used_pct":           round(
                100 * total_cost / budget_constraint, 2)
                if budget_constraint > 0 else 0,
            "n_proposed":                len(initiatives),
            "n_selected":                len(selected),
            "n_deferred":                len(deferred),
            "generated_at":              datetime.now(
                timezone.utc).isoformat(),
            "basis":                     "rule_based",
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def prioritize_initiatives(
        pillars: List[Dict],
        budget_constraint: float) -> Dict[str, Any]:
    """Convenience wrapper — instantiate portfolio and prioritize."""
    return StrategicInitiativePortfolio().prioritize_initiatives(
        pillars, budget_constraint)
