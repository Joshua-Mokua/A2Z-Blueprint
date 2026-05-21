# CHANGELOG v10.90 — PG migration batch 3 + automated consistency check + Phase 3 deferral

**Status:** Phase 1A continuation. PG migration coverage advanced from 34→41 tables (65.4%→78.8%). Phase 3 items (Peer Learning, FATCA/CRS, CBK reports, React) formally deferred to end per Joshua's directive — to be planned after Phase 1 + Phase 2 close. Migration consistency check (flat-cols-vs-schema verifier) folded into the audit script per v10.89 honest acknowledgment, so every drop now runs it automatically.

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 31/31 FLAT_MIGRATIONS entries verified clean

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.90 | After v10.90 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| **PG migration coverage** | 34 / 52 (65.4%) | **41 / 52 (78.8%)** | **+7 tables** |
| flat tables | 24 | 31 | +7 |
| nested sub-tables | 8 | 8 | 0 |
| special-case tables | 2 | 2 | 0 |
| JSON files covered | 28 / 129 | 35 / 129 | +7 |
| Schema tables in `utils/db.py` | 47 | 54 | +7 |
| API endpoints | 35 / 136 (25.7%) | 35 / 136 (25.7%) | 0 |

**No new research_addition standards in this drop.** Maintenance drop closing existing gaps; continuation_doc count held at floor.

---

## Phase 3 directive

Per your message: **"we shall skip the 4 items listed in phase 3 and plan them at the end"**.

The four blocked items (Peer Learning standards #14–#20, FATCA/CRS XML, deferred CBK reports, React/React Native standards #37–#38) are now formally deferred to end of plan. They will be planned and executed after Phase 1 (PG migration + API endpoint expansion + test coverage) and Phase 2 (planned-spec subcategory activation) close.

This is documented in:
- `SCOPE_LEDGER.md` — top-of-document directive note
- `scripts/audit_completion_state.py` — Phase 3 block now includes the deferral note in every state report
- This CHANGELOG

The audit script will continue to surface the four items at every drop so they don't get forgotten — just not asked-for-content during Phase 1/2 work.

---

## What landed (in order)

### 1. PG migration batch 3 — 7 new FLAT tables

All 7 are clean standard flat migrations (no pre-existing collisions, unlike v10.88's `aml_alerts` and v10.89's `loan_applications` situations).

| JSON file | PG table | Records | Notes |
|---|---|---|---|
| `staff_history.json` | `staff_history` | 394 | HR staff movements; no `id` field — uses (staff_code, effective_date) pattern; multiple rows per staff allowed |
| `pipeline.json` | `pipeline` | 294 | Sales pipeline; `backup_staff_codes` list + `actions_due` list of dicts + `win_probability_ai_factors` dict all flow through `data` JSONB |
| `lms_enrollments.json` | `lms_enrollments` | 1146 | High-volume training records; `completion_date` + `due_date` VARCHAR (530+616 empty); composite PK `(staff_code, course_id)` |
| `edms_documents.json` | `edms_documents` | 500 | Document management; `review_date` is 500/500 empty so VARCHAR; `tags` list → data JSONB |
| `revenue_assurance.json` | `revenue_assurance` | 300 | Revenue leakage tracking (revenue_assurance arc data; arc closed at G133+G134); indexed on status + type + period + recovered |
| `treasury_fx.json` | `treasury_fx` | 200 | FX deals; clean flat structure |
| `credit_admin.json` | `credit_admin` | 214 | Credit ops disbursement readiness; `disbursement_date` VARCHAR (175/214 empty/None); `conditions` list of dicts → data JSONB |

PG coverage moved **34/52 → 41/52** (65.4% → **78.8%**). Hit the v10.89 forecast exactly.

### 2. Automated migration consistency check (`check_migration_consistency()`)

Per the v10.89 honest acknowledgment that the flat-cols-vs-schema verifier should be automated, this drop folds it into `scripts/audit_completion_state.py`. Every state report now runs it and surfaces:

- **Mismatches:** tables whose FLAT_MIGRATIONS column tuple has columns missing from the corresponding CREATE TABLE block. This is what caught the v10.88 `notes` drop on asset_register and the v10.89 mismatches.
- **Duplicate tables:** tables with >1 CREATE TABLE statement in `utils/db.py`. This is what caught the v10.88 aml_alerts duplication and v10.89 loan_applications duplication.

Current state: **31/31 entries verified clean, no duplicates**. The check runs in ~50ms — cheap enough to run before every drop ships.

The check is also surfaced in `--json` output so future automation can consume it.

### 3. Phase 3 deferral note

Two places now display the deferral:
- `SCOPE_LEDGER.md` top-of-document directive note locks the policy
- `scripts/audit_completion_state.py` Phase 3 block adds "(Per Joshua's directive at v10.90: deferred to end; planned after Phase 1 + Phase 2 close)" so it shows up in every state report

The four items remain visible in the report so they're never silently forgotten — just deprioritized until the structured flow gets to them.

---

## What v10.91 covers

Phase 1A close-out. Targets to reach 52/52 (100%):

Looking at the remaining ~11 tables needed, the top-priority candidates from the uncovered list (sorted by operational significance):

1. `referrals.json` (200 records, 106 KB)
2. `consent_register.json` (200 records, 106 KB) — DPO compliance
3. `collateral_register.json` (200 records, 106 KB) — credit collateral
4. `execute_initiatives.json` (61 records, 143 KB) — strategic execution
5. `projects.json` (40 records, 135 KB)
6. `cards_register.json` if present
7. Plus 5-6 simpler remaining files

That batch should bring coverage to ~50/52 (~96%). One final small drop closes Phase 1A.

After Phase 1A closes (estimated v10.92), Phase 1B begins — surfacing existing engine outputs as FastAPI endpoints to grow the 35→136 endpoint count.

---

## Files changed

- **MOD** `utils/db.py` (7 new CREATE TABLE blocks)
- **MOD** `scripts/migrate_to_postgres.py` (7 new FLAT_MIGRATIONS entries)
- **MOD** `scripts/audit_completion_state.py` (added `check_migration_consistency()` + Phase 3 deferral note)
- **MOD** `SCOPE_LEDGER.md` (v10.90 progress + Phase 3 directive note + Phase 1A table updated)
- **NEW** `CHANGELOG_v10.90.md` (this file)

## Files NOT changed (deliberately)

- `standards_registry.py` — no new standards (continuation_doc still 51, research_addition still 90)
- `scenario_simulator.py` — no scenarios (migration code is infrastructure, not engine architecture)
- `scripts/audit.py` — G142 unchanged (floor stays at 51)
- All closed-arc files — closure invariants preserved
- `pages/7_admin.py` — no Tier changes

## Honest acknowledgements

**The v10.89 forecast was off by 0.** Predicted "v10.90 brings coverage to ~41/52 (~79%)". Actual: 41/52 (78.8%). Coincidence, but worth noting that the forecasting is now reliable enough that I can reasonably commit to per-drop targets.

**`staff_history` has no primary key.** Source JSON has no `id` field; staff can have multiple movements. Schema declares all columns NOT NULL on staff_code only. If duplicate (staff_code, effective_date) rows ever appear in the JSON, both insert. Acceptable for this use — staff history is naturally append-only — but worth flagging.

**`lms_enrollments` composite PK assumes uniqueness.** The schema declares `PRIMARY KEY (staff_code, course_id)`. If the same staff member is enrolled in the same course twice (e.g., a refresh cycle), the migration would conflict. Inspection of the source data shows 1146 records with all-unique (staff_code, course_id) pairs — fine for current data but a future refresh cycle would break this. Easy fix later: add an enrollment_date or attempt_number to the PK.

**Migration consistency check has a regex limitation.** The verifier extracts schema columns from regex matches on the CREATE TABLE block. It assumes columns are formatted as `    name TYPE` with leading whitespace. Multi-line column definitions (e.g., `column NUMERIC(18, 2) NOT NULL CHECK (...)`) might trip up the column-name extraction. Currently no such columns exist in the schema, but worth flagging if someone adds CHECK constraints later. The fix would be to use a proper SQL parser (e.g., sqlglot), but for the platform's needs the regex is sufficient.

**The verifier doesn't check NESTED_MIGRATIONS or SPECIAL_MIGRATIONS column consistency.** Those use different shapes (NESTED has sub-keys, SPECIAL has handlers). NESTED entries have been verified manually during the original NESTED migration setup; SPECIAL handlers are write-once code that's verified by inspection. If those fail, the migration script's per-record exception handling logs the issue. A future enhancement could extend the verifier to handle them — but the current FLAT verifier covers the largest source of error.

**The current 41/52 target reflects current FLAT_MIGRATIONS scope.** The 52-table target was set early in the project; some of the original target tables may turn out to be redundant or covered by JSON-as-data-column patterns. The actual completion ratio for "all the JSON data needed for the platform" is harder to measure precisely. The current ratio is a reasonable proxy.

**Phase 3 deferral is documented but not yet enforced.** I won't ask for Peer Learning / FATCA / CBK / React content until Phase 1 + 2 close. There's no audit gate enforcing this; it's a process commitment. If the deferral needs to be revisited (e.g., business priority shift), it's easy to update — just remove the directive note from SCOPE_LEDGER and re-list the items as in-scope.

---

**v10.90 ships under the anti-drift protocol.** PG migration coverage 65.4% → 78.8%. Migration consistency now mechanically verified each drop. Phase 3 deferred to end per directive. Phase 1A close-out continues in v10.91 with the final ~11 tables.
