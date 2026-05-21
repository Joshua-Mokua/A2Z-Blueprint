# A2Z MIS 360 — Deployment Guide

This document covers production deployment of A2Z MIS 360, with
particular attention to the FastAPI backend that serves the
React frontend (#37) and the Streamlit cockpit (which hosts the
read-side views today).

Last updated: v10.299 (2026-05-11)

---

## Architecture overview

```
                            ┌────────────────────────┐
                            │  React SPA (port 443)  │
                            │  (Phase 3 closure)     │
                            └────────┬───────────────┘
                                     │ HTTPS + JWT
                                     ▼
       ┌────────────────────────────────────────────────────┐
       │  FastAPI (uvicorn) — utils/api.py                   │
       │    ├── /api/cockpit/*    (v10.297 React-ready)      │
       │    ├── /api/treasury/*   (v10.154)                  │
       │    ├── /api/strategy/*   (v10.141)                  │
       │    └── /api/*            (CRUD + auth + admin)      │
       └────────┬─────────────────────────────────────────────┘
                │
                ▼
       ┌────────────────────────────────────────────────────┐
       │  Engines + Storage                                  │
       │    ├── utils/bsc_engine.py    (write chokepoint)    │
       │    ├── data/*.json            (JSON-mode tables)    │
       │    └── PostgreSQL             (PG-mode tables)       │
       └────────────────────────────────────────────────────┘

       ┌────────────────────────────────────────────────────┐
       │  Streamlit cockpit — pages/*.py                     │
       │    ├── pages/109_cims_live.py    (Phase 3 Arc 1)    │
       │    ├── pages/110_treasury_live.py (Phase 3 Arc 2)   │
       │    └── pages/0-108_*.py           (Phase 1-2 pages) │
       │  Shares the same engines and cockpit_read composers │
       │  as the API. Single source of truth.                 │
       └────────────────────────────────────────────────────┘
```

The React SPA and the Streamlit cockpit both read the same
data through the same composers (`utils/cockpit_read.py`). The
React app fetches via HTTP from `/api/cockpit/*`; the Streamlit
pages call the composers directly in-process. **There is no
duplicated business logic between the two transports.**

---

## Environment variables

All configuration is via environment variables. See
`.env.example` for the full template. Critical ones for
production:

### `A2Z_CORS_ORIGINS` (required for React frontend)

Comma-separated list of origins allowed to make authenticated
requests. The React SPA will run on a different origin from the
backend in production, so this **must** be set explicitly.

Example:

```
A2Z_CORS_ORIGINS=https://app.ecobank.co.ke,https://internal.ecobank.co.ke
```

**Critical security rule (V-009):** Never use `*` in this list.
The combination of wildcard origin + `allow_credentials=True`
(which we require for JWT bearer tokens) is a known
vulnerability. The app raises `RuntimeError` at startup if it
detects `*`.

**Empty-value handling:** If `A2Z_CORS_ORIGINS` is set to an
empty string, the app falls back to the localhost dev defaults
and logs a warning. Don't ship empty in production.

**Default (when unset):** Includes localhost ports for React
Create-React-App (3000), Vite (5173), and Streamlit (8501,
8502). Useful for dev; insufficient for production.

### `A2Z_JWT_SECRET` (required in production)

HS256 signing key for JWT access tokens. The app's default
secret is intentionally weak so dev/test work without setup, but
`warn_if_default_secret()` logs at startup if it's still in use.

Generate a strong value:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Rotating this value invalidates all outstanding sessions —
useful for incident response.

### `A2Z_DB_BACKEND`

Master switch for JSON vs PostgreSQL storage. Set to
`postgresql` along with the PG connection vars
(`A2Z_PG_HOST`, etc.) to use the migrated tables. The G163
audit gate reports current PG migration progress.

### Other vars

See `.env.example` for the full list with comments. Notable
ones for production:

- `A2Z_FLEXCUBE_*` — Oracle FLEXCUBE connection (leave blank in
  dev to use the in-process simulator).
- `A2Z_LLM_PROVIDER`, `A2Z_LLM_API_KEY` — Cat D engine LLM
  integration. Optional; engines fall back to rule-based scorers
  when unset.
- `A2Z_LOG_LEVEL` — `INFO` is the production default.

---

## CORS configuration deep-dive

The CORS middleware lives in `utils/api.py` at module level.
Settings:

| Setting | Value | Why |
|---------|-------|-----|
| `allow_origins` | from `A2Z_CORS_ORIGINS` env var | Explicit list — never wildcard |
| `allow_credentials` | `True` | Required for JWT bearer headers |
| `allow_methods` | `GET, POST, PUT, DELETE, PATCH, OPTIONS` | Standard verb set + preflight |
| `allow_headers` | `Authorization, Content-Type, Accept, X-Requested-With` | Explicit list, includes JWT header |

The `OPTIONS` method is required for CORS preflight requests
that the browser sends before non-simple cross-origin requests
(any request with `Authorization`, `Content-Type: application/json`,
or non-GET/POST methods triggers preflight). Without OPTIONS in
the methods list, every authenticated React request would fail.

For each new frontend deploy environment:

1. Add its origin to `A2Z_CORS_ORIGINS`.
2. Restart the backend.
3. Verify in the browser DevTools Network tab that preflight
   responses come back with the right headers.

---

## JWT authentication

Tokens are HS256-signed using `A2Z_JWT_SECRET`. They carry
`{username, role, iat, exp}` in the payload. Default expiry is
8 hours; configurable in `utils/auth_jwt.py`.

The React frontend should:

1. POST credentials to `/api/auth/login` → receives `{token, user}`.
2. Store the token in memory (NOT localStorage — XSS risk).
3. Send `Authorization: Bearer <token>` on every API call.
4. On 401, prompt re-auth.

Server-side, every endpoint in `/api/cockpit/*` and other arcs
uses `Depends(get_current_user)` to validate the token.

---

## React frontend deployment

The React SPA build output (typically `dist/` or `build/`)
should be served by a separate process — nginx, Caddy, or any
static file server. It is **not** served by the FastAPI backend
in production (don't co-locate static and API serving in the
same process).

Typical layout:

```
production.example.com/      → React SPA  (nginx static)
api.production.example.com/  → FastAPI    (uvicorn)
```

The React app's `.env.production` should set:

```
REACT_APP_API_URL=https://api.production.example.com
```

(or `VITE_API_URL=...` if using Vite).

CORS connects them: include
`https://production.example.com` in `A2Z_CORS_ORIGINS` on the
backend.

---

## Running the backend

Development:

```bash
uvicorn utils.api:app --reload --host 0.0.0.0 --port 8000
```

Production:

```bash
uvicorn utils.api:app --host 0.0.0.0 --port 8000 --workers 4
```

Or behind gunicorn:

```bash
gunicorn utils.api:app -w 4 -k uvicorn.workers.UvicornWorker
```

---

## Running the Streamlit cockpit

The cockpit pages live in `pages/`. Start with:

```bash
streamlit run 0_home.py --server.port 8501
```

Streamlit reads the same JSON files and engine state as the API,
so the cockpit and React frontend show the same numbers when
backed by the same data directory.

---

## Database migration

PG migration is tracked by G163. Current state: 48/79 tables in
PG-mode (61%). To enable PG for a specific table:

1. Set `A2Z_DB_BACKEND=postgresql` and the connection vars.
2. Set the table's `TABLE_USE_DB` flag to `True` in
   `utils/db.py`.
3. Run the migration script for that table (in
   `scripts/migrations/`).

The dual-write pattern means tables can be flipped one-by-one
without service interruption.

---

## Observability

The platform writes structured audit logs via `audit_log()`
(see `utils/core_audit.py`). Every state change is recorded.

For production:

- Forward stdout/stderr to your log aggregator.
- The `audit_log()` function writes to `data/audit_log.json`
  by default; configure a database backend in production via
  `A2Z_AUDIT_BACKEND`.
- Health endpoint: `GET /api/cockpit/health` (requires JWT).

---

## Smoke tests after deploy

Run these in order after a deploy:

1. **Backend reachable:** `curl https://api.example.com/api/docs`
   should return the OpenAPI HTML.

2. **CORS configured:**

   ```bash
   curl -i -X OPTIONS https://api.example.com/api/cockpit/health \
     -H "Origin: https://app.example.com" \
     -H "Access-Control-Request-Method: GET"
   ```

   Response should include
   `Access-Control-Allow-Origin: https://app.example.com`.

3. **Auth working:** Login via `/api/auth/login`, then
   `GET /api/cockpit/health` with the token. Should return
   `{"status": "ok", "cockpit_read_api_version": "...", ...}`.

4. **Audit logs flowing:** Check `data/audit_log.json` or your
   audit backend for the login entry.

5. **Streamlit cockpit reachable:** Open the Streamlit URL in a
   browser; pages 109 and 110 should render.

---

## Rollback

The platform follows a tag-per-version pattern (`v10.NNN`). To
roll back:

1. Check out the previous tag in the deployment.
2. Restart the backend + Streamlit processes.
3. The G162 baseline and audit gates verify the rollback —
   `python scripts/audit.py` should report the prior version's
   score.

No database schema changes ship in cockpit/API arcs (Phase 3 is
read-side only so far), so rollback is purely a code revert.

---

## See also

- `STANDING_RULES_PHASE_3.md` — Phase 3 architectural rules
- `PHASE_3_BACKLOG.md` — known debt items
- `PHASE_3_PREFLIGHT_AUDIT.md` — last full structural audit
- `.env.example` — full env var reference
- `CHANGELOG_v10.297.md` — cockpit HTTP API arc
- `CHANGELOG_v10.298.md` — BSC/KPI integrity arc
- `CHANGELOG_v10.299.md` — this batch (CORS + deploy config)
