# CHANGELOG v10.57 — revenue_assurance arc · ENH-248 Regulatory Revenue Reporting

**Status:** revenue_assurance arc 8/8+1 batches (closure pending v10.58)
**Audit:** 131/132 (transient — see G117 note below) · **G128:** STABLE (322 modules · 805 imports · 3 HARD)
**Active standards:** 126 → **127** / 260 · **Scenario library:** 82 → **86** (4 ORR-* added)

## What this batch does

Final standalone engine of the revenue_assurance arc. Diagnostic engine for revenue-side regulatory report generation + management-vs-statutory reconciliation. Engine produces **structured ReportPackage data**; serialization (XBRL/XML/CSV) and submission rails (CBK BSD portal, KRA iTax) belong to the caller's submission workflow per Rule 7.

## New module

`utils/regulatory_revenue_reporting.py` (~970 lines · 15 self-tests). Single public engine `RegulatoryRevenueReportingEngine` with 3 capabilities.

## Three capabilities

### A) `generate_report(template, records) → ReportPackage`
- Aggregates records into line items per `ReportLineSpec.revenue_categories`
- Out-of-period records excluded
- Unmapped categories surfaced as `unmapped_categories` tuple — never silently dropped (silent dropping risks under-reporting to the regulator)
- Per Rule 1: each `ReportLineItem` carries `contributing_record_ids`, `record_count`, and `revenue_categories` so a CBK reviewer can trace any line back to source records

### B) `reconcile_management_vs_statutory(...)` 
- Compares `ReportPackage` line items to `StatutoryReportRecord` stream by `(line_code, period_label)`
- KES 1 absolute tolerance
- 4 `DifferenceType` classifications:
  - **TIMING** — variance < 5% of larger figure (likely cut-off difference)
  - **GENUINE** — variance ≥ 5% (investigate)
  - **CLASSIFICATION** — different line code carries the amount (caller-supplied resolution; engine doesn't auto-detect cross-line)
  - **UNCLASSIFIED** — line missing from one side
- Missing-from-statutory and missing-from-management both surface as `UNCLASSIFIED` HIGH severity for human review

### C) `validate_completeness(package, template) → CompletenessReport`
- Required-vs-optional distinction prevents noise on lines that legitimately have no activity
- 3 `CompletenessIssue` types: `MISSING_LINE_ITEM`, `ZERO_AMOUNT_REQUIRED_LINE`, `UNMAPPED_CATEGORY`
- Validates `package.template_id == template.template_id` (prevents accidental cross-comparison)

## 11 frozen dataclasses with construction-time validation

- `ReportLineSpec` — non-empty `revenue_categories`
- `ReportTemplate` — non-empty `line_specs`, unique `line_code`s, `period_end ≥ period_start`
- `StatutoryReportRecord`, `ReportLineItem`, `ReportPackage`
- `ReconciliationDifference`, `MgmtStatReconResult`
- `CompletenessFinding`, `CompletenessReport`

## 3 Regulator enums

`CBK` (Central Bank of Kenya), `KRA` (Kenya Revenue Authority), `INTERNAL` (management-only). Engine doesn't differentiate behaviour by regulator — that's a serialization concern.

## Compositional reuse

- `RevenueRecord` from ENH-241 — shared revenue record shape across the arc
- `ValidationSeverity` from ENH-241 — same severity vocabulary

## Scenario library

- **ORR-01** Generate report aggregates 4 records into 2 lines (INT 800k + FEE 150k); contributing record IDs surface (4 assertions)
- **ORR-02** Recon with TIMING (2% variance) + GENUINE (50% variance) classification (3 assertions)
- **ORR-03** Unmapped categories surfaced + completeness flags `UNMAPPED_CATEGORY` (2 assertions)
- **ORR-04** Required `L-FEE` zero → `ZERO_AMOUNT_REQUIRED_LINE`; optional `L-FX` zero NOT flagged (3 assertions)

12/12 PASS.

## Standards registry

ENH-248 activated: `planned → active`, `v10.40+ → v10.57`, `affected_engines: ("revenue_assurance", "regulatory_reporting") → ("regulatory_revenue_reporting",)`.

## Verification

- `python3 -m utils.regulatory_revenue_reporting` → ✓ 15 tests
- `python3 scripts/audit.py` → **131/132 (G117 transient)**
- `python3 scripts/structure_audit.py` → STABLE (322 modules · 805 imports · HARD=3)

## G117 transient — known state, fixes at v10.58 closure

After this batch, G117 (engine_hub_integration_coverage) reports 94.5% (173/183), one tick below the 95% threshold. **This is the expected transient state** caused by adding 8 new engines across v10.50-v10.57 without hub-tier registration — the v10.46-amended Lean+Compact protocol explicitly defers Engine Hub Tier additions to arc closure to avoid duplicate work.

The v10.58 closure batch (next) ships:
- Tier 26 in `pages/7_admin.py` registering all 8 engines in the hub tuple
- `pages/95_revenue_assurance_cockpit.py` importing all 8 engines

Either of these alone restores G117 above 95%; together they push coverage well above. v10.58 verification will report **134/134 PASS** (132 existing + G133 + G134).

This is the same pattern observed earlier in the credit_model_risk arc closure (v10.49 — G117 was momentarily below threshold after v10.48 addition of credit_committee.py, then restored by the closure cockpit + Tier 25 in v10.49). Documented and expected.

## Honest scope notes

1. **No XBRL/XML/CSV serialization.** Engine outputs `ReportPackage` data structures only. Different regulators want different formats; that's a caller concern.
2. **No actual submission.** No CBK BSD portal calls, no KRA iTax submissions, no email. Submission rails are human workflow.
3. **No cross-line CLASSIFICATION detection.** When mgmt has 100k in L-INT and statutory has 100k in L-FEE, that's a classification difference but the engine flags both as `UNCLASSIFIED`. Cross-line analysis requires reasoning about category mappings beyond what's encoded in the template; left to human review.
4. **No FX or comparative period.** Single-period KES-only reports. Multi-currency reports and prior-year comparatives require a wrapping layer.
5. **TIMING heuristic is 5% rule of thumb.** Real cut-off discipline requires looking at record dates relative to period boundary (the `TIMING_DAYS_HEURISTIC=5` constant exists but isn't currently consulted — engine uses amount variance only). Future revision could combine both signals.

## Files changed

- **NEW** `utils/regulatory_revenue_reporting.py`
- **MOD** `utils/standards_registry.py` (ENH-248 activated)
- **MOD** `utils/scenario_simulator.py` (+4 ORR-*)

**Next:** v10.58 — revenue_assurance arc closure. G133 + G134 + Tier 26 + Master Prompt + cockpit page.
