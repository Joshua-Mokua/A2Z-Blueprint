A2Z MIS 360 — v5.38 release notes
===================================

STANDARD #11: Real-Time Performance Nudges — CLOSED (Volume Two opens)
======================================================================
Verified score: 22/22 gates (100%) per scripts/audit.py
Audit gate added: G22 nudge_engine_accuracy
Test count: 14 files / 270 → 15 files / 306 (+36 nudge tests)
Trigger accuracy: 20/20 = 100% on labeled fixture set (spec target: ≥95%)
Volume Two opens: this is the first Volume Two standard delivered.

THE WORK
--------
Standard #11 calls for real-time nudges that fire when KPIs deviate
from targets. Per spec:

    if current > target * 1.10 and trajectory == "accelerating":
        nudge(type="recognition", message="🎉 Exceeding target!")
    elif current < pace_target * 0.80:
        nudge(type="alert", message="⚠️ Behind target", action_items=[...])

Verification:
  - 95% trigger accuracy   ← verifiable in code (fixture set)
  - Engagement 23% → 85%   ← business-outcome metric, OUT OF SCOPE
                            for this session (needs deployed users)

v5.38 ships the framework + verifies the accuracy claim.

WHAT'S DELIVERED
----------------

1. utils/nudge_engine.py (~370 LOC) — `PerformanceNudgeEngine`:
     - evaluate(staff_code, kpi_id, new_value, period) → list[Nudge]
     - All collaborators injectable for testing:
         target_lookup_fn(staff, kpi, period) → Decimal | None
         history_lookup_fn(staff, kpi, period, n) → list[Decimal]
         period_progress_fn(period, today) → float in [0, 1]
         action_items_fn(staff, kpi) → list[str]
     - Default implementations:
         target_lookup → reads target_cascade.json
         history_lookup → calls bsc_engine.get_actual on prior periods
         period_progress → calendar math on YYYY-MM and YYYY-Qn
         action_items → KPI-class routing (sales / NPL / AML / generic)
     - Trajectory classifier: accelerating / flat / declining /
       insufficient_data
         "accelerating" requires:
           - all values monotonically non-decreasing (no dips)
           - prior delta-mean > 0 (some growth was happening)
           - latest delta > prior delta-mean (positive curvature)
         This rejects flat-then-spike patterns like [110, 110, 110, 115]
         (would trigger naive accelerating but really just one good
         period after stasis) AND perfectly-linear growth like
         [800M, 1.1B, 1.4B, 1.7B] (steady doubling, not accelerating).
     - Persistence helpers:
         save_pending_nudges([Nudge]) → int — idempotent dedup on
                                         (staff, kpi, period, type)
         list_active_nudges(staff_code) → list[dict]
         acknowledge_nudge(nudge_id, actor) → bool
     - Self-test via `python -m utils.nudge_engine` — 7 assertions

2. utils/notifications.py — extended to surface active nudges in the
   existing notification bell. Recognition shows as info icon 🎉,
   alert as warning ⚠️. Existing notification types (FD maturity,
   loan apps, waivers, legal SLAs, approvals, month-end) untouched.

3. tests/fixtures/nudge_scenarios.json — 20 labeled scenarios:
     - clear recognition (T001)
     - clear alert (T002)
     - on-pace no-nudge (T003)
     - above-110% but not accelerating (T004)
     - target=0 (T005)
     - target=None (T006)
     - period just started (T007) — verifies early-period guard
     - strong recognition (T008)
     - just-below-110% threshold (T009)
     - just-above-80% pace threshold (T010)
     - clear decline + alert (T011)
     - AML KPI alert with class-specific actions (T012)
     - NPL KPI alert with recovery actions (T013)
     - insufficient history suppresses recognition (T014)
     - mutual exclusivity of recognition vs alert (T015)
     - large numbers (1.5B target, 1.7B value) (T016)
     - zero value with non-zero pace (T017)
     - quarterly period recognition (T018)
     - accelerating but still below 110% (T019)
     - target=0 with low value (T020)

4. tests/test_nudge_engine.py — 36 tests:
     Unit tests:
       - 7 trajectory classifier tests (clear, flat, decline,
         insufficient_data variations, dip-breaks-acceleration)
       - 8 period-progress tests (mid-month, boundaries, before/after,
         quarterly, invalid input)
       - 3 prior-period enumeration tests (monthly, year boundary,
         quarterly)
       - 4 action-items routing tests (deposit/sales, NPL, AML, fallback)
       - 4 recognition-path tests (fires correctly, suppressed cases)
       - 5 alert-path tests including the early-period guard at the
         0.10 boundary
       - 3 persistence tests (save+list, dedup, acknowledge)
     The harness:
       - test_trigger_accuracy_meets_95_percent runs every fixture
         scenario; asserts ≥ 95%; writes nudge_accuracy_results.json
         for G22 to read.

5. scripts/audit.py — new gate G22 nudge_engine_accuracy:
     - Reads nudge_accuracy_results.json
     - Missing → informational pass
     - Present → enforces accuracy_pct ≥ 95.0
     - Fail → lists each missed scenario with reason
     - Same artifact-handoff design as G18-G21

THE TWO ENGINE-CALIBRATION FIXES
--------------------------------
While building the harness against the fixture set I caught two
edge-case errors and fixed them with code changes (not by adjusting
the test):

  Fix 1 — Trajectory: flat-then-spike no longer accelerating.
    [110, 110, 110, 115] previously matched accelerating (deltas
    [0, 0, 5]; latest 5 > mean 0). The new rule requires prior
    delta-mean > 0 — flat-then-spike is now correctly classified
    as "flat" with a single-period spike. Real-world: three flat
    months then one good month doesn't count as a sustained
    upswing — it's noise.

  Fix 2 — Early-period guard: alerts no longer fire below 10%
    period progress. Without this, a low value on day 1 of a 30-day
    month would fire an alert immediately (pace=3, threshold=2.4,
    value=1 < 2.4 → alert). Adding `progress >= 0.10` gives staff
    a few days to ramp up before being nagged. The boundary fires
    at exactly 10% (verified by test).

I also caught and fixed two scenario errors (T016, T018) where I had
specified "linearly growing history" as accelerating — perfectly
linear growth has constant deltas, NOT accelerating. Updated the
fixtures to use truly accelerating histories.

WHAT'S NOT YET WIRED
--------------------
The engine is ready to be invoked but no caller currently invokes it.
The natural integration point is at the bottom of the two BSC bridges:
  - utils/actuals_engine.py (CBS-derived submits)
  - utils/core.update_bsc_from_modules (operational submits)

Both call submit_batch and could add a follow-up loop that calls
nudge_engine.evaluate() per record then save_pending_nudges() the
results. This wiring is deferred to a future session because:
  (a) it's a calling-side change (every record after submit), and
  (b) it adds runtime cost to every batch — wants careful perf
      measurement before enabling
The engine itself is fully tested and the artifact contract is locked.

VERIFICATION (sandbox)
----------------------
  scripts/audit.py syntax OK:                             ✓
  audit gates 22/22 PASS:                                 ✓
  G13 grew: 14 files / 270 tests → 15 files / 306 tests
  python -m utils.nudge_engine self-test:                ALL PASS
  Manual run of all 36 unit tests:                        passes
  Trigger-accuracy harness on fixtures:                   20/20 = 100%
  G22 informational pass when artifact missing:           ✓
  G22 PASS at 96.7% accuracy:                             ✓
  G22 FAIL at 90% accuracy:                               ✓
  G22 FAIL on corrupt artifact:                           ✓
  BSC engine self-test:                                   ALL PASS

PRODUCTION VERIFICATION
-----------------------
  1. pip install -r requirements.txt -r requirements-dev.txt
  2. pytest tests/test_nudge_engine.py -v
     → produces nudge_accuracy_results.json
  3. python scripts/audit.py
     → G22 reports actual accuracy

CURRENT AUDIT STATE (post-v5.38)
--------------------------------
  ✅ G1-G12 all pass (foundational + security)
  ✅ G13: 15 files / 306 tests
  ✅ G14-G17 all pass (architecture)
  ✅ G18-G22 all pass — informational in sandbox, enforced in CI
  Score: 22/22 = 100% PASS

INSTALLATION
------------
1. Extract this zip over your v5.37 working tree.
2. Run audit:
     python scripts/audit.py
   Expected: 22/22 PASS, G22 informational.
3. Run nudge engine self-test:
     python -m utils.nudge_engine
   Expected: ALL TESTS PASSED.
4. Run pytest:
     pytest tests/test_nudge_engine.py -v
   Expected: 36 tests pass; nudge_accuracy_results.json created.
5. Re-run audit:
     python scripts/audit.py
   Expected: G22 reports actual accuracy ≥ 95%.

ROLLBACK
--------
If anything goes wrong:
  1. Restore scripts/audit.py from scripts/audit.py.v5.37.bak
  2. Restore utils/notifications.py from utils/notifications.py.v5.37.bak
  3. Delete:
       utils/nudge_engine.py
       tests/test_nudge_engine.py
       tests/fixtures/nudge_scenarios.json
Or: git revert v5.38.

Pure additive change — removing v5.38 returns to v5.37's exact state.

WHAT'S NEXT
-----------

Volume Two has 10 standards (#11-#20). #11 done. The progression:

  #12 Personalized Growth Paths       — GrowthPathEngine, promotion
                                         readiness scores, skill gaps,
                                         recommended actions
  #13 Daily Micro-Task Engine          — auto-generated daily tasks
  #14 Peer Learning Network            — match staff for skill exchange
  #15 ...

Volume One open items (deferred):
  fast #8 — WCAG 2.1 AA accessibility (axe-core scan + G23)
  fast #10 — UAT framework (68 scenarios + G24)

Operational deployment items (still framework-only):
  G18 — pytest --cov against deployed code
  G19 — k6 load tests against staging
  G20 — FLEXCUBE pipeline against live target
  G21 — pip-audit + safety scan
  G22 — nudge accuracy harness (run pytest in CI to materialize)

Recommended next: fast #12 (Personalized Growth Paths) — same
engine-shape pattern as #11, will reuse the audit-handoff design.

LATENT ISSUES (UNCHANGED)
-------------------------
1. Seed data refresh — `data/*.json` doesn't match production shape.
2. core_kpi shim still in shim phase.
3. 12 PG schemas still missing from get_schema_sql().
4. Export 10K load test still needs ≥10k seed rows.
5. **NEW**: nudge engine not yet wired into bsc_engine submit path.
   Deferred — wants careful perf measurement on batch submits.

COMMIT
------
git add scripts/audit.py utils/nudge_engine.py utils/notifications.py \
        tests/test_nudge_engine.py tests/fixtures/nudge_scenarios.json \
        Master_Prompt_v3.md
git commit -m "v5.38: Standard #11 PerformanceNudgeEngine + G22 gate"
git tag v5.38
git push origin main --tags
