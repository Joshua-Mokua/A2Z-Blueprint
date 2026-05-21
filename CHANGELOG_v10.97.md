# CHANGELOG v10.97 — Phase 1C kickoff: coverage infrastructure + parameterized CRUD smoke test

**Status:** Phase 1C kickoff. Three concrete deliverables that set up the test-coverage workstream: a parameterized CRUD smoke test for the 16 wired modules (112 test cases), test-coverage visibility folded into the audit script (static + dynamic signals), and a helper script for running coverage measurement. Joshua runs the actual measurement in v10.98; this drop builds the infrastructure to ingest and report the result.

**Audit:** 142/142 PASS (unchanged)
**Engine self-tests:** 152/152 (unchanged)
**Migration consistency:** 40/40 FLAT_MIGRATIONS entries verified clean

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.97 | After v10.97 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 (31.3%) | 51 / 163 (31.3%) | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| API endpoints | 147 / 136 (108.1%) | 147 / 136 (108.1%) | 0 (Phase 1B frozen) |
| **Test coverage (static, file-count)** | (uncounted) | **47.9%** of 332 files | new visibility |
| **Test coverage (dynamic, line)** | unknown | unknown — need v10.98 measurement | infra ready |

**No new research_addition standards in this drop.** Maintenance work + infrastructure; continuation_doc count held at floor.

---

## Why this drop is structural, not execution

Earlier phase kickoffs (v10.88 for 1A, v10.92 for 1B) added structural mechanism + first execution batch in the same drop. v10.97 is structure-only:

1. The coverage.py and pytest tools aren't available in the sandbox where I write code, but they ARE available in Joshua's environment. So a coverage measurement here would produce nothing useful; a coverage measurement on Joshua's side produces the real number.

2. Without a baseline number, picking the highest-ROI tests to write is guesswork. The right sequence is: build infrastructure → Joshua measures → I target the gaps.

3. The parameterized CRUD smoke test IS execution — 112 test cases against 16 modules. It just runs in Joshua's environment, not mine.

This is also the recommended Phase 1C pattern from v10.96's CHANGELOG: "v10.97 might NOT be a +24 cadence drop. Test coverage drops have a different shape than CRUD wiring drops." The shape this drop has: infrastructure that pays off across all subsequent Phase 1C drops.

---

## What landed (in order)

### 1. `tests/test_api_v1_crud_modules.py` — parameterized CRUD smoke test

7 test functions × 16 wired modules = **112 test cases**. Each test is parameterized via `@pytest.mark.parametrize` over the `CRUD_MODULES` catalog (which mirrors the 16 `make_crud_router()` calls in `utils/api.py`).

Tests:
- `test_factory_call_succeeds` — `make_crud_router(...)` doesn't raise (table is in TABLE_USE_DB)
- `test_router_has_eight_routes` — APIRouter has exactly 8 routes (catches factory regressions)
- `test_route_paths_follow_v1_pattern` — every route starts with `/api/v1/{module}` (catches misrouting)
- `test_every_route_requires_jwt` — every route's dependant tree includes `get_current_user` (V-001 regression)
- `test_module_registered` — module name shows up in `_REGISTERED_MODULES` (G16 audit relies on this)
- `test_phase_1b_module_count` — sanity check: `CRUD_MODULES` list has exactly 16 entries
- `test_no_duplicate_module_names` — module names are unique

These are STRUCTURAL tests — they don't need live PG or a TestClient. Same shape as the existing `tests/test_api_crud.py`. The point is to lock in the factory contract for each wired module so a future regression (e.g., someone removes a route from the factory, breaks JWT, etc.) fails immediately instead of being noticed in production.

The `CRUD_MODULES` catalog is duplicated from `utils/api.py` configuration. This is intentional — importing `utils/api.py` in tests would trigger FastAPI app construction and pull in all the side-effecting page imports, slowing test collection. The cost is the catalog must stay in sync; the `test_phase_1b_module_count` assertion catches drift loudly.

### 2. `count_test_coverage()` in `audit_completion_state.py`

Two signals:

**Static analysis** — counts test/source ratios per module via:
- Filename pattern: `test_<stem>.py` matches `<dir>/<stem>.py`
- Import scanning: `from utils.X import` / `from pages.X import` etc.

Categorizes each source file as **well-tested** (≥3 test refs), **moderately tested** (1-2 refs), or **untested** (0 refs). Aggregates by directory.

**Dynamic** — parses `coverage.xml` if present. Surfaces overall line-rate percentage and notes the per-module spec targets that G18 enforces.

The text report's new "Test coverage" block shows both signals. Currently:
- Dynamic: "no coverage.xml — run `pytest --cov --cov-report=xml`" (sandbox doesn't have it)
- Static: 93 well-tested, 66 moderate, 173 untested across 332 source files

By directory:
- `utils/` — 92 well + 65 moderate + 57 untested = **73.4% file-count coverage** (157 of 214 files have at least some test reference)
- `scripts/` — 1 well + 1 moderate + 15 untested = 11.8%
- `pages/` — 0 of 101 files have detectable tests = **0.0%**

Note: file-count coverage and line-coverage are different metrics. A file with 1 test reference might have 90% line coverage (if the test exercises most paths) or 5% (if it's a smoke test). The static signal is a heuristic for "where to look for gaps"; line-coverage from `coverage.xml` is the metric that drives the 80% target.

### 3. `scripts/measure_coverage.sh` — coverage runner

Bash wrapper around `pytest --cov --cov-report=xml --cov-report=html`. Defaults to running all tests; takes pytest arguments for subset selection. Outputs:
- `coverage.xml` (cobertura format — G18 audit gate parses this)
- `htmlcov/index.html` (human-readable report)

After running, prints the audit-script command to surface G18's verdict and the audit_completion_state command to see the headline number.

Joshua runs this in his environment. The sandbox environment doesn't have `pytest` or `coverage` (they're not in the audit's runtime dependencies — by design, the audit is a static-analysis tool that runs in any environment).

### 4. SCOPE_LEDGER.md Phase 1C section expanded

Replaced the placeholder "NOT STARTED" content with the full v10.97 kickoff details:
- Three deliverables documented
- Static-signal baseline table (47.9% file-count overall)
- Spec thresholds (`utils/bsc_engine.py` 95%, `utils/db.py` 90%, etc.)
- Multi-drop execution path through ~v10.106

---

## What v10.98 covers

**Joshua's action:** run `./scripts/measure_coverage.sh` in his environment. Output: real `coverage.xml` + `htmlcov/`.

**Drop content (after I see the output):** target the lowest-coverage modules with new tests. Likely candidates from the static signal:
- `utils/flexcube_adapter.py` (67 KB, 0 test refs) — high-volume integration code
- `utils/audit_trail_cert.py` (54 KB, 0 test refs) — audit infrastructure
- `utils/mlops_adjudication_log.py` (53 KB, 0 test refs) — closed arc, but not in well-tested set
- The 53 other untested utils files

If Joshua's measurement reveals which utils modules are below the spec thresholds, those become the v10.98 priority. If utils is mostly fine and pages/ is the gap, v10.98 starts on the page tests (smaller modules first since pages 101 untested files is a much bigger surface).

The Phase 1C estimated cadence (5-10 drops) holds — but v10.98's specific direction depends on the v10.98 measurement.

---

## Files changed

- **NEW** `tests/test_api_v1_crud_modules.py` — 7 test functions × 16 modules = 112 parameterized test cases
- **NEW** `scripts/measure_coverage.sh` — coverage runner helper
- **MOD** `scripts/audit_completion_state.py` — `count_test_coverage()` added; text report extended with Test coverage block
- **MOD** `SCOPE_LEDGER.md` — Phase 1C section replaced with v10.97 kickoff details + multi-drop plan
- **NEW** `CHANGELOG_v10.97.md` (this file)

## Files NOT changed (deliberately)

- `utils/api.py` — Phase 1B is closed; no new modules
- `utils/db.py` — Phase 1A is closed; no schema changes
- `scripts/audit.py` — G18 already exists with the right thresholds; no audit-gate changes
- `scripts/migrate_to_postgres.py` — Phase 1A frozen
- `standards_registry.py` — no new standards
- `utils/api_crud.py` — factory unchanged; the new tests just verify its contract
- `pytest.ini`, `.coveragerc` — both already present and configured correctly
- All closed-arc files — closure invariants preserved

## Honest acknowledgements

**The CRUD_MODULES catalog in the test file duplicates utils/api.py configuration.** If a v10.98 drop adds a new `make_crud_router()` call in api.py without updating CRUD_MODULES in the test file, the test loses parameterization for that module silently. The `test_phase_1b_module_count` assertion catches the count drift but not the actual sync — if I add module 17 in api.py and module 17 in CRUD_MODULES with wrong configuration, the test could pass while testing the wrong thing. Mitigation: keep the count assertion strict, add a comment in api.py reminding that CRUD_MODULES needs updating, and review test diffs alongside api.py diffs in any CRUD drop.

**Static analysis ≠ line coverage.** The 47.9% file-count number is NOT comparable to the 80% line-coverage target. They measure different things:
- File-count: did we write a test that imports/references this file?
- Line-coverage: of the lines in this file, what fraction are executed by tests?

A file can be referenced by 3 tests but have 5% line coverage if the tests only exercise one happy path. Conversely, a file with 0 detected references could have high coverage if other tests transitively execute it. The static signal is a "where to look for gaps" heuristic, not a measurement.

**The `pages/` 0.0% file-count signal might overstate the problem.** Streamlit pages render via `st.*` calls; testing them typically requires Streamlit's testing framework (e.g., `streamlit-testing` library) or explicit unit tests for the page's helper functions. The platform's existing test suite focuses on engines + utils, which is the right priority — pages render UI from data the engines produce. The 70% pages threshold in G18 is aspirational; achieving it requires either Streamlit-specific testing infrastructure or refactoring page logic into testable helpers.

**Joshua's v10.98 measurement might show the existing baseline is well above 45%.** The "~45% baseline" number from the v10.96 plan was an estimate based on indirect signals. The actual line-coverage number could be 35% (worse than estimated) or 60% (better than estimated). Both are possible. The right move is to wait for the measurement before declaring how many drops Phase 1C needs.

**The parameterized CRUD smoke test is asymmetric in coverage value.** It tests the factory contract (well covered by the existing `test_api_crud.py`) and the wiring decisions in `utils/api.py` (the include_router calls). It does NOT test:
- Live PG behavior (those are integration tests)
- Per-module domain logic
- Per-module RLS enforcement (e.g., aml_alerts compliance role check)

So the 112 test cases will likely add modest line-coverage gain but high regression-protection value. The right benchmark is: "if someone breaks the factory or a wiring decision, do these tests catch it?" Answer: yes. The line-coverage gain is a side effect, not the primary value.

**Five-to-ten-drop estimate could be off.** Phase 1A took 4 drops; Phase 1B took 5. Phase 1C complexity is higher because each test requires understanding the module under test. If a few utils modules have intricate logic (e.g., the BSC engine's KPI calculations, the audit script's gates), writing meaningful tests for them takes significant time. Worst case: 12-15 drops. Best case: 4-6 drops if the existing test suite is closer to 80% than expected.

**The audit_completion_state's `count_test_coverage()` makes 332 file-system reads per invocation.** Each source file's test references requires walking the entire `tests/` directory. For a 332-source codebase with ~99 test files, that's ~33k pairs to check. The implementation is a regex scan — fast enough at the current scale (under 1 second), but if the codebase grows 10x it'll be noticeable. Future enhancement: cache test imports in a single pass instead of re-scanning per source. Holding off — premature optimization at current scale.

---

**v10.97 ships under the anti-drift protocol.** Phase 1A COMPLETE (53/52 PG). Phase 1B COMPLETE (147/136 endpoints). Phase 1C KICKOFF — coverage infrastructure live, 112 test cases for the 16 CRUD modules, audit script reports test coverage signals. v10.98 awaits Joshua's coverage measurement to direct the next round of test additions.
