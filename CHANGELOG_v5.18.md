A2Z MIS 360 — v5.18 release notes
=================================

Verified score: 12/12 gates (100%) per scripts/audit.py
Closes: BSC central integration engine (addendum Standards #1 + #2)

This release builds the central BSC integration engine that the addendum
mandates and that the audit had flagged as the only remaining unimplemented
addendum standard. Prior to v5.18, G8 was vacuous — passing with "0 BSC
writers found, 0 contract-compliant" because no module had ever been wired
through a contract. v5.18 makes G8 a structural enforcement and wires one
pilot module (utils/actuals_engine) through the new contract.

WHAT WAS WRONG
--------------
The addendum specifies two non-negotiable standards:

  Standard #1 — Universal BSC Data Contract:
    {staff_code, kpi_id, value, period, source_module}

  Standard #2 — Central BSC Integration Engine:
    Modules MUST pass through validate → standardise → enrich → persist → audit

There was no central engine. Every module that produced performance data
either wrote directly to JSON files or to PostgreSQL tables. No two
modules used the same field names, period formats, or audit-trail
conventions. The G8 audit gate was a presence-check that passed when
zero writers were found — the worst kind of pass.

WHAT WAS BUILT
--------------

1. utils/bsc_engine.py (NEW, 607 lines):

   Public API:
     submit(staff_code, kpi_id, value, period, source_module, *, actor, metadata)
       → (bool, "created"|"updated"|<error_reason>)
     submit_batch(records, source_module, *, actor)
       → {"ok": int, "rejected": int, "created": int, "updated": int, "errors": [...]}
     get_actual(staff_code, kpi_id, period)
       → Optional[Decimal]
     get_actuals_for_period(period, source_module=None)
       → List[Dict]
     validate(record)
       → (bool, error_msg)   # exposed for ETL preflight

   Pipeline (all 5 stages run on every submission):
     1. validate     — 8 fail-closed checks (presence, types, ranges, formats,
                       staff_code in users, kpi_id in kpi_library, NaN/Inf rejection)
     2. standardise  — coerce types, normalise period to canonical form
     3. enrich       — add timestamp (UTC ISO), actor, idempotency hash
     4. persist      — atomic upsert to data/bsc_actuals_<period>.json,
                       routed through a2z_db.save_json (so dual-mode PG/JSON
                       pattern applies; when TABLE_USE_DB['bsc_actuals'] flips
                       True the records will land in performance.actuals)
     5. audit        — emit BSC_SUBMIT / BSC_REJECTED / BSC_PERSIST_FAILED
                       to audit.audit_logs

   Key design decisions:
     - Keyword arguments are MANDATORY on submit() — that's how G8 detects
       contract compliance syntactically.
     - Idempotency: SHA-256 hash of (staff_code, kpi_id, period, source_module).
       Replays update existing records rather than duplicate. Correct for ETL.
     - Period format: "YYYY-MM" or "YYYY-Q[1-4]" — regex-validated.
     - Bounds: ±1e15. Generous because banking KPIs span counts/ratios/KES
       millions/billions; gate catches obvious errors (NaN, infinity), not
       policy violations.
     - Storage: one JSON file per period. Reading one month doesn't load the
       whole bank's history.
     - Lazy index loading: KPI library + users mapping cached for 5 min.

   Self-test: `python -m utils.bsc_engine` runs a full smoke test covering
   happy path, replay/update, NaN rejection, bad-period rejection, unknown-
   user rejection, unknown-kpi rejection, quarter format, batch submission.
   All pass.

2. utils/actuals_engine.py (pilot module wired):

   After compute_actuals_from_cbs() writes the legacy XLSX, every row also
   flows through bsc_engine.submit_batch(source_module="actuals_engine").
   New helpers:
     _period_to_engine_format("Mar-26") → "2026-03"
     _submit_to_bsc_engine(rows, period) → batch summary

   The legacy XLSX still ships even if the engine rejects records — the
   pilot is non-blocking by design. The result dict now includes a
   `bsc_engine` key with the batch summary so the admin UI can surface
   it later.

3. scripts/audit.py G8 evolved:

   OLD: "0 BSC writers found, 0 contract-compliant" — passed vacuously.

   NEW: structural enforcement with TWO checks, both must hold:
     A) Every call to submit()/submit_batch() in modules that import
        utils.bsc_engine must pass the contract fields as kwargs
     B) NO module outside utils/bsc_engine.py is allowed to write directly
        to bsc_actuals_*.json or performance.actuals (via INSERT/UPDATE).
        The engine is the only legitimate writer.

   Output: "engine=present, 1 compliant submitter call(s) across 1 module(s),
   0 bypass writer(s) (target: 0)"

   With the actuals_engine pilot wired, G8 is no longer vacuous. Future
   modules adding submit() calls will increment the compliant count.
   Anyone bypassing the engine will fail the gate.

4. Master_Prompt_v3.md updated:
   - Version v5.17 → v5.18
   - Standard #2 section now points to utils/bsc_engine.py with usage example
   - G8 description in gates table reflects new behavior
   - BSC engine added to closed-gaps list

WHAT'S STILL OPEN
-----------------
All four critical CVEs and the BSC engine are now done. Remaining:

  PG migration (3 weeks)         — 31 of 52 tables still JSON
  core.py split (1 week)         — 6,596 lines, 15 classes
  API expansion (6-8 weeks)      — 12 of ~144 endpoints exist
  Test suite + CI/CD (4 weeks)   — zero unit tests
  Wire more modules through bsc_engine — currently 1 pilot

INSTALLATION
------------
1. Extract this zip over your project root, replacing files where prompted.
2. Run the engine self-test:
     python -m utils.bsc_engine
   Expected: "ALL TESTS PASSED"
3. Run the audit:
     python scripts/audit.py
   Expected: 12/12 PASS, G8 reports "engine=present, 1 compliant submitter
   call(s) across 1 module(s), 0 bypass writer(s)"
4. Restart Streamlit. Smoke-test:
   - Admin → System Health → Recompute Actuals (whatever your UI calls
     the actuals_engine entry point). After it runs, you'll see a new
     file at data/bsc_actuals_<YYYY-MM>.json containing one record per
     staff/KPI combination, each with the contract fields, an idem_hash,
     a UTC timestamp, and source_module="actuals_engine".
   - Re-run actuals computation. Records should UPDATE not duplicate
     (the file should have the same number of entries, with refreshed
     submitted_at timestamps).

VERIFY THE ENGINE (FROM PYTHON)
--------------------------------
  >>> from utils.bsc_engine import submit, get_actual
  >>> ok, msg = submit(
  ...     staff_code    = "300001",      # an existing staff_code from users.json
  ...     kpi_id        = "DEP_GROWTH",  # a KPI from kpi_library
  ...     value         = 12.5,
  ...     period        = "2026-04",
  ...     source_module = "manual_entry",
  ...     actor         = "your_username",
  ... )
  >>> ok, msg
  (True, 'created')
  >>> get_actual("300001", "DEP_GROWTH", "2026-04")
  Decimal('12.5')

ADDING ANOTHER MODULE
---------------------
The pattern from utils/actuals_engine.py is the reference. Any module
that produces performance data should:

  from utils.bsc_engine import submit_batch

  records = [
      {"staff_code": "...", "kpi_id": "...", "value": ..., "period": "YYYY-MM"},
      ...
  ]
  result = submit_batch(records, source_module="my_module", actor="user_or_etl")
  # result = {"ok": N, "rejected": N, "created": N, "updated": N, "errors": [...]}

The audit gate G8 will count your module as compliant on the next run.
Conversely, if you write directly to bsc_actuals_*.json or to
performance.actuals via SQL, G8 will fail the build.

COMMIT
------
git add .
git commit -m "v5.18: BSC central integration engine — Standards #1+#2 implemented, actuals_engine pilot wired"
git tag v5.18-bsc-engine
git push origin main --tags
