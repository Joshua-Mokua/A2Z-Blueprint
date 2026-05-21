"""utils.allocation_optimizer — Customer-to-RM Allocation Intelligence
(Standard #24, v5.49). Volume Three.

Per the master spec:

    class CustomerAllocationOptimizer:
        def optimize_rm_allocation(self, segment):
            for customer in customers:
                for rm in rms:
                    projected_pbt = self.project_profitability_if_served_by(customer, rm)
            return {"assignments": assignments, "total_potential_gain": total_potential_gain}

Verification: not stated explicitly. The verifiable structural claim is
**optimization correctness on labelled fixtures**: given known-optimal
allocations, the engine reproduces the same total PBT within ≥99%.
Audit gate G35.

WHAT THIS ENGINE DOES
----------------------
For a given segment of the bank's book (e.g. Mass Retail, SME, Corporate):

  1. Get the customers in that segment
  2. Get the RMs available to serve that segment
  3. For each (customer, rm) pair, project the PBT if served by that RM
  4. Solve the assignment problem to maximize total projected PBT
     subject to RM capacity constraints
  5. Return assignments + total_potential_gain (delta vs current allocation)

THE ASSIGNMENT PROBLEM
----------------------
This is the classic "linear assignment" with capacity. For small
banks (≤100 customers, ≤20 RMs in a segment), an O(N×M) greedy
algorithm gives near-optimal results in practice and runs fast.
For larger problem sizes, a proper Hungarian algorithm or LP
solver should replace the greedy approach (documented as
ARCHITECTURAL_LIMITATION_LARGE_BOOK).

GREEDY ALGORITHM (v5.49)
-------------------------
1. Compute the full (customer, rm) → projected_pbt matrix
2. Compute "marginal gain" for each (customer, rm) pair = projected_pbt
   minus the customer's CURRENT allocation pbt (if any). This sorts
   pairs that move customers to better-fit RMs ahead of pairs that
   keep customers where they are.
3. Iterate the pairs in descending marginal gain order:
     - If the customer is still unassigned AND the RM still has
       capacity, assign the pair, decrement RM capacity, mark
       customer as assigned
     - Otherwise skip
4. Compute total_potential_gain = sum(projected_pbt - current_pbt)

This guarantees:
  - No RM exceeds capacity
  - Every customer gets exactly one assignment (or remains unassigned
    if all eligible RMs are at capacity)
  - The algorithm is deterministic given the same inputs (lex
    tie-breaking on (rm_code, customer_id) when marginal gains tie)
  - On labelled fixtures with simple structures, greedy hits the
    optimal solution

HONESTY INHERITANCE FROM MANDATORY STANDARD #11
================================================
This engine consumes projected PBTs that originate from #21's
CustomerProfitabilityEngine. The same FTP/balance-basis assumptions
that apply to #21 apply to projections used here.

Mechanisms inherited (per Mandatory Standard #11 portfolio-level
inheritance section in the master prompt):

  1. meta.upstream_ftp_modes counter — how the projected PBTs split
     by upstream FTP mode
  2. data_quality_warning when ANY projection had ftp_mode="off"
     (with explicit Mandatory Standard #11 citation)
  3. provisional flag on the optimization result when >50% of
     projections ran on naive math

These mean an optimization result that says "move 12 customers from
RM_A to RM_B for KES 8M total gain" is correctly flagged as
provisional if the underlying projections are FTP-blind — saving
the bank from an expensive reorganization based on wrong economics.

ADDITIONAL HONESTY RULES
------------------------
4. Empty segment / no customers → returns {"assignments": [],
   "total_potential_gain": 0.0, ...} with data_quality_warning
   explaining the empty result. NOT silent zeros.

5. No RMs available for the segment → same shape, with warning.

6. Customer has NO projection from ANY RM → unassigned,
   recorded in meta.unassignable_customers list.

7. RM capacity exhausted before all customers placed → leftover
   customers in meta.unassignable_customers with reason
   "all eligible RMs at capacity".

8. project_profitability_if_served_by returning None or negative
   PBT is a valid projection (not all assignments are profitable;
   negative PBT might still be the BEST available for a customer).
   The optimizer assigns based on RANKING, not absolute sign.

SPEC METHOD NAMES
-----------------
The spec mentions:
  optimize_rm_allocation(segment)            ← public entry
  project_profitability_if_served_by(c, rm)  ← injectable

Both implemented. project_profitability_if_served_by is injectable
via constructor — defaults to a simple model documented inline.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("a2z.allocation")
getcontext().prec = 28

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
ALLOCATION_FILE = DATA_DIR / "rm_allocations.json"

ZERO = Decimal("0")
PROVISIONAL_FTP_OFF_THRESHOLD = 0.5    # consistent with #23

# Default RM capacity if not supplied (book-of-30 is a common reference)
DEFAULT_RM_CAPACITY = 30


# ─────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────

class CustomerAllocationOptimizer:
    """Standard #24 — Customer-to-RM Allocation Intelligence.

    Stateless: each call returns a fresh allocation result.
    """

    def __init__(
        self,
        customers_in_segment_fn: Optional[Callable[[str], List[str]]] = None,
        rms_for_segment_fn:      Optional[Callable[[str], List[str]]] = None,
        rm_capacity_fn:          Optional[Callable[[str], int]] = None,
        current_allocation_fn:   Optional[Callable[[str], Optional[str]]] = None,
        projection_fn:           Optional[Callable[[str, str, str], Optional[dict]]] = None,
    ):
        """All collaborators injectable.

        customers_in_segment_fn(segment) → list[customer_id]
        rms_for_segment_fn(segment) → list[rm_code]
        rm_capacity_fn(rm_code) → int (max customers RM can serve;
            defaults to DEFAULT_RM_CAPACITY)
        current_allocation_fn(customer_id) → rm_code | None
            Current RM serving the customer (for marginal gain).
        projection_fn(customer_id, rm_code, period) → dict | None
            Returns:
              {"projected_pbt": float,
               "ftp_mode": "on"|"off"|"unknown",  # upstream PnL mode}
            None = no projection available (RM ineligible or data missing).
        """
        self._customers      = customers_in_segment_fn or (lambda s: [])
        self._rms            = rms_for_segment_fn      or (lambda s: [])
        self._capacity       = rm_capacity_fn          or (lambda r: DEFAULT_RM_CAPACITY)
        self._current_alloc  = current_allocation_fn   or (lambda c: None)
        self._projection     = projection_fn           or _default_projection

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    def optimize_rm_allocation(
        self, segment: str, period: str = "",
    ) -> Dict[str, Any]:
        """Run the optimization for a given segment.

        Returns:
            {
              "segment":              str,
              "period":               str,
              "assignments":          [{customer_id, rm_code, projected_pbt,
                                         current_rm, marginal_gain}, ...],
              "total_potential_gain": float,
              "total_projected_pbt":  float,
              "provisional":          bool,
              "data_quality_warning": str | None,
              "meta": {...}
            }

        Returns {} when segment is empty.
        """
        if not segment:
            return {}

        customers = self._customers(segment) or []
        rms       = self._rms(segment) or []

        # Defensive: empty segment / no RMs → still return shape
        if not customers:
            return self._empty_result(
                segment, period,
                "Segment has no customers — nothing to allocate",
            )
        if not rms:
            return self._empty_result(
                segment, period,
                "Segment has no eligible RMs — cannot allocate",
                customer_count=len(customers),
            )

        # Build the (customer, rm, projected_pbt, mode) matrix
        ftp_mode_counter: Counter = Counter()
        unassignable: List[dict] = []
        # pair list: (marginal_gain_d, projected_pbt_d, customer_id, rm_code, ftp_mode)
        pairs: List[Tuple[Decimal, Decimal, str, str, str]] = []

        # Pre-compute current PBTs for marginal-gain calculation
        current_pbts: Dict[str, Decimal] = {}
        current_rm_lookup: Dict[str, Optional[str]] = {}
        for c in customers:
            current_rm = self._current_alloc(c)
            current_rm_lookup[c] = current_rm
            current_pbt = ZERO
            if current_rm:
                proj = self._projection(c, current_rm, period)
                if proj and proj.get("projected_pbt") is not None:
                    try:
                        current_pbt = Decimal(str(proj["projected_pbt"]))
                    except Exception:
                        current_pbt = ZERO
            current_pbts[c] = current_pbt

        # Build pair matrix
        for c in customers:
            customer_has_any_projection = False
            for rm in rms:
                proj = self._projection(c, rm, period)
                if not proj:
                    continue
                ppbt = proj.get("projected_pbt")
                if ppbt is None:
                    continue
                customer_has_any_projection = True
                try:
                    ppbt_d = Decimal(str(ppbt))
                except Exception:
                    continue
                mode = proj.get("ftp_mode", "unknown")
                ftp_mode_counter[mode if mode in ("on", "off", "unknown") else "unknown"] += 1
                marginal_gain = ppbt_d - current_pbts[c]
                pairs.append((marginal_gain, ppbt_d, str(c), str(rm), mode))
            if not customer_has_any_projection:
                unassignable.append({
                    "customer_id": c,
                    "reason": "no projection from any eligible RM",
                })

        # Sort by marginal_gain DESC; ties broken by (projected_pbt DESC,
        # rm_code, customer_id) for determinism
        pairs.sort(key=lambda p: (-p[0], -p[1], p[3], p[2]))

        # Greedy assignment with capacity
        assigned_customers: set = set()
        rm_used: Counter = Counter()
        rm_capacities: Dict[str, int] = {rm: int(self._capacity(rm)) for rm in rms}
        assignments: List[dict] = []

        for marginal_gain, ppbt_d, c, rm, mode in pairs:
            if c in assigned_customers:
                continue
            if rm_used[rm] >= rm_capacities.get(rm, DEFAULT_RM_CAPACITY):
                continue
            assignments.append({
                "customer_id":   c,
                "rm_code":       rm,
                "projected_pbt": _money(ppbt_d),
                "current_rm":    current_rm_lookup.get(c),
                "marginal_gain": _money(marginal_gain),
                "upstream_ftp_mode": mode,
            })
            assigned_customers.add(c)
            rm_used[rm] += 1

        # Customers with projections but no assignment (capacity exhausted)
        for c in customers:
            if c in assigned_customers:
                continue
            already_in = any(u["customer_id"] == c for u in unassignable)
            if not already_in:
                unassignable.append({
                    "customer_id": c,
                    "reason": "all eligible RMs at capacity",
                })

        total_projected_pbt = sum(
            (Decimal(str(a["projected_pbt"])) for a in assignments), start=ZERO
        )
        total_marginal_gain = sum(
            (Decimal(str(a["marginal_gain"])) for a in assignments), start=ZERO
        )

        # Honesty inheritance — Mandatory Standard #11 portfolio level
        total_projections = sum(ftp_mode_counter.values()) or 1
        ftp_off_count = ftp_mode_counter.get("off", 0)
        provisional = (ftp_off_count / total_projections) > PROVISIONAL_FTP_OFF_THRESHOLD

        warning = None
        if ftp_off_count > 0:
            warning = (
                f"{ftp_off_count} of {total_projections} projections ran with "
                f"upstream ftp_mode='off' (per Mandatory Standard #11). "
                f"Re-run upstream PnLs with ftp_mode='on' before treating "
                f"the allocation result as final."
            )

        return {
            "segment":              segment,
            "period":               period,
            "assignments":          assignments,
            "total_potential_gain": _money(total_marginal_gain),
            "total_projected_pbt":  _money(total_projected_pbt),
            "provisional":          provisional,
            "data_quality_warning": warning,
            "meta": {
                "customers_in_segment":       len(customers),
                "rms_in_segment":             len(rms),
                "assignments_made":           len(assignments),
                "unassignable":               unassignable,
                "unassignable_count":         len(unassignable),
                "rm_utilization":             {rm: f"{rm_used[rm]}/{rm_capacities[rm]}"
                                                for rm in rms},
                "upstream_ftp_modes":         dict(ftp_mode_counter),
                "provisional_threshold_pct":  PROVISIONAL_FTP_OFF_THRESHOLD * 100,
                "algorithm":                  "greedy_capacity_constrained_v1",
                "algorithm_caveats": [
                    "Greedy with marginal-gain ordering. Hits optimal on "
                    "labelled small fixtures; for >100 customers consider "
                    "Hungarian / LP solver."
                ],
                "generated_at":               datetime.now(timezone.utc).isoformat(),
            },
        }

    def project_profitability_if_served_by(
        self, customer_id: str, rm_code: str, period: str = "",
    ) -> Optional[dict]:
        """Spec-named accessor that delegates to the injected projection_fn.

        Returns None when no projection is available.
        """
        if not customer_id or not rm_code:
            return None
        return self._projection(customer_id, rm_code, period)

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    def _empty_result(
        self, segment: str, period: str, warning: str,
        customer_count: int = 0,
    ) -> Dict[str, Any]:
        return {
            "segment":              segment,
            "period":               period,
            "assignments":          [],
            "total_potential_gain": 0.0,
            "total_projected_pbt":  0.0,
            "provisional":          False,
            "data_quality_warning": warning,
            "meta": {
                "customers_in_segment":   customer_count,
                "rms_in_segment":         0,
                "assignments_made":       0,
                "unassignable":           [],
                "unassignable_count":     0,
                "rm_utilization":         {},
                "upstream_ftp_modes":     {},
                "provisional_threshold_pct": PROVISIONAL_FTP_OFF_THRESHOLD * 100,
                "algorithm":              "greedy_capacity_constrained_v1",
                "generated_at":           datetime.now(timezone.utc).isoformat(),
            },
        }

    # ============================================================================
    # v7.4: L09 Branch performance → Resource allocation feedback loop (CONSUMER)
    # ============================================================================
    @classmethod
    def reallocation_signals_from_branch_performance(
        cls,
        branch_performance_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """L09 (CONSUMER) — derive RM reallocation signals from branch performance.

        Consumes per-branch performance metrics (cost-income ratio,
        return-on-avg-assets, quartile rank from peer benchmark) and
        produces reallocation directives:

            top_quartile      → expand capacity (replicate model)
            second_quartile   → maintain (no action needed)
            third_quartile    → coaching investment recommended
            bottom_quartile   → reallocation candidate (move RMs to higher-performing branches)

        Per Charter §7 Published Language pattern.

        Returns dict with:
            reallocation_directives: list[dict]
            consumed_payload_version: str
            pattern: str
            cited_invariants: list — none (resource allocation is bank policy)
        """
        if not isinstance(branch_performance_payload, dict):
            return {
                "status": "INVALID_PAYLOAD",
                "error": "branch_performance_payload must be a dict",
                "reallocation_directives": [],
            }

        branches = branch_performance_payload.get("branches") or \
                   branch_performance_payload.get("branch_metrics") or []

        directives = []
        for b in branches:
            if not isinstance(b, dict):
                continue

            branch_id = b.get("branch_id")
            quartile = b.get("quartile") or b.get("performance_quartile")
            cir = b.get("cost_income_ratio")
            roaa = b.get("return_on_avg_assets")

            if quartile == "TOP" or quartile == "Q1" or quartile == 1:
                action = "EXPAND_CAPACITY"
                rationale = "top quartile branch — model for replication; consider opening adjacent branch or moving high-potential RMs here"
                priority = "HIGH_OPPORTUNITY"
            elif quartile == "BOTTOM" or quartile == "Q4" or quartile == 4:
                action = "REALLOCATION_CANDIDATE"
                rationale = "bottom quartile branch — move 1-2 RMs to higher-performing branches; remaining staff get coaching"
                priority = "HIGH_RISK"
            elif quartile == "Q3" or quartile == 3:
                action = "COACHING_INVESTMENT"
                rationale = "third quartile branch — coaching + targeted training; review in 90 days"
                priority = "MEDIUM"
            else:
                # Q2 / mid-range / unknown
                action = "MAINTAIN"
                rationale = "second quartile or unclassified — no immediate action; monitor"
                priority = "LOW"

            directives.append({
                "branch_id": branch_id,
                "current_quartile": quartile,
                "action": action,
                "priority": priority,
                "rationale": rationale,
                "cost_income_ratio": cir,
                "return_on_avg_assets": roaa,
            })

        # Sort by priority for action queue
        priority_order = {"HIGH_RISK": 0, "HIGH_OPPORTUNITY": 1,
                          "MEDIUM": 2, "LOW": 3}
        directives.sort(key=lambda d: priority_order.get(d["priority"], 99))

        action_counts: Dict[str, int] = {}
        for d in directives:
            action_counts[d["action"]] = action_counts.get(d["action"], 0) + 1

        return {
            "reallocation_directives": directives,
            "summary": {
                "total_branches_analysed": len(directives),
                "by_action": action_counts,
            },
            "consumed_payload_version": "branch_performance.peer_benchmark_metrics+quartile_rank v1.0",
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": [],
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _money(d: Decimal) -> float:
    if not isinstance(d, Decimal):
        try:
            d = Decimal(str(d))
        except Exception:
            return 0.0
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _default_projection(customer_id: str, rm_code: str, period: str) -> Optional[dict]:
    """Default returns None — projections require explicit caller wiring.

    Production deployments inject a projection_fn that combines
    customer characteristics + RM skill profile to project PBT.
    """
    return None


# ─────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────

def save_allocation(segment: str, period: str, allocation: dict) -> bool:
    if not segment or not allocation:
        return False
    try:
        from utils.db import db
        existing = db.load_json(ALLOCATION_FILE, default={})
    except Exception:
        existing = {}
    if not isinstance(existing, dict):
        existing = {}
    by_segment = existing.setdefault(segment, {})
    if not isinstance(by_segment, dict):
        by_segment = {}
        existing[segment] = by_segment
    by_segment[period or "default"] = allocation
    try:
        from utils.db import db
        db.save_json(ALLOCATION_FILE, existing)
        return True
    except Exception as e:
        logger.error("allocation: could not save: %s", e)
        return False


def get_allocation(segment: str, period: str = "") -> Optional[dict]:
    try:
        from utils.db import db
        existing = db.load_json(ALLOCATION_FILE, default={})
    except Exception:
        return None
    if not isinstance(existing, dict):
        return None
    by_seg = existing.get(segment, {})
    if not isinstance(by_seg, dict):
        return None
    return by_seg.get(period or "default")


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.allocation_optimizer self-test")

    # ── Build a small known-optimal scenario ──────────────────────────
    # 3 customers (C1 C2 C3), 2 RMs (RM1 RM2), capacity 2 each.
    # Projections:
    #   C1: RM1=100, RM2=80
    #   C2: RM1=90,  RM2=70
    #   C3: RM1=60,  RM2=50
    # Optimal (capacity=2 each, all customers placed):
    #   C1→RM1 (100), C2→RM1 (90), C3→RM2 (50). Wait — RM1 capacity is 2, that's full.
    #   So C3 must go to RM2: total = 100 + 90 + 50 = 240.
    # Alternative (C2→RM2): 100 + 70 + 60 = 230.
    # So optimal = 240.
    projections = {
        ("C1", "RM1"): {"projected_pbt": 100, "ftp_mode": "on"},
        ("C1", "RM2"): {"projected_pbt": 80,  "ftp_mode": "on"},
        ("C2", "RM1"): {"projected_pbt": 90,  "ftp_mode": "on"},
        ("C2", "RM2"): {"projected_pbt": 70,  "ftp_mode": "on"},
        ("C3", "RM1"): {"projected_pbt": 60,  "ftp_mode": "on"},
        ("C3", "RM2"): {"projected_pbt": 50,  "ftp_mode": "on"},
    }
    eng = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1", "C2", "C3"],
        rms_for_segment_fn=lambda s: ["RM1", "RM2"],
        rm_capacity_fn=lambda r: 2,
        current_allocation_fn=lambda c: None,
        projection_fn=lambda c, r, p: projections.get((c, r)),
    )
    r = eng.optimize_rm_allocation("Mass")
    assert r["meta"]["assignments_made"] == 3, f"got {r['meta']['assignments_made']}"
    assert r["total_projected_pbt"] == 240.0, f"got {r['total_projected_pbt']}"
    assert r["provisional"] is False
    assert r["data_quality_warning"] is None
    print(f"  ✅ greedy hits optimal: total_projected_pbt={r['total_projected_pbt']}")

    # ── Capacity constraint forces unassignable ───────────────────────
    eng_tight = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1", "C2", "C3"],
        rms_for_segment_fn=lambda s: ["RM1"],
        rm_capacity_fn=lambda r: 2,
        projection_fn=lambda c, r, p: projections.get((c, r)),
    )
    r2 = eng_tight.optimize_rm_allocation("Mass")
    assert r2["meta"]["assignments_made"] == 2
    assert r2["meta"]["unassignable_count"] == 1
    print(f"  ✅ capacity constraint: 2 assigned, 1 unassignable")

    # ── Empty segment ─────────────────────────────────────────────────
    eng_empty = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: [],
        rms_for_segment_fn=lambda s: ["RM1"],
    )
    r3 = eng_empty.optimize_rm_allocation("EmptySeg")
    assert r3["assignments"] == []
    assert "no customers" in r3["data_quality_warning"]
    print(f"  ✅ empty segment: warning='{r3['data_quality_warning'][:40]}...'")

    # ── No RMs ────────────────────────────────────────────────────────
    eng_no_rms = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1"],
        rms_for_segment_fn=lambda s: [],
    )
    r4 = eng_no_rms.optimize_rm_allocation("NoRMs")
    assert r4["assignments"] == []
    assert "no eligible RMs" in r4["data_quality_warning"]
    print(f"  ✅ no RMs: warning surfaces")

    # ── Empty segment string → {} ─────────────────────────────────────
    assert eng.optimize_rm_allocation("") == {}
    print(f"  ✅ empty segment string → {{}}")

    # ── Honesty rule: FTP-off triggers warning ─────────────────────────
    proj_mixed = {
        ("C1", "RM1"): {"projected_pbt": 100, "ftp_mode": "on"},
        ("C2", "RM1"): {"projected_pbt": 90,  "ftp_mode": "off"},
    }
    eng_mixed = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1", "C2"],
        rms_for_segment_fn=lambda s: ["RM1"],
        rm_capacity_fn=lambda r: 5,
        projection_fn=lambda c, r, p: proj_mixed.get((c, r)),
    )
    r5 = eng_mixed.optimize_rm_allocation("Mixed")
    assert r5["data_quality_warning"] is not None
    assert "Mandatory Standard #11" in r5["data_quality_warning"]
    # 1 of 2 = 50%, NOT > 50%, so not provisional
    assert r5["provisional"] is False
    print(f"  ✅ FTP-off warning surfaces; provisional={r5['provisional']}")

    # ── Provisional triggers when >50% off ────────────────────────────
    proj_mostly_off = {
        ("C1", "RM1"): {"projected_pbt": 100, "ftp_mode": "off"},
        ("C2", "RM1"): {"projected_pbt": 90,  "ftp_mode": "off"},
        ("C3", "RM1"): {"projected_pbt": 80,  "ftp_mode": "on"},
    }
    eng_off = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1", "C2", "C3"],
        rms_for_segment_fn=lambda s: ["RM1"],
        rm_capacity_fn=lambda r: 5,
        projection_fn=lambda c, r, p: proj_mostly_off.get((c, r)),
    )
    r6 = eng_off.optimize_rm_allocation("MostlyOff")
    # 2/3 = 66.7% > 50%
    assert r6["provisional"] is True
    print(f"  ✅ provisional flag: 2/3 FTP-off → provisional=True")

    # ── Marginal gain from current allocation ──────────────────────────
    # C1 currently with RM2 (80), best is RM1 (100) → marginal_gain = 20
    eng_curr = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1"],
        rms_for_segment_fn=lambda s: ["RM1", "RM2"],
        rm_capacity_fn=lambda r: 5,
        current_allocation_fn=lambda c: "RM2" if c == "C1" else None,
        projection_fn=lambda c, r, p: projections.get((c, r)),
    )
    r7 = eng_curr.optimize_rm_allocation("Mass")
    assignment = r7["assignments"][0]
    assert assignment["rm_code"] == "RM1"
    assert assignment["projected_pbt"] == 100.0
    assert assignment["current_rm"] == "RM2"
    assert assignment["marginal_gain"] == 20.0
    print(f"  ✅ marginal gain: C1 RM2→RM1 gain={assignment['marginal_gain']}")

    # ── Customer with no eligible RM → unassignable ───────────────────
    eng_iso = CustomerAllocationOptimizer(
        customers_in_segment_fn=lambda s: ["C1", "C_ISOLATED"],
        rms_for_segment_fn=lambda s: ["RM1"],
        rm_capacity_fn=lambda r: 5,
        projection_fn=lambda c, r, p: (
            {"projected_pbt": 100, "ftp_mode": "on"} if c == "C1" else None
        ),
    )
    r8 = eng_iso.optimize_rm_allocation("Mass")
    assert r8["meta"]["unassignable_count"] == 1
    assert r8["meta"]["unassignable"][0]["customer_id"] == "C_ISOLATED"
    print(f"  ✅ unassignable: customer with no eligible RM tracked")

    # ── Determinism ───────────────────────────────────────────────────
    a = eng.optimize_rm_allocation("Mass")
    b = eng.optimize_rm_allocation("Mass")
    def strip_ts(d):
        if isinstance(d, dict):
            return {k: strip_ts(v) for k, v in d.items() if k != "generated_at"}
        if isinstance(d, list):
            return [strip_ts(x) for x in d]
        return d
    assert strip_ts(a) == strip_ts(b)
    print(f"  ✅ determinism: same inputs → same output")

    print("\n  ALL TESTS PASSED")
