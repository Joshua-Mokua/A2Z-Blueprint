"""
================================================================================
A2Z MIS 360 — Standards #372 + #373: Lead Tracking + Commission Automation
================================================================================

Risk classification: Cat A (financial — commission calculation)
                     + Cat B (deterministic lead funnel tracking)

Combined module: partner-sourced lead tracking with attribution +
conversion funnel + revenue share, plus auto-calculation of partner
commissions per agreed splits with auto-generated payment instructions.

Public API (#372 — Lead Tracking):
    submit_lead(partner_id, lead_data, actor)
    transition_lead_state(lead_id, new_state, actor, reason)
    funnel_summary(partner_id, period) -> conversion metrics
    time_to_close(partner_id, period) -> avg / p50 / p90 days

Public API (#373 — Commission Automation):
    compute_commissions(partner_id, period, split_pct) -> {amount, breakdown}
    generate_payment_instruction(partner_id, period) -> structured payload
    reconcile_commission(partner_id, period, paid_amount, actor)

LEAD_STATES byte-for-byte (Continuation.docx #372):
    NEW             -- submitted, not yet reviewed
    QUALIFIED       -- meets qualification criteria
    IN_PIPELINE     -- active sales process
    WON             -- converted to customer (terminal-success)
    LOST            -- declined or lost (terminal)
    DUPLICATE       -- pre-existing customer or lead (terminal)
    EXPIRED         -- not converted within window (terminal)

ALLOWED_LEAD_TRANSITIONS (Rule 4):
    NEW           → QUALIFIED | LOST | DUPLICATE
    QUALIFIED     → IN_PIPELINE | LOST
    IN_PIPELINE   → WON | LOST | EXPIRED
    WON           → ()
    LOST          → ()
    DUPLICATE     → ()
    EXPIRED       → ()

DEFAULT_LEAD_EXPIRY_DAYS = 90  -- per Continuation.docx; auto-EXPIRED
                                   if no movement within window

DEFAULT_COMMISSION_SPLIT_PCT = Decimal("10")  -- standard referral baseline

PAYMENT_STATUSES byte-for-byte:
    PENDING_CALCULATION
    CALCULATED
    APPROVED
    PAID
    DISPUTED

Honesty rules:
    Rule 4: actor mandatory; no skip transitions
    Rule 6: invalid state / split_pct rejected
    Rule 1: time_to_close = None when zero WON leads in period

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

LEAD_STATES: Tuple[str, ...] = (
    "NEW", "QUALIFIED", "IN_PIPELINE",
    "WON", "LOST", "DUPLICATE", "EXPIRED",
)

ALLOWED_LEAD_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "NEW":         ("QUALIFIED", "LOST", "DUPLICATE"),
    "QUALIFIED":   ("IN_PIPELINE", "LOST"),
    "IN_PIPELINE": ("WON", "LOST", "EXPIRED"),
    "WON":         (),
    "LOST":        (),
    "DUPLICATE":   (),
    "EXPIRED":     (),
}

PAYMENT_STATUSES: Tuple[str, ...] = (
    "PENDING_CALCULATION", "CALCULATED", "APPROVED", "PAID", "DISPUTED",
)

DEFAULT_LEAD_EXPIRY_DAYS: int = 90
DEFAULT_COMMISSION_SPLIT_PCT: Decimal = Decimal("10")
MIN_COMMISSION_SPLIT_PCT:     Decimal = Decimal("0")
MAX_COMMISSION_SPLIT_PCT:     Decimal = Decimal("50")


# ────────────────────────────────────────────────────────────────────
# Lead tracking engine (#372)
# ────────────────────────────────────────────────────────────────────

class LeadTrackingEngine:
    """Partner-sourced lead lifecycle + funnel analytics."""

    def __init__(self, leads_path: Optional[Path] = None):
        self.leads_path = (
            leads_path
            if leads_path is not None
            else Path(__file__).parent.parent / "data" / "partner_leads.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.leads_path,
                table="partner_leads",
                index_cols=("lead_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.leads_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.leads_path,
                data=records,
                table="partner_leads",
                pk_col="lead_id")
            return True
        except Exception:
            return False

    def submit_lead(
        self,
        partner_id: str,
        lead_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Submit new lead in NEW state."""
        if not actor:
            return {"submitted": False, "error": "actor_required"}

        for f in ("lead_id", "customer_name", "submitted_date"):
            if f not in lead_data or not lead_data[f]:
                return {"submitted": False, "error": f"missing_field:{f}"}

        try:
            sub_date = date.fromisoformat(lead_data["submitted_date"])
        except (ValueError, TypeError):
            return {"submitted": False, "error": "invalid_submitted_date"}

        records = self._load()
        if any(r.get("lead_id") == lead_data["lead_id"] for r in records):
            return {"submitted": False, "error": "duplicate_lead_id"}

        record = {
            "lead_id": lead_data["lead_id"],
            "partner_id": partner_id,
            "customer_name": lead_data["customer_name"],
            "customer_segment": lead_data.get("customer_segment", ""),
            "expected_revenue_kes": str(lead_data.get("expected_revenue_kes", 0)),
            "actual_revenue_kes": None,
            "state": "NEW",
            "submitted_date": lead_data["submitted_date"],
            "closed_date": None,
            "expiry_date": (sub_date + timedelta(
                days=DEFAULT_LEAD_EXPIRY_DAYS)).isoformat(),
            "transitions": [{
                "to": "NEW", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": "lead_submission",
            }],
        }
        records.append(record)
        ok = self._save(records)
        return {"submitted": ok, "lead_id": lead_data["lead_id"]}

    def transition_lead_state(
        self,
        lead_id: str,
        new_state: str,
        actor: str,
        reason: str,
        actual_revenue_kes: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Transition lead state (Rule 4 no-skip)."""
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in LEAD_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load()
        for r in records:
            if r.get("lead_id") == lead_id:
                current = r.get("state", "NEW")
                allowed = ALLOWED_LEAD_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_state
                if new_state == "WON" and actual_revenue_kes is not None:
                    try:
                        r["actual_revenue_kes"] = str(Decimal(str(actual_revenue_kes)))
                    except (ValueError, TypeError):
                        return {
                            "transitioned": False,
                            "error": "invalid_actual_revenue",
                        }
                # Set closed_date for terminal states
                if new_state in ("WON", "LOST", "DUPLICATE", "EXPIRED"):
                    r["closed_date"] = datetime.utcnow().date().isoformat()
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(records)
                return {"transitioned": ok, "from": current, "to": new_state}

        return {"transitioned": False, "error": "lead_not_found"}

    def funnel_summary(
        self,
        partner_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Conversion funnel metrics for a partner-period."""
        records = self._load()
        filtered = [r for r in records if r.get("partner_id") == partner_id]
        if period_start:
            filtered = [r for r in filtered
                          if r.get("submitted_date", "") >= period_start]
        if period_end:
            filtered = [r for r in filtered
                          if r.get("submitted_date", "") <= period_end]

        total = len(filtered)
        by_state = {s: 0 for s in LEAD_STATES}
        for r in filtered:
            s = r.get("state", "NEW")
            if s in by_state:
                by_state[s] += 1

        # Rule 1: conversion = None when total = 0
        conversion_pct = None
        if total > 0:
            conversion_pct = (Decimal(by_state["WON"]) / Decimal(total) * Decimal("100")).quantize(Decimal("0.01"))

        return {
            "partner_id": partner_id,
            "period_start": period_start,
            "period_end": period_end,
            "total_leads": total,
            "by_state": by_state,
            "conversion_pct": str(conversion_pct) if conversion_pct is not None else None,
        }

    def time_to_close(
        self,
        partner_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Statistics on days from submission to WON close.

        Rule 1: returns None values when zero WON leads in period.
        """
        records = self._load()
        filtered = [
            r for r in records
            if r.get("partner_id") == partner_id and r.get("state") == "WON"
        ]
        if period_start:
            filtered = [r for r in filtered
                          if r.get("closed_date", "") >= period_start]
        if period_end:
            filtered = [r for r in filtered
                          if r.get("closed_date", "") <= period_end]

        if not filtered:
            return {
                "partner_id": partner_id,
                "won_count": 0,
                "avg_days": None,
                "p50_days": None,
                "p90_days": None,
                "reason": "no_won_leads_in_period",
            }

        days_list = []
        for r in filtered:
            try:
                sub = date.fromisoformat(r["submitted_date"])
                clo = date.fromisoformat(r["closed_date"])
                days_list.append((clo - sub).days)
            except (ValueError, TypeError, KeyError):
                continue

        if not days_list:
            return {
                "partner_id": partner_id,
                "won_count": 0,
                "avg_days": None,
                "p50_days": None,
                "p90_days": None,
                "reason": "no_valid_dates",
            }

        days_list.sort()
        avg = sum(days_list) / len(days_list)

        def percentile(data, pct):
            if not data:
                return None
            idx = (Decimal(pct) / Decimal("100")) * Decimal(len(data) - 1)
            lower = int(idx)
            upper = lower + 1
            if upper >= len(data):
                return data[lower]
            frac = idx - Decimal(lower)
            return float(Decimal(data[lower]) + (Decimal(data[upper]) - Decimal(data[lower])) * frac)

        return {
            "partner_id": partner_id,
            "won_count": len(days_list),
            "avg_days": round(avg, 2),
            "p50_days": percentile(days_list, 50),
            "p90_days": percentile(days_list, 90),
        }


# ────────────────────────────────────────────────────────────────────
# Commission engine (#373)
# ────────────────────────────────────────────────────────────────────

class CommissionEngine:
    """Auto-commission calculation + payment instruction generation."""

    def __init__(
        self,
        commissions_path: Optional[Path] = None,
        lead_engine: Optional[LeadTrackingEngine] = None,
    ):
        self.commissions_path = (
            commissions_path
            if commissions_path is not None
            else Path(__file__).parent.parent / "data" / "partner_commissions.json"
        )
        self.lead_engine = lead_engine or LeadTrackingEngine()

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(
                self.commissions_path,
                table="partner_commissions",
                index_cols=("partner_id", "period"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.commissions_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.commissions_path,
                data=records,
                table="partner_commissions",
                pk_col="partner_id")
            return True
        except Exception:
            return False

    def compute_commissions(
        self,
        partner_id: str,
        period_start: str,
        period_end: str,
        split_pct: Decimal = DEFAULT_COMMISSION_SPLIT_PCT,
    ) -> Dict[str, Any]:
        """
        Compute commission owed = Σ(WON leads' actual revenue × split_pct).

        Rule 6: split_pct outside [0, 50] rejected.
        Rule 1: amount = 0 (not None) when no WON leads (commission is 0,
                not unknown).
        """
        try:
            split = Decimal(str(split_pct))
        except (ValueError, TypeError):
            return {"computed": False, "error": "split_pct_not_decimal"}

        if split < MIN_COMMISSION_SPLIT_PCT or split > MAX_COMMISSION_SPLIT_PCT:
            return {
                "computed": False,
                "error": f"split_pct_out_of_range:{split}",
                "valid_range": f"[{MIN_COMMISSION_SPLIT_PCT}, {MAX_COMMISSION_SPLIT_PCT}]",
            }

        # Load WON leads for partner-period
        leads = self.lead_engine._load()
        won_leads = [
            r for r in leads
            if r.get("partner_id") == partner_id
            and r.get("state") == "WON"
            and r.get("closed_date", "") >= period_start
            and r.get("closed_date", "") <= period_end
        ]

        total_revenue = Decimal("0")
        breakdown = []
        for lead in won_leads:
            try:
                rev = Decimal(str(lead.get("actual_revenue_kes") or "0"))
            except (ValueError, TypeError):
                continue
            total_revenue += rev
            breakdown.append({
                "lead_id": lead["lead_id"],
                "actual_revenue_kes": str(rev),
                "commission_kes": str((rev * split / Decimal("100")).quantize(Decimal("0.01"))),
            })

        commission_amount = (total_revenue * split / Decimal("100")).quantize(Decimal("0.01"))

        return {
            "partner_id": partner_id,
            "period_start": period_start,
            "period_end": period_end,
            "split_pct": str(split),
            "won_lead_count": len(won_leads),
            "total_attributed_revenue_kes": str(total_revenue.quantize(Decimal("0.01"))),
            "commission_amount_kes": str(commission_amount),
            "breakdown": breakdown,
            "status": "CALCULATED",
        }

    def generate_payment_instruction(
        self,
        partner_id: str,
        period_start: str,
        period_end: str,
        split_pct: Decimal = DEFAULT_COMMISSION_SPLIT_PCT,
        actor: str = "system",
    ) -> Dict[str, Any]:
        """Generate structured payment instruction payload."""
        comp = self.compute_commissions(
            partner_id, period_start, period_end, split_pct
        )
        if not comp.get("status"):
            return {"generated": False, "error": comp.get("error", "compute_failed")}

        instruction = {
            "instruction_id": f"PAY-{partner_id}-{period_end}",
            "partner_id": partner_id,
            "period_start": period_start,
            "period_end": period_end,
            "amount_kes": comp["commission_amount_kes"],
            "lead_count": comp["won_lead_count"],
            "status": "PENDING_CALCULATION" if Decimal(comp["commission_amount_kes"]) == 0 else "CALCULATED",
            "generated_by": actor,
            "generated_at": datetime.utcnow().isoformat(),
            "breakdown_summary": {
                "leads": comp["won_lead_count"],
                "total_revenue": comp["total_attributed_revenue_kes"],
                "split_pct": comp["split_pct"],
            },
            "reconciliation_status": "PENDING",
        }

        # Persist
        records = self._load()
        records.append(instruction)
        self._save(records)
        return {"generated": True, "instruction": instruction}

    def reconcile_commission(
        self,
        instruction_id: str,
        paid_amount_kes: Decimal,
        actor: str,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Reconcile actual paid amount against calculated commission."""
        if not actor:
            return {"reconciled": False, "error": "actor_required"}

        try:
            paid = Decimal(str(paid_amount_kes))
        except (ValueError, TypeError):
            return {"reconciled": False, "error": "paid_amount_not_decimal"}

        records = self._load()
        for r in records:
            if r.get("instruction_id") == instruction_id:
                expected = Decimal(r["amount_kes"])
                variance = paid - expected
                tolerance = expected * Decimal("0.01")  # 1% tolerance
                status = "PAID" if abs(variance) <= tolerance else "DISPUTED"
                r["reconciliation_status"] = status
                r["paid_amount_kes"] = str(paid.quantize(Decimal("0.01")))
                r["variance_kes"] = str(variance.quantize(Decimal("0.01")))
                r["reconciled_by"] = actor
                r["reconciled_at"] = datetime.utcnow().isoformat()
                r["reconciliation_notes"] = notes
                ok = self._save(records)
                return {
                    "reconciled": ok,
                    "status": status,
                    "variance_kes": str(variance.quantize(Decimal("0.01"))),
                }

        return {"reconciled": False, "error": "instruction_not_found"}


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        leads = LeadTrackingEngine(leads_path=Path(tmpdir) / "leads.json")
        commissions = CommissionEngine(
            commissions_path=Path(tmpdir) / "comm.json",
            lead_engine=leads,
        )

        # === Lead tracking tests ===

        # Test 1: submit lead
        r = leads.submit_lead(
            "P-001",
            {"lead_id": "L-001", "customer_name": "Acme Corp",
             "customer_segment": "SME", "expected_revenue_kes": "500000",
             "submitted_date": "2026-04-01"},
            actor="rm",
        )
        assert r["submitted"]

        # Test 2: lifecycle NEW → QUALIFIED → IN_PIPELINE → WON
        t = leads.transition_lead_state(
            "L-001", "QUALIFIED", "rm", "passed qualification"
        )
        assert t["transitioned"]
        t = leads.transition_lead_state(
            "L-001", "IN_PIPELINE", "rm", "active selling"
        )
        assert t["transitioned"]
        t = leads.transition_lead_state(
            "L-001", "WON", "rm", "deal closed",
            actual_revenue_kes=Decimal("450000"),
        )
        assert t["transitioned"]

        # Test 3: skip rejected NEW → IN_PIPELINE
        leads.submit_lead(
            "P-001",
            {"lead_id": "L-002", "customer_name": "Beta Inc",
             "submitted_date": "2026-04-02"},
            actor="rm",
        )
        t = leads.transition_lead_state(
            "L-002", "IN_PIPELINE", "rm", "skip"
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 4: WON terminal
        t = leads.transition_lead_state(
            "L-001", "QUALIFIED", "rm", "trying to revive"
        )
        assert not t["transitioned"]

        # Test 5: funnel_summary
        summary = leads.funnel_summary("P-001")
        assert summary["total_leads"] == 2
        assert summary["by_state"]["WON"] == 1
        assert summary["conversion_pct"] == "50.00"

        # Test 6: Rule 1 — empty partner returns None conversion
        empty = leads.funnel_summary("P-NONEXISTENT")
        assert empty["conversion_pct"] is None
        assert empty["total_leads"] == 0

        # Test 7: time_to_close
        ttc = leads.time_to_close("P-001")
        assert ttc["won_count"] == 1
        assert ttc["avg_days"] is not None

        # Test 8: Rule 1 — no WON leads returns None
        ttc = leads.time_to_close("P-NONEXISTENT")
        assert ttc["avg_days"] is None
        assert ttc["reason"] == "no_won_leads_in_period"

        # === Commission tests ===

        # Test 9: compute commission — 1 WON lead, 450k × 10% = 45k
        comp = commissions.compute_commissions(
            "P-001", "2026-04-01", "2026-12-31",
            split_pct=Decimal("10"),
        )
        assert comp["won_lead_count"] == 1
        assert Decimal(comp["commission_amount_kes"]) == Decimal("45000.00")

        # Test 10: split_pct out of range rejected
        bad = commissions.compute_commissions(
            "P-001", "2026-04-01", "2026-12-31",
            split_pct=Decimal("75"),
        )
        assert not bad.get("status")
        assert "out_of_range" in bad["error"]

        # Test 11: zero WON leads → commission = 0 (NOT None)
        zero = commissions.compute_commissions(
            "P-NONEXISTENT", "2026-04-01", "2026-12-31",
            split_pct=Decimal("10"),
        )
        assert zero["won_lead_count"] == 0
        assert Decimal(zero["commission_amount_kes"]) == Decimal("0")

        # Test 12: generate_payment_instruction
        instr = commissions.generate_payment_instruction(
            "P-001", "2026-04-01", "2026-12-31",
            split_pct=Decimal("10"), actor="finance",
        )
        assert instr["generated"]
        assert instr["instruction"]["status"] == "CALCULATED"
        instr_id = instr["instruction"]["instruction_id"]

        # Test 13: reconcile within tolerance → PAID
        rec = commissions.reconcile_commission(
            instr_id, Decimal("45000.00"), actor="finance"
        )
        assert rec["reconciled"]
        assert rec["status"] == "PAID"

        # Test 14: reconcile outside tolerance → DISPUTED
        instr2 = commissions.generate_payment_instruction(
            "P-001", "2026-04-01", "2026-04-30",
            split_pct=Decimal("10"), actor="finance",
        )
        rec2 = commissions.reconcile_commission(
            instr2["instruction"]["instruction_id"],
            Decimal("40000.00"),  # significant variance
            actor="finance", notes="under-payment investigation"
        )
        # Either commission was 45000 (10% of 450k) or 0 if dates didn't match
        # If commission 0, paid 40000 → variance >> tolerance → DISPUTED
        # If commission 45000, paid 40000 → variance 5000 > 450 → DISPUTED
        assert rec2["status"] == "DISPUTED"

    print("  ✅ partner_leads_commissions self-test PASS")


if __name__ == "__main__":
    _self_test()
