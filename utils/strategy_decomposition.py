"""utils.strategy_decomposition — Strategic Pillars & Workstream Mapping
(Standard ENH-143, v10.136). Phase 1 Strategy Module — third engine.

Per Continuation.docx §Standard #143 (Eco Bank QA spec):
    StrategyDecompositionEngine — decompose strategy into 3-5 pillars,
    each with owner / success metrics / workstreams; map workstreams
    to contributing departments and roles to create an accountability
    matrix.

This is a Category D standard (LLM scaffolding for vision-aware pillar
refinement; the core decomposition is fully deterministic over the 5
canonical pillar templates plus a default workstream-to-department map).

WHAT THIS MODULE SHIPS
----------------------
1. StrategyDecompositionEngine class with:
   - define_strategic_pillars(vision, strategic_options=None) — selects
     3-5 pillars from 5 canonical templates based on vision keyword
     match; each pillar has name, description, owner, success_metrics,
     workstreams
   - map_workstream_contributions(pillars) — produces contribution
     matrix (pillar → workstream → departments → role_contributions)
   - identify_contributing_departments(workstream) — default mapping
   - LLM hook ai_refine_pillar (injectable; falls back to template)

2. Five canonical pillar templates (per Continuation.docx Standard #143):
   - Customer Experience Excellence    (Chief Customer Officer)
   - Digital & Data Transformation     (CTO/CDO)
   - Operational Excellence            (COO)
   - Risk & Compliance Leadership      (CRO)
   - Sustainable Growth                (CFO)

3. Default workstream-to-department mapping covering 25+ canonical
   bank workstreams across the 5 pillars.

HONESTY DISCIPLINE
------------------
- Default workstreams have placeholder target_date strings (e.g.,
  "Q4 2026") that callers replace with real planning dates
- Vision-keyword pillar selection is rule-based (deterministic);
  LLM-refinement is opt-in
- The 5 templates are explicitly canonical — banks customizing the
  templates pass their own pillar dicts to map_workstream_contributions
  directly, bypassing define_strategic_pillars

RELATED STANDARDS
-----------------
- ENH-141 SWOT engine — produces input vision context
- ENH-142 Strategic Options Generator — produces strategic_options input
- ENH-144 Strategic Initiative & Portfolio Management — consumes pillars
  to score and prioritize initiatives
- ENH-145 OKR/BSC Cascade (Enhanced) — consumes pillars for cascade
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.strategy_decomposition")


# ════════════════════════════════════════════════════════════════════
# Five canonical pillar templates (per Continuation.docx Standard #143)
# ════════════════════════════════════════════════════════════════════

PILLAR_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "Customer Experience Excellence",
        "description":
            "Deliver personalized, omnichannel banking experience.",
        "owner":           "Chief Customer Officer",
        "success_metrics": ["NPS > 75", "CSAT > 4.5",
                            "Digital adoption > 70%"],
        "workstreams": [
            "Digital Onboarding",
            "Mobile App Enhancement",
            "Contact Centre Transformation",
        ],
        "vision_keywords":
            ("customer", "experience", "service", "satisfaction",
             "nps", "loyalty", "personalized", "omnichannel"),
    },
    {
        "name": "Digital & Data Transformation",
        "description":
            "Leverage AI and data for competitive advantage.",
        "owner":           "CTO/CDO",
        "success_metrics": ["AI adoption in 5 processes",
                            "Data quality score > 95%",
                            "API calls growth > 50%"],
        "workstreams": [
            "Data Lake",
            "AI/ML Models",
            "API Marketplace",
            "Cloud Migration",
        ],
        "vision_keywords":
            ("digital", "data", "ai", "ml", "api", "cloud", "platform",
             "fintech", "innovation", "automation", "transformation"),
    },
    {
        "name": "Operational Excellence",
        "description":
            "Improve efficiency and reduce costs.",
        "owner":           "COO",
        "success_metrics": ["CIR < 45%",
                            "TAT reduction of 30%",
                            "Automation rate > 60%"],
        "workstreams": [
            "Process Automation",
            "Cost Optimization",
            "Branch Efficiency",
            "Shared Services Centre",
        ],
        "vision_keywords":
            ("efficiency", "cost", "operational", "productivity",
             "lean", "process", "automation", "tat"),
    },
    {
        "name": "Risk & Compliance Leadership",
        "description":
            "Proactive risk management and regulatory excellence.",
        "owner":           "CRO",
        "success_metrics": ["NPL < 5%",
                            "Compliance score > 95%",
                            "Audit findings reduced by 50%"],
        "workstreams": [
            "Credit Risk Model",
            "AML/KYC Enhancement",
            "Regulatory Reporting",
            "Operational Risk Framework",
        ],
        "vision_keywords":
            ("risk", "compliance", "regulatory", "cbk", "kyc", "aml",
             "audit", "credit", "operational"),
    },
    {
        "name": "Sustainable Growth",
        "description":
            "Profitable growth with ESG focus.",
        "owner":           "CFO",
        "success_metrics": ["ROE > 18%",
                            "ESG score top quartile",
                            "Green lending portfolio > 10%"],
        "workstreams": [
            "ESG Framework",
            "Green Products",
            "Community Banking",
            "Diaspora Banking",
        ],
        "vision_keywords":
            ("growth", "sustainable", "esg", "green", "climate",
             "responsible", "expansion", "diaspora", "africa"),
    },
]


# ════════════════════════════════════════════════════════════════════
# Default workstream → contributing departments mapping
# ════════════════════════════════════════════════════════════════════

# Department names match data/users.json values (Eco Bank Kenya HR
# taxonomy). 22 actual departments observed in seed:
#   Retail Banking (1075), Digital Financial Services (106),
#   Bancassurance (53), Credit (30), Commercial & Corporate (27),
#   IT & Digital (21), Contact Centre (20), Operations (19),
#   Finance (14), Trade Finance (12), People & HR (9),
#   Support Services (8), Diaspora & Special Segments (7),
#   Treasury (7), Legal (6), Risk & Compliance (5), Executive (4),
#   Cybersecurity (4), Marketing (4), Business Intelligence (3),
#   Internal Audit (3), Agency Banking (1).
WORKSTREAM_TO_DEPARTMENTS: Dict[str, List[str]] = {
    # Customer Experience pillar
    "Digital Onboarding":
        ["Retail Banking", "Contact Centre", "IT & Digital",
         "Operations", "Digital Financial Services"],
    "Mobile App Enhancement":
        ["IT & Digital", "Digital Financial Services", "Marketing",
         "Retail Banking"],
    "Contact Centre Transformation":
        ["Contact Centre", "People & HR", "IT & Digital",
         "Retail Banking"],

    # Digital & Data pillar
    "Data Lake":
        ["IT & Digital", "Business Intelligence",
         "Risk & Compliance", "Finance"],
    "AI/ML Models":
        ["Business Intelligence", "IT & Digital",
         "Risk & Compliance", "Internal Audit"],
    "API Marketplace":
        ["IT & Digital", "Digital Financial Services", "Legal"],
    "Cloud Migration":
        ["IT & Digital", "Cybersecurity", "Support Services"],

    # Operational Excellence pillar
    "Process Automation":
        ["Operations", "IT & Digital", "People & HR",
         "Retail Banking"],
    "Cost Optimization":
        ["Finance", "Operations", "People & HR", "Support Services"],
    "Branch Efficiency":
        ["Retail Banking", "Operations", "Contact Centre",
         "People & HR"],
    "Shared Services Centre":
        ["Operations", "People & HR", "IT & Digital", "Finance",
         "Support Services"],

    # Risk & Compliance pillar
    "Credit Risk Model":
        ["Risk & Compliance", "Credit", "Business Intelligence",
         "IT & Digital"],
    "AML/KYC Enhancement":
        ["Internal Audit", "Operations", "IT & Digital",
         "Risk & Compliance", "Retail Banking"],
    "Regulatory Reporting":
        ["Internal Audit", "Finance", "Risk & Compliance",
         "IT & Digital"],
    "Operational Risk Framework":
        ["Risk & Compliance", "Operations", "IT & Digital",
         "Internal Audit"],

    # Sustainable Growth pillar
    "ESG Framework":
        ["Risk & Compliance", "Marketing", "Internal Audit",
         "Executive"],
    "Green Products":
        ["Credit", "Marketing", "Treasury", "Commercial & Corporate"],
    "Community Banking":
        ["Retail Banking", "Agency Banking", "Marketing"],
    "Diaspora Banking":
        ["Diaspora & Special Segments", "Treasury", "IT & Digital",
         "Marketing"],
}

# Default placeholder target dates per pillar (callers should override
# with their actual planning calendar)
DEFAULT_TARGET_DATES = {
    "Customer Experience Excellence":     "Q4 2026",
    "Digital & Data Transformation":      "Q2 2027",
    "Operational Excellence":             "Q4 2026",
    "Risk & Compliance Leadership":       "Q3 2026",
    "Sustainable Growth":                  "Q4 2027",
}

# Pillar selection bounds (per doc spec)
MIN_PILLARS = 3
MAX_PILLARS = 5


# ════════════════════════════════════════════════════════════════════
# StrategyDecompositionEngine
# ════════════════════════════════════════════════════════════════════

class StrategyDecompositionEngine:
    """Decompose strategy into pillars and workstreams.

    Caller pattern:

        from utils.strategy_formulation import StrategyFormulationEngine
        from utils.strategic_options import StrategicOptionsGenerator
        from utils.strategy_decomposition import StrategyDecompositionEngine

        swot = StrategyFormulationEngine().generate_swot()
        options = StrategicOptionsGenerator().generate_options(
            "digital growth", swot)

        decomposer = StrategyDecompositionEngine()
        pillars = decomposer.define_strategic_pillars(
            vision="digital transformation and customer-centric banking",
            strategic_options=options["options"])
        matrix = decomposer.map_workstream_contributions(pillars)
    """

    def __init__(self,
                 ai_refiner_fn: Optional[
                     Callable[[Dict, str], Dict]] = None):
        """
        Args:
            ai_refiner_fn: optional callable(template_dict, vision_str)
                returning a refined pillar dict. When None, templates
                are returned as-is with default target dates added.
        """
        self.ai_refiner_fn = ai_refiner_fn

    # ── Pillar definition ──

    def define_strategic_pillars(
            self,
            vision: str,
            strategic_options: Optional[List[Dict[str, Any]]] = None
            ) -> List[Dict[str, Any]]:
        """Select 3-5 strategic pillars from 5 canonical templates.

        Args:
            vision: free-text vision statement
            strategic_options: optional list of options from ENH-142;
                used to bias pillar selection toward ones aligned with
                the recommended option's Ansoff type

        Returns:
            List of 3-5 pillar dicts, each with:
            {name, description, owner, success_metrics, workstreams,
             target_date, basis, source_template_id}
        """
        vision_lower = (vision or "").lower()
        scored_templates = []

        for idx, tpl in enumerate(PILLAR_TEMPLATES):
            score = self._score_template(tpl, vision_lower,
                                         strategic_options)
            scored_templates.append((score, idx, tpl))

        # Sort by score desc, take top 3-5
        scored_templates.sort(key=lambda x: -x[0])
        n_to_pick = min(MAX_PILLARS,
                        max(MIN_PILLARS,
                            sum(1 for s, _, _ in scored_templates
                                if s > 0)))
        selected = scored_templates[:n_to_pick]

        pillars = []
        for score, idx, tpl in selected:
            pillar = {
                "name":            tpl["name"],
                "description":     tpl["description"],
                "owner":           tpl["owner"],
                "success_metrics": list(tpl["success_metrics"]),
                "workstreams":     list(tpl["workstreams"]),
                "target_date":     DEFAULT_TARGET_DATES.get(
                                       tpl["name"], "Q4 2027"),
                "selection_score": score,
                "source_template_id": idx,
                "basis":           "rule_based",
            }
            # Optional LLM refinement
            if self.ai_refiner_fn is not None:
                try:
                    refined = self.ai_refiner_fn(pillar, vision)
                    refined["basis"] = "llm"
                    pillar = refined
                except Exception as e:
                    logger.warning(
                        f"ai_refiner_fn raised {type(e).__name__}: "
                        f"{e}; keeping template")
                    pillar["basis"] = "rule_based"
                    pillar["fallback_reason"] = (
                        f"LLM refiner raised {type(e).__name__}; used "
                        f"canonical template.")
            pillars.append(pillar)

        return pillars

    def _score_template(self,
                        template: Dict[str, Any],
                        vision_lower: str,
                        strategic_options: Optional[List[Dict]] = None
                        ) -> float:
        """Score a pillar template against vision keywords + selected
        strategic option's Ansoff type. Higher = better fit.

        Score components:
        - Vision keyword matches: each match adds 10 points (max 80)
        - Strategic-option alignment: if vision keyword overlaps with
          the recommended option's Ansoff keyword bucket: +20

        Returns 0-100.
        """
        keywords = template.get("vision_keywords", ())
        keyword_score = sum(10 for kw in keywords if kw in vision_lower)
        keyword_score = min(80, keyword_score)

        option_score = 0
        if strategic_options:
            # Prefer pillar templates aligned with the highest-impact option
            for opt in strategic_options:
                ansoff = opt.get("ansoff_type", "")
                # Cross-reference keywords (e.g., "digital" appears in both
                # Digital pillar's keywords AND product_development option)
                opt_initiatives = " ".join(
                    opt.get("key_initiatives", [])).lower()
                overlap = sum(1 for kw in keywords if kw in opt_initiatives)
                option_score = max(option_score, overlap * 5)
        option_score = min(20, option_score)

        return keyword_score + option_score

    # ── Workstream → contribution mapping ──

    def map_workstream_contributions(
            self,
            pillars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Produce accountability matrix: pillar → workstream →
        departments → role_contributions.

        Args:
            pillars: list of pillar dicts from define_strategic_pillars()
                (or caller-provided custom pillars)

        Returns:
            List of contribution matrix rows, one per workstream:
            {pillar, workstream, owner, departments, role_contributions,
             success_criteria, target_date}
        """
        matrix = []
        for pillar in pillars:
            workstreams = pillar.get("workstreams", [])
            for ws in workstreams:
                # Workstream may be a string (default) or dict (custom)
                if isinstance(ws, dict):
                    ws_name = ws.get("name", "Unnamed Workstream")
                    ws_owner = ws.get("owner") or pillar.get("owner")
                    ws_success = ws.get("success_criteria",
                                        pillar.get("success_metrics", []))
                    ws_target = ws.get("target_date",
                                       pillar.get("target_date"))
                else:
                    ws_name = ws
                    ws_owner = pillar.get("owner")
                    ws_success = pillar.get("success_metrics", [])
                    ws_target = pillar.get("target_date")

                departments = self.identify_contributing_departments(ws_name)
                role_contributions = self.map_role_contributions(
                    ws_name, departments)

                matrix.append({
                    "pillar":             pillar.get("name"),
                    "workstream":         ws_name,
                    "owner":              ws_owner,
                    "departments":        departments,
                    "role_contributions": role_contributions,
                    "success_criteria":   ws_success,
                    "target_date":        ws_target,
                })
        return matrix

    def identify_contributing_departments(
            self, workstream: str) -> List[str]:
        """Default workstream-to-department lookup; returns empty list
        for unknown workstreams (caller fills in)."""
        return WORKSTREAM_TO_DEPARTMENTS.get(workstream, [])

    def map_role_contributions(
            self,
            workstream: str,
            departments: List[str]) -> List[Dict[str, str]]:
        """Map departments to typical role contributions.

        Default mapping: each department contributes a "Lead" role and
        a "Member" role per workstream. Banks customizing roles (e.g.,
        "Programme Director" vs "Workstream Lead") replace this method.
        """
        roles = []
        for dept in departments:
            roles.append({
                "department": dept,
                "role":       "Lead" if dept == departments[0] else "Member",
                "contribution": (f"{dept} {'leads' if dept == departments[0] else 'contributes to'} "
                                 f"{workstream}"),
            })
        return roles


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def define_strategic_pillars(
        vision: str,
        strategic_options: Optional[List[Dict]] = None
        ) -> List[Dict[str, Any]]:
    """Convenience wrapper — instantiate engine and define pillars."""
    return StrategyDecompositionEngine().define_strategic_pillars(
        vision, strategic_options)
