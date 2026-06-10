# CHANGELOG_v10501_batch4b.md

**Batch:** v10.501 Phase 2 Arc B Batch 4b
**Date:** 2026-06-10
**Authors:** Joshua Mokua + Claude
**Closure:** GAP-006 (no rate limiting on auth endpoints)
**Previous batch commit:** `e542acd` (v10.501 Phase 2 Arc A Batch 4a)
**Phase 2 Arc B status after this batch:** **CLOSED**

---

## Summary

Closes GAP-006 by mounting `slowapi` on the FastAPI app and applying
per-endpoint rate limits to the two auth endpoints that surface to
attackers:

- **`/api/auth/login`** — 10 attempts per minute per IP + 100 per
  hour per IP. Per-IP keying because the username is part of the
  attack surface and we want to throttle attackers regardless of
  what username they're guessing.
- **`/api/auth/change-password`** — 5 attempts per minute per
  bearer token. Per-token keying (not per-IP) because NAT'd corporate
  networks would otherwise share a 5/min budget across hundreds of
  legitimate users.
- **`/api/auth/whoami-detailed`** — intentionally NOT rate-limited.
  Legitimate dashboard polling makes frequent requests; throttling
  would degrade UX for honest clients.

A custom `_ratelimit_exceeded_handler` writes an `API_RATE_LIMITED`
audit row on every 429 so the operator can see when an attacker hits
the wall vs. when they're just guessing slowly.

`X-RateLimit-*` response headers are intentionally disabled to avoid
leaking remaining-quota information to brute-forcing attackers.

---

## Files changed

### New files

| Path | Lines | Purpose |
|---|---:|---|
| `tests/test_rate_limit_auth.py` | ~245 | 8 regression cases covering the policy per endpoint, 429 response shape, credential non-leakage in 429 body, per-token-vs-per-IP independence, audit row written + SECURITY pin that the audit row does not contain the raw JWT. |
| `docs/CHANGELOG_v10501_batch4b.md` | this file | Per-batch closure record. |

### Modified files

| Path | Change | Closes |
|---|---|---|
| `requirements.txt` | `slowapi>=0.1.9` added to the API tier section with a citation comment. | GAP-006 (dependency) |
| `utils/api.py` | Six discrete additions, no other changes. See "Implementation" section below. | GAP-006 (wiring) |
| `docs/architecture/OPERATIONAL_PROTOCOL.md` | New section "Single-worker FastAPI operational constraint" inserted before Future Protocol Candidates. Codifies the rule, trigger, failure mode if violated, and the future migration path to Redis/memcached. | doctrine codification |
| `docs/architecture/POLICY_GAPS.md` | GAP-006 flipped to CLOSED with closure summary; historical OPEN record preserved per RL1. Phase summary updated. | doctrine sync |
| `docs/architecture/REVIVAL_LEDGER.md` | New top entry (this batch). | RL1 append discipline |
| `docs/continuity/SESSION_BOOTSTRAP.md` | Phase 2 commit list extended with Batch 4b row. Active workstreams renumbered (Arc B removed, Arc C is now next). Known doctrine gaps section marks GAP-006 closed. Single-worker constraint added to "Governance doctrine in force" list. | doctrine sync |
| `app.py` | `_APP_VERSION` bumped to `v10.501-batch4b-2026.06.10`. | session_state invalidation |

---

## Implementation in `utils/api.py` — six discrete additions

1. **Import block extension** (top of file):
   - `Request` added to the existing `fastapi` import.
   - New `slowapi` block: `Limiter`, `errors.RateLimitExceeded`,
     `middleware.SlowAPIMiddleware`, `util.get_remote_address`.

2. **`_ratelimit_key_by_token(request)` helper** (after CORS block):
   Derives a stable 64-bit hashed key from the bearer token in the
   `Authorization` header. SHA-256 → first 16 hex chars. Falls back
   to per-IP if no header present. SECURITY: the raw JWT never
   appears in any storage structure.

3. **`Limiter` instance:**
   ```python
   limiter = Limiter(
       key_func=get_remote_address,
       default_limits=[],
       headers_enabled=False,
   )
   app.state.limiter = limiter
   ```
   `headers_enabled=False` is intentional. See the inline comment
   for the rationale (avoids leaking remaining-quota to attackers,
   also avoids slowapi's requirement that every limited route
   declare a `response: Response` parameter).

4. **`_ratelimit_exceeded_handler(request, exc)`:** Custom 429
   handler that:
   - Best-efforts the authenticated username from the bearer token
     (the helper logs at DEBUG on decode failure — silent-except
     discipline preserved as logged-non-fatal).
   - Writes `API_RATE_LIMITED` audit row with path, method, IP, and
     limit detail.
   - Returns generic 429 with `Retry-After: 60`.
   - SECURITY: never includes the raw JWT in the audit payload or
     response body.

5. **Handler + middleware mount:**
   ```python
   app.add_exception_handler(RateLimitExceeded, _ratelimit_exceeded_handler)
   app.add_middleware(SlowAPIMiddleware)
   ```

6. **Endpoint decorators:**
   - `/api/auth/login`:
     `@limiter.limit("10/minute;100/hour")` + `request: Request` param
   - `/api/auth/change-password`:
     `@limiter.limit("5/minute", key_func=_ratelimit_key_by_token)`
     + `request: Request` param
   - `/api/auth/whoami-detailed`: deliberately NOT decorated.

---

## Verification performed during authoring

### Standalone slowapi pattern sanity check

Before any A2Z integration, the slowapi pattern was verified in a
minimal standalone FastAPI app:

```
attempt 1: status=200
attempt 2: status=200
attempt 3: status=200
attempt 4: status=429
attempt 5: status=429
```

Pattern works exactly as designed against a `3/minute` limit.

### Integration test against the actual A2Z app

```
tests/test_rate_limit_auth.py::test_login_allows_up_to_10_requests_per_minute        PASSED
tests/test_rate_limit_auth.py::test_login_429_response_shape                         PASSED
tests/test_rate_limit_auth.py::test_login_429_does_not_leak_credentials              PASSED
tests/test_rate_limit_auth.py::test_change_password_allows_up_to_5_per_minute_per_token  PASSED
tests/test_rate_limit_auth.py::test_change_password_limit_is_per_token_not_per_ip    PASSED
tests/test_rate_limit_auth.py::test_whoami_detailed_is_not_rate_limited              PASSED
tests/test_rate_limit_auth.py::test_429_audit_row_is_written                         PASSED
tests/test_rate_limit_auth.py::test_429_handler_does_not_leak_token_in_audit         PASSED
```

8/8 against the real `utils.api` app with slowapi mounted.

### Cross-batch regression check

`tests/test_validate_password_policy.py` (Batch 4a): 22/22 still
pass. Combined Batch 4a + Batch 4b: **30/30 green.**

---

## Operator extraction instructions

The delivery is a ZIP whose root contains `_batch4b_payload/` per
Trap #14. Tree:

```
_batch4b_payload/
  app.py
  requirements.txt
  utils/
    api.py
  tests/
    test_rate_limit_auth.py
  docs/
    architecture/
      OPERATIONAL_PROTOCOL.md
      POLICY_GAPS.md
      REVIVAL_LEDGER.md
    continuity/
      SESSION_BOOTSTRAP.md
    CHANGELOG_v10501_batch4b.md
```

From the repo root (`C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`),
with `.venv\Scripts\activate` active, after extracting the ZIP at
the repo root:

```cmd
:: Verify staging folder
dir _batch4b_payload

:: Code files
copy /Y _batch4b_payload\app.py                                                 app.py
copy /Y _batch4b_payload\requirements.txt                                       requirements.txt
copy /Y _batch4b_payload\utils\api.py                                            utils\api.py
copy /Y _batch4b_payload\tests\test_rate_limit_auth.py                           tests\test_rate_limit_auth.py

:: Doctrine artifacts
copy /Y _batch4b_payload\docs\architecture\OPERATIONAL_PROTOCOL.md               docs\architecture\OPERATIONAL_PROTOCOL.md
copy /Y _batch4b_payload\docs\architecture\POLICY_GAPS.md                        docs\architecture\POLICY_GAPS.md
copy /Y _batch4b_payload\docs\architecture\REVIVAL_LEDGER.md                     docs\architecture\REVIVAL_LEDGER.md
copy /Y _batch4b_payload\docs\continuity\SESSION_BOOTSTRAP.md                    docs\continuity\SESSION_BOOTSTRAP.md
copy /Y _batch4b_payload\docs\CHANGELOG_v10501_batch4b.md                        docs\CHANGELOG_v10501_batch4b.md

:: Remove staging folder ONLY AFTER all copies completed
rmdir /S /Q _batch4b_payload
```

### Install the new dependency

```cmd
pip install -r requirements.txt
```

You should see `slowapi-0.1.9` (or newer) and its transitive `limits`
dependency get installed. If pip warns about other versions, that's
unrelated to this batch.

### Verification steps

```cmd
:: 1. Syntax check on modified Python files
python -m py_compile utils\api.py

:: 2. Confirm slowapi wiring landmarks
findstr /n "from slowapi" utils\api.py
findstr /n "@limiter.limit" utils\api.py
findstr /n "_ratelimit_" utils\api.py

:: 3. Run the new regression test
python -m pytest tests\test_rate_limit_auth.py -v

:: 4. Run Batch 4a regression too — no cross-batch breakage
python -m pytest tests\test_validate_password_policy.py tests\test_rate_limit_auth.py -v

:: 5. Confirm _APP_VERSION bump
findstr /n "_APP_VERSION" app.py
```

Expected results:
- Step 1: silent success.
- Step 2: imports at lines ~53 + ~59-62; two `@limiter.limit` lines (login + change-password); five `_ratelimit_*` references (helper, decorator, handler, exception handler mount).
- Step 3: 8 tests pass.
- Step 4: 30 tests pass total (22 from Batch 4a + 8 from Batch 4b).
- Step 5: `_APP_VERSION = "v10.501-batch4b-2026.06.10"`.

### Commit

```cmd
git add app.py requirements.txt utils\api.py tests\test_rate_limit_auth.py docs\architecture\OPERATIONAL_PROTOCOL.md docs\architecture\POLICY_GAPS.md docs\architecture\REVIVAL_LEDGER.md docs\continuity\SESSION_BOOTSTRAP.md docs\CHANGELOG_v10501_batch4b.md
git status
git commit -m "v10.501 Phase 2 Arc B Batch 4b - API rate limiting (closes GAP-006)"
```

Push is still deferred to the phase boundary per OPERATIONAL_PROTOCOL.
Phase 2 boundary lands after Arc C (GAP-002 closure).

---

## Operational constraint introduced

**Single-worker FastAPI deployment.** The slowapi in-memory storage
is correct only when there's exactly one Python process serving the
API. Multi-worker deployment (`uvicorn --workers N` with N > 1) would
let an attacker effectively get N × the stated rate budget because
each worker maintains its own in-memory counter.

This is now codified in `docs/architecture/OPERATIONAL_PROTOCOL.md`
as a binding rule. If a future deployment needs multi-worker, that
becomes its own arc: swap the slowapi storage backend to Redis or
memcached, add the shared cache to deployment topology, decide
fail-open vs. fail-closed when the cache is unavailable, and remove
the operational constraint section.

### What is NOT affected by the constraint

- **Multiple uvicorn instances on different hosts.** If you scale by
  running independent FastAPI processes on host A and host B with a
  load balancer in front, each host has its own rate-limit state.
  This is a legitimate scaling pattern — but it means a per-IP limit
  applies per-host, not globally. For login (per-IP), this is mildly
  weaker than ideal but acceptable. For change-password (per-token),
  it's fine — a single bearer token typically routes to a single host
  via session affinity. If session affinity is not configured, the
  per-token limit becomes per-host-per-token, which is still better
  than no limit at all.

- **Streamlit deployment.** Streamlit's own lockout at
  `pages/_login.py:194-204` is unaffected; it lives in
  `st.session_state` and is per-Streamlit-session. Independent of
  the FastAPI rate limit.

---

## What did NOT change

- **`utils/auth_jwt.py`** — unchanged. Token lifetime, scope semantics,
  and dependencies are not in Arc B scope.
- **`utils/core.py`** — unchanged from its Batch 4a state.
- **`pages/_login.py`** — unchanged from its Batch 4a state.
- **`frontend/web/src/`** — unchanged. The React `Login.tsx` and
  `ChangePassword.tsx` already display API error responses generically;
  they render a 429 detail string ("Rate limit exceeded: ...") as-is.
  A future polish batch could add explicit "Too many attempts" UX,
  but it's not required for closure.
- **`/api/auth/me`** — explicitly NOT rate-limited. Like
  whoami-detailed, this is a polling endpoint legitimately called
  by the React app at frequent intervals. If a future security
  review surfaces a different threat model, that becomes a separate
  arc.

---

## Next batch

**v10.501 Phase 2 Arc C Batch 4c — `users.json` tracking
(closes GAP-002).**

Direction: Path (B) — accept-and-document. Single-batch arc, low
blast radius. One `.gitignore` comment update clarifying that the
entry only applies to NEW files (not the already-tracked existing
copy), one note in `OPERATIONAL_PROTOCOL.md` documenting that
`data/users.json` is intentionally tracked despite the gitignore
entry, doctrine sync in POLICY_GAPS + REVIVAL_LEDGER +
SESSION_BOOTSTRAP, `_APP_VERSION` bump.

After Arc C lands, Phase 2 is closed and the local commits get
pushed to origin/main at the phase boundary.
