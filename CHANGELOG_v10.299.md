# Changelog — v10.299 Phase 3 Arc 5: CORS + Production Deploy Config

**Date:** 2026-05-11
**Phase:** 3 (fifth arc — React-readiness deploy contract)
**Audit:** 190/190 gates PASS = 100.0%
**Tests:** 95/95 passing across 6 integration suites (13 skipped
in audit env)
**G162 Rebase:** none — this batch touched markdown + Python
but added no new tenant tokens beyond the v10.298 baseline.

---

## Summary

Fifth Phase 3 arc. Where v10.297 made the cockpit data
HTTP-fetchable, v10.299 makes it **safely fetchable from a
different origin** — the configuration shape every React frontend
deploy needs. Plus a real deploy guide so operators can actually
ship the stack.

This is option (1) from the v10.298 "next arcs" list: CORS +
production deploy config. The next two items (Credit live
cockpit, CIMS field vocabulary harmonization) follow when this
foundation is in place.

---

## What's actually new

### `utils/api.py` — CORS configuration hardened

The CORS middleware was already in place (since v5.17, the
V-009 fix), but several gaps existed:

| Setting | Before | After | Rationale |
|---------|--------|-------|-----------|
| `allow_methods` | `GET, POST, PUT` | `GET, POST, PUT, DELETE, PATCH, OPTIONS` | OPTIONS is mandatory for CORS preflight; DELETE/PATCH coming as state-changing endpoints land |
| `allow_headers` | `["*"]` | `Authorization, Content-Type, Accept, X-Requested-With` | Explicit list documents what the React frontend needs |
| Default origins | Streamlit only (8501, 8502) | Streamlit + React CRA (3000) + Vite (5173) | Fresh React dev workflow works without env-var fiddling |
| Empty env var | Silently allows zero origins | Falls back to defaults + warns | Prevents the misconfigured-env trap |

The V-009 wildcard-with-credentials guard is preserved
verbatim — the `RuntimeError` still raises if `*` appears in
the origins list.

### `.env.example` (NEW)

Documents every environment variable the app reads:

- `A2Z_CORS_ORIGINS` — with explicit V-009 warning
- `A2Z_JWT_SECRET` — with generation command
- `A2Z_DB_BACKEND` + PG connection vars
- `A2Z_FLEXCUBE_*` connection
- `A2Z_LLM_PROVIDER`, `A2Z_LLM_API_KEY`
- `A2Z_LOG_LEVEL`

Each variable has a comment explaining what it does, when it's
needed, and how to set it.

### `DEPLOY.md` (NEW)

Production deployment guide for the FastAPI backend + React
frontend split:

1. Architecture overview diagram (React → FastAPI → engines)
2. Full environment variable reference
3. CORS configuration deep-dive (preflight, OPTIONS,
   troubleshooting)
4. JWT authentication flow (server + client side)
5. React frontend deployment (nginx/Caddy static + API on
   separate origin)
6. Running the backend (dev + production uvicorn/gunicorn
   commands)
7. Running the Streamlit cockpit
8. Database migration tracking (G163)
9. Observability + audit logs
10. Post-deploy smoke tests (CORS preflight, auth, audit
    flow)
11. Rollback procedure (tag-per-version pattern)

### `scripts/audit.py` — G190 added

`gate_cors_and_deploy_config` locks the React-readiness deploy
contract via 8 checks:

1. `utils/api.py` has `CORSMiddleware` configured
2. `allow_methods` includes the full standard set
3. V-009 wildcard guard with `RuntimeError` intact
4. React dev origins (3000, 5173) in defaults
5. Empty `A2Z_CORS_ORIGINS` guarded (fallback or raise)
6. `.env.example` exists with documented `A2Z_CORS_ORIGINS` +
   JWT secret + V-009 warning
7. `DEPLOY.md` exists with CORS, JWT, env vars, React topics
8. `utils/api_cockpit.py` does NOT define its own CORS
   (inherits parent)

### `tests/integration/test_cors_and_deploy_config.py` (NEW)

14 tests across 6 sections:

1. CORS middleware presence + verb/header completeness
2. V-009 wildcard-with-credentials guard liveness
3. React dev-server origins in defaults + empty-env fallback
4. `.env.example` exists with critical vars + V-009 warning
5. G190 gate liveness
6. Cockpit API doesn't define own CORS (inheritance check)

All 14 pass.

---

## TDD red→green progression

Following the v10.296 Kaizen pattern: tests written FIRST.

**Red phase (before edits):** 4 passing, 7 failing, 3 skipped.
The 4 already-passing checks confirmed the V-009 fix was intact
and CORS middleware was wired up — that's the part v5.17 got
right. The 7 failing tests defined what needed to change:
methods, headers, default origins, empty-env guard, `.env.example`,
`DEPLOY.md`, audit gate.

**Green phase (after edits):** 14/14 passing.

The 3 originally-skipped tests (waiting on file creation) now
run because `.env.example` and `DEPLOY.md` exist.

---

## What didn't change

- No new pages
- No new engines
- No new HTTP endpoints
- No new tenant tokens (G162 stays at 3999)
- Memory + live-data files untouched

Configuration + documentation arc. Backend code change is
limited to ~30 lines in `utils/api.py`.

---

## React frontend deployment math

After this batch, deploying a React SPA against this backend
requires exactly these steps:

1. **Build the React app** with `REACT_APP_API_URL` or `VITE_API_URL`
   pointing to the backend.
2. **Set `A2Z_CORS_ORIGINS`** on the backend to include the
   frontend's production URL.
3. **Restart the backend.**
4. Run the post-deploy smoke tests from `DEPLOY.md`.

Before this batch, step 2 was guesswork — operators had no
template and no way to know which env vars existed. Now
`.env.example` is the reference.

---

## Real findings during this batch

1. **The V-009 fix was already in place** (v5.17). Phase 3 just
   tightened the surrounding posture. Nothing was actually broken
   before; the gaps were on completeness, not correctness.

2. **`utils/api_cockpit.py` did not define its own CORS.**
   The check `test_cockpit_api_module_does_not_define_its_own_cors`
   passes — confirms the v10.297 module correctly leaves CORS to
   the parent app.

3. **G162 doesn't scan markdown or env files.** The gate
   targets `*.py` files only. DEPLOY.md and `.env.example`
   mention "Ecobank", "Kenya", "CBK" etc. liberally without
   triggering rebase. This is correct behavior — documentation
   files are *meant* to mention the bank — but worth noting for
   any future audit-scope expansion.

4. **The default CORS origins now cover 4 dev-server setups**
   (CRA 3000, Vite 5173, Streamlit 8501, 8502). If a Phase 3
   developer adds a new tool with a different default port (say,
   Next.js on 3001), they need to extend `_default_cors` or set
   `A2Z_CORS_ORIGINS` explicitly. Logged in `DEPLOY.md` as
   guidance.

---

## Files changed

- `utils/api.py` — CORS middleware tightened (~30 lines)
- `.env.example` — NEW (~80 lines)
- `DEPLOY.md` — NEW (~280 lines)
- `scripts/audit.py` — G190 added and registered
- `tests/integration/test_cors_and_deploy_config.py` — NEW
  (14 tests)
- `CHANGELOG_v10.299.md` — this file

---

## Audit results

```
Score: 190/190 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 190/190 gates green
- **Standards active:** 330/330 (no change)
- **Pages:** 114 (no change)
- **Tiers:** 55 (no change)
- **Gates:** G1-G190 (linear, no gaps)
- **Live cockpits:** 2 (CIMS + Treasury), both HTTP-reachable
- **HTTP endpoints (cockpit):** 7 (no change)
- **Integration test suites:** 6 (was 5)
- **Integration tests passing:** 95/95 (13 skipped in audit env)
- **Deploy artifacts:** `.env.example`, `DEPLOY.md` (both NEW)
- **CORS posture:** full method set, explicit headers, React
  dev origins, V-009 wildcard guard intact

---

## React-readiness check

Three React-readiness invariants now hold and are tested:

1. **CORS handles the preflight roundtrip.** OPTIONS in
   `allow_methods`, Authorization in `allow_headers`,
   `allow_credentials=True` paired with explicit origins.
2. **Dev workflow works without env-var setup.** Default
   origins cover the two main React dev servers.
3. **Production deploys have a documented contract.**
   `.env.example` is the template; `DEPLOY.md` is the guide.

When the frontend work begins (whether next batch or in a
month), the backend won't be the blocker.

---

## Next Phase 3 arc options (unchanged from v10.298)

In order:

1. ~~**CORS + production deploy config**~~ — DONE this batch.
2. **Credit live cockpit** — 12 engines (#119-#130). Treasury-
   style pattern. Inherits Phase 3 discipline + React-readiness
   automatically.
3. **Compliance live cockpit** — CMS engines (#191-#200).
4. **TreasuryDashboardEngine wiring** — close the "0 sections"
   placeholder in Treasury cockpit tab 7.
5. **CIMS field vocabulary harmonization (B-001)** — real-world
   data-join bug.
6. **PG migration push** — toward 75/79 (95%).
