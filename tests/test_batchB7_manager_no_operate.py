"""Batch B7 — managers oversee but don't operate a subordinate's deal.

A non-admin manager-in-scope keeps view + validate + approve-cancel, but loses
edit + advance (the owner drives the deal). Owner, backup (advance only), and
admin are unaffected.
"""
from utils.api_pipeline_permissions import resolve_deal_permissions

DEAL = {"staff_code": "300731", "stage": "Lead", "backup_staff_codes": []}
SCOPE = {"300731"}  # manager's cascade includes the owner


def _p(user):
    return resolve_deal_permissions(DEAL, user, SCOPE)


def test_manager_cannot_edit_or_advance():
    mgr = {"staff_code": "300716", "role": "Senior Branch Manager"}
    p = _p(mgr)
    assert p["can_view"] is True
    assert p["can_validate"] is True
    assert p["can_edit"] is False
    assert p["can_advance_stage"] is False


def test_owner_can_edit_and_advance():
    owner = {"staff_code": "300731", "role": "Relationship Officer-Personal Banker"}
    p = _p(owner)
    assert p["can_edit"] is True
    assert p["can_advance_stage"] is True


def test_admin_retains_operate():
    admin = {"staff_code": "ADMIN001", "role": "Admin", "is_admin": True}
    p = _p(admin)
    assert p["can_edit"] is True
    assert p["can_advance_stage"] is True
