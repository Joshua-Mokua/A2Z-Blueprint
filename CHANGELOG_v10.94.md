# CHANGELOG v10.94 — Phase 1B continuation: 3 more CRUD modules

**Status:** Phase 1B continuation. Smooth execution drop — pre-flight check passed cleanly (no surprises like v10.93's TABLE_USE_DB gap), all 3 candidates fully CRUD-ready. API endpoint coverage moves 75→99 (55.1%→72.8%). Phase 1B is on track to close at v10.96 (next 1-2 drops).

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean (no PG schema changes)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.94 | After v10.94 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| **API endpoints** | 75 / 136 (55.1%) | **99 / 136 (72.8%)** | **+24** |
| TABLE_USE_DB enabled | 48 | 48 | 0 |
| CRUD factory modules | 7 | **10** | +3 |

**No new research_addition standards in this drop.** Maintenance work; continuation_doc count held at floor.

---

## What landed (in order)

### 1. Pre-flight check passed cleanly

The 3 v10.93-flagged candidates (`agent_transactions`, `debt_recovery`, `cims_tickets`) were verified for all 4 prerequisites:

| Module | Source JSON | Schema | FLAT_MIGRATIONS | TABLE_USE_DB |
|---|---|---|---|---|
| agent_transactions | ✓ 679 records | ✓ | ✓ | True |
| debt_recovery | ✓ 150 records | ✓ | ✓ | True |
| cims_tickets | ✓ 200 records | ✓ | ✓ | True |

No surprises like v10.93's TABLE_USE_DB gap — the v10.93 sync (+27 entries) made all v10.88-v10.91 PG-migrated tables CRUD-eligible. The pre-flight check is now a quick green-pass for these candidates because the registries are aligned.

### 2. 3 new CRUD modules (+24 endpoints)

| Module | Records | Searchable | Order by | Why this priority |
|---|---|---|---|---|
| `agent_transactions` | 679 (→ millions in prod) | agent_id, branch, txn_type, fraud_flag, txn_date | txn_date DESC | Agent banking fraud-detection workflow runs against this table; agent_id + fraud_flag are the two most-used filters |
| `debt_recovery` | 150 | status, recovery_stage, client_cif, rm_code, legal_referral, branch | npl_days DESC | NPL recovery; recovery_stage segments early/letter/legal/written-off; legal_referral surfaces matters needing legal-arc handoff |
| `cims_tickets` | 200 | status, priority, instruction_type, branch, rm_code, client_cif | due_date ASC | Customer instructions; SLA-driven; due_date ASC surfaces soon-to-breach tickets first |

Each gets the standard 8 CRUD verbs via `make_crud_router()`: list, get, create, update, delete, export, search, dashboard. All inherit JWT auth, audit logging, PG/JSON fallback automatically.

The `order_by` choices are operationally tuned:
- `txn_date DESC` for agent_transactions matches how operations review recent activity
- `npl_days DESC` for debt_recovery surfaces the worst delinquencies first
- `due_date ASC` for cims_tickets surfaces upcoming SLA breaches first

### 3. SCOPE_LEDGER.md Phase 1B section updated

Updated the Phase 1B table with v10.94 column showing 99/136. Removed the 3 v10.94 candidates from the "remaining" list. Updated forecast: at 3 modules/drop, **Phase 1B closes at v10.96** (3 more modules → 123/136 ~90%); after 5 more modules wired by v10.97, count reaches 139/136 — exceeds target with operational-priority cushion.

---

## What v10.95 covers

Phase 1B continues. Targets in priority order from the 8 remaining CRUD-ready candidates:

1. **`compliance_cases`** (115 records) — compliance ops; high-priority because compliance workflow is currently 100% JSON-fallback
2. **`referrals`** (200 records) — customer referrals; channel-attribution analytics
3. **`consent_register`** (200 records) — DPO compliance; growing regulatory importance

That batch adds +24 endpoints → ~123/136 (~90%). One more drop after that closes Phase 1B above the 136 target with cushion.

After Phase 1B closes (~v10.96-v10.97), Phase 1C — test coverage push from ~45% → 80% via baseline coverage measurement + targeted tests for under-tested modules. v10.95+ should also start surfacing whether some currently-unwired tables are better served by direct decorators rather than generic CRUD (e.g., if a module's read pattern is summary-aggregated rather than row-by-row).

---

## Files changed

- **MOD** `utils/api.py` (3 new `make_crud_router()` calls after `collateral_register`)
- **MOD** `SCOPE_LEDGER.md` (Phase 1B table + remaining candidates list updated)
- **NEW** `CHANGELOG_v10.94.md` (this file)

## Files NOT changed (deliberately)

- `utils/db.py` — no schema changes (Phase 1A frozen; TABLE_USE_DB sync done in v10.93)
- `scripts/audit.py` — G16 still passes, G142 still locks the floor
- `scripts/audit_completion_state.py` — methodology from v10.92 produces correct counts
- `scripts/migrate_to_postgres.py` — Phase 1A frozen
- `standards_registry.py` — no new standards
- `utils/api_crud.py` — factory unchanged; just consumed by 3 more module calls
- All closed-arc files — closure invariants preserved

## Honest acknowledgements

**This drop is mechanically simple.** Three `app.include_router()` calls. The hard work was done in v10.93 (TABLE_USE_DB sync) and v10.92 (structural decision + counting fix). v10.94 just executes the pattern. That's the right shape for execution drops — when the infrastructure is right, individual additions are cheap. If every drop required substantial structural work, that'd be a sign the foundation isn't holding.

**The "+24 endpoints" framing slightly overstates new work.** Each `make_crud_router()` call IS 8 endpoints, but they're 8 templated endpoints with consistent semantics — list/get/create/update/delete/export/search/dashboard. The real new work per call is: the table's identity (which schema, which JSON), the searchable columns whitelist, and the order-by choice. That's roughly 5-6 lines of meaningful configuration per module. The factory does the rest. From a code-line perspective, +24 endpoints = ~18 lines of new code. From a capability perspective, +24 endpoints = 3 new modules with full CRUD.

**The `cims_tickets` ordering by `due_date ASC` ignores already-resolved tickets.** Tickets where `status = 'Resolved'` will still appear in list calls with their long-past due_date. For dashboard usage, the consumer would filter by `status != 'Resolved'` via the search endpoint. The list endpoint as wired is "all tickets, soonest due first" — which is fine for general queries but not optimized for the most common workflow. Future enhancement: factory could accept a `default_filter` parameter; for now, consumers handle filtering.

**`agent_transactions` is wired with simple CRUD, but fraud detection might need richer endpoints later.** The fraud-detection workflow likely involves: aggregating transactions over time windows, computing per-agent metrics, detecting unusual patterns. Those are domain-specific operations that don't fit generic CRUD. The current CRUD wiring covers the data-access layer; the fraud detection workflow would need direct-decorator endpoints in `utils/api.py` to surface engine outputs. Not blocking — the CRUD endpoints serve the data view; fraud workflow can be layered on top.

**The Phase 1B forecast assumes per-drop cadence holds.** v10.92, v10.93, v10.94 all delivered 3 modules. If a future drop needs to handle a tricky pre-existing table (similar to v10.89's `loan_applications` situation), or needs schema-side work (similar to v10.93's TABLE_USE_DB sync), the cadence might slow. The forecast is "roughly v10.96 closes Phase 1B" — could be v10.95 if smooth, v10.97-98 if surprises.

**No tests added for the new endpoints.** The existing `tests/test_api_crud.py` validates the factory pattern with a `foo` test fixture; the new modules' specific behaviors aren't tested. Per the Phase 1C plan (test coverage push), this is the right time to begin: now that there are 10 CRUD modules, test coverage gains are concrete (each module's wiring can be smoke-tested). Phase 1C begins after Phase 1B closes; expect test additions to start landing in v10.97+.

---

**v10.94 ships under the anti-drift protocol.** API endpoints 75 → 99 (55.1% → 72.8% of 136 target). Phase 1A remains COMPLETE; Phase 1B IN PROGRESS. v10.95 continues with 3 more CRUD modules (compliance_cases, referrals, consent_register), targeting ~123/136 (~90%) — one more drop after that closes Phase 1B.
