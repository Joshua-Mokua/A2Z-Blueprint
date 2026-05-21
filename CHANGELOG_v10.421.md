# Changelog — v10.421 Backup retention cleanup

**Date:** 2026-05-14
**Phase:** Phase 2d (data integrity housekeeping)
**Audit:** G307 added (cumulative 307 gates)
**Tests:** 14/14 PASSED in `test_v10421_backup_retention.py`
**Regression:** 312/312 v10.4xx tests PASSED (298 + 14)
**Verifier:** 710/710 checks pass (703 → 710, +7 v10.421 checks)
**G162 baseline:** 4022 (114 consecutive zero-drift batches)
**Master prompt:** v4.63 → v4.64 (lockstep — 65 consecutive batches)

---

## What this batch is

Closes another Phase 2d housekeeping item. Across the v10.345–v10.420 arc, every batch that touched canonical data dropped a `_v10X_backups/` directory with before-snapshots. The arc shipped 75+ batches; 17 of those backup directories are still on disk and several are 20+ MB each. Total: **~173 MB** in sandbox (Joshua noted 122 MB in the backlog; this kept growing).

This batch ships a **safety-first** engine to clean them up. Nothing is auto-deleted by this batch's CI — the destructive path is opt-in via `--confirm` flag on the runner or `confirm=True` query param on the API.

## Live sandbox audit (under default policy)

| Status | Version | Size | Reason |
|---|---|---|---|
| ✓ KEEP | v10404 | 23.18 MB | recent (top 3) |
| ✓ KEEP | v10403 | 24.36 MB | recent |
| ✓ KEEP | v10402 | 24.70 MB | recent |
| ✗ DEL | v10401 | 24.68 MB | stale, above 1 MB threshold |
| ✗ DEL | v10399 | 25.71 MB | stale |
| ✗ DEL | v10398 | 20.12 MB | stale |
| ✗ DEL | v10397 | 24.10 MB | stale |
| ✓ KEEP | v10396 | 0.02 MB | below threshold |
| ✗ DEL | v10392 | 4.55 MB | stale |
| ✓ KEEP | v10390..v10345 | <0.2 MB each | below threshold |

**Reclaim available: 99.2 MB across 5 directories.**

## What v10.421 built

### NEW `utils/backup_retention_engine.py` (~250 LOC)

Zero streamlit imports. 16th engine.

**Defaults (conservative):**
- `DEFAULT_KEEP_RECENT_N = 3`
- `DEFAULT_PRESERVE_SIZE_THRESHOLD_BYTES = 1 * 1024 * 1024` (1 MB)

**`BACKUP_DIR_PATTERN`** — `re.compile(r"^_v(\d+)_backups$")` — only matches `_v10X_backups` directory naming. **Engine never touches `data/_canonical_backups/`** (different purpose: point-in-time canonical config snapshots, not batch before-snapshots).

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `audit_backup_retention(keep_recent_n, size_threshold_bytes, data_dir)` | `BackupRetentionAudit` | Per-dir audit; no FS changes |
| `apply_retention_policy(keep_recent_n, size_threshold_bytes, dry_run, data_dir)` | `RetentionApplyResult` | Apply (default `dry_run=True`) |

**Dataclasses (JSON-serializable):**
- `BackupDirInfo` — per-directory (name, version, path, file_count, total_bytes, total_mb, is_below_threshold, is_recent, will_delete, note)
- `BackupRetentionAudit` — bank rollup with `dirs` list
- `RetentionApplyResult` — outcome (`dry_run`, `dirs_deleted`, `bytes_reclaimed`, `mb_reclaimed`, `deleted_dirs`, `errors`)

### NEW `scripts/cleanup_backups.py` runner

```bash
# Default: dry-run (no FS changes)
python scripts/cleanup_backups.py

# Actually delete
python scripts/cleanup_backups.py --confirm

# Adjust retention
python scripts/cleanup_backups.py --keep-recent 5 --size-threshold-mb 2 --confirm
```

Always shows the full per-directory breakdown before doing anything.

### NEW 2 FastAPI endpoints in `utils/api.py`

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/backup-retention/audit`  | Audit (default policy or query-param tweak) |
| `POST` | `/api/v1/backup-retention/apply?confirm=true` | Apply (gated by `confirm=true`) |

### Audit gate G307

Verifies engine API + dataclass + AST zero-streamlit + `dry_run=True` default (safety) + `BACKUP_DIR_PATTERN` + runner `--confirm` gate + 2 endpoints + engine state 0/0/0/0 + E2E synthetic 3-dir cleanup.

## What this batch did NOT do

- **No backups were actually deleted in this sandbox.** Destructive operations belong on the user's workspace where they have control. The patch ships the tool.
- **No automatic CI deletion path.** The G307 gate verifies the engine works; it does not run cleanup.
- **No retention modification of `data/_canonical_backups/`.** That directory uses a different naming scheme and is excluded from `BACKUP_DIR_PATTERN`.

## Verified outcome

| Metric | v10.420 | v10.421 |
|---|---|---|
| Audit gates | 306 | **307** |
| v10.4xx tests | 298 | **312** (+14) |
| Verifier | 703 | **710** (+7) |
| API endpoints | 36 | **38** (+2) |
| React-ready engines | 15 | **16** |
| Lockstep batches | 64 | **65** consecutive |
| G162 baseline | 4022 (113) | 4022 (**114** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## Architecture — what React sees

A React admin retention dashboard:

```typescript
// 1. Get the audit
const audit = await api.get('/api/v1/backup-retention/audit?keep_recent=3&size_threshold_mb=1.0');
// {
//   total_dirs: 17, total_mb: 172.1, will_keep: 12, will_delete: 5,
//   mb_to_reclaim: 99.2, dirs: [{name, version, total_mb, is_recent, will_delete, ...}]
// }

// 2. Show the per-dir breakdown; user clicks "Run Cleanup"

// 3. POST with confirm=true (gated; production: also admin role check)
const result = await api.post('/api/v1/backup-retention/apply?confirm=true');
// { result: { dry_run: false, dirs_deleted: 5, mb_reclaimed: 99.2, deleted_dirs: [...] } }
```

Same engine the Streamlit page or runner script calls.

## 10 honest acknowledgements

1. **Safety-first is non-negotiable for destructive ops.** Defaulting `dry_run=True` ensures every consumer (runner, API, future Streamlit admin tab) makes the destructive choice explicit. The G307 gate specifically asserts this default — if someone "fixes" the safety later, the gate fails.

2. **`_canonical_backups` was deliberately excluded.** Different purpose (point-in-time canonical config snapshots, manually curated) vs. `_v10X_backups` (auto-generated batch before-snapshots). Naming-pattern enforcement keeps the scope tight.

3. **99.2 MB is the conservative number.** Aggressive policy (`keep_recent_n=1`, `size_threshold_mb=0.1`) would reclaim ~155 MB. Defaults err toward preserving more history; user can tune if desired.

4. **The 17 dirs all date back to batches that did real canonical work.** Each existed for a good reason at the time. Keeping the top 3 most recent means we still have a 3-batch rollback window without paper-cutting historical depth.

5. **Tiny backups are essentially free.** The 9 dirs below 1 MB total < 1 MB combined. Preserving them costs nothing and gives long-tail rollback options for batches that touched lightweight files.

6. **Idempotency tested explicitly.** Running cleanup → re-running audit shows 0 to delete. The pattern matches v10.419 and v10.420 — each Phase 2d engine is safe to re-run.

7. **No batch-revision linkage.** I'm not auto-cleaning when a new batch ships — that would be aggressive and surprising. The runner is a one-shot tool; users can schedule it via cron if they want recurring cleanup, but defaults to manual.

8. **The audit is the most useful artifact.** Even if a user never runs `--confirm`, the audit tells them what's eating their disk and lets them make selective per-dir decisions outside this tool. That's why the audit always shows the full per-dir breakdown.

9. **Sandbox not cleaned in this batch.** I considered running `apply_retention_policy(dry_run=False)` to demonstrate. Decided against it — the sandbox is a test environment; if we delete here, the next batch can't reference those backups if needed. The runner is the right place.

10. **Phase 2d is steady housekeeping.** Each batch tackles a discrete debt item: v10.419 (normalize), v10.420 (dedup), v10.421 (cleanup), v10.422 (next). Pattern works — small batches, single-concern, fully tested, opt-in for anything destructive.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10421_patch.zip` on top of v10.420 state
3. `python scripts/verify_local_state.py` → expect **710/710**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/backup_retention_engine.py` → engine self-test (7 checks)
6. **First**: `python scripts/cleanup_backups.py` → review the per-dir breakdown (no FS changes)
7. **If satisfied**: `python scripts/cleanup_backups.py --confirm` → reclaim ~99 MB
8. (Optional) `python scripts/cleanup_backups.py --keep-recent 5` for a more conservative pass
9. Tell me **"continue"** → v10.422 = retired test cleanup (11 stale tests across 3 files)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.419-v10.420~~ | ~~Role weight + KPI dedup~~ | **DONE** |
| **v10.421** | **Backup retention cleanup** | **DONE (this batch)** |
| v10.422 | Retired test cleanup (11 stale across 3 files) | Next |
| v10.423 | Pillar weights decision (68/14/6/12 vs Kaplan-Norton 40/25/25/10) | Pending |
| v10.424 | BSC scorecard dual-view + compliance in pages/1_perform.py | Pending |
| v10.425-v10.427 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.428+ | React SPA build | Pending |
