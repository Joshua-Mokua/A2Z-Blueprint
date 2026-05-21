# CHANGELOG v10.147 — ENH-136 Product Ranking & Scoring Engine

**Status:** **PHASE 1E PRODUCT 6/10 ACTIVE — SECOND SYNTHESIZER ENGINE.** Sixth engine of the Product Module; second that synthesizes outputs from multiple prior engines into a unified product score.

**Audit:** `Score: 146/146 gates = 100.0% — PASS`. No new gate; engine-level drop. **G142 anti-drift floor 71 → 72**. Engine self-tests 152/152. v10.147 tests 25/25 pass.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/product_ranking.py` | ~420 | NEW. ProductRankingEngine synthesizer + frozen ProductScore dataclass |
| `utils/standards_registry.py` | +1 line | ENH-136 status flipped planned → active |
| `pages/7_admin.py` | +25 lines | Tier 4B extended with sixth engine entry |
| `tests/test_product_v10_147.py` | ~280 | NEW. 25 tests across 9 classes |
| `docs/Master_Prompt_v3.40.md` | ~1100 | Anti-drift sync v3.39 → v3.40 |
| `SCOPE_LEDGER.md` | updated | v10.147 row + status block |
| `CHANGELOG_v10.147.md` | this file | This document |

---

## The engine — `utils/product_ranking.py`

Per Continuation.docx Standard #136: "Multi-factor product scoring and ranking dashboard."

### Second synthesizer engine

ENH-135 (CVP Builder) was the first synthesizer — combined needs + competitive + P&L into per-segment value propositions. ENH-136 is the second — combines P&L + competitive + product-level signals (growth, npl, book) into a unified 0-100 score per product with banding and ranking.

Companion engines (`ProductPnLIntelligence`, `ProductCompetitiveIntelligence`) are injectable via the constructor (DI pattern). Tests can mock them; defaults to live engines.

### Multi-factor scoring formula

The formula sums to exactly 100 points across five components:

```
total_score =
    profitability  * 30 pts    # margin scaled −30%→0 to +50%→full
  + competitive    * 25 pts    # LEADER=25 / FOLLOWER=12.5 / LAGGARD=0
  + growth         * 20 pts    # growth_rate scaled −10% to +20%
  + risk           * 15 pts    # npl_rate scaled inverted (lending only)
  + scale          * 10 pts    # book scaled 0 to 100B KES
```

All thresholds and weights are NAMED CONSTANTS on the engine class — banks override via constructor or subclass.

### Bands

```
TOP_TIER:    score ≥ 75
GROWING:     50 ≤ score < 75
WATCHLIST:   25 ≤ score < 50
DECLINE:     score < 25
```

### Public methods

- `get_product_score(product_id)` → frozen `ProductScore` with per-component breakdown (`component_scores` dict + `component_max` dict + `components_available` tuple + `components_missing` tuple + `is_estimate` flag + raw `profitability_inputs` and `competitive_inputs` dicts for traceability)
- `rank_all_products()` → list of all `ProductScore` ordered by total_score desc, with `product_id` as stable tiebreaker
- `get_top_n(n)` / `get_bottom_n(n)` — with rank position included
- `get_score_distribution()` — band counts + avg/min/max scores
- `aggregate_by_category()` — per-category rollup with avg/top/bottom + band counts
- `rank_within_category(category)` — products ranked within a single category

### Honest renormalization

When a sub-score cannot be computed (e.g. fee products skip risk + competitive components, deposit products skip risk), the formula does NOT zero-fill the missing component. Instead it RENORMALIZES the achieved sum over the components that ARE available:

```
total = (sum_of_achieved_scores / sum_of_available_max_weights) * 100
```

Example: P015 Bancassurance has only 50 max-available weight (profitability 30 + growth 20 — competitive/risk/scale all N/A for fee products). Achieves ~41.5/50 → renormalized to 83/100 with `is_estimate=True`. The behavior preserves cross-product comparability while flagging that the score is built from fewer signals.

The justification: penalizing fee products for not having a competitive benchmark or NPL rate would distort the ranking — those components don't apply. The `is_estimate` flag tells operators the score is built on fewer signals without dropping the product from the analysis.

### Stable sort

`rank_all_products()` uses `(-total_score, product_id)` as the sort key — descending by score, ascending by product_id for ties. Same input produces same rank order across runs. Auditability is preserved.

---

## Self-test on real data

```
Distribution: TOP_TIER=1 GROWING=8 WATCHLIST=7 DECLINE=0 of 16
  avg_score=54.12 range=[33, 83]

Top 5:
  #1 P015 Bancassurance: 83 (TOP_TIER, is_estimate)
  #2 P013 Savings Accounts: 74 (GROWING)
  #3 P009 Corporate Loans: 73 (GROWING)
  #4 P014 Fixed Deposits: 68 (GROWING)
  #5 P002 Mortgage Finance: 62 (GROWING)

Bottom 5:
  #12 P011 Import Finance: 45 (WATCHLIST)
  #13 P005 Business Loans: 38 (WATCHLIST)
  #14 P003 Asset Finance: 35 (WATCHLIST)
  #15 P010 Trade Finance LC: 34 (WATCHLIST)
  #16 P012 Current Accounts: 33 (WATCHLIST)

By category:
  Fee Income: avg 83.0 (1 product)
  Corporate: avg 73.0 (1)
  Digital: avg 60.0 (1)
  Deposits: avg 58.3 (3)
  Retail Lending: avg 53.3 (4)
  SME Lending: avg 45.8 (4)
  Trade Finance: avg 39.5 (2)

P001 Personal Loans: total=54 (GROWING)
  components_available: profitability, competitive, growth, risk, scale
    profitability: 9.49/30
    competitive: 25.00/25  ← full marks (LEADER)
    growth: 5.13/20
    risk: 9.82/15
    scale: 4.88/10
```

The category aggregation tells the story: **Trade Finance (39.5) and SME Lending (45.8) lag**, while **Fee Income (83) and Corporate (73) lead**. This is fully coherent with ENH-131's earlier finding that lending categories struggle on fully-loaded cost basis — the multi-factor score translates that profitability gap directly into lower ranking position. Bancassurance tops the list at 83 but with `is_estimate=True` flagged honestly because three of its five components don't apply.

The Personal Loans component breakdown shows the engine's transparency: 25/25 on competitive (LEADER status fully recognized), 9.49/30 on profitability (modest, reflects loaded margin), 5.13/20 on growth (low signal). Operators see exactly how each component contributed.

---

## Tests — `tests/test_product_v10_147.py`

25 tests across 9 classes:

- **TestEngineModule** (5) — exists / parses / class+dataclass present / 7 required methods / weights sum to exactly 100
- **TestScoring** (5) — real product score in [0,100] range / unknown product returns DECLINE / band thresholds consistent across all 16 products / lending product uses risk component / fee product skips risk component
- **TestRenormalization** (2) — missing components flag is_estimate=True / score renormalizes to 100 scale rather than penalizing missing
- **TestRanking** (5) — returns all 16 products / descending order / stable for ties (same input → same order) / top_n returns N entries with sequential ranks / bottom_n correct ranks (last entry rank = 16)
- **TestAggregations** (3) — distribution band counts add up to total / category aggregation has all required keys / within-category ranking sequential
- **TestRegistryAndAdmin** (3) — ENH-136 active / prior 1E engines (131-135) still active / admin Tier 4B has all six engines
- **TestNoRegression** (2) — audit gates intact / strategy module engines still active

All 25 pass via inline runner.

---

## Apply order

After v10.146:

```
1. utils/product_ranking.py                → utils/
2. utils/standards_registry.py             → utils/   (ENH-136 flip)
3. pages/7_admin.py                        → pages/   (Tier 4B extension)
4. tests/test_product_v10_147.py           → tests/
5. docs/Master_Prompt_v3.40.md             → docs/
6. SCOPE_LEDGER.md                         → root
7. CHANGELOG_v10.147.md                    → root
```

`git add -A && git commit -m "v10.147 ENH-136 Product Ranking & Scoring Engine — Phase 1E 6/10"`. Then `python scripts/audit.py` should print `Score: 146/146 gates = 100.0% — PASS`.

---

## Phase 1E Product trajectory

| drop | scope | status |
|---|---|---|
| v10.142 | ENH-131 Product Profitability Intelligence | SHIPPED |
| v10.143 | ENH-132 Product Lifecycle Management | SHIPPED |
| v10.144 | ENH-133 Customer Needs & Gap Analysis | SHIPPED |
| v10.145 | ENH-134 Competitive Intelligence for Products | SHIPPED |
| v10.146 | ENH-135 CVP Builder | SHIPPED |
| **v10.147 (THIS)** | **ENH-136 Product Ranking & Scoring Engine** | **SHIPPED** |
| v10.148 | ENH-137 Dynamic Pricing Engine | next |
| v10.149 | ENH-138 + ENH-139 + ENH-140 → MODULE CLOSE + G147 + cockpit + G148 UI gate | |

**v10.148 next-up:** ENH-137 Dynamic Pricing Engine. Rule-based price optimization using ENH-134 peer benchmarks as input — will recommend pricing adjustments for products materially out of step (LAGGARD on lending or LAGGARD on deposits), constrained by minimum-margin floors from ENH-131. Like ENH-135 and ENH-136, another synthesizer combining prior-engine outputs into actionable guidance.

---

## Summary

ENH-136 ships the second Phase 1E synthesizer — a multi-factor product scoring and ranking engine that combines profitability, competitive position, growth, risk, and scale into a unified 0-100 score. The honest renormalization (missing components don't penalize, but is_estimate flag surfaces the limitation) preserves cross-product comparability while staying transparent. The category-level finding — Trade Finance and SME Lending averaging 39-46 vs Fee Income / Corporate averaging 73-83 — coheres with ENH-131's earlier P&L picture and makes the cross-engine signal even sharper. Phase 1E now 6/10. Total active 143/264 (54.2%).

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. v10.147 tests `25/25 pass`.
