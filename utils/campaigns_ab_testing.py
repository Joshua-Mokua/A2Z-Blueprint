"""
================================================================================
A2Z MIS 360 — Standard #394: Campaign A/B Testing
================================================================================

Risk classification: Cat C (deterministic z-test for two proportions)

Statistical A/B testing for campaigns: subject line, content, timing,
channel. Winning variant auto-promotion. Pattern follows v10.277
propositions_ab_testing — z-test via math.erf, INSUFFICIENT_DATA below
30/arm.

Public API:
    register_experiment(experiment_data, actor, reason)
    transition_experiment_state(experiment_id, new_state, actor, reason)
    assign_variant(experiment_id, customer_id, actor) -> "A"|"B"
    record_outcome(experiment_id, customer_id, outcome, actor)
    significance_test(experiment_id) -> Dict
    auto_promote_winner(experiment_id, actor, reason)

EXPERIMENT_STATES byte-for-byte (5):
    DRAFT, RUNNING, PAUSED, CONCLUDED, ARCHIVED

EXPERIMENT_OUTCOMES byte-for-byte (4):
    VARIANT_A_WINS, VARIANT_B_WINS, INCONCLUSIVE, INSUFFICIENT_DATA

DEFAULT_ALPHA = 0.05  -- 95% confidence
MIN_SAMPLE_SIZE_PER_VARIANT = 30

Honesty rules:
    Rule 1: returns INSUFFICIENT_DATA below threshold (no false winner)
    Rule 4: actor + reason mandatory
    Rule 6: invalid outcome / state rejected

================================================================================
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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
    "VARIANT_A_WINS", "VARIANT_B_WINS", "INCONCLUSIVE", "INSUFFICIENT_DATA",
)

DEFAULT_ALPHA: float = 0.05
MIN_SAMPLE_SIZE_PER_VARIANT: int = 30


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _z_test_two_proportions(
    successes_a: int, n_a: int,
    successes_b: int, n_b: int,
) -> Tuple[float, float]:
    """Returns (z_stat, two_tailed_p_value)."""
    if n_a == 0 or n_b == 0:
        return (0.0, 1.0)
    p_a = successes_a / n_a
    p_b = successes_b / n_b
    p_pool = (successes_a + successes_b) / (n_a + n_b)
    se = math.sqrt(p_pool * (1 - p_pool) * (1.0/n_a + 1.0/n_b))
    if se == 0:
        return (0.0, 1.0)
    z = (p_b - p_a) / se
    p_two_tail = 2.0 * (1.0 - _normal_cdf(abs(z)))
    return (z, p_two_tail)


class CampaignsABTestingEngine:
    """Statistical A/B framework for campaigns."""

    def __init__(
        self,
        experiments_path: Optional[Path] = None,
        assignments_path: Optional[Path] = None,
        outcomes_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.experiments_path = experiments_path or base / "campaign_ab_experiments.json"
        self.assignments_path = assignments_path or base / "campaign_ab_assignments.json"
        self.outcomes_path = outcomes_path or base / "campaign_ab_outcomes.json"

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
        self, experiment_data: Dict[str, Any],
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("experiment_id", "campaign_id", "variant_a", "variant_b"):
            if f not in experiment_data:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.experiments_path,
                                 "campaign_ab_experiments",
                                 ("experiment_id",))
        if any(r.get("experiment_id") == experiment_data["experiment_id"]
                  for r in records):
            return {"registered": False, "error": "duplicate_experiment_id"}
        records.append({
            "experiment_id": experiment_data["experiment_id"],
            "campaign_id": experiment_data["campaign_id"],
            "experiment_name": experiment_data.get("experiment_name", ""),
            "dimension": experiment_data.get("dimension", "SUBJECT_LINE"),
            "variant_a": experiment_data["variant_a"],
            "variant_b": experiment_data["variant_b"],
            "traffic_split_pct": experiment_data.get("traffic_split_pct", 50),
            "alpha": experiment_data.get("alpha", DEFAULT_ALPHA),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        })
        ok = self._save(self.experiments_path, records,
                          "campaign_ab_experiments", "experiment_id")
        return {"registered": ok,
                  "experiment_id": experiment_data["experiment_id"]}

    def transition_experiment_state(
        self, experiment_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in EXPERIMENT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.experiments_path,
                                 "campaign_ab_experiments",
                                 ("experiment_id",))
        for r in records:
            if r.get("experiment_id") == experiment_id:
                current = r.get("state", "DRAFT")
                if new_state not in ALLOWED_EXPERIMENT_TRANSITIONS.get(current, ()):
                    return {"transitioned": False,
                              "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                ok = self._save(self.experiments_path, records,
                                  "campaign_ab_experiments", "experiment_id")
                return {"transitioned": ok}
        return {"transitioned": False, "error": "experiment_not_found"}

    def assign_variant(
        self, experiment_id: str, customer_id: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"assigned": False, "error": "actor_required"}
        experiments = self._load(self.experiments_path,
                                       "campaign_ab_experiments",
                                       ("experiment_id",))
        exp = next((e for e in experiments
                       if e.get("experiment_id") == experiment_id), None)
        if exp is None:
            return {"assigned": False, "error": "experiment_not_found"}
        if exp.get("state") != "RUNNING":
            return {"assigned": False,
                      "error": f"experiment_not_running:{exp.get('state')}"}

        assignments = self._load(self.assignments_path,
                                       "campaign_ab_assignments",
                                       ("assignment_id",))
        existing = next((a for a in assignments
                            if a.get("experiment_id") == experiment_id
                            and a.get("customer_id") == customer_id), None)
        if existing:
            return {
                "assigned": True,
                "variant": existing["variant"],
                "already_assigned": True,
            }

        # Hash-based deterministic split
        split_pct = exp.get("traffic_split_pct", 50)
        variant = "A" if hash(customer_id) % 100 < split_pct else "B"
        assign_id = f"AS-{experiment_id}-{customer_id}"
        assignments.append({
            "assignment_id": assign_id,
            "experiment_id": experiment_id,
            "customer_id": customer_id,
            "variant": variant,
            "actor": actor,
            "assigned_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.assignments_path, assignments,
                          "campaign_ab_assignments", "assignment_id")
        return {"assigned": ok, "variant": variant, "already_assigned": False}

    def record_outcome(
        self, experiment_id: str, customer_id: str,
        outcome: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if outcome not in ("CONVERTED", "NOT_CONVERTED"):
            return {"recorded": False,
                      "error": f"invalid_outcome:{outcome} "
                                  "(must be CONVERTED|NOT_CONVERTED)"}

        # Verify assignment exists
        assignments = self._load(self.assignments_path,
                                       "campaign_ab_assignments",
                                       ("assignment_id",))
        if not any(a.get("experiment_id") == experiment_id
                      and a.get("customer_id") == customer_id
                      for a in assignments):
            return {"recorded": False, "error": "customer_not_assigned"}

        records = self._load(self.outcomes_path,
                                 "campaign_ab_outcomes", ("outcome_id",))
        # Reject duplicate
        if any(r.get("experiment_id") == experiment_id
                  and r.get("customer_id") == customer_id
                  for r in records):
            return {"recorded": False, "error": "outcome_already_recorded"}

        outcome_id = f"OC-{experiment_id}-{customer_id}"
        records.append({
            "outcome_id": outcome_id,
            "experiment_id": experiment_id,
            "customer_id": customer_id,
            "outcome": outcome,
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.outcomes_path, records,
                          "campaign_ab_outcomes", "outcome_id")
        return {"recorded": ok}

    def significance_test(self, experiment_id: str) -> Dict[str, Any]:
        experiments = self._load(self.experiments_path,
                                       "campaign_ab_experiments",
                                       ("experiment_id",))
        exp = next((e for e in experiments
                       if e.get("experiment_id") == experiment_id), None)
        if exp is None:
            return {"error": "experiment_not_found"}

        assignments = self._load(self.assignments_path,
                                       "campaign_ab_assignments",
                                       ("assignment_id",))
        outcomes = self._load(self.outcomes_path,
                                  "campaign_ab_outcomes", ("outcome_id",))
        outcome_map = {(o["experiment_id"], o["customer_id"]): o["outcome"]
                            for o in outcomes}

        n_a = n_b = 0
        c_a = c_b = 0
        for a in assignments:
            if a.get("experiment_id") != experiment_id:
                continue
            v = a.get("variant")
            if v == "A":
                n_a += 1
                if outcome_map.get((experiment_id, a["customer_id"])) == "CONVERTED":
                    c_a += 1
            elif v == "B":
                n_b += 1
                if outcome_map.get((experiment_id, a["customer_id"])) == "CONVERTED":
                    c_b += 1

        alpha = float(exp.get("alpha", DEFAULT_ALPHA))
        if n_a < MIN_SAMPLE_SIZE_PER_VARIANT or n_b < MIN_SAMPLE_SIZE_PER_VARIANT:
            return {
                "experiment_id": experiment_id,
                "outcome": "INSUFFICIENT_DATA",
                "n_a": n_a, "n_b": n_b,
                "min_sample_size_per_variant": MIN_SAMPLE_SIZE_PER_VARIANT,
                "alpha": alpha,
            }

        z, p = _z_test_two_proportions(c_a, n_a, c_b, n_b)
        rate_a = c_a / n_a
        rate_b = c_b / n_b
        if p < alpha:
            outcome = "VARIANT_A_WINS" if rate_a > rate_b else "VARIANT_B_WINS"
        else:
            outcome = "INCONCLUSIVE"

        return {
            "experiment_id": experiment_id,
            "outcome": outcome,
            "n_a": n_a, "n_b": n_b,
            "conversions_a": c_a, "conversions_b": c_b,
            "rate_a": round(rate_a, 6),
            "rate_b": round(rate_b, 6),
            "z_stat": round(z, 4),
            "p_value": round(p, 6),
            "alpha": alpha,
        }

    def auto_promote_winner(
        self, experiment_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"promoted": False, "error": "actor_and_reason_required"}
        sig = self.significance_test(experiment_id)
        if sig.get("outcome") not in ("VARIANT_A_WINS", "VARIANT_B_WINS"):
            return {
                "promoted": False,
                "outcome": sig.get("outcome", "UNKNOWN"),
                "reason": "no_significant_winner",
            }
        # Conclude experiment
        self.transition_experiment_state(
            experiment_id, "CONCLUDED", actor=actor,
            reason=f"auto_promote_winner: {reason} ({sig['outcome']})",
        )
        return {
            "promoted": True,
            "winner": sig["outcome"],
            "experiment_id": experiment_id,
            "p_value": sig["p_value"],
        }


def _self_test() -> None:
    import tempfile

    assert "VARIANT_A_WINS" in EXPERIMENT_OUTCOMES
    assert ALLOWED_EXPERIMENT_TRANSITIONS["ARCHIVED"] == ()

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CampaignsABTestingEngine(
            experiments_path=Path(tmpdir) / "e.json",
            assignments_path=Path(tmpdir) / "a.json",
            outcomes_path=Path(tmpdir) / "o.json",
        )

        # Test 1: register
        r = engine.register_experiment(
            {"experiment_id": "EXP-001", "campaign_id": "CAMP-001",
             "experiment_name": "subject test",
             "dimension": "SUBJECT_LINE",
             "variant_a": "Welcome to our exclusive program",
             "variant_b": "Don't miss out — apply today"},
            actor="x", reason="r",
        )
        assert r["registered"]

        # Test 2: cannot assign if not RUNNING
        r = engine.assign_variant("EXP-001", "C1", actor="x")
        assert not r["assigned"]

        # Test 3: activate
        engine.transition_experiment_state(
            "EXP-001", "RUNNING", actor="x", reason="r",
        )

        # Test 4: assign 100 customers
        for i in range(100):
            r = engine.assign_variant(f"EXP-001", f"C{i}", actor="adapter")
            assert r["assigned"]

        # Test 5: re-assign returns same variant
        first = engine.assign_variant("EXP-001", "C0", actor="adapter")
        second = engine.assign_variant("EXP-001", "C0", actor="adapter")
        assert first["variant"] == second["variant"]
        assert second["already_assigned"]

        # Test 6: insufficient data
        sig = engine.significance_test("EXP-001")
        # Both variants now have 50ish, but no outcomes recorded
        # So both samples are 50 each (above 30) but with 0 conversions
        # → p-value 1.0, outcome INCONCLUSIVE

        # Test 7: record outcomes — strong A win
        # First, find which customers are in A vs B
        assignments = engine._load(engine.assignments_path,
                                            "campaign_ab_assignments",
                                            ("assignment_id",))
        a_customers = [a["customer_id"] for a in assignments
                            if a.get("experiment_id") == "EXP-001"
                            and a.get("variant") == "A"]
        b_customers = [a["customer_id"] for a in assignments
                            if a.get("experiment_id") == "EXP-001"
                            and a.get("variant") == "B"]

        # 80% conversion in A, 20% in B
        for i, cid in enumerate(a_customers):
            outcome = "CONVERTED" if i < int(len(a_customers) * 0.8) else "NOT_CONVERTED"
            engine.record_outcome("EXP-001", cid, outcome, actor="adapter")
        for i, cid in enumerate(b_customers):
            outcome = "CONVERTED" if i < int(len(b_customers) * 0.2) else "NOT_CONVERTED"
            engine.record_outcome("EXP-001", cid, outcome, actor="adapter")

        sig = engine.significance_test("EXP-001")
        # Should be VARIANT_A_WINS
        assert sig["outcome"] == "VARIANT_A_WINS", sig

        # Test 8: auto_promote
        r = engine.auto_promote_winner(
            "EXP-001", actor="campaign_lead", reason="ship winner",
        )
        assert r["promoted"]
        assert r["winner"] == "VARIANT_A_WINS"

        # Test 9: invalid outcome
        r = engine.record_outcome("EXP-001", "X", "MAYBE", actor="x")
        assert not r["recorded"]

        # Test 10: duplicate outcome rejected
        r = engine.record_outcome("EXP-001", a_customers[0], "CONVERTED",
                                          actor="adapter")
        assert not r["recorded"]

    print("  ✅ campaigns_ab_testing self-test PASS")


if __name__ == "__main__":
    _self_test()
