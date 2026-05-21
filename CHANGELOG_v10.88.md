# CHANGELOG v10.88 — Anti-drift mechanism + PG migration batch 1 (Phase 1A)

**Status:** Structural pivot. After Joshua flagged drift in the v10.87 review, this drop establishes the anti-drift protocol that governs subsequent work + executes the first concrete batch under that protocol (PG migration Phase 1A).

**Audit:** 141/141 PASS (closure invariants preserved)
**Engine self-tests:** 152/152 (unchanged)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.88 | After v10.88 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 10 / 52 (19.2%) | **16 / 52 (30.8%)** | **+6 tables** |
| API endpoints | 35 / 136 (25.7%) | 35 / 136 (25.7%) | 0 |
| Schema tables in `utils/db.py` | 38 | 44 | +6 |
| JSON files covered | 10 / 129 | 16 / 129 | +6 |

**No new research_addition standards in this drop.** Per anti-drift Rule C, this is intentional — the drop's whole point is closing existing gaps, not adding new ones.

---

## What landed (in order)

### 1. SCOPE_LEDGER.md (new at repo root)

Source of truth for what's outstanding. Documents three phases of work with explicit definitions of done, an audit-gate floor for continuation_doc active count (locked at 51), and three anti-drift rules:

- **Rule A — Phase priority.** Phase 1 maintenance (PG migration, API endpoints, test coverage) and Phase 2 planned-spec activation take precedence over new research_addition arcs. New arcs require explicit user sign-off.
- **Rule B — CHANGELOG completion delta.** Every CHANGELOG includes the four headline numbers before/after. Missing section = incomplete drop.
- **Rule C — No silent additions.** New research_addition standards require offsetting continuation_doc activation OR explicit user request.

The ledger lists Phase 3 items I'm blocked on for spec content from Joshua (Peer Learning #14–#20, FATCA/CRS XML, deferred CBK reports, React #37–#38).

### 2. scripts/audit_completion_state.py (new)

Produces the structured state report each drop. Counts standards by source + status, PG migration coverage from FLAT_MIGRATIONS, API endpoint count from `@app/@router` decorators across the codebase. Two output modes: text (human-readable, default) and JSON (machine-readable for CHANGELOG inclusion).

The script is what makes drift mechanically visible. Running `python3 scripts/audit_completion_state.py` before and after any drop instantly shows whether the drop made progress on the four headline dimensions or quietly reverted them.

A future v10.89 enhancement could promote this into an audit gate G142 that ratchets the continuation_doc active floor (currently 51) — any drop that reduces it would fail audit. Not adding the gate yet because the floor mechanism needs one or two drops of operational feedback first.

### 3. PG migration batch 1 — six new tables

Phase 1A first execution. Six high-value JSON data files now wired through the migration pipeline:

| JSON file | PG table | Records | Notes |
|---|---|---|---|
| `agent_fraud_alerts.json` | `agent_fraud_alerts` | 15 → ~150 prod | Lists (`txn_ids`, `amounts`) flow through `data` JSONB catch-all |
| `agents_data.json` | `agents_data` | 150 | Agent banking master data |
| `agent_transactions.json` | `agent_transactions` | 679 → millions | High-volume; indexed on agent_id + txn_date + fraud_flag |
| `aml_alerts.json` | `aml_alerts` (existing) | 120 | Pre-existing table extended with `data` column for migration compatibility; RLS preserved |
| `asset_register.json` | `asset_register` | 200 | Fixed asset register; `disposal_date` as VARCHAR (data has empty strings) |
| `bid_bonds.json` | `bid_bonds` | 50 | Trade-finance bonds; CBK-reportable flag preserved |

Schema additions in `utils/db.py` follow the established platform pattern: `VARCHAR(50)` primary key, type-appropriate columns, `data JSONB DEFAULT '{}'` catch-all, `created_at` + `updated_at` timestamps. Indexes added for the columns operations actually filters on (status, agent_id, date, fraud flags).

`scripts/migrate_to_postgres.py` extended with corresponding `FLAT_MIGRATIONS` entries. The standard `insert_records` flow applies — flat columns get their own typed column, everything else collapses into the `data` JSONB blob.

### 4. Discoveries during the work

A pre-existing `aml_alerts` table was found at line 1010 of `utils/db.py` from earlier work — defined with full RLS but **without a `data JSONB` column**, meaning it was never compatible with the migration pipeline. The fix added the missing column without disturbing the RLS policy, so AML compliance access controls remain enforced.

Two issues were caught by the in-line verifier during this drop that wouldn't have surfaced until the migration script actually ran against PG:
- `notes` was accidentally dropped from the `asset_register` schema during initial editing
- `txn_ids` and `amounts` were initially in `agent_fraud_alerts` flat_cols but they're list values that don't fit a regular column — moved to `data` catch-all

Both were caught by a small verification script that compares each FLAT_MIGRATIONS entry's column tuple against the actual `CREATE TABLE` block. Worth keeping that verifier as part of the migration workflow — easy enough to fold into `scripts/audit_completion_state.py` in a future drop.

---

## What v10.89 covers

PG migration batch 2 — another 6-10 tables. Targets in priority order:

1. **`alm_liquidity.json`** (167 KB) — ALM data; complex because it's a DICT with 4 sub-tables (`gap_analysis`, `funding_sources`, `alco_meetings`, `contingency_plans`). One of these (`alm_gap_analysis`) is partially defined in NESTED_MIGRATIONS already; needs completion of the other three.
2. **`bank_targets.json`** (3 KB) — DICT keyed by composite "metric|year" pattern; needs structure decision (single table with metric+year+value columns, or one row per metric per year).
3. **`baseline_2025_Dec.json`** (100 KB) — atypical structure with `branch` and `rm` sub-DICTs; may not need a flat table at all (could go entirely into `data` JSONB).

Plus 3-5 simpler files from the remaining 113 uncovered. Should bring coverage to ~24/52 (~46%).

After v10.89, evaluate whether to push further on PG (Phase 1A) or pivot to API endpoint expansion (Phase 1B).

---

## Files changed

- **NEW** `SCOPE_LEDGER.md` (anti-drift source of truth)
- **NEW** `scripts/audit_completion_state.py` (state report producer)
- **MOD** `utils/db.py` (6 new CREATE TABLE blocks; 1 ALTER on existing aml_alerts)
- **MOD** `scripts/migrate_to_postgres.py` (6 new FLAT_MIGRATIONS entries)
- **NEW** `CHANGELOG_v10.88.md` (this file)

## Files NOT changed (deliberately)

- `standards_registry.py` — no new standards. Phase 1A maintenance work doesn't add to the active count; it advances PG coverage instead. The completion-state report tracks PG separately from standards.
- `scenario_simulator.py` — no scenarios. Migration code isn't engine-architecture; the verification is in the audit script + `scripts/migrate_to_postgres.py` itself when run against PG.
- All closed-arc files (`utils/mlops_*`, `utils/trade_finance_*`, etc.) — closure invariants preserved.
- `pages/7_admin.py` — no Tier changes; PG migration isn't a tier.
- `scripts/audit.py` — G142 deferred to v10.89 pending feedback on the soft-floor mechanism. The current audit (141/141) is unchanged.

## Honest acknowledgements

**The audit script doesn't fail on drift yet.** It surfaces drift, but doesn't block it. That's deliberate for v10.88 — operational feedback first, hard enforcement second. If the mechanism is working (Joshua sees state each drop and the discipline holds), G142 in v10.89 will lock the continuation_doc active floor and any drop reducing it will fail audit.

**FLAT_MIGRATIONS' duplicate-detection isn't enforced.** I found the pre-existing `aml_alerts` by checking, but the migration script wouldn't have caught it on its own — the second `CREATE TABLE IF NOT EXISTS` would have silently no-op'd. A future enhancement to `audit_completion_state.py` could check for tables defined twice in `utils/db.py` and surface them as warnings.

**"PG migration coverage" is JSON-files-covered, not records-migrated.** The script counts how many JSON files have FLAT_MIGRATIONS entries. It doesn't count how many records have actually been written to PG (that requires a live connection). The latter is a separate workstream — when Joshua runs `migrate_to_postgres.py` against the actual database, the script's per-table report covers that.

**The continuation_doc active count didn't change in this drop.** This is the right outcome under the new protocol: the drop's value is in PG progress and structural anti-drift mechanism, not in activating new standards. But it does mean the 31.3% completion ratio hasn't moved. Closing that gap requires either (a) Joshua sharing spec content for the Phase 3 blocked items, or (b) activating Phase 2 planned subcategories using their existing descriptions. Both are open paths.

**`bank_targets.json` and the nested files are deferred deliberately.** The DICT-keyed-by-composite structure of `bank_targets` and the nested structure of `alm_liquidity` need design decisions (one table per sub-key vs flatten-with-key-as-column). Easier to handle in v10.89 with focus, rather than rushing them into batch 1.

**Six tables in one batch is a deliberate choice over twelve.** Bigger batches mean more chances for column-mismatch errors like the ones caught above. Smaller batches with thorough verification are more reliable. Joshua can tell me to push more aggressively if the cadence feels too slow.

---

**v10.88 ships under the anti-drift protocol** that will govern v10.89 and beyond. PG migration coverage moved 19.2% → 30.8%. Continuation_doc and research_addition counts unchanged (no new standards added; closure invariants preserved). Phase 1A continues in v10.89 with another 6-10 tables.
