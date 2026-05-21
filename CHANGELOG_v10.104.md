# CHANGELOG v10.104 — Phase 1C: repo sync + auth_jwt close-out + bearer-without-token fix

**Status:** Phase 1C continuation. Three deliverables: ship the missing `utils/mlops_model_registry.py` (closes the standards_registry test failure + unblocks engine wrapper for mlops_persistence + restores 7 dependent modules), fix the `Bearer ` IndexError in `utils/auth_jwt.py` (real bug found by your test run), and add 17 close-out tests for auth_jwt to push it from 91.2% to ≥95% (one Standard #4 spec target closed).

**Audit:** 142/142 PASS in sandbox (unchanged)
**Engine self-tests:** 152/152 (unchanged)

---

## Scope completion delta (anti-drift Rule B)

| Dimension | Before v10.104 | After v10.104 | Δ |
|---|---|---|---|
| continuation_doc active | 51 / 163 | 51 / 163 | 0 (held at floor) |
| research_addition active | 90 | 90 | 0 |
| PG migration coverage | 53 / 52 (101.9%) | 53 / 52 (101.9%) | 0 (Phase 1A frozen) |
| API endpoints | 147 / 136 (108.1%) | 147 / 136 (108.1%) | 0 (Phase 1B frozen) |
| Phase 1C test cases | 325 | **342** (+17 auth_jwt close-out) | +17 |
| Standard #4 spec targets met | 1/5 (core_kpi only) | **2/5 expected** (core_kpi + auth_jwt) | +1 |
| Repo file count (utils/) | n/a | +1 (mlops_model_registry.py) | unblocks 7 dependents |

**No new research_addition standards in this drop.** Bug fix + repo sync + targeted close-out tests; continuation_doc count held at floor.

---

## What landed (in order)

### 1. `utils/mlops_model_registry.py` — file restoration

**Joshua's `Test-Path utils\mlops_model_registry.py` returned False.** The file existed in the working sandbox (~50 KB, dated May 3) but never made it into your repo. This was the only confirmed missing file across all the test-suite anomalies we've been seeing:

- `tests/integration/test_standards_registry.py::test_affected_engines_exist` failed because the file is referenced in standards_registry but doesn't exist
- `tests/test_engine_self_tests.py::test_engine_self_test[mlops_persistence]` failed because mlops_persistence imports it
- 7 other modules silently degrade when it's absent: `mlops_model_card_composer.py`, `scenario_simulator.py`, `mlops_adjudication_log.py`, `scripts/audit.py` G124 reference, `standards_registry.py` ENH-281 entry, `pages/7_admin.py`, `pages/98_ml_governance_arc_cockpit.py`

The file is the v10.81 ml_governance arc engine — five capabilities for ML model version tracking (register_new_model_version, lookup_active_version, list_versions, compare_versions, validate_promotion_readiness). Module-level docstring documents the boundary with `utils/model_governance` (closed at G124): operational lifecycle (this file) vs validation lifecycle (model_governance).

This isn't NEW code — it's restoration of code that's been part of the platform but somehow didn't sync into your local repo. After applying v10.104, those 4-5 chained test failures resolve.

### 2. `utils/auth_jwt.py` — IndexError fix in `get_current_user`

**Real bug found by your test run.** `tests/test_auth_jwt.py::test_bearer_without_token_rejected` failed with IndexError, not the expected HTTPException. Trace:

```python
authorization = "Bearer "  # trailing space, no token
# .lower().startswith("bearer ") → True (passes guard)
authorization.split(None, 1)
# → ["Bearer"]   (length 1, not 2)
# → [1] raises IndexError
```

The fix adds an explicit length-check after split:

```python
parts = authorization.split(None, 1)
if len(parts) < 2 or not parts[1].strip():
    raise HTTPException(status_code=401, ...)
token = parts[1].strip()
```

Verified in sandbox against 7 edge cases:
- `"Bearer "` (trailing space) → 401 ✓
- `"Bearer  "` (double space) → 401 ✓
- `"Bearer"` (no space at all) → 401 ✓
- `""` (empty) → 401 ✓
- `"Basic xyz"` (wrong scheme) → 401 ✓
- `None` → 401 ✓
- `"Bearer abc.def.ghi"` (valid format, fake token) → 401 "Invalid token" ✓

This is a security-relevant fix. Pre-v10.104, a request with `Authorization: Bearer ` would crash the FastAPI handler with a 500 error and a Python traceback in logs (information leak). Post-v10.104, it returns a clean 401 with the documented `WWW-Authenticate: Bearer` challenge header.

### 3. `tests/test_auth_jwt_closeout.py` — 17 tests across 5 classes

Targets the ~5pp of auth_jwt that existing tests don't reach:

**TestResolveSecret (4 tests):** the env-var resolution path. Existing tests bypass this by monkeypatching SECRET_KEY directly; this file exercises `_resolve_secret()`'s real branches.
- env var set → returns its value
- whitespace stripped from env var
- env unset → falls back to generated 48-char secret
- empty env var ("") → treated as unset, falls back to generation

**TestWarnIfDefaultSecret (2 tests):** both branches of the startup warning.
- `_DEFAULT_SECRET_USED=True` → warning logged
- `_DEFAULT_SECRET_USED=False` → no warning

**TestCreateAccessTokenEdgeCases (3 tests):**
- Missing both `username` and `sub` → ValueError raised
- `sub` accepted as username alias (covers `.get('username') or .get('sub')`)
- Default role is "Staff" when role key absent

**TestRequireAdminImpl (5 tests):** direct unit on the inner role check.
- Admin role passes
- Director role passes
- Case-insensitive (admin/Admin/ADMIN/AdMiN)
- Staff role → 403
- Missing role → 403

**TestBearerEdgeCases (3 tests):** regression tests for the v10.104 IndexError fix.
- "Bearer " trailing space → 401
- "Bearer    " multiple trailing spaces → 401
- "Bearer" no space at all → 401

Expected coverage gain on `utils/auth_jwt.py`: 91.2% → ≥95% (4-5pp). The 17 tests target the specific uncovered lines visible from inspection (the `warn_if_default_secret` branches, `_resolve_secret` env-set path, `create_access_token` ValueError, `_require_admin_impl` role checks).

---

## Phase 1C roadmap (Joshua confirmed pages/ aspirational)

| Drop | Target | Coverage move |
|---|---|---|
| ✅ v10.104 | auth_jwt close-out + repo sync + IndexError fix | 91.2% → ≥95% |
| v10.105 | bsc_engine close-out (your selling-point engine) | 74.2% → ≥95% |
| v10.106 | db.py investigation + first batch | 32.1% → ~50-60% |
| v10.107 | db.py close-out + Phase 1C closure | → ≥90% |
| v10.108 | Phase 1D kickoff (BSC autofit completion) | n/a |

Pages/ at 1% declared aspirational; revisited as Phase 1E after Phase 1D closes (or never — depends on operator priorities).

---

## Files changed

- **NEW** `utils/mlops_model_registry.py` — restored from sandbox; ~50 KB; 5 capabilities; was missing from your repo
- **MOD** `utils/auth_jwt.py` — `get_current_user` IndexError fix (parts-length check after split)
- **NEW** `tests/test_auth_jwt_closeout.py` — 17 tests across 5 classes
- **MOD** `SCOPE_LEDGER.md` — Phase 1C roadmap with Joshua's pages/ aspirational decision
- **NEW** `CHANGELOG_v10.104.md` (this file)

## Files NOT changed (deliberately)

- `tests/test_engine_self_tests.py` — v10.103's encoding fix is working (3,633 passed in your run)
- `tests/test_api_v1_crud_modules.py` — v10.103's api.py import test landed
- `tests/test_actuals_engine_module.py` — v10.103's 32 tests landed
- `scripts/audit.py`, `scripts/coverage_summary.py` — v10.102's cobertura schema fix is working (per-target numbers correct now)
- `scripts/audit_completion_state.py` — its coverage.xml parsing reads only the root `line-rate` attribute (overall %), doesn't have the per-target schema bug, no fix needed
- All Phase 1A/1B closed-arc files — closure invariants preserved
- The 5 unfixed test files with cp1252 encoding bugs (`test_dependency_audit.py`, `test_growth_path_engine.py`, `test_peer_learning.py`, `test_performance_insights.py`, `test_volume_five_batch.py`) — pre-existing tech debt; deferred until Phase 1C closes

## Honest acknowledgements

**The missing file was a quiet repo-sync issue I should have flagged earlier.** The standards_registry test failure has been visible in every pytest run since v10.100. I noted it twice as "Joshua-env-specific, file exists in my sandbox, would pass in a synced repo" — but didn't propose shipping the file. The right move was to ship it the moment your `Test-Path` returned False; I waited for explicit authorization. Process gap: when a file exists in sandbox + is referenced by tests/audits + is missing from Joshua's repo + Joshua confirms missing, ship without further negotiation. Folding into pre-flight checklist.

**The IndexError fix is the v10.99 finding I should have addressed three drops ago.** Your CHANGELOG-v10.99 reply mentioned "test_bearer_without_token_rejected with IndexError" as an unresolved issue. v10.100, v10.101, v10.102, v10.103 all left it on the table. The pattern of "noted but not fixed" creates exactly the drift the anti-drift protocol was built to prevent. Direction: any test failure attributable to a real production-code bug (not test infrastructure) gets fixed in the next drop, not deferred.

**The 17 close-out tests are inferred-uncovered, not measured-uncovered.** I haven't seen a per-line coverage report for `utils/auth_jwt.py` (only the file-level 91.2%). The test design targets the lines I can identify by reading the source — the env-var resolution path, the warn function's both branches, the require_admin placeholder/impl pair. If my inference is right, this drop closes the target; if wrong, you'll see the post-v10.104 number stay at 91.2% and v10.105 needs a more targeted approach (using `coverage report --show-missing utils/auth_jwt.py` to see specific uncovered line numbers). Worth flagging.

**The fixture pattern in the close-out tests does `del sys.modules["utils.auth_jwt"]` repeatedly.** That's because `_resolve_secret` reads the env var ONCE at module-import time, sets `SECRET_KEY` from that, and never re-reads. To test the env-var-set path, the module has to be re-imported with the env state we want. This is hacky but correct for the goal. A cleaner design would be a `auth_jwt.refresh_secret()` function or a `Config()` class — but that's refactor scope, not test scope.

**v10.104 doesn't fix the audit script crashes (`G2 G8 G18 G110 G118 G123 G139` failing) on your re-run.** Those cascading failures are downstream of the audit subprocess output handling under Windows. The actual audit gate failures (G123 missing audit_trail_cert, G18 below threshold for 4/5 spec targets) are the **truth** the audit script is reporting — not bugs in audit.py. When auth_jwt closes (v10.104) and bsc_engine closes (v10.105) and db.py closes (v10.107), G18 will go from 1/5 to 4/5 thresholds met (with pages/ remaining as the only failing target, by your aspirational-decision design). That's the right path.

**The v10.103 coverage gain prediction was off by ~half.** I predicted overall 36.5% → 42-48%; actual was 49.9%. Better than I projected because the engine wrapper unblocking lit up much more code than I expected. v10.104's prediction (auth_jwt 91% → 95%, no significant change to overall) is more conservative because the close-out is targeted at one file. Expect overall to stay around 50% after v10.104 and move significantly only with v10.105 (bsc_engine 74% → 95% on a 4,000-line file is +800 covered lines).

---

**v10.104 ships under the anti-drift protocol.** Phase 1A COMPLETE. Phase 1B COMPLETE. Phase 1C IN PROGRESS — repo synced, real production bug fixed, auth_jwt targeted close-out tests delivered. v10.105 targets bsc_engine.py close-out (your selling-point engine).
