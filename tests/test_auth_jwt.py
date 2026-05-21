"""tests/test_auth_jwt.py — exercise utils/auth_jwt.py.

V-001 mitigation (CVSS 9.1) — every API endpoint except /api/health
requires a valid bearer token. These tests verify the cryptographic
guarantees the auth layer makes:

  - Tokens issued by create_access_token round-trip cleanly via decode_token
  - Tampered tokens are rejected
  - Wrong-secret tokens are rejected
  - Expired tokens are rejected
  - get_current_user enforces Bearer scheme
  - require_admin enforces role-based access

These are functional tests, not type checks — they exercise the actual
JWT validation logic.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import jwt
import pytest


# ── Token round-trip ────────────────────────────────────────────────────
@pytest.mark.security
class TestTokenRoundtrip:
    def test_create_decode_roundtrip(self, jwt_secret):
        from utils.auth_jwt import create_access_token, decode_token
        token = create_access_token({"username": "william001", "role": "Admin"})
        payload = decode_token(token)
        assert payload["sub"] == "william001"
        assert payload["role"] == "Admin"

    def test_token_is_three_part_jwt(self, jwt_secret):
        from utils.auth_jwt import create_access_token
        token = create_access_token({"username": "u", "role": "Staff"})
        assert token.count(".") == 2

    def test_token_includes_expiry(self, jwt_secret):
        from utils.auth_jwt import create_access_token, decode_token
        before = datetime.now(timezone.utc).timestamp()
        token = create_access_token({"username": "u", "role": "Staff"})
        payload = decode_token(token)
        assert "exp" in payload
        assert payload["exp"] > before

    def test_expiry_is_30_minutes(self, jwt_secret):
        from utils.auth_jwt import create_access_token, decode_token, TOKEN_LIFETIME
        token = create_access_token({"username": "u", "role": "Staff"})
        payload = decode_token(token)
        diff = payload["exp"] - payload["iat"]
        assert diff == int(TOKEN_LIFETIME.total_seconds())

    def test_create_without_username_raises(self, jwt_secret):
        from utils.auth_jwt import create_access_token
        with pytest.raises(ValueError, match="username"):
            create_access_token({"role": "Admin"})


# ── Tamper rejection ────────────────────────────────────────────────────
@pytest.mark.security
class TestTamperRejection:
    def test_tampered_signature_rejected(self, jwt_secret):
        from utils.auth_jwt import create_access_token, decode_token
        from fastapi import HTTPException

        token = create_access_token({"username": "u", "role": "Staff"})
        # Mutate last 4 chars (signature region) — with very high probability
        # this breaks the signature.
        bad = token[:-4] + "AAAA"
        with pytest.raises(HTTPException) as exc:
            decode_token(bad)
        assert exc.value.status_code == 401

    def test_wrong_secret_rejected(self, jwt_secret):
        from utils.auth_jwt import decode_token
        from fastapi import HTTPException

        # Issue a token with a DIFFERENT secret
        hostile = jwt.encode(
            {"sub": "evil", "role": "Admin",
             "exp": int(datetime.now(timezone.utc).timestamp()) + 3600},
            "different_secret_xxxxxxxxxxxxxxxx",
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc:
            decode_token(hostile)
        assert exc.value.status_code == 401

    def test_expired_token_rejected(self, jwt_secret):
        from utils.auth_jwt import decode_token, SECRET_KEY, ALGORITHM
        from fastapi import HTTPException

        # Forge a token that's already expired by 60 seconds
        expired = jwt.encode(
            {"sub": "u", "role": "Staff",
             "exp": int(datetime.now(timezone.utc).timestamp()) - 60},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc:
            decode_token(expired)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    def test_garbage_token_rejected(self, jwt_secret):
        from utils.auth_jwt import decode_token
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            decode_token("this.is.not.a.jwt")
        assert exc.value.status_code == 401


# ── Bearer header parsing ───────────────────────────────────────────────
@pytest.mark.security
class TestBearerParsing:
    def test_valid_bearer_returns_user_dict(self, jwt_secret):
        from utils.auth_jwt import create_access_token, get_current_user
        token = create_access_token({"username": "william001", "role": "Admin"})
        user = get_current_user(authorization=f"Bearer {token}")
        assert user["username"] == "william001"
        assert user["role"] == "Admin"
        assert "exp" in user

    def test_lowercase_bearer_accepted(self, jwt_secret):
        from utils.auth_jwt import create_access_token, get_current_user
        token = create_access_token({"username": "u", "role": "Staff"})
        # `bearer` (lowercase) is RFC-allowed
        user = get_current_user(authorization=f"bearer {token}")
        assert user["username"] == "u"

    def test_missing_header_rejected(self, jwt_secret):
        from utils.auth_jwt import get_current_user
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None)
        assert exc.value.status_code == 401

    def test_empty_header_rejected(self, jwt_secret):
        from utils.auth_jwt import get_current_user
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization="")
        assert exc.value.status_code == 401

    def test_basic_auth_rejected(self, jwt_secret):
        """Basic auth must NOT be accepted — bearer-only."""
        from utils.auth_jwt import get_current_user
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization="Basic YWRtaW46cGFzcw==")
        assert exc.value.status_code == 401

    def test_bearer_without_token_rejected(self, jwt_secret):
        from utils.auth_jwt import get_current_user
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            get_current_user(authorization="Bearer ")


# ── Role-based access (require_admin) ──────────────────────────────────
@pytest.mark.security
class TestRequireAdmin:
    def test_admin_role_accepted(self, jwt_secret):
        from utils.auth_jwt import _require_admin_impl
        user = _require_admin_impl({"username": "william001", "role": "Admin"})
        assert user["role"] == "Admin"

    def test_director_role_accepted(self, jwt_secret):
        from utils.auth_jwt import _require_admin_impl
        user = _require_admin_impl({"username": "u", "role": "Director"})
        assert user["role"] == "Director"

    def test_staff_role_rejected(self, jwt_secret):
        from utils.auth_jwt import _require_admin_impl
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _require_admin_impl({"username": "u", "role": "Staff"})
        assert exc.value.status_code == 403

    def test_manager_role_rejected(self, jwt_secret):
        from utils.auth_jwt import _require_admin_impl
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _require_admin_impl({"username": "u", "role": "Manager"})
        assert exc.value.status_code == 403

    def test_empty_role_rejected(self, jwt_secret):
        from utils.auth_jwt import _require_admin_impl
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _require_admin_impl({"username": "u", "role": ""})

    def test_missing_role_rejected(self, jwt_secret):
        from utils.auth_jwt import _require_admin_impl
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _require_admin_impl({"username": "u"})

    def test_case_insensitive_role_check(self, jwt_secret):
        """role='admin' should pass even though role='Admin' is the canonical
        casing — case-insensitive comparison."""
        from utils.auth_jwt import _require_admin_impl
        user = _require_admin_impl({"username": "u", "role": "admin"})
        assert user["role"] == "admin"
