# CHANGELOG v10.39 — RISK ARC OPENS · MARKET RISK FOUNDATION

**Audit:** 128/128 PASS — **121st consecutive clean.**
**Tests:** 871 integration (+33 from v10.38's 838) + 48 self-tests across the 3 new modules (15 + 14 + 19).
**Status:** Risk arc opens. Market Risk foundation ships first — VaR / ES / sensitivities / backtests / risk-factor taxonomy. **5 ENH-MR-* standards activated. 109/252 active.**

---

## Why Market Risk first

Risk arc has many subdomains (Market / Credit / Operational / Liquidity / Settlement). Market Risk goes first because:

1. **It composes naturally with Treasury** (closed at v10.37). IRRBB shocks in `treasury_alm` now have a sensitivity engine to apply them to actual bond positions. The 6 BCBS d368 IRRBB scenarios are first-class objects, not strings in test fixtures.
2. **VaR + Expected Shortfall are foundational** for everything else. Credit RWA frameworks borrow VaR machinery; operational risk uses similar Monte Carlo techniques; liquidity stress testing uses the same stress-scenario machinery.
3. **Pure-stdlib implementation** — `statistics.NormalDist` + `math.exp/log/sqrt`, no scipy. Every χ² critical value is hard-coded with the citation visible in the code. Reviewable by anyone who knows the math; reproducible without a Python package install dance.

## Three new modules

### `utils/market_risk_factors.py` (644 lines, 15 self-tests) — ENH-MR-004

5 `RiskFactorClass` enums (INTEREST_RATE / FOREIGN_EXCHANGE / EQUITY / COMMODITY / CREDIT_SPREAD) × 23 specific `RiskFactor` enums:

- **IR (6):** `IR_KES_GENERIC`, `IR_KES_GOVT`, `IR_KES_INTERBANK`, `IR_USD_GENERIC`, `IR_EUR_GENERIC`, `IR_GBP_GENERIC`
- **FX (6):** `FX_USDKES`, `FX_EURKES`, `FX_GBPKES`, `FX_ZARKES`, `FX_UGXKES`, `FX_TZSKES`
- **Equity (3):** `EQUITY_NSE_GENERIC`, `EQUITY_GLOBAL_DEVELOPED`, `EQUITY_GLOBAL_EMERGING`
- **Commodity (3):** `COMMODITY_OIL`, `COMMODITY_GOLD`, `COMMODITY_AGRICULTURAL`
- **Credit Spread (5):** `CREDIT_SPREAD_KES_AAA`, `_AA`, `_A`, `_BBB`, `_BB_AND_BELOW`

`RISK_FACTOR_TO_CLASS` provides O(1) class lookup. `ShockType` enum: ABSOLUTE_BPS (IR), ABSOLUTE_PCT (crashes), RELATIVE_PCT (FX/equity multiplicative). `FactorShock` and `StressScenario` are frozen dataclasses.

**9 ALL_PREBUILT_SCENARIOS** (per Rule 1, every scenario carries name + description + shocks tuple + framework_refs):

| ID | Description | KES magnitude per BCBS d368 §K |
|---|---|---|
| `BCBS-IRRBB-1` | Parallel up | +200 bp |
| `BCBS-IRRBB-2` | Parallel down | −200 bp |
| `BCBS-IRRBB-3` | Short rates up | +250 bp |
| `BCBS-IRRBB-4` | Short rates down | −250 bp |
| `BCBS-IRRBB-5` | Steepener | short −100 bp / long +100 bp |
| `BCBS-IRRBB-6` | Flattener | short +100 bp / long −100 bp |
| `INT-FX-1` | USD/KES depreciation | +15% |
| `INT-FX-2` | USD/KES appreciation | −10% |
| `INT-EQ-1` | Equity crash | −30% |

`RiskFactorRegistry`: `.get`, `.by_factor_class`, `.by_framework`, `.scenarios`, `.summary`.

### `utils/market_risk_sensitivities.py` (664 lines, 14 self-tests) — ENH-MR-003

Per BCBS d352 FRTB SBM §A.5 + IFRS 7 §40.

| Position type | Constructor signature | Validates |
|---|---|---|
| `BondPosition` | `position_id, factor, notional_kes, modified_duration, convexity=0` | factor is IR; D ≥ 0 |
| `FXPosition` | `position_id, factor, foreign_amount, spot_to_kes` | factor is FX; spot > 0 |
| `EquityPosition` | `position_id, factor, market_value_kes, beta=1.0` | factor is equity |

`SensitivityType`: DELTA / VEGA / CURVATURE / DV01.

**Computation formulas:**

- **DV01:** `D_mod × P × 0.0001` with second-order term `0.5 × convexity × P × Δy²`. For a 1m KES bond at D=7y, DV01 = 700 KES per bp.
- **FX delta:** `foreign_amount × spot × 0.01`. 100k USD at 130 KES/USD → 130,000 KES per 1% move.
- **Equity delta:** `market_value × beta × 0.01`. Beta-adjusted per single-factor model.

`apply_scenario_pnl(sensitivities, shocks)` — signed PnL respecting:
- DV01 + ABSOLUTE_BPS shock: returns `−delta × magnitude` (long bond loses on rate UP)
- DELTA + ABSOLUTE_PCT or RELATIVE_PCT: returns `+delta × magnitude`

A 1m KES bond at D=7y under BCBS-IRRBB-1 (+200bp) produces PnL = −140,000 KES. Verified in integration test.

`aggregate(sensitivities)` produces `SensitivityReport` with `by_factor` + `by_class` (groups by `RiskFactorClass`) + `total_delta_kes`. `per_factor_pnl_contribution` decomposes total PnL.

**Decimal-internal precision throughout.** Constants: `ONE_BP = Decimal("0.0001")`, `ONE_PCT = Decimal("0.01")`.

### `utils/market_risk_var.py` (815 lines, 19 self-tests) — ENH-MR-001 / 002 / 005

Pure stdlib — `statistics.NormalDist` + `math.exp/log/sqrt`, no scipy.

**Hard-coded χ² critical values** (citation visible at the top of the module):

```
_CHI2_1_CRITICAL = {0.10: 2.706, 0.05: 3.841, 0.01: 6.635}
_CHI2_2_CRITICAL = {0.10: 4.605, 0.05: 5.991, 0.01: 9.210}
```

#### ENH-MR-001 — three VaR methodologies

| Method | Implementation |
|---|---|
| **Parametric** | Variance-covariance with Normal returns. `z = NormalDist().inv_cdf(α)`. √T scaling per Basel MRA 1996. |
| **Historical** | Empirical percentile via linear interpolation (numpy default). |
| **Monte Carlo** | Gauss simulation. `n_simulations ≥ 100` enforced. Optional `seed` for reproducibility (`Random(seed)`). Internally calls `historical_var` on simulated returns. |

Confidence levels: 95% (z ≈ 1.645), 97.5% FRTB-IMA (z ≈ 1.96), 99% Basel VaR (z ≈ 2.326).

**Sign convention:** `var_kes` is POSITIVE loss magnitude.

#### ENH-MR-002 — Expected Shortfall (FRTB-IMA)

ES = average of returns in tail beyond VaR.
- Parametric: `ES = φ(z) / (1−α) × σ × √T`
- Historical / Monte Carlo: mean of returns ≤ VaR percentile

ES ≥ VaR by construction (monotonicity). Verified in integration test.

#### ENH-MR-005 — backtests

| Test | Returns | Statistic | Distribution |
|---|---|---|---|
| **Kupiec POF** | unconditional coverage verdict | `LR = −2(log_h0 − log_h1)` | χ²(1) |
| **Christoffersen indep** | breach-clustering verdict | 2×2 transition matrix LR | χ²(1) |

Edge cases handled: x = 0, x = N (Bernoulli LR limit). 3 `BacktestVerdict`: PASS / FAIL / INSUFFICIENT_DATA.

Per Rule 1, every `VaRResult` surfaces methodology + confidence + horizon + portfolio_value + `ReturnDistributionSummary` + framework_refs. Every `BacktestResult` surfaces test_name + significance + n_observations + n_breaches + expected_n_breaches + test_statistic + critical_value + verdict + framework_refs.

## 5 RISK-* scenarios in `scenario_simulator.TREASURY_SCENARIO_LIBRARY`

Library extended 19 → 24:

| ID | What it verifies |
|---|---|
| `RISK-01` | Parametric VaR on N(0, 1%) returns (1000 samples seed=42, PV=1m KES, conf=0.99) → VaR ∈ [20k, 28k], ES ≥ VaR, methodology = PARAMETRIC |
| `RISK-02` | BCBS-IRRBB-1 (+200bp) on 1m bond D=7y → DV01=700, PnL=−140,000 |
| `RISK-03` | Historical/parametric VaR ratio ∈ [0.7, 1.3] for n=2000 normal returns |
| `RISK-04` | Kupiec POF FAIL when 25 breaches in 250 days at 99% (10× expected); LR > 3.841 |
| `RISK-05` | Sensitivity aggregation — IR=500, FX=130000, Equity=50000 across 3 positions |

All 5 scenarios PASS when the 3 modules are wired into `ScenarioRunner(engines=…)`. 12 assertions total all green.

## Standards registry

5 new `ENH-MR-*` activated:

| ID | Title | Severity | Engines |
|---|---|---|---|
| ENH-MR-001 | VaR Computation Framework | HIGH | `market_risk_var` |
| ENH-MR-002 | Expected Shortfall (FRTB-IMA) | HIGH | `market_risk_var` |
| ENH-MR-003 | Sensitivity-Based Measures | MEDIUM | `market_risk_sensitivities` |
| ENH-MR-004 | Risk Factor Taxonomy & Stress Scenarios | MEDIUM | `market_risk_factors` |
| ENH-MR-005 | VaR Backtesting (Kupiec + Christoffersen) | HIGH | `market_risk_var` |

All `subcategory="market_risk"`, `priority_tier="A"`, `implementation_batch="v10.39"`.

**Total active: 109 / 252 standards.**

## Engine Hub Tier 21

Added "Tier 21 — Market Risk Foundation (v10.39+)" with the 3 new modules. Each entry documents the standard implemented + numerical formulas + sign conventions + framework references.

## G128 baseline — STABLE after v10.39

Despite adding 3 modules + 6 new internal imports, the structural audit confirms:

```
Modules scanned: 305 (was 302 in v10.38)
Internal imports: 759 (was 753)
Findings: 56 total
HARD failures: 3 (unchanged from baseline)
Status: STABLE
```

**No new circular imports introduced. No new layer violations.** The anti-entanglement gate from v10.38 is doing its job.

## Honest scope notes

1. **Risk arc not yet closed.** v10.39 ships the *foundation*. More batches needed before Risk arc closes — at minimum: trading book boundary (BCBS d352 §A.4), market risk limits (concentration / VaR limits / breach workflow), credit risk PD/LGD/EAD (separate from Climate's PD overlay), operational risk (RCSA / loss events), liquidity stress testing (composes with treasury_alm).
2. **No live market data wired.** All examples use synthetic returns or hard-coded test inputs. Per Rule 7, the engines accept returns/spots/sensitivities as inputs — they never fetch from external systems. Integration with a market-data provider (Bloomberg / Refinitiv / NSE feed) is a separate workstream and would be flagged `REQUIRES_PROVIDER:market_data_provider`.
3. **No correlation matrix yet.** Parametric VaR uses single-factor assumption (sum of variances). Multi-factor parametric VaR with full correlation matrix is a future enhancement under ENH-MR-006 (not yet planned).
4. **Backtests need real breach data.** The Kupiec / Christoffersen tests work on a `breach_sequence: Sequence[bool]`. Producing this sequence from live VaR forecasts vs realized PnL is a separate workflow (downstream system).
5. **Decimal vs float boundary.** Statistical inputs (returns, percentiles) are float internally for `statistics.NormalDist` compatibility; monetary outputs (var_kes, es_kes, portfolio_value_kes) are Decimal via `Decimal(str(...))` conversion. This is documented in module-level comments.

## Honesty Rule conformance

- **Rule 1.** Every `VaRResult`, `BacktestResult`, `Sensitivity`, `StressScenario` surfaces full triage info — methodology, confidence, horizon, observed values, framework refs. Tests verify presence of `framework_refs` on every prebuilt scenario.
- **Rule 7.** Engines never fetch live data. `apply_scenario_pnl` takes shocks as input; `parametric_var` takes returns as input. Live market data wiring is a future REQUIRES_PROVIDER hookup.
- **Decimal-internal precision** in monetary outputs.

## What ships next — v10.40+

Risk arc continues. Likely sequence (subject to revision):

1. **v10.40 Trading Book Boundary** — BCBS d352 §A.4 boundary classification (TB vs BB allocation per instrument), trading desk concept, regulatory reporting hooks.
2. **v10.41 Market Risk Limits** — concentration limits per RiskFactor + VaR / ES limits + breach workflow (composes with `treasury_agents.PaymentReviewAgent`).
3. **v10.42 Credit Risk Foundation** — PD / LGD / EAD per BCBS d424 IRB framework, expanding beyond v10.6-10 climate-PD overlay.
4. **v10.43 Operational Risk** — RCSA + loss events + Basel SMA capital.

Each batch will:
- Pass all 871+ integration tests
- Pass G128 (no new circular imports / layer violations)
- Add 3-5 RISK-* / CREDIT-* / OPRISK-* scenarios to library
- Get an Engine Hub Tier 22+ entry

**121 consecutive clean batches. 9 closed arcs (Climate · Credit · KESONIA · RMS · Audit/GRC · Model Gov · Virtual Bank · Bandit · Treasury). Risk arc OPEN with Market Risk foundation. 109/252 active. Next: trading book boundary or market risk limits.**
