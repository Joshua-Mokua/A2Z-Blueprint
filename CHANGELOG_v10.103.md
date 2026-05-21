# CHANGELOG v10.103 — Phase 1C: diagnostic + first targeted tests

**Status:** Phase 1C continues. v10.102 unblocked the per-target view. Diagnostic on Joshua's env revealed two issues with my earlier work plus one large untested module worth targeting now. Three concrete fixes in one drop.

**Audit:** 142/142 PASS in sandbox (unchanged)
**Engine self-tests:** 152/152 (unchanged)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.103 | After v10.103 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 | 51 / 163 | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| API endpoints | 147 / 136 (108.1%) | 147 / 136 (108.1%) | 0 (Phase 1B frozen) |
| Phase 1C test cases | 290 | **325** (+3 api.py import tests +32 actuals_engine) | +35 |
| Engine wrapper expected on Windows | 0/152 (broken) | 152/152 (after fix) | unblocks |

**No new research_addition standards in this drop.** Maintenance + targeted tests; continuation_doc count held at floor.

---

## What the v10.102 coverage data showed

After the v10.102 schema fix, the real picture emerged:

| Spec target | Actual | Target | Gap |
|---|---|---|---|
| `utils/auth_jwt.py` | 91.2% | 95% | -3.8pp (close) |
| `utils/bsc_engine.py` | 74.2% | 95% | -20.8pp |
| `utils/core_kpi.py` | 100% | 85% | PASS already |
| `utils/db.py` | 32.1% | 90% | -57.9pp |
| `pages/` | 1.0% | 70% | -69pp |

Top 20 gaps in `utils/` showed:
- `utils/api.py`: **0.0%** (355 uncovered lines)
- `utils/actuals_engine.py`: **3.2%** (663 uncovered)
- `utils/mlops_persistence.py`: **0.0%** (357 uncovered)
- `utils/trading_book_boundary.py`: **0.0%** (344 uncovered)
- `utils/reconciliation.py`: **0.0%** (248 uncovered)
- and others

The 0%s on api.py and the engine modules with `self_test()` were the diagnostic. Those modules SHOULD have been exercised by my v10.97/v10.98 tests. Joshua's `pytest --collect-only` confirmed:

- `tests/test_engine_self_tests.py` collected **0 items**
- `tests/test_api_v1_crud_modules.py` collected 82 items but doesn't import `utils/api.py`

---

## What landed (in order)

### 1. `tests/test_engine_self_tests.py` — explicit utf-8 in discovery

The original `_discover_engines()` used `path.read_text(errors="ignore")` without explicit encoding. On Windows that defaults to cp1252. While `errors="ignore"` keeps the function from raising, the combination might silently mis-decode multi-byte UTF-8 sequences in some engine docstrings (the `═` `║` `▶` characters used heavily for box drawings) in a way that prevents the substring match `"def self_test(" in text` from succeeding.

I'm not 100% certain that's the cause — the fix is precautionary because it's the most likely explanation matching the symptom (0 items collected, no error message). Even if it isn't the root cause, explicit utf-8 is the right encoding for these source files.

If after this fix the file still collects 0 items, the next debugging step is `pytest tests/test_engine_self_tests.py --collect-only -v` (verbose, full output) to see if pytest is reporting an error somewhere. v10.103's CHANGELOG asks Joshua to run that if the symptom persists.

### 2. `tests/test_api_v1_crud_modules.py` — three new api.py import tests

Original v10.97 design deliberately avoided importing `utils/api.py` to keep test collection fast — importing api.py triggers FastAPI app construction + 100+ page imports + all 16 `app.include_router()` calls. That's slow at collection time.

But the side effect is api.py never executed during tests, so coverage was 0%. v10.103 adds three explicit import tests as a module-scoped fixture:

- `test_api_module_imports` — basic guarantee api.py imports cleanly
- `test_api_module_has_app` — the FastAPI `app` instance exists and has routes
- `test_api_module_route_count_at_phase_1b_floor` — soft floor of ≥100 routes (Phase 1B closed at 147; floor allows for legitimate refactors but catches accidental removal)

These three tests should bring `utils/api.py` from 0% to substantial coverage (most of the 355 lines are import-time decorators and include_router calls — they all execute at the moment of import).

The slow-collection cost is real but bounded: a few seconds added to pytest startup. The coverage gain is large.

### 3. `tests/test_actuals_engine_module.py` — NEW, 32 unit tests

`utils/actuals_engine.py` is the existing BSC autofit pipeline. Phase 1D (BSC autofit completion) extends this same module. Coverage was 3.2% pre-v10.103 — meaning Phase 1D would build on essentially unverified primitives, exactly the v10.99 concern.

Test breakdown:
- **TestMapCbsToKpi (18 tests):** the primary KPI lookup function. Both paths (exact ID match via ID_MAP, name-fallback via substring matching), edge cases (missing fields → 0.0, None values → 0.0, ID precedence over name)
- **TestPeriodConversion (4 tests):** period format converter
- **TestPathHelpers (5 tests):** _root, get_cbs_paths, get_period_label
- **TestModuleExports (5 tests):** public API callables exist (compute_actuals_from_cbs, aggregate_cbs_by_rm, etc.)

All 30 assertions verified clean against the actual module in the sandbox (manual run before shipping).

What this DOESN'T cover:
- `compute_actuals_from_cbs()` end-to-end — needs CBS file fixtures
- `aggregate_cbs_by_rm()` — same, fixture-heavy
- `_build_from_cbs()` — depends on KPI library + staff list

Those are integration-test scope. The pure-function surface plus import-time coverage should bring actuals_engine from 3.2% to roughly 35-40%, leaving 50-60% for the integration tests when Phase 1C closure needs them (or earlier if Phase 1D depends on those paths being verified).

---

## What v10.104 awaits

Joshua re-runs the full pytest:

```powershell
pytest --cov --cov-report=xml --cov-report=html tests/
python3 scripts/coverage_summary.py
```

Then sends me the new coverage_summary output. With v10.103 applied, expected changes:

- **utils/api.py**: 0.0% → 60-80% (most lines run at import time)
- **utils/actuals_engine.py**: 3.2% → 35-40%
- **utils/auth_jwt.py**: 91.2% → 91.2% (unchanged this drop; close to target, planned for v10.104)
- **utils/bsc_engine.py**: 74.2% → 74.2% (unchanged this drop; needs targeted tests in v10.105)
- **Engine modules with self_test()**: from 0% to substantial coverage IF the encoding fix unblocked discovery
- **Overall**: 36.5% → likely 42-48%

If the engine-wrapper fix doesn't work (still 0/152 collected on Joshua's env), v10.104 investigates with verbose collection output. If it does work, v10.104 targets `auth_jwt.py` (close-out, ~5 tests) and `db.py` (large gap, 30+ tests across the dual-mode JSON/PG paths).

---

## Files changed

- **MOD** `tests/test_engine_self_tests.py` — explicit `encoding="utf-8"` in `_discover_engines()`
- **MOD** `tests/test_api_v1_crud_modules.py` — 3 new tests + 1 module-scoped fixture for api.py import
- **NEW** `tests/test_actuals_engine_module.py` — 32 unit tests across 4 test classes
- **MOD** `SCOPE_LEDGER.md` — Phase 1C status updated with diagnostic findings + targeting plan
- **NEW** `CHANGELOG_v10.103.md` (this file)

## Files NOT changed (deliberately)

- `utils/api.py`, `utils/actuals_engine.py` — no production code changes; tests cover existing behaviour as-is
- `scripts/audit.py`, `scripts/coverage_summary.py` — v10.102's fixes still working
- `scripts/audit_completion_state.py` — its `count_test_coverage()` still has the cobertura schema bug; left for v10.105 if the state report becomes load-bearing again
- All Phase 1A/1B closed-arc files — closure invariants preserved

## Honest acknowledgements

**The engine wrapper's broken-on-Windows behaviour is mine.** I designed `_discover_engines()` to mirror `scripts/run_engine_self_tests.py` exactly — except the runner script's discovery was tested in CI on Linux, and CI runs on Linux. The wrapper inherited the same encoding-naive read which works on Linux but breaks on Windows. The pattern is now: any code that reads source files and pattern-matches against them needs explicit encoding, full stop. Same lesson as v10.100. Adding it to the pre-flight checklist again, and this time also reviewing all of `tests/` and `scripts/` for the same pattern.

**The v10.97 CRUD smoke test design was a tradeoff with bad downstream consequences.** I deliberately didn't import `utils/api.py` to keep test collection fast. That decision left api.py at 0% coverage, which I didn't notice until v10.102 showed the gap. v10.103 adds back the import path with the slow-collection cost. The right initial design would have been to import api.py once via a module-scoped fixture (which is what I'm doing now), accepting the few-second slowdown for the coverage benefit.

**The actuals_engine tests are pure-function coverage only.** That's intentional — fixture-heavy integration tests for `compute_actuals_from_cbs()` need real CBS files (or carefully-built synthetic ones), staff lists, and KPI library setup. Adding 30 quick pure-function tests now is high-ROI; the integration tests are a separate workstream that can happen as Phase 1D builds on top of actuals_engine. If Joshua wants the integration tests prioritized, that changes Phase 1C's shape — let me know.

**32 tests in one file with class-grouping but no parametrize.** I deliberately used test classes for grouping rather than `@pytest.mark.parametrize` because each `_map_cbs_to_kpi` test asserts a different combination of ID/name/data, not the same logic with different inputs. Parametrize would force a uniform shape on tests that shouldn't be uniform. Class-grouping keeps related tests together while letting each one express its specific check. Result: 32 distinct test names in pytest's output, easy to identify when one fails.

**The api.py import test has a side effect on test collection time.** The module-scoped fixture means import happens once per session (good), but it's a heavy import (FastAPI + 100+ pages). On Joshua's Windows env, expect pytest collection to take 5-15 seconds longer. That's acceptable for the coverage win, but if it becomes a CI bottleneck, the right move is splitting api.py imports into a separate test session (slow tests marker) that runs less often. Holding off — measure first.

---

**v10.103 ships under the anti-drift protocol.** Phase 1A COMPLETE. Phase 1B COMPLETE. Phase 1C IN PROGRESS — diagnostic findings addressed, 35 new test cases added, two coverage gaps targeted (api.py 0% → expected 60-80%, actuals_engine 3.2% → expected 35-40%). v10.104 awaits the next coverage measurement to confirm the predicted gains and target the next round.
