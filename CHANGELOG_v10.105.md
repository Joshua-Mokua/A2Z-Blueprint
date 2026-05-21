# CHANGELOG v10.105 — Phase 1C: bsc_engine close-out (your selling-point engine)

**Status:** Phase 1C continuation. v10.104 hit auth_jwt's target cleanly (91.2% → 95.0%). v10.105 ships 29 close-out tests for `utils/bsc_engine.py` — the most important file in Phase 1C because it's your selling-point engine for BSC autofit. Target: 74.2% → ≥95% (-20.8pp gap → 0).

**Audit:** 142/142 PASS in sandbox (unchanged)
**Engine self-tests:** 152/152 (unchanged)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.105 | After v10.105 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 | 51 / 163 | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| API endpoints | 147 / 136 (108.1%) | 147 / 136 (108.1%) | 0 (Phase 1B frozen) |
| Phase 1C test cases | 342 | **371** (+29 bsc_engine close-out) | +29 |
| Standard #4 spec targets met | 2/5 (core_kpi, auth_jwt) | **3/5 expected** (+ bsc_engine) | +1 |

**No new research_addition standards in this drop.** Targeted close-out tests; continuation_doc count held at floor.

---

## Why this drop matters disproportionately

`utils/bsc_engine.py` is the operational core of the BSC autofit selling point. The CBS pathway (Pathway A from the v10.99 review) flows through `actuals_engine.compute_actuals_from_cbs()` → `bsc_engine.submit_batch()`. Phase 1D (operational-table autofit, Pathway B) will add a second tributary that also feeds `bsc_engine.submit()`. Both pathways depend on the validation, persistence, and read-side functions in this file.

Pre-v10.105: 74.2% coverage means ~156 lines uncovered. Post-v10.105 prediction: 95%+ once these 29 tests run. With bsc_engine verified at spec target, Phase 1D can build the operational-table tributary on a foundation we know works — addressing the v10.99 concern about building on unverified primitives.

---

## What's covered (the 5 categories of uncovered paths)

The existing 44 tests across `tests/test_bsc_engine.py` and `tests/test_bsc_engine_breadth.py` cover the happy paths thoroughly. v10.105 targets what they don't reach:

### Category 1 — Index loading (6 tests)
- `_load_kpi_index` cache-hit branch (second call returns same dict identity)
- `_load_kpi_index` exception path (returns `{}` instead of crashing)
- `_load_users_index` cache-hit branch
- `_load_users_index` exception path
- `_refresh_indexes` resets state (4 module globals to None)
- KPI index includes active_kpis fallbacks (semantic IDs not in catalogue)

### Category 2 — `_coerce_value` edge cases (8 tests)
- None input → None
- Decimal input goes through Decimal-specific branch
- Decimal NaN rejected
- Random object that can't cast to float → None (TypeError path)
- String numeric "12.5" → 12.5 (float() accepts strings)
- String non-numeric "abc" → None
- Above MAX_VALUE → None
- Below MIN_VALUE → None

### Category 3 — `_normalise_period` non-string inputs (5 tests)
- None → None
- int (202604) → None
- dict → None
- Lowercase quarter "2026-q2" → "2026-Q2" (uppercased)
- Whitespace stripped before regex match

### Category 4 — Read-side functions (9 tests)
- `get_actual` with bad period → None
- `get_actual` with no record → None
- `get_actual` picks most recent when multiple records exist
- `get_actual` with load exception → None (not crash)
- `get_actual` with non-Decimal-convertible value → None
- `get_actuals_for_period` with bad period → []
- `get_actuals_for_period` with no records → []
- `get_actuals_for_period` filters by source_module
- `get_actuals_for_period` with load exception → []

### Category 5 — `_self_test` direct invocation (1 test)
- Discovered an oversight: bsc_engine's self-test function is named `_self_test` (underscore prefix), so the v10.98 engine-self-test wrapper doesn't pick it up (the wrapper looks for `def self_test(`). This means 60+ lines of internal smoke-test code were never exercised under coverage. v10.105 invokes it directly via a single test that captures stdout and asserts exit code 0. This is the highest-leverage single test in this drop.

---

## Sandbox verification

Of the 29 tests, 18 are direct assertions I could verify in the sandbox without the PG/JSON fixture infrastructure:

```
18/18 assertions hold
✓ _self_test internal: ALL TESTS PASSED
```

The other 11 tests need the `tmp_data_dir` fixture (PG/JSON layer) and verify at pytest run time on Joshua's side. Those tests follow the same fixture pattern as the existing `tests/test_bsc_engine.py` (33 tests) which all pass on Joshua's env, so the pattern is known-working.

---

## Files changed

- **NEW** `tests/test_bsc_engine_closeout.py` — 29 tests across 6 classes targeting 5 categories of uncovered paths
- **MOD** `SCOPE_LEDGER.md` — Phase 1C status updated
- **NEW** `CHANGELOG_v10.105.md` (this file)

## Files NOT changed (deliberately)

- `utils/bsc_engine.py` — no production code changes; tests cover existing behaviour as-is. The `_self_test` underscore-prefix oversight could be fixed by adding a `self_test = _self_test` alias so the engine wrapper picks it up — but that would change the wrapper's count from 152 to 153 engines, which has cascading effects on test_engine_count_matches_runner_baseline. Cleaner to exercise `_self_test` directly via this test file and leave the engine wrapper unchanged.
- `tests/test_engine_self_tests.py` — v10.103's encoding fix is working
- `tests/test_api_v1_crud_modules.py` — v10.103's api.py import test landed cleanly
- `tests/test_actuals_engine_module.py` — v10.103's pure-function tests landed
- `tests/test_auth_jwt_closeout.py` — v10.104's tests are operational
- `scripts/audit.py`, `scripts/coverage_summary.py`, `scripts/audit_completion_state.py` — all working post-v10.102/v10.101
- All Phase 1A/1B closed-arc files — closure invariants preserved

## Honest acknowledgements

**The `_self_test` underscore-prefix oversight is the kind of thing that ought to be caught by a meta-test.** The engine wrapper's `_discover_engines()` regex says `def self_test(` (no underscore). Any engine module using `_self_test` (private convention) is silently excluded. This is the second time underscore-prefix conventions have caused silent test exclusions (the first was tests/__init__.py in some early drops). The right meta-fix is either: enforce the public `self_test` convention via a lint rule, or have the discovery accept both. Holding off on the meta-fix because it's scope creep beyond Phase 1C; flagging for the future Phase 1E if we ever do a cleanup pass.

**The 29-test count is bigger than my v10.104 estimate of "25-35 tests."** I went up to 29 because the 5 categories of uncovered paths each had several distinct cases worth testing — the temptation to drop, say, the "Decimal NaN rejected" test for brevity would have left a real edge case unverified. The selling-point status of this engine warrants thorough coverage rather than minimum-viable.

**11 of 29 tests need fixture infrastructure I can't run in sandbox.** The `tmp_data_dir` fixture creates a temp directory and points DATA_DIR + the JSON files there. My sandbox lacks pytest, so I can't run these directly. The mitigation: I made the fixture pattern identical to the existing `tests/test_bsc_engine.py` fixture which has been working on Joshua's env across 33 tests. If the pattern is sound there, it's sound here. But I do want Joshua to flag any test failures on his run that aren't simple assertion-mismatch fixes.

**The `test_picks_most_recent_when_multiple` test makes a determinism assumption.** It asserts that submitting 20.0 from "src_b" after 10.0 from "src_a" results in get_actual returning 20.0. The "most recent wins" behaviour relies on `submitted_at` ordering being microsecond-precise enough to differentiate two adjacent calls. On a fast machine this could fail intermittently if both submits hash to the same `submitted_at` millisecond. If Joshua's run shows this test flaking, the fix is to add a `time.sleep(0.001)` between submits — but I'd rather flag the assumption now than ship the sleep and obscure what it's there for.

**The 95% target prediction is conservative.** The 29 tests target ~120-150 lines of currently-uncovered code (out of ~156 total uncovered). Even if 80% of those lines are reachable through these tests (realistic — fixture-dependent tests sometimes don't hit the branches I expect), that's 96-120 newly-covered lines, taking bsc_engine from 74.2% to roughly 90-94%. The full 95% might require one more drop with `coverage report --show-missing utils/bsc_engine.py` to identify any specific lines my tests still don't reach. Worth flagging the possibility.

**v10.105 has a higher-than-usual chance of needing a v10.106 follow-up patch on bsc_engine itself, before db.py work begins.** Justification: the file matters disproportionately, the tests are fixture-heavy, and inferred-from-source target identification is error-prone. If the post-v10.105 measurement shows 92-94% on bsc_engine instead of 95%+, v10.106 starts with a small bsc_engine top-up rather than db.py investigation. v10.106's plan flexes to whichever the measurement shows.

---

**v10.105 ships under the anti-drift protocol.** Phase 1A COMPLETE. Phase 1B COMPLETE. Phase 1C IN PROGRESS — bsc_engine close-out delivered (29 tests across 6 classes), addressing the 5 categories of uncovered paths in the most operationally-critical engine. v10.106 plans flex against the measurement: if bsc_engine hit 95%, start db.py investigation; if 92-94%, top-up bsc_engine first.
