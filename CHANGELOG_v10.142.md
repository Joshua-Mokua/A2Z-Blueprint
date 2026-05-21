# CHANGELOG v10.142 — Phase 1E Product Module Opens: ENH-131 Product Profitability Intelligence

**Status:** **PHASE 1E PRODUCT MODULE FIRST ENGINE LIVE.** v10.141 closed the Strategy UI pass under the new UI-pass-on-closure norm. v10.142 opens Phase 1E by activating the first of ten Product Module standards. This drop ships engines + tests + registry flip + admin Tier 4B entry. Cockpit + API + UI gate ship at module close (~v10.146) per the standing norm.

**Audit:** `Score: 146/146 gates = 100.0% — PASS` (quoted directly from `python scripts/audit.py`). No new gate added — engine-level drop. **G142 anti-drift floor ratcheted continuation_doc active 66 → 67**. G144 264/264 STABLE; G145 15/15 STABLE; G146 STABLE; G117 unchanged. **Engine self-tests:** 152/152. **v10.142 tests:** 24/24 pass via inline runner (sandbox lacks pytest install).

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/product_pnl_intelligence.py` | ~430 | NEW. ProductPnLIntelligence engine — book-based product P&L with per-category cost model |
| `data/cost_allocation_config.json` | ~30 | NEW seed. Bank-overridable cost-allocation parameters with category overrides |
| `utils/standards_registry.py` | +1 line | ENH-131 status flipped planned → active; affected_engines + implementation_batch set |
| `pages/7_admin.py` | +25 lines | NEW Tier 4B section "Product Intelligence (v10.142)" between Tier 4 + Tier 5 |
| `tests/test_product_v10_142.py` | ~250 | NEW. 24 tests across 8 classes |
| `docs/Master_Prompt_v3.35.md` | ~1100 | Anti-drift sync v3.34 → v3.35; v10.142 narrative paragraph |
| `SCOPE_LEDGER.md` | updated | v10.142 trajectory row + status block + Phase 1E remaining roadmap |
| `CHANGELOG_v10.142.md` | this file | This document |

---

## The engine — `utils/product_pnl_intelligence.py`

**Per Continuation.docx Standard #131:** "Full product P&L with direct + allocated costs, customer profitability by product."

### Companion relationship to existing #47

There is an EXISTING `utils/product_profitability.py` (Standard #47, v5.52) that does product P&L via customer rollup with FTP-mode honesty inheritance — it requires per-customer P&L data injected via DI callbacks. ENH-131 is a **separate, complementary engine** for the case where only product-level book + revenue data is available (which is what `data/products.json` provides today). The two engines coexist:

- **#47 ProductProfitabilityEngine** — use when per-customer P&L data is flowing in
- **ENH-131 ProductPnLIntelligence** — use when product-level granularity is what's available

### Cost model

Per-category — each category has a cost-model semantic, not a one-size-fits-all formula:

- **lending** — `book × COF (funding) + book × npl × LGD (credit) + revenue × ops% + revenue × overhead%`
- **deposits** — `0 (funding) + 0 (credit) + revenue × ops% + revenue × overhead%` because revenue is already NIM-net (not gross interest paid)
- **fee** — `0 (funding) + 0 (credit) + revenue × ops% + revenue × overhead%` for Bancassurance, Digital fee streams

Categories mapped: Retail Lending → lending; SME Lending → lending; Corporate → lending; Trade Finance → lending; Deposits → deposits; Fee Income → fee; Digital → fee.

### Bank-overridable constants

Defaults (Tier-2 Kenya bank baseline; config takes precedence):

```python
DEFAULT_COF_RATE_PCT = 8.5             # cost of funds, blended
DEFAULT_LGD_PCT = 45.0                 # loss given default, Basel
DEFAULT_DIRECT_OPS_COST_PCT_OF_REVENUE = 12.0
DEFAULT_OVERHEAD_PCT_OF_REVENUE = 18.0
PROFITABLE_THRESHOLD_PCT = 5.0
BREAKEVEN_BAND_PCT = 2.0
```

`data/cost_allocation_config.json` provides global + per-category overrides:
- **Trade Finance**: ops 18% (LC issuance + document handling), LGD 35% (collateralized)
- **Digital**: ops 6% (low marginal STP cost)
- **Corporate**: LGD 35% (collateral / parent guarantees)

### Public methods

- `compute_product_pnl(product)` → `ProductPnLBookBased` frozen dataclass
- `compute_portfolio()` → all 16 products in data/products.json
- `aggregate_by_category()` → 7 categories rolled up
- `get_loss_making(threshold_pct)` → products below margin threshold
- `get_bank_wide_summary()` → totals + ratios + status counts
- `customer_profitability_by_segment(product_id, segment_data)` → segment-level allocation when caller supplies data; explicit `fallback_reason="no_segment_data_supplied"` when not

### Status classification (3 bands, not 2)

- `profitable` — margin ≥ +5%
- `breakeven` — margin within ±2% band around zero
- `loss-making` — margin < -2%

Three bands instead of binary preserves the honesty: a product near zero margin is meaningfully different from one at -25%.

---

## Self-test on real seed

Running `python -m utils.product_pnl_intelligence` against the live `data/products.json` (16 products, KES 4.99T total book):

```
Bank-wide:
  n_products: 16
  total_book_kes: 4988806983960.0
  total_revenue_kes: 429109032993.0
  total_cost_kes: 234874605561.87
  total_net_profit_kes: 194234427431.13
  margin_pct: 45.26
  roa_pct: 3.89
  n_profitable: 4
  n_breakeven: 1
  n_loss_making: 10

Categories:
  Retail Lending: n=4 margin=-18.34% roa=-2.38%
  SME Lending: n=4 margin=-21.72% roa=-3.03%
  Corporate: n=1 margin=-3.91% roa=-0.45%
  Trade Finance: n=2 margin=-40.21% roa=-4.11%
  Deposits: n=3 margin=70.00% roa=5.38%
  Fee Income: n=1 margin=70.00% roa=None%
  Digital: n=1 margin=76.00% roa=None%
```

The honest finding: **10 of 16 products are loss-making on a fully-loaded basis.** Retail Lending, SME Lending, and Trade Finance categories all show negative margins; Deposits + Fee Income + Digital carry the bank. This is plausible for a Tier-2 Kenya bank — the deposit franchise + fee streams subsidize the lending book on fully-allocated overhead. The point of the standard is to surface exactly this picture for Eco Bank's Product Heads — not to make products look profitable.

---

## Honesty discipline

Per the standing rules:

- **All cost components flagged is_estimate=True** with explicit `missing_inputs` trail describing each imputation basis (e.g. `"funding_cost: imputed at 8.5% COF on book"`)
- **Deposits + Fee products explicitly skip funding+credit costs** — never zero-fudged. The cost model encodes the semantic.
- **`customer_profitability_by_segment` returns explicit `fallback_reason="no_segment_data_supplied"`** when caller doesn't provide segment book/revenue. Never fabricates a split.
- **Three-band status** preserves the breakeven case rather than binary classification
- **Read-only contract** — never writes to `performance.*` tables (per standing rule)
- **Decimal arithmetic throughout** — no float drift in money math

---

## Tests — `tests/test_product_v10_142.py`

24 tests across 8 classes:

- **TestEngineModule** (4) — module exists / parses / class+dataclass defined / dataclass frozen / required public methods
- **TestPnLBehavior** (5) — cost model lending / deposits skips funding+credit / fee skips funding+credit / status classification bands / missing_inputs trail
- **TestAggregations** (4) — portfolio returns list / aggregate_by_category keys / bank_wide_summary complete / get_loss_making threshold
- **TestSegmentProfitability** (3) — no_segment_data fallback / unknown_product fallback / with segment_data returns segments
- **TestCostConfig** (3) — config exists / parses / has required keys
- **TestRegistry** (1) — ENH-131 active with affected_engines + implementation_batch
- **TestAdminHub** (1) — Tier 4B section present with engine entry
- **TestNoRegression** (3) — audit script imports + GATES intact + all 15 strategy standards still active

All 24 pass via inline runner (sandbox can't `pip install pytest`; the sandbox-only stub is removed before packaging).

---

## What this drop does NOT change

- **Audit gate count** — still 146; cockpit + API + UI gate ship at module close (~v10.146)
- **G117 admin hub coverage** — Tier 4B is a NEW section but engines added there are read-only Tier entries; G117 logic unaffected
- **G144 QA spec coverage** — still 264/264; ENH-131 is `active` not new spec
- **G145 / G146** — Strategy module unchanged
- **Existing `utils/product_profitability.py`** — preserved untouched as Standard #47 (different abstraction)
- **Strategy module** — all 15 ENH-141..155 still active; no regression

---

## Apply order

After applying v10.141 + v10.141.1 hotfix:

```
1. utils/product_pnl_intelligence.py      → utils/
2. data/cost_allocation_config.json       → data/
3. utils/standards_registry.py            → utils/   (ENH-131 flip)
4. pages/7_admin.py                       → pages/   (Tier 4B addition)
5. tests/test_product_v10_142.py          → tests/
6. docs/Master_Prompt_v3.35.md            → docs/
7. SCOPE_LEDGER.md                        → root
8. CHANGELOG_v10.142.md                   → root
```

`git add -A && git commit -m "v10.142 ENH-131 Product Profitability Intelligence — Phase 1E opens"`. Then `python scripts/audit.py` should print `Score: 146/146 gates = 100.0% — PASS`.

---

## Phase 1E Product trajectory

| drop | scope | gate impact |
|------|-------|-------------|
| **v10.142 (THIS)** | **ENH-131 Product Profitability Intelligence** | **G142 67/161; 138/264 active (52.3%)** |
| v10.143 | ENH-132 Product Lifecycle Management | G142 68/161 |
| v10.144 | ENH-133 Customer Needs & Gap + ENH-134 Competitive Intel | G142 70/161 |
| v10.145 | ENH-135 CVP Builder + ENH-136 Product Ranking + ENH-137 Dynamic Pricing | G142 73/161 |
| v10.146 | ENH-138 AI Recommendation + ENH-139 Bundling + ENH-140 Analytics Dashboard → **MODULE CLOSE + G147 + cockpit + API + G148 UI gate** | G142 76/161; G147 + G148 NEW |

**v10.143 next-up:** ENH-132 Product Lifecycle Management — stage-gate lifecycle with automated gates, approvals, and sunset criteria.

---

## Summary

Phase 1E Product Module is now open. ENH-131 Product Profitability Intelligence is the first of ten engines and ships standalone from products.json + bank-overridable cost-allocation config. The engine surfaces an honest finding — 10 of 16 products loss-making on fully-loaded costs — which is exactly the value the standard was specified to deliver. Phase 1E closes at ~v10.146 with the cockpit + API + UI gate trio under the v10.141 standing norm.

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. Engine self-tests `152/152`. v10.142 tests `24/24 pass`.
