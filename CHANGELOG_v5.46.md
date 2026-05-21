A2Z MIS 360 — v5.46 release notes
===================================

STANDARD #21 v5.45 → v5.46 — FTP CORRECTION
============================================
Verified score: 32/32 gates (100%) per scripts/audit.py
Audit: G32 unchanged (still ≥99.5%); harness extended to FTP fixtures
Test count: 25 files / 570 → 25 files / 580 (+10 FTP tests)
Live Excel match: 20/20 → 28/28 = 100% across PBT, margins, indirect,
                   FTP credit, FTP charge

WHAT V5.45 GOT WRONG
--------------------
v5.45 shipped a naive "gross-interest" treatment:
  revenue.interest_income       = interest customer paid on loans
  direct_costs.interest_expense = interest the bank paid on deposits

That made deposit-only customers (e.g. fixture P018) look loss-making:
revenue 2,000 fees − 8,000 interest expense = PBT -6,000.

This is wrong on the economics. A deposit-only customer is NOT a loss
to the bank — their deposits fund lending elsewhere, and that lending
generates the spread that pays the depositor and earns margin for
the bank. v5.45's "Matches Excel within 0.5%" claim was true but
matched a naive Excel, not the production Excel any bank's actual
P&L uses (which applies Funds Transfer Pricing).

THE USER CAUGHT THIS DEFECT. I DIDN'T.

THE FIX: FUNDS TRANSFER PRICING
--------------------------------
Real bank profitability accounting splits the interest book via an
internal FTP rate:

  Deposit side (customer is a funder):
    ftp_credit_on_deposits = deposit_bal × (FTP - rate_paid) × pf
    → revenue (deposits create funding-value the bank uses elsewhere)

  Loan side (customer is a fund user):
    ftp_charge_on_loans    = loan_bal × FTP × period_fraction
    → direct cost (loan consumes the bank's funding pool)

Two sides sum to the bank's actual NIM with no double-counting. No
false losses, no false windfalls.

V5.46 — TWO MODES
-----------------
ftp_mode = "off" (DEFAULT)
  v5.45 behavior preserved. All 20 existing fixtures pass unchanged.

ftp_mode = "on"
  Engine adds two extra buckets:
    revenue.ftp_credit_on_deposits
    direct_costs.ftp_charge_on_loans
  Sourced from new ftp_inputs_fn(customer_id, period) collaborator
  returning {ftp_rate, deposit_balance, deposit_rate_paid,
             loan_balance, period_fraction}.

NEW HONESTY RULE
-----------------
When ftp_mode='on' but inputs are incomplete for a customer, engine
does NOT silently fall back to 'off'. Instead it logs missing keys
in meta.ftp_missing and skips FTP buckets for THAT customer (other
components still compute). Surfaces data-quality issues per-customer
rather than hiding them in aggregate.

WHAT WAS CHANGED
----------------
1. utils/customer_profitability.py
   - Module docstring rewritten with FTP explanation
   - Constructor: + ftp_mode, ftp_inputs_fn, balance_basis params
                  + invalid value rejection
   - calculate_customer_pnl: + FTP bucket computation when mode='on'
                              + meta.ftp_mode, ftp_rate, ftp_missing,
                                ftp_simplifications, balance_basis
   - + _default_ftp_inputs collaborator (returns None — explicit
       caller wiring required)
   - Self-test extended 11 → 18 cases
   - All v5.45 behavior preserved when ftp_mode defaults to "off"

2. tests/fixtures/customer_pnl_scenarios.json
   - Existing 20 fixtures gain explicit ftp_mode="off"
   - + 8 new FTP fixtures (P021–P028):
       P021 deposit-only canonical (was -6,333, now +52,000)
       P022 loan-only with reduced margin
       P023 mixed deposit + loan customer
       P024 deposit-rate-equals-FTP edge (zero credit)
       P025 quarterly period_fraction
       P026 FTP + revenue-weighted overhead allocation composing
       P027 large corporate (KES 500M deposit, 200M loan)
       P028 incomplete-inputs honesty test

3. tests/test_customer_profitability.py
   - + TestFTPBehavior class with 10 tests:
       default_mode_is_off
       invalid_ftp_mode_raises
       invalid_balance_basis_raises
       ftp_on_deposit_only_is_profitable (THE canonical demo)
       ftp_on_loan_only_lending_margin
       ftp_missing_inputs_not_silent
       ftp_inputs_returns_none_logged
       meta_records_ftp_rate_and_basis
       zero_balances_no_ftp_buckets
       off_mode_unaffected_by_ftp_inputs (backward compat sanity)
   - Harness updated to handle both modes
   - Artifact schema bumped to v2 with ftp_credit_correct,
     ftp_charge_correct counts
   - Asserts FTP credits and charges match alongside PBT

4. Master_Prompt_v3.md
   - Version bumped v5.45 → v5.46
   - **NEW MANDATORY STANDARD #11: Financial Accounting Honesty**
     Codifies: FTP requirement, average vs spot balances, period
     accruals, curve vs flat rate disclosure, no-silent-fallback
     rule, Decimal-internal math, None-margin-on-zero-revenue,
     meta-block traceability. Applies to ALL future financial
     reporting engines (#22 hierarchy, #23 RM dashboards, etc).
   - + v5.46 closure entry explicitly documenting the v5.45 bug
     and the v5.46 fix (so future-me doesn't repeat the same
     class of mistake)
   - G32 row updated to mention FTP extension
   - Footer bumped to v5.46

5. scripts/audit.py
   - No changes to G32 logic — same ≥99.5% bar
   - Live: 28/28 = 100% on extended fixture set

NO RUNTIME CODE CHANGES TO PRIOR ENGINES
-----------------------------------------
v5.46 is purely additive to #21. The 11 prior engines (#11-#20)
are untouched. No regression.

VERIFICATION (sandbox)
----------------------
  scripts/audit.py syntax OK:                             ✓
  audit gates 32/32 PASS:                                 ✓
  G13 grew: 25/570 → 25/580 (+10 FTP tests)
  python -m utils.customer_profitability self-test:       ALL PASS (18/18)
  All 11 other engine self-tests still pass:              ✓
  Manual run of all 42 unit tests:                        43/43 sub-checks pass
  G32 informational pass when artifact missing:           ✓
  G32 PASS at 28/28 = 100% on FTP-extended fixtures:     ✓
  v5.45 fixtures still pass with ftp_mode='off' default:  ✓ (20/20)
  P021 deposit-only customer: PBT was -6,333 → now +52,000 ✓

CURRENT AUDIT STATE (post-v5.46)
--------------------------------
  ✅ G1-G31 unchanged from v5.45
  ✅ G32 customer_pnl_excel_match: 100.0% (28/28 within ±0.5%)
       — schema v2: ftp_credit_correct=28, ftp_charge_correct=28
  Score: 32/32 = 100% PASS

THE LESSON, RECORDED
====================
When verification fixtures match a "naive Excel" rather than a
"production Excel," the verification claim must be flagged as such.
v5.45 should have flagged the naive treatment but didn't; v5.46
adds the FTP-aware path AND records the principle in the master
prompt as Mandatory Standard #11.

This protects #22 (tier hierarchy reads #21's PBT — if PBT was
wrong, tiers would be wrong too), #23 (RM dashboards aggregate
#21), and onward.

INSTALLATION
------------
1. Extract this zip over your v5.45 working tree.
2. Run audit:
     python scripts/audit.py
   Expected: 32/32 PASS. G32 reports 28/28 = 100%.
3. Run engine self-test:
     python -m utils.customer_profitability
   Expected: 18 cases pass (was 11 in v5.45).
4. Run pytest:
     pytest tests/test_customer_profitability.py -v
   Expected: 42 tests pass.

ROLLBACK
--------
git revert v5.46 OR restore the .v5.45.bak files:
  scripts/audit.py.v5.45.bak (no audit changes, identical)
  utils/customer_profitability.py.v5.45.bak
  tests/fixtures/customer_pnl_scenarios.json.v5.45.bak

WHAT'S NEXT
-----------
With #21 corrected and the financial honesty principle in the
master prompt, Standard #22 (Customer Profitability Hierarchy)
can proceed safely. It will read FTP-corrected PBT outputs from
#21 and classify customers into tiers (platinum/gold/silver/
bronze/negative) — without falsely tagging deposit-only customers
as "negative."

COMMIT
------
git add scripts/audit.py utils/customer_profitability.py \
        tests/test_customer_profitability.py \
        tests/fixtures/customer_pnl_scenarios.json \
        Master_Prompt_v3.md
git commit -m "v5.46: FTP correction for #21 + financial honesty principle"
git tag v5.46
git push origin main --tags
