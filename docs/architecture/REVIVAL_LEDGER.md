# A2Z Blueprint MIS 360 — Revival Ledger

**Type:** Constitutional artifact, system-wide governance
**Authority level:** Cross-cutting (chronological index over all domains)
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 6)
**Last updated:** 2026-05-22
**Owner:** Architecture / Doctrine
**Authoritative source:** This document (append-only ledger)
**Machine-readable equivalent:** `REVIVAL_LEDGER.json`
**Companion artifact:** `CHANGELOG_MASTER.md`

---

## Purpose

The Revival Ledger is the **chronological harmonization log** of the A2Z system. Where the constitutional artifacts (Waves 1-5) declare _what_ the system is, this ledger records _what was done, when, why, and by whom_ to bring it into compliance with that constitution.

This is the system's "lab notebook" — an append-only record of:

- **Harmonization events** — when canonical drift was identified and remediated
- **Migration milestones** — PostgreSQL migration progress, twin→production cutovers
- **Certification milestones** — when each rung G357-G380 was first achieved
- **Vulnerability fixes** — V-001 through V-009 (and forward)
- **Governance evolution** — the v10.497 program itself, and all future amendments

Per Article XII of `SYSTEM_CONSTITUTION.md`: constitutional changes are append-only. The Revival Ledger is where they appear.

---

## Doctrine

**RL1 — Append-only.** Entries are never deleted. Corrections are themselves new entries citing the original.

**RL2 — One entry per harmonization event.** A discrete change (a batch, a vulnerability fix, a certification rung achieved) gets one entry. Bundling unrelated changes into a single entry is a violation.

**RL3 — Every entry has a rationale.** "Why was this done?" must be present. Mechanical changes without rationale are not entries — they're noise.

**RL4 — Forward references are valid.** An entry can declare future intent ("PostgreSQL migration scheduled for v10.510"). Future intent is recorded but not enforced until realized.

**RL5 — The ledger is the canonical migration registry.** PostgreSQL migration per-file status, twin→production cutover playbook, and similar long-running migrations live here. Spreading them across multiple files fragments the migration trail.

---

## Ledger entries (reverse-chronological, newest first)

Each entry follows this shape:

```
### [DATE] [BATCH_ID] — [TITLE]

**Type:** [governance / harmonization / migration / certification / vulnerability / amendment]
**Owner:** [team or individual]
**Rationale:** [why this happened]
**Changes:** [what changed]
**Verification:** [how we know it worked]
**Cross-references:** [related entries, gates, articles]
```

---

### 2026-05-22 — v10.498 Stage C Batch 1 — First five enforcement gates wired

**Type:** governance
**Owner:** Joshua + Claude (Stage C kickoff)
**Rationale:** Stage B (v10.497) shipped 32 constitutional artifacts to
`docs/architecture/`, declaring contracts and identifying ~35 planned
enforcement gates. Stage C begins mechanically wiring those gates into
`scripts/audit.py`. Batch 1 ships the five CRITICAL-severity gates that
have no grace period per the rollout schedule in this ledger.

**Changes:**

- `scripts/audit.py` — added 5 gate function bodies (G383–G387)
- `scripts/audit.py` — added 5 registry tuples at top of GATES list
- `docs/CHANGELOG_v10498.md` — first per-batch CHANGELOG (CM1 doctrine
  in force)
- Commit pending

**Gates added:**

| ID   | Function                                          | Constitutional source                          |
| ---- | ------------------------------------------------- | ---------------------------------------------- |
| G383 | `gate_v10498_no_require_role_collision`           | ROLE_GOVERNANCE OI-1                           |
| G384 | `gate_v10498_event_bus_publisher_purity`          | TELEMETRY_MAP T2 / CANONICAL_DEPENDENCY_MAP D2 |
| G385 | `gate_v10498_react_no_tenant_strings`             | FRONTEND_GOVERNANCE FE3                        |
| G386 | `gate_v10498_no_unregistered_model_in_production` | AI_GOVERNANCE AI1                              |
| G387 | `gate_v10498_agent_scope_declared`                | AI_GOVERNANCE AI7                              |

**Expected initial state:** G383 will fail until `auth.py::require_role` is
renamed to `require_module_access` (scheduled for Phase 1 Step 1.4+).
G386 likely fails for several engines (each ~5-20 LOC remediation).
G387 likely fails or passes vacuously depending on `utils/agents/`
contents (OI-46). G384 and G385 status TBD by first run.

This is the **expected pattern**: ship the gate to make doctrine
mechanically detectable, then drive violations to zero in subsequent
batches.

**Verification:**

- Syntax check on `scripts/audit.py` passes
- Each gate is importable as `scripts.audit.gate_v10498_*`
- Each gate runs individually without raising exceptions
- Full audit suite includes G383–G387 in report

**Open items added:**

- OI-63: Audit historical `event_bus.publish()` callsites in transports
  (Stage C Batch 2)
- OI-64: Register existing 11 production AI engines with
  `mlops_model_registry` (Stage C Batch 2-3)
- OI-65: Survey `utils/agents/` for existing modules; backfill
  AGENT_SCOPE (Stage C Batch 2)

### 2026-05-22 — v10.497 Stage B — Constitutional governance program completion

**Type:** governance
**Owner:** Joshua + Claude (collaborative authorship session)
**Rationale:** System had grown to 412 audit gates, 526 utils modules, 80+ API endpoints with no consolidated constitution. Honest assessment identified that mechanical enforcement gates outpaced declarative governance. The governance constitution program addresses this by authoring 32 constitutional artifacts on the `feature/governance-constitution` branch before resuming feature development.

**Changes:**

- Wave 1 (commit `185eb4c`): 6 files — CANONICAL_TRUTH_REGISTRY, GOVERNANCE_CLASSIFICATION_REGISTRY, SYSTEM_CONSTITUTION
- Wave 2 (commit `74b4460`): 6 files — ROLE_GOVERNANCE, RBAC_MATRIX, API_CONTRACTS
- Wave 3 (commit `7814efa`): 4 files — ORGANS_REGISTRY, CANONICAL_DEPENDENCY_MAP
- Wave 4 (commit `b503773`): 6 files — DATA_DICTIONARY, TELEMETRY_MAP, FRONTEND_GOVERNANCE
- Wave 5 (commit `40d124e`): 6 files — DIGITAL_TWIN_ARCHITECTURE, AI_GOVERNANCE, RESILIENCE_AND_CERTIFICATION_GOVERNANCE
- Wave 6 (this commit, pending): 4 files — REVIVAL_LEDGER, CHANGELOG_MASTER

**Verification:**

- All artifacts under `docs/architecture/` on `feature/governance-constitution` branch
- 32 files (16 .md + 16 .json), ~280 KB human-readable + ~150 KB machine-readable
- 56 open items (OI-1 through OI-56) catalogued for Stage C and follow-up batches
- ~25 Stage C enforcement gates planned across the wave outputs

**Cross-references:**

- All v10.497 governance artifacts in `docs/architecture/`
- Next phase: Stage C (mechanical enforcement gate wiring with tiered Visibility → Grace → Full rollout per GOVERNANCE_CLASSIFICATION_REGISTRY)
- Resumes: Phase 1 Step 1.4 (whoami-detailed) after Stage C completes

---

### 2026-05-21 (prior session) — v10.497 P1.3 — JWT cookie + revocation

**Type:** vulnerability + feature
**Owner:** Joshua + Claude (prior session)
**Rationale:** Step 1.3 of Phase 1 JWT hardening. Implemented httpOnly cookie auth, dual-source extraction (cookie wins over Bearer), blocklist via `data/jwt_blocklist.json`, `require_role(roles)` factory, cookie-based login + revocation-on-logout.

**Changes:**

- `utils/auth_jwt.py` — cookie auth, blocklist persistence, dual-source extraction
- `data/jwt_blocklist.json` — append-only revocation list
- Test credentials standardized: `william001` / `EcoStaff0001` (MD, staff_code 300001)
- Commit `c25a8e9` on `feature/v10.497-jwt-auth` (later merged or co-existed with constitution branch)

**Verification:** End-to-end test executed in prior session:

1. Login with `william001` → cookie set
2. `whoami` returns 200 with username
3. Logout → cookie cleared, jti added to blocklist
4. Subsequent `whoami` with stale token → 401 "Token revoked"

**Cross-references:**

- `CANONICAL_TRUTH_REGISTRY::authentication_and_session_tokens`
- V-001, V-003 (password security, prior remediation)
- OI-1 (require_role collision between Streamlit auth.py and FastAPI auth_jwt.py)

---

### 2026-05-21 (prior session) — v10.497 P0 — shadcn/ui pivot

**Type:** harmonization
**Owner:** Joshua + Claude (prior session)
**Rationale:** Pre-existing bespoke React primitives (v10.496) created maintenance burden and fragmentation. Pivoted to shadcn/ui as the single component system. Codified as FE1 doctrine in FRONTEND_GOVERNANCE.

**Changes:**

- 11 shadcn primitives installed (`button`, `badge`, `card`, `input`, `label`, `alert`, `skeleton`, `table`, `dialog`, `form`, `sonner`)
- A2Z extensions added: `Button.loading`, `Badge.tone` (preserving original shadcn API per FE6)
- `tokens.ts` retained as hex source
- `index.css` derived to HSL components (critical for opacity modifiers per FRONTEND_GOVERNANCE)
- `StatCard.tsx` composition kept (KPI tile)
- Build: 107 modules, 22 KB CSS / 273 KB JS / 2.37s
- Commit `4b27c1c`

**Verification:**

- Build succeeds
- Showcase.tsx renders all 11 primitives + extensions
- BrandingProvider injects tenant brand vars correctly
- Opacity modifiers (`bg-primary/90`) render correctly (proved by visual test)

**Cross-references:**

- `FRONTEND_GOVERNANCE.md` (canonical post-pivot governance)
- Critical lesson: shadcn opacity requires HSL components in CSS vars, not hex

---

### 2026-05-13 — v10.398 / v10.399 — Joshua canonical org hierarchy resolution

**Type:** harmonization
**Owner:** Joshua
**Rationale:** Org hierarchy had drifted across multiple data sources. Resolution required collapsing to single source of truth (`data/org_hierarchy_config.json`) with explicit canonical batches.

**Changes:**

- `_v10398_joshua_hq_canonical` batch — 103 roles, 127 tier updates committed
- `_v10399_joshua_corrections` — 7-point correction batch
- MD synthetic role deleted (single canonical MD only)
- `role_taxonomy.py` validated `default: 0` across all coverage checks

**Verification:**

- `gate_role_taxonomy_alignment` (G260, scripts/audit.py:36381) passes
- `gate_canonical_retail_chain` (scripts/audit.py:31416) passes
- `role_taxonomy.validate_role_coverage()` returns `{'default': 0, ...}`

**Cross-references:**

- `ROLE_GOVERNANCE.md`
- `data/org_hierarchy_config.json::_v10398_joshua_hq_canonical` batch entry
- `_v10469_role_kpis_resolution` (final 1469 KPI role resolutions completed)

---

### (Implicit, pre-this-session) — v10.470-v10.494 — Resilience certification ladder

**Type:** certification
**Owner:** Joshua + Claude (prior batches)
**Rationale:** Build out the 24-rung certification ladder from enterprise discharge readiness through full uncertainty exposure (G357-G380).

**Changes:** See `RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md` Section "The certification ladder (24 rungs)" for the full enumeration. Each rung corresponds to a v10.4xx batch.

**Verification:**

- Each rung's audit gate at `scripts/audit.py` (line numbers in RESILIENCE artifact)
- Cumulative property enforced: G380 implies G379 implies ... G357

**Cross-references:**

- `RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md`
- Per-rung CHANGELOG entries in `CHANGELOG_MASTER.md` (Wave 6 follow-up — see open green-field state below)

---

## PostgreSQL migration roadmap (resolves OI-28)

Per `DATA_DICTIONARY.md::postgresql_migration_tracking`: the system is migrating from JSON to PostgreSQL. The roadmap is centralized here as the canonical migration registry.

### Migration phases

| Phase   | Description                                                  | Active gate                     |
| ------- | ------------------------------------------------------------ | ------------------------------- |
| Phase 0 | Baseline established (current — JSON canonical)              | `gate_pg_migration_baseline`    |
| Phase 1 | Read path cutover (PG reads OK, JSON writes still canonical) | `gate_pg_read_path_cutover`     |
| Phase 2 | Composer fan-out (PG ready, both sinks written)              | `gate_pg_ready_composer_fanout` |
| Phase 3 | Cutover fan-out (PG canonical, JSON shadow)                  | `gate_pg_cutover_fanout`        |
| Phase 4 | Production cutover (PG only, JSON archived)                  | `gate_pg_production_cutover`    |
| Phase 5 | JSON deprecated (read-only legacy)                           | (new gate TBD)                  |

### Per-file migration status

| File                                     | Current phase | Target phase  | Migration priority | Rationale                           |
| ---------------------------------------- | ------------- | ------------- | ------------------ | ----------------------------------- |
| `data/users.json`                        | 0             | 4             | HIGH               | High read volume; auth-critical     |
| `data/audit_log.json`                    | 0             | 4             | HIGH               | Event sourcing target; append-heavy |
| `data/audit_trail.jsonl`                 | 0             | 4             | HIGH               | Same as audit_log                   |
| `data/bsc_data.json`                     | 0             | 4             | HIGH               | Large per-period datasets           |
| `data/bsc_actuals_*.json` (8 periods)    | 0             | 4             | HIGH               | Same as bsc_data                    |
| `data/bsc_scores.json`                   | 0             | 4             | MEDIUM             | Derived; can lag bsc_data           |
| `data/target_cascade.json`               | 0             | 4             | MEDIUM             | Moderate complexity                 |
| `data/cascade_scores_*.json` (4 periods) | 0             | 4             | MEDIUM             | Derived                             |
| `data/pipeline.json`                     | 0             | 4             | MEDIUM             | Pipeline operations                 |
| `data/credit_*.json` (multiple)          | 0             | 4             | MEDIUM             | Credit operations                   |
| `data/treasury_*.json` (7 files)         | 0             | 4             | MEDIUM             | Treasury operations                 |
| `data/compliance_cases.json`             | 0             | 4             | MEDIUM             | Compliance operations               |
| `data/cbs_baseline_*.json`               | 0             | 4             | MEDIUM             | Period snapshots                    |
| `data/org_hierarchy_config.json`         | 0             | 0 (stay JSON) | LOW                | Config-like; low write volume       |
| `data/kpi_library.json`                  | 0             | 0 (stay JSON) | LOW                | Config-like; harmonization-stamped  |
| `data/org_config.json`                   | 0             | 0 (stay JSON) | LOW                | Tenant config                       |
| `data/role_default_targets.json`         | 0             | 0 (stay JSON) | LOW                | Config-like                         |
| `data/role_skill_matrix.json`            | 0             | 0 (stay JSON) | LOW                | Config-like                         |
| `data/bank_targets.json`                 | 0             | 0 (stay JSON) | LOW                | Annual setup                        |
| `data/locked_targets.json`               | 0             | 0 (stay JSON) | LOW                | Lock state                          |
| `data/fixed_kpis.json`                   | 0             | 0 (stay JSON) | LOW                | Top-of-precedence overrides         |

### Migration ordering

When migration begins, this is the canonical order (preserves dependencies):

1. **users.json** first — foundational; needed by everything
2. **audit_log + audit_trail** — must not lose events during migration
3. **bsc_data + bsc_actuals** — large; benefits from query optimization
4. **target_cascade + cascade_scores** — depends on users.json being in PG
5. **pipeline, credit*\*, treasury*\*, compliance_cases** — domain data
6. **cbs*baseline*\*** — large; can use efficient bulk loads

Each migration triggers a new REVIVAL*LEDGER entry. The migration gate (`gate_pg*<file>\_migrated`) increments as files complete.

### Schema versioning during migration

Per `DATA_DICTIONARY.md::schema_governance`: every file gets a JSON Schema in `data/_schemas/` BEFORE PG migration. The schema becomes the PG table DDL source. Schema drift between JSON shape and PG table shape is a CRITICAL violation.

---

## Twin → Production cutover playbook (resolves OI-43)

The digital twin (`utils/virtual_bank_*`) serves as the development and certification environment. Production deployment swaps the data source to live Flexcube. This playbook is the canonical cutover sequence.

### Pre-cutover requirements (must all be true)

1. Olympic certification G373 passing on twin data
2. Championship readiness G374 passing on twin data
3. Uncertainty exposure phases G375-G380 maintained on twin data
4. Flexcube integration gates pass (`gate_flexcube_*` family, 7 gates)
5. DR drill executed in last 90 days with passing recovery
6. Stage C enforcement gates wired (governance constitution active)
7. PG migration at least at Phase 2 (composer fanout) for high-priority files
8. Per-organ RTO/RPO declarations complete (resolves OI-54)

### Cutover sequence

```
Step 1 — Shadow run
    Twin: full traffic
    Production: parallel read-only from Flexcube
    Duration: 14 days minimum
    Verification: data_isolation_guard confirms no cross-pollination
    Exit criteria: Flexcube reads produce expected shapes

Step 2 — Dual-write
    Twin: full traffic, canonical writes
    Production: writes shadowed to PG + Flexcube readback
    Duration: 14 days minimum
    Verification: writes match across both sinks
    Exit criteria: write parity > 99.99%

Step 3 — Reverse-canonical
    Twin: shadow-mode
    Production: canonical writes; twin reads as fallback
    Duration: 30 days minimum
    Verification: production audit log complete; no fallback to twin observed
    Exit criteria: no twin reads triggered for 7 consecutive days

Step 4 — Twin deprecation
    Twin: archived (immutable historical reference)
    Production: sole source
    Generator scripts: marked as `replay-only`
    DR matrix updated: twin no longer a recovery option

Step 5 — Post-cutover audit
    Full gate suite re-run against production
    Olympic G373 verified on production
    Regulator notification per local CBK requirement
    REVIVAL_LEDGER entry created
```

### Rollback procedure

At any step, rollback returns the system to the prior step's state:

```
Step 4 → Step 3: restore generator scripts to live mode
Step 3 → Step 2: restore canonical writes to twin
Step 2 → Step 1: cease dual-write; twin remains canonical
Step 1 → pre-cutover: detach Flexcube; twin sole source
```

Rollback events are full ledger entries with rationale.

---

## Twin → production audit checkpoints

Per `RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md::regression_sentinels`: certain measurements must not drop during cutover:

| Sentinel                        | Check                          |
| ------------------------------- | ------------------------------ |
| Audit gate pass count           | Same after cutover as before   |
| Integration test count          | Same after cutover as before   |
| Role classification coverage    | 100% maintained                |
| API endpoints with auth Depends | 100% maintained                |
| Olympic certification (G373)    | Re-verified on production data |

Any drop blocks cutover until remediated.

---

## Vulnerability remediation history

| Vuln  | Title                                                    | Resolved in                                | Verification                                  |
| ----- | -------------------------------------------------------- | ------------------------------------------ | --------------------------------------------- |
| V-001 | Cleartext password storage                               | Pre-v10.400 (historical)                   | `gate_password_safety` (scripts/audit.py:741) |
| V-002 | (TBD — exact title not in session memory)                | Historical                                 | (audit gate)                                  |
| V-003 | SHA-256 password migration to bcrypt on successful login | Historical (continues passive migration)   | `gate_password_safety` continues to verify    |
| V-009 | CORS origins hardcoded → env-driven with safe defaults   | v10.497 (referenced in utils/api.py:72-99) | `gate_cors_safety` (line TBD)                 |

(**OI-56 carried** — Document V-002, V-004 through V-008 from CHANGELOG context where available.)

---

## Stage C enforcement rollout plan

Per `GOVERNANCE_CLASSIFICATION_REGISTRY.md::tiered_rollout`: enforcement gates roll out in three phases:

### Phase 1 — Visibility (1 batch per gate)

New gate registered at severity `LOW`. Failures **logged but do not block**. Batch CHANGELOGs include findings.

### Phase 2 — Grace (2-3 batches per gate, severity-tiered)

Gate severity escalates:

- `MEDIUM` gates: 1 batch grace
- `HIGH` gates: 2-3 batches grace
- `CRITICAL` gates: immediate fail-fast (no grace)

Failures during grace produce **warnings**, with remediation tracked.

### Phase 3 — Full enforcement

Gate at declared canonical severity. Failures **block** at that severity tier.

### Wave-by-wave Stage C rollout schedule

| Wave                            | Gate count | Rollout start         | Full enforcement |
| ------------------------------- | ---------- | --------------------- | ---------------- |
| W1 (Foundation)                 | 3 gates    | next batch            | +2 batches       |
| W2 (Role/Auth/API)              | 5 gates    | next batch            | +3 batches       |
| W3 (Organs/Dependencies)        | 3 gates    | next batch            | +2 batches       |
| W4 (Data/Telemetry/Frontend)    | 7 gates    | next batch            | +3 batches       |
| W5 (Digital Twin/AI/Resilience) | 15 gates   | staged over 3 batches | +5 batches       |
| W6 (this wave)                  | 2 gates    | next batch            | +1 batch         |

Total: **35 Stage C gates planned**. Stage C completion estimate: 6 batches with disciplined progression.

---

## Recurring ledger sections (future entries)

When entries accumulate, this artifact may be split per the **`Index → Per-year detail`** pattern. The current scope (single page) is feasible because the ledger has just been initialized. After approximately **50 entries**, refactor into:

- `REVIVAL_LEDGER.md` (this file, kept as index)
- `REVIVAL_LEDGER_2026.md` (per-year detail)
- etc.

Until then, this single file remains canonical.

---

## Open items

| ID    | Title                                        | Resolution                                 |
| ----- | -------------------------------------------- | ------------------------------------------ |
| OI-28 | PostgreSQL migration roadmap per file        | **Resolved in this artifact**              |
| OI-43 | Twin → production cutover playbook           | **Resolved in this artifact**              |
| OI-57 | Document V-002, V-004 through V-008 details  | Stage C amendment from CHANGELOG forensics |
| OI-58 | Per-gate Stage C rollout calendar with dates | Stage C kickoff batch                      |

---

**End of REVIVAL_LEDGER.md**
