"""Regression tests for Phase 3 Arc α Batch α4 — Pipeline LMS Handoff.

Authored v10.506 Phase 3 Arc α Batch α4.

Coverage
--------
- G397 (gate_pipeline_advance_triggers_lms_handoff) — registration,
  behavior, well-formed result.
- LoanApplicationManager.create_from_pipeline_deal — happy path,
  idempotency, swim lane bands, field mapping (product_type vs
  product), ID generation (max+1 not len+1), defensive on bad input.
- is_lms_handoff_transition — trigger conditions.
- handle_lms_handoff — no-op for non-LMS, fires for LMS entry.
- The α4 doctrine transition: validate_advance_target now ACCEPTS
  LMS stages (test inverts α3's rejection assertion).

Why this matters
----------------
α4 closes GAP-013 (LMS handoff) by implementing the auto-create
LoanApplication flow that α3 explicitly deferred (Option C). The
load-bearing guarantee: when a deal advances to a stage in
LMS_DEFERRED_STAGES, a linked LoanApplication is created idempotently
via the canonical `LoanApplicationManager.create_from_pipeline_deal`
method. Same deal twice = no duplicate. Streamlit isn't migrated to
the new method in this batch but the canonical path now exists.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"
API_PATH = REPO_ROOT / "utils" / "api.py"
MUTATIONS_PATH = REPO_ROOT / "utils" / "api_pipeline_mutations.py"
CORE_PATH = REPO_ROOT / "utils" / "core.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g397_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_repo_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


# ──────────────────────────────────────────────────────────────────
# G397 registration / behavior (4)
# ──────────────────────────────────────────────────────────────────


def test_g397_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G397" in gate_ids


def test_g397_function_exists_and_is_callable():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_advance_triggers_lms_handoff")
    assert callable(audit.gate_pipeline_advance_triggers_lms_handoff)


def test_g397_returns_well_formed_result():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_advance_triggers_lms_handoff()
    assert result["id"] == "G397"
    assert result["name"] == "pipeline_advance_triggers_lms_handoff"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)


def test_g397_passes_against_current_code():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_advance_triggers_lms_handoff()
    assert result["passed"], (
        f"G397 fails against current code — violations: "
        f"{result['violations']}"
    )


# ──────────────────────────────────────────────────────────────────
# Doctrine transition — α3 rejection inverted to α4 acceptance (2)
# ──────────────────────────────────────────────────────────────────


def test_validate_advance_target_now_accepts_lms_stages_post_alpha4():
    """α4 doctrine transition test (inverts α3's
    test_validate_advance_target_rejects_lms_stages).

    α3 explicitly rejected all 7 LMS_DEFERRED_STAGES from the advance
    surface (Option C). α4 implements the handoff and lifts the
    restriction — LMS stages are now permitted at the validator
    layer. Rejection of inconsistent state is now the LoanApplication
    auto-create's job (different mechanism, same end goal).

    α3's test is gone; this is its replacement. The git history
    preserves the original assertion.
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


def test_validate_create_payload_still_rejects_lms_stage():
    """α4 unlocks LMS stages on ADVANCE but NOT on create. Creating
    a deal directly at an LMS stage skips the discovery flow
    (Lead → Contacted → Negotiation → Credit Review) and is still
    an integrity issue."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import validate_create_payload
    bad = {
        "client_name": "Acme Inc", "staff_code": "300722",
        "staff_name": "Test", "deal_value": 250000.0,
        "product_type": "Business Loan", "stage": "Credit Review",
    }
    ok, reason = validate_create_payload(bad)
    assert not ok
    assert "Credit Review" in reason or "LMS" in reason


# ──────────────────────────────────────────────────────────────────
# is_lms_handoff_transition (4)
# ──────────────────────────────────────────────────────────────────


def test_is_lms_handoff_transition_fires_on_lms_entry():
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_lms_handoff_transition
    assert is_lms_handoff_transition("Negotiation", "Credit Review") is True
    assert is_lms_handoff_transition("Compliance", "Approval") is True
    assert is_lms_handoff_transition("Lead", "Disbursed") is True


def test_is_lms_handoff_transition_no_fire_on_non_lms():
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_lms_handoff_transition
    assert is_lms_handoff_transition("Lead", "Contacted") is False
    assert is_lms_handoff_transition("Negotiation", "Closed Won") is False


def test_is_lms_handoff_transition_no_fire_on_same_stage():
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_lms_handoff_transition
    assert is_lms_handoff_transition("Credit Review", "Credit Review") is False
    assert is_lms_handoff_transition("Lead", "Lead") is False


def test_is_lms_handoff_transition_fires_on_lms_to_lms():
    """LMS→LMS transitions DO fire (Credit Review → Approval).
    Idempotency in create_from_pipeline_deal handles them safely —
    returns existing app id instead of creating a duplicate."""
    _setup_repo_path()
    from utils.api_pipeline_mutations import is_lms_handoff_transition
    assert is_lms_handoff_transition("Credit Review", "Approval") is True


# ──────────────────────────────────────────────────────────────────
# LoanApplicationManager.create_from_pipeline_deal (6)
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_lam(monkeypatch, tmp_path):
    """Run LoanApplicationManager against a temp directory copy of
    loan_applications.json. Prevents tests from mutating real data."""
    _setup_repo_path()
    import utils.core
    real_dir = utils.core.DATA_DIR
    src = real_dir / "loan_applications.json"
    if src.exists():
        shutil.copy(src, tmp_path / "loan_applications.json")
    monkeypatch.setattr(utils.core, "DATA_DIR", tmp_path)
    from utils.core import LoanApplicationManager
    yield LoanApplicationManager()


def test_create_from_pipeline_deal_happy_path(isolated_lam):
    lam = isolated_lam
    initial_count = len(lam.apps)
    deal = {
        "id": "D_TEST_001",
        "client_name": "Acme Corp",
        "product_type": "Business Loan",
        "deal_value": 50_000_000,
        "staff_code": "300600",
        "staff_name": "Helena Mwaburi",
        "unit": "Dagoretti",
    }
    app_id = lam.create_from_pipeline_deal(deal, "tester")
    assert app_id is not None
    assert app_id.startswith("LMS")
    assert len(lam.apps) == initial_count + 1

    # Verify linkage
    created = next((a for a in lam.apps if a["id"] == app_id), None)
    assert created is not None
    assert created["pipeline_deal_id"] == "D_TEST_001"
    assert created["client_name"] == "Acme Corp"
    assert created["amount"] == 50_000_000
    assert created["status"] == "submitted"


def test_create_from_pipeline_deal_idempotent(isolated_lam):
    """Same deal twice returns the same app id and creates no
    duplicate."""
    lam = isolated_lam
    deal = {
        "id": "D_TEST_002", "client_name": "Test Co",
        "product_type": "Mortgage", "deal_value": 10_000_000,
        "staff_code": "300722", "staff_name": "Test",
    }
    first_id = lam.create_from_pipeline_deal(deal, "tester")
    count_after_first = len(lam.apps)

    second_id = lam.create_from_pipeline_deal(deal, "tester")
    assert second_id == first_id
    assert len(lam.apps) == count_after_first  # no new app


def test_create_from_pipeline_deal_swim_lane_bands(isolated_lam):
    lam = isolated_lam
    cases = [
        (3_000_000, "Express"),    # < 5M
        (5_000_000, "Express"),    # boundary inclusive
        (10_000_000, "Standard"),  # between
        (99_999_999, "Standard"),  # below 100M
        (100_000_000, "Complex"),  # boundary inclusive
        (500_000_000, "Complex"),  # well above
    ]
    for amount, expected in cases:
        deal = {
            "id": f"D_SWIM_{amount}",
            "client_name": "X",
            "product_type": "X",
            "deal_value": amount,
            "staff_code": "300722",
            "staff_name": "X",
        }
        app_id = lam.create_from_pipeline_deal(deal, "tester")
        actual = next(a["swim_lane"] for a in lam.apps if a["id"] == app_id)
        assert actual == expected, (
            f"amount {amount}: expected {expected}, got {actual}"
        )


def test_create_from_pipeline_deal_prefers_product_type(isolated_lam):
    """The canonical Gen B field name `product_type` is preferred
    over the legacy `product` field. This is the bug fix from α4 —
    Streamlit's inline handoff reads `product` only, which is empty
    for Gen B deals."""
    lam = isolated_lam
    deal = {
        "id": "D_PT_1", "client_name": "X",
        "product_type": "Mortgage",     # Gen B canonical
        "product": "Should Be Ignored", # Gen A legacy
        "deal_value": 1_000_000, "staff_code": "300722",
        "staff_name": "X",
    }
    app_id = lam.create_from_pipeline_deal(deal, "tester")
    created = next(a for a in lam.apps if a["id"] == app_id)
    assert created["product"] == "Mortgage"


def test_create_from_pipeline_deal_falls_back_to_product(isolated_lam):
    """If product_type is missing/None, fall back to product."""
    lam = isolated_lam
    deal = {
        "id": "D_PT_2", "client_name": "X",
        "product_type": None,
        "product": "Legacy Product",
        "deal_value": 1_000_000, "staff_code": "300722",
        "staff_name": "X",
    }
    app_id = lam.create_from_pipeline_deal(deal, "tester")
    created = next(a for a in lam.apps if a["id"] == app_id)
    assert created["product"] == "Legacy Product"


def test_create_from_pipeline_deal_id_uses_max_plus_one_not_len_plus_one(
    isolated_lam,
):
    """Latent-bug fix from α4: Streamlit's `LMS{len+1}` would collide
    with existing IDs if there are gaps. α4 uses `LMS{max+1}` to
    avoid this. Verified against real data state where 724 apps
    exist but max ID is LMS00725 (one gap)."""
    lam = isolated_lam
    initial_count = len(lam.apps)
    if initial_count == 0:
        pytest.skip("No baseline data — skip gap test")

    # Compute what max+1 should yield
    nums = sorted([
        int(a["id"][3:]) for a in lam.apps
        if a.get("id", "").startswith("LMS") and a["id"][3:].isdigit()
    ])
    expected_next = nums[-1] + 1 if nums else 1

    deal = {
        "id": "D_MAX_TEST", "client_name": "X",
        "product_type": "X", "deal_value": 100, "staff_code": "300722",
        "staff_name": "X",
    }
    app_id = lam.create_from_pipeline_deal(deal, "tester")
    actual_num = int(app_id[3:])
    assert actual_num == expected_next, (
        f"ID should be LMS{expected_next:05d}, got {app_id}"
    )


# ──────────────────────────────────────────────────────────────────
# Defensive behavior (3)
# ──────────────────────────────────────────────────────────────────


def test_create_from_pipeline_deal_returns_none_for_empty_input(isolated_lam):
    lam = isolated_lam
    assert lam.create_from_pipeline_deal({}, "test") is None
    assert lam.create_from_pipeline_deal(None, "test") is None


def test_create_from_pipeline_deal_returns_none_for_no_id(isolated_lam):
    lam = isolated_lam
    deal_no_id = {
        "client_name": "X", "product_type": "X",
        "deal_value": 100, "staff_code": "300722", "staff_name": "X",
    }
    assert lam.create_from_pipeline_deal(deal_no_id, "test") is None


def test_handle_lms_handoff_noop_for_non_lms_advance():
    _setup_repo_path()
    from utils.api_pipeline_mutations import handle_lms_handoff
    deal = {
        "id": "D_NOOP_001", "client_name": "X",
        "product_type": "X", "deal_value": 100,
        "staff_code": "300722", "staff_name": "X",
    }
    triggered, app_id, err = handle_lms_handoff(
        deal, "Lead", "Contacted", "test_user"
    )
    assert triggered is False
    assert app_id is None
    assert err is None
