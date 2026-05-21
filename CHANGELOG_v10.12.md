# CHANGELOG v10.12 — Credit batch 2: Alt Data + Bureau + eKYC + Fraud

**Audit:** 120/120 PASS — **95th consecutive clean.**

## What ships in v10.12

`utils/applicant_data_sources.py` — 1,077 lines covering 4 of 19 Credit standards:

| Standard | Implemented as |
|---|---|
| **ENH-120** Alternative Data Intelligence | `AltDataSource` enum (9 sources), `AltDataRecord` + `AltDataScore` dataclasses, `compute_alt_data_score()` with consent + history gating |
| **ENH-129** Credit Bureau Integration | `BureauProvider` enum (3 Kenya CRBs), `BureauReport` standardized dataclass, `fetch_bureau_report()` callable-based fetch (no silent network), `aggregate_bureau_reports()` worst-case aggregation |
| **ENH-121** Digital Identity Verification (eKYC) | `EKYCResult` enum, `EKYCAssessment` with 6 mandatory checks, `assess_ekyc()` returning VERIFIED / FAILED / INCONCLUSIVE per CBK + FATF |
| **ENH-122** Real-Time Fraud Detection | `FraudSignal` enum (10 signals), `FRAUD_SIGNAL_WEIGHTS` table, `assess_fraud()` returning ALLOW / CHALLENGE / BLOCK, `evaluate_velocity_rules()` for IP/device velocity |

Plus the orchestrator: `ApplicantDataAggregator.build_profile()` composes all 4 into a unified PROCEED / REFER / DECLINE recommendation.

## Regulatory provenance

- **Alt data**: CBK Digital Credit Guideline 2022 (Digital Lending Provider licensing)
- **Bureau**: CBK CRB Regulations 2020 (Revised) + CBK PG/8; Kenya CRB Act 2008 + 2014 amendments
- **eKYC**: CBK AML/CFT Guideline 2017 + Digital Lending Reg 2022; Kenya Registration of Persons Act + IPRS Act; FATF Recommendation 10 (CDD); EU eIDAS Reg 910/2014
- **Fraud**: CBK Cyber Security Guidance Note 2017 + Risk Mgmt Reg; PCI DSS v4.0; ISO 27001

## Reference data registered

| Constant | Value | Source |
|---|---|---|
| `AltDataSource` enum | 9 sources | M-Pesa, Airtel, KP, Water, Telco, Bank, Payroll, Social, KRA |
| `ALT_DATA_FRESH_DAYS` | 30 | Industry default for "fresh" data |
| `ALT_DATA_MIN_HISTORY_MONTHS` | 3 | Minimum to derive payment-pattern signal |
| `BureauProvider` enum | 3 | TransUnion KE, Metropol KE, Creditinfo KE (CBK-licensed) |
| `BUREAU_SCORE_RANGES` | per-provider | TransUnion + Metropol: 200-900; Creditinfo: 0-999 |
| `EKYC_REQUIRED_CHECKS` | 6 | IPRS, biometric, doc auth, mobile, PEP, sanctions |
| `BIOMETRIC_MATCH_VERIFIED_ABOVE` | 0.85 | Industry default for face-match liveness |
| `BIOMETRIC_MATCH_FAILED_BELOW` | 0.50 | Below this = explicit fail |
| `FraudSignal` enum | 10 signals | Velocity, device sharing, IP sharing, behavior, geo, doc, synthetic, ring |
| `FRAUD_SIGNAL_WEIGHTS` | per-signal | Range 10-90 (KNOWN_FRAUD_RING_MATCH highest) |
| `VELOCITY_RULE_APPLICATIONS_PER_30MIN` | 3 | Threshold for velocity-fraud signal |
| `VELOCITY_RULE_APPLICATIONS_PER_24H` | 8 | Daily velocity threshold |

## Composition with v10.11

The aggregator's output `recommendation` (PROCEED / REFER / DECLINE) flows into the v10.11 underwriting engine via these gates:
- **Sanctions hit** → eKYC FAILED → recommendation DECLINE → v10.11 sees forced decline
- **Fraud BLOCK** → recommendation DECLINE → v10.11 forced decline
- **Fraud CHALLENGE** or **eKYC INCONCLUSIVE** → REFER → v10.11 routes to human review
- **Thin file** (no bureau + low alt-data confidence) → REFER → human review
- Otherwise PROCEED → v10.11 evaluates on PD + DTI + LTV thresholds

## Honesty Rules enforced

**Rule 1 (no silent zero):**
- `AltDataRecord` without consent → score 0 with explicit rationale
- `AltDataRecord` with `months_of_history < 3` → skipped, not silently extrapolated
- `EKYCAssessment` with missing checks → INCONCLUSIVE, not silent pass
- `BureauReport` with missing score → `normalized_score_pct() = None`

**Rule 7 (no silent ML / network):**
- `fetch_bureau_report` requires `fetcher` callable; no fetcher → returns `None`
- Failing fetcher → returns `None` (graceful degradation, no fabrication)
- Engine never invents bureau scores or biometric match scores

## Key compliance implementations

### eKYC: PEP vs sanctions
Per FATF Recommendation 6 + 12 — PEP hit triggers Enhanced Due Diligence (EDD), not auto-decline. The engine returns `INCONCLUSIVE` for PEP hits (routes to manual review), but `FAILED` for sanctions hits (must decline per FATF Rec 6).

### Bureau: worst-case aggregation
Many lenders consult ≥1 of the 3 Kenya CRBs (CBK Regulations 2020 require ≥1; many use all 3). When aggregating, the engine takes WORST case per dimension (`max` for delinquencies/DPD/bankruptcies, `min` for normalized score). This is conservative but defensible.

### Alt data: high-signal weighting
Mobile money (M-Pesa, Airtel), bank statements, and payroll verification get 1.5× weight vs. utility/social signals. This reflects the demonstrated predictive value of cash-flow data for thin-file underwriting in East Africa (per Tala, Branch, JUMO published research).

### Fraud: capped score
Score sums to max 100 even when many signals fire. Single high-weight signal (KNOWN_FRAUD_RING_MATCH = 90) is enough to BLOCK. This prevents both false positives (one weak signal blocking) and weight gaming.

## Tests

- **27 module-level self-tests** (`python -m utils.applicant_data_sources`)
- **21 integration tests** in `tests/integration/test_v10_12_applicant_data_sources.py`

## Verified output

```
✓ applicant_data_sources self-test passed (27 tests)
Ran 202 tests in 18.970s OK
Audit: 120/120 gates PASS
```

## Standards registry

```
Credit (subcategory) — 8 of 19 active after v10.12:
  ENH-119:    AI-Powered Credit Decisioning Engine          (v10.11)
  ENH-120:    Alternative Data Intelligence                  (v10.12) ← NEW
  ENH-121:    Digital Identity Verification (eKYC)           (v10.12) ← NEW
  ENH-122:    Real-Time Fraud Detection                      (v10.12) ← NEW
  ENH-124:    Explainable AI for Regulatory Compliance       (v10.11)
  ENH-129:    Credit Bureau Integration                      (v10.12) ← NEW
  ENH-CRD-R2: EU AI Act High-Risk Classification Compliance (v10.11)
  ENH-CRD-R3: CFPB-Compliant Adverse Action Reason Codes    (v10.11)

Credit still planned: 11 (for v10.13-v10.15; v10.16 closes)
```

## Honest acknowledgements

1. **No real bureau API integration.** The `fetch_bureau_report()` interface accepts a callable fetcher — actual TransUnion / Metropol / Creditinfo API SDKs are integration work outside this batch. The framework is ready; the credentials + endpoints are deployment-time config.
2. **Biometric match score thresholds (0.85 / 0.50)** are industry defaults from major eKYC vendors (Onfido, Jumio, Smile Identity) — not Ecobank-tuned. Calibration against actual fraud rates belongs downstream.
3. **PEP screening assumes external service** — the `pep_hit` parameter accepts a True/False from a screening provider (e.g., World-Check, Dow Jones, ComplyAdvantage). The engine doesn't ship with a PEP database.
4. **Sanctions screening** likewise assumes external lookup. Our engine handles the result classification (FAILED on hit per FATF Rec 6) but does not maintain the sanctions list.
5. **Alt-data scoring formula is illustrative**: `payment_score (60% weight) + inflow_score (40% weight)`. Real-world models trained on Ecobank default rates would replace this — the architecture is ready, the weights need calibration.
6. **Fraud signal weights are heuristic.** Production deployment requires regression of historical fraud cases against signal frequencies. The 10 signals + weights are defensible defaults but not validated against Ecobank fraud data.
7. **Velocity rules use simple count thresholds.** Per-IP-per-device-per-applicant attribution is more sophisticated in production (e.g., session graphs, link analysis) — that's part of v10.14 fraud-ring detection extension.
8. **No persistence.** Profiles accumulate in `_profiles` per aggregator instance.

## What v10.13 ships next

**Pricing + workflow + memo + 80/20 automation pattern** (5 standards):
- ENH-123 Dynamic Risk-Based Pricing — risk-adjusted rate calculation
- ENH-125 End-to-End Digital Workflow Orchestration — application state machine
- ENH-130 Credit Committee Automation — auto-routing + voting
- ENH-CRD-R5 GenAI Credit Memo Drafting Agent — memo template + LLM hook
- ENH-CRD-R7 Confident Automation Pattern (80/20) — automation policy formalization

These build on v10.11 + v10.12 to complete the application → decision → execution flow.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| **Batch 2 — Credit (v10.11–v10.16)** | **8/19** | **🟡 in flight** |
| Batch 3 — RMS (v10.17–v10.21) | 0/17 | pending |
| Batch 4 — Audit/GRC (v10.22–v10.26) | 0/17 | pending |
