# SESSION_BOOTSTRAP.md

**Purpose:** orient a fresh Claude (or human collaborator) on A2Z Blueprint
in under 5 minutes. This file is the entry point — it does NOT duplicate
canonical artifacts; it points to them.

**Maintenance rule:** update this file at the end of each batch, alongside
the per-batch CHANGELOG. If you ship code without updating this file, the
next session will eat rediscovery tax. This is now mechanically enforced
by audit gate G388 (planned for Phase 2 Stage C resumption).

---

## A2Z in 3 lines

A2Z Blueprint is an enterprise banking MIS configurable to any bank (Ecobank
Kenya is the prospect tenant): 700K simulated customers, 35 branches, 487
staff, KES 11.5T simulated deposits. ~726,896 Python LOC (Streamlit + FastAPI)
+ ~2,500 TypeScript LOC (React frontend with 8 bespoke v10.496 primitives,
Phase 1 auth substrate post-v10.500). 171 Streamlit pages. Constitutional
governance layer with 32 artifacts (16 .md + 16 .json pairs) in
`docs/architecture/` plus operational protocol added in Batch 3d. Mechanical
audit suite at 418 gates in `scripts/audit.py`. The system is in active
development across multiple concurrent arcs.

---

## Current certified state

**Last commit on main:** `5c34117` (2026-06-29 — auth-store read-only `_load`; enrichment scope race closed)

**Latest arc — PostgreSQL concurrency + auth hardening (2026-06-29, pushed to origin/main):** Two concurrency P0s closed, each gated by a committed RED→GREEN probe + `simulate_credit_chain.py` 295/295. (1) Credit Admin money-path: `88820eb` CA-1 PG mirror → `cbc983d` CA-2 PG-authoritative reads + row-locked RMW + save()-hook → `7ca9e35` CA-3 troops disbursement serialized (double-disburse probe 10/10→1/N). (2) `5c34117` auth-store: `UserManager._load` made read-only — removed the per-request `users.json` rewrite whose `os.replace` collisions (Windows `WinError 5`) were swallowed by `_enrich`'s bare `except`, causing spurious 403/404 on users' own resources under load (R/U/L probe ~50%→0/N). Standing probes: `scripts/stress_credit_admin.py`, `scripts/stress_auth_scope.py`. Full detail in REVIVAL_LEDGER (2026-06-29 entries). NOTE: the Stage C / Arc-D block below predates this arc and was not refreshed during it.

**Phase 1 closure commit:** `f268330` (v10.500 Phase 1 Batch 3d — doctrine refresh)
**Last shipped batch:** v10.501 Phase 2 Arc A Batch 4a — 2026-06-10 (password policy hardening)
**Phase 1 status:** **CLOSED** — 10/10 gates green
**Phase 2 status:** **CLOSED** (pushed to origin/main at `535b477`). All three arcs complete.
**Stage C status:** Arc D RESUMED. Arc D1 doctrine baseline alignment (Batch 5a) is the current focus. See Active Workstreams below.
**Governance doctrine in force:** CGR1 (reality-grounding) + Trap #11 (no fabrication) + Trap #12 (no paste cascade) + Trap #14 (no path-colliding extractions) + single-worker FastAPI constraint (Batch 4b) + intentionally-tracked credential data discipline (Batch 4c) — all active
**Gate count:** 394 total. G388-G393 authored across Stage C Arc D2. G388 closes CANONICAL_TRUTH_REGISTRY D4 (Batch 5b); G389 surveils API_CONTRACTS inventory drift in TRANSITIONAL mode + G390 enforces DATA_DICTIONARY tracking claims (Batch 5c); G391 enforces CANONICAL_DEPENDENCY_MAP D5 cycles + G392 enforces TELEMETRY_MAP T1+T2 event-naming discipline (Batch 5d); G393 surveils ORGANS_REGISTRY O5 coverage in TRANSITIONAL mode (Batch 5e). Arc D2 mechanically complete: 8 of 8 provisional artifacts reality-checked.
**Stage C commits (newest first):**
- `[pending]` v10.502 Stage C Arc D2 Batch 5e — ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE reality-checked; G393 `gate_organs_registry_coverage` authored (TRANSITIONAL, 70% coverage); ORGANS_REGISTRY classified TRANSITIONAL with corrected inventory numbers (290→369 claimed, 237→158 unclaimed); DIGITAL_TWIN + RESILIENCE drop "(provisional)" qualifier, stay TRANSITIONAL; **Arc D2 mechanically complete (8/8 artifacts)**; 9/9 new gate tests green
- `[pending]` v10.502 Stage C Arc D2 Batch 5d — CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP reality-checked; G391 + G392 authored; both artifacts classified ACTIVE; 17/17 new gate tests green
- `6085eda` v10.502 Stage C Arc D2 Batch 5c — API_CONTRACTS + DATA_DICTIONARY reality-checked; G389 + G390 authored; API_CONTRACTS TRANSITIONAL; DATA_DICTIONARY ACTIVE; 16/16 new gate tests green
- `[5b]` v10.502 Stage C Arc D2 Batch 5b — CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY reality-checked; G388 authored; 11/11 new gate tests green
- `72b1f1f` v10.502 Stage C Arc D1 Batch 5a — doctrine baseline alignment

**Phase 2 commits (newest first):**
- `535b477` v10.501 Phase 2 Arc C Batch 4c — `.gitignore` doctrine fix + OPERATIONAL_PROTOCOL section + httpx dev-dep bundle (closes GAP-002; PHASE 2 CLOSED)
- `97fb635` v10.501 Phase 2 Arc B Batch 4b — slowapi rate limiting on login + change-password (closes GAP-006); single-worker FastAPI operational constraint codified
- `e542acd` v10.501 Phase 2 Arc A Batch 4a — password policy helper + Streamlit `current_password` parity (closes GAP-001 + GAP-005)

**Phase 1 commits (newest first):**
- `92c2e0a` v10.500 Batch 3d follow-up — gitignore runtime audit files
- `f268330` v10.500 Phase 1 Batch 3d — doctrine refresh, observability regression test, OPERATIONAL_PROTOCOL.md, POLICY_GAPS.md (Phase 1 closed at 10/10 gates)
- `216171d` v10.500 Phase 1 Batch 3c — bcrypt envelope migration + verify_pw multi-path + auto-upgrade instrumentation (1437 SHA-256 → envelope-wrapped)
- `2aab56b` v10.500 Phase 1 Batch 3b — FastAPI must_change_password enforcement via must_rotate JWT scope + core.py hash_pw hotfix
- `13d5258` v10.500 Phase 1 Batch 3a — Real AuthProvider + login lifecycle (replaces v10.495 stub)

For full ledger: `docs/architecture/REVIVAL_LEDGER.md` (newest entry on top)
For Phase 1 closure record: `docs/CHANGELOG_v10500_batch3d.md`
For Phase 2 Arc A closure record: `docs/CHANGELOG_v10501_batch4a.md`
For operational discipline: `docs/architecture/OPERATIONAL_PROTOCOL.md` (introduced Batch 3d)

---

## Current architectural reality (CGR1-grounded)

These statements describe runtime as of commit `92c2e0a` + Batch 4a working tree:

- **Governance Stage C is paused at the start of Phase 2.** Stage B
  (32 constitutional artifacts) shipped. Stage C wired ~5/35 gates
  through Batch 2e (commit `f3187dc`) before Phase 1 React substrate
  work began. Stage C resumes after Phase 2 planning lands.
- **React substrate Phase 1 is complete.** Auth lifecycle fully wired
  end-to-end: real AuthProvider (Batch 3a), must_change_password
  rotation gate with `must_rotate` JWT scope (Batch 3b), envelope-based
  bcrypt migration for 1437 dormant SHA-256 records (Batch 3c), and
  doctrine refresh + observability regression test (Batch 3d).
- **JWT bearer auth ACTIVE (not cookies).** `utils/auth_jwt.py` has
  `create_access_token`, `decode_token`, `get_current_user`,
  `require_admin`, `require_role(roles)` factory (Stage C Batch 2b),
  `get_current_user_allow_rotation` (Batch 3b). Token scopes "full"
  (default, omitted from payload for backward-compat) vs "must_rotate"
  (only `/api/auth/change-password` accepts). CSRF is N/A (Bearer header,
  not cookies). Refresh tokens NOT supported by design (re-login on
  expiry, 30-min lifetime).
- **React migration in progress, Streamlit operational.** Both transports
  coexist. Frontend at `frontend/web/src/` (Vite + React + TS + Tailwind):
  8 bespoke primitives in `components/`, 5 pages including Login and
  ChangePassword (Batch 3a/3b), 3 providers (Auth, Role, Branding),
  hooks for useAuth + useRole + useBranding, lib + types. 171 Streamlit
  pages in `pages/*.py`. Migration is TRANSITIONAL.
- **bcrypt envelope verify path ACTIVE.** `UserManager.verify_pw` (post-
  Batch-3c) tries direct-bcrypt, envelope-bcrypt, then legacy SHA-256
  in order. Envelope is a TRANSITIONAL stabilization layer per CGR1 —
  not canonical end-state. Phase 2 may add forced normalization,
  Argon2 migration, etc. Observability: INFO log "Envelope-backed
  credential authenticated" fires on envelope success (Phase 2 will
  use this signal to plan envelope retirement). Regression test:
  `tests/test_verify_pw_observability.py` (5 tests, all passing).
- **Virtual bank certified for Olympic simulation drills (G373).**
- **PostgreSQL migration TRANSITIONAL.** 27/52 tables migrated per G163
  baseline ratchet; remaining 25 tables still JSON-backed.
- **mlops_model_registry exists but 11 production AI engines do NOT yet
  load through it.** AI_GOVERNANCE AI1 doctrine ACTIVE; implementation
  TRANSITIONAL (Stage C Batch 2-3 work, paused).

When in doubt about whether something is ACTIVE or ASPIRATIONAL, consult
`docs/architecture/GOVERNANCE_REALITY_INDEX.md`.

---

## Active workstreams

1. **Stage C Arc D — Doctrine baseline + reality-classification (active focus).**
   Resumed v10.502 after Phase 2 closure. Sub-arc structure:
   - **Arc D1 — Doctrine baseline alignment.** CLOSED (Batch 5a, commit `72b1f1f`). GOVERNANCE_REALITY_INDEX restructure + 4 CGR1 corrections recorded (gate count drift; G10463 cluster pathology; ledger drift; Stage C scope overcount).
   - **Arc D2 — Reality-check the 8 provisional artifacts. MECHANICALLY COMPLETE.**
     - 5b CLOSED — CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY; G388.
     - 5c CLOSED `6085eda` — API_CONTRACTS + DATA_DICTIONARY; G389 (TRANSITIONAL) + G390.
     - 5d CLOSED `[pending]` — CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP; G391 + G392.
     - 5e CLOSED `[pending]` — ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE; G393 (TRANSITIONAL).
     - Zero "(provisional)" qualifiers remain in classification table. Future arcs may tighten TRANSITIONAL artifacts toward ACTIVE.
   - **Arc D3 — Optional ledger backfill (v10.380-v10.413 + v10.463).** Pending operator decision.
   - **Arc D phase boundary push** consolidates 5a-5e (and any 5f) commits to origin/main.
   - **Arc D3 — Ledger backfill (optional).** ~75 v10.380-v10.413 + v10.463 gates exist with no ledger entries. 1 batch (5f). Decide at end of D2 whether to backfill or accept gap.

2. **PostgreSQL migration (incremental).** 27/52 tables migrated. G163 ratchet enforces no regression.

3. **mlops_model_registry adoption (incremental).** 11 engines pending registration per G386.

4. **Post-Phase-2 hygiene candidates (optional, non-gating).**
   - `@app.on_event("startup")` → lifespan handler migration (`utils/api.py:258`). FastAPI emits deprecation warnings.
   - GAP-007 `_APP_VERSION` stamp policy formalisation. De facto applied in 4a/4b/4c/5a.
   - Two `docs/` untracked items (`KPA Pin.pdf`, `architecture/survey_inputs/`).
   - G10463 cluster cleanup (Finding 2 in Batch 5a CGR1 correction) — 21 gates collapse to 7 OR genuine differentiation.

---

## Key file paths

**Repo root:** `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\` (operator) /
`/home/claude/a2z/` (Claude sandbox clone).

**Frontend auth substrate:** `frontend/web/src/`
- `providers/AuthProvider.tsx` — JWT lifecycle, login/logout/changePassword,
  must_rotate handling, 3 storage keys: `a2z_token`,
  `a2z_token_expires_at`, `a2z_must_rotate`
- `providers/RoleProvider.tsx` — identity/role hydration via
  `/api/auth/whoami-detailed` (fires only on `status === 'authenticated'`)
- `components/ProtectedRoute.tsx` — path-aware must_rotate gate
- `pages/Login.tsx`, `pages/ChangePassword.tsx`, `pages/Dashboard.tsx`,
  `pages/Perform.tsx`, `pages/Profitability.tsx`, `pages/Showcase.tsx`
- `hooks/useAuth.ts`, `hooks/useRole.ts`, `hooks/useBranding.ts`
- `lib/api.ts` — centralized Authorization-header injection,
  `setCurrentToken`, `setOn401Callback`
- `types/auth.ts`, `types/role.ts`

**Backend auth:** `utils/auth_jwt.py`, `utils/api.py:276-468` (auth routes),
`utils/core.py:5743-5852` (UserManager auth helpers).

**Migration tooling:** `scripts/verify_bcrypt.py` (audit + envelope upgrade
with timestamped backup per OPERATIONAL_PROTOCOL.md backup-before-mutation
discipline).

**Tests:** `tests/test_verify_pw_observability.py` (envelope INFO log
regression; 5 tests).

**Doctrine:** `docs/architecture/` (32 constitutional artifacts + 2 added
in Batch 3d), `docs/continuity/SESSION_BOOTSTRAP.md` (this file),
`docs/CHANGELOG_v*` (per-batch records).

---

## Phase 1 closure gates (10/10 green)

| Gate | Status | Closed by |
|---|---|---|
| 1. Real user opens app | ✅ | Batch 3a (`13d5258`) |
| 2. Redirect to /login | ✅ | Batch 3a |
| 3. Authenticate | ✅ | Batch 3a |
| 4. Receive token | ✅ | Batch 3a |
| 5. Refresh page, stay authenticated | ✅ | Batch 3a |
| 6. Access protected routes | ✅ | Batch 3a |
| 7. Logout cleanly | ✅ | Batch 3a |
| 8. Dormant SHA-256 migration path | ✅ | Batch 3c |
| 9. `must_change_password` consistent Streamlit + FastAPI | ✅ | Batch 3b (`2aab56b`) |
| 10. Doctrine artifacts refreshed | ✅ | Batch 3d (`216171d`) |

---

## Operational protocol (codified Batch 3d)

See `docs/architecture/OPERATIONAL_PROTOCOL.md` for full doctrine. Key rules:

- **Trap #11 — No fabrication.** Every claim about file contents grounded
  in same-turn code inspection.
- **Trap #12 — No paste cascade.** Multi-file deliveries use ZIP, not
  inline prose dumps.
- **Trap #14 — No path-colliding extractions.** ZIP payloads use
  namespaced staging folders (e.g. `_batch3c_payload/`) that cannot
  share directory names with the destination tree. Codified after the
  Batch 3b `utils/` directory deletion false-alarm.
- **CGR1 — Reality grounds doctrine.** Documents describe runtime, not
  aspiration. Drift between doctrine and runtime is recorded in
  `GOVERNANCE_REALITY_INDEX.md`.
- **Backup-before-mutation.** Any script that writes to credential data
  (e.g. `data/users.json`) MUST create a timestamped backup first.
  Pattern: `<file>.pre_<operation>_YYYYMMDD_HHMMSS`. Backups are gitignored.

---

## Known doctrine gaps (Phase 2 candidates)

Recorded in `docs/architecture/POLICY_GAPS.md`. Phase 2 closure
status:

1. ~~**Stated-vs-enforced password policy.**~~ **CLOSED** in v10.501
   Batch 4a. `validate_password_policy(pw)` in `utils/core.py` is the
   single source of truth.
2. ~~**No rate limiting on auth endpoints.**~~ **CLOSED** in v10.501
   Batch 4b. slowapi mounted on FastAPI: per-IP 10/min on login,
   per-token 5/min on change-password, whoami-detailed unlimited.
3. ~~**Streamlit force_change_pw lacks current_password verify.**~~
   **CLOSED** in v10.501 Batch 4a alongside GAP-001.
4. ~~**`data/users.json` tracked-but-gitignored inconsistency.**~~
   **CLOSED** in v10.501 Batch 4c via Path (B) accept-and-document.
   `.gitignore` comment rewritten; OPERATIONAL_PROTOCOL section added.
5. **Envelope retirement.** DEFERRED. Trigger: when the
   "Envelope-backed credential authenticated" INFO log stops
   appearing in production logs for ≥30 days. Phase 2 did not move
   the needle here.
6. **Auto-upgrade re-hash on envelope success.** DEFERRED. Envelope
   hashes remain envelope-wrapped indefinitely. A future hardening
   arc could add observable staged normalization.
7. **`_APP_VERSION` stamp policy.** OPEN. De facto applied in
   Phase 2 (bumped per batch in 4a/4b/4c). Formalisation as either
   audit-gate-enforced doctrine or formal-informational is a small
   hygiene candidate; not gating any other work.

---

## How to resume in a fresh session

Paste this into a new Claude chat:

> Continuing A2Z v10.502 Stage C Arc D. Last pushed commit: `535b477`
> (Phase 2 Arc C Batch 4c — Phase 2 closed). Stage C Arc D1 (doctrine
> baseline alignment) Batch 5a is in working tree pending commit. Phase
> 1 complete: 10/10 gates. Phase 2 complete: 4 gaps closed.
> Stage C Arc D2 (reality-check 8 provisional artifacts) is the next
> focus across 4 paired batches (5b-5e). Read
> `docs/continuity/SESSION_BOOTSTRAP.md` for current state.

That plus `userMemories` gives Claude full context immediately.
