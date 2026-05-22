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
| CANONICAL_TRUTH_REGISTRY.md                | ACTIVE (provisional)       | Reality check scheduled Batch 2                                    |
| GOVERNANCE_CLASSIFICATION_REGISTRY.md      | ACTIVE (provisional)       | Self-referential; supplemented by this index                       |
| SYSTEM_CONSTITUTION.md                     | ACTIVE                     | Received CGR1 article in this batch                                |
| API_CONTRACTS.md                           | ACTIVE (provisional)       | Reality check scheduled Batch 2                                    |
| ORGANS_REGISTRY.md                         | ACTIVE (provisional)       | Reality check scheduled Batch 3                                    |
| CANONICAL_DEPENDENCY_MAP.md                | ACTIVE (provisional)       | D2 enforced by G384, passed; broader coverage scheduled Batch 2    |
| DATA_DICTIONARY.md                         | ACTIVE (provisional)       | Reality check scheduled Batch 2                                    |
| TELEMETRY_MAP.md                           | ACTIVE (provisional)       | T2 enforced by G384, passed; broader coverage scheduled Batch 2    |
| DIGITAL_TWIN_ARCHITECTURE.md               | TRANSITIONAL (provisional) | Twin exists; full parity ASPIRATIONAL; reality check Batch 4       |
| RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md | TRANSITIONAL (provisional) | G373-G380 ladder ACTIVE; full Olympic certification TRANSITIONAL   |
| REVIVAL_LEDGER.md                          | ACTIVE                     | This is the operational log; always reflects reality by definition |
| CHANGELOG_MASTER.md                        | ACTIVE                     | CM1 doctrine ACTIVE since v10.498                                  |
| (~18 remaining artifacts)                  | ACTIVE (provisional)       | Reality check scheduled Batch 5-7                                  |

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

**End of GOVERNANCE_REALITY_INDEX.md (initial v10.498 Stage C Batch 1b).**
