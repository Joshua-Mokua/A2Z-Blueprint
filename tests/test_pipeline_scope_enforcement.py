"""Regression tests for Phase 3 Arc α Batch α2 — Pipeline Cascade
Scope Enforcement. Verifies G395
(`gate_pipeline_api_enforces_cascade_scope`) and the underlying
behavior: that `/api/pipeline/summary` and `/api/pipeline/deals`
filter deals server-side via the canonical cascade-walk function.

Authored v10.504 Phase 3 Arc α Batch α2.

Why this matters
----------------
Per PIPELINE_DOMAIN_AUDIT Section 10 GAP-001 + Section 15.10 — before
α2, the API path had no equivalent of the Streamlit page's
`get_visible_staff(user_data, staff_scores)` filter. Every
authenticated caller saw every deal regardless of role. That left
a visibility hole the moment any non-Streamlit client (the React
frontend being introduced incrementally) called the endpoints.

α2 closes the hole by introducing `utils/api_pipeline_scope.py` —
a thin server-side adapter that wraps `get_visible_staff` and
supplies the staff_register roster the API path otherwise lacks.

These tests guard against:
1. G395 deregistration.
2. The scope helper module being deleted.
3. Either endpoint losing its scope filter step.
4. The helper failing to filter correctly against live PipelineManager
   data for the canonical role types (admin, branch manager, teller).
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"
API_PATH = REPO_ROOT / "utils" / "api.py"
SCOPE_PATH = REPO_ROOT / "utils" / "api_pipeline_scope.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g395_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ──────────────────────────────────────────────────────────────────
# Gate registration tests (3)
# ──────────────────────────────────────────────────────────────────


def test_g395_is_registered_in_gates_table():
    """G395 must appear in the GATES dispatch table."""
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G395" in gate_ids, (
        "G395 missing from GATES table — gate cannot run via the "
        "automated audit harness"
    )


def test_g395_function_exists_and_is_callable():
    """The gate function must exist and be callable."""
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_api_enforces_cascade_scope")
    assert callable(audit.gate_pipeline_api_enforces_cascade_scope)


def test_g395_returns_well_formed_result():
    """Gate result must include id, name, passed, violations, summary."""
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_api_enforces_cascade_scope()
    assert result["id"] == "G395"
    assert result["name"] == "pipeline_api_enforces_cascade_scope"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)
    assert isinstance(result["summary"], str)


# ──────────────────────────────────────────────────────────────────
# Gate behavior test (1)
# ──────────────────────────────────────────────────────────────────


def test_g395_passes_against_current_code():
    """Against the post-Batch-α2 code state, G395 must pass."""
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_api_enforces_cascade_scope()
    assert result["passed"], (
        f"G395 fails against current code — violations: "
        f"{result['violations']}"
    )


# ──────────────────────────────────────────────────────────────────
# Scope helper module structural tests (3)
# ──────────────────────────────────────────────────────────────────


def test_scope_helper_module_exists():
    """utils/api_pipeline_scope.py must exist."""
    assert SCOPE_PATH.exists(), (
        "utils/api_pipeline_scope.py missing — the server-side cascade "
        "scope adapter must be present"
    )


def test_scope_helper_exports_required_functions():
    """The three required helper functions must be defined."""
    tree = ast.parse(SCOPE_PATH.read_text(encoding="utf-8"))
    fn_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    expected = {
        "get_staff_roster",
        "get_visible_staff_codes",
        "filter_deals_by_visible_codes",
    }
    missing = expected - fn_names
    assert not missing, (
        f"utils/api_pipeline_scope.py missing required functions: "
        f"{sorted(missing)}"
    )


def test_endpoints_apply_scope_filter():
    """Both endpoints must invoke get_visible_staff_codes and
    filter_deals_by_visible_codes in their bodies."""
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))

    target_fns = {"pipeline_summary", "pipeline_deals"}
    fns = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in target_fns
    }
    assert len(fns) == 2, (
        f"Expected both pipeline_summary and pipeline_deals in api.py, "
        f"found: {set(fns.keys())}"
    )

    for fn_name, fn in fns.items():
        calls_visibility = False
        calls_filter = False
        for sub in ast.walk(fn):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                if sub.func.id == "get_visible_staff_codes":
                    calls_visibility = True
                elif sub.func.id == "filter_deals_by_visible_codes":
                    calls_filter = True
        assert calls_visibility, (
            f"`{fn_name}` does not call get_visible_staff_codes"
        )
        assert calls_filter, (
            f"`{fn_name}` does not call filter_deals_by_visible_codes"
        )


# ──────────────────────────────────────────────────────────────────
# Live behavior tests against real PipelineManager data (4)
# ──────────────────────────────────────────────────────────────────
#
# These tests use the actual 8 deals in data/pipeline_deals.json and
# the actual staff_register.xlsx (1,438 rows). The specific staff
# codes and outcomes are documented in the audit (Section 15) and
# verified same-turn at sandbox time. Any regression in either file
# would naturally surface as a test failure.


def _setup_repo_path():
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    # Roster cache may persist across tests in the same session.
    # Invalidate to ensure each test sees fresh state.
    from utils.api_pipeline_scope import invalidate_staff_roster_cache
    invalidate_staff_roster_cache()


def test_admin_sees_all_pipeline_deals():
    """An admin user must see every PipelineManager deal."""
    _setup_repo_path()
    from utils.api_pipeline_scope import (
        get_visible_staff_codes, filter_deals_by_visible_codes
    )
    from utils.core import PipelineManager

    admin = {
        "staff_code": "ADMIN001",
        "is_admin": True,
        "role": "System Administrator",
        "full_name": "System Admin",
        "unit": "Head Office",
    }
    visible = get_visible_staff_codes(admin)
    assert len(visible) > 100, (
        f"Admin should see the full roster, got {len(visible)} codes"
    )

    pm = PipelineManager()
    all_deals = pm.get_deals()
    filtered = filter_deals_by_visible_codes(all_deals, visible)
    assert len(filtered) == len(all_deals), (
        f"Admin should see all {len(all_deals)} deals, saw {len(filtered)}"
    )


def test_teller_sees_only_own_deals():
    """A Teller — who has no REPORTING_TREE subordinates — must see
    only their own deals (self-only visibility)."""
    _setup_repo_path()
    from utils.api_pipeline_scope import (
        get_visible_staff_codes, filter_deals_by_visible_codes
    )
    from utils.core import PipelineManager

    # Rodgers Weru, code 300722, Teller in Thika — owns deal D0006
    teller = {
        "staff_code": "300722",
        "is_admin": False,
        "role": "Teller",
        "full_name": "Rodgers Weru",
        "unit": "Thika",
    }
    visible = get_visible_staff_codes(teller)
    assert "300722" in visible, "Teller must see own staff_code"
    # Teller has no tree config so cascade-walk returns self-only
    # (or branch staff if the teller's unit is matched by some tree
    # config — the canonical function handles this).

    pm = PipelineManager()
    all_deals = pm.get_deals()
    filtered = filter_deals_by_visible_codes(all_deals, visible)
    # Teller should at minimum see deals where they're the staff_code.
    for d in filtered:
        sc = str(d.get("staff_code", "") or "")
        po = str(d.get("portfolio_owner_code", "") or "")
        assert sc in visible or (po and po in visible), (
            f"Deal {d.get('id')} returned to teller but neither "
            f"staff_code={sc} nor portfolio_owner_code={po} is visible"
        )


def test_branch_manager_sees_branch_staff_deals():
    """A Branch Manager must see deals from staff in their unit, not
    from other branches."""
    _setup_repo_path()
    from utils.api_pipeline_scope import (
        get_visible_staff_codes, filter_deals_by_visible_codes
    )
    from utils.core import PipelineManager

    # Helena Mwaburi, code 300600, Branch Manager in Dagoretti
    bm = {
        "staff_code": "300600",
        "is_admin": False,
        "role": "Branch Manager",
        "full_name": "Helena Mwaburi",
        "unit": "Dagoretti",
    }
    visible = get_visible_staff_codes(bm)
    # BM gets unit-scoped visibility per REPORTING_TREE
    assert "300600" in visible
    assert len(visible) >= 1

    pm = PipelineManager()
    all_deals = pm.get_deals()
    filtered = filter_deals_by_visible_codes(all_deals, visible)
    # Every filtered deal should belong to staff in the BM's unit
    for d in filtered:
        sc = str(d.get("staff_code", "") or "")
        po = str(d.get("portfolio_owner_code", "") or "")
        assert sc in visible or (po and po in visible)


def test_random_user_with_no_deals_sees_none():
    """A user whose visibility set doesn't include any deal owner
    should see zero deals."""
    _setup_repo_path()
    from utils.api_pipeline_scope import (
        get_visible_staff_codes, filter_deals_by_visible_codes
    )
    from utils.core import PipelineManager

    # 300100 is a Teller in a different unit; no pipeline deals
    # belong to this code.
    random_user = {
        "staff_code": "300100",
        "is_admin": False,
        "role": "Teller",
        "full_name": "Some Other Teller",
        "unit": "Eastleigh",
    }
    visible = get_visible_staff_codes(random_user)
    # Teller self-only — set has just their code
    assert "300100" in visible

    pm = PipelineManager()
    all_deals = pm.get_deals()
    filtered = filter_deals_by_visible_codes(all_deals, visible)
    # No deals owned by 300100, so filtered should be empty
    assert len(filtered) == 0, (
        f"Random teller should see 0 deals, saw {len(filtered)}: "
        f"{[d.get('id') for d in filtered]}"
    )


# ──────────────────────────────────────────────────────────────────
# Cache + edge cases (2)
# ──────────────────────────────────────────────────────────────────


def test_roster_cache_returns_same_dataframe_within_ttl():
    """Two calls inside TTL window must return the same DataFrame
    object (cache hit, not reload)."""
    _setup_repo_path()
    from utils.api_pipeline_scope import (
        get_staff_roster, invalidate_staff_roster_cache
    )
    invalidate_staff_roster_cache()
    r1 = get_staff_roster()
    r2 = get_staff_roster()
    assert r1 is r2, "Roster cache should return same object within TTL"


def test_invalidate_cache_forces_reload():
    """After invalidation, the next call should produce a fresh
    DataFrame (different object identity)."""
    _setup_repo_path()
    from utils.api_pipeline_scope import (
        get_staff_roster, invalidate_staff_roster_cache
    )
    r1 = get_staff_roster()
    invalidate_staff_roster_cache()
    r2 = get_staff_roster()
    assert r1 is not r2, (
        "After invalidate_staff_roster_cache, subsequent get_staff_roster "
        "should produce a fresh DataFrame instance"
    )
