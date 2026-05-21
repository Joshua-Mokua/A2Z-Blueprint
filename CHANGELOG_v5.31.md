A2Z MIS 360 — v5.31 release notes
===================================

STANDARD #2: API CRUD Factory — FRAMEWORK LANDED
================================================
Verified score: 16/16 gates (100%) per scripts/audit.py
Audit gate added: G16 api_v1_coverage
First pilot module: pipeline_deals (8 new endpoints under /api/v1/)

WHAT THE FRAMEWORK PROVIDES
---------------------------
v5.31 is the runtime infrastructure for Standard #2 of the master
addendum. Before this release, utils/api.py had 14 hand-written
endpoints — adding more was bespoke work per module. The spec demands
136 endpoints (8 verbs × 17 modules + system). Hand-coding that would
be ~700 lines of repetitive route handlers.

v5.31 builds the factory:

  utils/api_crud.py
    make_crud_router(
        module      = "pipeline_deals",     # path segment
        table       = "pipeline_deals",     # PG table (must be in TABLE_USE_DB)
        json_file   = "pipeline.json",      # fallback file
        list_key    = "deals",              # JSON dict key (or None for list)
        searchable  = ["stage", "unit"],    # search whitelist
        order_by    = "open_date DESC",
        pk_column   = "id",
    ) -> APIRouter

The factory generates 8 routes under /api/v1/<module>/*:

  list      GET    /api/v1/{module}              ?limit=&offset=
  get       GET    /api/v1/{module}/{id}
  create    POST   /api/v1/{module}              {body}
  update    PUT    /api/v1/{module}/{id}         {body}    (upsert)
  delete    DELETE /api/v1/{module}/{id}
  export    POST   /api/v1/{module}/export       {limit, offset}
  search    POST   /api/v1/{module}/search       {criteria, limit, offset}
  dashboard GET    /api/v1/{module}/dashboard

Every route:
  ✓ JWT-gated via Depends(get_current_user)        — closes V-001
  ✓ uses _qid() for identifiers + %s for values    — closes V-002
  ✓ audit-logs via core_audit.audit_log
  ✓ falls back to a2z_db.load_json when PG offline — graceful degradation
  ✓ returns _serialize() output                    — Decimals/dates JSON-clean

Adding a new module to /api/v1/* is now ONE call:

  app.include_router(make_crud_router(module="vendors", table="vendors", ...))

— and you get 8 endpoints. Hit the same pattern 16 more times to reach
the spec's 136 target.

WHY THIS DESIGN
---------------
Three reasons:

(a) Pages get React-ready APIs without bespoke work. Every CRUD module
    lit up by the factory ships consistent shapes, consistent auth,
    consistent search semantics. The React migration (Standard #36-#40)
    needs this — without it, every component would have to learn a
    different endpoint shape.

(b) Safety is built in, not bolted on. Hand-written endpoints have
    historically had inconsistent SQL safety (the existing
    /api/pipeline/deals uses an f-string for LIMIT — a low risk
    because of Query() validation, but a pattern that doesn't scale).
    Every factory-generated route uses the same SQL-safe builder.

(c) Whitelisting at the boundary. The factory's `searchable`
    parameter is an explicit allow-list of columns that can appear in
    /search criteria. Anything outside the list is dropped silently —
    no information leak about schema, no surprise filters, no SQL
    injection.

PILOT: pipeline_deals
---------------------
First module wired: pipeline_deals.

Why this one:
  - PG-live (TABLE_USE_DB["pipeline_deals"] = True)
  - Has a clean schema in SCHEMA_SQL with `id` PK
  - Existing /api/pipeline/* endpoints stay (backward compat)
  - Sales/business data — no HR/compliance sensitivity
  - 8 NEW endpoints under /api/v1/pipeline_deals/* on top of the
    existing 2 read endpoints under /api/pipeline/

Searchable columns: stage, deal_category, unit, staff_code, client_cif.
Order: open_date DESC.

The existing /api/pipeline/deals endpoint (which has business-specific
filters) keeps working unchanged. The /api/v1/pipeline_deals/search
endpoint provides the same filtering through the factory pattern.

Why I rejected disciplinary as the pilot:
  - Schema marked confidential = true; needs RLS + role-based access
  - Generic CRUD on disciplinary records = HR data leak
  - Will need a "sensitive" variant of the factory in v5.3X with
    role checks built in

Why I rejected vendors:
  - In TABLE_USE_DB as True but no CREATE TABLE in SCHEMA_SQL
  - Latent gap (12 tables PG-live without schemas — separate issue)

NEW AUDIT GATE: G16 api_v1_coverage
-----------------------------------
Reports:
  - total_endpoints: 22
  - system_endpoints: 14 (the existing hand-written ones)
  - v1_endpoints: 8 (from 1 wired module × 8 verbs)
  - wired_modules: ["pipeline_deals"]
  - factory_decorators: 8 (validates all 8 verbs are in the factory)
  - factory_auth_count: 8 (validates JWT on every route)
  - missing_verbs: [] (none — all 8 present)
  - spec_target: 136
  - progress_pct: 16%

The gate passes when:
  (a) utils/api_crud.py exists
  (b) The factory defines all 8 CRUD verbs
  (c) Every factory-generated route uses Depends(get_current_user)
  (d) At least one module is wired through make_crud_router()
  (e) No JWT-auth violations

The gate is a TRACKING gate. It surfaces drift — e.g. if someone
removes a verb from the factory or forgets the auth dep, G16 fails.

WHAT WAS CHANGED
----------------
1. utils/api_crud.py (NEW, 537 lines):
     - make_crud_router(...) factory function
     - Helpers: _serialize, _audit, _db_available
     - Pydantic models: _SearchCriteria, _ExportOpts
     - Module registry: _REGISTERED_MODULES, register_module,
       get_registered_modules

2. utils/api.py (modified):
     - Imports make_crud_router
     - Mounts pipeline_deals through the factory at /api/v1/pipeline_deals/*
     - Existing /api/pipeline/* endpoints unchanged

3. scripts/audit.py:
     - gate_api_v1_coverage (G16) added
     - GATES list extended to 16

4. tests/test_api_crud.py (NEW, 11 structural tests):
     - factory_function_exists
     - factory_signature_is_keyword_only
     - factory_rejects_unknown_table (V-002 defence)
     - factory_produces_router_with_8_routes
     - factory_routes_have_expected_verbs_and_paths
     - factory_registers_module_for_g16
     - factory_module_no_unsafe_sql (V-002 defence)
     - factory_module_qid_usage_count
     - factory_every_route_has_jwt_auth (V-001 defence)
     - factory_audit_logs_every_route
     - pipeline_deals_wired_in_api

5. Master_Prompt_v3.md → v5.31:
     - Codebase headline: ~55K → ~56K, 15 utils → 16
     - db.py LOC: 1,470 → 1,673
     - file map: api_crud.py listed
     - API expansion entry rewritten (Standard #2 framework landed)
     - G16 row added to gates table
     - Footer bumped

VERIFICATION (sandbox-stubbed; no fastapi/pydantic available)
-------------------------------------------------------------
  utils/api_crud.py syntax OK:                       ✓
  utils/api.py syntax OK:                            ✓
  Audit gates:                                       16/16 PASS
  G13 grew: 5 files / 79 tests → 6 files / 90 tests
  G16 reports correctly: 22 endpoints, 16% of 136     ✓
  AST verification: factory has 8 @router decorators ✓
  AST verification: 8+ Depends(get_current_user)     ✓
  Static check: ≥16 _qid() calls (no f-string SQL)   ✓
  Static check: 8+ _audit() calls                    ✓
  BSC engine self-test:                              ALL PASS

Production verification (when fastapi + psycopg2 installed and PG
reachable) requires:
  1. pip install -r requirements.txt
  2. A2Z_USE_DB=true + PG connection details
  3. python -m utils.api  (starts on port 8502)
  4. POST /api/auth/login → get JWT
  5. GET  /api/v1/pipeline_deals/dashboard with Bearer token
       → returns {module, table, total_rows, searchable, ...}
  6. POST /api/v1/pipeline_deals/search {"criteria": {"stage": "Won"}}
       → returns matching deals

INSTALLATION
------------
1. Extract this zip over your v5.30 working tree.
2. Run the audit:
     python scripts/audit.py
   Expected: 16/16 PASS, G16 reports 22 endpoints, 16% of 136.
3. Run pytest:
     pytest tests/test_api_crud.py -v
   Expected: 11 tests pass.
4. Smoke test the existing endpoints (no behaviour change):
     - /api/auth/login still issues tokens
     - /api/pipeline/deals still serves the legacy shape
   Expected: identical output to v5.30.

ROLLBACK
--------
1. Restore utils/api.py from utils/api.py.v5.30.bak (in your tree).
2. Delete utils/api_crud.py.
3. Delete tests/test_api_crud.py.
4. Restore scripts/audit.py from v5.30 git tag.
Or: git revert v5.31.

The /api/v1/* endpoints are entirely additive — removing them does not
affect any existing caller.

WHAT'S NEXT
-----------
Three paths from here:

a) WIRE THE NEXT MODULE
   Pick another PG-live table from TABLE_USE_DB (currently 19/52). For
   each one, add a make_crud_router(...) call to utils/api.py. 16 more
   modules brings G16 to 100% (136 endpoints).

   Highest-value next pilots:
     - watchlist          (credit monitoring; already in TABLE_USE_DB=True)
     - aml_alerts         (AML; PG-live, schema present)
     - rcsa_risks         (risk register; PG-live)
     - projects           (initiatives; PG-live)
     - workforce          (HR open data, NOT disciplinary)

b) MOVE TO STANDARD #3 (BSC ENGINE UNIVERSAL ADOPTION)
   v5.32 = "fast #3". Currently 2/17 modules use bsc_engine.submit().
   Spec demands all 17. The pattern is documented in v5.18; expansion
   is per-module wiring of compute_operational_kpi_actuals callers.

c) ADVANCE THE PG MIGRATION
   module_config has been in Phase 1 dual-write for one session. After
   2 weeks of production validation, flip TABLE_USE_DB["module_config"]
   to True (Phase 2). Then pick the next table for Phase 1.

Recommended order from the spec: Standard #3 next (fast #3).

LATENT ISSUE NOTED (NOT FIXED)
------------------------------
12 tables marked True in TABLE_USE_DB are missing schemas in
SCHEMA_SQL: assets, contracts, deal_rooms, ews_cases, invoices,
projects, purchase_orders, purchase_requests, rcsa_risks, vendors,
watchlist, workforce. They claim to be PG-live but PG would reject
queries against them. Should be addressed before any of these is
wired through the factory. v5.32 or later.

COMMIT
------
git add utils/api_crud.py utils/api.py scripts/audit.py \
        tests/test_api_crud.py Master_Prompt_v3.md
git commit -m "v5.31: Standard #2 CRUD factory + pipeline_deals pilot + G16 gate"
git tag v5.31
git push origin main --tags
