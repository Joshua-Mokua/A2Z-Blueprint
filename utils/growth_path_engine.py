"""utils.growth_path_engine — Personalized growth paths (Standard #12, v5.39).

Per the master spec:

    class GrowthPathEngine:
        def generate_development_plan(self, staff_code):
            return {
                "promotion_readiness": 0.75,
                "skill_gaps":          [{"skill": "Risk Management",
                                         "current": 2.5, "required": 4.0}],
                "recommended_actions": ["Complete e-learning",
                                         "Shadow senior RM"]
            }

Verification:
  - 100% of active staff have plans   ← verifiable in code (G23)
  - Promotion clarity 12% → 95%        ← deployed-users metric, OUT OF SCOPE

This module produces plans; persistence + display happen elsewhere.
The engine is INVOKED EXPLICITLY by `scripts/generate_growth_plans.py`
(nightly job) which writes `data/growth_plans.json`. Pages read that
materialized result rather than recomputing on every render.

Entry points
------------
    GrowthPathEngine().generate_development_plan(staff_code) -> dict
        Returns the full plan dict. Empty dict when staff_code is
        unknown (defensive — never raises for missing staff).

    save_plans(plans: dict[staff_code, plan]) -> int
        Persists the materialized plans table to data/growth_plans.json.

    get_plan(staff_code: str) -> Optional[dict]
        Returns the materialized plan for one staff member, or None.

    list_staff_with_plans() -> list[str]
        Returns every staff_code that has a plan.

How promotion_readiness is computed
-----------------------------------
Composite score in [0, 1] derived from three deterministic inputs:

    bsc_score_factor   ← average BSC score over last 3 periods, normalised
                          to [0, 1] where 1.0 is "score 5.0 across the board"
    tenure_factor      ← min(tenure_months / 24, 1.0). Two years in role
                          is the convention for full eligibility.
    skill_factor       ← sum(min(current, required)) / sum(required) per
                          assessed skill row. 1.0 means all skill gaps
                          fully closed.

    promotion_readiness = round(0.5 * bsc + 0.3 * tenure + 0.2 * skill, 2)

Weights:
  - BSC dominates (50%) because performance is the main signal
  - Tenure 30% — promotability requires demonstrated time in role
  - Skill 20% — complementary; many bands certify at promotion time

The output is bounded to [0, 1] and rounded to 2 decimal places. The
weights are configurable per-bank by injecting weights to the engine
constructor.

How skill_gaps is computed
--------------------------
For each skill the role requires, compare the staff's current level
to the required level. Gap = required - current (positive only). Only
gaps > 0 produce skill_gap entries. The engine returns at most
DEFAULT_MAX_GAPS entries (top by gap size) — surfacing every minor
gap is noise, the top few are actionable.

How recommended_actions is computed
-----------------------------------
Each skill gap maps to one or more training catalog entries via the
skill name. Recommendations list deduplicated, capped at
DEFAULT_MAX_ACTIONS items.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.growth_path")

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
PLANS_FILE = DATA_DIR / "growth_plans.json"

# ── Spec-aligned defaults ──────────────────────────────────────────────
DEFAULT_BSC_WEIGHT      = 0.50
DEFAULT_TENURE_WEIGHT   = 0.30
DEFAULT_SKILL_WEIGHT    = 0.20
DEFAULT_TENURE_CAP_MONTHS = 24    # 2 years for full tenure credit
DEFAULT_MAX_GAPS        = 5       # top 5 gaps by size
DEFAULT_MAX_ACTIONS     = 6


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class GrowthPathEngine:
    """Standard #12 — Personalized Growth Paths.

    Pure-function evaluator. Construct once, call
    generate_development_plan(staff_code) for each staff.

    All collaborators are injectable for testing.
    """

    def __init__(
        self,
        staff_lookup_fn:    Optional[Callable[[str], Optional[dict]]] = None,
        bsc_history_fn:     Optional[Callable[[str, int], List[float]]] = None,
        skill_assessment_fn: Optional[Callable[[str], Dict[str, float]]] = None,
        role_requirements_fn: Optional[Callable[[str], Dict[str, float]]] = None,
        training_catalog_fn: Optional[Callable[[str, float, float], List[str]]] = None,
        weights: Optional[Tuple[float, float, float]] = None,
    ):
        """All collaborators are functions to keep the engine testable.

        staff_lookup_fn(staff_code) -> dict | None
            Returns the staff record. Required keys (best-effort):
              role, band, hire_date, role_start_date (or hire_date as fallback)
            Default: reads data/users.json keyed by staff_code.

        bsc_history_fn(staff_code, n) -> list[float]
            Returns the last n overall BSC scores (most recent first).
            Default: reads data/bsc_scores.json (best-effort; returns
            empty if not found).

        skill_assessment_fn(staff_code) -> {skill_name: current_level}
            Default: reads data/staff_skills.json keyed by staff_code.

        role_requirements_fn(role) -> {skill_name: required_level}
            Default: reads data/role_skill_matrix.json keyed by role.

        training_catalog_fn(skill_name, current, required) -> list[str]
            Returns 1+ training/dev actions for closing this gap.
            Default: reads data/training_catalog.json keyed by skill.

        weights = (bsc, tenure, skill) — tuple of three floats summing
            to ~1.0. Default (0.5, 0.3, 0.2).
        """
        self._staff_lookup       = staff_lookup_fn       or _default_staff_lookup
        self._bsc_history        = bsc_history_fn        or _default_bsc_history
        self._skill_assessment   = skill_assessment_fn   or _default_skill_assessment
        self._role_requirements  = role_requirements_fn  or _default_role_requirements
        self._training_catalog   = training_catalog_fn   or _default_training_catalog
        if weights is not None:
            assert abs(sum(weights) - 1.0) < 0.01, \
                f"weights must sum to ~1.0; got {weights}"
            self._w_bsc, self._w_tenure, self._w_skill = weights
        else:
            self._w_bsc    = DEFAULT_BSC_WEIGHT
            self._w_tenure = DEFAULT_TENURE_WEIGHT
            self._w_skill  = DEFAULT_SKILL_WEIGHT

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def generate_development_plan(
        self, staff_code: str, today: Optional[date] = None
    ) -> Dict[str, Any]:
        """Return the spec-shaped development plan.

        Returns a dict with keys:
          - promotion_readiness : float in [0, 1]
          - skill_gaps          : list of {skill, current, required, gap}
          - recommended_actions : list[str]
          - meta                : {staff_code, role, band, generated_at,
                                    bsc_score_avg, tenure_months,
                                    skill_factor, weights}

        Returns {} if staff_code is unknown — the caller should treat
        empty dict as "no plan available." This is the engine's
        contract for missing/inactive staff: never raise, never fabricate.
        """
        if today is None:
            today = date.today()

        staff = self._staff_lookup(staff_code) or {}
        if not staff:
            return {}
        role = staff.get("role") or ""

        # ── BSC factor ────────────────────────────────────────────────
        bsc_history = self._bsc_history(staff_code, 3)
        bsc_avg = (
            sum(bsc_history) / len(bsc_history)
            if bsc_history else 0.0
        )
        # BSC is on the 1.0–5.0 scale per the bank's convention.
        # Map to [0, 1] linearly: score 5.0 → 1.0, score 1.0 → 0.0.
        bsc_factor = max(0.0, min(1.0, (bsc_avg - 1.0) / 4.0)) if bsc_avg else 0.0

        # ── Tenure factor ────────────────────────────────────────────
        tenure_months = _compute_tenure_months(staff, today)
        tenure_factor = min(tenure_months / DEFAULT_TENURE_CAP_MONTHS, 1.0)

        # ── Skill factor + skill gaps ────────────────────────────────
        current_skills  = self._skill_assessment(staff_code) or {}
        required_skills = self._role_requirements(role) or {}
        skill_factor, skill_gaps = _compute_skill_factor_and_gaps(
            current_skills, required_skills
        )

        # ── Composite promotion_readiness ─────────────────────────────
        promotion_readiness = (
            self._w_bsc    * bsc_factor +
            self._w_tenure * tenure_factor +
            self._w_skill  * skill_factor
        )
        promotion_readiness = round(max(0.0, min(1.0, promotion_readiness)), 2)

        # ── Recommended actions from training catalog ─────────────────
        recommended_actions: List[str] = []
        for gap in skill_gaps[:DEFAULT_MAX_GAPS]:
            for action in self._training_catalog(
                gap["skill"], gap["current"], gap["required"]
            ) or []:
                if action not in recommended_actions:
                    recommended_actions.append(action)
                if len(recommended_actions) >= DEFAULT_MAX_ACTIONS:
                    break
            if len(recommended_actions) >= DEFAULT_MAX_ACTIONS:
                break

        # If no skill gaps, surface a minimum coaching action so the
        # plan isn't empty for the rare staff with all skills met.
        if not recommended_actions and not skill_gaps:
            recommended_actions = [
                "Discuss next-step opportunities with your line manager",
                "Identify a stretch assignment for the next 90 days",
            ]

        return {
            "promotion_readiness": promotion_readiness,
            "skill_gaps":          skill_gaps[:DEFAULT_MAX_GAPS],
            "recommended_actions": recommended_actions,
            "meta": {
                "staff_code":     staff_code,
                "role":           role,
                "band":           staff.get("band", ""),
                "generated_at":   datetime.now(timezone.utc).isoformat(),
                "bsc_score_avg":  round(bsc_avg, 2),
                "tenure_months":  tenure_months,
                "skill_factor":   round(skill_factor, 2),
                "weights":        {
                    "bsc":    self._w_bsc,
                    "tenure": self._w_tenure,
                    "skill":  self._w_skill,
                },
            },
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _compute_tenure_months(staff: dict, today: date) -> int:
    """Tenure in months. Prefers role_start_date over hire_date.

    Returns 0 if no usable date is present (defensive — don't credit
    tenure we can't verify). Returns 0 for future dates (data error)."""
    for key in ("role_start_date", "hire_date", "start_date", "date_of_joining"):
        raw = staff.get(key)
        if not raw:
            continue
        try:
            d = _parse_date(str(raw))
            if d and d <= today:
                months = (today.year - d.year) * 12 + (today.month - d.month)
                if today.day < d.day:
                    months -= 1
                return max(0, months)
        except Exception:
            continue
    return 0


def _parse_date(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s.strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def _compute_skill_factor_and_gaps(
    current_skills: Dict[str, float],
    required_skills: Dict[str, float],
) -> Tuple[float, List[dict]]:
    """Returns (skill_factor in [0,1], gaps list sorted by gap descending).

    skill_factor = sum(min(current, required)) / sum(required)
        where current defaults to 0 if not assessed.
    Skill gaps include only skills where current < required.

    Returns (1.0, []) if there are no requirements (engine reports
    "no role-specific gaps" rather than crashing on KeyError)."""
    if not required_skills:
        return 1.0, []

    total_required = sum(float(v) for v in required_skills.values() if v)
    if total_required <= 0:
        return 1.0, []

    total_satisfied = 0.0
    gaps: List[dict] = []
    for skill, required in required_skills.items():
        try:
            req = float(required)
        except (TypeError, ValueError):
            continue
        if req <= 0:
            continue
        cur = float(current_skills.get(skill, 0))
        total_satisfied += min(cur, req)
        if cur < req:
            gaps.append({
                "skill":    skill,
                "current":  round(cur, 2),
                "required": round(req, 2),
                "gap":      round(req - cur, 2),
            })

    factor = total_satisfied / total_required
    factor = max(0.0, min(1.0, factor))
    gaps.sort(key=lambda g: g["gap"], reverse=True)
    return factor, gaps


# ─────────────────────────────────────────────────────────────────────
# Default collaborators (read from data/*.json; tolerant to missing files)
# ─────────────────────────────────────────────────────────────────────

def _safe_load_dict(path: Path) -> dict:
    try:
        from utils.db import db
        d = db.load_json(path, default={})
        return d if isinstance(d, dict) else {}
    except Exception as e:
        logger.warning("growth_path: could not load %s: %s", path, e)
        return {}


def _default_staff_lookup(staff_code: str) -> Optional[dict]:
    users = _safe_load_dict(DATA_DIR / "users.json")
    # users.json is keyed by username; staff_code is a separate field.
    # Walk to find the matching staff_code.
    for username, info in users.items():
        if not isinstance(info, dict):
            continue
        if str(info.get("staff_code", "")) == str(staff_code):
            # Merge username into the lookup result for traceability
            return {**info, "username": username}
    return None


def _default_bsc_history(staff_code: str, n: int) -> List[float]:
    """Best-effort: reads data/bsc_scores.json and returns the last n
    overall scores for this staff member. Returns [] if the file is
    absent or the staff has no scores yet (typical for fresh
    deployments)."""
    scores_file = DATA_DIR / "bsc_scores.json"
    if not scores_file.exists():
        return []
    raw = _safe_load_dict(scores_file)
    # Accepted shapes:
    #   {staff_code: [{period: ..., overall: ...}]}
    #   {staff_code: {period: overall, ...}}
    entries = raw.get(staff_code, [])
    if isinstance(entries, dict):
        # period→score mapping
        sorted_pairs = sorted(entries.items(), key=lambda kv: kv[0], reverse=True)
        return [float(v) for _, v in sorted_pairs[:n] if v is not None]
    if isinstance(entries, list):
        # list of dicts; sort by period descending if available
        try:
            entries = sorted(
                [e for e in entries if isinstance(e, dict)],
                key=lambda e: e.get("period", ""),
                reverse=True,
            )
        except Exception:
            pass
        scores: List[float] = []
        for e in entries[:n]:
            v = e.get("overall") or e.get("score") or e.get("total")
            if v is not None:
                try:
                    scores.append(float(v))
                except (TypeError, ValueError):
                    pass
        return scores
    return []


def _default_skill_assessment(staff_code: str) -> Dict[str, float]:
    raw = _safe_load_dict(DATA_DIR / "staff_skills.json")
    entry = raw.get(staff_code, {})
    if not isinstance(entry, dict):
        return {}
    return {
        skill: float(level) for skill, level in entry.items()
        if isinstance(level, (int, float))
    }


def _default_role_requirements(role: str) -> Dict[str, float]:
    raw = _safe_load_dict(DATA_DIR / "role_skill_matrix.json")
    entry = raw.get(role)
    # Fall back to 'default' role when the specific role isn't in the
    # matrix. The default is a reasonable baseline (Customer Service +
    # Compliance + Operations) so the engine still produces something
    # meaningful for roles HR hasn't curated yet.
    if not isinstance(entry, dict) or not entry:
        entry = raw.get("default", {})
    if not isinstance(entry, dict):
        return {}
    return {
        skill: float(level) for skill, level in entry.items()
        if isinstance(level, (int, float))
    }


def _default_training_catalog(skill: str, current: float, required: float) -> List[str]:
    """Read suggested training actions per skill from data/training_catalog.json.

    Falls back to a generic action when the catalog has no entry for
    this skill — better to return a useful default than nothing."""
    raw = _safe_load_dict(DATA_DIR / "training_catalog.json")
    entry = raw.get(skill, [])
    if isinstance(entry, list):
        actions = [str(a) for a in entry if a]
        if actions:
            return actions
    if isinstance(entry, dict):
        # By-level mapping: {"basic": [...], "advanced": [...]}
        # Pick the level closest to (required - current)
        level = "basic" if (required - current) <= 1.0 else "advanced"
        actions = entry.get(level) or entry.get("basic") or []
        if isinstance(actions, list) and actions:
            return [str(a) for a in actions if a]
    # Generic fallback
    return [
        f"Identify training opportunities for {skill} (gap: "
        f"{round(current, 1)} → {round(required, 1)})"
    ]


# ─────────────────────────────────────────────────────────────────────
# Persistence (delegates to utils.db so PG migration works)
# ─────────────────────────────────────────────────────────────────────

def save_plans(plans: Dict[str, dict]) -> int:
    """Persist plans dict (staff_code → plan) to data/growth_plans.json."""
    if not isinstance(plans, dict):
        return 0
    try:
        from utils.db import db
        db.save_json(PLANS_FILE, plans)
    except Exception as e:
        logger.error("growth_path: could not save plans: %s", e)
        return 0
    return len(plans)


def get_plan(staff_code: str) -> Optional[dict]:
    """Return the materialized plan for one staff member, or None."""
    try:
        from utils.db import db
        plans = db.load_json(PLANS_FILE, default={})
    except Exception:
        return None
    if not isinstance(plans, dict):
        return None
    return plans.get(staff_code)


def list_staff_with_plans() -> List[str]:
    try:
        from utils.db import db
        plans = db.load_json(PLANS_FILE, default={})
    except Exception:
        return []
    if not isinstance(plans, dict):
        return []
    return list(plans.keys())


# ─────────────────────────────────────────────────────────────────────
# Self-test (run via `python -m utils.growth_path_engine`)
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.growth_path_engine self-test")

    # Mock data
    staff_table = {
        "S001": {
            "role": "Branch Manager", "band": "M3",
            "role_start_date": "2024-01-15",
        },
        "S002": {
            "role": "Credit Analyst", "band": "M5",
            "hire_date": "2025-08-01",   # only 8 months of tenure
        },
    }
    bsc_table = {"S001": [4.5, 4.3, 4.4], "S002": [3.0, 3.2, 3.1]}
    skill_table = {
        "S001": {"Risk Management": 3.5, "Customer Service": 4.0,
                 "Leadership": 3.5},
        "S002": {"Credit Analysis": 4.0, "Risk Management": 2.5},
    }
    role_req = {
        "Branch Manager":  {"Risk Management": 4.0, "Customer Service": 4.0,
                            "Leadership": 4.5, "Product Knowledge": 3.5},
        "Credit Analyst":  {"Credit Analysis": 4.5, "Risk Management": 4.0,
                            "Financial Modelling": 3.0},
    }
    training = {
        "Risk Management": ["Complete CISI Risk Management Level 1",
                            "Shadow a Senior Risk Officer"],
        "Leadership":      ["Enroll in Bank Leadership Programme"],
        "Customer Service": ["Complete e-learning: NPS Champions"],
        "Product Knowledge": ["Attend product training quarterly briefing"],
        "Credit Analysis":  ["CISI Credit Risk certification"],
        "Financial Modelling": ["Complete advanced Excel for finance course"],
    }

    eng = GrowthPathEngine(
        staff_lookup_fn=     lambda sc: staff_table.get(sc),
        bsc_history_fn=      lambda sc, n: bsc_table.get(sc, [])[:n],
        skill_assessment_fn= lambda sc: skill_table.get(sc, {}),
        role_requirements_fn=lambda r:  role_req.get(r, {}),
        training_catalog_fn= lambda s, c, r: training.get(s, []),
    )

    # Case 1: Strong performer, mid-tenure
    plan = eng.generate_development_plan("S001", today=date(2026, 4, 15))
    assert "promotion_readiness" in plan
    assert "skill_gaps" in plan
    assert "recommended_actions" in plan
    assert plan["meta"]["bsc_score_avg"] > 4.0
    # S001: bsc=4.4 → factor=0.85; tenure=27m capped to 24m → 1.0;
    # skills: 3.5+4.0+3.5+0=11 / 4.0+4.0+4.5+3.5=16 → 0.6875
    # readiness = 0.5*0.85 + 0.3*1.0 + 0.2*0.6875 ≈ 0.86
    assert 0.80 <= plan["promotion_readiness"] <= 0.95, \
        f"readiness: {plan['promotion_readiness']}"
    assert len(plan["skill_gaps"]) >= 1, "expected gaps for S001"
    assert any("Leadership" in g["skill"] for g in plan["skill_gaps"]), \
        "S001 should show Leadership gap"
    print(f"  ✅ S001 strong performer: readiness={plan['promotion_readiness']}, "
          f"{len(plan['skill_gaps'])} gaps, {len(plan['recommended_actions'])} actions")

    # Case 2: Weaker performer, low tenure
    plan2 = eng.generate_development_plan("S002", today=date(2026, 4, 15))
    # bsc=3.1 → factor=0.525; tenure=8m → 0.333; skills: 4.0+2.5+0=6.5/11.5=0.565
    # readiness = 0.5*0.525 + 0.3*0.333 + 0.2*0.565 ≈ 0.475
    assert 0.40 <= plan2["promotion_readiness"] <= 0.55, \
        f"S002 readiness: {plan2['promotion_readiness']}"
    print(f"  ✅ S002 weaker: readiness={plan2['promotion_readiness']}, "
          f"{len(plan2['skill_gaps'])} gaps")

    # Case 3: Unknown staff → empty dict
    plan3 = eng.generate_development_plan("UNKNOWN")
    assert plan3 == {}, f"unknown should return empty dict, got {plan3}"
    print(f"  ✅ unknown staff returned empty dict")

    # Case 4: Skill factor bounds
    factor, gaps = _compute_skill_factor_and_gaps(
        {"A": 5.0}, {"A": 5.0}
    )
    assert factor == 1.0 and gaps == [], "all-met skills"
    factor, gaps = _compute_skill_factor_and_gaps(
        {}, {"A": 5.0}
    )
    assert factor == 0.0 and len(gaps) == 1, f"all-missing: factor={factor} gaps={gaps}"
    factor, gaps = _compute_skill_factor_and_gaps({}, {})
    assert factor == 1.0 and gaps == [], "no requirements"
    print(f"  ✅ skill factor bounds")

    # Case 5: Tenure parsing
    assert _compute_tenure_months({"role_start_date": "2024-04-15"}, date(2026, 4, 15)) == 24
    assert _compute_tenure_months({"hire_date": "2025-08-01"}, date(2026, 4, 15)) == 8
    assert _compute_tenure_months({}, date(2026, 4, 15)) == 0
    assert _compute_tenure_months({"hire_date": "2030-01-01"}, date(2026, 4, 15)) == 0
    print(f"  ✅ tenure parsing")

    # Case 6: Plan structure (the spec contract)
    for k in ("promotion_readiness", "skill_gaps", "recommended_actions"):
        assert k in plan
    assert isinstance(plan["promotion_readiness"], float)
    assert 0.0 <= plan["promotion_readiness"] <= 1.0
    assert isinstance(plan["skill_gaps"], list)
    assert isinstance(plan["recommended_actions"], list)
    print(f"  ✅ plan structure matches spec contract")

    print("\n  ALL TESTS PASSED")
