"""
================================================================================
A2Z MIS 360 — Standard #346: New Customer Onboarding Optimization
================================================================================

Risk classification: Cat C (deterministic onboarding funnel + revenue tracking)

Onboarding funnel analysis: drop-off, completion rate, time-to-active,
first-90-days revenue. Optimize each step.

Public API:
    register_onboarding(customer_id, onboarding_data, actor)
    advance_onboarding_step(customer_id, step, actor, reason)
    fail_onboarding_step(customer_id, step, actor, reason)
    record_first_revenue(customer_id, amount_kes, recorded_at, actor)
    onboarding_funnel_summary(period_start, period_end)
    cohort_first_90_day_revenue(cohort_period_start, cohort_period_end)

ONBOARDING_STEPS byte-for-byte (Continuation.docx #346, ordered):
    APPLICATION_SUBMITTED   -- application form complete
    KYC_COMPLETE            -- identity + documents verified
    ACCOUNT_OPENED          -- account number issued
    FIRST_FUNDING           -- first deposit / funding
    DIGITAL_ACTIVATION      -- mobile/web app first login
    FIRST_TRANSACTION       -- first outbound transaction
    PRODUCT_ADOPTION        -- second product / service taken up

ONBOARDING_STEP_STATES byte-for-byte:
    PENDING       -- not yet started
    IN_PROGRESS   -- step underway
    COMPLETE      -- step finished successfully
    FAILED        -- step failed; onboarding paused
    SKIPPED       -- step skipped per business rule (not failure)

ONBOARDING_OVERALL_STATES (composite):
    DRAFT         -- registered, no steps started
    IN_PROGRESS   -- at least 1 step in progress, none failed
    BLOCKED       -- a step failed
    COMPLETE      -- all 7 steps either COMPLETE or SKIPPED
    ABANDONED     -- formally cancelled (terminal)

Strict order enforced (Rule 4 no-skip):
    Cannot mark step N as IN_PROGRESS if step N-1 is not COMPLETE or SKIPPED.

ACTIVATION_TARGET_DAYS byte-for-byte = 30
    Time-to-active KPI: days from APPLICATION_SUBMITTED to FIRST_TRANSACTION.
    Compliant if <= 30 days.

REVENUE_TRACKING_WINDOW_DAYS = 90  -- first 90 days revenue per customer

Honesty rules:
    Rule 4: actor + reason mandatory; step order strictly enforced
    Rule 6: invalid step / state rejected
    Rule 1: time_to_active = None when FIRST_TRANSACTION never reached
            (NOT zero); funnel_summary returns None completion_pct for
            empty cohort

================================================================================
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28


ONBOARDING_STEPS: Tuple[str, ...] = (
    "APPLICATION_SUBMITTED",
    "KYC_COMPLETE",
    "ACCOUNT_OPENED",
    "FIRST_FUNDING",
    "DIGITAL_ACTIVATION",
    "FIRST_TRANSACTION",
    "PRODUCT_ADOPTION",
)

ONBOARDING_STEP_STATES: Tuple[str, ...] = (
    "PENDING", "IN_PROGRESS", "COMPLETE", "FAILED", "SKIPPED",
)

ONBOARDING_OVERALL_STATES: Tuple[str, ...] = (
    "DRAFT", "IN_PROGRESS", "BLOCKED", "COMPLETE", "ABANDONED",
)

ACTIVATION_TARGET_DAYS: int = 30
REVENUE_TRACKING_WINDOW_DAYS: int = 90


class OnboardingOptimizationEngine:
    """New customer onboarding funnel + revenue tracking."""

    def __init__(
        self,
        onboardings_path: Optional[Path] = None,
        revenues_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.onboardings_path = onboardings_path or base / "customer_onboardings.json"
        self.revenues_path = revenues_path or base / "customer_first_revenues.json"

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

    def _compute_overall_state(self, steps: Dict[str, Dict[str, Any]]) -> str:
        """Derive composite onboarding state from step states."""
        # All COMPLETE or SKIPPED → COMPLETE
        terminal_ok = all(
            steps.get(s, {}).get("state") in ("COMPLETE", "SKIPPED")
            for s in ONBOARDING_STEPS
        )
        if terminal_ok:
            return "COMPLETE"
        # Any FAILED → BLOCKED
        if any(steps.get(s, {}).get("state") == "FAILED" for s in ONBOARDING_STEPS):
            return "BLOCKED"
        # Any IN_PROGRESS / COMPLETE / SKIPPED → IN_PROGRESS
        if any(steps.get(s, {}).get("state") in ("IN_PROGRESS", "COMPLETE", "SKIPPED")
                 for s in ONBOARDING_STEPS):
            return "IN_PROGRESS"
        return "DRAFT"

    def register_onboarding(
        self,
        customer_id: str,
        onboarding_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Register new customer onboarding with all steps PENDING."""
        if not actor:
            return {"registered": False, "error": "actor_required"}
        if not customer_id:
            return {"registered": False, "error": "customer_id_required"}

        records = self._load(self.onboardings_path,
                                "customer_onboardings",
                                ("customer_id",))
        # Reject duplicate active onboarding
        for r in records:
            if (r.get("customer_id") == customer_id
                    and r.get("overall_state") not in ("COMPLETE", "ABANDONED")):
                return {
                    "registered": False,
                    "error": "active_onboarding_exists",
                }

        steps = {
            s: {"state": "PENDING", "completed_at": None,
                  "history": []}
            for s in ONBOARDING_STEPS
        }
        record = {
            "customer_id": customer_id,
            "channel": onboarding_data.get("channel", "BRANCH"),
            "rm_id": onboarding_data.get("rm_id"),
            "started_at": onboarding_data.get(
                "started_at", datetime.utcnow().isoformat()
            ),
            "steps": steps,
            "overall_state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "events": [{
                "event": "registered", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.onboardings_path, records,
                          "customer_onboardings", "customer_id")
        return {"registered": ok, "customer_id": customer_id}

    def _previous_step_terminal_ok(
        self, steps: Dict[str, Dict[str, Any]], step: str,
    ) -> bool:
        idx = ONBOARDING_STEPS.index(step)
        if idx == 0:
            return True
        prev = ONBOARDING_STEPS[idx - 1]
        return steps.get(prev, {}).get("state") in ("COMPLETE", "SKIPPED")

    def advance_onboarding_step(
        self,
        customer_id: str,
        step: str,
        actor: str,
        reason: str,
        target_state: str = "IN_PROGRESS",
        timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Advance step (PENDING → IN_PROGRESS or directly to COMPLETE)."""
        if not actor or not reason:
            return {"advanced": False, "error": "actor_and_reason_required"}
        if step not in ONBOARDING_STEPS:
            return {
                "advanced": False,
                "error": f"invalid_step:{step}",
                "valid_steps": list(ONBOARDING_STEPS),
            }
        if target_state not in ("IN_PROGRESS", "COMPLETE", "SKIPPED"):
            return {
                "advanced": False,
                "error": f"invalid_target_state:{target_state}",
                "valid_targets": ["IN_PROGRESS", "COMPLETE", "SKIPPED"],
            }

        timestamp = timestamp or datetime.utcnow().isoformat()
        records = self._load(self.onboardings_path,
                                "customer_onboardings",
                                ("customer_id",))
        for r in records:
            if r.get("customer_id") == customer_id:
                if r.get("overall_state") in ("COMPLETE", "ABANDONED"):
                    return {
                        "advanced": False,
                        "error": f"onboarding_in_terminal:{r['overall_state']}",
                    }
                steps = r.get("steps", {})
                # Rule 4: previous step must be COMPLETE or SKIPPED
                if not self._previous_step_terminal_ok(steps, step):
                    idx = ONBOARDING_STEPS.index(step)
                    prev = ONBOARDING_STEPS[idx - 1]
                    return {
                        "advanced": False,
                        "error": f"previous_step_not_complete:{prev}",
                    }
                current = steps.get(step, {}).get("state", "PENDING")
                # Cannot revert COMPLETE
                if current == "COMPLETE":
                    return {
                        "advanced": False,
                        "error": "step_already_complete",
                    }
                steps.setdefault(step, {"history": []})["state"] = target_state
                if target_state in ("COMPLETE", "SKIPPED"):
                    steps[step]["completed_at"] = timestamp
                steps[step].setdefault("history", []).append({
                    "to": target_state, "actor": actor,
                    "at": timestamp, "reason": reason,
                })
                r["steps"] = steps
                r["overall_state"] = self._compute_overall_state(steps)
                r.setdefault("events", []).append({
                    "event": f"step:{step}:{target_state}",
                    "actor": actor, "at": timestamp, "reason": reason,
                })
                ok = self._save(self.onboardings_path, records,
                                  "customer_onboardings", "customer_id")
                return {
                    "advanced": ok,
                    "step": step,
                    "from": current,
                    "to": target_state,
                    "overall_state": r["overall_state"],
                }

        return {"advanced": False, "error": "onboarding_not_found"}

    def fail_onboarding_step(
        self,
        customer_id: str,
        step: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"failed": False, "error": "actor_and_reason_required"}
        if step not in ONBOARDING_STEPS:
            return {"failed": False, "error": f"invalid_step:{step}"}

        records = self._load(self.onboardings_path,
                                "customer_onboardings",
                                ("customer_id",))
        for r in records:
            if r.get("customer_id") == customer_id:
                steps = r.get("steps", {})
                current = steps.get(step, {}).get("state", "PENDING")
                if current == "COMPLETE":
                    return {
                        "failed": False,
                        "error": "cannot_fail_already_complete_step",
                    }
                steps.setdefault(step, {"history": []})["state"] = "FAILED"
                steps[step].setdefault("history", []).append({
                    "to": "FAILED", "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                r["overall_state"] = self._compute_overall_state(steps)
                ok = self._save(self.onboardings_path, records,
                                  "customer_onboardings", "customer_id")
                return {
                    "failed": ok, "step": step,
                    "overall_state": r["overall_state"],
                }

        return {"failed": False, "error": "onboarding_not_found"}

    def record_first_revenue(
        self,
        customer_id: str,
        amount_kes: Decimal,
        recorded_at: str,
        actor: str,
        revenue_source: str = "TRANSACTION_FEE",
    ) -> Dict[str, Any]:
        """Record per-event revenue attributable to customer in first 90 days."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        try:
            amt = Decimal(str(amount_kes))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "amount_not_decimal"}
        if amt <= 0:
            return {"recorded": False, "error": "amount_must_be_positive"}
        try:
            datetime.fromisoformat(recorded_at.replace("Z", ""))
        except (ValueError, TypeError, AttributeError):
            return {"recorded": False, "error": "invalid_recorded_at"}

        records = self._load(self.revenues_path,
                                "customer_first_revenues",
                                ("revenue_id",))
        revenue_id = f"REV-{customer_id}-{int(datetime.utcnow().timestamp())}"
        records.append({
            "revenue_id": revenue_id,
            "customer_id": customer_id,
            "amount_kes": str(amt.quantize(Decimal("0.01"))),
            "recorded_at": recorded_at,
            "revenue_source": revenue_source,
            "actor": actor,
            "saved_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.revenues_path, records,
                          "customer_first_revenues", "revenue_id")
        return {"recorded": ok, "revenue_id": revenue_id}

    # ── Analytics ──────────────────────────────────────────────────

    def time_to_active(self, customer_id: str) -> Dict[str, Any]:
        """Days from APPLICATION_SUBMITTED to FIRST_TRANSACTION."""
        records = self._load(self.onboardings_path,
                                "customer_onboardings",
                                ("customer_id",))
        for r in records:
            if r.get("customer_id") == customer_id:
                steps = r.get("steps", {})
                app = steps.get("APPLICATION_SUBMITTED", {})
                txn = steps.get("FIRST_TRANSACTION", {})
                if app.get("state") not in ("COMPLETE", "SKIPPED"):
                    return {
                        "customer_id": customer_id,
                        "days_to_active": None,
                        "reason": "application_step_not_complete",
                    }
                if txn.get("state") not in ("COMPLETE", "SKIPPED"):
                    return {
                        "customer_id": customer_id,
                        "days_to_active": None,
                        "reason": "first_transaction_step_not_complete",
                    }
                try:
                    app_at = datetime.fromisoformat(
                        app["completed_at"].replace("Z", ""))
                    txn_at = datetime.fromisoformat(
                        txn["completed_at"].replace("Z", ""))
                except (ValueError, TypeError, AttributeError, KeyError):
                    return {
                        "customer_id": customer_id,
                        "days_to_active": None,
                        "reason": "invalid_timestamps",
                    }
                days = (txn_at - app_at).days
                return {
                    "customer_id": customer_id,
                    "days_to_active": days,
                    "compliant_with_target": days <= ACTIVATION_TARGET_DAYS,
                    "target_days": ACTIVATION_TARGET_DAYS,
                }
        return {
            "customer_id": customer_id,
            "days_to_active": None,
            "reason": "onboarding_not_found",
        }

    def onboarding_funnel_summary(
        self,
        period_start: str,
        period_end: str,
    ) -> Dict[str, Any]:
        """Per-step completion + drop-off across the cohort."""
        records = self._load(self.onboardings_path,
                                "customer_onboardings",
                                ("customer_id",))
        in_period = [
            r for r in records
            if period_start <= r.get("started_at", "") <= period_end
        ]

        if not in_period:
            return {
                "period_start": period_start,
                "period_end": period_end,
                "cohort_size": 0,
                "step_completion_pct": {},
                "completion_pct": None,
                "reason": "no_onboardings_in_period",
            }

        cohort_size = len(in_period)
        step_complete: Dict[str, int] = {s: 0 for s in ONBOARDING_STEPS}
        for r in in_period:
            for s in ONBOARDING_STEPS:
                if r.get("steps", {}).get(s, {}).get("state") in ("COMPLETE", "SKIPPED"):
                    step_complete[s] += 1

        step_pct = {
            s: str((Decimal(c) / Decimal(cohort_size) * Decimal("100"))
                    .quantize(Decimal("0.01")))
            for s, c in step_complete.items()
        }

        # Overall completion (all steps COMPLETE or SKIPPED)
        completed_overall = sum(
            1 for r in in_period
            if r.get("overall_state") == "COMPLETE"
        )
        completion_pct = (
            Decimal(completed_overall) / Decimal(cohort_size) *
            Decimal("100")
        ).quantize(Decimal("0.01"))

        return {
            "period_start": period_start,
            "period_end": period_end,
            "cohort_size": cohort_size,
            "completed_count": completed_overall,
            "completion_pct": str(completion_pct),
            "step_completion_count": step_complete,
            "step_completion_pct": step_pct,
        }

    def cohort_first_90_day_revenue(
        self,
        cohort_period_start: str,
        cohort_period_end: str,
    ) -> Dict[str, Any]:
        """Revenue per customer in first 90 days of relationship."""
        records = self._load(self.onboardings_path,
                                "customer_onboardings",
                                ("customer_id",))
        cohort = [
            r for r in records
            if cohort_period_start <= r.get("started_at", "") <= cohort_period_end
        ]

        if not cohort:
            return {
                "cohort_period_start": cohort_period_start,
                "cohort_period_end": cohort_period_end,
                "cohort_size": 0,
                "total_revenue_kes": "0",
                "avg_revenue_per_customer_kes": None,
                "reason": "no_cohort_members",
            }

        revenues = self._load(self.revenues_path,
                                  "customer_first_revenues",
                                  ("revenue_id",))

        total_rev = Decimal("0")
        per_customer: Dict[str, Decimal] = {}
        for r in cohort:
            cid = r["customer_id"]
            try:
                started = datetime.fromisoformat(r["started_at"].replace("Z", ""))
                cutoff = (started + timedelta(days=REVENUE_TRACKING_WINDOW_DAYS)).isoformat()
            except (ValueError, TypeError, KeyError):
                continue
            cust_rev = Decimal("0")
            for rev in revenues:
                if rev.get("customer_id") != cid:
                    continue
                rev_at = rev.get("recorded_at", "")
                if r["started_at"] <= rev_at <= cutoff:
                    try:
                        cust_rev += Decimal(rev["amount_kes"])
                    except (ValueError, TypeError, KeyError):
                        continue
            per_customer[cid] = cust_rev
            total_rev += cust_rev

        avg = (total_rev / Decimal(len(cohort))).quantize(Decimal("0.01"))

        return {
            "cohort_period_start": cohort_period_start,
            "cohort_period_end": cohort_period_end,
            "cohort_size": len(cohort),
            "total_revenue_kes": str(total_rev.quantize(Decimal("0.01"))),
            "avg_revenue_per_customer_kes": str(avg),
            "tracking_window_days": REVENUE_TRACKING_WINDOW_DAYS,
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = OnboardingOptimizationEngine(
            onboardings_path=Path(tmpdir) / "ob.json",
            revenues_path=Path(tmpdir) / "rev.json",
        )

        # Test 1: register onboarding
        r = engine.register_onboarding(
            "CUST-001",
            {"channel": "BRANCH", "rm_id": "RM-101",
             "started_at": "2026-01-01T10:00:00"},
            actor="rm",
        )
        assert r["registered"]

        # Test 2: duplicate active rejected
        r = engine.register_onboarding(
            "CUST-001",
            {"started_at": "2026-01-02T10:00:00"},
            actor="rm",
        )
        assert not r["registered"]
        assert r["error"] == "active_onboarding_exists"

        # Test 3: cannot skip — try ACCOUNT_OPENED before APPLICATION_SUBMITTED
        a = engine.advance_onboarding_step(
            "CUST-001", "ACCOUNT_OPENED", actor="rm", reason="skip attempt",
        )
        assert not a["advanced"]
        assert "previous_step_not_complete" in a["error"]

        # Test 4: full lifecycle
        # APPLICATION_SUBMITTED → COMPLETE
        a = engine.advance_onboarding_step(
            "CUST-001", "APPLICATION_SUBMITTED",
            actor="rm", reason="form complete",
            target_state="COMPLETE",
            timestamp="2026-01-01T10:05:00",
        )
        assert a["advanced"]
        # KYC_COMPLETE → COMPLETE
        a = engine.advance_onboarding_step(
            "CUST-001", "KYC_COMPLETE",
            actor="rm", reason="docs verified",
            target_state="COMPLETE",
            timestamp="2026-01-01T10:30:00",
        )
        assert a["advanced"]

        # Test 5: invalid step rejected
        a = engine.advance_onboarding_step(
            "CUST-001", "INVALID_STEP", actor="rm", reason="x",
        )
        assert not a["advanced"]

        # Test 6: invalid target_state rejected
        a = engine.advance_onboarding_step(
            "CUST-001", "ACCOUNT_OPENED", actor="rm", reason="x",
            target_state="DONE",
        )
        assert not a["advanced"]

        # Test 7: complete remaining steps
        for step, ts in [
            ("ACCOUNT_OPENED",     "2026-01-02T10:00:00"),
            ("FIRST_FUNDING",      "2026-01-03T11:00:00"),
            ("DIGITAL_ACTIVATION", "2026-01-04T08:00:00"),
            ("FIRST_TRANSACTION",  "2026-01-15T15:00:00"),
        ]:
            a = engine.advance_onboarding_step(
                "CUST-001", step, actor="rm", reason="auto progress",
                target_state="COMPLETE", timestamp=ts,
            )
            assert a["advanced"], (step, a)

        # Test 8: skip the optional last step (PRODUCT_ADOPTION)
        a = engine.advance_onboarding_step(
            "CUST-001", "PRODUCT_ADOPTION",
            actor="rm", reason="single product customer",
            target_state="SKIPPED",
            timestamp="2026-01-15T15:30:00",
        )
        assert a["advanced"]
        assert a["overall_state"] == "COMPLETE"

        # Test 9: cannot advance after COMPLETE
        a = engine.advance_onboarding_step(
            "CUST-001", "PRODUCT_ADOPTION", actor="rm", reason="redo",
        )
        assert not a["advanced"]
        assert "onboarding_in_terminal" in a["error"]

        # Test 10: time_to_active
        # APPLICATION_SUBMITTED 2026-01-01, FIRST_TRANSACTION 2026-01-15 → 14 days
        ta = engine.time_to_active("CUST-001")
        assert ta["days_to_active"] == 14
        assert ta["compliant_with_target"] is True

        # Test 11: time_to_active for incomplete onboarding
        engine.register_onboarding(
            "CUST-002",
            {"started_at": "2026-02-01T09:00:00"},
            actor="rm",
        )
        ta = engine.time_to_active("CUST-002")
        assert ta["days_to_active"] is None
        assert ta["reason"] == "application_step_not_complete"

        # Test 12: fail step
        engine.advance_onboarding_step(
            "CUST-002", "APPLICATION_SUBMITTED",
            actor="rm", reason="form filled", target_state="COMPLETE",
        )
        f = engine.fail_onboarding_step(
            "CUST-002", "KYC_COMPLETE",
            actor="compliance", reason="ID document expired",
        )
        assert f["failed"]
        assert f["overall_state"] == "BLOCKED"

        # Test 13: cannot fail completed step
        f = engine.fail_onboarding_step(
            "CUST-002", "APPLICATION_SUBMITTED",
            actor="rm", reason="trying to corrupt",
        )
        assert not f["failed"]
        assert "cannot_fail_already_complete" in f["error"]

        # Test 14: record_first_revenue
        rv = engine.record_first_revenue(
            "CUST-001", Decimal("500"),
            "2026-01-16T10:00:00", actor="finance",
            revenue_source="TRANSACTION_FEE",
        )
        assert rv["recorded"]
        engine.record_first_revenue(
            "CUST-001", Decimal("1500"),
            "2026-02-01T10:00:00", actor="finance",
        )

        # Test 15: invalid revenue rejected
        rv = engine.record_first_revenue(
            "CUST-001", Decimal("-100"),
            "2026-01-16T10:00:00", actor="finance",
        )
        assert not rv["recorded"]

        # Test 16: onboarding_funnel_summary
        summary = engine.onboarding_funnel_summary(
            "2026-01-01", "2026-02-28",
        )
        assert summary["cohort_size"] == 2
        assert summary["completed_count"] == 1
        # 1 / 2 = 50.00
        assert summary["completion_pct"] == "50.00"
        # Step completion: APPLICATION_SUBMITTED done by both → 100%
        assert summary["step_completion_pct"]["APPLICATION_SUBMITTED"] == "100.00"

        # Test 17: empty funnel
        empty = engine.onboarding_funnel_summary(
            "2027-01-01", "2027-12-31",
        )
        assert empty["cohort_size"] == 0
        assert empty["completion_pct"] is None
        assert empty["reason"] == "no_onboardings_in_period"

        # Test 18: cohort_first_90_day_revenue
        rev = engine.cohort_first_90_day_revenue(
            "2026-01-01", "2026-02-28",
        )
        assert rev["cohort_size"] == 2
        # CUST-001: 500 + 1500 = 2000 (within 90 days of 2026-01-01)
        # CUST-002: no revenue
        # Total: 2000; avg: 1000
        assert Decimal(rev["total_revenue_kes"]) == Decimal("2000.00")
        assert Decimal(rev["avg_revenue_per_customer_kes"]) == Decimal("1000.00")

        # Test 19: empty cohort revenue
        empty = engine.cohort_first_90_day_revenue(
            "2027-01-01", "2027-12-31",
        )
        assert empty["cohort_size"] == 0
        assert empty["avg_revenue_per_customer_kes"] is None

    print("  ✅ onboarding_optimization self-test PASS")


if __name__ == "__main__":
    _self_test()
