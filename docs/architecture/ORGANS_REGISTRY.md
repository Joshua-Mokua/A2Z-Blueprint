# A2Z Blueprint MIS 360 — Organs Registry

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md`)
**Status:** `canonical_with_unknown_subareas`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 3)
**Last updated:** 2026-05-22
**Owner:** Architecture / Doctrine
**Authoritative source:** `utils/core.py` + `utils/*.py` inventory
**Machine-readable equivalent:** `ORGANS_REGISTRY.json`
**Companion artifact:** `CANONICAL_DEPENDENCY_MAP.md`

---

## Purpose

This document catalogs every **organ** in the A2Z system. An "organ" is a coherent unit of compute responsibility — a `Manager` class, an `_engine.py` module, or a tightly-coupled module family — with declared inputs, outputs, dependencies, and a contract.

Per SYSTEM_CONSTITUTION Article I §1.1: **the system is an organism**. Organs interconnect through a cross-organ event bus. Every state-changing decision flows through an organ. Code that doesn't belong to any organ is a violation.

This registry is the single source of truth for:
- What modules exist
- Which Manager owns which responsibility
- Which utility files belong to which functional domain
- Which directories remain `unknown` and require resolution
- The boundary between transports (Streamlit/FastAPI) and compute (engines)

---

## Doctrine

**O1 — Every module belongs to exactly one organ.** A module is owned by one functional domain. Cross-domain coordination happens through the event bus, not through cross-imports.

**O2 — Manager classes are the canonical interface to multi-record domain logic.** `UserManager`, `CascadeManager`, `PipelineManager`, etc. are the entry points for cross-record operations. Direct file reads from outside these classes are violations (per `CANONICAL_TRUTH_REGISTRY.md`).

**O3 — `_engine.py` modules are pure-compute single-purpose engines.** They take inputs (data structures, configs), produce outputs (computations, reports, scores), and have no transport awareness. They may import from `utils/core.py` Managers but not from `pages/` or FastAPI routes.

**O4 — `_audit.py` modules are read-only verifiers.** They produce reports comparing actual state to declared contracts. They never mutate state. The system's audit gate suite (`scripts/audit.py`) is the broader enforcement layer; these in-utils audit modules are the per-domain inspectors that gates may call.

**O5 — No anonymous modules.** Every `.py` file in `utils/` MUST be claimable by exactly one organ in this registry. Unknown modules are constitutional violations until classified.

---

## Inventory summary

| Surface | Count |
|---|---|
| `utils/core.py` Manager classes (canonical multi-record interfaces) | 15 |
| `utils/*.py` modules total | 527 |
| `utils/*/` subdirectories | 8 (currently `unknown`, see Section 10) |
| Files in `utils/` claimed by an organ in this registry | ~290 |
| Files awaiting explicit organ assignment in Wave 4-6 batches | ~237 |

The unclaimed count is high because (a) many modules are individually small but functionally peripheral (e.g. CIMS sub-modules, channels, propositions), and (b) Wave 3 prioritizes the load-bearing organs over the long tail. Subsequent waves will assign the remainder.

---

## Section 1 — Core Manager organs (`utils/core.py`)

The 15 Manager classes are the **primary canonical interfaces** for multi-record domain operations. Every Streamlit page and FastAPI endpoint that touches multi-record state goes through one of these.

| Manager | Line | Domain | Canonical method examples | Backing data |
|---|---|---|---|---|
| `LeaveManager` | 2356 | HR leave administration | `request_leave`, `approve`, `get_balance` | `data/hr_leave.json` (TBD) |
| `HRManager` | 2527 | HR staff lifecycle | `register`, `transfer`, `update_role`, `terminate` | `data/hr.json`, `data/staff_register.xlsx` |
| `CascadeManager` | 2798 | Target cascade BSC | `cascade_targets`, `walk_subordinates`, `compute_per_staff` | `data/target_cascade.json`, `data/bank_targets.json`, `data/locked_targets.json` |
| `ValidationManager` | 3688 | Cross-cutting validation | `validate_schema`, `validate_referential_integrity` | (in-memory; reads multiple JSON files) |
| `ReportingLineManager` | 3728 | Reporting chains | `get_chain_to_root`, `get_subordinates`, `is_manager_of` | `data/org_hierarchy_config.json` + `data/users.json` |
| `PipelineManager` | 3889 | CRM pipeline (deals) | `create_deal`, `move_stage`, `get_summary` | `data/pipeline.json`, `data/deal_rooms.json` |
| `ExecuteManager` | 4079 | Strategic initiatives | `create_initiative`, `update_milestone` | `data/strategic_initiatives.json`, `data/execute_*.json` |
| `ProductManager` | 4686 | Product catalog | `register_product`, `get_pricing` | `data/products.json` (TBD) |
| `RIPipelineManager` | 4810 | Relationship-intelligence pipeline | (similar to PipelineManager + RI scoring) | `data/ri_pipeline.json` |
| `LoanApplicationManager` | 5260 | Loan workflow | `submit_application`, `approve`, `decline` | `data/loan_applications.json` |
| `CreditAdminManager` | 5342 | Credit administration | `monitor_portfolio`, `flag_ews` | `data/credit_admin.json`, `data/credit_monitoring.json`, `data/ews_cases.json` |
| `ComplianceManager` | 5390 | Compliance | `flag_case`, `escalate`, `resolve` | `data/compliance_cases.json` |
| `TreasuryManager` | 5438 | Treasury | `record_position`, `compute_exposure` | `data/treasury_*.json` (6 files) |
| `UserManager` | 5626 | Users + auth | `authenticate`, `lookup`, `update_password`, `set_role` | `data/users.json` |
| `_BranchMgmtProxy` | 768 | Internal helper (proxy for branch-management role checks) | `__contains__`, `__iter__`, `__len__` | (in-memory derived from `org_hierarchy_config`) |

### Manager contract

Each Manager class follows this conventional shape (per `gate_core_split_adoption`):

```python
class XManager:
    def __init__(self):
        # Load backing data; cache structures; no transport assumptions
        ...

    # Read methods (no audit emit)
    def get_X(self, ...): ...
    def list_X(self, ...): ...

    # Write methods (must audit upstream OR the engine emits)
    def create_X(self, ...): ...
    def update_X(self, ...): ...

    # Audit methods
    def audit_X(self) -> Dict[str, Any]: ...
```

Critical convention: **Managers do NOT call `_audit()` directly**. The transport (FastAPI route handler or Streamlit page) is responsible for emitting audit events when state changes. This keeps Managers free of transport coupling.

---

## Section 2 — Authentication & user organs

Two-module organ family. See `CANONICAL_TRUTH_REGISTRY.md` for full pointers.

| Module | Role | Canonical interface | Classification |
|---|---|---|---|
| `utils/auth_jwt.py` | JWT mint/decode/blocklist, FastAPI Depends factories | `get_current_user`, `create_access_token`, `decode_token`, `revoke_token`, `_is_revoked`, `require_admin`, `require_role`, `warn_if_default_secret` | `canonical` |
| `utils/auth.py` | Streamlit page-access RBAC | `require_access`, `has_access`, `is_admin`, `get_current_user`, `check_access`, **`require_role` (alias — OI-1 collision)** | `transitional` (post OI-1 rename: `canonical` with `require_module_access`) |

### Cross-Manager helpers

- `utils/super_user_registry.py` — Super-user registry (data unknown; needs survey in next batch)
- `utils/data_isolation_guard.py` — Multi-tenant data isolation guard (unknown contract; survey pending)

---

## Section 3 — BSC organs (Balanced Scorecard)

11-module family + `CascadeManager` in core.py. The most complex domain in the system.

| Module | Responsibility |
|---|---|
| `utils/bsc_engine.py` | Primary BSC computation entry point; per-staff scoring |
| `utils/bsc_score_computation.py` | Pillar/KPI scoring math (fixed + cascaded + role-default fallback) |
| `utils/bsc_universal_contract.py` | Canonical contract: every staff has 4 pillars, weights sum to 1.0 |
| `utils/canonical_bsc_writer.py` | Single canonical write path to `data/bsc_data.json` |
| `utils/canonical_pbt_bsc_view.py` | PBT roll-up view per staff/branch/SBU |
| `utils/bsc_audit_engine.py` | BSC integrity verifier (consumed by `/api/v1/bsc-audit/*`) |
| `utils/bsc_pillar_normalize_engine.py` | Pillar value normalization migrations |
| `utils/bsc_library_register_engine.py` | KPI library registration enforcement |
| `utils/bsc_completeness_engine.py` | Staff coverage completeness checks |
| `utils/bsc_weight_normalize_engine.py` | Per-staff weight renormalization |
| `utils/bsc_cascade_actuals_engine.py` | Cascade actuals computation |
| `utils/bsc_cascade_linkage_engine.py` | Cascade ↔ BSC linkage verification |
| `utils/bsc_admin_panel.py` | Admin UI helpers (Streamlit) |

### Cascade sub-family (8 modules)

| Module | Responsibility |
|---|---|
| `utils/cascade_hierarchy.py` | Cascade walk down org tree |
| `utils/cascade_bsc_360_engine.py` | 360° cascade↔BSC harmony checks |
| `utils/cascade_bsc_harmonize_engine.py` | Cascade harmonization migrations (5 stages) |
| `utils/cascade_buffer_engine.py` | Buffer cap enforcement |
| `utils/cascade_health_engine.py` | Cascade health checks |
| `utils/cascade_regenerator.py` | Full cascade regeneration |
| `utils/cascade_retain_engine.py` | Selective retention during regeneration |
| `utils/cascade_structure_engine.py` | Cascade structural integrity |
| `utils/enhanced_cascade.py` | Enhanced cascade variants |

### Pillar sub-family (3 modules)

| Module | Responsibility |
|---|---|
| `utils/pillar_impact_engine.py` | Pillar impact computation |
| `utils/pillar_weights_canonical.py` | Canonical pillar weight definitions |
| `utils/pillar3_disclosure.py` | Basel Pillar 3 regulatory disclosure (separate from BSC pillars; namespace collision) |

### KPI sub-family (13 modules)

| Module | Responsibility |
|---|---|
| `utils/kpi_aggregation_rules.py` | Aggregation rule definitions |
| `utils/kpi_alias_resolver.py` | Canonical KPI ID resolution from aliases/short codes |
| `utils/kpi_dedup_engine.py` | KPI library dedup migration |
| `utils/kpi_ownership.py` | Which organ owns which KPI |
| `utils/kpi_ownership_pairing.py` | KPI pairing logic |
| `utils/core_kpi.py` | Core KPI helpers (re-export from core.py) |
| `utils/aggregation_rules_loader.py` | Rule loader |
| `utils/segment_kpi_library.py` | Segment-specific KPI library |
| `utils/cbk_regulatory_reporting.py` | Central Bank of Kenya reporting |
| `utils/regulatory_reporting.py` | Generic regulatory reporting |
| `utils/regulatory_returns.py` | Periodic regulatory returns |
| `utils/regulatory_revenue_reporting.py` | Revenue-specific regulatory |
| `utils/regulatory_change.py` | Regulatory change tracking |

---

## Section 4 — Role & org hierarchy organs (canonical foundation)

Per `ROLE_GOVERNANCE.md`, these are the canonical interfaces:

| Module | Responsibility | Classification |
|---|---|---|
| `utils/role_taxonomy.py` | **Canonical RBAC interface** (`classify_role`, `can_be_tagged`, etc.) | `canonical` |
| `utils/org_hierarchy_config.py` | Org config loader/validator | `canonical` |
| `utils/hierarchy_synth.py` | Hierarchy synthesizer (consumes `org_hierarchy_config.json`) | `canonical` |
| `utils/profitability_hierarchy.py` | Profitability axis hierarchy walker | `canonical` |
| `utils/cascade_hierarchy.py` | Cascade-aware hierarchy walker (overlap with BSC domain) | `canonical` |
| `utils/role_weight_engine.py` | Role weight computation (BSC pillar weights per role) | `canonical` |
| `utils/staff_role_resolver.py` | Resolve staff_code → role | `canonical` |
| `utils/staff_field_resolver.py` | Resolve staff_code → field values | `canonical` |
| `utils/staff_name_resolver.py` | Resolve staff_code → display name | `canonical` |

---

## Section 5 — Actuals engines (14 modules)

One actuals engine per major domain. Each consumes domain data and produces canonical KPI actuals.

| Module | Domain | Consumes |
|---|---|---|
| `utils/actuals_engine.py` | Generic dispatcher | All below |
| `utils/admin_actuals_engine.py` | Admin operations | `data/admin_*.json` |
| `utils/compliance_actuals_engine.py` | Compliance KPIs | `data/compliance_cases.json` |
| `utils/credit_actuals_engine.py` | Credit KPIs | `data/credit_*.json` |
| `utils/crm_actuals_engine.py` | CRM/Pipeline KPIs | `data/pipeline*.json` |
| `utils/finance_actuals_engine.py` | Finance KPIs | Finance ledgers, CBS |
| `utils/hr_actuals_engine.py` | HR KPIs | `data/hr*.json` |
| `utils/ict_actuals_engine.py` | ICT KPIs | ICT incident data |
| `utils/legal_actuals_engine.py` | Legal KPIs | `data/legal_*.json` |
| `utils/operations_actuals_engine.py` | Operations KPIs | Ops dashboards |
| `utils/reporting_analytics_actuals_engine.py` | Reporting analytics | Analytics outputs |
| `utils/risk_actuals_engine.py` | Risk KPIs | `data/risk_*.json` |
| `utils/treasury_actuals_engine.py` | Treasury KPIs | `data/treasury_*.json` |
| `utils/live_actuals.py` | Live actuals overlay (real-time refresh) | CBS + manual override |
| `utils/vb_actuals_bridge.py` | Virtual bank actuals bridge | CBS baseline |

---

## Section 6 — Risk & Compliance organs

### Market risk (5 modules)

| Module | Responsibility |
|---|---|
| `utils/market_risk.py` | Market risk umbrella |
| `utils/market_risk_factors.py` | RiskFactor enum (23 factors per v10.39) |
| `utils/market_risk_sensitivities.py` | DV01, FX delta, equity delta (BCBS d352 FRTB SBM) |
| `utils/market_risk_var.py` | Parametric / Historical / Monte Carlo VaR + ES + backtests |
| `utils/market_risk_limits.py` | 3 limit types, 4 severity bands |

### Operational & credit risk

| Module | Responsibility |
|---|---|
| `utils/operational_risk.py` | Op risk umbrella |
| `utils/op_risk.py` | Op risk helpers |
| `utils/liquidity_risk.py` | Liquidity risk |
| `utils/liquidity_stress.py` | Liquidity stress testing |
| `utils/credit_risk_irb.py` | Internal Ratings-Based credit risk |
| `utils/credit_risk_scoring.py` | Credit scoring |
| `utils/credit_alt_scoring.py` | Alternative credit scoring |
| `utils/risk_based_pricing.py` | Risk-based pricing |
| `utils/risk_weighted_assets.py` | RWA computation |
| `utils/rwa_optimization.py` | RWA optimization |
| `utils/irrbb.py` | Interest Rate Risk in Banking Book (BCBS d368) |
| `utils/stress_testing.py` | Stress test umbrella |
| `utils/stress_test_harness.py` | Stress test execution harness |

### Climate & ESG

| Module | Responsibility |
|---|---|
| `utils/climate_risk.py` | Climate risk |
| `utils/climate_ecl_adjustment.py` | IFRS9 ECL climate adjustments |
| `utils/climate_treasury_limits.py` | Climate-aware treasury limits |
| `utils/esg_intelligence.py` | ESG intelligence |
| `utils/esg_reporting.py` | ESG reporting |
| `utils/esg_reporting_outputs.py` | ESG report outputs |

### Compliance (11 modules)

| Module | Responsibility |
|---|---|
| `utils/aml_monitoring.py` | AML transaction monitoring |
| `utils/sanctions_screening.py` | Sanctions screening |
| `utils/screening_orchestrator.py` | Screening orchestration |
| `utils/sar_filing.py` | SAR filing |
| `utils/kyc_aml_risk.py` | KYC/AML risk |
| `utils/kyc_onboarding.py` | KYC onboarding |
| `utils/fatca_crs.py` | FATCA/CRS |
| `utils/transaction_monitoring.py` | TM rules |
| `utils/compliance_dashboard.py` | Compliance dashboard |
| `utils/compliance_risk_assessment.py` | Risk assessment |
| `utils/compliance_training.py` | Training tracking |

---

## Section 7 — Finance & Treasury organs

### Finance (close + statements + intelligence)

| Module | Responsibility |
|---|---|
| `utils/finance_close_orchestrator.py` | Close process orchestration |
| `utils/financial_close.py` | Close routines |
| `utils/financial_statement_generator.py` | F/S generation |
| `utils/financial_ratios_engine.py` | Ratio computation |
| `utils/finance_intelligence_dashboard.py` | Finance intelligence |
| `utils/finance_hub_render.py` | Finance hub UI |
| `utils/finance_audit_compliance.py` | Finance audit |
| `utils/predictive_financial_analytics.py` | Predictive financial analytics |
| `utils/management_reporting.py` | Management reporting |
| `utils/board_reporting.py` | Board reporting |
| `utils/examiner_reporting.py` | Examiner-facing reporting |
| `utils/regulatory_reporting.py` | (already listed under KPI) |
| `utils/consolidated_tb_engine.py` | Consolidated trial balance |
| `utils/group_consolidation.py` | Group consolidation |
| `utils/group_exposure.py` | Group exposure tracking |
| `utils/intercompany_matching.py` | Intercompany matching |

### IFRS / GAAP

| Module | Responsibility |
|---|---|
| `utils/ifrs9_classification.py` | IFRS 9 classification |
| `utils/ifrs7_disclosures.py` | IFRS 7 disclosures |
| `utils/ias1_presentation.py` | IAS 1 presentation |
| `utils/ias8_policies.py` | IAS 8 accounting policies |
| `utils/asset_impairment.py` | Asset impairment |
| `utils/deferred_tax.py` | Deferred tax |
| `utils/earnings_per_share.py` | EPS |
| `utils/revenue_recognition.py` | Revenue recognition |
| `utils/lease_accounting.py` | Lease accounting (IFRS 16) |
| `utils/held_for_sale.py` | Held for sale |
| `utils/cash_flow_statement.py` | Cash flow statement |
| `utils/operating_segments.py` | Operating segments |
| `utils/fair_value_measurement.py` | Fair value |
| `utils/provisions.py` | Provisions |
| `utils/related_party.py` | Related party |
| `utils/multi_entity_currency.py` | Multi-entity FX |

### Treasury (13+ modules)

| Module | Responsibility |
|---|---|
| `utils/treasury_alm.py` | Asset/Liability Management |
| `utils/treasury_dashboard.py` | Treasury dashboard |
| `utils/treasury_dashboard_wiring.py` | Dashboard wiring |
| `utils/treasury_intelligence.py` | Treasury intelligence |
| `utils/treasury_products.py` | Treasury products |
| `utils/treasury_connectivity.py` | Connectivity |
| `utils/treasury_digital_assets.py` | Digital assets |
| `utils/treasury_unified_platform.py` | Unified platform |
| `utils/treasury_agents.py` | Treasury agents |
| `utils/cash_forecasting.py` | Cash forecasting |
| `utils/cash_forecast_wiring.py` | Forecast wiring |
| `utils/funds_transfer_pricing.py` | FTP |
| `utils/fund_transfer_pricing.py` | FTP variant |
| `utils/fx_position.py` | FX positions |
| `utils/benchmark_rates.py` | Benchmark rates |
| `utils/islamic_treasury.py` | Islamic banking treasury |
| `utils/trading_book_boundary.py` | Trading vs banking book |
| `utils/investment_portfolio.py` | Investment portfolio |

### PBT / Profitability

| Module | Responsibility |
|---|---|
| `utils/pbt_computation.py` | PBT computation |
| `utils/branch_pbt_allocator.py` | Branch PBT allocation |
| `utils/customer_pbt_allocator.py` | Customer PBT allocation |
| `utils/customer_profitability.py` | Customer profitability |
| `utils/product_profitability.py` | Product profitability |
| `utils/product_pnl_intelligence.py` | Product P&L intelligence |
| `utils/product_raroc.py` | Product RAROC |
| `utils/profitability_heatmap.py` | Profitability heatmap |
| `utils/profitability_hierarchy.py` | (already listed) |
| `utils/profitability_integration.py` | Profitability integration |
| `utils/profitability_reconciliation.py` | Reconciliation |
| `utils/profitability_trends.py` | Trends |
| `utils/sbu_pnl_rollup.py` | SBU P&L rollup |
| `utils/rm_profitability.py` | RM profitability |
| `utils/segment_pnl_attribution.py` | Segment P&L attribution |

---

## Section 8 — Customer & Commercial organs

### Customer (9 modules)

| Module | Responsibility |
|---|---|
| `utils/customer_master_canonical.py` | Customer master record |
| `utils/customer_segmentation.py` | Segmentation |
| `utils/customer_value_segments.py` | Value segments |
| `utils/customer_lifetime_value.py` | CLV |
| `utils/customer_needs_analyzer.py` | Needs analysis |
| `utils/customer_behavioral_profile.py` | Behavioral profile |
| `utils/customer_pbt_allocator.py` | (already listed) |
| `utils/customer_profitability.py` | (already listed) |
| `utils/churn_prediction.py` | Churn prediction (ML) |
| `utils/decline_prediction.py` | Decline prediction (ML) |
| `utils/dormancy_intelligence.py` | Dormancy intelligence |
| `utils/dynamic_cohorts.py` | Dynamic cohorts |

### Segment (8 modules)

| Module | Responsibility |
|---|---|
| `utils/segment_classifier.py` | Segment classification |
| `utils/segment_kpi_library.py` | (already listed) |
| `utils/segment_propositions.py` | Segment propositions |
| `utils/segment_pnl_attribution.py` | (already listed) |
| `utils/segment_balance_sheet.py` | Segment B/S |
| `utils/segment_behavioral_insights.py` | Behavioral insights |
| `utils/segment_dashboards.py` | Segment dashboards |
| `utils/segment_manager_role.py` | Segment manager role mapping |
| `utils/specialized_segments_tagging.py` | Specialized segment tagging |

### Proposition (10 modules)

| Module | Responsibility |
|---|---|
| `utils/propositions_catalog.py` | Catalog |
| `utils/propositions_orchestration.py` | Orchestration |
| `utils/propositions_eligibility.py` | Eligibility |
| `utils/propositions_pricing.py` | Pricing |
| `utils/propositions_presentation.py` | Presentation |
| `utils/propositions_analytics.py` | Analytics |
| `utils/propositions_ab_testing.py` | A/B testing |
| `utils/propositions_hub_render.py` | Hub UI |
| `utils/proposition_activity_generator.py` | Activity gen |

### Campaigns (8 modules)

| Module | Responsibility |
|---|---|
| `utils/campaigns_catalog.py` | Catalog |
| `utils/campaigns_orchestration.py` | Orchestration |
| `utils/campaigns_personalization.py` | Personalization |
| `utils/campaigns_triggers.py` | Triggers |
| `utils/campaigns_ab_testing.py` | A/B testing |
| `utils/campaigns_attribution.py` | Attribution |
| `utils/campaigns_performance.py` | Performance |
| `utils/campaigns_journey_integration.py` | Journey integration |

### Partnerships (7 modules)

| Module | Responsibility |
|---|---|
| `utils/partner_master.py` | Partner master |
| `utils/partner_onboarding.py` | Onboarding |
| `utils/partner_scorecard.py` | Scorecard |
| `utils/partner_risk_and_kpis.py` | Risk & KPIs |
| `utils/partner_portal_and_analytics.py` | Portal & analytics |
| `utils/partner_leads_commissions.py` | Leads & commissions |
| `utils/partner_supplier_recon.py` | Supplier recon |

### Insurance (Bancassurance, 7 modules)

| Module | Responsibility |
|---|---|
| `utils/insurance_catalog.py` | Insurance catalog |
| `utils/insurance_claims.py` | Claims |
| `utils/insurance_recommendation.py` | Recommendation |
| `utils/insurance_ira_compliance.py` | IRA compliance (Kenya) |
| `utils/insurance_commission_recon.py` | Commission recon |
| `utils/insurance_partner_hub.py` | Partner hub |
| `utils/insurance_customer_rm_desktop.py` | Customer RM desktop |

### Trade Finance (11 modules)

| Module | Responsibility |
|---|---|
| `utils/trade_finance_accounting.py` | Accounting |
| `utils/trade_finance_compliance.py` | Compliance |
| `utils/trade_finance_connectivity.py` | Connectivity |
| `utils/trade_finance_corporate_portal.py` | Corporate portal |
| `utils/trade_finance_document_checking.py` | Document checking |
| `utils/trade_finance_instruments.py` | Instruments |
| `utils/trade_finance_limits.py` | Limits |
| `utils/trade_finance_mobile.py` | Mobile |
| `utils/trade_finance_reporting.py` | Reporting |
| `utils/trade_finance_sustainability.py` | Sustainability |
| `utils/trade_finance_swift.py` | SWIFT integration |

---

## Section 9 — CIMS organs (Customer Information Management System, 15 modules)

| Module | Responsibility |
|---|---|
| `utils/cims_agent_workspace.py` | Agent workspace |
| `utils/cims_analytics_dashboard.py` | Analytics dashboard |
| `utils/cims_audit_ready_history.py` | Audit history |
| `utils/cims_completion_feedback.py` | Completion feedback |
| `utils/cims_dropout_prevention.py` | Dropout prevention |
| `utils/cims_exception_management.py` | Exception management |
| `utils/cims_next_best_action.py` | Next best action |
| `utils/cims_nlp_classification.py` | NLP classification |
| `utils/cims_omnichannel_capture.py` | Omnichannel capture |
| `utils/cims_process_intelligence.py` | Process intelligence |
| `utils/cims_regulatory_sla.py` | Regulatory SLA |
| `utils/cims_secure_pan_documents.py` | Secure PAN documents |
| `utils/cims_self_service_portal.py` | Self-service portal |
| `utils/cims_stp_engine.py` | Straight-through processing |
| `utils/cims_unified_identity.py` | Unified identity |

---

## Section 10 — Unknown subdirectories (8)

These 8 subdirectories appear in `utils/` but their contents and contracts were not surveyed in Stage A. They remain `unknown` per `GOVERNANCE_CLASSIFICATION_REGISTRY.md::G5` and must transition to a real state within 1 batch.

| Subdirectory | Hypothesized purpose | Resolution wave |
|---|---|---|
| `utils/agents/` | AI agent definitions (treasury_agents, etc.) | Wave 5 AI_GOVERNANCE |
| `utils/arena/` | Training arena (per `gate_v10485_o7a_training_arena`) | Wave 5 RESILIENCE_AND_CERTIFICATION_GOVERNANCE |
| `utils/cert/` | Certification artifacts | Wave 5 RESILIENCE_AND_CERTIFICATION_GOVERNANCE |
| `utils/channels/` | Channel-specific modules (separate from top-level channel_*.py) | Wave 4 DATA_DICTIONARY context |
| `utils/chaos/` | Chaos engineering (per `gate_v10482_o5_chaos_engineering`) | Wave 5 RESILIENCE_AND_CERTIFICATION_GOVERNANCE |
| `utils/ml/` | ML model definitions | Wave 5 AI_GOVERNANCE |
| `utils/scenarios/` | Scenario library | Wave 5 DIGITAL_TWIN_ARCHITECTURE |
| `utils/uncertainty/` | Uncertainty exposure phases (per `gate_v10489-v10494`) | Wave 5 RESILIENCE_AND_CERTIFICATION_GOVERNANCE |

**Resolution command for follow-up:**

```
dir utils\agents /b > docs\architecture\survey_inputs\subdir_agents.txt
dir utils\arena /b > docs\architecture\survey_inputs\subdir_arena.txt
dir utils\cert /b > docs\architecture\survey_inputs\subdir_cert.txt
dir utils\channels /b > docs\architecture\survey_inputs\subdir_channels.txt
dir utils\chaos /b > docs\architecture\survey_inputs\subdir_chaos.txt
dir utils\ml /b > docs\architecture\survey_inputs\subdir_ml.txt
dir utils\scenarios /b > docs\architecture\survey_inputs\subdir_scenarios.txt
dir utils\uncertainty /b > docs\architecture\survey_inputs\subdir_uncertainty.txt
```

Upload these 8 files when resolving each subdirectory in its target wave.

---

## Section 11 — Mounted API routers (10 modules awaiting verification)

Per `API_CONTRACTS.md`, three routers are confirmed mounted in `utils/api.py` startup. The following 10 modules exist as router files but their mount status was not visible in extracted signatures:

| Module | Status | Verification needed |
|---|---|---|
| `utils/api_cockpit.py` | mount status unknown | Look for `app.include_router(api_cockpit.router)` in api.py |
| `utils/api_compliance.py` | mount status unknown | Same |
| `utils/api_legal.py` | mount status unknown | Same |
| `utils/api_telemetry.py` | mount status unknown | Same |
| `utils/api_treasury.py` | mount status unknown | Same |
| `utils/api_strategy.py` | mount status unknown | Same |
| `utils/api_product.py` | mount status unknown | Same |
| `utils/api_resource_optimization.py` | mount status unknown | Same |
| `utils/api_crud.py` | mount status unknown | Same |
| `utils/api_gateway_developer_portal.py` | mount status unknown | Same |

Resolution: in a follow-up batch, run:

```
findstr /n "app.include_router" utils\api.py
```

This produces the canonical mount manifest.

---

## Section 12 — Frontend organs (post v10.497 P0)

### React frontend (`frontend/web/`)

| Surface | Files | Status |
|---|---|---|
| Design tokens | `src/lib/tokens.ts` | `canonical` |
| Class composition | `src/lib/cn.ts` | `canonical` |
| API client | `src/lib/api.ts` | `canonical` |
| shadcn primitives | `src/components/ui/*` (11 files: button, badge, card, input, label, alert, skeleton, table, dialog, form, sonner) | `canonical` |
| A2Z compositions | `src/components/StatCard.tsx` | `canonical` |
| Branding | `src/providers/BrandingProvider.tsx` | `canonical` |
| Auth (future) | `src/providers/AuthProvider.tsx` | `transitional` (v10.497 Phase 2) |
| Pages | `src/pages/*.tsx` (Dashboard, Showcase + others) | `canonical` for delivered, full enumeration in Wave 4 FRONTEND_GOVERNANCE |
| App shell | `src/App.tsx` | `canonical` |
| CSS variables | `src/index.css` | `derived` from tokens.ts |
| Tailwind config | `tailwind.config.js` | `canonical` |
| shadcn config | `components.json` | `canonical` |

### Streamlit pages (`pages/*.py`)

158 pages declared in Master Prompt v5.40. Full enumeration with per-page RBAC mapping is OI-13, scheduled for follow-up batch.

Known canonical pages (from session memory):

| Page | Module |
|---|---|
| `pages/1_perform.py` | BSC scorecard |
| `pages/3_pipeline.py` | CRM pipeline |
| `pages/7_admin.py` | Admin + KPI Library |
| `pages/12_cascade.py` | Target cascade |
| `pages/15_cbs.py` | CBS explorer |

Plus `app.py` entry point with `_APP_VERSION` stamp (manager cache invalidation on code update).

---

## Section 13 — Audit & telemetry organs

### Audit gates (the enforcer)

- `scripts/audit.py` — single canonical gate registry, 412 gates, see `CANONICAL_TRUTH_REGISTRY.md::audit_gates_the_enforcer`

### In-utils audit modules

| Module | Responsibility |
|---|---|
| `utils/audit_log.py` | Audit log writer |
| `utils/audit_core.py` | Audit core helpers |
| `utils/audit_universe.py` | Audit universe definitions |
| `utils/audit_dashboards_portal.py` | Audit dashboards |
| `utils/audit_reporting.py` | Audit reporting |
| `utils/audit_analytics_vendor.py` | Audit analytics vendor integration |
| `utils/audit_controls_issues.py` | Controls issue tracking |
| `utils/audit_trail_cert.py` | Audit trail certification (TBD vs `audit_trail_certification`) |
| `utils/audit_trail_certification.py` | Audit trail certification (canonical?) |
| `utils/bsc_audit_engine.py` | (already listed under BSC) |
| `utils/hr_section_audit_engine.py` | HR section audit |
| `utils/credit_doctrine_audit.py` | Credit doctrine audit |
| `utils/credit_section_audit_engine.py` | Credit section audit |
| `utils/standards_wiring_audit_engine.py` | Standards wiring audit |
| `utils/standards_wiring_per_module.py` | Standards wiring per module |
| `utils/admin_validation_engine.py` | Admin validation engine |
| `utils/module_doctrine_audit.py` | Module doctrine audit |
| `utils/structure_audit_core.py` | Structure audit (G128 baseline) |
| `utils/enterprise_discharge_audit.py` | Enterprise discharge audit |

### Telemetry & event bus

| Module | Responsibility |
|---|---|
| `utils/api_telemetry.py` | API telemetry router |
| `utils/observability_monitoring.py` | Observability |
| `utils/anomaly_observer.py` | Anomaly observation |
| `utils/analytics_anomaly_detection.py` | Anomaly detection |
| `utils/event_bus.py` | Event bus |
| `utils/cross_organ_event_bus.py` | Cross-organ event bus |
| `utils/notification_broadcaster.py` | Notification broadcaster |
| `utils/notifications.py` | Notifications |
| `utils/nudge_engine.py` | Nudge engine |
| `utils/smart_alerts.py` | Smart alerts |
| `utils/smart_alerts_i18n.py` | i18n smart alerts |

Full telemetry contract: Wave 4 `TELEMETRY_MAP.md`.

---

## Section 14 — System administration organs

| Module | Responsibility |
|---|---|
| `utils/admin_registry.py` | Admin registry |
| `utils/admin_actuals_engine.py` | (already listed) |
| `utils/admin_validation_engine.py` | (already listed) |
| `utils/canonical_admin.py` | Canonical admin operations |
| `utils/super_user_registry.py` | Super-user registry |
| `utils/backup_retention_engine.py` | Backup retention |
| `utils/test_cleanup_engine.py` | Test cleanup |
| `utils/data_migration.py` | Data migration |
| `utils/data_isolation_guard.py` | Multi-tenant isolation |
| `utils/schema_validator.py` | Schema validator |
| `utils/static_check.py` | Static code checks |
| `utils/dynamic_smoke.py` | Dynamic smoke tests |
| `utils/page_smoke.py` | Page smoke tests |
| `utils/page_access.py` | Streamlit page access helpers |
| `utils/page_manifest_loader.py` | Page manifest loader |
| `utils/page_shared.py` | Shared page utilities |
| `utils/page_cockpit_render.py` | Cockpit rendering |
| `utils/older_logic_scanner.py` | Older logic scanner |
| `utils/module_consolidation_analyzer.py` | Module consolidation analyzer |
| `utils/module_doc_generator.py` | Module doc generator |
| `utils/work_mode_declaration.py` | Work mode declaration |
| `utils/standards_registry.py` | Standards registry |

---

## Section 15 — Virtual bank / digital twin organs (8 modules)

See `CANONICAL_TRUTH_REGISTRY.md::digital_twin_simulation`. Wave 5 will produce dedicated `DIGITAL_TWIN_ARCHITECTURE.md`.

| Module | Responsibility |
|---|---|
| `utils/virtual_bank.py` | Virtual bank umbrella |
| `utils/virtual_bank_core.py` | Core |
| `utils/virtual_bank_cbs_writer.py` | CBS writer |
| `utils/virtual_bank_kpi_unifier.py` | KPI unifier |
| `utils/virtual_bank_readiness.py` | Readiness |
| `utils/virtual_bank_seed.py` | Deterministic seed |
| `utils/virtual_bank_simulator.py` | Simulator |
| `utils/vb_actuals_bridge.py` | (already listed) |
| `utils/cbs_baseline.py` | CBS baseline computation |
| `utils/simulation_clock.py` | Simulation clock |
| `utils/scenario_simulator.py` | Scenario simulator |
| `utils/target_scenario_simulator.py` | Target scenario simulator |
| `utils/hybrid_scheduling_simulator.py` | Hybrid scheduling simulator |
| `utils/strategy_simulator.py` | Strategy simulator |
| `utils/macro_state.py` | Macro state |
| `utils/macro_calendar.py` | Macro calendar |
| `utils/macro_bridge.py` | Macro bridge |
| `utils/macro_evolution.py` | Macro evolution |

---

## Section 16 — AI / ML organs

See `CANONICAL_TRUTH_REGISTRY.md::ai_ml_governance`. Wave 5 will produce dedicated `AI_GOVERNANCE.md`.

| Module | Responsibility |
|---|---|
| `utils/model_governance.py` | Model governance |
| `utils/model_governance_runtime.py` | Runtime governance |
| `utils/mlops_model_registry.py` | Model registry |
| `utils/mlops_model_card_composer.py` | Model card composer |
| `utils/mlops_adjudication_log.py` | Adjudication log |
| `utils/mlops_ab_harness.py` | A/B harness |
| `utils/mlops_persistence.py` | Persistence |
| `utils/mlops_retraining_scheduler.py` | Retraining scheduler |
| `utils/ai_explainability.py` | Explainability |
| `utils/ai_underwriting.py` | AI underwriting |
| `utils/fairness_testing.py` | Fairness testing |
| `utils/cross_sell_bandit.py` | Cross-sell bandit (RL) |
| `utils/cross_sell_nba.py` | Cross-sell next best action |
| `utils/predictive_performance.py` | Predictive performance |
| `utils/behavioral_anomaly_detection.py` | Behavioral anomaly |

---

## Section 17 — Resilience & certification organs

See `CANONICAL_TRUTH_REGISTRY.md::resilience_and_certification`. Wave 5 will produce dedicated `RESILIENCE_AND_CERTIFICATION_GOVERNANCE.md`.

| Module | Responsibility |
|---|---|
| `utils/disaster_recovery.py` | DR |
| `utils/it_disaster_recovery.py` | IT DR |
| `utils/it_cicd.py` | CI/CD |
| `utils/scalability_validator.py` | Scalability |
| `utils/audit_trail_certification.py` | (already listed) |
| `utils/enterprise_discharge_audit.py` | (already listed) |
| `utils/body_health_engine.py` | Body health engine |
| `utils/system_invariants.py` | System invariants |
| `utils/system_flows.py` | System flows |
| `utils/system_stocks.py` | System stocks |

---

## Section 18 — Strategic & command organs

### Strategy

| Module | Responsibility |
|---|---|
| `utils/strategic_planning.py` | Planning |
| `utils/strategic_options.py` | Options |
| `utils/strategic_response.py` | Response |
| `utils/strategy_formulation.py` | Formulation |
| `utils/strategy_decomposition.py` | Decomposition |
| `utils/strategy_communication.py` | Communication |
| `utils/strategy_summaries.py` | Summaries |
| `utils/strategy_health.py` | Health |
| `utils/strategy_learning.py` | Learning |
| `utils/strategy_roi.py` | ROI |
| `utils/strategy_simulator.py` | (already listed) |
| `utils/daily_strategy_integration.py` | Daily integration |

### Command Centre

| Module | Responsibility |
|---|---|
| `utils/command_centre_alert_routing.py` | Alert routing |
| `utils/command_centre_crisis.py` | Crisis |
| `utils/command_centre_dashboard.py` | Dashboard |
| `utils/command_centre_forecasting.py` | Forecasting |
| `utils/command_centre_mobile_board.py` | Mobile board |
| `utils/command_centre_nl_query.py` | NL query |
| `utils/command_centre_stakeholder_comms.py` | Stakeholder comms |
| `utils/command_centre_strategic_initiatives.py` | Initiatives |

### Initiative tracking

| Module | Responsibility |
|---|---|
| `utils/initiative_dependency.py` | Dependency |
| `utils/initiative_impact.py` | Impact |
| `utils/initiative_portfolio.py` | Portfolio |
| `utils/initiative_resource.py` | Resource |
| `utils/stage_gate.py` | Stage gate |

---

## Section 19 — SLA, channels, branch operations

### SLA (10 modules)

`utils/sla_analytics.py`, `sla_breach.py`, `sla_calendar.py`, `sla_dashboard.py`, `sla_early_warning.py`, `sla_monitoring.py`, `sla_registry.py`, `sla_reporting.py`, `sla_vendor_scorecard.py`, `sla_bsc_integration.py`

### Channels (6 + sub-dir)

`utils/channel_income.py`, `channel_performance.py`, `channel_sla.py`, `channels_reliability.py`, `cross_channel_balancing.py` + `utils/channels/` subdir (unknown)

### Branch operations

`utils/branch_interaction.py`, `branch_manager_generator.py`, `branch_ops_excellence.py`, `branch_pbt_allocator.py`, `branch_performance.py`, `branch_staff_generator.py`, `teller_actions.py`, `teller_activity_generator.py`, `specialist_activity_generator.py`, `support_function_generator.py`, `credit_activity_generator.py`

---

## Section 20 — IT / Cloud / Infrastructure

`utils/it_api_gateway.py`, `it_cbk_compliance.py`, `it_cicd.py`, `it_cloud_architecture.py`, `it_data_encryption.py`, `it_digital_banking.py`, `it_disaster_recovery.py`, `it_itsm.py`, `it_multi_tenancy.py`, `it_observability.py`, `cloud_native_architecture.py`, `itsm_framework.py`

---

## Section 21 — Performance / HR (peer learning, gamification, wellness)

`utils/performance_insights.py`, `performance_talent.py`, `predictive_performance.py`, `peer_learning.py`, `coaching_intelligence.py`, `growth_path_engine.py`, `microtask_engine.py`, `gamification.py`, `wellness.py`, `wellbeing_integration.py`, `employee_engagement.py`, `employee_benefits.py`, `compensation_equity.py`, `workforce_analytics.py`, `workload_forecasting.py`, `staff_exit_engine.py`, `staff_onboarding_engine.py`, `onboarding_optimization.py`, `integrity_culture.py`, `executive_resource_dashboard.py`

---

## Section 22 — Flexcube integration

`utils/flexcube_adapter.py`, `flexcube_aggregator.py`, `flexcube_connection.py`, `flexcube_etl_dag.py`, `flexcube_integration_readiness.py`, `flexcube_mappings.py`, `flexcube_staging.py`

---

## Section 23 — Reconciliation organs

`utils/reconciliation.py`, `reconciliation_engine.py`, `reconciliation_matching.py`, `reconciliation_realtime.py`, `reconciliation_specialized.py`, `reconciliation_workflow.py`

---

## Section 24 — Competitive intelligence

`utils/competitive_alerts.py`, `competitive_gap_analysis.py`, `competitive_intel_api.py`, `competitive_radar.py`, `competitor_data_collection.py`, `competitor_digital_intel.py`, `competitor_hub_render.py`, `competitor_rates.py`, `product_competitive_intel.py`

---

## Section 25 — Legal organs

`utils/legal_analytics.py`, `legal_case_management.py`, `legal_dashboard.py`, `legal_document_management.py`, `legal_hold_management.py`, `legal_spend_management.py`, `legal_actuals_engine.py`, `clause_library.py`, `contract_management.py`, `outside_counsel_portal.py`, `obligation_tracking.py`, `submission_workflow.py`

---

## Section 26 — Long-tail organs (single-purpose modules)

Modules not yet categorized in a domain section above. These represent the long tail and will be progressively absorbed into domain sections in subsequent waves:

`utils/business_intelligence.py`, `revenue_orchestrator.py`, `revenue_dashboard_metrics.py`, `revenue_anomaly_patterns.py`, `revenue_validation.py`, `revenue_recognition.py`, `accruals_synthesizer.py`, `bank_targets_schema.py`, `applicant_data_sources.py`, `allocation_optimizer.py`, `composite_scores.py`, `commission_assurance.py`, `continuous_billing_verification.py`, `corrective_actions.py`, `cost_allocation.py`, `cockpit_read.py`, `live_cockpit_render.py`, `platform_hub_render.py`, `journey_optimization.py`, `journey_and_widget.py`, `mobile_app_tracking.py`, `cards.py`, `db.py`, `config.py`, `config_v10495_append.py`, `environment.py`, `manager_rollup.py`, `period_harmonizer.py`, `tick_scheduler.py`, `policy_management.py`, `gap_analyzer.py`, `analytics_credit_workbench.py`, `analytics_data_export.py`, `analytics_nlq.py`, `analytics_scheduled_reports.py`, `dynamic_pricing.py`, `deposit_intelligence.py`, `lending_intelligence.py`, `product_ranking.py`, `product_recommendation.py`, `product_bundling.py`, `product_lifecycle.py`, `product_cvp_builder.py`, `product_analytics_dashboard.py`, `interaction_capture.py`, `interface_routing.py`, `operations_dashboard.py`, `operational_heatmap.py`, `queue_analytics.py`, `workflow_engine.py`, `workflow_replay.py`, `transaction_lineage.py`, `state_backend.py`, `stakeholder_engagement.py`, `tax_compliance.py`, `kra_tax_compliance.py`, `procurement_workflow.py`, `vendor_risk.py`, `internal_controls.py`, `issue_management.py`, `edms.py`, `document_management.py`, `pillar3_disclosure.py`, `pipeline_to_bsc.py`, `products_to_bsc.py`, `rm_behavior_intelligence.py`, `resource_investment_case.py`, `sto_toolkit.py`, `tsl_optimization.py`, `websocket_manager.py`, `predictive_performance.py`, `utilization_dashboard.py`, `older_logic_scanner.py`, `model_governance.py`, `model_governance_runtime.py`

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-13 | Streamlit page list enumeration with per-page RBAC | Follow-up batch |
| OI-14 | Verify mount status of 10 router modules | Immediate (one findstr) |
| OI-16 | Resolve 8 utils subdirectories | Wave 5 (per subdir target wave column) |
| OI-17 | Classify ~237 modules currently in long-tail (Section 26) | Waves 4-6 progressively |
| OI-18 | Disambiguate `audit_trail_cert.py` vs `audit_trail_certification.py` (potential duplicate) | Wave 5 RESILIENCE |

---

**End of ORGANS_REGISTRY.md**
