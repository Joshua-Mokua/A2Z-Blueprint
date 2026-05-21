# CHANGELOG v10.23 — Audit/GRC Arc Batch 1: Core Audit Engine

**Audit:** 122/122 PASS — **106th consecutive clean.**
**Status:** Phase 2 batch 4 (Audit/GRC arc, v10.23-v10.27) opens.

## What ships in v10.23

`utils/audit_core.py` — 1122 lines, **Cat A**. 4 of 17 Audit/GRC standards active:

| Standard | Implemented as |
|---|---|
| **ENH-201** Audit Universe & Risk-Based Planning | `AuditableEntityType` enum (8 types: BUSINESS_LINE, LEGAL_ENTITY, PROCESS, SYSTEM, GEOGRAPHY, SUPPORT_FUNCTION, THIRD_PARTY, REGULATORY_DOMAIN); 5-tier `RiskRating` (VERY_LOW=1 to CRITICAL=5); `AuditableEntity` with `risk_score()` (inherent + residual); `AuditFrequency` enum (ANNUAL/BIENNIAL/TRIENNIAL/AS_REQUIRED); `DEFAULT_FREQUENCY_BY_RISK` mapping per IPPF Std 2010 (CRITICAL/HIGH→ANNUAL, MEDIUM→BIENNIAL, LOW→TRIENNIAL, VERY_LOW→AS_REQUIRED); `is_audit_due()` cycle calculation; `build_annual_audit_plan()` quarterly bucketing by risk |
| **ENH-202** Continuous Control Monitoring Engine | `ControlType` enum (PREVENTIVE/DETECTIVE/CORRECTIVE/DIRECTIVE per COSO); `ControlNature` (MANUAL/SEMI_AUTOMATED/AUTOMATED); `ControlFrequency` (REAL_TIME→AD_HOC); `ControlTestVerdict` (7 verdicts including REQUIRES_PROVIDER for Rule 7); 4-tier `ControlSeverity`; `DEFAULT_REMEDIATION_DAYS` (CRITICAL=7d, HIGH=30d, MEDIUM=60d, LOW=90d); `execute_control_test()` with severity inferred from exception rate (≥50%→CRITICAL, ≥20%→HIGH, ≥5%→MEDIUM, else LOW) |
| **ENH-203** Electronic Working Papers | `WorkingPaperType` enum (11 types per IPPF Std 2330: PLANNING_MEMO, RISK_ASSESSMENT, CONTROL_NARRATIVE, WALKTHROUGH, TEST_RESULTS, EXCEPTION_ANALYSIS, INTERVIEW_NOTES, EVIDENCE_DOCUMENT, MANAGEMENT_RESPONSE, AUDIT_REPORT, QUALITY_REVIEW); 5-state `WorkingPaperStatus`; `DEFAULT_WORKING_PAPER_RETENTION_YEARS=7` per CBK CRMF §7; SHA-256 `integrity_check()` for tamper detection; `compute_paper_hash()` |
| **ENH-AUD-R7** Connect-Validate-Respond Architecture | 3-stage `CVRStage` (CONNECT/VALIDATE/RESPOND); `CVRConnectorType` (8 types: DATABASE/API/FILE_SYSTEM/SWIFT_FEED/GL_FEED/CBS_FEED/LDAP_DIRECTORY/SIEM_LOG); `CVRResponseAction` (7 actions including BLOCK_TRANSACTION for preventive controls); `run_connect_validate_respond()` with hookable connector/validator/responder per Rule 7 — surfaces stage-completed for partial runs |

## Regulatory provenance

- **IIA International Standards for Internal Auditing (IPPF)**
- **IPPF Standard 1100** — independence and objectivity
- **IPPF Standard 2010** — risk-based planning
- **IPPF Standard 2120** — risk management
- **IPPF Standard 2330** — documenting information (working papers)
- **COSO Internal Control Integrated Framework** (2013)
- **COSO ERM Framework** (2017)
- **Basel Principles for the Assessment of Bank Internal Audit** (2012)
- **CBK Prudential Guideline CBK/PG/02** — operational risk
- **CBK CRMF April 2021 §7** — internal audit function
- **CBK Banking Act §44** — internal audit independence
- **Sarbanes-Oxley §302** + **§404** — internal control reporting
- **ISO 31000:2018** — Risk Management
- **ISO 27001 §A.18** — internal audit (information security)
- **ISACA COBIT 2019** — IT governance + audit

## Key design decisions

### 5-tier risk rating with numeric mapping
Mapping `VERY_LOW=1` to `CRITICAL=5` lets `risk_score()` compute combined inherent + residual prioritization (range 2-10). Higher score → higher priority in the annual plan. Avoids the "everyone is HIGH" inflation common in qualitative-only risk frameworks.

### Frequency-by-risk per IPPF Std 2010
`DEFAULT_FREQUENCY_BY_RISK` codifies industry standard:
- CRITICAL/HIGH → ANNUAL (12-month cycle)
- MEDIUM → BIENNIAL (24 months)
- LOW → TRIENNIAL (36 months)
- VERY_LOW → AS_REQUIRED (no fixed cycle)

The `is_audit_due()` check uses 30 days/month approximation × cycle months → days_since threshold. Production deployments override per their CAE's specific schedule.

### Annual plan: quarterly bucketing by risk
Critical/high risk → Q1 (200 hours each); medium → Q2 (120h); low → Q3/Q4 alternating (80h); very low → Q4 (40h). Front-loads high-risk audits early in the fiscal year — board-defensible per IPPF.

### Control test severity inferred from exception rate
Rather than asking the tester to declare severity (subjective), severity is derived from `exceptions_found / sample_size`:
- ≥50% exceptions → CRITICAL (control essentially non-operational)
- ≥20% → HIGH
- ≥5% → MEDIUM
- otherwise → LOW

This is auditor-defensible: severity has a deterministic calculation tied to evidence.

### Per-severity remediation deadlines per industry practice
- CRITICAL: 7 days
- HIGH: 30 days
- MEDIUM: 60 days
- LOW: 90 days

These match standard internal audit practice. Engine computes `remediation_due` automatically from test_date + severity days.

### Working papers SHA-256 integrity per IPPF Std 2330
Each working paper stores `sha256_content_hash` at filing. `integrity_check(current_content)` recomputes and compares — detects post-filing tampering. Standard cryptographic practice; auditor-defensible against assertions of "we have evidence."

### 7-year retention per CBK CRMF
`DEFAULT_WORKING_PAPER_RETENTION_YEARS=7` matches CBK's expectation for audit evidence (also aligns with SOX 7-year retention). Production deployments may extend (some banks retain 10 years).

### Connect-Validate-Respond as the assurance pattern
The CVR pattern (ENH-AUD-R7) is a 3-stage cycle that any continuous monitoring control should follow:
1. **Connect** to data source (DB, API, file, SWIFT, SIEM, etc.)
2. **Validate** against control criteria
3. **Respond** to detected failures (LOG_FINDING, OPEN_TICKET, ESCALATE_TO_AUDIT_COMMITTEE, etc.)

Per Rule 7: each stage is a callable hook. Engine surfaces `stage_completed` for partial runs — caller knows exactly how far the cycle got and why it stopped (no connector? no validator? validation crashed?).

### Rule 7 enforcement at every external boundary
- `execute_control_test()` without `automated_tester` → `REQUIRES_PROVIDER` verdict, NOT silent EFFECTIVE
- `run_connect_validate_respond()` without connector → `stage_completed=CONNECT, connect_success=False`
- All exceptions in hooks → INCONCLUSIVE (test) or stage-failure (CVR), with exception type + message preserved in notes

The engine cannot silently report "no findings" when no actual testing happened.

### Engine validates referential integrity
`register_control()` requires the entity to exist first (raises ValueError on missing entity). Same pattern across the codebase — composing engines must respect each other's preconditions.

## Engine Hub integration

**Tier 11 added.** New tier groups Audit/GRC engines distinctly from RMS (Tier 10) — distinguishing reconciliation from audit/compliance is important for ops/auditor users navigating the surfaces.

**G117 coverage holds at ≥ 95%.**

## Tests

- 28 self-tests in `audit_core.py`
- 22 integration tests in `tests/integration/test_v10_23_audit_core.py`

## Verified output

```
✓ audit_core self-test passed (28 tests)
Ran 452 tests in 52.119s OK
Audit: 122/122 gates PASS
```

## Standards registry — 4 Audit/GRC active

```
audit (subcategory) — 4 of 17 active after v10.23:
  ENH-201:    Audit Universe & Risk-Based Planning             (v10.23) ← NEW
  ENH-202:    Continuous Control Monitoring Engine             (v10.23) ← NEW
  ENH-203:    Electronic Working Papers                         (v10.23) ← NEW
  ENH-AUD-R7: Connect-Validate-Respond Architecture            (v10.23) ← NEW

Audit/GRC still planned: 13 (for v10.24-v10.26; v10.27 closes)
  ENH-204:    Issue Tracking & Remediation
  ENH-205:    AI-Powered Audit Analytics
  ENH-206:    Automated Control Testing
  ENH-207:    Auditor Dashboard & Mobile Access
  ENH-208:    External Auditor Portal
  ENH-209:    Audit Committee Reporting
  ENH-210:    Audit Trail & Compliance Certification
  ENH-AUD-R1: Control-Graph Cross-Framework Mapping
  ENH-AUD-R2: AI-Powered Third-Party / Vendor Risk Monitoring
  ENH-AUD-R3: Board-Ready Risk-Quantified Dashboards
  ENH-AUD-R4: Automated Remediation Ticketing Integration
  ENH-AUD-R5: 24/7 Always-On Assurance
  ENH-AUD-R6: Cybersecurity Audit Framework Integration
```

## Honest acknowledgements

1. **No actual testing is performed.** The engine is the orchestration framework. Real automated control tests (querying DBs, parsing GL, checking access logs) are per-deployment via `automated_tester` callable hooks. Without wiring, every test reports `REQUIRES_PROVIDER` — not silent pass.

2. **No external integrations ship.** CVR connectors for SIEM (e.g., Splunk, ELK), GL feeds, LDAP directory queries, CBS extracts — all require deployment-specific wiring. The framework supports them via `connector` callable; the wiring is downstream.

3. **No actual data analytics ship.** ENH-205 (AI-Powered Audit Analytics) is in v10.25 batch — this v10.23 batch deliberately scopes to the foundation. Same separation as v10.18 → v10.21 in RMS.

4. **No persistence.** Engine maintains entities, controls, test results, working papers, CVR runs in-memory per instance. Postgres persistence wires in a dedicated batch.

5. **Cycle calculation uses 30-day months.** A 12-month cycle = 360 days, not 365. For most audit purposes this is acceptable (5-day annual drift); production deployments may want exact calendar arithmetic.

6. **Working paper file content not stored in framework.** The `file_path` field references where the file lives; the engine stores only metadata + integrity hash. Production deployments wire to actual document management (S3 + KMS + audit logs).

7. **No e-signature for working paper review.** `reviewed_by_user_id` + `reviewed_at` capture review attribution; integration with DocuSign/Adobe Sign for actual qualified electronic signatures is per-deployment.

8. **Risk scoring is heuristic.** `risk_score()` = inherent + residual is a simple sum. Some frameworks weight residual higher (residual is what actually exists post-controls). Production deployments can override for their organization's risk methodology.

9. **No control framework cross-mapping.** ENH-AUD-R1 (Control-Graph Cross-Framework Mapping — COSO ↔ COBIT ↔ ISO 27001 ↔ NIST CSF) is in v10.24 batch.

10. **No vendor/third-party risk monitoring.** ENH-AUD-R2 (AI-Powered Third-Party Risk Monitoring) is in v10.25 batch.

## What v10.24 ships next

**Control testing extension + issue management** (4 standards):
- ENH-204 Issue Tracking & Remediation (issue lifecycle from finding → remediation → closure with aging)
- ENH-206 Automated Control Testing (test scripts library + scheduling + result aggregation across the v10.23 monitoring engine)
- ENH-AUD-R1 Control-Graph Cross-Framework Mapping (COSO ↔ COBIT ↔ ISO 27001 ↔ NIST CSF ↔ CBK PG/PG/02 cross-references)
- ENH-AUD-R4 Automated Remediation Ticketing Integration (Jira/ServiceNow hookable plus internal ticketing fallback)

These build on the v10.23 monitoring foundation — issue tracking takes failed test results from v10.23 and walks them through a workflow; automated testing provides a scriptable testing library; control-graph maps controls across multiple regulatory frameworks; ticketing integrates the remediation workflow with operations.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| Batch 2 — Credit (v10.11–v10.16) | 19/19 | ✅ closed |
| Enhancement — KESONIA (v10.17) | 1/1 | ✅ closed |
| Batch 3 — RMS Reconciliation (v10.18–v10.22) | 17/17 | ✅ closed |
| **Batch 4 — Audit/GRC (v10.23–v10.27)** | **4/17** | **🟡 in flight (1 of 5 batches)** |
| Batch 5+ — Treasury / Risk / Trade etc. | 0/116 | pending |

After v10.23: **66 of 247 standards active** (62 baseline + 4 new). 181 still planned across remaining categories.
