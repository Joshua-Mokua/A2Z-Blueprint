# Changelog — v10.288 Compliance Dashboard & KPIs (lone)

**Date:** 2026-05-08
**Phase:** 2B
**Audit:** 180/180 gates PASS = 100.0%
**G162 Rebase:** 3927 → 3950 (+17 CBK, +6 Kenya; rationale: ComplianceDashboardEngine locks three regulatory references and the REGULATORY_FRAMEWORKS enum carries CBK + Kenya tokens)

---

## Summary

Lone-standard cluster. Surfaces the existing CMS suite (#191–#200,
already active) via a dedicated executive cockpit. The CMS engines —
KYC onboarding, KYB onboarding, PEP/sanctions screening, AML monitoring,
SAR filing, regulatory change management, policy management, training
tracking, risk assessment, examiner portal — were built earlier;
this batch closes the gap by giving the CCO, MD, audit committee, and
board a unified read-side surface across them.

16 active standards remain planned: CIMS arc 15 (#166–#180) and Trade
Finance Mobile 1 (#279).

---

## Standard activated

| ID      | Name                            | Subcategory   | Risk |
|---------|---------------------------------|---------------|------|
| ENH-200 | Compliance Dashboard & KPIs     | compliance    | Cat C |

Flipped status="active", implementation_batch="v10.288".

---

## Engine module

### `utils/compliance_dashboard.py` (#200)

`ComplianceDashboardEngine` — KPI definition + observation + executive view registry. Read-side composition over CMS suite (#191–#200); never modifies upstream engines.

Byte-for-byte invariants:
- `KPI_DOMAINS` (8: KYC, AML, SANCTIONS, REGULATORY_REPORTING, POLICY, TRAINING, EXAMINER_FINDINGS, RISK_ASSESSMENT)
- `KPI_FREQUENCIES` (5: DAILY, WEEKLY, MONTHLY, QUARTERLY, ANNUAL)
- `KPI_STATES` (4: ACTIVE, PAUSED, DEPRECATED, ARCHIVED) — Rule 4 (DEPRECATED → ARCHIVED only)
- `KPI_BREACH_SEVERITIES` (4: GREEN, AMBER, RED, CRITICAL)
- `EXECUTIVE_VIEW_TYPES` (5: BOARD_PACK, AUDIT_COMMITTEE, CCO_DASHBOARD, REGULATOR_BRIEFING, INTERNAL_REVIEW)
- `REGULATORY_FRAMEWORKS` (5: CBK_PRUDENTIAL, DPA_KENYA_2019, AML_POCAMLA, BASEL_III, ISO_27001)
- `DEFAULT_KPI_REFRESH_HOURS = 24`
- `DEFAULT_BREACH_ESCALATION_HOURS = 4`
- `CBK_PRUDENTIAL_REFERENCE = "CBK Prudential Guidelines"`
- `DPA_KENYA_REFERENCE = "Data Protection Act 2019"`
- `AML_REFERENCE = "POCAMLA Kenya 2009"`

Key methods:
- `register_kpi_definition`, `transition_kpi_state`
- `record_kpi_observation` (severity must be one of GREEN/AMBER/RED/CRITICAL)
- `register_executive_view` (5 view types)
- `compliance_summary(framework=None, days=30)` — aggregates active KPIs by severity and domain, with optional framework filter
- `kpi_breach_log(severity=None)` — defaults to RED + CRITICAL across all frameworks

---

## Page

### `pages/103_compliance_dashboard.py`

7 tabs (G4 ceiling, planned upfront):
1. KPI definitions — register + state transitions
2. Observations — record observed value + severity + narrative
3. Executive views — board pack / audit committee / CCO / regulator briefing / internal review
4. Per-framework summary — selectable across ALL or one of 5 frameworks
5. Breach log — RED + CRITICAL by default, single-severity filter available
6. Drill-down by domain — composes KPI registry + observations to produce per-domain views
7. Metrics — dashboard-level counts and observation coverage

Canonical imports throughout (G177):
```python
from utils.core_audit import audit_log
from pages._access import require_access
require_access("compliance_regulatory.compliance_dashboard")
```

`audit_log()` calls use canonical signature on every write surface.

---

## Audit gate

### G180 — `gate_compliance_dashboard_registered`

Locks the engine + 6 enum tuples + 2 default constants + 3 regulatory reference strings byte-for-byte.

Checks:
1. `utils.compliance_dashboard` imports and exposes `ComplianceDashboardEngine`.
2. All 6 enum tuples byte-for-byte.
3. `ALLOWED_KPI_TRANSITIONS["ARCHIVED"]` is `()` (Rule 4 terminal).
4. `ALLOWED_KPI_TRANSITIONS["DEPRECATED"]` is `("ARCHIVED",)` (DEPRECATED → ARCHIVED only).
5. Default constants (24h refresh, 4h escalation) match.
6. Three regulatory reference strings match: CBK Prudential Guidelines, Data Protection Act 2019, POCAMLA Kenya 2009.
7. ENH-200 is active and tagged v10.288.
8. Page 103 exists on disk.

---

## G162 ratchet

```
Before:    3927 (established_in v10.287)
After:     3950 (established_in v10.288)
Delta:     +23 (CBK +17, Kenya +6)
Scope history entries: 42
```

The increase comes from the engine's three regulatory reference constants being echoed across the audit gate, the cockpit caption, the manifest description, and the Tier 48 admin entry — plus the REGULATORY_FRAMEWORKS enum carrying CBK_PRUDENTIAL, DPA_KENYA_2019, and AML_POCAMLA token strings.

---

## Tier registration

`Tier 48 — Compliance Dashboard & KPIs (v10.288, Phase 2B)` added to `pages/7_admin.py` with the engine documented.

---

## Manifest entry

`103_compliance_dashboard.py` registered with all 7 required fields:
- `department_primary`: "compliance_regulatory"
- `module_path`: "compliance_regulatory.compliance_dashboard"
- `current_module_key`: "compliance_dashboard"
- `icon`: "⚖️"

G160 enforces; G177 confirms `require_access("compliance_regulatory.compliance_dashboard")` resolves.

---

## Files in this release

```
utils/compliance_dashboard.py                  NEW (#200, ~340 lines)
utils/standards_registry.py                    flipped ENH-200 to active
scripts/audit.py                               +G180 gate_compliance_dashboard_registered
pages/7_admin.py                               +Tier 48
pages/103_compliance_dashboard.py              NEW (7-tab cockpit)
pages/_manifest.json                           +103 entry
data/audit_baselines.json                      g162 rebase to 3950
CHANGELOG_v10.288.md                           NEW (this document)
```

---

## Audit summary

```
  Score: 180/180 gates = 100.0% — PASS
```

Compliance Management closure complete (#191–#200 all active). 314 of 330 standards active. 16 planned remain (CIMS arc 15 + Trade Finance Mobile 1).

Next batch: **v10.289 — Trade Finance Mobile App (#279, lone, mirrors v10.283 SWIFT pattern)**.
