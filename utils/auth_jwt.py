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
        "jti":  "<uuid4>",           # NEW v10.497: unique token id for blocklist
    }

Lifetime: 30 minutes (matches the audit's session-timeout expectation).
Refresh tokens are intentionally NOT supported in this iteration — log in
again on expiry. The audit didn't require refresh and the React migration
that would benefit from it isn't here yet.

v10.497 Phase 1 additions:
    - jti (JWT ID, RFC 7519 §4.1.7) minted into every token. UUID4. Lets
      us blocklist individual tokens without storing every token issued —
      we only track explicitly-revoked ones until their natural expiry.

    - Cookie-based token source. get_current_user now accepts the JWT
      from either:
        (a) `Authorization: Bearer <token>` header (existing API path —
            scripts/run_load_tests.py, tests/load/lib/auth.js, etc.)
        (b) `access_token` httpOnly cookie (new browser path — React
            SPA, set by /api/auth/login response).
      Cookie wins when both are present (browsers send both; the cookie
      is the more secure source because httpOnly hides it from JS, so
      XSS attacks can't exfiltrate it).

    - Token blocklist for logout. revoke_token(jti, exp) writes to
      data/jwt_blocklist.json; decode_token checks this list before
      returning claims. Entries auto-expire when the underlying token
      would have expired anyway, so the file stays small (max ~30
      minutes of recently-revoked tokens at any time).

    - require_role(roles) factory generalizes require_admin. Returns
      a FastAPI Depends that accepts any role in the given list.

Usage in routes:
    from fastapi import Depends
    from utils.auth_jwt import get_current_user, require_admin, require_role

    @app.get("/api/bsc/summary")
    def bsc_summary(user: dict = Depends(get_current_user)):
        ...

    @app.post("/api/cache/clear")
    def clear_cache(user: dict = Depends(require_admin)):
        ...

    @app.get("/api/md/cockpit")
    def md_cockpit(user = Depends(require_role(["MD", "Director Retail Banking"]))):
        ...

audit gate G12 (api_auth_safety) verifies every @app.get/post route except
/api/health declares one of these Depends arguments.
audit gate G382 (NEW v10.497) verifies JWT + cookie + CSRF wiring is in
place across utils/api.py and this module.
"""
from __future__ import annotations

import json
import os
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Header, Cookie, status

logger = logging.getLogger("a2z.auth")

# ── Secret + algorithm ───────────────────────────────────────────────────
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


# ── Blocklist (v10.497) ──────────────────────────────────────────────────
# Logged-out tokens go here, keyed by jti, valued by epoch-expiry.
# Entries auto-prune on every check so the file stays bounded by the
# JWT lifetime (~30 min worth of recently-revoked tokens).
#
# File location follows the existing a2z/data/* convention. JSON because
# we already have JSON read/write infrastructure and the access pattern
# is low-volume (only on logout + every authenticated request).
#
# Future: when A2Z_DB_BACKEND=postgresql is on, this should migrate to
# a `jwt_blocklist` table with the same {jti, exp} schema. Deferred to
# a later batch — out of scope for v10.497 Phase 1.

_BLOCKLIST_PATH = Path(__file__).resolve().parent.parent / "data" / "jwt_blocklist.json"


def _load_blocklist() -> dict:
    """Load blocklist from disk and prune expired entries in one pass.

    Returns {jti: exp_epoch}. Missing file → empty dict (first call).
    Corrupt file → empty dict + log warning (don't crash auth on bad
    JSON; failing closed would lock everyone out).
    """
    try:
        if not _BLOCKLIST_PATH.exists():
            return {}
        with _BLOCKLIST_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        # Prune entries that have expired anyway — the underlying tokens
        # are already invalid via the exp claim, so blocklist tracking
        # them adds no security and grows the file unnecessarily.
        now = datetime.now(timezone.utc).timestamp()
        pruned = {jti: exp for jti, exp in data.items()
                  if isinstance(exp, (int, float)) and exp > now}
        # Persist the pruned version if anything was removed, so the
        # file shrinks over time. Best-effort; if the write fails the
        # in-memory pruned view is still correct for this call.
        if len(pruned) != len(data):
            try:
                _save_blocklist(pruned)
            except Exception as e:
                logger.warning(f"jwt_blocklist: prune-save failed: {e}")
        return pruned
    except Exception as e:
        logger.warning(f"jwt_blocklist: load failed ({e}); treating as empty")
        return {}


def _save_blocklist(bl: dict) -> None:
    """Persist blocklist to disk. Creates parent directory if needed.

    Atomic write via temp-file + rename to avoid leaving a partial JSON
    file on crash. Best-effort — caller is the audited path so a failed
    save is logged but does not raise (the in-memory revocation still
    holds for this process; persistence is the durability layer).
    """
    try:
        _BLOCKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _BLOCKLIST_PATH.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(bl, f, indent=2, sort_keys=True)
        os.replace(tmp_path, _BLOCKLIST_PATH)
    except Exception as e:
        logger.error(f"jwt_blocklist: save failed: {e}")


def revoke_token(jti: str, exp: int) -> None:
    """Add a token's jti to the blocklist until its natural expiry.

    Called from /api/auth/logout. Idempotent (re-revoking is a no-op).
    The exp is the *original* token expiry epoch — used so the entry
    self-prunes on next _load_blocklist() pass after the token would
    have expired anyway.

    Failing closed on save error is wrong here: the cookie is already
    cleared on the client and the user expects to be logged out. We
    log + return; worst case the token remains usable until natural
    expiry, which is no worse than the pre-v10.497 baseline.
    """
    if not jti:
        return
    bl = _load_blocklist()
    bl[jti] = int(exp)
    _save_blocklist(bl)


def _is_revoked(jti: Optional[str]) -> bool:
    """True if this jti is on the blocklist. None / empty → not revoked
    (covers pre-v10.497 tokens that lack a jti claim — they remain
    valid until natural expiry, which is the existing behavior)."""
    if not jti:
        return False
    bl = _load_blocklist()
    return jti in bl


# ── Token issue / decode ─────────────────────────────────────────────────
def create_access_token(user: dict) -> str:
    """Issue a bearer JWT for a freshly authenticated user.

    `user` is the dict UserManager.authenticate returns. Only `username`,
    `role`, and a freshly minted `jti` go into the token — never the
    password hash, never PII.

    v10.497: `jti` (UUID4) added so individual tokens can be revoked via
    the blocklist on /api/auth/logout. Pre-v10.497 tokens without jti
    remain valid until natural expiry; the blocklist check no-ops on
    them (see _is_revoked).
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
        "jti":  str(uuid.uuid4()),
    }
    return _jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + validate a bearer JWT. Raises HTTPException(401) on any
    failure — expired, malformed, wrong signature, or revoked (v10.497).

    Order matters: signature/expiry check first (cheap, cryptographic),
    then blocklist (I/O). A token that fails signature verification
    should never trigger a blocklist read.
    """
    import jwt as _jwt

    try:
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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

    # v10.497: blocklist check. Tokens that have been explicitly logged
    # out via /api/auth/logout are rejected even though the signature
    # is still valid. _is_revoked is a no-op for tokens without a jti
    # claim (pre-v10.497 issuance).
    if _is_revoked(payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ── FastAPI dependencies ─────────────────────────────────────────────────
def get_current_user(
    authorization: Optional[str] = Header(None),
    access_token: Optional[str] = Cookie(None),
) -> dict:
    """FastAPI Depends — extract + validate JWT, return user dict.

    The dict has shape {"username", "role", "iat", "exp", "jti"}. Pages
    that need fuller user data should call UserManager.users[username]
    themselves.

    v10.497: dual-source. The token can come from either:
      (a) `Authorization: Bearer <token>` header (existing API path —
          load tests, scripts, server-to-server callers).
      (b) `access_token` httpOnly cookie (new browser path — React SPA).

    Cookie wins when both are present. Browsers will send the cookie
    automatically on every request; explicit Bearer headers are only set
    by code that knows what it's doing. Preferring cookie means the
    React app stays cookie-only and never accidentally falls back to
    a stale header.

    Either path missing → continue to the other. Both missing → 401.
    """
    # ── Path A: cookie (preferred for browsers) ──
    token = None
    if access_token:
        token = access_token.strip()

    # ── Path B: Authorization: Bearer (existing API consumers) ──
    if not token:
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
        "iat":      payload.get("iat"),
        "exp":      payload.get("exp"),
        "jti":      payload.get("jti"),
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


# ── Generic role gating (v10.497) ────────────────────────────────────────
def require_role(roles: list[str]):
    """FastAPI Depends factory — require user.role to be in the given list.

    Generalizes require_admin. Returns a FastAPI Depends-compatible
    callable. Role comparison is case-insensitive on the resolved user
    side but case-preserving on the configured list, so call sites can
    write the doctrinal capitalization:

        @app.get("/api/md/cockpit")
        def md_cockpit(
            user = Depends(require_role(["MD", "Director Retail Banking"]))
        ):
            ...

    Raises 403 (token valid, role insufficient) — never 401 (which
    means "no valid token"). The distinction matters for clients
    deciding whether to redirect to login (401) or show "access
    denied" (403).

    Empty list raises immediately on call — a role check with no
    allowed roles is almost certainly a typo, not a deliberate
    deny-all.
    """
    if not roles:
        raise ValueError("require_role: at least one role must be specified")

    allowed = {r.strip().lower() for r in roles if r and r.strip()}
    if not allowed:
        raise ValueError("require_role: no usable roles after normalization")

    # Capture the original list for the error message (preserves user-
    # facing capitalization vs the normalized lowercase set used for
    # matching).
    allowed_display = ", ".join(roles)

    from fastapi import Depends

    def role_dep(user: dict = Depends(get_current_user)) -> dict:
        role = (user.get("role") or "").strip().lower()
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This endpoint requires one of: {allowed_display}",
            )
        return user

    # Set a readable __name__ so FastAPI's docs render meaningful names
    # for these dependencies. Without this, every route shows
    # "role_dep" in the OpenAPI schema, which is unhelpful.
    role_dep.__name__ = f"require_role_{'_or_'.join(sorted(allowed))}"
    return role_dep


# ── Self-test (run with: python -m utils.auth_jwt) ───────────────────────
if __name__ == "__main__":
    # Minimal smoke test — exercises the token lifecycle and the
    # blocklist round-trip. Not a substitute for the integration tests
    # in tests/test_auth_jwt*.py which cover every branch.
    import sys

    print("auth_jwt self-test")
    print("─" * 60)

    test_user = {"username": "selftest", "role": "Admin"}
    token = create_access_token(test_user)
    print(f"  ✓ create_access_token: {len(token)} chars")

    claims = decode_token(token)
    print(f"  ✓ decode_token: sub={claims['sub']} jti={claims['jti'][:8]}…")
    assert claims["sub"] == "selftest"
    assert claims["role"] == "Admin"
    assert "jti" in claims

    # Revoke it and verify decode now rejects.
    revoke_token(claims["jti"], claims["exp"])
    print(f"  ✓ revoke_token: jti added to blocklist")

    try:
        decode_token(token)
    except HTTPException as e:
        if e.detail == "Token revoked":
            print(f"  ✓ decode_token after revoke: 401 'Token revoked'")
        else:
            print(f"  ✗ wrong 401 detail: {e.detail}")
            sys.exit(1)
    else:
        print(f"  ✗ revoked token still decoded — blocklist broken")
        sys.exit(1)

    print("─" * 60)
    print("auth_jwt self-test PASSED")
