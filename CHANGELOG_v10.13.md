# CHANGELOG v10.13 — Credit batch 3: Pricing + Workflow + Committee + Memo + 80/20

**Audit:** 120/120 PASS — **96th consecutive clean.**

## What ships in v10.13

Two cohesive modules covering 5 of 19 Credit standards:

### `utils/risk_based_pricing.py` (472 lines, **Cat A**) — ENH-123

Risk-adjusted rate calculation per Basel III IRB principles.

| Component | Source |
|---|---|
| Funding cost | bank's marginal funding rate (input) |
| Expected Loss | PD × LGD |
| Capital charge | Basel IRB K(PD) × LGD × cost_of_equity |
| Operating cost | configurable, default 1.5% |
| Target margin | configurable, default 3.0% |
| **Required rate** | sum of above |

Plus RAROC = (revenue – funding – EL – opex) / capital_ratio.

`PricingDecision` outcomes: PRICE_OFFERED, PRICE_AT_FLOOR, PRICE_AT_CEILING, DECLINE_UNECONOMIC, REFER_HUMAN.

### `utils/credit_workflow.py` (897 lines, **Cat A**) — ENH-125, ENH-130, ENH-CRD-R5, ENH-CRD-R7

| Sub-system | Standard | Components |
|---|---|---|
| **State machine** | ENH-125 | 17-state `ApplicationState` enum + explicit `ALLOWED_TRANSITIONS` graph + `is_terminal_state()` / `is_valid_transition()` |
| **80/20 automation policy** | ENH-CRD-R7 | `evaluate_automation()` with 4-tier amount thresholds + confidence gate + high-risk-sector gate + first-loan KYC gate + jurisdiction gate |
| **Credit committee** | ENH-130 | `CommitteeRole` enum (7 roles), `COMMITTEE_REQUIREMENTS` per tier (quorum + role mix + approval threshold), `evaluate_committee_decision()` returning APPROVED / DECLINED / NO_QUORUM / TIE |
| **Memo drafting** | ENH-CRD-R5 | 8 required sections, `draft_memo_template()` with rule-based default + LLM callable hook (Rule 7 — no silent generation) |
| **Workflow engine** | (orchestrator) | `CreditWorkflowEngine` — registers state, transitions, committee decisions, memos with full audit trail |

## Regulatory provenance

- **Basel III IRB** (BCBS 128 / BCBS 424) — capital charge formula
- **CBK Prudential Guideline CBK/PG/03** — capital adequacy 14% target
- **CBK Banking Act §44** — interest rate disclosure requirements
- **Truth in Lending Act / Reg Z** §1026.18 — APR disclosure analog
- **CBK Digital Lending Reg 2022 §12** — affordability assessment
- **CBK Prudential Guideline CBK/PG/13** — credit risk management

## Key design decisions

### Capital charge — Basel IRB simplified
Rather than reimplementing the full Basel IRB supervisory formula (which involves correlation R, maturity adjustment b, and a normal CDF), we use a **deterministic linear lookup table** calibrated to typical Basel IRB outputs at LGD=0.45, M=2.5y. The table covers PD bands from 0.01% to 100% with linear interpolation between points. This is defensible (capital figures match Basel IRB within ~10%) and auditable (no opaque math).

### State machine — explicit graph, not regex
`ALLOWED_TRANSITIONS: Mapping[State, Tuple[State, ...]]` lists every allowed transition. Invalid transitions raise `ValueError` with the allowed-list in the message. This makes the workflow auditable and prevents silent drift through unintended paths.

### 80/20 automation — explicit thresholds
4 amount tiers (≤500K, ≤5M, ≤50M, >50M KES) with explicit handling per tier. Confidence threshold default = 0.80 from v10.11 ConfidenceLevel.HIGH. High-risk sectors (FOSSIL_FUELS_OIL_GAS, REAL_ESTATE_COASTAL, etc.) and first-loan + first-jurisdiction trigger HUMAN_REVIEW even if other gates would pass.

### Committee — role × quorum × threshold
Tier 2 (500K – 5M): 2-of-2 from {Credit, Risk}, 60% threshold
Tier 3 (5M – 50M): 3-of-4 from {Credit, Risk, Business, Compliance}, 75% threshold
Tier 4 (>50M): 4-of-5 board-level, 80% threshold

### Memo — Rule 7 honesty for GenAI
Default `draft_memo_template()` produces deterministic templated text in 8 required sections + surfaces `SPEC_DEVIATION_NOTE`. Pass an `llm_hook: Callable[[section_name, context], str]` to have an LLM draft each section. The result's `drafted_by` field flips to `"gen_ai"` and `deviation_notes` clears. **No silent LLM generation** — caller must explicitly opt in.

## Tests

- 12 self-tests in `risk_based_pricing.py`
- 19 self-tests in `credit_workflow.py`
- 25 integration tests in `tests/integration/test_v10_13_pricing_workflow.py`

## Verified output

```
✓ risk_based_pricing self-test passed (12 tests)
✓ credit_workflow self-test passed (19 tests)
Ran 227 tests in 18.645s OK
Audit: 120/120 gates PASS
```

## Standards registry

```
Credit (subcategory) — 13 of 19 active after v10.13:
  ENH-119:    AI-Powered Credit Decisioning Engine          (v10.11)
  ENH-120:    Alternative Data Intelligence                  (v10.12)
  ENH-121:    Digital Identity Verification (eKYC)           (v10.12)
  ENH-122:    Real-Time Fraud Detection                      (v10.12)
  ENH-123:    Dynamic Risk-Based Pricing                     (v10.13) ← NEW
  ENH-124:    Explainable AI for Regulatory Compliance       (v10.11)
  ENH-125:    End-to-End Digital Workflow Orchestration      (v10.13) ← NEW
  ENH-129:    Credit Bureau Integration                      (v10.12)
  ENH-130:    Credit Committee Automation                    (v10.13) ← NEW
  ENH-CRD-R2: EU AI Act High-Risk Classification Compliance (v10.11)
  ENH-CRD-R3: CFPB-Compliant Adverse Action Reason Codes    (v10.11)
  ENH-CRD-R5: GenAI Credit Memo Drafting Agent              (v10.13) ← NEW
  ENH-CRD-R7: Confident Automation Pattern (80/20)          (v10.13) ← NEW

Credit still planned: 6 (for v10.14-v10.15; v10.16 closes)
```

## Honest acknowledgements

1. **Basel IRB K-table is approximation.** Real Basel IRB capital is computed via the full supervisory formula (correlation R = 0.12 × (1 - exp(-50×PD))/(1 - exp(-50)) + 0.24 × (1 - (1 - exp(-50×PD))/(1 - exp(-50))), then K = LGD × N(...) - PD × LGD with normal CDF). Our linear table matches the formula's outputs within ~10% across typical PD bands. For regulatory capital reporting itself, banks use the full formula via their finance/risk systems — this engine is for pricing, not capital reporting.
2. **Rate floor (6%) and ceiling (32%)** are illustrative. Kenya's market practice ranges widely; CBK no longer caps interest rates as of 2019 (Banking (Amendment) Act 2016 was repealed in 2019), but reputational + competitive constraints still create soft ceilings. Banks should configure these per product.
3. **Default operating cost (1.5%) and target margin (3%)** are illustrative. Real values depend on product, channel, customer segment.
4. **Committee role definitions** (HEAD_OF_CREDIT, etc.) are conventional naming. Different banks use different titles; the framework just requires consistent mapping.
5. **Memo template is bare-bones.** Production deployment would expand each section with bank-specific language, citation patterns, and quantitative tables. The 8 required sections + LLM hook architecture are the durable parts.
6. **State machine doesn't model time-based transitions** (e.g., auto-expire after 90 days). That requires a scheduler/cron — outside this batch's scope.
7. **No persistence.** Workflow state lives in-memory per engine instance.

## What v10.14 ships next

**Portfolio monitoring + collections + bias testing + unstructured data** (4 standards):
- ENH-126 Dynamic Portfolio Monitoring & Early Warning
- ENH-128 Collections & Recovery Intelligence
- ENH-CRD-R1 LDA-Based Bias Search & Disparate Impact Testing
- ENH-CRD-R6 Continuous Portfolio Risk Monitoring (Unstructured Data)

These shift focus from acquisition (decisioning + workflow) to lifecycle (portfolio monitoring + collections + fairness + behavioral signals).

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG | 13/13 | ✅ closed |
| **Batch 2 — Credit** | **13/19** | **🟡 3 batches done of 6** |
| Batch 3 — RMS | 0/17 | pending |
