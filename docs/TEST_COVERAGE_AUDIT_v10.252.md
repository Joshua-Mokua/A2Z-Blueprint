# A2Z MIS 360 — Test Coverage Reality Audit (v10.252)

**Audit date:** 2026-05-07
**Scope:** Test coverage state vs memory's "~45%" claim. Pattern follows
v10.251's PG audit and v10.219's tenant audit.
**Audit baseline:** 162/162 PASS at start of batch.

---

## Executive summary

The test infrastructure is substantial — **187 test files across 9
categories, ~61,620 lines of test code**. But coverage cannot be
measured in the current sandbox (pytest + coverage not installed),
so memory's "~45%" claim cannot be verified.

What CAN be verified:
- Test structure exists and is well-organized
- conftest.py provides fixtures (113 lines)
- Test categories align with platform discipline (unit / integration /
  e2e / regression / performance / security / accessibility / integrity /
  dr / load)
- Most test files were shipped between v9.26–v9.30 (per
  `tests/README.md`)

What CANNOT be verified:
- Actual line/branch coverage percentage
- Which engines / utils / pages are well-covered vs gaps
- Whether tests pass on current code

**This audit's contribution:** inventory + documentation + G165 skeleton
ratchet (deferred activation until coverage can be measured).

---

## 1. Test infrastructure inventory

### 1.1 Test categories (per tests/README.md)

| Directory | Purpose | Tools | Status |
|---|---|---|---|
| `tests/` (root) | Unit tests for engines + utilities | unittest (stdlib) | ✅ 53 files |
| `tests/integration/` | Cross-module workflow correctness | unittest | ✅ 43 tests |
| `tests/e2e/` | End-to-end user journeys | Playwright (optional) | 🟡 1 file (scaffolding) |
| `tests/regression/` | Audit gate + invariant regression | unittest + audit.py | ✅ |
| `tests/performance/` | Latency + throughput benchmarks | unittest + load_test_multi_instance | ✅ 1 file |
| `tests/security/` | DAST + injection / XSS / param tampering | unittest | ✅ 1 file |
| `tests/accessibility/` | WCAG 2.1 AA compliance | axe-selenium (optional) | 🟡 1 file (scaffolding) |
| `tests/integrity/` | Dual-write JSON ↔ PostgreSQL consistency | unittest | ✅ |
| `tests/dr/` | Disaster recovery + failover | unittest | ✅ 1 file |
| `tests/load/` | k6 load scripts | k6 (optional) | ✅ existing |
| `tests/fixtures/` | Scenario JSON for byte-for-byte tests | — | ✅ existing |

### 1.2 By the numbers

```
Total test files:    187 test_*.py files
Total test code:     ~61,620 lines
conftest.py size:    113 lines (fixtures, setup/teardown helpers)
Categories:          9 active + scaffolding for 2 more
```

### 1.3 What's missing

- **No coverage.xml or htmlcov/** in the repo. Either coverage was
  never measured, or the artifacts weren't committed.
- **No CI workflow visible** that runs tests + reports coverage.
- **187 test files but no master test runner** documented in README's
  "How to run" section beyond "pytest".
- **Optional dependencies** (Playwright, axe-selenium) suggest some
  tests are skipped in default runs. Coverage from skipped tests is 0.

---

## 2. Why memory's 45% can't be verified

Memory says "test coverage (~45%)" but:

1. No coverage report file exists in repo → can't check measurement
2. pytest + coverage not installed in this sandbox → can't measure now
3. README doesn't reference a baseline coverage number → no historical
   anchor

The 45% number could be:
- Measured at some past point and remembered
- An estimate based on test file count vs source file count
- Aspirational — the target the team wanted to reach

**Without a coverage.xml in the repo, the number is unverifiable.**

---

## 3. Recommended G165 skeleton (kaizen ratchet)

```python
def gate_test_coverage_baseline():
    """G165 — kaizen ratchet on test coverage.

    Reads coverage.xml from the repo root. If present, compares
    line-coverage percentage to baseline in audit_baselines.json.

    PASSES if:
      - coverage.xml absent (no measurement yet — gate is informational)
      - coverage ≥ baseline
    FAILS if:
      - coverage.xml present AND coverage < baseline - 0.5pp tolerance

    The 0.5pp tolerance prevents flaky-test noise from triggering FAILs.
    Real regressions (1pp+ drops) still get caught.
    """
```

**Defer activation to when coverage.xml can be generated.** Adding
G165 now would:
- Pass trivially (no coverage.xml → "informational" branch)
- Provide no actual protection
- Reset baseline silently on first measurement

Better: Joshua runs `pytest --cov=. --cov-report=xml` in his
environment, commits the coverage.xml, and v10.NEXT activates G165
against the real baseline.

---

## 4. Recommended sub-campaign

### Phase A — Establish measurement (Joshua-action)

```bash
# In Joshua's office PC environment
pip install pytest pytest-cov coverage
pytest --cov=. --cov-report=xml --cov-report=html
# Commits: coverage.xml, htmlcov/
```

This produces:
- `coverage.xml` — machine-readable report (G165 reads this)
- `htmlcov/` — human-readable report (Joshua reviews to prioritize)

### Phase B — Activate G165 (one batch)

After coverage.xml exists:
```python
# Add G165 gate function to scripts/audit.py
# Add baseline to data/audit_baselines.json
# G165 reads coverage.xml, compares to baseline, FAILS on drop > 0.5pp
```

### Phase C — Coverage push sub-campaign (3-5 batches)

Target the lowest-coverage modules first:
1. Identify ~5 lowest-coverage utility modules
2. Add unit tests targeting their public APIs
3. Each batch raises coverage by ~1-2pp
4. Stop when coverage reaches a healthy plateau (~75-80%)

After 3-5 batches: coverage ratchets from baseline up to ~70-75%
sustainably.

---

## 5. What's already strong

1. **187 test files is substantial.** Many platforms have <50.
   The test infrastructure exists and is well-categorized.

2. **Audit gate suite is its own integration test.** 162 ratcheting
   gates exercise import paths, constructors, methods, access
   controls, audit_log discipline. This isn't unit-test coverage,
   but it IS behavior coverage.

3. **conftest.py with fixtures.** Suggests tests are organized
   around real data scenarios, not isolated mocks.

4. **Test categories align with platform discipline.** Integrity
   tests for dual-write seam, DR tests for failover, security
   tests for injection — these match the platform's actual risks.

---

## 6. What's missing

1. **No measured coverage baseline.** Can't enforce "no drops"
   without a number to anchor against.

2. **CI integration unclear.** If tests don't run automatically on
   every commit, coverage drift can sneak in.

3. **Test maintenance discipline.** As pages refactor (e.g. v10.222
   onwards's tenant cleanup), associated tests may need updates.
   No clear ratchet protects against test/code divergence.

4. **No gate enforces "every page has at least one smoke test."**
   Could be a future ratchet — every active page in the manifest
   needs `tests/smoke/test_<page>.py` or equivalent.

---

## 7. Honest acknowledgements

1. **Sandbox limitation prevents direct measurement.** pytest +
   coverage not installed in this environment. Audit relies on
   file-system inventory + tests/README.md content.

2. **G165 is deferred, not skipped.** Skeleton documented; awaits
   coverage.xml from Joshua's environment to activate.

3. **The 45% memory claim is plausible but unverifiable.** Could
   be accurate, optimistic, or stale. Memory reconciliation Rule N6
   says: when reality can't be checked, mark the claim as such
   rather than treating it as ground truth.

4. **51 consecutive clean batches.**

5. **No code changes in this batch** — pure documentation.
   Single-purpose discipline holds.

---

## 8. Memory update recommended

```diff
- test coverage (~45%)
+ test coverage: 187 test files across 9 categories (~61,620 lines).
+ Coverage measurement deferred — pytest + coverage required in
+ runtime environment. Once coverage.xml exists, G165 ratchet will
+ activate to prevent drops. Sub-campaign of 3-5 batches will push
+ coverage to ~70-75% from whatever the measured baseline is.
```

---

## 9. Comparison with v10.219 + v10.251 audits

| Audit | Memory said | Reality | Gap |
|---|---|---|---|
| v10.219 — tenant identity | (not specified) | ~4,100 hardcoded values | Quantified for first time |
| v10.251 — PG migration | "33/52 tables" | 12 in DDL, 2 migrators | Memory was 20pp optimistic |
| v10.252 — test coverage | "~45%" | unmeasurable in sandbox | Memory unverifiable |

Three audits, three different drift modes:
- Tenant identity: memory was silent; audit quantified the surface
- PG migration: memory was optimistically wrong; audit measured reality
- Test coverage: memory may be right or wrong; audit names the
  uncertainty

This pattern of periodic audit-against-memory is what Rule N6 + the
KAIZEN framework's "weekly memory reconciliation" ritual is supposed
to catch. v10.252 is the third such reconciliation in this session.
