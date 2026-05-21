# A2Z MIS 360 — CHANGELOG v7.3

**v7.3 deposit_base + L10 — systems-layer expansion batch**
**Released:** May 2026
**Audit gates:** **105/105** = 100% PASS (clean on first attempt — 12th consecutive)
**Strategic milestone:** **🎯 67%/67% BALANCE ACHIEVED.** Stocks 4 of 6 (67%) + loops 10 of 15 (67%). The systems layer's two key axes — what accumulates (stocks) and what flows (loops) — are now in balance.

---

## What changed

### L10: Customer churn → Cross-sell prioritisation (WIRED)

**Consumer added** to `utils/cross_sell_nba.py`:
```python
CrossSellNextBestActionEngine.priorities_from_churn(
    churn_priority_payload, opportunities, churn_uplift_factor=1.5
) → {
    "reranked_opportunities": [...],  # boosted scores
    "uplift_applied_count": 2,
    "churn_risk_map": {"C001": "MEDIUM", "C002": "HIGH"},
    "consumed_payload_version": "churn_prediction.retention_intervention_priority v1.0",
}
```

**Strategy** (Meadows leverage point #4 — self-organisation):
- HIGH-risk customers: full uplift (× 1.5)
- MEDIUM-risk: half uplift (× 1.25)
- LOW-risk: untouched
- Saving an existing customer is cheaper than acquiring a new one

**Round-trip verified**: HIGH-risk C002 jumped from score 80 → 120 (top); MEDIUM-risk C001 from 70 → 87.5.

**Registry correction**: L10's `to_engine` was `utils.cross_sell` (doesn't exist). Corrected to `utils.cross_sell_nba`.

### deposit_base stock WIRED

**New accessor** `_deposit_base_snapshot()` returns:

```python
{
    "status": "WIRED",
    "value": "110000000000",  # 110B KES
    "loan_to_deposit_ratio_pct": "72.73",
    "by_stability_tier_kes": {
        "RETAIL_STABLE": "55B",         # 50% — insured retail
        "RETAIL_LESS_STABLE": "22B",    # 20% — uninsured retail
        "OPERATIONAL_DEPOSITS": "16.5B", # 15% — corporate operating
        "NON_OPERATIONAL_CORPORATE": "11B",  # 10%
        "FINANCIAL_INSTITUTIONS": "5.5B",  # 5%
    },
    "by_product_kes": {"CURRENT": "33B", "SAVINGS": "44B",
                       "FIXED_DEPOSITS": "27.5B", "CALL": "5.5B"},
    "by_segment_kes": {"RETAIL": "66B", "SME": "16.5B",
                       "CORPORATE": "22B", "FI": "5.5B"},
    "data_source": "demo_defaults...",
}
```

LDR computed dynamically against `loan_portfolio` basis. By-stability-tier breakdown follows Basel III runoff-rate framework — directly feeds LCR/NSFR computation.

### G104 ratchet raised

Stocks ratchet 3 → 4. Once met, regression blocked.

### Charter §8 updated

Wired count 9 → 10 (67%); learning loops still 3/3 wired.

---

## End-to-end smoke test (all green)

```
=== FULL AUDIT ===
  Score: 105/105 gates = 100.0% — PASS

Loop counts: WIRED=10, DESIGNED_NOT_WIRED=5
  WIRED: 10/15 = 67%
Stock counts: WIRED=4, NOT_WIRED=2
  WIRED: 4/6 = 67%

  ✓ L10: WIRED (HIGH C002 80→120, MEDIUM C001 70→87.5)
  ✓ deposit_base: KES 110B (LDR 72.73%)
  ✓ G104: 6 engines, 4 stocks (ratchet raised)
```

---

## ✅ Twelfth consecutive clean-first-try

12th batch in a row landing clean.

---

## Comparison vs v7.2

| | v7.2 | v7.3 |
|---|---|---|
| Audit gates | 105/105 | **105/105** |
| Stocks WIRED | 3 (50%) | **4 (67%)** ⭐ |
| Feedback loops WIRED | 9 (60%) | **10 (67%)** ⭐ |
| Engines reading from registry | 6 | 6 (unchanged) |
| Clean-first-try streak | 11 | **12** |

---

## The 10 wired loops + 4 wired stocks

**Loops wired:** L01, L02, L03, L06, L07, L08, **L10** ⭐, L11, L12, L15
**Loops remaining:** L04, L05, L09, L13, L14

**Stocks wired:** capital_base (v7.0.1), loan_portfolio (v7.1), npl_inventory (v7.1), **deposit_base** (v7.3) ⭐
**Stocks remaining:** customer_base, dormant_accounts (both Customer Intelligence)

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — engines compile + round-trip-tested.
2. **deposit_base uses demo defaults** — explicitly attributed in `data_source` field per Rule 6.
3. **5 of 15 loops still DESIGNED_NOT_WIRED** — L04, L05, L09, L13, L14.
4. **2 of 6 stocks still NOT_WIRED** — customer_base + dormant_accounts (Customer Intelligence; need CBS customer table).
5. **G104 ratchet raised**, G105 scope unchanged.
6. **L10 uplift_factor is bank-policy** — could become composite-scores tunable in future.
7. **L10 consumer requires caller-supplied opportunities list** — returns NO_OPPORTUNITIES_PROVIDED if not.
8. **deposit_base no time-series** — period-over-period deferred to FLEXCUBE integration.
9. **Page 91 not yet updated** to show deposit_base — page reads from accessor so it will display when loaded.
10. **Charter §14 still says "all 6 stocks NOT_WIRED"** — out of date; pending amendment.
11. **No new audit gate** — G104+G105 sufficient.
12. **Engine methods not in `__all__`** — accessible as class methods.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v7.4 Wire customer_base + dormant_accounts (stocks 4→6 = 100%) + close L09** | Completes stock wiring; loops 10→11 (73%) |
| (2) | v7.4 Close 2 more loops (L05, L13) | Pure loops batch |
| (3) | v7.4 Continue Credit Risk depth on pages/32_ifrs9.py | Functional |
| (4) | v7.4 AML-health composite addition | Extends composite_scores |

**Strong recommendation: v7.4 = wire remaining 2 stocks + close L09** — completes stock wiring (100%) and brings loops to 73%.

---

🎯 **67%/67% balance achieved. The systems layer's two key axes are now in balance.**
