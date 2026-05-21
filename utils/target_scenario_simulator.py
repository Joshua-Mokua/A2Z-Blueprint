"""Target Scenario Simulator — v10.408 (E3 QA-Standards enhancement).

Per Joshua's QA standards Enhancement #3:
  Problem: Managers cannot test "what-if" allocation scenarios.
  Solution: Interactive simulator for target allocation scenarios.

This is the TARGET-CASCADE what-if simulator — distinct from the existing
utils/scenario_simulator.py which handles risk/compliance scenarios
(LCR, fraud, disaster recovery).

Workflow:
  1. Manager picks a KPI + period.
  2. Sees CURRENT cascade allocation to their direct reports.
  3. Defines an ALTERNATIVE allocation (e.g., 60/40 instead of equal).
  4. Engine projects:
     - Achievement likelihood per report (vs historical 2-yr avg pct)
     - Coverage % (allocated_sum vs total_target)
     - Variance vs current allocation
     - BSC impact estimate per report
  5. Side-by-side comparison of current vs alternative.

The simulator is a PURE COMPUTATION module (Rule 7) — it does NOT
write to target_cascade.json. Manager separately saves the alternative
through CascadeManager.set_allocation if they choose to commit.

Shipped: v10.408.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class AllocationRow:
    """One direct report's allocation under a scenario."""
    to_code: str
    to_name: str
    to_role: str
    to_unit: str
    amount: float
    pct_of_total: float            # this row's % of total cascade pool
    historical_achievement_pct: Optional[float]  # 2-yr avg % achievement
    likelihood_label: str          # "very likely" / "likely" / "stretching" / "unrealistic"
    likelihood_score: float        # 0.0-1.0 — model confidence the target will be hit


@dataclass
class ScenarioResult:
    """One what-if scenario's computed result."""
    name: str                      # "Current" or "Alternative"
    kpi: str
    period: str
    total_target: float            # what's available to allocate
    allocated_sum: float           # sum of allocations
    coverage_pct: float            # allocated / total × 100
    rows: List[AllocationRow] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ComparisonReport:
    """Side-by-side comparison of two scenarios."""
    kpi: str
    period: str
    manager_code: str
    current: ScenarioResult
    alternative: ScenarioResult
    variance_per_row: List[Tuple[str, float, float]] = field(default_factory=list)
    # variance_per_row entries: (to_code, current_amount, alternative_amount)


# ════════════════════════════════════════════════════════════════════
# Lookups (cached at module load)
# ════════════════════════════════════════════════════════════════════

_USERS_CACHE: Optional[Dict[str, Any]] = None


def _users() -> Dict[str, Any]:
    global _USERS_CACHE
    if _USERS_CACHE is not None:
        return _USERS_CACHE
    path = DATA_DIR / "users.json"
    if not path.exists():
        _USERS_CACHE = {}
        return _USERS_CACHE
    _USERS_CACHE = json.loads(path.read_text(encoding="utf-8"))
    return _USERS_CACHE


def _staff_info(staff_code: str) -> Dict[str, str]:
    for u in _users().values():
        if isinstance(u, dict) and str(u.get("staff_code", "")) == str(staff_code):
            return {
                "name": str(u.get("full_name") or u.get("name", "")),
                "role": str(u.get("role", "")),
                "unit": str(u.get("unit") or u.get("department", "")),
            }
    return {"name": "?", "role": "?", "unit": "?"}


def _get_cascade_entry(manager_code: str, kpi: str, period: str) -> Optional[Dict[str, Any]]:
    """Load one cascade entry from target_cascade.json."""
    path = DATA_DIR / "target_cascade.json"
    if not path.exists():
        return None
    tc = json.loads(path.read_text(encoding="utf-8"))
    return tc.get(f"{manager_code}|{kpi}|{period}")


def _historical_achievement(staff_code: str, kpi: str) -> Optional[float]:
    """Compute 2-year average achievement % for staff+kpi.

    Reads prior year actuals from bsc_actuals_*.json files.
    Returns None if insufficient data (new hire / no history).
    """
    achievements: List[float] = []
    # Sample recent quarter files
    for variant in ("2025-Q4", "2025-Q3", "2025-Q2", "2025-Q1",
                   "2025", "2024-Q4", "2024-Q3"):
        path = DATA_DIR / f"bsc_actuals_{variant}.json"
        if not path.exists():
            continue
        try:
            recs = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(recs, list):
                continue
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                if (str(rec.get("staff_code")) == str(staff_code) and
                        (rec.get("kpi_id") == kpi or rec.get("kpi") == kpi)):
                    try:
                        act = float(rec.get("actual", 0))
                        tgt = float(rec.get("target", 0))
                        if tgt > 0:
                            achievements.append(act / tgt * 100)
                    except (TypeError, ValueError):
                        pass
        except (json.JSONDecodeError, OSError):
            continue
    if not achievements:
        return None
    return sum(achievements) / len(achievements)


def _classify_likelihood(
    new_amount: float,
    historical_actual_avg: Optional[float],
    historical_target_avg: Optional[float],
) -> Tuple[str, float]:
    """Classify how achievable a target is for this staff.

    Returns (label, score 0-1) where score is model confidence the
    new_amount will be achieved.
    """
    if historical_actual_avg is None or historical_target_avg is None or historical_target_avg <= 0:
        return ("unknown (no history)", 0.5)
    historical_capacity = historical_actual_avg  # what they actually delivered
    ratio = new_amount / historical_capacity if historical_capacity > 0 else 999.0
    if ratio <= 0.85:
        return ("very likely", 0.95)
    if ratio <= 1.0:
        return ("likely", 0.85)
    if ratio <= 1.10:
        return ("on stretch", 0.65)
    if ratio <= 1.25:
        return ("stretching", 0.45)
    if ratio <= 1.50:
        return ("very stretching", 0.25)
    return ("unrealistic", 0.10)


def _avg_actual_target_for_staff_kpi(
    staff_code: str, kpi: str
) -> Tuple[Optional[float], Optional[float]]:
    """Return (avg_actual, avg_target) from historical bsc_actuals."""
    actuals: List[float] = []
    targets: List[float] = []
    for variant in ("2025-Q4", "2025-Q3", "2025-Q2", "2025-Q1",
                   "2025", "2024-Q4", "2024-Q3"):
        path = DATA_DIR / f"bsc_actuals_{variant}.json"
        if not path.exists():
            continue
        try:
            recs = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(recs, list):
                continue
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                if (str(rec.get("staff_code")) == str(staff_code) and
                        (rec.get("kpi_id") == kpi or rec.get("kpi") == kpi)):
                    try:
                        a = float(rec.get("actual", 0))
                        t = float(rec.get("target", 0))
                        if a > 0:
                            actuals.append(a)
                        if t > 0:
                            targets.append(t)
                    except (TypeError, ValueError):
                        pass
        except (json.JSONDecodeError, OSError):
            continue
    avg_a = sum(actuals) / len(actuals) if actuals else None
    avg_t = sum(targets) / len(targets) if targets else None
    return avg_a, avg_t


# ════════════════════════════════════════════════════════════════════
# Scenario computation
# ════════════════════════════════════════════════════════════════════

def compute_scenario(
    name: str,
    manager_code: str,
    kpi: str,
    period: str,
    allocations: List[Dict[str, Any]],
    total_target: float,
) -> ScenarioResult:
    """Build a ScenarioResult from a proposed allocation list.

    allocations: list of dicts each with `to_code` and `amount`.
    """
    rows: List[AllocationRow] = []
    allocated_sum = 0.0
    for a in allocations:
        to_code = str(a.get("to_code", ""))
        amount = float(a.get("amount", 0) or 0)
        allocated_sum += amount
        info = _staff_info(to_code)
        avg_actual, avg_target = _avg_actual_target_for_staff_kpi(to_code, kpi)
        hist_pct = _historical_achievement(to_code, kpi)
        label, score = _classify_likelihood(amount, avg_actual, avg_target)
        pct = (amount / total_target * 100) if total_target else 0.0
        rows.append(AllocationRow(
            to_code=to_code,
            to_name=a.get("to_name") or info["name"],
            to_role=a.get("to_role") or info["role"],
            to_unit=a.get("to_unit") or info["unit"],
            amount=round(amount, 2),
            pct_of_total=round(pct, 2),
            historical_achievement_pct=(
                round(hist_pct, 1) if hist_pct is not None else None
            ),
            likelihood_label=label,
            likelihood_score=score,
        ))
    coverage = (allocated_sum / total_target * 100) if total_target else 0.0
    notes: List[str] = []
    if coverage < 99.0:
        notes.append(
            f"Under-allocated: {coverage:.1f}% of total target "
            f"(missing {total_target - allocated_sum:,.0f})"
        )
    elif coverage > 101.0:
        notes.append(
            f"Over-allocated: {coverage:.1f}% of total target "
            f"(excess {allocated_sum - total_target:,.0f})"
        )
    return ScenarioResult(
        name=name,
        kpi=kpi,
        period=period,
        total_target=total_target,
        allocated_sum=round(allocated_sum, 2),
        coverage_pct=round(coverage, 1),
        rows=rows,
        notes=notes,
    )


def load_current_scenario(
    manager_code: str, kpi: str, period: str
) -> Optional[ScenarioResult]:
    """Build a ScenarioResult from the current target_cascade entry."""
    entry = _get_cascade_entry(manager_code, kpi, period)
    if not entry:
        return None
    return compute_scenario(
        name="Current",
        manager_code=manager_code,
        kpi=kpi,
        period=period,
        allocations=entry.get("allocations", []),
        total_target=float(entry.get("total_target", 0) or 0),
    )


def simulate_alternative(
    manager_code: str,
    kpi: str,
    period: str,
    alternative_allocations: List[Dict[str, Any]],
) -> ComparisonReport:
    """Compare current cascade vs proposed alternative.

    alternative_allocations: list of {to_code, amount}.
    """
    current = load_current_scenario(manager_code, kpi, period)
    if not current:
        # No current entry — build empty current with same total_target inferred from alt
        alt_total = sum(float(a.get("amount", 0) or 0)
                       for a in alternative_allocations)
        current = ScenarioResult(
            name="Current",
            kpi=kpi,
            period=period,
            total_target=alt_total,
            allocated_sum=0.0,
            coverage_pct=0.0,
            notes=["No current cascade entry — using alternative total as benchmark."],
        )

    alternative = compute_scenario(
        name="Alternative",
        manager_code=manager_code,
        kpi=kpi,
        period=period,
        allocations=alternative_allocations,
        total_target=current.total_target,
    )

    # Build variance comparison
    current_map = {r.to_code: r.amount for r in current.rows}
    alt_map = {r.to_code: r.amount for r in alternative.rows}
    all_codes = set(current_map.keys()) | set(alt_map.keys())
    variance: List[Tuple[str, float, float]] = []
    for code in sorted(all_codes):
        variance.append((
            code,
            round(current_map.get(code, 0.0), 2),
            round(alt_map.get(code, 0.0), 2),
        ))

    return ComparisonReport(
        kpi=kpi,
        period=period,
        manager_code=manager_code,
        current=current,
        alternative=alternative,
        variance_per_row=variance,
    )


# ════════════════════════════════════════════════════════════════════
# Convenience: split methods
# ════════════════════════════════════════════════════════════════════

def split_equal(total: float, to_codes: List[str]) -> List[Dict[str, Any]]:
    """Equal split among recipients."""
    if not to_codes:
        return []
    per = total / len(to_codes)
    return [{"to_code": c, "amount": per} for c in to_codes]


def split_weighted_by_history(
    total: float, to_codes: List[str], kpi: str
) -> List[Dict[str, Any]]:
    """Split proportional to each recipient's historical actual.

    Strong performers (higher actuals) get bigger share.
    """
    weights = []
    for c in to_codes:
        avg_a, _ = _avg_actual_target_for_staff_kpi(c, kpi)
        weights.append(avg_a if avg_a else 0.0)
    total_w = sum(weights)
    if total_w <= 0:
        return split_equal(total, to_codes)
    return [
        {"to_code": c, "amount": total * w / total_w}
        for c, w in zip(to_codes, weights)
    ]


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ target_scenario_simulator self-test ─")
    # CRBO PBT 2026 — pick a real cascade entry
    cur = load_current_scenario("300002", "PBT", "2026")
    if cur:
        print(f"  CRBO PBT 2026 current: total={cur.total_target:,.0f}, "
              f"{len(cur.rows)} reports, coverage={cur.coverage_pct}%")
        for r in cur.rows[:3]:
            print(f"    {r.to_code} {r.to_name[:25]:<25s}: "
                  f"{r.amount:,.0f} ({r.pct_of_total}%) — {r.likelihood_label}")
    else:
        print("  CRBO PBT 2026: no cascade entry")

    # Simulate alternative — 50/30/20 split for first 3 reports
    if cur and len(cur.rows) >= 3:
        alt = [
            {"to_code": cur.rows[0].to_code, "amount": cur.total_target * 0.5},
            {"to_code": cur.rows[1].to_code, "amount": cur.total_target * 0.3},
            {"to_code": cur.rows[2].to_code, "amount": cur.total_target * 0.2},
        ]
        cmp_report = simulate_alternative("300002", "PBT", "2026", alt)
        print(f"  Alternative: {len(cmp_report.alternative.rows)} rows, "
              f"coverage={cmp_report.alternative.coverage_pct}%")
        for r in cmp_report.alternative.rows:
            print(f"    {r.to_code}: {r.amount:,.0f} — {r.likelihood_label} "
                  f"(score={r.likelihood_score:.2f})")

    # Split helpers
    equal = split_equal(1000, ["A", "B", "C", "D"])
    print(f"  split_equal(1000, 4) = {[r['amount'] for r in equal]}")
    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
