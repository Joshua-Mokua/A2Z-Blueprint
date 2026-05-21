# CHANGELOG v10.17 — KESONIA + Revised RBCPM (CBK Aug 2025)

**Audit:** 121/121 PASS — **100th consecutive clean.**

## Why this batch slots in here

The original Phase 2 plan called for v10.17 to open the RMS deep-impl arc. **A user-supplied document on KESONIA integration prompted a fact-check + redirect** before proceeding to RMS.

The CBK regulatory deadlines are already triggered:
- **1 Sept 2025** — KESONIA officially launched; revised RBCPM effective for new variable-rate loans
- **1 Dec 2025** — most banks live with KESONIA-based pricing for new loans (after 3-mo grace)
- **28 Feb 2026** — mandatory deadline for migrating EXISTING variable-rate loans (4 days before this CHANGELOG was written)

Shipping KESONIA support now is more time-sensitive than RMS arc opening. RMS arc is pushed to v10.18+.

## Fact-check of the user-supplied document

The original document had several factual errors that needed correction before any code was written:

| Claim in document | Reality (per CBK official sources) |
|---|---|
| "Effective February 2024" | **Wrong.** KESONIA officially launched **1 Sept 2025** as a renaming of the existing overnight interbank rate. |
| "New methodology" | **Wrong.** Per CBK FAQ: "There are no methodological changes." It is a rename of the existing volume-weighted overnight interbank average. |
| "Replaces KIBOR" | **Wrong.** Kenya never had a "KIBOR" formally adopted as a lending benchmark. KESONIA replaces **CBR** as the reference for variable-rate KES loans. CBR remains as fallback. |
| "Use cases include derivatives valuation" | **Overstated.** CBK's mandate is currently for variable-rate KES loan pricing. Derivatives/discount curve use is downstream practice, not regulatory. |
| K-001..K-005 (5 standards) | **Over-engineered.** The right cut is one new module + composition with existing v10.13. |

The document also missed several material requirements:

- **Pricing formula = `KESONIA + K`** where K is the borrower-specific risk premium per the new RBCPM
- **Board approval requirement** for each bank's KESONIA-based RBCPM before submission to CBK
- **Dual-track rollout** with explicit deadlines for new vs existing loans
- **KESONIA Compounded Index** for compound-in-arrears accrual (`Index_i = Index_{i-1} × (1 + r × α)`)
- **Lookback period conventions** (operational lag vs payment date)
- **K premium disclosure** — separate from base rate, transparency requirement
- **Customer notification** for existing borrowers in January 2026
- **TCC portal expansion** to cover more facility types
- **Scope exclusions** explicit in CBK FAQ: FCY loans + fixed-rate loans excluded

## What ships in v10.17

`utils/benchmark_rates.py` — 869 lines, **Cat A** (rate determination affects loan pricing + revenue). 1 new Credit standard active:

| Standard | Implemented as |
|---|---|
| **ENH-CBK-KESONIA** KESONIA + RBCPM | `BenchmarkRateRegistry` with `RateCode` enum (KESONIA / CBR / KESONIA_COMPOUNDED_INDEX), `LoanRateType` enum (in-scope / out-of-scope), spot lookup with weekend holdover + CBR fallback, KESONIA Compounded Index ratio for compound-in-arrears, `compute_total_rate()` returning RBCPM `KESONIA + K`, bridges to v10.13 `risk_based_pricing.PricingInputs.funding_rate` via `resolve_funding_rate_decimal()`, and customer-facing K disclosure via `derive_k_premium_pct()`. |

## Regulatory provenance

- **CBK Revised Risk-Based Credit Pricing Model** (Aug 2025) — official document at centralbank.go.ke
- **KESONIA launch announcement** — 1 Sept 2025
- **CBK Banking Act §44** — interest rate disclosure requirements
- **CBK Weekly Bulletin** — daily KESONIA publication (current rate ~8.76% as of 23 April 2026)
- **Cooperative Bank circular Dec 2025** — first major bank implementation (Co-op Bank used 1 Dec 2025 effective date for new loans)
- **Kenya Bankers Association** — industry coordination on board-approved RBCPMs

## Key design decisions

### Composition over modification
**Zero changes to v10.13 `utils/risk_based_pricing.py`.** The existing API takes `funding_rate: Decimal` — the new module's `resolve_funding_rate_decimal()` returns exactly that, so callers compose:

```python
# Resolve KESONIA → decimal funding rate
rate, lookup = resolve_funding_rate_decimal(
    registry=reg, as_of_date="2026-04-23")

# Use it in v10.13 PricingInputs
inputs = PricingInputs(asset_id="L1", pd=..., funding_rate=rate, ...)
result = price_loan(inputs)

# Express to customer per RBCPM
k = derive_k_premium_pct(
    offered_rate_decimal=result.offered_rate,
    kesonia_pct=lookup.rate_pct)
# Customer sees: KESONIA (8.76%) + K (4.50pp) = 13.26%
```

This pattern keeps v10.13 stable (98th-clean batch unchanged) while adding the regulatory disclosure layer cleanly above it.

### Rate lookup honors CBK methodology
- **Weekend/holiday holdover**: per CBK methodology, KESONIA is held constant on non-business days. Engine returns the most recent prior business-day observation with explicit notes.
- **CBR fallback**: when KESONIA unavailable, fallback to CBR per RBCPM rules. The result has `is_fallback=True` flag — caller sees the substitution.
- **No fabrication**: when neither KESONIA nor CBR is available, returns `BenchmarkLookupResult` with `rate_pct=None` and explicit notes. Per Rule 1, never invents a rate.

### Compounded Index uses official CBK formula
Per CBK guidance, period interest is computed as ratio of indices:
```
accrual_factor = Index(period_end) / Index(period_start) - 1
annualized_rate = accrual_factor × (360 / days)
```
This matches SONIA + SOFR international practice. The engine's `compute_compounded_accrual()` uses this exactly — no manual daily compounding (which is operationally infeasible).

### Scope explicit per CBK FAQ
`LoanRateType` enum has `is_kesonia_in_scope()` method:
- `VARIABLE_KES` → True (use KESONIA + K)
- `VARIABLE_FCY` → False (excluded — FCY)
- `FIXED_RATE` → False (excluded — fixed)

`compute_total_rate()` checks scope and returns `is_in_scope=False` with explanation when the loan type is excluded. No silent application to wrong scope.

### Rule 7 hookable rate fetcher
`BenchmarkRateRegistry` accepts a `rate_fetcher: Callable` for real-time CBK feed integration. When configured, fresh rates auto-cache on first lookup. When absent, registry uses only manually-loaded observations. **No silent network calls.**

## G121 forward-compat fix

When ENH-CBK-KESONIA was added, it bumped the credit-subcategory standards count from 19 to 20, which broke G121's hard-coded `len(credit) == 19` assertion. Fix: G121 now locks the **closure set** (the 19 specific standard IDs from v10.16) rather than the **count**. Future credit additions are allowed without backslide of the closure set. Same forward-compat pattern as the v10.10 audit-score test fix in v10.16.

Two integration tests also got the same treatment:
- `test_v10_15_docs_group_exposure.TestV1015RegistryAlignment.test_all_19_credit_active` — now asserts ≥19
- `test_v10_16_audit_gate_g121.TestV1016G121Passes` — renamed to `test_g121_reports_closure_set_preserved`

This pattern is now standard practice for closure-snapshot tests across the codebase.

## Engine Hub integration

Tier 9 added to `pages/7_admin.py`:
- `benchmark_rates` (`BenchmarkRateRegistry`) — KESONIA + CBR + Compounded Index registry per CBK Revised RBCPM

G117 coverage holds at ≥ 95%.

## Tests

- 26 self-tests in `benchmark_rates.py`
- 23 integration tests in `tests/integration/test_v10_17_kesonia.py`

## Verified output

```
✓ benchmark_rates self-test passed (26 tests)
Ran 315 tests in 39.307s OK
Audit: 121/121 gates PASS
```

## Standards registry — KESONIA active

```
ENH-CBK-KESONIA: KESONIA + Risk-Based Credit Pricing Model (RBCPM)
  Subcategory: credit
  Affected engines: benchmark_rates, risk_based_pricing, funds_transfer_pricing
  Regulatory source: CBK Revised RBCPM 2025 + Banking Act §44
  Status: active
  Implementation batch: v10.17
```

Total active standards: **45 of 247** (was 44 of 246 at v10.16 closure; +1 new active, +1 new total).

## Honest acknowledgements

1. **No CBK API integration ships.** The `rate_fetcher` callable is the integration hook; actual CBK API (or daily CSV ingest) is per-deployment work. The framework is ready; the credentials/endpoints are configuration.

2. **Compounded Index data must be loaded externally.** The engine accepts `CompoundedIndexObservation` records but doesn't fetch them. CBK publishes the index daily on its website; ingestion belongs in a daily cron/Airflow job.

3. **K premium disclosure is computed but not enforced as a UI requirement.** A future batch should add a customer-facing rate-disclosure widget (per Banking Act §44 + the TCC portal expansion).

4. **Existing-loan migration tooling is not built.** The 28 Feb 2026 deadline required banks to migrate existing variable-rate loans to KESONIA pricing. The engine supports computing the new rate, but a bulk migration tool (re-pricing N loans, generating customer notices, updating loan accounts) is not in scope for this batch.

5. **No OIS curve / IRRBB / FTP integration yet.** Those map to existing planned standards **ENH-233** (IRRBB) and **ENH-236** (FTP). They're larger pieces and belong in dedicated batches when the Treasury arc is opened.

6. **Compounded Index baseline assumption.** The engine treats the index as a black-box value provided by CBK; it doesn't reproduce the index from scratch. Per CBK methodology the index started at 100.0000 on 1 Jan 2025; the engine accepts whatever values CBK publishes.

7. **Day-count convention is 360.** Matches CBK / SONIA / SOFR practice. If CBK switches to ACT/365 in future guidance, update `KESONIA_DAY_COUNT_BASIS`.

8. **No persistence.** Rate observations live in-memory per registry instance. Postgres persistence wires in when the persistence layer ships.

## What v10.18 ships next

Back to the original Phase 2 plan: **RMS deep-impl arc opens**. 17 standards across 5 batches (v10.18 → v10.22):

- v10.18: RMS core — AI matching engine for relationship → opportunity
- v10.19: Candidate sourcing + ranking
- v10.20: BSC integration + RM performance overlay
- v10.21: Pipeline analytics + handover workflows
- v10.22: G122 audit gate + RMS arc closure

## Phase 2 progress after v10.17

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| Batch 2 — Credit (v10.11–v10.16) | 19/19 | ✅ closed |
| **Enhancement — KESONIA (v10.17)** | **1 added (20/19+1)** | **✅ closed** |
| Batch 3 — RMS (v10.18–v10.22) | 0/17 | pending |
| Batch 4 — Audit/GRC | 0/17 | pending |
