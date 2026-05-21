"""Pillar Impact Engine — v10.407 (E2: Strategic pillar visualization).

Per Joshua's QA standards Enhancement #2:
  Problem: Employees don't see how their targets connect to bank strategy.
  Solution: Interactive visualization linking individual targets to
            strategic pillars.

Provides:
  1. `pillar_breakdown_for_staff(staff_code, period)` — for one staff
     member, returns per-pillar: KPI count, weight sum, target sum,
     achievement % (if actuals exist).
  2. `pillar_breakdown_for_manager(manager_code, period)` — aggregates
     pillar breakdown across direct team + subtree (recursive).
  3. `kpi_to_strategic_pillar_map()` — fast lookup id → pillar.
  4. `bank_pillar_weights()` — canonical weights from kpi_library.

Per Rule 7, this is a COMPUTATION module. Reads kpi_library + actuals;
produces derived views. No mutations.

Shipped: v10.407.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# v10.407 — module-level caches for target/actual lookups. Keyed by
# period so repeated calls in same period (UI render) are cheap.
_TARGET_CACHE: Dict[str, Dict[tuple, bool]] = {}
_ACTUAL_CACHE: Dict[str, Dict[tuple, bool]] = {}


def _build_target_set_for_period(period: str) -> Dict[tuple, bool]:
    """Pre-compute (staff_code, kpi_id) → has_target for the period."""
    out: Dict[tuple, bool] = {}
    tc_path = DATA_DIR / "target_cascade.json"
    if not tc_path.exists():
        return out
    try:
        tc = json.loads(tc_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return out
    for k, v in tc.items():
        if k.startswith("_") or "|" not in k:
            continue
        if not isinstance(v, dict):
            continue
        parts = k.split("|")
        if len(parts) < 3:
            continue
        if parts[2] != period:
            continue
        for a in v.get("allocations", []):
            try:
                if float(a.get("amount", 0)) != 0:
                    out[(str(a.get("to_code")), parts[1])] = True
            except (TypeError, ValueError):
                pass
    return out


def _build_actuals_set_for_period(period: str) -> Dict[tuple, bool]:
    """Pre-compute (staff_code, kpi_id) → has_actual for period + Q variants."""
    out: Dict[tuple, bool] = {}
    for variant in (period, f"{period}-Q1", f"{period}-Q2", f"{period}-Q3", f"{period}-Q4"):
        path = DATA_DIR / f"bsc_actuals_{variant}.json"
        if not path.exists():
            continue
        try:
            recs = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(recs, list):
                continue
            for rec in recs:
                if isinstance(rec, dict):
                    sc = str(rec.get("staff_code", ""))
                    kid = rec.get("kpi_id") or rec.get("kpi")
                    if sc and kid:
                        out[(sc, kid)] = True
        except (json.JSONDecodeError, OSError):
            continue
    return out


def _get_target_lookup(period: str) -> Dict[tuple, bool]:
    if period not in _TARGET_CACHE:
        _TARGET_CACHE[period] = _build_target_set_for_period(period)
    return _TARGET_CACHE[period]


def _get_actual_lookup(period: str) -> Dict[tuple, bool]:
    if period not in _ACTUAL_CACHE:
        _ACTUAL_CACHE[period] = _build_actuals_set_for_period(period)
    return _ACTUAL_CACHE[period]


def clear_cache() -> None:
    """Clear caches (call after data refresh)."""
    global _USERS_CACHE
    _TARGET_CACHE.clear()
    _ACTUAL_CACHE.clear()
    _USERS_CACHE = None


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class PillarSlice:
    """One pillar's slice of a staff/manager's KPIs."""
    pillar: str
    kpi_count: int
    weight_sum: float          # total KPI weights (should sum to 1.0 across pillars per role)
    weight_pct: float          # weight_sum * 100 for display
    bank_pillar_weight: float  # the canonical bank weight (0-1) for this pillar
    targets_set_count: int     # how many of these KPIs have targets cascaded
    has_actuals_count: int     # how many of these KPIs have actuals
    kpi_ids: List[str] = field(default_factory=list)


@dataclass
class PillarBreakdown:
    """Strategic-pillar breakdown for one staff member or manager."""
    staff_code: str
    role: Optional[str]
    period: str
    total_kpis: int
    pillars: List[PillarSlice] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# Lookups
# ════════════════════════════════════════════════════════════════════

def _load_kpi_library() -> Dict[str, Any]:
    path = DATA_DIR / "kpi_library.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def kpi_to_strategic_pillar_map() -> Dict[str, str]:
    """Build kpi_id → pillar lookup."""
    lib = _load_kpi_library()
    out: Dict[str, str] = {}
    for k in lib.get("kpis", []):
        if isinstance(k, dict) and k.get("id"):
            pillar = k.get("pillar")
            if pillar:
                out[k["id"]] = pillar
    return out


def kpi_weight_map() -> Dict[str, float]:
    """Build kpi_id → weight lookup (per-KPI weight as defined in library)."""
    lib = _load_kpi_library()
    out: Dict[str, float] = {}
    for k in lib.get("kpis", []):
        if isinstance(k, dict) and k.get("id"):
            try:
                out[k["id"]] = float(k.get("weight", 0))
            except (TypeError, ValueError):
                out[k["id"]] = 0.0
    return out


def bank_pillar_weights() -> Dict[str, float]:
    """Canonical bank pillar weights (sum to 1.0)."""
    lib = _load_kpi_library()
    raw = lib.get("pillar_weights", {})
    if not isinstance(raw, dict):
        return {}
    # Strip meta keys
    return {k: float(v) for k, v in raw.items()
            if not k.startswith("_") and isinstance(v, (int, float))}


def _role_kpi_ids(role: str) -> List[str]:
    """Get KPI ids for a role (from role_kpis mapping)."""
    lib = _load_kpi_library()
    role_map = lib.get("role_kpis", {})
    kpis = role_map.get(role, [])
    if isinstance(kpis, list):
        return [k for k in kpis if isinstance(k, str)]
    return []


_USERS_CACHE: Optional[Dict[str, Any]] = None


def _users() -> Dict[str, Any]:
    """Load users.json (cached)."""
    global _USERS_CACHE
    if _USERS_CACHE is not None:
        return _USERS_CACHE
    path = DATA_DIR / "users.json"
    if not path.exists():
        _USERS_CACHE = {}
        return _USERS_CACHE
    _USERS_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _USERS_CACHE


def _staff_role(staff_code: str) -> Optional[str]:
    """Lookup staff role by code."""
    for u in _users().values():
        if isinstance(u, dict) and str(u.get("staff_code", "")) == str(staff_code):
            return u.get("role")
    return None


def _has_target_for_staff(staff_code: str, kpi_id: str, period: str) -> bool:
    """Check if there's a cascaded target for this staff+KPI+period (cached)."""
    lookup = _get_target_lookup(period)
    return lookup.get((str(staff_code), kpi_id), False)


def _has_actual_for_staff(staff_code: str, kpi_id: str, period: str) -> bool:
    """Check if there's an actual recorded for this staff+KPI+period (cached)."""
    lookup = _get_actual_lookup(period)
    return lookup.get((str(staff_code), kpi_id), False)


# ════════════════════════════════════════════════════════════════════
# Main API
# ════════════════════════════════════════════════════════════════════

def pillar_breakdown_for_staff(
    staff_code: str,
    period: str,
) -> PillarBreakdown:
    """Build pillar breakdown for one staff member.

    Looks up their role's KPIs, groups by pillar, counts which have
    cascaded targets / actuals.
    """
    role = _staff_role(staff_code)
    if not role:
        return PillarBreakdown(
            staff_code=staff_code, role=None, period=period,
            total_kpis=0,
            notes=[f"Staff code {staff_code} not found in users"],
        )

    kpi_ids = _role_kpi_ids(role)
    if not kpi_ids:
        return PillarBreakdown(
            staff_code=staff_code, role=role, period=period,
            total_kpis=0,
            notes=[f"Role '{role}' has no KPIs in role_kpis mapping"],
        )

    pillar_map = kpi_to_strategic_pillar_map()
    weight_map = kpi_weight_map()
    bank_weights = bank_pillar_weights()

    # Group KPIs by pillar
    by_pillar: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "kpi_count": 0, "weight_sum": 0.0,
        "targets_set_count": 0, "has_actuals_count": 0,
        "kpi_ids": [],
    })
    for kid in kpi_ids:
        pillar = pillar_map.get(kid, "Unmapped")
        slot = by_pillar[pillar]
        slot["kpi_count"] += 1
        slot["weight_sum"] += weight_map.get(kid, 0.0)
        slot["kpi_ids"].append(kid)
        if _has_target_for_staff(staff_code, kid, period):
            slot["targets_set_count"] += 1
        if _has_actual_for_staff(staff_code, kid, period):
            slot["has_actuals_count"] += 1

    pillars_out: List[PillarSlice] = []
    for p_name, p_data in by_pillar.items():
        pillars_out.append(PillarSlice(
            pillar=p_name,
            kpi_count=p_data["kpi_count"],
            weight_sum=round(p_data["weight_sum"], 4),
            weight_pct=round(p_data["weight_sum"] * 100, 1),
            bank_pillar_weight=bank_weights.get(p_name, 0.0),
            targets_set_count=p_data["targets_set_count"],
            has_actuals_count=p_data["has_actuals_count"],
            kpi_ids=sorted(p_data["kpi_ids"]),
        ))

    # Sort by canonical bank pillar weight desc, then by KPI count
    pillars_out.sort(
        key=lambda p: (-p.bank_pillar_weight, -p.kpi_count, p.pillar)
    )

    return PillarBreakdown(
        staff_code=staff_code,
        role=role,
        period=period,
        total_kpis=len(kpi_ids),
        pillars=pillars_out,
    )


def pillar_breakdown_for_manager(
    manager_code: str,
    period: str,
    max_subs: int = 1500,
) -> Dict[str, Any]:
    """Aggregated pillar breakdown across a manager's full subtree.

    v10.407: optimized — builds per-sub breakdown using cached lookups
    + pre-resolved role→KPIs map. max_subs caps very-wide trees.

    Returns:
      {
        manager_code, role, period, total_subordinates,
        own_breakdown: PillarBreakdown for manager themselves,
        team_pillar_summary: {pillar: {kpi_count, staff_count, ...}},
      }
    """
    # Manager's own breakdown
    own = pillar_breakdown_for_staff(manager_code, period)

    # Subtree
    try:
        from utils.manager_rollup import _all_subordinate_codes
        subs = _all_subordinate_codes(manager_code)[:max_subs]
    except Exception:  # noqa: BLE001
        subs = []

    # Pre-resolve user → role map (avoids loading users.json 808 times)
    users = _users()
    sub_to_role: Dict[str, Optional[str]] = {}
    for u in users.values():
        if isinstance(u, dict):
            sc = str(u.get("staff_code", ""))
            if sc:
                sub_to_role[sc] = u.get("role")

    pillar_map = kpi_to_strategic_pillar_map()
    weight_map = kpi_weight_map()

    # Aggregate per pillar across subs
    team_summary: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "kpi_count": 0,
        "staff_count": 0,
        "targets_set_count": 0,
        "has_actuals_count": 0,
    })

    target_lookup = _get_target_lookup(period)
    actual_lookup = _get_actual_lookup(period)

    for sub in subs:
        role = sub_to_role.get(str(sub))
        if not role:
            continue
        kpi_ids = _role_kpi_ids(role)
        # Track pillars this staff touches (1 staff_count per pillar per staff)
        pillars_seen: set = set()
        for kid in kpi_ids:
            pillar = pillar_map.get(kid, "Unmapped")
            slot = team_summary[pillar]
            slot["kpi_count"] += 1
            if (str(sub), kid) in target_lookup:
                slot["targets_set_count"] += 1
            if (str(sub), kid) in actual_lookup:
                slot["has_actuals_count"] += 1
            if pillar not in pillars_seen:
                slot["staff_count"] += 1
                pillars_seen.add(pillar)

    return {
        "manager_code": manager_code,
        "role": own.role,
        "period": period,
        "total_subordinates": len(subs),
        "own_breakdown": own,
        "team_pillar_summary": dict(team_summary),
    }


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    """Smoke test."""
    print("─ pillar_impact_engine self-test ─")
    bw = bank_pillar_weights()
    print(f"  bank_pillar_weights: {bw}")
    total = sum(bw.values())
    assert abs(total - 1.0) < 0.01, f"weights don't sum to 1.0: {total}"

    pm = kpi_to_strategic_pillar_map()
    print(f"  kpi→pillar map: {len(pm)} entries")
    assert len(pm) > 0

    # Try MD
    bd = pillar_breakdown_for_staff("300001", "2026")
    print(f"  MD breakdown: role={bd.role}, KPIs={bd.total_kpis}, "
          f"pillars={[p.pillar for p in bd.pillars]}")
    assert bd.total_kpis > 0

    # CRBO with subtree
    crbo = pillar_breakdown_for_manager("300002", "2026")
    print(f"  CRBO subtree: {crbo['total_subordinates']} subs, "
          f"{len(crbo['team_pillar_summary'])} pillars in team")
    assert crbo["total_subordinates"] > 0
    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
