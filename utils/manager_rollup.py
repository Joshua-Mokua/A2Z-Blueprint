"""utils/manager_rollup.py — Manager BSC rollup engine (v10.321).

Joshua's v10.318 reminder put the design constraint cleanly:

  - **Fixed KPIs** (CX Score, bank-level KPIs): manager scores on
    their OWN actual against the bank target — same path as any
    staff
  - **Cascaded KPIs**: manager's actual = aggregate of team's
    actuals (sum for volume-type KPIs, mean for score-type KPIs);
    target = manager's own cascaded target

For the cascade demo, every level of the hierarchy needs a
computable BSC score. v10.317 generated Teller actuals; this
module computes manager scores by recursively rolling up team
performance to any node in the org tree.

Two complementary views:

  1. `compute_team_rollup(manager_code, period)` — aggregate of
     direct reports' KPI actuals. For volume KPIs (deposits,
     transactions): sum. For score KPIs (CX, Audit): mean. Pairs
     against the manager's own cascaded target where available,
     else against the team's summed targets.

  2. `compute_recursive_score(staff_code, period)` — single
     score (1-5) for any node in the tree. Leaf nodes use
     compute_staff_scorecard directly. Non-leaf nodes compute
     average of direct reports' recursive scores. Result is
     cacheable per period.

Per Rule 7, this is a COMPUTATION module. It reads actuals and
configs, produces derived views. No data mutation.

Shipped: v10.321. Closes B-013.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# KPI aggregation type heuristics
# ════════════════════════════════════════════════════════════════════

# KPIs where summing across team is the correct aggregation
# (volume / count / amount metrics). Currency tokens come from
# org config so this stays tenant-agnostic (G162 compliance).
def _money_unit_patterns() -> List[str]:
    """Patterns indicating a monetary KPI unit. Reads the configured
    currency code from org_config rather than hardcoding."""
    code = ""
    try:
        from utils.db import db
        cfg = db.load_json(DATA_DIR / "org_config.json",
                            default={}) or {}
        code = str(
            cfg.get("currency") or
            cfg.get("currency_code") or ""
        ).upper()
    except Exception:  # noqa: BLE001
        pass
    patterns: List[str] = []
    if code:
        patterns.extend([f"{code} M", f"{code} B", code])
    # Generic money/scale suffixes that appear regardless of currency
    patterns.extend([" m", " b", "millions", "billions"])
    return patterns


# Non-currency hints that always indicate sum aggregation
SUM_AGGREGATION_HINTS = (
    "count", "number", "transactions",
    "volume", "tickets",
)

# KPIs where averaging is correct (score / rating / percentage)
MEAN_AGGREGATION_HINTS = (
    "score", "%", "percent", "ratio", "rating",
)


def aggregation_for_kpi(kpi_def: Dict[str, Any]) -> str:
    """Return 'sum' or 'mean' for how to roll up a KPI across team.

    Heuristic based on unit. Volume/money metrics sum. Score/%
    metrics mean. Default to mean (safer for unknown units).
    """
    unit = str(kpi_def.get("unit", "")).lower()
    # Check currency-based money patterns first
    for pattern in _money_unit_patterns():
        if pattern.lower() in unit:
            return "sum"
    for hint in SUM_AGGREGATION_HINTS:
        if hint.lower() in unit:
            return "sum"
    for hint in MEAN_AGGREGATION_HINTS:
        if hint.lower() in unit:
            return "mean"
    return "mean"  # Conservative default


# ════════════════════════════════════════════════════════════════════
# Direct reports + recursive subordinates
# ════════════════════════════════════════════════════════════════════

def _direct_report_codes(manager_code: str) -> List[str]:
    """Return staff codes of direct reports.

    v10.406: Falls back to canonical reporting tree from
    `cascade_regenerator.build_reporting_tree` when virtual_bank's
    `direct_reports` returns empty. virtual_bank only knows
    explicit manager_code from hr.json; real C-suite chiefs (300002-
    300010 + 300178) have no hr.json record, so we rely on the same
    canonical resolver that `target_cascade.json` uses.
    """
    from utils.virtual_bank import direct_reports
    reports = direct_reports(manager_code)
    if reports:
        return [r.staff_code for r in reports]

    # v10.406 — canonical fallback
    try:
        from utils.cascade_regenerator import (
            build_reporting_tree, _strip_meta, DEFAULT_BRANCH_TIER_THRESHOLD,
        )
        import json as _json
        users_path = DATA_DIR / "users.json"
        ohc_path = DATA_DIR / "org_hierarchy_config.json"
        if users_path.exists() and ohc_path.exists():
            users = _json.loads(users_path.read_text(encoding="utf-8"))
            ohc = _json.loads(ohc_path.read_text(encoding="utf-8"))
            rmw = _strip_meta(ohc.get("role_manager_whitelist", {}))
            rmw = {k: v for k, v in rmw.items() if isinstance(v, list)}
            tiers = _strip_meta(ohc.get("role_tiers", {}))
            tiers = {k: int(v) for k, v in tiers.items()
                     if isinstance(v, (int, float))}
            threshold = int(ohc.get(
                "branch_tier_threshold", DEFAULT_BRANCH_TIER_THRESHOLD))
            _tree, _orphans, reports_of = build_reporting_tree(
                users, rmw, tiers, threshold
            )
            return reports_of.get(manager_code, [])
    except Exception:  # noqa: BLE001
        pass
    return []


def _staff_role(staff_code: str) -> Optional[str]:
    """Resolve a staff member's role."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    s = u.get(staff_code)
    return s.role if s else None


def _all_subordinate_codes(
    manager_code: str,
    max_depth: int = 10,
) -> List[str]:
    """Return staff codes of EVERY subordinate (direct + indirect)
    in the org tree below manager_code."""
    visited: set = set()
    queue: List[Tuple[str, int]] = [(manager_code, 0)]
    out: List[str] = []
    while queue:
        code, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        for sub in _direct_report_codes(code):
            if sub in visited:
                continue
            visited.add(sub)
            out.append(sub)
            queue.append((sub, depth + 1))
    return out


# ════════════════════════════════════════════════════════════════════
# Team-rollup view
# ════════════════════════════════════════════════════════════════════

@dataclass
class KpiAggregate:
    kpi_id: str                     # canonical id
    direction: str                  # higher / lower
    aggregation_method: str         # sum / mean
    team_actual: Optional[float]
    team_target: Optional[float]
    achievement_pct: Optional[float]
    aggregated_score: Optional[float]   # 1-5
    reports_with_actual: int
    target_source: str              # bank_fixed / cascaded_team_sum / cascaded_manager / missing


@dataclass
class TeamRollup:
    manager_code: str
    manager_role: Optional[str]
    period: str
    direct_reports_count: int
    indirect_reports_count: int     # total subordinates incl indirect
    scored_reports_count: int
    team_avg_score: Optional[float]
    team_kpi_aggregates: List[KpiAggregate] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def _get_actual(
    staff_code: str,
    kpi_id: str,
    period: str,
) -> Optional[float]:
    try:
        from utils.bsc_engine import get_actual
        v = get_actual(staff_code, kpi_id, period)
        if v is None:
            return None
        return float(v)
    except Exception:  # noqa: BLE001
        return None


def _kpi_def(kpi_id: str) -> Dict[str, Any]:
    from utils.bsc_score_computation import _kpi_library
    lib = _kpi_library()
    for k in lib.get("kpis", []):
        if isinstance(k, dict) and k.get("id") == kpi_id:
            return k
    return {}


def _direct_actuals_for_kpi(
    direct_report_codes: List[str],
    kpi_id: str,
    period: str,
) -> List[float]:
    """Collect actuals across direct reports for one KPI."""
    out: List[float] = []
    for code in direct_report_codes:
        v = _get_actual(code, kpi_id, period)
        if v is not None:
            out.append(v)
    return out


def compute_team_rollup(
    manager_code: str,
    period: str,
    kpi_ids: Optional[List[str]] = None,
) -> TeamRollup:
    """Aggregate the team's KPI actuals into a manager-level view.

    Walks direct reports + their subordinates (so a Branch Manager's
    team rollup includes Tellers via Operations Supervisor →
    Operations Manager). Each KPI is aggregated using its unit-
    based aggregation method (sum for volumes, mean for scores).

    If `kpi_ids` is None, auto-discovers from the actuals present
    in any subordinate's data (the demo case — we want to show
    whatever data exists for the team).
    """
    from utils.bsc_score_computation import (
        compute_achievement_pct, score_from_achievement_pct,
        get_target_for_staff,
    )

    direct = _direct_report_codes(manager_code)
    all_subs = _all_subordinate_codes(manager_code)
    manager_role = _staff_role(manager_code)

    if not all_subs:
        return TeamRollup(
            manager_code=manager_code,
            manager_role=manager_role,
            period=period,
            direct_reports_count=0,
            indirect_reports_count=0,
            scored_reports_count=0,
            team_avg_score=None,
            notes=["No subordinates — leaf node."],
        )

    # Discover KPIs from team actuals if not specified
    if kpi_ids is None:
        from utils.db import db
        kpi_ids = set()
        # Auto-discover by scanning actuals in the period file
        actuals_file = (
            DATA_DIR / f"bsc_actuals_{period}.json"
        )
        if actuals_file.exists():
            records = db.load_json(actuals_file, default=[]) or []
            sub_set = set(all_subs)
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                code = rec.get("staff_code")
                kid = rec.get("kpi_id") or rec.get("kpi")
                if code in sub_set and kid:
                    kpi_ids.add(kid)
        kpi_ids = sorted(kpi_ids)

    aggregates: List[KpiAggregate] = []
    weighted_score_sum = 0.0
    weighted_total = 0.0

    for kpi_id in kpi_ids:
        kdef = _kpi_def(kpi_id)
        direction = str(kdef.get("direction", "higher"))
        agg_method = aggregation_for_kpi(kdef)
        reports_with = 0
        team_target: Optional[float] = None
        team_actual: Optional[float] = None

        # Collect actuals from ALL subordinates (direct + indirect)
        sub_actuals = _direct_actuals_for_kpi(
            all_subs, kpi_id, period)
        reports_with = len(sub_actuals)

        if reports_with == 0:
            aggregates.append(KpiAggregate(
                kpi_id=kpi_id,
                direction=direction,
                aggregation_method=agg_method,
                team_actual=None,
                team_target=None,
                achievement_pct=None,
                aggregated_score=None,
                reports_with_actual=0,
                target_source="missing",
            ))
            continue

        # Aggregate actual
        if agg_method == "sum":
            team_actual = sum(sub_actuals)
        else:
            team_actual = sum(sub_actuals) / len(sub_actuals)

        # Target: prefer manager's own target if cascaded, else
        # aggregate team's targets (sum for volume, mean for score)
        target_info = get_target_for_staff(
            manager_code, kpi_id, period)
        target_source = "missing"
        if target_info:
            team_target = target_info[0]
            target_source = (
                "bank_fixed" if target_info[1] == "bank_fixed"
                else "cascaded_manager"
            )
        else:
            # Try team-summed/meaned target
            sub_targets: List[float] = []
            for sub in all_subs:
                t_info = get_target_for_staff(
                    sub, kpi_id, period)
                if t_info:
                    sub_targets.append(t_info[0])
            if sub_targets:
                if agg_method == "sum":
                    team_target = sum(sub_targets)
                else:
                    team_target = (
                        sum(sub_targets) / len(sub_targets))
                target_source = "cascaded_team_sum"

        # Compute score
        ach = None
        agg_score = None
        if team_actual is not None and team_target:
            ach = compute_achievement_pct(
                team_actual, team_target, direction)
            agg_score = score_from_achievement_pct(ach)
            weight = float(kdef.get("weight", 0.05))
            weighted_score_sum += agg_score * weight
            weighted_total += weight

        aggregates.append(KpiAggregate(
            kpi_id=kpi_id,
            direction=direction,
            aggregation_method=agg_method,
            team_actual=(
                round(team_actual, 2)
                if team_actual is not None else None),
            team_target=team_target,
            achievement_pct=ach,
            aggregated_score=agg_score,
            reports_with_actual=reports_with,
            target_source=target_source,
        ))

    team_score: Optional[float] = None
    if weighted_total > 0:
        team_score = round(
            weighted_score_sum / weighted_total, 2)
        team_score = max(1.0, min(5.0, team_score))

    return TeamRollup(
        manager_code=manager_code,
        manager_role=manager_role,
        period=period,
        direct_reports_count=len(direct),
        indirect_reports_count=len(all_subs),
        scored_reports_count=sum(
            1 for a in aggregates
            if a.aggregated_score is not None),
        team_avg_score=team_score,
        team_kpi_aggregates=aggregates,
    )


# ════════════════════════════════════════════════════════════════════
# Recursive per-node score (for cascade tree visualisation)
# ════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=2048)
def _cached_staff_score(
    staff_code: str,
    period: str,
) -> Optional[float]:
    """Cache layer — compute one staff's leaf score once per
    period."""
    from utils.bsc_score_computation import compute_staff_scorecard
    role = _staff_role(staff_code)
    if not role:
        return None
    card = compute_staff_scorecard(staff_code, role, period)
    return card.final_score


def compute_recursive_score(
    staff_code: str,
    period: str,
    _depth: int = 0,
) -> Optional[float]:
    """Compute effective BSC score for any node in the org tree.

    Leaf nodes: their own scorecard.
    Non-leaf nodes: weighted average of direct reports' recursive
    scores, blended with the manager's own scorecard (if available).

    For demo simplicity: at non-leaf nodes, the score is the mean
    of direct reports' recursive scores. The manager's own actuals
    (if generated in a future batch) can be blended in then.
    """
    if _depth > 10:
        return None  # safety guard

    direct = _direct_report_codes(staff_code)
    if not direct:
        # Leaf — own scorecard
        return _cached_staff_score(staff_code, period)

    # Non-leaf — recursive average of direct reports
    sub_scores: List[float] = []
    for sub in direct:
        s = compute_recursive_score(
            sub, period, _depth=_depth + 1)
        if s is not None:
            sub_scores.append(s)

    if not sub_scores:
        # No subordinate has a score — try own scorecard
        return _cached_staff_score(staff_code, period)

    return round(sum(sub_scores) / len(sub_scores), 2)


def cascade_score_tree(
    period: str,
    max_nodes: int = 100,
) -> Dict[str, Any]:
    """Walk down from the MD and compute recursive scores at every
    level for cascade-page display.

    Returns a tree structure:
      {"root": {"code", "role", "score", "children": [...]}}

    `max_nodes` limits depth/breadth for the demo (full 1,439-node
    tree is computable but presenting it in one shot isn't useful).

    Performance: if `data/cascade_scores_<PERIOD>.json` exists
    (pre-computed by scripts/precompute_cascade_scores.py), uses
    that — sub-second walk. Otherwise computes on demand (slow:
    minutes for the full org).
    """
    from utils.virtual_bank import staff_universe
    from utils.hierarchy_synth import cascade_from_root

    # Load pre-computed scores if available
    precomputed_scores: Dict[str, float] = {}
    try:
        from utils.db import db
        precomp_file = (
            DATA_DIR / f"cascade_scores_{period}.json"
        )
        if precomp_file.exists():
            data = db.load_json(precomp_file, default={}) or {}
            raw_scores = data.get("scores", {}) or {}
            for code, val in raw_scores.items():
                try:
                    precomputed_scores[code] = float(val)
                except (TypeError, ValueError):
                    pass
    except Exception:  # noqa: BLE001
        pass

    universe_view = cascade_from_root(
        staff_universe(include_synth_hierarchy=False),
    )
    if not universe_view or "root" not in universe_view:
        return {"error": "No cascade root found"}

    nodes_emitted = 0

    def _score_for(code: str) -> Optional[float]:
        if code in precomputed_scores:
            return precomputed_scores[code]
        return compute_recursive_score(code, period)

    def _build(node, depth: int) -> Optional[Dict[str, Any]]:
        nonlocal nodes_emitted
        if nodes_emitted >= max_nodes:
            return None
        staff = node.get("staff", {})
        code = staff.get("staff_code") or node.get("staff_code")
        if not code:
            return None
        score = _score_for(code)
        children = []
        for c in node.get("children", []):
            cb = _build(c, depth + 1)
            if cb:
                children.append(cb)
            if nodes_emitted >= max_nodes:
                break
        nodes_emitted += 1
        return {
            "staff_code": code,
            "role": staff.get("role"),
            "department": staff.get("department"),
            "score": score,
            "depth": depth,
            "children_count": len(children),
            "children": children,
        }

    root_node = {
        "staff": universe_view["root"],
        "children": universe_view.get("children", []),
    }
    tree = _build(root_node, 0)
    return {
        "period": period,
        "tree": tree,
        "nodes_emitted": nodes_emitted,
        "precomputed_used": bool(precomputed_scores),
        "precomputed_count": len(precomputed_scores),
    }


SPEC_DEVIATION_NOTE = (
    "This module is a COMPUTATION layer. It reads bsc_actuals + "
    "kpi_library + bank_targets + target_cascade + hierarchy "
    "synthesis, and produces derived views (team rollups + "
    "recursive node scores). No data mutation. Honours Joshua's "
    "design: fixed KPIs use bank target; cascaded KPIs aggregate "
    "team (sum for volumes by unit hint; mean for scores). "
    "Recursive score for non-leaf nodes = mean of direct "
    "reports' recursive scores (leaf nodes use their own "
    "scorecard). LRU-cached per (staff_code, period)."
)
