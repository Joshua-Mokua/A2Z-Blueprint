A2Z MIS 360 — v5.23 release notes
===================================

Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: thirteen more page migrations to utils.core_audit

G14 ADOPTION JUMPED FROM 22% TO 42%
-----------------------------------
Before this release: 15/67 pages adopted (22%)
After  this release: 28/67 pages adopted (42%)

Same recipe as v5.22 — clean single-line `audit_log` swaps. The shim
pattern is now exercised across 28 pages spanning ~25 distinct
functional areas (audit, risk, AML, vendors, contracts, approvals,
merchants, retail finance, competitor analysis, board reporting,
reconciliation, strategy, and more from v5.21/v5.22).

PAGES MIGRATED THIS SESSION
---------------------------
All 13 had a single clean line to swap:

    pages/44_incidents.py            pages/54_rcsa.py
    pages/64_vendors.py              pages/59_cab.py
    pages/65_contracts.py            pages/37_approvals.py
    pages/55_aml.py                  pages/80_merchant.py
    pages/70_retailer_finance.py     pages/11_competitor.py
    pages/84_board.py                pages/_admin_reconciliation.py
    pages/83_strategy.py

For each:
    OLD:  from utils.core import audit_log
    NEW:  from utils.core_audit import audit_log

NO BEHAVIORAL CHANGES
---------------------
Every migrated import resolves to the SAME OBJECT in memory it did
before — verified by tests/test_core_split.py's `is`-identity check.
Run `pytest -v tests/test_core_split.py` to confirm. The page-level
test suite now exercises 28 migrations × 3 checks = 84 parametrised
cases (all green).

WHAT WAS CHANGED
----------------
1. Thirteen pages migrated (one-line change each).
2. tests/test_core_split.py — MIGRATED_PAGES list extended from 15
   to 28 entries.
3. Master_Prompt_v3.md → v5.23 (gates table unchanged at 14, just
   the adoption metric in the closed-gaps section).

VERIFICATION (sandbox-stubbed)
------------------------------
  All 13 newly migrated pages:    13/13 PASS
    - Each parses cleanly
    - Each uses `from utils.core_audit import` for shimmed symbols
    - None have leftover old-path imports for shimmed symbols

  scripts/audit.py:               14/14 gates PASS
    G14: 1 shim(s), 28/67 pages adopted (42%) (28 fully, 0 partial)

G14 TRAJECTORY
--------------
  v5.21:   3/67 ( 4%)  ← shim pattern proved
  v5.22:  15/67 (22%)  ← broad coverage
  v5.23:  28/67 (42%)  ← THIS RELEASE — past 40% milestone
  v5.24: ~42/67 (62%)  ← next batch of clean swaps
  v5.25: ~50/67 (75%)  ← physical code move from utils.core
                          → utils/core_audit.py becomes safe
                          (audit-cluster code shrinks core.py by ~300L)

REMAINING PENDING PAGES (39 of 67)
----------------------------------
The next clean batch (more single-line audit_log swaps):

    pages/69_consent.py            pages/82_oprisk.py
    pages/71_bid_bond.py           pages/79_cards.py
    pages/85_esg.py                pages/63_assets.py
    pages/81_alm.py                pages/72_observability.py
    pages/78_onboarding.py         pages/75_data_protection.py
    pages/76_sanctions.py          pages/73_channels.py
    plus ~25 more

Each is one-line. Doing 12-14 of these in the next session pushes
G14 to ~60-65%.

INSTALLATION
------------
1. Extract this zip over your project root (over the v5.22 working tree).
2. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 reports 28/67 (42%)
3. Run the test suite:
     pytest -v tests/test_core_split.py
   Expected: parametrised cases all pass.
4. Hit each migrated page in the running app to confirm runtime imports.

WHAT'S NEXT
-----------
Three options:

a) Continue migrations — 12-14 more pages, push G14 to ~60-65%.
   Same recipe. Low risk, visible progress.

b) Add the next shim — utils/core_kpi.py for KPI library helpers.
   Expands what's migratable. Different cluster, different test
   surface.

c) Physically move audit-cluster code from utils.core into
   utils/core_audit.py. With 42% adoption + 75-test suite, this is
   genuinely safer than at 22%, but I'd still wait for ~50% to
   minimise risk.

My pick: (a) again. Get to ~65% before the physical move. Each
additional migration further reduces the risk surface of the
eventual code relocation.

COMMIT
------
git add pages/44_incidents.py pages/54_rcsa.py pages/64_vendors.py pages/59_cab.py pages/65_contracts.py pages/37_approvals.py pages/55_aml.py pages/80_merchant.py pages/70_retailer_finance.py pages/11_competitor.py pages/84_board.py pages/_admin_reconciliation.py pages/83_strategy.py tests/test_core_split.py Master_Prompt_v3.md
git commit -m "v5.23: thirteen more page migrations to utils.core_audit (G14: 22% -> 42%)"
git tag v5.23
git push origin main --tags
