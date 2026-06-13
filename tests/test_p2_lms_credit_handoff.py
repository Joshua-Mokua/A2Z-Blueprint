"""Phase P Batch P2 regression — LMS-approval -> Credit-Admin handoff.

Proves CreditAdminManager.create_case_from_application creates a correctly
shaped, idempotent case, and that the LMS decision route invokes the
handoff on approval and surfaces the new case id.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


# ── source-scan (always runs) ───────────────────────────────────────────
def test_manager_has_create_case():
    assert "def create_case_from_application" in _src("utils/core.py")


def test_decision_route_invokes_handoff_and_surfaces_case_id():
    src = _src("utils/api_lms_routes.py")
    assert "create_case_from_application" in src, "approval must create a case"
    assert "credit_admin_case_id" in src, "response must surface the case id"
    assert 'verdict_normalized == "approved"' in src, "handoff only on approval"


# ── behavioral (needs utils.core importable) ────────────────────────────
def test_create_case_shape_and_idempotency(tmp_path):
    from utils.core import CreditAdminManager
    cam = CreditAdminManager()
    cam.file = tmp_path / "credit_admin.json"
    cam.cases = []

    app = {
        "id": "LMS00042", "client_name": "Acme Ltd",
        "product": "SME Term Loan", "amount": 5_000_000,
        "rm_code": "0006", "rm_name": "Branch Mgr",
    }
    cid = cam.create_case_from_application(
        app, conditions=["Board resolution", "Debenture"],
        authority="Branch Credit Manager",
    )
    assert cid == "CALMS00042"
    case = cam.get(cid)
    assert case["application_id"] == "LMS00042"
    assert case["client_name"] == "Acme Ltd"
    assert len(case["conditions"]) == 2
    assert case["conditions"][0]["fulfilled"] is False
    assert case["all_conditions_met"] is False
    assert case["ready_for_disbursement"] is False

    # idempotent: re-approval does not duplicate
    cam.create_case_from_application(app, conditions=["Board resolution", "Debenture"])
    assert len([c for c in cam.cases if c["id"] == cid]) == 1


def test_create_case_no_conditions_is_all_met(tmp_path):
    from utils.core import CreditAdminManager
    cam = CreditAdminManager()
    cam.file = tmp_path / "credit_admin.json"
    cam.cases = []
    cid = cam.create_case_from_application(
        {"id": "LMS00099", "client_name": "NoCond"}, conditions=[],
    )
    case = cam.get(cid)
    assert case["all_conditions_met"] is True
    assert case["ready_for_disbursement"] is False  # manager still clears
