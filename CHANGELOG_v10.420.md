# Changelog — v10.420 KPI library dedup migration

**Date:** 2026-05-14
**Phase:** Phase 2d (data integrity housekeeping)
**Audit:** G306 added (cumulative 306 gates)
**Tests:** 14/14 PASSED in `test_v10420_kpi_library_dedup.py`
**Regression:** 298/298 v10.4xx tests PASSED (284 + 14)
**Verifier:** 703/703 checks pass (695 → 703, +8 v10.420 checks)
**G162 baseline:** 4022 (113 consecutive zero-drift batches)
**Master prompt:** v4.62 → v4.63 (lockstep — 64 consecutive batches)

---

## What this batch is

Closes a long-pending data integrity item. In v10.403 (earlier this arc), 4 KPI alias pairs were identified as duplicates and stamped into `_v10403_dedup_pending` — but the actual consolidation was deferred. v10.420 ships the migration.

## The 4 pairs

| Duplicate | → | Canonical | Reason |
|---|---|---|---|
| `NEW_ACCOUNTS` | → | `K006` | Both "New Accounts Opened" |
| `K069` | → | `K024` | Both "Digital Channel Adoption (%)" |
| `K048` | → | `K028` | Both "Collateral Review Completion (%)" |
| `NIM` | → | `NET_INTEREST_MARGIN` | Both "Net Interest Margin" |

## Live migration result

Pre-migration state in sandbox:

| Pair | duplicate role refs | canonical role refs | overlapping | in kpi_weights | in bank_targets |
|---|---|---|---|---|---|
| NEW_ACCOUNTS → K006 | 8 | 8 | 0 | yes | 0 |
| K069 → K024 | 8 | 6 | **4** | no | 0 |
| K048 → K028 | 0 | 7 | 0 | no | 0 |
| NIM → NET_INTEREST_MARGIN | 1 | 3 | 0 | yes | 0 |

Post-migration: **0/4 pending**. Migration outcomes:
- **17 role lists updated** (4 had overlapping refs that needed dedup)
- **4 KPI definitions removed** from the `kpis` list
- **2 kpi_weights entries removed** (NEW_ACCOUNTS and NIM weights)
- **0 bank_targets entries** needed migration (none referenced duplicates)
- **role_normalized_weights** cleared and re-migrated via v10.419 engine to reflect new state

## What v10.420 built

### NEW `utils/kpi_dedup_engine.py` (~280 LOC)

Zero streamlit imports. 15th React-ready engine module.

**`KPI_ALIAS_PAIRS`** — single source of truth for the 4 mappings.

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `audit_kpi_dedup(library, bank_targets)` | `DedupAudit` | Per-pair reference counts |
| `migrate_dedup_kpi_library(library, bank_targets, write_back, rebuild_normalized_weights)` | `DedupMigrationResult` | Consolidate references |

**Dataclasses** (JSON-serializable):
- `AliasPairAudit` — per-pair reference snapshot (8 fields)
- `DedupAudit` — bank rollup (total/already/pending/pair_audits/timestamp)
- `DedupMigrationResult` — migration counts (pairs/role_kpis/kpi_definitions/kpi_weights/bank_targets/rebuilt/note)

**Idempotency:** Re-running the migration on an already-deduped library produces no changes. Tested + verified.

### Migration steps per pair

1. **`role_kpis`** — in each role's list, replace duplicate ID with canonical; dedupe to avoid double-counting if both are already present
2. **`kpi_weights`** — drop duplicate entry (canonical kept)
3. **`kpis` list** — remove duplicate definition
4. **`bank_targets`** — in each period, if duplicate has a target but canonical doesn't, the canonical inherits; otherwise just drop the duplicate
5. **`role_normalized_weights`** (v10.419) — cleared, then re-migrated via `migrate_normalize_all_roles` to reflect the deduped state

### NEW `scripts/dedup_kpi_library.py` runner

```bash
# Preview without writing
python scripts/dedup_kpi_library.py --dry-run

# Run the migration
python scripts/dedup_kpi_library.py
```

Per-pair audit shown; idempotent on re-run.

### NEW 2 FastAPI endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/kpi-dedup/audit`   | Bank-wide audit |
| `POST` | `/api/v1/kpi-dedup/migrate` | Run migration (production: gate behind admin) |

### Forward-compat for existing tests

Two pre-existing assertions had to be relaxed:

1. **v10.403 test `test_v10403_kpi_library_duplicates_marked`** — was checking for `_v10403_alias_of` markers on the 4 duplicates. Updated to accept EITHER the markers (pre-v10.420) OR the `_v10420_dedup_complete` metadata + physical removal of duplicates (post-v10.420).

2. **G289 audit gate** — same fix as above.

3. **v10.390 verifier check** on 4 KPIs (`NIM`, `CIR`, `ROE`, `DEP_GROWTH`) — was looking for `NIM` to exist. Updated to accept `NET_INTEREST_MARGIN` as the canonical replacement after v10.420.

### Audit gate G306

Verifies engine surface + zero streamlit + KPI_ALIAS_PAIRS constant + migration script + 2 endpoints + engine state 0/0/0/0 + E2E synthetic library dedup + idempotency.

## Verified outcome

| Metric | v10.419 | v10.420 |
|---|---|---|
| Audit gates | 305 | **306** |
| v10.4xx tests | 284 | **298** (+14) |
| Verifier | 695 | **703** (+8) |
| Total API endpoints | 34 | **36** (+2 kpi-dedup) |
| React-ready engines | 14 | **15** |
| Master prompt lockstep | 63 | **64** consecutive |
| G162 baseline | 4022 (112) | 4022 (**113** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## Architecture — what React sees

```typescript
// Before any migration: see what's pending
const audit = await api.get('/api/v1/kpi-dedup/audit');
// { total_pairs: 4, already_migrated: 0, pending: 4, pair_audits: [...] }

// Admin runs the consolidation
await api.post('/api/v1/kpi-dedup/migrate');

// Re-audit: confirms 4/4 already_migrated
const audit2 = await api.get('/api/v1/kpi-dedup/audit');
// { pending: 0, already_migrated: 4 }
```

## 10 honest acknowledgements

1. **This was overdue.** The duplicates were flagged in v10.403. Comment said "Full dedup in v10.409." That didn't happen — and the library carried the duplicates for 17 more batches. Closing that loop matters; data integrity issues compound silently.

2. **The 4 pairs are genuinely duplicates by name.** Every pair has identical KPI names — not similar, identical. They came from K-coded migration history meeting canonical-coded migration history with overlap. Safe to consolidate.

3. **Overlapping roles needed careful handling.** 4 roles had BOTH `K069` and `K024` in their KPI list — would double-count after replacement if I'd just done blind substitution. The dedup logic in the engine prevents that by building a new list with `not in new_list` check.

4. **K048 had zero role refs.** It was a phantom — defined in `kpis` list but no role actually used it. Cleanest removal in the batch.

5. **Bank targets didn't need migration this time.** None of the 4 duplicates had bank_targets entries in the sandbox. The migration code still handles that case correctly (canonical inherits if it was missing), but it didn't fire.

6. **v10.419 integration was free.** The migration ends by clearing + re-running `migrate_normalize_all_roles`. After dedup, the normalized weights reflect the canonical-only state. Without the rebuild step, normalized weights would still reference the now-removed duplicates.

7. **The forward-compat changes are paid debt.** v10.403 tests + verifier had hardcoded expectations that became stale the moment we ran v10.420. Standard rebase cost. The pattern (accept either state) is what I'll use in similar future cases.

8. **Idempotency was a design goal, not an accident.** The migration logic builds new lists from scratch, applies KPI_ALIAS_PAIRS once, and skips no-op writes. Tested both via the engine's self-test and a dedicated integration test.

9. **`_v10420_dedup_complete` metadata stamp.** Records what was done, when, with what counts. Future batches can read this to know the dedup has been applied without re-running an audit.

10. **15 React-ready engines now.** All zero-streamlit, all dataclass-returning. The pattern is reproducible: introduce a constant (`KPI_ALIAS_PAIRS`), wrap audit + migration around it, expose via FastAPI, add a runner script. ~280 LOC each. Phase 2d batches will continue using this shape.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10420_patch.zip` on top of v10.419 state
3. `python scripts/verify_local_state.py` → expect **703/703**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/kpi_dedup_engine.py` → engine self-test (9 checks)
6. **First**: `python scripts/dedup_kpi_library.py --dry-run` → review what will change
7. **Then**: `python scripts/dedup_kpi_library.py` → run the migration
8. Verify in `data/kpi_library.json` → see `_v10420_dedup_complete` metadata + 4 duplicate IDs absent from `kpis` list
9. (Optional) `curl /api/v1/kpi-dedup/audit` → confirm 0/4 pending
10. Tell me **"continue"** → v10.421 = backup retention cleanup (122 MB of stale `.before` snapshots)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.419~~ | ~~Role weight renormalization~~ | **DONE** |
| **v10.420** | **KPI library dedup** | **DONE (this batch)** |
| v10.421 | Backup retention cleanup (122 MB) | Next |
| v10.422 | Retired test cleanup | Pending |
| v10.423 | Pillar weights decision (68/14/6/12 vs Kaplan-Norton 40/25/25/10) | Pending |
| v10.424 | BSC scorecard dual-view + compliance in pages/1_perform.py | Pending |
| v10.425-v10.427 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.428+ | React SPA build | Pending |
