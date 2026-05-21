# CHANGELOG v10.35 — TREASURY ARC BATCH 3 (FORECASTING + DASHBOARD)

**Audit:** 126/126 PASS — **118th consecutive clean.**
**Tests:** 768 integration (+23 from v10.34's 745) + 34 self-tests across 2 new engines.
**Status:** Treasury arc continues — **8 of 16 standards now active = 50% milestone.** G127 closure deferred to v10.37.

---

## What v10.35 ships

2 dedicated Cat A modules implementing ENH-237 + ENH-238.

### 1. `utils/cash_forecasting.py` (870 lines, ENH-237 — 19 self-tests)

**13-week treasury cash flow projection per Basel BCBS 144 + CBK PG/16.**

Three composed components surface separately per Rule 1:

| Component | Implementation |
|---|---|
| **(1) Deterministic** | `ScheduledCashFlow` with 9 `FlowDriver` enums (BOND_MATURITY / BOND_COUPON / LOAN_AMORTIZATION / LOAN_DISBURSEMENT / FD_ROLLOVER / INTERBANK_SETTLEMENT / FX_SETTLEMENT / SCHEDULED_PAYMENT / OTHER_SCHEDULED). Aggregated per target date with driver breakdown |
| **(2) Seasonal** | `SeasonalityModel` fit from history (min 30 days). Day-of-week multipliers (0=Mon … 6=Sun) + day-of-month bucket multipliers (BEGIN/MID/END) + overall mean + stdev. Multiplier per date = DoW × DoM bucket |
| **(3) Baseline** | `exponential_smoothing_baseline` Holt-Winters lite: `s_t = α × x_t + (1−α) × s_{t-1}` with α=0.3 default. Validates α ∈ [0,1] |

**Forecast composition:** `total = deterministic + (baseline × seasonality_multiplier)`. Confidence bands: `total ± Z × σ` where Z_80%=1.28, Z_95%=1.96.

**ML overlay (per Rule 7):** `ml_provider` is a callable hook. `forecast_with_ml_overlay()` raises `ValueError("REQUIRES_PROVIDER: ml_forecast_provider")` if no provider wired. When wired, ML rates per-day overlay the seasonality estimate; deterministic + bands remain unchanged. Every `ForecastResult.ml_overlay_applied` flag tells consumers which path was taken.

### 2. `utils/treasury_dashboard.py` (755 lines, ENH-238 — 15 self-tests)

**Aggregator composing all 5 upstream Treasury arc engines.**

| Component | Implementation |
|---|---|
| **4 ReportType enums** | DAILY_TREASURY (today's positions + ratios + near-term forecast) · BOARD_PACK (monthly ALCO/Risk-Cmtte aggregation) · REGULATORY_PACK (CBK PG/16 + PG/03 + IRRBB structured per CBK submission) · INTRADAY_LIQUIDITY |
| **4 SectionStatus enums** | OK / WARNING (within proximity of threshold) / BREACH (limit exceeded) / NO_DATA (upstream engine empty). Worst-of roll-up across all sections gives `overall_status` |
| **6 section builders** | `build_alm_lcr_section` (LCR per BCBS 188) · `build_alm_nsfr_section` (NSFR per BCBS 295) · `build_irrbb_outlier_section` (15% Tier 1 outlier per BCBS 368) · `build_capital_ratios_section` (dual Basel + CBK PG/03 thresholds) · `build_fx_exposure_section` (per-currency net exposure) · `build_nim_section` (FTP lending + funding margins) · `build_cash_forecast_section` (13-week net position) |
| **CBK regulatory pack** | Section IDs use `cbk_pg_16_lcr` / `cbk_pg_16_nsfr` / `cbk_pg_03_capital` / `cbk_irrbb_outliers` namespacing for direct CBK submission mapping |

**Honest wiring:** Engines wire as constructor arguments — all optional. Unwired engines produce sections marked NO_DATA cleanly without errors. The dashboard never invents data.

## Cross-module composability — Treasury arc fully integrated

```
v10.33 treasury_alm ─┐
v10.34 treasury_products ─┐
v10.34 rwa_optimization ─┼──► v10.35 treasury_dashboard
v10.34 fund_transfer_pricing ─┘
v10.35 cash_forecasting ─┘
```

`TestV1035DashboardWithLiveEngines.test_full_stack_board_pack` wires real instances of all 5 upstream engines and verifies the board pack contains all 6 expected sections (alm_lcr, alm_nsfr, irrbb_outliers, capital_ratios, nim, cash_forecast).

## 2 standards activated → 95 of 247 active

```
v10.34 ships:    93 active
v10.35 ships:    95 active (+ENH-237 +ENH-238)
Treasury arc:    16 standards total → 8 remaining → 2 batches (v10.36, v10.37)
```

## Honesty Rule conformance

- **Rule 1.** Every `ForecastResult` reports deterministic + baseline + seasonality_multiplier + statistical + total + 80%/95% bands + drivers_summary. Every `DashboardSection` reports source_engine + status + metrics + thresholds + headroom. Limit breaches surface specific numerator/denominator/threshold for examiner trace.
- **Rule 7.** `ml_forecast_provider` is hookable. Without wiring, `forecast_with_ml_overlay()` raises `REQUIRES_PROVIDER`. Dashboard never invents data — unwired upstream engines yield NO_DATA sections cleanly. Decimal-internal precision 28 throughout.

## Why no G127 yet

Same as v10.33 + v10.34. Treasury arc closes at v10.37 with G127 locking 16/16 standards.

## Honest closing notes

1. **126 gates passing; 95 standards active; 118th consecutive clean batch.** Treasury arc 50% complete (8/16). Foundation + products + capital + FTP + forecasting + dashboard all shipped. Specialized work + closure remain.

2. **Forecasting is foundation-grade, not production ML.** Three honest components: (a) deterministic (scheduled flows from known instruments) — high confidence, (b) seasonality (day-of-week + day-of-month from historical fit) — moderate confidence, (c) exponential smoothing baseline — moderate confidence on stationary patterns. Combined accuracy is decent for short horizons (1-2 weeks) but degrades over the 13-week window without an ML overlay. Production banks layer Prophet, LSTM, or foundation-model providers via the `ml_provider` hook.

3. **No statistical residual analysis yet.** Confidence bands use the seasonality model's overall stdev. Production ML adds: residual heteroscedasticity, day-of-week-specific volatility, and out-of-sample backtesting. Foundation ships the framework; refinement comes when CBS data + observed-vs-forecast feedback wire in.

4. **Day-of-week + day-of-month bucket seasonality is coarse.** Production banks model per-month + holiday effects + payday peaks (15th + month-end). Foundation ships 2-dimensional seasonality (DoW × DoM bucket); finer modeling is deferred.

5. **Dashboard uses simple worst-of status roll-up.** A single BREACH dominates regardless of severity or section weight. Production dashboards apply weighted aggregation (regulatory ratios > internal metrics) + decay (recent breaches matter more than old). Foundation ships the simpler model; refinement deferred.

6. **CBK regulatory submission format is layout-only.** `generate_regulatory_pack` produces the right section IDs and fields per CBK PG/03 + PG/16 conceptually but does not generate the actual XML/Excel templates CBK accepts. Production ships templates per the CBK supervision technology guide; foundation ships the underlying data.

7. **The 5 upstream engines compose cleanly.** Wiring is optional and additive. The dashboard never mutates upstream engines — it only reads their `board_summary()` methods (which are the public contract). This means the dashboard works equally well with stubs (for testing) and with the live full stack.

---

## Phase 2 progress after v10.35

| Arc | Standards | Status |
|---|---|---|
| Climate/ESG | 13/13 | ✅ closed |
| Credit | 19/19 | ✅ closed |
| KESONIA | 1/1 | ✅ closed |
| RMS | 17/17 | ✅ closed |
| Audit/GRC | 17/17 | ✅ closed |
| Model Governance | 7/10 | ✅ closed |
| Virtual Bank | 0 (Cat B) | ✅ closed |
| Cross-Sell Bandit | 1 | ✅ first ML |
| **Treasury** | **8/16 active = 50%** | **🟡 batch 3 shipped** |
| Risk · Trade · IT etc. | 0/152 | pending |

**95 of 247 standards active.** Treasury arc 50% complete.

## What ships next — v10.36

Per planned sequence: ENH-239 Islamic Treasury Products + ENH-240 Agentic Treasury Orchestration (Kyriba TAI-class) + ENH-TRS-R1 through R6 (8 standards covering 9900+ bank connections, stablecoin/digital asset integration, MMF direct access, MX.3 cross-asset platform, real-time API ERP-to-bank journey, climate-adjusted treasury risk limits). Then v10.37 G127 closure.

**118 consecutive clean batches.** Treasury arc 50% complete. Foundation + products + capital + FTP + forecasting + dashboard all shipped. Specialized work + closure remaining.
