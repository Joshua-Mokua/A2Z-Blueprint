# CHANGELOG v10.25 — Audit/GRC Arc Batch 3: Analytics + Vendor + Always-On + Cyber

**Audit:** 122/122 PASS — **108th consecutive clean.**

## What ships in v10.25

`utils/audit_analytics_vendor.py` — 1214 lines, **Cat A**. 4 of 17 Audit/GRC standards active:

| Standard | Implemented as |
|---|---|
| **ENH-205** AI-Powered Audit Analytics | `AnomalyDetectionMethod` enum (Z_SCORE/IQR/BENFORD_LAW/ISOLATION_FOREST/AUTOENCODER/CUSTOM_ML); 4-tier `AnomalySeverity` mapped to Z-score thresholds (2σ→LOW, 3σ→MEDIUM, 4σ→HIGH, 5σ+→CRITICAL); `detect_z_score_anomalies()` Bessel-corrected sample std; `detect_iqr_anomalies()` Tukey 1.5×IQR + 3×IQR extreme fence; `BENFORD_EXPECTED_DIGIT_PCT` distribution + `benford_conformance_test()` chi-square at ~95%/~90% confidence (NORMAL/WARNING/FAIL); `detect_with_ml_hook()` Rule 7 callable for ISOLATION_FOREST + AUTOENCODER + CUSTOM_ML methods |
| **ENH-AUD-R2** Vendor Risk Monitoring | 4-tier `VendorTier` (CRITICAL/HIGH/MEDIUM/LOW); 12-category `VendorCategory`; 8-dimension `VendorRiskDimension` (FINANCIAL/CYBER/OPERATIONAL/REPUTATIONAL/REGULATORY/BUSINESS_CONTINUITY/CONCENTRATION/DATA_PRIVACY); 7-state `VendorOnboardingStatus`; per-tier `DEFAULT_VENDOR_REASSESSMENT_DAYS` (180/365/730/1095 days per CBK Outsourcing); `VendorRiskScore` with `is_overdue()` + `highest_risk_dimensions()`; `compute_concentration_risk()` per-category breakdown; `excessive_concentration_categories()` 25% threshold per CBK Outsourcing Guidelines |
| **ENH-AUD-R5** 24/7 Always-On Assurance | 4-priority `AssurancePriority` (P1_CRITICAL→P4_LOW); per-priority `ASSURANCE_RESPONSE_SLA_MINUTES` (15min/4h/24h/1wk); 7-channel `AlertChannel` (PAGERDUTY/SMS/SLACK/EMAIL/SIEM_LOG/BOARD_DASHBOARD/AUDIT_COMMITTEE_DIGEST); `AssuranceAlert` with `is_overdue_for_response()`; `select_channels_for_priority()` defaults |
| **ENH-AUD-R6** Cybersecurity Framework Integration | NIST CSF v2.0 — 6 functions (GOVERN/IDENTIFY/PROTECT/DETECT/RESPOND/RECOVER) × 22 categories with `assess_nist_csf_coverage()`; ISO 27001:2022 — 4 control groups (ORGANIZATIONAL=37/PEOPLE=8/PHYSICAL=14/TECHNOLOGICAL=34) totaling 93 controls; CIS Controls v8 (18 controls × 153 sub-controls); `CyberFrameworkCoverage` with `meets_target()` + `gap_to_target()` |

## Regulatory provenance

- **IIA IPPF Standard 2120** — risk management
- **IIA IPPF Standard 2130** — control monitoring
- **NIST Cybersecurity Framework v2.0** (GV/ID/PR/DE/RS/RC functions)
- **ISO 27001:2022** (4 control groups, 93 controls)
- **CIS Controls v8** (18 controls + 153 sub-controls)
- **CBK Prudential Guideline CBK/PG/02** — operational risk + outsourcing
- **CBK Outsourcing Guidelines (CBK/PG/15)**
- **CBK Cybersecurity Guidance Note (2017, updated 2023)**
- **Basel BCBS 239 §11/§12** — completeness, timeliness, integrity
- **Basel Outsourcing Principles (2005, updated 2018)**
- **EU DORA** — operational resilience for ICT third parties
- **OFAC SDN sanctions list** reference
- **Hill (1995) Benford's Law in fraud detection** — `American Mathematical Monthly` 102(4)
- **NIST SP 800-30 Rev. 1** — risk assessment guide

## Key design decisions

### Statistical methods first, ML hooks second
Z-score and IQR detect outliers without any ML. Benford's Law is a deterministic chi-square test. These run on every dataset without infrastructure dependencies. ML-based detectors (isolation forest, autoencoder) are wired through `detect_with_ml_hook()` — but the core analytics work without them.

This is a deliberate choice: deterministic statistics are reproducible and auditor-defensible. Per Rule 7, when no ML detector is wired, the engine returns empty (no fabricated findings) — but the statistical methods still produce results. So an auditor running the engine on day one (no ML model trained yet) gets useful Z-score/IQR/Benford findings; on day 100 (with a trained model), the ML hook augments those findings.

### Bessel-corrected sample std
`compute_mean_std()` uses `n - 1` denominator, not `n`. This is the standard sample standard deviation correction for finite populations. Avoids the systematic underestimation of population std that the biased estimator produces.

### Benford chi-square at 95% / 90% confidence
The chi-square thresholds are 15.5 (~95%, df=8) for FAIL and 13.4 (~90%, df=8) for WARNING. Insufficient sample (<50) returns INSUFFICIENT_DATA — never silently passes. This matches the Hill (1995) and modern fraud detection practice (Carslaw 1988, Nigrini 2012).

### Vendor reassessment cadence per CBK Outsourcing Guidelines
- CRITICAL vendors: every 180 days (semiannual)
- HIGH: annual
- MEDIUM: biennial
- LOW: triennial

These match CBK's expectations for outsourcing oversight intensity per vendor materiality. Production deployments override per their specific CBK supervisor's letters.

### Concentration risk threshold at 25%
CBK Outsourcing Guidelines flag concentration > 25% in a single category for review. The framework computes concentration % per category and surfaces breaches. Production may tighten (e.g., 15% for cloud) or loosen per their risk appetite.

### 8-dimension vendor risk model
Beyond traditional financial/operational, modern vendor risk includes:
- **CYBER** — vendor's own security posture
- **CONCENTRATION** — single-vendor dependency
- **DATA_PRIVACY** — GDPR/Kenya DPA exposure
- **BUSINESS_CONTINUITY** — exit plan + redundancy

EU DORA + Basel BCBS 239 specifically call out these dimensions. The framework supports per-dimension scoring; production deployments can weight per-dimension differently in `compute_overall_risk_score()`.

### Always-on alert SLAs match industry incident response
- **P1 CRITICAL**: 15-minute response (PagerDuty + SMS) — service outage, security breach
- **P2 HIGH**: 4-hour response (Slack + email) — significant degradation
- **P3 MEDIUM**: 24-hour response (email) — non-urgent finding
- **P4 LOW**: 1-week response (audit committee digest) — minor observation

Channels escalate accordingly — P1 hits 5 channels including paging; P4 hits 1 (audit committee digest).

### NIST CSF v2.0 with new GOVERN function
NIST CSF v2.0 (released 2024) adds GOVERN as a new function alongside the original 5 (IDENTIFY/PROTECT/DETECT/RESPOND/RECOVER). The framework references this evolution explicitly. Production deployments still using v1.1 should migrate; the framework supports both via the categories mapping.

### ISO 27001:2022 control reorganization
ISO 27001:2022 reorganized the 114 controls of the 2013 version into 93 controls across 4 groups (Organizational/People/Physical/Technological). The framework codifies the new structure with per-group counts. Production deployments validate their ISMS against the 2022 baseline.

### Acknowledged alerts terminate the SLA timer
`AssuranceAlert.is_overdue_for_response()` returns False once `acknowledged_at_utc` is set. The SLA is on response (acknowledgment), not resolution. This matches industry incident response practice — pager-out at SLA means "someone has confirmed the alert," not "issue is fixed."

## Engine Hub integration

Tier 11 expanded from 2 to 3 engines. **G117 coverage holds at ≥ 95%.**

## Tests

- 33 self-tests in `audit_analytics_vendor.py`
- 24 integration tests in `tests/integration/test_v10_25_audit_analytics_vendor.py`

## Verified output

```
✓ audit_analytics_vendor self-test passed (33 tests)
Ran 497 tests in 59.358s OK
Audit: 122/122 gates PASS
```

## Standards registry — 12 Audit/GRC active

```
audit (subcategory) — 12 of 17 active after v10.25:
  ENH-201:    Audit Universe & Risk-Based Planning             (v10.23)
  ENH-202:    Continuous Control Monitoring Engine             (v10.23)
  ENH-203:    Electronic Working Papers                         (v10.23)
  ENH-204:    Issue Tracking & Remediation                     (v10.24)
  ENH-205:    AI-Powered Audit Analytics                       (v10.25) ← NEW
  ENH-206:    Automated Control Testing                        (v10.24)
  ENH-AUD-R1: Control-Graph Cross-Framework Mapping            (v10.24)
  ENH-AUD-R2: AI-Powered Third-Party / Vendor Risk Monitoring  (v10.25) ← NEW
  ENH-AUD-R4: Automated Remediation Ticketing Integration      (v10.24)
  ENH-AUD-R5: 24/7 Always-On Assurance                         (v10.25) ← NEW
  ENH-AUD-R6: Cybersecurity Audit Framework Integration        (v10.25) ← NEW
  ENH-AUD-R7: Connect-Validate-Respond Architecture            (v10.23)

Audit/GRC still planned: 5 (for v10.26; v10.27 closes)
  ENH-207:    Auditor Dashboard & Mobile Access
  ENH-208:    External Auditor Portal
  ENH-209:    Audit Committee Reporting
  ENH-210:    Audit Trail & Compliance Certification
  ENH-AUD-R3: Board-Ready Risk-Quantified Dashboards
```

## Honest acknowledgements

1. **No actual ML detectors ship.** `detect_with_ml_hook()` is the entry point; isolation forest, autoencoder, and custom-ML detectors are per-deployment. Without wiring, statistical methods (Z-score, IQR, Benford) deliver useful baseline analytics.

2. **Benford analysis requires natural data distributions.** Audit transaction amounts, journal entries, vendor invoices typically follow Benford's Law. Manipulated values (rounded amounts, threshold-avoiders, duplicates) often don't — making Benford a useful fraud-detection proxy. But Benford is NOT a positive identifier of fraud; it's a screening tool that triggers further investigation. The framework returns suspicion levels (NORMAL/WARNING/FAIL), not fraud verdicts.

3. **Z-score assumes approximately normal distribution.** Highly skewed data (transaction amounts, exposure sizes) may produce too many or too few anomaly flags. The IQR method is more robust to skew. Production deployments should use both and triangulate.

4. **Vendor risk scoring is an unweighted average.** `compute_overall_risk_score()` treats all dimensions equally. Production deployments can override with different weights (e.g., CYBER 2× weight for technology vendors). The framework supports this via dimension-specific scoring.

5. **No actual sanctions screening, adverse media monitoring, or KYC ships.** The risk dimensions are tracked but not automated. Wiring to OFAC SDN, adverse media APIs (Refinitiv, Sayari), and KYC providers (Trulioo, Onfido) is per-deployment.

6. **Concentration thresholds are seed values.** 25% is a reasonable starting point per CBK Outsourcing Guidelines. Banks with specific guidance from their CBK supervisor may use different thresholds; some industries (cloud-heavy) tolerate higher concentration if redundancy is documented.

7. **No actual paging integration.** PagerDuty/SMS/Slack channel selection is a routing decision; actual API integration is per-deployment. The framework selects channels but does NOT call the API.

8. **NIST CSF coverage is binary per category.** A category is either "implemented" or not. Real maturity assessments use 4-5 levels (Tier 1-4 in CSF). The framework supports binary as the seed; production deployments may extend to maturity tiers.

9. **No control inheritance modeling.** A control may satisfy multiple framework references (handled in v10.24); but a parent-child control hierarchy (e.g., generic "access control" parent → specific "MFA" child) is not modeled. Future enhancement.

10. **No persistence.** All engines in-memory per instance.

## What v10.26 ships next

**Dashboards + auditor portal + committee reporting** (4 standards):
- ENH-207 Auditor Dashboard & Mobile Access (real-time dashboard for internal audit team — KPIs, open issues, due tests, alert backlog)
- ENH-208 External Auditor Portal (read-only access for external auditors with engagement-scoped permissions)
- ENH-209 Audit Committee Reporting (board-ready summary reports + risk heatmap + plan-vs-actual)
- ENH-AUD-R3 Board-Ready Risk-Quantified Dashboards (CRO-style dashboard with risk metrics aggregated across the audit/GRC stack)

These deliver the operational intelligence layer atop v10.23/24/25 — surfacing the captured data through dashboards/portals/reports for the various audiences (internal team / external auditors / audit committee / board).

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG | 13/13 | ✅ closed |
| Batch 2 — Credit | 19/19 | ✅ closed |
| KESONIA enhancement | 1/1 | ✅ closed |
| Batch 3 — RMS | 17/17 | ✅ closed |
| **Batch 4 — Audit/GRC (v10.23–v10.27)** | **12/17** | **🟡 in flight (3 of 5 batches)** |

After v10.25: **74 of 247 standards active** (70 + 4 new). 173 still planned across remaining categories.
