# CHANGELOG v10.20 — RMS Arc Batch 3: Specialized Reconciliation

**Audit:** 121/121 PASS — **103rd consecutive clean.**

## What ships in v10.20

`utils/reconciliation_specialized.py` — 1045 lines, **Cat A**. 4 of 17 RMS standards active:

| Standard | Implemented as |
|---|---|
| **ENH-185** CBK Regulatory Reconciliation | `CBKReturnType` enum (15 returns: CRR, LR, RAR, CAR_TIER1, LCR, NSFR, LEVERAGE_RATIO, DAILY/WEEKLY/MONTHLY/QUARTERLY_RETURN, LARGE_EXPOSURES, CONNECTED_LENDING, AML_CTR/STR, FOREX_RETURN); `DEFAULT_RETURN_DEADLINE_DAYS` per type (1d for daily/AML-STR, 7d for weekly/AML-CTR, 15d for monthly/RAR/LCR/NSFR, 21d for quarterly, 30d for connected lending); `ReturnStatus` enum (6 states); `DeadlineSeverity` enum (OK ≥3d, AMBER ≤3d, RED ≤1d, BREACHED past); `compute_return_deadline()` + `CBKReturnRecord` with severity tracking |
| **ENH-186** Nostro/Vostro Reconciliation | `CorrespondentAccountType` enum (NOSTRO/VOSTRO/LORO); `SwiftMessageType` enum (MT940/942/950/900/910 + MX camt.052/053/054); `StaleAgeBucket` enum (FRESH_0_30, AGING_31_60, OVERDUE_61_90, BREACH_91_PLUS — per CBK CRMF §6.4); `NostroVostroAccount` with `variance_kes()` + `variance_pct()`; `StaleItem` with aging; `compute_fx_reval()` for FX revaluation explaining variance |
| **ENH-187** Intercompany & Internal Suspense | `IntercompanyEntityType` enum (5 types: SUBSIDIARY, BRANCH, ASSOCIATE, JV, HEAD_OFFICE); `IntercompanyCounterparty` with tolerance-based `is_in_balance()`; `SuspenseCategory` enum (9 categories: CHEQUES_IN_CLEARING, DEBIT_CARD_DISPUTES, UNAPPLIED_RECEIPTS, etc.); `DEFAULT_SUSPENSE_MAX_AGE_DAYS` per category (3-30 days); `SuspenseItem.is_overdue()` per-category aging |
| **ENH-RMS-R6** Real-time KEPSS / PesaLink Reconciliation | `RealTimePaymentSystem` enum (KEPSS, PESALINK, EAPS); `RealTimeReconciliationConfig` (5-min default max latency, 30s auto threshold, ISO 20022 required); `RealTimePaymentObservation` with `latency_seconds()` derived; `RealTimeMatchVerdict` enum (MATCHED_AUTO ≤30s, MATCHED_DELAYED 30-300s, LATENCY_BREACH >300s, SETTLEMENT_PENDING, AMOUNT_MISMATCH, NOT_FOUND); `assess_real_time_match()` returns explicit verdict + latency + reason |

## Regulatory provenance

- **Kenya Banking Act §39** — books and records integrity
- **Kenya Banking Act §32** — statutory returns submission
- **CBK Prudential Guideline CBK/PG/02** — operational risk framework
- **CBK CRMF April 2021 §6** — internal controls + reconciliation
- **CBK CRMF §6.4** — Nostro reconciliation monthly minimum
- **CBK Act Cap 491 §4(d)** — payment/clearing/settlement systems
- **KEPSS Rules and Procedures** (Schedules A-H, published by CBK)
- **PesaLink/IPSL Operating Rules**
- **SWIFT MT940/942/950** — customer statement messages
- **SWIFT MX (ISO 20022)** — camt.052/053/054
- **Basel BCBS 239 §5** — accuracy and integrity principles
- **PFMI 2012 (CPMI-IOSCO)** — Principles for Financial Market Infrastructures

## Key design decisions

### CBK return deadlines are per-type defaults but overridable
`DEFAULT_RETURN_DEADLINE_DAYS` maps each `CBKReturnType` to a default day count. These defaults match standard CBK practice:
- Daily returns (CRR, FOREX, AML_STR, daily liquidity): T+1
- Weekly (AML_CTR, weekly returns): T+2 to T+7
- Monthly (RAR, CAR, LCR, NSFR, monthly returns): T+15
- Quarterly: T+21
- Connected lending: T+30

Production deployments override per their CBK supervisor's specific guidance via `compute_return_deadline(custom_deadline_days=N)`.

### Severity tracking surfaces approaching breaches early
`DeadlineSeverity.AMBER` fires at ≤3 days remaining, `RED` at ≤1 day, `BREACHED` after deadline. This four-level severity gives the Compliance team a runway to escalate before deadlines miss — much more useful than binary on-time/late.

### Stale Nostro items align with CBK CRMF
`StaleAgeBucket` thresholds (30/60/90 days) match CBK guidance: items >30 days require investigation, >90 days require provisioning consideration. The `BREACH_91_PLUS` bucket directly maps to CBK supervisory expectations.

### FX revaluation as explicit reconciliation explainer
`compute_fx_reval()` produces a `FXRevaluationAdjustment` that explains how much of a Nostro variance is due to FX rate movement (not actual breaks). Pure book-balance comparison ignoring FX would surface phantom breaks every reporting period. The dedicated reval calculation separates the explainable from the genuine.

### Per-category suspense aging
`DEFAULT_SUSPENSE_MAX_AGE_DAYS` recognizes that different suspense items have different reasonable lifespans:
- Cheques in clearing: 5 days (within standard clearing cycle)
- Interbranch transit: 3 days
- Card disputes: 30 days (matching scheme dispute windows)
- Card disputes get longer threshold than fraud suspense — treating them all the same would over-flag legitimate disputes.

### Real-time match verdicts are explicit, not inferred
`assess_real_time_match()` returns one of 6 explicit verdicts:
1. MATCHED_AUTO (≤30s) — green light, no review needed
2. MATCHED_DELAYED (30-300s) — review recommended
3. LATENCY_BREACH (>300s) — investigation required
4. SETTLEMENT_PENDING — observation incomplete
5. AMOUNT_MISMATCH — clear break
6. NOT_FOUND — payment recorded but no settlement observation

Caller sees the exact verdict + latency + reason. Per Rule 1, no silent pass.

### Aggregator pattern for cross-surface reporting
`SpecializedReconciliationEngine` is an in-memory aggregator that lets the board summary surface KPIs across all 4 surfaces in one call:
- CBK returns overdue
- Stale Nostro items in critical buckets
- IC counterparties out of balance
- Overdue suspense items
- Real-time payment latency breaches

This is the dashboard data feed for ENH-184 (Real-time Recon Dashboard) coming in v10.21.

### Compose with v10.18 + v10.19 — don't reimplement
v10.20 doesn't reimplement matching or workflow. Specialized surfaces produce specialized exception types that flow into v10.19's `ExceptionRecord` workflow:
- An `OVERDUE` CBK return → `ExceptionRecord` of type `WRONG_ACCOUNT` or `REFERENCE_MISSING`
- A stale Nostro item → `ExceptionRecord` of type `UNMATCHED_TARGET`
- An out-of-balance IC counterparty → `ExceptionRecord` of type `AMOUNT_MISMATCH`

The integration is "specialized engine produces evidence; workflow engine routes for resolution." Same composition pattern v10.13 used between credit_workflow + risk_based_pricing.

## Engine Hub integration

Tier 10 expanded from 2 to 3 engines. The new `reconciliation_specialized` entry covers all 4 specialized surfaces in one engine (intentional: they share the dashboard view and are typically accessed together by the recon ops team).

**G117 coverage holds at ≥ 95%.**

## Tests

- 29 self-tests in `reconciliation_specialized.py`
- 24 integration tests in `tests/integration/test_v10_20_specialized_recon.py`

## Verified output

```
✓ reconciliation_specialized self-test passed (29 tests)
Ran 387 tests in 37.706s OK
Audit: 121/121 gates PASS
```

## Standards registry — 12 RMS active

```
RMS (subcategory) — 12 of 17 active after v10.20:
  ENH-181:    Multi-Source Data Ingestion                   (v10.18)
  ENH-182:    Intelligent Matching Engine                   (v10.18)
  ENH-183:    Exception Management & Workflow               (v10.19)
  ENH-185:    CBK Regulatory Reconciliation                 (v10.20) ← NEW
  ENH-186:    Nostro/Vostro Reconciliation                  (v10.20) ← NEW
  ENH-187:    Intercompany & Internal Suspense Recon        (v10.20) ← NEW
  ENH-RMS-R1: 90%+ AI-Matching Threshold Target             (v10.18)
  ENH-RMS-R2: Memory-Layer Architecture                     (v10.19)
  ENH-RMS-R3: Vendor Name Normalization Library             (v10.18)
  ENH-RMS-R4: Timing-Difference Auto-Handling               (v10.19)
  ENH-RMS-R5: Governed Execution Layer (TruePath-style)    (v10.19)
  ENH-RMS-R6: Real-time KEPSS / PesaLink Reconciliation     (v10.20) ← NEW

RMS still planned: 5 (for v10.21; v10.22 closes)
  ENH-184:    Real-time Reconciliation Dashboard
  ENH-188:    AI-Powered Reconciliation Learning
  ENH-189:    Continuous/Real-time Reconciliation
  ENH-190:    Reconciliation Audit & Certification
  ENH-RMS-R7: Sub-Monthly Daily Reconciliation Support
```

## Honest acknowledgements

1. **Default deadline days are seed values.** CBK supervisors may issue bank-specific letters changing deadlines. Override via `compute_return_deadline(custom_deadline_days=N)` per bank's actual obligations.

2. **No SWIFT MT940 parser ships.** The architecture references the message types but parsing is per-deployment (using e.g., `tweepy-mt`, `parsemt940`, or commercial libraries). The framework accepts already-parsed observations.

3. **No ISO 20022 parser ships.** Same as SWIFT — accept structured observations from upstream parser. Real bank deployments use Banking Industry Architecture Network (BIAN) or vendor-specific MX parsers.

4. **FX revaluation uses simple linear method.** Real bank treasury systems may use forward-curve based revaluation, especially for term deposits. The seed implementation handles spot revaluation; forward-rate revaluation is per-deployment.

5. **Real-time latency thresholds (30s/300s) are configurable defaults.** PesaLink target latency is typically <60s end-to-end; KEPSS RTGS targets <30s. Override per `RealTimeReconciliationConfig`.

6. **No actual KEPSS/PesaLink network integration.** The framework accepts payment observations from upstream collectors. Real integration uses CBK-provided KEPSS gateway + PesaLink IPSL APIs (per-deployment credentials).

7. **Per-category suspense max ages are conventional.** Banks may have stricter or looser policies. The defaults are reasonable starting points; production overrides via `max_age_override` parameter.

8. **No persistence.** All engines are in-memory per instance. Postgres persistence wires in a dedicated batch.

9. **No regulatory return content generation.** The engine tracks deadlines and variance but doesn't generate the actual CBK 105 / RAR / LCR returns. That's a separate workstream that produces the structured data files for CBK submission portals.

10. **Stale item provisioning is flagged but not computed.** The engine surfaces 91+ day items as `BREACH_91_PLUS`; computing the provision amount per CBK guidance (typically 100% for items >90 days) belongs in the credit/IFRS9 module, not here.

## What v10.21 ships next

**Final RMS arc batch — 5 standards** (the largest):
- ENH-184 Real-time Reconciliation Dashboard
- ENH-188 AI-Powered Reconciliation Learning
- ENH-189 Continuous/Real-time Reconciliation
- ENH-190 Reconciliation Audit & Certification
- ENH-RMS-R7 Sub-Monthly Daily Reconciliation Support

These deliver the dashboard surface, ML learning loop (Rule-7-hookable), continuous (vs. batch) recon mode, audit/certification trail, and sub-monthly cadence. Then v10.22 closes the arc with G122.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| Batch 2 — Credit (v10.11–v10.16) | 19/19 | ✅ closed |
| Enhancement — KESONIA (v10.17) | 1/1 | ✅ closed |
| **Batch 3 — RMS Reconciliation (v10.18–v10.22)** | **12/17** | **🟡 in flight (3 of 5 batches)** |
| Batch 4 — Audit/GRC | 0/17 | pending |
