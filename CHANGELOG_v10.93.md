# CHANGELOG v10.93 — Phase 1B continuation: 3 more CRUD modules + TABLE_USE_DB sync

**Status:** Phase 1B continuation. Discovered + fixed a structural gap between TABLE_USE_DB and PG migration tracks (they evolved in parallel without sync), then wired 3 more CRUD modules. API endpoint coverage moves from 51→75 (37.5%→55.1%).

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean (no PG schema changes)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.93 | After v10.93 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| **API endpoints** | 51 / 136 (37.5%) | **75 / 136 (55.1%)** | **+24** |
| **TABLE_USE_DB enabled** | 19 | **48** | **+29** ⁽¹⁾ |

⁽¹⁾ +27 from new entries for v10.88-v10.91 PG-migrated tables (the gap fix), +2 from flipping stale placeholder entries (`referrals`, `compliance_cases`) that pre-existed as `False` but now have real schemas.

**No new research_addition standards in this drop.** Maintenance + infrastructure work; continuation_doc count held at floor.

---

## What landed (in order)

### 1. Discovered the TABLE_USE_DB / PG-migration gap

The original v10.93 plan was to wire 3 CRUD modules: `assets`, `vendors`, `purchase_orders` (the candidates flagged in v10.92's "next CRUD candidates" list because they were in `TABLE_USE_DB=True`). Pre-flight check found:

- `vendors.json` doesn't exist in `data/`
- `assets` and `purchase_orders` have no schema in `utils/db.py` (despite being in TABLE_USE_DB)
- `asset_register` (the table that DOES have a schema + migration, paired with `asset_register.json` from v10.88) is NOT in TABLE_USE_DB at all

Looked further: of the 25 PG-migrated tables from v10.88-v10.91 PG batches, **zero** were in `TABLE_USE_DB`. The two registries evolved in parallel — TABLE_USE_DB grew from project-start convention, PG migrations grew from Phase 1A work — without a sync mechanism between them.

This gap matters because `make_crud_router()` requires the table to be in `TABLE_USE_DB`. Without it, the factory's `_check_table()` whitelist check fails. So Phase 1B couldn't wire any of the 25 freshly-migrated tables until this gap was closed.

### 2. TABLE_USE_DB sync — 27 new entries

Added 27 entries to `TABLE_USE_DB` in `utils/db.py`, all set to `True` since each has both a CREATE TABLE schema in this file AND a FLAT/SPECIAL migration in `scripts/migrate_to_postgres.py`:

- **v10.88 (5):** agent_fraud_alerts, agents_data, agent_transactions, asset_register, bid_bonds
- **v10.89 (9):** ifrs9_loans, legal_matters, rms_reconciliations, debt_recovery, cims_tickets, treasury_fd, bnc_policies, bank_targets, baselines
- **v10.90 (7):** staff_history, pipeline, lms_enrollments, edms_documents, revenue_assurance, treasury_fx, credit_admin
- **v10.91 (6):** consent_register, collateral_register, execute_initiatives, clearing_records, commission_records, trade_finance

Plus flipped 2 stale placeholder entries from `False` to `True`:
- `referrals` (line 105) — entry pre-existed for a different planned table; v10.91 migration created the actual schema
- `compliance_cases` (line 92) — same situation

The flip is safe because the table now has a schema (`CREATE TABLE IF NOT EXISTS referrals` exists in `utils/db.py` from v10.91) and a FLAT_MIGRATIONS entry. Setting True means reads come from PG when populated; the JSON fallback still works for empty tables.

### 3. 3 new CRUD modules (+24 endpoints)

Picked the 3 highest-value tables from the 27 newly-eligible entries:

| Module | Table | Records | Why this priority |
|---|---|---|---|
| `ifrs9_loans` | `ifrs9_loans` (PK: `account_id`) | 5045 | High-volume; IFRS 9 ECL is core credit-risk concern; stage-by-stage filtering is the most common query in credit dashboards |
| `legal_matters` | `legal_matters` (PK: `id`) | 362 | Legal arc operations; SLA breach status is the priority filter |
| `collateral_register` | `collateral_register` (PK: `id`) | 200 | Credit collateral inventory; LTV ratio + status drives credit governance queries |

Each module gets 8 CRUD verbs via `make_crud_router()`. All inherit JWT auth, audit logging, and PG/JSON fallback automatically.

For `ifrs9_loans`, the `pk_column="account_id"` parameter overrides the factory's default (`id`) — important because this table uses `account_id` as PK per the IFRS 9 reporting convention.

For `legal_matters`, `searchable=` includes `sla_breached` (BOOLEAN) — the legal team's most common operational query is "what matters are SLA-breached and need escalation."

For `collateral_register`, `order_by="market_value DESC"` — credit governance reviews start from highest-value collateral.

---

## Why not assets / vendors / purchase_orders (the v10.92 candidates)

The v10.92 CHANGELOG flagged these three as the v10.93 targets. None of them turned out to be CRUD-ready:

**`vendors`** — no source JSON. `data/vendors.json` doesn't exist. The TABLE_USE_DB entry pre-dates any data file; the table was probably planned for procurement workflow that never reached data-population stage. Wiring CRUD against an empty table is technically possible (the factory would work, just return empty results), but it's lower value than wiring tables with real data.

**`assets`** — TABLE_USE_DB entry pre-exists but no schema. The actual asset-related table is `asset_register` (added v10.88), which has different name semantics. The right move would be to either (a) rename the TABLE_USE_DB entry to match the schema (potential breaking change for any code that referenced "assets"), or (b) add a separate `assets` schema.

**`purchase_orders`** — TABLE_USE_DB entry exists but no schema, no migration, no JSON file. Same situation as `vendors` — registered intent, never built.

The v10.93 work updates the SCOPE_LEDGER's "next CRUD candidates" list to reflect the corrected picture: **15 truly-eligible tables** (TABLE_USE_DB=True + has schema + PG-migrated + has source JSON), of which 3 are wired this drop. Remaining 12 are candidates for v10.94+.

---

## What v10.94 covers

Phase 1B continues. Targets in priority order from the 12 remaining eligible tables:

1. **`agent_transactions`** (679 records) — high-volume agent banking ops; needed for fraud detection workflow
2. **`debt_recovery`** (150 records) — NPL recovery tracking; close to credit ops priority
3. **`cims_tickets`** (200 records) — customer instructions; SLA-driven workflows

That batch adds +24 endpoints → ~99/136 (~73%). One more drop after that closes Phase 1B at ~123/136 (~90%) with a few direct-decorator endpoints to reach the 136 target.

---

## Files changed

- **MOD** `utils/db.py` (27 new TABLE_USE_DB entries; 2 flipped from False to True)
- **MOD** `utils/api.py` (3 new `make_crud_router()` calls)
- **MOD** `SCOPE_LEDGER.md` (Phase 1B section updated; corrected next-candidates list)
- **NEW** `CHANGELOG_v10.93.md` (this file)

## Files NOT changed (deliberately)

- `scripts/audit.py` — no audit changes (G16 still passes, G142 still locks the floor)
- `scripts/audit_completion_state.py` — methodology from v10.92 produces correct counts
- `scripts/migrate_to_postgres.py` — Phase 1A is frozen
- `standards_registry.py` — no new standards
- `utils/api_crud.py` — factory unchanged; just consumed by 3 more module calls
- All closed-arc files — closure invariants preserved

## Honest acknowledgements

**The TABLE_USE_DB / PG-migration desync should have been caught earlier.** I had visibility into both registries during v10.88-v10.91 PG batches. I added schemas + migrations correctly each drop but didn't update TABLE_USE_DB at the same time. The v10.92 CHANGELOG even flagged "side decision needed for v10.93: several existing PG-migrated tables are NOT in TABLE_USE_DB at all" — but framed it as a design choice rather than a bug. It was a bug. The fix is +27 entries here; the meta-fix is to make TABLE_USE_DB updates a checklist item for every future PG migration.

**Should TABLE_USE_DB updates be enforced by an audit gate?** Possible G143: "every table in FLAT_MIGRATIONS must have a TABLE_USE_DB entry, and every TABLE_USE_DB entry with True must have either a schema or be a known runtime table." Holding off for v10.93 — visibility script + this CHANGELOG should make it visible. If it desyncs again in v10.94+, G143 becomes warranted.

**`referrals` and `compliance_cases` flip from False to True is a behavioral change for any existing code.** Code that previously relied on the JSON fallback now reads from PG. If the PG table is empty, reads return empty. If the JSON file has data the PG table doesn't, those reads break. Mitigation: when migration is run against a real PG, the JSON gets loaded into PG, so reads stay consistent. For local development without PG, behavior is unchanged. Worth flagging because it's the kind of thing that surfaces only at deploy time.

**The v10.92 CHANGELOG's "next CRUD candidates" list was wrong on three counts (vendors/assets/purchase_orders).** All three appeared eligible in TABLE_USE_DB but failed the deeper check. The SCOPE_LEDGER's updated list in v10.93 reflects the corrected picture. Going forward, the next-candidates list should distinguish "TABLE_USE_DB enabled" from "fully CRUD-ready" (TABLE_USE_DB + schema + migration + source JSON).

**`ifrs9_loans` CRUD endpoints expose 5045 records.** That's not a security concern (JWT auth gates them), but list operations should ideally use pagination. The factory's list endpoint defaults to first 500 records (per the factory's `limit=500` default in `_SearchCriteria`). For 5045 records, full extraction needs 11 list calls or one export call. The export endpoint should handle this fine, but worth flagging that a "load all" pattern needs the export endpoint, not the list endpoint.

**`bnc_policies` is a high-value candidate but bancassurance subcategory is 0/10 active in standards.** The PG table exists, the data is migrated, the table is now in TABLE_USE_DB. CRUD wiring would expose bancassurance operational data to consumers — but the bancassurance domain logic (in the planned subcategory standards) hasn't been built. The endpoint would be functional but the operations layer above it would be missing. Holding off on bnc_policies CRUD until bancassurance subcategory work begins (Phase 2). Same caveat for `treasury_fx`, `treasury_fd`, `trade_finance` — operationally PG-ready but the higher-level standards aren't all active yet.

**Phase 1B is mechanically simple but requires good judgment about which tables to wire.** Each `make_crud_router()` call is one line of code. The harder question is which tables warrant generic CRUD vs which need specialized endpoints. The factory's pattern works well for tables where the CRUD verbs map cleanly (list collateral, get a single matter, etc.). For tables where domain logic dominates (e.g., where a "create" needs to invoke 5 engines, run scenario simulation, audit log to multiple destinations), direct decorators in api.py are better. The current cadence is wiring the easy CRUD cases first; the harder ones come in later phases.

---

**v10.93 ships under the anti-drift protocol.** API endpoints 51 → 75 (37.5% → 55.1% of 136 target). TABLE_USE_DB synced with v10.88-v10.91 PG migrations (+27 entries + 2 flips). Phase 1A remains COMPLETE; Phase 1B IN PROGRESS. v10.94 continues with 3 more CRUD modules (agent_transactions, debt_recovery, cims_tickets), targeting ~99/136 (~73%).
