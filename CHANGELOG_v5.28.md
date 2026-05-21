A2Z MIS 360 — v5.28 release notes
===================================

THE NEXT CLUSTER STARTS HERE
============================
Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: utils/core_kpi.py shim, 3 pilot page migrations, test
      infrastructure for multi-shim era

A SECOND CLUSTER ENTERS THE ARENA
---------------------------------
v5.21-v5.27 closed out the audit cluster: 14 functions extracted
from utils/core.py and physically homed in utils/core_audit.py,
with the legacy path locked off. core.py shrunk by 328 lines.

v5.28 starts the same arc on the KPI library cluster — 12 symbols
covering KPI configuration and BSC scoring:

    KPI library config:
        KPI_LIBRARY_FILE       (constant — Path)
        DEFAULT_KPI_LIBRARY    (constant — dict, ~45L)
        DEFAULT_ROLE_KPIS      (constant — dict, ~17L)
        get_kpi_library()      (~16L)
        save_kpi_library(lib)  (~5L)
        get_active_kpis()      (~10L)
        get_role_kpis(role)    (~4L)
        get_pillar_weights()   (~9L)

    BSC scoring:
        get_scoring_scale()        (~6L)
        bsc_score_from_pct(pct)    (~22L)
        get_performance_bands()    (~6L)
        score_to_band(score)       (~13L)

Total: ~140 LOC if eventually physically moved (less than half
the audit cluster's 327 LOC).

WHY THIS CLUSTER WILL BE A FASTER ARC
-------------------------------------
Discovery scan found:
  - Only 3 pages import any KPI cluster symbol
    (1_perform.py, 12_cascade.py, 7_admin.py — all big
     infrastructural pages)
  - 1 non-pages file (utils/actuals_engine.py — has a mixed
    import that combines get_kpi_library + get_org_config)
  - 0 cross-cluster dependencies (KPI symbols don't reference
    anything from the audit cluster)

For the eventual physical move (v5.32 or wherever), core_kpi.py
will need to import back exactly ONE name from core.py:
get_org_config. Compare to core_audit's 8 constant imports.

Cleaner deps + smaller call surface = 2-3 session arc instead
of the audit cluster's 6-session arc.

PILOT MIGRATIONS THIS SESSION
-----------------------------
The 3 pages that import KPI cluster symbols, all migrated:

  pages/1_perform.py — 3 inline imports:
    L304: from utils.core import score_to_band as _s2b
       →  from utils.core_kpi import score_to_band as _s2b
    L442: from utils.core import get_kpi_library, DEFAULT_ROLE_KPIS, DEFAULT_KPI_LIBRARY
       →  from utils.core_kpi import get_kpi_library, DEFAULT_ROLE_KPIS, DEFAULT_KPI_LIBRARY
    L694: from utils.core import bsc_score_from_pct as _bsc_score_fn
       →  from utils.core_kpi import bsc_score_from_pct as _bsc_score_fn

  pages/12_cascade.py — 1 single-line import:
    L744: from utils.core import get_kpi_library, save_kpi_library
       →  from utils.core_kpi import get_kpi_library, save_kpi_library

  pages/7_admin.py — 3 imports (2 inline single-line + 1 mixed parenthesised):
    L392: from utils.core import get_kpi_library, save_kpi_library
       →  from utils.core_kpi import get_kpi_library, save_kpi_library
    L436: from utils.core import get_kpi_library, save_kpi_library
       →  from utils.core_kpi import get_kpi_library, save_kpi_library
    L1865: parenthesised mixed:
       OLD: from utils.core import (get_kpi_library, save_kpi_library,
                                     DEFAULT_KPI_LIBRARY, DEFAULT_ROLE_KPIS,
                                     CBS_SOURCE_LABELS, get_active_kpis)
       NEW: from utils.core_kpi import (get_kpi_library, save_kpi_library,
                                         DEFAULT_KPI_LIBRARY, DEFAULT_ROLE_KPIS,
                                         get_active_kpis)
            from utils.core import CBS_SOURCE_LABELS

NEW TEST INFRASTRUCTURE
-----------------------
The introduction of a second shim required test scoping changes.
Pre-v5.28, the test suite assumed there was one shim and it had
ALWAYS completed the physical move. With KPI cluster still in the
shim phase, that assumption breaks.

Added to tests/test_core_split.py:

  PHYSICALLY_MOVED = {"utils.core_audit"}
    Subset of SHIMS whose implementations have been extracted from
    utils/core.py. Currently just core_audit. When core_kpi
    completes its physical move (v5.32+), it joins the set.

Two tests scoped to PHYSICALLY_MOVED only:

  test_implementations_live_in_core_audit:
    Asserts fn.__module__ == shim_modpath. Only true post-move.
    During shim phase, fn.__module__ reports 'utils.core' (correct).
    Now skips clusters not in PHYSICALLY_MOVED.

    Also fixed a latent bug: was using `ca = utils.core_audit` for
    every iteration regardless of which shim was being checked.
    Refactored to use importlib.import_module(shim_modpath).

    Also added: skip non-callable constants (paths, dicts) — only
    functions/classes have a meaningful __module__.

  test_no_legacy_imports_outside_core_audit:
    Static lint forbidding `from utils.core import X` for X in any
    fully-closed cluster. KPI cluster is mid-migration; legacy
    imports of KPI symbols still resolve correctly via the shim
    re-exporting from core, so they're permitted. Once KPI cluster
    graduates, those imports become forbidden.

DECISIONS DOCUMENTED
--------------------
1. Shim does NOT include the formatters (fmt_kpi_value, fmt_pct,
   fmt_score, COUNT_KPIS_CORE, is_count_kpi_core). Those belong
   to a future utils/core_format cluster — different concern,
   different test surface.

2. Shim does NOT include process_kpi_data, compute_initiative_kpis,
   build_staff_scores, get_bsc_summary_cached, etc. Those are
   heavy data pipelines, not configuration helpers. Different
   cluster (likely utils/core_bsc_pipeline if we get to it).

3. Shim does NOT include is_bsc_locked / lock_bsc / unlock_bsc.
   That's BSC engine state — already partly served by
   utils/bsc_engine.py from v5.18.

4. Latent bug noted but NOT fixed: get_scoring_scale and
   get_performance_bands are defined TWICE in utils/core.py
   (L1584+L1758, L1614+L1751). The later definition shadows
   the earlier. Both pairs have functionally equivalent bodies.
   Leaving them in place — fixing them changes behaviour
   (technically) which is a separate commit. Will be cleaned
   up at physical-move time.

VERIFICATION (sandbox-stubbed)
------------------------------
  All three modules import cleanly:                3/3 PASS
  v5.27 closure invariants intact:                10/10 PASS
    - audit-cluster names GONE from utils.core
    - audit-cluster .__module__ == utils.core_audit
  KPI shim: identity preserved across paths:     12/12 PASS
  KPI shim: __module__ == utils.core (pre-move):  9/9 PASS
  Pilot pages parse + use new path:                6/6 PASS
  Real call: get_kpi_library() returns dict:       1/1 PASS
  Real call: bsc_score_from_pct(95.0) numeric:     1/1 PASS

  Total: 42/42 PASS

  scripts/audit.py: 14/14 gates PASS
    G14: 2 shim(s), 68/68 pages adopted (100%) (68 fully, 0 partial)

INSTALLATION
------------
1. Extract this zip over your v5.27 working tree.
2. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 reports 2 shim(s), 68/68 (100%).
3. Run pytest:
     pytest -v
   Expected: 79 tests pass.
4. Smoke-test the running app:
     - Visit performance page (1_perform): exercises score_to_band,
       get_kpi_library, DEFAULT_*, bsc_score_from_pct via core_kpi
     - Visit cascade page (12_cascade): exercises get_kpi_library +
       save_kpi_library via core_kpi
     - Visit admin page (7_admin) → KPI Library tab: exercises the
       parenthesised import case

WHAT'S NEXT
-----------
The shim is in. Three options for v5.29:

a) **Migrate the one remaining caller — utils/actuals_engine.py.**
   Mixed import: get_kpi_library (shimmed) + get_org_config (kept).
   Same split-import pattern as v5.27 stragglers. Tiny session.
   After this, every named caller of KPI symbols uses the shim.

b) **Physical code move NOW.** With only 3 pages + 1 utils file
   on the new path, plus identity-equality tests holding, we
   could move the implementations into core_kpi.py immediately.
   Skip the multi-session migration arc since the call surface
   is so small. Same pattern as v5.25 — extract source, write
   header with constant imports, install reverse-export
   __getattr__ in core.py.

   Risk: if there are any hidden callers I missed (wildcard imports
   from `from utils.core import *` in the 3 pilot pages plus
   actuals_engine; any inline imports I missed), they'd suddenly
   start crashing. v5.27 found 13 stragglers G14 wasn't tracking.
   The same risk surface is here.

c) **Migrate utils/actuals_engine.py FIRST, then physical move next
   session.** The conservative option. Lock in 100% named-caller
   adoption, then move. This is what v5.21 → v5.25 did for the
   audit cluster — and it caught the stragglers before they
   became production crashes.

My pick: (c). v5.27 taught us that G14 misses utils/, scripts/,
app.py, and exotic import shapes. The only way to catch all of
them is to do a PRE-DELETION audit (the script we ran in v5.27).
But before the physical move, we want all the named callers
already on the new path so post-move debugging is simpler.

The actuals_engine migration in v5.29, then physical move + pre-
deletion audit + reverse-export deletion in v5.30 (since the
cluster is so small). That's a 2-session close instead of 6.

COMMIT
------
git add utils/core_kpi.py scripts/audit.py tests/test_core_split.py \
        pages/1_perform.py pages/12_cascade.py pages/7_admin.py \
        Master_Prompt_v3.md
git commit -m "v5.28: introduce utils.core_kpi shim + 3 pilot migrations"
git tag v5.28
git push origin main --tags
