# A2Z Blueprint MIS 360 — API Contracts

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md` + `RBAC_MATRIX.md`)
**Status:** `transitional` (per v10.502 Stage C Arc D2 Batch 5c — 81 endpoints documented, 276 actual; G389 enforces ceiling)
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 2); reality-checked v10.502 Stage C Arc D2 Batch 5c
**Last updated:** 2026-06-10 (Batch 5c surgical corrections)
**Owner:** Platform / Security
**Authoritative source:** `utils/api.py` + 15 mounted routers (`utils/api_*.py`)
**Machine-readable equivalent:** `API_CONTRACTS.json`

---

## Purpose

This document is the canonical contract for every HTTP endpoint in A2Z. For each endpoint it declares:

- **Method + path** (the surface)
- **Auth posture** (`PUBLIC`, `AUTHENTICATED`, `ADMIN`, or specific role/capability)
- **Capability name** (per `RBAC_MATRIX.md`)
- **Required request shape** (path/query/body parameters)
- **Response shape** (200 OK)
- **Audit event** emitted (per `TELEMETRY_MAP.md`, Wave 4)
- **Idempotency** (safe to retry?)
- **Side effects** (state changes)

It is the source of truth for:
- Test suites (load tests, contract tests)
- React frontend API client (`frontend/web/src/lib/api.ts`)
- Streamlit pages calling `utils/api_client.py`
- External integrations (future)
- Audit gates (`gate_api_v1_coverage`, `G12 gate_api_auth_safety`, `gate_audit_coverage`)

---

## Doctrine

**API1 — Every endpoint declares auth.** Per Article V §5.1: every endpoint except `/api/health` MUST declare `Depends(get_current_user)`, `Depends(require_admin)`, or `Depends(require_role([...]))`. No exceptions.

**API2 — State changes emit audit events.** Per Article VIII §8.1: every state-changing operation MUST call `_audit()` with an event name of the form `API_<DOMAIN>_<ACTION>`. Read-only operations need not audit (per `gate_audit_coverage`).

**API3 — Destructive operations need RBAC, not just `confirm=true`.** Per `RBAC_MATRIX.md::RB5`: a `confirm: bool = False` query parameter is a safety measure, NOT an authorization mechanism. Destructive endpoints must declare `Depends(require_admin)` or stricter.

**API4 — Idempotency where possible.** GET is idempotent by HTTP convention. POST that audits should be at-least-once safe. Migration endpoints accept dry-run (the `confirm: bool = False` default) for safe rehearsal.

**API5 — Path versioning is permanent.** `/api/v1/*` is forever v1. New versions live at `/api/v2/*`. Breaking changes within a version are constitutional violations.

---

## Endpoint inventory (81 endpoints documented; 276 actual — TRANSITIONAL doctrine debt)

> **Doctrine debt declared v10.502 Stage C Arc D2 Batch 5c.** This document was authored against a 81-endpoint baseline at v10.498 Stage B Wave 2. Same-turn AST-walk of `utils/api*.py` in Batch 5c orientation revealed **276 actual endpoints** across 16 router files — primarily because v10.412 capacity_feedback, v10.413 cascade, and the v10.4xx api_cockpit/compliance/legal/product/strategy/telemetry/treasury router families landed during the Stage-C-paused period without being added to this contract.
>
> The endpoint tables below remain accurate for what they describe. The gap between documented and actual is enforced mechanically by G389 (`gate_api_contract_inventory`) which:
> - PASSES while `actual_total <= 300` (transitional ceiling — gives breathing room without admitting unbounded drift).
> - FAILS if the surface grows beyond 300, surfacing the worsening drift.
> - Always reports INFO-level counts and the first 5 undocumented endpoints in its summary so a future maintainer can begin closing the gap.
>
> **The substantive rewrite to document all 276 endpoints is deferred to a future arc.** Classification of this artifact is consequently **TRANSITIONAL**, not ACTIVE, until that rewrite completes.

### Convention

Each row below has columns:
- **Endpoint** — method + path
- **Cap** — capability name (per RBAC_MATRIX)
- **Auth** — Depends declaration target
- **Audit event** — event name emitted (or `—` if read-only)
- **Side effects** — what state changes
- **Status** — `canonical`, `transitional`, or specific notes

For brevity I group obvious patterns (e.g. all `bsc-audit/*` endpoints share an auth posture).

---

### Auth domain

| Endpoint | Cap | Auth | Audit event | Side effects | Status |
|---|---|---|---|---|---|
| `POST /api/auth/login` | `auth:login` | `PUBLIC` | `API_LOGIN_SUCCESS` / `API_LOGIN_FAILED` | mints JWT, returns in JSON `TokenResponse` body (Bearer-header only; no cookie set) | canonical *(corrected v10.502 Stage C Arc D2 Batch 5c — cookie path was rolled back; cross-ref GOVERNANCE_REALITY_INDEX Batch 3d React substrate correction)* |
| `GET /api/auth/me` | `auth:me` | `Depends(get_current_user)` | — | none | canonical |
| `POST /api/auth/logout` | `auth:logout` | `Depends(get_current_user)` | `API_LOGOUT_SUCCESS` | adds jti to blocklist (Bearer-header only; no cookie clearing) | canonical (v10.497 P1.3 cookie path superseded by v10.500 Phase 1 Batch 3a Bearer lifecycle) |
| `POST /api/auth/change-password` | `auth:change_password` | `Depends(get_current_user)` | `API_PASSWORD_CHANGED` | bcrypt-rehash + invalidates prior tokens via blocklist; rate-limited 5/min/token (Phase 2 Arc B G_rate_limit_auth); enforces `validate_password_policy` (Phase 2 Arc A) | canonical (v10.501 Phase 2 Arcs A+B) |
| `GET /api/auth/whoami-detailed` | `auth:whoami_detailed` | `Depends(get_current_user)` | — | none | canonical (v10.499 Stage C Batch 2b) — rate-limit exempt by design |
| `GET /api/health` | (none) | `PUBLIC` | — | none | canonical |
| `GET /api/branding` | (none) | `PUBLIC` | — | none | canonical (v10.495) |

---

### Core resource summaries

| Endpoint | Cap | Auth | Audit event | Side effects | Status |
|---|---|---|---|---|---|
| `GET /api/bsc/summary` | `bsc:read_summary` | `Depends(get_current_user)` | `API_BSC_SUMMARY` | none | canonical |
| `GET /api/bsc/staff/{username}` | `bsc:read_own` OR `bsc:read_subordinates` OR `bsc:read_all_staff` | `Depends(get_current_user)` + handler-level scope check | `API_BSC_STAFF` / `API_BSC_STAFF_DENIED` | none | canonical |
| `GET /api/pipeline/summary` | `pipeline:read_summary` | `Depends(get_current_user)` | `API_PIPELINE_SUMMARY` | none | canonical |
| `GET /api/pipeline/deals` | `pipeline:read_own_deals` OR `pipeline:read_all_deals` | `Depends(get_current_user)` + handler-level filter | `API_PIPELINE_DEALS` | none | canonical |
| `GET /api/credit/summary` | `credit:read_summary` | `Depends(get_current_user)` | `API_CREDIT_SUMMARY` | none | canonical |
| `GET /api/credit/watchlist` | `credit:read_watchlist` | `Depends(get_current_user)` + handler-level scope check | `API_CREDIT_WATCHLIST` | none | canonical |
| `GET /api/aml/summary` | `aml:read_summary` | `Depends(get_current_user)` + handler-level filter | `API_AML_SUMMARY` | none | canonical |
| `GET /api/users/summary` | `users:read_summary` | `Depends(get_current_user)` | `API_USERS_SUMMARY` | none | canonical |
| `GET /api/dashboard/md` | `dashboard:md` | `Depends(get_current_user)` + handler-level MD check | `API_DASHBOARD_MD` | none | canonical |

**Note on handler-level scope checks:** Endpoints like `/api/bsc/staff/{username}` declare only `Depends(get_current_user)` at the route level. The actual capability resolution (own / subordinates / all-staff) happens inside the handler by comparing the requested username to the caller's identity and walking the reporting hierarchy. Stage C OI-11 (`require_manager_of` Depends factory) will canonicalize this pattern.

---

### Cache and system

| Endpoint | Cap | Auth | Audit event | Side effects | Status |
|---|---|---|---|---|---|
| `POST /api/cache/clear` | `cache:clear` | `Depends(require_admin)` | `API_CACHE_CLEAR` | invalidates in-memory cache | canonical |
| `GET /api/cache/stats` | `cache:read_stats` | `Depends(get_current_user)` | `API_CACHE_STATS` | none | canonical |
| `GET /api/v1/vitals/full` | `vitals:read` | `Depends(get_current_user)` | — | none (long-running, ~30-60s) | canonical |
| `GET /api/v1/vitals/organs` | `vitals:read` | `Depends(get_current_user)` | — | none | canonical |
| `GET /api/v1/vitals/regression` | `vitals:read` | `Depends(get_current_user)` | — | none | canonical |

---

### Performance insights (v2 namespace)

| Endpoint | Cap | Auth | Audit event | Side effects | Status |
|---|---|---|---|---|---|
| `GET /api/v2/performance/insights/{staff_code}` | (own + subordinates filter) | `Depends(get_current_user)` + scope check | — | none | canonical |

---

### Integration / actuals

| Endpoint | Cap | Auth | Audit event | Side effects | Status |
|---|---|---|---|---|---|
| `GET /api/integration/rules` | `integration:read_rules` | `Depends(get_current_user)` | — | none | canonical |
| `GET /api/integration/actuals/{period}` | `integration:read_actuals` | `Depends(get_current_user)` + scope filter | — | none | canonical |
| `GET /api/integration/resolution-metrics` | `integration:read_metrics` | `Depends(get_current_user)` | — | none | canonical |
| `POST /api/integration/run-period` | `integration:run_period` | `Depends(get_current_user)` + `confirm: bool` | `API_INTEGRATION_RUN_PERIOD` | writes period actuals | **TRANSITIONAL** — should declare `Depends(require_admin)` |
| `GET /api/integration/coverage` | `integration:read_coverage` | `Depends(get_current_user)` | — | none | canonical |
| `GET /api/integration/rule-explain/{kpi_id}` | `integration:read_rule_explain` | `Depends(get_current_user)` | — | none | canonical |

---

### v1 admin governance — read endpoints (audit operations)

All 14 of these endpoints share this profile:

- **Auth:** `Depends(get_current_user)`
- **Audit event:** `—` (read-only operations)
- **Side effects:** none

| Endpoint | Cap | Target grant | Current grant |
|---|---|---|---|
| `GET /api/v1/role-weights/audit` | `role-weights:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/role-weights/{role}/audit` | `role-weights:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/role-weights/{role}/normalized` | `role-weights:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/kpi-dedup/audit` | `kpi-dedup:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/backup-retention/audit` | `backup-retention:audit` | `[ADMIN]` | `[ALL_AUTHENTICATED]` ⚠️ should tighten |
| `GET /api/v1/test-cleanup/audit` | `test-cleanup:audit` | `[ADMIN]` | `[ALL_AUTHENTICATED]` ⚠️ should tighten |
| `GET /api/v1/bsc-audit/full` | `bsc-audit:full` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-audit/staff-coverage` | `bsc-audit:staff-coverage` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-audit/kpi-completeness` | `bsc-audit:kpi-completeness` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-audit/pillar-canonical` | `bsc-audit:pillar-canonical` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-audit/weight-normalization` | `bsc-audit:weight-normalization` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-audit/library-alignment` | `bsc-audit:library-alignment` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-audit/cascade-linkage` | `bsc-audit:cascade-linkage` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-pillar/audit` | `bsc-pillar:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-library/audit` | `bsc-library:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-completeness/audit` | `bsc-completeness:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-weights/audit` | `bsc-weights:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/bsc-codes/audit` | `bsc-codes:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/admin-validation/library` | `admin-validation:library` | `[ADMIN]` | `[ALL_AUTHENTICATED]` ⚠️ should tighten |
| `GET /api/v1/cascade-360/audit` | `cascade-360:audit` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |
| `GET /api/v1/cascade-360/stage/{stage}` | `cascade-360:stage` | `[ALL_AUTHENTICATED]` | `[ALL_AUTHENTICATED]` ✓ |

---

### v1 admin governance — write endpoints (migrations and repairs)

**All marked `TRANSITIONAL`** — current state uses only `Depends(get_current_user)` + `confirm: bool = False` query param. Target state adds `Depends(require_admin)`.

| Endpoint | Cap | Target | Current | Audit event |
|---|---|---|---|---|
| `POST /api/v1/role-weights/migrate` | `role-weights:migrate` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_ROLE_WEIGHTS_MIGRATE` |
| `POST /api/v1/kpi-dedup/migrate` | `kpi-dedup:migrate` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_KPI_DEDUP_MIGRATE` |
| `POST /api/v1/backup-retention/apply` | `backup-retention:apply` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_BACKUP_RETENTION_APPLY` |
| `POST /api/v1/test-cleanup/archive` | `test-cleanup:archive` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_TEST_CLEANUP_ARCHIVE` |
| `POST /api/v1/bsc-pillar/migrate` | `bsc-pillar:migrate` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_BSC_PILLAR_MIGRATE` |
| `POST /api/v1/bsc-library/register` | `bsc-library:register` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_BSC_LIBRARY_REGISTER` |
| `POST /api/v1/bsc-completeness/repair` | `bsc-completeness:repair` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_BSC_COMPLETENESS_REPAIR` |
| `POST /api/v1/bsc-weights/renormalize` | `bsc-weights:renormalize` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_BSC_WEIGHTS_RENORMALIZE` |
| `POST /api/v1/bsc-codes/fix` | `bsc-codes:fix` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_BSC_CODES_FIX` |
| `POST /api/v1/admin-validation/legacy-aliases` | `admin-validation:legacy-aliases` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_ADMIN_VALIDATION_LEGACY_ALIASES` |
| `POST /api/v1/harmonize/all` | `harmonize:all` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_HARMONIZE_ALL` |
| `POST /api/v1/harmonize/stage/{stage}` | `harmonize:stage` | `[ADMIN]` | `Depends(get_current_user)` + confirm | `API_HARMONIZE_STAGE` |

**Tracked as OI-2.** Migration to `Depends(require_admin)` planned for next governance batch following Wave 6 sign-off.

---

### v1 HR — read endpoints

All `Depends(get_current_user)` + handler-level scope:

| Endpoint | Cap | Scope filter | Audit |
|---|---|---|---|
| `GET /api/v1/onboarding/audit` | `onboarding:audit` | Head+ in HR SBU OR ADMIN | — |
| `GET /api/v1/onboarding/audit/{staff_code}` | `onboarding:audit_staff` | Manager of subordinate OR Head+ | — |
| `GET /api/v1/exit-risk/audit` | `exit-risk:audit` | Head+ in HR SBU OR ADMIN | — |
| `GET /api/v1/exit-risk/audit/{staff_code}` | `exit-risk:audit_staff` | Manager OR Head+ | — |
| `GET /api/v1/exit-risk/simulate/{staff_code}` | `exit-risk:simulate_staff` | Manager OR Head+ in HR SBU | — |
| `GET /api/v1/hr-audit/full` | `hr-audit:full` | Head+ in HR SBU OR ADMIN | — |
| `GET /api/v1/hr-audit/dimension/{dimension}` | `hr-audit:dimension` | Head+ in HR SBU | — |
| `GET /api/v1/peer-learning/cards/{staff_code}` | `peer-learning:cards` | Own or subordinates | — |
| `GET /api/v1/peer-learning/match-skill` | `peer-learning:match_skill` | [ALL_AUTHENTICATED] | — |
| `GET /api/v1/coaching/script` | `coaching:script` | Manager of staff_code | — |
| `GET /api/v1/predict/{staff_code}` | `predict:achievement` | Own or subordinates | — |
| `GET /api/v1/gamification/badges/{staff_code}` | `gamification:badges` | Own or subordinates | — |
| `GET /api/v1/gamification/leaderboard` | `gamification:leaderboard` | Relevant scope | — |
| `GET /api/v1/efficiency/{staff_code}` | `efficiency:read` | Own or subordinates | — |
| `GET /api/v1/wellness/{staff_code}` | `wellness:read` | Manager OR ADMIN OR subject self | — |
| `GET /api/v1/wellness/alerts/{manager_code}` | `wellness:alerts` | manager_code must equal caller's staff_code | — |
| `GET /api/v1/hr-actuals/staff/{staff_code}` | `hr-actuals:staff` | Own or subordinates | — |
| `GET /api/v1/hr-actuals/bank-wide/{kpi_id_or_name}` | `hr-actuals:bank_wide` | Head+ in HR SBU OR ADMIN | — |
| `GET /api/v1/hr-actuals/coverage` | `hr-actuals:coverage` | [ALL_AUTHENTICATED] | — |

---

### v1 HR — write endpoints (state-changing)

| Endpoint | Cap | Auth | Audit event | Status |
|---|---|---|---|---|
| `POST /api/v1/onboarding/simulate` | `onboarding:simulate` | **OI-7: UNCLEAR** | `API_ONBOARDING_SIMULATE` (expected) | **VERIFY** — extracted signature lacks `Depends(get_current_user)`; almost certainly extraction artifact, must confirm |
| `POST /api/v1/peer-learning/generate-cards` | `peer-learning:generate_cards` | **OI-7: UNCLEAR** | `API_PEER_LEARNING_GENERATE` (expected) | **VERIFY** — same as above |
| `POST /api/v1/gamification/evaluate/{staff_code}` | `gamification:evaluate` | `Depends(get_current_user)` | `API_GAMIFICATION_EVALUATE` | canonical |

---

### Mounted routers (sub-API surfaces)

These routers are imported and mounted by `utils/api.py` in the startup block:

| Router | Mount point | Source | Status |
|---|---|---|---|
| Cascade | `/api/v1/cascade/*` | `utils/api_cascade.py` | canonical (v10.413) |
| Capacity feedback | `/api/cascade/capacity-feedback` | `utils/api_capacity_feedback.py` | canonical (v10.413) |
| Branding | `/api/branding` | `utils/api_branding.py` | canonical (v10.495) |
| Cockpit | (TBD) | `utils/api_cockpit.py` | Listed in utils_inventory; not mounted in extracted startup |
| Compliance | (TBD) | `utils/api_compliance.py` | Listed; not yet surfaced |
| Legal | (TBD) | `utils/api_legal.py` | Listed; not yet surfaced |
| Telemetry | (TBD) | `utils/api_telemetry.py` | Listed; not yet surfaced |
| Treasury | (TBD) | `utils/api_treasury.py` | Listed; not yet surfaced |
| Strategy | (TBD) | `utils/api_strategy.py` | Listed; not yet surfaced |
| Product | (TBD) | `utils/api_product.py` | Listed; not yet surfaced |
| Resource optimization | (TBD) | `utils/api_resource_optimization.py` | Listed; not yet surfaced |
| CRUD | (TBD) | `utils/api_crud.py` | Listed; not yet surfaced |
| Gateway developer portal | (TBD) | `utils/api_gateway_developer_portal.py` | Listed; not yet surfaced |

**Note:** The "not yet surfaced" routers exist as files but aren't visible in the extracted `api_endpoints.txt`. Either they're mounted with conditional `try/except` blocks that didn't show in the extract, or they're not currently mounted. Wave 3 ORGANS_REGISTRY will resolve.

---


### Pipeline domain (12 endpoints; Arc α α1–α7, v10.502–v10.509)

Endpoints expose `PipelineManager` (`utils/core.py`) to React. All require Bearer JWT auth. All filter by cascade scope via `get_visible_staff_codes` (`utils/api_pipeline_scope.py`). Mutating endpoints emit audit events via the canonical `_audit(...)` wrapper (`utils/api.py:312`) per T2 doctrine.

**Pattern note:** Pipeline uses an attempt/outcome dual-emit pattern. Every mutation emits an `API_PIPELINE_X_ATTEMPT` event first (the gate event) and one of `API_PIPELINE_X_REJECTED` / `_FORBIDDEN` / business-success-event (e.g. `DEAL_ADDED`). The dual emission allows audit dashboards to reconstruct intent-vs-outcome separately.

**Read endpoints (5):**

| Verb | Path | Audit (success) | Auth gate |
|---|---|---|---|
| GET | `/api/pipeline/summary` | `API_PIPELINE_SUMMARY` | In scope (returns aggregate) |
| GET | `/api/pipeline/deals?stage=X&unit=Y&limit=N` | `API_PIPELINE_DEALS` | In scope, query filters applied post-scope |
| GET | `/api/pipeline/deals/{deal_id}` | `API_PIPELINE_DEAL_DETAIL` | In scope + per-deal permissions object returned |
| GET | `/api/pipeline/queues/validation` | `API_PIPELINE_QUEUE_VALIDATION` (success) / `API_PIPELINE_QUEUE_FORBIDDEN` (denied) | Manager-tier |
| GET | `/api/pipeline/queues/cancellation` | `API_PIPELINE_QUEUE_CANCELLATION` (success) / `API_PIPELINE_QUEUE_FORBIDDEN` (denied) | Manager-tier |

**Write endpoints (7):**

| Verb | Path | Audit events emitted | Auth gate |
|---|---|---|---|
| POST | `/api/pipeline/deals` (201) | `API_PIPELINE_CREATE_ATTEMPT` + `DEAL_ADDED` (success) or `API_PIPELINE_CREATE_REJECTED` (validation failure) | In scope + α5 conflict-resolution semantics |
| POST | `/api/pipeline/deals/refer` (201) | `API_PIPELINE_REFER_ATTEMPT` + `DEAL_REFERRED` (success) or `API_PIPELINE_REFER_REJECTED` | In scope; portfolio owner becomes target |
| PUT | `/api/pipeline/deals/{deal_id}` | `API_PIPELINE_UPDATE_ATTEMPT` + `DEAL_UPDATED` (success) or `API_PIPELINE_UPDATE_FORBIDDEN` (no permission) | Owner or manager-in-scope |
| POST | `/api/pipeline/deals/{deal_id}/advance` | `API_PIPELINE_ADVANCE_ATTEMPT` + `API_PIPELINE_ADVANCED` (success) or `API_PIPELINE_ADVANCE_REJECTED` / `API_PIPELINE_ADVANCE_FORBIDDEN`. On Won→LMS handoff also emits `LMS_APPLICATION_CREATED`; if LMS create fails: `API_PIPELINE_ADVANCE_LMS_FAILED` | Owner or manager-in-scope |
| POST | `/api/pipeline/deals/{deal_id}/validate` | `API_PIPELINE_VALIDATE_ATTEMPT` + `DEAL_VALIDATED` (approved) or `DEAL_QUERIED` (needs info) or `API_PIPELINE_VALIDATE_FORBIDDEN` | Manager-tier |
| POST | `/api/pipeline/deals/{deal_id}/cancel/request` | `API_PIPELINE_CANCEL_REQUEST_ATTEMPT` + `CANCEL_REQUESTED` (success) or `API_PIPELINE_CANCEL_REQUEST_REJECTED` / `API_PIPELINE_CANCEL_REQUEST_FORBIDDEN` | Owner only (the RM requests; manager approves) |
| POST | `/api/pipeline/deals/{deal_id}/cancel/approve` | `API_PIPELINE_CANCEL_APPROVE_ATTEMPT` + `CANCEL_APPROVED` (approve) or `CANCEL_REJECTED` (reject the cancel request) or `API_PIPELINE_CANCEL_APPROVE_FORBIDDEN` | Manager-tier |

**Domain audit detail:** Cross-references `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Sections 1–17 for the full doctrine (cascade walk semantics, α5 conflict-resolution model, validation-queue mechanics, BSC credit attribution).

---

### LMS domain (5 endpoints; α8, v10.515)

Endpoints expose `LoanApplicationManager` (`utils/core.py:5267`) to React. **Mounted via `APIRouter`** (`utils/api_lms_routes.py`) rather than `@app.method` decorators directly in `api.py` — first use of APIRouter pattern in this codebase. All require Bearer JWT auth.

**Audit emission note — T2 canonical-emitter gap:** These routes call `utils.core_audit.audit_log(...)` directly rather than the `_audit(...)` wrapper at `utils/api.py:312`. See `TELEMETRY_MAP.md` candidate GAP-018 for the T2 discipline issue this creates and resolution paths.

| Verb | Path | Audit | Auth gate |
|---|---|---|---|
| GET | `/api/lms/applications` | (no audit — read-only) | Cascade scope + analyst override (caller's staff_code matches `analyst.code` overrides cascade) |
| GET | `/api/lms/applications/{app_id}` | (no audit — read-only) | Per-app permissions object returned (`can_view`, `can_update`, `can_assign`, `can_record_decision`) |
| POST | `/api/lms/applications/{app_id}/assign` | `LMS_ANALYST_ASSIGNED` (detail: `{app_id}\|{analyst_code}`) | Manager-tier, status must be `submitted` |
| PUT | `/api/lms/applications/{app_id}` | `LMS_APPLICATION_UPDATED` (detail: `{app_id}`) | Owner / assigned analyst / manager-in-scope, status must be `submitted` or `assigned` |
| POST | `/api/lms/applications/{app_id}/decision` | `LMS_DECISION_APPROVED` / `LMS_DECISION_DECLINED` / `LMS_DECISION_RETURNED` (detail: `{app_id}\|{authority}`) | Manager-tier, status must be `submitted` or `assigned` |

**Domain audit detail:** Cross-references `PIPELINE_DOMAIN_AUDIT.md` Section 18 (α8 batch specification, scope exclusions, enum-vs-data discrepancy as candidate GAP-017).

---

### Credit Admin domain (4 endpoints; α9, v10.518)

Endpoints expose `CreditAdminManager` (`utils/core.py`) to React. **Mounted via `APIRouter`** (`utils/api_credit_admin_routes.py`) — second use of the pattern after α8. All require Bearer JWT auth.

**Same T2 gap as LMS** — uses `audit_log()` directly. See GAP-018.

| Verb | Path | Audit | Auth gate |
|---|---|---|---|
| GET | `/api/credit-admin/cases` | (no audit) | Cascade scope by `rm_code` (no analyst-override; see Section 19.5) |
| GET | `/api/credit-admin/cases/{case_id}` | (no audit) | Per-case permissions object (`can_view`, `can_fulfill_condition`, `can_disburse`) |
| POST | `/api/credit-admin/cases/{case_id}/conditions/fulfill` | `CREDIT_ADMIN_CONDITION_FULFILLED` (detail: `{case_id}\|{condition_type}\|{officer_name}`) | Anyone in scope, case not disbursed |
| POST | `/api/credit-admin/cases/{case_id}/disburse` | `CREDIT_ADMIN_DISBURSED` (detail: `{case_id}\|{authority}`) | Manager-tier, all_conditions_met required, case not already disbursed |

**Domain audit detail:** Cross-references `PIPELINE_DOMAIN_AUDIT.md` Section 19 (α9 batch specification, deliberate scope exclusions including no `disbursed=True` setter — that's a finance-system handoff).

**Arc α surface summary:** 21 endpoints (Pipeline 12 + LMS 5 + Credit Admin 4) across three loan-origination domains. Same auth model (cascade scope + tier check + state guardrails). Same response shape (`{detail, application/deal/case, permissions, status}`). Same audit detail format (`{entity_id}|{additional_keys}`). The contract uniformity means React frontend batches consuming these APIs (β5 LMS UI, β6 Credit Admin UI, post-β5) can use near-identical code patterns.

## Resolution of OI-7

The two routes flagged in survey require code-level verification. Joshua should run:

```
findstr /n "def onboarding_simulate_endpoint\|def peer_learning_generate_endpoint" utils\api.py
```

Then view ~10 lines around each match. The expected output shows the full signature including `, user: dict = Depends(get_current_user)` continuation. If that's confirmed:

- OI-7 is closed (extraction artifact, false alarm)
- Both routes get `canonical` status in this document

If `Depends(get_current_user)` is genuinely missing:

- This is a **CRITICAL** G12 violation
- Must be fixed in a hot-fix commit before this governance batch merges
- Stage C gate `gate_api_auth_safety` (G12) would already flag this in CI; the fact that the gate is reported passing (1153/1153) suggests the auth IS there and the extract truncated it

**Default assumption pending verification: extraction artifact.** This document treats both routes as `canonical` with `OI-7 verify` annotation, will be promoted to `canonical` unmarked once Joshua confirms.

---

## API contract version

Current contract version: **v10.497-API-1**

A breaking change to any endpoint shape requires:
1. New endpoint at `/api/v2/...` path
2. Old endpoint marked `deprecated` in this document with `superseded_by` pointer
3. Deprecation cycle: 3 batches grace before removal
4. CHANGELOG entry per `CHANGELOG_MASTER.md` (Wave 6)

The 80 v1 endpoints catalogued here are the **canonical v1 surface**. Adding endpoints inside `/api/v1/*` is permitted; breaking changes to existing v1 endpoints is a constitutional violation.

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-2 | 53 v1 admin endpoint migration to `Depends(require_admin)` | Implementation in next governance batch |
| OI-7 | Verify `/onboarding/simulate` + `/peer-learning/generate-cards` auth state | Immediate (Joshua grep verification) |
| OI-14 | Mount status of api_cockpit, api_compliance, api_legal, api_telemetry, api_treasury, api_strategy, api_product, api_resource_optimization, api_crud, api_gateway_developer_portal routers | Wave 3 ORGANS_REGISTRY |
| OI-15 | Full audit event vocabulary documentation | Wave 4 TELEMETRY_MAP |

---

**End of API_CONTRACTS.md**
