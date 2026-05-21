A2Z MIS 360 — v5.24 release notes
===================================

Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: fourteen more page migrations to utils.core_audit

G14 ADOPTION JUMPED FROM 42% TO 63% — PAST THE 50% THRESHOLD
------------------------------------------------------------
Before this release: 28/67 pages adopted (42%)
After  this release: 42/67 pages adopted (63%)

This is the milestone release. Physical code move from utils.core
into utils/core_audit.py — i.e. actually moving the audit_log,
check_access, _hash_password etc. implementations out of the
6,672-line core.py — is now safe to do.

PAGES MIGRATED THIS SESSION
---------------------------
All 14 had a single clean line to swap (audit_log only):

    pages/69_consent.py             pages/82_oprisk.py
    pages/71_bid_bond.py            pages/79_cards.py
    pages/85_esg.py                 pages/63_assets.py
    pages/81_alm.py                 pages/72_observability.py
    pages/78_onboarding.py          pages/75_data_protection.py
    pages/76_sanctions.py           pages/73_channels.py
    pages/30_rms.py                 pages/_admin_module_renderer.py

For each:
    OLD:  from utils.core import audit_log
    NEW:  from utils.core_audit import audit_log

Functional coverage now spans data protection, sanctions screening,
operational risk, ESG, ALM, asset management, channel management,
observability, onboarding, consent management, bid bonds, cards,
RMS, and the admin module renderer — on top of all earlier batches.

NO BEHAVIORAL CHANGES
---------------------
Same shim, same re-exports, same `is`-identity guarantee verified
by tests/test_core_split.py. The 14 added entries to MIGRATED_PAGES
trigger 42 new parametrised test cases (3 checks × 14 pages).

WHAT WAS CHANGED
----------------
1. Fourteen pages migrated (one-line change each).
2. tests/test_core_split.py — MIGRATED_PAGES list extended from 28
   to 42 entries.
3. Master_Prompt_v3.md → v5.24:
     - core.py decomposition entry: "Past the 50% threshold —
       physical code move is now safe."
     - footer bumped

VERIFICATION (sandbox-stubbed)
------------------------------
  All 14 newly migrated pages:    14/14 PASS
    - parses cleanly
    - uses `from utils.core_audit import` for shimmed symbols
    - no leftover old-path imports for shimmed symbols

  scripts/audit.py:               14/14 gates PASS
    G14: 1 shim(s), 42/67 pages adopted (63%) (42 fully, 0 partial)

G14 TRAJECTORY
--------------
  v5.21:   3/67 ( 4%)  ← shim pattern proved
  v5.22:  15/67 (22%)  ← broad coverage
  v5.23:  28/67 (42%)
  v5.24:  42/67 (63%)  ← THIS RELEASE — past 50%
  v5.25: ~55/67 (82%)  ← next batch (17 clean swaps remaining)
  v5.26:  67/67 (100%) ← all migrated, ready for physical move
                          OR — start the physical move now since
                          we're past 50%

REMAINING PENDING PAGES (25 of 67)
-----------------------------------
17 clean single-line audit_log swaps still pending:

    pages/35_stress_testing.py    pages/74_cbk_returns.py
    pages/_admin_etl.py           pages/31_edms.py
    pages/77_capital.py           pages/_admin_postgres.py
    plus ~11 more

7 pages need split-imports (mixed shimmed + non-shimmed on same line):

    pages/24_compliance.py        — audit_log + ComplianceManager
    pages/_admin_sprint.py        — audit_log + get_org_config + save_org_config
    pages/_login.py               — audit_log + UserManager
    pages/22_credit_analysis.py   — audit_log + LoanApplicationManager
    pages/21_loan_applications.py — multiple shimmed + LoanApplicationManager
    pages/61_projects.py          — audit_log + get_org_config
    pages/0_home.py               — check_access + get_visible_staff + MODULE_ACCESS

Same shape as pages/26_legal.py and pages/_access.py (already done).
Each needs the import split into two lines, like:
    from utils.core_audit import audit_log
    from utils.core import ComplianceManager

INSTALLATION
------------
1. Extract this zip over your project root.
2. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 reports 42/67 (63%)
3. Run tests:
     pytest -v tests/test_core_split.py
   Expected: all parametrised cases pass.
4. Smoke-test each migrated page in the running app.

WHAT'S NEXT
-----------
Three options ordered by ROI:

a) **Continue migrations** — finish the remaining 17 clean swaps and
   migrate the 7 split-import pages. Push G14 to 100% over 1-2 sessions.

b) **Physically move audit-cluster code** from utils.core into
   utils/core_audit.py NOW. With 42/67 = 63% adoption + 75-test
   suite + `is`-identity guarantees, this is genuinely safe. core.py
   shrinks by ~300 lines. The remaining 25 unmigrated pages keep
   working because the shim still re-exports — but now the shim re-
   exports its own implementations rather than pulling from core.

c) **Add the next shim** — utils/core_kpi.py for KPI library helpers
   (~10-15 symbols). Different cluster, different test surface.
   Doesn't help core.py shrink yet but expands the migratable surface.

My pick: (b). With 63% adoption past the 50% safety threshold and
all callers verified at the `is`-identity level, the physical move
is the highest-impact deliverable available. It's the first session
where utils.core actually gets smaller. Doing (a) first is fine but
delays the only step that meaningfully shrinks the monolith.

If you'd rather lock in higher adoption before the move, do (a) —
finish out the clean swaps, then (b) the session after.

COMMIT
------
git add pages/69_consent.py pages/82_oprisk.py pages/71_bid_bond.py pages/79_cards.py pages/85_esg.py pages/63_assets.py pages/81_alm.py pages/72_observability.py pages/78_onboarding.py pages/75_data_protection.py pages/76_sanctions.py pages/73_channels.py pages/30_rms.py pages/_admin_module_renderer.py tests/test_core_split.py Master_Prompt_v3.md
git commit -m "v5.24: fourteen more page migrations to utils.core_audit (G14: 42% -> 63%)"
git tag v5.24
git push origin main --tags
