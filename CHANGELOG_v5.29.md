A2Z MIS 360 — v5.29 release notes
===================================

CONSERVATIVE TWO-SESSION CLOSE — STEP 1 of 2
============================================
Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: actuals_engine.py migration + pre-physical-move stragglers audit

THE GOAL OF THIS SESSION
------------------------
v5.28 introduced the core_kpi shim and migrated 3 pilot pages. After
that, the KPI cluster had three places that still used the legacy
`from utils.core import` path:
  - utils/actuals_engine.py (mixed import)
  - 16 pages with `from utils.core import *` (wildcard)
  - All other named imports already moved to core_kpi

In v5.27 we learned the hard way that G14 misses imports outside
pages/. So before doing the physical move (v5.30), we want every
named caller on the new path. This session does that:

  ✅ utils/actuals_engine.py migrated
  ✅ Wildcard pages audited — confirmed they don't depend on the
     wildcard for KPI symbols
  ✅ Per-scope AST analysis confirmed every KPI reference has an
     in-scope explicit core_kpi import

The cluster is now ready for the physical move.

WHAT WAS CHANGED
----------------
1. utils/actuals_engine.py:L254 — split mixed import:
     OLD: from utils.core import get_kpi_library, get_org_config
     NEW: from utils.core_kpi import get_kpi_library
          from utils.core import get_org_config

   Same shape as v5.27 stragglers (e.g. pages/28_ra.py).

2. Master_Prompt_v3.md → v5.29:
   - KPI cluster entry: "100% named adoption"
   - Confirms wildcard non-dependency
   - Ready-for-move note

That's it. This is a small, surgical session whose value is the
audit work, not the code change.

THE PRE-PHYSICAL-MOVE AUDIT (THE WORK)
--------------------------------------

Step 1: textual + AST scan of all .py files for KPI symbol
references via the legacy `from utils.core import` path.

  Results (post-actuals_engine fix):
    - 0 single-line imports
    - 0 parenthesised imports
    - 0 bare attribute access (utils.core.<KPI_symbol>)
    - 16 wildcard `from utils.core import *` (pages only)

Step 2: For the 16 wildcard pages, determine if each one actually
uses any KPI symbol (i.e. depends on the wildcard pulling them in).

  Results:
    13 pages use NO KPI symbols at all — wildcard provides nothing
        critical for them re: KPI cluster
        (pages 13_sla, 14_branch_log, 15_optimize, 16_commission,
         17_campaigns, 18_cims, 2_people, 3_pipeline, 4_execute,
         5_products, 8_export, 9_sbu, _shared)
     3 pages DO use KPI symbols, but each one already has explicit
        `from utils.core_kpi import X` lines added in v5.28
        (1_perform, 12_cascade, 7_admin)

Step 3: Per-scope AST coverage check. For the 3 pages using KPI
symbols, verify every reference has an in-scope EXPLICIT import
(NOT counting the wildcard, since after the physical move +
PEP 562 reverse-export, `from utils.core import *` will NOT
re-export the moved symbols).

  Results:
     1_perform.py:    3 unique refs, all covered ✅
    12_cascade.py:    2 unique refs, all covered ✅
     7_admin.py:     18 unique refs, all covered ✅

  Total: 23 references, 23 covered.

CONCLUSION: The physical move in v5.30 will not break any caller.
Every legitimate use of a KPI symbol has an in-scope binding via
`from utils.core_kpi import X`, independent of the wildcard.

WHY THE WILDCARD STILL MATTERS (BUT NOT FOR THIS CLUSTER)
---------------------------------------------------------
PEP 562 module-level __getattr__ (which we use in core.py for
backward compat after the v5.25 audit-cluster move) is invoked
ONLY on explicit attribute access. It does NOT participate in
`from X import *`.

So after the v5.30 move:
  ✅ `from utils.core import get_kpi_library` works (via __getattr__)
  ✅ `utils.core.get_kpi_library` access works (via __getattr__)
  ❌ `from utils.core import *; get_kpi_library` does NOT find it
     (because `*` doesn't trigger __getattr__)

This means: any future cluster where wildcard pages DO depend on
the wildcard for cluster symbols would need explicit imports added
BEFORE the physical move. We got lucky here — the 3 pages using
KPI symbols all have explicit imports.

Documenting this for future sessions: when adding the next cluster
shim, run the same pre-move audit and add explicit imports to any
wildcard-dependent page before doing the physical move.

VERIFICATION
------------
  utils.actuals_engine still imports cleanly:        1/1 PASS
  AST: actuals_engine imports get_kpi_library
       from core_kpi:                                 1/1 PASS
  AST: actuals_engine imports get_org_config
       from core (split):                             1/1 PASS
  v5.27 invariants intact (audit cluster GONE):      6/6 PASS
  v5.28 invariants intact (KPI shim identity):     12/12 PASS
  Static check: no remaining named legacy imports
       of KPI symbols anywhere:                       1/1 PASS

  Total: 22/22 PASS

  scripts/audit.py: 14/14 gates PASS
    G14: 2 shim(s), 68/68 pages adopted (100%) (68 fully, 0 partial)

INSTALLATION
------------
1. Extract this zip over your v5.28 working tree.
   (Only 2 files changed: utils/actuals_engine.py + Master_Prompt_v3.md)
2. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 still reports 2 shim(s), 68/68 (100%).
3. Run pytest:
     pytest -v
   Expected: 79 tests pass.
4. Smoke-test in app:
     - The CBS actuals refresh path triggers
       utils.actuals_engine — anything reading from CBS data still
       works. (No change to behaviour, just import path.)

WHAT'S NEXT — v5.30: THE PHYSICAL MOVE
--------------------------------------
The cluster is ready. v5.30 will:

  1. Extract the 12 symbol implementations from utils/core.py:
       Constants:  KPI_LIBRARY_FILE, DEFAULT_KPI_LIBRARY,
                   DEFAULT_ROLE_KPIS  (~63L total)
       Library helpers: get_kpi_library, save_kpi_library,
                   get_active_kpis, get_role_kpis,
                   get_pillar_weights  (~44L)
       Scoring:    bsc_score_from_pct, score_to_band,
                   get_performance_bands, get_scoring_scale (~32L)
       Total: ~140 LOC moved out of core.py

  2. Replace core_kpi.py's re-export shim with the actual
     implementations + a small `from utils.core import get_org_config`
     line for the one constant dependency.

  3. Delete the 12 implementations + 2 latent duplicate definitions
     from core.py. Net change: ~-160 lines (we get to clean up the
     duplicates as part of the move since we're re-writing the area).

  4. Install PEP 562 __getattr__ block in core.py for backward
     compat with the wildcard-using pages. Use the cycle-safe
     pattern from v5.25.

  5. Add core_kpi to PHYSICALLY_MOVED set in test_core_split.py.

  6. Add core_kpi.py to FOUNDATIONAL list in scripts/audit.py
     (it'll do JSON file I/O via save_kpi_library).

  7. Run the full smoke-test battery + audit.

Estimated session impact:
  - core.py:     6,345 → ~6,185 lines  (~-160)
  - core_kpi.py:    71 →   ~220 lines

DECIDED: do v5.30 the same session as v5.31 (delete reverse-export +
migrate any newly-discovered stragglers + lock the cluster down)?
Or split them?

  Recommendation: SPLIT. v5.30 = move + reverse-export installed.
  v5.31 = run pre-deletion audit (the script we'll need to also
  add to the audit gate so we can spot stragglers automatically),
  delete reverse-export, lock cluster down.

  Same conservative two-step we used for v5.25 → v5.27.

COMMIT
------
git add utils/actuals_engine.py Master_Prompt_v3.md
git commit -m "v5.29: migrate utils/actuals_engine.py KPI imports + pre-move audit (KPI cluster ready for v5.30 physical move)"
git tag v5.29
git push origin main --tags
