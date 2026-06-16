"""Batch B21 — committee voting wired to the existing CreditCommitteeEngine.

Verifies the adapter maps stored votes -> the engine and back, without
duplicating committee logic. committee_required is off in the default
authority_tier mode.
"""
from utils.api_lms_committee import (
    evaluate_committee, charter_from_config, committee_member_ids,
    committee_required,
)


def _app(amount, votes):
    return {"id": "LMST", "amount": amount,
            "committee": {"votes": votes}}


def test_charter_builds_with_members():
    assert len(committee_member_ids()) >= 3


def test_committee_required_off_in_authority_tier_default():
    # default policy is authority_tier -> never required
    assert committee_required(999_000_000) is False


def test_approved_within_authority_majority_yes():
    res = evaluate_committee(_app(50_000_000, [
        {"member_id": "m1", "vote": "YES"}, {"member_id": "m2", "vote": "YES"},
        {"member_id": "m3", "vote": "YES"}, {"member_id": "m4", "vote": "NO"}]))
    assert res["approved"] is True
    assert res["quorum_status"] == "MET"


def test_rejected_majority_no():
    res = evaluate_committee(_app(50_000_000, [
        {"member_id": "m1", "vote": "NO"}, {"member_id": "m2", "vote": "NO"},
        {"member_id": "m3", "vote": "NO"}, {"member_id": "m4", "vote": "YES"}]))
    assert res["rejected"] is True


def test_quorum_fails_without_required_role():
    # CRO (m2) absent -> required-role quorum failure
    res = evaluate_committee(_app(50_000_000, [
        {"member_id": "m1", "vote": "YES"}, {"member_id": "m3", "vote": "YES"},
        {"member_id": "m4", "vote": "YES"}]))
    assert res["quorum_failed"] is True


def test_over_authority_escalates():
    # above default authority limit (100M) -> escalate before voting
    res = evaluate_committee(_app(200_000_000, [
        {"member_id": "m1", "vote": "YES"}, {"member_id": "m2", "vote": "YES"},
        {"member_id": "m3", "vote": "YES"}]))
    assert res["escalated"] is True
