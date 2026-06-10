"""Regression tests for Phase 3 Arc α Batch α6 — Pipeline Manager Queues.

Authored v10.508 Phase 3 Arc α Batch α6.

Coverage
--------
- G399 (gate_pipeline_manager_queues_present) — registration,
  behavior, well-formed result.
- is_manager — detection across 9 representative role scenarios
  (covers each of the 10 MANAGER_ROLE_KEYWORDS + admin + several
  non-manager roles).
- validate_cancel_request_payload — missing reason, too short, valid.
- Pydantic models — PipelineDealValidate, PipelineDealCancelRequest,
  PipelineDealCancelApprove parse correctly + Pydantic enforces
  required fields.
- Endpoint surface — all 5 endpoints have route decorators.
- Authorization wiring — manager-only endpoints all call is_manager.

Why this matters
----------------
α6 closes GAP-011 by exposing the manager-side action surface that
Streamlit page lines 1290-1336 implemented. Before α6, the FastAPI
surface had no way for managers to validate deals or approve
cancellations — a React-only frontend couldn't replace Streamlit's
manager UX. After α6, the load-bearing manager flow is complete.

The asymmetric authorization (RM can request cancel, only manager
can approve) is the load-bearing design choice. G399's check that
manager-only endpoints call is_manager protects this asymmetry —
removing the check would silently expand authorization to all
authenticated users.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"
API_PATH = REPO_ROOT / "utils" / "api.py"
ACTIONS_PATH = REPO_ROOT / "utils" / "api_pipeline_manager_actions.py"
MODELS_PATH = REPO_ROOT / "utils" / "api_pipeline_models.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g399_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_repo_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


# ──────────────────────────────────────────────────────────────────
# G399 plumbing (4)
# ──────────────────────────────────────────────────────────────────


def test_g399_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G399" in gate_ids


def test_g399_function_exists_and_is_callable():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_manager_queues_present")
    assert callable(audit.gate_pipeline_manager_queues_present)


def test_g399_returns_well_formed_result():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_manager_queues_present()
    assert result["id"] == "G399"
    assert result["name"] == "pipeline_manager_queues_present"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)


def test_g399_passes_against_current_code():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_manager_queues_present()
    assert result["passed"], f"G399 fails: {result['violations']}"


# ──────────────────────────────────────────────────────────────────
# is_manager detection (9)
# ──────────────────────────────────────────────────────────────────


def test_is_manager_admin_user_is_manager():
    """is_admin=True overrides everything — admins are managers."""
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"is_admin": True}) is True
    # Even with a non-manager role string, admin overrides
    assert is_manager({"is_admin": True, "role": "Teller"}) is True


def test_is_manager_md_director_head():
    """Top-tier manager roles."""
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "Managing Director"}) is True
    assert is_manager({"role": "Director Retail Banking"}) is True
    assert is_manager({"role": "Director Commercial Banking"}) is True
    assert is_manager({"role": "Head of Retail"}) is True
    assert is_manager({"role": "Head of SME"}) is True


def test_is_manager_branch_and_regional():
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "Branch Manager"}) is True
    assert is_manager({"role": "Regional Head"}) is True


def test_is_manager_credit_and_operations():
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "Branch Credit Manager"}) is True
    assert is_manager({"role": "Branch Operations Manager"}) is True
    assert is_manager({"role": "Operations Supervisor"}) is True


def test_is_manager_chief():
    """Chief-tier roles."""
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "Chief Risk Officer"}) is True
    assert is_manager({"role": "Chief Operating Officer"}) is True


def test_is_manager_rm_roles_are_not_managers():
    """The RM tier is not manager — they handle deals but don't
    validate them."""
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "RM SME"}) is False
    assert is_manager({"role": "RM Corporate"}) is False
    assert is_manager({"role": "RO PB"}) is False
    assert is_manager({"role": "RO BB"}) is False
    assert is_manager({"role": "DSO"}) is False


def test_is_manager_teller_cso_not_managers():
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "Teller"}) is False
    assert is_manager({"role": "CSO"}) is False
    assert is_manager({"role": "BOS"}) is False


def test_is_manager_defensive_inputs():
    """Empty, None, missing — all return False."""
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({}) is False
    assert is_manager(None) is False
    assert is_manager({"role": ""}) is False
    assert is_manager({"role": None}) is False


def test_is_manager_case_insensitive():
    """Match is case-insensitive substring."""
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import is_manager
    assert is_manager({"role": "BRANCH MANAGER"}) is True
    assert is_manager({"role": "branch manager"}) is True
    assert is_manager({"role": "BRANCH manager"}) is True


# ──────────────────────────────────────────────────────────────────
# validate_cancel_request_payload (3)
# ──────────────────────────────────────────────────────────────────


def test_validate_cancel_request_accepts_real_reason():
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import validate_cancel_request_payload
    ok, _ = validate_cancel_request_payload({"reason": "lost to NCBA"})
    assert ok


def test_validate_cancel_request_rejects_missing_reason():
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import validate_cancel_request_payload
    ok, reason = validate_cancel_request_payload({})
    assert not ok
    assert "reason" in reason.lower()

    ok, reason = validate_cancel_request_payload({"reason": ""})
    assert not ok


def test_validate_cancel_request_rejects_too_short():
    _setup_repo_path()
    from utils.api_pipeline_manager_actions import (
        validate_cancel_request_payload, MIN_CANCEL_REASON_LEN,
    )
    ok, reason = validate_cancel_request_payload({"reason": "ok"})
    assert not ok
    assert "too short" in reason or str(MIN_CANCEL_REASON_LEN) in reason


# ──────────────────────────────────────────────────────────────────
# Pydantic models (3)
# ──────────────────────────────────────────────────────────────────


def test_pipeline_deal_validate_model_parses():
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealValidate
    m = PipelineDealValidate(approved=True, note="looks good")
    assert m.approved is True
    assert m.note == "looks good"

    # Pydantic enforces approved as required
    with pytest.raises(Exception):
        PipelineDealValidate(note="missing approved field")


def test_pipeline_deal_cancel_request_model_parses():
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealCancelRequest
    m = PipelineDealCancelRequest(reason="duplicate of D0005")
    assert m.reason == "duplicate of D0005"

    # Pydantic enforces reason as required (and min_length=1)
    with pytest.raises(Exception):
        PipelineDealCancelRequest()
    with pytest.raises(Exception):
        PipelineDealCancelRequest(reason="")


def test_pipeline_deal_cancel_approve_model_parses():
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealCancelApprove
    m = PipelineDealCancelApprove(approve=False, note="not yet")
    assert m.approve is False
    assert m.note == "not yet"

    # Default note empty string
    m2 = PipelineDealCancelApprove(approve=True)
    assert m2.note == ""


# ──────────────────────────────────────────────────────────────────
# Endpoint surface — all 5 routes present (1)
# ──────────────────────────────────────────────────────────────────


def test_five_manager_queue_endpoints_have_route_decorators():
    src = API_PATH.read_text(encoding="utf-8")
    expected_routes = [
        '/api/pipeline/queues/validation',
        '/api/pipeline/queues/cancellation',
        '/api/pipeline/deals/{deal_id}/validate',
        '/api/pipeline/deals/{deal_id}/cancel/request',
        '/api/pipeline/deals/{deal_id}/cancel/approve',
    ]
    missing = [r for r in expected_routes if r not in src]
    assert not missing, f"Missing route decorators: {missing}"


# ──────────────────────────────────────────────────────────────────
# Authorization wiring — manager-only endpoints call is_manager (1)
# ──────────────────────────────────────────────────────────────────


def test_manager_only_endpoints_call_is_manager():
    """Structural check: each manager-only endpoint function body
    must reference is_manager. The cancel/request endpoint (RM-side
    action) deliberately does NOT call is_manager."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))
    manager_only_endpoints = {
        "pipeline_queue_validation",
        "pipeline_queue_cancellation",
        "pipeline_deal_validate",
        "pipeline_deal_cancel_approve",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in manager_only_endpoints:
            calls_is_manager = any(
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "is_manager"
                for sub in ast.walk(node)
            )
            assert calls_is_manager, (
                f"{node.name} does not call is_manager — manager "
                "authorization not enforced"
            )


def test_cancel_request_endpoint_does_not_call_is_manager():
    """The RM-side cancel/request endpoint must NOT require manager
    role — any authenticated user with scope access can request."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "pipeline_deal_cancel_request":
            calls_is_manager = any(
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "is_manager"
                for sub in ast.walk(node)
            )
            assert not calls_is_manager, (
                "pipeline_deal_cancel_request wrongly calls is_manager — "
                "would block RMs from requesting cancellation of their "
                "own deals (breaks the asymmetric authorization model)"
            )
            return
    pytest.fail("pipeline_deal_cancel_request endpoint not found")
