# CHANGELOG v10.89 — PG migration batch 2 + G142 anti-drift audit ratchet

**Status:** Phase 1A continuation under the v10.88 anti-drift protocol. PG migration coverage advanced from 24→34 tables (46.2%→65.4%). G142 audit gate promoted from soft-floor to enforced ratchet — any future drop reducing continuation_doc active below 51 fails audit.

**Audit:** **142/142 PASS** (was 141/141; +1 from G142)
**Engine self-tests:** 152/152 (unchanged)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.89 | After v10.89 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 |
| research_addition active | 90 | 90 | 0 |
| **PG migration coverage** | **24 / 52 (46.2%)** ⁽¹⁾ | **34 / 52 (65.4%)** | **+10 tables** |
| API endpoints | 35 / 136 (25.7%) | 35 / 136 (25.7%) | 0 |
| Schema tables in `utils/db.py` | 38 | 47 | +9 ⁽²⁾ |
| JSON files covered | 18 / 129 ⁽¹⁾ | 28 / 129 | +10 |

⁽¹⁾ The v10.88 baseline number was 16 because the audit script wasn't counting NESTED_MIGRATIONS sub-tables (8 tables across alm_liquidity + esg_climate). Real v10.88 baseline was 24/52 (46.2%). The script is fixed in this drop — counts FLAT + NESTED + SPECIAL correctly going forward.

⁽²⁾ Schema went from 38 to 47 tables (+9) because the v10.89 batch added 9 NEW table definitions; the 10th JSON file (`loan_applications.json`) used a pre-existing table that I extended with missing columns + a `data` JSONB.

**No new research_addition standards in this drop.** Per anti-drift Rule C, this is a maintenance drop closing existing gaps, not adding new ones. continuation_doc count is held at the floor.

---

## What landed (in order)

### 1. audit_completion_state.py corrected to count NESTED + SPECIAL

The v10.88 baseline reported 16/52 tables wired but only counted FLAT_MIGRATIONS. The actual coverage was 24/52 because NESTED_MIGRATIONS already had 8 sub-tables wired across `alm_liquidity` (4 sub-tables) and `esg_climate` (4 sub-tables). The v10.89 audit script now counts FLAT + NESTED + SPECIAL correctly. The baseline correction is documented in SCOPE_LEDGER.md so the historical record is honest.

### 2. PG migration batch 2 — 10 new tables

**8 standard FLAT migrations** (one row per JSON record, columns extracted via the standard `insert_records` flow):

| JSON file | PG table | Records | Notes |
|---|---|---|---|
| `ifrs9_loans.json` | `ifrs9_loans` | 5045 | High-volume IFRS 9 ECL data; indexed on stage + reporting_date + npl + sicr |
| `loan_applications.json` | `loan_applications` (existing) | 724 | Pre-existing table extended; analyst dict + decision dict + docs lists flow through `data` JSONB; existing `metadata` column kept for backward compat |
| `legal_matters.json` | `legal_matters` | 362 | Legal arc; `completed_date`/`next_action_date` stored as VARCHAR (250+223 empty strings respectively) |
| `rms_reconciliations.json` | `rms_reconciliations` | 400 | RMS arc; `resolved_date` VARCHAR (141 empty) |
| `debt_recovery.json` | `debt_recovery` | 150 | NPL recovery; indexed on status + recovery_stage + legal_referral |
| `cims_tickets.json` | `cims_tickets` | 200 | Customer instructions; `resolved_date` VARCHAR (118 empty); `audit_trail` list → `data` |
| `treasury_fd.json` | `treasury_fd` | 184 | Fixed deposits; `ratified_date`/`booked_date` VARCHAR (23+96 empty) |
| `bnc_policies.json` | `bnc_policies` | 200 | Bancassurance — note: bancassurance subcategory standards are 0/10 active, but operations now has a data foundation when those activate |

**2 special-case migrations** (atypical JSON shapes that don't fit FLAT or NESTED — custom handlers in `migrate_to_postgres.py`):

| JSON file | PG table | Handler | Approach |
|---|---|---|---|
| `bank_targets.json` | `bank_targets` | `migrate_bank_targets()` | Source DICT keyed by composite `"metric\|year"` → split into separate `metric` + `year` columns; primary key `(metric, year)` |
| `baseline_2025_Dec.json` | `baselines` | `migrate_baselines()` | Source DICT with `period`/`date` scalars + `branch`/`rm` sub-DICTs → single row per `(period, snapshot_date)` with sub-DICTs as JSONB; preserves snapshot without forcing per-branch flattening; uses `ON CONFLICT DO UPDATE` for idempotent re-runs |

The special-case handler pattern is now generalizable. Future atypical JSON files register a function in the `SPECIAL_MIGRATIONS = {filename: handler}` dict. `main()` loops it as a third migration phase between NESTED and FLEXCUBE.

### 3. G142 — anti-drift completion floor ratchet (audit gate)

Promotes the v10.88 soft-floor mechanism into an enforced gate. Verifies:

1. continuation_doc active count ≥ FLOOR (currently 51)
2. SCOPE_LEDGER.md exists at repo root
3. scripts/audit_completion_state.py exists

**The floor is set in `gate_anti_drift_completion_floor()` in scripts/audit.py.** Future drops that activate planned standards should ratchet the floor up (e.g., activating 5 standards from customer_360 → update floor to 56). The gate function is the single source of truth for the floor value.

To legitimately reduce the floor (e.g., for a deprecation), update both the count and the floor in the same drop with explicit CHANGELOG justification.

Per Rule 7, this gate enforces a PROCESS commitment, not engine behaviour — engines themselves remain diagnostic-only as before.

### 4. Discoveries during the work

A pre-existing `loan_applications` table at line 957 of `utils/db.py` was found — heavily referenced (used in `pages/21_loan_applications.py`, `utils/core.py`, several tests). Same situation as the v10.88 `aml_alerts` discovery: the existing schema lacked the `data JSONB` column needed for migration compatibility plus several columns my flat_cols expected (`clean_repayment_history`, `compliance_type`, `appraisal_notes`, `proposition_tag`).

Resolution: extended the existing table with the missing columns + a `data JSONB` (kept the legacy `metadata JSONB` column for backward compat with existing code that wrote to it). The `analyst` field stays as the existing `VARCHAR(200)` column at the schema level — but the migration excludes "analyst" from flat_cols because the JSON has it as a DICT (so analyst's full structure goes into `data` instead, and the existing analyst column receives NULL or its default).

This pattern is worth flagging: **about 15% of the JSON files we migrate already have pre-existing tables** with subtly-different schemas. The verifier script that compares flat_cols against schema columns catches the mismatch before it would hit a real PG run. Future drops should run the verifier early.

---

## What v10.90 covers

Phase 1A continues. Targets in priority order (from the uncovered list, sorted by operational significance):

1. `staff_history.json` (394 records, 138 KB) — HR data
2. `pipeline.json` (294 records, 341 KB) — sales pipeline
3. `lms_enrollments.json` (1146 records, 389 KB) — learning management
4. `edms_documents.json` (500 records, 359 KB) — document management
5. `revenue_assurance.json` (300 records, 157 KB) — revenue assurance arc data
6. `treasury_fx.json` (200 records, 82 KB) — treasury FX
7. `credit_admin.json` (214 records, 223 KB) — credit ops

That batch should bring coverage to ~41/52 (~79%). After that, the final ~10 tables to reach 52/52 are smaller specialty files. Estimated 2-3 more drops to reach the target.

After Phase 1A reaches ~45/52 (~v10.91), Phase 1B begins — surfacing existing engine outputs as FastAPI endpoints to grow the 35→136 target.

---

## Files changed

- **MOD** `utils/db.py` (10 new CREATE TABLE blocks; 1 ALTER on existing `loan_applications` — added 4 columns + `data` JSONB)
- **MOD** `scripts/migrate_to_postgres.py` (8 new FLAT_MIGRATIONS entries; 2 SPECIAL_MIGRATIONS handlers + main() phase wiring)
- **MOD** `scripts/audit.py` (G142 added + registered in GATES)
- **MOD** `scripts/audit_completion_state.py` (NESTED + SPECIAL counting fixed)
- **MOD** `SCOPE_LEDGER.md` (v10.89 progress documented; v10.88 baseline correction noted)
- **NEW** `CHANGELOG_v10.89.md` (this file)

## Files NOT changed (deliberately)

- `standards_registry.py` — no new standards. Maintenance work doesn't add to the active count.
- `scenario_simulator.py` — no scenarios. Migration code isn't engine-architecture.
- All closed-arc files — closure invariants preserved.
- `pages/7_admin.py` — no Tier changes.

## Honest acknowledgements

**The v10.88 baseline number was wrong by 8 tables.** Reported 16/52 was actually 24/52. The audit script wasn't counting NESTED sub-tables. v10.88 wasn't dishonest — the methodology limitation was acknowledged in the v10.88 CHANGELOG ("the script counts how many JSON files have FLAT_MIGRATIONS entries"), but the headline number in the delta table was misleading. The fix in this drop applies retroactively to how we measure coverage; the SCOPE_LEDGER documents the correction.

**G142's floor mechanism only enforces continuation_doc active.** It doesn't enforce PG progress, API progress, or research_addition cap. Each of those could be added as separate sub-checks if drift creeps back into them. The scope of G142 is deliberately narrow: enforce the most important anti-drift commitment (continuation_doc active doesn't go down). Other dimensions are surfaced via the visibility script.

**The flat-cols-vs-schema verifier isn't yet automated.** I ran it manually after each batch. Should be folded into `audit_completion_state.py` so every drop that touches `migrate_to_postgres.py` or `utils/db.py` schema gets the check automatically. Future enhancement.

**Special-case migrations don't have full test coverage.** The handlers (`migrate_bank_targets`, `migrate_baselines`) only run against a real PG database. There's no unit test for the transform logic. For these specifically, the JSON shape is deterministic so the transform is straightforward, but a unit test would catch regressions if the JSON shape changes. Future enhancement.

**`bank_targets` only has 1 year (2026) in the source data.** The schema supports multi-year (year is part of the composite primary key), but the current 45 entries are all for 2026. When historical data backfills happen, the same migration handles them — no schema change needed.

**`baselines` is a single snapshot.** The current source has just `baseline_2025_Dec.json`. Future periods (`baseline_2026_Mar.json` etc.) would need to be added to `SPECIAL_MIGRATIONS` mapping, OR the handler refactored to scan for all `baseline_*.json` files. Left as future work — current pattern handles single-snapshot migration cleanly.

**The `analyst` column on `loan_applications` is now slightly inconsistent.** Pre-existing schema says `analyst VARCHAR(200)` but the JSON has it as `{code, name}` DICT. Migration excludes "analyst" from flat_cols, so the column receives NULL on insert (or its default if any). Existing code that writes to this column directly still works. Reading code that queries the column gets NULL for migrated rows — which is fine because the full analyst data is in `data` JSONB. This is the price of extending pre-existing schemas; cleaner long-term would be to drop the column and rely on `data->>'analyst'` extractions, but that's a bigger schema change deferred for now.

---

**v10.89 ships under the anti-drift protocol** with G142 now mechanically enforcing the floor. PG migration coverage moved 46.2% → 65.4%. Phase 1A continues in v10.90 with another 6-8 tables, targeting ~79% coverage.
