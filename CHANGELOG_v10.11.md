# CHANGELOG v10.11 — Phase 2 batch 2: Credit deep impl arc opens with AI underwriting

**Audit:** 120/120 PASS — **94th consecutive clean.**

## Phase 2 batch 2 begins — Credit deep impl arc (v10.11–v10.16)

With the Climate/ESG arc closed at v10.10, the next priority arc per strategic plan is **Credit deep impl** — 19 standards across 6 batches. Batch arc:

| Batch | Theme | Standards | Status |
|---|---|---|---|
| **v10.11** | **AI underwriting core** | **ENH-119, 124, R2, R3 (4)** | **✅ THIS BATCH** |
| v10.12 | Alt data + bureau + eKYC + fraud | ENH-120, 129, 121, 122 (4) | pending |
| v10.13 | Pricing + workflow + memo + 80/20 | ENH-123, 125, 130, R5, R7 (5) | pending |
| v10.14 | Portfolio monitoring + collections + bias + unstructured | ENH-126, 128, R1, R6 (4) | pending |
| v10.15 | Doc mgmt + group exposure | ENH-127, R4 (2) | pending |
| v10.16 | G121 audit gate + arc closure | (locks 19) | pending |

## What ships in v10.11

`utils/ai_underwriting.py` — 1,087 lines, **Risk class Cat A** (decisions affect issuance/denial outcomes). 4 of 19 Credit standards now active:

| Standard | Implemented as |
|---|---|
| **ENH-119** AI-Powered Credit Decisioning Engine | `AIUnderwritingEngine.decide()` orchestrator + `compute_underwriting_decision()` rule-based core with hookable `pd_provider` callable for ML model integration |
| **ENH-124** Explainable AI for Regulatory Compliance | `compute_feature_contributions()` ranks all features by signed contribution, `ModelCard` dataclass per Google + EU AI Act Art 13 |
| **ENH-CRD-R2** EU AI Act High-Risk Classification Compliance | `EUAIActHighRiskMetadata` covering Art 9 (risk mgmt), 13 (transparency), 14 (human oversight), 15 (accuracy + cybersecurity); `validate_eu_ai_act_compliance()` returns missing-per-article gap list |
| **ENH-CRD-R3** CFPB-Compliant Adverse Action Reason Codes | `generate_adverse_action_codes()` returning Reg B App C-mapped codes; 22-code catalog; max 4 codes per Reg B §1002.9 |

## Regulatory provenance

- **EU AI Act (Reg 2024/1689)** Art 6 + Annex III §5(b) — credit underwriting is high-risk AI
- **EU AI Act Art 9** (risk mgmt), Art 13 (transparency), Art 14 (human oversight), Art 15 (accuracy + cybersecurity)
- **EU AI Act Art 26** (deployer obligations) + Art 86 (right to explanation)
- **ECOA** — Equal Credit Opportunity Act 15 USC §1691
- **Regulation B** 12 CFR §1002.9 (adverse action notification) + 12 CFR Pt 1002 App C (sample forms)
- **CFPB Circular 2022-03** — adverse action via algorithms must produce specific reasons
- **Basel BCBS 239** — risk data aggregation principles
- **CBK Prudential Guideline CBK/PG/13** — credit risk management

## Decision logic (rule-based, ML-hookable)

```
PD < 5%   → APPROVE (HIGH/MEDIUM/LOW depending on margin + DTI/LTV)
PD 5–20%  → REFER_HUMAN
PD > 20%  → DECLINE

Hard caps (always DECLINE regardless of PD):
  DTI > 60%
  Bankruptcy in past 84 months
  LTV > 100%

CONDITIONAL_APPROVE triggers:
  Low PD but DTI 45–60%
  Low PD but LTV 80–100%
```

## Confidence + 80/20 automation pattern

Per **ENH-CRD-R7 Confident Automation Pattern** (will land formally in v10.13, but the threshold framework is plumbed now):

| Score range | Level | Effect |
|---|---|---|
| ≥ 0.80 | HIGH | Eligible for full automation |
| 0.50–0.80 | MEDIUM | Proceed with caveats / supervision |
| < 0.50 | LOW | Human review required |

`is_automated()` on `AIDecisionResult` returns True only when decision is APPROVE/CONDITIONAL_APPROVE/DECLINE **and** confidence is HIGH.

## CFPB adverse action codes — 22-code catalog

`CFPB_ADVERSE_ACTION_CODES` mirrors Reg B Appendix C Sample Form C-1 + CFPB Circular 2022-03 specificity requirement:

```
AA_001_INSUFFICIENT_INCOME              AA_012_GARNISHMENT_ATTACHMENT_FORECLOSURE
AA_002_INCOME_UNVERIFIABLE              AA_013_VALUE_OF_COLLATERAL
AA_003_LENGTH_OF_EMPLOYMENT_TOO_SHORT   AA_014_INADEQUATE_COLLATERAL
AA_004_INSUFFICIENT_RESIDENCY_STABILITY AA_015_TYPE_OF_CREDIT_REQUESTED
AA_005_TEMPORARY_RESIDENCE              AA_016_AMOUNT_REQUESTED_TOO_HIGH
AA_006_INSUFFICIENT_CREDIT_FILE         AA_017_PURPOSE_OF_LOAN_NOT_ACCEPTABLE
AA_007_NO_CREDIT_FILE                   AA_018_DEBT_TO_INCOME_RATIO_TOO_HIGH
AA_008_LIMITED_CREDIT_EXPERIENCE        AA_019_NUMBER_OF_TRADELINES
AA_009_DELINQUENT_PAST_OR_PRESENT...    AA_020_INSUFFICIENT_DOWN_PAYMENT
AA_010_BANKRUPTCY                       AA_021_PAYMENT_HISTORY
AA_011_NUMBER_OF_RECENT_INQUIRIES       AA_022_OTHER_REASON
```

`FEATURE_TO_AA_CODE` mapping covers 19 features → specific codes; `AA_022_OTHER_REASON` is fallback only.

## EU AI Act compliance dimensions tracked

| Article | Bucket | Required artifacts |
|---|---|---|
| Art 9 | Risk management | RISK_IDENTIFICATION, RISK_ESTIMATION_AND_EVALUATION, RISK_MITIGATION_MEASURES, TESTING_AGAINST_RISKS |
| Art 13 | Transparency | PURPOSE_OF_AI_SYSTEM, ACCURACY_LEVEL, CIRCUMSTANCES_OF_USE, INPUT_DATA_REQUIREMENTS, HUMAN_OVERSIGHT_MEASURES |
| Art 14 | Human oversight | INTERPRET_AI_OUTPUT, DISREGARD_OR_OVERRIDE_AI, INTERVENE_OR_INTERRUPT |
| Art 15 | Accuracy + security | ACCURACY_METRICS_DEFINED, ACCURACY_METRICS_REPORTED, ROBUSTNESS_TESTING, CYBERSECURITY_MEASURES |

`completeness_pct()` returns % of all 16 artifacts in place. `is_compliant()` is True only at 100% with no open findings.

## Honesty Rule 7 enforced — no silent ML

The engine has a `pd_provider: Optional[Callable]` parameter. When **no provider is set**:
- Decision = `REFER_HUMAN` with `LOW` confidence
- `pd_estimate` = `None` (not silently zero)
- `ModelCard.methodology` = `"rule_based"`
- `ModelCard.deviation_notes` = `SPEC_DEVIATION_NOTE`
- `ModelCard.accuracy_metric_value` = `None`

This mirrors the same Rule 7 pattern enforced in `utils/credit_risk_scoring.py` since v5.55.

## Composes with existing engines

| Existing | New module's relationship |
|---|---|
| `utils/credit_risk_scoring.py` (v5.55) | Plug as `pd_provider` callable; **not modified** |
| `utils/composite_scores.py` | Available for feature engineering; **not modified** |
| `utils/system_invariants.py` | Could supply DTI/LTV thresholds dynamically (future) |

Zero modifications to existing files in this batch.

## Tests

- **24 module-level self-tests** (`python -m utils.ai_underwriting`)
- **19 integration tests** in `tests/integration/test_v10_11_ai_underwriting.py`:
  - Engine imports + 22 public symbols
  - Self-test passes
  - Registry alignment (4 active)
  - Decision logic (strong → APPROVE; DTI cap → DECLINE; no PD → REFER)
  - Explainability (contributions ranked; missing features skipped)
  - CFPB codes (decline produces codes; approve produces none; max-4 cap)
  - EU AI Act compliance (default not compliant; full → compliant; gap detection per article)
  - Board summary aggregation
  - Rule 7 honesty (default rule-based)
  - Coexistence with v10.6–v10.10 climate engines

## Verified output

```
✓ ai_underwriting self-test passed (24 tests)
Ran 181 tests in 15.561s OK
Audit: 120/120 gates PASS
```

## Standards registry update

```
Credit (subcategory) — 4 of 19 active after v10.11:
  ENH-119:    AI-Powered Credit Decisioning Engine          ← NEW
  ENH-124:    Explainable AI for Regulatory Compliance      ← NEW
  ENH-CRD-R2: EU AI Act High-Risk Classification Compliance ← NEW
  ENH-CRD-R3: CFPB-Compliant Adverse Action Reason Codes    ← NEW

Credit still planned: 15 (for v10.12-v10.15; v10.16 closes)
```

## Honest acknowledgements

1. **Decision logic is heuristic, not bank-calibrated.** PD thresholds (5%/20%), DTI cap (60%), LTV cap (100%) are illustrative defaults consistent with retail underwriting practice but not Ecobank-tuned. Calibration belongs downstream once historical default data is integrated.
2. **Feature contributions are weighted heuristics**, not ML model gradients. The `_DEFAULT_FEATURE_WEIGHTS` mapping uses traditional credit-scoring intuition; replace with SHAP/permutation importance from a trained model when available.
3. **Feature-direction logic is binary**: positive value of a "higher-is-better" feature → POSITIVE direction. Real ML systems would use distribution-aware contribution. The framework is ready to receive richer signals.
4. **EU AI Act compliance is metadata-tracking, not regulatory blessing.** `validate_eu_ai_act_compliance()` checks artifact presence; it doesn't certify compliance. That requires legal + audit review per Art 17 (notified body) for high-risk AI.
5. **CFPB codes are mapped from features, not from real-world adverse action notices.** A bank's specific adverse-action letter wording must be drafted by Compliance — this engine only produces the codes that drive that letter.
6. **No persistence layer.** Decisions accumulate in `_decisions` list per engine instance. Postgres/audit-log persistence wires in later batches.
7. **No fairness/bias testing yet** — that's ENH-CRD-R1 (LDA-based bias search) shipping in v10.14. The engine HOLDS `protected_class_signals` but does NOT use them for decisions.

## What v10.12 ships next

**Alternative data + bureau + eKYC + fraud** (4 standards):
- ENH-120 Alternative Data Intelligence — mobile money / utility / cash-flow data for thin-file applicants
- ENH-129 Credit Bureau Integration — TransUnion + Metropol (Kenya bureaus) integration framework
- ENH-121 Digital Identity Verification (eKYC) — IPRS (Integrated Population Registration Service) + biometric checks
- ENH-122 Real-Time Fraud Detection — velocity rules + device fingerprinting + behavioral signals

These plug into the v10.11 `ApplicantFeatures` pipeline and will require expanding the dataclass.

## Phase 2 progress

| Phase 2 batch | Arc | Standards | Status |
|---|---|---|---|
| Batch 1 | Climate/ESG (v10.6–v10.10) | 13/13 active | ✅ closed |
| **Batch 2** | **Credit deep impl (v10.11–v10.16)** | **4/19 active** | **🟡 in flight** |
| Batch 3 | RMS deep impl (v10.17–v10.21) | 0/17 active | pending |
| Batch 4 | Audit/GRC deep impl (v10.22–v10.26) | 0/17 active | pending |
| Batch 5+ | Treasury, Risk, Trade, IT, etc. | 0/116 active | pending |
