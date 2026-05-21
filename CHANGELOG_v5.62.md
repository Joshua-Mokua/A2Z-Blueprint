# A2Z MIS 360 — CHANGELOG v5.62

**Volume Sixteen — Internal Audit / Internal Controls**
**Released:** April 2026
**Audit gates:** 79/79 = 100% PASS (was 76/76)
**Test count:** 41 files / 1333 tests (was 40/1248 — added 85 in `tests/test_volume_sixteen_batch.py`)

---

## Standards delivered (4 — all Cat B audit/controls metrics)

### #81 Internal Audit Universe & Risk-Based Audit Planning (Cat B)
**Module:** `utils/audit_universe.py` (~430 LOC)
**Engine:** `AuditUniverseEngine`

5 entries: `inherent_risk_score`, `control_environment_score`, `residual_risk_score`, `generate_audit_plan`, `audit_universe_summary`.

**Risk tier thresholds byte-for-byte (IIA + CBK PG/15):**

| Tier | Residual threshold | Audit frequency |
|---|---|---|
| HIGH | ≥ 70 | 12 months (annual) |
| MEDIUM | 40-69 | 24 months (biennial) |
| LOW | < 40 | 36 months (triennial) |

**6 INHERENT_RISK_WEIGHTS_PCT byte-for-byte (sum=100):**

| Factor | Weight |
|---|---|
| financial_materiality_kes | 30% |
| transaction_volume | 15% |
| regulatory_exposure | 20% |
| fraud_susceptibility | 15% |
| process_complexity | 10% |
| change_velocity | 10% |

**5 CONTROL_RATING_BANDS byte-for-byte:**

| Rating | Score range |
|---|---|
| EFFECTIVE | 90-100 |
| LARGELY_EFFECTIVE | 70-89 |
| PARTIALLY_EFFECTIVE | 50-69 |
| INEFFECTIVE | 25-49 |
| NON_EXISTENT | 0-24 |

**6 ENTITY_TYPES catalog:** BRANCH, DEPARTMENT, PROCESS, SUBSIDIARY, IT_SYSTEM, PRODUCT_LINE.

**6 MATERIALITY_THRESHOLDS_KES** mapping table (100M→100 score, 50M→80, 10M→60, 1M→40, 100K→20, 0→0).

**Rolling audit plan generator:** uses STRICT `cur < plan_end` for clean year boundaries (3-year HIGH plan = exactly 3 audits, not 4); month-step rolling forward with day-clamping at 28 to handle Feb edge case.

**Inherent score re-normalisation:** when factors are missing, present-factor weights re-normalise to sum 100 (Rule 6 transparent, not silently zero-imputed).

**Residual = Inherent × (1 - Control/100)**; missing control = no mitigation assumed (worst case).

**Honesty rules:**
- **Rule 1:** residual=None when inherent is None
- **Rule 6:** missing factors surfaced in `missing_factors[]`

**Self-test:** 18/18 PASS

---

### #82 Internal Controls Framework (Cat B)
**Module:** `utils/internal_controls.py` (~470 LOC)
**Engine:** `InternalControlsEngine`

5 entries: `sample_size`, `test_control`, `classify_deficiency`, `coso_component_score`, `control_effectiveness_summary`.

**5 COSO_COMPONENTS byte-for-byte (COSO 2013):**
1. CONTROL_ENVIRONMENT (5 principles)
2. RISK_ASSESSMENT (4 principles)
3. CONTROL_ACTIVITIES (3 principles)
4. INFORMATION_COMMUNICATION (3 principles)
5. MONITORING_ACTIVITIES (2 principles)

**TOTAL_COSO_PRINCIPLES = 17** (constant sanity check).

**4 SAMPLE_SIZES_BY_RISK byte-for-byte (ISA 530 / AICPA AU-C 530):**

| Risk level | Sample size | Tolerable exception rate |
|---|---|---|
| LOW | 25 | 10% |
| MEDIUM | 40 | 5% |
| HIGH | 60 | 2% |
| KEY | 90 | 0% (zero-tolerance) |

**3 DEFICIENCY_SEVERITIES byte-for-byte (PCAOB AS 2201):**

| Severity | Threshold |
|---|---|
| DEFICIENCY | < 1% of total assets |
| SIGNIFICANT_DEFICIENCY | 1-5% of total assets |
| MATERIAL_WEAKNESS | ≥ 5% of total assets |

**3 TEST_OUTCOMES:** EFFECTIVE (0 exceptions), PARTIALLY_EFFECTIVE (within tolerance), INEFFECTIVE (exceeds tolerance).

**Severity escalation rule:** small impact + affects financial reporting + no compensating controls → upgrade DEFICIENCY → SIGNIFICANT_DEFICIENCY.

**Honesty rules:**
- **Rule 1:** effectiveness_pct=None when sample_size≤0
- **Rule 6:** missing exception count → outcome=None

**Self-test:** 23/23 PASS

---

### #83 Issue Management & Remediation Tracking (Cat B)
**Module:** `utils/issue_management.py` (~470 LOC)
**Engine:** `IssueManagementEngine`

5 entries: `classify_issue_severity`, `aging_bucket`, `sla_breach_check`, `escalation_required`, `kri_summary`.

**4 ISSUE_SEVERITIES + SLA_TARGET_DAYS byte-for-byte:**

| Severity | SLA | Escalation target | Days threshold |
|---|---|---|---|
| CRITICAL | 30 days | BOARD_AUDIT_COMMITTEE | 30 |
| HIGH | 60 days | RISK_COMMITTEE | 60 |
| MEDIUM | 90 days | MANAGEMENT_AUDIT_COMMITTEE | 90 |
| LOW | 180 days | DEPARTMENT_HEAD | 365 |

**5 AGING_BUCKETS + day ranges byte-for-byte:**

| Bucket | Days |
|---|---|
| CURRENT | 0-30 |
| EARLY_AGED | 31-60 |
| AGED | 61-90 |
| PROLONGED | 91-180 |
| OVERDUE | 181+ |

**6 ISSUE_STATUSES:** OPEN, IN_PROGRESS, REMEDIATED, CLOSED, OVERDUE, ESCALATED.

**CLUSTER_ESCALATION_THRESHOLD = 5** (5+ overdue issues in same business unit triggers Board escalation).

**Severity classification by impact:** CRITICAL≥100M, HIGH≥10M, MEDIUM≥1M, LOW<1M.

**Auto-escalation rules:**
- Regulatory finding → at minimum CRITICAL
- Fraud-related → at minimum CRITICAL

**Closed issue aging:** uses `closed_date` not ref_date for accurate days-to-closure measurement.

**Honesty rules:**
- **Rule 1:** closure_rate_pct=None when total=0
- **Rule 6:** missing impact → severity=None; missing raised_date → aging=None

**Self-test:** 26/26 PASS

---

### #84 Audit Reporting & Audit Committee Dashboard (Cat B)
**Module:** `utils/audit_reporting.py` (~410 LOC)
**Engine:** `AuditReportingEngine`

4 entries: `validate_audit_opinion`, `audit_universe_coverage`, `outstanding_recommendations_summary`, `generate_audit_committee_dashboard`.

**4 AUDIT_OPINIONS byte-for-byte (ISA 700):**

| Opinion | Meaning |
|---|---|
| UNQUALIFIED | Clean opinion; financials fairly presented |
| QUALIFIED | Exception(s) but otherwise clean |
| ADVERSE | Financials NOT fairly presented (severe) |
| DISCLAIMER | Unable to obtain sufficient evidence |

**8 REQUIRED_REPORT_SECTIONS byte-for-byte (ISA 700):**
EXECUTIVE_SUMMARY, SCOPE_AND_OBJECTIVES, METHODOLOGY, DETAILED_FINDINGS, MANAGEMENT_RESPONSE, RECOMMENDATIONS, OPINION, APPENDICES.

**4 COVERAGE_RATINGS byte-for-byte:**

| Rating | Threshold |
|---|---|
| EXCELLENT | ≥ 90% |
| GOOD | 75-89% |
| ADEQUATE | 60-74% |
| INADEQUATE | < 60% |

**4 RECOMMENDATION_AGING_BUCKETS byte-for-byte (in months):**

| Bucket | Months |
|---|---|
| RECENT | 0-6 |
| AGED | 7-12 |
| PROLONGED | 13-24 |
| STALE | 25+ |

**Quarterly AC dashboard payload:** combines valid reports, opinion counts, coverage rating, recommendation aging summary, and explicit `invalid_reports[]` for fail-closed surfacing.

**Honesty rules:**
- **Rule 1:** coverage_pct=None when total_universe≤0
- **Rule 6:** invalid reports surfaced separately in `invalid_reports[]` not silently dropped

**Self-test:** 18/18 PASS

---

## Audit gates added (3)

### G77 `audit_universe_correct`
Inline programmatic — risk thresholds 70/40 + audit frequencies 12/24/36 + 6 inherent weights byte-for-byte (sum=100); 5 control rating bands byte-for-byte. **Runtime:** inherent score weighted-sum 68.50 verified; residual with 70% control → LOW tier; HIGH risk → 3 annual audits in 3-year plan; Rule 1 + Rule 6 paths.

**Tampering verified:** HIGH_RISK_THRESHOLD (70→30) caught.

### G78 `internal_controls_correct`
Inline programmatic — 5 COSO components + 17 principles + per-component principle counts byte-for-byte. 4 sample sizes + tolerance + 1%/5% severity thresholds + 3 deficiency severities byte-for-byte. **Runtime:** KEY 1 exception → INEFFECTIVE (zero tolerance); MEDIUM 2/40=5% → PARTIALLY_EFFECTIVE; deficiency 6% → MATERIAL_WEAKNESS. Rule 1 + Rule 6 paths.

**Tampering verified:** TOLERABLE_EXCEPTION_RATE_PCT["KEY"] (0→50) caught.

### G79 `audit_issue_reporting_correct`
Combined inline programmatic for #83 + #84.
- **Issues (#83):** 4 severities + SLA targets + 4 aging buckets + escalation thresholds + cluster=5 byte-for-byte; runtime regulatory→CRITICAL escalation + 30-day→Board escalation; 6 cluster overdue → flagged
- **Reports (#84):** 4 ISA 700 opinions + 8 required sections byte-for-byte; 3 coverage thresholds (90/75/60) + 4 rec aging buckets byte-for-byte; runtime 95/100=EXCELLENT, 30/100=INADEQUATE; unknown opinion + missing sections rejected

**Tampering verified:**
- SLA_TARGET_DAYS["CRITICAL"] (30→365) caught
- COVERAGE_THRESHOLDS_PCT["EXCELLENT"] (90→50) caught

---

## Spec deviations (cumulative — UNCHANGED at 9)

No new spec deviations introduced in v5.62. All 4 standards delivered as Cat B with full deterministic implementation.

---

## Rule application status (UNCHANGED)

- **Rule 4 applications:** 6 (no change in v5.62)
- **Rule 7 applications:** 6 (no change in v5.62 — all 4 standards Cat B audit/controls metrics, no ML branches)

---

## Why this batch matters — Three Lines of Defence COMPLETE

With v5.62, the **Three Lines of Defence model is now complete**:

| Line | Volume | Standards | Function |
|---|---|---|---|
| 1st line | Vol 8, 12 | Operations | Day-to-day risk ownership |
| 2nd line | Vol 9 | Risk Management (#43-#48) | Risk oversight |
| 2nd line | Vol 10 | Compliance (#49-#52) | Regulatory adherence |
| 2nd line | Vol 14 | Treasury/ALM (#73-#76) | LCR/NSFR/IRRBB/FX |
| 2nd line | Vol 15 | Capital/Returns (#77-#80) | CAR/RWA/Stress/BSD |
| **3rd line** | **Vol 16** | **Audit/Controls (#81-#84)** | **Independent assurance** |

The Internal Audit / Internal Controls batch represents the bank's **third line of defence**: independent assurance over the effectiveness of risk management and control activities.

Byte-for-byte fidelity to **IIA Standards + COSO 2013 + ISA 530 + PCAOB AS 2201 + ISA 700** is critical because:
1. **IIA Standards** govern the function's professional practice and chartering
2. **COSO** is the SEC/PCAOB-recognised framework for internal control over financial reporting
3. **ISA 530 sample sizes** are accepted by external auditors as evidence of sufficient testing
4. **PCAOB AS 2201 deficiency thresholds (1%/5% of assets)** are the SEC standard for material weakness disclosure
5. **ISA 700 opinion language** is the global audit reporting standard

The combination of:
- Decimal precision (28 digits)
- Risk-based audit planning with strict-inequality year boundaries
- COSO 5-component × 17-principle structure
- ISA 530 sample sizes for control testing
- KEY-control zero-tolerance
- PCAOB severity escalation logic (small impact + financial reporting + no compensating → upgrade)
- 4-tier severity classification with regulatory/fraud auto-escalation to CRITICAL
- Business-unit cluster-escalation pattern (5+ overdue → Board)
- ISA 700 8-section completeness validation
- Fail-closed validation surfacing in `invalid_reports[]`
- Explicit Rule 1 + Rule 6 honesty paths

means: when the audit committee receives a quarterly dashboard showing coverage=87% (GOOD), 12 reports issued with 10 UNQUALIFIED + 2 QUALIFIED, 45 open recommendations with 5 STALE (>24mo), 3 cluster escalations to Board, MTTR=72 days for closed issues — those numbers are **independently verifiable, drift-detected, and tamper-evident**. The bank's audit committee can rely on these computations as the primary mechanism by which they discharge their own oversight duty under CMA + CBK + Companies Act.

Volume Sixteen completes the **supervisory governance backbone**. With Volumes 9 (Risk) + 10 (Compliance) + 14 (Treasury/ALM) + 15 (Capital/Returns) + 16 (Audit/Controls) shipped, the platform now spans the **full enterprise risk + governance stack** — first line (operations, treasury), second line (risk, compliance, ALM), third line (audit, controls) — that defines the bank's CBK + CMA + IIA + Basel + ISA + COSO regulatory posture.

---

## What's new in v5.62 vs v5.61

| | v5.61 | v5.62 |
|--|-------|-------|
| Standards delivered | 80 | **84** |
| Audit gates | 76/76 | **79/79 = 100%** |
| Test files | 40 | **41** |
| Total tests | 1248 | **1333** |
| Three Lines of Defence | 1st+2nd | **1st+2nd+3rd COMPLETE** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 4 applications | 6 | 6 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |

---

## Next: Volume Seventeen #85-#88

Anticipated standards (subject to A2Z_Continuation_Spec_v6.md):
- #85-#88 — likely Reporting Automation, Management/Board Reporting Pack Generators, or Reporting Calendar & SLA Monitoring

Target: 4 engines + tests + 3 gates G80-G82 → 82/82.
