A2Z MIS 360 — v5.40 release notes
===================================

STANDARD #13: Daily Micro-Task Engine — CLOSED
==================================================
Verified score: 24/24 gates (100%) per scripts/audit.py
Audit gate added: G24 microtask_engine_reliability
Test count: 16 files / 341 → 17 files / 371 (+30 microtask tests)
Trigger reliability: 20/20 = 100% on labeled fixture set (spec ≥90%)
Volume Two: 3 of 10 standards delivered (#11, #12, #13)

THE WORK
--------
Standard #13 calls for `MicroTaskEngine.generate_daily_tasks(staff_code)`
that emits behind-pace warnings as concrete daily actions. Per spec:

    for kpi in active_kpis:
        daily_req = kpi.target / working_days_remaining
        if current_pace < daily_req * 0.9:
            tasks.append({"task": ..., "priority": "High"})

Verification:
  - 90% task conversion rate ← deployed-runtime behavioral metric
                                 (% of recommended tasks staff actually
                                 do). OUT OF SCOPE here.

The verifiable structural claim we DO measure is trigger reliability:
given labeled behind-pace inputs, the engine produces tasks for ≥90%
of them.

WHAT'S DELIVERED
----------------

1. utils/microtask_engine.py (~480 LOC) — `MicroTaskEngine`:
     - generate_daily_tasks(staff_code, today=None) → list[MicroTask]
     - All collaborators injectable for testability:
         active_kpis_fn(staff_code) → list[{"id"}]
         target_lookup_fn(staff_code, kpi_id, period) → Decimal | None
         actual_lookup_fn(staff_code, kpi_id, period) → Decimal | None
         recommended_task_fn(kpi_id) → str
         working_days_fn(period, today) → int
         period_fn(today) → str
     - Default collaborators read from target_cascade.json + bsc_engine
     - Honest deviation from literal spec:
         spec:    daily_req = target / working_days_remaining
         reality: daily_req = max(target - current, 0) / working_days_remaining
       The literal spec would say "you need to do 50/day" when 80% is
       already in the bag. Documented in module docstring.
     - current_pace = current_actual / weekdays_elapsed_in_period
     - Priority bands:
         gap_ratio < 0.5  → High
         gap_ratio < 0.9  → Medium  (the 0.9 spec gate)
         gap_ratio ≥ 0.9  → no task
     - Cap at 5 tasks per staff (don't overwhelm)
     - Sorted by gap_ratio ascending = most urgent first
     - Persistence helpers:
         save_pending_tasks([MicroTask]) → int — idempotent dedup on
                                          (staff, kpi, for_date)
         list_active_tasks(staff_code, for_date) → list[dict]
         complete_task(task_id, actor) → bool
     - KPI-class task routing (DEP_GROWTH → "Make 5 outbound prospect calls",
       NPL → "Call delinquent accounts", AML → "Clear AML alerts", etc.)
     - Self-test via `python -m utils.microtask_engine` — 6 cases pass

2. tests/fixtures/microtask_scenarios.json — 20 labeled scenarios:
     M001 clear behind-pace (High)        M011 deposit task routing
     M002 on-pace (no task)                M012 borderline below threshold
     M003 target met (no task)             M013 clearly above threshold
     M004 target exceeded                  M014 day-1 of period (High)
     M005 no target                        M015 no active KPIs
     M006 zero target                      M016 large numbers (1.5B)
     M007 end of period (no days)         M017 cap at 5 tasks
     M008 multi-KPI mixed (1 fires)       M018 very low pace = High
     M009 AML task routing                M019 medium pace = Medium
     M010 NPL task routing                M020 quarterly period

3. tests/test_microtask_engine.py — 30 tests:
     Unit tests:
       - 5 period-bounds tests (monthly, quarterly, invalid)
       - 6 weekday-counting tests (full month, week, weekend, edge)
       - 4 task routing tests (deposit/NPL/AML/unknown)
       - 7 pace-threshold tests (behind/on-pace/met/exceeded/no-target/
         zero-target/no-working-days)
       - 3 priority-band tests (very-low/medium/boundary)
       - 1 max-tasks-cap test
       - 2 task-shape tests (required fields + ID determinism)
       - 3 persistence tests (save+list, dedup, complete)
     The harness:
       - test_trigger_reliability_meets_90_percent runs every fixture;
         asserts ≥90%; writes microtask_reliability_results.json

4. scripts/audit.py — new gate G24 microtask_engine_reliability:
     - Reads microtask_reliability_results.json
     - Missing → informational pass
     - Present → enforces reliability_pct ≥ 90.0
     - Lists missed scenarios on failure
     - Same artifact-handoff design as G18-G23

TWO SCENARIO ERRORS CAUGHT + FIXED
-----------------------------------
While running the harness against the fixtures I found two scenarios
where my expected values didn't match the math:

  M012 — "current_pace = daily_req * 0.85"
    Original: target=100, actual=47, days_elapsed=11, days_remaining=12
              expected: 1 task
    Reality:  pace=4.27, daily_req=53/12=4.42, ratio=0.97 (above gate)
              → engine correctly emits 0 tasks
    Fix: changed actual to 44 (ratio 0.86 → just below gate → Medium task)

  M013 — "current_pace = daily_req * 0.95"
    Original: target=100, actual=53, days_elapsed=11, days_remaining=12
              description claimed ratio 0.95
    Reality:  pace=4.82, daily_req=47/12=3.92, ratio=1.23 (well above gate)
              → engine correctly emits 0 tasks (which the assertion expected)
    Fix: updated description to reflect actual ratio. Assertion was
         already correct.

Engine output was correct in both cases — fixtures were mis-labeled.

LIVE TRIGGER RELIABILITY
------------------------
After fixing the two scenarios:
  Trigger reliability: 20/20 = 100.0%
  Spec target:         ≥90.0%
  Result:              ✅ PASS

DESIGN DECISIONS WORTH NOTING
-----------------------------
1. Engine NOT auto-fired on submit
   Same call-site pattern as #11 (nudge engine). This engine is
   invoked by a daily scheduler (or a UI page), not synchronously
   inside bsc_engine.submit. Keeps persistence path pure.

2. Working days only (Mon–Fri)
   Bankers don't usually work weekends. daily_req = remaining /
   weekdays_remaining gives a more honest "what to do today" target.
   Holidays are NOT excluded — that's a future enhancement when a
   bank-specific holiday calendar exists.

3. Idempotent dedup on (staff, kpi, for_date)
   Re-running the morning generator doesn't multiply yesterday's
   already-saved tasks; it replaces same-day duplicates. Re-running
   on a new day appends without touching prior days. Daily history
   preserved.

4. Cap at 5 tasks per staff
   Surfacing 12 "you're behind" alerts is noise. Staff need a
   short, ordered list. Cap is configurable via constructor.

5. Task text is one specific action FOR TODAY
   Different from nudge engine's action_items (which are multi-day
   strategies). Micro-task: "Make 5 outbound prospect calls today."
   Nudge action: "Review your top 5 prospects and confirm next-step
   dates" (multi-day activity). Both are useful; they're for
   different cadences.

NO RUNTIME CODE CHANGES
-----------------------
v5.40 doesn't touch utils/api.py, utils/db.py, utils/bsc_engine.py,
utils/nudge_engine.py, utils/growth_path_engine.py, or any pages.
Pure additive (new engine + new tests + new gate + master prompt).

WHAT WAS CHANGED
----------------
1. utils/microtask_engine.py (NEW, ~480 LOC)
2. tests/fixtures/microtask_scenarios.json (NEW, 20 scenarios)
3. tests/test_microtask_engine.py (NEW, 30 tests)
4. scripts/audit.py — added gate_microtask_engine_reliability (G24)
5. Master_Prompt_v3.md → v5.40

VERIFICATION (sandbox)
----------------------
  scripts/audit.py syntax OK:                           ✓
  audit gates 24/24 PASS:                               ✓
  G13 grew: 16 files / 341 tests → 17 files / 371 tests
  python -m utils.microtask_engine self-test:           ALL PASS (6/6)
  python -m utils.bsc_engine self-test:                 ALL PASS
  python -m utils.nudge_engine self-test:               ALL PASS
  python -m utils.growth_path_engine self-test:         ALL PASS
  Manual run of all 30 microtask tests:                 44/44 sub-checks pass
  G24 informational pass when artifact missing:         ✓
  G24 PASS at 95% reliability:                          ✓
  G24 FAIL at 80% reliability:                          ✓
  G24 FAIL on corrupt artifact:                         ✓
  Live harness run on fixtures:                         100% reliability

CURRENT AUDIT STATE (post-v5.40)
--------------------------------
  ✅ G1-G12 all pass (foundational + security)
  ✅ G13: 17 files / 371 tests
  ✅ G14-G17 all pass (architecture)
  ✅ G18-G22 informational in sandbox, enforced in CI
  ✅ G23 growth_path_coverage: 1428/1428 (100%, with 10 duplicate
       staff_codes flagged as data issue)
  ✅ G24 microtask_engine_reliability: informational in sandbox
  Score: 24/24 = 100% PASS

INSTALLATION
------------
1. Extract this zip over your v5.39 working tree.
2. Run audit:
     python scripts/audit.py
   Expected: 24/24 PASS. G24 informational until pytest runs.
3. Run engine self-test:
     python -m utils.microtask_engine
   Expected: ALL TESTS PASSED.
4. Run pytest:
     pytest tests/test_microtask_engine.py -v
   Expected: 30 tests pass; microtask_reliability_results.json created.
5. Re-run audit:
     python scripts/audit.py
   Expected: G24 reports actual reliability ≥ 90%.

ROLLBACK
--------
If anything goes wrong:
  1. Restore scripts/audit.py from scripts/audit.py.v5.39.bak
  2. Delete:
       utils/microtask_engine.py
       tests/test_microtask_engine.py
       tests/fixtures/microtask_scenarios.json
       microtask_reliability_results.json (if generated)
       data/microtasks.json (if generated)
Or: git revert v5.40.

WHAT'S NEXT
-----------
Volume Two has 10 standards (#11-#20). #11, #12, #13 done. The
progression:

  #14 Peer Learning Network — match staff with skill GAPS to staff
                              with skill EXCESS. Composes naturally
                              with #12 (uses growth path skill_gaps)
                              and #11 (recognition nudges identify
                              top performers).
  #15 ...

Volume One open items (deferred):
  fast #8  — WCAG 2.1 AA accessibility
  fast #10 — UAT framework

Recommended next: fast #14 (Peer Learning Network) — naturally
extends the Volume Two engines. Or fast #15 if you want to keep
chaining engines.

LATENT ISSUES (unchanged from v5.39)
------------------------------------
1. Seed data refresh — `data/*.json` doesn't match production shape.
2. core_kpi shim still in shim phase — physical move pending.
3. 12 PG schemas still missing from get_schema_sql() (from v5.31).
4. Export 10K load test still needs ≥10k seed rows.
5. Nudge engine not yet wired into bsc_engine submit path
   (deferred from v5.38).
6. 10 duplicate staff_codes in users.json (data integrity).
7. data/bsc_scores.json doesn't exist — engines that read BSC
   history report 0.
8. users.json has no hire_date / role_start_date fields.
9. **NEW**: Holiday calendar not yet supported in micro-task engine
   (working_days_remaining counts Mon-Fri only). When Kenya/East
   African holidays are added to a config file, working_days_fn can
   subtract them.
10. **NEW**: Micro-task engine not yet wired into a daily scheduler
    (cron / Celery beat / GitHub Actions schedule). Same deferral
    as nudges — wants careful op review before enabling.

COMMIT
------
git add scripts/audit.py utils/microtask_engine.py \
        tests/test_microtask_engine.py \
        tests/fixtures/microtask_scenarios.json \
        Master_Prompt_v3.md
git commit -m "v5.40: Standard #13 MicroTaskEngine + G24 gate"
git tag v5.40
git push origin main --tags
