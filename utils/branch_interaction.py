"""
================================================================================
A2Z MIS 360 — Standard #339: Branch Interaction Tracking
================================================================================

Risk classification: Cat C (deterministic branch visit tracking)

Branch visit logs: queue time, service time, NPS, purpose of visit,
RM/teller assignment, outcome. Composes interaction_capture as the
event layer; this module owns the structured visit lifecycle.

Public API:
    log_branch_visit(customer_id, visit_data, actor)
    transition_visit_state(visit_id, new_state, actor, reason)
    record_visit_outcome(visit_id, outcome_data, actor)
    queue_analytics(branch_id, period_start, period_end)
    branch_kpis(branch_id, period_start, period_end)
    nps_summary(branch_id, period_start, period_end)

VISIT_PURPOSES byte-for-byte (Continuation.docx #339):
    ACCOUNT_OPENING        -- new account / product application
    DEPOSIT                -- cash deposit
    WITHDRAWAL             -- cash withdrawal
    TRANSFER               -- money transfer
    LOAN_INQUIRY           -- loan / credit application
    INVESTMENT_INQUIRY     -- investment products
    COMPLAINT              -- complaint resolution
    DOCUMENT_REQUEST       -- statement / certificate
    INSURANCE_INQUIRY      -- bancassurance discussion
    GENERAL_INQUIRY        -- other / general

VISIT_STATES byte-for-byte:
    QUEUED          -- customer in queue
    BEING_SERVED    -- with teller / RM
    COMPLETED       -- service complete (terminal)
    ABANDONED       -- customer left queue (terminal)
    REFERRED        -- redirected to another channel/branch (terminal)

ALLOWED_VISIT_TRANSITIONS (Rule 4):
    QUEUED       → BEING_SERVED | ABANDONED
    BEING_SERVED → COMPLETED | REFERRED
    COMPLETED    → ()  -- terminal
    ABANDONED    → ()  -- terminal
    REFERRED     → ()  -- terminal

VISIT_OUTCOMES byte-for-byte:
    RESOLVED              -- customer's need fully addressed
    PARTIALLY_RESOLVED    -- some progress; follow-up needed
    UNRESOLVED            -- could not address; complaint or escalation
    REFERRED_OUT          -- routed to specialist / different branch

NPS_RANGE: 0-10 inclusive

DEFAULT_QUEUE_TIME_TARGET_MIN = 10  -- service-level target
DEFAULT_SERVICE_TIME_TARGET_MIN = 15

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid purpose / state / outcome rejected
    Rule 1: queue_analytics returns None metrics for empty period

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.interaction_capture import InteractionCaptureEngine

getcontext().prec = 28


VISIT_PURPOSES: Tuple[str, ...] = (
    "ACCOUNT_OPENING", "DEPOSIT", "WITHDRAWAL", "TRANSFER",
    "LOAN_INQUIRY", "INVESTMENT_INQUIRY", "COMPLAINT",
    "DOCUMENT_REQUEST", "INSURANCE_INQUIRY", "GENERAL_INQUIRY",
)

VISIT_STATES: Tuple[str, ...] = (
    "QUEUED", "BEING_SERVED", "COMPLETED", "ABANDONED", "REFERRED",
)

ALLOWED_VISIT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "QUEUED":       ("BEING_SERVED", "ABANDONED"),
    "BEING_SERVED": ("COMPLETED", "REFERRED"),
    "COMPLETED":    (),
    "ABANDONED":    (),
    "REFERRED":     (),
}

VISIT_OUTCOMES: Tuple[str, ...] = (
    "RESOLVED", "PARTIALLY_RESOLVED", "UNRESOLVED", "REFERRED_OUT",
)

DEFAULT_QUEUE_TIME_TARGET_MIN: int = 10
DEFAULT_SERVICE_TIME_TARGET_MIN: int = 15


class BranchInteractionEngine:
    """Branch visit lifecycle + queue/service analytics."""

    def __init__(
        self,
        visits_path: Optional[Path] = None,
        capture: Optional[InteractionCaptureEngine] = None,
    ):
        self.visits_path = (
            visits_path
            if visits_path is not None
            else Path(__file__).parent.parent / "data" / "branch_visits.json"
        )
        self.capture = capture or InteractionCaptureEngine()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.visits_path,
                table="branch_visits",
                index_cols=("visit_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.visits_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.visits_path,
                data=records,
                table="branch_visits",
                pk_col="visit_id")
            return True
        except Exception:
            return False

    def log_branch_visit(
        self,
        customer_id: str,
        visit_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Log new branch visit in QUEUED state + emit interaction event."""
        if not actor:
            return {"logged": False, "error": "actor_required"}

        for f in ("visit_id", "branch_id", "purpose", "queued_at"):
            if f not in visit_data or not visit_data[f]:
                return {"logged": False, "error": f"missing_field:{f}"}

        if visit_data["purpose"] not in VISIT_PURPOSES:
            return {
                "logged": False,
                "error": f"invalid_purpose:{visit_data['purpose']}",
                "valid_purposes": list(VISIT_PURPOSES),
            }

        try:
            datetime.fromisoformat(visit_data["queued_at"].replace("Z", ""))
        except (ValueError, TypeError, AttributeError):
            return {"logged": False, "error": "invalid_queued_at_iso8601"}

        records = self._load()
        if any(r.get("visit_id") == visit_data["visit_id"] for r in records):
            return {"logged": False, "error": "duplicate_visit_id"}

        record = {
            "visit_id": visit_data["visit_id"],
            "customer_id": customer_id,
            "branch_id": visit_data["branch_id"],
            "purpose": visit_data["purpose"],
            "state": "QUEUED",
            "queued_at": visit_data["queued_at"],
            "service_started_at": None,
            "service_ended_at": None,
            "rm_or_teller_id": None,
            "outcome": None,
            "nps_score": None,
            "logged_by": actor,
            "logged_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "QUEUED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": "visit_logged",
            }],
        }
        records.append(record)
        ok = self._save(records)

        # Emit interaction event
        self.capture.capture_event(
            customer_id,
            {
                "event_id": f"BRV-{visit_data['visit_id']}",
                "channel": "BRANCH",
                "event_type": "INTERACTION",
                "outcome": "PENDING",
                "occurred_at": visit_data["queued_at"],
                "location": visit_data["branch_id"],
                "metadata": {
                    "visit_id": visit_data["visit_id"],
                    "purpose": visit_data["purpose"],
                },
            },
            actor=actor,
        )

        return {"logged": ok, "visit_id": visit_data["visit_id"]}

    def transition_visit_state(
        self,
        visit_id: str,
        new_state: str,
        actor: str,
        reason: str,
        rm_or_teller_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in VISIT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        timestamp = timestamp or datetime.utcnow().isoformat()
        records = self._load()
        for r in records:
            if r.get("visit_id") == visit_id:
                current = r.get("state", "QUEUED")
                allowed = ALLOWED_VISIT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_state
                if new_state == "BEING_SERVED":
                    r["service_started_at"] = timestamp
                    if rm_or_teller_id:
                        r["rm_or_teller_id"] = rm_or_teller_id
                elif new_state in ("COMPLETED", "REFERRED"):
                    r["service_ended_at"] = timestamp
                elif new_state == "ABANDONED":
                    r["abandoned_at"] = timestamp
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": timestamp, "reason": reason,
                })
                ok = self._save(records)
                return {"transitioned": ok, "from": current, "to": new_state}

        return {"transitioned": False, "error": "visit_not_found"}

    def record_visit_outcome(
        self,
        visit_id: str,
        outcome: str,
        actor: str,
        nps_score: Optional[int] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if outcome not in VISIT_OUTCOMES:
            return {
                "recorded": False,
                "error": f"invalid_outcome:{outcome}",
                "valid_outcomes": list(VISIT_OUTCOMES),
            }
        if nps_score is not None:
            try:
                nps = int(nps_score)
            except (ValueError, TypeError):
                return {"recorded": False, "error": "nps_not_integer"}
            if nps < 0 or nps > 10:
                return {"recorded": False, "error": "nps_out_of_0_10_range"}

        records = self._load()
        for r in records:
            if r.get("visit_id") == visit_id:
                if r.get("state") not in ("COMPLETED", "REFERRED"):
                    return {
                        "recorded": False,
                        "error": f"visit_not_in_terminal_service_state:{r['state']}",
                    }
                r["outcome"] = outcome
                if nps_score is not None:
                    r["nps_score"] = int(nps_score)
                r["outcome_notes"] = notes
                r["outcome_recorded_by"] = actor
                r["outcome_recorded_at"] = datetime.utcnow().isoformat()
                ok = self._save(records)
                return {"recorded": ok, "visit_id": visit_id, "outcome": outcome}

        return {"recorded": False, "error": "visit_not_found"}

    # ── Analytics ──────────────────────────────────────────────────

    def queue_analytics(
        self,
        branch_id: str,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Queue + service time statistics for a branch-period."""
        records = self._load()
        in_period = [
            r for r in records
            if r.get("branch_id") == branch_id
            and period_start <= r.get("queued_at", "") <= period_end
        ]

        if not in_period:
            return {
                "branch_id": branch_id,
                "period_start": period_start,
                "period_end": period_end,
                "visit_count": 0,
                "avg_queue_time_min": None,
                "avg_service_time_min": None,
                "abandonment_rate_pct": None,
                "queue_target_compliance_pct": None,
                "reason": "no_visits_in_period",
            }

        # Queue times — for those who actually got served (BEING_SERVED+)
        queue_times: List[Decimal] = []
        service_times: List[Decimal] = []
        abandoned_count = 0
        within_queue_target = 0

        for r in in_period:
            try:
                q_at = datetime.fromisoformat(r["queued_at"].replace("Z", ""))
            except (ValueError, KeyError, AttributeError):
                continue

            if r.get("state") == "ABANDONED":
                abandoned_count += 1
                continue

            if r.get("service_started_at"):
                try:
                    s_at = datetime.fromisoformat(
                        r["service_started_at"].replace("Z", ""))
                    qt_min = Decimal((s_at - q_at).total_seconds()) / Decimal("60")
                    queue_times.append(qt_min)
                    if qt_min <= DEFAULT_QUEUE_TIME_TARGET_MIN:
                        within_queue_target += 1
                except (ValueError, AttributeError):
                    pass

            if r.get("service_started_at") and r.get("service_ended_at"):
                try:
                    s_at = datetime.fromisoformat(
                        r["service_started_at"].replace("Z", ""))
                    e_at = datetime.fromisoformat(
                        r["service_ended_at"].replace("Z", ""))
                    st_min = Decimal((e_at - s_at).total_seconds()) / Decimal("60")
                    service_times.append(st_min)
                except (ValueError, AttributeError):
                    pass

        def _avg(arr):
            if not arr:
                return None
            return str((sum(arr) / Decimal(len(arr))).quantize(Decimal("0.01")))

        served = len(queue_times)
        return {
            "branch_id": branch_id,
            "period_start": period_start,
            "period_end": period_end,
            "visit_count": len(in_period),
            "served_count": served,
            "abandoned_count": abandoned_count,
            "avg_queue_time_min": _avg(queue_times),
            "avg_service_time_min": _avg(service_times),
            "abandonment_rate_pct": str(
                (Decimal(abandoned_count) / Decimal(len(in_period))
                 * Decimal("100")).quantize(Decimal("0.01"))
            ),
            "queue_target_compliance_pct": (
                str((Decimal(within_queue_target) / Decimal(served) *
                     Decimal("100")).quantize(Decimal("0.01")))
                if served > 0 else None
            ),
            "queue_target_min": DEFAULT_QUEUE_TIME_TARGET_MIN,
        }

    def branch_kpis(
        self,
        branch_id: str,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Aggregate branch KPIs."""
        records = self._load()
        in_period = [
            r for r in records
            if r.get("branch_id") == branch_id
            and period_start <= r.get("queued_at", "") <= period_end
        ]

        by_purpose = Counter(r.get("purpose") for r in in_period)
        by_state = Counter(r.get("state") for r in in_period)
        by_outcome = Counter(
            r.get("outcome") for r in in_period if r.get("outcome")
        )

        queue_stats = self.queue_analytics(
            branch_id, period_start, period_end,
        )

        return {
            "branch_id": branch_id,
            "period_start": period_start,
            "period_end": period_end,
            "visit_count": len(in_period),
            "by_purpose": dict(by_purpose),
            "by_state": dict(by_state),
            "by_outcome": dict(by_outcome),
            "avg_queue_time_min": queue_stats.get("avg_queue_time_min"),
            "avg_service_time_min": queue_stats.get("avg_service_time_min"),
            "abandonment_rate_pct": queue_stats.get("abandonment_rate_pct"),
        }

    def nps_summary(
        self,
        branch_id: str,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """NPS score summary for a branch-period."""
        records = self._load()
        in_period = [
            r for r in records
            if r.get("branch_id") == branch_id
            and period_start <= r.get("queued_at", "") <= period_end
            and r.get("nps_score") is not None
        ]

        if not in_period:
            return {
                "branch_id": branch_id,
                "period_start": period_start,
                "period_end": period_end,
                "respondent_count": 0,
                "nps": None,
                "reason": "no_nps_responses",
            }

        scores = [int(r["nps_score"]) for r in in_period]
        n = len(scores)
        promoters = sum(1 for s in scores if s >= 9)
        detractors = sum(1 for s in scores if s <= 6)
        passives = n - promoters - detractors
        nps_value = ((promoters - detractors) / n) * 100

        return {
            "branch_id": branch_id,
            "period_start": period_start,
            "period_end": period_end,
            "respondent_count": n,
            "promoters": promoters,
            "passives": passives,
            "detractors": detractors,
            "nps": round(nps_value, 2),
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        capture = InteractionCaptureEngine(
            events_path=Path(tmpdir) / "ev.json",
        )
        engine = BranchInteractionEngine(
            visits_path=Path(tmpdir) / "vs.json",
            capture=capture,
        )

        # Test 1: log valid visit
        r = engine.log_branch_visit(
            "CUST-001",
            {"visit_id": "VST-001",
             "branch_id": "BR-NRB-CBD",
             "purpose": "DEPOSIT",
             "queued_at": "2026-04-15T09:00:00"},
            actor="branch_pipeline",
        )
        assert r["logged"], r

        # Test 2: invalid purpose rejected
        r = engine.log_branch_visit(
            "CUST-001",
            {"visit_id": "VST-X", "branch_id": "BR-NRB-CBD",
             "purpose": "INVALID",
             "queued_at": "2026-04-15T09:00:00"},
            actor="x",
        )
        assert not r["logged"]
        assert "invalid_purpose" in r["error"]

        # Test 3: state lifecycle QUEUED → BEING_SERVED → COMPLETED
        t = engine.transition_visit_state(
            "VST-001", "BEING_SERVED", actor="teller",
            reason="customer at counter", rm_or_teller_id="TLR-005",
            timestamp="2026-04-15T09:08:00",
        )
        assert t["transitioned"]
        t = engine.transition_visit_state(
            "VST-001", "COMPLETED", actor="teller",
            reason="deposit processed",
            timestamp="2026-04-15T09:18:00",
        )
        assert t["transitioned"]

        # Test 4: skip rejected (QUEUED → COMPLETED)
        engine.log_branch_visit(
            "CUST-002",
            {"visit_id": "VST-002", "branch_id": "BR-NRB-CBD",
             "purpose": "WITHDRAWAL",
             "queued_at": "2026-04-15T09:30:00"},
            actor="branch_pipeline",
        )
        t = engine.transition_visit_state(
            "VST-002", "COMPLETED", actor="teller", reason="skip",
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 5: abandonment
        engine.log_branch_visit(
            "CUST-003",
            {"visit_id": "VST-003", "branch_id": "BR-NRB-CBD",
             "purpose": "GENERAL_INQUIRY",
             "queued_at": "2026-04-15T09:45:00"},
            actor="branch_pipeline",
        )
        t = engine.transition_visit_state(
            "VST-003", "ABANDONED", actor="branch_pipeline",
            reason="customer left after 25 min wait",
        )
        assert t["transitioned"]

        # Test 6: record_visit_outcome — must be in terminal service state
        out = engine.record_visit_outcome(
            "VST-001", "RESOLVED", actor="teller", nps_score=9,
            notes="customer satisfied",
        )
        assert out["recorded"]

        # Test 7: cannot record outcome on non-terminal state
        out = engine.record_visit_outcome(
            "VST-002", "RESOLVED", actor="teller", nps_score=8,
        )
        assert not out["recorded"]
        assert "not_in_terminal_service_state" in out["error"]

        # Test 8: invalid NPS rejected
        engine.transition_visit_state("VST-002", "BEING_SERVED",
            actor="teller", reason="now serving",
            timestamp="2026-04-15T09:40:00")
        engine.transition_visit_state("VST-002", "COMPLETED",
            actor="teller", reason="done",
            timestamp="2026-04-15T09:55:00")
        out = engine.record_visit_outcome(
            "VST-002", "RESOLVED", actor="teller", nps_score=15,
        )
        assert not out["recorded"]
        assert "nps_out_of_0_10_range" in out["error"]

        # Test 9: invalid outcome rejected
        out = engine.record_visit_outcome(
            "VST-002", "INVALID", actor="teller",
        )
        assert not out["recorded"]

        # Test 10: queue_analytics
        # VST-001: queued 09:00, served 09:08 → queue=8 min (within target 10)
        # VST-001: served 09:08 to 09:18 → service=10 min
        # VST-002: queued 09:30, served 09:40 → queue=10 min (within target)
        # VST-002: served 09:40 to 09:55 → service=15 min
        # VST-003: ABANDONED
        qa = engine.queue_analytics(
            "BR-NRB-CBD", "2026-04-15", "2026-04-15T23:59:59",
        )
        assert qa["visit_count"] == 3
        assert qa["served_count"] == 2
        assert qa["abandoned_count"] == 1
        # Avg queue (VST-001 + VST-002) / 2 = (8 + 10) / 2 = 9
        assert qa["avg_queue_time_min"] == "9.00"
        # Avg service (10 + 15) / 2 = 12.5
        assert qa["avg_service_time_min"] == "12.50"
        # Abandonment rate 1/3 = 33.33
        assert qa["abandonment_rate_pct"] == "33.33"

        # Test 11: empty period
        empty = engine.queue_analytics(
            "BR-NRB-CBD", "2027-01-01", "2027-12-31",
        )
        assert empty["visit_count"] == 0
        assert empty["reason"] == "no_visits_in_period"

        # Test 12: branch_kpis
        kpis = engine.branch_kpis(
            "BR-NRB-CBD", "2026-04-15", "2026-04-15T23:59:59",
        )
        assert kpis["visit_count"] == 3
        assert "DEPOSIT" in kpis["by_purpose"]

        # Test 13: nps_summary
        engine.record_visit_outcome("VST-002", "PARTIALLY_RESOLVED",
                                       actor="teller", nps_score=4)
        nps = engine.nps_summary(
            "BR-NRB-CBD", "2026-04-15", "2026-04-15T23:59:59",
        )
        # 9 (promoter) + 4 (detractor) → NPS = (1-1)/2 * 100 = 0
        assert nps["respondent_count"] == 2
        assert nps["nps"] == 0

        # Test 14: empty NPS
        empty_nps = engine.nps_summary(
            "BR-X", "2026-04-15", "2026-04-15",
        )
        assert empty_nps["nps"] is None

    print("  ✅ branch_interaction self-test PASS")


if __name__ == "__main__":
    _self_test()
