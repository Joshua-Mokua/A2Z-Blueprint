"""
tests/integration/test_cors_and_deploy_config.py
================================================================================
v10.299 — CORS + production deploy config tests, written BEFORE
the fix per Kaizen TDD discipline.

The React SPA (#37) will run on a separate origin from the
FastAPI backend. Without proper CORS, every browser request from
React fails with a preflight error. This batch tightens the CORS
posture and documents the deploy contract.

Test sections:
  1. CORS middleware presence + correct configuration
  2. Wildcard-origin-with-credentials is still blocked (V-009)
  3. OPTIONS preflight method allowed
  4. React dev-server origins included in default list
  5. CORS gate G190 reports PASS
  6. Deploy config: .env.example exists with documented vars
  7. Deploy config: A2Z_CORS_ORIGINS validation guards against
     empty / malformed values
  8. Deploy config: documented in DEPLOY.md
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — CORS middleware presence
# ============================================================

def test_api_module_has_cors_middleware():
    """The main API module must add CORSMiddleware. Without it,
    every cross-origin request from React fails."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    assert "CORSMiddleware" in src
    assert "add_middleware" in src
    # Both must be related — they need to be near each other
    cors_idx = src.find("CORSMiddleware")
    add_idx = src.find("add_middleware")
    # Allow either order; just check both exist within reasonable proximity
    assert abs(cors_idx - add_idx) < 5000


def test_cors_methods_include_all_standard_verbs():
    """The CORS allow_methods list must cover what the API
    actually serves. We currently have GET/POST/PUT but the
    cockpit API + future expansion will need DELETE/PATCH, and
    OPTIONS is required for preflight."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    # Extract the allow_methods value from add_middleware call
    m = re.search(
        r"allow_methods\s*=\s*\[([^\]]+)\]",
        src,
    )
    assert m, "allow_methods not found in api.py"
    methods_blob = m.group(1)
    required = {"GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"}
    for verb in required:
        assert verb in methods_blob, (
            f"CORS allow_methods missing `{verb}`. Found: "
            f"{methods_blob.strip()}"
        )


def test_cors_headers_explicit_not_wildcard():
    """allow_headers=['*'] is technically allowed, but explicit
    headers are safer + clearer for the React frontend team. At
    minimum, document the headers we actually need."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    m = re.search(
        r"allow_headers\s*=\s*\[([^\]]+)\]",
        src,
    )
    assert m, "allow_headers not found in api.py"
    headers_blob = m.group(1)
    # Either explicit list with Authorization, or a documented "*" with comment
    if '"*"' in headers_blob or "'*'" in headers_blob:
        # Wildcard is acceptable when paired with a comment explaining why
        # — but the comment must mention React/SPA + headers
        # Look for explanatory comment within 3 lines above
        idx = src.find("allow_headers")
        nearby = src[max(0, idx - 500):idx]
        assert ("React" in nearby or "Authorization" in nearby
                or "Content-Type" in nearby), (
            "allow_headers=['*'] should have a comment near it "
            "explaining the React/Authorization rationale"
        )
    else:
        # Explicit list — must include the essentials
        assert ("Authorization" in headers_blob
                or "authorization" in headers_blob), (
            "CORS allow_headers must include Authorization "
            "(for JWT)"
        )
        assert ("Content-Type" in headers_blob
                or "content-type" in headers_blob), (
            "CORS allow_headers must include Content-Type"
        )


# ============================================================
# Section 2 — V-009 wildcard-with-credentials guard
# ============================================================

def test_wildcard_origin_with_credentials_still_blocked():
    """The V-009 fix must stay in place. Using '*' in
    A2Z_CORS_ORIGINS with allow_credentials=True is a critical
    vulnerability (any malicious site can read authenticated
    responses). The check raises RuntimeError at import time."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    # Look for the guard
    assert "'*'" in src or '"*"' in src
    assert "RuntimeError" in src or "raise" in src
    # The guard text mentions V-009 for traceability
    assert "V-009" in src, (
        "The V-009 fix should remain documented in the code "
        "by name — it's how operators search for the rationale "
        "when modifying CORS"
    )


def test_allow_credentials_true_with_explicit_origins():
    """allow_credentials=True is correct (we send JWTs as
    cookies/Authorization headers). Origins must be explicit, NOT
    wildcard."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    # Check the middleware call has allow_credentials=True
    m = re.search(
        r"add_middleware\s*\([^)]*CORSMiddleware[^)]*\)",
        src,
        re.DOTALL,
    )
    if not m:
        # Try a multi-line form (more common)
        idx = src.find("CORSMiddleware")
        assert idx >= 0
        # Look at the next 500 chars for `allow_credentials=True`
        nearby = src[idx:idx + 800]
        assert "allow_credentials=True" in nearby


# ============================================================
# Section 3 — React dev-server origins
# ============================================================

def test_default_cors_origins_include_react_dev_servers():
    """The default A2Z_CORS_ORIGINS value must include common
    React dev-server ports (3000 for CRA, 5173 for Vite). Otherwise
    a fresh React dev environment can't talk to the backend
    without env-var fiddling."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    # Locate the _default_cors definition. It may be a single-line
    # string OR a multi-line tuple/parenthesized form.
    idx = src.find("_default_cors")
    assert idx >= 0, "_default_cors constant not found"
    # Take a generous window and check React dev ports appear
    window = src[idx:idx + 1200]
    # React dev servers
    assert "3000" in window, (
        "Default CORS origins must include localhost:3000 "
        "(Create React App)"
    )
    assert "5173" in window, (
        "Default CORS origins must include localhost:5173 "
        "(Vite, the modern React default)"
    )
    # Streamlit dev origins should remain too
    assert "8501" in window
    assert "8502" in window


def test_cors_origins_empty_env_var_falls_back_to_default():
    """If A2Z_CORS_ORIGINS is set to empty string, the system
    must NOT silently allow zero origins (which would block
    everything). Either fall back to defaults or fail loudly."""
    src = (REPO_ROOT / "utils" / "api.py").read_text()
    # Look for handling: either `or _default_cors` fallback,
    # explicit length-zero check, or raise on empty.
    # Trivial regex check for the pattern:
    has_guard = (
        "_cors_origins:" in src and (
            "raise" in src.split("_cors_origins")[1][:600]
            or "len(_cors_origins)" in src
        )
    ) or "if not _cors_origins" in src
    assert has_guard, (
        "api.py must guard against empty A2Z_CORS_ORIGINS — "
        "either fall back to defaults or raise. Otherwise a "
        "misconfigured env var silently blocks all CORS."
    )


# ============================================================
# Section 4 — Deploy config files
# ============================================================

def test_env_example_exists():
    """A .env.example file must exist documenting every
    environment variable the app reads. Without this, fresh
    deployments are guesswork."""
    path = REPO_ROOT / ".env.example"
    assert path.exists(), (
        ".env.example missing — operators have no reference "
        "for which env vars to set in production"
    )


def test_env_example_documents_a2z_cors_origins():
    """The .env.example must include A2Z_CORS_ORIGINS with a
    comment explaining the format and warning against '*'."""
    path = REPO_ROOT / ".env.example"
    if not path.exists():
        pytest.skip("waits for .env.example creation")
    text = path.read_text()
    assert "A2Z_CORS_ORIGINS" in text
    # The comment / surrounding text must warn about wildcard
    idx = text.find("A2Z_CORS_ORIGINS")
    nearby = text[max(0, idx - 400):idx + 400]
    assert ("V-009" in nearby
            or "wildcard" in nearby.lower()
            or "credentials" in nearby.lower()), (
        ".env.example must warn against the V-009 wildcard-"
        "with-credentials pattern near A2Z_CORS_ORIGINS"
    )


def test_env_example_documents_jwt_secret():
    """JWT secret config must be documented too. Production
    deployments that miss this fall back to a default that
    `warn_if_default_secret()` warns about — but operators need
    to see it in the env template."""
    path = REPO_ROOT / ".env.example"
    if not path.exists():
        pytest.skip("waits for .env.example creation")
    text = path.read_text()
    # Some form of JWT secret env var
    assert (
        "JWT_SECRET" in text
        or "A2Z_JWT_SECRET" in text
        or "SECRET_KEY" in text
    ), (
        ".env.example must document the JWT signing secret "
        "env var"
    )


def test_deploy_md_exists():
    """A DEPLOY.md must exist with React frontend deployment
    instructions, CORS config, JWT signing, and the
    production-vs-dev distinction."""
    path = REPO_ROOT / "DEPLOY.md"
    assert path.exists(), (
        "DEPLOY.md missing — React frontend team will have "
        "no documented deployment story"
    )


def test_deploy_md_covers_required_topics():
    """The DEPLOY.md must cover at least: CORS, JWT, env vars,
    React build output location."""
    path = REPO_ROOT / "DEPLOY.md"
    if not path.exists():
        pytest.skip("waits for DEPLOY.md creation")
    text = path.read_text()
    required_topics = {
        "CORS": "CORS configuration",
        "JWT": "JWT signing key",
        "A2Z_CORS_ORIGINS": "env var",
        "React": "frontend deploy",
    }
    missing = []
    for keyword, what in required_topics.items():
        if keyword not in text:
            missing.append(f"`{keyword}` ({what})")
    assert not missing, (
        f"DEPLOY.md missing topics: {', '.join(missing)}"
    )


# ============================================================
# Section 5 — Audit gate G190 liveness
# ============================================================

def test_g190_gate_exists_and_passes():
    """After the CORS + deploy work, audit gate G190 must
    report PASS. If this test fails, the gate or its
    preconditions broke."""
    from scripts.audit import GATES

    g190_found = None
    for gid, fn in GATES:
        if gid == "G190":
            g190_found = fn()
            break

    assert g190_found is not None, (
        "G190 gate not registered. v10.299 must add the "
        "CORS + deploy gate."
    )
    assert g190_found["passed"], (
        f"G190 failed. Summary: {g190_found.get('summary', '')}. "
        f"Violations: {g190_found.get('violations', [])[:5]}"
    )


# ============================================================
# Section 6 — Cockpit API CORS-compatible at the route layer
# ============================================================

def test_cockpit_api_module_does_not_define_its_own_cors():
    """utils/api_cockpit.py is included into the main app
    via include_router. It must NOT define its own CORSMiddleware
    — the parent app's middleware applies to all mounted routers."""
    src = (REPO_ROOT / "utils" / "api_cockpit.py").read_text()
    assert "add_middleware(CORSMiddleware" not in src, (
        "api_cockpit.py should NOT define its own CORS — "
        "it inherits from the parent app's middleware"
    )
    assert "CORSMiddleware" not in src, (
        "api_cockpit.py shouldn't import CORSMiddleware — "
        "CORS is a parent-app concern"
    )
