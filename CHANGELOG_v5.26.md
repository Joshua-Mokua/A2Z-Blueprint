A2Z MIS 360 — v5.26 release notes
===================================

THE 100% ADOPTION RELEASE
=========================
Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: 25 page migrations — completes the audit cluster

G14 ADOPTION: 63% → 100%
------------------------
  Before v5.26:  42/67 pages adopted (63%)
  After  v5.26:  67/67 pages adopted (100%)

Six sessions in, the audit cluster is fully decomposed:

  v5.21:   3/67 ( 4%)  ← shim pattern proved
  v5.22:  15/67 (22%)  ← broad coverage across business modules
  v5.23:  28/67 (42%)  ← past 40%
  v5.24:  42/67 (63%)  ← past 50%, physical move now safe
  v5.25:  42/67 (63%)  ← physical move executed (core.py -290 lines)
  v5.26:  67/67 (100%) ← THIS RELEASE — every page migrated

PAGES MIGRATED THIS SESSION
---------------------------

17 CLEAN single-line swaps (audit_log only):

  pages/35_stress_testing.py     pages/_admin_postgres.py
  pages/74_cbk_returns.py        pages/62_p2p.py
  pages/_admin_etl.py            pages/67_fraud.py
  pages/31_edms.py               pages/_admin_cutover.py
  pages/77_capital.py            pages/68_clearing.py
  pages/86_flexcube.py           pages/_admin_module_config.py
  pages/_admin_org.py            pages/87_benchmarking.py
  pages/33_statement_analyzer.py pages/66_partnerships.py
  pages/20_debt_recovery.py

  Each:  from utils.core import audit_log
    →    from utils.core_audit import audit_log

7 SPLIT-IMPORTS (shimmed + non-shimmed on same line):

  pages/24_compliance.py
    OLD: from utils.core import ComplianceManager, audit_log
    NEW: from utils.core_audit import audit_log
         from utils.core import ComplianceManager

  pages/_admin_sprint.py
    OLD: from utils.core import audit_log, get_org_config, save_org_config
    NEW: from utils.core_audit import audit_log
         from utils.core import get_org_config, save_org_config

  pages/_login.py
    OLD: from utils.core import UserManager, audit_log
    NEW: from utils.core_audit import audit_log
         from utils.core import UserManager

  pages/22_credit_analysis.py
    OLD: from utils.core import LoanApplicationManager, audit_log
    NEW: from utils.core_audit import audit_log
         from utils.core import LoanApplicationManager

  pages/21_loan_applications.py
    OLD: from utils.core import LoanApplicationManager, audit_log,
                                  requires_dual_approval, submit_for_approval
    NEW: from utils.core_audit import audit_log, requires_dual_approval,
                                       submit_for_approval
         from utils.core import LoanApplicationManager

  pages/61_projects.py
    OLD: from utils.core import audit_log, get_org_config
    NEW: from utils.core_audit import audit_log
         from utils.core import get_org_config

  pages/0_home.py
    OLD: from utils.core import check_access, MODULE_ACCESS, get_visible_staff
    NEW: from utils.core_audit import check_access, get_visible_staff
         from utils.core import MODULE_ACCESS

1 BONUS — pages/_sidebar.py:

  Three forms in one file:
    1. Top-level parenthesised multi-line (audit_log + 7 non-shimmed)
    2. Inline at L227: `from utils.core import get_visible_staff as _gvs`
    3. Inline at L303: `from utils.core import get_visible_staff`

  All three migrated. The parenthesised form became a split-import
  with the parenthesised tail kept on utils.core; the two inline
  occurrences got a literal swap. Adding _sidebar.py was needed to
  push G14 from 99% to 100%.

NO BEHAVIOURAL CHANGES
----------------------
Every test still passes:

  - 80 test functions across 5 files
  - All `is`-identity assertions hold (functions are the SAME objects
    via either import path)
  - Both import orders still work cycle-safe (PEP 562 __getattr__)
  - Every shimmed symbol's __module__ still reports utils.core_audit
  - audit_log still writes to data/audit_trail.jsonl via both paths

WHAT WAS CHANGED
----------------
1. 25 pages migrated:
     - 17 one-line clean swaps
     - 7 split-imports (matching the v5.21 _access.py pattern)
     - 1 bonus (_sidebar.py with mixed multi-line + inline forms)

2. tests/test_core_split.py:
     - MIGRATED_PAGES extended from 42 to 67 entries
     - Adds 25 × 3 = 75 new parametrised test cases

3. Master_Prompt_v3.md → v5.26:
     - core.py decomposition entry: "(audit cluster) — COMPLETE"
     - footer bumped

VERIFICATION (sandbox-stubbed)
------------------------------
  All 25 newly migrated pages:    25/25 PASS
    - Each parses cleanly
    - Each uses `from utils.core_audit import` for shimmed symbols
    - None have leftover old-path imports for shimmed symbols

  Cycle safety + identity (post-v5.26):
    - Both import orders succeed
    - All 14 symbols preserve `is`-identity across paths
    - _sidebar.py (the trickiest) parses

  scripts/audit.py:               14/14 gates PASS
    G14: 1 shim(s), 67/67 pages adopted (100%) (67 fully, 0 partial)

WHAT'S NEXT
-----------
Now that adoption is 100%, the v5.25 backward-compat block in
utils/core.py becomes unused — no production page does
`from utils.core import audit_log` anymore. Three options:

a) **Delete the reverse-export __getattr__ block in core.py.**
   That ~12-line block at the bottom of core.py exists ONLY for
   backward compat with pages that haven't migrated. Now that none
   exist, it's dead weight. Drop it. core.py shrinks to ~6,371
   lines. Update test_core_split.py's TestPhysicalMoveV525 to
   either remove or relax the legacy-path tests, since the legacy
   path is being removed by design.

   This is the cleanest "the audit cluster is done, lock the door
   on the way out" move. Low-risk because we're just removing dead
   code with full test coverage.

b) **Start the next cluster — utils/core_kpi.py** for KPI library
   helpers (~10-15 symbols: get_kpi_library, save_kpi_library,
   get_active_kpis, get_role_kpis, bsc_score_from_pct, is_pct,
   is_count_kpi, score_to_band, get_pillar_weights, etc.). The
   v5.21→v5.26 playbook applies verbatim:
       step 1: introduce shim re-exporting from core
       step 2-N: migrate pages to the shim path
       step (50%+): physical code move
       step (100%): delete reverse-exports

c) **Test coverage expansion** — db.py SQL safety, the UserManager
   class, FLEXCUBE adapter, page-level smoke tests. Builds the
   safety margin for everything else.

My pick: (a). It's a 5-minute job that finalises the audit cluster
work, removes dead code, and leaves a cleaner baseline for whoever
picks up (b). The audit cluster started in v5.21 with a re-export
shim. Six sessions later, the shim is empty — let's delete it.

COMMIT
------
git add pages/35_stress_testing.py pages/74_cbk_returns.py \
        pages/_admin_etl.py pages/31_edms.py pages/77_capital.py \
        pages/_admin_postgres.py pages/62_p2p.py pages/67_fraud.py \
        pages/_admin_cutover.py pages/68_clearing.py pages/86_flexcube.py \
        pages/_admin_module_config.py pages/_admin_org.py \
        pages/87_benchmarking.py pages/33_statement_analyzer.py \
        pages/66_partnerships.py pages/20_debt_recovery.py \
        pages/24_compliance.py pages/_admin_sprint.py pages/_login.py \
        pages/22_credit_analysis.py pages/21_loan_applications.py \
        pages/61_projects.py pages/0_home.py pages/_sidebar.py \
        tests/test_core_split.py Master_Prompt_v3.md
git commit -m "v5.26: complete audit cluster migration — G14 reaches 100%"
git tag v5.26
git push origin main --tags
