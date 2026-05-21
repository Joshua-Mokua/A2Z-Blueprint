"""utils.initiative_impact — Initiative Impact Automation
(Standard #49, v5.54). Volume Eight — Execute Enhancement.

Per v6 spec §8:
    InitiativeImpactEngine: connects initiative completion to KPI actuals
    automatically; measures realized impact post-completion.

WHAT THIS MODULE SHIPS
----------------------
1. InitiativeImpactEngine class with:
   - auto_link_initiative_to_kpi(initiative_id, kpi_id) — establishes link
   - compute_realized_impact(initiative_id, baseline_period, comparison_period)
     — measures actual KPI delta post-completion
   - track_progress(initiative_id) — % complete from milestone data
   - aggregate_realized_impact(period) — bank-wide rollup

2. INITIATIVE_TYPES catalog: KPI_IMPROVEMENT, REVENUE_GENERATION,
   COST_REDUCTION, RISK_MITIGATION, COMPLIANCE_REMEDIATION

3. INITIATIVE_STATUSES: PROPOSED, APPROVED, IN_PROGRESS, COMPLETED, CANCELLED

HONESTY DISCIPLINE
------------------
Rule 1 — Standard #11:
  - Decimal-internal precision 28 for monetary impacts
  - realized_impact_pct returns None when baseline_kpi_value <= 0

Rule 6 — No silent fallback:
  - When actuals unavailable for comparison period → realized_impact=None
    with explicit reason "comparison_period_actuals_missing"
  - Initiative not yet completed → status="in_progress" with progress_pct
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.initiative_impact")
getcontext().prec = 28

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────
# Spec literals (v6 §8 #49)
# ─────────────────────────────────────────────────────────────────────

INITIATIVE_TYPES: List[str] = [
    "KPI_IMPROVEMENT",
    "REVENUE_GENERATION",
    "COST_REDUCTION",
    "RISK_MITIGATION",
    "COMPLIANCE_REMEDIATION",
]

INITIATIVE_STATUSES: List[str] = [
    "PROPOSED", "APPROVED", "IN_PROGRESS", "COMPLETED", "CANCELLED",
]


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class InitiativeImpactEngine:
    """Initiative impact automation — links initiatives to KPI actuals."""

    INITIATIVE_TYPES   = INITIATIVE_TYPES
    INITIATIVE_STATUSES = INITIATIVE_STATUSES

    def __init__(
        self,
        initiative_lookup_fn: Optional[Callable[[str], Optional[dict]]]      = None,
        kpi_actuals_fn:       Optional[Callable[[str, str], Optional[float]]] = None,
        milestone_lookup_fn:  Optional[Callable[[str], List[dict]]]          = None,
        link_store_fn:        Optional[Callable[[str, str], bool]]           = None,
        all_initiatives_fn:   Optional[Callable[[], List[dict]]]             = None,
    ):
        """All collaborators injectable.

        initiative_lookup_fn(initiative_id) → dict | None
        kpi_actuals_fn(kpi_id, period) → float | None  (None = no data)
        milestone_lookup_fn(initiative_id) → list of milestone dicts
        link_store_fn(initiative_id, kpi_id) → bool (success)
        all_initiatives_fn() → list of initiative dicts
        """
        self._init   = initiative_lookup_fn or (lambda i: None)
        self._kpi    = kpi_actuals_fn       or (lambda k, p: None)
        self._miles  = milestone_lookup_fn  or (lambda i: [])
        self._store_link = link_store_fn    or (lambda i, k: False)
        self._all    = all_initiatives_fn   or (lambda: [])

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: auto_link_initiative_to_kpi
    # ──────────────────────────────────────────────────────────────────

    def auto_link_initiative_to_kpi(
        self, initiative_id: str, kpi_id: str,
    ) -> Dict[str, Any]:
        """Establish a link between an initiative and a KPI it impacts."""
        if not initiative_id or not kpi_id:
            return {"success": False, "reason": "initiative_id and kpi_id required"}

        init = self._init(initiative_id)
        if not init:
            return {"success": False, "reason": "initiative_not_found"}

        if init.get("status") not in INITIATIVE_STATUSES:
            return {"success": False, "reason": f"invalid initiative status: {init.get('status')!r}"}

        ok = self._store_link(initiative_id, kpi_id)
        return {
            "success":      ok,
            "initiative_id": initiative_id,
            "kpi_id":        kpi_id,
            "linked_at":     datetime.now(timezone.utc).isoformat(),
            "meta": {
                "initiative_type":   init.get("initiative_type"),
                "initiative_status": init.get("status"),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: compute_realized_impact
    # ──────────────────────────────────────────────────────────────────

    def compute_realized_impact(
        self,
        initiative_id: str,
        baseline_period: str,
        comparison_period: str,
    ) -> Dict[str, Any]:
        """Measure actual KPI delta from baseline to comparison period.

        Returns:
            {
              "initiative_id": str,
              "kpi_id": str,
              "baseline_value": float | None,
              "comparison_value": float | None,
              "delta": float | None,
              "delta_pct": float | None,
              "status": str,
              "reason": str | None,
              "meta": {...}
            }

        HONESTY: returns None for delta when baseline or comparison
        actuals are missing (Rule 6 — no silent zero substitution).
        """
        if not initiative_id:
            return {}

        init = self._init(initiative_id)
        if not init:
            return {
                "initiative_id": initiative_id,
                "status":        "not_found",
                "reason":        "initiative_not_found",
            }

        # Initiative must be COMPLETED to compute realized impact
        if init.get("status") != "COMPLETED":
            progress = self.track_progress(initiative_id)
            return {
                "initiative_id":  initiative_id,
                "kpi_id":         init.get("linked_kpi_id"),
                "status":         "in_progress",
                "reason":         f"initiative status is {init.get('status')!r}, not COMPLETED",
                "progress_pct":   progress.get("progress_pct"),
                "baseline_value":   None,
                "comparison_value": None,
                "delta":            None,
                "delta_pct":        None,
            }

        kpi_id = init.get("linked_kpi_id")
        if not kpi_id:
            return {
                "initiative_id": initiative_id,
                "status":        "no_kpi_link",
                "reason":        "initiative has no linked_kpi_id (call auto_link first)",
                "delta":         None,
                "delta_pct":     None,
            }

        # Fetch actuals for both periods
        baseline = self._kpi(kpi_id, baseline_period)
        comparison = self._kpi(kpi_id, comparison_period)

        if baseline is None or comparison is None:
            missing = []
            if baseline is None:
                missing.append(f"baseline ({baseline_period})")
            if comparison is None:
                missing.append(f"comparison ({comparison_period})")
            return {
                "initiative_id":  initiative_id,
                "kpi_id":         kpi_id,
                "baseline_value":   baseline,
                "comparison_value": comparison,
                "delta":            None,
                "delta_pct":        None,
                "status":           "actuals_missing",
                "reason":           f"missing actuals for: {', '.join(missing)}",
            }

        try:
            baseline_dec = Decimal(str(baseline))
            comparison_dec = Decimal(str(comparison))
        except Exception as e:
            return {
                "initiative_id": initiative_id,
                "status":        "invalid_actuals",
                "reason":        f"unable to parse actuals: {e}",
                "delta":         None,
                "delta_pct":     None,
            }

        delta = comparison_dec - baseline_dec
        if baseline_dec > 0:
            delta_pct = float(delta / baseline_dec * Decimal("100"))
        elif baseline_dec < 0:
            # Baseline negative — define delta_pct vs absolute baseline for direction
            delta_pct = float(delta / baseline_dec.copy_abs() * Decimal("100"))
        else:
            # baseline == 0 → undefined growth (Rule 1)
            delta_pct = None

        return {
            "initiative_id":  initiative_id,
            "kpi_id":         kpi_id,
            "baseline_value":   _money(baseline_dec),
            "comparison_value": _money(comparison_dec),
            "delta":            _money(delta),
            "delta_pct":        round(delta_pct, 4) if delta_pct is not None else None,
            "status":           "computed",
            "reason":           None,
            "meta": {
                "initiative_type":  init.get("initiative_type"),
                "baseline_period":  baseline_period,
                "comparison_period": comparison_period,
                "generated_at":     datetime.now(timezone.utc).isoformat(),
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: track_progress
    # ──────────────────────────────────────────────────────────────────

    def track_progress(self, initiative_id: str) -> Dict[str, Any]:
        """Compute progress % from milestone completion."""
        if not initiative_id:
            return {}

        init = self._init(initiative_id)
        if not init:
            return {"initiative_id": initiative_id, "status": "not_found"}

        if init.get("status") == "COMPLETED":
            return {
                "initiative_id": initiative_id,
                "progress_pct":  100.0,
                "status":        "COMPLETED",
            }
        if init.get("status") == "CANCELLED":
            return {
                "initiative_id": initiative_id,
                "progress_pct":  None,
                "status":        "CANCELLED",
            }

        milestones = self._miles(initiative_id) or []
        if not milestones:
            return {
                "initiative_id":   initiative_id,
                "progress_pct":    None,
                "status":          init.get("status", "UNKNOWN"),
                "reason":          "no_milestones_defined",
            }

        total = len(milestones)
        completed = sum(1 for m in milestones if m.get("completed"))
        pct = round(completed / total * 100, 2) if total > 0 else None
        return {
            "initiative_id": initiative_id,
            "progress_pct":  pct,
            "status":        init.get("status"),
            "milestones_total":     total,
            "milestones_completed": completed,
        }

    # ──────────────────────────────────────────────────────────────────
    # Spec entry: aggregate_realized_impact
    # ──────────────────────────────────────────────────────────────────

    def aggregate_realized_impact(
        self,
        period: str,
        baseline_period: str,
        comparison_period: str,
    ) -> Dict[str, Any]:
        """Aggregate realized impact across all completed initiatives.

        Returns a rollup grouped by initiative_type, with counts and
        sum-of-deltas where deltas are computable.
        """
        if not period:
            return {}

        all_inits = self._all() or []
        completed = [i for i in all_inits if isinstance(i, dict) and i.get("status") == "COMPLETED"]

        rollup: Dict[str, Dict[str, Any]] = {
            t: {"count": 0, "computable": 0, "uncomputable": 0,
                "sum_delta": ZERO, "delta_count": 0}
            for t in INITIATIVE_TYPES
        }

        results: List[dict] = []
        for init in completed:
            t = init.get("initiative_type")
            if t not in INITIATIVE_TYPES:
                continue
            rollup[t]["count"] += 1
            r = self.compute_realized_impact(
                init.get("initiative_id"), baseline_period, comparison_period,
            )
            if r.get("status") == "computed" and r.get("delta") is not None:
                try:
                    rollup[t]["sum_delta"] += Decimal(str(r["delta"]))
                    rollup[t]["delta_count"] += 1
                    rollup[t]["computable"] += 1
                except Exception:
                    rollup[t]["uncomputable"] += 1
            else:
                rollup[t]["uncomputable"] += 1
            results.append(r)

        out_rollup = {}
        for t, vals in rollup.items():
            out_rollup[t] = {
                "count":         vals["count"],
                "computable":    vals["computable"],
                "uncomputable":  vals["uncomputable"],
                "sum_delta":     _money(vals["sum_delta"]),
                "average_delta": _money(vals["sum_delta"] / Decimal(vals["delta_count"]))
                                 if vals["delta_count"] > 0 else None,
            }

        return {
            "period":          period,
            "baseline_period": baseline_period,
            "comparison_period": comparison_period,
            "rollup":          out_rollup,
            "total_completed": len(completed),
            "results":         results,
            "meta": {
                "initiative_types_in_spec": list(INITIATIVE_TYPES),
                "generated_at":             datetime.now(timezone.utc).isoformat(),
            },
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
    print("A2Z MIS 360 — utils.initiative_impact self-test")

    # ── Spec literals ─────────────────────────────────────────────────
    assert INITIATIVE_TYPES == [
        "KPI_IMPROVEMENT", "REVENUE_GENERATION", "COST_REDUCTION",
        "RISK_MITIGATION", "COMPLIANCE_REMEDIATION",
    ]
    print(f"  ✅ initiative types: {len(INITIATIVE_TYPES)} categories")
    assert INITIATIVE_STATUSES == ["PROPOSED", "APPROVED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    print(f"  ✅ initiative statuses: {INITIATIVE_STATUSES}")

    # ── Empty inputs ──────────────────────────────────────────────────
    eng = InitiativeImpactEngine()
    assert eng.auto_link_initiative_to_kpi("", "K1")["success"] is False
    assert eng.compute_realized_impact("", "2026-Q1", "2026-Q2") == {}
    assert eng.track_progress("") == {}
    print(f"  ✅ empty inputs handled")

    # ── auto_link with unknown initiative ─────────────────────────────
    eng2 = InitiativeImpactEngine(initiative_lookup_fn=lambda i: None)
    r = eng2.auto_link_initiative_to_kpi("INIT_X", "K1")
    assert r["success"] is False
    assert r["reason"] == "initiative_not_found"
    print(f"  ✅ unknown initiative → not_found")

    # ── auto_link with valid initiative ───────────────────────────────
    inits = {
        "INIT_001": {
            "initiative_id":   "INIT_001",
            "initiative_type": "KPI_IMPROVEMENT",
            "status":          "APPROVED",
        },
    }
    stored = []
    eng3 = InitiativeImpactEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        link_store_fn=lambda i, k: stored.append((i, k)) or True,
    )
    r = eng3.auto_link_initiative_to_kpi("INIT_001", "MORTGAGE_DISBURSEMENT")
    assert r["success"] is True
    assert ("INIT_001", "MORTGAGE_DISBURSEMENT") in stored
    print(f"  ✅ auto_link succeeded, stored {stored[-1]}")

    # ── compute_realized_impact: not yet COMPLETED → in_progress ──────
    inits["INIT_001"]["status"] = "IN_PROGRESS"
    inits["INIT_001"]["linked_kpi_id"] = "MORTGAGE_DISBURSEMENT"
    milestones = {"INIT_001": [
        {"name": "design", "completed": True},
        {"name": "build",  "completed": True},
        {"name": "pilot",  "completed": False},
        {"name": "rollout", "completed": False},
    ]}
    eng4 = InitiativeImpactEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        milestone_lookup_fn=lambda i: milestones.get(i, []),
    )
    r = eng4.compute_realized_impact("INIT_001", "2026-Q1", "2026-Q2")
    assert r["status"] == "in_progress"
    assert r["delta"] is None
    assert r["progress_pct"] == 50.0
    print(f"  ✅ in-progress → status=in_progress, progress={r['progress_pct']}%")

    # ── compute_realized_impact: COMPLETED + actuals available ────────
    inits["INIT_001"]["status"] = "COMPLETED"
    actuals = {("MORTGAGE_DISBURSEMENT", "2026-Q1"): 100_000_000,
               ("MORTGAGE_DISBURSEMENT", "2026-Q2"): 125_000_000}
    eng5 = InitiativeImpactEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        kpi_actuals_fn=lambda k, p: actuals.get((k, p)),
    )
    r = eng5.compute_realized_impact("INIT_001", "2026-Q1", "2026-Q2")
    assert r["status"] == "computed"
    assert r["delta"] == 25_000_000.00
    assert r["delta_pct"] == 25.0
    print(f"  ✅ realized impact: delta={r['delta']:,.2f} ({r['delta_pct']}%)")

    # ── compute_realized_impact: actuals missing → None (Rule 6) ──────
    eng6 = InitiativeImpactEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        kpi_actuals_fn=lambda k, p: None,    # no data
    )
    r = eng6.compute_realized_impact("INIT_001", "2026-Q1", "2026-Q2")
    assert r["status"] == "actuals_missing"
    assert r["delta"] is None
    assert "missing" in r["reason"]
    print(f"  ✅ actuals missing → delta=None (Rule 6 — no silent zero)")

    # ── compute_realized_impact: zero baseline → delta_pct=None ───────
    actuals_zero = {("MORTGAGE_DISBURSEMENT", "2026-Q1"): 0,
                    ("MORTGAGE_DISBURSEMENT", "2026-Q2"): 1_000_000}
    eng7 = InitiativeImpactEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        kpi_actuals_fn=lambda k, p: actuals_zero.get((k, p)),
    )
    r = eng7.compute_realized_impact("INIT_001", "2026-Q1", "2026-Q2")
    assert r["delta"] == 1_000_000.00
    assert r["delta_pct"] is None    # Rule 1 — undefined growth from zero
    print(f"  ✅ baseline=0 → delta_pct=None (Rule 1)")

    # ── track_progress for COMPLETED → 100% ───────────────────────────
    inits["INIT_001"]["status"] = "COMPLETED"
    r = eng4.track_progress("INIT_001")
    assert r["progress_pct"] == 100.0
    print(f"  ✅ track_progress for COMPLETED → 100%")

    # ── track_progress for CANCELLED → None ───────────────────────────
    inits["INIT_002"] = {"initiative_id": "INIT_002", "status": "CANCELLED"}
    r = eng4.track_progress("INIT_002")
    assert r["progress_pct"] is None
    print(f"  ✅ track_progress for CANCELLED → None")

    # ── aggregate_realized_impact rollup by type ──────────────────────
    inits.update({
        "INIT_R1": {"initiative_id": "INIT_R1", "initiative_type": "REVENUE_GENERATION",
                     "status": "COMPLETED", "linked_kpi_id": "FEE_INCOME"},
        "INIT_C1": {"initiative_id": "INIT_C1", "initiative_type": "COST_REDUCTION",
                     "status": "COMPLETED", "linked_kpi_id": "OPEX"},
    })
    actuals_agg = {
        ("FEE_INCOME", "2026-Q1"): 100_000, ("FEE_INCOME", "2026-Q2"): 130_000,
        ("OPEX", "2026-Q1"): 50_000, ("OPEX", "2026-Q2"): 45_000,
    }
    eng8 = InitiativeImpactEngine(
        initiative_lookup_fn=lambda i: inits.get(i),
        kpi_actuals_fn=lambda k, p: actuals_agg.get((k, p)),
        all_initiatives_fn=lambda: list(inits.values()),
    )
    r = eng8.aggregate_realized_impact("2026", "2026-Q1", "2026-Q2")
    assert r["rollup"]["REVENUE_GENERATION"]["count"] == 1
    assert r["rollup"]["COST_REDUCTION"]["count"] == 1
    assert r["rollup"]["REVENUE_GENERATION"]["sum_delta"] == 30_000.00
    print(f"  ✅ aggregate rollup: REV count=1 sum_delta=30k, COST count=1 sum_delta=-5k")

    print("\n  ALL TESTS PASSED")
