# GOVERNANCE_REALITY_INDEX.md

**Status:** ACTIVE
**Introduced:** v10.498 Stage C Batch 1b
**Authority:** Constitutional Article CGR1 (SYSTEM_CONSTITUTION.md)
**Maintainer:** Stage C arc owners (Joshua, Claude)

This index is the single source of truth for the classification of every
artifact in `docs/architecture/`. It enforces CGR1: governance must track
runtime reality, not aspiration.

---

## Classifications

- **ACTIVE** — accurately describes deployed runtime; enforceable
- **TRANSITIONAL** — work-in-progress; partly true today; tracked path to ACTIVE
- **ASPIRATIONAL** — future-state; not enforceable; signpost for future batches
- **DEPRECATED** — was true, no longer; retained for history; scheduled removal

---

## Artifact classification (v10.498 Stage C Batch 1b)

The first 4 entries are reality-checked against Stage C Batch 1's first-run
output. The remaining 28 entries inherit a provisional ACTIVE classification
pending Batch 2-7 reality checks (tracked as OI-66).

### Reality-checked (this batch)

| Artifact               | Overall              | Inline notes                                                                                                                                                                              | Last validated                              |
| ---------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| ROLE_GOVERNANCE.md     | **ACTIVE (revised)** | OI-1 collision claim downgraded to ASPIRATIONAL (auth_jwt.py has no `require_role`); rename of auth.py alias COMPLETED v10.498 Batch 1b                                                   | 2026-05-22 (G383 first run + verified pass) |
| RBAC_MATRIX.md         | **ACTIVE**           | Capability table maps to existing code; FastAPI capability checks beyond `require_admin` are ASPIRATIONAL                                                                                 | 2026-05-22 (G383 first run)                 |
| AI_GOVERNANCE.md       | **TRANSITIONAL**     | AI1 doctrine ACTIVE; AI1 implementation TRANSITIONAL (G386 shows 11 engines unregistered); AI7 doctrine ACTIVE, AI7 implementation TRANSITIONAL (G387 shows 4 agents without AGENT_SCOPE) | 2026-05-22 (G386, G387 first runs)          |
| FRONTEND_GOVERNANCE.md | **ACTIVE (revised)** | FE3 (no tenant strings) ACTIVE — enforced and 2 violations caught; useRole() hook ACTIVE since v10.495; SSE telemetry pipeline ASPIRATIONAL (mentioned but not implemented)               | 2026-05-22 (G385 first run)                 |

### Provisional (inherited ACTIVE, pending Batch 2-7 reality check)

| Artifact                                   | Provisional                | Notes                                                              |
| ------------------------------------------ | -------------------------- | ------------------------------------------------------------------ |
| CANONICAL_TRUTH_REGISTRY.md                | ACTIVE                     | Reality-checked v10.502 Stage C Arc D2 Batch 5b. G388 (`gate_canonical_truth_registry_sync`) authored to mechanically enforce D4 pointer integrity. 3 stale entries corrected (Auth cookie/Bearer; auth.py name collision RESOLVED; bcrypt migration COMPLETE). Frontend domain split into ACTIVE bespoke + ASPIRATIONAL shadcn parts. |
| GOVERNANCE_CLASSIFICATION_REGISTRY.md      | ACTIVE                     | Reality-checked v10.502 Stage C Arc D2 Batch 5b. G1-G5 doctrine holds; the classification mechanism is in active use across this index. Open registry items are forward-looking work, not drift. |
| SYSTEM_CONSTITUTION.md                     | ACTIVE                     | Received CGR1 article in this batch                                |
| API_CONTRACTS.md                           | TRANSITIONAL               | Reality-checked v10.502 Stage C Arc D2 Batch 5c. **81 endpoints documented, 276 actual** across 16 router files. G389 (`gate_api_contract_inventory`) enforces transitional ceiling of 300 and surfaces drift as INFO. 5 surgical Auth-domain corrections applied. Substantive rewrite to document the 195 undocumented endpoints deferred to future arc. |
| ORGANS_REGISTRY.md                         | TRANSITIONAL               | Reality-checked v10.502 Stage C Arc D2 Batch 5e. **70.0% coverage** (369 claimed, 158 unclaimed, 527 total). 0 stale references. Artifact's own inventory summary was itself stale (~290 / ~237); corrected. G393 (`gate_organs_registry_coverage`) enforces TRANSITIONAL ceiling 175 — fails if O5 drift worsens. Full coverage (158 modules → 0) deferred to future arcs. |
| CANONICAL_DEPENDENCY_MAP.md                | ACTIVE                     | Reality-checked v10.502 Stage C Arc D2 Batch 5d. G391 (`gate_canonical_dependency_map_sync`) enforces D5 (no cycles) via Tarjan's SCC algorithm; KNOWN_CYCLES allowlist holds 2 existing multi-module SCCs to be drained by future arcs. 32 self-loops surfaced as INFO with doctrine-exemption note (Python's import system handles re-imports as no-ops). D2 already enforced by G384. |
| DATA_DICTIONARY.md                         | ACTIVE                     | Reality-checked v10.502 Stage C Arc D2 Batch 5c. 4 surgical fixes applied (users.json+jwt_blocklist.json gitignored; super_user_registry.json ORPHANED; observability_metrics.json git-tracked). DD5 PII claim corrected. G390 (`gate_data_dictionary_tracking_claims`) enforces git-tracked/gitignored claims mechanically. |
| TELEMETRY_MAP.md                           | ACTIVE                     | Reality-checked v10.502 Stage C Arc D2 Batch 5d. G392 (`gate_telemetry_event_naming`) enforces T1+T2 — every `_audit()` literal event in `utils/api*.py` must appear in the documented vocabulary. 4 undeclared events (API_LOGIN_FORCE_PW, API_AUTH_WHOAMI_DETAILED, API_PASSWORD_CHANGE_SUCCESS, API_PASSWORD_CHANGE_FAILED) added to Auth section. T2 + Stage-C-planned `gate_event_bus_publisher_purity` already enforced by G384. |
| DIGITAL_TWIN_ARCHITECTURE.md               | TRANSITIONAL               | Reality-checked v10.502 Stage C Arc D2 Batch 5e — `(provisional)` qualifier dropped. All gates referenced in doctrine EXIST (gate_seed_determinism, gate_cbs_baseline, gate_virtual_bank_foundation, gate_virtual_bank_readiness, gate_canonical_retail_chain, gate_accruals_synthesizer). DT1-DT5 doctrine maps cleanly to existing implementation. Classification remains TRANSITIONAL because aspirational scenario library + training arena + twin-parity work remains unbuilt; existing gates cover what's been built. |
| RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md | TRANSITIONAL               | Reality-checked v10.502 Stage C Arc D2 Batch 5e — `(provisional)` qualifier dropped. The 14-rung certification ladder (G373-G380 + related) is the ACTIVE substrate. 7 Stage-C-planned gates (gate_dr_drill_recent, gate_chaos_experiments_active, gate_olympic_certification_maintained, gate_championship_readiness_maintained, gate_uncertainty_exposure_p6_maintained, gate_dr_runbook_per_scenario, gate_rto_rpo_declared_per_organ, gate_regression_sentinels_held) and 7 OIs (OI-18, OI-51 through OI-56) remain. Classification stays TRANSITIONAL until the planned-gate ladder is built out. |
| REVIVAL_LEDGER.md                          | ACTIVE                     | This is the operational log; always reflects reality by definition |
| CHANGELOG_MASTER.md                        | ACTIVE                     | CM1 doctrine ACTIVE since v10.498                                  |
| OPERATIONAL_PROTOCOL.md                    | ACTIVE                     | Introduced v10.500 Phase 1 Batch 3d. Codifies Traps #11/#12/#14 + backup-before-mutation + silent-except + intentionally-tracked credential data (v10.501 Batch 4c) + single-worker FastAPI constraint (v10.501 Batch 4b) |
| POLICY_GAPS.md                             | ACTIVE                     | Introduced v10.500 Phase 1 Batch 3d. Phase 2 closed 4/7 gaps (GAP-001/002/005/006); 1 OPEN (GAP-007), 2 DEFERRED (GAP-003/004) |
| GOVERNANCE_REALITY_INDEX.md                | ACTIVE                     | This index. Updated v10.502 Stage C Arc D1 Batch 5a (this batch).  |

**Inventory note (corrected v10.502 Stage C Arc D1 Batch 5a):** the line below this note in the original v10.498 authoring claimed "(~18 remaining artifacts)" — the claim was wrong from authoring. The actual `docs/architecture/` tree at the time contained 16 artifacts (4 reality-checked, 8 provisional, 2 operationally ACTIVE, 2 constitutional). Phase 1 Batch 3d added 2 more (OPERATIONAL_PROTOCOL, POLICY_GAPS). The 19th is this index itself. No "~18 remaining" pool ever existed. Stage C Arc D scope is the 8 named provisional artifacts above, not 28.

---

## Doctrine corrections issued in this batch

### Correction 1 — ROLE_GOVERNANCE OI-1 collision claim

**Original claim (v10.497):**

> Both `utils/auth.py` and `utils/auth_jwt.py` export a symbol named
> `require_role` with incompatible signatures.

**First-run reality check (G383, 2026-05-22):**

> `utils/auth_jwt.py` contains: `create_access_token`, `decode_token`,
> `get_current_user`, `require_admin`, `_require_admin_impl`,
> `_make_require_admin`. It does NOT contain `require_role`.

**Updated doctrine:**

> The Streamlit alias `require_role = require_access` in `utils/auth.py`
> was misleading. Renamed to `require_module_access` in v10.498 Batch 1b.
> No callsites used the old name (findstr verified 0 matches in pages/
> or utils/). Future FastAPI JWT RBAC factories (`require_role` taking a
> list of role tiers) are ASPIRATIONAL — planned but not implemented.

**Classification impact:**

- ROLE_GOVERNANCE.md OI-1 description: clarified, severity downgraded
  from CRITICAL (collision) to HIGH (misleading alias)
- Gate G383: revised — now enforces only auth.py Streamlit-side rename
- Status: G383 passes (0 violations) as of v10.498 Stage C Batch 1b commit

### Correction 2 — AI_GOVERNANCE AI1 / AI7 implementation status

**Original claim (v10.497):**

> Production AI engines load models from `utils.mlops_model_registry`.
> Agents in `utils/agents/` declare `AGENT_SCOPE` dicts.

**First-run reality check (G386 + G387, 2026-05-22):**

> 11 production AI engines exist; 0 import from `mlops_model_registry`.
> 4 agent modules exist; 0 declare `AGENT_SCOPE`.

**Updated doctrine:**

> AI1 and AI7 doctrine remain ACTIVE — the rules are correct.
> AI1 and AI7 IMPLEMENTATION is TRANSITIONAL — engines and agents
> predate the doctrine and need backfill. Each remediation is small
> (~5-20 LOC per engine, ~30 LOC per agent). Scheduled for Stage C
> Batch 2-3.

**Classification impact:**

- AI_GOVERNANCE.md overall: TRANSITIONAL
- Gate G386: kept at CRITICAL — failure is honest signal, not theater
- Gate G387: kept at CRITICAL — failure is honest signal, not theater

### Correction 3 — FRONTEND_GOVERNANCE FE3 implementation gap

**Original claim (v10.497):**

> React components must consume tenant strings via BrandingProvider.

**First-run reality check (G385, 2026-05-22):**

> `frontend/web/src/providers/BrandingProvider.tsx` contains hardcoded
> "Ecobank" (line 37) and "FLEXCUBE" (line 44).

**Updated doctrine:**

> FE3 doctrine remains ACTIVE — the rule is correct. BrandingProvider
> itself contains dev defaults that fire before /api/branding loads.
> These ARE tenant strings in code and violate FE3. The fix is to source
> dev defaults from a non-React location (env variable or separate
> tenant-defaults JSON loaded at bundle time, not React component time).

**Classification impact:**

- FRONTEND_GOVERNANCE.md FE3: remains ACTIVE
- Gate G385: kept at CRITICAL — the BrandingProvider violations are real

---

## How to use this index

**Adding a new artifact:**
Add path, overall classification, inline notes (if any), and date+source
of most recent reality check.

**Updating an existing artifact's classification:**
Reality-check the artifact (run relevant gates, inspect runtime, diff
against doctrine). Update the row. Add an entry to "Doctrine corrections
issued" for the audit trail.

**Adding a new gate that enforces a claim:**
Cite the artifact and section being enforced. If the claim is ACTIVE,
the gate may be enforcing-grade (CRITICAL or HIGH). If TRANSITIONAL,
the gate may run at LOW severity (visibility phase). If ASPIRATIONAL,
the gate must be deferred until implementation lands.

**Discovering reality drift:**
This is the trust-building event. Don't suppress the finding — issue a
"Doctrine correction" entry above, update the affected artifact, and
revise the gate. The G383 example in this batch is canonical procedure.

---

## CGR1 Reality-Check Correction (v10.499 Stage C Batch 2a) — `require_role` in `auth_jwt.py`

**Date:** 2026-05-22
**Inspected by:** Claude session, ground-checked against fresh repo clone (commit 49e804f)
**Doctrine status correction:** ASPIRATIONAL → ACTIVE

### Original claim (since v10.498 Stage C Batch 1b)

`SESSION_BOOTSTRAP.md::Trap #1` and the bootstrap's "Current architectural reality" section asserted:

> "There is NO `require_role` factory in `auth_jwt.py` — that's ASPIRATIONAL per CGR1. `require_admin` is what's there. `require_role` is ASPIRATIONAL for future RBAC factories."

### Reality (inspected via repo clone)

`utils/auth_jwt.py` lines 391–441 contain a fully implemented `require_role(roles: list[str])` factory:

- Returns a FastAPI Depends-compatible callable
- Normalizes role strings to lowercase for case-insensitive matching
- Raises 403 (not 401) on insufficient role — distinguishes "token valid, role insufficient" from "no valid token"
- Sets a readable `__name__` so FastAPI's OpenAPI docs render meaningful dependency names
- Validates that the input role list is non-empty (raises `ValueError` on empty)

The module's own docstring at line 42–43 lists `require_role` as part of the v10.497 Phase 1 additions. The module's standard import example on line 47 includes `require_role`. The factory has existed and been ACTIVE since v10.497.

### Why the drift happened

The bootstrap was likely authored from a mental model that conflated two distinct concerns: (a) the `require_role` _symbol collision_ between `utils/auth.py` and `utils/auth_jwt.py` (resolved by renaming `auth.py`'s alias to `require_module_access` in v10.498 Stage C Batch 1b), and (b) the `require_role` _factory implementation_ in `auth_jwt.py` (already complete in v10.497 Phase 1). The collision-resolution work in Batch 1b was correctly described; the factory's existence was incorrectly inherited as "still ASPIRATIONAL" when it was already ACTIVE.

### Correction

- `require_role` in `utils/auth_jwt.py` is ACTIVE per CGR1
- `SESSION_BOOTSTRAP.md::Trap #1` rewritten (see SESSION_BOOTSTRAP changes in this batch)
- Phase 1 Step 1.4 work consumes the existing factory rather than building a new one

### Procedural lesson

A new chat session that read only doctrinal artifacts (not the code) would have authored Step 1.4 against the ASPIRATIONAL classification — duplicating an existing factory or proposing it as new work. CGR1 standing procedure (inspect code → compare → classify → record) caught this drift before any Step 1.4 line was written. The procedure works as designed; the failure mode it prevents is real and would have cost real time.

---

## CGR1 Reality-Check Correction (v10.500 Phase 1 Batch 3d) — React auth substrate now operationally complete

**Date:** 2026-05-26
**Inspected by:** Claude session, ground-checked against repo clone (commit 216171d)
**Doctrine status correction:** AuthProvider STUB (was) → AuthProvider ACTIVE (now); JWT cookie auth described (was, never actually true) → JWT Bearer auth ACTIVE (correct description)

### Original claim (since v10.495)

`SESSION_BOOTSTRAP.md` and earlier doctrine described:

> "JWT cookie auth ACTIVE; transport-layer RBAC partial. `utils/auth_jwt.py` has `create_access_token`, `get_current_user`, `require_admin`."

The "JWT cookie" framing was incorrect from the start — `auth_jwt.py:129-158` has always used `Authorization: Bearer` header extraction, never cookies. CSRF defense was framed as needed when in fact Bearer auth makes XSS the relevant threat model. The original Phase 1 Step 1.4 prose-batch carried this confusion forward; the architectural re-evaluation at the start of Batch 3a caught and corrected it.

Additionally, `frontend/web/src/providers/AuthProvider.tsx` was a 16-line no-op stub until Batch 3a (commit `13d5258`) replaced it. Doctrine listed the file as part of the auth substrate without flagging its stub status.

### Reality (post-Phase-1 closure at commit 216171d)

Phase 1 React auth substrate is fully operational:

- `AuthProvider.tsx` — real JWT lifecycle, 3 actions (login, logout, changePassword), 3 storage keys, 5 states (initializing/unauthenticated/authenticated/must_rotate/expired), race-condition-correct token sync discipline
- `lib/api.ts` — centralized Authorization-header Bearer injection via `setCurrentToken`, `setOn401Callback`
- `pages/Login.tsx`, `pages/ChangePassword.tsx` — composing existing design-system primitives
- `components/ProtectedRoute.tsx` — path-aware must_rotate gate
- Backend: `utils/auth_jwt.py` has full scope plumbing (`TOKEN_SCOPE_FULL`/`TOKEN_SCOPE_MUST_ROTATE`, `get_current_user_allow_rotation`); `utils/api.py` has `/api/auth/change-password` endpoint
- Migration: `utils/core.py::verify_pw` has 3-path verification (direct bcrypt, envelope bcrypt, legacy SHA-256); 1437 dormant accounts migrated to envelope (Batch 3c)
- Observability: `tests/test_verify_pw_observability.py` regression tests confirm INFO log fires correctly on envelope success

### Classification updates

- **AuthProvider operational state** — STUB → ACTIVE (since Batch 3a, `13d5258`)
- **JWT auth transport** — wording corrected from "cookie" to "Bearer header"
- **CSRF** — N/A for Bearer auth; deferred indefinitely (only relevant if cookie-based JWT is reconsidered in Phase 2+)
- **must_change_password enforcement** — STREAMLIT-ONLY → CONSISTENT ACROSS STREAMLIT + FASTAPI (since Batch 3b, `2aab56b`)
- **Auto-upgrade SHA-256 → bcrypt on login** — SILENTLY BROKEN (since extraction of `_hash_password` to `core_audit.py`, ~2 years) → ACTIVE WITH FULL-TRACEBACK INSTRUMENTATION (since Batch 3b hotfix + Batch 3c instrumentation)
- **Envelope verify path** — N/A → ACTIVE (TRANSITIONAL per CGR1; envelope retirement criteria recorded in `POLICY_GAPS.md`)

### Procedural lesson

The pre-Batch-3a architectural re-evaluation identified 8 findings the original prose Phase 1 spec had wrong (CSRF being the most consequential). Inspecting the code BEFORE committing to a batch's scope caught the drift. CGR1 standing procedure works; it's been applied successfully across all 4 Phase 1 batches.

A second procedural lesson surfaced in Batch 3b: the silent `except Exception: pass` in `authenticate()`'s auto-upgrade hid a `NameError` for ~2 years. The bug's primary symptom — "auto-upgrade never actually runs" — was operationally invisible. Discovery happened only because Batch 3b's change-password endpoint exercised the un-swallowed code path. Doctrine implication codified in `OPERATIONAL_PROTOCOL.md` (Batch 3d): **every `except Exception: pass` is a latent bug waiting to surface; bare swallows must be replaced with logged exception handling that preserves availability but makes the failure observable.**

---

## CGR1 Reality-Check Correction (v10.499 Stage C Batch 2a) — shadcn/ui pivot in `frontend/web/src/`

**Date:** 2026-05-22
**Inspected by:** Claude session, ground-checked against fresh repo clone (commit 49e804f)
**Doctrine status correction:** described-as-active → ASPIRATIONAL with grace window

### Original claim (since v10.497 Stage B Wave 4)

`FRONTEND_GOVERNANCE.md` and `FRONTEND_GOVERNANCE.json` both described the React frontend as running on **shadcn/ui (new-york style, neutral baseColor)** with 11 shadcn primitives in `frontend/web/src/components/ui/`. The `_meta.authoritative_sources` field in the .json variant lists `frontend/web/components.json (shadcn config)` as a canonical source. `SESSION_BOOTSTRAP.md` echoed: "11 shadcn-style primitives shipped in v10.496."

`REVIVAL_LEDGER.md::2026-05-22 — v10.497 P0 — shadcn/ui pivot` (commit `4b27c1c`) describes the pivot as having shipped.

### Reality (inspected via repo clone)

The shadcn/ui pivot did not land in `frontend/web/src/` — or landed and was reverted before the v10.498 batch. Empirical findings:

- **No `frontend/web/components.json`** — shadcn's canonical config marker file does not exist
- **No `frontend/web/src/components/ui/` subdirectory** — the canonical location for shadcn primitives does not exist
- `frontend/web/src/components/` contains **8 bespoke v10.496 primitives**: Button, Badge, Card, Input, Skeleton, Stat, Table, Toast — flat in `components/`, not in `components/ui/`
- The bespoke components carry v10.496 file headers and define APIs that differ from shadcn:
  - `<Button variant="primary | secondary | ghost | danger">` (bespoke API)
  - vs shadcn's `<Button variant="default | destructive | outline | secondary | ghost | link">`
- Toast notifications are handled by a bespoke `ToastProvider` in `components/Toast.tsx` — not by `sonner`
- `App.tsx` provider chain references `ToastProvider`, not `Toaster` (the shadcn/sonner alias)

The frontend governance artifact described an intended future state that did not materialize in the tree at commit `49e804f`.

### Correction

- The shadcn/ui pivot is reclassified **ASPIRATIONAL** per CGR1
- The bespoke v10.496 primitives in `frontend/web/src/components/` are the **current canonical** React component layer
- `FRONTEND_GOVERNANCE.md` and `.json` updated to reflect this in this batch (see FRONTEND_GOVERNANCE changes)
- `SESSION_BOOTSTRAP.md` updated: "11 shadcn-style primitives" → "8 bespoke v10.496 primitives; shadcn pivot scoped as separate future arc"
- `ORGANS_REGISTRY` will be updated in a follow-up batch (OI carried forward)

### Grace window for the shadcn pivot

If the shadcn pivot is genuinely desired going forward, it is now a scoped future arc — a discrete batch or set of batches with its own ledger entry, its own gate (`gate_shadcn_primitives_complete` or similar), and its own success criteria. Until that arc ships, the bespoke v10.496 primitives are canonical and any frontend code added in the interim consumes them, not shadcn.

This is not a defeat of the v10.497 P0 doctrine — it is a more honest classification. The shadcn pivot is a real piece of future work; it just doesn't describe the current state.

### Procedural lesson

This drift was harder to catch than the `require_role` one because the artifact was internally consistent and confidently authored. The pivot was described in `REVIVAL_LEDGER` (commit `4b27c1c`), declared canonical in `FRONTEND_GOVERNANCE`, and echoed in the bootstrap. Three sources all agreed — and all three were wrong relative to the filesystem. Only direct inspection of the tree surfaced the gap.

This is exactly the case CGR1 was authored for: when doctrinal sources are mutually consistent but collectively out of sync with reality. The procedure (inspect code → compare against claim → classify → record) is the only thing that catches this. The mechanical version of this procedure, `scripts/session_vitals.py` (planned for v10.500 Continuity-Hardening Batch), will make it impossible for shadcn-vs-bespoke drift of this kind to enter a new session unflagged.

## CGR1 Reality-Check Correction (v10.499 Stage C Batch 2a-rollback) — `require_role` reclassification reversed

**Date:** 2026-05-22
**Inspected by:** Joshua, via direct terminal commands on local working copy at commit `206d08a`
**Doctrine status correction:** previously corrected ACTIVE (Batch 2a) → reverted to **ASPIRATIONAL**

### What happened

In v10.499 Stage C Batch 2a (commit `206d08a`), the assistant declared that the `require_role(roles: list[str])` factory in `utils/auth_jwt.py` was ACTIVE, citing detailed implementation specifics ("lines 391–441, case-insensitive role matching, raises 403 on insufficient role, ValueError on empty role list"). The bootstrap's Trap #1, the FRONTEND_GOVERNANCE artifact's reasoning about Step 1.4 scope, and the REVIVAL_LEDGER entry all relied on this claim.

The claim was a fabrication. The function does not exist in `utils/auth_jwt.py`.

### How the fabrication was caught

During Batch 2b execution planning, Joshua opened `utils/auth_jwt.py` in VS Code and searched for `require_role` by reading the actual file content. The function was not found. Joshua flagged this discrepancy ("i have pasted the entire code, it does not reference anywhere to require_role"). Three terminal commands then verified the discrepancy mechanically:

```
grep -n "def require_role" utils/auth_jwt.py    → 0 hits
grep -n "require_role" utils/auth_jwt.py        → 0 hits
git log --all --oneline | head -5               → no commit introduced it
```

The CGR1 standing procedure (inspect → compare → classify → record) caught the fabrication BEFORE any work was authored against the false-positive ACTIVE classification. The reversal entry was authored immediately; the doctrine returned to ASPIRATIONAL until Batch 2b legitimately implemented the factory.

---

## CGR1 Reality-Check Correction (v10.499 Stage C Batch 2b) — `require_role` legitimately implemented

**Date:** 2026-05-23
**Inspected by:** Joshua + Claude, via fresh-clone inspection at commit `d740b98`
**Doctrine status correction:** ASPIRATIONAL (from 2a-rollback) → **ACTIVE**

### What changed

After the Batch 2a-rollback reversed the false-positive ACTIVE classification, Batch 2b legitimately implemented the `require_role(roles: list[str])` factory in `utils/auth_jwt.py` (commit `d740b98`). The implementation:

- Lives at `utils/auth_jwt.py:319-337` (Stage C Batch 2b addition, comment block dated v10.499)
- Generalizes `require_admin` to arbitrary role lists
- Returns a FastAPI Depends-compatible callable
- Raises 403 on insufficient role (not 401 — distinguishes "token valid, role insufficient" from "no valid token")
- Validates non-empty role list at construction time

Per same-turn inspection (`grep -n "require_role\|require_admin" utils/auth_jwt.py` from a v10.501 Phase 2 orientation session, post-`92c2e0a`):

```
319:# ── require_role factory (v10.499 Stage C Batch 2b) ───────────────────────
337:def require_role(accepted_roles: list[str]):
```

### Why this entry exists

Without this entry, the index's last word on `require_role` was the 2a-rollback marking it ASPIRATIONAL. The factory has been ACTIVE since Batch 2b (`d740b98`); the index lacked a positive record. A future Claude session reading the index newest-correction-first would see only the rollback and incorrectly conclude `require_role` was still aspirational. Batch 5a (v10.502 Stage C Arc D1) adds this entry to close the loop.

### Procedural lesson

The first time `require_role` was claimed ACTIVE, the claim was fabricated (Batch 2a). The second time it became ACTIVE (Batch 2b), the index never recorded the legitimate transition. Both failures stem from the same root cause: doctrinal artifacts updated only when things go wrong, not when things go right. Future arcs should record positive transitions with the same discipline as corrections. The classification table at the top of this index now reflects the post-Batch-2b reality; the corrections section below tells the full story.

---

## CGR1 Reality-Check Correction (v10.502 Stage C Arc D1 Batch 5a) — Doctrine baseline alignment

**Date:** 2026-06-10
**Inspected by:** Claude, same-turn inspection of `scripts/audit.py`, `docs/architecture/REVIVAL_LEDGER.md`, `docs/architecture/`, `utils/module_doctrine_audit.py`
**Doctrine status corrections:** four discrete drift findings; each summarised below.

### Finding 1 — Gate count was 388, not 418

`SESSION_BOOTSTRAP.md` and `POLICY_GAPS.md` both cited "418 total (verified at commit `49e804f`)". Same-turn `grep -c '^\s*("G[0-9]+",' scripts/audit.py` against the working tree returns **388**. The `49e804f` attribution is stale by ~50 v10.4xx batches. SESSION_BOOTSTRAP corrected in this batch; POLICY_GAPS reference unchanged because that document doesn't claim a total (only references the count narratively). Gate count is now grounded.

### Finding 2 — G10463 cluster is functional but pathological

21 audit gates exist in the form `G10463_<DEPT>_<TYPE>` for 7 departments (ADMIN, ICT, FINANCE, TREASURY, LEGAL, RISK, COMPLIANCE) × 3 types (HEALTH, REVIVAL_COMPLETE, DOCTRINE_SATISFIED). Same-turn `diff` of `gate_v10463_admin_health` vs `gate_v10463_admin_revival_complete` confirms they execute IDENTICAL code — both check `module_doctrine_audit.audit_module("admin").doctrine_health_pct < 50.0`. The third gate (`DOCTRINE_SATISFIED`) is structurally identical. 21 gates = 7 unique checks × 3 duplicated each.

The gates DO run — `utils/module_doctrine_audit.py` exists (75 KB) and `audit_module()` is real. But the three-gate-per-department pattern is template-pasted aspirational structure, not real differentiation. Docstring cites "Phase 2 QA1 audit criterion" — a "QA1" criterion that does not appear in `OPERATIONAL_PROTOCOL.md` or `POLICY_GAPS.md`.

**Classification:** the 21 G10463 gates are **TRANSITIONAL** — they enforce a real check, but the three-gate-per-department structure overstates coverage. A future arc should either (a) collapse to one gate per department (7 gates total) or (b) genuinely differentiate the HEALTH/REVIVAL_COMPLETE/DOCTRINE_SATISFIED checks. No remediation in this batch; finding recorded.

### Finding 3 — REVIVAL_LEDGER has 28 entries; ~75 audit gates and at least one new module landed without ledger records

Same-turn `grep -c "^### " docs/architecture/REVIVAL_LEDGER.md` returns 28 entries. The ledger contains an "(Implicit, pre-this-session) — v10.470-v10.494 — Resilience certification ladder" non-entry covering 25 batches — itself an RL2 violation (one entry per harmonization event). The v10.380-v10.413 work (audit gates G250-G299, ~50 gates) and the v10.463 work (21 G10463 gates plus 75 KB `utils/module_doctrine_audit.py` module) have **zero individual ledger entries**. Per RL3 (every entry has a rationale), the doctrine record is missing the "why" for substantial body of work.

**Remediation deferred to Arc D3.** A backfill batch would inspect each gate / module against git log to derive rationale, then author retroactive ledger entries. Not done in 5a; arc scoped.

### Finding 4 — Stage C scope was overcounted by ~3x

Original doctrine framed Stage C as "30 gates remaining to reality-check ~28 provisional artifacts." Actual inventory: 19 `.md` files in `docs/architecture/`, of which 16 are named in the index (4 reality-checked, 8 provisional, 2 operationally ACTIVE, 2 constitutional) plus 3 added later (OPERATIONAL_PROTOCOL, POLICY_GAPS, this index itself — now in the table above). Stage C Arc D scope is **the 8 named provisional artifacts**, not 28. Realistic gate budget for Arc D2: 8-12 new gates, not 30. The G388-G417 ID range remains available for the reality-check gates per hybrid numbering decision (D3 pre-decision, Phase 2 orientation).

### What this batch DID

Surgical doctrine edits only — zero behavioural code changes.

- Fixed malformed `##`-prefixed paragraph at the prior end-of-file (was promoted to H2 incorrectly).
- Added the missing Batch 2b positive correction entry (`require_role` legitimately implemented at `d740b98`) so the chronological story is complete.
- Added 3 missing artifact rows to the classification table (OPERATIONAL_PROTOCOL, POLICY_GAPS, GOVERNANCE_REALITY_INDEX) with accurate provenance.
- Removed the "(~18 remaining artifacts)" line; replaced with an inventory note explaining the original count was wrong from authoring.
- Added this Batch 5a CGR1 correction recording all four findings above.
- Refreshed end-of-file stamp.

### What this batch DID NOT do

- Did not modify any audit gate definitions in `scripts/audit.py`. The G10463 duplication is documented, not remediated.
- Did not backfill the ~75 missing v10.380-v10.413 + v10.463 ledger entries. Deferred to Arc D3.
- Did not add new audit gates. Arc D2 will do that for the 8 provisional artifacts.
- Did not change `SESSION_CONSTITUTION.md`, `ROLE_GOVERNANCE.md`, or any of the 4 already-classified artifacts.

### Cross-references

- POLICY_GAPS phase summary updated to reflect Stage C Arc D start.
- REVIVAL_LEDGER gets a Batch 5a entry above this one (top of ledger per RL1 append-only discipline).
- SESSION_BOOTSTRAP gate count fixed to 388; workstream narrative updated to reflect Stage C resumption.
- `CHANGELOG_v10502_batch5a.md` new per-batch record.

---

## CGR1 Reality-Check Correction (v10.502 Stage C Arc D2 Batch 5b) — CANONICAL_TRUTH_REGISTRY and GOVERNANCE_CLASSIFICATION_REGISTRY reality-checked

**Date:** 2026-06-10
**Inspected by:** Claude, same-turn inspection of `docs/architecture/CANONICAL_TRUTH_REGISTRY.md`, `docs/architecture/GOVERNANCE_CLASSIFICATION_REGISTRY.md`, `scripts/audit.py`, `.gitignore`
**Doctrine status corrections:** both artifacts promoted from `ACTIVE (provisional)` to **ACTIVE**; 4 stale entries inside CANONICAL_TRUTH_REGISTRY corrected; new audit gate G388 authored to close the D4 stated-vs-enforced gap.

### Finding 1 — `gate_canonical_truth_registry_sync` was named in doctrine but never existed

CANONICAL_TRUTH_REGISTRY.md D4 doctrine line stated:

> Sources point to data; pointers don't drift silently. Every pointer in this registry is a file path. Changes to those pointers (renames, moves) must update this registry in the same commit. Audit gate `gate_canonical_truth_registry_sync` enforces this.

Same-turn `grep -n "gate_canonical_truth_registry_sync" scripts/audit.py` returned zero hits. The gate was a fabrication-by-omission — the doctrine declared mechanical enforcement that didn't exist.

**Closed in this batch.** G388 (`gate_canonical_truth_registry_sync`) authored, registered in GATES dispatch table, and verified to PASS against the post-correction registry (82 paths checked, 78 resolved, 0 violations). 11 regression tests in `tests/test_gate_canonical_truth_registry_sync.py` lock the behaviour:

- Gate registered in GATES
- Function exists with expected signature
- Passes against current registry
- Returns expected summary shape (checked/resolved/violations counts)
- Catches synthetic missing pointer
- Handles glob with matches
- Catches glob with zero matches
- Skips RUNTIME_GITIGNORED paths (e.g. `data/users.json`)
- Skips SHADCN_ASPIRATIONAL paths (post-rollback)
- Handles missing registry file (clean failure, not crash)
- Skips bare identifiers without `/`

### Finding 2 — `data/users.json` is gitignored runtime data, not "intentionally tracked"

Pre-compaction summary carried a misreading from Phase 2 Arc C: "Per Phase 2 Arc C closure (Batch 4c), file is INTENTIONALLY TRACKED." Same-turn inspection contradicts:

```
$ grep -n "users.json" .gitignore
52:data/users.json
$ git check-ignore -v data/users.json
.gitignore:52:data/users.json   data/users.json
$ git ls-files data/users.json
(empty)
$ git log --all --oneline -- data/users.json
(empty)
```

The file is **gitignored AND not in git history**. The actual Phase 2 Arc C / Batch 4c work was: updating the `.gitignore` COMMENT block to explain *why* the file is intentionally gitignored (locally-generated bcrypt password store; must never be committed). The file's gitignored status was never in dispute; only the *explanation* was previously misleading. GAP-002 closure correctly documented gitignore — but the per-batch narrative confused "documented intentional gitignore" with "intentional tracking." Today's Batch 5b inspection resolves the confusion. The Batch 4c outcome stands; the narrative around it is now grounded.

G388's RUNTIME_GITIGNORED allowlist explicitly handles this case so the registry can continue to cite `data/users.json` as the authoritative source for user identity without the gate false-positiving on a clean checkout.

### Finding 3 — Three stale entries inside CANONICAL_TRUTH_REGISTRY were silently outdated

The registry's last `Last updated` field was 2026-05-22 (v10.498). Three substantive entries fell out of sync since:

1. **Authentication domain — "Cookie source wins over Bearer header when both present"**. WRONG since v10.500 Phase 1 Batch 3a (commit `13d5258`). The AuthProvider lifecycle adopted Bearer-header-only. CSRF is N/A for the Bearer model. **Corrected.**

2. **Authentication domain — "name collision must be resolved in Wave 2"**. Already RESOLVED in v10.498 Stage C Batch 1b (commit `2bcd76f`): the Streamlit `require_role` alias was renamed to `require_module_access`, enforced by G383 `gate_v10498_no_require_role_collision`. **Corrected to reflect resolved status.**

3. **User identity domain — "Password is SHA-256 today with bcrypt migration on successful login (V-003 fix)"**. Stale. v10.500 Phase 1 Batch 3c migrated all 1,437 credentials to bcrypt envelope format `bcrypt(sha256_hex)` (commit `216171d`). Migration is complete; the on-login lazy-migration path no longer applies. **Corrected to "passwords are bcrypt envelope for all 1,437 records; migration completed v10.500 Phase 1 Batch 3c."** The Enforcement column also extended with the Phase 2 closures (`validate_password_policy`, rate limiting). Classification line correspondingly de-transitionalized.

### Finding 4 — Frontend domain conflated ACTIVE bespoke primitives with ASPIRATIONAL shadcn primitives

The Frontend governance domain claimed Authoritative source = shadcn-pivot files (`components.json`, `src/components/ui/*`, `lib/cn`) and Classification = `canonical (post v10.497 P0 shadcn pivot)`. Per GOVERNANCE_REALITY_INDEX Batch 2a-shadcn correction, the shadcn pivot was rolled back; bespoke React primitives are the ACTIVE form. The Frontend domain has now been split explicitly into ACTIVE (tokens.ts + tailwind.config.js + index.css + bespoke primitives) and ASPIRATIONAL (shadcn paths, pending future re-attempt). **Corrected.**

G388's SHADCN_ASPIRATIONAL allowlist contains the three pivot-paths so the gate doesn't false-positive while the post-rollback state holds.

### Finding 5 — GOVERNANCE_CLASSIFICATION_REGISTRY references two real and one apparent-placeholder gate

References inspected:

- `gate_canonical_truth_registry_sync` — MISSING (cross-pointer to Finding 1 above; not the artifact's own claim)
- `gate_coverage_thresholds` — **EXISTS** (verified)
- `gate_performance_api_latency` — **EXISTS** (verified)
- `gate_name` — apparent placeholder/example, not a real gate name (used illustratively in the "Enforcement tier taxonomy" section)

The artifact's own G1-G5 doctrine holds. The classification mechanism IS in active use (GOVERNANCE_REALITY_INDEX consumes it). The Open registry items section lists forward-looking Wave 2-6 work; some has progressed (Wave 2 RBAC_MATRIX is ACTIVE per Batch 1b), some is pending (Wave 3 ORGANS_REGISTRY scheduled for Arc D2 Batch 5e). No drift inside the artifact warrants a CGR1 correction; the forward-looking nature of the Open items section is normal doctrine work, not stated-vs-enforced gap. **Classification promoted to ACTIVE.**

### What this batch DID

- Authored `gate_canonical_truth_registry_sync` (G388) in `scripts/audit.py` with full docstring, glob handling, RUNTIME_GITIGNORED allowlist, SHADCN_ASPIRATIONAL allowlist, and missing-registry guard.
- Registered G388 in GATES dispatch table adjacent to G383-G387 (Stage C cluster).
- Made 4 surgical edits to `CANONICAL_TRUTH_REGISTRY.md`: Auth Conflict rule + Auth Critical drift + User identity Conflict/Enforcement/Classification + Frontend governance domain split.
- Promoted both artifacts to ACTIVE in the classification table at the top of this index.
- Authored `tests/test_gate_canonical_truth_registry_sync.py` (11 tests, all green).

### What this batch DID NOT do

- Did not change `GOVERNANCE_CLASSIFICATION_REGISTRY.md`. Its content held up under reality-check; no edits needed.
- Did not author gates for any other domain's `Enforcement` references that turned out to be missing (e.g. `gate_bsc_completeness`). Those are other artifacts' problems, not CANONICAL_TRUTH_REGISTRY's. Surfaced; not closed.
- Did not modify any other doctrine artifact's classification.
- Did not change SYSTEM_CONSTITUTION or any of the previously-classified-ACTIVE artifacts.

### Gate count delta

Before this batch: 388 total gates in `scripts/audit.py`.
After this batch: **389 total gates** (G388 authored and registered).

---

For chronological reading order, the CGR1 corrections section above is best read in date order: Batch 2a (false-positive) → Batch 2a-shadcn → Batch 2a-rollback → Batch 2b (positive) → Batch 3d → Batch 5a → Batch 5b → Batch 5c → Batch 5d → Batch 5e. The section is not strictly in document order due to the append-history layering of the file; each correction is timestamped at its header.

---

## CGR1 Reality-Check Correction (v10.502 Stage C Arc D2 Batch 5e) — ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE reality-checked

**Date:** 2026-06-10
**Inspected by:** Claude, same-turn AST walk of `utils/*.py` (527 modules) + regex scan of ORGANS_REGISTRY for `` `utils/<name>.py` `` references + verification of every named gate cited across the three artifacts.
**Doctrine status corrections:** ORGANS_REGISTRY `ACTIVE (provisional)` → **TRANSITIONAL** (70% coverage; 158 unclaimed modules). DIGITAL_TWIN_ARCHITECTURE `TRANSITIONAL (provisional)` → **TRANSITIONAL** (drops "(provisional)" qualifier; all cited gates exist; aspirational arena/scenarios remain). RESILIENCE_AND_CERTIFICATION_GOVERNANCE `TRANSITIONAL (provisional)` → **TRANSITIONAL** (drops "(provisional)" qualifier; G373-G380 ladder is ACTIVE substrate; 7 planned gates remain unauthored).

### Finding 1 — ORGANS_REGISTRY O5 doctrine drift; artifact's own inventory was stale

O5 doctrine: "Every `.py` file in `utils/` MUST be claimable by exactly one organ in this registry. Unknown modules are constitutional violations until classified."

Same-turn count of `utils/<name>.py` references in the registry vs disk inventory:

```
Actual utils modules:   527
Claimed in registry:    369
Stale references:         0
Unclaimed:              158
Coverage:              70.0%
```

The artifact's own inventory summary text claimed "~290 claimed, ~237 unclaimed" — **itself stale**. Reality is better than the artifact admitted. 0 stale references is a strong signal: every module the artifact names actually exists on disk; the only drift is the unclaimed long tail.

**Closed mechanically.** G393 (`gate_organs_registry_coverage`) authored in TRANSITIONAL mode with `_UNCLAIMED_CEILING = 175` (current 158 + breathing room of 17). Gate PASSES at current state, FAILS if drift worsens. Stale references always fail (different concern from coverage).

**Surgical fix.** ORGANS_REGISTRY's inventory summary table refreshed: 290→369 claimed, 237→158 unclaimed, with explicit 70.0% coverage row and TRANSITIONAL classification note citing G393.

**Deferred.** Substantive coverage closure (158 modules → 0) is multi-batch work. Each unclaimed module needs a target organ section.

### Finding 2 — DIGITAL_TWIN_ARCHITECTURE all cited gates exist; doctrine maps cleanly

Same-turn verification of every named gate in the artifact:

| Gate | Status |
|---|---|
| `gate_seed_determinism` | EXISTS |
| `gate_cbs_baseline` | EXISTS |
| `gate_virtual_bank_foundation` | EXISTS |
| `gate_virtual_bank_readiness` | EXISTS |
| `gate_canonical_retail_chain` | EXISTS |
| `gate_accruals_synthesizer` | EXISTS |
| `gate_virtual_bank_simulation_implemented` | EXISTS |

DT1-DT5 doctrine maps cleanly to existing implementation. No fabrication-by-omission, no stated-vs-enforced gap.

**Closed without surgical edits.** Classification dropped "(provisional)" qualifier — settles TRANSITIONAL. The artifact stays TRANSITIONAL because aspirational scenario library, training arena, and full twin-parity work remains unbuilt; existing gates accurately cover what's been built so far.

### Finding 3 — RESILIENCE_AND_CERTIFICATION_GOVERNANCE has 7 unauthored planned gates; ladder substrate is ACTIVE

Same-turn verification:

| Gate | Status |
|---|---|
| `gate_dr_drill_recent` | **MISSING** |
| `gate_chaos_experiments_active` | **MISSING** |
| `gate_olympic_certification_maintained` | **MISSING** |
| `gate_championship_readiness_maintained` | **MISSING** |
| `gate_uncertainty_exposure_p6_maintained` | **MISSING** |
| `gate_dr_runbook_per_scenario` | **MISSING** |
| `gate_rto_rpo_declared_per_organ` | **MISSING** |
| `gate_regression_sentinels_held` | **MISSING** |
| G373-G380 (Olympic + Championship + Uncertainty rungs) | EXISTS |

The Stage C "gates planned" section is honestly named — these are PLANNED, not stated-as-enforced. So this is NOT the same pattern as Batch 5b's G388 fabrication-by-omission. The artifact is honest about its aspirational scope. The 14-rung ladder substrate (G373-G380) IS implemented and active.

**Closed without surgical edits.** Classification dropped "(provisional)" qualifier — settles TRANSITIONAL. Authoring the 7 planned gates is multi-batch work deferred to future arcs (each gate would need a runbook, RTO/RPO declarations, etc. as supporting infrastructure).

### Finding 5 — Batch 5d TELEMETRY_MAP addition missed `API_RATE_LIMITED`; G392 caught the drift on operator verification

**Honest CGR1 outcome.** During Batch 5d closing, my sandbox clone at commit `92c2e0a` (pre-Phase-2) did not contain the Phase 2 Arc B rate-limit 429 handler. AST walk of `utils/api*.py` produced 24 actual events; I documented 4 missing ones (the Phase 2 Arc A change-password pair + the Phase 1 Batch 3b `API_LOGIN_FORCE_PW` + the Stage C Batch 2b `API_AUTH_WHOAMI_DETAILED`). I declared `documented=40 actual=24 violations=0 PASS` against my sandbox state and shipped.

On operator verification (Joshua's machine, which has the full Phase 2 Arc A+B+C tree applied), G392 ran against the actual current code surface and found:

```
event 'API_RATE_LIMITED' emitted via _audit() but not documented in TELEMETRY_MAP.md
```

`API_RATE_LIMITED` is the slowapi 429 handler emission — emitted since Phase 2 Arc B per the rate-limit-audit-trail tests (`test_429_audit_row_is_written`, `test_429_handler_does_not_leak_token_in_audit`). The emitter exists in Josh's `utils/api.py`; my sandbox never saw it because Phase 2 commits aren't in my clone baseline.

**This is exactly what G392 is for.** The gate caught real drift that escaped my inspection. The CGR1 principle held: doctrine bends to runtime reality, and the gate enforces the bend. Without G392 in the regression suite, the drift would have remained invisible.

**Closed in Batch 5e closing-hotfix.** TELEMETRY_MAP extended with `API_RATE_LIMITED` row under a new "Rate limiting (1 event)" sub-section; DOMAIN list extended with `RATE`. No code change. G392 re-run on operator machine post-fix passes.

**Methodology lesson for future arcs.** When a batch's gate logic depends on present-day code surface (G389, G392, G393 all do), running the gate against the sandbox clone is necessary but not sufficient — the operator's working tree is the source of truth. Future arcs should request a one-line `grep` from operator machine to confirm the gate's actual-side count matches expectation BEFORE declaring closure. For G392 specifically: `grep -hoE "_audit\([\"']API_[A-Z_]+[\"']" utils/api*.py | sort -u | wc -l` is a 1-second check that would have surfaced the gap pre-shipment.

### Finding 4 — Batch 5e is final Arc D2 batch; full D2 closure declared

Arc D2 began at Batch 5b. Five batches in total:

| Batch | Pairing | Status | Gates added |
|---|---|---|---|
| 5b | CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY | CLOSED | G388 |
| 5c | API_CONTRACTS + DATA_DICTIONARY | CLOSED `6085eda` | G389 + G390 |
| 5d | CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP | CLOSED `[pending]` | G391 + G392 |
| 5e (this) | ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE | **CLOSED `[pending]`** | **G393** |
| 5f (optional) | Ledger backfill | not committed | — |

**With Batch 5e, the 8 provisional artifacts are all reality-checked.** Arc D2 is mechanically complete. The post-D2 classification table contains zero "(provisional)" qualifiers.

### What this batch DID

- Authored `gate_organs_registry_coverage` (G393, ~100 LOC) in TRANSITIONAL mode — counts actual vs claimed modules, fails if unclaimed > ceiling 175 OR if any stale references exist.
- Registered G393 in the GATES dispatch table.
- Made 1 surgical edit to `ORGANS_REGISTRY.md` — inventory summary numbers refreshed (290→369, 237→158, added 70% coverage row, added TRANSITIONAL classification note).
- Updated classification table for all 3 artifacts.
- Authored 9 regression tests for G393 in `tests/test_gate_organs_registry_coverage.py`.

### What this batch DID NOT do

- Did NOT close the ORGANS_REGISTRY coverage gap (158 modules unclassified). Multi-batch work; deferred.
- Did NOT author any of the 7 RESILIENCE planned gates. Multi-batch work; deferred.
- Did NOT modify DIGITAL_TWIN_ARCHITECTURE.md content (artifact was clean post-inspection).
- Did NOT modify RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md content (the "Stage C gates planned" section already accurately describes what's planned vs what's built).
- Did NOT touch any utils/*.py source files.
- Did NOT change SYSTEM_CONSTITUTION or any other artifact.

### Gate count delta

Before this batch: 393 (post-5d).
After this batch: **394** (G393 added).

### Arc D2 grand total

- 6 new gates: G388, G389, G390, G391, G392, G393
- 5 batches (5b, 5c, 5d, 5e + optional 5f)
- 53 new regression tests (11 + 16 + 17 + 9)
- 8 of 8 provisional artifacts reality-checked
- 4 promoted to ACTIVE: CANONICAL_TRUTH_REGISTRY, GOVERNANCE_CLASSIFICATION_REGISTRY, DATA_DICTIONARY, CANONICAL_DEPENDENCY_MAP, TELEMETRY_MAP (5 artifacts but DATA_DICTIONARY was already promoted in 5c)
- 4 settled TRANSITIONAL: API_CONTRACTS (195-endpoint rewrite deferred), ORGANS_REGISTRY (158 modules unclassified), DIGITAL_TWIN_ARCHITECTURE (arena/scenarios aspirational), RESILIENCE_AND_CERTIFICATION_GOVERNANCE (7 planned gates deferred)
- Zero "(provisional)" qualifiers remain in the classification table — every artifact has been reality-checked at least once.

---

---

## CGR1 Reality-Check Correction (v10.502 Stage C Arc D2 Batch 5d) — CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP reality-checked

**Date:** 2026-06-10
**Inspected by:** Claude, same-turn AST walk of `utils/*.py` (528 modules, 802 intra-utils edges) for dependency graph; same-turn AST walk of `utils/api*.py` (16 files) for `_audit()` calls; regex parse of TELEMETRY_MAP for canonical vocabulary.
**Doctrine status corrections:** both artifacts promoted from `ACTIVE (provisional)` to **ACTIVE**. Both gates pass post-corrections.

### Finding 1 — `gate_canonical_dependency_map_sync` named in D4 doctrine but never existed

Same as Batch 5b Finding 1 for CANONICAL_TRUTH_REGISTRY's D4: the artifact's doctrine line stated "Stage C gate `gate_canonical_dependency_map_sync` enforces" but same-turn `grep -n "gate_canonical_dependency_map_sync" scripts/audit.py` returned **zero hits**. Same fabrication-by-omission pattern.

**Closed in this batch.** G391 authored. Tarjan's SCC algorithm + self-loop detection. Tests verify drift catches and allowlist semantics.

### Finding 2 — Import graph has 2 multi-module SCCs and 32 self-loops

Same-turn Tarjan analysis revealed:

**Multi-module SCCs (KNOWN_CYCLES allowlist captures both):**
- `actuals_engine ↔ bsc_engine ↔ core ↔ core_audit ↔ core_kpi` (5-module SCC — core BSC computation graph)
- `credit_doctrine_audit ↔ credit_section_audit_engine` (2-module mutual)

**32 self-loops** (modules importing themselves, primarily for `from utils.X import Y` patterns inside conditional blocks or `if __name__ == "__main__"` self-tests; see e.g. `auth_jwt.py:38`, `db.py:10`, `api_cockpit.py:134`). Per Python's import semantics these are no-ops at runtime (the module is in `sys.modules` at the point of re-import). D5 doctrine still flags them as cycles, but their resolution is a refactor/doctrine-amendment decision deferred to a future arc. G391 surfaces them as INFO with explicit doctrine-exemption note.

**Not closed substantively, captured mechanically.** Future arcs should drain KNOWN_CYCLES to zero by either refactoring the SCCs or amending D5 to explicitly permit these structural patterns.

### Finding 3 — `gate_telemetry_event_naming` named in TELEMETRY_MAP's "Stage C gates planned" section but never existed

TELEMETRY_MAP's "Stage C gates planned" section listed 5 gates by name. Same-turn check:

| Gate | Status before Batch 5d |
|---|---|
| `gate_telemetry_event_naming` | **missing** |
| `gate_event_bus_publisher_purity` | EXISTS (this is G384, registered v10.498 Batch 1b) |
| `gate_event_bus_subscriber_idempotent` | missing |
| `gate_observability_freshness` | missing |
| `gate_audit_event_schema_compliance` | missing |

**Closed in this batch.** G392 authored — verifies every literal `_audit(EVENT, ...)` call in `utils/api*.py` against the canonical vocabulary in TELEMETRY_MAP. Dynamically-constructed event names (f-strings, vars) are silently skipped. Reverse direction (documented-but-not-in-code) reported as INFO, not violation. Stage C gates planned section updated to reflect G384 + G392 status.

The other 3 planned gates (subscriber_idempotent, observability_freshness, audit_event_schema_compliance) remain unauthored — deferred to future arcs.

### Finding 4 — 4 events emitted by code were undocumented in TELEMETRY_MAP

Same-turn AST walk found these literal `_audit()` events in code, NOT in TELEMETRY_MAP:

- `API_LOGIN_FORCE_PW` — emitted since Phase 1 Batch 3b (must_change_password lifecycle)
- `API_AUTH_WHOAMI_DETAILED` — emitted since v10.499 Stage C Batch 2b
- `API_PASSWORD_CHANGE_SUCCESS` — emitted since Phase 2 Arc A
- `API_PASSWORD_CHANGE_FAILED` — emitted since Phase 2 Arc A

**Closed.** All 4 added to TELEMETRY_MAP's Auth section (bumped from "3 events" to "7 events" header). The DOMAIN list in the naming-convention section extended with AUTH and PASSWORD_CHANGE. `API_LOGIN_SUCCESS` detail-field example corrected from `"mode (cookie/bearer)"` to `"mode=bearer"` (Phase 1 Batch 3a rollback of the cookie path).

### What this batch DID

- Authored `gate_canonical_dependency_map_sync` (G391, ~180 LOC) — Tarjan's SCC + self-loop detection + KNOWN_CYCLES allowlist.
- Authored `gate_telemetry_event_naming` (G392, ~110 LOC) — AST scan of `utils/api*.py` + regex parse of TELEMETRY_MAP.
- Registered both gates in the GATES dispatch table.
- Made 4 surgical edits to `TELEMETRY_MAP.md`: 4 new Auth events added; DOMAIN list extended; `API_LOGIN_SUCCESS` detail field cookie/bearer corrected; "Stage C gates planned" section updated with status column showing G384 + G392 ACTIVE.
- Updated classification table: both artifacts ACTIVE.
- Authored `tests/test_gate_dependency_and_telemetry.py` (17 tests, all green).

### What this batch DID NOT do

- Did NOT enforce D1 stratification (transport → manager → engine → foundation). Stratum membership not exhaustively declared; full enforcement is multi-batch.
- Did NOT refactor any of the 2 multi-module SCCs or 32 self-loops. Captured in allowlist; resolution deferred.
- Did NOT author the remaining 3 TELEMETRY_MAP "planned" gates (subscriber_idempotent, observability_freshness, audit_event_schema_compliance). Future arcs.
- Did NOT modify `CANONICAL_DEPENDENCY_MAP.md` content. The artifact's claims held up; only its mechanical enforcement was missing.
- Did NOT change any other artifact's classification.

### Gate count delta

Before this batch: 391 (post-5c).
After this batch: **393** (G391 + G392 added).

---

---

## CGR1 Reality-Check Correction (v10.502 Stage C Arc D2 Batch 5c) — API_CONTRACTS + DATA_DICTIONARY reality-checked

**Date:** 2026-06-10
**Inspected by:** Claude, same-turn AST-walk of `utils/api*.py`, regex parsing of `docs/architecture/API_CONTRACTS.md`, `git check-ignore` + `git ls-files` verification of every tracking claim in `docs/architecture/DATA_DICTIONARY.md`
**Doctrine status corrections:** API_CONTRACTS moves from `ACTIVE (provisional)` to **TRANSITIONAL** (substantive doctrine debt — 195 endpoints undocumented); DATA_DICTIONARY moves from `ACTIVE (provisional)` to **ACTIVE** (4 surgical fixes closed all drift).

### Finding 1 — API_CONTRACTS documents 81 endpoints; actual surface is 276 across 16 routers

Same-turn AST walk of `utils/api*.py`:

```
   81  utils/api.py
    1  utils/api_branding.py
    5  utils/api_capacity_feedback.py
   29  utils/api_cascade.py
    0  utils/api_client.py
   25  utils/api_cockpit.py
   21  utils/api_compliance.py
    8  utils/api_crud.py
    0  utils/api_gateway_developer_portal.py
   16  utils/api_legal.py
   24  utils/api_product.py
   11  utils/api_resource_optimization.py
    1  utils/api_roles.py
   19  utils/api_strategy.py
    0  utils/api_telemetry.py
   43  utils/api_treasury.py
  ----
  276  TOTAL
```

API_CONTRACTS documented 81 endpoints (verified: regex match of method-path table rows). The 195-endpoint gap accumulated primarily during the Stage-C-paused period — v10.412 capacity_feedback, v10.413 cascade, and the entire api_cockpit/compliance/legal/product/strategy/telemetry/treasury family landed without being added to the contract.

**Closed in this batch via mechanical surveillance, not substantive rewrite.** G389 (`gate_api_contract_inventory`) runs in TRANSITIONAL mode: ceiling 300 (surface 276 + breathing room), PASSES while ≤ ceiling, FAILS if surface grows further. INFO summary always emits documented/actual/undocumented counts so a future maintainer sees the gap. Substantive rewrite to document all 276 endpoints is multi-batch work deferred to a future arc.

**Side-effect corrections:** 5 Auth-domain rows updated in API_CONTRACTS — login/logout cookie behavior corrected to Bearer-header-only (cross-ref Batch 3d / Batch 5b corrections); change-password row added with rate-limit + password-policy enforcement notes; whoami-detailed row added with rate-limit-exempt note.

### Finding 2 — DATA_DICTIONARY had 4 incorrect tracking claims; all corrected this batch

Same-turn validation of every `git-tracked` / `gitignored` claim against `git check-ignore -v` + `git ls-files --error-unmatch`:

| Path | Claim | Reality | Action |
|---|---|---|---|
| `data/users.json` | git-tracked | gitignored | Corrected to **gitignored** with cross-ref to GAP-002 closure |
| `data/jwt_blocklist.json` | git-tracked | gitignored (file does not exist; runtime-generated) | Corrected to **gitignored** with runtime-generated note |
| `data/super_user_registry.json` | git-tracked | neither tracked NOR ignored; file does not exist | Marked **ORPHANED** with explicit note for future cleanup |
| `data/observability_metrics.json` | "TBD (likely gitignored)" | tracked | Corrected to **git-tracked** |

DD5 doctrine line corrected: previously claimed "users.json is in git (intentional — seed data with synthetic identities)" — same-turn `git ls-files data/users.json` returned empty, `git check-ignore -v` confirmed `.gitignore:52`. Same narrative confusion source as Batch 5b Finding 2; closed at the doctrine layer here.

**Closed.** G390 (`gate_data_dictionary_tracking_claims`) now runs `git check-ignore -v` + `git ls-files --error-unmatch` against every row's tracking claim. Post-correction: 74/74 rows pass, 0 violations.

### Finding 3 — Both gates registered and tested

- G389 `gate_api_contract_inventory` — AST-walks utils/api*.py via standard library `ast` module; parses contract via regex; computes set difference; reports drift as INFO when within ceiling, violation when over. 8 regression tests including a synthetic 301-endpoint scenario that proves the ceiling triggers FAIL.
- G390 `gate_data_dictionary_tracking_claims` — shells out to `git check-ignore` and `git ls-files` per row; handles globs by sampling first match; tolerates orphan paths (no file + no ignore rule) only for gitignored claims with an INFO note. 8 regression tests including a fresh-git-repo scenario that proves both directions of drift (wrong git-tracked AND wrong gitignored) are caught.

Both pass against the current corrected state.

### What this batch DID

- Authored `gate_api_contract_inventory` (G389) in `scripts/audit.py` with AST walk + regex inventory parse + TRANSITIONAL ceiling enforcement.
- Authored `gate_data_dictionary_tracking_claims` (G390) in `scripts/audit.py` with `git check-ignore` + `git ls-files` validation per row.
- Registered both G389 and G390 in the GATES dispatch table.
- Made 5 surgical edits to `API_CONTRACTS.md`: artifact header Status field → TRANSITIONAL; inventory section header rewritten with doctrine-debt declaration; 3 Auth-domain rows corrected + 2 new rows added for change-password and whoami-detailed.
- Made 5 surgical edits to `DATA_DICTIONARY.md`: 4 row corrections (users.json, jwt_blocklist.json, super_user_registry.json, observability_metrics.json) + DD5 PII doctrine line corrected.
- Updated classification table: API_CONTRACTS → TRANSITIONAL; DATA_DICTIONARY → ACTIVE.
- Authored `tests/test_gate_api_and_data_dictionary.py` (16 tests, all green).

### What this batch DID NOT do

- Did NOT do the substantive API_CONTRACTS rewrite to document all 276 endpoints. Deferred — multi-batch scope.
- Did NOT modify any of the `utils/api*.py` router files. Those are authoritative sources; the contract should follow them, not vice versa.
- Did NOT remove the `data/super_user_registry.json` row from DATA_DICTIONARY. Marked ORPHANED with a note; removal vs creation is a future-arc decision.
- Did NOT change SYSTEM_CONSTITUTION, GOVERNANCE_CLASSIFICATION_REGISTRY, or any other artifact beyond the two reality-checked here.

### Gate count delta

Before this batch: 389 (post-5b).
After this batch: **391** (G389 + G390 added).

---

## CGR1 Reality-Check Correction (v10.503 Phase 3 Arc α Batch α1) — Pipeline API consolidation

**Type:** Architectural drift correction (presentation-canonical alignment).
**Scope:** `utils/api.py` pipeline endpoints + new `utils/api_pipeline_models.py` + new `scripts/audit.py::gate_pipeline_api_uses_canonical_manager` (G394) + `tests/test_pipeline_api_consolidation.py` + `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 16 amendment.

### Drift identified

The `/api/pipeline/summary` and `/api/pipeline/deals` endpoints in `utils/api.py` were reading `data/pipeline.json` directly via `_load_json("pipeline.json")` while `PipelineManager.get_deals()` (the canonical business-logic layer Streamlit consumes via `pages/3_pipeline.py:67`) was reading the DIFFERENT file `data/pipeline_deals.json`. Two presentation surfaces — same domain — different datasets.

Same-turn verification at commit `b2cf3a4`:
- `PipelineManager().get_deals()` returned **8 records** with canonical Generation B shape (`deal_value`, `product_type`, `staff_name`).
- `/api/pipeline/deals` (JSON path) returned **302 records** with legacy Generation A shape (`amount`, `product`, `staff_name`).
- Stage vocabularies also differed: PipelineManager records use doctrine-aligned stages (Lead, Contacted, Closed Lost); the 302 legacy records use stages not in any `PIPELINE_STAGES_*` constant (Prospecting, Needs Analysis, Credit Review, etc.).

This was documented as Finding D3 in `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 15.1 (authored 2026-06-10 ahead of this batch). It is a direct violation of the established doctrine, "Streamlit stays, React additive, FastAPI canonical — business logic centralized, no duplicate logic across presentation surfaces" (per `docs/REACT_READINESS_AUDIT.md` line 35 + the "zero-streamlit engine" pattern documented across `CHANGELOG_v10.21.md`, `v10.400.md`, `v10.417.md`, `v10.426.md`, `v10.434.md`–`v10.439.md`).

### Resolution

The JSON-fallback branch in each pipeline endpoint was refactored to call `PipelineManager().get_deals()` instead of `_load_json("pipeline.json")`. The PostgreSQL primary path was untouched (the PG schema migration is a separate data-store concern). The response source label was changed from `"json"` to `"pipeline_manager"` to make the new path observable.

Both endpoints now serve 8 records (the canonical PipelineManager dataset). The aggregation logic was updated to prefer `deal_value` over the legacy `amount` field (with fallback), and a previously-hardcoded `lost_count: 0` in the summary endpoint was replaced with a proper Closed Lost count (= 2 on current data; the hardcoded zero was an unflagged bug).

### Gate authored

`G394 gate_pipeline_api_uses_canonical_manager` (`scripts/audit.py`, ~120 LOC). AST-walks `utils/api.py`, locates `pipeline_summary` and `pipeline_deals` function definitions, walks each body for:

- **`_load_json("pipeline.json")` calls** — FAIL if found (the drift pattern).
- **`PipelineManager` or `_PM_for_api` instantiation** — FAIL if absent (the required canonical-manager invocation).

Additionally verifies that `utils/api_pipeline_models.py` exists and exports the three Pydantic models (`PipelineDeal`, `PipelineSummaryResponse`, `PipelineDealsResponse`).

Cost: ~0.05s.

### Counter-test (CGR1 verification — gates that always pass are aspirational)

Same-turn counter-test executed: the `_load_json("pipeline.json")` pattern was reinjected into `pipeline_deals` programmatically, G394 was re-run, and the gate FAILED with two precise violation messages identifying the offending function and the expected fix. The file was then restored, G394 re-run, PASSED. The gate mechanically detects drift in both directions.

### Pydantic schema

`utils/api_pipeline_models.py` (NEW, ~210 LOC) declares the canonical pipeline contract:

- `PipelineDeal` — 29-field model matching `PipelineManager.get_deals()[0]` output exactly. Generation B field names are canonical: `deal_value` (not `amount`), `product_type` (not `product`), `staff_name` (not `rm_name`). Generation A field names are NOT canonical here.
- `PipelineSummaryResponse` — wraps `by_stage` + `totals`.
- `PipelineDealsResponse` — wraps `deals` + `count` + `source`.

All fields except `id`, `client_name`, `stage` are optional. Models accept `extra="allow"` and do NOT raise on validation failure during this batch (non-strict). Strict validation is deferred to a future arc once all transitional records are verified parseable. Same-turn verification: all 8 PipelineManager records parse cleanly through `PipelineDeal.model_validate()` with zero errors.

### Tests

`tests/test_pipeline_api_consolidation.py` (NEW, ~280 LOC) — 10 regression tests, all green:

| # | Test | Confirms |
|---|---|---|
| 1 | `test_g394_is_registered_in_gates_table` | G394 in GATES dispatch |
| 2 | `test_g394_function_exists_and_is_callable` | Function exported |
| 3 | `test_g394_returns_well_formed_result` | Return-shape contract |
| 4 | `test_g394_passes_against_current_code` | Post-α1 state is clean |
| 5 | `test_g394_detects_regression_when_load_json_reintroduced` | Structural counter-test for the AST walker |
| 6 | `test_pydantic_models_module_exists` | File present |
| 7 | `test_pydantic_models_export_expected_classes` | All three classes declared |
| 8 | `test_pydantic_pipeline_deal_parses_real_pipeline_manager_records` | Live data parses cleanly |
| 9 | `test_api_endpoint_response_source_is_pipeline_manager` | Source label updated |
| 10 | `test_pipeline_summary_and_deals_use_consistent_data_source` | End-to-end aggregation arithmetic |

### Audit Section 16 amendment

The PIPELINE_DOMAIN_AUDIT document was extended with Section 16 (append-only; Sections 1-15 untouched). Section 16 explicitly references the established "Streamlit stays, React additive, FastAPI canonical" doctrine with citations to REACT_READINESS_AUDIT.md and 5 specific changelogs. It corrects the framing of Section 15.12 (which proposed "α1 = data consolidation") to the architecturally precise "α1 = route API through canonical manager." Section 16.3 also refines the Arc α sequence from 7 to 10 numbered batches based on the deep anatomy findings.

### Classification updates

- **PIPELINE_DOMAIN_AUDIT.md** — added as a new ACTIVE artifact in `docs/architecture/`. Audit document established 2026-06-10; Section 16 amendment same-day per append-only discipline.

(The classification table at the top of this index does not yet contain a PIPELINE_DOMAIN_AUDIT row; this is a candidate addition for the next governance batch.)

### What this batch DID

- Refactored `pipeline_summary` and `pipeline_deals` in `utils/api.py` to route through `PipelineManager` instead of `_load_json("pipeline.json")`.
- Created `utils/api_pipeline_models.py` with Pydantic models for the canonical pipeline shape.
- Authored `gate_pipeline_api_uses_canonical_manager` (G394) in `scripts/audit.py`. Registered above G393 in GATES dispatch.
- Authored `tests/test_pipeline_api_consolidation.py` (10 tests, all green).
- Appended Section 16 to `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` documenting the doctrine reference and corrected Arc α framing.
- Appended this CGR1 correction.
- Appended Batch α1 entry to REVIVAL_LEDGER.md at the top of the entries section (reverse-chronological convention).

### What this batch DID NOT do

- Did NOT delete `data/pipeline.json`. The file is now unreferenced by the API path; archival decision deferred.
- Did NOT modify `PipelineManager` itself. Its file (`data/pipeline_deals.json`) remains the canonical store.
- Did NOT touch the PostgreSQL primary path in either endpoint. PG schema migration is a separate concern.
- Did NOT add any new endpoints. CRUD remains α3's scope.
- Did NOT add server-side cascade scope enforcement (GAP-001). That's α2.
- Did NOT write any React frontend code. React UI work begins after Arc α closes.
- Did NOT promote Pydantic validation from non-strict to strict. Future-arc concern.
- Did NOT modify SYSTEM_CONSTITUTION, CANONICAL_TRUTH_REGISTRY, or any other doctrine artifact beyond REVIVAL_LEDGER, this index, and PIPELINE_DOMAIN_AUDIT.

### Gate count delta

Before this batch: 393 (post-Arc-D2).
After this batch: **394** (G394 added).

---

## CGR1 Reality-Check Correction (v10.504 Phase 3 Arc α Batch α2) — Pipeline cascade scope enforcement

**Type:** Architectural drift correction (presentation-canonical asymmetry).
**Scope:** `utils/api.py` pipeline endpoints + new `utils/api_pipeline_scope.py` helper + new `scripts/audit.py::gate_pipeline_api_enforces_cascade_scope` (G395) + `tests/test_pipeline_scope_enforcement.py`.

### Drift identified

Before α2, the FastAPI pipeline endpoints (`/api/pipeline/summary` and `/api/pipeline/deals`, post-α1 routed through PipelineManager) returned the full PipelineManager dataset to any authenticated caller — no server-side scope filtering. The Streamlit page `pages/3_pipeline.py:47` filtered client-side via `get_visible_staff(user_data, staff_scores)` from `utils.core_audit`. **The cascade RBAC logic existed and was correctly applied for Streamlit; the API path simply did not invoke it.**

This was documented as GAP-001 in `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 10:

> "Cascade visibility not server-side. `/api/pipeline/deals` returns all deals regardless of caller. RBAC is currently client-side in Streamlit via `get_visible_staff()`. Production go-live REQUIRES server-side scope enforcement in every loan-workflow endpoint."

Section 15.10 of the same audit traced the existing visibility chain end-to-end:

```
1. Page imports get_visible_staff from utils.core_audit
2. Caller invokes: vis_staff = get_visible_staff(user_data, staff_scores)
3. get_visible_staff walks REPORTING_TREE per role
4. Page extracts vis_names + vis_codes from filtered DataFrame
5. Page filters deals by staff_name in vis_names OR staff_code in vis_codes
6. Backup deals appended regardless (out-of-tree exception)
```

The API path was missing steps 2-5 entirely.

### Resolution

A new module `utils/api_pipeline_scope.py` was created. It exports three public functions:

- `get_staff_roster()` — caches `data/staff_register.xlsx` (1,438 rows verified same-turn) for 60 seconds. Thread-safe via module-level lock. Lazy-imports pandas.
- `get_visible_staff_codes(user_data) -> set[str]` — wraps the canonical `get_visible_staff(user_data, get_staff_roster())` call and projects the result to a Python set of staff codes. Always includes the caller's own staff_code as a floor (safe default).
- `filter_deals_by_visible_codes(deals, visible_codes)` — set-membership filter on `staff_code` OR `portfolio_owner_code` (per audit Section 15.4 portfolio-sovereignty model — the portfolio owner sees their deals even when another RM is actively pursuing them).

Plus `invalidate_staff_roster_cache()` for admin endpoints (future arc) and tests.

**The cascade-walk logic itself is NOT reimplemented.** The new module is a thin server-side adapter that supplies the roster DataFrame the API path otherwise lacks. If `REPORTING_TREE` changes, the API visibility changes automatically alongside Streamlit visibility — no duplicate-logic drift possible.

Both `/api/pipeline/summary` and `/api/pipeline/deals` now apply the filter BEFORE any other processing (stage/category/unit filters, pagination, aggregation). The PostgreSQL primary path is untouched (data store concern, deferred).

### Gate authored

`G395 gate_pipeline_api_enforces_cascade_scope` (`scripts/audit.py`, ~130 LOC). AST-walks `utils/api.py`, locates `pipeline_summary` and `pipeline_deals` functions, walks each body for:

- **`get_visible_staff_codes(user)` calls** — FAIL if absent.
- **`filter_deals_by_visible_codes(...)` calls** — FAIL if absent.

Additionally verifies `utils/api_pipeline_scope.py` exists and exports the three required functions.

Cost: ~0.05s.

### Counter-test (CGR1 verification)

Same-turn counter-test executed: the scope filter block was removed programmatically from `pipeline_deals`, G395 was re-run, and the gate FAILED with two precise violations identifying both the missing `get_visible_staff_codes` and missing `filter_deals_by_visible_codes` calls. The file was then restored, G395 re-run, PASSED. The gate mechanically detects scope-enforcement drift.

### Live behavior verification

Tested against the real PipelineManager dataset (8 deals) + real staff_register.xlsx (1,438 rows):

| Caller | Role / unit | Visible codes | Deals returned |
|---|---|---|---|
| `ADMIN001` (System Admin) | admin | 1,438 (full roster) | 8 of 8 |
| `300722` Rodgers Weru | Teller, Thika | 1 (self only) | 1 (D0006, owned by 300722) |
| `300600` Helena Mwaburi | Branch Manager, Dagoretti | 6 (her branch staff) | 1 (D0005, owned by 300600) |
| `300100` (Random Teller) | Teller, Eastleigh | 1 (self only) | 0 (no deals owned by 300100) |

Behavior matches the canonical `get_visible_staff` cascade walk exactly, because the same function is being invoked.

### Tests

`tests/test_pipeline_scope_enforcement.py` (NEW, ~290 LOC) — 13 regression tests, all green:

| # | Test | Confirms |
|---|---|---|
| 1-3 | G395 registration / function exists / well-formed result | Gate is reachable |
| 4 | G395 passes against current code | Post-α2 state clean |
| 5-7 | Scope helper module structural tests | Helper file + 3 functions + endpoints invoke them |
| 8 | Admin sees all pipeline deals | Live verification (admin) |
| 9 | Teller sees only own deals | Live verification (self-only) |
| 10 | Branch Manager sees branch staff deals | Live verification (unit-scoped) |
| 11 | Random user with no deals sees none | Live verification (empty visibility) |
| 12-13 | Roster cache behavior (TTL + invalidation) | Cache mechanics |

19/19 cumulative tests (α2 13 + α1 10 + Arc D2 G393 9) pass — full prior surface intact.

### What this batch DID

- Authored `utils/api_pipeline_scope.py` (~210 LOC) — server-side cascade scope adapter wrapping the canonical `get_visible_staff` function.
- Surgical edits to `utils/api.py` to invoke the scope helper in both pipeline endpoints. ~10 lines added per endpoint; PostgreSQL paths untouched.
- Authored `gate_pipeline_api_enforces_cascade_scope` (G395) in `scripts/audit.py`. Registered above G394 in GATES dispatch.
- Authored `tests/test_pipeline_scope_enforcement.py` (13 tests, all green).
- Appended this CGR1 correction.
- Appended Batch α2 entry to REVIVAL_LEDGER.md at top of entries section.

### What this batch DID NOT do

- Did NOT modify the PostgreSQL primary path. PG-side scope (requires `WHERE staff_code IN (...)` parameterized SQL) is a separate concern; covered in a later arc once data store migration roadmap is clearer.
- Did NOT modify `utils.core_audit.get_visible_staff` or any REPORTING_TREE config. The canonical function stays as-is; α2 is purely additive (server-side adapter wrapping it).
- Did NOT alter Streamlit pipeline page. Streamlit's pre-existing client-side filter continues to work; α2 simply makes the API match.
- Did NOT add CRUD endpoints (α3 scope).
- Did NOT add LMS handoff endpoint (α4 scope).
- Did NOT write any React frontend code.

### Gate count delta

Before this batch: 394 (post-α1).
After this batch: **395** (G395 added).

---

## CGR1 Reality-Check Correction (v10.505 Phase 3 Arc α Batch α3) — Pipeline CRUD + advance + LMS allowlist

**Type:** First mutation-capable batch in Arc α. Architectural drift correction (presentation-canonical asymmetry — Streamlit could mutate pipeline state, API could not). One new CRITICAL enforcement gate. One new server-side helpers module. Pydantic model extensions for mutations.

**Scope:** `utils/api.py` (three new endpoints) + new `utils/api_pipeline_mutations.py` (helpers + load-bearing constants) + extended `utils/api_pipeline_models.py` + new `scripts/audit.py::gate_pipeline_api_crud_present` (G396) + `tests/test_pipeline_crud_advance.py` (19 tests).

### Drift identified

Before α3, the FastAPI pipeline surface was read-only — α1 (canonical-manager routing) and α2 (cascade scope enforcement) made reads correct, but no API endpoint could create, update, or transition a deal. Streamlit page `pages/3_pipeline.py` had all three flows (add at 940-988, update at 1310-1314, stage change at 1310-1340) plus the consequential LMS handoff at 1239-1281 (auto-create LoanApplication on advance to LMS stages). Per the established "Streamlit stays, React additive, FastAPI canonical" doctrine, the API surface must reach Streamlit parity for the React frontend to be production-viable.

The audit's Section 15.12 + Section 16.3 framed this as "α3 — Pipeline CRUD endpoints — POST/PUT/advance with BSC trigger calls and draft state." Same-turn inspection at α3 scoping time revealed this was three or four distinct concerns that wouldn't fit in one disciplined batch.

### Resolution (Option C from three options surfaced)

The user was offered three explicit options:
- **A.** Reject LMS-stage advances with 400.
- **B.** Allow LMS-stage advances, document the gap (creates inconsistent state).
- **C.** Allow advances only up to a documented stage ceiling, with the allowlist explicit in code and audit gate.

The user picked C. Implementation:

`utils/api_pipeline_mutations.py` (NEW) declares two stage sets that must be disjoint:

```python
ALLOWED_ADVANCE_STAGES = {  # 15 stages from canonical vocabularies
    "Lead", "Contacted", "Qualified", "Proposal", "Negotiation",
    "Compliance", "Closed Won", "Closed Lost",
    "Information Gathered", "Documentation Complete", "Account Opened",
    "Pitched", "Negotiating", "Funded", "Open",
}

LMS_DEFERRED_STAGES = {  # 7 stages — must match audit Section 15.7
    "Credit Review", "Approval", "Bank Approval", "Credit Committee",
    "Documentation", "Vetting", "Disbursed",
}
```

`validate_advance_target(new_stage)` returns `(False, reason)` for any stage in `LMS_DEFERRED_STAGES` with the message `"Stage 'X' requires LMS handoff (planned for Arc α4). Use the Streamlit pipeline page for this transition until α4 lands."` The advance endpoint calls this first; if rejected, returns HTTP 400 + emits `API_PIPELINE_ADVANCE_REJECTED` audit event. Similarly `validate_create_payload` rejects creation directly at LMS stages.

### Three endpoints added

`POST /api/pipeline/deals` (status 201) — validates payload via `validate_create_payload` → calls `PipelineManager.add_deal(deal_dict)` (the canonical engine, per α1's G394) → emits `DEAL_ADDED` audit (matching Streamlit's emission convention at page line 965) → calls `emit_bsc_trigger(username)` (server-side equivalent of Streamlit's `_bsc_trigger(uname, "K041")` pattern) → calls `invalidate_pipeline_caches` so the next GET reflects the new deal → returns the created deal with its PipelineManager-assigned id.

`PUT /api/pipeline/deals/{deal_id}` — verifies deal exists (404 if not) → applies cascade scope check via α2's `get_visible_staff_codes` (403 if out of scope) → calls `PipelineManager.update_deal(deal_id, updates, user)` with `exclude_unset=True` so absent keys are not touched → emits `DEAL_UPDATED` → BSC + cache invalidation.

`POST /api/pipeline/deals/{deal_id}/advance` — `validate_advance_target` (rejects LMS stages) → 404 check → cascade scope check → `PipelineManager.update_stage` (PM logs the stage change as an activity in its own stream) → emits `API_PIPELINE_ADVANCED` with old→new transition → BSC + cache invalidation.

### Gate authored

`G396 gate_pipeline_api_crud_present` (`scripts/audit.py`, ~190 LOC). AST walks check:
- All three endpoint functions exist in `utils/api.py`
- `utils/api_pipeline_mutations.py` exists with the two stage sets and four required helper functions
- `pipeline_deal_create` calls `validate_create_payload` (required-field enforcement at create surface)
- `pipeline_deal_advance` calls `validate_advance_target` (the **load-bearing Option C guarantee** at advance surface)

Cost: ~0.05s.

### Counter-test (CGR1 verification)

Same-turn counter-test executed: the `validate_advance_target` call was removed programmatically from `pipeline_deal_advance`, G396 was re-run, and the gate FAILED with the precise violation: `\`pipeline_deal_advance\` does not call \`validate_advance_target\` — the LMS-stage allowlist is not enforced; advance to Credit Review/Approval/Vetting/etc. would succeed without creating the required LoanApplication (α4's scope)`. After restore, G396 PASSED again. The gate mechanically catches Option C drift.

### Tests

`tests/test_pipeline_crud_advance.py` (NEW, ~290 LOC) — 19 regression tests, all green:

| # | Tests | Confirms |
|---|---|---|
| 1-4 | G396 registration / callable / well-formed / passes | Gate plumbing |
| 5-6 | Three endpoints exist + have route decorators | Endpoint surface |
| 7 | Good payload validates | Create happy path |
| 8 | Missing required field rejected with name | Required-field enforcement |
| 9 | Negative deal_value rejected | Numeric sanity |
| 10 | LMS stage on create rejected with α4 pointer | Option C at create surface |
| 11 | All 7 LMS stages rejected on advance with α4 pointer | Option C at advance surface (load-bearing) |
| 12 | Standard stages accepted on advance | Allowed-set correctness |
| 13 | ALLOWED and LMS_DEFERRED sets disjoint | Invariant: no contradictions |
| 14 | LMS_DEFERRED_STAGES matches audit Section 15.7 exactly | Code-audit alignment |
| 15-17 | Pydantic mutation models parse / enforce required fields | Schema correctness |
| 18 | emit_bsc_trigger returns False for empty username | Defensive behavior |
| 19 | invalidate_pipeline_caches doesn't raise | Idempotent + safe |

51 cumulative tests (19 α3 + 13 α2 + 10 α1 + 9 Arc D2) pass. Full prior surface intact.

### What this batch DID

- Created `utils/api_pipeline_mutations.py` with the load-bearing stage sets + helpers.
- Extended `utils/api_pipeline_models.py` with four new mutation models.
- Added three new endpoints to `utils/api.py` (POST/PUT/advance).
- Authored `gate_pipeline_api_crud_present` (G396) with structural + behavioral checks.
- Authored 19-test regression suite.
- Appended Batch α3 entry to REVIVAL_LEDGER.
- Appended this CGR1 correction.

### What this batch DID NOT do

- Did NOT implement LMS handoff. α3 explicitly defers to α4.
- Did NOT add DELETE endpoint. Cancellation flow is α5 scope.
- Did NOT add draft state endpoints (`DRAFT_COMPLETED` / `DRAFT_DISCARDED`).
- Did NOT modify `PipelineManager` or the canonical cascade-walk function.
- Did NOT touch the PostgreSQL primary path.
- Did NOT write React frontend code.

### Gate count delta

Before this batch: 395 (post-α2).
After this batch: **396** (G396 added).

---

## CGR1 Reality-Check Correction (v10.506 Phase 3 Arc α Batch α4) — Pipeline LMS handoff + two latent Streamlit bugs

**Type:** Largest batch in Arc α. Closes the pipeline→credit bridge. One new CRITICAL enforcement gate. Two latent Streamlit bug fixes shipped in the canonical method (Streamlit-side fix deferred to migration batch). First time in this arc that previous-batch behavior changes (one α3 test inverted).

**Scope:** `utils/core.py` (+`LoanApplicationManager.create_from_pipeline_deal`) + `utils/api_pipeline_mutations.py` (+`is_lms_handoff_transition`, +`handle_lms_handoff`, modified `validate_advance_target`) + `utils/api_pipeline_models.py` (extended `PipelineDealMutationResponse`) + `utils/api.py` (extended `pipeline_deal_advance`) + `scripts/audit.py` (+G397) + inverted α3 test + new α4 regression tests.

### Drift identified

α3 deliberately deferred LMS handoff (Option C from the three-option design discussion at α3 scoping time). The advance endpoint rejected LMS-stage transitions with HTTP 400 + pointer to α4. The Streamlit page had the handoff working (lines 1239-1287 of `pages/3_pipeline.py`), but the FastAPI surface couldn't drive a deal past `Compliance` stage. The React frontend could create deals, update them, advance them through the pre-credit stages — but couldn't push them into the credit workflow.

This was the largest single gap in the pipeline domain API. Without α4, the FastAPI surface was only useful for pre-application work; everything from Credit Review onward required Streamlit.

### Two latent Streamlit bugs surfaced during inspection

Inspecting the Streamlit handoff code (lines 1239-1287) revealed two real bugs that have been in production for months:

**Bug #1 — ID collision via `len(apps)+1`.**

Streamlit's formula:
```python
"id": f"LMS{str(len(_lam.apps)+1).zfill(5)}"
```

Same-turn inspection of `data/loan_applications.json` found:
- 724 apps total
- IDs `LMS00001` through `LMS00725`
- **One gap somewhere** in the sequence (some app number is missing)
- Streamlit formula would yield `LMS00725` for the next handoff
- But `LMS00725` already exists → collision

Any deal advanced to Credit Review today via Streamlit would attempt to create `LMS00725` and either crash on save or overwrite the existing record depending on JSON write semantics. This is a real bug. It hasn't been triggered yet because no one's tested this code path recently with the current data shape.

**Bug #2 — `product` field empty for Gen B deals.**

Streamlit's mapping:
```python
"product": _sd.get("product",""),
```

Generation B canonical deals (established by α1 — `pipeline_deals.json` records) use `product_type`, not `product`. The `_sd.get("product","")` returns empty string for those records. Result: applications created via Streamlit handoff have empty `product` field. Downstream, `LoanApplicationManager.bsc_actuals()` (line 5328) routes by product substring matching — an empty string falls into the MSME bucket as the default. So all Streamlit-created applications since the Gen B transition have been miscounted in BSC actuals.

### Resolution

`utils/core.py` extended with `LoanApplicationManager.create_from_pipeline_deal(deal, username)` — the canonical handoff method. Key properties:

- **Idempotent.** Checks for existing application via `pipeline_deal_id` linkage; returns existing app's id if found, no duplicate created. Safe to re-call.
- **Safe ID generation.** Uses `max(existing_ids) + 1`, not `len + 1`. Fixes Bug #1.
- **Canonical field mapping.** Reads `product_type` first, falls back to `product`. Fixes Bug #2.
- **Swim lane bands match Streamlit exactly.** `Express` ≤5M, `Complex` ≥100M, `Standard` between.
- **Provenance breadcrumbs.** New `created_by` and `created_via` fields on the application record distinguish API-created from Streamlit-created records. Useful for forensics during the migration window.
- **Defensive.** Returns `None` for empty/None deal, deal without id, deal lacking required fields. The caller decides how to handle.

`utils/api_pipeline_mutations.py` extended:

- `validate_advance_target` modified: LMS stages now PERMITTED (was rejected in α3). The docstring explicitly documents the α3→α4 doctrine transition.
- `is_lms_handoff_transition(old_stage, new_stage)` — encapsulates the trigger condition. Matches Streamlit page line 1242 exactly: fires when entering an LMS stage AND it's a real transition.
- `handle_lms_handoff(deal, old_stage, new_stage, username)` — the orchestrator. Returns `(triggered, app_id, error)`. Failure semantics: handoff failure does NOT roll back advance.

`utils/api.py::pipeline_deal_advance` extended with handoff invocation after successful `pm.update_stage()`. Emits `LMS_APPLICATION_CREATED` (matching Streamlit's emission convention) on success, `API_PIPELINE_ADVANCE_LMS_FAILED` on failure. Response includes `lms_triggered`, `lms_application_id`, `lms_error` for caller transparency.

### Gate authored

`G397 gate_pipeline_advance_triggers_lms_handoff` (`scripts/audit.py`, ~180 LOC). Four checks:

1. AST walk: `pipeline_deal_advance` calls `handle_lms_handoff`.
2. AST walk: mutations module exports `handle_lms_handoff` and `is_lms_handoff_transition`.
3. AST walk: `LoanApplicationManager` class in `utils/core.py` defines `create_from_pipeline_deal` method.
4. Behavioral: load mutations module and call `validate_advance_target("Credit Review")` — must return `(True, "")`. Sanity check that α3 Option C was actually superseded, not just superficially.

Cost: ~0.2s (core.py is large).

### Counter-test (CGR1 verification)

Same-turn counter-test: the `handle_lms_handoff` block was removed programmatically from `pipeline_deal_advance`, G397 was re-run, and the gate FAILED with the precise message: "advance to an LMS stage will NOT create the linked LoanApplication; α4 doctrine broken; deals will sit at Credit Review/Approval/etc. without an application record". After restore, G397 PASSED again.

### Tests

`tests/test_pipeline_lms_handoff.py` (NEW, ~340 LOC) — 19 regression tests, all green. Highlights:

- G397 plumbing (4)
- α3→α4 doctrine transition tests (2) — LMS stages now ACCEPTED on advance, STILL REJECTED on create
- `is_lms_handoff_transition` covers all 4 trigger cases (enter LMS, non-LMS advance, no-op, LMS→LMS)
- `create_from_pipeline_deal` live tests using `monkeypatch` to redirect `DATA_DIR` to a temp directory copy of the real `loan_applications.json` — happy path, idempotency, all 6 swim-lane band sample points, `product_type` preference, `product` fallback
- **The latent-bug fix test** — `test_create_from_pipeline_deal_id_uses_max_plus_one_not_len_plus_one` directly verifies the canonical method produces the right next ID against the real data state where `len + 1` would collide
- Defensive: empty/None/no-id all return None

**Inverted from α3:** `tests/test_pipeline_crud_advance.py::test_validate_advance_target_rejects_lms_stages` (α3 doctrine: reject) is replaced with `test_validate_advance_target_no_longer_rejects_lms_stages_post_alpha4` (α4 doctrine: accept). The docstring records the doctrine transition explicitly. Git history preserves the original assertion. **First time in Arc α that previous-batch behavior is changed.**

70 cumulative tests pass: 19 α4 + 19 α3 (one inverted) + 13 α2 + 10 α1 + 9 Arc D2 G393.

### What this batch DID

- Added `LoanApplicationManager.create_from_pipeline_deal` canonical method.
- Added `is_lms_handoff_transition` + `handle_lms_handoff` orchestrator helpers.
- Modified `validate_advance_target` to permit LMS stages.
- Extended `pipeline_deal_advance` endpoint with handoff invocation.
- Extended `PipelineDealMutationResponse` with 3 optional LMS fields.
- Authored `gate_pipeline_advance_triggers_lms_handoff` (G397).
- Authored 19-test regression suite.
- Inverted one α3 test (with explicit docstring transition record).
- Documented two latent Streamlit bugs found during inspection.
- Appended Batch α4 entry to REVIVAL_LEDGER.
- Appended this CGR1 correction.

### What this batch DID NOT do

- Did NOT migrate `pages/3_pipeline.py:1239-1287` to use the new canonical method. Streamlit's inline handoff continues to work (with its latent bugs). Migration is a small follow-up batch — could fold into the ORGANS_REGISTRY housekeeping batch slated for ~α7-α8.
- Did NOT touch the PostgreSQL primary path.
- Did NOT add manager queues (α6), conflict resolution (α5), per-deal permissions (α7), Loan Application endpoints (α8), Credit Admin endpoints (α9).
- Did NOT write React frontend code.

### Gate count delta

Before this batch: 396 (post-α3).
After this batch: **397** (G397 added).

### Streamlit/API divergence note

After α4, the FastAPI surface and Streamlit surface produce **subtly different LoanApplication records**:
- Streamlit-created records: empty `product` field (Bug #2), risk of ID collision (Bug #1), no `created_by`/`created_via` provenance fields.
- API-created records: correct `product` field, safe ID generation, provenance breadcrumbs (`created_via: "api_pipeline_advance"`).

This divergence is **deliberate and time-bounded** — it lasts only until the migration batch that switches Streamlit to use the canonical method. The `created_via` field lets forensics distinguish which surface created any given record during the migration window.

---
