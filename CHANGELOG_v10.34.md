# CHANGELOG v10.34 — TREASURY ARC BATCH 2

**Audit:** 126/126 PASS — **117th consecutive clean.**
**Tests:** 745 integration (+31 from v10.33's 714) + 56 self-tests across 3 new engines.
**Status:** Treasury arc continues — 6 of 16 standards now active. G127 closure deferred to v10.37.

---

## What v10.34 ships

3 dedicated Cat A modules — each implementing one ENH from the Treasury arc.

### 1. `utils/treasury_products.py` (930 lines, ENH-234)

**Treasury Products Suite** — Oracle/Temenos-class trading-book infrastructure.

| Component | Implementation |
|---|---|
| **Yield curve** | `YieldCurve` with linear interpolation between points + flat extrapolation at endpoints. Monotonic tenor enforcement at construction. `discount_factor` (simple-compounded). Negative tenor evaluations raise ValueError |
| **FX spot MTM** | `mtm_fx_spot` Level 1 fair value (quoted spot). `pnl = sign × notional × (spot - contract)` |
| **FX forward MTM** | `mtm_fx_forward` Level 2 via covered interest parity: `F = S × (1 + r_quote × t) / (1 + r_base × t)`. PnL = `sign × notional × (F_market − F_contract) × DF_quote` |
| **Bond pricing** | `mtm_bond_via_yield` discounts coupon stream + face at YTM. Returns clean + accrued + dirty + market value + valuation_basis. ACT/365 accrued interest. Matured bonds return par |
| **IFRS classification** | 5 IFRS 9 classifications (HFT/AFS/HTM/LAR/DESIGNATED_FVTPL) + IFRS 13 fair value hierarchy (Level 1/2/3) per IFRS 13.72 |
| **Engine** | `TreasuryProductsEngine` with yield curve registry, FX position registry, bond position registry, MTM dispatch by instrument type, net FX exposure aggregation |

### 2. `utils/rwa_optimization.py` (788 lines, ENH-235)

**RWA Optimization & Capital Management** — Pillar 1 Basel III.

| Component | Implementation |
|---|---|
| **SA-CR asset classes** | 25 `AssetClass` enums per Basel III final framework (Dec 2017): SOVEREIGN_DOMESTIC (0%), CORPORATE_UNRATED (100%), MORTGAGE_RESIDENTIAL (35% per CBK PG/03), DEFAULTED (150%), etc. |
| **CCFs** | 5 `CCFCategory` per BCBS final: UNCONDITIONALLY_CANCELLABLE (10%), SHORT_TERM_LC (20%), LONG_TERM_LC (50%), UNDRAWN_COMMITMENT (40%), ON_BALANCE_SHEET (100%) |
| **RWA computation** | `compute_exposure_rwa`: effective_exposure = on_BS + off_BS × CCF − collateral (if secured); rwa = effective × RW%. Capital required = rwa × 8% (Pillar 1 floor) |
| **Capital ratios** | `compute_capital_ratios` with **dual thresholds**: Basel III (CET1 4.5%, T1 6%, Total 8%) + CBK PG/03 (CET1 10.5%, Total 14.5% — Kenya-specific). Headroom CET1% surfaced explicitly |
| **SACCR** | 5 `SACCRAssetClass` per BCBS 282 with supervisory factors (IR 0.5%, FX 4%, credit 0.46%, equity 32%, commodity 18%) + α=1.4 alpha multiplier. EAD = α × (RC + PFE) where RC = max(MTM−collateral, 0) |
| **Engine** | `RWAOptimizationEngine` with exposure registry, RWA computation per exposure, total RWA, RWA by asset class, SACCR EAD per counterparty, capital ratios |

### 3. `utils/fund_transfer_pricing.py` (652 lines, ENH-236)

**Fund Transfer Pricing Enhancement** — matched-maturity FTP + NIM decomposition.

| Component | Implementation |
|---|---|
| **9 product categories** | DEMAND_DEPOSIT · SAVINGS_DEPOSIT · FIXED_DEPOSIT · INTERBANK_BORROWING · LOAN_TERM · LOAN_REVOLVING · BOND_INVESTMENT · UNSECURED_OD · MORTGAGE |
| **Liquidity premium spreads** | DEFAULT_LIQUIDITY_PREMIUM_BPS from 0bps (demand deposit, at-call) to 75bps (unsecured OD, term funding). Per-category bps added to base yield curve |
| **Behavioral tenor fallback** | DEFAULT_BEHAVIORAL_TENOR_YEARS for NMD products without contractual tenor: demand deposit 2y core, savings 3y core, revolving 1y, OD 0.5y |
| **FTP curve construction** | `construct_ftp_curve` from yield curve points + liquidity premium. Empty yield_curve_points raises `REQUIRES_PROVIDER` per Rule 7 |
| **NIM decomposition** | `decompose_nim` separates `lending_margin` (asset rate − FTP, positive = profit) and `funding_margin` (FTP − liability rate, positive = profit for the bank's deposit-taking unit) |
| **Engine** | `FTPEngine` with FTP curve registry, per-product rate computation, NIM decomposition, board-level lending/funding spread aggregation |

## Cross-module composability

The 3 modules compose cleanly with v10.33 + each other:

```
                  v10.33 treasury_alm
                  - IRRBBScenario
                       │ (yield curve fed into IR shocks)
                       ▼
v10.34 treasury_products            v10.34 fund_transfer_pricing
- YieldCurve         ─────────────►  - construct_ftp_curve
- discount_factor                     - FTPCurve

                  v10.34 rwa_optimization
                  - compute_capital_ratios
                       │ (uses RWA from all asset/MTM positions)
```

**Tested:** `TestV1034CrossModuleComposability.test_yield_curve_to_ftp_curve_pipeline` builds a YieldCurve in treasury_products and converts it to an FTPCurve via construct_ftp_curve.

## 3 new standards activated → 93 of 247 active

```
v10.33 ships:    90 active (+ENH-231 +ENH-232 +ENH-233)
v10.34 ships:    93 active (+ENH-234 +ENH-235 +ENH-236)
Treasury arc:    16 standards total → 10 remaining → 3 batches (v10.35-37)
```

## Self-test counts

```
treasury_products:        18 tests (yield curves + FX + bonds + engine)
rwa_optimization:         22 tests (SA-CR + capital ratios + SACCR + engine)
fund_transfer_pricing:    16 tests (FTP curves + NIM + engine)
TOTAL (v10.34):           56 self-tests
```

## Honesty Rule conformance

- **Rule 1.** Every MTM result reports clean_price + accrued + dirty + market value + valuation_basis (e.g., `"forward_via_yield_curve"` / `"matured_at_par"`) + fair_value_level (Level 1/2/3 per IFRS 13). Every RWA result surfaces effective_exposure breakdown + risk_weight + rwa + capital_required_8pct + secured/unsecured + collateral. Every CapitalRatioResult surfaces both Basel and CBK compliance flags + headroom_cet1_pct. Every NIM decomposition surfaces customer_rate + ftp_rate + spread + spread_label.
- **Rule 7.** YieldCurve construction requires explicit points (no fabrication). `construct_ftp_curve` raises `REQUIRES_PROVIDER` if no yield curve points supplied. `mtm_fx_forward` requires both base + quote yield curves. `compute_saccr_ead` requires at least 1 trade. Decimal-internal precision 28 throughout.

## Why no G127 yet

Same as v10.33 — Treasury arc closes at v10.37 with 16/16 standards locked. v10.34 ships 3 more standards toward that target.

## Honest closing notes

1. **126 gates, 745 tests, 117th consecutive clean batch.** Treasury arc 38% complete (6/16).

2. **Bond pricing is stylized.** YTM-based discount with all coupons at single yield is the textbook approach but ignores curve shape. Production banks use bootstrapped zero-curves + scenario revaluation. The current implementation ships the framework; refinement comes when KESONIA + Treasury yield-point feeds wire in.

3. **FX forward uses simple covered interest parity.** Production-grade FX forward valuation accounts for forward points (FRAs), basis swaps, cross-currency basis. Foundation ships interest-parity approximation per textbook BIS guidance. Refinements track real markets.

4. **SACCR PFE is simplified.** Real SACCR uses hedging-set offsets, supervisory delta adjustments, supervisory correlations — full Basel BCBS 282 compute is multi-page. Foundation ships notional × supervisory_factor × maturity_factor approximation; full netting is future work.

5. **Capital buffers not yet enforced.** Capital conservation buffer (2.5%) + countercyclical (0-2.5% CBK-set) + G-SIB surcharge are constants but not used in compute_capital_ratios — only Pillar 1 minima are checked. Buffer enforcement deferred to v10.36 stress arc.

6. **No real-time market data.** All curves require explicit supply. Production needs KESONIA + CBR + FX provider wiring. Per Rule 7, the modules raise REQUIRES_PROVIDER when called without inputs rather than fabricate values.

7. **Coexistence with legacy preserves additive composition.** `risk_weighted_assets.py` (Volume Seven shell, 543 lines) and `capital_adequacy.py` (696 lines) coexist with new `rwa_optimization.py`. Same for `treasury_intelligence.py` legacy + v10.33 `treasury_alm.py` + v10.34 `treasury_products.py`. Mutating prior modules risks unknown breakages.

8. **The 3 v10.34 modules compose cleanly with v10.33.** YieldCurves built in treasury_products feed both IRRBB scenarios in treasury_alm AND FTP curve construction in fund_transfer_pricing. This is the composition discipline that makes the platform extensible.

---

## Phase 2 progress after v10.34

| Arc | Standards | Status |
|---|---|---|
| Climate/ESG | 13/13 | ✅ closed |
| Credit | 19/19 | ✅ closed |
| KESONIA | 1/1 | ✅ closed |
| RMS | 17/17 | ✅ closed |
| Audit/GRC | 17/17 | ✅ closed |
| Model Governance | 7/10 | ✅ closed |
| Virtual Bank | 0 (Cat B) | ✅ closed |
| Cross-Sell Bandit | 1 (ENH-267) | ✅ first ML |
| **Treasury** | **6/16 active** | **🟡 batch 2 shipped** |
| Risk / Trade etc. | 0/108 | pending |

**93 of 247 standards active.** Treasury arc 38% complete.

## What ships next — v10.35

Per planned sequence: ENH-237 AI-Powered Cash Forecasting + ENH-238 Treasury Dashboard & Reporting (2 standards). Then v10.36 Specialized batch (Islamic + Agentic + R-series, 8 standards). Then v10.37 G127 closure.

**117 consecutive clean batches.** Treasury arc 38% complete. Foundation + products + capital + FTP all shipped. Forecasting + dashboard + specialized work remaining.
