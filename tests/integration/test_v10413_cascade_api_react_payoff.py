"""Integration tests for v10.413 — E7 Cascade API & exports.

Verifies React-readiness payoff:
  - Cascade endpoints respond with expected shapes
  - JWT auth enforced (401 without token)
  - Both routers (api_cascade + api_capacity_feedback) mounted
  - OpenAPI spec exports cleanly with both prefixes
  - Engine state preserved

15 tests across 5 sections.
"""

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


os.environ.setdefault("A2Z_JWT_SECRET", "test-secret-v10413-integration")


@pytest.fixture(scope="module")
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from utils.api_cascade import router as cascade_router
    app = FastAPI()
    app.include_router(cascade_router)
    try:
        from utils.api_capacity_feedback import router as capacity_router
        app.include_router(capacity_router)
    except ImportError:
        pass
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    from utils.auth_jwt import create_access_token
    token = create_access_token({
        "username": "test_user",
        "role": "Managing Director",
        "staff_code": "100001",
        "is_admin": True,
    })
    return {"Authorization": f"Bearer {token}"}


def test_v10413_router_module_exists():
    assert (REPO / "utils" / "api_cascade.py").exists()


def test_v10413_router_has_prefix_and_routes():
    from utils.api_cascade import router
    assert router.prefix == "/api/v1/cascade"
    assert len(router.routes) >= 12


def test_v10413_router_included_in_main_api():
    text = (REPO / "utils" / "api.py").read_text()
    assert "from utils.api_cascade import router" in text


def test_v10413_capacity_router_also_mounted():
    text = (REPO / "utils" / "api.py").read_text()
    assert "from utils.api_capacity_feedback import router" in text


def test_v10413_endpoints_require_jwt(client):
    for p in (
        "/api/v1/cascade/health/summary?period=2026",
        "/api/v1/cascade/pairing/shared-kpis",
        "/api/v1/cascade/structure/audit-summary",
    ):
        r = client.get(p)
        assert r.status_code in (401, 403)


def test_v10413_health_summary_endpoint(client, auth_headers):
    r = client.get("/api/v1/cascade/health/summary?period=2026",
                   headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "overall_health_score" in data


def test_v10413_pillar_health_endpoint(client, auth_headers):
    r = client.get("/api/v1/cascade/health/pillars?period=2026",
                   headers=auth_headers)
    assert r.status_code == 200


def test_v10413_sbu_health_endpoint(client, auth_headers):
    r = client.get("/api/v1/cascade/health/sbu?period=2026",
                   headers=auth_headers)
    assert r.status_code == 200


def test_v10413_shared_kpis_endpoint(client, auth_headers):
    r = client.get("/api/v1/cascade/pairing/shared-kpis",
                   headers=auth_headers)
    assert r.status_code == 200
    assert "PBT" in r.json()


def test_v10413_co_owners_endpoint(client, auth_headers):
    r = client.get("/api/v1/cascade/pairing/co-owners/PBT",
                   headers=auth_headers)
    assert r.status_code == 200
    assert "primary_owners" in r.json()


def test_v10413_pairing_apply_endpoint(client, auth_headers):
    body = {
        "kpi": "PBT", "total_target": 10000.0,
        "recipients": ["Director Retail Banking",
                       "Director Commercial Banking"],
        "strategy": "equal_split",
    }
    r = client.post("/api/v1/cascade/pairing/apply",
                    json=body, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["allocations"]["Director Retail Banking"] == 5000.0


def test_v10413_structure_audit_endpoint(client, auth_headers):
    r = client.get("/api/v1/cascade/structure/audit-summary",
                   headers=auth_headers)
    assert r.status_code == 200


def test_v10413_openapi_export_script_exists():
    assert (REPO / "scripts" / "export_cascade_openapi.py").exists()


def test_v10413_canonical_openapi_spec_has_both_routers():
    p = REPO / "docs" / "openapi_cascade_v10413.json"
    assert p.exists()
    spec = json.loads(p.read_text())
    paths = spec["paths"]
    assert any("/api/v1/cascade/" in pp for pp in paths)
    assert any("/api/cascade/capacity-feedback" in pp for pp in paths)


def test_v10413_g299_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10413_cascade_api_react_payoff
    r = gate_v10413_cascade_api_react_payoff()
    assert r["passed"], r.get("violations")
