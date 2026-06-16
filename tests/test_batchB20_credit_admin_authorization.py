"""Batch B20 — Credit-Admin two-layer authorization.

An approval (officer requests) AND a confirmation (manager authorizes) are both
required before a case can be disbursed, when the policy is on. The integrity
gate (no disburse before authorize) is the key assertion.
"""
from utils.api_credit_admin_mutations import case_can_be_disbursed


def test_disburse_blocked_before_authorization_requested():
    case = {"disbursed": False, "all_conditions_met": True,
            "ready_for_disbursement": False,
            "authorization_requested": False, "authorized": False}
    ok, reason = case_can_be_disbursed(case)
    assert not ok
    assert "request" in reason.lower()


def test_disburse_blocked_while_awaiting_authorization():
    case = {"disbursed": False, "all_conditions_met": True,
            "ready_for_disbursement": False,
            "authorization_requested": True, "authorized": False}
    ok, reason = case_can_be_disbursed(case)
    assert not ok
    assert "authoriz" in reason.lower()


def test_disburse_allowed_once_authorized_and_ready():
    case = {"disbursed": False, "all_conditions_met": True,
            "ready_for_disbursement": True,
            "authorization_requested": True, "authorized": True}
    ok, _ = case_can_be_disbursed(case)
    assert ok


def test_already_disbursed_cannot_redisburse():
    case = {"disbursed": True, "all_conditions_met": True,
            "ready_for_disbursement": True,
            "authorization_requested": True, "authorized": True}
    ok, reason = case_can_be_disbursed(case)
    assert not ok
    assert "already disbursed" in reason.lower()
