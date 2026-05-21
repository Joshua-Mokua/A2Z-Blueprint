# Changelog — v10.335 Products → BSC bridge

**Date:** 2026-05-12
**Phase:** 4 (twentieth arc — completing the SBU + Products integration)
**Audit:** 224/224 gates PASS = 100.0%
**Tests:** 672/672 passing across 40 integration suites (12 new for v10.335)
**G162 Baseline:** 4022 — 29 consecutive zero-drift batches

---

## Your design ask (verbatim)

> "we are still far off from any demo, lets focus on ensuring every
> department and all staff are fully operating and every module is
> interconnected as supposed. We had defined SBU and how the
> customers are segmented and the various propositions that have
> heads and staff, lets now bring that arm to live now, then move to
> products"

v10.334 brought the Propositions arm to life. v10.335 completes the
"then move to products" step.

## What v10.335 shipped

### `utils/products_to_bsc.py`

7th producer in the cascade. Per banking convention, products are
owned at line-of-business level — there are no dedicated "Product
Manager" staff in Tier-2 banks. Each product category maps to one
owning Head whose BSC reflects the category's performance.

**Category → Owner mapping (7 categories, 6 unique owner heads):**

| Category | Owner | Staff Code |
|----------|-------|------------|
| Retail Lending | Chief Retail Banking Officer | EXEC-CRO-001 |
| Deposits | Chief Retail Banking Officer | EXEC-CRO-001 |
| Digital | Head of Digital Financial Services | 300051 |
| SME Lending | Head of MSME | 300018 |
| Corporate | Chief Commercial Officer | EXEC-CCMO-001 |
| Trade Finance | Head Of Corporates & Trade Finance | 300017 |
| Fee Income | General Manager - Bancassurance | 300178 |

**16 products spread across the categories:**

| Category | # Products | Book | Revenue |
|----------|-----------|------|---------|
| Retail Lending | 4 (Personal/Mortgage/Asset/Salary) | 174.6B | 22.7B |
| Deposits | 3 (Current/Savings/Fixed) | 3,939.3B | 302.9B |
| SME Lending | 4 (Biz/LPO/Invoice/WC OD) | 175.4B | 24.5B |
| Corporate | 1 (Corporate Loans) | 547.4B | 63.0B |
| Trade Finance | 2 (LC/Import) | 152.1B | 15.5B |
| Digital | 1 (Digital Finance) | — | 0.4B |
| Fee Income | 1 (Bancassurance) | — | 0.2B |

Total book ~5T, total revenue ~429B.

### 4 canonical PRODUCT_ KPIs in `data/kpi_library.json`

| KPI | Pillar | Unit | Direction |
|-----|--------|------|-----------|
| PRODUCT_BOOK_ACHIEVEMENT | Financial | % | higher |
| PRODUCT_REVENUE_ACHIEVEMENT | Financial | % | higher |
| PRODUCT_NPL_RATE | Risk | % | lower |
| PRODUCT_GROWTH_RATE | Financial | % | higher |

All weighted 0.05-0.10. Tagged `_origin: v10.335_products_bridge`.

### Fee-only category handling

Digital and Fee Income categories have `target_book=0` (they're
revenue-only — no loan book). The aggregator skips book-derived
KPIs (book achievement, NPL rate, growth rate) for these categories
and only submits PRODUCT_REVENUE_ACHIEVEMENT. This avoids spurious
zero values that would unfairly hit fee-only segment scores.

Result: 18 KPIs/quarter instead of 24 (6 categories x 4 KPIs minus
6 skipped for fee-only).

### Multi-category owner aggregation

Chief Retail owns both Retail Lending AND Deposits. The bridge
aggregates ACROSS both categories before submitting (one
PRODUCT_BOOK_ACHIEVEMENT for CRO, computed from combined Retail +
Deposits actuals, not two separate values). Avoids double-counting
when one head owns multiple categories.

### Seasonal variation across quarters

`_seasonal_factor()` deterministic plus-or-minus-5% variation per
quarter. 2026-Q2 is baseline (1.0) matching the products.json
snapshot. Other quarters deterministic factors so trend lines are
visible but realistic.

## Verified outcome

### 6 product owner heads — Q2 2026 product KPIs

| Owner | Book Achv | Rev Achv | NPL | Growth |
|-------|-----------|----------|-----|--------|
| Chief Retail (CRO) | 109.3% | 115.4% | 0.28% | +10.5% |
| Chief Commercial | 109.5% | 109.5% | 0.0% | +9.5% |
| Head Corp & TF | 108.6% | 108.7% | 6.15% | +8.7% |
| Head MSME | 87.7% | 87.9% | 9.57% | -11.9% |
| Head DFS | — | 139.6% | — | — |
| GM Bancassurance | — | 57.9% | — | — |

MSME line genuinely underperforming (book at 88%, NPL at 9.57%,
shrinking 11.9%). DFS exceeding revenue target. Honest reflection of
the products.json snapshot.

### 4-quarter cascade trend — product owner heads

| Role | Q3'25 | Q4'25 | Q1'26 | Q2'26 |
|------|-------|-------|-------|-------|
| Chief Retail | 3.13 | 3.10 | 3.17 | 3.11 |
| Chief Commercial | 3.65 | 3.57 | 3.71 | 1.71 |
| Head of MSME | 3.29 | 3.43 | 3.43 | 3.00 |
| Head Corporates & TF | 4.00 | 3.71 | 4.00 | 1.83 |
| Head DFS | 3.66 | 3.69 | 3.67 | 3.71 |
| GM Bancassurance | 1.50 | 2.00 | 1.50 | 2.55 |
| MD | 3.47 | 3.54 | 3.44 | 3.32 |

Q2'26 visible variation because that's when the full pipeline data
(commercial sales) joined with product line data. Prior quarters had
synthetic seasonal factors + sparser real data. The Q2 dip in
Commercial / Trade Finance / MD is the cascade telling the truth
about an underperforming commercial line.

## New audit gate G224 — products_bridge_integration

7 invariants:
1. `utils/products_to_bsc.py` has canonical surface
2. CATEGORY_OWNER_ROLE maps 7+ categories
3. All 6 owner heads (5 unique staff_codes) resolve
4. PRODUCT_* canonical KPIs exist in kpi_library
5. BSC actuals 2026-Q2 has 15+ records `source_module='products_to_bsc'`
6. 18+ product KPI actuals exist across 4 quarters total
7. 4-quarter trend: each owner has at least 1 quarter scoring

## Architecture compliance fixes during build

**G215 — fixed_kpis count exceeded cap of 16**. I initially added
the 4 PRODUCT_ KPIs to fixed_kpis (intent: bank-uniform targets via
fixed_kpis registry). G215 caught the cap breach. Better fix: PRODUCT_
KPIs already have `bank_targets[KPI|YYYY]` entries; the scoring engine
resolves through bank_targets directly. Removed PRODUCT_ from
fixed_kpis. fixed_kpis stays at 16 entries/period.

**G162 — +1 tenant-identity literal**. Initial G224 docstring had
a tenant-specific phrase. Removed to maintain G162 zero-drift
(4022 baseline holds — 29 consecutive zero-drift batches now).

## Files changed

| File | Change |
|------|--------|
| `utils/products_to_bsc.py` | NEW — 12,384 bytes, 318 lines |
| `data/kpi_library.json` | +4 PRODUCT_ canonical KPIs, +6 role_kpi entries for owner Heads |
| `data/bank_targets.json` | +8 PRODUCT_ target entries (4 KPIs x 2 years) |
| `data/bsc_actuals_2025-Q3.json` | +18 products_to_bsc actuals |
| `data/bsc_actuals_2025-Q4.json` | +18 |
| `data/bsc_actuals_2026-Q1.json` | +18 |
| `data/bsc_actuals_2026-Q2.json` | +18 |
| `data/cascade_scores_*.json` | All 4 quarters re-precomputed |
| `data/fixed_kpis.json` | Reverted accidental PRODUCT_ additions (G215 fix) |
| `scripts/audit.py` | NEW G224 gate function + registration |
| `tests/integration/test_v10335_products_bridge.py` | NEW — 12 tests across 5 sections |

## Platform state

| Metric | v10.334 → v10.335 |
|--------|-------------------|
| Audit gates | 223 → **224** |
| Integration test suites | 39 → **40** |
| Tests passing | 660 → **672** |
| Producer modules | 6 → **7** (added Products bridge) |
| Product categories in cascade | 0 → **7** |
| Owner heads with PRODUCT_ KPIs | 0 → **6** |
| Total Phase 4 cascade actuals (Q2) | ~2,700 → ~2,718 |
| G162 baseline | 4022 (29 consecutive zero-drift batches) |

## Real findings during this batch

1. **Products module had infrastructure but no producer.** Same
   pattern as v10.334 propositions: 13 product engines existed
   (product_profitability, product_raroc, product_lifecycle, etc.)
   plus the 16-product products.json. What was missing: an aggregator
   that pushes per-category metrics into the BSC cascade.

2. **Fee-only categories needed special handling.** Digital and Fee
   Income have target_book=0 — they're revenue-only segments. The
   initial aggregator emitted book/NPL/growth=0 for them, which
   would falsely score those owners as failing on book metrics they
   don't actually own. Fixed: skip book-derived KPIs when target_book=0.

3. **Multi-category owners need aggregate-first, then submit.** Chief
   Retail owns Retail Lending + Deposits. Submitting two separate
   PRODUCT_BOOK_ACHIEVEMENT values would override one with the other
   (last-write-wins via index). Fix: aggregate book / revenue /
   weighted-NPL across both categories first, then submit one
   combined KPI per owner.

4. **Q2 dips revealed pipeline-vs-product data difference.** Chief
   Commercial dropped 3.71 → 1.71 in Q2. Not a bug — Q3/Q4/Q1 had
   only product-line data (seasonal-synthetic), while Q2 has REAL
   pipeline sales data joined. The product line is fine (109% book
   achievement) but the commercial sales pipeline shows
   underperformance the prior quarters were hiding.

5. **The role_kpis already had PRODUCT_ entries.** From in-progress
   work prior to this chat. I verified, didn't duplicate.

6. **G162 holds at 4022.** 29 consecutive zero-drift batches now.

## What's NOT in v10.335

1. **No product-level drill-down page.** The aggregates feed into
   each owner's cockpit, but a dedicated "Product Performance" page
   showing per-product (P001 Personal Loans, P002 Mortgage Finance,
   etc.) isn't part of this batch. The data is in place for that page
   when it's built — `get_product_kpi_summary(period)` returns the
   per-category breakdown.

2. **No quarterly product snapshots.** `products.json` represents the
   current snapshot (last_updated 2026-04-17). The 4-quarter trend is
   synthesized via deterministic plus-or-minus-5% seasonal factor.
   Real bank deployment would have quarterly product P&L snapshots
   feeding the bridge from FLEXCUBE.

3. **No SBU drill-down page.** Per the user's mention of "SBU and how
   the customers are segmented", the SBU lens is achievable via the
   propositions arm (v10.334) + this products arm. A dedicated SBU
   page combining both is a candidate for the next batch.

4. **Cards, Retailer Financing, Value Chain not in bridge.** These
   have their own standards (#429-468) and their own page-level
   pipelines. They're not in `products.json`. Bringing them into a
   unified product bridge would require either folding them into
   products.json or building separate sub-bridges. Not yet done.

## Backlog status

| ID | Status |
|----|--------|
| B-027 | Open — Treasury (7), Trade Finance specialists (7), Marketing (4) etc still non-scoring |
| B-028 | **NEW** — Cards / Retailer Financing / Value Chain not yet in products bridge |
| B-029 | **NEW** — `products.json` is single-snapshot; needs quarterly P&L history for real trend (vs synthetic seasonal factor) |
| B-023, B-025, B-026 | Open |

## Suggested next batches

With Propositions (v10.334) + Products (v10.335) both in cascade, the
SBU + Customer Segments + Propositions + Products arm is alive.

1. **v10.336 — TRANSITION_BRIEF.md for next chat** — knowledge handoff
   document so the next conversation starts at the right state. RECOMMENDED
   given chat length.
2. **v10.336 — Remaining department coverage** (B-027) — bring
   Treasury, Trade Finance specialists, Marketing into the cascade
3. **v10.336 — Branch-level staff coverage** — give 496 retail
   branch staff (CSOs, Branch RMs, Personal/Business Bankers) their
   own scorecards
4. **v10.336 — SBU drill-down page** — combines propositions + products
   into one per-SBU view
