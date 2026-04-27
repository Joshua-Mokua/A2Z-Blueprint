A2Z MIS 360 — v5.17 release notes
=================================

Verified score: 12/12 gates (100%) per scripts/audit.py
Closes: V-001 (CVSS 9.1 API auth bypass) + V-009 (CVSS 7.0 CORS misconfig)

This release closes the LAST critical CVE. All four CVSS 9.0+ findings
(V-001, V-002, V-003, V-004) and the V-009 high finding are now closed.

WHAT WAS WRONG
--------------
The audit identified that all 12 FastAPI endpoints on port 8502 required
zero authentication:

  GET http://<server>:8502/api/dashboard/md       → Full bank metrics
  GET http://<server>:8502/api/credit/watchlist   → All NPL accounts
  GET http://<server>:8502/api/aml/summary        → AML alert counts
  GET http://<server>:8502/api/bsc/staff/<any>    → Anyone's BSC

Combined with V-007 (no rate limiting) and V-009 (CORS allow_credentials
with localhost), any network-adjacent attacker had complete read access
to the entire MIS — performance scores, NPL portfolios, AML alerts, user
directory.

WHAT WAS FIXED
--------------
1. New utils/auth_jwt.py — 200 lines:
   - HS256 JWT with 30-min expiry
   - Secret from A2Z_JWT_SECRET env var (auto-generated for dev with
     loud startup warning if defaulted)
   - create_access_token(user) — issues bearer token
   - decode_token(token)        — validates, raises 401 on tamper/expire
   - get_current_user(authorization: Header) — FastAPI Depends
   - require_admin              — chained Depends, raises 403 for non-admins
   - Token payload: {sub, role, iat, exp} — never password hash, never PII

2. utils/api.py — every route now declares its auth posture:
   PUBLIC (no auth):
     GET  /api/health             — system probe (intentionally public)
     POST /api/auth/login         — issues the token; cannot itself require one
   AUTHENTICATED (any role):
     GET  /api/auth/me            — NEW — current user from token
     GET  /api/bsc/summary
     GET  /api/bsc/staff/{user}   — also has V-005 IDOR mitigation
     GET  /api/pipeline/summary
     GET  /api/pipeline/deals
     GET  /api/credit/summary
     GET  /api/credit/watchlist
     GET  /api/aml/summary
     GET  /api/users/summary
     GET  /api/dashboard/md
     GET  /api/cache/stats
   ADMIN ONLY:
     POST /api/cache/clear

   Every endpoint also calls _audit("API_<NAME>", user, ...) so every
   API call is traceable in audit.audit_logs.

3. V-009 closed — CORS hardened:
   - Origins now from A2Z_CORS_ORIGINS env var (comma-separated)
   - Default for dev: localhost:8501/8502
   - Wildcard "*" with credentials raises at app startup (was the V-009 risk)

4. Direct I/O removed — _load_json now routes through a2z_db (matches
   the architectural seam convention).

5. utils/api_client.py — token-aware:
   - login(username, password) — exchanges creds for bearer, caches it
   - logout() — discards the cached token
   - is_authenticated() — checks for cached token
   - _get/_post — attach Authorization: Bearer <token>
   - 401/403 silently fall back to direct DB/JSON access (preserves the
     graceful-degradation behaviour pages rely on)

6. pages/7_admin.py — the one internal caller:
   - System Health panel logs the api_client in before clicking
     "Clear API cache". Falls back gracefully with a helpful message
     if session credentials aren't available.

7. requirements.txt — PyJWT>=2.8.0 added.

8. scripts/audit.py — G12 api_auth_safety gate:
   - Verifies every @app.get/@app.post route except /health and
     /auth/login declares Depends(get_current_user) or
     Depends(require_admin)
   - Verifies utils/auth_jwt.py exports the expected helpers
   - Verifies PyJWT in requirements.txt
   - Verifies CORS isn't allow_origins=["*"] with allow_credentials=True

9. Master_Prompt_v3.md updated:
   - Version v5.16 → v5.17
   - V-001 marked closed in Verified Gaps
   - Quality Gates table now shows 12 gates

FUNCTIONAL VERIFICATION (pre-shipment)
--------------------------------------
JWT round-trip tested with FastAPI stubbed (sandbox lacks fastapi):
  ✅ Token issuance produces valid 3-part JWT
  ✅ Tampered signatures rejected (401)
  ✅ Wrong-secret tokens rejected (401)
  ✅ Expired tokens rejected (401, "Token expired")
  ✅ Missing/malformed Authorization header rejected (401)
  ✅ "Basic" scheme rejected (401)
  ✅ require_admin accepts Admin role
  ✅ require_admin rejects Staff role (403)

WHAT'S STILL OPEN
-----------------
All four critical CVEs are now closed (V-001, V-002, V-003, V-004).
What remains is structural / operational work:

  BSC central engine (addendum-mandated)   — 1 week
  core.py split (6,596 lines → 8-10 files) — 1 week
  PG migration of 31 remaining tables      — 3 weeks
  API expansion 12 → 144 endpoints         — 6-8 weeks
  Test suite + CI/CD                       — 4 weeks

The G8 (bsc_contract) gate currently passes vacuously because no
modules use the central BSC engine yet — building it is the highest-
value next move because it's an explicit addendum standard.

INSTALLATION
------------
1. Extract this zip over your project root, replacing files where prompted.
2. Install the new dependency:
     pip install PyJWT>=2.8.0
3. (Optional but recommended) set the JWT secret in env:
     export A2Z_JWT_SECRET="$(openssl rand -base64 48)"
   On Windows:
     setx A2Z_JWT_SECRET "your-long-random-secret-here"
4. Restart Streamlit AND restart the FastAPI server (utils/api).
5. Run the audit:
     python scripts/audit.py
   Expected: 12/12 PASS, exit 0

VERIFY THE FIX (smoke test)
---------------------------
With the API running, test from a terminal:

  # Should fail (no auth):
  curl http://localhost:8502/api/bsc/summary
  → {"detail":"Missing or malformed Authorization header"}

  # Login:
  curl -X POST http://localhost:8502/api/auth/login \
       -H 'Content-Type: application/json' \
       -d '{"username":"william001","password":"ECOStaff001"}'
  → {"access_token":"eyJ...", "token_type":"bearer", ...}

  # Use the token:
  TOKEN="<paste token>"
  curl -H "Authorization: Bearer $TOKEN" http://localhost:8502/api/bsc/summary
  → {"by_dept": [...], "total_staff": ...}

  # Admin-only endpoint with non-admin token would return 403:
  curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8502/api/cache/clear
  → 200 if william001 is Admin, 403 otherwise

The FastAPI auto-generated docs at /api/docs now show a "Authorize"
button — clicking it lets you paste a token and try every endpoint
from the browser.

COMMIT
------
git add .
git commit -m "v5.17: V-001 API auth — JWT bearer on all endpoints (CVSS 9.1+7.0 closed)"
git tag v5.17-api-auth
git push origin main --tags
