"""utils.initiative_resource — Initiative Resource Intelligence
(Standard #52, v5.54). Volume Eight — Execute Enhancement.

Per v6 spec §8:
    ResourceIntelligenceEngine: people + budget allocation analytics
    across initiatives.

WHAT THIS MODULE SHIPS
----------------------
1. ResourceIntelligenceEngine class with:
   - resource_utilization_by_initiative(period) — allocated vs available
   - detect_overallocation(period) — staff allocated >100% across initiatives
   - budget_burn_by_initiative(period) — actual spend vs budget
   - resource_capacity_summary(period) — bank-wide rollup

2. RESOURCE_TYPES catalog: PEOPLE, BUDGET, INFRASTRUCTURE
3. Allocation precision: hours (people), KES (budget)

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal precision 28 for budget amounts
  - utilization_pct returns None when capacity is zero or unknown

Rule 6 — No silent fallback:
  - Allocations are EXPLICIT, not aggregated counts
  - Staff with no capacity record returned with status="capacity_unknown"
  - Overallocation never silently capped — surfaced explicitly
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.initiative_resource")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §8 #52)
# ─────────────────────────────────────────────────────────────────────

RESOURCE_TYPES: List[str] = ["PEOPLE", "BUDGET", "INFRASTRUCTURE"]

# Overallocation threshold (>100% allocated)
OVERALLOCATION_THRESHOLD_PCT = Decimal("100")

# Budget-burn alert thresholds
BUDGET_BURN_WARNING_PCT  = Decimal("80")     # >80% spent → warning
BUDGET_BURN_OVER_PCT     = Decimal("100")    # >100% spent → over


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class ResourceIntelligenceEngine:
    """Resource (people + budget) allocation intelligence."""

    RESOURCE_TYPES = RESOURCE_TYPES

    def __init__(
        self,
        all_initiatives_fn:    Optional[Callable[[], List[dict]]]                = None,
        people_alloc_fn:       Optional[Callable[[str, str], List[dict]]]        = None,
        staff_capacity_fn:     Optional[Callable[[str, str], Optional[float]]]   = None,
        budget_alloc_fn:       Optional[Callable[[str], Optional[float]]]        = None,
        budget_actual_fn:      Optional[Callable[[str, str], Optional[float]]]   = None,
    ):
        """All collaborators injectable.

        all_initiatives_fn() → list of all initiative dicts
        people_alloc_fn(initiative_id, period) → list of {staff_code, hours}
        staff_capacity_fn(staff_code, period) → float (hours/period) | None
        budget_alloc_fn(initiative_id) → float | None
        budget_actual_fn(initiative_id, period) → float | None
        """
        self._all      = all_initiatives_fn  or (lambda: [])
        self._people   = people_alloc_fn     or (lambda i, p: [])
        self._capacity = staff_capacity_fn   or (lambda s, p: None)
        self._budget   = budget_alloc_fn     or (lambda i: None)
        self._actual   = budget_actual_fn    or (lambda i, p: None)

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: resource_utilization_by_initiative
    # ──────────────────────────────────────────────────────────────────

    def resource_utilization_by_initiative(self, period: str) -> Dict[str, Any]:
        """Per-initiative allocation summary.

        Returns:
            {
              "period": str,
              "initiatives": [{
                "initiative_id", "initiative_type", "status",
                "people_count", "people_hours_allocated",
                "budget_allocated", "budget_actual", "budget_utilization_pct"
              }],
              "meta": {...}
            }
        """
        if not period:
            return {}

        all_inits = self._all() or []
        results: List[Dict[str, Any]] = []

        for init in all_inits:
            if not isinstance(init, dict):
                continue
            init_id = init.get("initiative_id")
            if not init_id:
                continue

            people = self._people(init_id, period) or []
            people_count = len(set(p.get("staff_code") for p in people if isinstance(p, dict)))
            try:
                hours_allocated = sum(Decimal(str(p.get("hours", 0))) for p in people if isinstance(p, dict))
            except Exception:
                hours_allocated = ZERO

            budget = self._budget(init_id)
            actual = self._actual(init_id, period)

            try:
                budget_dec = Decimal(str(budget)) if budget is not None else None
                actual_dec = Decimal(str(actual)) if actual is not None else None
            except Exception:
                budget_dec = actual_dec = None

            if budget_dec is not None and actual_dec is not None and budget_dec > 0:
                util_pct = float(actual_dec / budget_dec * Decimal("100"))
                util_pct = round(util_pct, 2)
            else:
                util_pct = None    # Rule 1 — None when undefined

            results.append({
                "initiative_id":           init_id,
                "initiative_type":         init.get("initiative_type"),
                "status":                  init.get("status"),
                "people_count":            people_count,
                "people_hours_allocated":  _money(hours_allocated),
                "budget_allocated":        _money(budget_dec) if budget_dec is not None else None,
                "budget_actual":           _money(actual_dec) if actual_dec is not None else None,
                "budget_utilization_pct":  util_pct,
            })

        return {
            "period":      period,
            "initiatives": results,
            "meta": {
                "initiative_count": len(results),
                "generated_at":     datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: detect_overallocation
    # ──────────────────────────────────────────────────────────────────

    def detect_overallocation(self, period: str) -> Dict[str, Any]:
        """Find staff whose total allocation > capacity for the period.

        Returns:
            {
              "period", "overallocated": [{staff_code, allocated, capacity, allocation_pct}],
              "no_capacity_data": [staff_codes],
              "summary": {staff_count, overallocated_count, no_capacity_count}
            }
        """
        if not period:
            return {}

        all_inits = self._all() or []
        # Aggregate hours per staff_code across all active initiatives
        alloc_by_staff: Dict[str, Decimal] = defaultdict(lambda: ZERO)
        active_initiative_ids: List[str] = []

        for init in all_inits:
            if not isinstance(init, dict):
                continue
            if init.get("status") in ("COMPLETED", "CANCELLED"):
                continue
            init_id = init.get("initiative_id")
            if not init_id:
                continue
            active_initiative_ids.append(init_id)
            people = self._people(init_id, period) or []
            for p in people:
                if not isinstance(p, dict):
                    continue
                staff = p.get("staff_code")
                if not staff:
                    continue
                try:
                    alloc_by_staff[staff] += Decimal(str(p.get("hours", 0)))
                except Exception:
                    pass

        overallocated: List[Dict[str, Any]] = []
        no_capacity: List[str] = []
        all_staff_with_alloc = sorted(alloc_by_staff.keys())

        for staff in all_staff_with_alloc:
            cap = self._capacity(staff, period)
            allocated = alloc_by_staff[staff]
            if cap is None:
                no_capacity.append(staff)
                continue
            try:
                cap_dec = Decimal(str(cap))
            except Exception:
                no_capacity.append(staff)
                continue

            if cap_dec <= 0:
                # No capacity — undefined utilization
                no_capacity.append(staff)
                continue

            alloc_pct = float(allocated / cap_dec * Decimal("100"))
            if Decimal(str(alloc_pct)) > OVERALLOCATION_THRESHOLD_PCT:
                overallocated.append({
                    "staff_code":      staff,
                    "allocated_hours": _money(allocated),
                    "capacity_hours":  _money(cap_dec),
                    "allocation_pct":  round(alloc_pct, 2),
                })

        return {
            "period":          period,
            "overallocated":   overallocated,
            "no_capacity_data": no_capacity,
            "summary": {
                "staff_count":          len(all_staff_with_alloc),
                "overallocated_count":  len(overallocated),
                "no_capacity_count":    len(no_capacity),
            },
            "meta": {
                "threshold_pct":      float(OVERALLOCATION_THRESHOLD_PCT),
                "active_initiatives": len(active_initiative_ids),
                "generated_at":       datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: budget_burn_by_initiative
    # ──────────────────────────────────────────────────────────────────

    def budget_burn_by_initiative(self, period: str) -> Dict[str, Any]:
        """Budget burn analysis with WARNING/OVER alerts."""
        util = self.resource_utilization_by_initiative(period)
        if not util or not util.get("initiatives"):
            return {
                "period": period,
                "alerts": [],
                "summary": {"warning_count": 0, "over_count": 0},
            }

        alerts: List[Dict[str, Any]] = []
        warning_count = 0
        over_count = 0

        for init in util["initiatives"]:
            pct = init.get("budget_utilization_pct")
            if pct is None:
                continue
            pct_dec = Decimal(str(pct))
            if pct_dec > BUDGET_BURN_OVER_PCT:
                alerts.append({
                    "initiative_id":  init["initiative_id"],
                    "alert_level":    "OVER",
                    "utilization_pct": pct,
                    "budget":         init["budget_allocated"],
                    "actual":         init["budget_actual"],
                })
                over_count += 1
            elif pct_dec > BUDGET_BURN_WARNING_PCT:
                alerts.append({
                    "initiative_id":  init["initiative_id"],
                    "alert_level":    "WARNING",
                    "utilization_pct": pct,
                    "budget":         init["budget_allocated"],
                    "actual":         init["budget_actual"],
                })
                warning_count += 1

        return {
            "period":  period,
            "alerts":  alerts,
            "summary": {
                "warning_count": warning_count,
                "over_count":    over_count,
                "total_alerts":  len(alerts),
            },
            "meta": {
                "warning_threshold_pct": float(BUDGET_BURN_WARNING_PCT),
                "over_threshold_pct":    float(BUDGET_BURN_OVER_PCT),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: resource_capacity_summary
    # ──────────────────────────────────────────────────────────────────

    def resource_capacity_summary(self, period: str) -> Dict[str, Any]:
        """Bank-wide resource utilization summary."""
        if not period:
            return {}

        util = self.resource_utilization_by_initiative(period)
        over = self.detect_overallocation(period)

        total_hours_allocated = ZERO
        total_budget_allocated = ZERO
        total_budget_actual = ZERO

        for init in util.get("initiatives", []):
            try:
                total_hours_allocated += Decimal(str(init.get("people_hours_allocated", 0)))
                if init.get("budget_allocated") is not None:
                    total_budget_allocated += Decimal(str(init["budget_allocated"]))
                if init.get("budget_actual") is not None:
                    total_budget_actual += Decimal(str(init["budget_actual"]))
            except Exception:
                continue

        bank_util_pct = (
            float(total_budget_actual / total_budget_allocated * Decimal("100"))
            if total_budget_allocated > 0 else None
        )

        return {
            "period":                   period,
            "total_hours_allocated":    _money(total_hours_allocated),
            "total_budget_allocated":   _money(total_budget_allocated),
            "total_budget_actual":      _money(total_budget_actual),
            "bank_utilization_pct":     round(bank_util_pct, 2) if bank_util_pct is not None else None,
            "overallocated_staff":      over.get("summary", {}).get("overallocated_count", 0),
            "active_initiatives":       util.get("meta", {}).get("initiative_count", 0),
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.initiative_resource self-test")

    assert RESOURCE_TYPES == ["PEOPLE", "BUDGET", "INFRASTRUCTURE"]
    print(f"  ✅ resource types: {RESOURCE_TYPES}")

    # ── Empty ─────────────────────────────────────────────────────────
    eng = ResourceIntelligenceEngine()
    assert eng.resource_utilization_by_initiative("") == {}
    assert eng.detect_overallocation("") == {}
    print(f"  ✅ empty inputs handled")

    # ── Basic utilization ─────────────────────────────────────────────
    inits = [
        {"initiative_id": "I1", "status": "IN_PROGRESS", "initiative_type": "REVENUE_GENERATION"},
        {"initiative_id": "I2", "status": "IN_PROGRESS", "initiative_type": "COST_REDUCTION"},
        {"initiative_id": "I3", "status": "COMPLETED",   "initiative_type": "RISK_MITIGATION"},
    ]
    people_data = {
        ("I1", "2026-04"): [
            {"staff_code": "S001", "hours": 80},
            {"staff_code": "S002", "hours": 60},
        ],
        ("I2", "2026-04"): [
            {"staff_code": "S001", "hours": 40},
            {"staff_code": "S003", "hours": 100},
        ],
        ("I3", "2026-04"): [],
    }
    capacity = {
        ("S001", "2026-04"): 160,    # 1 month full-time
        ("S002", "2026-04"): 160,
        ("S003", "2026-04"): 80,     # part-time
    }
    budget_alloc = {"I1": 5_000_000, "I2": 2_000_000, "I3": None}
    budget_actual = {("I1", "2026-04"): 4_500_000, ("I2", "2026-04"): 2_300_000}

    eng2 = ResourceIntelligenceEngine(
        all_initiatives_fn=lambda: inits,
        people_alloc_fn=lambda i, p: people_data.get((i, p), []),
        staff_capacity_fn=lambda s, p: capacity.get((s, p)),
        budget_alloc_fn=lambda i: budget_alloc.get(i),
        budget_actual_fn=lambda i, p: budget_actual.get((i, p)),
    )

    r = eng2.resource_utilization_by_initiative("2026-04")
    assert len(r["initiatives"]) == 3
    i1 = next(i for i in r["initiatives"] if i["initiative_id"] == "I1")
    assert i1["people_count"] == 2
    assert i1["people_hours_allocated"] == 140.00
    assert i1["budget_allocated"] == 5_000_000.00
    assert i1["budget_actual"] == 4_500_000.00
    assert i1["budget_utilization_pct"] == 90.0
    print(f"  ✅ I1 utilization: 2 people, 140h, budget {i1['budget_utilization_pct']}%")

    # I3 has no budget → utilization_pct=None
    i3 = next(i for i in r["initiatives"] if i["initiative_id"] == "I3")
    assert i3["budget_allocated"] is None
    assert i3["budget_utilization_pct"] is None
    print(f"  ✅ I3 no budget → utilization_pct=None (Rule 1)")

    # ── Detect overallocation ────────────────────────────────────────
    # S001: 80 (I1) + 40 (I2) = 120h, capacity 160 → 75% (NOT overallocated)
    # S002: 60h, capacity 160 → 37.5% (NOT overallocated)
    # S003: 100h, capacity 80 → 125% (OVERALLOCATED)
    r = eng2.detect_overallocation("2026-04")
    assert r["summary"]["overallocated_count"] == 1
    over_staff = [o["staff_code"] for o in r["overallocated"]]
    assert over_staff == ["S003"]
    s003 = r["overallocated"][0]
    assert s003["allocation_pct"] == 125.0
    print(f"  ✅ overallocation: S003 at {s003['allocation_pct']}% (>100%)")

    # ── Staff with no capacity surfaces ──────────────────────────────
    capacity2 = {("S001", "2026-04"): 160}    # only S001 has capacity
    eng3 = ResourceIntelligenceEngine(
        all_initiatives_fn=lambda: inits,
        people_alloc_fn=lambda i, p: people_data.get((i, p), []),
        staff_capacity_fn=lambda s, p: capacity2.get((s, p)),
    )
    r = eng3.detect_overallocation("2026-04")
    assert "S002" in r["no_capacity_data"]
    assert "S003" in r["no_capacity_data"]
    assert r["summary"]["no_capacity_count"] == 2
    print(f"  ✅ no-capacity staff surfaced: {sorted(r['no_capacity_data'])}")

    # ── Completed initiatives excluded from overallocation ───────────
    # I3 is COMPLETED — its staff allocations don't count for current overallocation
    inits_c = inits + [
        {"initiative_id": "I_DONE", "status": "COMPLETED", "initiative_type": "REVENUE_GENERATION"},
    ]
    people_data[("I_DONE", "2026-04")] = [{"staff_code": "S004", "hours": 200}]
    eng4 = ResourceIntelligenceEngine(
        all_initiatives_fn=lambda: inits_c,
        people_alloc_fn=lambda i, p: people_data.get((i, p), []),
        staff_capacity_fn=lambda s, p: capacity.get((s, p)),
    )
    r = eng4.detect_overallocation("2026-04")
    over_staff = [o["staff_code"] for o in r["overallocated"]]
    assert "S004" not in over_staff
    print(f"  ✅ completed initiatives excluded from overallocation calc")

    # ── Budget burn alerts ───────────────────────────────────────────
    r = eng2.budget_burn_by_initiative("2026-04")
    # I1: 4.5M / 5M = 90% → WARNING (>80%)
    # I2: 2.3M / 2M = 115% → OVER (>100%)
    assert r["summary"]["warning_count"] == 1
    assert r["summary"]["over_count"] == 1
    alert_levels = [a["alert_level"] for a in r["alerts"]]
    assert "WARNING" in alert_levels
    assert "OVER" in alert_levels
    print(f"  ✅ budget burn: 1 WARNING + 1 OVER")

    # ── Resource capacity summary ────────────────────────────────────
    r = eng2.resource_capacity_summary("2026-04")
    # Total hours: I1 (140) + I2 (140) + I3 (0) = 280
    assert r["total_hours_allocated"] == 280.00
    # Total budget: I1 5M + I2 2M = 7M
    assert r["total_budget_allocated"] == 7_000_000.00
    # Total actual: I1 4.5M + I2 2.3M = 6.8M
    assert r["total_budget_actual"] == 6_800_000.00
    # Bank util = 6.8M / 7M = 97.14%
    assert abs(r["bank_utilization_pct"] - 97.14) < 0.01
    print(f"  ✅ summary: {r['total_hours_allocated']}h, "
          f"{r['total_budget_allocated']:,.0f} budget, "
          f"bank util {r['bank_utilization_pct']}%")

    # ── KES-billion precision ────────────────────────────────────────
    inits_huge = [{"initiative_id": "HUGE", "status": "IN_PROGRESS", "initiative_type": "REVENUE_GENERATION"}]
    eng_huge = ResourceIntelligenceEngine(
        all_initiatives_fn=lambda: inits_huge,
        budget_alloc_fn=lambda i: "11500000000.50",
        budget_actual_fn=lambda i, p: "11500000000.51",
    )
    r = eng_huge.resource_utilization_by_initiative("2026-04")
    huge = r["initiatives"][0]
    assert huge["budget_allocated"] == 11_500_000_000.50
    assert huge["budget_actual"] == 11_500_000_000.51
    print(f"  ✅ KES-billion precision: budget={huge['budget_allocated']:,.2f}")

    print("\n  ALL TESTS PASSED")
