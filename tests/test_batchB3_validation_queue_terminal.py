"""Batch B3 — validation queue must exclude terminal (closed) deals.

STAGE_NAMES[idx:] runs to the end of the stage list, which includes
'Closed Won' / 'Closed Lost'. A closed deal never needs validation, so
get_pending_validations now intersects with ACTIVE_STAGES.
"""
from utils.core import PipelineManager


def _pm_with(deals):
    pm = PipelineManager()
    pm.deals = deals
    return pm


def test_terminal_deals_excluded_from_validation_queue():
    pm = _pm_with([
        {"id": "D1", "stage": "Closed Lost", "staff_code": "S1"},
        {"id": "D2", "stage": "Closed Won", "staff_code": "S1"},
        {"id": "D3", "stage": "Qualified", "staff_code": "S1"},
        {"id": "D4", "stage": "Compliance", "staff_code": "S1"},
    ])
    ids = {d["id"] for d in pm.get_pending_validations()}
    assert "D1" not in ids and "D2" not in ids   # terminal excluded
    assert "D3" in ids and "D4" in ids            # active retained


def test_validated_and_cancel_requested_excluded():
    pm = _pm_with([
        {"id": "D5", "stage": "Proposal", "staff_code": "S1", "manager_validated": True},
        {"id": "D6", "stage": "Negotiation", "staff_code": "S1", "cancel_requested": True},
        {"id": "D7", "stage": "Negotiation", "staff_code": "S1"},
    ])
    ids = {d["id"] for d in pm.get_pending_validations()}
    assert ids == {"D7"}
