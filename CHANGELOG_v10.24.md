# CHANGELOG v10.24 — Audit/GRC Arc Batch 2: Issues + Testing + Frameworks + Tickets

**Audit:** 122/122 PASS — **107th consecutive clean.**

## What ships in v10.24

`utils/audit_controls_issues.py` — 1137 lines, **Cat A**. 4 of 17 Audit/GRC standards active:

| Standard | Implemented as |
|---|---|
| **ENH-204** Issue Tracking & Remediation | 7-source `IssueSource` enum (INTERNAL/EXTERNAL audit, CONTROL_TEST_FAILURE links to v10.23, REGULATOR_LETTER, WHISTLEBLOWER, SELF_IDENTIFIED, INCIDENT_INVESTIGATION); 8-state `IssueStatus` lifecycle with explicit `ALLOWED_ISSUE_TRANSITIONS` graph (REJECTED is terminal); 4-tier `IssueSeverity` mapped to `DEFAULT_ISSUE_REMEDIATION_DAYS` (CRITICAL=7d, HIGH=30d, MEDIUM=60d, LOW=90d per CBK CRMF §7.5); 4-bucket `IssueAgingBucket` (FRESH/APPROACHING/OVERDUE/AGED); `compute_issue_deadline()` + `compute_issue_aging()` helpers |
| **ENH-206** Automated Control Testing | 7-language `TestScriptLanguage` enum (SQL/Python/SPL/KQL/Shell/Regex/Declarative); `TestSchedule` with `is_due()` + `is_overdue()` cadence-based detection; 6-state `TestScheduleStatus`; `TestCoverageReport` with per-framework breakdown + `coverage_passes_threshold()` (default 80%) |
| **ENH-AUD-R1** Control-Graph Cross-Framework Mapping | 14-framework `ControlFramework` enum (COSO IC/ERM, COBIT 2019, ISO 27001/27002, NIST CSF/800-53, PCI DSS, SOX 404, CBK PG/02 + CRMF, Basel BCBS 239, GDPR, Kenya DPA); `DEFAULT_CROSS_FRAMEWORK_MAPPINGS` with 10 seed canonical concepts (ACCESS_CONTROL_LOGICAL, SEGREGATION_OF_DUTIES, CHANGE_MANAGEMENT, INCIDENT_RESPONSE, DATA_BACKUP_RECOVERY, ENCRYPTION_DATA_AT_REST, AUDIT_LOGGING, VENDOR_RISK_MANAGEMENT, RECONCILIATION_INTEGRITY, ACCESS_REVIEW_PERIODIC) — each maps to 4-7 specific framework references; `coverage_by_framework()` + `map_control_by_concept()` helpers |
| **ENH-AUD-R4** Automated Remediation Ticketing | 5-system `TicketingSystem` enum (Jira, ServiceNow, GitHub Issues, Azure DevOps, INTERNAL_ONLY); 8-state `TicketStatus` lifecycle; `create_ticket_stub()` with hookable `ticket_creator` per Rule 7 (no creator → INTERNAL_ONLY draft, never fabricated external ID); `sync_ticket_status()` with hookable `status_fetcher` |

## Regulatory provenance

- **IIA IPPF Standard 2500** — monitoring progress (issue tracking)
- **IIA IPPF Standard 2600** — communicating risk acceptance
- **COSO IC** + **ERM** frameworks
- **COBIT 2019** — IT governance + audit framework
- **ISO 27001:2022** — information security controls
- **NIST Cybersecurity Framework (CSF) v2.0**
- **PCI DSS v4.0** — payment card industry
- **SOX §404** — internal control reporting + remediation
- **CBK Prudential Guideline CBK/PG/02** — operational risk controls
- **CBK CRMF April 2021 §7.5** — issue management
- **Basel BCBS 239 §11** — completeness, timeliness

## Key design decisions

### 8-state issue lifecycle reflects audit reality
- `OPEN` → `ASSIGNED` → `IN_PROGRESS` → `PENDING_VERIFICATION` → `CLOSED` is the happy path
- `DEFERRED` accepts management's documented risk acceptance (per IPPF Std 2600)
- `REJECTED` (terminal) for invalid issues — no further transitions
- `REOPENED` allows previously-closed issues to revert (caught recurring failure)

The lifecycle handles the messy realities of remediation: deferrals require sign-off, verifications can fail (back to IN_PROGRESS), and recurring issues need reopening. The graph is explicit so audit committee can trace any issue's path.

### Aging is severity-aware
`compute_issue_aging()` takes both `days_past_deadline` and `days_remaining` along with `sla_days`. APPROACHING fires at ≤25% of SLA remaining — so for a CRITICAL (7-day) issue, APPROACHING fires at 1.75 days remaining (≤1 day rounded). For a LOW (90-day) issue, APPROACHING fires at 22 days remaining. Each severity gets proportional warning windows.

### Cross-framework mapping uses canonical concepts
Rather than hardcoding 100+ control IDs across 14 frameworks (combinatorial), the framework uses 10 seed canonical concepts. Each concept (e.g., "ACCESS_CONTROL_LOGICAL") maps to its specific framework references. When a control is registered, the auditor selects the concept; the engine auto-derives all 5-7 framework references. This is auditor-defensible: each mapping has a documented canonical lineage.

The seed library covers the most-common cross-framework controls. Production deployments add their organization-specific concepts via `register_mapping()`.

### Ticketing integration honest about no-fab
`create_ticket_stub()` without `ticket_creator` creates an INTERNAL_ONLY stub with status DRAFT. No fabricated external ticket ID. The notes explicitly say "Rule 7: no ticket_creator wired." When the integration eventually wires up, the engine seamlessly creates real tickets — but never silently lies that a ticket exists.

`sync_ticket_status()` similarly: without `status_fetcher`, the stub returns unchanged (no fabricated status). With fetcher, it refreshes from external system. If the fetcher raises, status becomes `SYNC_FAILED` with the exception type captured in notes.

### Test coverage report breaks down by framework
`compute_coverage()` returns:
- Total control count
- Covered count + percentage
- **Per-framework breakdown** (covered/total per framework)

This lets the CAE answer "what's our PCI DSS coverage?" or "are we meeting NIST CSF for fiscal year-end attestation?" — questions the audit committee asks regularly.

### Compose with v10.23
v10.24 doesn't reimplement Control or ControlTestResult — it imports v10.23 implicitly through the related-test-id reference. An Issue can be linked to a v10.23 ControlTestResult via `related_test_id`, completing the trace from monitoring → finding → remediation → ticket.

## Engine Hub integration

Tier 11 expanded from 1 to 2 engines. **G117 coverage holds at ≥ 95%.**

## Tests

- 30 self-tests in `audit_controls_issues.py`
- 21 integration tests in `tests/integration/test_v10_24_audit_controls_issues.py`
- Forward-compat fix: `test_master_prompt_at_v10_22` updated to `test_master_prompt_at_v10_22_or_later` accepting any v10.22+ stamp

## Verified output

```
✓ audit_controls_issues self-test passed (30 tests)
Ran 473 tests in 52.490s OK
Audit: 122/122 gates PASS
```

## Standards registry — 8 Audit/GRC active

```
audit (subcategory) — 8 of 17 active after v10.24:
  ENH-201:    Audit Universe & Risk-Based Planning             (v10.23)
  ENH-202:    Continuous Control Monitoring Engine             (v10.23)
  ENH-203:    Electronic Working Papers                         (v10.23)
  ENH-204:    Issue Tracking & Remediation                     (v10.24) ← NEW
  ENH-206:    Automated Control Testing                        (v10.24) ← NEW
  ENH-AUD-R1: Control-Graph Cross-Framework Mapping            (v10.24) ← NEW
  ENH-AUD-R4: Automated Remediation Ticketing Integration      (v10.24) ← NEW
  ENH-AUD-R7: Connect-Validate-Respond Architecture            (v10.23)

Audit/GRC still planned: 9 (for v10.25-v10.26; v10.27 closes)
  ENH-205:    AI-Powered Audit Analytics
  ENH-207:    Auditor Dashboard & Mobile Access
  ENH-208:    External Auditor Portal
  ENH-209:    Audit Committee Reporting
  ENH-210:    Audit Trail & Compliance Certification
  ENH-AUD-R2: AI-Powered Third-Party / Vendor Risk Monitoring
  ENH-AUD-R3: Board-Ready Risk-Quantified Dashboards
  ENH-AUD-R5: 24/7 Always-On Assurance
  ENH-AUD-R6: Cybersecurity Audit Framework Integration
```

## Honest acknowledgements

1. **Cross-framework mappings are seed values, not exhaustive.** 10 canonical concepts cover the most-common audit controls. Production deployments add concepts (e.g., "ANTI_MONEY_LAUNDERING_KYC", "SANCTIONS_SCREENING") per their applicable framework set.

2. **No external test script execution.** `TestScript` describes scripts (language + description) but does NOT execute them. Real execution wires through `automated_tester` from v10.23 `execute_control_test()` — same separation as the rest of the framework.

3. **No external ticketing integration.** Jira/ServiceNow API calls are per-deployment via `ticket_creator` callable. The framework provides the data model + lifecycle; the wiring is downstream.

4. **No actual ticket status webhook.** `sync_ticket_status()` is a poll-based refresh. Real production deployments may want webhook subscriptions from Jira/ServiceNow for push notifications. The hook structure supports it.

5. **Issue deadlines computed at issue creation are static.** If severity changes during the lifecycle, deadline doesn't auto-recompute. Caller must explicitly re-derive if needed.

6. **No SLA enforcement.** The framework detects `OVERDUE` and `AGED` but doesn't auto-escalate, auto-block, or auto-notify. Escalation actions are downstream workflow integration (probably v10.25 with the dashboard surfaces).

7. **No persistence.** All engines in-memory per instance.

8. **Framework references are version-stamped to specific publication years** in some cases (COSO 2013, COBIT 2019, ISO 27001:2022, NIST CSF v2.0). Production deployments verify currency against their compliance program's official applicable versions.

9. **Canonical concepts have no enforced naming convention.** Production deployments should establish their own naming standards (probably ALL_CAPS_UNDERSCORE) and document which concepts are organization-internal vs library-shared.

10. **No regulatory framework drift detection.** When a framework publishes a new version (e.g., NIST CSF 2.0 → 2.1), the seed mappings need manual update. Future enhancement: subscribe to framework update feeds + alert when mapped controls fall out of currency.

## What v10.25 ships next

**Analytics + vendor + cyber** (4 standards):
- ENH-205 AI-Powered Audit Analytics (anomaly detection, pattern recognition for audit data — Rule 7 hookable)
- ENH-AUD-R2 AI-Powered Third-Party/Vendor Risk Monitoring (vendor onboarding workflow + ongoing risk scoring + due-diligence cycle)
- ENH-AUD-R5 24/7 Always-On Assurance (continuous monitoring + alerting infrastructure tying CVR runs into real-time observability)
- ENH-AUD-R6 Cybersecurity Audit Framework Integration (NIST CSF + ISO 27001 + CIS Controls audit programs)

These move from foundation (v10.23) + workflow (v10.24) to operational intelligence — analytics over the captured data + extended integrations.

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG | 13/13 | ✅ closed |
| Batch 2 — Credit | 19/19 | ✅ closed |
| KESONIA enhancement | 1/1 | ✅ closed |
| Batch 3 — RMS | 17/17 | ✅ closed |
| **Batch 4 — Audit/GRC (v10.23–v10.27)** | **8/17** | **🟡 in flight (2 of 5 batches)** |

After v10.24: **70 of 247 standards active** (66 + 4 new). 177 still planned across remaining categories.
