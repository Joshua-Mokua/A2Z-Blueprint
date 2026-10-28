import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
import utils.api_lms_routes as routes


def application(status="post_approval_verification", offer=True):
    app = dict(id="TEST-PA-001", status=status, post_approval_verification_status="pending", post_approval_verification_assignee=dict(code="KE1219", name="Original Analyst"))
    if offer:
        app["offer"] = dict(issued_at="2026-10-27T10:00:00")
    return app


def test_original_analyst_accepted():
    assert routes._post_approval_verification_actor(application(), dict(staff_code="KE1219"))[0] == "KE1219"


def test_different_analyst_rejected_by_endpoint():
    manager = MagicMock()
    manager.get.return_value = application()
    with patch.object(routes, "_lam", return_value=manager):
        with pytest.raises(HTTPException) as exc:
            routes.lms_post_approval_verification_verify("TEST-PA-001", {}, user=dict(staff_code="KE9999"))
    assert exc.value.status_code == 403
    manager.update.assert_not_called()


def test_missing_analyst_assignment_blocked():
    app = application()
    app["post_approval_verification_assignee"] = {}
    with pytest.raises(HTTPException) as exc:
        routes._post_approval_verification_actor(app, dict(staff_code="KE1219"))
    assert exc.value.status_code == 409


def test_missing_offer_blocks_verification():
    manager = MagicMock()
    manager.get.return_value = application(offer=False)
    with patch.object(routes, "_lam", return_value=manager), patch.object(routes, "_post_approval_fulfilment", return_value=({}, [])):
        with pytest.raises(HTTPException) as exc:
            routes.lms_post_approval_verification_verify("TEST-PA-001", {}, user=dict(staff_code="KE1219"))
    assert exc.value.status_code == 409
    manager.update.assert_not_called()


def test_verification_proceeds_to_offer_without_cad():
    manager = MagicMock()
    manager.get.return_value = application()
    with patch.object(routes, "_lam", return_value=manager), patch.object(routes, "_post_approval_fulfilment", return_value=({}, [])), patch.object(routes, "audit_log"), patch("utils.core.CreditAdminManager.create_case_from_application") as create_case:
        result = routes.lms_post_approval_verification_verify("TEST-PA-001", {}, user=dict(staff_code="KE1219", username="analyst"))
    assert result["status"] == "offer_issued"
    changes = manager.update.call_args.args[1]
    assert changes["status"] == "offer_issued"
    assert changes["post_approval_verification_status"] == "verified"
    assert changes["post_approval_verification_required"] is False
    create_case.assert_not_called()


def test_manager_validation_required_blocks_confirmation():
    manager = MagicMock()
    manager.get.return_value = application(status="offer_signed")
    with patch.object(routes, "_lam", return_value=manager), patch.object(routes, "get_credit_workflow_config", return_value=dict(require_line_manager_offer_validation=True)):
        with pytest.raises(HTTPException) as exc:
            routes.lms_confirm_to_credit_admin("TEST-PA-001", MagicMock(note="test"), user=dict(is_admin=True, username="analyst"))
    assert exc.value.status_code == 409
    manager.confirm_to_credit_admin.assert_not_called()


def test_manager_validation_disabled_allows_confirmation():
    manager = MagicMock()
    manager.get.return_value = application(status="offer_signed")
    manager.confirm_to_credit_admin.return_value = True
    with patch.object(routes, "_lam", return_value=manager), patch.object(routes, "get_credit_workflow_config", return_value=dict(require_line_manager_offer_validation=False)), patch.object(routes, "_maybe_handoff_to_credit_admin", return_value="CALMS001") as handoff, patch.object(routes, "audit_log"):
        result = routes.lms_confirm_to_credit_admin("TEST-PA-001", MagicMock(note="test"), user=dict(is_admin=True, username="analyst"))
    manager.confirm_to_credit_admin.assert_called_once()
    handoff.assert_called_once()
    assert result["credit_admin_case_id"] == "CALMS001"


def test_cad_handoff_combines_approved_conditions():
    from utils.core import CreditAdminManager
    app = application(status="analyst_confirmed")
    app["post_approval_verification_required"] = False
    app["pre_approval_conditions"] = [dict(text="Obtain tax compliance certificate", met=True, kind="pre_approval")]
    app["pre_disbursement_conditions"] = [dict(text="Obtain tax compliance certificate", met=False, kind="pre_disbursement"), dict(text="Register security", met=False, kind="pre_disbursement")]
    manager = MagicMock()
    manager.get.return_value = app
    manager.update.return_value = True
    cad = CreditAdminManager.__new__(CreditAdminManager)
    cad.cases = []
    cad.get = lambda case_id: next((c for c in cad.cases if c["id"] == case_id), None)
    cad.save = lambda: None
    with patch.object(routes, "_lam", return_value=manager), patch.object(routes, "get_credit_workflow_config", return_value=dict(require_analyst_confirmation=True)), patch("utils.core.CreditAdminManager", return_value=cad):
        case_id = routes._maybe_handoff_to_credit_admin(manager, "TEST-PA-001", dict(username="analyst"))
    assert case_id == "CATEST-PA-001"
    assert len(cad.cases) == 1
    conditions = cad.cases[0]["conditions"]
    assert [c["type"] for c in conditions] == ["Obtain tax compliance certificate", "Register security"]
    assert all(c["mandatory"] and not c["fulfilled"] for c in conditions)
    assert cad.cases[0]["ready_for_disbursement"] is False


def test_cad_verification_snapshot_is_independent():
    from utils.core import CreditAdminManager
    app = application(status="analyst_confirmed")
    app["post_approval_verification"] = dict(status="verified", by="KE1219", conditions=[dict(text="Register security", evidence=["security-document.pdf"])])
    cad = CreditAdminManager.__new__(CreditAdminManager)
    cad.cases = []
    cad.get = lambda case_id: next((c for c in cad.cases if c["id"] == case_id), None)
    cad.save = lambda: None
    case_id = cad.create_case_from_application(app, conditions=["Register security"])
    case = cad.get(case_id)
    snapshot = case["post_approval_verification_snapshot"]
    assert snapshot == app["post_approval_verification"]
    assert snapshot is not app["post_approval_verification"]
    app["post_approval_verification"]["conditions"][0]["evidence"].append("later-document.pdf")
    assert snapshot["conditions"][0]["evidence"] == ["security-document.pdf"]
    assert case["conditions"][0]["fulfilled"] is False
    assert case["conditions"][0]["mandatory"] is True
    assert case["ready_for_disbursement"] is False


def test_previously_required_document_cannot_be_silently_deselected():
    app = application()
    app["post_approval_verification"] = {"documents": {"tcc": {"required": True}}}
    payload = {"documents": {"tcc": {"required": False}}}
    fulfilment, blockers = routes._post_approval_fulfilment(app, payload)
    assert fulfilment["documents"]["tcc"]["required"] is True
    assert fulfilment["documents"]["tcc"]["present"] is False
    assert "Required post-approval document missing: Total Credit Cost (TCC)" in blockers
    assert fulfilment["ready"] is False
    app["document_files"] = {"Total Credit Cost (TCC)": {"filename": "tcc.pdf"}}
    fulfilment, blockers = routes._post_approval_fulfilment(app, payload)
    assert fulfilment["documents"]["tcc"]["required"] is True
    assert fulfilment["documents"]["tcc"]["present"] is True
    assert blockers == []
    assert fulfilment["ready"] is True


def test_previously_declared_terms_change_cannot_be_cleared():
    app = application()
    app["post_approval_verification"] = {"terms_changed": True}
    fulfilment, blockers = routes._post_approval_fulfilment(app, {"terms_changed": False})
    assert fulfilment["terms_changed"] is True
    assert fulfilment["ready"] is False
    assert any("authorized resolution/reapproval" in blocker for blocker in blockers)
