"""utils/auth_jwt.py — JWT auth for the A2Z FastAPI layer.

V-001 fix (CVSS 9.1) — every endpoint except /api/health requires a bearer
JWT issued by /api/auth/login. The token is signed with HS256 using
A2Z_JWT_SECRET (env var, generated default for dev with a startup warning).

Token payload:
    {
        "sub":  "<username>",        # subject = username
        "role": "<role>",
        "iat":  <issued-at>,
        "exp":  <expires>,
    }

Lifetime: 30 minutes (matches the audit's session-timeout expectation).
Refresh tokens are intentionally NOT supported in this iteration — log in
again on expiry. The audit didn't require refresh and the React migration
that would benefit from it isn't here yet.

Usage in routes:
    from fastapi import Depends
    from utils.auth_jwt import get_current_user, require_admin

    @app.get("/api/bsc/summary")
    def bsc_summary(user: dict = Depends(get_current_user)):
        ...

    @app.post("/api/cache/clear")
    def clear_cache(user: dict = Depends(require_admin)):
        ...

audit gate G12 (api_auth_safety) verifies every @app.get/post route except
/api/health declares one of these Depends arguments.
"""
from __future__ import annotations

import os
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Header, status

logger = logging.getLogger("a2z.auth")

# ── Secret + algorithm ────────────────────────────────────────────────────
# In production this MUST be set via environment. Falling back to a
# generated value preserves dev ergonomics but a warning fires once at
# startup so it can't ship to prod unnoticed.
ALGORITHM       = "HS256"
TOKEN_LIFETIME  = timedelta(minutes=30)
_DEFAULT_SECRET_USED = False


def _resolve_secret() -> str:
    global _DEFAULT_SECRET_USED
    s = os.getenv("A2Z_JWT_SECRET", "").strip()
    if s:
        return s
    # Generate a random secret per process. This is dev-only behaviour:
    # restarts invalidate every token, which is correct for development
    # and intolerable for production.
    _DEFAULT_SECRET_USED = True
    return secrets.token_urlsafe(48)


SECRET_KEY = _resolve_secret()


def warn_if_default_secret() -> None:
    """Called once from api.py at startup. Logs a loud warning if the
    secret was auto-generated (i.e. A2Z_JWT_SECRET wasn't set in env).
    Intentionally noisy so it can't ship to prod silently."""
    if _DEFAULT_SECRET_USED:
        logger.warning(
            "A2Z_JWT_SECRET not set — using a generated per-process secret. "
            "This is acceptable for development only. Set the environment "
            "variable in production. Tokens issued by this process will be "
            "invalidated on restart."
        )


# ── Token issue / decode ──────────────────────────────────────────────────
def create_access_token(user: dict) -> str:
    """Issue a bearer JWT for a freshly authenticated user.

    `user` is the dict UserManager.authenticate returns. Only `username`
    and `role` go into the token — never the password hash, never PII.
    """
    import jwt as _jwt

    username = user.get("username") or user.get("sub")
    if not username:
        raise ValueError("create_access_token: user dict missing 'username'")

    now = datetime.now(timezone.utc)
    payload = {
        "sub":  username,
        "role": user.get("role", "Staff"),
        "iat":  int(now.timestamp()),
        "exp":  int((now + TOKEN_LIFETIME).timestamp()),
    }
    return _jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + validate a bearer JWT. Raises HTTPException(401) on any
    failure — expired, malformed, wrong signature."""
    import jwt as _jwt

    try:
        return _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except _jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependencies ──────────────────────────────────────────────────
def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI Depends — extract + validate bearer token, return user dict.

    The dict has shape {"username", "role", "iat", "exp"}. Pages that need
    fuller user data should call UserManager.users[username] themselves.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()
    payload = decode_token(token)
    return {
        "username": payload.get("sub"),
        "role":     payload.get("role", "Staff"),
        "iat":      payload.get("iat"),
        "exp":      payload.get("exp"),
    }


def require_admin(user: dict = None) -> dict:
    """FastAPI Depends — require role=Admin or equivalent.

    Used on destructive endpoints like /api/cache/clear. Raises 403 (not
    401) so the caller knows the token was valid but the user isn't
    authorised.

    Usage:
        from fastapi import Depends
        @app.post("/api/cache/clear")
        def clear(user = Depends(require_admin)):
            ...

    This dep itself depends on get_current_user via FastAPI's sub-dep
    injection — it gets the user dict, then enforces the role check.
    """
    from fastapi import Depends as _Depends
    # When invoked through FastAPI DI, user is None at decoration time;
    # the framework wires the chain. We declare the chain inline below.
    raise HTTPException(status_code=500, detail="require_admin must be used via Depends")


def _require_admin_impl(user: dict) -> dict:
    """Internal — the actual role-check, called with a resolved user."""
    role = (user.get("role") or "").lower()
    if role not in ("admin", "director"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for this endpoint",
        )
    return user


# Re-bind require_admin to the FastAPI-friendly chained form. This pattern
# avoids importing Depends at module top (keeps the auth module usable
# in non-FastAPI contexts) while still letting routes write
# `Depends(require_admin)` cleanly.
def _make_require_admin():
    from fastapi import Depends

    def require_admin_dep(user: dict = Depends(get_current_user)) -> dict:
        return _require_admin_impl(user)

    return require_admin_dep


require_admin = _make_require_admin()
