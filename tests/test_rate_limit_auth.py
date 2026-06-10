"""tests/test_rate_limit_auth.py — regression coverage for v10.501
Phase 2 Arc B Batch 4b rate limiting (closes GAP-006).

Verifies the per-endpoint policy in POLICY_GAPS.md GAP-006:

  /api/auth/login           — 10 per minute / IP, 100 per hour / IP
  /api/auth/change-password — 5 per minute per bearer token
  /api/auth/whoami-detailed — UNLIMITED (legitimate dashboard polling)

Each test resets the slowapi limiter state in a fixture so per-test
runs are independent. Tests use the FastAPI TestClient against the
real `utils.api` app — no mocks of the limiter itself.

Run with:
    pytest tests/test_rate_limit_auth.py -v

Notes for future maintainers:
- These tests do NOT actually wait 60 seconds between buckets. The
  limiter has a 1-minute window for the 5/min and 10/min limits;
  tests reset the limiter to bypass the wall-clock dependency.
- We assert STATUS CODES, not exact remaining-quota headers, because
  slowapi headers are intentionally disabled on auth endpoints
  (see utils/api.py Limiter config comment about not leaking quota
  to brute-forcers).
- Tests that need a valid bearer token mint one directly via
  utils.auth_jwt.create_access_token rather than hitting /api/auth/login
  (which would consume login-limit budget).
"""

import pytest
from fastapi.testclient import TestClient


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """Fresh TestClient against the real utils.api app for each test."""
    from utils.api import app
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_limiter_state():
    """Reset slowapi's in-memory storage before every test so tests
    don't pollute each other's rate-limit buckets. autouse=True means
    every test in this module gets this without opting in."""
    from utils.api import limiter
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def valid_token():
    """Mint a valid full-scope JWT for an arbitrary test user.

    Avoids consuming /api/auth/login budget in tests that need an
    authenticated request. Uses the same token issuance path the
    real login endpoint uses, so the token format / scope semantics
    match production behaviour."""
    from utils.auth_jwt import create_access_token, TOKEN_SCOPE_FULL
    return create_access_token(
        {"username": "william001", "role": "MD"},
        scope=TOKEN_SCOPE_FULL,
    )


# ─── /api/auth/login — per-IP, 10/min ────────────────────────────────

def test_login_allows_up_to_10_requests_per_minute(client):
    """Confirm the per-IP 10/minute limit is honoured exactly: the
    first 10 requests pass the limiter (status will be 401 because
    credentials are bogus, but NOT 429), and the 11th hits 429."""
    statuses = []
    for i in range(11):
        r = client.post(
            "/api/auth/login",
            json={"username": f"bogus_user_{i}", "password": "wrong"},
        )
        statuses.append(r.status_code)

    # First 10 attempts: limiter passes them through. They fail auth
    # (401) but DO NOT hit the rate-limit handler. The 11th request
    # MUST be 429.
    assert statuses[:10] == [401] * 10, (
        f"First 10 login attempts should fail auth (401), got {statuses[:10]}. "
        "Either auth is succeeding for bogus credentials (security bug) or "
        "the limiter is firing too early (policy bug)."
    )
    assert statuses[10] == 429, (
        f"11th login attempt should be rate-limited (429), got {statuses[10]}. "
        "GAP-006 policy violation."
    )


def test_login_429_response_shape(client):
    """A 429 from the auth endpoints MUST carry a Retry-After header
    and a JSON body with a non-empty detail string. Clients (React
    Login.tsx) read these."""
    # Burn the budget
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "x", "password": "y"})
    # 11th: 429
    r = client.post("/api/auth/login", json={"username": "x", "password": "y"})

    assert r.status_code == 429
    assert "Retry-After" in r.headers, (
        "429 response must include Retry-After header for client UX"
    )
    body = r.json()
    assert "detail" in body, "429 body must include 'detail' field"
    assert body["detail"], "429 detail must be non-empty"


def test_login_429_does_not_leak_credentials(client):
    """SECURITY pin: a 429 response from /api/auth/login must NOT echo
    the candidate username or password back to the client. The
    rate-limit detail is generic by design."""
    sentinel_user = "AttackerProbeUsername12345"
    sentinel_pw = "AttackerProbePassword67890"
    for _ in range(10):
        client.post(
            "/api/auth/login",
            json={"username": sentinel_user, "password": sentinel_pw},
        )
    r = client.post(
        "/api/auth/login",
        json={"username": sentinel_user, "password": sentinel_pw},
    )
    assert r.status_code == 429
    body_text = r.text
    assert sentinel_user not in body_text, (
        "429 body must NOT echo the candidate username"
    )
    assert sentinel_pw not in body_text, (
        "429 body must NOT echo the candidate password"
    )


# ─── /api/auth/change-password — per-token, 5/min ────────────────────

def test_change_password_allows_up_to_5_per_minute_per_token(client, valid_token):
    """Per-token rate limit: first 5 attempts with the SAME token are
    passed by the limiter (they fail auth-of-current-password with
    401, but not 429); the 6th MUST 429."""
    headers = {"Authorization": f"Bearer {valid_token}"}
    payload = {"current_password": "wrong_current", "new_password": "Abcdef1!"}

    statuses = []
    for i in range(6):
        r = client.post("/api/auth/change-password", json=payload, headers=headers)
        statuses.append(r.status_code)

    # The first 5 attempts pass the limiter. They will fail with 401
    # because current_password is wrong (or, depending on test data, the
    # user may not exist and the endpoint returns 401 anyway). The point
    # is they are NOT 429. The 6th MUST be 429.
    assert all(s != 429 for s in statuses[:5]), (
        f"First 5 change-password attempts must not be rate-limited; "
        f"got {statuses[:5]}"
    )
    assert statuses[5] == 429, (
        f"6th change-password attempt with the SAME token must be 429; "
        f"got {statuses[5]}. GAP-006 policy violation."
    )


def test_change_password_limit_is_per_token_not_per_ip(client):
    """Two different tokens from the same IP MUST be metered
    independently. Otherwise a NAT'd corporate network would share
    the 5/min budget across hundreds of users — that's the design
    rationale for token-keyed limiting documented in
    utils/api.py:_ratelimit_key_by_token."""
    from utils.auth_jwt import create_access_token, TOKEN_SCOPE_FULL
    token_a = create_access_token({"username": "alice", "role": "Staff"},
                                   scope=TOKEN_SCOPE_FULL)
    token_b = create_access_token({"username": "bob", "role": "Staff"},
                                   scope=TOKEN_SCOPE_FULL)
    payload = {"current_password": "wrong", "new_password": "Abcdef1!"}

    # Burn 5/5 on token A
    for _ in range(5):
        client.post(
            "/api/auth/change-password",
            json=payload,
            headers={"Authorization": f"Bearer {token_a}"},
        )

    # Token A's 6th request: 429
    r_a = client.post(
        "/api/auth/change-password",
        json=payload,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r_a.status_code == 429, (
        f"Token A's 6th request must be 429; got {r_a.status_code}"
    )

    # Token B's FIRST request: must NOT be 429 (independent bucket)
    r_b = client.post(
        "/api/auth/change-password",
        json=payload,
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r_b.status_code != 429, (
        f"Token B's first request must not be rate-limited (different "
        f"bucket from token A); got {r_b.status_code}. The change-password "
        "limit is meant to be per-token, not per-IP."
    )


# ─── /api/auth/whoami-detailed — UNLIMITED ───────────────────────────

def test_whoami_detailed_is_not_rate_limited(client, valid_token):
    """POLICY_GAPS.md GAP-006 explicitly excludes whoami-detailed from
    rate limiting because legitimate dashboard polling makes frequent
    requests. We assert that 30 consecutive requests never produce a
    429 — well above any reasonable per-minute limit we might
    accidentally introduce."""
    headers = {"Authorization": f"Bearer {valid_token}"}
    statuses = []
    for _ in range(30):
        r = client.get("/api/auth/whoami-detailed", headers=headers)
        statuses.append(r.status_code)

    assert 429 not in statuses, (
        f"whoami-detailed should NEVER be rate-limited; got status sequence "
        f"with 429s: {statuses}. Either a @limiter.limit decorator was "
        "accidentally added to whoami_detailed, or a global default_limits "
        "was introduced on the Limiter (it should be empty)."
    )


# ─── Custom 429 handler observability ────────────────────────────────

def test_429_audit_row_is_written(client, monkeypatch):
    """The custom _ratelimit_exceeded_handler MUST call _audit so the
    operator can see rate-limit hits in the audit trail.

    We monkey-patch _audit to capture the calls rather than reading
    the live audit log file — keeps the test hermetic and avoids
    writing to the operator's real audit log when the test suite runs.
    """
    captured = []

    def fake_audit(action, user, detail=""):
        captured.append({"action": action, "user": user, "detail": detail})

    monkeypatch.setattr("utils.api._audit", fake_audit)

    # Burn login budget
    for _ in range(10):
        client.post("/api/auth/login", json={"username": "x", "password": "y"})
    # Trigger 429
    r = client.post("/api/auth/login", json={"username": "x", "password": "y"})

    assert r.status_code == 429

    # At least one API_RATE_LIMITED audit row must have been written.
    rate_limited_rows = [c for c in captured if c["action"] == "API_RATE_LIMITED"]
    assert rate_limited_rows, (
        f"_audit was not called with API_RATE_LIMITED on 429. "
        f"Captured actions: {[c['action'] for c in captured]}"
    )
    # Detail should mention the path so the operator can see WHAT was
    # rate-limited
    row = rate_limited_rows[0]
    assert "path=/api/auth/login" in row["detail"], (
        f"Audit detail should include the path; got: {row['detail']!r}"
    )


def test_429_handler_does_not_leak_token_in_audit(client, monkeypatch, valid_token):
    """SECURITY pin: even though the rate-limit key is derived from
    the bearer token, the audit row's detail field must NOT contain
    the raw JWT or its hash key. The audit log is read by operators
    and must not become a credential-harvesting target.

    The audit row may legitimately include the AUTHENTICATED USERNAME
    if we could decode the token — that's fine, the username is not a
    secret. What it must NOT include is the token itself.
    """
    captured = []

    def fake_audit(action, user, detail=""):
        captured.append({"action": action, "user": user, "detail": detail})

    monkeypatch.setattr("utils.api._audit", fake_audit)

    headers = {"Authorization": f"Bearer {valid_token}"}
    payload = {"current_password": "wrong", "new_password": "Abcdef1!"}
    # Burn change-password budget
    for _ in range(5):
        client.post("/api/auth/change-password", json=payload, headers=headers)
    # Trigger 429
    r = client.post("/api/auth/change-password", json=payload, headers=headers)
    assert r.status_code == 429

    rate_limited_rows = [c for c in captured if c["action"] == "API_RATE_LIMITED"]
    assert rate_limited_rows, "API_RATE_LIMITED audit row not written"

    for row in rate_limited_rows:
        full_text = f"{row['user']} {row['detail']}"
        assert valid_token not in full_text, (
            "SECURITY VIOLATION: audit row contains the raw JWT. The "
            "_ratelimit_exceeded_handler must NOT include the token in "
            "any field of the audit payload."
        )
