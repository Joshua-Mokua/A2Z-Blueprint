"""
================================================================================
A2Z MIS 360 — Standard #356: Dynamic Cohorts & Signals Engine
================================================================================

Risk classification: Cat C (deterministic cohort definition + auto-refresh
                              based on signal triggers)

Dynamic customer cohorts based on signals: life stage, behavioral patterns,
financial events. Auto-update as signals change. Composes v10.276
BehavioralProfileEngine (life_stage, spending_tier, risk_appetite) +
v10.275 InteractionCaptureEngine for signal detection.

Public API:
    register_cohort(cohort_data, actor, reason)
    transition_cohort_state(cohort_id, new_state, actor, reason)
    refresh_cohort(cohort_id, customer_pool, actor)
        -> evaluates cohort rules across pool + updates membership
    cohort_membership(cohort_id) -> List[customer_id]
    customer_cohorts(customer_id) -> List[cohort_id]
    detect_signal_changes(customer_id, prior_profile, current_profile)
        -> List[trigger_events]

COHORT_STATES byte-for-byte:
    DRAFT       -- cohort defined, not yet active
    ACTIVE      -- live, auto-refreshing on signal triggers
    REFRESHING  -- mid-refresh (transient, brief)
    RETIRED     -- no longer used (terminal-ish)
    ARCHIVED    -- archived (terminal)

ALLOWED_COHORT_TRANSITIONS (Rule 4):
    DRAFT      → ACTIVE | ARCHIVED
    ACTIVE     → REFRESHING | RETIRED | ARCHIVED
    REFRESHING → ACTIVE | RETIRED
    RETIRED    → ARCHIVED
    ARCHIVED   → ()

AUTO_UPDATE_TRIGGERS byte-for-byte (signal types that trigger refresh):
    BEHAVIORAL_PROFILE_CHANGE  -- spending tier / risk appetite changed
    LIFE_STAGE_CHANGE          -- age bracket / life event change
    SPENDING_TIER_CHANGE       -- specific spending tier transition
    RISK_APPETITE_CHANGE       -- specific risk appetite transition
    CUSTOM                     -- any other custom-defined trigger

COHORT_RULE_TYPES byte-for-byte:
    FILTER     -- include if customer matches predicate
    AGGREGATE  -- include if group statistic crosses threshold
    UNION      -- combine multiple sub-cohorts

Honesty rules:
    Rule 1: refresh returns explicit member counts; never silent
    Rule 4: actor + reason mandatory on lifecycle
    Rule 6: invalid trigger / rule_type rejected

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.customer_behavioral_profile import (
    BehavioralProfileEngine, SPENDING_TIERS, RISK_APPETITE_LEVELS, LIFE_STAGES,
)


COHORT_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "REFRESHING", "RETIRED", "ARCHIVED",
)

ALLOWED_COHORT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("REFRESHING", "RETIRED", "ARCHIVED"),
    "REFRESHING": ("ACTIVE", "RETIRED"),
    "RETIRED":    ("ARCHIVED",),
    "ARCHIVED":   (),
}

AUTO_UPDATE_TRIGGERS: Tuple[str, ...] = (
    "BEHAVIORAL_PROFILE_CHANGE", "LIFE_STAGE_CHANGE",
    "SPENDING_TIER_CHANGE", "RISK_APPETITE_CHANGE", "CUSTOM",
)

COHORT_RULE_TYPES: Tuple[str, ...] = ("FILTER", "AGGREGATE", "UNION")


class DynamicCohortsEngine:
    """Dynamic cohort registry + auto-refresh based on signal triggers."""

    def __init__(
        self,
        profile: Optional[BehavioralProfileEngine] = None,
        cohorts_path: Optional[Path] = None,
        memberships_path: Optional[Path] = None,
        signals_path: Optional[Path] = None,
    ):
        self.profile = profile or BehavioralProfileEngine()
        base = Path(__file__).parent.parent / "data"
        self.cohorts_path = cohorts_path or base / "dynamic_cohorts.json"
        self.memberships_path = memberships_path or base / "cohort_memberships.json"
        self.signals_path = signals_path or base / "cohort_signals.json"

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

    def register_cohort(
        self,
        cohort_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("cohort_id", "cohort_name", "rule_type"):
            if f not in cohort_data or not cohort_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if cohort_data["rule_type"] not in COHORT_RULE_TYPES:
            return {
                "registered": False,
                "error": f"invalid_rule_type:{cohort_data['rule_type']}",
                "valid_types": list(COHORT_RULE_TYPES),
            }
        # Validate triggers if provided
        triggers = cohort_data.get("triggers", [])
        for t in triggers:
            if t not in AUTO_UPDATE_TRIGGERS:
                return {
                    "registered": False,
                    "error": f"invalid_trigger:{t}",
                    "valid_triggers": list(AUTO_UPDATE_TRIGGERS),
                }

        records = self._load(self.cohorts_path,
                                "dynamic_cohorts", ("cohort_id",))
        if any(r.get("cohort_id") == cohort_data["cohort_id"] for r in records):
            return {"registered": False, "error": "duplicate_cohort_id"}

        record = {
            "cohort_id": cohort_data["cohort_id"],
            "cohort_name": cohort_data["cohort_name"],
            "description": cohort_data.get("description", ""),
            "rule_type": cohort_data["rule_type"],
            "predicate": cohort_data.get("predicate", {}),
            "sub_cohort_ids": cohort_data.get("sub_cohort_ids", []),
            "triggers": triggers,
            "owner_role": cohort_data.get("owner_role", ""),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "last_refreshed_at": None,
            "registration_reason": reason,
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": reason,
            }],
        }
        records.append(record)
        ok = self._save(self.cohorts_path, records,
                          "dynamic_cohorts", "cohort_id")
        return {"registered": ok, "cohort_id": cohort_data["cohort_id"]}

    def transition_cohort_state(
        self,
        cohort_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in COHORT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load(self.cohorts_path,
                                "dynamic_cohorts", ("cohort_id",))
        for r in records:
            if r.get("cohort_id") == cohort_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_COHORT_TRANSITIONS.get(current, ())
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
                ok = self._save(self.cohorts_path, records,
                                  "dynamic_cohorts", "cohort_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "cohort_not_found"}

    def _evaluate_predicate(
        self,
        predicate: Dict[str, Any],
        customer_id: str,
        customer_attrs: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate FILTER predicate against a customer's behavioral profile."""
        customer_attrs = customer_attrs or {}

        # Predicate keys map to BehavioralProfileEngine outputs:
        #   spending_tier_in: ["HIGH", "MEDIUM"]
        #   risk_appetite_in: ["MODERATE", "ADVENTUROUS"]
        #   life_stage_in: ["FAMILY_BUILDING", "ESTABLISHED"]
        #   loyalty_score_min: "70"
        #   age_min, age_max
        #   segment_in: ["DIASPORA", "WOMEN"]

        age = customer_attrs.get("age")
        life_events = customer_attrs.get("life_events", [])

        # Pull profile components on demand (only what's needed)
        if "spending_tier_in" in predicate:
            st = self.profile.spending_tier(customer_id)
            if st.get("tier") not in predicate["spending_tier_in"]:
                return False
        if "risk_appetite_in" in predicate:
            ra = self.profile.customer_risk_appetite(customer_id)
            if ra.get("level") not in predicate["risk_appetite_in"]:
                return False
        if "life_stage_in" in predicate:
            ls = self.profile.life_stage(customer_id, age=age,
                                              life_events=life_events)
            if ls.get("stage") not in predicate["life_stage_in"]:
                return False
        if "loyalty_score_min" in predicate:
            ly = self.profile.customer_loyalty_score(customer_id)
            if ly.get("score") is None:
                return False
            try:
                if Decimal(ly["score"]) < Decimal(str(predicate["loyalty_score_min"])):
                    return False
            except (ValueError, TypeError):
                return False
        if "age_min" in predicate:
            if age is None or age < predicate["age_min"]:
                return False
        if "age_max" in predicate:
            if age is None or age > predicate["age_max"]:
                return False
        if "segment_in" in predicate:
            seg = customer_attrs.get("segment")
            if seg not in predicate["segment_in"]:
                return False

        return True

    def refresh_cohort(
        self,
        cohort_id: str,
        customer_pool: List[Dict[str, Any]],
        actor: str,
    ) -> Dict[str, Any]:
        """Re-evaluate cohort rules across the customer pool.

        customer_pool is a list of {customer_id, age?, life_events?, segment?}.
        Returns updated membership counts.
        """
        if not actor:
            return {"refreshed": False, "error": "actor_required"}
        records = self._load(self.cohorts_path,
                                "dynamic_cohorts", ("cohort_id",))
        cohort = next((r for r in records
                          if r.get("cohort_id") == cohort_id), None)
        if cohort is None:
            return {"refreshed": False, "error": "cohort_not_found"}
        if cohort.get("state") not in ("ACTIVE", "DRAFT", "REFRESHING"):
            return {
                "refreshed": False,
                "error": f"cohort_not_refreshable:{cohort['state']}",
            }

        rule_type = cohort.get("rule_type")
        prev_member_ids: set = set()

        # Load existing memberships
        memberships = self._load(self.memberships_path,
                                       "cohort_memberships",
                                       ("cohort_id", "customer_id"))
        for m in memberships:
            if m.get("cohort_id") == cohort_id:
                prev_member_ids.add(m.get("customer_id"))

        new_member_ids: set = set()

        if rule_type == "FILTER":
            predicate = cohort.get("predicate", {})
            for entry in customer_pool:
                cid = entry.get("customer_id")
                if not cid:
                    continue
                if self._evaluate_predicate(predicate, cid, entry):
                    new_member_ids.add(cid)
        elif rule_type == "UNION":
            sub_ids = cohort.get("sub_cohort_ids", [])
            for sub_id in sub_ids:
                for m in memberships:
                    if m.get("cohort_id") == sub_id:
                        new_member_ids.add(m.get("customer_id"))
        elif rule_type == "AGGREGATE":
            # Simple example: include all customers if pool size > threshold
            min_pool = cohort.get("predicate", {}).get("min_pool_size", 0)
            if len(customer_pool) >= min_pool:
                new_member_ids = {c.get("customer_id")
                                       for c in customer_pool if c.get("customer_id")}
            else:
                new_member_ids = set()

        # Remove old memberships not in new set
        memberships = [
            m for m in memberships
            if not (m.get("cohort_id") == cohort_id
                      and m.get("customer_id") not in new_member_ids)
        ]
        # Add new memberships
        existing_set = {(m.get("cohort_id"), m.get("customer_id"))
                            for m in memberships}
        added = 0
        for cid in new_member_ids:
            if (cohort_id, cid) not in existing_set:
                memberships.append({
                    "membership_id": f"COH-{cohort_id}-{cid}",
                    "cohort_id": cohort_id,
                    "customer_id": cid,
                    "joined_at": datetime.utcnow().isoformat(),
                })
                added += 1

        self._save(self.memberships_path, memberships,
                     "cohort_memberships", "membership_id")

        # Update cohort meta
        for r in records:
            if r.get("cohort_id") == cohort_id:
                r["last_refreshed_at"] = datetime.utcnow().isoformat()
                break
        self._save(self.cohorts_path, records,
                     "dynamic_cohorts", "cohort_id")

        removed = len(prev_member_ids - new_member_ids)
        return {
            "refreshed": True,
            "cohort_id": cohort_id,
            "previous_size": len(prev_member_ids),
            "current_size": len(new_member_ids),
            "added": added,
            "removed": removed,
            "rule_type": rule_type,
        }

    def cohort_membership(self, cohort_id: str) -> List[str]:
        memberships = self._load(self.memberships_path,
                                       "cohort_memberships",
                                       ("cohort_id", "customer_id"))
        return [m["customer_id"] for m in memberships
                  if m.get("cohort_id") == cohort_id]

    def customer_cohorts(self, customer_id: str) -> List[str]:
        memberships = self._load(self.memberships_path,
                                       "cohort_memberships",
                                       ("cohort_id", "customer_id"))
        return [m["cohort_id"] for m in memberships
                  if m.get("customer_id") == customer_id]

    def detect_signal_changes(
        self,
        customer_id: str,
        prior_profile: Dict[str, Any],
        current_profile: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Compare two profile snapshots; record any AUTO_UPDATE_TRIGGER fired."""
        if not actor:
            return {"detected": [], "error": "actor_required"}
        triggers_fired: List[Dict[str, Any]] = []

        prior_tier = (prior_profile.get("spending", {}) or {}).get("tier")
        current_tier = (current_profile.get("spending", {}) or {}).get("tier")
        if prior_tier and current_tier and prior_tier != current_tier:
            triggers_fired.append({
                "trigger": "SPENDING_TIER_CHANGE",
                "from": prior_tier, "to": current_tier,
            })

        prior_risk = (prior_profile.get("risk_appetite", {}) or {}).get("level")
        current_risk = (current_profile.get("risk_appetite", {}) or {}).get("level")
        if prior_risk and current_risk and prior_risk != current_risk:
            triggers_fired.append({
                "trigger": "RISK_APPETITE_CHANGE",
                "from": prior_risk, "to": current_risk,
            })

        prior_stage = (prior_profile.get("life_stage", {}) or {}).get("stage")
        current_stage = (current_profile.get("life_stage", {}) or {}).get("stage")
        if prior_stage and current_stage and prior_stage != current_stage:
            triggers_fired.append({
                "trigger": "LIFE_STAGE_CHANGE",
                "from": prior_stage, "to": current_stage,
            })

        # Composite trigger
        if len(triggers_fired) >= 2:
            triggers_fired.append({
                "trigger": "BEHAVIORAL_PROFILE_CHANGE",
                "component_changes": len(triggers_fired),
            })

        # Persist detected signals for audit
        if triggers_fired:
            signals = self._load(self.signals_path,
                                       "cohort_signals", ("signal_id",))
            for tf in triggers_fired:
                signal_id = (f"SIG-{customer_id}-{tf['trigger']}-"
                                  f"{int(datetime.utcnow().timestamp() * 1000)}")
                signals.append({
                    "signal_id": signal_id,
                    "customer_id": customer_id,
                    "trigger": tf["trigger"],
                    "details": tf,
                    "actor": actor,
                    "detected_at": datetime.utcnow().isoformat(),
                })
            self._save(self.signals_path, signals,
                         "cohort_signals", "signal_id")

        return {
            "customer_id": customer_id,
            "detected": triggers_fired,
            "trigger_count": len(triggers_fired),
        }


def _self_test() -> None:
    import tempfile

    assert "REFRESHING" in COHORT_STATES
    assert ALLOWED_COHORT_TRANSITIONS["ARCHIVED"] == ()
    assert "BEHAVIORAL_PROFILE_CHANGE" in AUTO_UPDATE_TRIGGERS
    assert "FILTER" in COHORT_RULE_TYPES

    with tempfile.TemporaryDirectory() as tmpdir:
        from datetime import timedelta
        from utils.interaction_capture import InteractionCaptureEngine

        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        profile = BehavioralProfileEngine(capture=capture)

        engine = DynamicCohortsEngine(
            profile=profile,
            cohorts_path=Path(tmpdir) / "c.json",
            memberships_path=Path(tmpdir) / "m.json",
            signals_path=Path(tmpdir) / "s.json",
        )

        # Test 1: register cohort
        r = engine.register_cohort(
            {"cohort_id": "COH-AFFLUENT",
             "cohort_name": "Affluent Engaged",
             "rule_type": "FILTER",
             "predicate": {
                 "spending_tier_in": ["HIGH"],
                 "loyalty_score_min": "60",
             },
             "triggers": ["SPENDING_TIER_CHANGE",
                            "BEHAVIORAL_PROFILE_CHANGE"]},
            actor="segment_lead", reason="affluent customer cohort",
        )
        assert r["registered"]

        # Test 2: invalid rule_type
        r = engine.register_cohort(
            {"cohort_id": "X", "cohort_name": "Y", "rule_type": "INVALID"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 3: invalid trigger
        r = engine.register_cohort(
            {"cohort_id": "X", "cohort_name": "Y", "rule_type": "FILTER",
             "triggers": ["INVALID"]},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Test 4: state lifecycle DRAFT → ACTIVE
        t = engine.transition_cohort_state(
            "COH-AFFLUENT", "ACTIVE", actor="x", reason="go",
        )
        assert t["transitioned"]

        # Test 5: refresh — empty pool
        r = engine.refresh_cohort("COH-AFFLUENT", [], actor="x")
        assert r["refreshed"]
        assert r["current_size"] == 0

        # Test 6: refresh with pool — seed CUST-1 as HIGH spender + tenured
        # Add old event for tenure
        old_day = (date.today() - timedelta(days=400)).isoformat()
        capture.capture_event(
            "CUST-1",
            {"event_id": "OLD", "channel": "BRANCH",
             "event_type": "APPLICATION", "outcome": "SUCCESS",
             "occurred_at": old_day + "T10:00:00"},
            actor="x",
        )
        # Add HIGH-tier transactions + diverse channels for loyalty
        for i in range(40):
            day = (date.today() - timedelta(days=80 - i*2)).isoformat()
            capture.capture_event(
                "CUST-1",
                {"event_id": f"H-{i}",
                 "channel": ["BRANCH", "MOBILE_APP", "ATM", "WEB",
                                "CALL_CENTER"][i % 5],
                 "event_type": "TRANSACTION",
                 "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "60000"},
                actor="x",
            )
        # CUST-2 LOW spender
        for i in range(3):
            day = (date.today() - timedelta(days=15+i)).isoformat()
            capture.capture_event(
                "CUST-2",
                {"event_id": f"L-{i}", "channel": "ATM",
                 "event_type": "TRANSACTION", "outcome": "SUCCESS",
                 "occurred_at": day + "T10:00:00",
                 "amount_kes": "5000"},
                actor="x",
            )
        pool = [
            {"customer_id": "CUST-1", "age": 40},
            {"customer_id": "CUST-2", "age": 35},
        ]
        r = engine.refresh_cohort("COH-AFFLUENT", pool, actor="x")
        assert r["refreshed"]
        # CUST-1 is HIGH + loyal
        members = engine.cohort_membership("COH-AFFLUENT")
        assert "CUST-1" in members
        # CUST-2 is LOW → excluded
        assert "CUST-2" not in members

        # Test 7: customer_cohorts
        c1_cohorts = engine.customer_cohorts("CUST-1")
        assert "COH-AFFLUENT" in c1_cohorts

        # Test 8: detect_signal_changes
        prior_p = {
            "spending": {"tier": "MEDIUM"},
            "risk_appetite": {"level": "MODERATE"},
            "life_stage": {"stage": "ESTABLISHED"},
        }
        current_p = {
            "spending": {"tier": "HIGH"},  # changed
            "risk_appetite": {"level": "MODERATE"},
            "life_stage": {"stage": "PRE_RETIREMENT"},  # changed
        }
        r = engine.detect_signal_changes(
            "CUST-1", prior_p, current_p, actor="profile_engine",
        )
        assert r["trigger_count"] >= 2
        triggers = {t["trigger"] for t in r["detected"]}
        assert "SPENDING_TIER_CHANGE" in triggers
        assert "LIFE_STAGE_CHANGE" in triggers
        # composite trigger fires when 2+ component changes
        assert "BEHAVIORAL_PROFILE_CHANGE" in triggers

        # Test 9: no changes
        r = engine.detect_signal_changes(
            "CUST-1", prior_p, prior_p, actor="x",
        )
        assert r["trigger_count"] == 0

        # Test 10: UNION cohort
        engine.register_cohort(
            {"cohort_id": "COH-UNION",
             "cohort_name": "Union of Affluent",
             "rule_type": "UNION",
             "sub_cohort_ids": ["COH-AFFLUENT"]},
            actor="x", reason="union test",
        )
        engine.transition_cohort_state(
            "COH-UNION", "ACTIVE", actor="x", reason="go",
        )
        r = engine.refresh_cohort("COH-UNION", pool, actor="x")
        union_members = engine.cohort_membership("COH-UNION")
        assert "CUST-1" in union_members

    print("  ✅ dynamic_cohorts self-test PASS")


if __name__ == "__main__":
    _self_test()
