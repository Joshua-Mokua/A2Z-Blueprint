# Structural Hygiene Audit Report

- Modules scanned: **302**
- Internal imports counted: **753**
- Total findings: **53**
- Hard failures: **3**
- Status: **ATTENTION**

## Findings by severity

- HARD: 3
- WARN: 45
- INFO: 5

## Findings by category

- CIRCULAR_IMPORT: 3
- LAYER_VIOLATION: 0
- GOD_MODULE: 1
- JUNK_DRAWER: 1
- ORPHAN_MODULE: 25
- DUPLICATE_SYMBOL: 15
- SIZE_OUTLIER: 8

## HARD findings

### `utils.core` (CIRCULAR_IMPORT)

**Description:** Circular import detected through 4 modules
**Observed:** `utils.core → utils.actuals_engine → utils.bsc_engine → utils.core_audit → utils.core`
**Suggestion:** Break the cycle by extracting shared types to a lower-layer module, or invert one dependency via a callback/protocol.

### `utils.core` (CIRCULAR_IMPORT)

**Description:** Circular import detected through 2 modules
**Observed:** `utils.core → utils.actuals_engine → utils.core`
**Suggestion:** Break the cycle by extracting shared types to a lower-layer module, or invert one dependency via a callback/protocol.

### `utils.core` (CIRCULAR_IMPORT)

**Description:** Circular import detected through 3 modules
**Observed:** `utils.core → utils.actuals_engine → utils.core_kpi → utils.core`
**Suggestion:** Break the cycle by extracting shared types to a lower-layer module, or invert one dependency via a callback/protocol.

## WARN findings

### `utils.core` (GOD_MODULE)

**Description:** 74 other modules import from this module — exceeds threshold of 15
**Observed:** `74`
**Threshold:** `15`
**Suggestion:** Consider extracting cohesive subsets into focused modules. High fan-in is a refactor smell unless this is an intentional facade.

### `scripts.audit` (JUNK_DRAWER)

**Description:** Module imports from 102 other modules — exceeds threshold of 25
**Observed:** `102`
**Threshold:** `25`
**Suggestion:** High fan-out suggests the module has too many responsibilities. Consider splitting by concern.

### `utils.applicant_data_sources` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.audit_controls_issues` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.audit_dashboards_portal` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.audit_trail_certification` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.benchmark_rates` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.credit_workflow` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.deposit_intelligence` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.document_management` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.efficiency` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.fairness_testing` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.gamification` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.initiative_impact` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.lending_intelligence` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.microtask_engine` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.notifications` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.portfolio_monitoring` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.product_profitability` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.profitability_heatmap` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.profitability_trends` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.reconciliation` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.reconciliation_engine` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.reconciliation_specialized` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.risk_based_pricing` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.scenario_simulator` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.wellness` (ORPHAN_MODULE)

**Description:** No other scanned modules import from this module
**Observed:** `0`
**Threshold:** `1`
**Suggestion:** If this is an intentional entry point, add the short name to ORPHAN_EXEMPT_PATTERNS. Otherwise it may be dead code or a forgotten wiring.

### `utils.operational_risk` (DUPLICATE_SYMBOL)

**Description:** Function 'build_schema_ddl' defined in 3 modules
**Observed:** `3`
**Threshold:** `3`
**Suggestion:** Review whether these implementations are truly distinct or should be consolidated into a shared module. Modules: utils.operational_risk, utils.dormancy_intelligence, utils.edms

### `utils.operational_risk` (DUPLICATE_SYMBOL)

**Description:** Function 'ddl_contains_required_columns' defined in 5 modules
**Observed:** `5`
**Threshold:** `3`
**Suggestion:** Review whether these implementations are truly distinct or should be consolidated into a shared module. Modules: utils.operational_risk, utils.cost_allocation, utils.dormancy_intelligence, utils.edms, utils.flexcube_staging

### `scripts.audit` (DUPLICATE_SYMBOL)

**Description:** Function 'main' defined in 15 modules
**Observed:** `15`
**Threshold:** `3`
**Suggestion:** Review whether these implementations are truly distinct or should be consolidated into a shared module. Modules: scripts.audit, scripts.etl_flexcube, scripts.export_openapi, scripts.generate_growth_plans, scripts.generate_learning_cards

### `utils.treasury_connectivity` (DUPLICATE_SYMBOL)

**Description:** Function 'self_test' defined in 110 modules
**Observed:** `110`
**Threshold:** `3`
**Suggestion:** Review whether these implementations are truly distinct or should be consolidated into a shared module. Modules: utils.treasury_connectivity, utils.rwa_optimization, utils.islamic_treasury, utils.treasury_digital_assets, utils.treasury_unified_platform

### `utils.rwa_optimization` (DUPLICATE_SYMBOL)

**Description:** Class 'AssetClass' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.audit_trail_cert` (DUPLICATE_SYMBOL)

**Description:** Class 'AttestationStatus' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.audit_trail_certification` (DUPLICATE_SYMBOL)

**Description:** Class 'AuditTrailEntry' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.audit_core` (DUPLICATE_SYMBOL)

**Description:** Class 'AuditableEntity' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.rwa_optimization` (DUPLICATE_SYMBOL)

**Description:** Class 'CapitalComponents' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.audit_trail_cert` (DUPLICATE_SYMBOL)

**Description:** Class 'ChainIntegrityResult' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.reconciliation` (DUPLICATE_SYMBOL)

**Description:** Class 'CheckResult' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.audit_trail_cert` (DUPLICATE_SYMBOL)

**Description:** Class 'ComplianceFramework' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.rwa_optimization` (DUPLICATE_SYMBOL)

**Description:** Class 'Exposure' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.scenario_simulator` (DUPLICATE_SYMBOL)

**Description:** Class 'Scenario' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `utils.reconciliation_matching` (DUPLICATE_SYMBOL)

**Description:** Class 'Transaction' defined in 2 modules
**Observed:** `2`
**Threshold:** `2`
**Suggestion:** Two or more modules define the same class name. Review for accidental duplication.

### `scripts.audit` (SIZE_OUTLIER)

**Description:** Module is 15843 lines — exceeds refactor threshold of 4000
**Observed:** `15843`
**Threshold:** `4000`
**Suggestion:** Modules > 4000 lines are difficult to navigate and review. Consider splitting by cohesive concern.

### `utils.core` (SIZE_OUTLIER)

**Description:** Module is 6346 lines — exceeds refactor threshold of 4000
**Observed:** `6346`
**Threshold:** `4000`
**Suggestion:** Modules > 4000 lines are difficult to navigate and review. Consider splitting by cohesive concern.

### `pages.7_admin` (SIZE_OUTLIER)

**Description:** Module is 4761 lines — exceeds refactor threshold of 4000
**Observed:** `4761`
**Threshold:** `4000`
**Suggestion:** Modules > 4000 lines are difficult to navigate and review. Consider splitting by cohesive concern.

## INFO findings

### `pages.2_people` (SIZE_OUTLIER)

**Description:** Module is 3784 lines — above comfortable threshold of 2000
**Observed:** `3784`
**Threshold:** `2000`
**Suggestion:** Worth keeping an eye on. Not actionable yet.

### `pages.34_customer360` (SIZE_OUTLIER)

**Description:** Module is 3314 lines — above comfortable threshold of 2000
**Observed:** `3314`
**Threshold:** `2000`
**Suggestion:** Worth keeping an eye on. Not actionable yet.

### `utils.standards_registry` (SIZE_OUTLIER)

**Description:** Module is 3139 lines — above comfortable threshold of 2000
**Observed:** `3139`
**Threshold:** `2000`
**Suggestion:** Worth keeping an eye on. Not actionable yet.

### `pages.12_cascade` (SIZE_OUTLIER)

**Description:** Module is 2934 lines — above comfortable threshold of 2000
**Observed:** `2934`
**Threshold:** `2000`
**Suggestion:** Worth keeping an eye on. Not actionable yet.

### `pages.3_pipeline` (SIZE_OUTLIER)

**Description:** Module is 2029 lines — above comfortable threshold of 2000
**Observed:** `2029`
**Threshold:** `2000`
**Suggestion:** Worth keeping an eye on. Not actionable yet.
