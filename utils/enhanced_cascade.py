"""utils.enhanced_cascade — OKR/BSC Cascade Engine (Enhanced)
(Standard ENH-145, v10.137). Phase 1 Strategy Module — fifth engine.

Per Continuation.docx §Standard #145 (Eco Bank QA spec):
    EnhancedCascadeEngine — OKR/BSC cascade with full visibility
    and engagement: cascade pillar OKRs to departments with two-way
    feedback, then cascade to individuals; track alignment and
    engagement metrics.

This is a Category D standard (LLM scaffolding for sentiment-aware
feedback parsing; the cascade itself is fully deterministic).

WHAT THIS MODULE SHIPS
----------------------
1. EnhancedCascadeEngine class with:
   - cascade_with_engagement(pillar_okrs, department) — full pipeline:
     pillar OKRs → department OKRs → individual OKRs + alignment +
     engagement scoring
   - generate_department_okrs(pillar_okrs, department) — filters
     pillar OKRs to those workstreams the department owns
   - collect_department_feedback(department_okrs, feedback=None) —
     accepts caller-provided feedback dict or returns no-feedback
     stub; LLM hook for sentiment analysis injectable
   - align_okrs(department_okrs, feedback) — applies feedback updates
   - cascade_to_individuals(department_okrs, department) — splits
     KRs across employees in the department by band weighting
   - calculate_alignment_score(individual_okrs, strategic_pillars)
   - calculate_engagement(individual_okrs)

2. Department → workstream reverse lookup using
   utils.strategy_decomposition.WORKSTREAM_TO_DEPARTMENTS, so the
   cascade automatically knows which strategic pillars touch a given
   department.

3. Default OKR template per pillar:
   - Objective = pillar name
   - Key results = pillar success_metrics

HONESTY DISCIPLINE
------------------
- Same input → same output for the deterministic core; LLM-enhanced
  sentiment analysis is opt-in and labeled
- Empty feedback returns "engagement_score=0" with explicit
  fallback_reason rather than fabricating engagement values
- Alignment score is keyword overlap (transparent), not embedded ML
- Individual cascade respects band-weighted distribution: senior
  bands receive a larger share of strategic KRs than junior bands

RELATED STANDARDS
-----------------
- ENH-143 Strategic Pillars — provides input pillar_okrs
- ENH-144 Initiative Portfolio — initiatives feed KR specifics
- ENH-153 Strategy-to-BSC Daily Integration — consumes individual OKRs
- BSC engine (utils.bsc_engine) — individual OKR scoring submitted via
  contract-compliant submit() calls (out of scope for cascade engine)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set


logger = logging.getLogger("a2z.enhanced_cascade")


# ════════════════════════════════════════════════════════════════════
# Band-weighted distribution defaults
# ════════════════════════════════════════════════════════════════════

# Senior bands receive larger share of strategic KRs.
# Bands per Eco Bank Kenya HR taxonomy (E1=Executive, M=Manager,
# S=Supervisor, O=Officer, A=Assistant)
BAND_KR_WEIGHT = {
    "E1": 1.00,   # Executive — full ownership
    "E2": 0.90,
    "M1": 0.75,
    "M2": 0.65,
    "S1": 0.50,
    "S2": 0.40,
    "O1": 0.30,
    "O2": 0.25,
    "A1": 0.15,
}
DEFAULT_BAND_WEIGHT = 0.20  # for unrecognized bands

# Engagement thresholds (per Continuation.docx ENH-148/149 conventions)
ENGAGEMENT_HIGH = 75
ENGAGEMENT_MEDIUM = 50


# ════════════════════════════════════════════════════════════════════
# EnhancedCascadeEngine
# ════════════════════════════════════════════════════════════════════

class EnhancedCascadeEngine:
    """OKR/BSC cascade with full visibility and engagement.

    Caller pattern:

        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.enhanced_cascade import EnhancedCascadeEngine

        pillars = StrategyDecompositionEngine().define_strategic_pillars(
            "digital transformation")

        # Convert pillars → pillar OKRs
        pillar_okrs = [
            {
                "pillar_name":  p["name"],
                "objective":    p["name"],
                "key_results":  list(p["success_metrics"]),
            }
            for p in pillars
        ]

        cascade = EnhancedCascadeEngine()
        result = cascade.cascade_with_engagement(
            pillar_okrs, department="IT/Digital")
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 llm_sentiment_fn: Optional[
                     Callable[[List[str]], Dict[str, Any]]] = None):
        """
        Args:
            data_dir: where to read users.json from. Defaults to repo's
                data/ directory.
            llm_sentiment_fn: optional callable(feedback_texts) →
                {sentiment_score, themes} for LLM-enhanced engagement.
                When None, engagement is computed from acknowledgment
                status only.
        """
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.llm_sentiment_fn = llm_sentiment_fn
        self._users_cache: Optional[Dict[str, Dict]] = None

    # ── Data loaders ──

    def _load_users(self) -> Dict[str, Dict[str, Any]]:
        """Load users.json (cached)."""
        if self._users_cache is not None:
            return self._users_cache
        path = self.data_dir / "users.json"
        if not path.exists():
            self._users_cache = {}
            return self._users_cache
        try:
            with open(path, encoding="utf-8") as f:
                self._users_cache = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"users.json unreadable: {e}")
            self._users_cache = {}
        return self._users_cache

    def _employees_in_department(self,
                                  department: str) -> List[Dict[str, Any]]:
        """Return list of user dicts where user['department'] == department."""
        users = self._load_users()
        if not isinstance(users, dict):
            return []
        result = []
        for username, urec in users.items():
            if not isinstance(urec, dict):
                continue
            if urec.get("department") != department:
                continue
            if not urec.get("active", True):
                continue
            entry = dict(urec)
            entry["username"] = username
            result.append(entry)
        return result

    # ── Department-aware filtering ──

    def _department_workstreams(
            self, department: str) -> Set[str]:
        """Reverse lookup: which workstreams does this department touch?

        Uses utils.strategy_decomposition.WORKSTREAM_TO_DEPARTMENTS.
        """
        try:
            from utils.strategy_decomposition import (
                WORKSTREAM_TO_DEPARTMENTS)
        except ImportError:
            logger.warning(
                "strategy_decomposition not importable; using empty map")
            return set()
        return {ws for ws, depts in WORKSTREAM_TO_DEPARTMENTS.items()
                if department in depts}

    # ── Department OKR generation ──

    def generate_department_okrs(
            self,
            pillar_okrs: List[Dict[str, Any]],
            department: str) -> List[Dict[str, Any]]:
        """Generate department OKRs from pillar OKRs.

        Logic:
        - For each pillar OKR, check if any of the pillar's workstreams
          touches this department (via WORKSTREAM_TO_DEPARTMENTS lookup)
        - If yes, the department inherits a contextualized version of
          the pillar OKR with workstream-specific KRs

        When no pillar OKRs map to the department's workstreams,
        returns an empty list with a logged note (not a crash).
        """
        dept_workstreams = self._department_workstreams(department)
        dept_okrs = []
        for pokr in pillar_okrs:
            pillar_name = pokr.get("pillar_name", pokr.get("objective", ""))
            # Pull the pillar template's workstreams (best-effort via
            # strategy_decomposition lookup)
            pillar_workstreams = pokr.get("workstreams", [])
            if not pillar_workstreams:
                # Look up by pillar name from canonical templates
                try:
                    from utils.strategy_decomposition import (
                        PILLAR_TEMPLATES)
                    tpl = next((t for t in PILLAR_TEMPLATES
                                if t["name"] == pillar_name), None)
                    if tpl:
                        pillar_workstreams = list(tpl["workstreams"])
                except ImportError:
                    pillar_workstreams = []

            # Intersection
            relevant = (set(pillar_workstreams) & dept_workstreams
                        if dept_workstreams else set())
            if not relevant:
                continue

            dept_okrs.append({
                "pillar_name":     pillar_name,
                "department":      department,
                "objective":       (
                    f"Deliver {department}'s contribution to "
                    f"{pillar_name}"),
                "key_results":     list(pokr.get("key_results", [])),
                "relevant_workstreams": sorted(relevant),
                "status":          "draft",
                "feedback":        None,
            })
        return dept_okrs

    # ── Two-way feedback collection ──

    def collect_department_feedback(
            self,
            department_okrs: List[Dict[str, Any]],
            feedback: Optional[List[Dict[str, Any]]] = None
            ) -> Dict[str, Any]:
        """Collect/synthesize department feedback on draft OKRs.

        Args:
            department_okrs: from generate_department_okrs()
            feedback: optional list of feedback entries:
                [{"author", "okr_index", "comment", "agree"|"disagree"}]
                If None, returns empty-feedback stub.

        Returns:
            {feedback: [...], sentiment_score, themes, basis,
             fallback_reason | None}
        """
        if not feedback:
            return {
                "feedback":         [],
                "sentiment_score":  None,
                "themes":           [],
                "basis":            "rule_based",
                "fallback_reason":  "No feedback provided by caller; "
                                   "returning empty stub.",
            }

        # If LLM sentiment hook injected, use it
        if self.llm_sentiment_fn is not None:
            try:
                texts = [f.get("comment", "") for f in feedback]
                sentiment = self.llm_sentiment_fn(texts)
                return {
                    "feedback":        feedback,
                    "sentiment_score": sentiment.get("sentiment_score"),
                    "themes":          sentiment.get("themes", []),
                    "basis":           "llm",
                    "fallback_reason": None,
                }
            except Exception as e:
                logger.warning(
                    f"llm_sentiment_fn raised {type(e).__name__}: {e}; "
                    f"falling back to rule-based")

        # Rule-based: compute simple agree/disagree ratio
        total = len(feedback)
        agrees = sum(1 for f in feedback if f.get("agree"))
        sentiment_score = (agrees / total * 100) if total > 0 else None
        return {
            "feedback":        feedback,
            "sentiment_score": sentiment_score,
            "themes":          [],
            "basis":           "rule_based",
            "fallback_reason": (
                "No llm_sentiment_fn injected; using "
                "agree/disagree-ratio sentiment."),
        }

    # ── Alignment of dept OKRs with feedback ──

    def align_okrs(self,
                   department_okrs: List[Dict[str, Any]],
                   feedback_result: Dict[str, Any]
                   ) -> List[Dict[str, Any]]:
        """Apply feedback to draft department OKRs.

        Logic:
        - Each feedback entry references okr_index
        - 'disagree' feedback flips status to 'review_required'
        - All dept OKRs without feedback advance to 'aligned'
        - Captures the actual feedback list on each OKR for traceability
        """
        feedback_list = feedback_result.get("feedback", [])
        feedback_by_idx: Dict[int, List[Dict]] = {}
        for f in feedback_list:
            idx = f.get("okr_index")
            if idx is None:
                continue
            feedback_by_idx.setdefault(idx, []).append(f)

        aligned = []
        for idx, okr in enumerate(department_okrs):
            new_okr = dict(okr)
            applicable = feedback_by_idx.get(idx, [])
            if applicable:
                disagrees = [f for f in applicable
                             if not f.get("agree", True)]
                new_okr["feedback"] = applicable
                new_okr["status"] = ("review_required" if disagrees
                                     else "aligned")
            else:
                new_okr["status"] = "aligned"
            aligned.append(new_okr)
        return aligned

    # ── Cascade to individuals ──

    def cascade_to_individuals(
            self,
            department_okrs: List[Dict[str, Any]],
            department: str) -> List[Dict[str, Any]]:
        """Cascade department OKRs to individual employees.

        Each employee receives a personalized OKR set with:
        - Their share of each department KR (band-weighted)
        - acknowledgment_status="pending" by default

        Returns one entry per employee per relevant OKR.
        """
        employees = self._employees_in_department(department)
        if not employees:
            return []

        individual_okrs = []
        for emp in employees:
            band = emp.get("band", "")
            weight = BAND_KR_WEIGHT.get(band, DEFAULT_BAND_WEIGHT)
            staff_code = emp.get("staff_code", "")
            full_name = emp.get("full_name", emp.get("username", ""))
            role = emp.get("role", "")

            for dokr in department_okrs:
                # Skip OKRs that need review at the department level
                if dokr.get("status") == "review_required":
                    continue
                individual_okrs.append({
                    "staff_code":            staff_code,
                    "username":              emp.get("username"),
                    "full_name":             full_name,
                    "role":                  role,
                    "band":                  band,
                    "department":            department,
                    "pillar_name":           dokr.get("pillar_name"),
                    "objective":
                        f"Deliver my {role or 'contribution'} to "
                        f"{dokr.get('pillar_name')}",
                    "key_results":           list(
                        dokr.get("key_results", [])),
                    "kr_weight":             weight,
                    "acknowledgment_status": "pending",
                    "linked_workstreams":    dokr.get(
                        "relevant_workstreams", []),
                })
        return individual_okrs

    # ── Visibility dashboard placeholder ──

    def create_visibility_dashboard(
            self,
            pillar_okrs: List[Dict[str, Any]],
            department_okrs: List[Dict[str, Any]],
            individual_okrs: List[Dict[str, Any]]
            ) -> Dict[str, Any]:
        """Produce a structured dashboard payload (caller renders to
        Streamlit/UI). Returns a flat structure with three layers."""
        return {
            "layers": [
                {"layer": "pillar",     "okrs": pillar_okrs},
                {"layer": "department", "okrs": department_okrs},
                {"layer": "individual", "okrs": individual_okrs},
            ],
            "n_pillar":     len(pillar_okrs),
            "n_department": len(department_okrs),
            "n_individual": len(individual_okrs),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── Alignment scoring ──

    def calculate_alignment_score(
            self,
            individual_okrs: List[Dict[str, Any]],
            strategic_pillars: List[Dict[str, Any]]
            ) -> Dict[str, Any]:
        """Return alignment score (0-100) for individual OKRs vs pillars.

        Per Continuation.docx ENH-145: every employee should see how
        their work connects to strategic pillars. Score = % of
        individual OKRs whose linked pillar matches a strategic pillar
        name AND whose key_results overlap (keyword) with the pillar's
        success_metrics.
        """
        if not individual_okrs:
            return {
                "alignment_score": 0.0,
                "n_individuals":   0,
                "n_aligned":       0,
                "basis":           "rule_based",
                "fallback_reason":
                    "No individual OKRs to score.",
            }

        pillar_names = {p.get("name") for p in strategic_pillars}
        # Keyword extractor: lowercase tokens from each pillar's success_metrics
        pillar_keywords: Dict[str, Set[str]] = {}
        for p in strategic_pillars:
            kws = set()
            for sm in p.get("success_metrics", []):
                for tok in sm.lower().split():
                    if len(tok) >= 3 and tok.isalnum():
                        kws.add(tok)
            pillar_keywords[p.get("name", "")] = kws

        aligned_count = 0
        for iokr in individual_okrs:
            pname = iokr.get("pillar_name")
            if pname not in pillar_names:
                continue
            iokr_kws = set()
            for kr in iokr.get("key_results", []):
                for tok in kr.lower().split():
                    if len(tok) >= 3 and tok.isalnum():
                        iokr_kws.add(tok)
            pillar_kws = pillar_keywords.get(pname, set())
            if iokr_kws & pillar_kws:
                aligned_count += 1

        score = (aligned_count / len(individual_okrs)) * 100
        return {
            "alignment_score": round(score, 2),
            "n_individuals":   len(individual_okrs),
            "n_aligned":       aligned_count,
            "basis":           "rule_based",
            "fallback_reason": None,
        }

    # ── Engagement scoring ──

    def calculate_engagement(
            self,
            individual_okrs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return engagement score (0-100) based on acknowledgment
        status: % of individual OKRs that have been acknowledged or
        accepted by the employee.

        Note: in default state, every cascaded OKR has status='pending'
        — engagement_score=0 reflects the truth that nobody has
        acknowledged yet. Bank's HR system updates these statuses; the
        score reflects the most recent state.
        """
        if not individual_okrs:
            return {
                "engagement_score": 0.0,
                "n_total":          0,
                "n_acknowledged":   0,
                "level":            "n/a",
                "basis":            "rule_based",
                "fallback_reason":  "No individual OKRs to score.",
            }
        n = len(individual_okrs)
        acknowledged = sum(
            1 for o in individual_okrs
            if o.get("acknowledgment_status") in ("acknowledged",
                                                  "accepted"))
        score = (acknowledged / n) * 100
        if score >= ENGAGEMENT_HIGH:
            level = "high"
        elif score >= ENGAGEMENT_MEDIUM:
            level = "medium"
        else:
            level = "low"
        return {
            "engagement_score": round(score, 2),
            "n_total":          n,
            "n_acknowledged":   acknowledged,
            "level":            level,
            "basis":            "rule_based",
            "fallback_reason":  None,
        }

    # ── Main API ──

    def cascade_with_engagement(
            self,
            pillar_okrs: List[Dict[str, Any]],
            department: str,
            feedback: Optional[List[Dict[str, Any]]] = None,
            strategic_pillars: Optional[List[Dict[str, Any]]] = None
            ) -> Dict[str, Any]:
        """Full cascade pipeline.

        Args:
            pillar_okrs: list of pillar-level OKRs
            department: department to cascade to
            feedback: optional list of feedback entries
            strategic_pillars: list of pillar dicts for alignment scoring;
                if None, falls back to using pillar_okrs

        Returns:
            {
              "pillar_okrs":        [...],
              "department_okrs":    [...],
              "individual_okrs":    [...],
              "alignment":          {...},
              "engagement":         {...},
              "visibility":         {...},
              "feedback_summary":   {...},
              "generated_at":       ISO-8601,
              "department":         str,
              "n_employees":        int,
            }
        """
        dept_okrs_draft = self.generate_department_okrs(
            pillar_okrs, department)
        feedback_result = self.collect_department_feedback(
            dept_okrs_draft, feedback)
        dept_okrs = self.align_okrs(dept_okrs_draft, feedback_result)
        individual_okrs = self.cascade_to_individuals(
            dept_okrs, department)

        # Alignment scoring needs pillar dicts (with success_metrics);
        # pillar_okrs may not have them, so fall back to pillar_okrs
        pillars_for_align = strategic_pillars or [
            {"name": p.get("pillar_name"),
             "success_metrics": p.get("key_results", [])}
            for p in pillar_okrs
        ]
        alignment = self.calculate_alignment_score(
            individual_okrs, pillars_for_align)
        engagement = self.calculate_engagement(individual_okrs)
        visibility = self.create_visibility_dashboard(
            pillar_okrs, dept_okrs, individual_okrs)

        return {
            "pillar_okrs":      pillar_okrs,
            "department_okrs":  dept_okrs,
            "individual_okrs":  individual_okrs,
            "alignment":        alignment,
            "engagement":       engagement,
            "visibility":       visibility,
            "feedback_summary": feedback_result,
            "generated_at":     datetime.now(timezone.utc).isoformat(),
            "department":       department,
            "n_employees":      len(self._employees_in_department(
                department)),
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def cascade_with_engagement(
        pillar_okrs: List[Dict[str, Any]],
        department: str,
        feedback: Optional[List[Dict]] = None,
        strategic_pillars: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """Convenience wrapper — instantiate and run cascade."""
    return EnhancedCascadeEngine().cascade_with_engagement(
        pillar_okrs, department, feedback, strategic_pillars)
