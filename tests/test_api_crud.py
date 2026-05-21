"""tests/test_api_crud.py — Verify the v1 CRUD factory contract.

These are STRUCTURAL tests on the factory module — they don't spin up a
TestClient (that would require a live PG and a fully-mocked DB pool).
Instead, they verify:

  1. The factory function exists with the documented signature
  2. Calling it produces an APIRouter with exactly 8 routes
  3. Each route has the correct HTTP verb and path shape
  4. Every route has a JWT auth dependency
  5. The factory rejects unknown table names (V-002 defence)
  6. The module registry is populated on each call
  7. The factory uses _qid() for identifiers (no f-string SQL)

Live integration tests (POST /api/v1/foo, etc.) belong in a separate
test that mocks a Database instance — out of scope for v5.31.
"""
from __future__ import annotations

import inspect
import re
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def crud_module():
    """Import utils.api_crud — fail loudly if it doesn't import."""
    # Stub the optional deps that aren't in the test env
    for m in ("plotly", "plotly.express", "plotly.graph_objects", "plotly.subplots"):
        sys.modules.setdefault(m, types.ModuleType(m))
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data     = lambda *a, **k: (lambda f: f)
        st.cache_resource = lambda *a, **k: (lambda f: f)
        st.session_state  = {}
        sys.modules["streamlit"] = st
    import utils.api_crud as mod
    return mod


def test_factory_function_exists(crud_module):
    """make_crud_router must be exposed at module level."""
    assert hasattr(crud_module, "make_crud_router")
    assert callable(crud_module.make_crud_router)


def test_factory_signature_is_keyword_only(crud_module):
    """The factory takes keyword-only args (caller readability)."""
    sig = inspect.signature(crud_module.make_crud_router)
    required = {"module", "table"}
    for name in required:
        assert name in sig.parameters, f"missing required kwarg: {name}"
        # All args are keyword-only because of the `*` in signature
        assert sig.parameters[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_factory_rejects_unknown_table(crud_module):
    """Passing a table not in TABLE_REGISTRY must fail at import time
    (V-002 defence — surface typos before the first request)."""
    with pytest.raises(Exception):  # ValueError or KeyError from _check_table
        crud_module.make_crud_router(
            module="foo",
            table="totally_made_up_table_xyz",
        )


def test_factory_produces_router_with_8_routes(crud_module):
    """Every wired module must get exactly 8 routes."""
    # Use a real registered table from utils/db.py TABLE_REGISTRY
    router = crud_module.make_crud_router(
        module    = "pipeline_deals",
        table     = "pipeline_deals",
        json_file = "pipeline.json",
        list_key  = "deals",
        searchable= ["stage", "unit"],
        order_by  = "open_date DESC",
    )
    # Each route in router.routes is a fastapi.routing.APIRoute
    assert len(router.routes) == 8, (
        f"Expected 8 routes, got {len(router.routes)}: "
        f"{[r.path for r in router.routes]}"
    )


def test_factory_routes_have_expected_verbs_and_paths(crud_module):
    """Verify list/get/create/update/delete/export/search/dashboard
    are all wired with correct HTTP methods."""
    router = crud_module.make_crud_router(
        module    = "pipeline_deals",
        table     = "pipeline_deals",
        searchable= ["stage"],
    )
    expected = {
        ("GET",    "/api/v1/pipeline_deals"),
        ("GET",    "/api/v1/pipeline_deals/{row_id}"),
        ("POST",   "/api/v1/pipeline_deals"),
        ("PUT",    "/api/v1/pipeline_deals/{row_id}"),
        ("DELETE", "/api/v1/pipeline_deals/{row_id}"),
        ("POST",   "/api/v1/pipeline_deals/export"),
        ("POST",   "/api/v1/pipeline_deals/search"),
        ("GET",    "/api/v1/pipeline_deals/dashboard"),
    }
    actual = set()
    for r in router.routes:
        for method in r.methods or set():
            actual.add((method, r.path))
    assert actual == expected, f"Routes don't match. Diff:\n  expected-actual: {expected - actual}\n  actual-expected: {actual - expected}"


def test_factory_registers_module_for_g16(crud_module):
    """Each make_crud_router call registers the module name so the
    G16 audit gate can introspect."""
    # Reset the registry for this test
    crud_module._REGISTERED_MODULES.clear()
    crud_module.make_crud_router(
        module    = "pipeline_deals",
        table     = "pipeline_deals",
        searchable= [],
    )
    assert "pipeline_deals" in crud_module.get_registered_modules()


def test_factory_module_no_unsafe_sql():
    """Static check: no f-string SQL on identifiers in api_crud.py.
    This is the V-002 defence — caller-controlled table/column names
    must always go through _qid() (psycopg2.sql.Identifier)."""
    src = (ROOT / "utils" / "api_crud.py").read_text(encoding="utf-8")
    # Patterns: f"...{table}..." or f"...{col}..." inside SQL contexts
    bad = re.findall(
        r'f"[^"\n]*\b(?:SELECT|INSERT|UPDATE|DELETE|FROM)\b[^"\n]*\{(?:table|col|column)[^}]*\}',
        src, re.IGNORECASE,
    )
    assert not bad, f"Found f-string SQL with raw identifier interpolation: {bad}"


def test_factory_module_qid_usage_count():
    """_qid() must be called many times — once per identifier in each
    SQL builder. We expect at least 16 (8 routes × 2 average)."""
    src = (ROOT / "utils" / "api_crud.py").read_text(encoding="utf-8")
    n = len(re.findall(r"_qid\(", src))
    assert n >= 16, f"Expected ≥16 _qid() calls, got {n} — some SQL may lack identifier escaping"


def test_factory_every_route_has_jwt_auth():
    """Static check: every @router.<verb> decorator's handler has
    Depends(get_current_user) in its signature (V-001 defence)."""
    src = (ROOT / "utils" / "api_crud.py").read_text(encoding="utf-8")
    # Count @router.<verb>(...) decorators
    route_decorators = re.findall(r"@router\.(?:get|post|put|delete|patch)\(", src)
    # Count Depends(get_current_user) occurrences
    auth_calls = re.findall(r"Depends\(get_current_user\)", src)
    assert len(route_decorators) == 8, f"expected 8 routes, got {len(route_decorators)}"
    assert len(auth_calls) >= len(route_decorators), (
        f"{len(route_decorators)} routes but only {len(auth_calls)} JWT-auth deps — "
        f"V-001 risk if any route is unauthed"
    )


def test_factory_audit_logs_every_route():
    """Static check: every route handler calls _audit(...)."""
    src = (ROOT / "utils" / "api_crud.py").read_text(encoding="utf-8")
    audit_calls = re.findall(r"_audit\(", src)
    # 8 routes; each calls _audit at least once
    assert len(audit_calls) >= 8, f"expected ≥8 _audit calls, got {len(audit_calls)}"


def test_pipeline_deals_wired_in_api():
    """Verify utils/api.py wires pipeline_deals through the factory.
    This is the v5.31 pilot."""
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert 'make_crud_router(' in src, "factory not imported/used in api.py"
    assert 'module     = "pipeline_deals"' in src or 'module="pipeline_deals"' in src, \
        "pipeline_deals pilot not wired"
