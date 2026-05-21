# CHANGELOG v10.75–v10.76 — trade_finance arc batches 5-6 (6/12)

**Status:** Dual batch per standing protocol. ENH-275 Trade Finance Accounting & Integration (v10.75) + ENH-280 Trade Finance Reporting & Analytics (v10.76). Trade finance arc now 6/12 active, closes at v10.80.

**Audit:** 136/136 PASS (unchanged — closure-batch ratchets are batched at v10.80)
**G117:** 99.0% (195/197) (unchanged — same reason)
**G128:** STABLE (342 modules · 875 imports · HARD=3) (+2 modules, +4 imports from new engines)
**Active standards:** 143/260 (was 141; +2 from this drop)
**Scenario library:** 150 (was 142; +8 from this drop — TFA-01..04 + RPT-01..04)
**Engine self-tests:** 142/142 via orchestrator (was 140; +2 from this drop)

---

## Why this dual batch matters strategically

This is the drop where the ML extension contract enters the platform as a first-class architectural pattern. Joshua's standing direction — "ML are training the system to more accuracy as this shall be a major win for us" — gets honored not by smuggling ML into engines that don't need it (ENH-275 Accounting is rules-based and stays deterministic), but by establishing a clean, reusable contract on the engine where ML genuinely improves outcomes (ENH-280 Reporting & Analytics). The pattern established here is the one ENH-270 AI-Powered Document Checking will reuse at v10.77, and the one any future ML-extensible engine plugs into.

The rule-of-thumb the arc now follows: **ML augments diagnostic engines; it does not replace them.** Every engine ships a deterministic or statistical fallback that produces correct, defensible outputs without any model. When a trained ML hook is injected, the engine consumes it and surfaces the upgrade with full provenance. When the hook is absent — or fails — the fallback runs and the operator sees `ml_disabled=True` so they know which path produced each finding. This honors Rule 6 (explicit disclosure of fallback usage) and Rule 7 (operator adjudicates; engine never auto-acts on predictions) without compromising the accuracy ceiling that real ML can reach.

## v10.75 — ENH-275 Trade Finance Accounting & Integration (deterministic)

**Module:** `utils/trade_finance_accounting.py` (~880 lines, 20/20 tests pass)

Diagnostic IFRS 9 + IAS 37 + Basel III accounting engine consuming `TradeInstrument` from ENH-269. Five capabilities, all deterministic — accounting and capital adequacy are rules-based, ML adds no accuracy here:

1. **`compute_ccf`** — Basel III Credit Conversion Factor lookup by 6 `BaselCcfBucket` (DOCUMENTARY_LC_SHORT 0.20, DOCUMENTARY_LC_LONG 0.50, SBLC_GUARANTEE 1.00, PERFORMANCE_BG 0.50, DOC_COLLECTION 0.20, CLEAN_COLLECTION 0.00) per CBK PG/04 + Basel III CRE 22.20-30. Partial-draw aware: for LC and DOC_COLLECTION, only the undrawn notional × CCF feeds the credit equivalent (drawn portion is on-balance-sheet receivable). Bucket override accepted so the operator can promote a payment guarantee from PERFORMANCE_BG (0.50) to SBLC_GUARANTEE (1.00) when discretion calls for it.

2. **`compute_capital_impact`** — applies caller-supplied `risk_weight` (validated 0..1.5) to credit equivalent → RWA → 8% Basel minimum capital required. Per Rule 7, risk weights are operator-set per CBK / Basel discretion; the engine never derives them.

3. **`generate_journal_template`** — IFRS 9 §5.5 + IAS 37 §10 + IFRS 15 journal templates per 7 `JournalEvent`: ISSUE (4 lines: contingent DR/CR + fee DR/CR), DRAWDOWN (4 lines: receivable + cash + contingent reversal), EXPIRE (2 lines: contingent reversal), CANCEL (identical to EXPIRE), AMEND_INCREASE (delta posting), AMEND_DECREASE (delta reversal), FEE_RECOGNITION (standalone fee accrual). 6 `AccountClass` × 2 `JournalSide`. `JournalLine` rejects negative `amount_kes` at construction — sign is carried by side.

4. **`validate_journal_balance`** — confirms DR sum == CR sum across templates; 3 `BalanceCheckOutcome` (BALANCED / UNBALANCED / EMPTY) with explicit `difference_kes` surfaced for triage.

5. **`build_off_balance_sheet_disclosure`** — IAS 37 disclosure helper. Counts only active states (ISSUED / AMENDED / ACTIVE); excludes EXPIRED / CANCELLED / SETTLED so the disclosure doesn't double-count cleared exposures. Returns notional + contingent + credit equivalent + by-instrument-type rollup.

**Per Rule 7, engine NEVER:** posts journals to GL (operator approves + posts via core banking workflow); updates capital ratios in GL; modifies risk weights; submits regulatory capital returns (cbk_regulatory_reporting territory); mutates inputs.

## v10.76 — ENH-280 Trade Finance Reporting & Analytics (ML-extensible)

**Module:** `utils/trade_finance_reporting.py` (~1080 lines, 21/21 tests pass)

Diagnostic reporting + analytics engine with optional ML extension hooks for accuracy improvement over time. Six capabilities — four deterministic, two ML-extensible:

1. **`compute_trade_volumes`** — deterministic aggregation by period × instrument type × counterparty × country. Beneficiary-side country attribution via caller-supplied map; missing entries tagged `UNKNOWN` (transparent rather than silent).

2. **`compute_country_exposure`** — Herfindahl-Hirschman Index Σ(share²) on per-country exposure for active instruments only. Three-tier `ConcentrationSeverity`: DIVERSIFIED (HHI ≤ 0.15) / MODERATE (0.15–0.25) / CONCENTRATED (> 0.25). Top-3 and top-5 share also surfaced.

3. **`compute_sector_concentration`** — applicant-side sector HHI + top-3 share + severity.

4. **`detect_volume_anomalies` — ML-EXTENSIBLE.** Statistical fallback uses Modified Z-score on log-volume per Iglewicz & Hoaglin 1993 with median absolute deviation (MAD) — chosen specifically because outlier-resistance prevents anomalies from suppressing their own scores, which a naive mean+stdev approach would do. Saturated to [0,1]. Three-tier `AnomalySeverity` at thresholds 0.50 (WATCH) and 0.75 (ALERT). Series shorter than 4 periods returns no findings (insufficient sample); flat series returns no findings (no detectable variance).

5. **`forecast_volume_trajectory` — ML-EXTENSIBLE.** Statistical fallback uses Ordinary Least Squares regression on the most recent 12 periods. Negative-value clipping (volumes can't be negative). Horizon validated 1..36; > 36 rejected by policy (unreliable for any method, ML or statistical). Series shorter than 3 periods returns flat last-observation forecast.

6. **`build_management_report`** — orchestrator returning `ManagementReport` with all 5 outputs + `overall_ml_disabled` aggregation flag (True if any analytical path used the statistical fallback).

### The ML extension contract

This is the architectural anchor of v10.76. Every future ML-augmented engine in the platform will follow this same pattern:

```python
class TradeFinanceReportingEngine:
    def __init__(
        self,
        ml_anomaly_scorer: Optional[
            Callable[[Sequence[Decimal]], Sequence[float]]] = None,
        ml_forecaster: Optional[
            Callable[[Sequence[Decimal], int],
                     Sequence[Decimal]]] = None,
    ):
        ...
```

Three properties of this contract that matter:

**Graceful failure.** When an injected hook raises an exception or returns wrong-length output, the engine catches the failure, falls back to the statistical method, and surfaces `ml_disabled=True` plus a fallback note explaining what failed. The platform never crashes because a model is unavailable. RPT-02 + RPT-03 + the failure-fallback unit tests cover all three states (no hook, hook present, hook broken).

**Provenance always surfaced.** Every `AnomalyFinding` and every `VolumeForecast` carries an `AnalysisMethod` enum value (DETERMINISTIC / STATISTICAL_FALLBACK / ML_INJECTED) and a boolean `ml_disabled`. The operator looking at a flagged anomaly always knows which path produced the finding. Per Rule 6, this is non-negotiable — fallback usage is disclosed, not hidden.

**Caller-injectable, training-pipeline-agnostic.** The engine accepts plain Python callables. Whatever produces those callables — sklearn, pytorch, an internal training pipeline, or even a hand-coded heuristic during prototyping — is invisible to the engine. This means the model lifecycle (data collection → training → evaluation → versioning → drift monitoring → deployment) lives in separate infrastructure that this engine consumes. Until that infrastructure exists, statistical fallback runs and `ml_disabled=True` everywhere; when it exists, models slot in as one-line constructor injections.

### Path to accuracy improvement

For Joshua's "major win" framing, the concrete steps from "no ML" to "trained ML improving accuracy" are:

1. **Today (this drop):** statistical fallback runs in production. Every output carries `ml_disabled=True`. Operators see fallback findings and adjudicate them. Adjudication outcomes form the supervised training signal for the next stage.

2. **Phase 1 — data collection:** scenario library + production adjudication history accumulate (period_total → was_truly_anomaly) and (history_window → actual_realized_value) pairs. The 8 new scenarios in this drop are deliberately ground-truth-anchored so they double as evaluation cases.

3. **Phase 2 — training pipeline (separate infrastructure, not this engine):** rolling-window training on the accumulated supervised pairs. Holdout evaluation against the ground-truth scenarios. Drift detection. Model versioning + serialization. The platform's existing `audit_log` discipline gives auditable training data; the existing `STANDARDS_REGISTRY` framework_refs give documented evaluation cases.

4. **Phase 3 — model injection:** at engine construction time, scoring/forecasting models inject as callables. `ml_disabled=False` starts appearing in outputs. Operators compare ML findings against the same statistical fallback (now run in shadow mode for ongoing comparison) and confirm or reject the upgrade.

5. **Phase 4 — continuous improvement:** new adjudications feed back into training. Drift detection triggers retraining. Models version up; `model_version` becomes a future field on `AnomalyFinding`.

The engine code itself doesn't change across these phases — only what's passed in at construction. That's the win the contract delivers: **the production engine ships today and gets more accurate over time without any code changes.** ENH-270 AI-Powered Document Checking at v10.77 will use this same contract for document discrepancy classification.

**Per Rule 7, engine NEVER:** acts on anomaly findings (operator adjudicates each); submits regulatory reports; publishes management dashboards (cockpit consumes); retrains models in-place (training is separate infrastructure); mutates inputs.

## 8 new scenarios (TFA-01..04 + RPT-01..04)

Wired into `TREASURY_SCENARIO_LIBRARY`. All 8 pass with 32/32 assertions:

- **TFA-01** capital impact — 1m short LC × CCF 0.20 = 200k credit equiv × 100% RW × 8% = 16k capital required
- **TFA-02** journal lifecycle — ISSUE (4 lines) + DRAWDOWN (4 lines) + EXPIRE (2 lines), all balance
- **TFA-03** unbalanced detection — DR 1000 / CR 900 → UNBALANCED, difference 100 KES surfaced exactly
- **TFA-04** off-balance-sheet disclosure — 3 instruments, EXPIRED excluded, credit equivalent 1.2m
- **RPT-01** volumes + country HHI = 0.5 → CONCENTRATED severity
- **RPT-02** statistical fallback anomaly detection — 10x spike against 9 normal periods, `ml_disabled=True` surfaced in every finding
- **RPT-03** ML hook injected — fake scorer returns 0.95 for all periods → 5 ALERT findings, `ml_disabled=False`, method=ML_INJECTED, score 0.95 surfaced exactly
- **RPT-04** management report orchestrator — 8-period linear history → OLS forecast ~9m next period, `overall_ml_disabled=True` (no hooks injected)

RPT-02 + RPT-03 are the pair that prove the ML contract: the same scenario surface, two different injection states, two different `method` values, two different `ml_disabled` flags. This is the reference implementation any future ML-extensible engine should mirror.

## Tier 28 expansion (`pages/7_admin.py`)

Tier 28 label updated: `(v10.70-v10.76, in flight, closes vTBD)`. Two new entries appended after `trade_finance_compliance`:
- `trade_finance_accounting` / `TradeFinanceAccountingEngine` — full description
- `trade_finance_reporting` / `TradeFinanceReportingEngine` — full description with ML extension contract noted

Tier 28 now has 6 of 12 expected entries. Closure batch v10.80 adds full descriptions for the remaining 6 (ENH-270, ENH-271, ENH-276, ENH-278, ENH-279 deferred-to-mobile-stack, plus the closure cockpit `pages/97_trade_finance_arc_cockpit.py`).

## Files changed in this drop

- **NEW** `utils/trade_finance_accounting.py` (~880 lines, 20 tests)
- **NEW** `utils/trade_finance_reporting.py` (~1080 lines, 21 tests, ML hook contract)
- **MOD** `utils/standards_registry.py` (ENH-275 + ENH-280 activated, comprehensive descriptions)
- **MOD** `utils/scenario_simulator.py` (8 new scenarios + library wiring)
- **MOD** `pages/7_admin.py` (Tier 28 +2 entries, label v10.70-v10.76)
- **NEW** `CHANGELOG_v10.75_to_v10.76.md` (this file)

## Trade finance arc state

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-269 | trade_finance_instruments | v10.70 | active |
| ENH-273 | trade_finance_limits | v10.71 | active |
| ENH-272 | trade_finance_swift | v10.72 | active |
| ENH-274 | trade_finance_compliance | v10.73 | active |
| ENH-275 | trade_finance_accounting | **v10.75** | **active** |
| ENH-280 | trade_finance_reporting | **v10.76** | **active** |
| ENH-278 | (sustainable trade finance) | v10.77 | next |
| ENH-270 | (AI document checking) | v10.77 | next — uses ML contract from ENH-280 |
| ENH-271 | (corporate trade portal) | v10.78 | queued — split implementation candidate |
| ENH-276 | (multi-bank connectivity) | v10.78 | queued — diagnostic adapter surface |
| ENH-279 | (mobile app) | v10.79 | scope review — mobile UI not diagnostic-engine pattern |
| (closure) | trade_finance_arc_cockpit | v10.80 | closure batch |

6 of 12 active. Closure batch v10.80 ships the cockpit page + G137 + G138 ratchets + remaining Tier 28 expansions + Master Prompt update. **Trade finance becomes the 14th closed arc at v10.80.**

## What's next

v10.77 dual batch: ENH-278 Sustainable Trade Finance + ENH-270 AI-Powered Document Checking. ENH-270 is where the ML contract from this drop earns its keep — document discrepancy classification is exactly the kind of pattern-recognition task that ML genuinely improves. The engine ships with a heuristic rule-based fallback; an injected ML classifier raises accuracy without code change to the consuming surfaces.
