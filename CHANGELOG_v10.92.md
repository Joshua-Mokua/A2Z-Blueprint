# CHANGELOG v10.92 — Phase 1B kickoff: 3 new CRUD modules + API counting fix

**Status:** Phase 1B kickoff. Phase 1A (PG migration) closed in v10.91. v10.92 begins Phase 1B (API endpoint expansion) by adding 3 new CRUD modules and correcting the audit script's API counting methodology. Real coverage moves from 27 endpoints baseline to **51/136 (37.5%)**.

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean (no PG changes this drop)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.92 | After v10.92 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A complete) |
| **API endpoints** | 35 / 136 (mis-counted) → 27 real | **51 / 136 (37.5%)** | **+24 real** ⁽¹⁾ |

⁽¹⁾ The before/after numbers reflect both new work AND a counting methodology correction. The +24 figure is decomposed below:

- **+24 from new CRUD modules:** 3 × `make_crud_router()` calls × 8 verbs/call = 24 new endpoints
- **+0 net from counting correction:** the new methodology removes 8 false-positives (audit.py's own regex strings), removes test-file matches (factory test fixtures), but adds the 4 × 8 = 32 CRUD expansion accounting that was previously hidden inside an 8-decorator factory count. Net effect on the same code state would have been to surface +16 hidden endpoints (32 CRUD - 8 factory templates - 8 audit.py false-positives). 

So the corrected baseline is 27 endpoints (15 api.py direct + 8 pipeline_deals CRUD + 3 auth_jwt + 1 perf_insights), and v10.92 adds 24 to reach 51. The visibility correction was always going to surface eventually — better to do it now alongside real work.

**No new research_addition standards in this drop.** Maintenance close-out + visibility fix; continuation_doc count held at floor.

---

## Structural decision (per v10.91 plan)

The v10.91 CHANGELOG noted: "v10.92's first drop should make a structural decision — single FastAPI app vs per-module routers." After surveying the existing structure, the answer is **stay with single-app + CRUD factory**, for these reasons:

- The existing `utils/api.py` is a single FastAPI app with thematic groupings (`/api/auth/*`, `/api/bsc/*`, `/api/pipeline/*`, etc.). Adding more thematic groups follows the same pattern.
- The CRUD factory (`utils/api_crud.py`) already implements per-module routers internally — each `make_crud_router()` call returns an `APIRouter` that gets included via `app.include_router()`. So we already get the benefits of router-based organization without splitting the app file.
- The factory has 8 endpoints per call (list/get/create/update/delete/export/search/dashboard), all JWT-gated, audit-logged, and PG/JSON-fallback-aware. One `make_crud_router()` call adds 8 endpoints with consistent semantics.

**Implication for Phase 1B cadence.** Each drop wires 1-3 new CRUD modules. At 3 modules/drop = 24 endpoints/drop, Phase 1B closes in ~4 more drops (51 + 4×24 = 147, exceeding the 136 target). At 1 module/drop, ~11 more drops. Likely cadence is 2-3 modules/drop with occasional direct-decorator additions for special workflows.

---

## What landed (in order)

### 1. 3 new CRUD modules

Wired in `utils/api.py` immediately after the existing `pipeline_deals` block. All 3 are in `TABLE_USE_DB` (enabled) and have v10.88-v10.91 PG migrations completed.

| Module | Table | Source JSON | Searchable columns | Order by |
|---|---|---|---|---|
| `loan_applications` | `loan_applications` (extended pre-existing) | `loan_applications.json` | status, swim_lane, deal_category, rm_code, client_cif, compliance_flag, is_repeat_borrower | last_updated DESC |
| `aml_alerts` | `aml_alerts` (extended pre-existing, RLS-protected) | `aml_alerts.json` | status, risk_level, str_filed, assigned_to, rule_triggered | transaction_date DESC |
| `projects` | `projects` (added v10.91) | `projects.json` | status, priority, rag_status, department, project_manager, sponsor | start_date DESC |

Each module gets 8 endpoints via the factory:
- `GET /api/v1/{module}` — list with pagination
- `GET /api/v1/{module}/{id}` — single row
- `POST /api/v1/{module}` — create
- `PUT /api/v1/{module}/{id}` — update (upsert)
- `DELETE /api/v1/{module}/{id}` — delete
- `POST /api/v1/{module}/export` — bulk export
- `POST /api/v1/{module}/search` — search by criteria (whitelist)
- `GET /api/v1/{module}/dashboard` — module summary metrics

All inherit JWT auth via `Depends(get_current_user)`, audit logging via `audit_log()`, and PG/JSON fallback automatically.

For `aml_alerts`, the existing row-level security policy (Risk & Compliance + Internal Audit only) is enforced by PostgreSQL at SELECT/INSERT time regardless of how the SQL is built — so the CRUD router automatically respects the RLS without needing app-level changes.

### 2. API counting methodology corrected (`count_api_endpoints()`)

The old methodology was: regex-count `@app|@router\.(get|post|put|delete|patch)\(` matches across all `.py` files. This had three problems:

**Problem 1: false positives in scripts/audit.py.** The audit script itself contains regex string literals that LOOK FOR these decorator patterns (it checks that endpoints have JWT auth, etc.). Those strings get counted as decorators. **8 false-positive matches.**

**Problem 2: false positives in test files.** `tests/test_api_crud.py` contains test fixtures that decorate test endpoints with `@app.get` etc. Those aren't production endpoints. **2-4 false-positive matches.**

**Problem 3: under-counting CRUD factory expansions.** The factory in `utils/api_crud.py` has 8 decorator definitions (one per CRUD verb). The OLD count saw those 8 decorators ONCE regardless of how many times the factory was called. The truth: each `make_crud_router(module=X)` call creates a NEW `APIRouter` instance with its own 8 endpoints, scoped to module X. **8 endpoints per CRUD module call, not 8 total.**

The new methodology:
1. Scan production code only (excluding `scripts/audit.py` and `tests/`)
2. Subtract the factory's 8 template decorators (counted once)
3. Add `8 × count(make_crud_router(...))` to account for CRUD expansions

Result: 19 direct decorators + 32 CRUD endpoints (4 modules × 8) = **51 endpoints** real. Old methodology reported 35; the corrected baseline (without v10.92's new modules) is 27.

### 3. SCOPE_LEDGER.md Phase 1B section expanded

The Phase 1B section now documents:
- The two-path strategy (CRUD factory vs direct decorators)
- The corrected counting methodology
- The list of next CRUD candidates by `TABLE_USE_DB` status

Phase 1A status section retained as historical reference.

---

## What v10.93 covers

Phase 1B continuation. Targets:

**3 more CRUD modules** for tables already in `TABLE_USE_DB` (enabled) with PG migrations:
1. `assets` (asset_register, in TABLE_USE_DB enabled, v10.88 migrated)
2. `vendors` (in TABLE_USE_DB enabled, source JSON to confirm)
3. `purchase_orders` (in TABLE_USE_DB enabled, source JSON to confirm)

That batch adds +24 endpoints. Coverage moves to ~75/136 (~55%).

**Side decision needed for v10.93:** several existing PG-migrated tables (e.g., `agent_transactions`, `bid_bonds`, `treasury_fd`, `clearing_records`) are NOT in `TABLE_USE_DB` at all. To wire them as CRUD modules, they need TABLE_USE_DB entries first. The default state (False) means reads come from JSON fallback. Adding entries with False is safe (just registers them as CRUD-eligible).

After Phase 1B closes (~v10.96-v10.98), Phase 1C — test coverage push from ~45% → 80% via baseline coverage measurement + targeted tests for under-tested modules.

---

## Files changed

- **MOD** `utils/api.py` (3 new `make_crud_router()` calls after `pipeline_deals`)
- **MOD** `scripts/audit_completion_state.py` (`count_api_endpoints()` rewritten with correct methodology + text report shows breakdown)
- **MOD** `SCOPE_LEDGER.md` (Phase 1B section expanded; Phase 1A status preserved)
- **NEW** `CHANGELOG_v10.92.md` (this file)

## Files NOT changed (deliberately)

- `utils/db.py` — no schema changes (Phase 1A is complete; PG migration scope is locked)
- `scripts/migrate_to_postgres.py` — no migration changes
- `scripts/audit.py` — G16 unchanged (existing api_v1_coverage gate still passes), G142 unchanged (continuation_doc floor still 51)
- `standards_registry.py` — no new standards
- `utils/api_crud.py` — factory unchanged; just consumed by 3 more module calls
- All closed-arc files — closure invariants preserved

## Honest acknowledgements

**The before/after API endpoint numbers are partly a counting fix.** The "+24" delta is decomposed honestly above: +24 from real new work (3 CRUD modules × 8) and a methodology correction that reveals previous miscount. Without the new work, the corrected baseline would have been 27 (not 35); the new methodology surfaces the correct number, then v10.92's work moves it to 51. Reporting just "+16 net visible delta" or "+24 real new endpoints" both miss part of the story.

**The CRUD factory's 8 endpoints aren't all equally useful for every table.** The `dashboard` endpoint, for example, returns "module summary metrics" — it's likely placeholder-shaped until customized per module. The `search` endpoint is whitelist-driven (only the columns I declared in `searchable=` work). For some tables, only a subset of the 8 verbs is genuinely useful in practice. The count of 8 is correct from an audit-script perspective; the count of "useful endpoints" might be lower per module.

**The aml_alerts CRUD module exposes a sensitive surface.** RLS is enforced at the PG level so unauthorized users can't read rows, but the `/api/v1/aml_alerts/*` endpoints exist regardless of role. A user without "Risk & Compliance" or "Internal Audit" role hitting `GET /api/v1/aml_alerts/AML00001` gets a 404 (RLS hides the row), not a 403 (forbidden). The semantic difference matters for security audit trails — failing-to-find is different from being-denied. Future enhancement: add an explicit role check at the route level for aml_alerts to give 403 for unauthorized roles. Holding off for now — RLS provides correctness; the 404-vs-403 distinction is a refinement.

**v10.92 doesn't add API endpoint anti-drift enforcement.** Same logic as v10.91 — visibility script + CHANGELOG completion delta provide discipline. If endpoint regression becomes a concern, a G143 ratchet could be added in a future drop. Not adding it preemptively.

**The CRUD factory's `register_module()` registry is not used by the new counting code.** I used static analysis (regex-counting `make_crud_router(` calls) rather than runtime introspection of `_REGISTERED_MODULES`. Reason: the audit script runs at static-analysis time, not at app-import time. Importing `utils.api_crud` at audit time would require FastAPI as a dependency. The static count and the runtime count should match — if they ever diverge, it'd be a sign that registration is happening conditionally or in a non-discoverable code path, which is itself a smell worth surfacing.

**`pipeline.json` data file maps to `pipeline_deals` PG table, not `pipeline`.** The v10.90 CHANGELOG mentioned this nuance. The v10.92 work doesn't touch this — `pipeline_deals` was already wired. Worth flagging that the table-name-to-source-file mapping isn't always 1:1.

**Phase 1B's first drop is more about the structural decision than raw endpoint count.** The decision to stay with single-app + CRUD factory is the load-bearing call. Adding 3 modules tests the pattern; the next drops will scale it. If the pattern starts breaking down (e.g., the api.py file gets too long, or some modules need significantly different conventions), Phase 1B might pivot to per-domain router files. For now, the single-app pattern works well.

---

**v10.92 ships under the anti-drift protocol.** API endpoints 27 baseline → 51 after this drop (37.5% of 136 target). Phase 1A remains COMPLETE; Phase 1B IN PROGRESS. v10.93 continues with 3 more CRUD modules (assets, vendors, purchase_orders), targeting ~75/136 (~55%).
