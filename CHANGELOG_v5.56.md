# A2Z MIS 360 — CHANGELOG v5.56

**Volume Ten — Compliance Intelligence**
**Released:** April 2026
**Audit gates:** 61/61 = 100% PASS (was 58/58)
**Test count:** 35 files / 947 tests (was 34/891 — added 56 in `tests/test_volume_ten_batch.py`)

---

## Standards delivered (4)

### #57 KYC/AML Risk Scoring (Cat B)
**Module:** `utils/kyc_aml_risk.py` (~410 LOC)
**Engine:** `KycAmlRiskEngine.assess_customer(customer)` → `KycRiskAssessment`

Deterministic 5-component additive scorecard producing 4 risk bands (LOW / MEDIUM / HIGH / PROHIBITED) per CBK PG/15 + FATF 40 recommendations.

**Scoring components (additive, capped):**
- Geography (0-30 points)
- Product (0-25 points)
- Customer Type (0-20 points)
- Channel (0-15 points)
- Behavior (0-10 points)

**Risk bands:** LOW (0-19) / MEDIUM (20-49) / HIGH (50-79) / PROHIBITED (80+)

**CDD level mapping:** LOW→Simplified DD, MEDIUM→Standard DD, HIGH→Enhanced DD, PROHIBITED→Onboarding Rejected.

**Honesty rules applied:**
- **Rule 4 (auto-prohibit, no override):** sanctions_hit OR prohibited jurisdiction → immediate PROHIBITED with `auto_prohibited=True`
- **Rule 6:** missing country/product/customer_type → non-zero score with explicit "pending KYC" reason (NEVER defaulted to LOW)

**Self-test:** 12/12 PASS

---

### #58 Sanctions Screening (Cat A schema + Cat C workflow) — **RULE 4 STRONGEST APPLICATION YET**
**Module:** `utils/sanctions_screening.py` (~360 LOC)
**Engine:** `SanctionsScreeningEngine`

Levenshtein-based deterministic fuzzy name screening across 5 sanctions lists (OFAC SDN, UN Consolidated, EU Consolidated, UK HMT, CBK Domestic).

**Workflow states (Cat C):** NEW_HIT → UNDER_REVIEW → CLEARED_FALSE | CONFIRMED_TRUE

**Cat A schema:** `risk.sanctions_list`, `risk.sanctions_record`, `risk.screening_result` (3 tables, all with PKs and indexes).

**The Rule 4 strongest formulation — terminal-state immutability:**
- `ALLOWED_TRANSITIONS[CLEARED_FALSE] = ()` — empty tuple makes the state architecturally immutable
- `ALLOWED_TRANSITIONS[CONFIRMED_TRUE] = ()` — same
- `NEW_HIT → CLEARED_FALSE` directly is BLOCKED — must pass through `UNDER_REVIEW`
- Mandatory `reviewer_id` + `clearance_reason` on every transition

This means a compliance officer cannot silently bypass review. The architectural constraint is verifiable at audit time via gate G60.

**Self-test:** 13/13 PASS

---

### #59 Transaction Monitoring (Cat B)
**Module:** `utils/transaction_monitoring.py` (~430 LOC)
**Engine:** `TransactionMonitoringEngine.scan(transactions)`

8 deterministic AML rules per CBK PG/15 §6 + FATF Recommendation 20:

| Rule | Name | Severity | Trigger |
|------|------|----------|---------|
| R1 | CASH_THRESHOLD_BREACH | HIGH | Single cash deposit/withdrawal > KES 1M |
| R2 | STRUCTURING_PATTERN | CRITICAL | 3+ deposits 800k-999k within 7 days |
| R3 | RAPID_MOVEMENT | HIGH | Funds in & out > KES 5M within 48 hrs |
| R4 | HIGH_RISK_GEOGRAPHY | CRITICAL | Wire to/from prohibited jurisdiction |
| R5 | ACCOUNT_DORMANT_ACTIVITY | MEDIUM | Activity > KES 100k on dormant account |
| R6 | ROUND_NUMBER_PATTERN | MEDIUM | 5+ identical round-number txns / 30 days |
| R7 | VELOCITY_BREACH | HIGH | Daily count > 20 OR daily amount > KES 10M |
| R8 | PEP_LARGE_TRANSACTION | HIGH | PEP customer txn > KES 2M |

**CBK byte-for-byte:** `CASH_REPORTING_THRESHOLD_KES = Decimal("1000000")`

**Honesty rules:**
- **Rule 1 (Decimal precision):** strict greater-than for all thresholds — 1M exactly does NOT trigger R1
- **Rule 4:** alerts cannot be auto-dismissed; OPEN→DISMISSED blocked, must pass through INVESTIGATING; mandatory `reviewer_id` + `resolution_reason` on terminal states

**Self-test:** 14/14 PASS

---

### #60 FATCA/CRS Reporting (Cat A schema + Cat B aggregation)
**Module:** `utils/fatca_crs.py` (~420 LOC)
**Engine:** `FatcaCrsReportingEngine`

Deterministic reportable-status determination for FATCA (US person + IRS Form 8966) and CRS (~40 OECD participating jurisdictions).

**FATCA byte-for-byte (IRC §1471):**
- `FATCA_INDIVIDUAL_THRESHOLD_USD = Decimal("50000")`
- `FATCA_ENTITY_THRESHOLD_USD = Decimal("250000")`
- `FATCA_FORM = "8966"`

**CRS byte-for-byte:**
- ~40 participating jurisdictions (GB, DE, FR, IT, ES, NL, BE, CH, US, CA, AU, JP, SG, ZA, MU, AE, etc.)
- `HOME_JURISDICTION = "KE"` (Kenyan tax residents excluded from CRS reporting)

**Status enum:** REPORTABLE_FATCA / REPORTABLE_CRS / REPORTABLE_BOTH / NOT_REPORTABLE / **UNDOCUMENTED**

**Cat A schema:** `tax.account_holder_self_cert`, `tax.reportable_account`, `tax.reporting_submission` (3 tables with PKs).

**Honesty rules:**
- **Rule 1 (Decimal precision):** strict greater-than — 50000.00 USD NOT reportable; 50000.01 USD reportable
- **Rule 6:** missing or inactive self-certification → status = `UNDOCUMENTED` (highest scrutiny, NEVER auto-non-reportable)

**Self-test:** 16/16 PASS

---

## Audit gates added (3)

### G59 `kyc_aml_risk_correct`
Combined inline programmatic + artifact-handoff gate.
- Inline: 4 risk band thresholds byte-for-byte; PROHIBITED+HIGH jurisdictions; CDD mapping; Rule 4 sanctions auto-prohibit; Rule 6 missing-country
- Artifact: `kyc_aml_results.json` from harness fixture KY001-KY010 — observed 10/10 = 100% accuracy

**Tampering verified:**
- `RISK_BAND_PROHIBITED_MIN` (80→100) caught with 1 violation
- Drop "KP" from `PROHIBITED_JURISDICTIONS` caught with 2 violations (including harness drop to 90%)

### G60 `sanctions_screening_correct` — **RULE 4 STRONGEST VERIFICATION**
Inline programmatic — verifies `SUPPORTED_SANCTIONS_LISTS` membership byte-for-byte; `SCREENING_HIT_THRESHOLD == 75`; **`ALLOWED_TRANSITIONS` enforces NEW→CLEARED_FALSE blocked + terminal states immutable**; runtime workflow check that `transition_hit(NEW_HIT → CLEARED_FALSE)` returns `(False, "transition_not_allowed")`; Rule 6 unknown-list filtering; schema PK presence.

**Tampering verified:**
- `SCREENING_HIT_THRESHOLD` (75→50) caught
- **Tampered `ALLOWED_TRANSITIONS` to allow `NEW_HIT→CLEARED_FALSE` direct caught with 2 violations** — most important Rule 4 verification yet

### G61 `transaction_monitoring_fatca_crs_correct`
Combined inline programmatic for #59 + #60.
- TXN MON: `CASH_REPORTING_THRESHOLD_KES == Decimal("1000000")` byte-for-byte; 8 RULE_CATALOG entries R1-R8 with exact name+severity; R2/R4 CRITICAL; Rule 4 OPEN→DISMISSED blocked
- FATCA/CRS: thresholds 50k/250k byte-for-byte; FATCA_FORM="8966"; HOME_JURISDICTION="KE"; SPEC_DEVIATION_NOTE byte-for-byte; Rule 1 strict-greater-than; Rule 6 UNDOCUMENTED default; 3 schema PKs

**Tampering verified:**
- `CASH_REPORTING_THRESHOLD_KES` (1M→500k) caught
- `FATCA_INDIVIDUAL_THRESHOLD_USD` (50k→25k) caught with 2 violations including Rule 1 violation surfaced via runtime check
- `SPEC_DEVIATION_NOTE` drift caught

---

## Spec deviations (cumulative — now 6)

| # | Volume | Description |
|---|--------|-------------|
| 1 | v5.49 | Heatmap React→Streamlit/plotly |
| 2 | v5.51 | React SPA + React Native scaffolding |
| 3 | v5.52 | Rule 7 / Cat D scaffolding pattern formalized |
| 4 | v5.52 | #48 LLM commentary deferred (rule-based template engine ships) |
| 5 | v5.55 | CBK reports: 3 of 8 fully implemented (CAR + LE + LCR); 5 deferred (NSFR, INSIDER_LOANS, CONNECTED_LENDING, SECTORAL_LIMITS, FX_NET_OPEN_POSITION) |
| **6** | **v5.56** | **Full FATCA Form 8966 XML and OECD CRS XML generation deferred to v7; v6 ships deterministic classification + balance aggregation + skeleton envelope** |

---

## Honesty rules — pattern stability

This volume advanced **Rule 4 (default-strict downstream submission) to its strongest application yet** — terminal-state immutability via empty-tuple `ALLOWED_TRANSITIONS` (#58 sanctions screening). The architectural constraint that compliance reviewers cannot silently bypass review is now auditable via introspection at gate G60.

**Rule 4 progression:**
- v5.53 #42: Legal hold blocks MODIFY/DELETE while permitting VIEW (no override mode)
- v5.54 #50: No `force_advance`, `override_criteria`, `admin_skip`, `bypass_gate` methods (introspection-verified)
- **v5.56 #58: Terminal states have empty allowed-transitions tuple (architecturally immutable)** ← strongest yet
- **v5.56 #59: Alerts cannot be auto-dismissed (must pass through INVESTIGATING)**

**No new Rule 7 application this volume.** KYC/AML risk scoring stayed Cat B rule-based (ML deferred). Rule 7 application count remains 3 (#48 BI commentary, #41 dormancy prediction, #53 credit risk scoring).

---

## What's new in v5.56 vs v5.55

| | v5.55 | v5.56 |
|--|-------|-------|
| Standards delivered | 56 | 60 |
| Audit gates | 58 | 61 |
| Test files | 34 | 35 |
| Total tests | 891 | 947 |
| Spec deviations | 5 | 6 |
| Rule 4 applications | 2 | 4 |
| Rule 7 applications | 3 | 3 (no change) |

---

## Next: Volume Eleven — HR Intelligence (#61-#64)

Anticipated standards (subject to A2Z_Continuation_Spec_v6.md):
- #61 Workforce Analytics (Cat B — headcount, attrition, span-of-control)
- #62 Compensation & Pay Equity (Cat B — gender pay gap, internal equity)
- #63 Performance & Talent Pipeline (Cat B/C — calibration, succession)
- #64 Employee Engagement Intelligence (potential 4th Rule 7 application — sentiment scoring)

Target: 4 engines + fixtures + 3 gates G62-G64 → 64/64.
