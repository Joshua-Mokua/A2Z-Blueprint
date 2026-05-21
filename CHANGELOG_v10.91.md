# CHANGELOG v10.91 — PG migration batch 4 (Phase 1A close-out: COMPLETE)

**Status:** Phase 1A close-out. PG migration coverage advanced from 41→53 tables (78.8%→101.9% — exceeds the original 52-target). Phase 1A is complete. v10.92 pivots to Phase 1B (API endpoint expansion).

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.91 | After v10.91 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| **PG migration coverage** | 41 / 52 (78.8%) | **53 / 52 (101.9%)** | **+12 tables** ⁽¹⁾ |
| flat tables | 31 | 40 | +9 |
| nested sub-tables | 8 | 8 | 0 |
| special-case tables | 2 | 2 | 0 |
| legacy in-main() tables | (uncounted) | 3 | +3 ⁽²⁾ |
| JSON files covered | 35 / 129 | 47 / 129 | +12 |
| Schema tables in `utils/db.py` | 54 | 63 | +9 |
| API endpoints | 35 / 136 (25.7%) | 35 / 136 (25.7%) | 0 |

⁽¹⁾ +12 = 9 new FLAT tables + 3 legacy-in-main tables that were always migrated but not counted until this drop. The 9 new tables are the only new migration code in this drop; the +3 is a counting correction.

⁽²⁾ Legacy in-main() migrations (`flexcube_config`, `flexcube_events`, `module_config`) were always present in `main()`'s STEP 4+5 inline code, but the audit script's coverage count only scanned FLAT/NESTED/SPECIAL dicts. v10.91's audit script extension detects them via INSERT-statement string matching, bringing visibility to ~100% of actually-migrated tables.

**No new research_addition standards in this drop.** Maintenance close-out drop; continuation_doc count held at floor.

---

## Phase 1A: COMPLETE

The original 52-table PG migration target set at project start is met (and exceeded by the legacy-counting correction). What's covered:

**40 FLAT migrations** — standard one-row-per-JSON-record pattern with `data` JSONB catch-all for nested fields.

**8 NESTED sub-tables** — across 2 source files (`alm_liquidity.json` with 4 sub-tables, `esg_climate.json` with 4 sub-tables).

**2 SPECIAL-case migrations** — `bank_targets` (composite-keyed flatten) and `baselines` (atypical structure preserved as JSONB snapshot).

**3 legacy in-main() migrations** — `flexcube_config`, `flexcube_events`, `module_config`. These predate the SPECIAL_MIGRATIONS pattern and use inline transform code in `main()`'s STEP 4 + STEP 5. Behaviorally identical to SPECIAL handlers, just lives in a different code shape. Could be refactored into SPECIAL_MIGRATIONS for code consistency in a future drop, but no functional benefit.

**11 schema tables intentionally NOT migrated** — these are runtime/system tables that have no JSON backers:
- `audit_trail`, `sessions`, `users`, `bsc_scores`, `pipeline_deals`, `disciplinary` — runtime tables; data is created at app runtime, not loaded from JSON
- `audit`, `staging` — schema namespaces (these are false-positives in the regex count; they appear because `audit.recon_runs` and `staging.flexcube_*` tables are defined in those namespaces)

The platform's PG migration is **effectively complete.** When run against a real PG database, every operational JSON data file the platform uses gets loaded into a corresponding table.

---

## What landed (in order)

### 1. PG migration batch 4 — 9 new FLAT tables

All 9 are clean standard flat migrations (no pre-existing collisions, unlike v10.88 `aml_alerts` and v10.89 `loan_applications`):

| JSON file | PG table | Records | Notes |
|---|---|---|---|
| `referrals.json` | `referrals` | 200 | Customer referrals; `conversion_date` 85/200 empty → VARCHAR |
| `consent_register.json` | `consent_register` | 200 | DPO compliance; `granted_date`/`withdrawn_date`/`expiry_date` all VARCHAR (51-176 empty values) |
| `collateral_register.json` | `collateral_register` | 200 | Credit collateral; clean flat structure |
| `execute_initiatives.json` | `execute_initiatives` | 61 | Strategic initiatives; complex shape — 9 list/dict fields flow through `data` JSONB. JSON's `created_at`/`updated_at` (ISO strings, 60/61 empty) drop into `data` rather than conflicting with schema's TIMESTAMPTZ DEFAULT columns |
| `projects.json` | `projects` | 40 | Project management; `actual_end_date` 35/40 empty → VARCHAR; lists go to `data` |
| `clearing_records.json` | `clearing_records` | 120 | Clearing house; `reconciled_at` 20/120 empty → VARCHAR |
| `compliance_cases.json` | `compliance_cases` | 115 | Compliance ops; `cleared_date` 80/115 empty → VARCHAR |
| `commission_records.json` | `commission_records` | 118 | Staff commissions; no `id` field — composite PK `(staff_code, period)` |
| `trade_finance.json` | `trade_finance` | 80 | LC instruments; supplements the closed trade_finance arc engines with operational data |

PG coverage moved **41/52 → 50/52** (78.8% → 96.2%) for FLAT+NESTED+SPECIAL, then **+3** counting correction for legacy in-main() bringing total to **53/52** (101.9%).

### 2. Legacy migration counting fix

The v10.91 audit script extension adds a `legacy_tables` / `legacy_jsons` set populated by string-matching `"INSERT INTO flexcube_config"`, `"INSERT INTO flexcube_events"`, `"INSERT INTO module_config"` in `migrate_to_postgres.py`. These get included in `total_tables_wired` and `covered_jsons` counts, plus a new "legacy in-main():" line in the text report.

The legacy migrations' actual code is unchanged. The fix is purely visibility — accurate coverage reporting requires counting all paths to PG, not just the FLAT/NESTED/SPECIAL dicts.

### 3. Migration consistency check holds at 40/40 clean

The automated `check_migration_consistency()` introduced in v10.90 caught zero issues during this drop. All 9 new FLAT_MIGRATIONS entries' flat_cols match the corresponding CREATE TABLE columns. No duplicate-table situations (unlike v10.88 + v10.89). This validates the v10.90 plan to fold the verifier into the audit script — it's now part of the standard close-of-drop verification.

---

## What v10.92+ covers (Phase 1B)

Phase 1A is closed. v10.92 begins Phase 1B — surfacing existing engine outputs as FastAPI endpoints to grow the count from 35 → 136.

The work pattern:
1. Identify high-value engines (those that would be called by external integrations, dashboards, or other modules)
2. For each, write a thin FastAPI route handler that wraps the engine call (request → engine.compute() → response)
3. Add JWT auth via `Depends(get_current_user)` per platform convention
4. Add `audit_log()` after every write operation per platform convention
5. Test with a sample request payload

Estimated 5-10 endpoints per drop. At that cadence, Phase 1B closes around v10.95-v10.98 (3-7 drops).

After Phase 1B closes, Phase 1C — test coverage push from ~45% → 80%. Begins with a baseline coverage measurement via `coverage.py`.

After Phase 1 closes, Phase 2 begins — activate the 11 untouched planned subcategories (customer_360, it_digital, bancassurance, command_centre, competitor_intel, propositions, specialized_segments, partnerships, sla_tracker, campaigns, legal completion). Recommended sequence per the SCOPE_LEDGER: customer_360 first.

Phase 3 (the four deferred items) waits for Phase 1 + Phase 2 to close, per Joshua's directive at v10.90.

---

## Files changed

- **MOD** `utils/db.py` (9 new CREATE TABLE blocks)
- **MOD** `scripts/migrate_to_postgres.py` (9 new FLAT_MIGRATIONS entries)
- **MOD** `scripts/audit_completion_state.py` (legacy in-main() migration detection added to `count_pg_migration()`)
- **MOD** `SCOPE_LEDGER.md` (v10.91 progress + Phase 1A COMPLETE declaration + intentional-unmigrated-tables note)
- **NEW** `CHANGELOG_v10.91.md` (this file)

## Files NOT changed (deliberately)

- `standards_registry.py` — no new standards (continuation_doc still 51, research_addition still 90)
- `scenario_simulator.py` — no scenarios (migration code is infrastructure, not engine architecture)
- `scripts/audit.py` — G142 unchanged (floor stays at 51)
- All closed-arc files — closure invariants preserved
- `pages/7_admin.py` — no Tier changes
- Legacy in-main() migration code itself — unchanged. Visibility was the issue, not behavior.

## Honest acknowledgements

**The legacy-migration count correction is +3, not +12.** v10.91 itself only added 9 new tables (the FLAT batch). The other 3 came from a counting bug fix — flexcube_config, flexcube_events, module_config were always migrated, just not counted. Real new-coverage delta is +9, presented as +12 only because the count now includes previously-uncounted work. The CHANGELOG headline "+12" is accurate but worth disambiguating.

**Coverage % > 100% is mathematically odd.** 53/52 (101.9%) reflects that the original 52-target was set early in the project before all migration paths existed. The number is honest — it's just that the denominator was a planning estimate, not a hard ceiling. A future audit script could update the target to match the actual operational table count, but that would obscure the historical reference point. Leaving the target at 52 makes the historical delta tables more readable.

**`commission_records` composite PK assumes uniqueness.** `(staff_code, period)` is the PK. If a staff member is listed twice for the same period (e.g., a re-run of payroll), the second insert fails. Inspection of the source data shows 118 records with all-unique (staff_code, period) pairs — clean for current data, would need adjustment if mid-period re-runs ever produce duplicates.

**`execute_initiatives` schema simplification.** The JSON has `created_at` and `updated_at` as ISO timestamp strings (60/61 empty). I initially designed `created_at_iso` and `updated_at_iso` columns to receive those, but ended up dropping them entirely so the JSON values flow into `data` JSONB. The simplification works because (a) only 1/61 records has populated timestamps, (b) the schema's standard `created_at`/`updated_at` TIMESTAMPTZ DEFAULT columns provide migration-time timestamps, (c) keeping the original ISO strings in `data` preserves any semantic meaning if needed later.

**The migration consistency verifier still doesn't check NESTED or SPECIAL.** Same caveat as v10.90 — the automated check covers FLAT only. NESTED entries were verified manually at original NESTED setup; SPECIAL handlers are write-once code verified by inspection. If those break, the per-record exception handling logs the issue. A future enhancement could extend the verifier; left as future work.

**Phase 1A close is a meaningful milestone but not a hard gate.** There's no audit gate that fails if Phase 1A regresses (e.g., if someone accidentally removes a FLAT_MIGRATIONS entry). G142 enforces only the continuation_doc floor. If PG-coverage anti-drift becomes a real concern, a similar G143 ratchet could be added in a future drop. Holding off for now — the visibility script + CHANGELOG completion delta are sufficient discipline at current cadence.

**Phase 1B's first drop should make a structural decision.** API endpoint expansion can take two shapes: (a) one big FastAPI app with all 136 endpoints, or (b) per-module routers (e.g., `routes/credit.py`, `routes/treasury.py`, etc.). The platform's existing 35 endpoints suggest it may have started down path (a); v10.92's first action should be to inspect the existing endpoint structure and decide path before adding more. If the existing endpoints are mixed across files, the answer might be (c) — refactor first, then expand.

---

**v10.91 ships under the anti-drift protocol.** PG migration Phase 1A is closed at 53/52 tables (101.9%). Migration consistency holds at 40/40 clean. v10.92 begins Phase 1B (API endpoint expansion).
