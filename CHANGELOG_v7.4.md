# A2Z MIS 360 — CHANGELOG v7.4

**v7.4 customer_base + dormant_accounts + L09 — STOCKS 100% milestone batch**
**Released:** May 2026
**Audit gates:** **105/105** = 100% PASS (clean on first attempt — 13th consecutive)
**Strategic milestone:** **⭐ FIRST KEY-AXIS 100% MILESTONE.** Stocks 6 of 6 (100%) + loops 11 of 15 (73%). The bank's accumulator structure is now fully visible at the system level.

---

## What this batch is

**Pure unification work.** Zero new domain features. Zero new pages. Zero new depth analytics. Zero new engines. Zero new audit gates.

**Three things wired**: L09 loop closure, customer_base stock, dormant_accounts stock. With the latter two, **all 6 stocks defined in Charter §5 are now WIRED** — first 100% completion on a key axis of the systems layer.

---

## What changed

### L09: Branch performance → Resource allocation (WIRED)

**Consumer added** to `utils/allocation_optimizer.py`:
```python
CustomerAllocationOptimizer.reallocation_signals_from_branch_performance(
    branch_performance_payload
) → {
    "reallocation_directives": [
        {"branch_id": "BR-004", "current_quartile": "BOTTOM",
         "action": "REALLOCATION_CANDIDATE", "priority": "HIGH_RISK", ...}
    ],
    "summary": {"total_branches_analysed": 5,
                "by_action": {"REALLOCATION_CANDIDATE": 2, "EXPAND_CAPACITY": 1, ...}},
    "consumed_payload_version": "branch_performance.peer_benchmark_metrics+quartile_rank v1.0",
}
```

**Quartile-based directive logic**:
- TOP quartile → EXPAND_CAPACITY (model for replication)
- Q2 → MAINTAIN
- Q3 → COACHING_INVESTMENT (review in 90 days)
- BOTTOM quartile → REALLOCATION_CANDIDATE (move 1-2 RMs to higher-performing branches)

Sorted by priority — HIGH_RISK reallocations surface first.

**Registry correction**: L09's `from_engine` was `utils.branch_log` (doesn't exist). Corrected to `utils.branch_performance`. This is the third such correction in v7.x (v7.2 audit_workflow→audit_universe, v7.3 cross_sell→cross_sell_nba, v7.4 branch_log→branch_performance). The pattern: original v7.0 registry was drafted from charter design notes; subsequent batches correct paths as engines are actually wired.

### customer_base stock WIRED

**New accessor** `_customer_base_snapshot()` returns:
```python
{
    "status": "WIRED",
    "value": "700000",  # matches A2Z Blueprint CBS simulation
    "by_segment_count": {"RETAIL_INDIVIDUAL": 595000, "SME": 70000,
                         "CORPORATE": 28000, "STAFF": 7000},
    "by_tenure_band_count": {"0_TO_1_YEAR": 105000, "1_TO_3_YEARS": 175000,
                              "3_TO_5_YEARS": 140000, "OVER_5_YEARS": 280000},
    "by_onboarding_channel_count": {...},
    "by_kyc_risk_band_count": {"LOW": 525000, "MEDIUM": 140000,
                                "HIGH": 35000, "PROHIBITED": 0},
    "monthly_growth_rate_pct": "0.8",
    ...
}
```

**Notable**: `by_kyc_risk_band_count` directly links to L07 KYC→TxnMonitor loop. Future batches can compute "what % of total transaction volume comes from HIGH-risk customers?" by composing customer_base + transaction_monitoring data.

### dormant_accounts stock WIRED

**New accessor** `_dormant_accounts_snapshot()` returns:
```python
{
    "status": "WIRED",
    "value": "84000",                       # 12% dormancy rate
    "by_dormancy_band_count": {
        "DAYS_90_TO_180": 42000,            # 50%
        "DAYS_181_TO_365": 25200,           # 30%
        "OVER_365_DAYS": 16800              # 20%
    },
    "dormancy_rate_pct": "12.00",            # computed against customer_base
    "customer_basis_count": 700000,
    "reactivation_potential_count": 12600,   # 15% of 90-180 day band
    "estimated_latent_value_kes": "714000000",  # 0.71B
    ...
}
```

**Notable**: dormancy_rate_pct computed against customer_base 700K basis, so the two stocks remain consistent. If real CBS data later shifts customer_base, dormant_accounts.dormancy_rate_pct updates automatically.

### G104 stocks ratchet raised

4 → 6. **First key-axis 100% threshold reached.** Once met, regression is permanently blocked.

### Charter §8 + §14 updated

**§8**: 10→11 wired loops, 4→6 wired stocks (73%/100%)

**§14 catch-up** (long pending): the 6-item "what charter does NOT do" list reorganised into:
- **4 RESOLVED** (engine migration, loop wiring, stock wiring, audit gates) with citations to v7.0.1 / v7.1 / v7.2 / v7.3 / v7.4
- **6 STILL-OPEN** (S2 coordination, info-flow latency, peer benchmarking, demo defaults, bounded-context enforcement, football team test)

This is the first §14 update since v7.0 (acknowledged as pending in the v7.0.1, v7.1, v7.2, v7.3 changelogs).

---

## End-to-end smoke test (all green)

```
=== FULL AUDIT ===
  Score: 105/105 gates = 100.0% — PASS

Loop counts: WIRED=11, DESIGNED_NOT_WIRED=4
  WIRED: 11/15 = 73%
Stock counts: WIRED=6, NOT_WIRED=0
  WIRED: 6/6 = 100% ⭐

  ✓ All 6 stocks return live snapshots:
    capital_base       27.2B KES (Tier 1+2 from CapitalAdequacyEngine)
    loan_portfolio     80.0B KES (gross outstanding)
    deposit_base      110.0B KES (LDR 73%)
    npl_inventory       8.0B KES (10% NPL ratio)
    customer_base   700,000 customers (4 segments + KYC bands)
    dormant_accounts 84,000 (12% rate, 3 dormancy bands)
  ✓ L09 round-trip: 5 branches → correct quartile-based actions
  ✓ G104: 6 engines + 6 stocks (ratchet at 6/6)
```

---

## ✅ Thirteenth consecutive clean-first-try

13th batch in a row landing clean.

---

## Comparison vs v7.3

| | v7.3 | v7.4 |
|---|---|---|
| Audit gates | 105/105 | **105/105** |
| Stocks WIRED | 4 (67%) | **6 (100%)** ⭐ |
| Feedback loops WIRED | 10 (67%) | **11 (73%)** ⭐ |
| Engines reading from registry | 6 | 6 (unchanged) |
| Clean-first-try streak | 12 | **13** |
| Charter §14 status | Out of date since v7.0 | **Caught up** ⭐ |

---

## The 11 wired loops + 6 wired stocks

**Loops wired:** L01, L02, L03, L06, L07, L08, **L09** ⭐, L10, L11, L12, L15
**Loops remaining:** L04 (vendor→opl risk), L05 (cards→segmentation), L13 (comp→workforce), L14 (channel→alerts)

**Stocks wired (100%):**
- capital_base (v7.0.1)
- loan_portfolio (v7.1)
- npl_inventory (v7.1)
- deposit_base (v7.3)
- **customer_base** ⭐ (v7.4)
- **dormant_accounts** ⭐ (v7.4)

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — engines compile + round-trip-tested.
2. **4 of 6 stocks use demo defaults** — loan_portfolio, deposit_base, customer_base, dormant_accounts. capital_base partially derives from CapitalAdequacyEngine; npl_inventory derives Stage 3 from loan_portfolio. All `data_source` fields explicitly attributed.
3. **4 of 15 loops still DESIGNED_NOT_WIRED** — L04, L05, L13, L14.
4. **G104 stock ratchet at 6/6** (100%) — once met, regression permanently blocked.
5. **G105 scope unchanged at 6 regulated engines** — L09's allocation_optimizer doesn't enter G105 scope (no registered invariants).
6. **L09 quartile mapping accepts multiple formats** — TOP/Q1/1 and BOTTOM/Q4/4 both supported.
7. **Stock accessors don't yet support time-series** — period_change is None across all 6.
8. **customer_base + dormant_accounts coherent** — dormant_accounts dormancy_rate_pct uses customer_base as basis.
9. **Page 91 doesn't yet show the 2 new stocks** — accessor reads them, so they'll display when page loads.
10. **Charter §14 catch-up complete** — first major §14 update since v7.0.
11. **No new audit gate** — G104+G105 sufficient.
12. **Remaining 4 loops need engine extensions** — L04 partnerships, L05 cards, L13 comp_equity, L14 streaming infra.

---

## Strategic narrative — first 100% milestone

| Batch | Type | Stocks | Loops |
|---|---|---|---|
| v7.0 | Foundation | 0 wired (6 declared) | 5 wired (15 designed) |
| v7.0.1 | Propagation | 1 wired (capital_base) | 5 wired |
| v7.1 | Functional landing | 3 wired (+loan, +npl) | 6 wired (+L01) |
| v7.2 | Loops closure | 3 wired | 9 wired (60%) |
| v7.3 | Expansion | 4 wired (+deposit) | 10 wired (67%) |
| **v7.4** | **Stocks 100%** | **6 wired (100%)** ⭐ | **11 wired (73%)** |

**The bank's accumulator structure is now fully visible at the system level.** Every accumulator (customer count, loan book, deposit book, NPL inventory, dormant accounts, capital base) is queryable through one canonical accessor: `get_stock_snapshot(stock_id)`.

**When real CBS / FLEXCUBE integration arrives in v7.x+, the accessor pattern is stable; only the data sources change.** This is exactly Gall's Law evolution — the system started as a small thing in v7.0 and has grown without breaking.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v7.5 AML-health composite + close L13** | Composite extension overdue + loops 11→12 (80%) |
| (2) | v7.5 Continue Credit Risk depth on pages/32_ifrs9.py | Functional |
| (3) | v7.5 Close L05 Card usage → Segmentation | Cards engine surfacing |
| (4) | v7.5 Close L04 Vendor health → Operational risk | partnerships→operational_risk |
| (5) | v7.5 Customer-value composite UI surfacing | Extends v5.96 |

**Strong recommendation: v7.5 = AML-health composite + close L13** — composite_scores has been quiet since v6.0 (overdue for extension); L13 closure pushes loops to 80% which feels comprehensive.

---

🎯 **STOCKS 100% — first key-axis 100% milestone reached.**

⭐ **The bank's accumulator structure is now fully visible at the system level. Every stock queryable through one canonical accessor.**
