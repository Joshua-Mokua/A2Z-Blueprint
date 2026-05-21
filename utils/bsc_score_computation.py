"""utils/bsc_score_computation.py — Canonical BSC score
computation for a staff member (v10.319).

Joshua reminded us on the v10.318 demo of the original BSC design:

  - Each role has its OWN set of KPIs (defined in role_kpis)
  - KPI weights sum to 100% across a role's set
  - Per-KPI score is on the 1-5 scale (based on achievement %)
  - Final BSC score = weighted average of KPI scores (1-5 scale)
  - Some KPIs are FIXED (bank-level — same target for everyone)
  - Other KPIs are CASCADED (target allocated per staff member)

This module computes a staff's BSC score honouring all of that:

  1. Read role_kpis to find the staff's KPI set
  2. For each KPI, fetch:
       - actual: from bsc_actuals (period-keyed)
       - target: from bank_targets[KPI|YEAR] if fixed,
                 else target_cascade[staff|KPI|YEAR] if cascaded
       - direction: from kpi_library (higher/lower better)
       - weight: from kpi_library
  3. Compute achievement_pct → score (1-5) via canonical formula
  4. Weighted average → final BSC score
  5. Validate weights sum to 100% across the role's set

Per Rule 7, this is a COMPUTATION module — not a producer (it
reads and computes, no submissions). The producer (v10.317) is
unchanged; this batch adds the computation layer that consumes
what the producer wrote.

Shipped: v10.319.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Canonical sources (cached — clear via clear_caches())
# ════════════════════════════════════════════════════════════════════

_CACHE: Dict[str, Any] = {}


def clear_caches() -> None:
    """Clear cached file loads. Call when configs are edited."""
    _CACHE.clear()


def _kpi_library() -> Dict[str, Any]:
    if "kpi_library" not in _CACHE:
        from utils.db import db
        _CACHE["kpi_library"] = (
            db.load_json(DATA_DIR / "kpi_library.json",
                          default={}) or {}
        )
    return _CACHE["kpi_library"]


def _bank_targets() -> Dict[str, Any]:
    if "bank_targets" not in _CACHE:
        from utils.db import db
        _CACHE["bank_targets"] = (
            db.load_json(DATA_DIR / "bank_targets.json",
                          default={}) or {}
        )
    return _CACHE["bank_targets"]


def _target_cascade() -> Dict[str, Any]:
    if "target_cascade" not in _CACHE:
        from utils.db import db
        _CACHE["target_cascade"] = (
            db.load_json(DATA_DIR / "target_cascade.json",
                          default={}) or {}
        )
    return _CACHE["target_cascade"]


def _fixed_kpis_config() -> Dict[str, Any]:
    """data/fixed_kpis.json — admin-marks which KPIs are bank-fixed
    per period. Format: {period: [kpi_id, kpi_id, ...]} or
    {period: {"kpis": [...], "values": {...}}}."""
    if "fixed_kpis" not in _CACHE:
        from utils.db import db
        _CACHE["fixed_kpis"] = (
            db.load_json(DATA_DIR / "fixed_kpis.json",
                          default={}) or {}
        )
    return _CACHE["fixed_kpis"]


# ════════════════════════════════════════════════════════════════════
# KPI categorisation: fixed vs cascaded
# ════════════════════════════════════════════════════════════════════

def is_fixed_kpi(kpi_id: str, period: str) -> bool:
    """A KPI is FIXED for a period if it appears in fixed_kpis.json.

    v10.323 update: removed the bank_targets fallback. Previously
    any KPI with a bank_targets entry was treated as fixed, which
    caused volume KPIs (Disbursements, Loan Growth) to score
    individuals against bank-aggregate targets — always producing
    1.0. Now: fixed_kpis.json is the authoritative list. KPIs not
    in it use cascaded individual targets (target_cascade.json)
    or role-default targets (role_default_targets.json).
    """
    fk = _fixed_kpis_config()
    entry = fk.get(period, {})
    if isinstance(entry, dict):
        # New shape: {"kpis": [...]}
        fixed_list = entry.get("kpis", [])
        # Old shape: {"KPI": value, ...} — keys are the fixed KPIs
        if not fixed_list and entry:
            fixed_list = [
                k for k in entry.keys()
                if not k.startswith("_")
            ]
    elif isinstance(entry, list):
        fixed_list = entry
    else:
        fixed_list = []
    return kpi_id in fixed_list


def _role_default_targets() -> Dict[str, Any]:
    """Read data/role_default_targets.json — per-role quarterly
    targets for sales/volume KPIs."""
    if "role_default_targets" not in _CACHE:
        from utils.db import db
        _CACHE["role_default_targets"] = (
            db.load_json(
                DATA_DIR / "role_default_targets.json",
                default={},
            ) or {}
        )
    return _CACHE["role_default_targets"]


def _staff_role_for_target(staff_code: str) -> Optional[str]:
    """Resolve a staff's role for role-default target lookup."""
    try:
        from utils.virtual_bank import staff_universe
        u = staff_universe()
        s = u.get(staff_code)
        return s.role if s else None
    except Exception:  # noqa: BLE001
        return None


def get_target_for_staff(
    staff_code: str,
    kpi_id: str,
    period: str,
) -> Optional[Tuple[float, str]]:
    """Get the target value for a staff member on a KPI for a period.

    Returns (target, source) tuple where source is one of:
      - 'bank_fixed' — bank-level target (KPI is fixed for period)
      - 'cascaded' — per-staff target from target_cascade
      - 'role_default' — per-role quarterly default (v10.323 fallback)
      - None — no target configured

    Order: fixed → cascaded → role_default → missing.
    """
    year = period.split("-")[0] if "-" in period else period

    # 1. Fixed (bank-wide target — same for everyone)
    if is_fixed_kpi(kpi_id, period):
        bt = _bank_targets()
        for key_format in (f"{kpi_id}|{year}",
                            f"{kpi_id}|{period}"):
            if key_format in bt:
                entry = bt[key_format]
                if isinstance(entry, dict) and "target" in entry:
                    return (float(entry["target"]), "bank_fixed")
                if isinstance(entry, (int, float)):
                    return (float(entry), "bank_fixed")
        # Fixed but no explicit bank target — fall through

    # 2. Cascaded (per-staff target)
    tc = _target_cascade()
    for key_format in (f"{staff_code}|{kpi_id}|{year}",
                        f"{staff_code}|{kpi_id}|{period}"):
        if key_format in tc:
            entry = tc[key_format]
            if isinstance(entry, dict):
                t = entry.get("target") or entry.get("value")
                if t is not None:
                    return (float(t), "cascaded")
            elif isinstance(entry, (int, float)):
                return (float(entry), "cascaded")

    # 3. Role default (v10.323 — per-role quarterly target)
    role = _staff_role_for_target(staff_code)
    if role:
        rd = _role_default_targets()
        role_targets = (
            rd.get("quarterly_targets_by_role", {})
            .get(role, {})
        )
        if kpi_id in role_targets:
            return (float(role_targets[kpi_id]),
                     "role_default")

    return None


# ════════════════════════════════════════════════════════════════════
# Canonical 1-5 scoring formula
# ════════════════════════════════════════════════════════════════════

def score_from_achievement_pct(
    achievement_pct: float,
    reverse: bool = False,
) -> float:
    """Canonical 1-5 scoring scale (mirrors utils.core.bsc_score_
    from_pct without the Streamlit dependency).

    reverse=True for KPIs where LOWER is better (NPL, PAR, dormancy).
    """
    if achievement_pct is None:
        return 0.0
    pct = (achievement_pct if not reverse
           else (200 - achievement_pct))
    if pct >= 120: return 5.0
    if pct >= 110: return 4.5
    if pct >= 100: return 4.0
    if pct >= 90:  return 3.5
    if pct >= 80:  return 3.0
    if pct >= 70:  return 2.5
    if pct >= 60:  return 2.0
    if pct >= 50:  return 1.5
    return 1.0


def compute_achievement_pct(
    actual: float,
    target: float,
    direction: str = "higher",
) -> float:
    """Compute achievement % respecting direction.

    direction='higher' or 'higher_better': actual / target × 100
    direction='lower'  or 'lower_better':  target / max(actual, ε) × 100
    """
    if target <= 0:
        return 0.0
    is_lower = direction.startswith("lower")
    if is_lower:
        if actual <= 0:
            return 200.0  # zero NPL = perfect
        return round(target / actual * 100, 1)
    return round(actual / target * 100, 1)


# ════════════════════════════════════════════════════════════════════
# Role KPI resolution + weight validation
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class KpiResolution:
    """Resolved KPI definition for use in computation.

    Resolves the role_kpis convention mismatch (B-010) by mapping
    UPPER_SNAKE_CASE refs to actual KPI IDs in the library.
    """
    role_kpi_ref: str        # what role_kpis says (e.g. "CX_SCORE")
    canonical_id: str        # what kpis[] uses (e.g. "CX Score")
    weight: float            # from kpi_library
    direction: str           # higher / lower
    pillar: str              # Financial / Customer Focus / etc
    defined: bool            # True if found in kpis[]


# Aliases for B-010 dangling refs — auto-built from kpi.code field
# at module load + supplemented with manual entries for KPIs whose
# code differs from their canonical id. The kpi_library has a 'code'
# field on most KPIs (e.g. id="CX Score", code="CX_SCORE"). v10.320
# uses this as the source of truth.

def _build_alias_map_from_library() -> Dict[str, str]:
    """Build alias map from kpi.code → kpi.id automatically.

    This is the proper B-010 fix — instead of hardcoding 18 manual
    aliases, derive them from the kpi_library itself. Every KPI
    with a `code` field that differs from its `id` becomes an alias.
    """
    lib = _kpi_library()
    aliases: Dict[str, str] = {}
    for k in lib.get("kpis", []):
        if not isinstance(k, dict):
            continue
        code = k.get("code")
        kid = k.get("id")
        if code and kid and code != kid:
            aliases[code] = kid

    # Manual extras for legacy abbreviations not in any KPI's code
    # field. These appear in role_kpis with shorter forms than the
    # canonical kpi.code values.
    aliases.setdefault("STAFF_PROD", "Staff Productivity")
    aliases.setdefault("DEP_GROWTH", "Retail & MSME Deposit Growth")
    aliases.setdefault("FEES_COMM", "Total NFI")
    aliases.setdefault("LOAN_DISB", "Disbursements Retail Loans")
    aliases.setdefault("TRANSACTIONS", "Digital Transactions (%)")
    aliases.setdefault("NEW_CUST", "Number of Business Borrowers")
    # v10.329 — Branch Manager scorecard alignment
    aliases.setdefault("COMPLIANCE", "COMPLIANCE_SCORE")
    # Refs without a clean equivalent yet (logged for backlog):
    # ACTIVE_ACCTS, CIR, COMPLIANCE*, CREDIT_*, DIGITAL_ACT,
    # DILIGENCE, INIT_*, LEGAL_*, NEW_ACCOUNTS, NIM, NPL_RATIO,
    # NPS, ROE, TRADE_FIN — these need KPI definitions added
    return aliases


KPI_ID_ALIASES: Dict[str, str] = _build_alias_map_from_library()


def resolve_role_kpis(role: str) -> List[KpiResolution]:
    """Resolve a role's KPI set with weights, directions, and
    canonical IDs (handling B-010 alias mappings)."""
    lib = _kpi_library()
    role_kpi_ids = lib.get("role_kpis", {}).get(role, []) or []
    if not role_kpi_ids:
        return []

    all_defs = {k.get("id"): k for k in lib.get("kpis", [])
                if isinstance(k, dict) and k.get("id")}

    out: List[KpiResolution] = []
    for ref in role_kpi_ids:
        canonical = KPI_ID_ALIASES.get(ref, ref)
        defn = all_defs.get(canonical)
        if not defn:
            # Try the ref directly (in case it IS already canonical)
            defn = all_defs.get(ref)
            canonical = ref if defn else canonical
        if defn:
            out.append(KpiResolution(
                role_kpi_ref=ref,
                canonical_id=defn.get("id", canonical),
                weight=float(defn.get("weight", 0.0)),
                direction=str(defn.get("direction", "higher")),
                pillar=str(defn.get("pillar", "")),
                defined=True,
            ))
        else:
            out.append(KpiResolution(
                role_kpi_ref=ref,
                canonical_id=canonical,
                weight=0.0,
                direction="higher",
                pillar="",
                defined=False,
            ))
    return out


def validate_role_weights(role: str) -> Dict[str, Any]:
    """Verify that the weights for a role's KPI set sum to 100%
    (or normalise if not). Returns a diagnostic dict.

    v10.320 update: also returns `normalized_weights` map and
    `normalization_factor` for callers that want to enforce the
    100% sum mathematically.
    """
    resolutions = resolve_role_kpis(role)
    if not resolutions:
        return {
            "role": role,
            "valid": False,
            "reason": "no KPIs in role_kpis",
            "total_weight": 0.0,
            "kpi_count": 0,
            "undefined_count": 0,
            "normalized_weights": {},
            "normalization_factor": 0.0,
        }

    defined = [r for r in resolutions if r.defined]
    undefined = [r for r in resolutions if not r.defined]
    total_weight = sum(r.weight for r in defined)

    # Joshua's rule: weights should sum to 1.0 (=100%)
    # Tolerance: ±0.05 (5 percentage points) for rounding
    is_valid = abs(total_weight - 1.0) < 0.05

    # Normalised weights (sum to exactly 1.0 — enforces the design)
    normalized_weights: Dict[str, float] = {}
    if total_weight > 0:
        for r in defined:
            normalized_weights[r.canonical_id] = round(
                r.weight / total_weight, 6)

    normalization_factor = (
        1.0 / total_weight if total_weight > 0 else 0.0
    )

    return {
        "role": role,
        "valid": is_valid,
        "total_weight": round(total_weight, 4),
        "deviation_from_100": round(
            (total_weight - 1.0) * 100, 2),
        "kpi_count": len(resolutions),
        "defined_count": len(defined),
        "undefined_count": len(undefined),
        "undefined_refs": [r.role_kpi_ref for r in undefined],
        "normalized_weights": normalized_weights,
        "normalization_factor": round(
            normalization_factor, 6),
    }


# ════════════════════════════════════════════════════════════════════
# Per-staff score computation
# ════════════════════════════════════════════════════════════════════

@dataclass
class KpiScore:
    kpi_id: str
    canonical_id: str
    actual: Optional[float]
    target: Optional[float]
    target_source: str            # bank_fixed / cascaded / missing
    achievement_pct: Optional[float]
    score: Optional[float]        # 1-5
    weight: float
    direction: str
    pillar: str


@dataclass
class StaffScorecard:
    staff_code: str
    role: str
    period: str
    final_score: Optional[float]
    kpi_scores: List[KpiScore] = field(default_factory=list)
    total_weight: float = 0.0
    weight_validation: Dict[str, Any] = field(default_factory=dict)


def _get_actual(
    staff_code: str,
    kpi_id: str,
    period: str,
) -> Optional[float]:
    """Read bsc_actuals for one staff/KPI/period."""
    try:
        from utils.bsc_engine import get_actual
        v = get_actual(staff_code, kpi_id, period)
        if v is None:
            return None
        return float(v)
    except Exception:  # noqa: BLE001
        return None


def compute_staff_scorecard(
    staff_code: str,
    role: str,
    period: str,
) -> StaffScorecard:
    """Compute one staff's BSC scorecard for a period.

    Returns a StaffScorecard with per-KPI breakdown and final
    weighted-average score.
    """
    resolutions = resolve_role_kpis(role)
    weight_val = validate_role_weights(role)

    kpi_scores: List[KpiScore] = []
    weighted_sum = 0.0
    total_used_weight = 0.0

    for res in resolutions:
        actual = _get_actual(staff_code, res.canonical_id, period)
        if actual is None and res.role_kpi_ref != res.canonical_id:
            # Try the un-aliased form
            actual = _get_actual(
                staff_code, res.role_kpi_ref, period)

        target_info = get_target_for_staff(
            staff_code, res.canonical_id, period)
        if target_info is None and res.role_kpi_ref != res.canonical_id:
            target_info = get_target_for_staff(
                staff_code, res.role_kpi_ref, period)

        if target_info:
            target_value, target_source = target_info
        else:
            target_value, target_source = (None, "missing")

        if actual is not None and target_value is not None:
            ach = compute_achievement_pct(
                actual, target_value, res.direction)
            reverse = res.direction.startswith("lower")
            score = score_from_achievement_pct(ach, reverse=reverse)
            weighted_sum += score * res.weight
            total_used_weight += res.weight
        else:
            ach = None
            score = None

        kpi_scores.append(KpiScore(
            kpi_id=res.role_kpi_ref,
            canonical_id=res.canonical_id,
            actual=actual,
            target=target_value,
            target_source=target_source,
            achievement_pct=ach,
            score=score,
            weight=res.weight,
            direction=res.direction,
            pillar=res.pillar,
        ))

    final_score: Optional[float] = None
    if total_used_weight > 0:
        final_score = round(
            weighted_sum / total_used_weight, 2)
        # Clamp to 1-5
        final_score = max(1.0, min(5.0, final_score))

    return StaffScorecard(
        staff_code=staff_code,
        role=role,
        period=period,
        final_score=final_score,
        kpi_scores=kpi_scores,
        total_weight=round(total_used_weight, 4),
        weight_validation=weight_val,
    )


SPEC_DEVIATION_NOTE = (
    "This module is a COMPUTATION layer (not a producer). It "
    "reads bsc_actuals + bank_targets + target_cascade + kpi_"
    "library + fixed_kpis, and computes a staff's BSC scorecard "
    "honouring the original design: 1-5 weighted scoring, fixed "
    "KPIs use bank-level target (everyone scored uniformly), "
    "cascaded KPIs use per-staff target, weights sum to 100% "
    "(validated). The B-010 KPI ID alias map resolves UPPER_"
    "SNAKE_CASE refs in role_kpis to canonical IDs in kpis[] for "
    "the most common dangling references."
)
