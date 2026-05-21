# A2Z MIS 360 — CHANGELOG v5.63

**Volume Seventeen — Reporting Automation**
**Released:** April 2026
**Audit gates:** 82/82 = 100% PASS (was 79/79)
**Test count:** 42 files / 1407 tests (was 41/1333 — added 74 in `tests/test_volume_seventeen_batch.py`)

---

## Standards delivered (4 — all Cat B reporting workflow)

### #85 Management Reporting Pack Generator (Cat B)
**Module:** `utils/management_reporting.py` (~310 LOC)
**Engine:** `ManagementReportingEngine`

3 entries: `generate_monthly_mis_pack`, `generate_weekly_executive_flash`, `distribution_list`.

**10 MONTHLY_MIS_SECTIONS byte-for-byte:**
EXECUTIVE_SUMMARY, FINANCIAL_HIGHLIGHTS, BALANCE_SHEET, INCOME_STATEMENT, KPI_DASHBOARD, BRANCH_PERFORMANCE, RISK_INDICATORS, COMPLIANCE_STATUS, HR_METRICS, IT_OPERATIONS

**4 WEEKLY_FLASH_SECTIONS byte-for-byte:**
EXECUTIVE_SUMMARY, KEY_KPIS, RISK_ALERTS, ACTION_ITEMS

**3 PACK_FREQUENCIES byte-for-byte:** MONTHLY, WEEKLY, AD_HOC

**3 DISTRIBUTION_TIERS byte-for-byte:** EXCO, MANCO, DEPARTMENT_HEADS

**Tier-based completeness thresholds byte-for-byte:**

| Tier | Min completeness |
|---|---|
| EXCO | 100% (zero tolerance) |
| MANCO | 90% |
| DEPARTMENT_HEADS | 80% |

**Lead times byte-for-byte:**
- MONTHLY_PACK_LEAD_DAYS = 5
- WEEKLY_FLASH_LEAD_DAYS = 1

**Rule 1**: completeness_pct=None when no required sections defined (denominator zero).
**Rule 6**: missing/unpopulated sections surfaced; pack NOT eligible if completeness < tier minimum (fail closed). Self-test: 17/17.

---

### #86 Board Reporting Pack Generator (Cat B)
**Module:** `utils/board_reporting.py` (~340 LOC)
**Engine:** `BoardReportingEngine`

3 entries: `generate_board_pack`, `generate_committee_pack`, `validate_lead_time`.

**12 BOARD_PACK_SECTIONS byte-for-byte (CMA Code + Banking Act):**
COVER_LETTER, STRATEGIC_UPDATE, FINANCIAL_PERFORMANCE, RISK_REPORT, COMPLIANCE_REPORT, AUDIT_REPORT, HR_REPORT, IT_CYBER_REPORT, CUSTOMER_EXPERIENCE, SUSTAINABILITY_ESG, BOARD_RESOLUTIONS, APPENDICES

**5 BOARD_COMMITTEES byte-for-byte:**
BOARD_AUDIT_COMMITTEE, BOARD_RISK_COMMITTEE, BOARD_CREDIT_COMMITTEE, BOARD_NOMINATIONS_COMMITTEE, BOARD_STRATEGY_COMMITTEE

**CMA Code lead times byte-for-byte:**
- BOARD_PACK_LEAD_DAYS = 14 (CMA Code of Corporate Governance)
- BOARD_COMMITTEE_LEAD_DAYS = 7

**BOARD_MIN_COMPLETE_PCT = 100%** (zero tolerance for board distribution)

**3 BOARD_FREQUENCIES byte-for-byte:** QUARTERLY, MONTHLY, EXTRAORDINARY

**Committee primary section mapping (selected):**
| Committee | Primary sections |
|---|---|
| BAC | AUDIT_REPORT, FINANCIAL_PERFORMANCE, COMPLIANCE_REPORT, RISK_REPORT |
| BRC | RISK_REPORT, COMPLIANCE_REPORT, IT_CYBER_REPORT |
| BCC | RISK_REPORT, FINANCIAL_PERFORMANCE |
| BNC | HR_REPORT, STRATEGIC_UPDATE |
| BSC | STRATEGIC_UPDATE, FINANCIAL_PERFORMANCE, CUSTOMER_EXPERIENCE, SUSTAINABILITY_ESG |

**Triple validation for distribution:** lead_time_compliant AND completeness_compliant AND all_approved must all be true.

**Rule 1**: lead_days=None when meeting_date missing.
**Rule 6**: missing dates / sections / approvals block distribution. Self-test: 17/17.

---

### #87 Regulatory Submission Workflow Engine (Cat B)
**Module:** `utils/submission_workflow.py` (~360 LOC)
**Engine:** `SubmissionWorkflowEngine`

4 entries: `validate_state_transition`, `days_until_deadline`, `log_workflow_event`, `submission_status_summary`.

**6 SUBMISSION_STATES byte-for-byte:**
DRAFT, REVIEW, APPROVED, SUBMITTED, ACKNOWLEDGED, REJECTED

**State machine transitions byte-for-byte (`ALLOWED_TRANSITIONS` dict):**
| From | To (allowed) |
|---|---|
| DRAFT | (REVIEW,) |
| REVIEW | (APPROVED, DRAFT) |
| APPROVED | (SUBMITTED, REVIEW) |
| SUBMITTED | (ACKNOWLEDGED, REJECTED) |
| REJECTED | (DRAFT,) |
| ACKNOWLEDGED | () — terminal |

**10 SUBMISSION_TYPES + filing deadlines byte-for-byte (calendar days from period-end):**
| Type | Deadline | Frequency |
|---|---|---|
| BSD_1 | T+1 | Daily liquidity |
| BSD_2 | T+5 | Weekly balance sheet |
| BSD_3 | T+15 | Monthly capital adequacy |
| BSD_17 | T+15 | Monthly credit quality |
| BSD_19 | T+30 | Quarterly financials |
| LCR | T+15 | Monthly LCR |
| NSFR | T+30 | Monthly NSFR |
| LARGE_EXPOSURES | T+15 | Monthly |
| PILLAR_3 | T+90 | Semi-annual |
| ANNUAL_RETURN | T+90 | Annual audited |

**3 WORKFLOW_EVENT_TYPES byte-for-byte:** STATE_CHANGE, REVIEWER_ASSIGNED, COMMENT_ADDED

**5 DEADLINE_STATUS_BANDS_DAYS byte-for-byte:**
- OVERDUE: (-99999, -1)
- DUE_TODAY: (0, 0)
- URGENT: (1, 2)
- UPCOMING: (3, 7)
- ON_TRACK: (8, 99999)

**State machine enforcement (fail closed):** invalid transitions REJECTED — submission state UNCHANGED, audit trail event NOT appended.

**Rule 1**: days_until_deadline=None when period_end missing.
**Rule 6**: invalid state transition blocks logging (fail closed). Self-test: 21/21.

---

### #88 Pillar 3 Disclosure Generator (Cat B)
**Module:** `utils/pillar3_disclosure.py` (~370 LOC)
**Engine:** `Pillar3Engine`

5 entries: `is_large_bank`, `generate_km1_key_metrics`, `generate_ov1_overview_rwa`, `generate_lr1_leverage`, `generate_pillar3_pack`.

**12 PILLAR_3_TABLES byte-for-byte (BCBS 309/356):**
KM1, OV1, CR1, CR3, CR4, CR5, LIQ1, LIQ2, LR1, MR1, OR1, REM1

**3 DISCLOSURE_FREQUENCIES byte-for-byte:** ANNUAL, SEMI_ANNUAL, QUARTERLY

**TABLE_FREQUENCIES_LARGE_BANK byte-for-byte:**
- KM1, OV1, LIQ1, LIQ2 → QUARTERLY
- REM1 → ANNUAL
- CR1, CR3, CR4, CR5, LR1, MR1, OR1 → SEMI_ANNUAL

**TABLE_FREQUENCIES_OTHER_BANK byte-for-byte:**
- KM1, OV1, LIQ1, LIQ2 → SEMI_ANNUAL (downgrade)
- All other tables retain their large-bank cadence

**Large bank threshold byte-for-byte:** `LARGE_BANK_ASSET_THRESHOLD_KES = Decimal("100000000000")` (KES 100B per Basel + CBK definition)

**10 KM1_MANDATORY_METRICS byte-for-byte:**
cet1_capital_kes, tier1_capital_kes, total_capital_kes, rwa_kes, cet1_ratio_pct, tier1_ratio_pct, total_car_pct, leverage_ratio_pct, lcr_pct, nsfr_pct

**Runtime sample (verified by G82):**
| Metric | Computation | Result |
|---|---|---|
| CET1 ratio | 12B / 90B × 100 | 13.33% |
| Total CAR | 15B / 90B × 100 | 16.67% |
| Leverage | 13B / 250B × 100 | 5.20% |
| LCR | 20B / 15B × 100 | 133.33% |
| NSFR | 100B / 90B × 100 | 111.11% |

**Bank classification:**
- total_assets ≥ 100B → LARGE_BANK
- total_assets < 100B → OTHER_BANK
- total_assets is None → UNKNOWN (Rule 1)

**Rule 1**: ratios=None when any zero denominator (zero RWA → CET1=Tier1=Total CAR=None; zero leverage exposures → leverage=None; zero net outflows → LCR=None; zero RSF → NSFR=None).
**Rule 6**: missing mandatory metrics surfaced in `missing_mandatory_metrics[]`; missing tables surfaced in `missing_tables[]`; pack `eligible_for_distribution=False` if not all 12 tables present. Self-test: 19/19.

---

## Audit gates added (3)

### G80 — `gate_management_reporting_correct`
Inline programmatic gate verifying:
- 10 MONTHLY_MIS_SECTIONS byte-for-byte
- 4 WEEKLY_FLASH_SECTIONS byte-for-byte
- 3 PACK_FREQUENCIES + 3 DISTRIBUTION_TIERS catalog
- Completeness thresholds (100/90/80%) byte-for-byte
- Lead times (5/1 days) byte-for-byte
- Runtime: full sections → 100% eligible for EXCO; 90% blocked from EXCO but eligible for MANCO (tier-based threshold enforcement); 75% weekly flash blocked
- Rule 6: missing period blocks generation; unknown tier rejected

**Tampering test:** EXCO_MIN_COMPLETE_PCT (100→50) caught.

---

### G81 — `gate_board_reporting_correct`
Inline programmatic gate verifying:
- 12 BOARD_PACK_SECTIONS byte-for-byte
- 5 BOARD_COMMITTEES byte-for-byte
- BOARD_PACK_LEAD_DAYS=14 (CMA Code) byte-for-byte
- BOARD_COMMITTEE_LEAD_DAYS=7 byte-for-byte
- BOARD_MIN_COMPLETE_PCT=100 byte-for-byte
- 3 BOARD_FREQUENCIES catalog
- Committee primary section mapping (BAC, BRC verified)
- Runtime: full pack with 15d lead → eligible; 7d lead violates 14d CMA rule; missing 1 of 12 sections blocks distribution; unapproved section blocks
- Rule 6: missing meeting_date blocks generation; unknown frequency rejected
- Rule 1: validate_lead_time with missing dates → lead_days=None
- Committee pack: BAC with 8d lead eligible (≥7d required)

**Tampering test:** BOARD_PACK_LEAD_DAYS (14→1) caught.

---

### G82 — `gate_submission_pillar3_correct`
Combined inline programmatic gate for #87 + #88.

**SUBMISSION (#87):**
- 6 SUBMISSION_STATES byte-for-byte
- State machine transitions byte-for-byte (DRAFT only → REVIEW; ACKNOWLEDGED terminal)
- 10 SUBMISSION_TYPES byte-for-byte
- 10 FILING_DEADLINE_DAYS byte-for-byte (T+1 / T+5 / T+15 / T+30 / T+90)
- 3 WORKFLOW_EVENT_TYPES + 5 DEADLINE_STATUS_BANDS byte-for-byte
- Runtime: DRAFT→REVIEW allowed, DRAFT→SUBMITTED rejected; ACKNOWLEDGED has no exit
- BSD-3 14d remaining = ON_TRACK; 3d past = OVERDUE
- Rule 1: missing period_end → days=None
- Invalid state change NOT logged (fail closed) — state stays DRAFT

**PILLAR 3 (#88 BCBS 309/356):**
- 12 PILLAR_3_TABLES byte-for-byte
- 3 DISCLOSURE_FREQUENCIES + freq maps (large/other) byte-for-byte
- LARGE_BANK_ASSET_THRESHOLD_KES = 100B byte-for-byte
- 10 KM1_MANDATORY_METRICS byte-for-byte
- Runtime: KM1 16.67% CAR, 133.33% LCR; 12-table pack complete; 2-of-12 surfaces 10 missing
- Rule 1: zero RWA → ratios=None
- Bank class: 150B → LARGE_BANK, 50B → OTHER_BANK, None → UNKNOWN

**Tampering tests:** FILING_DEADLINE_DAYS["BSD_1"] (1→100) caught; LARGE_BANK_ASSET_THRESHOLD_KES (100B→1) caught.

---

## Spec deviations through v5.63

**Cumulative count UNCHANGED at 9** — no new spec deviations introduced (all 4 standards Cat B with full deterministic implementation).

## Rule 7 application count

**UNCHANGED at 6** — no ML branches in v5.63 (all 4 standards Cat B reporting workflow).

---

## Comparison v5.62 → v5.63

| Metric | v5.62 | v5.63 |
|---|---|---|
| Standards delivered | 84 | **88** |
| Audit gates | 79/79 = 100% | **82/82 = 100%** |
| Test files | 41 | **42** |
| Total tests | 1333 | **1407** |
| Spec deviations | 9 | 9 (unchanged) |
| Rule 7 applications | 6 | 6 (unchanged) |
| New utility modules | 4 | **4** (~1,380 LOC) |

---

## Why Volume Seventeen matters

The Reporting Automation batch represents the **delivery channel** of the bank's governance and supervisory work product. Where Volumes 9-16 build the *substance* (Risk, Compliance, Treasury, Capital, Audit), Volume 17 builds the *form* through which that substance reaches its audiences:

- **#85 Management MIS** — substance reaches ExCo, ManCo, Department Heads on monthly + weekly cycles with tier-based completeness gating
- **#86 Board Pack** — substance reaches Board + 5 sub-committees per CMA Code 14-day rule with 100% completeness requirement
- **#87 Submission Workflow** — substance reaches CBK BSD on T+1 / T+5 / T+15 / T+30 / T+90 schedules with state-machine-enforced 4-eyes approval and immutable audit trail
- **#88 Pillar 3 Disclosure** — substance reaches the public market on quarterly/semi-annual cadence per BCBS 309/356 with 12-table completeness validation

Byte-for-byte fidelity to CMA Code + CBK BSD + BCBS 309/356 means: when the bank distributes the Q1 board pack 14 days before the meeting at 100% completeness, submits BSD-3 on T+15 with state=SUBMITTED→ACKNOWLEDGED, and publishes a full Pillar 3 pack with KM1 showing CET1=13.5% / Total CAR=16.7% / LCR=125% / NSFR=110% — those distributions are independently verifiable, drift-detected, audit-trail-enforced, and tamper-evident.

**The reporting superstructure is now complete on top of the three lines of defence.**
