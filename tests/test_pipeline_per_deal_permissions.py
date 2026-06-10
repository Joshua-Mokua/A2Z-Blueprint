"""Regression tests for Phase 3 Arc α Batch α7 — Per-deal permissions.

Authored v10.509 Phase 3 Arc α Batch α7.

Coverage
--------
- G400 plumbing (4 tests).
- resolve_deal_permissions — exhaustive scenarios across the 4
  caller-vs-deal relationships and state gates (11 tests).
- PERMISSION_KEYS invariant — exactly 6 keys matching audit Section
  15.6 spec (1 test).
- enrich_deal_with_permissions — adds permissions, doesn't mutate
  input, idempotent (3 tests).
- Endpoint surface — GET /api/pipeline/deals/{id} present + the 3
  list endpoints call enrich (2 tests).

Why this matters
----------------
α7 closes GAP-012. Without per-deal permissions, the React UI has
two bad choices: (a) duplicate authorization logic in TypeScript
(drift risk against the server's is_manager + scope rules), or
(b) attempt actions and handle HTTP 403 errors (terrible UX —
buttons that the user "shouldn't" click would still render).

The 6-permission contract is load-bearing for the React UI design.
If the resolution logic changes silently, the UI either shows
buttons that 403 or hides buttons that would have worked. G400 +
these tests are the structural guard.
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
PERMS_PATH = REPO_ROOT / "utils" / "api_pipeline_permissions.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g400_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _setup_repo_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


# ──────────────────────────────────────────────────────────────────
# G400 plumbing (4)
# ──────────────────────────────────────────────────────────────────


def test_g400_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G400" in gate_ids


def test_g400_function_exists_and_is_callable():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_per_deal_permissions_present")
    assert callable(audit.gate_pipeline_per_deal_permissions_present)


def test_g400_returns_well_formed_result():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_per_deal_permissions_present()
    assert result["id"] == "G400"
    assert result["name"] == "pipeline_per_deal_permissions_present"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)


def test_g400_passes_against_current_code():
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_per_deal_permissions_present()
    assert result["passed"], f"G400 fails: {result['violations']}"


# ──────────────────────────────────────────────────────────────────
# PERMISSION_KEYS invariant (1)
# ──────────────────────────────────────────────────────────────────


def test_permission_keys_match_audit_section_15_6():
    """The 6-permission contract from PIPELINE_DOMAIN_AUDIT.md
    Section 15.6 + GAP-012. If this set drifts, the React UI's
    permission consumers will break in subtle ways."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import PERMISSION_KEYS
    expected = {
        "can_view",
        "can_edit",
        "can_advance_stage",
        "can_request_cancel",
        "can_approve_cancel",
        "can_validate",
    }
    assert set(PERMISSION_KEYS) == expected, (
        f"PERMISSION_KEYS drift. Expected: {expected}. "
        f"Got: {set(PERMISSION_KEYS)}"
    )
    assert len(PERMISSION_KEYS) == 6


# ──────────────────────────────────────────────────────────────────
# Relationship scenarios (5)
# ──────────────────────────────────────────────────────────────────


def _base_deal(stage="Lead", **extra):
    """Minimum deal record for permission tests."""
    return {
        "id": "D_TEST",
        "staff_code": "300600",
        "stage": stage,
        "backup_staff_codes": extra.pop("backup_staff_codes", []),
        **extra,
    }


def test_owner_of_active_deal_has_full_owner_permissions():
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal()
    user = {"staff_code": "300600", "role": "Teller"}
    p = resolve_deal_permissions(deal, user, {"300600"})
    assert p["can_view"] is True
    assert p["can_edit"] is True
    assert p["can_advance_stage"] is True
    assert p["can_request_cancel"] is True
    assert p["can_approve_cancel"] is False  # owner cannot approve own cancel
    assert p["can_validate"] is False  # owner is not a manager


def test_backup_only_cannot_edit_but_can_advance():
    """Section 15.6 line 656: 'You can move the stage but not edit details.'"""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(backup_staff_codes=["300722"])
    user = {"staff_code": "300722", "role": "Teller"}
    p = resolve_deal_permissions(deal, user, {"300722"})
    assert p["can_view"] is True
    assert p["can_edit"] is False  # the load-bearing backup-only rule
    assert p["can_advance_stage"] is True
    assert p["can_request_cancel"] is True
    assert p["can_approve_cancel"] is False
    assert p["can_validate"] is False


def test_manager_in_scope_has_full_manager_permissions():
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(stage="Contacted")
    user = {"staff_code": "300100", "role": "Branch Manager"}
    p = resolve_deal_permissions(deal, user, {"300100", "300600"})
    assert p["can_view"] is True
    assert p["can_edit"] is True
    assert p["can_advance_stage"] is True
    assert p["can_request_cancel"] is True
    assert p["can_approve_cancel"] is False  # no pending cancel
    assert p["can_validate"] is True  # Contacted is in validation stage


def test_out_of_scope_user_has_all_false_permissions():
    """A user who is not owner, not backup, not manager-in-scope sees
    no permissions on this deal — equivalent to not being able to see
    the deal at all."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import (
        resolve_deal_permissions, PERMISSION_KEYS,
    )
    deal = _base_deal()
    user = {"staff_code": "999999", "role": "Teller"}
    p = resolve_deal_permissions(deal, user, {"999999"})
    for k in PERMISSION_KEYS:
        assert p[k] is False, f"out-of-scope user wrongly has {k}=True"


def test_admin_user_treated_as_manager_with_full_scope():
    """is_admin=True overrides everything — admin is a manager and
    visible_codes doesn't constrain them."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(stage="Contacted")
    user = {"staff_code": "100", "is_admin": True}
    # Narrow visible_codes — admin should still be in scope
    p = resolve_deal_permissions(deal, user, {"100"})
    assert p["can_view"] is True
    assert p["can_edit"] is True
    assert p["can_validate"] is True  # admin treated as manager


# ──────────────────────────────────────────────────────────────────
# State gates (4)
# ──────────────────────────────────────────────────────────────────


def test_terminal_stage_blocks_advance_and_cancel_request():
    """At Closed Won/Lost, the deal is done — no advance, no new
    cancel request, even for the owner."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    for terminal in ("Closed Won", "Closed Lost"):
        deal = _base_deal(stage=terminal)
        user = {"staff_code": "300600"}
        p = resolve_deal_permissions(deal, user, {"300600"})
        assert p["can_view"] is True
        assert p["can_edit"] is True  # editing closed deals is OK
        assert p["can_advance_stage"] is False, f"advance from {terminal}"
        assert p["can_request_cancel"] is False, f"cancel from {terminal}"


def test_pending_cancel_blocks_new_cancel_request():
    """A deal that already has cancel_requested=True cannot have a
    new cancel request issued — would be a duplicate."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(stage="Negotiation", cancel_requested=True)
    user = {"staff_code": "300600"}
    p = resolve_deal_permissions(deal, user, {"300600"})
    assert p["can_request_cancel"] is False


def test_pending_cancel_allows_approve_for_manager():
    """The flip side: a manager-in-scope with a pending cancel
    request can approve it (this is the validation queue action)."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(stage="Negotiation", cancel_requested=True)
    user = {"staff_code": "300100", "role": "Branch Manager"}
    p = resolve_deal_permissions(deal, user, {"300100", "300600"})
    assert p["can_approve_cancel"] is True


def test_already_validated_deal_blocks_validate():
    """can_validate must be False once manager_validated=True."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(stage="Contacted", manager_validated=True)
    user = {"staff_code": "300100", "role": "Branch Manager"}
    p = resolve_deal_permissions(deal, user, {"300100", "300600"})
    assert p["can_validate"] is False


def test_draft_deal_blocks_validate():
    """Drafts are explicitly excluded from validation per
    Streamlit's queue filter (line 1294 has `not d.get('draft')`)."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    deal = _base_deal(stage="Contacted", draft=True)
    user = {"staff_code": "300100", "role": "Branch Manager"}
    p = resolve_deal_permissions(deal, user, {"300100", "300600"})
    assert p["can_validate"] is False


# ──────────────────────────────────────────────────────────────────
# enrich_deal_with_permissions wrapper (2)
# ──────────────────────────────────────────────────────────────────


def test_enrich_adds_permissions_field_without_mutating_input():
    _setup_repo_path()
    from utils.api_pipeline_permissions import enrich_deal_with_permissions
    original = _base_deal()
    enriched = enrich_deal_with_permissions(
        original, {"staff_code": "300600"}, {"300600"}
    )
    assert "permissions" in enriched
    assert "permissions" not in original  # input not mutated
    assert isinstance(enriched["permissions"], dict)
    # All 6 keys present
    assert set(enriched["permissions"].keys()) == {
        "can_view", "can_edit", "can_advance_stage",
        "can_request_cancel", "can_approve_cancel", "can_validate",
    }


def test_enrich_overwrites_existing_permissions_field():
    """If a deal record somehow already has a permissions key (from
    a stale fixture or upstream system), the enrichment overwrites
    it with the freshly computed values."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import enrich_deal_with_permissions
    stale = _base_deal()
    stale["permissions"] = {"junk": True}
    enriched = enrich_deal_with_permissions(
        stale, {"staff_code": "300600"}, {"300600"}
    )
    assert "junk" not in enriched["permissions"]
    assert "can_view" in enriched["permissions"]


# ──────────────────────────────────────────────────────────────────
# Defensive (2)
# ──────────────────────────────────────────────────────────────────


def test_resolve_handles_empty_deal_gracefully():
    """Empty / None / malformed inputs return all-False, not raise."""
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    p = resolve_deal_permissions({}, {"staff_code": "X"}, set())
    assert all(v is False for v in p.values())

    p = resolve_deal_permissions(None, {"staff_code": "X"}, set())
    assert all(v is False for v in p.values())


def test_resolve_handles_empty_user_gracefully():
    _setup_repo_path()
    from utils.api_pipeline_permissions import resolve_deal_permissions
    p = resolve_deal_permissions(_base_deal(), None, set())
    assert all(v is False for v in p.values())

    p = resolve_deal_permissions(_base_deal(), {}, set())
    assert all(v is False for v in p.values())


# ──────────────────────────────────────────────────────────────────
# Endpoint surface (2)
# ──────────────────────────────────────────────────────────────────


def test_pipeline_deal_detail_endpoint_exists():
    """The NEW GET /api/pipeline/deals/{deal_id} endpoint."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))
    fn_names = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "pipeline_deal_detail" in fn_names

    src = API_PATH.read_text(encoding="utf-8")
    assert '/api/pipeline/deals/{deal_id}"' in src


def test_three_list_endpoints_call_enrich():
    """Each of the three list-returning GET endpoints must call
    enrich_deal_with_permissions so the React UI gets the permissions
    object on every deal."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))
    list_endpoints = {
        "pipeline_deals",
        "pipeline_queue_validation",
        "pipeline_queue_cancellation",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in list_endpoints:
            calls = any(
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "enrich_deal_with_permissions"
                for sub in ast.walk(node)
            )
            assert calls, (
                f"{node.name} does not call enrich_deal_with_permissions"
            )
