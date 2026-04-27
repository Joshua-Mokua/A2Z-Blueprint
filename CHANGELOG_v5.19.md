A2Z MIS 360 — v5.19 release notes
=================================

Verified score: 12/12 gates (100%) per scripts/audit.py
Adds: second BSC engine pilot wiring (operational modules path)

This release wires the most-called scoring function in the system
(`utils.core.update_bsc_from_modules`) through the BSC engine built in
v5.18. G8 now reports 2 compliant submitters across 2 modules, up from
1 in v5.18.

WHY THIS PILOT
--------------
The v5.18 release wired one pilot — utils/actuals_engine — which covers
CBS-derived financial/transactional KPIs. That validated the engine
design for the batch ETL pattern.

But the operational KPI path is different:
  - Triggered per-event (a project milestone completes, a CIMS ticket
    closes, a deal is won, a loan disburses, etc.) instead of nightly batch.
  - Computes 36 KPIs (K036-K071, K109-K111) from 8 different data sources.
  - Called from every operational module.

If the engine works for both patterns, it works.

WHAT WAS CHANGED
----------------

1. utils/core.py — new helper:
     _legacy_period_to_engine(legacy: str) → str
       Translates "Feb 2026" / "Feb-26" / "February 2026" / "2026-04" /
       "2026-Q2" into canonical "YYYY-MM". Falls back to current YYYY-MM
       on parse failure (well-formed fallback always returned).

2. utils/core.py — update_bsc_from_modules wired:
     After compute_operational_kpi_actuals returns its dict of
     {kpi_id: {actual, source, detail}}, every entry is translated
     into the universal BSC contract and submitted through the engine
     in one batch:

         _bsc_submit_batch(
             records       = [...36 records or fewer...],
             source_module = "operational_modules",
             actor         = username,
         )

     The original per-KPI source (e.g. "projects", "cims") is preserved
     in metadata.original_source so downstream analytics can still see
     where each value came from.

     Engine failures are non-blocking — the legacy kpi_scores update
     still runs even if the engine rejects records.

3. G8 (audit.py, unchanged from v5.18) now reports:
     "engine=present, 2 compliant submitter call(s) across 2 module(s),
      0 bypass writer(s) (target: 0)"

   That count goes up next time another module is wired.

4. Master_Prompt_v3.md updated:
     - Version v5.18 → v5.19
     - Pilot list now mentions both modules

PERIOD-FORMAT TEST RESULTS
--------------------------
The translator was tested against every format the bridge function
might encounter in the wild:

  ✅ 'Feb 2026'         → '2026-02'   (default arg of update_bsc_from_modules)
  ✅ 'Mar 2026'         → '2026-03'
  ✅ 'Feb-26'           → '2026-02'   (actuals_engine label format)
  ✅ 'Dec-25'           → '2025-12'
  ✅ '2026-04'          → '2026-04'   (already canonical, passthrough)
  ✅ '2026-Q2'          → '2026-Q2'   (quarterly, passthrough)
  ✅ 'February 2026'    → '2026-02'   (full month name)
  ✅ ''                 → fallback to today's YYYY-MM
  ✅ 'garbage'          → fallback
  ✅ '2026'             → fallback

WHAT'S STILL OPEN
-----------------

  More engine wirings (per-module, ~half day each)
    - Any module that today computes per-staff KPI values and writes
      them anywhere should be routed through the engine.
    - Each adds +1 to G8's compliant counter.

  PG migration (3 weeks)         — 31 of 52 tables still JSON
  core.py split (1 week)         — 6,596 → 6,640 lines now (added ~40 for v5.19),
                                    15 classes
  API expansion (6-8 weeks)
  Test suite + CI/CD (4 weeks)

INSTALLATION
------------
1. Extract this zip — only utils/core.py and Master_Prompt_v3.md change
   from v5.18.
2. Run the engine self-test:
     python -m utils.bsc_engine
   Expected: ALL TESTS PASSED
3. Run the audit:
     python scripts/audit.py
   Expected: 12/12 PASS, G8 reports 2 compliant submitters

VERIFY THE WIRING
-----------------
After running compute_operational_kpi_actuals + update_bsc_from_modules
for a real user, check data/bsc_actuals_<YYYY-MM>.json. Each record
should have:

  "staff_code":    "300001",
  "kpi_id":        "K039",
  "value":         85.0,
  "period":        "2026-02",
  "source_module": "operational_modules",
  "actor":         "william001",
  "submitted_at":  "2026-04-27T...Z",
  "metadata": {
      "original_source": "cims",
      "detail":          "85% tickets closed within SLA",
  },
  "idem_hash":     "<16 hex chars>"

Re-running the function should UPDATE the same records (idempotency
hash matches), not duplicate them.

COMMIT
------
git add .
git commit -m "v5.19: BSC engine pilot #2 — operational modules path wired"
git tag v5.19-engine-pilot2
git push origin main --tags
