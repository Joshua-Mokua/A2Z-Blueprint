A2Z MIS 360 — v5.30 release notes
===================================

STANDARD #1: PostgreSQL Migration Framework — Phase 1 LANDED
============================================================
Verified score: 15/15 gates (100%) per scripts/audit.py
Audit gate added: G15 pg_migration_progress
First pilot table: module_config (Phase 1 dual-write)

WHAT THE FRAMEWORK PROVIDES
---------------------------
v5.30 is the runtime infrastructure for Standard #1 of the master
addendum. Before this release, utils/db.py had:
  - TABLE_USE_DB (a boolean flag per table)
  - is_postgres_ready() helper
  - table_uses_db() helper
  - PG schemas defined for many tables

But it had NO routing logic — load_json/save_json were pure file I/O.
Setting TABLE_USE_DB[t] = True did nothing.

v5.30 adds the routing:

  1. JSON_PATH_TO_TABLE: dict
     Maps "<filename>.json" → "<table_name>". The router uses this to
     decide whether a path is tracked.

  2. _table_for_path(path) -> str | None
     Returns the table name for any path, or None.

  3. Per-table marshaller pairs
     Each pilot table gets:
       _save_<table>_to_pg(data) -> int  (returns rows upserted)
       _load_<table>_from_pg() -> dict
     Registered via Database._get_marshallers(table).

  4. Dual-mode load_json:
     If table_uses_db(table) is True (Phase 2), reads from PG.
     On PG failure, falls back to JSON file with warning.
     If table_uses_db is False (Phase 1) or path isn't tracked,
     reads JSON as before. No change to existing pages.

  5. Dual-mode save_json:
     ALWAYS writes the JSON file first (atomic; safety net).
     If is_postgres_ready() and the path is tracked and a marshaller
     is registered, ALSO upserts to PG.
     PG failures during dual-write are logged as warnings but DO NOT
     fail the save — JSON has already succeeded and is the source of
     truth in Phase 1.

WHY THIS DESIGN
---------------
Three reasons:

(a) Pages don't change. _admin_module_config.py still calls
    a2z_db.load_json(p) and a2z_db.save_json(p, cfg). The migration
    is invisible to the call sites. This is the "extract and regroup,
    never mass-rewrite" rule from the operating instructions.

(b) Rollback is trivial. Set TABLE_USE_DB[table] back to False — reads
    return to JSON. Or remove the path from JSON_PATH_TO_TABLE — even
    the dual-write stops. Two ways out at every step.

(c) JSON is the safety net through Phases 1-3. Even when Phase 2 flips
    reads to PG, writes still hit JSON. If PG corrupts or you need to
    audit historical changes, the JSON file is right there. Phase 4 is
    when JSON gets archived — that's after weeks of clean PG operation.

PILOT: module_config
--------------------
First table wired: module_config.

Why this one:
  - It has actual production usage (called by _admin_module_config.py)
  - PG schema already defined in utils/db.py (lines 1354-1364)
  - Small data (one row per module, ~19 modules)
  - Slow-changing (admin edits, not hot writes)
  - Clean data shape (dict keyed by module_id, JSONB columns map well)

Phase status: PHASE 1 (DUAL-WRITE).
TABLE_USE_DB["module_config"] is still False, so:
  - Reads continue from data/module_config.json
  - Writes go to JSON (always) AND to PG (when reachable)

To advance to Phase 2 (PG becomes the read source):
  1. Run for 2 weeks in production with PG reachable.
  2. Verify PG row count matches JSON top-level key count daily.
  3. Verify the reconciliation engine reports zero breaks.
  4. Flip TABLE_USE_DB["module_config"] = True.
  5. Reads now come from PG. Writes still go to both.

To advance to Phase 3 (deprecate JSON write):
  1. Run for another week post-flip.
  2. Verify zero PG-side errors during dual-write.
  3. Remove the JSON write path (or replace with read-only fallback).

To advance to Phase 4:
  1. Move data/module_config.json to data/archive/.
  2. Future runs read from PG only.

NEW AUDIT GATE: G15 pg_migration_progress
-----------------------------------------
Reports:
  - tables_total: 52
  - tables_pg_mode: 19 (currently True in TABLE_USE_DB)
  - tables_json_mode: 33
  - adoption_pct: 37%
  - pilot_tables: ["module_config"]
  - wired_marshallers: ["module_config"]
  - violations: []  (would flag pilots without marshallers, etc.)

The gate passes when:
  (a) TABLE_USE_DB is well-formed
  (b) Every JSON_PATH_TO_TABLE entry references a registered table
  (c) Every JSON_PATH_TO_TABLE pilot has a marshaller pair wired
  (d) At least one table is in PG-mode

The gate is a TRACKING gate, not enforcement. It surfaces drift —
e.g. if someone adds an entry to JSON_PATH_TO_TABLE but forgets the
marshaller, G15 will fail with a clear message.

WHAT WAS CHANGED
----------------
1. utils/db.py:
     - JSON_PATH_TO_TABLE map added (1 entry: module_config.json)
     - _table_for_path() helper added
     - _save_module_config_to_pg() method added
     - _load_module_config_from_pg() method added
     - _get_marshallers(table) registry method added
     - load_json() rewritten with dual-mode read path
     - save_json() rewritten with dual-write path
     - Net: ~150 lines added, ~80 lines modified

2. scripts/audit.py:
     - gate_pg_migration_progress (G15) added
     - GATES list extended

3. Master_Prompt_v3.md → v5.30:
     - PG migration entry rewritten to reflect Phase 1 framework
     - G15 row added to quality gates table
     - Footer bumped

VERIFICATION (sandbox-stubbed; no real PG available)
----------------------------------------------------
  utils/db.py syntax OK:                              1/1 PASS
  Audit gates:                                       15/15 PASS
  G15 reports correctly: 19/52 (37%), 1 pilot:         ✓
  JSON_PATH_TO_TABLE map populated:                    ✓
  _table_for_path() resolves both Path and string:     ✓
  _table_for_path() returns None for unknown:          ✓
  is_postgres_ready() False (sandbox has no PG):       ✓
  table_uses_db() correctly False when PG not ready:   ✓
  _get_marshallers("module_config") returns pair:      ✓
  _get_marshallers("unknown_table") returns None:      ✓
  save_json round-trips dict via JSON when PG absent:  ✓
  load_json reads back dict cleanly:                   ✓
  _admin_module_config.py still uses a2z_db API:       ✓
  BSC engine self-test:                              ALL PASS

Production verification (when PG is reachable) requires:
  1. psycopg2 installed (already in requirements.txt)
  2. A2Z_USE_DB=true environment variable set
  3. PostgreSQL connection details configured
  4. The module_config schema applied (already in SCHEMA_SQL)

Then save a module config in the admin UI and verify:
  SELECT module_key, last_updated FROM module_config;
shows rows matching data/module_config.json.

INSTALLATION
------------
1. Extract this zip over your v5.29 working tree.
2. Run the audit:
     python scripts/audit.py
   Expected: 15/15 PASS, G15 reports 19/52 (37%), 1 pilot.
3. Verify the BSC engine self-test:
     python -m utils.bsc_engine
   Expected: ALL TESTS PASSED.
4. (Optional) Apply the PG schema in your test DB:
     python -c "from utils.db import get_schema_sql; print(get_schema_sql())" | psql ...
5. Smoke-test in app:
     - Visit Admin → Module Configuration Centre.
     - Edit any module's configurable settings, hit Save.
     - data/module_config.json should reflect the change.
     - If PG is reachable, the module_config table should also have
       the new row (check logs: "save_json: dual-write to PG ... OK").

ROLLBACK
--------
If anything goes wrong:
  1. Restore utils/db.py from utils/db.py.v5.29.bak (in your tree).
  2. Restore scripts/audit.py from v5.29 git tag.
  3. data/module_config.json was never disturbed — it's the source
     of truth in Phase 1.
Or git revert v5.30.

WHAT'S NEXT
-----------
The framework is in. Three paths from here:

a) MIGRATE THE NEXT TABLE
   Pick another currently-False table that has actual usage. Looking
   at the codebase, the next clean candidate is flexcube_config (used
   by utils/flexcube_adapter.py). Same recipe: add to
   JSON_PATH_TO_TABLE, write the marshaller pair, register it.
   Repeat 31 more times to reach 52/52.

b) ADVANCE module_config TO PHASE 2
   Run for 2 weeks in production with PG reachable. Once the
   reconciliation engine confirms zero breaks, flip
   TABLE_USE_DB["module_config"] = True. PG becomes the read source.

c) MOVE TO STANDARD #2 (API EXPANSION)
   v5.31 = "fast #2". 12 endpoints → 136 endpoints. The framework
   from v5.17 (utils/auth_jwt.py) gives us JWT-protected route
   templates; expansion is per-module CRUD.

Recommended order from the master spec:
  Standard #1 (PostgreSQL) → Standard #2 (API) → Standard #3 (BSC) → ...

So the next session is "fast #2" — API expansion. v5.30 framework
unblocks it: every endpoint that reads/writes a tracked table now
gets PG benefits automatically as flags flip.

COMMIT
------
git add utils/db.py scripts/audit.py Master_Prompt_v3.md
git commit -m "v5.30: Standard #1 PG migration framework + module_config Phase 1 pilot + G15 gate"
git tag v5.30
git push origin main --tags
