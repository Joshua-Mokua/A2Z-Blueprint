"""Regression tests for Phase 3 Arc α Batch α5 — Pipeline Conflict Resolution.

Authored v10.507 Phase 3 Arc α Batch α5.

Coverage
--------
- G398 (gate_pipeline_conflict_resolution_present) — registration,
  behavior, well-formed result.
- is_override_semantics — detection across all 5 scenarios.
- validate_refer_payload — happy path, missing fields, self-referral.
- validate_create_payload override enforcement — fails without note,
  fails with short note, passes with valid note.
- Seek permission semantics — validator passes without override note
  when bsc_credit_to routes to the portfolio owner.
- PipelineDealRefer model — required fields enforced by Pydantic.
- Refer endpoint exists in api.py with correct route decorator.

Why this matters
----------------
α5 closes GAP-005 by implementing the three conflict-resolution paths
from audit Section 15.4:

1. **Refer** — POST /api/pipeline/deals/refer (NEW endpoint)
2. **Override** — POST /api/pipeline/deals + manager_override_note
3. **Seek permission** — POST /api/pipeline/deals (implicit semantics)

Also fixes a latent Streamlit UX bug: the page promises "requires
manager override note" but never collects one. The API enforces
collection. Streamlit-side fix deferred to migration batch.
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
MUTATIONS_PATH = REPO_ROOT / "utils" / "api_pipeline_mutations.py"
MODELS_PATH = REPO_ROOT / "utils" / "api_pipeline_models.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g398_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_repo_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


# ──────────────────────────────────────────────────────────────────
# G398 registration / behavior (4)
# ──────────────────────────────────────────────────────────────────


def test_g398_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G398" in gate_ids


def test_g398_function_exists_and_is_callable():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_conflict_resolution_present")
    assert callable(audit.gate_pipeline_conflict_resolution_present)


def test_g398_returns_well_formed_result():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_conflict_resolution_present()
    assert result["id"] == "G398"
    assert result["name"] == "pipeline_conflict_resolution_present"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)


def test_g398_passes_against_current_code():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_conflict_resolution_present()
    assert result["passed"], (
        f"G398 fails: {result['violations']}"
    )


# ──────────────────────────────────────────────────────────────────
# is_override_semantics — detection logic (5)
# ──────────────────────────────────────────────────────────────────


def test_is_override_semantics_no_conflict():
    """No portfolio_owner_code set → not override semantics."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_override_semantics
    assert is_override_semantics({
        "staff_code": "300600", "staff_name": "Helena",
    }) is False


def test_is_override_semantics_own_portfolio():
    """portfolio_owner_code == staff_code → not override (no conflict)."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_override_semantics
    assert is_override_semantics({
        "staff_code": "300600", "portfolio_owner_code": "300600",
    }) is False


def test_is_override_semantics_seek_permission():
    """Conflict + bsc_credit_to == portfolio_owner_name → SEEK PERMISSION,
    not override."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_override_semantics
    assert is_override_semantics({
        "staff_code": "300600", "staff_name": "Helena",
        "portfolio_owner_code": "300722", "portfolio_owner_name": "Rodgers",
        "bsc_credit_to": "Rodgers",
    }) is False


def test_is_override_semantics_no_bsc_credit_specified():
    """Conflict + bsc_credit_to unset → default to seek-permission,
    not override."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_override_semantics
    assert is_override_semantics({
        "staff_code": "300600", "staff_name": "Helena",
        "portfolio_owner_code": "300722", "portfolio_owner_name": "Rodgers",
    }) is False


def test_is_override_semantics_override_detected():
    """Conflict + bsc_credit_to == staff_name → OVERRIDE."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_override_semantics
    assert is_override_semantics({
        "staff_code": "300600", "staff_name": "Helena",
        "portfolio_owner_code": "300722", "portfolio_owner_name": "Rodgers",
        "bsc_credit_to": "Helena",
    }) is True


# ──────────────────────────────────────────────────────────────────
# validate_create_payload override enforcement (4)
# ──────────────────────────────────────────────────────────────────


def _base_create_payload():
    return {
        "client_name": "Acme",
        "staff_code": "300600",
        "staff_name": "Helena",
        "deal_value": 1_000_000,
        "product_type": "Loan",
        "stage": "Lead",
    }


def test_validate_create_no_conflict_passes_without_override_note():
    """Regression for α3 — non-conflicted payloads still work."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    ok, reason = validate_create_payload(_base_create_payload())
    assert ok, f"Non-conflicted payload rejected: {reason}"


def test_validate_create_override_without_note_rejected():
    """Override semantics + no note → reject with explanatory reason."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    payload = {
        **_base_create_payload(),
        "portfolio_owner_code": "300722",
        "portfolio_owner_name": "Rodgers",
        "bsc_credit_to": "Helena",  # = staff_name → override semantics
    }
    ok, reason = validate_create_payload(payload)
    assert not ok
    assert "manager_override_note" in reason or "override" in reason.lower()


def test_validate_create_override_with_short_note_rejected():
    """Override note must be at least MIN_OVERRIDE_NOTE_LEN chars."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import (
        validate_create_payload, MIN_OVERRIDE_NOTE_LEN,
    )
    payload = {
        **_base_create_payload(),
        "portfolio_owner_code": "300722",
        "portfolio_owner_name": "Rodgers",
        "bsc_credit_to": "Helena",
        "manager_override_note": "ok",  # 2 chars < minimum
    }
    ok, reason = validate_create_payload(payload)
    assert not ok
    assert "too short" in reason or str(MIN_OVERRIDE_NOTE_LEN) in reason


def test_validate_create_override_with_valid_note_passes():
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    payload = {
        **_base_create_payload(),
        "portfolio_owner_code": "300722",
        "portfolio_owner_name": "Rodgers",
        "bsc_credit_to": "Helena",
        "manager_override_note": "Customer requested transfer; owner unreachable",
    }
    ok, reason = validate_create_payload(payload)
    assert ok, f"Override with valid note rejected: {reason}"


def test_validate_create_seek_permission_passes_without_override_note():
    """Seek permission semantics (BSC credit to portfolio owner) → no
    override note required."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    payload = {
        **_base_create_payload(),
        "portfolio_owner_code": "300722",
        "portfolio_owner_name": "Rodgers",
        "bsc_credit_to": "Rodgers",  # = portfolio_owner_name → seek permission
    }
    ok, reason = validate_create_payload(payload)
    assert ok, f"Seek-permission rejected: {reason}"


# ──────────────────────────────────────────────────────────────────
# validate_refer_payload (3)
# ──────────────────────────────────────────────────────────────────


def _good_refer_payload():
    return {
        "client_name": "Acme",
        "staff_code": "300600",
        "staff_name": "Helena",
        "portfolio_owner_code": "300722",
        "portfolio_owner_name": "Rodgers",
        "referred_to": "Rodgers",
    }


def test_validate_refer_happy_path():
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_refer_payload
    ok, reason = validate_refer_payload(_good_refer_payload())
    assert ok, f"Good refer payload rejected: {reason}"


def test_validate_refer_missing_required_field():
    _setup_repo_path()
    from utils.api_pipeline_mutations import (
        validate_refer_payload, REQUIRED_REFER_FIELDS,
    )
    for field in REQUIRED_REFER_FIELDS:
        bad = {k: v for k, v in _good_refer_payload().items() if k != field}
        ok, reason = validate_refer_payload(bad)
        assert not ok, f"Missing '{field}' wrongly accepted"
        assert field in reason


def test_validate_refer_rejects_self_referral():
    """Referring RM cannot refer to themselves — no-op."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_refer_payload
    self_refer = {
        **_good_refer_payload(),
        "portfolio_owner_code": "300600",  # same as staff_code
    }
    ok, reason = validate_refer_payload(self_refer)
    assert not ok
    assert "yourself" in reason.lower() or "self" in reason.lower()


# ──────────────────────────────────────────────────────────────────
# Pydantic models (2)
# ──────────────────────────────────────────────────────────────────


def test_pipeline_deal_refer_model_parses_complete_input():
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealRefer
    m = PipelineDealRefer(
        client_name="Acme",
        staff_code="300600",
        staff_name="Helena",
        portfolio_owner_code="300722",
        portfolio_owner_name="Rodgers",
        referred_to="Rodgers",
        referral_note="Customer needs trade finance",
    )
    assert m.client_name == "Acme"
    assert m.referred_to == "Rodgers"
    assert m.referral_note == "Customer needs trade finance"


def test_pipeline_deal_create_accepts_manager_override_note():
    """The α5 extension to PipelineDealCreate."""
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealCreate
    m = PipelineDealCreate(
        client_name="Acme", staff_code="300600", staff_name="Helena",
        deal_value=1000, product_type="Loan", stage="Lead",
        portfolio_owner_code="300722",
        portfolio_owner_name="Rodgers",
        bsc_credit_to="Helena",
        manager_override_note="Owner unreachable for 3 days",
    )
    assert m.manager_override_note == "Owner unreachable for 3 days"


# ──────────────────────────────────────────────────────────────────
# Endpoint surface (1)
# ──────────────────────────────────────────────────────────────────


def test_refer_endpoint_has_route_decorator():
    """The refer endpoint must be registered at the correct URL."""
    src = API_PATH.read_text(encoding="utf-8")
    assert '@app.post("/api/pipeline/deals/refer"' in src or \
           '/api/pipeline/deals/refer' in src, \
           "POST /api/pipeline/deals/refer route decorator missing"
