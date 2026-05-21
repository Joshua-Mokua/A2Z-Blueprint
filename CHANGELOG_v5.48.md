A2Z MIS 360 — v5.48 release notes
===================================

STANDARD #23: RM Profitability Dashboard — CLOSED
==================================================
Verified score: 34/34 gates (100%) per scripts/audit.py
Audit gate added: G34 rm_aggregation_correct
Test count: 26 files / 625 → 27 files / 659 (+34 RM tests)
Live aggregation correctness: 10/10 = 100% on labeled fixtures

WHAT V5.48 SHIPS
-----------------

1. utils/rm_profitability.py (~470 LOC)
   - RMProfitabilityDashboard class with spec entry
     calculate_rm_portfolio_pnl(rm_code, period)
   - Spec-named methods: get_rm_customers, get_rm_rank
   - build_all_portfolios(period) helper for batch peer ranking
     (warned as O(N×M) — production needs caching)
   - All collaborators injectable
   - Decimal-internal aggregation at precision 28
   - Self-test: 14/14 cases pass

2. tests/fixtures/rm_portfolio_scenarios.json — 10 labeled fixtures
   - Clean 3-customer portfolio
   - Empty portfolio with warning
   - All-PnLs-missing scenario
   - 1-of-3 FTP-off (warning surfacing)
   - 2-of-3 FTP-off (provisional=True)
   - KES-billion-scale aggregation
   - Zero-revenue customer + customers_unclassified count
   - Single-customer portfolio
   - Genuinely loss-making FTP-aware portfolio
   - Exact 50% boundary not-provisional

3. tests/test_rm_profitability.py — 34 tests
   - Spec contract (4)
   - Aggregation math (6)
   - Peer ranking (5 incl. lex tie-break)
   - Honesty inheritance (6 — all 3 Std #11 mechanisms)
   - Defensive contract (6)
   - Decimal precision (1)
   - Determinism (1)
   - Persistence (2)
   - test_aggregation_correctness_meets_99_percent harness

4. scripts/audit.py — new gate G34 rm_aggregation_correct
   - ≥99% match rate enforced
   - Same artifact-handoff pattern as G18-G33
   - Verified across 4 cases: missing/90% fail/99% boundary/corrupt

5. Master_Prompt_v3.md
   - Version bumped v5.47 → v5.48
   - + v5.48 closure entry
   - + G34 row in gates table
   - + portfolio-level honesty inheritance section in
     Mandatory Standard #11 — codifying the pattern v5.48
     established for #24-#30

THE THREE STANDARD #11 INHERITANCE MECHANISMS
==============================================
v5.48 establishes the architectural pattern for ALL future portfolio-
level reporting in Volume Three:

1. meta.upstream_ftp_modes
   Counter dict showing how the portfolio's customers split by FTP mode:
     {"on": 12, "off": 3, "unknown": 0}
   Consumers can read this to gauge data quality directly.

2. data_quality_warning (top-level string)
   Populated when ANY customer in the portfolio had ftp_mode="off"
   in their upstream PnL. Warning explicitly cites Mandatory Standard
   #11 and recommends re-running #21 with ftp_mode="on" before
   treating the portfolio PBT as final.

3. portfolio_pnl.provisional flag
   True when >50% of customers had ftp_mode="off". Signals that the
   headline portfolio PBT figure is a working draft, not a final
   number for board reporting. PROVISIONAL_FTP_OFF_THRESHOLD = 0.5
   is documented architectural intent, not a magic constant.

This pattern prevents a board pack from reporting a "billion-shilling
RM portfolio loss" that's actually 67% deposit-funder customers
mis-priced by naive math. v5.48 makes that distortion impossible
to hide.

PEER COMPARISON HONESTY
========================
The spec asks for `peer_comparison: {rank: ...}`. v5.48 returns:

  rank                     ← spec primary; by total_pbt, lex tie-break
  rank_by_pbt_per_customer ← honest secondary view
  rank_by_margin           ← honest secondary view
  total_rms_ranked         ← so consumers know the comparison population
  _caveats                 ← surfaces "Peer ranking includes RMs with
                              mixed FTP treatment" when applicable

The caveats land in meta.peer_comparison_caveats. Standard #11
inheritance applies at peer-comparison level too: comparing your
RM's portfolio against peers running on naive math is not apples-
to-apples, and the engine says so.

REVENUE-WEIGHTED PORTFOLIO MARGIN
==================================
total_pbt / total_revenue, NOT mean of customer margins.

Mean-of-margins would over-weight tiny customers and produce
misleading aggregate numbers. A portfolio of one platinum customer
(KES 1M revenue, 80% margin) and 99 break-even tiny customers
(KES 100 each, 0% margin) has portfolio margin ≈ 80% (weighted),
not 0.8% (mean). The latter would be a lie.

Margin returned as None when total_revenue ≤ 0 (consistent with
#21's behavior under Standard #11).

VERIFICATION (sandbox)
----------------------
  scripts/audit.py syntax OK:                              ✓
  audit gates 34/34 PASS:                                  ✓
  G13 grew: 26/625 → 27/659 (+34 RM tests)
  python -m utils.rm_profitability self-test:             ALL PASS (14/14)
  All 12 other engine self-tests still pass:               ✓
  G34 informational pass when artifact missing:            ✓
  G34 PASS at 10/10 = 100%:                                ✓
  G34 FAIL at 90%:                                         ✓
  G34 PASS at exactly 99% boundary:                        ✓
  G34 FAIL on corrupt artifact:                            ✓

CURRENT AUDIT STATE (post-v5.48)
--------------------------------
  ✅ G1-G31 unchanged from v5.47
  ✅ G32 customer_pnl_excel_match: 100.0% (28/28)
  ✅ G33 hierarchy_classification_correct: 100.0% (20/20)
  ✅ G34 rm_aggregation_correct: 100.0% (10/10)
  Score: 34/34 = 100% PASS

INSTALLATION
------------
1. Extract over your v5.47 working tree.
2. python scripts/audit.py → 34/34 PASS expected.
3. python -m utils.rm_profitability → 14/14 self-test cases.
4. pytest tests/test_rm_profitability.py → 34 tests pass.

ROLLBACK
--------
git revert v5.48 OR delete:
  utils/rm_profitability.py
  tests/test_rm_profitability.py
  tests/fixtures/rm_portfolio_scenarios.json
  rm_aggregation_results.json (if generated)
And restore scripts/audit.py from scripts/audit.py.v5.47.bak.

WHAT'S NEXT
-----------
Volume Three: 3/10 standards delivered (#21, #22, #23). Remaining:
  #24 Customer-to-RM Allocation Intelligence
       (CustomerAllocationOptimizer.optimize_rm_allocation)
       Will inherit #23's honesty-inheritance pattern.
  #25 Dynamic Cost Allocation Engine (SQL: cost_allocation_rules)
  #26 Allocation Driver Library (DRIVERS dict)
  #27-30 (TBD)

LATENT ISSUES (v5.48 additions)
--------------------------------
21. RMProfitabilityDashboard not wired to UI page.
    pages/N_rm_dashboard.py is follow-up work.
22. build_all_portfolios is O(N×M) — production needs caching
    or pre-computed peer aggregates table.

COMMIT
------
git add scripts/audit.py utils/rm_profitability.py \
        tests/test_rm_profitability.py \
        tests/fixtures/rm_portfolio_scenarios.json \
        Master_Prompt_v3.md
git commit -m "v5.48: Standard #23 RM Profitability Dashboard + G34 + Std#11 inheritance pattern"
git tag v5.48
git push origin main --tags
