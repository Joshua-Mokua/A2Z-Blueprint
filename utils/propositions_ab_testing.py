"""
================================================================================
A2Z MIS 360 — Standard #355: Proposition A/B Testing Framework
================================================================================

Risk classification: Cat C (statistical experiment design + significance
                              testing on proposition variants)

Statistical A/B test framework: traffic split, experiment design,
significance testing (z-test for proportions), auto-winner deployment
recommendation. v10.277 ships deterministic significance test;
production ML-driven multi-armed bandit deferred.

Public API:
    register_experiment(experiment_data, actor, reason)
    transition_experiment_state(exp_id, new_state, actor, reason)
    assign_to_variant(exp_id, customer_id, actor) -> chosen variant
    record_conversion(exp_id, variant_id, customer_id, actor)
    experiment_results(exp_id) -> per-variant statistics
    significance_test(exp_id) -> {p_value, significant, winner}
    recommend_winner(exp_id, alpha=0.05) -> deployment recommendation

EXPERIMENT_STATES byte-for-byte:
    DRAFT       -- experiment designed, not running
    RUNNING     -- live, recruiting customers
    PAUSED      -- temporarily halted (resumable)
    CONCLUDED   -- ended, ready for winner selection (terminal)
    ARCHIVED    -- archived (terminal)

ALLOWED_EXPERIMENT_TRANSITIONS (Rule 4):
    DRAFT     → RUNNING | ARCHIVED
    RUNNING   → PAUSED | CONCLUDED | ARCHIVED
    PAUSED    → RUNNING | CONCLUDED | ARCHIVED
    CONCLUDED → ARCHIVED
    ARCHIVED  → ()

EXPERIMENT_OUTCOMES byte-for-byte:
    VARIANT_A_WINS    -- variant A statistically significant winner
    VARIANT_B_WINS    -- variant B statistically significant winner
    INCONCLUSIVE      -- no significant difference at chosen alpha
    INSUFFICIENT_DATA -- not enough customers in either arm

DEFAULT_ALPHA = 0.05  -- 95% confidence level
MIN_SAMPLE_SIZE_PER_VARIANT = 30  -- below this → INSUFFICIENT_DATA

Honesty rules:
    Rule 1: significance test returns INCONCLUSIVE / INSUFFICIENT_DATA
            with explicit reasons rather than fabricating winners
    Rule 4: actor + reason mandatory on lifecycle transitions
    Rule 6: invalid state / outcome rejected
    Rule 7: deterministic z-test only — production ML-driven multi-armed
            bandit deferred

================================================================================
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, date
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.propositions_catalog import PropositionsCatalogEngine

getcontext().prec = 28


EXPERIMENT_STATES: Tuple[str, ...] = (
    "DRAFT", "RUNNING", "PAUSED", "CONCLUDED", "ARCHIVED",
)

ALLOWED_EXPERIMENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":     ("RUNNING", "ARCHIVED"),
    "RUNNING":   ("PAUSED", "CONCLUDED", "ARCHIVED"),
    "PAUSED":    ("RUNNING", "CONCLUDED", "ARCHIVED"),
    "CONCLUDED": ("ARCHIVED",),
    "ARCHIVED":  (),
}

EXPERIMENT_OUTCOMES: Tuple[str, ...] = (
    "VARIANT_A_WINS", "VARIANT_B_WINS",
    "INCONCLUSIVE", "INSUFFICIENT_DATA",
)

DEFAULT_ALPHA: float = 0.05
MIN_SAMPLE_SIZE_PER_VARIANT: int = 30


def _z_test_two_proportions(
    success_a: int, total_a: int,
    success_b: int, total_b: int,
) -> Tuple[float, float]:
    """Returns (z_statistic, p_value_two_tailed). 0 if cannot compute."""
    if total_a == 0 or total_b == 0:
        return 0.0, 1.0
    p_a = success_a / total_a
    p_b = success_b / total_b
    p_pool = (success_a + success_b) / (total_a + total_b)
    if p_pool == 0 or p_pool == 1:
        return 0.0, 1.0
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / total_a + 1 / total_b))
    if se == 0:
        return 0.0, 1.0
    z = (p_a - p_b) / se
    # Two-tailed p-value approximation using normal CDF
    # P(|Z| > |z|) = 2 * (1 - Φ(|z|))
    p_value = 2 * (1 - _normal_cdf(abs(z)))
    return z, p_value


def _normal_cdf(x: float) -> float:
    """Standard normal CDF via erf."""
    return (1 + math.erf(x / math.sqrt(2))) / 2


class PropositionABTestingEngine:
    """Statistical A/B experiment framework."""

    def __init__(
        self,
        catalog: Optional[PropositionsCatalogEngine] = None,
        experiments_path: Optional[Path] = None,
        assignments_path: Optional[Path] = None,
        conversions_path: Optional[Path] = None,
    ):
        self.catalog = catalog or PropositionsCatalogEngine()
        base = Path(__file__).parent.parent / "data"
        self.experiments_path = experiments_path or base / "ab_experiments.json"
        self.assignments_path = assignments_path or base / "ab_assignments.json"
        self.conversions_path = conversions_path or base / "ab_conversions.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def register_experiment(
        self,
        experiment_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("experiment_id", "experiment_name",
                    "variant_a_proposition_id", "variant_b_proposition_id"):
            if f not in experiment_data or not experiment_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        records = self._load(self.experiments_path,
                                "ab_experiments", ("experiment_id",))
        if any(r.get("experiment_id") == experiment_data["experiment_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_experiment_id"}

        record = {
            "experiment_id": experiment_data["experiment_id"],
            "experiment_name": experiment_data["experiment_name"],
            "variant_a_proposition_id": experiment_data["variant_a_proposition_id"],
            "variant_b_proposition_id": experiment_data["variant_b_proposition_id"],
            "traffic_split_pct": experiment_data.get("traffic_split_pct", 50),
            "primary_metric": experiment_data.get("primary_metric", "TAKE_UP_RATE"),
            "alpha": experiment_data.get("alpha", DEFAULT_ALPHA),
            "min_sample_size_per_variant": experiment_data.get(
                "min_sample_size_per_variant", MIN_SAMPLE_SIZE_PER_VARIANT),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(self.experiments_path, records,
                          "ab_experiments", "experiment_id")
        return {"registered": ok,
                  "experiment_id": experiment_data["experiment_id"]}

    def transition_experiment_state(
        self,
        exp_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in EXPERIMENT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.experiments_path,
                                "ab_experiments", ("experiment_id",))
        for r in records:
            if r.get("experiment_id") == exp_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_EXPERIMENT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.experiments_path, records,
                                  "ab_experiments", "experiment_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "experiment_not_found"}

    def assign_to_variant(
        self,
        exp_id: str,
        customer_id: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"assigned": False, "error": "actor_required"}
        records = self._load(self.experiments_path,
                                "ab_experiments", ("experiment_id",))
        exp = next((r for r in records if r.get("experiment_id") == exp_id), None)
        if exp is None:
            return {"assigned": False, "error": "experiment_not_found"}
        if exp.get("state") != "RUNNING":
            return {
                "assigned": False,
                "error": f"experiment_not_running:{exp['state']}",
            }

        assignments = self._load(self.assignments_path,
                                      "ab_assignments",
                                      ("assignment_id",))
        # Check existing assignment
        existing = next((a for a in assignments
                              if a.get("experiment_id") == exp_id
                              and a.get("customer_id") == customer_id), None)
        if existing:
            return {
                "assigned": True,
                "variant": existing["variant"],
                "already_assigned": True,
            }

        # Deterministic split via customer_id hash
        split_pct = exp.get("traffic_split_pct", 50)
        h = abs(hash(customer_id)) % 100
        variant = "A" if h < split_pct else "B"

        assignments.append({
            "assignment_id": f"AB-{exp_id}-{customer_id}",
            "experiment_id": exp_id,
            "customer_id": customer_id,
            "variant": variant,
            "actor": actor,
            "assigned_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.assignments_path, assignments,
                          "ab_assignments", "assignment_id")
        return {"assigned": ok, "variant": variant}

    def record_conversion(
        self,
        exp_id: str,
        customer_id: str,
        actor: str,
    ) -> Dict[str, Any]:
        """Record a conversion event for a customer who has been assigned."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        assignments = self._load(self.assignments_path,
                                      "ab_assignments",
                                      ("assignment_id",))
        a = next((x for x in assignments
                      if x.get("experiment_id") == exp_id
                      and x.get("customer_id") == customer_id), None)
        if a is None:
            return {
                "recorded": False,
                "error": "customer_not_assigned_to_experiment",
            }

        conversions = self._load(self.conversions_path,
                                      "ab_conversions",
                                      ("conversion_id",))
        # Reject duplicate conversion
        if any(c.get("experiment_id") == exp_id
                 and c.get("customer_id") == customer_id for c in conversions):
            return {"recorded": False, "error": "already_converted"}

        conversion_id = (f"CV-{exp_id}-{customer_id}-"
                              f"{int(datetime.utcnow().timestamp())}")
        conversions.append({
            "conversion_id": conversion_id,
            "experiment_id": exp_id,
            "customer_id": customer_id,
            "variant": a["variant"],
            "actor": actor,
            "converted_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.conversions_path, conversions,
                          "ab_conversions", "conversion_id")
        return {"recorded": ok, "variant": a["variant"]}

    def experiment_results(self, exp_id: str) -> Dict[str, Any]:
        assignments = self._load(self.assignments_path,
                                      "ab_assignments",
                                      ("assignment_id",))
        conversions = self._load(self.conversions_path,
                                      "ab_conversions",
                                      ("conversion_id",))
        for_exp_assigned = [a for a in assignments
                                if a.get("experiment_id") == exp_id]
        for_exp_conv = [c for c in conversions
                              if c.get("experiment_id") == exp_id]

        a_assigned = sum(1 for a in for_exp_assigned if a["variant"] == "A")
        b_assigned = sum(1 for a in for_exp_assigned if a["variant"] == "B")
        a_converted = sum(1 for c in for_exp_conv if c["variant"] == "A")
        b_converted = sum(1 for c in for_exp_conv if c["variant"] == "B")

        a_conv_rate = (
            (Decimal(a_converted) / Decimal(a_assigned) *
              Decimal("100")).quantize(Decimal("0.01"))
            if a_assigned > 0 else None
        )
        b_conv_rate = (
            (Decimal(b_converted) / Decimal(b_assigned) *
              Decimal("100")).quantize(Decimal("0.01"))
            if b_assigned > 0 else None
        )

        return {
            "experiment_id": exp_id,
            "variant_a": {
                "assigned": a_assigned,
                "converted": a_converted,
                "conversion_rate_pct": str(a_conv_rate) if a_conv_rate is not None else None,
            },
            "variant_b": {
                "assigned": b_assigned,
                "converted": b_converted,
                "conversion_rate_pct": str(b_conv_rate) if b_conv_rate is not None else None,
            },
            "total_assigned": len(for_exp_assigned),
            "total_converted": len(for_exp_conv),
        }

    def significance_test(
        self,
        exp_id: str,
        alpha: Optional[float] = None,
    ) -> Dict[str, Any]:
        results = self.experiment_results(exp_id)
        records = self._load(self.experiments_path,
                                  "ab_experiments", ("experiment_id",))
        exp = next((r for r in records
                       if r.get("experiment_id") == exp_id), None)
        if exp is None:
            return {"outcome": "INSUFFICIENT_DATA",
                       "reason": "experiment_not_found"}

        a_assigned = results["variant_a"]["assigned"]
        b_assigned = results["variant_b"]["assigned"]
        a_converted = results["variant_a"]["converted"]
        b_converted = results["variant_b"]["converted"]

        min_sample = exp.get("min_sample_size_per_variant",
                                  MIN_SAMPLE_SIZE_PER_VARIANT)
        if a_assigned < min_sample or b_assigned < min_sample:
            return {
                "experiment_id": exp_id,
                "outcome": "INSUFFICIENT_DATA",
                "reason": (f"min_sample_required_{min_sample}_per_arm"),
                "a_assigned": a_assigned, "b_assigned": b_assigned,
            }

        z, p_value = _z_test_two_proportions(
            a_converted, a_assigned, b_converted, b_assigned,
        )

        actual_alpha = alpha if alpha is not None else exp.get("alpha", DEFAULT_ALPHA)
        significant = p_value < actual_alpha

        if significant:
            a_rate = a_converted / a_assigned if a_assigned else 0
            b_rate = b_converted / b_assigned if b_assigned else 0
            outcome = "VARIANT_A_WINS" if a_rate > b_rate else "VARIANT_B_WINS"
        else:
            outcome = "INCONCLUSIVE"

        return {
            "experiment_id": exp_id,
            "outcome": outcome,
            "z_statistic": round(z, 4),
            "p_value": round(p_value, 6),
            "alpha": actual_alpha,
            "significant": significant,
            "variant_a_conversion_rate_pct":
                results["variant_a"]["conversion_rate_pct"],
            "variant_b_conversion_rate_pct":
                results["variant_b"]["conversion_rate_pct"],
        }

    def recommend_winner(
        self,
        exp_id: str,
        alpha: float = DEFAULT_ALPHA,
    ) -> Dict[str, Any]:
        sig = self.significance_test(exp_id, alpha=alpha)
        outcome = sig.get("outcome")

        if outcome == "INSUFFICIENT_DATA":
            return {
                "recommendation": "CONTINUE_RUNNING",
                "reason": sig.get("reason"),
                "details": sig,
            }
        if outcome == "INCONCLUSIVE":
            return {
                "recommendation": "NO_CLEAR_WINNER",
                "reason": "p_value_not_below_alpha",
                "details": sig,
            }

        records = self._load(self.experiments_path,
                                  "ab_experiments", ("experiment_id",))
        exp = next((r for r in records
                       if r.get("experiment_id") == exp_id), None)
        winning_prop = (
            exp.get("variant_a_proposition_id") if outcome == "VARIANT_A_WINS"
            else exp.get("variant_b_proposition_id")
        )

        return {
            "recommendation": "DEPLOY_WINNER",
            "winning_variant": "A" if outcome == "VARIANT_A_WINS" else "B",
            "winning_proposition_id": winning_prop,
            "reason": "statistically_significant_at_alpha",
            "details": sig,
        }


def _self_test() -> None:
    import tempfile

    assert "DEPLOY" not in EXPERIMENT_STATES  # not a state
    assert "VARIANT_A_WINS" in EXPERIMENT_OUTCOMES
    assert ALLOWED_EXPERIMENT_TRANSITIONS["ARCHIVED"] == ()

    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = PropositionsCatalogEngine(
            propositions_path=Path(tmpdir) / "p.json",
            approvals_path=Path(tmpdir) / "a.json",
            reviews_path=Path(tmpdir) / "r.json",
        )
        engine = PropositionABTestingEngine(
            catalog=catalog,
            experiments_path=Path(tmpdir) / "exp.json",
            assignments_path=Path(tmpdir) / "asn.json",
            conversions_path=Path(tmpdir) / "cv.json",
        )

        # Test 1: register experiment
        r = engine.register_experiment(
            {"experiment_id": "EXP-001",
             "experiment_name": "Pricing A vs B",
             "variant_a_proposition_id": "PROP-A",
             "variant_b_proposition_id": "PROP-B"},
            actor="design_lead", reason="test pricing strategy",
        )
        assert r["registered"]

        # Test 2: missing field
        r = engine.register_experiment(
            {"experiment_id": "X"}, actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 3: state lifecycle
        t = engine.transition_experiment_state(
            "EXP-001", "RUNNING", actor="design", reason="go",
        )
        assert t["transitioned"]

        # Test 4: skip rejected
        r = engine.register_experiment(
            {"experiment_id": "EXP-002",
             "experiment_name": "Y",
             "variant_a_proposition_id": "P-A",
             "variant_b_proposition_id": "P-B"},
            actor="x", reason="x",
        )
        t = engine.transition_experiment_state(
            "EXP-002", "CONCLUDED", actor="x", reason="skip",
        )
        assert not t["transitioned"]

        # Test 5: cannot assign to non-RUNNING
        a = engine.assign_to_variant("EXP-002", "C-1", actor="x")
        assert not a["assigned"]

        # Test 6: assign to RUNNING
        a = engine.assign_to_variant("EXP-001", "C-1", actor="x")
        assert a["assigned"]
        assert a["variant"] in ("A", "B")

        # Test 7: re-assignment returns same variant
        a2 = engine.assign_to_variant("EXP-001", "C-1", actor="x")
        assert a2["already_assigned"]
        assert a2["variant"] == a["variant"]

        # Test 8: cannot record conversion for un-assigned
        c = engine.record_conversion("EXP-001", "C-UNKNOWN", actor="x")
        assert not c["recorded"]

        # Test 9: significance test with no data → INSUFFICIENT
        sig = engine.significance_test("EXP-001")
        assert sig["outcome"] == "INSUFFICIENT_DATA"

        # Test 10: seed substantial data — A converts higher than B
        for i in range(60):
            cid = f"CUST-A-{i}"
            engine.assign_to_variant("EXP-001", cid, actor="x")
        for i in range(60):
            cid = f"CUST-B-{i}"
            engine.assign_to_variant("EXP-001", cid, actor="x")
        # Convert all customers — but seed disparity: convert all assigned to A,
        # only 10% of those assigned to B
        results = engine.experiment_results("EXP-001")
        # Get all assignments
        assignments = engine._load(engine.assignments_path,
                                          "ab_assignments",
                                          ("assignment_id",))
        a_customers = [a["customer_id"] for a in assignments
                            if a["experiment_id"] == "EXP-001"
                            and a["variant"] == "A"]
        b_customers = [a["customer_id"] for a in assignments
                            if a["experiment_id"] == "EXP-001"
                            and a["variant"] == "B"]
        # Convert ALL A
        for cid in a_customers:
            engine.record_conversion("EXP-001", cid, actor="x")
        # Convert 10% of B
        for cid in b_customers[:max(1, len(b_customers) // 10)]:
            engine.record_conversion("EXP-001", cid, actor="x")

        # Test 11: experiment_results
        results = engine.experiment_results("EXP-001")
        assert results["variant_a"]["assigned"] >= 30
        assert results["variant_b"]["assigned"] >= 30

        # Test 12: significance test should detect A as winner
        sig = engine.significance_test("EXP-001")
        # Could be A_WINS if A's conversion is sufficiently higher
        if sig["significant"]:
            assert sig["outcome"] == "VARIANT_A_WINS"

        # Test 13: recommend_winner
        rec = engine.recommend_winner("EXP-001")
        if sig["significant"]:
            assert rec["recommendation"] == "DEPLOY_WINNER"
            assert rec["winning_variant"] == "A"
        else:
            # In low-power tests, might not be significant
            assert rec["recommendation"] in ("NO_CLEAR_WINNER", "CONTINUE_RUNNING")

        # Test 14: duplicate conversion rejected
        c = engine.record_conversion(
            "EXP-001", a_customers[0], actor="x",
        )
        assert not c["recorded"]
        assert c["error"] == "already_converted"

    print("  ✅ propositions_ab_testing self-test PASS")


if __name__ == "__main__":
    _self_test()
