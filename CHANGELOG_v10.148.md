# CHANGELOG v10.148 — ENH-137 Dynamic Pricing Engine

**Status:** **PHASE 1E PRODUCT 7/10 ACTIVE — THIRD SYNTHESIZER ENGINE.** Seventh engine of the Product Module; third that synthesizes outputs from multiple prior engines into actionable guidance.

**Audit:** `Score: 146/146 gates = 100.0% — PASS`. No new gate; engine-level drop. **G142 anti-drift floor 72 → 73**. Engine self-tests 152/152. v10.148 tests 24/24 pass.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/dynamic_pricing.py` | ~470 | NEW. DynamicPricingEngine synthesizer + frozen PricingRecommendation dataclass |
| `data/pricing_constraints_config.json` | ~40 | NEW seed. Bank-overridable global + per-category pricing constraints |
| `utils/standards_registry.py` | +1 line | ENH-137 status flipped planned → active |
| `pages/7_admin.py` | +29 lines | Tier 4B extended with seventh engine entry |
| `tests/test_product_v10_148.py` | ~280 | NEW. 24 tests across 9 classes incl. read-only verification |
| `docs/Master_Prompt_v3.41.md` | ~1100 | Anti-drift sync v3.40 → v3.41 |
| `SCOPE_LEDGER.md` | updated | v10.148 row + status block |
| `CHANGELOG_v10.148.md` | this file | This document |

---

## The engine — `utils/dynamic_pricing.py`

Per Continuation.docx Standard #137: "Real-time price optimization based on demand, competition, and customer."

### Third synthesizer engine

ENH-135 (CVP Builder) was the first synthesizer; ENH-136 (Ranking) the second; ENH-137 is the third. Combines:

- **ENH-134** `ProductCompetitiveIntelligence` → peer median + LEADER/FOLLOWER/LAGGARD position per product
- **ENH-131** `ProductPnLIntelligence` → margin floor guard
- **`data/pricing_constraints_config.json`** (NEW seed) → category floors/ceilings + global max-change-per-period

Companion engines injectable via constructor (DI pattern); defaults to live engines.

### Direction-aware pricing logic

The standard's value depends on getting direction right (same as ENH-134). For lending products, **lower rates are better** (acquisition); for deposits, **higher rates are better** (attraction). Engine encodes this:

```
LEADER position           →  HOLD (already winning)
FOLLOWER (±50bps)          →  HOLD
LAGGARD lending           →  DECREASE toward peer median
LAGGARD deposit           →  INCREASE toward peer median

All changes capped at MAX_CHANGE_PER_PERIOD_BPS (default 100bps).
Category floors/ceilings applied after directional logic.
Margin floor guard (1%) only fires when proposing a CHANGE.
Changes below MEANINGFUL_CHANGE_BPS (25bps) downgrade to HOLD.
```

### Action set

| Action | Meaning |
|---|---|
| `HOLD` | Hold current rate |
| `INCREASE` / `DECREASE` | Move toward peer median |
| `NO_BENCHMARK` | Product has no competitor mapping (fee/proprietary products) |
| `CONSTRAINED_BY_FLOOR` | Recommendation hit category rate floor |
| `CONSTRAINED_BY_CEILING` | Recommendation hit category rate ceiling |
| `CONSTRAINED_BY_MARGIN` | Recommendation would push margin below floor |
| `PRODUCT_NOT_FOUND` | Product not in products.json |

### Public methods

- `get_pricing_recommendation(product_id)` → frozen `PricingRecommendation` with rationale tuple, constraints_applied tuple, and margin_at_recommended_pct
- `get_all_recommendations()` — bank-wide list
- `get_actionable_recommendations(min_change_bps)` — sorted by magnitude desc
- `get_recommendation_summary()` — n_products + by_action counts + n_actionable + avg_actionable_change_bps
- `simulate_price_change(product_id, new_rate_pct)` — what-if margin impact, never persists state

### Honesty discipline

- **Engine NEVER writes pricing.** All recommendations are advisory; the decision and implementation belong to operators. Engine has no methods that mutate `data/products.json` or any pricing state.
- **Margin floor guard only fires on proposed CHANGES** — not on HOLD. The engine doesn't suddenly object to current margins it isn't trying to change. This was a careful design choice: a HOLD on a currently-loss-making product (negative margin) shouldn't trip the guard, because that's the operator's existing accepted state.
- **NO_BENCHMARK products** return null `recommended_rate` with explicit reason from `data/product_competitor_mapping.json`'s unmapped[] entry. Trade Finance LC, Bancassurance, Current Accounts, Import Finance, Digital Finance — operators see exactly why no recommendation is offered.
- **Constraint actions surface the binding constraint.** `CONSTRAINED_BY_FLOOR` tells operators the unconstrained recommendation would have been LOWER than the category floor (regulatory/COF lower bound). Same for ceiling and margin. The constraint isn't silently absorbed.
- **Single-period cap of 100bps** prevents customer-shock from pricing engine moves. A 200bps gap to peer median is bridged in two steps minimum. Operators can override the cap via config.
- **NO ML pricing models.** All logic is documented rule-based with named constants. Same input produces same recommendation across runs (auditability).
- **Read-only verified** — test class `TestReadOnly` parses the engine source and asserts no `json.dump` calls target product files in actual code.

---

## Self-test on real data

```
Recommendations: 16 products
  By action: {'HOLD': 10, 'NO_BENCHMARK': 5, 'INCREASE': 1}
  Actionable: 1 (avg change 100.0bps)

Sample recommendations:
  P001 Personal Loans (Retail Lending): current=14.5% → rec=14.5% (+0bps) action=HOLD
    → LEADER position; holding current rate (14.5%) — already beats peer median by 375 bps
  P002 Mortgage Finance (Retail Lending): current=12.0% → rec=12.0% (+0bps) action=HOLD
    → LEADER position; holding current rate (12.0%) — already beats peer median by 275 bps
  P005 Business Loans (SME Lending): current=13.5% → rec=13.5% (+0bps) action=HOLD
    → LEADER position; holding current rate (13.5%) — already beats peer median by 325 bps
  P010 Trade Finance LC (Trade Finance): current=10.0% → rec=None% (n/a) action=NO_BENCHMARK
    → no_competitor_benchmark: trade_finance_pricing_not_in_public_competitor_dataset
  P013 Savings Accounts (Deposits): current=3.5% → rec=3.5% (+0bps) action=HOLD
    → FOLLOWER within ±50bps of peer median; holding current rate
  P014 Fixed Deposits (Deposits): current=10.0% → rec=11.0% (+100bps) action=INCREASE
    → LAGGARD; moving INCREASE toward peer median (12.0000%), capped at 100bps per period
  P015 Bancassurance (Fee Income): current=0% → rec=None% (n/a) action=NO_BENCHMARK
    → no_competitor_benchmark: fee_income_product_pricing_proprietary_not_benchmarked

Actionable recommendations:
  P014 Fixed Deposits: INCREASE +100bps
```

The lone actionable recommendation is **exactly the LAGGARD ENH-134 identified**. Cross-engine signal:

- **ENH-134** flagged Fixed Deposits as LAGGARD (we pay 10% vs peer median 12% — `we_pay_less`)
- **ENH-137** produces the rule-based response (INCREASE +100bps, capped from full 200bps gap to peer median, moving from 10% toward 12%)

Operators see the recommendation + the rationale + the constraint that capped it. Whether to act, when to act, and how to phase the change are operator decisions; the engine surfaces evidence.

---

## Tests — `tests/test_product_v10_148.py`

24 tests across 9 classes:

- **TestEngineModule** (4) — exists / parses / class+dataclass present / 5 required methods
- **TestRecommendationLogic** (6) — unknown product not_found / unmapped no_benchmark / leader hold / lagging deposit increase / change capped at 100bps / constraint applied recorded
- **TestActionable** (3) — actionable filters by min_change_bps / sorted by magnitude desc / summary components consistent
- **TestSimulate** (2) — unknown fails with reason / real product projects margin
- **TestReadOnly** (1) — engine source contains no `json.dump` writes targeting product files
- **TestConfig** (3) — config exists+parses / global_constraints present / category_constraints for 5 lending+deposit categories
- **TestRegistryAndAdmin** (3) — ENH-137 active / prior 1E engines (131-136) still active / admin Tier 4B has all seven engines
- **TestNoRegression** (2) — audit gates intact / strategy module engines still active

All 24 pass via inline runner.

---

## Apply order

After v10.147:

```
1. utils/dynamic_pricing.py                 → utils/
2. data/pricing_constraints_config.json     → data/
3. utils/standards_registry.py              → utils/   (ENH-137 flip)
4. pages/7_admin.py                         → pages/   (Tier 4B extension)
5. tests/test_product_v10_148.py            → tests/
6. docs/Master_Prompt_v3.41.md              → docs/
7. SCOPE_LEDGER.md                          → root
8. CHANGELOG_v10.148.md                     → root
```

`git add -A && git commit -m "v10.148 ENH-137 Dynamic Pricing Engine — Phase 1E 7/10"`. Then `python scripts/audit.py` should print `Score: 146/146 gates = 100.0% — PASS`.

---

## Phase 1E Product trajectory

| drop | scope | status |
|---|---|---|
| v10.142 | ENH-131 Product Profitability Intelligence | SHIPPED |
| v10.143 | ENH-132 Product Lifecycle Management | SHIPPED |
| v10.144 | ENH-133 Customer Needs & Gap Analysis | SHIPPED |
| v10.145 | ENH-134 Competitive Intelligence for Products | SHIPPED |
| v10.146 | ENH-135 CVP Builder | SHIPPED |
| v10.147 | ENH-136 Product Ranking & Scoring Engine | SHIPPED |
| **v10.148 (THIS)** | **ENH-137 Dynamic Pricing Engine** | **SHIPPED** |
| v10.149 | ENH-138 AI Product Recommendation Engine | next |
| v10.150 | ENH-139 + ENH-140 → MODULE CLOSE + G147 + cockpit + G148 UI gate | closure |

**v10.149 next-up:** ENH-138 AI Product Recommendation Engine. Per Continuation.docx the name says "AI" but per the standing Rule 7, engine ships rule-based first with optional AI hook (same pattern as ENH-135). Will combine ENH-133 customer needs + propensity_scores + ENH-131 product margins + ENH-136 ranking to produce per-customer next-best-product recommendations. AI hook opt-in with basis tag and graceful fallback.

The final closure batch (ENH-139 + ENH-140 + G147 + cockpit + G148) moves to v10.150 — the one-per-zip rule preserves clean rollback per standard.

---

## Summary

ENH-137 ships rule-based pricing recommendations using ENH-134 peer benchmarks as input + ENH-131 margin floor as guard rail + bank-curated category constraints. The honest finding: the lone actionable recommendation across the 16-product portfolio is exactly the LAGGARD ENH-134 identified — Fixed Deposits +100bps toward peer median, capped from the full 200bps gap. The engine never writes pricing; operators decide. The cross-engine pattern (ENH-134 surfaces the gap, ENH-137 produces the rule-based response, ENH-131 guards the margin) demonstrates the synthesizer pattern working as intended. Phase 1E now 7/10. Total active 144/264 (54.5%).

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. v10.148 tests `24/24 pass`.
