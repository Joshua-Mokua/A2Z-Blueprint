"""Regression tests for Phase 3 Arc α Batch α3 — Pipeline CRUD +
Advance + BSC trigger.

Authored v10.505 Phase 3 Arc α Batch α3.

Coverage
--------
- G396 (gate_pipeline_api_crud_present) — registration, behavior,
  well-formed result, counter-test.
- Mutation helpers (`utils/api_pipeline_mutations.py`) — validation
  for create payloads, advance targets, the LMS allowlist
  (load-bearing — this is the Option C guarantee).
- Endpoint surface — three FastAPI route definitions exist.
- Pydantic mutation models — request/response shapes.
- BSC trigger fallback — emit_bsc_trigger never crashes the caller.
- Cache invalidation — invalidate_pipeline_caches clears the
  pipeline_summary entry from the in-memory cache.

Why this matters
----------------
α3 is the first batch in Arc α that lets the API mutate pipeline
state. The load-bearing guarantee is **Option C**: the advance
endpoint maintains an explicit allowlist of safe stages; LMS-handoff
stages are rejected with HTTP 400 until α4 implements
LoanApplication auto-creation. If any future batch silently widens
the allowlist (or removes the validate_advance_target call), G396
fails AND these tests fail. Defense in depth.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"
API_PATH = REPO_ROOT / "utils" / "api.py"
MUTATIONS_PATH = REPO_ROOT / "utils" / "api_pipeline_mutations.py"
MODELS_PATH = REPO_ROOT / "utils" / "api_pipeline_models.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g396_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_repo_path():
    import sys
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


# ──────────────────────────────────────────────────────────────────
# Gate registration / behavior (4)
# ──────────────────────────────────────────────────────────────────


def test_g396_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G396" in gate_ids


def test_g396_function_exists_and_is_callable():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_api_crud_present")
    assert callable(audit.gate_pipeline_api_crud_present)


def test_g396_returns_well_formed_result():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_api_crud_present()
    assert result["id"] == "G396"
    assert result["name"] == "pipeline_api_crud_present"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)
    assert isinstance(result["summary"], str)


def test_g396_passes_against_current_code():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_api_crud_present()
    assert result["passed"], (
        f"G396 fails against current code — violations: "
        f"{result['violations']}"
    )


# ──────────────────────────────────────────────────────────────────
# Endpoint surface (2)
# ──────────────────────────────────────────────────────────────────


def test_three_mutation_endpoints_exist_in_api():
    """The three Batch α3 endpoint functions must be present."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))
    fn_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    expected = {
        "pipeline_deal_create",
        "pipeline_deal_update",
        "pipeline_deal_advance",
    }
    missing = expected - fn_names
    assert not missing, f"Missing endpoint functions: {sorted(missing)}"


def test_mutation_endpoints_have_route_decorators():
    """Each endpoint must have a @app.post or @app.put decorator."""
    src = API_PATH.read_text(encoding="utf-8")
    assert '@app.post("/api/pipeline/deals"' in src or \
           '@app.post(\n    "/api/pipeline/deals"' in src, \
           "POST /api/pipeline/deals route decorator missing"
    assert '@app.put("/api/pipeline/deals/{deal_id}"' in src or \
           '@app.put(\n    "/api/pipeline/deals/{deal_id}"' in src, \
           "PUT /api/pipeline/deals/{deal_id} route decorator missing"
    assert '@app.post("/api/pipeline/deals/{deal_id}/advance"' in src or \
           '/advance"' in src, \
           "POST /api/pipeline/deals/{deal_id}/advance route decorator missing"


# ──────────────────────────────────────────────────────────────────
# Validation logic (5)
# ──────────────────────────────────────────────────────────────────


def test_validate_create_payload_accepts_complete_input():
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    good = {
        "client_name": "Acme Inc",
        "staff_code": "300722",
        "staff_name": "Test User",
        "deal_value": 250000.0,
        "product_type": "Business Loan",
        "stage": "Lead",
    }
    ok, reason = validate_create_payload(good)
    assert ok, f"Good payload rejected: {reason}"
    assert reason == ""


def test_validate_create_payload_rejects_missing_required():
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    bad = {"client_name": "Acme"}
    ok, reason = validate_create_payload(bad)
    assert not ok
    assert "Missing required field" in reason


def test_validate_create_payload_rejects_negative_deal_value():
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    bad = {
        "client_name": "Acme Inc",
        "staff_code": "300722",
        "staff_name": "Test User",
        "deal_value": -50000.0,
        "product_type": "Business Loan",
        "stage": "Lead",
    }
    ok, reason = validate_create_payload(bad)
    assert not ok
    assert "non-negative" in reason


def test_validate_create_payload_rejects_lms_stage():
    """Cannot create a deal directly at an LMS-handoff stage. This
    is the load-bearing Option C guarantee at the create surface."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    bad = {
        "client_name": "Acme Inc",
        "staff_code": "300722",
        "staff_name": "Test User",
        "deal_value": 250000.0,
        "product_type": "Business Loan",
        "stage": "Credit Review",   # LMS stage
    }
    ok, reason = validate_create_payload(bad)
    assert not ok
    assert "LMS handoff" in reason or "Arc α4" in reason


def test_validate_advance_target_no_longer_rejects_lms_stages_post_alpha4():
    """ALPHA4 DOCTRINE TRANSITION (Phase 3 Arc α Batch α4): this test
    REPLACES the original α3 assertion that LMS stages get rejected.
    α4 implements the LoanApplication auto-create handoff and lifts
    the restriction — LMS stages are now permitted at the validator
    layer.

    The original α3 assertion was: 'Each of the 7 LMS-deferred stages
    must be rejected.' That was correct for α3's Option C scope.
    α4 supersedes it. See REVIVAL_LEDGER for the explicit transition
    record. tests/test_pipeline_lms_handoff.py covers the new
    handoff mechanism end-to-end.
    """
    _setup_repo_path()
    from utils.api_pipeline_mutations import (
        validate_advance_target, LMS_DEFERRED_STAGES,
    )
    for stage in LMS_DEFERRED_STAGES:
        ok, reason = validate_advance_target(stage)
        assert ok, (
            f"LMS stage '{stage}' wrongly rejected post-α4. "
            f"reason: {reason}"
        )


def test_validate_advance_target_accepts_allowed_stages():
    """Non-LMS stages from the canonical pipeline vocabularies must
    be accepted."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import (
        validate_advance_target, ALLOWED_ADVANCE_STAGES,
    )
    # Sample a representative subset
    for stage in ("Lead", "Contacted", "Qualified", "Closed Won",
                  "Closed Lost"):
        assert stage in ALLOWED_ADVANCE_STAGES
        ok, reason = validate_advance_target(stage)
        assert ok, f"Allowed stage '{stage}' rejected: {reason}"


# ──────────────────────────────────────────────────────────────────
# Stage sets — invariants (2)
# ──────────────────────────────────────────────────────────────────


def test_allowed_and_lms_stage_sets_are_disjoint():
    """The two sets must never overlap. A stage that's allowed AND
    deferred is a contradiction."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import (
        ALLOWED_ADVANCE_STAGES, LMS_DEFERRED_STAGES,
    )
    overlap = ALLOWED_ADVANCE_STAGES & LMS_DEFERRED_STAGES
    assert not overlap, (
        f"ALLOWED_ADVANCE_STAGES and LMS_DEFERRED_STAGES overlap: "
        f"{overlap} — contradictory invariant"
    )


def test_lms_deferred_stages_matches_audit_section_15_7():
    """The 7 LMS-deferred stages must match PIPELINE_DOMAIN_AUDIT
    Section 15.7 exactly. If the audit and the code diverge, one
    needs to be corrected — the test fails to surface that."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import LMS_DEFERRED_STAGES
    expected = {
        "Credit Review", "Approval", "Bank Approval",
        "Credit Committee", "Documentation", "Vetting", "Disbursed",
    }
    assert LMS_DEFERRED_STAGES == expected, (
        f"LMS_DEFERRED_STAGES drift from audit Section 15.7. "
        f"Code: {LMS_DEFERRED_STAGES}. Audit: {expected}"
    )


# ──────────────────────────────────────────────────────────────────
# Pydantic mutation models (3)
# ──────────────────────────────────────────────────────────────────


def test_pipeline_deal_create_model_exists():
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealCreate
    m = PipelineDealCreate(
        client_name="Test",
        staff_code="300722",
        staff_name="Test",
        deal_value=100.0,
        product_type="X",
        stage="Lead",
    )
    assert m.client_name == "Test"
    assert m.deal_value == 100.0


def test_pipeline_deal_create_rejects_missing_field_via_pydantic():
    """Pydantic itself enforces required fields; the validate_create_payload
    is for defensive depth + custom rules (LMS stage, negative value)."""
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealCreate
    with pytest.raises(Exception):  # ValidationError or similar
        PipelineDealCreate(client_name="OnlyThis")


def test_pipeline_deal_advance_model_parses():
    _setup_repo_path()
    from utils.api_pipeline_models import PipelineDealAdvance
    m = PipelineDealAdvance(new_stage="Contacted", note="moved forward")
    assert m.new_stage == "Contacted"
    assert m.note == "moved forward"


# ──────────────────────────────────────────────────────────────────
# Side-effect helpers (2)
# ──────────────────────────────────────────────────────────────────


def test_emit_bsc_trigger_returns_false_for_empty_username():
    """BSC trigger should silently no-op for empty username (matches
    Streamlit's defensive pattern)."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import emit_bsc_trigger
    assert emit_bsc_trigger("") is False
    assert emit_bsc_trigger(None) is False


def test_invalidate_pipeline_caches_does_not_raise():
    """Cache invalidation must be safe to call even if the api
    module is in an unexpected state."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import invalidate_pipeline_caches
    # Should not raise regardless of cache state
    invalidate_pipeline_caches()
    invalidate_pipeline_caches()  # idempotent
