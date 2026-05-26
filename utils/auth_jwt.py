"""utils/auth_jwt.py — JWT auth for the A2Z FastAPI layer.

V-001 fix (CVSS 9.1) — every endpoint except /api/health requires a bearer
JWT issued by /api/auth/login. The token is signed with HS256 using
A2Z_JWT_SECRET (env var, generated default for dev with a startup warning).

Token payload:
    {
        "sub":   "<username>",        # subject = username
        "role":  "<role>",
        "iat":   <issued-at>,
        "exp":   <expires>,
        "scope": "must_rotate",       # OPTIONAL — present only on rotation-only
                                      # tokens (Batch 3b). Absent claim means
                                      # full-scope token (backward compatible
                                      # with pre-3b issued tokens still in
                                      # circulation in localStorage).
    }

Lifetime: 30 minutes (matches the audit's session-timeout expectation).
Refresh tokens are intentionally NOT supported in this iteration — log in
again on expiry. The audit didn't require refresh and the React migration
that would benefit from it isn't here yet.

Scope (Batch 3b — must_change_password enforcement):
    The default scope is "full" — the token grants access to every
    authenticated endpoint. When UserManager.authenticate returns a user
    whose `must_change_password` flag is true, /api/auth/login issues a
    token with scope="must_rotate" instead. That token is REJECTED by
    get_current_user (403) and only accepted by
    get_current_user_allow_rotation, which is used exclusively by
    /api/auth/change-password. Mechanical enforcement: every existing
    endpoint that already declared Depends(get_current_user) inherits
    the rotation gate for free.

Usage in routes:
    from fastapi import Depends
    from utils.auth_jwt import (
        get_current_user, require_admin, get_current_user_allow_rotation,
    )

    @app.get("/api/bsc/summary")
    def bsc_summary(user: dict = Depends(get_current_user)):
        ...

    @app.post("/api/cache/clear")
    def clear_cache(user: dict = Depends(require_admin)):
        ...

    # ONLY /api/auth/change-password uses the rotation-tolerant dep:
    @app.post("/api/auth/change-password")
    def change_password(user: dict = Depends(get_current_user_allow_rotation)):
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

# ── Token scope constants (Batch 3b) ──────────────────────────────────────
# Full-scope tokens grant access to every authenticated endpoint.
# Must-rotate-scope tokens are issued by /api/auth/login when the
# authenticating user has must_change_password=True; they ONLY pass the
# get_current_user_allow_rotation dep, used exclusively by
# /api/auth/change-password. Every other Depends(get_current_user) call
# rejects them with 403.
TOKEN_SCOPE_FULL          = "full"
TOKEN_SCOPE_MUST_ROTATE   = "must_rotate"
_VALID_SCOPES             = (TOKEN_SCOPE_FULL, TOKEN_SCOPE_MUST_ROTATE)


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
def create_access_token(user: dict, scope: str = TOKEN_SCOPE_FULL) -> str:
    """Issue a bearer JWT for a freshly authenticated user.

    `user` is the dict UserManager.authenticate returns. Only `username`
    and `role` go into the token — never the password hash, never PII.

    Args:
        user:  dict with at minimum a "username" key (or "sub").
        scope: "full" (default — full access) or "must_rotate" (only
               valid against /api/auth/change-password).

    Backward compatibility (Batch 3b):
        Full-scope tokens are encoded WITHOUT a `scope` claim. Tokens
        issued by pre-3b builds (still circulating in client localStorage)
        have no `scope` claim either, and must be interpreted as full
        scope on decode — encoding-side symmetry preserves that.
    """
    import jwt as _jwt

    username = user.get("username") or user.get("sub")
    if not username:
        raise ValueError("create_access_token: user dict missing 'username'")
    if scope not in _VALID_SCOPES:
        raise ValueError(
            f"create_access_token: invalid scope {scope!r}; "
            f"must be one of {_VALID_SCOPES}"
        )

    now = datetime.now(timezone.utc)
    payload = {
        "sub":  username,
        "role": user.get("role", "Staff"),
        "iat":  int(now.timestamp()),
        "exp":  int((now + TOKEN_LIFETIME).timestamp()),
    }
    # Omit `scope` for full tokens — keeps the on-the-wire payload
    # identical to pre-3b tokens, so any cached/in-flight tokens stay
    # valid through the deploy.
    if scope != TOKEN_SCOPE_FULL:
        payload["scope"] = scope
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
def _extract_token_payload(authorization: Optional[str]) -> dict:
    """Internal — extract + validate bearer token, return user dict WITH
    scope. Used by both get_current_user (which enforces full scope) and
    get_current_user_allow_rotation (which permits must_rotate).

    The returned dict has shape:
        {"username", "role", "scope", "iat", "exp"}

    `scope` defaults to TOKEN_SCOPE_FULL for tokens that don't include
    the claim (pre-Batch-3b tokens, or any externally-issued token that
    chose to omit the claim — interpreted as full access for backward
    compatibility with existing live tokens).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Bearer scheme followed by no token (e.g. "Bearer " or "Bearer  ")
    # passes the startswith check but split(None, 1) returns a 1-element
    # list, so [1] would IndexError. Defend explicitly.
    parts = authorization.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = parts[1].strip()
    payload = decode_token(token)
    return {
        "username": payload.get("sub"),
        "role":     payload.get("role", "Staff"),
        "scope":    payload.get("scope", TOKEN_SCOPE_FULL),
        "iat":      payload.get("iat"),
        "exp":      payload.get("exp"),
    }


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """FastAPI Depends — extract + validate bearer token, return user dict.

    Requires FULL-scope tokens. Tokens with scope="must_rotate" are
    rejected with 403 — they are only valid against the change-password
    endpoint, which uses get_current_user_allow_rotation.

    Mechanical enforcement (Batch 3b): every existing endpoint that
    already declared `Depends(get_current_user)` now inherits the
    rotation gate for free. No endpoint changes are needed elsewhere.

    The returned dict has shape {"username", "role", "scope", "iat", "exp"}.
    Pages that need fuller user data should call UserManager.users[username]
    themselves.
    """
    user = _extract_token_payload(authorization)
    if user.get("scope") == TOKEN_SCOPE_MUST_ROTATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Password rotation required. Call POST /api/auth/change-password "
                "to set a new password before accessing any other endpoint."
            ),
        )
    return user


def get_current_user_allow_rotation(
    authorization: Optional[str] = Header(None),
) -> dict:
    """FastAPI Depends — like get_current_user but accepts must_rotate scope.

    USE THIS DEP ONLY ON /api/auth/change-password. Every other
    authenticated endpoint must use get_current_user, which rejects
    must_rotate scope and forces users through the rotation flow.

    Returns the same dict shape as get_current_user, with `scope`
    indicating which token type was presented so the route can audit
    the rotation-from-forced vs voluntary-change distinction.
    """
    return _extract_token_payload(authorization)


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
    Because get_current_user enforces full scope (Batch 3b), require_admin
    inherits the rotation gate transparently — admins with
    must_change_password=true cannot reach admin endpoints until they
    rotate.
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

# ── require_role factory (v10.499 Stage C Batch 2b) ───────────────────────
# Generalises require_admin to arbitrary role lists. Used by routes that
# need RBAC beyond the admin/non-admin binary, e.g. /api/dashboard/md
# (MD only), /api/credit/watchlist (Credit roles + executives).
#
# Pattern matches require_admin: a factory builds the chained Depends form
# so routes write `Depends(require_role(["MD"]))` cleanly without importing
# the chain machinery at every callsite.
#
# Role matching is case-insensitive (so callers don't have to remember
# whether users.json stores "Managing Director" or "managing director").
# Whitespace is normalised on both sides. The accepted-roles list must
# be non-empty; passing [] raises ValueError immediately at factory call
# time, not at request time — fail-fast per A2Z doctrine.
#
# Batch 3b: this factory chains through get_current_user, which now
# enforces full scope — must_rotate-token users hit 403 from
# get_current_user before this factory's body ever runs.
def require_role(accepted_roles: list[str]):
    """FastAPI Depends factory — require user's role to be in accepted_roles.

    Returns a FastAPI dependency callable. Raises 403 (not 401) on
    insufficient role so the caller knows the token was valid but the
    user isn't authorised for this specific endpoint.

    Usage:
        from fastapi import Depends
        from utils.auth_jwt import require_role

        @app.get("/api/dashboard/md")
        def md_dashboard(user: dict = Depends(require_role(["Managing Director"]))):
            ...

        @app.get("/api/credit/decisions")
        def credit(user: dict = Depends(require_role(
            ["Branch Credit Manager", "Director Retail Banking", "Managing Director"]
        ))):
            ...

    Args:
        accepted_roles: list of role strings the user's role must match
                        (case-insensitive). Must be non-empty.

    Raises:
        ValueError: if accepted_roles is empty (factory call time).
        HTTPException 403: if authenticated user's role not in list
                           (request time).
    """
    if not accepted_roles:
        raise ValueError(
            "require_role: accepted_roles must be a non-empty list. "
            "If you mean 'any authenticated user', use Depends(get_current_user) "
            "directly. If you mean 'admin only', use Depends(require_admin)."
        )

    # Pre-normalise the accepted list once at factory time, not at every
    # request. Saves a few microseconds per call and makes intent explicit.
    normalised_accepted = {r.strip().lower() for r in accepted_roles if r and r.strip()}
    if not normalised_accepted:
        raise ValueError(
            "require_role: accepted_roles contained only blank strings."
        )

    from fastapi import Depends

    def require_role_dep(user: dict = Depends(get_current_user)) -> dict:
        """Inner dependency — verifies authenticated user's role is accepted."""
        user_role = (user.get("role") or "").strip().lower()
        if user_role not in normalised_accepted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This endpoint requires one of: "
                    f"{sorted(accepted_roles)}. Your role: "
                    f"{user.get('role', '(none)')}."
                ),
            )
        return user

    # Give the closure a readable __name__ so FastAPI's OpenAPI docs and
    # error messages show something meaningful instead of 'require_role_dep'.
    require_role_dep.__name__ = (
        f"require_role[{','.join(sorted(normalised_accepted))}]"
    )

    return require_role_dep
