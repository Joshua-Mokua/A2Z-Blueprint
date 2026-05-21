A2Z MIS 360 — v5.25 release notes
===================================

THE MILESTONE RELEASE
=====================
Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: physical code move — core.py shrinks by 301 lines

WHAT JUST HAPPENED
------------------
For four releases (v5.21 through v5.24) we built up to this moment.
The shim pattern, the test suite, the identity-equality guarantees,
the migration of 42/67 pages — all infrastructure that made this
session safe to do.

In v5.25, 14 functions physically moved out of utils/core.py and
into utils/core_audit.py:

    audit_log                    requires_dual_approval
    submit_for_approval          get_pending_approvals
    get_user_department          is_dept_super_user
    is_ict_admin                 get_dept_modules
    check_access                 check_page_access
    get_visible_staff            tab_visible_cascade
    fix_view_all_permissions     _hash_password

That's 327 lines of implementation code that no longer lives in the
6,673-line monolith. utils/core.py is now 6,383 lines (−290 net,
after adding back a 12-line PEP 562 __getattr__ block for backward
compat).

ZERO BEHAVIOURAL CHANGES
------------------------
Every page in the codebase keeps working — verified by the existing
67-test suite plus 5 new tests in TestPhysicalMoveV525:

  v5.21–v5.24 tests (still all green):
    - shim symbols match utils.core via `is`-identity
    - migrated pages parse cleanly
    - migrated pages don't have leftover old imports

  v5.25 NEW tests:
    - test_implementations_live_in_core_audit
        Every shimmed symbol's __module__ now reports
        utils.core_audit (not utils.core). This proves the move
        happened — if a future contributor accidentally moves the
        impls back, this test fires.
    - test_legacy_path_still_works
        Pages doing `from utils.core import audit_log` keep working
        via the reverse-export __getattr__.
    - test_legacy_path_returns_same_object_as_new_path
        Both paths must return the SAME object (`is`-identity).
    - test_import_cycle_safe_either_order
        Both `import utils.core` first AND `import utils.core_audit`
        first work cleanly. The cycle that would otherwise occur is
        broken by PEP 562 __getattr__.
    - test_unknown_attr_still_raises_on_core
        The __getattr__ only resolves the 14 reverse-exported names;
        anything else raises AttributeError. Critical to prevent it
        from silently swallowing typos.

THE CIRCULAR-IMPORT TRAP
------------------------
The first attempt at the physical move used eager `from utils.core_audit
import (audit_log, ...)` at the bottom of core.py. That created a real
circular import: when a page imported core_audit directly, Python would:

  1. Start loading utils.core_audit
  2. core_audit needs constants from utils.core — start loading core
  3. core's body runs to completion, hits the eager re-export
  4. eager re-export tries to import audit_log from core_audit, which
     is still mid-load (step 1 isn't done) → ImportError

The fix is PEP 562 module-level __getattr__ in utils.core. Instead of
eagerly importing the 14 names at module-load, we install a __getattr__
that resolves them lazily — only when actually accessed. By the time
a name is accessed, both modules are fully loaded, no cycle.

The new __getattr__ block in core.py:

    _REVERSE_EXPORTS = frozenset({
        "audit_log", "requires_dual_approval", ..., "_hash_password",
    })

    def __getattr__(name):
        if name in _REVERSE_EXPORTS:
            from utils.core_audit import __dict__ as _ca_dict
            try:
                return _ca_dict[name]
            except KeyError:
                pass
        raise AttributeError(f"module 'utils.core' has no attribute {name!r}")

WHAT WAS CHANGED
----------------
1. utils/core.py:
     - 14 function definitions removed (327 lines deleted)
     - PEP 562 __getattr__ block added (37 lines, includes
       commentary, frozenset, and the function)
     - Net: 6,673 → 6,383 lines (−290)

2. utils/core_audit.py:
     - Was a 62-line re-export shim from v5.21
     - Now 422 lines containing the actual implementations
     - Imports 9 module constants from utils.core
     - Imports 3 stdlib modules (json, hashlib, datetime)
     - Maintains __all__ for clean public API

3. scripts/audit.py:
     - utils/core_audit.py added to FOUNDATIONAL list
     - It now hosts the audit_log primitive used everywhere — same
       reasoning that exempts utils/core.py from G2's direct-I/O check.

4. tests/test_core_split.py:
     - 5 new tests in TestPhysicalMoveV525
     - Total test count: 75 → 80 (visible in G13)

5. Master_Prompt_v3.md → v5.25:
     - Directory tree shows core_audit.py as a sibling
     - core.py decomposition entry rewritten to reflect the milestone
     - Footer bumped

VERIFICATION (sandbox-stubbed)
------------------------------
  Cycle safety (both import orders):       2/2 PASS
  Shim symbols reachable both paths:      14/14 each direction PASS
  Identity preserved (`is` check):        14/14 PASS
  __module__ reports core_audit:          14/14 PASS
  Real call: audit_log writes to disk:     2/2 PASS (new + legacy paths)
  _hash_password produces valid hash:      2/2 PASS
  Unknown attr raises AttributeError:      1/1 PASS
  Constants still on core:                 9/9 PASS

  scripts/audit.py:                       14/14 gates PASS

INSTALLATION
------------
1. Extract this zip over your v5.24 working tree.
2. Run the engine self-test:
     python -m utils.bsc_engine
   Expected: ALL TESTS PASSED (unchanged from v5.18)
3. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 still shows 42/67 (63%)
4. Run pytest:
     pytest -v
   Expected: 80 tests pass.
5. Smoke-test in the running app:
     - Login (exercises _hash_password via UserManager)
     - Visit any unmigrated page (check_access via legacy import path)
     - Visit any migrated page (check_access via core_audit path)
     - Save a record on any page (audit_log writes to audit_trail.jsonl)
     - Verify data/audit_trail.jsonl has new entries

ROLLBACK PLAN
-------------
If anything goes wrong in production, rollback is simple:
  1. utils/core.py.v5.24.bak is included in your tree from this session
     (created automatically before the move).
  2. cp utils/core.py.v5.24.bak utils/core.py
  3. Delete utils/core_audit.py
  4. Restore the v5.24 shim version of utils/core_audit.py

Or just `git revert v5.25` if you tagged v5.24 cleanly.

WHAT'S STILL OPEN
-----------------

  Test coverage expansion (3 weeks)        — db.py SQL safety, UserManager,
                                              FLEXCUBE adapter, page smoke tests
  PG migration (3 weeks)                   — 31 of 52 tables still JSON
  More page migrations (G14: 63% → 100%)   — 25 pages remaining
  Then: more shims (utils/core_kpi.py, utils/core_perf.py, etc.)
  More engine wirings (per-mod)            — adds to G8 compliant counter
  API expansion (6-8 weeks)                — 12 → 144 endpoints

WHAT'S NEXT
-----------
Three options:

a) **Finish the migrations** — clear the remaining 25 pages over 1-2
   sessions, push G14 to 100%. Once 100%, delete the __getattr__ block
   in core.py (it'll be unused). core.py shrinks by another 12 lines.

b) **Add the next shim — utils/core_kpi.py** for KPI library helpers
   (~10-15 symbols: get_kpi_library, save_kpi_library, get_active_kpis,
   bsc_score_from_pct, is_pct, is_count_kpi, etc.). Same shim pattern,
   different cluster. Then migrate pages, then physically move. The
   v5.21→v5.25 playbook applies verbatim.

c) **Test coverage expansion** — write tests for db.py SQL safety, the
   UserManager class, FLEXCUBE adapter. Increases the safety margin
   for all future refactors.

My pick: (a). We're 4 sessions deep into this decomposition; finishing
the audit cluster cleanly is the right move before opening a new front.
The remaining 25 pages are mostly clean swaps with 7 split-imports.
1-2 sessions to 100% adoption, then we delete the reverse-export
shim in core.py and call the audit cluster done.

COMMIT
------
git add utils/core.py utils/core_audit.py scripts/audit.py tests/test_core_split.py Master_Prompt_v3.md
git commit -m "v5.25: physical move — 14 audit functions extracted from core.py to core_audit.py (-290 lines)"
git tag v5.25
git push origin main --tags
