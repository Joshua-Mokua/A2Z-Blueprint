# Changelog — v10.422 Retired test audit engine

**Date:** 2026-05-14
**Phase:** Phase 2d (data integrity housekeeping)
**Audit:** G308 added (cumulative 308 gates)
**Tests:** 15/15 PASSED in `test_v10422_retired_test_cleanup.py`
**Regression:** 327/327 v10.4xx tests PASSED (312 + 15)
**Verifier:** 717/717 checks pass (710 → 717, +7 v10.422 checks)
**G162 baseline:** 4022 (115 consecutive zero-drift batches)
**Master prompt:** v4.64 → v4.65 (lockstep — 66 consecutive batches)

---

## What this batch is

The codebase has a long-standing convention for retiring obsolete tests: rename them from `test_v10XXX_...` to `_retired_v10YYY_test_v10XXX_...` where `YYY` is the batch that retired them. Pytest skips functions not starting with `test_`, so soft-retired tests are no-execute while their bodies remain in source — preserved as in-context historical record. The version prefix encodes the **why**.

Across the v10.391–v10.420 arc, **12 functions** have accumulated this prefix (Joshua's backlog noted "11 across 3 files"; live count is 12 across 4 files). This batch makes that convention queryable and writes a searchable archive.

## Live audit result

| File | Retired count | Versions retiring |
|---|---|---|
| `test_v10391_cascade_diagnosis.py` | 4 | v10.397 (×2), v10.399 (×2) |
| `test_v10393_cascade_structure_engine.py` | 6 | v10.397 (×4), v10.398 (×2) |
| `test_v10394_hierarchy_and_fixed_kpi_review.py` | 1 | v10.402 |
| `test_v10397_staff_code_dedup.py` | 1 | v10.403 |
| **Total** | **12** | **5 distinct retiring versions** |

Most retirements came from the v10.397–v10.399 cascade restructuring arc (10 of 12). v10.402 and v10.403 closed the loop on the remaining two.

## What v10.422 built

### NEW `utils/test_cleanup_engine.py` (~280 LOC)

Zero streamlit imports. 17th engine.

**`RETIRED_PATTERN`** — `re.compile(r"^_retired_v(\d+)_test_v(\d+)_(.+)$")` — captures retired_by_version + original_version + descriptive suffix.

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `audit_retired_tests(tests_dir)` | `TestCleanupAudit` | AST-based scan; per-file + per-version aggregates |
| `archive_retired_tests(tests_dir, archive_path, dry_run)` | `ArchiveResult` | Extract metadata + bodies → JSON; **default dry_run=True** |

**Dataclasses (JSON-serializable):**
- `RetiredTestInfo` — function_name, original_test, retired_by_version, original_version, file_path, line_number, body_lines, docstring
- `TestCleanupAudit` — total_retired, files_affected, by_retired_version, by_original_version, by_file, tests list
- `ArchiveResult` — dry_run, tests_archived, archive_path, archive_size_bytes, note

### NEW `data/_retired_tests_archive.json` (13.7 KB)

Written by the engine. Contents:
- Metadata stamp (`shipped: v10.422`, generation timestamp)
- Aggregates (by_retired_version, by_original_version, by_file)
- Per-test entries with FULL BODY preserved (for searchability)

Schema:
```json
{
  "shipped": "v10.422",
  "total_retired": 12,
  "by_retired_version": {"v10397": 6, "v10399": 2, "v10398": 2, "v10402": 1, "v10403": 1},
  "tests": {
    "_retired_v10403_test_v10397_total_unique_codes_increased": {
      "function_name": "_retired_v10403_test_v10397_total_unique_codes_increased",
      "original_test": "test_v10397_total_unique_codes_increased",
      "retired_by_version": 10403,
      "original_version": 10397,
      "file_path": "tests/integration/test_v10397_staff_code_dedup.py",
      "line_number": 164,
      "body_lines": 8,
      "docstring": "After dedup, total unique codes should be 10 more than before...",
      "body": "def _retired_v10403_test_v10397_total_unique_codes_increased():\n    ..."
    },
    ...
  }
}
```

### NEW `scripts/audit_retired_tests.py` runner

```bash
# Audit only (no FS changes)
python scripts/audit_retired_tests.py

# Audit + write archive
python scripts/audit_retired_tests.py --archive
```

Default = audit only. Archive write is explicit opt-in.

### NEW 2 FastAPI endpoints in `utils/api.py`

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/test-cleanup/audit`   | Per-file + per-version rollup |
| `POST` | `/api/v1/test-cleanup/archive` | Write archive (idempotent) |

### Audit gate G308

Verifies engine API + AST zero-streamlit + RETIRED_PATTERN regex + runner --archive flag + 2 endpoints + engine state 0/0/0/0 + E2E synthetic test file audit and archive.

## What this batch did NOT do

- **Did NOT delete retired functions from source files.** The `_retired_` prefix functions remain in their original locations. Deletion would lose in-context historical reference (the test sits next to its replacement test). The archive provides search; the source provides context. Both serve.
- **Did NOT introduce a new retirement convention.** The existing `_retired_v10YYY_test_v10XXX_` pattern is the canonical naming — engine just queries it.
- **Did NOT touch tests Joshua hasn't already retired.** No automatic test retirement based on failures or staleness. Future retirements happen explicitly per-batch, same as today.

## Verified outcome

| Metric | v10.421 | v10.422 |
|---|---|---|
| Audit gates | 307 | **308** |
| v10.4xx tests | 312 | **327** (+15) |
| Verifier | 710 | **717** (+7) |
| API endpoints | 38 | **40** (+2) |
| React-ready engines | 16 | **17** |
| Lockstep batches | 65 | **66** consecutive |
| G162 baseline | 4022 (114) | 4022 (**115** zero-drift) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## Architecture — what React sees

A React admin test-health dashboard:

```typescript
// 1. Get the audit
const audit = await api.get('/api/v1/test-cleanup/audit');
// {
//   total_retired: 12, files_affected: 4,
//   by_retired_version: { v10397: 6, v10398: 2, v10399: 2, v10402: 1, v10403: 1 },
//   tests: [{ function_name, original_test, retired_by_version, file_path, ... }]
// }

// 2. Render a table grouped by file or by version
// 3. Admin clicks "Update Archive" → idempotent write
await api.post('/api/v1/test-cleanup/archive');
```

## 10 honest acknowledgements

1. **The retired prefix convention is good.** It encodes the **why** (which batch retired) and the **what** (original test name) without needing external tooling. The engine just makes it queryable; the convention itself is what enables this.

2. **Source-deletion would lose context.** If we deleted the `_retired_` functions, future devs hitting an audit gate failure for the same KPI wouldn't see the prior test that asserted the now-stale invariant. Keeping them in-place IS the documentation.

3. **The archive is the searchable index.** When a dev asks "did we ever assert X about KPI Y?", they can grep the archive (a single JSON file) instead of walking 40+ test files. Useful for forensics.

4. **AST parsing was the right choice.** Regex-only matching on function names would miss multi-line definitions or false-positive on string literals. `ast.walk` over `FunctionDef` nodes is unambiguous.

5. **`body_lines` count comes from `end_lineno`.** Python 3.8+ exposes this on AST nodes. Easy to compute without re-parsing source. The engine works on Python 3.10+ (project requirement).

6. **`docstring` field is the first line, max 200 chars.** Long docstrings (some retired tests have multi-paragraph explanations of why) are truncated in the dataclass but preserved in full inside `body` for the archive.

7. **Two FastAPI endpoints, not one.** Audit (GET) is cheap + read-only; can be polled. Archive (POST) writes to disk + might overwrite — separate verb. Matches REST semantics.

8. **The archive is idempotent.** Running it twice produces the same content. The `generated_at` timestamp updates, but if the source hasn't changed, the test list is identical. Safe to schedule via cron.

9. **Joshua's count was off by one.** Backlog said "11 across 3 files"; live audit shows 12 across 4. The engine's job isn't to reconcile — it's to make the truth queryable. Future audit-trail counts now come from the engine.

10. **Phase 2d's pattern is stable.** v10.419, v10.420, v10.421, v10.422 all follow the same template: engine + script + 2 endpoints + audit gate + safety-first defaults + 15±2 integration tests. Predictable, reviewable, low-surprise.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10422_patch.zip` on top of v10.421 state
3. `python scripts/verify_local_state.py` → expect **717/717**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/test_cleanup_engine.py` → engine self-test (8 checks)
6. **First**: `python scripts/audit_retired_tests.py` → review per-file breakdown
7. **Optional**: `python scripts/audit_retired_tests.py --archive` → write `data/_retired_tests_archive.json`
8. The archive ships pre-populated in this patch; running `--archive` is idempotent
9. Tell me **"continue"** → v10.423 = pillar weights decision (68/14/6/12 vs Kaplan-Norton 40/25/25/10)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.419-v10.421~~ | ~~Role weight / KPI dedup / backup cleanup~~ | **DONE** |
| **v10.422** | **Retired test audit engine** | **DONE (this batch)** |
| v10.423 | Pillar weights decision (68/14/6/12 vs Kaplan-Norton 40/25/25/10) | Next |
| v10.424 | BSC scorecard dual-view + compliance in pages/1_perform.py | Pending |
| v10.425-v10.427 | CBS baseline / PBT live actuals / MD BSC verification | Pending |
| v10.428+ | React SPA build | Pending |
