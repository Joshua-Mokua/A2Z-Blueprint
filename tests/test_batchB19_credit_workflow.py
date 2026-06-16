"""Batch B19 — credit workflow state machine (offer loop + info-request).

Tests the hardcoded transition graph + the config-policy helpers. The
integrity guard (no path to credit_admin without a signed offer) is the
key assertion — it must hold regardless of config.
"""
from utils.api_lms_mutations import (
    is_valid_lms_transition,
    handoff_trigger_status,
    next_offer_status_after_sign,
    get_credit_workflow_config,
    LMS_WORKFLOW_TRANSITIONS,
)


def test_integrity_no_credit_admin_before_signed_offer():
    # Cannot reach credit_admin straight from approval or an unsigned offer.
    assert not is_valid_lms_transition("approved", "credit_admin")
    assert not is_valid_lms_transition("offer_issued", "credit_admin")
    assert is_valid_lms_transition("offer_issued", "offer_signed")


def test_approval_routes_back_to_owner_for_offer():
    assert is_valid_lms_transition("approved", "offer_issued")


def test_info_request_loop():
    assert is_valid_lms_transition("assigned", "info_requested")
    assert is_valid_lms_transition("info_requested", "assigned")


def test_handoff_trigger_respects_policy():
    assert handoff_trigger_status(
        {"require_analyst_confirmation": True}) == "analyst_confirmed"
    assert handoff_trigger_status(
        {"require_analyst_confirmation": False,
         "require_line_manager_offer_validation": True}) == "offer_validated"
    assert handoff_trigger_status(
        {"require_analyst_confirmation": False,
         "require_line_manager_offer_validation": False}) == "offer_signed"


def test_next_status_after_sign_respects_policy():
    assert next_offer_status_after_sign(
        {"require_line_manager_offer_validation": True}) == "offer_validated"
    assert next_offer_status_after_sign(
        {"require_line_manager_offer_validation": False,
         "require_analyst_confirmation": True}) == "analyst_confirmed"


def test_config_has_policy_defaults():
    cfg = get_credit_workflow_config()
    for key in ("committee_mode", "signed_offer_attachment",
                "require_line_manager_offer_validation"):
        assert key in cfg


def test_terminal_states_have_no_exits():
    assert LMS_WORKFLOW_TRANSITIONS["declined"] == ()
    assert LMS_WORKFLOW_TRANSITIONS["disbursed"] == ()
