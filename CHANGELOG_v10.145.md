# CHANGELOG v10.145 — ENH-134 Competitive Intelligence for Products

**Status:** **PHASE 1E PRODUCT 4/10 ACTIVE.** Fourth engine of the Product Module — direction-aware competitive position classification across 8 Kenya peer banks with bank-level metric benchmarking.

**Audit:** `Score: 146/146 gates = 100.0% — PASS` (quoted from `python scripts/audit.py`). No new gate; engine-level drop. **G142 anti-drift floor 69 → 70**. Engine self-tests 152/152. v10.145 tests 29/29 pass.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/product_competitive_intel.py` | ~530 | NEW. ProductCompetitiveIntelligence with 6 public methods + frozen CompetitorLandscape dataclass |
| `data/product_competitor_mapping.json` | ~30 | NEW seed. Per-product → competitor benchmark mapping with explicit unmapped[] |
| `utils/standards_registry.py` | +1 line | ENH-134 status flipped planned → active |
| `pages/7_admin.py` | +28 lines | Tier 4B extended with fourth engine entry |
| `tests/test_product_v10_145.py` | ~310 | NEW. 29 tests across 11 classes |
| `docs/Master_Prompt_v3.38.md` | ~1100 | Anti-drift sync v3.37 → v3.38 |
| `SCOPE_LEDGER.md` | updated | v10.145 row + status block + cross-engine finding |
| `CHANGELOG_v10.145.md` | this file | This document |

---

## The engine — `utils/product_competitive_intel.py`

Per Continuation.docx Standard #134: "Automated competitive monitoring and benchmarking."

### What it reads

- `data/competitor_data.json` (existing) — 9 Kenya banks (KCB, Equity, Co-op, NCBA, Stanbic, Absa, DTB, Family, Ecobank) with:
  - bank-level metrics (assets, loans, deposits, NPL %, CAR %, NIM %, ROE %, branches, mobile users)
  - lending rates by product type (Personal Loan, Business Loan, Mortgage, Asset Finance)
  - deposit rates by tenor (Savings, 3M Fixed, 6M Fixed, 12M Fixed)
  - market share percentages
- `data/products.json` (existing) — our 16 products with `rate_avg`
- `data/product_competitor_mapping.json` (NEW seed) — bank-curated mapping table

### Direction-aware position classification

The standard's value depends on getting direction right. For lending products, **lower rates win** (acquisition logic — undercut peers). For deposits, **higher rates win** (attraction logic — outpay peers). The engine encodes this asymmetry explicitly:

```
Lending:   our_rate ≤ peer_median - 50bps  →  LEADER
           peer_median - 50 < our_rate < peer_median + 50  →  FOLLOWER
           our_rate ≥ peer_median + 50bps  →  LAGGARD

Deposits:  our_rate ≥ peer_median + 50bps  →  LEADER
           peer_median - 50 < our_rate < peer_median + 50  →  FOLLOWER
           our_rate ≤ peer_median - 50bps  →  LAGGARD
```

The 50bps threshold is `LEADER_THRESHOLD_PCT = Decimal("0.5")` — bank-overridable via constructor.

### Public methods

- `get_competitor_landscape(product_id)` → `CompetitorLandscape` (frozen) with our_rate / peer_median / peer_min / peer_max / n_peers / delta_vs_median_bps / position / per_peer_rates
- `compare_pricing(product_id)` — ranked list of all banks (asc for lending, desc for deposits) with `our_rank` position
- `get_market_position(product_id)` — lightweight position summary
- `get_peer_benchmarks(metric)` — bank-level metric comparison for any field in competitor_data.banks (npl_pct, car_pct, roe_pct, nim_pct, etc.)
- `identify_pricing_gaps(threshold_pct)` — sorted list of products outside threshold with explicit `direction` label (`we_charge_more`, `we_charge_less`, `we_pay_more`, `we_pay_less`)
- `get_competitive_summary()` — bank-wide LEADER/FOLLOWER/LAGGARD/NO_DATA counts + leadership_rate_pct + lag_rate_pct

### Mapping seed — what's covered

`data/product_competitor_mapping.json` maps:

- **Lending** (9 products): P001 Personal Loans → "Personal Loan"; P002 Mortgage → "Mortgage"; P003 Asset Finance → "Asset Finance"; P004 Salary Advance → "Personal Loan" (closest analogue); P005-P009 → "Business Loan"
- **Deposits** (2 products): P013 Savings → "Savings"; P014 Fixed Deposits → "12M Fixed"
- **Unmapped** (5 products with explicit reasons): P010 Trade Finance LC, P011 Import Finance (trade finance pricing not in public dataset); P012 Current Accounts (no-interest); P015 Bancassurance, P016 Digital Finance (proprietary fee pricing)

The unmapped[] array is the honesty discipline — operators see WHY a product has no benchmark, not a silent NO_DATA. They can extend the mapping over time as more competitor data becomes available.

---

## Self-test on real data — coherent cross-engine finding

`python -m utils.product_competitive_intel`:

```
Portfolio competitive position: LEADER=9 FOLLOWER=2 LAGGARD=0 NO_DATA=5 of 16
  leadership_rate=56.25% lag_rate=0.0%

P001 Personal Loans: us=14.5% peer_median=18.25% Δ=-375bps → LEADER (n=4)
P002 Mortgage Finance: us=12.0% peer_median=14.75% Δ=-275bps → LEADER (n=4)
P005 Business Loans: us=13.5% peer_median=16.75% Δ=-325bps → LEADER (n=4)
P010 Trade Finance LC: no_competitor_benchmark
P013 Savings Accounts: us=3.5% peer_median=3.625% Δ=-13bps → FOLLOWER (n=4)
P014 Fixed Deposits: us=10.0% peer_median=12.0% Δ=-200bps → LAGGARD (n=4)

Pricing gaps (|Δ|≥30bps): 10
  P009 Corporate Loans: Δ=-525bps (we_charge_less) → LEADER
  P001 Personal Loans: Δ=-375bps (we_charge_less) → LEADER
  P005 Business Loans: Δ=-325bps (we_charge_less) → LEADER
  P002 Mortgage Finance: Δ=-275bps (we_charge_less) → LEADER
  P014 Fixed Deposits: Δ=-200bps (we_pay_less) → LAGGARD

npl_pct: us=11.0 peer_median=9.0 (n_peers=8)
car_pct: us=18.2 peer_median=19.6 (n_peers=8)
roe_pct: us=13 peer_median=16.5 (n_peers=8)
nim_pct: us=7.8 peer_median=7.55 (n_peers=8)
```

### Cross-engine reading (combined with ENH-131)

Both engines surface a coherent portfolio picture:

- **ENH-131 P&L** (v10.142): 10 of 16 products loss-making on fully-loaded costs. Lending categories (Retail, SME, Trade Finance) all negative.
- **ENH-134 competitive position**: 9 of 16 products are price LEADERS, undercutting peer median by 175-525 bps. Fixed Deposits is the lone LAGGARD (we pay 10% vs peer 12% — `we_pay_less`). Bank-level: NPL 11% vs peer 9%, ROE 13% vs peer 16.5%.

Together, the picture is: **Eco Bank competes on price but lags on operational metrics.** Whether this is a deliberate market-share strategy (gain customers via cheaper rates, accept lower margins short-term) or operational drift (we just charge less because we always have) is a strategic call. The engines don't prescribe — they surface the evidence.

---

## Honesty discipline

- **Engine NEVER fabricates competitor rates.** Products without a mapping in `product_competitor_mapping.json` return `status="no_competitor_benchmark"` with the explicit reason from the unmapped[] entry.
- **Peer median EXCLUDES our own bank.** `OUR_BANK_KEY="Ecobank"` removed from the peer set before computing median, so we don't influence our own benchmark.
- **`is_estimate=True` flag** when `n_peers < MIN_PEERS_FOR_ROBUST_MEDIAN` (default 3). Operators see when a benchmark is thin.
- **Direction-aware classification** handles the lending-vs-deposits asymmetry explicitly. The `direction` label on pricing gaps (we_charge_more / we_charge_less / we_pay_more / we_pay_less) makes the actionable side obvious — operators don't have to interpret the sign of `delta_vs_median_bps`.
- **Snapshot honesty** — competitor_data.json carries `as_at` date; engine reports the snapshot it sees, never extrapolates competitor moves or predicts peer pricing changes.
- **Read-only contract.** Never writes.

---

## Tests — `tests/test_product_v10_145.py`

29 tests across 11 classes:

- **TestEngineModule** (4) — exists / parses / class+dataclass present / 6 required methods
- **TestLandscape** (4) — lending product / deposit product / unmapped product fallback / unknown product
- **TestPositionDirectionality** (5) — lending lower=leader / deposits higher=leader / deposits lower=laggard / lending higher=laggard / within threshold=follower
- **TestComparePricing** (4) — lending sorted ascending / deposits sorted descending / unmapped not_ok / us-marker present and unique
- **TestPeerBenchmarks** (2) — npl_pct returns real data with robust n_peers / unknown metric fallback
- **TestPricingGaps** (2) — gaps include direction labels / higher threshold returns subset
- **TestSummary** (1) — summary components add up to total
- **TestMapping** (2) — mapping seed exists+parses / unmapped entries have reasons
- **TestRegistryAndAdmin** (3) — ENH-134 active / prior Phase 1E engines (131/132/133) still active / admin Tier 4B has all four
- **TestNoRegression** (2) — audit gates intact / strategy module engines still active

All 29 pass via inline runner.

---

## Apply order

After v10.144:

```
1. utils/product_competitive_intel.py      → utils/
2. data/product_competitor_mapping.json    → data/
3. utils/standards_registry.py             → utils/   (ENH-134 flip)
4. pages/7_admin.py                        → pages/   (Tier 4B extension)
5. tests/test_product_v10_145.py           → tests/
6. docs/Master_Prompt_v3.38.md             → docs/
7. SCOPE_LEDGER.md                         → root
8. CHANGELOG_v10.145.md                    → root
```

`git add -A && git commit -m "v10.145 ENH-134 Competitive Intelligence for Products — Phase 1E 4/10"`. Then `python scripts/audit.py` should print `Score: 146/146 gates = 100.0% — PASS`.

---

## Phase 1E Product trajectory

| drop | scope | status |
|---|---|---|
| v10.142 | ENH-131 Product Profitability Intelligence | SHIPPED |
| v10.143 | ENH-132 Product Lifecycle Management | SHIPPED |
| v10.144 | ENH-133 Customer Needs & Gap Analysis | SHIPPED |
| **v10.145 (THIS)** | **ENH-134 Competitive Intelligence for Products** | **SHIPPED** |
| v10.146 | ENH-135 CVP Builder | next |
| v10.147 | ENH-136 Product Ranking & Scoring | |
| v10.148 | ENH-137 Dynamic Pricing | |
| v10.149 | ENH-138 + ENH-139 + ENH-140 → MODULE CLOSE + G147 + cockpit + G148 UI gate | |

**v10.146 next-up:** ENH-135 Customer Value Proposition (CVP) Builder. Will consume ENH-133's customer needs catalogue and ENH-134's competitive position to draft per-segment value propositions. First Phase 1E engine that synthesizes multiple prior engines into a forward-looking artifact.

---

## Summary

ENH-134 ships direction-aware competitive position classification across 8 Kenya peer banks plus bank-level metric benchmarking. The honest finding from combining this engine with ENH-131 — we lead on lending price but lag on operational metrics (NPL, ROE) — is exactly the kind of cross-engine signal that informs portfolio strategy decisions for Eco Bank. Phase 1E now 4/10. Total active 141/264 (53.4%).

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. v10.145 tests `29/29 pass`.
