"""
================================================================================
A2Z MIS 360 — Standard #98: Procurement Workflow & Approval Authority Matrix
================================================================================

Risk classification: Cat B (deterministic procurement workflow + approval gating)

Provides:
    - approval_authority(...)       -- determine required approver by amount
    - procurement_method(...)       -- DIRECT / RFQ / OPEN_TENDER threshold
    - validate_state_transition(...) -- procurement state machine
    - three_way_match(...)          -- PO + GRN + Invoice match check
    - bid_count_required(...)       -- minimum quotations required

7 PROCUREMENT_STATES byte-for-byte:
    REQUESTED, APPROVED, PO_ISSUED, RECEIVED, INVOICED, PAID, CANCELLED

ALLOWED_PROCUREMENT_TRANSITIONS byte-for-byte:
    REQUESTED  → APPROVED, CANCELLED
    APPROVED   → PO_ISSUED, CANCELLED
    PO_ISSUED  → RECEIVED, CANCELLED
    RECEIVED   → INVOICED
    INVOICED   → PAID
    PAID       → ()  terminal
    CANCELLED  → ()  terminal

5 APPROVAL_TIERS byte-for-byte (KES amount thresholds):
    BUYER       (≤ 100,000)
    MANAGER     (100,001 - 1,000,000)
    DIRECTOR    (1,000,001 - 10,000,000)
    MD          (10,000,001 - 50,000,000)
    BOARD       (> 50,000,000)

APPROVAL_THRESHOLDS_KES byte-for-byte:
    BUYER_LIMIT     = 100000
    MANAGER_LIMIT   = 1000000
    DIRECTOR_LIMIT  = 10000000
    MD_LIMIT        = 50000000
    -- above MD_LIMIT requires BOARD

5 PROCUREMENT_METHODS byte-for-byte:
    DIRECT_PURCHASE             (≤ 50K — single quote)
    REQUEST_FOR_QUOTATION       (50K - 1M — 3 quotations)
    OPEN_TENDER                 (1M - 10M — published tender)
    RESTRICTED_TENDER           (> 10M — pre-qualified vendors)
    FRAMEWORK_AGREEMENT         (recurring — established panel)

PROCUREMENT_METHOD_THRESHOLDS_KES byte-for-byte:
    DIRECT_PURCHASE_MAX   = 50000
    RFQ_MIN               = 50001
    RFQ_MAX               = 1000000
    OPEN_TENDER_MIN       = 1000001
    OPEN_TENDER_MAX       = 10000000
    RESTRICTED_TENDER_MIN = 10000001

Required quotation counts byte-for-byte:
    DIRECT_PURCHASE     = 1
    REQUEST_FOR_QUOTATION = 3   -- KEY 3-bid rule
    OPEN_TENDER         = 0     -- public tender (any number)
    RESTRICTED_TENDER   = 5     -- 5 pre-qualified vendors

4 VENDOR_SELECTION_CRITERIA byte-for-byte:
    PRICE, QUALITY, DELIVERY, COMPLIANCE

Three-way match tolerance byte-for-byte:
    THREE_WAY_MATCH_TOLERANCE_PCT = 2   -- ±2% allowed between PO/GRN/Invoice

Honesty rules applied:
    Rule 1: approval_authority=None when amount missing
            three_way_match=None when any of PO/GRN/Invoice missing
    Rule 6: invalid state transitions REJECTED (fail closed)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Any, Dict, Optional, Tuple

getcontext().prec = 28

# 7 PROCUREMENT STATES byte-for-byte
PROCUREMENT_STATES: Tuple[str, ...] = (
    "REQUESTED", "APPROVED", "PO_ISSUED", "RECEIVED", "INVOICED",
    "PAID", "CANCELLED",
)

# State machine byte-for-byte
ALLOWED_PROCUREMENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "REQUESTED": ("APPROVED", "CANCELLED"),
    "APPROVED": ("PO_ISSUED", "CANCELLED"),
    "PO_ISSUED": ("RECEIVED", "CANCELLED"),
    "RECEIVED": ("INVOICED",),
    "INVOICED": ("PAID",),
    "PAID": (),
    "CANCELLED": (),
}

# 5 APPROVAL TIERS byte-for-byte
APPROVAL_TIERS: Tuple[str, ...] = (
    "BUYER", "MANAGER", "DIRECTOR", "MD", "BOARD",
)

# Approval thresholds KES byte-for-byte
BUYER_LIMIT_KES = Decimal("100000")
MANAGER_LIMIT_KES = Decimal("1000000")
DIRECTOR_LIMIT_KES = Decimal("10000000")
MD_LIMIT_KES = Decimal("50000000")

# 5 PROCUREMENT METHODS byte-for-byte
PROCUREMENT_METHODS: Tuple[str, ...] = (
    "DIRECT_PURCHASE", "REQUEST_FOR_QUOTATION", "OPEN_TENDER",
    "RESTRICTED_TENDER", "FRAMEWORK_AGREEMENT",
)

# Procurement method thresholds byte-for-byte
DIRECT_PURCHASE_MAX_KES = Decimal("50000")
RFQ_MIN_KES = Decimal("50001")
RFQ_MAX_KES = Decimal("1000000")
OPEN_TENDER_MIN_KES = Decimal("1000001")
OPEN_TENDER_MAX_KES = Decimal("10000000")
RESTRICTED_TENDER_MIN_KES = Decimal("10000001")

# Required quotations byte-for-byte
QUOTATIONS_REQUIRED: Dict[str, int] = {
    "DIRECT_PURCHASE": 1,
    "REQUEST_FOR_QUOTATION": 3,
    "OPEN_TENDER": 0,
    "RESTRICTED_TENDER": 5,
    "FRAMEWORK_AGREEMENT": 0,
}

# 4 VENDOR SELECTION CRITERIA byte-for-byte
VENDOR_SELECTION_CRITERIA: Tuple[str, ...] = (
    "PRICE", "QUALITY", "DELIVERY", "COMPLIANCE",
)

# Three-way match tolerance byte-for-byte
THREE_WAY_MATCH_TOLERANCE_PCT = Decimal("2")


class ProcurementWorkflowEngine:
    """Deterministic procurement workflow + approval gating."""

    @staticmethod
    def approval_authority(amount_kes: Optional[Decimal]) -> Dict[str, Any]:
        """
        Determine required approver tier by amount.
        Rule 1: tier=None when amount missing or negative.
        """
        if amount_kes is None or amount_kes < 0:
            return {"tier": None, "computed": False,
                    "reason": "missing_or_negative_amount"}
        if amount_kes <= BUYER_LIMIT_KES:
            tier = "BUYER"
        elif amount_kes <= MANAGER_LIMIT_KES:
            tier = "MANAGER"
        elif amount_kes <= DIRECTOR_LIMIT_KES:
            tier = "DIRECTOR"
        elif amount_kes <= MD_LIMIT_KES:
            tier = "MD"
        else:
            tier = "BOARD"
        return {
            "amount_kes": str(amount_kes),
            "tier": tier,
            "computed": True,
        }

    @staticmethod
    def procurement_method(amount_kes: Optional[Decimal]) -> Dict[str, Any]:
        """
        Determine required procurement method by amount.
        Rule 1: method=None when amount missing.
        """
        if amount_kes is None or amount_kes < 0:
            return {"method": None, "computed": False,
                    "reason": "missing_or_negative_amount"}
        if amount_kes <= DIRECT_PURCHASE_MAX_KES:
            method = "DIRECT_PURCHASE"
        elif amount_kes <= RFQ_MAX_KES:
            method = "REQUEST_FOR_QUOTATION"
        elif amount_kes <= OPEN_TENDER_MAX_KES:
            method = "OPEN_TENDER"
        else:
            method = "RESTRICTED_TENDER"
        quotations = QUOTATIONS_REQUIRED[method]
        return {
            "amount_kes": str(amount_kes),
            "method": method,
            "quotations_required": quotations,
            "computed": True,
        }

    @staticmethod
    def validate_state_transition(
        from_state: str, to_state: str,
    ) -> Dict[str, Any]:
        """Rule 6: invalid transitions rejected (fail closed)."""
        if from_state not in PROCUREMENT_STATES:
            return {"allowed": False, "reason": f"unknown_from:{from_state}"}
        if to_state not in PROCUREMENT_STATES:
            return {"allowed": False, "reason": f"unknown_to:{to_state}"}
        allowed = ALLOWED_PROCUREMENT_TRANSITIONS.get(from_state, ())
        return {
            "from_state": from_state,
            "to_state": to_state,
            "allowed": to_state in allowed,
            "allowed_next_states": list(allowed),
        }

    @staticmethod
    def three_way_match(
        po_amount: Optional[Decimal],
        grn_amount: Optional[Decimal],
        invoice_amount: Optional[Decimal],
    ) -> Dict[str, Any]:
        """
        PO + GRN + Invoice match within ±2% tolerance.
        Rule 1: matched=None when any component missing.
        """
        if po_amount is None or grn_amount is None or invoice_amount is None:
            return {"matched": None, "computed": False,
                    "reason": "missing_component"}
        if po_amount <= 0:
            return {"matched": None, "computed": False,
                    "reason": "invalid_po_amount"}
        # Compute deviations vs PO
        grn_dev_pct = abs((grn_amount - po_amount) / po_amount) * Decimal("100")
        inv_dev_pct = abs((invoice_amount - po_amount) / po_amount) * Decimal("100")
        within_tolerance = (grn_dev_pct <= THREE_WAY_MATCH_TOLERANCE_PCT
                             and inv_dev_pct <= THREE_WAY_MATCH_TOLERANCE_PCT)
        return {
            "po_amount": str(po_amount),
            "grn_amount": str(grn_amount),
            "invoice_amount": str(invoice_amount),
            "grn_deviation_pct": str(grn_dev_pct.quantize(Decimal("0.01"))),
            "invoice_deviation_pct": str(inv_dev_pct.quantize(Decimal("0.01"))),
            "tolerance_pct": str(THREE_WAY_MATCH_TOLERANCE_PCT),
            "matched": within_tolerance,
            "eligible_for_payment": within_tolerance,  # fail closed
            "computed": True,
        }

    @staticmethod
    def bid_count_required(method: str) -> Optional[int]:
        """Lookup required quotations for a procurement method."""
        return QUOTATIONS_REQUIRED.get(method)


# ============================================================================
# Self-tests
# ============================================================================

def _test_states_byte_for_byte():
    expected = ("REQUESTED", "APPROVED", "PO_ISSUED", "RECEIVED",
                "INVOICED", "PAID", "CANCELLED")
    for s in expected:
        assert s in PROCUREMENT_STATES
    assert len(PROCUREMENT_STATES) == 7


def _test_transitions_byte_for_byte():
    assert ALLOWED_PROCUREMENT_TRANSITIONS["REQUESTED"] == ("APPROVED", "CANCELLED")
    assert ALLOWED_PROCUREMENT_TRANSITIONS["APPROVED"] == ("PO_ISSUED", "CANCELLED")
    assert ALLOWED_PROCUREMENT_TRANSITIONS["PO_ISSUED"] == ("RECEIVED", "CANCELLED")
    assert ALLOWED_PROCUREMENT_TRANSITIONS["RECEIVED"] == ("INVOICED",)
    assert ALLOWED_PROCUREMENT_TRANSITIONS["INVOICED"] == ("PAID",)
    assert ALLOWED_PROCUREMENT_TRANSITIONS["PAID"] == ()
    assert ALLOWED_PROCUREMENT_TRANSITIONS["CANCELLED"] == ()


def _test_approval_tiers_byte_for_byte():
    expected = ("BUYER", "MANAGER", "DIRECTOR", "MD", "BOARD")
    for t in expected:
        assert t in APPROVAL_TIERS


def _test_approval_thresholds_byte_for_byte():
    assert BUYER_LIMIT_KES == Decimal("100000")
    assert MANAGER_LIMIT_KES == Decimal("1000000")
    assert DIRECTOR_LIMIT_KES == Decimal("10000000")
    assert MD_LIMIT_KES == Decimal("50000000")


def _test_procurement_methods_byte_for_byte():
    expected = ("DIRECT_PURCHASE", "REQUEST_FOR_QUOTATION", "OPEN_TENDER",
                "RESTRICTED_TENDER", "FRAMEWORK_AGREEMENT")
    for m in expected:
        assert m in PROCUREMENT_METHODS


def _test_method_thresholds_byte_for_byte():
    assert DIRECT_PURCHASE_MAX_KES == Decimal("50000")
    assert RFQ_MIN_KES == Decimal("50001")
    assert RFQ_MAX_KES == Decimal("1000000")
    assert OPEN_TENDER_MIN_KES == Decimal("1000001")
    assert OPEN_TENDER_MAX_KES == Decimal("10000000")
    assert RESTRICTED_TENDER_MIN_KES == Decimal("10000001")


def _test_quotations_required_byte_for_byte():
    assert QUOTATIONS_REQUIRED["DIRECT_PURCHASE"] == 1
    assert QUOTATIONS_REQUIRED["REQUEST_FOR_QUOTATION"] == 3
    assert QUOTATIONS_REQUIRED["OPEN_TENDER"] == 0
    assert QUOTATIONS_REQUIRED["RESTRICTED_TENDER"] == 5


def _test_selection_criteria_byte_for_byte():
    expected = ("PRICE", "QUALITY", "DELIVERY", "COMPLIANCE")
    for c in expected:
        assert c in VENDOR_SELECTION_CRITERIA


def _test_three_way_tolerance_byte_for_byte():
    assert THREE_WAY_MATCH_TOLERANCE_PCT == Decimal("2")


def _test_approval_buyer():
    """50K → BUYER tier."""
    r = ProcurementWorkflowEngine.approval_authority(Decimal("50000"))
    assert r["tier"] == "BUYER"


def _test_approval_buyer_boundary():
    """Exactly 100K → BUYER (boundary inclusive)."""
    r = ProcurementWorkflowEngine.approval_authority(Decimal("100000"))
    assert r["tier"] == "BUYER"


def _test_approval_manager():
    r = ProcurementWorkflowEngine.approval_authority(Decimal("500000"))
    assert r["tier"] == "MANAGER"


def _test_approval_director():
    r = ProcurementWorkflowEngine.approval_authority(Decimal("5000000"))
    assert r["tier"] == "DIRECTOR"


def _test_approval_md():
    r = ProcurementWorkflowEngine.approval_authority(Decimal("30000000"))
    assert r["tier"] == "MD"


def _test_approval_board():
    """Above MD limit → BOARD."""
    r = ProcurementWorkflowEngine.approval_authority(Decimal("100000000"))
    assert r["tier"] == "BOARD"


def _test_approval_board_boundary():
    """Exactly above 50M → BOARD."""
    r = ProcurementWorkflowEngine.approval_authority(Decimal("50000001"))
    assert r["tier"] == "BOARD"


def _test_approval_missing_rule1():
    r = ProcurementWorkflowEngine.approval_authority(None)
    assert r["tier"] is None


def _test_method_direct():
    r = ProcurementWorkflowEngine.procurement_method(Decimal("30000"))
    assert r["method"] == "DIRECT_PURCHASE"
    assert r["quotations_required"] == 1


def _test_method_rfq():
    r = ProcurementWorkflowEngine.procurement_method(Decimal("500000"))
    assert r["method"] == "REQUEST_FOR_QUOTATION"
    assert r["quotations_required"] == 3


def _test_method_open_tender():
    r = ProcurementWorkflowEngine.procurement_method(Decimal("5000000"))
    assert r["method"] == "OPEN_TENDER"


def _test_method_restricted_tender():
    r = ProcurementWorkflowEngine.procurement_method(Decimal("50000000"))
    assert r["method"] == "RESTRICTED_TENDER"
    assert r["quotations_required"] == 5


def _test_state_valid_transition():
    r = ProcurementWorkflowEngine.validate_state_transition(
        "REQUESTED", "APPROVED")
    assert r["allowed"] is True


def _test_state_invalid_skip_rule6():
    """Cannot skip directly to PAID."""
    r = ProcurementWorkflowEngine.validate_state_transition(
        "REQUESTED", "PAID")
    assert r["allowed"] is False


def _test_state_terminal_paid():
    """PAID is terminal — no exits."""
    r = ProcurementWorkflowEngine.validate_state_transition(
        "PAID", "REQUESTED")
    assert r["allowed"] is False
    assert r["allowed_next_states"] == []


def _test_state_terminal_cancelled():
    r = ProcurementWorkflowEngine.validate_state_transition(
        "CANCELLED", "APPROVED")
    assert r["allowed"] is False


def _test_state_invoiced_to_paid():
    r = ProcurementWorkflowEngine.validate_state_transition(
        "INVOICED", "PAID")
    assert r["allowed"] is True


def _test_state_unknown_rule6():
    r = ProcurementWorkflowEngine.validate_state_transition(
        "WEIRD", "APPROVED")
    assert r["allowed"] is False


def _test_three_way_exact_match():
    """All 3 = 100K → match."""
    r = ProcurementWorkflowEngine.three_way_match(
        Decimal("100000"), Decimal("100000"), Decimal("100000"))
    assert r["matched"] is True
    assert r["eligible_for_payment"] is True


def _test_three_way_within_tolerance():
    """PO 100K, GRN 101K (1%), Invoice 99K (1%) → within 2% → match."""
    r = ProcurementWorkflowEngine.three_way_match(
        Decimal("100000"), Decimal("101000"), Decimal("99000"))
    assert r["matched"] is True


def _test_three_way_at_tolerance_boundary():
    """Exactly 2% deviation → still match (≤ 2%)."""
    r = ProcurementWorkflowEngine.three_way_match(
        Decimal("100000"), Decimal("102000"), Decimal("100000"))
    assert r["matched"] is True


def _test_three_way_exceeds_tolerance():
    """3% deviation > 2% → no match → not eligible (fail closed)."""
    r = ProcurementWorkflowEngine.three_way_match(
        Decimal("100000"), Decimal("103000"), Decimal("100000"))
    assert r["matched"] is False
    assert r["eligible_for_payment"] is False


def _test_three_way_missing_grn_rule1():
    r = ProcurementWorkflowEngine.three_way_match(
        Decimal("100000"), None, Decimal("100000"))
    assert r["matched"] is None


def _test_bid_count_lookup():
    assert ProcurementWorkflowEngine.bid_count_required("REQUEST_FOR_QUOTATION") == 3
    assert ProcurementWorkflowEngine.bid_count_required("RESTRICTED_TENDER") == 5


def _test_bid_count_unknown():
    assert ProcurementWorkflowEngine.bid_count_required("WEIRD") is None


def self_test() -> bool:
    tests = [
        _test_states_byte_for_byte,
        _test_transitions_byte_for_byte,
        _test_approval_tiers_byte_for_byte,
        _test_approval_thresholds_byte_for_byte,
        _test_procurement_methods_byte_for_byte,
        _test_method_thresholds_byte_for_byte,
        _test_quotations_required_byte_for_byte,
        _test_selection_criteria_byte_for_byte,
        _test_three_way_tolerance_byte_for_byte,
        _test_approval_buyer,
        _test_approval_buyer_boundary,
        _test_approval_manager,
        _test_approval_director,
        _test_approval_md,
        _test_approval_board,
        _test_approval_board_boundary,
        _test_approval_missing_rule1,
        _test_method_direct,
        _test_method_rfq,
        _test_method_open_tender,
        _test_method_restricted_tender,
        _test_state_valid_transition,
        _test_state_invalid_skip_rule6,
        _test_state_terminal_paid,
        _test_state_terminal_cancelled,
        _test_state_invoiced_to_paid,
        _test_state_unknown_rule6,
        _test_three_way_exact_match,
        _test_three_way_within_tolerance,
        _test_three_way_at_tolerance_boundary,
        _test_three_way_exceeds_tolerance,
        _test_three_way_missing_grn_rule1,
        _test_bid_count_lookup,
        _test_bid_count_unknown,
    ]
    print("=" * 60)
    print("Procurement Workflow Engine — Self-Tests (#98)")
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
