"""
================================================================================
A2Z MIS 360 — Standard #99: Financial Close & Reconciliation Discipline
================================================================================

Risk classification: Cat B (deterministic close calendar + reconciliation)

Provides:
    - close_state_transition(...)       -- close state machine
    - close_calendar_milestone(...)     -- T+N day milestones
    - reconciliation_variance(...)      -- absolute + pct variance
    - materiality_check(...)            -- variance vs threshold
    - signoff_complete(...)             -- 3-tier signoff verification

6 CLOSE_STATES byte-for-byte:
    OPEN, IN_CLOSE, RECONCILING, REVIEWED, CLOSED, REOPENED

ALLOWED_CLOSE_TRANSITIONS byte-for-byte:
    OPEN          → IN_CLOSE
    IN_CLOSE      → RECONCILING, OPEN
    RECONCILING   → REVIEWED, IN_CLOSE
    REVIEWED      → CLOSED, RECONCILING
    CLOSED        → REOPENED
    REOPENED      → IN_CLOSE

5 CLOSE_CALENDAR_MILESTONES byte-for-byte (days after period-end):
    TXN_CUTOFF      = 1     -- T+1 transactions cutoff
    GL_CLOSE        = 5     -- T+5 GL ledger close
    RECON_COMPLETE  = 10    -- T+10 all reconciliations complete
    REVIEW_COMPLETE = 12    -- T+12 review signoff
    MGMT_REPORT     = 15    -- T+15 management reporting due

5 RECONCILIATION_TYPES byte-for-byte:
    GL_TO_SUBLEDGER, BANK_RECON, INTERCOMPANY, SUSPENSE_ACCOUNT, NOSTRO_VOSTRO

5 ADJUSTMENT_TYPES byte-for-byte:
    ACCRUALS, PROVISIONS, REVALUATION, AMORTIZATION, DEPRECIATION

3 SIGNOFF_LEVELS byte-for-byte:
    PREPARER, REVIEWER, APPROVER

Materiality threshold byte-for-byte:
    MATERIALITY_THRESHOLD_PCT = 0.1   -- 0.1% of GL balance
    SUSPENSE_ZERO_TOLERANCE_KES = 0   -- suspense MUST be zero at close

Honesty rules applied:
    Rule 1: variance_pct=None when gl_balance=0 (denominator)
            materiality_check=None when variance missing
    Rule 6: invalid close state transitions REJECTED (fail closed)
            unknown reconciliation_type / adjustment_type surfaced
            ALL signoffs required for close (incomplete = fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 6 CLOSE STATES byte-for-byte
CLOSE_STATES: Tuple[str, ...] = (
    "OPEN", "IN_CLOSE", "RECONCILING", "REVIEWED", "CLOSED", "REOPENED",
)

# State machine byte-for-byte
ALLOWED_CLOSE_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "OPEN": ("IN_CLOSE",),
    "IN_CLOSE": ("RECONCILING", "OPEN"),
    "RECONCILING": ("REVIEWED", "IN_CLOSE"),
    "REVIEWED": ("CLOSED", "RECONCILING"),
    "CLOSED": ("REOPENED",),
    "REOPENED": ("IN_CLOSE",),
}

# Close calendar milestones byte-for-byte (T+N days)
CLOSE_CALENDAR_MILESTONES: Dict[str, int] = {
    "TXN_CUTOFF": 1,
    "GL_CLOSE": 5,
    "RECON_COMPLETE": 10,
    "REVIEW_COMPLETE": 12,
    "MGMT_REPORT": 15,
}

# 5 RECONCILIATION TYPES byte-for-byte
RECONCILIATION_TYPES: Tuple[str, ...] = (
    "GL_TO_SUBLEDGER", "BANK_RECON", "INTERCOMPANY",
    "SUSPENSE_ACCOUNT", "NOSTRO_VOSTRO",
)

# 5 ADJUSTMENT TYPES byte-for-byte
ADJUSTMENT_TYPES: Tuple[str, ...] = (
    "ACCRUALS", "PROVISIONS", "REVALUATION",
    "AMORTIZATION", "DEPRECIATION",
)

# 3 SIGNOFF LEVELS byte-for-byte
SIGNOFF_LEVELS: Tuple[str, ...] = ("PREPARER", "REVIEWER", "APPROVER")

# Materiality byte-for-byte
MATERIALITY_THRESHOLD_PCT = Decimal("0.1")
SUSPENSE_ZERO_TOLERANCE_KES = Decimal("0")


class FinancialCloseEngine:
    """Deterministic financial close + reconciliation."""

    @staticmethod
    def close_state_transition(
        from_state: str, to_state: str,
    ) -> Dict[str, Any]:
        """Rule 6: invalid transitions rejected (fail closed)."""
        if from_state not in CLOSE_STATES:
            return {"allowed": False, "reason": f"unknown_from:{from_state}"}
        if to_state not in CLOSE_STATES:
            return {"allowed": False, "reason": f"unknown_to:{to_state}"}
        allowed = ALLOWED_CLOSE_TRANSITIONS.get(from_state, ())
        return {
            "from_state": from_state,
            "to_state": to_state,
            "allowed": to_state in allowed,
            "allowed_next_states": list(allowed),
        }

    @staticmethod
    def close_calendar_milestone(
        period_end: date, milestone: str,
    ) -> Dict[str, Any]:
        """Compute T+N milestone date. Rule 6: unknown milestone surfaced."""
        if milestone not in CLOSE_CALENDAR_MILESTONES:
            return {"deadline": None, "computed": False,
                    "reason": f"unknown_milestone:{milestone}",
                    "valid_milestones": list(CLOSE_CALENDAR_MILESTONES.keys())}
        days = CLOSE_CALENDAR_MILESTONES[milestone]
        deadline = period_end + timedelta(days=days)
        return {
            "milestone": milestone,
            "period_end": period_end.isoformat(),
            "days_offset": days,
            "deadline_date": deadline.isoformat(),
            "computed": True,
        }

    @staticmethod
    def reconciliation_variance(
        gl_balance: Optional[Decimal],
        subledger_balance: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        Compute absolute + pct variance between GL and subledger.
        Rule 1: variance_pct=None when gl_balance=0.
        """
        if gl_balance is None or subledger_balance is None:
            return {"variance": None, "variance_pct": None, "computed": False,
                    "reason": "missing_balance"}
        abs_var = subledger_balance - gl_balance
        if gl_balance == 0:
            pct_var = None
        else:
            pct_var = (abs_var / gl_balance) * Decimal("100")
        return {
            "gl_balance": str(gl_balance),
            "subledger_balance": str(subledger_balance),
            "variance": str(abs_var),
            "variance_pct": (None if pct_var is None
                              else str(pct_var.quantize(Decimal("0.0001")))),
            "computed": True,
        }

    @staticmethod
    def materiality_check(
        variance_pct: Optional[Decimal],
        recon_type: str,
    ) -> Dict[str, Any]:
        """
        Determine if variance exceeds materiality threshold.
        Suspense accounts: zero tolerance (any non-zero is material).
        Other accounts: 0.1% threshold.
        Rule 1: material=None when variance_pct missing.
        Rule 6: unknown recon_type surfaced.
        """
        if recon_type not in RECONCILIATION_TYPES:
            return {"material": None, "computed": False,
                    "reason": f"unknown_recon_type:{recon_type}"}
        if variance_pct is None:
            return {"material": None, "computed": False,
                    "reason": "missing_variance_pct"}
        # Suspense account: zero tolerance
        if recon_type == "SUSPENSE_ACCOUNT":
            material = abs(variance_pct) > Decimal("0")
            threshold_used = Decimal("0")
        else:
            material = abs(variance_pct) > MATERIALITY_THRESHOLD_PCT
            threshold_used = MATERIALITY_THRESHOLD_PCT
        return {
            "recon_type": recon_type,
            "variance_pct": str(variance_pct),
            "threshold_pct": str(threshold_used),
            "material": material,
            "requires_investigation": material,
            "computed": True,
        }

    @staticmethod
    def signoff_complete(
        signoffs: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        Verify all 3 signoff levels completed.
        Rule 6: missing or False signoff = NOT complete (fail closed).
        """
        missing = [lvl for lvl in SIGNOFF_LEVELS
                   if not signoffs.get(lvl, False)]
        complete = len(missing) == 0
        return {
            "required_levels": list(SIGNOFF_LEVELS),
            "completed_levels": [l for l in SIGNOFF_LEVELS
                                  if signoffs.get(l, False)],
            "missing_levels": missing,
            "complete": complete,
            "eligible_for_close": complete,  # fail closed
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_close_states_byte_for_byte():
    expected = ("OPEN", "IN_CLOSE", "RECONCILING", "REVIEWED",
                "CLOSED", "REOPENED")
    for s in expected:
        assert s in CLOSE_STATES
    assert len(CLOSE_STATES) == 6


def _test_close_transitions_byte_for_byte():
    assert ALLOWED_CLOSE_TRANSITIONS["OPEN"] == ("IN_CLOSE",)
    assert ALLOWED_CLOSE_TRANSITIONS["IN_CLOSE"] == ("RECONCILING", "OPEN")
    assert ALLOWED_CLOSE_TRANSITIONS["RECONCILING"] == ("REVIEWED", "IN_CLOSE")
    assert ALLOWED_CLOSE_TRANSITIONS["REVIEWED"] == ("CLOSED", "RECONCILING")
    assert ALLOWED_CLOSE_TRANSITIONS["CLOSED"] == ("REOPENED",)
    assert ALLOWED_CLOSE_TRANSITIONS["REOPENED"] == ("IN_CLOSE",)


def _test_milestones_byte_for_byte():
    assert CLOSE_CALENDAR_MILESTONES["TXN_CUTOFF"] == 1
    assert CLOSE_CALENDAR_MILESTONES["GL_CLOSE"] == 5
    assert CLOSE_CALENDAR_MILESTONES["RECON_COMPLETE"] == 10
    assert CLOSE_CALENDAR_MILESTONES["REVIEW_COMPLETE"] == 12
    assert CLOSE_CALENDAR_MILESTONES["MGMT_REPORT"] == 15


def _test_recon_types_byte_for_byte():
    expected = ("GL_TO_SUBLEDGER", "BANK_RECON", "INTERCOMPANY",
                "SUSPENSE_ACCOUNT", "NOSTRO_VOSTRO")
    for t in expected:
        assert t in RECONCILIATION_TYPES
    assert len(RECONCILIATION_TYPES) == 5


def _test_adjustment_types_byte_for_byte():
    expected = ("ACCRUALS", "PROVISIONS", "REVALUATION",
                "AMORTIZATION", "DEPRECIATION")
    for t in expected:
        assert t in ADJUSTMENT_TYPES
    assert len(ADJUSTMENT_TYPES) == 5


def _test_signoff_levels_byte_for_byte():
    expected = ("PREPARER", "REVIEWER", "APPROVER")
    for l in expected:
        assert l in SIGNOFF_LEVELS


def _test_materiality_threshold_byte_for_byte():
    assert MATERIALITY_THRESHOLD_PCT == Decimal("0.1")
    assert SUSPENSE_ZERO_TOLERANCE_KES == Decimal("0")


def _test_close_state_open_to_in_close():
    r = FinancialCloseEngine.close_state_transition("OPEN", "IN_CLOSE")
    assert r["allowed"] is True


def _test_close_state_invalid_skip_rule6():
    """Cannot skip OPEN → CLOSED."""
    r = FinancialCloseEngine.close_state_transition("OPEN", "CLOSED")
    assert r["allowed"] is False


def _test_close_state_reopen_path():
    """CLOSED → REOPENED → IN_CLOSE allowed."""
    r1 = FinancialCloseEngine.close_state_transition("CLOSED", "REOPENED")
    assert r1["allowed"] is True
    r2 = FinancialCloseEngine.close_state_transition("REOPENED", "IN_CLOSE")
    assert r2["allowed"] is True


def _test_close_state_unknown_rule6():
    r = FinancialCloseEngine.close_state_transition("WEIRD", "OPEN")
    assert r["allowed"] is False


def _test_milestone_txn_cutoff():
    """30 Apr period-end + 1 day = 1 May."""
    r = FinancialCloseEngine.close_calendar_milestone(
        date(2026, 4, 30), "TXN_CUTOFF")
    assert r["deadline_date"] == "2026-05-01"


def _test_milestone_gl_close():
    r = FinancialCloseEngine.close_calendar_milestone(
        date(2026, 4, 30), "GL_CLOSE")
    assert r["deadline_date"] == "2026-05-05"


def _test_milestone_mgmt_report():
    r = FinancialCloseEngine.close_calendar_milestone(
        date(2026, 4, 30), "MGMT_REPORT")
    assert r["deadline_date"] == "2026-05-15"


def _test_milestone_unknown_rule6():
    r = FinancialCloseEngine.close_calendar_milestone(
        date(2026, 4, 30), "WEIRD")
    assert r["computed"] is False


def _test_variance_basic():
    """GL 1M, Subledger 1.001M → variance 1K = 0.1%."""
    r = FinancialCloseEngine.reconciliation_variance(
        Decimal("1000000"), Decimal("1001000"))
    assert r["variance"] == "1000"
    assert r["variance_pct"] == "0.1000"


def _test_variance_zero_gl_rule1():
    r = FinancialCloseEngine.reconciliation_variance(
        Decimal("0"), Decimal("1000"))
    assert r["variance_pct"] is None


def _test_variance_missing_rule1():
    r = FinancialCloseEngine.reconciliation_variance(None, Decimal("1000"))
    assert r["computed"] is False


def _test_materiality_immaterial():
    """0.05% < 0.1% → not material."""
    r = FinancialCloseEngine.materiality_check(
        Decimal("0.05"), "GL_TO_SUBLEDGER")
    assert r["material"] is False


def _test_materiality_material():
    """0.5% > 0.1% → material."""
    r = FinancialCloseEngine.materiality_check(
        Decimal("0.5"), "GL_TO_SUBLEDGER")
    assert r["material"] is True
    assert r["requires_investigation"] is True


def _test_materiality_boundary():
    """Exactly 0.1% → not material (strict >, not >=)."""
    r = FinancialCloseEngine.materiality_check(
        Decimal("0.1"), "GL_TO_SUBLEDGER")
    assert r["material"] is False


def _test_materiality_suspense_zero_tolerance():
    """Suspense: ANY non-zero is material."""
    r = FinancialCloseEngine.materiality_check(
        Decimal("0.01"), "SUSPENSE_ACCOUNT")
    assert r["material"] is True


def _test_materiality_suspense_zero_pass():
    """Suspense at exactly 0% → not material."""
    r = FinancialCloseEngine.materiality_check(
        Decimal("0"), "SUSPENSE_ACCOUNT")
    assert r["material"] is False


def _test_materiality_unknown_recon_rule6():
    r = FinancialCloseEngine.materiality_check(
        Decimal("0.5"), "WEIRD")
    assert r["computed"] is False


def _test_materiality_missing_variance_rule1():
    r = FinancialCloseEngine.materiality_check(
        None, "GL_TO_SUBLEDGER")
    assert r["material"] is None


def _test_signoff_complete_all_three():
    r = FinancialCloseEngine.signoff_complete(
        {"PREPARER": True, "REVIEWER": True, "APPROVER": True})
    assert r["complete"] is True
    assert r["eligible_for_close"] is True


def _test_signoff_missing_approver_rule6():
    """Missing APPROVER → fail closed."""
    r = FinancialCloseEngine.signoff_complete(
        {"PREPARER": True, "REVIEWER": True, "APPROVER": False})
    assert r["complete"] is False
    assert r["eligible_for_close"] is False
    assert "APPROVER" in r["missing_levels"]


def _test_signoff_all_missing():
    r = FinancialCloseEngine.signoff_complete({})
    assert r["complete"] is False
    assert len(r["missing_levels"]) == 3


def self_test() -> bool:
    tests = [
        _test_close_states_byte_for_byte,
        _test_close_transitions_byte_for_byte,
        _test_milestones_byte_for_byte,
        _test_recon_types_byte_for_byte,
        _test_adjustment_types_byte_for_byte,
        _test_signoff_levels_byte_for_byte,
        _test_materiality_threshold_byte_for_byte,
        _test_close_state_open_to_in_close,
        _test_close_state_invalid_skip_rule6,
        _test_close_state_reopen_path,
        _test_close_state_unknown_rule6,
        _test_milestone_txn_cutoff,
        _test_milestone_gl_close,
        _test_milestone_mgmt_report,
        _test_milestone_unknown_rule6,
        _test_variance_basic,
        _test_variance_zero_gl_rule1,
        _test_variance_missing_rule1,
        _test_materiality_immaterial,
        _test_materiality_material,
        _test_materiality_boundary,
        _test_materiality_suspense_zero_tolerance,
        _test_materiality_suspense_zero_pass,
        _test_materiality_unknown_recon_rule6,
        _test_materiality_missing_variance_rule1,
        _test_signoff_complete_all_three,
        _test_signoff_missing_approver_rule6,
        _test_signoff_all_missing,
    ]
    print("=" * 60)
    print("Financial Close Engine — Self-Tests (#99)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
