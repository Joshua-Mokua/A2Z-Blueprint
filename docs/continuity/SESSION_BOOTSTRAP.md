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

**Last commit on main:** `216171d` (v10.500 Phase 1 Batch 3d — doctrine refresh)
**Last shipped batch:** v10.500 Phase 1 Batch 3d — 2026-05-26
**Phase 1 status:** **CLOSED** — 10/10 gates green
**Governance doctrine in force:** CGR1 (reality-grounding) + Trap #11 (no fabrication) + Trap #12 (no paste cascade) + Trap #14 (no path-colliding extractions) — all active
**Gate count:** 418 total (verified at commit `49e804f`)
**Phase 1 commits (newest first):**
- `216171d` v10.500 Phase 1 Batch 3d — doctrine refresh, observability regression test, OPERATIONAL_PROTOCOL.md, POLICY_GAPS.md
- `[commit]`  v10.500 Phase 1 Batch 3c — bcrypt envelope migration + verify_pw multi-path + auto-upgrade instrumentation (1437 SHA-256 → envelope-wrapped)
- `2aab56b` v10.500 Phase 1 Batch 3b — FastAPI must_change_password enforcement via must_rotate JWT scope + core.py hash_pw hotfix
- `13d5258` v10.500 Phase 1 Batch 3a — Real AuthProvider + login lifecycle (replaces v10.495 stub)

For full ledger: `docs/architecture/REVIVAL_LEDGER.md` (newest entry on top)
For Phase 1 closure record: `docs/CHANGELOG_v10500_batch3d.md`
For operational discipline: `docs/architecture/OPERATIONAL_PROTOCOL.md` (introduced Batch 3d)

---

## Current architectural reality (CGR1-grounded)

These statements describe runtime as of commit `216171d`:

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

1. **Phase 2 planning (next focus).**
   Now that Phase 1 React auth substrate is closed, Phase 2 scope to be
   determined. Candidate themes: forced normalization to direct bcrypt
   (replacing envelope), audit-log file gitignore migration with
   `git rm --cached`, password policy strengthening (close the
   stated-vs-enforced gap from `POLICY_GAPS.md`), `_APP_VERSION`
   stamp policy formalization, additional React substrate features
   (settings, voluntary password change, password reset).

2. **Stage C governance enforcement (paused).**
   ~5/35 gates wired through Batch 2e. Remaining gates G388-G417
   tracked in `OI-66`. Will resume after Phase 2 planning.

3. **PostgreSQL migration (incremental).**
   27/52 tables migrated. G163 ratchet enforces no regression.

4. **mlops_model_registry adoption (incremental).**
   11 engines pending registration per G386.

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

Recorded in `docs/architecture/POLICY_GAPS.md`. Highlights:

1. **Stated-vs-enforced password policy.** `utils/core.py:313` email
   template advertises "uppercase, lowercase, number, special character"
   but `pages/_login.py:286-291` and Batch 3b's
   `/api/auth/change-password` enforce length-only. Cross-platform
   consistent; just weaker than advertised.
2. **Envelope retirement.** Phase 2 should plan when to drop the
   transitional envelope verify path. Trigger: when the
   "Envelope-backed credential authenticated" INFO log stops appearing
   in production logs for ≥30 days.
3. **`data/users.json` tracking inconsistency.** The file is listed in
   `.gitignore` but is tracked. `git rm --cached` would un-track but
   requires a bootstrap-from-generator workflow that hasn't been
   designed.
4. **Auto-upgrade re-hash on envelope success.** Currently deferred —
   envelope hashes stay envelope-wrapped indefinitely. Phase 2 hardening
   could add observable staged normalization.

---

## How to resume in a fresh session

Paste this into a new Claude chat:

> Continuing A2Z v10.500. Last commit: `216171d` (Phase 1 Batch 3d closed).
> Phase 1 complete: 10/10 gates green, React auth substrate fully wired.
> Ready for Phase 2 scoping. Read `docs/continuity/SESSION_BOOTSTRAP.md`
> for current state.

That plus `userMemories` gives Claude full Phase 1 context immediately.
