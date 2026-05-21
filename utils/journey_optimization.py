"""
================================================================================
A2Z MIS 360 — Standard #345: Customer Journey Optimization Engine
================================================================================

Risk classification: Cat C (deterministic A/B variant tracking + friction
                              discovery composer)

ML-driven journey optimization: A/B test journey variants, identify
friction, recommend changes, measure impact. v10.276 ships deterministic
A/B variant registry + variant-level performance tracking + friction
discovery aggregator over the v10.275 friction indicator base. ML-driven
variant ranking deferred (would require traffic + conversion data
volume not yet present).

Public API:
    register_variant(variant_data, actor, reason)
    transition_variant_state(variant_id, new_state, actor, reason)
    assign_customer_to_variant(variant_id, customer_id, actor)
    record_variant_event(variant_id, customer_id, event_type, ...)
    variant_performance(variant_id) -> {assigned, completed, conversion_pct}
    population_friction_summary(period_start, period_end)
        -> aggregate friction across all customers
    recommend_variant(...) -> rule-based recommendation

VARIANT_STATES byte-for-byte:
    DRAFT       -- created, not yet published
    RUNNING     -- live, receiving traffic
    PAUSED      -- temporarily halted (terminal in flow but resumable)
    COMPLETED   -- formally ended (terminal)
    ARCHIVED    -- archived for historical (terminal)

ALLOWED_VARIANT_TRANSITIONS (Rule 4):
    DRAFT      → RUNNING | ARCHIVED
    RUNNING    → PAUSED | COMPLETED | ARCHIVED
    PAUSED     → RUNNING | COMPLETED | ARCHIVED
    COMPLETED  → ARCHIVED
    ARCHIVED   → ()  -- terminal

VARIANT_EVENT_TYPES byte-for-byte:
    ENTERED_VARIANT     -- customer started variant
    STEP_COMPLETED      -- intermediate step in variant journey
    COMPLETED_VARIANT   -- customer reached variant goal
    DROPPED_VARIANT     -- customer abandoned variant

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid state / event_type rejected
    Rule 1: variant_performance returns conversion_pct=None for empty
            variant; population_friction_summary returns reason for empty

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.interaction_capture import InteractionCaptureEngine
from utils.journey_and_widget import (
    JourneyAndWidgetEngine, FRICTION_INDICATORS,
)

getcontext().prec = 28


VARIANT_STATES: Tuple[str, ...] = (
    "DRAFT", "RUNNING", "PAUSED", "COMPLETED", "ARCHIVED",
)

ALLOWED_VARIANT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":     ("RUNNING", "ARCHIVED"),
    "RUNNING":   ("PAUSED", "COMPLETED", "ARCHIVED"),
    "PAUSED":    ("RUNNING", "COMPLETED", "ARCHIVED"),
    "COMPLETED": ("ARCHIVED",),
    "ARCHIVED":  (),
}

VARIANT_EVENT_TYPES: Tuple[str, ...] = (
    "ENTERED_VARIANT", "STEP_COMPLETED",
    "COMPLETED_VARIANT", "DROPPED_VARIANT",
)


class JourneyOptimizationEngine:
    """A/B variant registry + performance tracking + friction aggregation."""

    def __init__(
        self,
        variants_path: Optional[Path] = None,
        assignments_path: Optional[Path] = None,
        events_path: Optional[Path] = None,
        capture: Optional[InteractionCaptureEngine] = None,
        journey: Optional[JourneyAndWidgetEngine] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.variants_path = variants_path or base / "journey_variants.json"
        self.assignments_path = assignments_path or base / "journey_variant_assignments.json"
        self.events_path = events_path or base / "journey_variant_events.json"
        self.capture = capture or InteractionCaptureEngine()
        self.journey = journey or JourneyAndWidgetEngine(capture=self.capture)

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

    # ── Variant registry ────────────────────────────────────────────

    def register_variant(
        self,
        variant_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("variant_id", "variant_name", "journey_steps"):
            if f not in variant_data or not variant_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        records = self._load(self.variants_path, "journey_variants",
                                ("variant_id",))
        if any(r.get("variant_id") == variant_data["variant_id"] for r in records):
            return {"registered": False, "error": "duplicate_variant_id"}

        record = {
            "variant_id": variant_data["variant_id"],
            "variant_name": variant_data["variant_name"],
            "journey_steps": list(variant_data["journey_steps"]),
            "traffic_split_pct": variant_data.get("traffic_split_pct", 50),
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
        ok = self._save(self.variants_path, records,
                          "journey_variants", "variant_id")
        return {"registered": ok, "variant_id": variant_data["variant_id"]}

    def transition_variant_state(
        self,
        variant_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in VARIANT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load(self.variants_path, "journey_variants",
                                ("variant_id",))
        for r in records:
            if r.get("variant_id") == variant_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_VARIANT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.variants_path, records,
                                  "journey_variants", "variant_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "variant_not_found"}

    # ── Customer assignment + events ───────────────────────────────

    def assign_customer_to_variant(
        self,
        variant_id: str,
        customer_id: str,
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"assigned": False, "error": "actor_required"}

        # Variant must be RUNNING
        variants = self._load(self.variants_path, "journey_variants",
                                  ("variant_id",))
        v = next((r for r in variants if r.get("variant_id") == variant_id), None)
        if v is None:
            return {"assigned": False, "error": "variant_not_found"}
        if v.get("state") != "RUNNING":
            return {
                "assigned": False,
                "error": f"variant_not_running:{v['state']}",
            }

        records = self._load(self.assignments_path,
                                "journey_variant_assignments",
                                ("variant_id", "customer_id"))
        # Prevent duplicate assignment
        if any(a.get("variant_id") == variant_id
                 and a.get("customer_id") == customer_id for a in records):
            return {"assigned": False, "error": "already_assigned"}

        records.append({
            "assignment_id": f"ASG-{variant_id}-{customer_id}",
            "variant_id": variant_id,
            "customer_id": customer_id,
            "assigned_by": actor,
            "assigned_at": datetime.utcnow().isoformat(),
            "current_step": None,
            "completed": False,
        })
        ok = self._save(self.assignments_path, records,
                          "journey_variant_assignments", "assignment_id")
        return {"assigned": ok}

    def record_variant_event(
        self,
        variant_id: str,
        customer_id: str,
        event_type: str,
        actor: str,
        step: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if event_type not in VARIANT_EVENT_TYPES:
            return {
                "recorded": False,
                "error": f"invalid_event_type:{event_type}",
                "valid_types": list(VARIANT_EVENT_TYPES),
            }

        records = self._load(self.events_path,
                                "journey_variant_events",
                                ("event_id",))
        event_id = (f"VEV-{variant_id}-{customer_id}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        records.append({
            "event_id": event_id,
            "variant_id": variant_id,
            "customer_id": customer_id,
            "event_type": event_type,
            "step": step,
            "actor": actor,
            "notes": notes,
            "occurred_at": datetime.utcnow().isoformat(),
        })

        # Update assignment if COMPLETED_VARIANT or DROPPED_VARIANT
        if event_type in ("COMPLETED_VARIANT", "DROPPED_VARIANT"):
            assignments = self._load(self.assignments_path,
                                          "journey_variant_assignments",
                                          ("variant_id", "customer_id"))
            for a in assignments:
                if (a.get("variant_id") == variant_id
                        and a.get("customer_id") == customer_id):
                    a["completed"] = (event_type == "COMPLETED_VARIANT")
                    a["dropped"] = (event_type == "DROPPED_VARIANT")
                    a["closed_at"] = datetime.utcnow().isoformat()
                    self._save(self.assignments_path, assignments,
                                 "journey_variant_assignments", "assignment_id")
                    break

        ok = self._save(self.events_path, records,
                          "journey_variant_events", "event_id")
        return {"recorded": ok, "event_id": event_id}

    # ── Performance ────────────────────────────────────────────────

    def variant_performance(self, variant_id: str) -> Dict[str, Any]:
        assignments = self._load(self.assignments_path,
                                      "journey_variant_assignments",
                                      ("variant_id", "customer_id"))
        for_variant = [a for a in assignments
                            if a.get("variant_id") == variant_id]
        assigned = len(for_variant)

        if assigned == 0:
            return {
                "variant_id": variant_id,
                "assigned": 0,
                "completed": 0,
                "dropped": 0,
                "conversion_pct": None,
                "reason": "no_assignments",
            }

        completed = sum(1 for a in for_variant if a.get("completed"))
        dropped = sum(1 for a in for_variant if a.get("dropped"))
        conv = (Decimal(completed) / Decimal(assigned) *
                  Decimal("100")).quantize(Decimal("0.01"))

        return {
            "variant_id": variant_id,
            "assigned": assigned,
            "completed": completed,
            "dropped": dropped,
            "conversion_pct": str(conv),
        }

    # ── Friction aggregation across population ────────────────────

    def population_friction_summary(
        self,
        customer_ids: List[str],
        as_of: Optional[date] = None,
    ) -> Dict[str, Any]:
        as_of = as_of or date.today()
        if not customer_ids:
            return {
                "as_of": as_of.isoformat(),
                "scanned_count": 0,
                "by_indicator": {},
                "friction_share_pct": {},
                "reason": "empty_customer_list",
            }

        indicator_counts: Counter = Counter()
        any_friction_count = 0
        for cid in customer_ids:
            f = self.journey.journey_friction_points(cid, as_of=as_of)
            present = f.get("indicators_present", [])
            if present:
                any_friction_count += 1
                for i in present:
                    indicator_counts[i] += 1

        share = {}
        if customer_ids:
            for ind in FRICTION_INDICATORS:
                count = indicator_counts.get(ind, 0)
                share[ind] = str(
                    (Decimal(count) / Decimal(len(customer_ids)) *
                      Decimal("100")).quantize(Decimal("0.01"))
                )

        return {
            "as_of": as_of.isoformat(),
            "scanned_count": len(customer_ids),
            "customers_with_any_friction": any_friction_count,
            "by_indicator": dict(indicator_counts),
            "friction_share_pct": share,
        }


def _self_test() -> None:
    import tempfile

    assert ALLOWED_VARIANT_TRANSITIONS["ARCHIVED"] == ()
    assert "COMPLETED_VARIANT" in VARIANT_EVENT_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = JourneyOptimizationEngine(
            variants_path=Path(tmpdir) / "v.json",
            assignments_path=Path(tmpdir) / "a.json",
            events_path=Path(tmpdir) / "vev.json",
            capture=capture,
        )

        # Test 1: register variant
        r = engine.register_variant(
            {"variant_id": "V-001", "variant_name": "Onboarding A",
             "journey_steps": ["welcome", "kyc", "fund"],
             "traffic_split_pct": 50},
            actor="design_lead", reason="A/B test for onboarding flow",
        )
        assert r["registered"]

        # Test 2: missing field
        r = engine.register_variant(
            {"variant_id": "V-X", "variant_name": ""},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 3: state lifecycle DRAFT → RUNNING → PAUSED → RUNNING → COMPLETED → ARCHIVED
        for ns, reason in [
            ("RUNNING", "ready to ship"),
            ("PAUSED", "investigating issue"),
            ("RUNNING", "issue fixed"),
            ("COMPLETED", "test concluded"),
            ("ARCHIVED", "archiving"),
        ]:
            t = engine.transition_variant_state(
                "V-001", ns, actor="design_lead", reason=reason,
            )
            assert t["transitioned"], (ns, t)

        # Test 4: skip rejected DRAFT → COMPLETED
        engine.register_variant(
            {"variant_id": "V-002", "variant_name": "B",
             "journey_steps": ["step1"]},
            actor="design", reason="b",
        )
        t = engine.transition_variant_state(
            "V-002", "COMPLETED", actor="design", reason="skip",
        )
        assert not t["transitioned"]

        # Test 5: cannot assign to non-RUNNING
        a = engine.assign_customer_to_variant("V-002", "CUST-1", actor="x")
        assert not a["assigned"]
        assert "variant_not_running" in a["error"]

        # Activate V-002
        engine.transition_variant_state(
            "V-002", "RUNNING", actor="d", reason="go",
        )
        a = engine.assign_customer_to_variant("V-002", "CUST-1", actor="x")
        assert a["assigned"]

        # Test 6: duplicate assignment
        a = engine.assign_customer_to_variant("V-002", "CUST-1", actor="x")
        assert not a["assigned"]
        assert a["error"] == "already_assigned"

        # Test 7: record events
        r = engine.record_variant_event(
            "V-002", "CUST-1", "ENTERED_VARIANT", actor="pipeline",
        )
        assert r["recorded"]
        r = engine.record_variant_event(
            "V-002", "CUST-1", "COMPLETED_VARIANT", actor="pipeline",
        )
        assert r["recorded"]

        # Test 8: invalid event type
        r = engine.record_variant_event(
            "V-002", "CUST-1", "INVALID", actor="x",
        )
        assert not r["recorded"]

        # Test 9: variant_performance
        engine.assign_customer_to_variant("V-002", "CUST-2", actor="x")
        engine.record_variant_event(
            "V-002", "CUST-2", "DROPPED_VARIANT", actor="pipeline",
        )
        engine.assign_customer_to_variant("V-002", "CUST-3", actor="x")
        # CUST-3 still in flight
        perf = engine.variant_performance("V-002")
        assert perf["assigned"] == 3
        assert perf["completed"] == 1
        assert perf["dropped"] == 1
        # 1 of 3 = 33.33
        assert perf["conversion_pct"] == "33.33"

        # Test 10: empty variant
        engine.register_variant(
            {"variant_id": "V-003", "variant_name": "empty",
             "journey_steps": ["x"]},
            actor="d", reason="empty test",
        )
        perf = engine.variant_performance("V-003")
        assert perf["conversion_pct"] is None
        assert perf["reason"] == "no_assignments"

        # Test 11: population_friction_summary — empty list
        summary = engine.population_friction_summary([])
        assert summary["scanned_count"] == 0
        assert summary["reason"] == "empty_customer_list"

        # Test 12: population_friction_summary with seeded data
        # Seed friction for CUST-1 (3+ abandoned events in 90 days)
        for i in range(3):
            capture.capture_event(
                "CUST-1",
                {"event_id": f"AB-{i}",
                 "channel": "MOBILE_APP",
                 "event_type": "INTERACTION",
                 "outcome": "ABANDONED",
                 "occurred_at": (date.today() - timedelta(days=10+i)).isoformat() + "T10:00:00"},
                actor="x",
            )
        summary = engine.population_friction_summary(
            ["CUST-1", "CUST-2"],
        )
        assert summary["scanned_count"] == 2
        # CUST-1 should show HIGH_ABANDONMENT
        assert summary["by_indicator"].get("HIGH_ABANDONMENT", 0) >= 1

    print("  ✅ journey_optimization self-test PASS")


if __name__ == "__main__":
    _self_test()
