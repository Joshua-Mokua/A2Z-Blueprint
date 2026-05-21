# CHANGELOG v10.15 — Credit batch 5: Document Management + Group Exposure

**Audit:** 120/120 PASS — **98th consecutive clean. All 19 Credit standards now active.**

## What ships in v10.15

Two focused modules covering the final 2 of 19 Credit standards:

### `utils/document_management.py` (818 lines, **Cat B**) — ENH-127

Digital document lifecycle, authenticity verification, retention tracking.

| Component | Purpose |
|---|---|
| `DocumentType` enum (18 types) | National ID, passport, KRA PIN, payslip, bank statement, audited financials, business permit, CR12, title deed, logbook, valuation, insurance, etc. |
| `DocumentState` enum (9 states) | SUBMITTED → AUTHENTICITY_PENDING → DATA_EXTRACTION_PENDING → VERIFIED / REJECTED / EXPIRED / ARCHIVED |
| `ALLOWED_DOC_TRANSITIONS` | Explicit transition graph — invalid skips raise ValueError |
| `DOC_RETENTION_YEARS` | KYC docs: 7yr (CBK AML 2017 §16); tax docs: 5yr (Tax Procedures Act §23); loan/collateral: 7yr (Banking Act §54) |
| `DOC_VALIDITY_WINDOW_DAYS` | Payslip/bank statement: 90d; mgmt accounts: 365d; audited financials: 547d; static identity: per-doc expiry |
| `AuthenticityCheck` enum (8 checks) | hash integrity, format, metadata, digital signature, MRZ, hologram, watermark, issuer lookup |
| `verify_file_integrity()` | SHA-256 hex digest comparison |
| `verify_format()` | PDF required for financials; PDF/image for identity |
| `is_document_expired()` | Explicit expiry > validity window > no rule (precedence) |
| `extract_fields()` | OCR/parser hookable per Rule 7 — no fabrication when no provider |
| `assess_document()` | End-to-end: integrity + format + expiry + extraction → terminal state |
| `DocumentManagementEngine` | Per-applicant document tracking + expiry surfacing |

### `utils/group_exposure.py` (786 lines, **Cat A**) — ENH-CRD-R4

Single obligor + group + insider lending limits per CBK Banking Act.

| Limit | Source | Threshold |
|---|---|---|
| Single Obligor | Banking Act §10A | **25%** of core capital |
| Single Insider | Banking Act §11(1) | **5%** of core capital |
| Aggregate Insider | Banking Act §11 | **20%** of core capital |
| Group / Large Exposure | Basel BCBS 283 + EU CRR Art 395 | **25%** of core capital |
| Large Exposure Reporting | CBK PG/06 | **≥10%** triggers reporting |

| Component | Purpose |
|---|---|
| `ExposureType` enum (8 types) | Term loan, overdraft, revolving, card, LC, guarantee, derivative PFE, undrawn commitment |
| `EXPOSURE_CCF` mapping | Basel CCF: LC=0.5, derivative=0.4, undrawn=0.4, on-BS=1.0 |
| `RelationshipType` enum (8 types) | NONE, GROUP_PARENT/SUBSIDIARY/AFFILIATE, INSIDER_DIRECTOR/OFFICER/SHAREHOLDER/RELATED |
| `LimitVerdict` enum (4 levels) | WITHIN_LIMIT / APPROACHING (≥80%) / NEAR_BREACH (≥95%) / BREACHED (>100%) |
| `Exposure.credit_equivalent_kes()` | drawn × 1.0 + undrawn × CCF |
| `aggregate_obligor_exposure()` | Sum across all facilities to one obligor |
| `aggregate_group_exposure()` | Sum across all obligors with same group_id |
| `aggregate_insider_exposure()` | Sum across all obligors flagged as insiders |
| `assess_group_exposure()` | Unified report with all relevant checks + breaches list |
| `GroupExposureEngine` | Portfolio-wide tracking with breach + large-exposure aggregation |

## Regulatory provenance

### Document management
- **Kenya Data Protection Act 2019 §28** — retention principles
- **Kenya Data Protection (General) Regulations 2021** — operational rules
- **CBK Digital Lending Regulations 2022 §15** — record-keeping
- **CBK AML/CFT Guideline 2017 §16** — KYC document retention 7 years
- **Kenya Tax Procedures Act §23** — KRA documents 5 years
- **EU eIDAS Regulation 910/2014** — qualified electronic signatures
- **ISO 27001** — information security management
- **ISO 19005 / PDF/A** — long-term archival format

### Group exposure
- **Kenya Banking Act §10A** — Single Obligor Limit (25%)
- **Kenya Banking Act §11** — Insider lending (single 5% / aggregate 20%)
- **CBK Prudential Guideline CBK/PG/05** — connected/insider lending
- **CBK Prudential Guideline CBK/PG/06** — large exposures
- **Basel BCBS Large Exposures Framework (2014, BCBS 283)** — 25% LE cap
- **EU CRR Art 395** — 25% Tier 1 capital large-exposure limit

## Key design decisions

### Document state transitions are explicit
`ALLOWED_DOC_TRANSITIONS` is a deterministic graph — no free-form state changes. Identity docs flow SUBMITTED → AUTHENTICITY_PENDING → AUTHENTICITY_FAILED OR DATA_EXTRACTION_PENDING → VERIFIED OR EXTRACTION_FAILED. Terminal states (REJECTED, ARCHIVED) have empty out-edges. Same pattern as v10.13 credit_workflow.

### Document expiry has precedence rules
1. Explicit `expires_at` if set (takes priority)
2. Otherwise `issued_date + DOC_VALIDITY_WINDOW_DAYS[type]` if window exists
3. Otherwise: never expires (static identity docs without explicit expiry)

This handles all real document types: ID with explicit expiry, payslip with sliding 90-day window, title deed without any expiry rule.

### Rule 7 honesty in OCR
`extract_fields()` requires an injected `extractor` callable. When no extractor is provided, the engine returns empty fields + explicit reason "no extractor provided — Rule 7 honesty: no fabricated data". Document state advances to `DATA_EXTRACTION_PENDING` rather than silently fabricating extracted values. When the OCR provider is wired (Tesseract, Google Cloud Vision, Azure Computer Vision, AWS Textract, etc.), the same engine call works without code changes.

### Credit-equivalent exposure (Basel CCF)
`Exposure.credit_equivalent_kes()` aggregates drawn + undrawn × CCF per Basel framework. This means:
- A KES 1M term loan with KES 1M outstanding → CE = KES 1M
- A KES 1M LC with KES 500K utilized → CE = 500K + 500K × 0.5 = KES 750K
- A KES 1M revolving credit with KES 400K drawn → CE = 400K + 600K × 1.0 = KES 1M

This conservative aggregation is what limit checks must use to be Basel-compliant. Pure outstanding-only aggregation would understate exposure.

### Insider checks fire automatically
When `Obligor.relationship_to_bank` is one of the INSIDER_* relationships, `assess_group_exposure()` automatically runs both single insider (5%) and aggregate insider (20%) checks. No special call needed — the report just includes them.

### Approaching / Near-Breach early warning
Beyond binary WITHIN/BREACHED, the engine flags 80% (APPROACHING) and 95% (NEAR_BREACH) thresholds. These give credit ops + treasury time to react before a hard breach.

## Engine Hub integration

Tier 8 expanded from 6 to 8 engines. The new entries cover document_management + group_exposure with their relationship to Banking Act §10A/§11. **G117 coverage holds at ≥ 95%.**

## Tests

- 23 self-tests in `document_management.py`
- 20 self-tests in `group_exposure.py`
- 22 integration tests in `tests/integration/test_v10_15_docs_group_exposure.py`

## Verified output

```
✓ document_management self-test passed (23 tests)
✓ group_exposure self-test passed (20 tests)
Ran 271 tests in 15.756s OK
Audit: 120/120 gates PASS
```

## Standards registry — Credit fully active

```
Credit (subcategory) — 19 of 19 active after v10.15:
  ENH-119:    AI-Powered Credit Decisioning Engine          (v10.11)
  ENH-120:    Alternative Data Intelligence                  (v10.12)
  ENH-121:    Digital Identity Verification (eKYC)           (v10.12)
  ENH-122:    Real-Time Fraud Detection                      (v10.12)
  ENH-123:    Dynamic Risk-Based Pricing                     (v10.13)
  ENH-124:    Explainable AI for Regulatory Compliance       (v10.11)
  ENH-125:    End-to-End Digital Workflow Orchestration      (v10.13)
  ENH-126:    Dynamic Portfolio Monitoring & Early Warning  (v10.14)
  ENH-127:    Digital Document Management & Verification    (v10.15) ← NEW
  ENH-128:    Collections & Recovery Intelligence            (v10.14)
  ENH-129:    Credit Bureau Integration                      (v10.12)
  ENH-130:    Credit Committee Automation                    (v10.13)
  ENH-CRD-R1: LDA-Based Bias Search & Disparate Impact      (v10.14)
  ENH-CRD-R2: EU AI Act High-Risk Classification Compliance (v10.11)
  ENH-CRD-R3: CFPB-Compliant Adverse Action Reason Codes    (v10.11)
  ENH-CRD-R4: Multi-Product Portfolio Underwriting (Group)  (v10.15) ← NEW
  ENH-CRD-R5: GenAI Credit Memo Drafting Agent              (v10.13)
  ENH-CRD-R6: Continuous Portfolio Risk Monitoring (Unstr.) (v10.14)
  ENH-CRD-R7: Confident Automation Pattern (80/20)          (v10.13)

Credit still planned: 0
```

## Honest acknowledgements

1. **Document hash integrity uses SHA-256 only.** Production systems may also verify cryptographic signatures (PKI for digital signatures, eIDAS-qualified certificates). The framework supports `DIGITAL_SIGNATURE_VERIFY` as an authenticity check; the verification logic itself is provider-specific (DocuSign, Adobe Sign, etc.) and plugs in via additional `AuthenticityCheckResult` items.
2. **Format validation is basic** (extension + PDF-required-for-financials). Production systems would add MIME-sniffing, content-type validation, virus scanning. The architecture supports this — additional `verify_format`-style functions can be composed.
3. **OCR/extraction is callable-hookable** (Rule 7). No actual OCR ships with this batch. Tesseract / Google Vision / Azure / AWS Textract integration is per-deployment.
4. **Document expiry windows (90d / 365d / 547d)** are conventional values; some regulators or product policies require different windows. Override per-deployment by editing `DOC_VALIDITY_WINDOW_DAYS`.
5. **Group identification is `group_id`-based.** Real-world group identification (parent-subsidiary corporate structure, common control via shareholding ≥20%, family relationships for individuals) is upstream investigation work. The engine accepts the identification; building it is per-deployment.
6. **Banking Act §10A / §11 percentages are hardcoded.** If CBK amends the limits via Prudential Guideline (e.g., post-Basel-IV), update `SINGLE_OBLIGOR_LIMIT_PCT` etc. Worth pulling from `system_invariants` for cross-engine consistency in a future refinement.
7. **Single Obligor Limit excludes capital-deductible exposures** per CBK PG/06; this engine treats all exposure types as in-scope. For a more nuanced application, the caller should pre-filter exposures to those subject to the limit.
8. **No persistence.** All engines are in-memory.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| **Batch 2 — Credit (v10.11–v10.15)** | **19/19** | **🟢 ready for v10.16 closure** |
| Batch 3 — RMS (v10.17–v10.21) | 0/17 | pending |

## What v10.16 ships next

**G121 audit gate + Credit deep-impl arc closure.** Per the established 6-batch arc pattern:

1. Add `gate_credit_engines_implemented()` to `scripts/audit.py` as G121
2. Verify all 19 Credit standards have `status='active'`
3. Verify all 8 Credit engines exist on disk + import cleanly:
   - `ai_underwriting`, `applicant_data_sources`, `risk_based_pricing`, `credit_workflow`, `portfolio_monitoring`, `fairness_testing`, `document_management`, `group_exposure`
4. Verify integration test files exist for v10.11-v10.15
5. Drift-test G121 (rename engine → fail; demote standard → fail; restore → pass)
6. Closing CHANGELOG with the full 6-batch retrospective
7. Phase 2 batch 2 closure package
