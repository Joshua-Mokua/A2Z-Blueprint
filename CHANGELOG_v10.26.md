# CHANGELOG v10.26 — Audit/GRC Arc Batch 4: Dashboards + Portal + Committee + Board

**Audit:** 122/122 PASS — **109th consecutive clean.**

## What ships in v10.26

`utils/audit_dashboards_portal.py` — 1200 lines, **Cat A**. 4 of 17 Audit/GRC standards active:

| Standard | Implemented as |
|---|---|
| **ENH-207** Auditor Dashboard & Mobile Access | 4-mode `DashboardViewMode` (DESKTOP_FULL / TABLET / MOBILE_DENSE / MOBILE_SUMMARY); 3-direction `KPIDirection` (HIGHER_IS_BETTER / LOWER_IS_BETTER / TARGET_RANGE); 4-state `KPIStatus` (GREEN / AMBER / RED / UNKNOWN); `AuditorDashboardKPI` with direction-aware status derivation; `AuditorDashboardSnapshot` with `red_kpis()`/`amber_kpis()`/`overall_health()`/`for_mobile()` filters; `build_default_kpi_catalog()` factory producing 8 standard KPIs aggregating from v10.23/24/25 board summaries |
| **ENH-208** External Auditor Portal | 3-tier `ExternalAuditorAccessLevel` (READ_ONLY / READ_WITH_NOTES / EXPORT_ALLOWED); 9-type `ExternalAuditorRequestType` (PLANNING_MEMO/CONTROL_NARRATIVES/TEST_RESULTS/ISSUE_TRACKING/POLICIES/EVIDENCE/BOARD_MINUTES/REGULATORY_CORR/PRIOR_REPORTS); `EngagementScope` with `is_active()` (default 6-month tolerance post period-end), `covers_request_type()`, `covers_entity()`; `authorize_external_access()` with explicit denial reasons per Rule 1; `ExternalAuditorAccessLog` immutable audit trail |
| **ENH-209** Audit Committee Reporting | 5-level `ReportingFrequency` enum (MONTHLY/QUARTERLY/SEMI_ANNUAL/ANNUAL/AD_HOC); `MINIMUM_AUDIT_COMMITTEE_REPORTING=QUARTERLY` per CBK CRMF §7.7 + SOX §301; `RiskHeatmapCell` for 5×5 likelihood × impact matrix (validated 1-5); `compute_risk_heatmap_cell()` + `build_risk_heatmap_summary()` 4-zone classification (low ≤4, medium 5-10, high 11-15, critical 16-25); `PlanVsActual` with `completion_pct()` + `hours_variance_pct()`; `AuditCommitteeReport` period-end report dataclass |
| **ENH-AUD-R3** Board-Ready Risk-Quantified Dashboards | 10-category `RiskCategory` (CREDIT/MARKET/OPERATIONAL/LIQUIDITY/STRATEGIC/REPUTATIONAL/REGULATORY/CYBERSECURITY/CLIMATE/THIRD_PARTY per Basel + COSO ERM); 4-state `RiskAppetiteStatus` (WITHIN_APPETITE / APPROACHING_LIMIT 80-99% / LIMIT_BREACH ≥100% / UNKNOWN); `QuantifiedRiskMetric` with VaR + Expected Loss support per NIST SP 800-30; `BoardRiskDashboard` with `metrics_in_breach()`/`metrics_approaching_limit()`/`total_exposure_by_category()` aggregations |

## Regulatory provenance

- **IIA IPPF Standard 2440** — disseminating results
- **IIA IPPF Standard 2450** — overall opinions
- **IIA IPPF Standard 2500** — monitoring progress
- **COSO ERM** — board reporting
- **CBK CRMF April 2021 §7.7** — audit committee reporting
- **CBK Banking Act §44** — internal audit reporting to board
- **Sarbanes-Oxley §301** — audit committee responsibilities
- **PCAOB AS 1301** — communications with audit committees
- **Basel BCBS** — internal audit principles (2012)
- **UK Corporate Governance Code** — audit committee provisions
- **NACD Risk Oversight** — board responsibility framework
- **NIST SP 800-30 Rev. 1** — quantitative risk metrics
- **Kenya Data Protection Act 2019 §28-§31** — controller obligations

## Key design decisions

### Direction-aware KPI thresholds with TARGET_RANGE
The `KPIDirection.TARGET_RANGE` mode handles metrics where staying within a band is desirable (e.g., capital ratio 14.5%-22% — too low triggers regulatory action, too high signals inefficient capital deployment). The other two directions (HIGHER_IS_BETTER, LOWER_IS_BETTER) cover the standard cases. This avoids the trap where the same threshold logic is wrong for some metrics.

### Mobile view sorted by status priority
`for_mobile()` returns top-4 (or top-8 for DENSE) KPIs ordered RED → AMBER → GREEN → UNKNOWN. The CAE walking into a 7am board meeting needs to see the worst issues first; she doesn't need to scroll past green KPIs to find the problems. Mobile is intentionally lossy — a focused subset, not a compressed full view.

### External auditor access scoped to engagement
Per PCAOB AS 1301 + IIA IPPF Std 2440, external auditor access must be tied to a specific engagement. `EngagementScope` codifies:
- **Time scope**: fiscal_period + 6-month default tolerance (extends valid_until automatically)
- **Object scope**: in_scope_entity_ids + in_scope_request_types (positive list, not blanket)
- **Action scope**: access_level (READ_ONLY / READ_WITH_NOTES / EXPORT_ALLOWED)

Every access attempt produces an immutable `ExternalAuditorAccessLog` with `access_granted` + (if denied) `denial_reason`. The audit committee can later reconstruct exactly what each external auditor saw.

### Authorization is explicit, not inferred
`authorize_external_access()` returns `(granted, reason)`. Both granted and denied paths produce a clear reason string. Per Rule 1 — the engine never silently denies (or grants); the reason is always recorded.

### 5×5 risk heatmap is the industry standard
Likelihood × Impact each scored 1-5 produces a 1-25 risk score. The 4-zone summary (low ≤4 / medium 5-10 / high 11-15 / critical 16-25) is conventional in board reporting. The framework validates 1-5 inputs and raises ValueError on out-of-range values (auditor can't accidentally score 6×6).

### Plan-vs-actual surfaces both completion + hours variance
A common audit committee question: "Are we delivering on the plan?" Answer needs both:
- **Completion %**: how many planned engagements are done
- **Hours variance %**: are we under/over budget on effort

Banks running over hours typically have scope creep or weak planning; under hours may signal cut corners or postponed work. Both signals matter to the committee.

### Risk appetite at 80% approaching, 100% breach
`APPROACHING_LIMIT` fires at 80-99% utilization, `LIMIT_BREACH` at ≥100%. Production deployments may use different thresholds (some banks use 90%/100%, some 70%/100%). The framework defaults match common bank practice. Override per `compute_overall_risk_score()` extension.

### NIST SP 800-30 quantitative risk metrics
`QuantifiedRiskMetric` supports both Expected Loss (`expected_loss_kes` = PD × LGD × EAD for credit) and Value at Risk (`var_95_kes` at 95% confidence by default). These are the two industry-standard quantification approaches. Production deployments wire model engines (credit IFRS 9 from v10.11, FRTB market risk, op risk SMA) to populate these fields.

### Board summary aggregates across the full Audit/GRC stack
`AuditDashboardsPortalEngine.board_summary()` reports:
- Number of dashboard snapshots + latest health
- Number of engagements + access logs + denied attempts
- Number of committee reports
- Number of board dashboards + metrics in breach + approaching

This is what the audit committee secretary sends out 2 days before the meeting.

## Engine Hub integration

Tier 11 expanded from 3 to 4 engines. **G117 coverage holds at ≥ 95%.**

## Tests

- 30 self-tests in `audit_dashboards_portal.py`
- 25 integration tests in `tests/integration/test_v10_26_audit_dashboards_portal.py`

## Verified output

```
✓ audit_dashboards_portal self-test passed (30 tests)
Ran 522 tests in 54.286s OK
Audit: 122/122 gates PASS
```

## Standards registry — 16 Audit/GRC active

```
audit (subcategory) — 16 of 17 active after v10.26:
  ENH-201:    Audit Universe & Risk-Based Planning             (v10.23)
  ENH-202:    Continuous Control Monitoring Engine             (v10.23)
  ENH-203:    Electronic Working Papers                         (v10.23)
  ENH-204:    Issue Tracking & Remediation                     (v10.24)
  ENH-205:    AI-Powered Audit Analytics                       (v10.25)
  ENH-206:    Automated Control Testing                        (v10.24)
  ENH-207:    Auditor Dashboard & Mobile Access                (v10.26) ← NEW
  ENH-208:    External Auditor Portal                           (v10.26) ← NEW
  ENH-209:    Audit Committee Reporting                         (v10.26) ← NEW
  ENH-AUD-R1: Control-Graph Cross-Framework Mapping            (v10.24)
  ENH-AUD-R2: AI-Powered Third-Party / Vendor Risk Monitoring  (v10.25)
  ENH-AUD-R3: Board-Ready Risk-Quantified Dashboards           (v10.26) ← NEW
  ENH-AUD-R4: Automated Remediation Ticketing Integration      (v10.24)
  ENH-AUD-R5: 24/7 Always-On Assurance                         (v10.25)
  ENH-AUD-R6: Cybersecurity Audit Framework Integration        (v10.25)
  ENH-AUD-R7: Connect-Validate-Respond Architecture            (v10.23)

Audit/GRC still planned: 1 (for v10.27 closure)
  ENH-210: Audit Trail & Compliance Certification
```

## Honest acknowledgements

1. **No actual UI rendering ships.** This batch produces structured data (KPIs, snapshots, reports). The actual Streamlit page rendering, mobile push notifications, board PDF generation belong in `pages/N_audit_dashboard.py` (separate batch).

2. **No external auditor portal authentication.** The framework authorizes access requests, but actual SSO/OAuth integration with external firms (PwC/Deloitte/EY) is per-deployment.

3. **Risk metrics are not auto-calculated.** `QuantifiedRiskMetric` accepts current_value, appetite_limit, EL, VaR — but doesn't compute them. Population happens upstream via the model engines (v10.11 credit, FRTB market risk model, etc.). The framework presents what others compute.

4. **Risk heatmap doesn't model dependencies.** Each cell is independent. Production deployments may extend with risk correlation matrices for portfolio-level analysis (NIST SP 800-30 §3.3).

5. **No regulatory submission generation.** Reports are structured data; the actual CBK Form CBK 105 PDF/Excel/XML format generation is a downstream conversion step.

6. **Audit committee email distribution is not integrated.** The engine produces `AuditCommitteeReport` records; emailing them to committee members + secretary requires SMTP/Exchange integration per deployment.

7. **6-month tolerance for engagement period is conservative.** Some external audits run longer (group reorg, restatements). Production may extend `valid_until` explicitly.

8. **Access logs in-memory.** Production must persist to immutable WORM (Write-Once-Read-Many) storage for SOX §404 compliance — typically S3 Object Lock or equivalent.

9. **No watermarking on exported documents.** When access_level = EXPORT_ALLOWED, the framework permits download but doesn't add per-auditor watermarks. This is a per-deployment data loss prevention concern.

10. **Board dashboard refresh frequency not enforced.** Board members typically expect monthly refresh; the framework supports any cadence via `generated_at_utc`. Scheduled refresh is downstream workflow.

## What v10.27 ships next — RMS arc closure pattern

**Audit/GRC arc closure** (1 standard + closure batch):
- ENH-210 Audit Trail & Compliance Certification — the final audit standard, focusing on cumulative audit trail integrity + period-end compliance attestation across the 16 prior standards
- G123 audit gate — locks the 17 active standards + 5 engines + 5 integration tests
- 4 drift tests verifying gate behavior
- Closing CHANGELOG with full 5-batch retrospective
- Phase 2 batch 4 closure package

This follows the established arc-closure pattern (Climate v10.10 G120 / Credit v10.16 G121 / RMS v10.22 G122).

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG | 13/13 | ✅ closed |
| Batch 2 — Credit | 19/19 | ✅ closed |
| KESONIA enhancement | 1/1 | ✅ closed |
| Batch 3 — RMS | 17/17 | ✅ closed |
| **Batch 4 — Audit/GRC (v10.23–v10.27)** | **16/17** | **🟢 ready for v10.27 closure** |

After v10.26: **78 of 247 standards active** (74 + 4 new). 169 still planned across remaining categories.
