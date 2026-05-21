# A2Z MIS 360 — Session Cumulative Recovery (v10.336 → v10.342)

This zip contains **every file changed in every batch shipped in the current chat session** — v10.336 through v10.342 — in one extract. If any earlier zip failed to land (e.g. extracted into a subfolder instead of overwriting), this is the recovery.

## How to apply

1. **Close Streamlit** — Ctrl+C in the terminal running it. If you leave it running, Python keeps stale bytecode loaded.

2. **Delete any leftover subfolder extracts** in your A2Z workspace:
   ```
   cd "C:\Users\Joshua\Desktop\A2Z Blue Print\a2z"
   rmdir /s /q a2z_v10342_cumulative 2>nul
   rmdir /s /q a2z_v10342_schema_lock 2>nul
   rmdir /s /q a2z_v10341_runtime_fixes 2>nul
   rmdir /s /q a2z_v10340_matrix_wired 2>nul
   rmdir /s /q a2z_v10339_cost_matrix 2>nul
   rmdir /s /q a2z_v10338_sbu_drilldown 2>nul
   rmdir /s /q a2z_v10337_branch_staff 2>nul
   rmdir /s /q a2z_v10336_specialist 2>nul
   ```
   (Each "not found" is fine — they're best-effort cleanup.)

3. **Extract `a2z_v10342_session_cumulative.zip` into `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\`, OVERWRITING all files.** This zip is built flat — the top of the archive is `data/`, `pages/`, `utils/`, `scripts/`, `tests/` directly, no parent folder. Windows should prompt to overwrite; choose "Yes to all."

4. **Run the verifier:**
   ```
   python scripts\verify_local_state.py
   ```
   Expected: **ALL 34 CHECKS PASSED.** If any ✗ appears, that file didn't overwrite — copy it manually from the zip.

5. **Run the audit:**
   ```
   python scripts\audit.py
   ```
   Expected: **230/230 PASS = 100.0%.**

6. **Restart Streamlit:**
   ```
   streamlit run app.py
   ```

## What's in this bundle

### v10.336 — Specialist Department Coverage (8th producer)
- `utils/specialist_activity_generator.py`
- `data/specialist_activity_config.json`
- `scripts/v10336_patch_kpi_library.py` (one-shot, safe to re-run if needed)

### v10.337 — Branch Staff (528) + Pipeline Activity Bridge
- `utils/branch_staff_generator.py` (9th producer)
- `utils/pipeline_to_bsc.py` (extended with `sync_pipeline_activity_to_bsc`)
- `data/branch_staff_config.json`

### v10.338 — Canonical Segment Vocabulary + SBU Drill-Down
- `utils/segment_classifier.py`, `utils/sbu_pnl_rollup.py`, `utils/segment_balance_sheet.py`
- `data/segment_config.json` (canonical vocabulary)
- `data/customer_intelligence.json` (1,078 individuals migrated to AFFLUENT/CORE_MIDDLE/MASS)
- `data/customer_intelligence_business.json` (206 businesses synthesized)
- `data/_v10338_segment_migration.json` (rollback log)
- `pages/114_sbu_drilldown.py` (7-tab drill-down)
- `scripts/v10338_*.py` (one-shot migration scripts)

### v10.339 — Cost Matrix Admin UI + Runtime
- `data/cost_allocation_rules.json` (10 seed rules, 7.9B annual)
- `utils/cost_allocation.py` (CRUD + compute engine; later updated v10.340 + v10.342)
- `pages/7_admin.py` (Performance → Cost Matrix tab)

### v10.340 — Cost matrix wired into SBU rollup
- `utils/sbu_pnl_rollup.py` (cost_source='matrix' parameter, `_MATRIX_INDIRECT_CACHE`)
- `utils/cost_allocation.py` (recursion broken — no `from utils.sbu_pnl_rollup` import)
- `pages/114_sbu_drilldown.py` (banner explaining matrix vs proxy + honest negative-PBT framing)

### v10.341 — Runtime fixes (4 crashes you reported)
- `data/bank_targets.json` (48 scalar entries normalized to dict shape)
- `data/bank_targets.json.v10341.bak` (backup)
- `pages/12_cascade.py` (`_buf_pct()` defensive helper)
- `pages/4_execute.py` (3 `i['gate']` → `i.get('gate', '—')`)
- `pages/113_branch_ranking.py` (`db.load_json` calls fixed — added .json suffix)
- `utils/command_centre_strategic_initiatives.py` (`r['phase']` → `r.get('phase')`)
- `scripts/smoke_pages.py` (static drift-key AST scanner)

### v10.342 — Data schema lock (Option D, foundation for harmonization)
- `data/_schemas/` — 5 JSON Schema files + README
- `utils/schema_validator.py` (pure-stdlib JSON Schema subset)
- `utils/cost_allocation.py` (schema-gated `save_rules`)
- `scripts/audit.py` (G230 audit gate)
- `tests/integration/test_v10342_schema_lock.py` (14 tests)

### Cross-cutting (updated by multiple batches — latest state shipped)
- `scripts/audit.py` (G225 through G230 all registered)
- `pages/7_admin.py` (specialist tier + cost matrix + segment config tabs)
- `pages/_manifest.json` (114_sbu_drilldown registered)

### Tests for every batch
- `tests/integration/test_v10336_*.py` through `test_v10342_*.py`

### Verification
- `scripts/verify_local_state.py` (34 checks across all 7 batches)

## Expected state after extraction

- Audit: **230/230 PASS = 100.0%**
- Tests: **755/755 across 46 integration suites**
- Cascade Q2 2026: 1,326 staff scoring, MD = 3.23
- 5 protected data files (all schema-validating)
- 9 producers + 4 SBU engines + 1 quality validator

## If verify_local_state shows any ✗

The extraction didn't overwrite that file. Right-click the zip → "Extract All" instead of "Extract Here," and let it overwrite. If a specific file still won't update, copy it manually from inside the zip — the paths in the zip are exactly the paths in your workspace.

— end —
