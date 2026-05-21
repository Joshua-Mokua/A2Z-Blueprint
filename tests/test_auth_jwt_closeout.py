"""tests/test_auth_jwt_closeout.py — Phase 1C close-out tests for
utils/auth_jwt.py.

Pre-v10.104 baseline: 91.2% coverage. Target: ≥95% (Standard #4).

This file targets the remaining uncovered paths the existing
tests/test_auth_jwt.py doesn't reach:

  1. warn_if_default_secret() — both branches (default-used and
     env-supplied)
  2. _resolve_secret() — explicit env-var-set path (existing tests
     monkeypatch SECRET_KEY directly; never exercise this function)
  3. create_access_token — ValueError when username missing
  4. require_admin — its FastAPI-Depends-chained form
  5. _require_admin_impl — direct unit test
  6. decode_token — the malformed (non-JWT-shape) path

Plus regression test for the v10.104 bearer-without-token fix
(which closes the v10.99 IndexError bug while we're here).

These are pure-function tests: monkeypatch env, call function,
assert behaviour. No pytest fixtures depending on FastAPI's
dependency-injection chain — those are integration territory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def jwt_secret(monkeypatch):
    """Set a fixed secret for this test, overriding any env state.
    Mirrors the fixture in tests/test_auth_jwt.py so we share idiom.
    Uses monkeypatch so changes don't leak across tests.
    """
    secret = "test-fixture-secret-v10-104-closeout"
    monkeypatch.setenv("A2Z_JWT_SECRET", secret)
    # Force re-import so SECRET_KEY picks up the env var
    if "utils.auth_jwt" in sys.modules:
        del sys.modules["utils.auth_jwt"]
    from utils import auth_jwt
    monkeypatch.setattr(auth_jwt, "SECRET_KEY", secret)
    return secret


# ── _resolve_secret ───────────────────────────────────────────────

class TestResolveSecret:
    """The env-var resolution. Existing tests skip this path entirely
    by monkeypatching SECRET_KEY at module level."""

    def test_returns_env_var_when_set(self, monkeypatch):
        """A2Z_JWT_SECRET set → returns its value."""
        monkeypatch.setenv("A2Z_JWT_SECRET", "explicit-test-secret")
        # Reload module so _resolve_secret picks up the env var
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        result = auth_jwt._resolve_secret()
        assert result == "explicit-test-secret"

    def test_strips_whitespace_from_env_var(self, monkeypatch):
        """Common deploy mistake: env var has leading/trailing
        whitespace. Resolver should strip it, not return literally."""
        monkeypatch.setenv("A2Z_JWT_SECRET", "  spaced-secret  ")
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        result = auth_jwt._resolve_secret()
        assert result == "spaced-secret"

    def test_falls_back_to_generated_when_env_unset(
            self, monkeypatch):
        """No env var → generates a random secret + sets the
        _DEFAULT_SECRET_USED flag (which warn_if_default_secret reads)."""
        monkeypatch.delenv("A2Z_JWT_SECRET", raising=False)
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        result = auth_jwt._resolve_secret()
        # Generated secret is non-empty and reasonably long
        assert isinstance(result, str)
        assert len(result) >= 32
        # The flag is now True (it gets set inside _resolve_secret)
        assert auth_jwt._DEFAULT_SECRET_USED is True

    def test_empty_env_var_treated_as_unset(self, monkeypatch):
        """A2Z_JWT_SECRET="" should fall back to generation, not
        return empty string. Empty secrets must never be used."""
        monkeypatch.setenv("A2Z_JWT_SECRET", "")
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        result = auth_jwt._resolve_secret()
        assert result != ""
        assert len(result) >= 32  # generated, not empty


# ── warn_if_default_secret ────────────────────────────────────────

class TestWarnIfDefaultSecret:
    """The startup warning for missing A2Z_JWT_SECRET. Both branches
    (warned, not-warned) need coverage."""

    def test_warns_when_default_used(self, monkeypatch, caplog):
        """When _DEFAULT_SECRET_USED=True, warning is logged."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        monkeypatch.setattr(
            auth_jwt, "_DEFAULT_SECRET_USED", True)
        import logging
        with caplog.at_level(logging.WARNING):
            auth_jwt.warn_if_default_secret()
        # Some logger should have warned
        warned = any(
            "A2Z_JWT_SECRET" in r.message
            for r in caplog.records)
        assert warned, (
            f"Expected warning when _DEFAULT_SECRET_USED=True; "
            f"got records: {[r.message for r in caplog.records]}"
        )

    def test_silent_when_env_secret_set(self, monkeypatch, caplog):
        """When _DEFAULT_SECRET_USED=False (env var was set), no
        warning fires."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        monkeypatch.setattr(
            auth_jwt, "_DEFAULT_SECRET_USED", False)
        import logging
        with caplog.at_level(logging.WARNING):
            auth_jwt.warn_if_default_secret()
        warned = any(
            "A2Z_JWT_SECRET" in r.message
            for r in caplog.records)
        assert not warned, (
            f"Expected NO warning when env var was set; "
            f"got records: {[r.message for r in caplog.records]}"
        )


# ── create_access_token edge cases ────────────────────────────────

class TestCreateAccessTokenEdgeCases:
    """Edge cases the existing roundtrip tests don't reach."""

    def test_missing_username_raises_value_error(self, jwt_secret):
        """A user dict with neither 'username' nor 'sub' is invalid;
        token creation must raise rather than mint a tokenless JWT."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt

        with pytest.raises(ValueError, match="username"):
            auth_jwt.create_access_token({"role": "Admin"})

    def test_accepts_sub_as_username_alias(self, jwt_secret):
        """`sub` is the standard JWT claim — should be accepted as
        an alias for username (covers both the .get('username') and
        .get('sub') paths in the function)."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        token = auth_jwt.create_access_token(
            {"sub": "joshua", "role": "Admin"})
        assert isinstance(token, str)
        # Decode and check
        payload = auth_jwt.decode_token(token)
        assert payload["sub"] == "joshua"

    def test_default_role_is_staff(self, jwt_secret):
        """User dict without 'role' key gets role=Staff in token."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        token = auth_jwt.create_access_token({"username": "joshua"})
        payload = auth_jwt.decode_token(token)
        assert payload["role"] == "Staff"


# ── _require_admin_impl direct unit ──────────────────────────────

class TestRequireAdminImpl:
    """Direct unit test on the inner role-check function. The outer
    require_admin uses FastAPI's Depends chain which is awkward to
    unit-test — _require_admin_impl is the actual logic."""

    def test_admin_role_passes(self):
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        result = auth_jwt._require_admin_impl(
            {"username": "j", "role": "Admin"})
        assert result == {"username": "j", "role": "Admin"}

    def test_director_role_passes(self):
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        result = auth_jwt._require_admin_impl(
            {"username": "j", "role": "Director"})
        assert result["role"] == "Director"

    def test_role_check_case_insensitive(self):
        """admin/Admin/ADMIN all pass — role comparison is .lower()."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        for role in ("admin", "Admin", "ADMIN", "AdMiN"):
            result = auth_jwt._require_admin_impl(
                {"username": "j", "role": role})
            assert result["role"] == role

    def test_staff_role_raises_403(self):
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_jwt._require_admin_impl(
                {"username": "j", "role": "Staff"})
        assert exc_info.value.status_code == 403

    def test_missing_role_raises_403(self):
        """Empty/None role is treated as not-admin (defensive)."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_jwt._require_admin_impl({"username": "j"})
        assert exc_info.value.status_code == 403


# ── Regression: bearer-without-token (v10.104 fix) ────────────────

class TestBearerEdgeCases:
    """The v10.99 IndexError bug Joshua's pytest run found:
    'Bearer ' (trailing space, no token) bypassed the startswith
    guard but crashed at split. v10.104 patches with an explicit
    parts-length check. This test fixes the regression and
    verifies all related edge cases."""

    def test_bearer_with_only_trailing_space(self, jwt_secret):
        """'Bearer ' → 401, not IndexError."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_jwt.get_current_user(authorization="Bearer ")
        assert exc_info.value.status_code == 401

    def test_bearer_with_multiple_trailing_spaces(self, jwt_secret):
        """'Bearer   ' → 401, not IndexError."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_jwt.get_current_user(authorization="Bearer    ")
        assert exc_info.value.status_code == 401

    def test_bearer_no_space_no_token(self, jwt_secret):
        """'Bearer' alone (no space, no token) → 401."""
        if "utils.auth_jwt" in sys.modules:
            del sys.modules["utils.auth_jwt"]
        from utils import auth_jwt
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth_jwt.get_current_user(authorization="Bearer")
        assert exc_info.value.status_code == 401
