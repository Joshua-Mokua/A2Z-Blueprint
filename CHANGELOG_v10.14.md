# CHANGELOG v10.14 — Credit batch 4: Portfolio Monitoring + Fairness Testing

**Audit:** 120/120 PASS — **97th consecutive clean.**

## What ships in v10.14

Two cohesive modules covering 4 of 19 Credit standards:

### `utils/portfolio_monitoring.py` (903 lines, **Cat A**)

| Standard | Implemented as |
|---|---|
| **ENH-126** Dynamic Portfolio Monitoring & Early Warning | `EWSSignal` enum (16 signals), `EWSLevel` (GREEN/AMBER/RED), `assess_ews()` with severity-3 → RED override, roll rate analysis between snapshots |
| **ENH-128** Collections & Recovery Intelligence | `CollectionStrategy` enum (9-step ladder), `assign_collection_strategy()` with collateral + repeat-defaulter + cure-history adjustments, recovery probability decay by DPD |
| **ENH-CRD-R6** Continuous Portfolio Risk Monitoring (Unstructured) | `UnstructuredSignalType` enum, `aggregate_unstructured_signals()` with confidence gating, action-required flag |

### `utils/fairness_testing.py` (685 lines, **Cat A**) — ENH-CRD-R1

| Function | Standard / methodology |
|---|---|
| `compute_disparate_impact_ratio()` | EEOC 4/5ths rule (29 CFR §1607.4(D)); ECOA + Reg B |
| `compute_equal_opportunity_difference()` | Hardt et al. (2016); TPR parity across protected classes |
| `lda_latent_bias_search()` | Simplified Latent Dirichlet Allocation (Blei et al. 2003); plug a real LDA via `keyword_extractor` callable |
| `generate_fairness_report()` | Multi-protected-attribute audit + verdict aggregation |

## Regulatory provenance

### Portfolio monitoring
- **CBK Prudential Guideline CBK/PG/04** — risk classification of assets (NORMAL / WATCH / SUBSTANDARD / DOUBTFUL / LOSS)
- **CBK CRMF April 2021 §3.4** — early warning systems
- **IFRS 9 §5.5.3** — significant increase in credit risk (SICR)
- **IFRS 9 §B5.5.17** — quantitative + qualitative SICR factors
- **CBK Debt Recovery Reg 2022** — collections + recovery practices
- **Kenya Data Protection Act 2019** — adverse-data subject rights

### Fairness testing
- **ECOA** 15 USC §1691 — Equal Credit Opportunity Act
- **Reg B** 12 CFR Pt 1002
- **Fair Housing Act** for mortgage analog
- **EEOC Uniform Guidelines** 29 CFR §1607.4(D) — 4/5ths rule
- **EU AI Act Art 10** (fairness in training data) + Art 15 (non-discrimination)
- **Kenya Constitution Art 27** — equality and freedom from discrimination
- **Kenya Banking Act §52** — fair treatment of customers

## Key design decisions

### EWS — severity-3 immediate escalation
A single severity-3 signal (LIMIT_BREACH, INCOME_DROP, COVENANT_BREACH, etc.) → RED. Otherwise, weighted score ≥ 6 = RED, 1–5 = AMBER, 0 = GREEN. This prevents any high-severity event from being masked by aggregate scoring.

### Collections — collateral changes the strategy
DPD ≥ 91 normally → LEGAL_DEMAND / LITIGATION. With collateral → REPOSSESSION takes precedence. Repeat defaulters escalate one rung; ≥2 cures de-escalate from SOFT_REMINDER → NO_ACTION. Recovery probability decays by DPD bucket and adjusts ±30% for collateral / ±30% for repeat-default history.

### Unstructured signals — confidence-gated
`min_confidence=0.5` default filter; signals below it are dropped, not retained at lower weight. This prevents noisy social/news signals from accumulating into false positives.

### 4/5ths rule — three explicit failure modes
Beyond the standard PASS / POTENTIAL_DISPARATE_IMPACT verdicts, the engine surfaces:
- **INSUFFICIENT_DATA**: <30 records per group → cannot statistically distinguish
- **REFERENCE_GROUP_NO_APPROVALS**: divisor=0 → ratio undefined (rare but possible in small samples)

This avoids both false positives (insufficient data masquerading as bias) and false negatives (silently passing tests with bad data).

### LDA latent search — Rule 7 hookable
Default uses simple keyword frequency clustering (alphanumeric tokens length ≥ 4). For production, pass `keyword_extractor=callable(text) → frozenset(str)` to plug a sklearn / gensim LDA pipeline. The framework is data-source-agnostic; the heuristic default surfaces obvious skews.

## Engine Hub integration

Added two new tiers to `pages/7_admin.py`:

- **Tier 7 — Climate / ESG (v10.6-v10.10)** — 4 engines (esg_intelligence, climate_risk, climate_ecl_adjustment, esg_reporting_outputs)
- **Tier 8 — Credit AI Underwriting (v10.11-v10.14)** — 6 engines (ai_underwriting, applicant_data_sources, risk_based_pricing, credit_workflow, portfolio_monitoring, fairness_testing)

All 10 deep-impl engines now surface in the Engine Hub admin panel. **G117 coverage stays ≥ 95%.**

## Tests

- 23 self-tests in `portfolio_monitoring.py`
- 13 self-tests in `fairness_testing.py`
- 22 integration tests in `tests/integration/test_v10_14_portfolio_fairness.py`

## Verified output

```
✓ portfolio_monitoring self-test passed (23 tests)
✓ fairness_testing self-test passed (13 tests)
Ran 249 tests in 15.865s OK
Audit: 120/120 gates PASS
```

## Standards registry

```
Credit (subcategory) — 17 of 19 active after v10.14:
  ENH-119:    AI-Powered Credit Decisioning Engine          (v10.11)
  ENH-120:    Alternative Data Intelligence                  (v10.12)
  ENH-121:    Digital Identity Verification (eKYC)           (v10.12)
  ENH-122:    Real-Time Fraud Detection                      (v10.12)
  ENH-123:    Dynamic Risk-Based Pricing                     (v10.13)
  ENH-124:    Explainable AI for Regulatory Compliance       (v10.11)
  ENH-125:    End-to-End Digital Workflow Orchestration      (v10.13)
  ENH-126:    Dynamic Portfolio Monitoring & Early Warning  (v10.14) ← NEW
  ENH-128:    Collections & Recovery Intelligence            (v10.14) ← NEW
  ENH-129:    Credit Bureau Integration                      (v10.12)
  ENH-130:    Credit Committee Automation                    (v10.13)
  ENH-CRD-R1: LDA-Based Bias Search & Disparate Impact      (v10.14) ← NEW
  ENH-CRD-R2: EU AI Act High-Risk Classification Compliance (v10.11)
  ENH-CRD-R3: CFPB-Compliant Adverse Action Reason Codes    (v10.11)
  ENH-CRD-R5: GenAI Credit Memo Drafting Agent              (v10.13)
  ENH-CRD-R6: Continuous Portfolio Risk Monitoring (Unstr.) (v10.14) ← NEW
  ENH-CRD-R7: Confident Automation Pattern (80/20)          (v10.13)

Credit still planned: 2 (ENH-127 + ENH-CRD-R4 in v10.15; v10.16 closes)
```

## Honest acknowledgements

1. **EWS signal severity weights are heuristics**, not calibrated to historical default outcomes. Calibration belongs downstream when a sufficient default-event corpus exists.
2. **Recovery probability decay (0.99 → 0.85 → 0.65 → 0.40 → 0.20 → 0.08 by bucket)** is illustrative. Actual values come from regression of recovery rates against DPD buckets in the bank's data.
3. **CBK PG/04 classification by DPD only** is the regulatory floor; CBK rules also allow downgrade based on qualitative weakness signs independent of DPD. Production code should compose this DPD-floor with EWS findings to reach final classification (the engine supports this — feed EWS signals into the snapshot).
4. **Unstructured signal aggregation is heuristic** — counts, weights, confidence gates. A production NLP pipeline (sentiment + entity recognition + classification) feeds this, but the aggregation logic itself is durable.
5. **LDA latent search is simplified** — keyword frequency clustering is enough to surface obvious skews. Real LDA via sklearn/gensim plugs in via the `keyword_extractor` parameter — Rule 7 hookable.
6. **MIN_GROUP_SAMPLE_SIZE = 30** is the conventional floor for normal-distribution approximation. For smaller samples, a Fisher's exact test is more appropriate; that's an enhancement once we have a legal review of which test to standardize on.
7. **Protected attributes are HELD, not USED for decisions.** The engine captures them for fairness monitoring, not as input features. ECOA §1691(a) prohibits using them in decisioning. Compliance verification of feature exclusion is a separate audit gate (not yet shipped).
8. **No persistence.** All engines are in-memory; durable state lands when persistence layer is wired in subsequent batches.

## What v10.15 ships next

**Document management + group exposure** (final 2 standards):
- ENH-127 Digital Document Management & Verification
- ENH-CRD-R4 Multi-Product Portfolio Underwriting (Group Exposure)

These are the last 2 Credit standards before v10.16 closes the arc with G121 audit gate.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG | 13/13 | ✅ closed |
| **Batch 2 — Credit** | **17/19** | **🟡 4 batches done of 6** |
