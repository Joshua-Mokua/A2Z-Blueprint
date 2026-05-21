A2Z MIS 360 — v5.22 release notes
===================================

Verified score: 14/14 gates (100%) per scripts/audit.py
Adds: twelve more page migrations to utils.core_audit

G14 ADOPTION JUMPED FROM 4% TO 22%
----------------------------------
Before this release:  3/67 pages adopted ( 4%)
After  this release: 15/67 pages adopted (22%)

The shim pattern from v5.21 is now exercised by 15 diverse pages
covering treasury, IRRBB risk, trade finance, management accounts,
collateral, disciplinary, credit admin, cybersecurity, bancassurance,
EWS, deal room, PIP — plus the original three (legal, revenue
assurance, access helper).

PAGES MIGRATED THIS SESSION
---------------------------

11 pages had a single clean line to swap (audit_log only):

    pages/53_irrbb.py             pages/40_collateral.py
    pages/46_trade_finance.py     pages/60_disciplinary.py
    pages/52_mgmt_accounts.py     pages/23_credit_admin.py
    pages/50_cybersecurity.py     pages/49_bancassurance.py
    pages/39_ews.py               pages/57_deal_room.py
    pages/43_pip.py

For each, the change is one line:
    OLD:  from utils.core import audit_log
    NEW:  from utils.core_audit import audit_log

1 page had multi-symbol shimmed import + an unrelated core import:

    pages/25_treasury.py
      Line 13 (the audit cluster) → core_audit
      Line 15 (fmt_kpi_value)     → stays on utils.core
    Same shape as 26_legal.py from v5.21.

NO BEHAVIORAL CHANGES
---------------------
Every migrated import resolves to the SAME OBJECT in memory it did
before — the shim is a pure re-export. Verified via
tests/test_core_split.py's `is`-identity check (which now exercises
14 symbols × 1 shim = 14 identity assertions, all green).

If at any point a future contributor accidentally re-defines a symbol
inside core_audit.py instead of re-importing it, the test_core_split
suite fires before CI lets the change through.

WHAT WAS CHANGED
----------------
1. Twelve pages migrated (one-line change each, except 25_treasury
   which had the same split-import shape as 26_legal from v5.21).

2. tests/test_core_split.py — MIGRATED_PAGES list extended from 3 to
   15 entries. Each new entry triggers the three parametrised tests:
     - test_migrated_page_parses
     - test_migrated_page_uses_new_path
     - test_migrated_page_no_old_imports_for_shimmed_symbols

   That's 12 new pages × 3 tests = 36 new test cases (parametrised).

3. Master_Prompt_v3.md → v5.22:
     - core.py decomposition entry rewritten to reflect 22% adoption
     - footer bumped

VERIFICATION (sandbox-stubbed)
------------------------------
  All 12 newly migrated pages:    12/12 PASS
    - Each parses cleanly
    - Each uses `from utils.core_audit import` for shimmed symbols
    - None have leftover `from utils.core import` for shimmed symbols

  scripts/audit.py:               14/14 gates PASS
    G14: 1 shim(s), 15/67 pages adopted (22%) (15 fully, 0 partial)

WHAT THE FULL G14 TRAJECTORY LOOKS LIKE
---------------------------------------
  v5.21:   3/67 ( 4%)  ← shim pattern proved
  v5.22:  15/67 (22%)  ← THIS RELEASE — broad coverage
  v5.23: ~30/67 (45%)  ← next session: more 1-symbol pages
  v5.24:  ~50/67 (75%) ← physical code move from core.py to core_audit.py
                          becomes safe at this point

INSTALLATION
------------
1. Extract this zip over your project root (over the v5.21 working tree).
2. Run the audit:
     python scripts/audit.py
   Expected: 14/14 PASS, G14 reports 15/67 (22%)
3. Run the test suite:
     pytest -v tests/test_core_split.py
   Expected: all parametrised cases pass — should be 75 total
   when combined with the rest of the suite.
4. Hit each migrated page in the running app to confirm imports
   resolve at runtime. The pages exercise diverse modules so this
   gives broad confidence in the shim pattern.

REMAINING PENDING PAGES (52 of 67)
-----------------------------------
The next batch of easy migrations: pages that import only `audit_log`
from utils.core. Examples from the audit's pending list:

    pages/54_rcsa.py             pages/65_contracts.py
    pages/64_vendors.py          pages/37_approvals.py
    pages/59_cab.py              pages/55_aml.py
    pages/80_merchant.py         pages/70_retailer_finance.py
    pages/11_competitor.py       pages/84_board.py
    pages/_admin_reconciliation.py
    pages/83_strategy.py         pages/44_incidents.py

Each is a one-line edit. 12-15 of these in the next session pushes
G14 to 40-45%.

WHAT'S NEXT
-----------
Three options ordered by ROI:

a) **Continue migrations** — do another 12-15 pages, push G14 to ~45%.
   Same recipe as this session. Low risk, visible progress.

b) **Add the next shim — utils/core_kpi.py** for KPI library helpers
   (~10-15 symbols: get_kpi_library, save_kpi_library, get_active_kpis,
   get_role_kpis, bsc_score_from_pct, is_pct, is_count_kpi, etc.).
   Add to G14's SHIMS dict and to test_core_split.py's SHIMS dict.
   This expands what can be migrated.

c) **Physically move audit-cluster code** from utils.core into
   utils/core_audit.py. With 22% adoption + 14-symbol identity tests,
   this is now genuinely safer than before — but I'd wait until 50%+
   adoption to maximise safety.

My pick is (a) again. Get to ~45% adoption, then either do (c) or
move on to (b) — that decision is easier to make from the higher
adoption baseline.

COMMIT
------
git add pages/25_treasury.py pages/53_irrbb.py pages/46_trade_finance.py pages/52_mgmt_accounts.py pages/40_collateral.py pages/60_disciplinary.py pages/23_credit_admin.py pages/50_cybersecurity.py pages/49_bancassurance.py pages/39_ews.py pages/57_deal_room.py pages/43_pip.py tests/test_core_split.py Master_Prompt_v3.md
git commit -m "v5.22: twelve more page migrations to utils.core_audit (G14: 4% -> 22%)"
git tag v5.22
git push origin main --tags
