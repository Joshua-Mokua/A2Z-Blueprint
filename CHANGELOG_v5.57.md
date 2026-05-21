# A2Z MIS 360 — CHANGELOG v5.57

**Volume Eleven — HR Intelligence**
**Released:** April 2026
**Audit gates:** 64/64 = 100% PASS (was 61/61)
**Test count:** 36 files / 996 tests (was 35/947 — added 49 in `tests/test_volume_eleven_batch.py`)

---

## Standards delivered (4)

### #61 Workforce Analytics (Cat B)
**Module:** `utils/workforce_analytics.py` (~360 LOC)
**Engine:** `WorkforceAnalyticsEngine`

5 entries: `headcount_by_dimension`, `attrition_rate`, `span_of_control`, `tenure_distribution`, `demographic_mix`.

**Spec literals byte-for-byte:**
- `EMPLOYMENT_STATUSES = (ACTIVE, ON_LEAVE, TERMINATED, RESIGNED, RETIRED)`
- `TENURE_BUCKETS` labels: UNDER_1Y, 1_3Y, 3_5Y, 5_10Y, OVER_10Y
- `AGE_BANDS` labels: UNDER_25, 25_34, 35_44, 45_54, 55_PLUS
- Span of control: `HEALTHY_MIN=4, HEALTHY_MAX=12, OVERLOADED=15`
- Attrition severity: `LOW=5%, HEALTHY_MAX=12%, HIGH=20%`

**Honesty rules:**
- **Rule 1:** `attrition_rate=None` when opening_headcount=0; `female_pct=None` when no known gender
- **Rule 6:** missing branch/role/grade → "UNKNOWN" bucket exposed in `meta.unknown_dimension_assignments`; missing date_of_birth → counted in age "UNKNOWN"; staff with no manager surfaced as `individual_contributors`

**Self-test:** 11/11 PASS

---

### #62 Compensation & Pay Equity (Cat B)
**Module:** `utils/compensation_equity.py` (~310 LOC)
**Engine:** `CompensationEquityEngine`

4 entries: `pay_distribution_by_grade` (deterministic median + IQR), `gender_pay_gap` (raw + grade-adjusted weighted), `internal_equity_ratios` (compa-ratio), `ceo_to_median_ratio`.

**Spec literals byte-for-byte:**
- `PAY_GAP_FAIR_MAX_PCT = 5.0`, `MODERATE_MAX_PCT = 10.0`
- `COMPA_RATIO_HEALTHY_MIN = 0.80`, `MAX = 1.20`
- `CEO_RATIO_HEALTHY_MAX = 50` (50:1), `HIGH_THRESHOLD = 100`

**Honesty rules:**
- **Rule 1:** `raw_gap=None` when male_median ≤ 0 OR no female records; CEO ratio = None when median ≤ 0; pay distribution percentiles = None when no records
- **Rule 6:** `unknown_gender_count` surfaced separately (NEVER imputed as M or F); zero-salary records excluded from distribution but counted in `headcount_excluded_no_salary`

Linear-interpolation percentile is deterministic.

**Self-test:** 10/10 PASS

---

### #63 Performance & Talent Pipeline (Cat B + Cat C)
**Module:** `utils/performance_talent.py` (~330 LOC)
**Engine:** `PerformanceTalentEngine`

5 entries: `rating_distribution` (calibration check), `calibration_compliance_by_manager` (rating inflation detection), `succession_bench_strength`, `transition_review_status` (Cat C workflow), `high_potential_pipeline`.

**Spec literals byte-for-byte:**
- `RATING_LEVELS = (EXCEEDS, MEETS_PLUS, MEETS, DEVELOPING, UNSATISFACTORY)`
- `CALIBRATION_TARGETS` dict (all 5 levels): EXCEEDS=(10,15)%, MEETS_PLUS=(20,25)%, MEETS=(50,55)%, DEVELOPING=(5,10)%, UNSATISFACTORY=(0,5)%
- `READINESS_LEVELS = (READY_NOW, READY_1_YEAR, READY_2_YEAR, NOT_READY)`
- `BENCH_HEALTHY_PCT = 75`, `AT_RISK_PCT = 50`

**Cat C workflow:**
```
DRAFT → MANAGER_SUBMITTED → CALIBRATED → FINALIZED | DISPUTED → CALIBRATED
```

**Honesty rules:**
- **Rule 4 (default-strict, no-skip):** DRAFT cannot transition directly to FINALIZED — must pass through MANAGER_SUBMITTED + CALIBRATED. FINALIZED is terminal (empty allowed-transitions tuple). MANAGER_SUBMITTED can return to DRAFT for revisions. Mandatory `actor_id` on every transition.
- **Rule 1:** distribution percentages = None when zero ratings exist; bench_strength = None when no critical roles defined
- **Rule 6:** staff with insufficient review history surfaced in `insufficient_history_count` for HiPo computation (NEVER auto-promoted on partial data)

**Self-test:** 12/12 PASS

---

### #64 Employee Engagement Intelligence (Cat B + Cat D) — **FOURTH RULE 7 APPLICATION**
**Module:** `utils/employee_engagement.py` (~430 LOC)
**Engine:** `EmployeeEngagementEngine`

5 entries: `engagement_score`, `enps`, `drivers_breakdown`, `sentiment_score` (Cat D scaffolding), `flight_risk_indicators` (deterministic, NOT ML).

**Spec literals byte-for-byte:**
- `ENGAGEMENT_DRIVERS = (LEADERSHIP, COMPENSATION, GROWTH_DEVELOPMENT, WORK_LIFE_BALANCE, RECOGNITION, PURPOSE_MEANING)` (6 drivers)
- `ENPS_PROMOTER_MIN_SCORE = 9`, `DETRACTOR_MAX_SCORE = 6` (industry standard)
- `FLIGHT_RISK_FACTOR_WEIGHTS` dict: engagement_below_40=30, no_promotion_3y=20, compensation_below_p25=25, low_manager_rating_consecutive=15, tenure_2_5y=10

**SPEC_DEVIATION_NOTE byte-for-byte:**
> "ML-based sentiment classification is downstream work; v6 ships rule-based keyword sentiment scoring"

**The Cat D scaffolding pattern (4th application):**

`sentiment_score(text, ml_sentiment_fn=None)` returns:
- **No ML provided:** `basis="rule_based"` + `ml_sentiment=None` + `reason="no_ml_sentiment_model_loaded"` + DETERMINISTIC keyword-based fallback (POSITIVE_KEYWORDS frozenset of 15 + NEGATIVE_KEYWORDS frozenset of 15) + `spec_deviation` byte-for-byte
- **ML succeeds:** `basis="ml"` + `ml_sentiment` + `rule_based_sentiment` ALSO surfaced for transparency (never silently substituted)
- **ML fails:** `basis="rule_based"` + `reason=f"ml_sentiment_error:{type(e).__name__}"`

**Honesty rules:**
- **Rule 1:** engagement_score=None when no respondents; eNPS=None when no eNPS responses; driver scores=None per driver when no data
- **Rule 6:** abstained respondents counted in `abstained` field separately; missing flight_risk signals listed in `missing_signals[]` (NEVER imputed); driver respondents tracked separately when partial
- **Rule 7:** sentiment_score uses Cat D scaffolding — never silently substitutes rule-based for ML

**Self-test:** 16/16 PASS

---

## Audit gates added (3)

### G62 `workforce_analytics_correct`
Inline programmatic — verifies 5 EMPLOYMENT_STATUSES + 5 TENURE_BUCKETS labels byte-for-byte; SPAN_OF_CONTROL thresholds 4/12/15; ATTRITION thresholds 5%/12%/20%; Rule 1 None-on-zero-opening; Rule 6 UNKNOWN bucket.

**Tampering verified:** SPAN_OF_CONTROL_OVERLOADED (15→25) caught with 1 violation.

### G63 `compensation_equity_correct`
Inline programmatic — pay-gap thresholds 5%/10% + compa-ratio band 0.80-1.20 + CEO ratio 50/100 byte-for-byte; Rule 1 verification (no males → gap=None); Rule 6 (unknown gender counted); compa-ratio band classification correctness.

**Tampering verified:** COMPA_RATIO_HEALTHY_MIN (0.80→0.50) caught with 2 violations including downstream band classification breakage.

### G64 `performance_engagement_correct` — **FOURTH RULE 7 VERIFICATION**
Combined inline programmatic for #63 + #64.
- PERF: RATING_LEVELS byte-for-byte; **CALIBRATION_TARGETS dict byte-for-byte for all 5 levels**; BENCH thresholds; Rule 4 review workflow no-skip + FINALIZED terminal
- ENG: 6 ENGAGEMENT_DRIVERS byte-for-byte; 5 FLIGHT_RISK_FACTOR_WEIGHTS byte-for-byte; SPEC_DEVIATION_NOTE byte-for-byte
- **Rule 7 verification (4th application):** no-model basis check, ML-fail error surfacing, rule-based determinism

**Tampering verified:** SPEC_DEVIATION_NOTE drift caught with Rule 7 violation.

---

## Spec deviations (cumulative — now 7)

| # | Volume | Description |
|---|--------|-------------|
| 1 | v5.49 | Heatmap React→Streamlit/plotly |
| 2 | v5.51 | React SPA + React Native scaffolding |
| 3 | v5.52 | Rule 7 / Cat D scaffolding pattern formalized |
| 4 | v5.52 | #48 LLM commentary deferred (rule-based template engine ships) |
| 5 | v5.55 | CBK reports: 3 of 8 fully implemented; 5 deferred |
| 6 | v5.56 | FATCA Form 8966 XML and OECD CRS XML generation deferred to v7 |
| **7** | **v5.57** | **ML-based sentiment classification deferred to v7; v6 ships rule-based keyword sentiment scoring** |

---

## Honesty rules — pattern stability

This volume marks the **FOURTH application of Rule 7** (no silent ML predictions) — same pattern as #41, #48, #53, now #64. Pattern is now stable across four prediction domains:

| App | Standard | Domain |
|-----|----------|--------|
| 1 | #48 | BI commentary generation (text generation) |
| 2 | #41 | Customer dormancy prediction (binary classification) |
| 3 | #53 | Credit default probability (regression) |
| 4 | **#64** | **Employee sentiment scoring (NLP/text classification)** |

**Significance of #64:** First Rule 7 application to text/NLP. Previous applications were numerical/categorical. The discipline transferred cleanly to text-based prediction:
- Same scaffolding (ml_*_fn injectable, rule-based fallback always surfaced)
- Same explicit-failure handling (ml_*_error reason with type name)
- Same byte-for-byte spec_deviation discipline

This validates that the Cat D pattern works for any predictive engine regardless of input modality.

---

## What's new in v5.57 vs v5.56

| | v5.56 | v5.57 |
|--|-------|-------|
| Standards delivered | 60 | 64 |
| Audit gates | 61 | 64 |
| Test files | 35 | 36 |
| Total tests | 947 | 996 |
| Spec deviations | 6 | 7 |
| Rule 4 applications | 4 | 5 (added #63 review workflow) |
| Rule 7 applications | 3 | **4** |

---

## Next: Volume Twelve — Operations Excellence (#65-#68)

Anticipated standards (subject to A2Z_Continuation_Spec_v6.md):
- #65 Operations Dashboard (Cat B — branch + back-office KPIs)
- #66 Branch Operations Excellence (Cat B/C — turnaround time, error rate, customer wait time)
- #67 Channel SLA Monitoring (Cat B — uptime, response time per channel)
- #68 Queue Analytics & Customer Experience (Cat B — wait-time distribution, abandonment rate)

Target: 4 engines + fixtures + 3 gates G65-G67 → 67/67.
