A2Z MIS 360 — v5.27 release notes
===================================

THE AUDIT CLUSTER CLOSURE
=========================
Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: deletes the dead reverse-export block in core.py, migrates 13
      stragglers G14 wasn't tracking, locks the legacy path off
      with two new safety tests.

THE SIX-SESSION ARC IS DONE
---------------------------

  v5.21:  3/67 ( 4%)  ← shim pattern proved
  v5.22: 15/67 (22%)  ← broad coverage
  v5.23: 28/67 (42%)  ← past 40%
  v5.24: 42/67 (63%)  ← past 50%, physical move now safe
  v5.25: 42/67 (63%)  ← physical move executed (core.py -290 lines)
  v5.26: 67/67 (100%) ← all pages tracked by G14 migrated
  v5.27: ────         ← THIS RELEASE — reverse-export deleted,
                        13 stragglers fixed, legacy path locked off

Final state of utils/core.py:
    started:  6,673 lines
    after v5.25 (move): 6,383 lines
    after v5.26: 6,383 lines (no change)
    after v5.27 (delete reverse-export): 6,345 lines
    Net change: -328 lines

THE 13 STRAGGLERS G14 WASN'T TRACKING
-------------------------------------
G14 only audits files in pages/. It misses:
  - app.py (top-level Streamlit entry)
  - utils/*.py (backend modules)
  - scripts/*.py (CLI scripts)
  - tests/*.py (test files)
  - inline imports inside function bodies
  - parenthesised multi-line imports (matched in v5.21+ tooling but
    a few exotic patterns slipped through)

A pre-deletion audit found 13 references that would crash the moment
the reverse-export block was removed. Fixed before deleting:

  app.py:L18          parenthesised import — extracted audit_log
  app.py:L486         from utils.core import fix_view_all_permissions
  app.py:L637         from utils.core import check_access as _ca
  app.py:L751         from utils.core import check_access
  app.py:L797         parenthesised — 4 dept helpers extracted
  pages/19_credit_monitoring.py:L497  inline aliased audit_log
  pages/28_ra.py:L18   mixed: audit_log + update_bsc_from_modules
  pages/2_people.py:L317  inline aliased get_visible_staff
  pages/7_admin.py:L860   mixed: fix_view_all_permissions + _ALL_VIEW_ROLES
  scripts/preflight_flexcube.py:L221  inline audit_log
  utils/api.py:L102                   inline audit_log
  utils/bsc_engine.py:L359            inline audit_log
  tests/test_core_split.py:L212  intentional — was the
                                  test_legacy_path_still_works test;
                                  rewritten as test_legacy_path_is_gone

Each was migrated using the now-standard pattern:
    OLD:  from utils.core import audit_log
    NEW:  from utils.core_audit import audit_log

For mixed imports, split into two lines:
    OLD:  from utils.core import audit_log, update_bsc_from_modules as _ubm
    NEW:  from utils.core_audit import audit_log
          from utils.core import update_bsc_from_modules as _ubm

THE BLOCK THAT GOT DELETED
--------------------------
utils/core.py shed 38 lines of code-comment-block at the bottom:

  - The _REVERSE_EXPORTS frozenset (8 lines)
  - The PEP 562 __getattr__ function (10 lines)
  - 20 lines of context comments explaining v5.25's circular-import fix

That block existed ONLY to keep `from utils.core import audit_log` working
during v5.25-v5.26 while pages were still being migrated. With G14 at
100% and the 13 stragglers fixed, the block is dead weight.

TWO NEW SAFETY TESTS
--------------------

1. test_legacy_path_is_gone (runtime):
     Verifies that hasattr(utils.core, "audit_log") returns False —
     the legacy path no longer resolves. If a future contributor
     re-adds the reverse-export block, this test fires.

2. test_no_legacy_imports_outside_core_audit (static lint):
     Walks every .py file in the project. For each, regex-finds
     `from utils.core import X` for any shimmed X. Excludes
     core_audit.py itself, core.py, and tests/test_core_split.py
     (which references symbol names as strings in SHIMS dict).
     If anything is found, the test fails with a clear list of
     offenders.

   This is the static counterpart to the runtime check. Together
   they guarantee no legacy imports can slip through code review.

DELETED TESTS (REPLACED BY ABOVE)
---------------------------------
Three tests that depended on the reverse-export are gone:

1. test_symbol_is_same_object_as_core (TestShimReExports class)
     Was checking `core_audit.X is core.X` — meaningless after the
     legacy path is gone since core.X no longer exists.

2. test_legacy_path_still_works
     Inverted to test_legacy_path_is_gone (described above).

3. test_legacy_path_returns_same_object_as_new_path
     Inverted (the legacy path returns nothing now).

Test count: 80 → 79 functions across 5 files.
  - test_core_split.py: 12 → 11 functions
    (removed 3, added 2; visible parametrisation differs)

WHAT WAS CHANGED
----------------
1. utils/core.py:
     - Removed the entire 38-line reverse-export __getattr__ block
       at the bottom of the file
     - 6,383 → 6,345 lines

2. 8 source files migrated (app.py + 4 pages + 1 script + 2 utils):
     - app.py (5 imports total — 2 parenthesised, 3 single-line)
     - pages/19_credit_monitoring.py (1 inline aliased)
     - pages/28_ra.py (1 mixed split)
     - pages/2_people.py (1 inline aliased)
     - pages/7_admin.py (1 mixed split)
     - scripts/preflight_flexcube.py (1 inline)
     - utils/api.py (1 inline)
     - utils/bsc_engine.py (1 inline)

3. tests/test_core_split.py:
     - Removed test_symbol_is_same_object_as_core (and its 14
       parametrised cases against the legacy path)
     - Removed test_legacy_path_still_works
     - Removed test_legacy_path_returns_same_object_as_new_path
     - Added test_legacy_path_is_gone (runtime)
     - Added test_no_legacy_imports_outside_core_audit (static lint)
     - Updated test_unknown_attr_still_raises_on_core docstring
     - Updated TestPhysicalMoveV525 class docstring

4. Master_Prompt_v3.md → v5.27:
     - core.py decomposition entry: "(audit cluster) — CLOSED"
     - Notes both safety tests
     - Footer bumped

VERIFICATION (sandbox-stubbed)
------------------------------
  Both modules import cleanly:                    2/2 PASS
  Each shimmed symbol GONE from utils.core:      14/14 PASS
  Each shimmed symbol present on core_audit:     14/14 PASS
  Each .__module__ reports utils.core_audit:     14/14 PASS
  Legacy `from utils.core import audit_log`
    raises ImportError:                            1/1 PASS
  Unknown attr raises AttributeError:              1/1 PASS
  audit_log writes to disk via core_audit:         1/1 PASS
  No legacy imports in any project file:           1/1 PASS

  Total: 48/48 PASS

  scripts/audit.py: 14/14 gates PASS
    G14: 1 shim(s), 67/67 pages adopted (100%) (67 fully, 0 partial)

INSTALLATION
------------
1. Extract this zip over your v5.26 working tree.
2. Run the engine self-test:
     python -m utils.bsc_engine
   Expected: ALL TESTS PASSED.
3. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 shows 67/67 (100%).
4. Run pytest:
     pytest -v
   Expected: 79 tests pass.
5. Smoke-test the running app:
     - Login (exercises _hash_password via UserManager)
     - Visit any page (check_access via core_audit path)
     - Save a record (audit_log writes via core_audit)

ROLLBACK PLAN
-------------
If anything breaks, the v5.26 backup remains at
utils/core.py.v5.24.bak (created in v5.25). To revert v5.27 only:

  # Restore the reverse-export block:
  git revert v5.27

Or hand-edit:
  Append the 38-line reverse-export block back to utils/core.py
  Restore the 8 import statements in the migrated files
  Restore the 3 deleted tests in test_core_split.py

WHAT'S NEXT
-----------
The audit cluster is now fully decomposed. utils/core.py shrunk by
328 lines net (4.9% of the original file). The pattern is proven:

  shim → migrate → physical move → close out

Three options for the next session:

a) **Start the next cluster — utils/core_kpi.py** for KPI library
   helpers. Candidate symbols (~10-15):
       get_kpi_library, save_kpi_library, get_active_kpis,
       get_role_kpis, get_pillar_weights, bsc_score_from_pct,
       is_pct, is_count_kpi, is_avg_kpi, score_to_band,
       get_performance_bands, get_scoring_scale
   The v5.21→v5.27 playbook applies verbatim. Estimated 4-6 sessions
   to close out. core.py would shrink another ~400-500 lines.

b) **Test coverage expansion** — db.py SQL safety, the UserManager
   class, FLEXCUBE adapter, page-level smoke tests. Builds the
   safety margin for everything else, including the next cluster.

c) **Pause on decomposition; pick up something else** — PG migration
   (3 weeks, 31 of 52 tables still JSON), API expansion (12 → 144
   endpoints), more BSC engine wirings.

My pick: (a). The pattern is fresh, the tooling is fresh, the
adopted-vs-pending mental model is fresh. Starting the KPI cluster
now while everything is loaded saves cold-start cost in 2-3 weeks.

COMMIT
------
git add app.py pages/19_credit_monitoring.py pages/28_ra.py \
        pages/2_people.py pages/7_admin.py scripts/preflight_flexcube.py \
        utils/api.py utils/bsc_engine.py utils/core.py \
        tests/test_core_split.py Master_Prompt_v3.md
git commit -m "v5.27: close audit cluster — delete reverse-export, migrate 13 stragglers"
git tag v5.27
git push origin main --tags
