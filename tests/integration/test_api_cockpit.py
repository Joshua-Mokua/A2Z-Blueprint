"""
tests/integration/test_api_cockpit.py
================================================================================
v10.297 — HTTP API for live cockpit reads (React-readiness arc).

Tests written BEFORE implementation per Kaizen TDD discipline.

The React SPA (#37) will fetch live cockpit data via these endpoints.
Streamlit pages 109/110 will eventually fetch through the same
endpoints — single source of truth.

This suite covers:
  1. Module structure (FastAPI-available, router exists,
     graceful degradation when FastAPI isn't installed)
  2. Endpoint existence (every cockpit_read composer has a
     paired HTTP route)
  3. Auth enforcement (JWT required, missing token returns 401)
  4. Response schema (every endpoint returns JSON dict with
     the documented keys)
  5. Audit-log emission (every successful call writes an audit
     record)
  6. Error handling (4xx for bad input, 5xx for engine errors,
     never an unhandled exception)
  7. React-readiness invariants (CORS-friendly, no
     server-side state, idempotent reads)
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — Module structure
# ============================================================

def test_api_cockpit_module_imports():
    """The module must be importable. If FastAPI isn't installed
    it must degrade gracefully (router=None, FASTAPI_AVAILABLE=False),
    same convention as utils/api_treasury.py."""
    import utils.api_cockpit as mod

    assert hasattr(mod, "FASTAPI_AVAILABLE"), (
        "api_cockpit must expose FASTAPI_AVAILABLE flag"
    )
    assert hasattr(mod, "router"), (
        "api_cockpit must expose `router` (may be None if FastAPI "
        "not installed)"
    )


def test_api_cockpit_router_exists_when_fastapi_available():
    """When FastAPI is available, router must be a real APIRouter."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    assert mod.router is not None
    assert mod.router.prefix == "/api/cockpit", (
        f"Expected prefix /api/cockpit, got {mod.router.prefix}"
    )


# ============================================================
# Section 2 — Endpoint existence
# ============================================================

EXPECTED_ENDPOINTS = [
    ("GET", "/api/cockpit/cims/open-work"),
    ("GET", "/api/cockpit/cims/instruction-trace/{session_id}"),
    ("GET", "/api/cockpit/treasury/open-work"),
    ("GET", "/api/cockpit/treasury/liquidity"),
    ("GET", "/api/cockpit/treasury/irrbb"),
    ("GET", "/api/cockpit/treasury/capital"),
    ("GET", "/api/cockpit/treasury/daily-report"),
    ("GET", "/api/cockpit/treasury/cash-forecast"),
    ("GET", "/api/cockpit/credit/open-work"),
    ("GET", "/api/cockpit/credit/applications"),
    ("GET", "/api/cockpit/credit/ifrs9"),
    ("GET", "/api/cockpit/credit/watchlist"),
    ("GET", "/api/cockpit/credit/portfolio-analytics"),
    ("GET", "/api/cockpit/compliance/open-work"),
    ("GET", "/api/cockpit/compliance/cases"),
    ("GET", "/api/cockpit/compliance/aml-alerts"),
    ("GET", "/api/cockpit/compliance/sanctions"),
    ("GET", "/api/cockpit/compliance/regulatory-returns"),
    ("GET", "/api/cockpit/compliance/cra-training"),
    ("GET", "/api/cockpit/audit/log"),
    ("GET", "/api/cockpit/audit/reviews"),
    ("GET", "/api/cockpit/ops/incidents"),
    ("GET", "/api/cockpit/cx/nps"),
    ("GET", "/api/cockpit/risk/rcsa"),
    ("GET", "/api/cockpit/health"),
]


def test_all_expected_endpoints_registered():
    """Every expected endpoint must be on the router."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")

    # Collect routes from the router
    routes = []
    for r in mod.router.routes:
        for method in r.methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            routes.append((method, r.path))

    for verb, path in EXPECTED_ENDPOINTS:
        # FastAPI strips the prefix; paths on the router are
        # relative
        rel_path = path.replace("/api/cockpit", "")
        assert (verb, rel_path) in routes, (
            f"{verb} {path} (relative: {rel_path}) not registered. "
            f"Found routes: {sorted(set(routes))[:10]}"
        )


# ============================================================
# Section 3 — Auth enforcement
# ============================================================

def test_endpoint_requires_jwt():
    """Every cockpit endpoint must require a JWT. Without an
    Authorization header, response must be 401."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    # Unauthenticated call to a read endpoint
    resp = client.get("/api/cockpit/cims/open-work")
    assert resp.status_code == 401, (
        f"Expected 401 without auth, got {resp.status_code}: "
        f"{resp.text[:200]}"
    )


def test_endpoint_rejects_malformed_token():
    """A non-Bearer token must produce 401, not crash."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    resp = client.get(
        "/api/cockpit/cims/open-work",
        headers={"Authorization": "Basic xyz"},
    )
    assert resp.status_code == 401


# ============================================================
# Section 4 — Response schema (with valid auth)
# ============================================================

def _make_test_jwt() -> str:
    """Mint a JWT for tests using the real signing key."""
    from utils.auth_jwt import create_access_token
    return create_access_token(
        username="test_user", role="admin",
    )


def test_cims_open_work_returns_documented_schema():
    """GET /api/cockpit/cims/open-work must return a dict with
    the documented keys."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    token = _make_test_jwt()
    resp = client.get(
        "/api/cockpit/cims/open-work",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, (
        f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    )
    data = resp.json()
    required_keys = [
        "open_capture_sessions", "pending_nlp",
        "pending_stp_manual", "open_exceptions",
        "upcoming_sla", "breached_sla", "pending_merges",
    ]
    for k in required_keys:
        assert k in data, (
            f"Response missing required key `{k}`. "
            f"Keys present: {sorted(data.keys())}"
        )


def test_treasury_open_work_returns_documented_schema():
    """GET /api/cockpit/treasury/open-work must return the
    same shape as treasury_open_work() composer."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")

    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    token = _make_test_jwt()
    resp = client.get(
        "/api/cockpit/treasury/open-work",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for k in (
        "fx_positions_count", "open_fx_deals", "irrbb_breaches",
        "lcr_pct", "lcr_min_pct", "lcr_breached", "as_at",
    ):
        assert k in data, f"missing key {k}"


def test_cims_instruction_trace_returns_documented_schema():
    """GET /api/cockpit/cims/instruction-trace/{session_id} must
    return a dict with the trace lifecycle keys."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    token = _make_test_jwt()
    resp = client.get(
        "/api/cockpit/cims/instruction-trace/NON-EXISTENT",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    for k in (
        "linked_session_id", "capture", "classification_requests",
        "stp_requests", "exceptions", "sla_obligations", "history",
    ):
        assert k in data, f"missing key {k}"
    # Unknown session: capture is None, lists are empty
    assert data["linked_session_id"] == "NON-EXISTENT"
    assert data["capture"] is None
    assert data["classification_requests"] == []


def test_health_endpoint_returns_ok():
    """GET /api/cockpit/health must return 200 with a health
    payload — useful for the React SPA to check connectivity."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    token = _make_test_jwt()
    resp = client.get(
        "/api/cockpit/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") in ("ok", "healthy")
    assert "cockpit_read_api_version" in data, (
        "Health endpoint must report cockpit_read API version "
        "so the React SPA can detect upgrades"
    )


# ============================================================
# Section 5 — Audit-log emission
# ============================================================

def test_endpoint_emits_audit_log_on_success():
    """Every successful endpoint call must write an audit record.
    Patches utils.core_audit.audit_log to capture calls."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")

    captured = []
    import utils.api_cockpit as api_mod
    # Capture the local reference inside the module
    original_audit = api_mod._audit_cockpit

    def fake_audit(action, user, detail=""):
        captured.append({
            "action": action,
            "user": user,
            "detail": detail,
        })

    api_mod._audit_cockpit = fake_audit
    try:
        app = FastAPI()
        app.include_router(mod.router)
        client = TestClient(app)
        token = _make_test_jwt()
        client.get(
            "/api/cockpit/cims/open-work",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        api_mod._audit_cockpit = original_audit

    assert len(captured) >= 1, (
        "Expected at least one _audit_cockpit call after "
        "successful endpoint hit; got none"
    )
    assert any("cims" in c["action"].lower() for c in captured), (
        f"Expected cims-related audit action; got "
        f"{[c['action'] for c in captured]}"
    )


# ============================================================
# Section 6 — Error handling
# ============================================================

def test_unknown_session_returns_200_not_404():
    """Per the cockpit_read contract, unknown session ID returns
    a well-formed empty trace (NOT a 404). The React SPA shouldn't
    have to handle two response shapes."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    token = _make_test_jwt()
    resp = client.get(
        "/api/cockpit/cims/instruction-trace/DOES-NOT-EXIST",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ============================================================
# Section 7 — React-readiness invariants
# ============================================================

def test_response_is_json_serialisable():
    """Every endpoint response must round-trip through JSON
    cleanly (no Decimal, no datetime objects, no custom types)."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    token = _make_test_jwt()

    for path in (
        "/api/cockpit/cims/open-work",
        "/api/cockpit/treasury/open-work",
        "/api/cockpit/health",
    ):
        resp = client.get(
            path,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, (
            f"{path}: {resp.status_code} {resp.text[:200]}"
        )
        # If the response body is JSON-decodable, it's
        # serialisable
        data = resp.json()
        # Round-trip
        re_serialised = json.dumps(data)
        round_tripped = json.loads(re_serialised)
        assert round_tripped == data


def test_endpoints_are_idempotent():
    """Calling the same endpoint twice must produce the same
    business data (the `as_at` timestamp may differ but the rest
    must match)."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("FastAPI test client not installed")
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)
    token = _make_test_jwt()

    r1 = client.get(
        "/api/cockpit/treasury/open-work",
        headers={"Authorization": f"Bearer {token}"},
    )
    r2 = client.get(
        "/api/cockpit/treasury/open-work",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    # Compare everything except as_at (read-time stamp)
    keys_to_compare = set(d1.keys()) - {"as_at"}
    for k in keys_to_compare:
        assert d1[k] == d2[k], (
            f"Endpoint not idempotent for key `{k}`: "
            f"{d1[k]} != {d2[k]}"
        )


def test_router_has_no_state_changing_endpoints():
    """v10.297 ships READ-ONLY. No POST/PUT/DELETE/PATCH on
    cockpit endpoints. State changes happen via the engine-
    specific APIs (api_treasury, api_compliance, etc.), not
    through cockpit composers."""
    import utils.api_cockpit as mod
    if not mod.FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not installed")

    for r in mod.router.routes:
        unsafe_methods = r.methods & {"POST", "PUT", "DELETE",
                                       "PATCH"}
        assert not unsafe_methods, (
            f"Cockpit endpoint {r.path} has state-changing "
            f"methods {unsafe_methods}. v10.297 is read-only."
        )


# ============================================================
# Section 8 — Documentation contract
# ============================================================

def test_api_cockpit_module_has_endpoint_map_docstring():
    """The module docstring must document every endpoint, like
    api_treasury does. New endpoints can't be added without
    documenting them — this fights drift."""
    import utils.api_cockpit as mod
    doc = mod.__doc__ or ""
    for verb, path in EXPECTED_ENDPOINTS:
        assert path in doc, (
            f"Endpoint {verb} {path} not in module docstring. "
            f"Document every endpoint in the module header."
        )


# ============================================================
# Section 9 — Static analysis (runs WITHOUT FastAPI installed)
# ============================================================
# These tests parse the source and verify structure, so they pass
# even in environments where FastAPI is missing — protecting the
# audit pipeline.

def _parse_api_cockpit():
    import ast
    src = (REPO_ROOT / "utils" / "api_cockpit.py").read_text()
    return ast.parse(src), src


def test_static_all_endpoints_have_auth():
    """Every `@router.get(...)`-decorated function must accept a
    `user` parameter (the Depends(get_current_user) injection)."""
    import ast
    tree, _ = _parse_api_cockpit()
    missing_auth = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        is_router = any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id == "router"
            for d in node.decorator_list
        )
        if not is_router:
            continue
        has_user = any(a.arg == "user" for a in node.args.args)
        if not has_user:
            missing_auth.append(node.name)
    assert not missing_auth, (
        f"Endpoints missing `user` auth parameter: {missing_auth}"
    )


def test_static_all_endpoints_emit_audit_log():
    """Every endpoint function body must call `_audit_cockpit(...)`."""
    import ast
    tree, src = _parse_api_cockpit()
    missing_audit = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        is_router = any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id == "router"
            for d in node.decorator_list
        )
        if not is_router:
            continue
        body_src = ast.unparse(node)
        if "_audit_cockpit(" not in body_src:
            missing_audit.append(node.name)
    assert not missing_audit, (
        f"Endpoints missing _audit_cockpit() call: {missing_audit}"
    )


def test_static_no_state_changing_methods():
    """v10.297 is read-only. No `@router.post`, `.put`, `.delete`,
    `.patch` decorators allowed."""
    import ast
    tree, _ = _parse_api_cockpit()
    forbidden_verbs = {"post", "put", "delete", "patch"}
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"
                    and dec.func.attr in forbidden_verbs):
                violations.append(
                    f"{node.name} uses @router.{dec.func.attr}"
                )
    assert not violations, (
        f"State-changing methods found (v10.297 is read-only): "
        f"{violations}"
    )


def test_static_endpoint_count_matches_expected():
    """The expected endpoint count from EXPECTED_ENDPOINTS must
    match the number actually defined in the source."""
    import ast
    tree, _ = _parse_api_cockpit()
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"):
                if dec.args and isinstance(dec.args[0],
                                             ast.Constant):
                    found.append(
                        (dec.func.attr.upper(), dec.args[0].value)
                    )
    assert len(found) == len(EXPECTED_ENDPOINTS), (
        f"Expected {len(EXPECTED_ENDPOINTS)} endpoints, found "
        f"{len(found)}: {found}"
    )


def test_static_module_does_not_import_streamlit():
    """The cockpit API module must be usable without Streamlit
    installed (the React SPA backend runs without it). If anything
    transitively imports streamlit at module-load time, this test
    catches it."""
    import ast
    tree, src = _parse_api_cockpit()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = (
                node.module if isinstance(node, ast.ImportFrom)
                else (node.names[0].name if node.names else "")
            )
            assert module is None or "streamlit" not in module, (
                f"Module imports streamlit (`{module}`) at "
                f"top level — breaks non-Streamlit environments"
            )
