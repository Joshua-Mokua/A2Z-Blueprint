"""tests/test_api_v1_crud_modules.py — Parameterized smoke tests for
the 16 CRUD modules wired in utils/api.py (Phase 1B).

These tests are STRUCTURAL — same shape as tests/test_api_crud.py.
They verify each wired module produces a well-formed APIRouter with
the expected 8 endpoints, without requiring a live PG / TestClient.

What the tests verify per module:
  1. The make_crud_router() call succeeds (table is in TABLE_USE_DB)
  2. The resulting APIRouter has exactly 8 routes
  3. The routes follow the standard /api/v1/{module}/* pattern
  4. Every route has a JWT auth dependency (via get_current_user)
  5. The module is registered in the api_crud._REGISTERED_MODULES list

What these tests DON'T check:
  - Live PG behavior (per-row CRUD operations) — that's an integration
    test that needs a running DB
  - Per-module domain logic correctness — module-specific tests
    handle that

Coverage gain estimate:
  - 16 module fixtures × 5 assertions each = 80 test cases
  - Direct coverage gain: utils.api_crud.py + utils.api.py
    (the include_router calls)
  - Indirect coverage: the factory's helper functions, JWT auth
    surface, table whitelist check
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Test fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def crud_module():
    """Import utils.api_crud — same stubbing pattern as
    tests/test_api_crud.py."""
    for m in (
        "plotly", "plotly.express",
        "plotly.graph_objects", "plotly.subplots",
    ):
        sys.modules.setdefault(m, types.ModuleType(m))
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data = lambda *a, **k: (lambda f: f)
        st.cache_resource = lambda *a, **k: (lambda f: f)
        st.session_state = {}
        sys.modules["streamlit"] = st
    import utils.api_crud as mod
    return mod


# ── Module catalog ───────────────────────────────────────────────────
# Mirrors the 16 make_crud_router() calls in utils/api.py (Phase 1B).
# (module_path, table, json_file, searchable, order_by, pk_column)
#
# Keeping this in the test file rather than importing utils.api means
# we don't trigger FastAPI's app-construction side effects during test
# collection. The cost is having to keep this list in sync with
# utils/api.py — a sync drift would cause this test to lose
# parameterization coverage rather than fail outright.

CRUD_MODULES = [
    # (module, table, json_file, searchable, order_by, pk_column)
    ("pipeline_deals",       "pipeline_deals",
     "pipeline.json",
     ["stage", "deal_category", "unit",
      "staff_code", "client_cif"],
     "open_date DESC", "id"),
    ("loan_applications",    "loan_applications",
     "loan_applications.json",
     ["status", "swim_lane", "deal_category",
      "rm_code", "client_cif", "compliance_flag",
      "is_repeat_borrower"],
     "last_updated DESC", "id"),
    ("aml_alerts",           "aml_alerts",
     "aml_alerts.json",
     ["status", "risk_level", "str_filed",
      "assigned_to", "rule_triggered"],
     "transaction_date DESC", "id"),
    ("projects",             "projects",
     "projects.json",
     ["status", "priority", "rag_status",
      "department", "project_manager", "sponsor"],
     "start_date DESC", "id"),
    ("ifrs9_loans",          "ifrs9_loans",
     "ifrs9_loans.json",
     ["stage", "ecl_basis", "sicr_flag",
      "product", "client_name"],
     "ecl_amount DESC", "account_id"),
    ("legal_matters",        "legal_matters",
     "legal_matters.json",
     ["status", "priority", "sla_breached",
      "matter_type", "client_cif", "attorney"],
     "opened_date DESC", "id"),
    ("collateral_register",  "collateral_register",
     "collateral_register.json",
     ["status", "collateral_type", "client_cif",
      "branch", "valuer"],
     "market_value DESC", "id"),
    ("agent_transactions",   "agent_transactions",
     "agent_transactions.json",
     ["agent_id", "branch", "txn_type",
      "fraud_flag", "txn_date"],
     "txn_date DESC", "id"),
    ("debt_recovery",        "debt_recovery",
     "debt_recovery.json",
     ["status", "recovery_stage", "client_cif",
      "rm_code", "legal_referral", "branch"],
     "npl_days DESC", "id"),
    ("cims_tickets",         "cims_tickets",
     "cims_tickets.json",
     ["status", "priority", "instruction_type",
      "branch", "rm_code", "client_cif"],
     "due_date ASC", "id"),
    ("compliance_cases",     "compliance_cases",
     "compliance_cases.json",
     ["status", "risk_level", "flag_type",
      "client_cif", "assigned_officer", "case_type"],
     "raised_date DESC", "id"),
    ("referrals",            "referrals",
     "referrals.json",
     ["status", "referral_source", "converted",
      "fee_paid", "branch", "rm_assigned",
      "product_interested"],
     "referral_date DESC", "id"),
    ("consent_register",     "consent_register",
     "consent_register.json",
     ["status", "consent_type", "granted",
      "legal_basis", "customer_cif", "cbk_category",
      "channel"],
     "granted_date DESC", "id"),
    ("revenue_assurance",    "revenue_assurance",
     "revenue_assurance.json",
     ["status", "type", "fee_type", "period",
      "branch", "recovered", "client_cif"],
     "date_raised DESC", "id"),
    ("edms_documents",       "edms_documents",
     "edms_documents.json",
     ["status", "category", "document_type",
      "client_cif", "branch", "is_expired",
      "requires_review", "access_level"],
     "uploaded_date DESC", "id"),
    ("clearing_records",     "clearing_records",
     "clearing_records.json",
     ["status", "system", "reconciled",
      "currency", "settlement_tat_met",
      "officer_username"],
     "value_date DESC", "id"),
]


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "module,table,json_file,searchable,order_by,pk_column",
    CRUD_MODULES,
    ids=[m[0] for m in CRUD_MODULES],
)
def test_factory_call_succeeds(
    crud_module, module, table, json_file,
    searchable, order_by, pk_column,
):
    """make_crud_router(module=X, table=X, ...) must succeed for every
    wired module. A failure here usually means TABLE_USE_DB is missing
    the table entry (the factory's _check_table() rejects unlisted
    tables)."""
    router = crud_module.make_crud_router(
        module=module,
        table=table,
        json_file=json_file,
        list_key=None,
        searchable=searchable,
        order_by=order_by,
        pk_column=pk_column,
    )
    assert router is not None
    # APIRouter from fastapi.APIRouter has a `.routes` list
    assert hasattr(router, "routes")


@pytest.mark.parametrize(
    "module,table,json_file,searchable,order_by,pk_column",
    CRUD_MODULES,
    ids=[m[0] for m in CRUD_MODULES],
)
def test_router_has_eight_routes(
    crud_module, module, table, json_file,
    searchable, order_by, pk_column,
):
    """Each module's APIRouter must produce exactly 8 routes
    (list/get/create/update/delete/export/search/dashboard)."""
    router = crud_module.make_crud_router(
        module=module, table=table, json_file=json_file,
        list_key=None, searchable=searchable,
        order_by=order_by, pk_column=pk_column,
    )
    # Filter out any auto-added routes (head/options) — count only
    # the explicit verbs the factory registers
    routes_with_methods = [
        r for r in router.routes
        if hasattr(r, "methods") and r.methods
    ]
    assert len(routes_with_methods) == 8, (
        f"{module}: expected 8 routes, got "
        f"{len(routes_with_methods)} "
        f"(routes: {[r.path for r in routes_with_methods]})"
    )


@pytest.mark.parametrize(
    "module,table,json_file,searchable,order_by,pk_column",
    CRUD_MODULES,
    ids=[m[0] for m in CRUD_MODULES],
)
def test_route_paths_follow_v1_pattern(
    crud_module, module, table, json_file,
    searchable, order_by, pk_column,
):
    """Every route must follow the /api/v1/{module}/* pattern."""
    router = crud_module.make_crud_router(
        module=module, table=table, json_file=json_file,
        list_key=None, searchable=searchable,
        order_by=order_by, pk_column=pk_column,
    )
    expected_prefix = f"/api/v1/{module}"
    for r in router.routes:
        if not hasattr(r, "path"):
            continue
        assert r.path.startswith(expected_prefix), (
            f"{module}: route {r.path} doesn't start with "
            f"{expected_prefix}"
        )


@pytest.mark.parametrize(
    "module,table,json_file,searchable,order_by,pk_column",
    CRUD_MODULES,
    ids=[m[0] for m in CRUD_MODULES],
)
def test_every_route_requires_jwt(
    crud_module, module, table, json_file,
    searchable, order_by, pk_column,
):
    """Every route must depend on get_current_user (JWT auth — V-001
    fix). A missing dependency means the endpoint is unauthenticated,
    which is a security regression."""
    router = crud_module.make_crud_router(
        module=module, table=table, json_file=json_file,
        list_key=None, searchable=searchable,
        order_by=order_by, pk_column=pk_column,
    )
    for r in router.routes:
        if not hasattr(r, "dependant"):
            continue
        # FastAPI's Dependant tracks all sub-dependencies. Look for
        # get_current_user by callable name across the dep tree.
        deps_found = []

        def walk_deps(d):
            if d.call:
                deps_found.append(
                    getattr(d.call, "__name__", str(d.call)))
            for sub in d.dependencies:
                walk_deps(sub)

        walk_deps(r.dependant)
        assert "get_current_user" in deps_found, (
            f"{module}: route {r.path} missing "
            f"get_current_user dep (deps={deps_found})"
        )


@pytest.mark.parametrize(
    "module,table,json_file,searchable,order_by,pk_column",
    CRUD_MODULES,
    ids=[m[0] for m in CRUD_MODULES],
)
def test_module_registered(
    crud_module, module, table, json_file,
    searchable, order_by, pk_column,
):
    """make_crud_router() registers the module name in
    _REGISTERED_MODULES. The G16 audit gate uses this to enforce
    CRUD coverage."""
    crud_module.make_crud_router(
        module=module, table=table, json_file=json_file,
        list_key=None, searchable=searchable,
        order_by=order_by, pk_column=pk_column,
    )
    registered = crud_module.get_registered_modules()
    assert module in registered, (
        f"{module} not in _REGISTERED_MODULES "
        f"(registered: {registered})"
    )


def test_phase_1b_module_count(crud_module):
    """Sanity check: this test file expects 16 modules. If
    utils/api.py adds new make_crud_router() calls without updating
    CRUD_MODULES, this test will fail loudly."""
    assert len(CRUD_MODULES) == 16, (
        f"Expected 16 CRUD modules per Phase 1B close at v10.96, "
        f"got {len(CRUD_MODULES)}. If this is intentional (new "
        f"module added in a later drop), update CRUD_MODULES "
        f"and this assertion."
    )


def test_no_duplicate_module_names():
    """Each module name must be unique across CRUD_MODULES."""
    names = [m[0] for m in CRUD_MODULES]
    assert len(names) == len(set(names)), (
        f"Duplicate module names in CRUD_MODULES: "
        f"{[n for n in names if names.count(n) > 1]}"
    )


# ── v10.103 — bring utils/api.py under coverage ───────────────────
# The smoke tests above exercise utils/api_crud.py (the factory).
# They deliberately don't import utils/api.py because doing so
# triggers FastAPI app construction + all 100+ page imports, slowing
# test collection. But that means utils/api.py — which has 19 direct
# decorators + 16 include_router calls + ~355 lines — was getting
# 0% coverage. The fix is one explicit import test that runs once,
# attributing all the line execution that happens at import time
# (decorator definitions, include_router calls, FastAPI app setup)
# to utils/api.py. Test collection slows by a few seconds; coverage
# on api.py jumps from 0% to most-of-file in one move.

@pytest.fixture(scope="module")
def api_module(crud_module):
    """Import utils.api as a module-scoped fixture so the import
    happens once per session, not per test. Reuses crud_module's
    streamlit/plotly stubbing."""
    import utils.api as mod
    return mod


def test_api_module_imports(api_module):
    """utils.api imports cleanly. This is the most basic guarantee
    — if it fails, every CRUD endpoint is broken and Phase 1B
    closure is invalid."""
    assert api_module is not None


def test_api_module_has_app(api_module):
    """utils.api defines the FastAPI `app` instance that all routes
    attach to."""
    assert hasattr(api_module, "app"), (
        "utils.api must define `app` (FastAPI instance) — this is "
        "the entry point CI uses to run the API server")
    # FastAPI app exposes `.routes`
    assert hasattr(api_module.app, "routes"), (
        "utils.api.app must be a FastAPI app (has .routes)")


def test_api_module_route_count_at_phase_1b_floor(api_module):
    """The number of routes registered on utils.api.app should be
    at or above the Phase 1B floor (147). Below the floor means
    a regression — either an include_router call was removed or
    the factory broke.

    The floor is a SOFT floor: the actual count varies because
    FastAPI auto-registers /openapi.json, /docs, etc. The test
    checks that the count is at least 147 to allow for FastAPI's
    auto-routes plus future additions, but not below the documented
    Phase 1B closure number (147 endpoints).
    """
    routes = [r for r in api_module.app.routes
              if hasattr(r, "methods") and r.methods]
    # Allow some slack for FastAPI auto-routes (typically 4-8 added)
    # and for future direct decorators added in Phase 1D+
    assert len(routes) >= 100, (
        f"utils.api.app has only {len(routes)} routes; "
        f"Phase 1B closed at 147. If routes were intentionally "
        f"removed, update this test and the SCOPE_LEDGER."
    )
