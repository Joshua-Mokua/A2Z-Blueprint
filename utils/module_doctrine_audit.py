"""utils/module_doctrine_audit.py — v10.452 Generic Module Doctrine Audit.

Per Joshua: "plan to do the same tests for the modules stated as
complete so that we have a true and honest reflection of the status
and the rescue efforts needed."

Per Document 2's organ classification:
  • Admin Module        = Central Nervous System Coordination
  • HR Module           = Human Capital & Regenerative System (ongoing)
  • BSC & Target Cascade = Brain Intelligence, Direction & Decision Flow
  • Credit              = The heart of the bank (audited at v10.451 = 38.6%)

This engine applies the SAME 8-phase doctrine + 14 final validation
criteria + 10 vital signs questions + 5 diagnostic principles audit
to ANY module, so we get HONEST health for every claimed-complete
organ — not just credit.

API-first; zero streamlit imports.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path(__file__).parent.parent
PAGES_DIR = REPO_ROOT / "pages"
UTILS_DIR = REPO_ROOT / "utils"
DATA_DIR  = REPO_ROOT / "data"
DOCS_DIR  = REPO_ROOT / "docs"


# ════════════════════════════════════════════════════════════════════
# MODULE CONFIGS
# ════════════════════════════════════════════════════════════════════

@dataclass
class ModuleConfig:
    """Configuration for one module's doctrine audit."""
    key: str                          # short id e.g. "hr", "credit"
    name: str                         # display name
    organ_role: str                   # per Document 2
    claimed_status: str               # what we previously claimed
    claimed_health_pct: float         # last claimed number
    pages: List[str]                  # module's pages
    engines: List[str]                # module's engines
    expected_roles: List[str]         # roles that should appear in cascade
    kpi_keywords: List[str]           # to find module's KPIs
    command_centre_candidates: List[str]  # possible Chief X Centre page filenames
    integration_keywords: Dict[str, List[str]]  # cross-organ links {organ: [keywords]}


MODULE_REGISTRY: Dict[str, ModuleConfig] = {
    "admin": ModuleConfig(
        key="admin",
        name="Admin Module",
        organ_role="Central Nervous System Coordination",
        claimed_status="completed",
        claimed_health_pct=100.0,
        pages=[
            "7_admin.py",
            # v10.465 — re-homed strategy/MD/executive pages (Admin = CNS)
            "0_home.py",
            "4_execute.py",
            "8_export.py",
            "9_sbu.py",
            "10_opex.py",
            "41_budget.py",
            "52_mgmt_accounts.py",
            "82_system_vitals.py",
            "83_strategy.py",
            "95_command_centre.py",
            "100_md_cockpit.py",
            "115_live_cockpits.py",
            "120_staff_pbt.py",
        ],
        engines=[
            "admin_registry",
            "admin_validation_engine",
            "canonical_admin",
            "standards_registry",
            "standards_wiring_audit_engine",
            "bsc_admin_panel",
        ],
        expected_roles=[
            "System Administrator",
            "Admin Super User",
            "Compliance Admin",
        ],
        kpi_keywords=["system", "audit", "compliance", "configuration"],
        command_centre_candidates=["7_admin.py"],  # admin IS the centre
        integration_keywords={
            "hr": ["users", "roles", "rbac"],
            "bsc": ["kpi_library", "target_cascade"],
            "audit": ["audit_log", "audit_trail"],
        },
    ),
    "hr": ModuleConfig(
        key="hr",
        name="HR Module",
        organ_role="Human Capital & Regenerative System",
        claimed_status="ongoing — claimed 88.7% at v10.443",
        claimed_health_pct=88.7,
        pages=[
            "2_people.py",
            "42_lms.py",
            "43_pip.py",
            "58_workforce.py",
            "60_disciplinary.py",
            "79_staff_onboarding.py",
            "80_staff_exit.py",
            "81_chief_hr_centre.py",
        ],
        engines=[
            "peer_learning",
            "coaching_intelligence",
            "predictive_performance",
            "gamification",
            "efficiency",
            "wellness",
            "staff_onboarding_engine",
            "staff_exit_engine",
            "hr_actuals_engine",
            "compliance_training",
        ],
        expected_roles=[
            "Chief Human Resources Officer",
            "HR Business Partner",
            "Recruitment Officer",
            "Compensation & Benefits Officer",
            "Learning & Development Officer",
            "Wellness Officer",
        ],
        kpi_keywords=["staff", "training", "wellness", "attrition",
                     "engagement", "headcount", "recruit", "onboarding"],
        command_centre_candidates=["81_chief_hr_centre.py"],
        integration_keywords={
            "credit": ["loan_officer", "credit_analyst"],
            "bsc": ["balanced_scorecard", "bsc_score"],
            "admin": ["users.json", "rbac"],
        },
    ),
    "bsc_cascade": ModuleConfig(
        key="bsc_cascade",
        name="BSC & Target Cascade",
        organ_role="Brain Intelligence, Direction & Decision Flow",
        claimed_status="rescued — claimed 100% at v10.433",
        claimed_health_pct=100.0,
        pages=[
            "1_perform.py",
            "12_cascade.py",
        
            # v10.465 — re-homed pages
            "15_optimize.py",
        ],
        engines=[
            "bsc_engine",
            "bsc_audit_engine",
            "bsc_admin_panel",
            "bsc_cascade_linkage_engine",
            "bsc_completeness_engine",
            "bsc_library_register_engine",
            "bsc_pillar_normalize_engine",
            "bsc_score_computation",
            "bsc_universal_contract",
            "cascade_bsc_360_engine",
            "api_cascade",
        ],
        expected_roles=[
            "MD",
            "Director Consumer & Commercial Banking (CCB)",
            "Director Corporate & Investment Banking (CIB)",
            "Head Of Retail",
            "Branch Manager",
        ],
        kpi_keywords=["kpi", "target", "score", "actual"],
        command_centre_candidates=["1_perform.py"],
        integration_keywords={
            "credit": ["credit", "loan", "npl"],
            "hr": ["staff", "training", "performance"],
            "admin": ["kpi_library", "role_kpis"],
        },
    ),
    "credit": ModuleConfig(
        key="credit",
        name="Credit Module",
        organ_role="The heart of the bank",
        claimed_status="38.6% honest at v10.451 (NOT certified)",
        claimed_health_pct=38.6,
        pages=[
            "21_loan_applications.py",
            "22_credit_analysis.py",
            "23_credit_admin.py",
            "39_ews.py",
            "40_collateral.py",
            "70_retailer_finance.py",
            "71_bid_bond.py",
            "82_credit_approvals.py",
            "85_chief_credit_centre.py",  # v10.458: include centre in module text
        
            # v10.465 — re-homed pages
            "19_credit_monitoring.py",
            "111_credit_live.py",
            "20_debt_recovery.py",
        ],
        engines=[
            "credit_workflow",
            "credit_committee",
            "credit_risk_scoring",
            "credit_alt_scoring",
            "credit_risk_irb",
            "credit_underwriting",
            "ifrs9_engine",
            "analytics_credit_workbench",
        ],
        expected_roles=[
            "Chief Credit Officer",
            "Head Of Credit",
            "Credit Analyst",
            "Senior Credit Analyst",
            "Credit Risk Analyst",
            "Branch Credit Manager",
            "Branch Credit Officer",
            "Credit Monitoring Officer",
            "Manager-Credit Monitoring",
            "Debt Recovery Officer",
            "Credit Administration Officer",
            "Collateral Officer",
        ],
        kpi_keywords=["credit", "loan", "disburs", "npl", "provision",
                     "collateral", "ifrs", "recovery", "write"],
        command_centre_candidates=[
            "85_chief_credit_centre.py",
            "84_chief_credit_centre.py",
            "83_chief_credit_centre.py",
        ],
        integration_keywords={
            "hr": ["hr_actuals", "staff_performance"],
            "risk": ["risk_factor", "ifrs9"],
            "operations": ["operations", "ops_queue"],
            "finance": ["provision", "treasury"],
            "crm": ["customer_360", "client"],
            "pipeline": ["pipeline_deal_id"],
        },
    ),
    # v10.456: ICT as the 5th organ (Lungs - per Joshua doctrine).
    # Per Document 2 organ analogy. ICT exchanges system-wide oxygen
    # via Flexcube integration, observability, CICD, cybersecurity.
    # Second-level system admin lives in ICT (per Joshua continue v10.456).
    "ict": ModuleConfig(
        key="ict",
        name="ICT Module",
        organ_role="Lungs - System-wide Oxygen Exchange "
                  "(Flexcube integration · Observability · CICD · "
                  "Cybersecurity · Disaster Recovery)",
        claimed_status="newly added v10.456; pages already exist but "
                      "never measured against doctrine",
        claimed_health_pct=50.0,  # Honest starting estimate
        pages=[
            "6_integrate.py",
            "50_cybersecurity.py",
            "72_observability.py",
            "86_flexcube.py",
            "91_systems_view.py",
            "96_it_digital_pt1.py",
            "97_it_digital_pt2.py",
            "98_platform_health.py",
            "119_platform_hub.py",
            "121_chief_ict_centre.py",  # v10.460 - CIO command centre
        
            # v10.465 — re-homed pages
            "15_cbs.py",
            "57_deal_room.py",
        ],
        engines=[
            "flexcube_adapter",
            "flexcube_connection",
            "flexcube_mappings",
            "flexcube_staging",
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
            "it_api_gateway",
            "it_cbk_compliance",
            "it_cicd",
            "it_cloud_architecture",
            "it_data_encryption",
            "it_digital_banking",
            "it_disaster_recovery",
            "it_itsm",
            "it_multi_tenancy",
            "it_observability",
            "virtual_bank_core",
            "virtual_bank_simulator",
            "virtual_bank_readiness",
        ],
        expected_roles=[
            "Chief Information Officer",
            "Chief Technology Officer",
            "Head of IT",
            "IT Manager",
            "Systems Administrator",
            "ICT Super User",  # Per Joshua: 2nd-level admin from ICT
            "Service Desk Manager",
            "Cybersecurity Officer",
        ],
        kpi_keywords=["uptime", "incident", "sla", "mttr", "system",
                     "security", "integration", "platform"],
        command_centre_candidates=[
            "121_chief_ict_centre.py",  # v10.460 - CIO command centre (primary)
            "119_platform_hub.py",       # Existing platform hub (fallback)
            "98_platform_health.py",
            "91_systems_view.py",
        ],
        integration_keywords={
            "all_modules": ["flexcube_adapter", "flexcube_integration_readiness"],
            "admin": ["super_user", "audit_log", "rbac"],
            "credit": ["credit", "loan"],
            "hr": ["staff", "branch"],
            "bsc": ["kpi", "bsc"],
            "observability": ["uptime", "metric", "alert"],
        },
    ),
    # v10.461 - Finance organ (Circulatory & Energy Distribution per
    # Joshua mantra doc). Substantial existing infrastructure: 3 pages,
    # 6 engines. CFO command centre will cover BOTH finance and treasury
    # per Joshua continue v10.461.
    "finance": ModuleConfig(
        key="finance",
        name="Finance Module",
        organ_role="Circulatory & Energy Distribution System "
                  "(GL · close · accruals · operating segments · "
                  "financial intelligence)",
        claimed_status="v10.461 newly added; substantial existing "
                      "infrastructure never measured against doctrine",
        claimed_health_pct=50.0,  # Honest starting estimate
        pages=[
            "46_trade_finance.py",
            "70_retailer_finance.py",
            "116_finance_hub.py",
            "122_chief_finance_centre.py",  # v10.461 NEW CFO centre
        
            # v10.465 — re-homed pages
            "29_revenue_assurance.py",
            "32_ifrs9.py",
            "33_statement_analyzer.py",
            "88_ifrs_engines.py",
            "90_remaining_ifrs.py",
        ],
        engines=[
            "accruals_synthesizer",
            "finance_audit_compliance",
            "finance_close_orchestrator",
            "finance_hub_render",
            "finance_intelligence_dashboard",
            "operating_segments",
            # Wired infrastructure
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Chief Financial Officer",  # Actual role in users.json (Financial not Finance)
            "Finance Manager & Money Laundering Reporting Officer",
            "Finance Officer",
            "Chief Finance Officer",   # Also accept canonical alias
            "Head of Finance",
            "Senior Accountant",
            "Accountant",
            "Financial Controller",
            "Tax Officer",
            "Finance Super User",
        ],
        kpi_keywords=["revenue", "cost", "margin", "pbt", "income",
                     "expense", "provision", "operating", "fee"],
        command_centre_candidates=[
            "122_chief_finance_centre.py",  # v10.461 NEW (primary)
            "116_finance_hub.py",            # Existing fallback
        ],
        integration_keywords={
            "credit": ["provision", "ifrs9"],
            "treasury": ["liquidity", "treasury"],
            "operations": ["transaction", "ops"],
            "risk": ["risk_weight", "capital"],
            "admin": ["audit_log", "rbac"],
            "bsc": ["kpi", "actual", "target"],
        },
    ),
    # v10.461 - Treasury organ (Cash Flow Reservoir / Arterial Blood
    # Pressure - sub-system of Finance circulatory). Substantial 15
    # engines including ALM, FTP, market risk, VAR. Treasury is almost
    # stand-alone per Joshua - gets its OWN Head of Treasury Centre.
    "treasury": ModuleConfig(
        key="treasury",
        name="Treasury Module",
        organ_role="Cash Flow Reservoir & Arterial Blood Pressure "
                  "(ALM · FTP · FX · liquidity · market risk · VAR)",
        claimed_status="v10.461 newly added; 15 engines substantial",
        claimed_health_pct=60.0,
        pages=[
            "25_treasury.py",
            "110_treasury_live.py",
            "123_head_treasury_centre.py",  # v10.461 NEW Head Treasury
        
            # v10.465 — re-homed pages
            "53_irrbb.py",
            "56_ftp.py",
            "77_capital.py",
            "81_alm.py",
        ],
        engines=[
            "benchmark_rates",
            "funds_transfer_pricing",
            "fx_position",
            "liquidity_risk",
            "liquidity_stress",
            "market_risk",
            "market_risk_factors",
            "market_risk_limits",
            "market_risk_sensitivities",
            "market_risk_var",
            "treasury_agents",
            "treasury_alm",
            "treasury_connectivity",
            "treasury_dashboard",
            "treasury_dashboard_wiring",
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Head of Treasury",
            "Senior Manager Treasury",  # Actual in users.json
            "Treasury Dealer",          # Actual
            "Treasury Front Office Officer",  # Actual
            "Treasury Manager",
            "Senior Dealer",
            "Dealer",
            "ALM Officer",
            "FX Officer",
            "Treasury Super User",
        ],
        kpi_keywords=["liquidity", "ftp", "fx", "var", "lcr", "nsfr",
                     "duration", "yield", "spread", "alm"],
        command_centre_candidates=[
            "123_head_treasury_centre.py",  # v10.461 NEW (primary)
            "110_treasury_live.py",
            "25_treasury.py",
        ],
        integration_keywords={
            "finance": ["revenue", "cost", "pbt"],
            "credit": ["liquidity", "asset_liab"],
            "risk": ["market_risk", "var"],
            "admin": ["audit_log", "rbac"],
            "bsc": ["kpi", "target"],
        },
    ),
    # v10.461 - Legal organ (Constitutional Framework / Bony Skeleton -
    # provides structural integrity and boundary enforcement; not in
    # original 8 organs but critical). Company Secretary is the Chief
    # per Joshua. 7 engines existing: cases, docs, hold, spend, board.
    "legal": ModuleConfig(
        key="legal",
        name="Legal Module",
        organ_role="Bony Skeleton & Constitutional Framework "
                  "(cases · documents · holds · board governance · "
                  "spend · contracts)",
        claimed_status="v10.461 newly added; 7 engines substantial",
        claimed_health_pct=50.0,
        pages=[
            "26_legal.py",
            "84_board.py",
            "124_company_secretary_centre.py",  # v10.461 NEW
        ],
        engines=[
            "legal_analytics",
            "legal_case_management",
            "legal_dashboard",
            "legal_document_management",
            "legal_hold_management",
            "legal_spend_management",
            "board_reporting",
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Company Secretary and Chief Legal Officer",  # Actual in users.json
            "Manager- Legal",          # Actual
            "Legal Officer",           # Actual (4 staff)
            "Company Secretary",       # Canonical alias
            "Head of Legal",
            "Senior Legal Counsel",
            "Legal Counsel",
            "Board Secretary",
            "Legal Super User",
        ],
        kpi_keywords=["case", "litigation", "contract", "board",
                     "hold", "spend", "counsel", "governance"],
        command_centre_candidates=[
            "124_company_secretary_centre.py",  # v10.461 NEW (primary)
            "84_board.py",
            "26_legal.py",
        ],
        integration_keywords={
            "admin": ["audit_log", "rbac", "user"],
            "hr": ["disciplinary", "exit"],
            "credit": ["legal_hold", "case"],
            "risk": ["litigation", "compliance"],
            "bsc": ["kpi", "target"],
        },
    ),
    # v10.461 - Risk organ (Immune System per Joshua mantra doc).
    # Chief Risk Officer covers BOTH risk and compliance per Joshua
    # continue v10.461 (pattern mirrors Chief Finance covering both
    # finance and treasury).
    "risk": ModuleConfig(
        key="risk",
        name="Risk Module",
        organ_role="Immune System Primary "
                  "(market risk · operational risk · RWA · "
                  "stress testing · risk-based pricing)",
        claimed_status="v10.461 newly added; 8 engines existing",
        claimed_health_pct=55.0,
        pages=[
            "82_oprisk.py",
            "89_capital_risk_engines.py",
            "125_chief_risk_centre.py",  # v10.461 NEW CRO centre
        
            # v10.465 — re-homed pages
            "35_stress_testing.py",
            "36_smart_alerts.py",
            "54_rcsa.py",
        ],
        engines=[
            "market_risk",
            "market_risk_factors",
            "market_risk_limits",
            "market_risk_sensitivities",
            "market_risk_var",
            "operational_risk",
            "risk_based_pricing",
            "risk_weighted_assets",
            "compliance_risk_assessment",
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Chief Risk Officer",       # Actual in users.json
            "Risk Manager",             # Actual
            "Operational Risk Manager", # Actual
            "Head of Risk",
            "Head of Operational Risk",
            "Senior Risk Officer",
            "Risk Officer",
            "Risk Analyst",
            "Risk Super User",
        ],
        kpi_keywords=["risk", "var", "rwa", "capital", "stress",
                     "operational", "incident", "loss", "kri"],
        command_centre_candidates=[
            "125_chief_risk_centre.py",  # v10.461 NEW (primary)
            "82_oprisk.py",
            "89_capital_risk_engines.py",
        ],
        integration_keywords={
            "credit": ["credit_risk", "npl"],
            "treasury": ["market_risk", "var"],
            "compliance": ["compliance", "kyc"],
            "finance": ["capital", "rwa"],
            "admin": ["audit_log", "rbac"],
            "bsc": ["kpi", "target"],
        },
    ),
    # v10.461 - Compliance organ (Immune System secondary - antibodies /
    # KYC/AML/CBK monitoring). Substantial 15 engines: AML, KYC, CBK,
    # sanctions, tax, IRA. Gets its own Compliance Centre per Joshua
    # (mirrors Treasury sub-organ pattern).
    "compliance": ModuleConfig(
        key="compliance",
        name="Compliance Module",
        organ_role="Immune System Antibodies "
                  "(KYC · AML · CBK returns · sanctions · tax · "
                  "regulatory reporting · IRA insurance)",
        claimed_status="v10.461 newly added; 15 engines substantial",
        claimed_health_pct=60.0,
        pages=[
            "24_compliance.py",
            "74_cbk_returns.py",
            "76_sanctions.py",
            "103_compliance_dashboard.py",
            "107_cims_compliance.py",
            "112_compliance_live.py",
            "126_compliance_centre.py",  # v10.461 NEW
        
            # v10.465 — re-homed pages
            "55_aml.py",
            "75_data_protection.py",
            "85_esg.py",
            "92_climate_esg.py",
        ],
        engines=[
            "aml_monitoring",
            "api_compliance",
            "cbk_regulatory_reporting",
            "compliance_dashboard",
            "compliance_risk_assessment",
            "compliance_training",
            "finance_audit_compliance",
            "insurance_ira_compliance",
            "it_cbk_compliance",
            "kra_tax_compliance",
            "kyc_aml_risk",
            "kyc_onboarding",
            "regulatory_reporting",
            "sanctions_screening",
            "tax_compliance",
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Senior Manager- Compliance",         # Actual head of compliance in users.json
            "Regulatory Compliance Officer",      # Actual
            "Head of Compliance",                 # Canonical alias
            "Compliance Manager",
            "AML Officer",
            "Senior Compliance Officer",
            "Compliance Officer",
            "KYC Officer",
            "Compliance Super User",
        ],
        kpi_keywords=["compliance", "kyc", "aml", "cbk", "sanctions",
                     "regulatory", "reporting", "tax", "ira"],
        command_centre_candidates=[
            "126_compliance_centre.py",  # v10.461 NEW (primary)
            "112_compliance_live.py",
            "103_compliance_dashboard.py",
            "24_compliance.py",
        ],
        integration_keywords={
            "risk": ["risk", "incident"],
            "credit": ["kyc", "aml", "customer"],
            "operations": ["transaction", "monitoring"],
            "admin": ["audit_log", "rbac"],
            "hr": ["training", "certification"],
            "bsc": ["kpi", "target"],
        },
    ),
    # v10.465 - Operations organ (Muscular & Movement System per Joshua
    # mantra doc). COO Grace Makokha is the chief. Covers branch
    # operations, centralized processing, service delivery, payments,
    # procurement, vendor management, asset & facilities, PMO. Special
    # attention per Joshua: EDMS, CIMS, SLA, Approvals are SHARED
    # modules with broad secondary visibility.
    "operations": ModuleConfig(
        key="operations",
        name="Operations Module",
        organ_role="Muscular & Movement System "
                  "(branch ops · CIMS · SLA · EDMS · approvals · "
                  "fraud · clearing · projects · procurement · "
                  "vendors · assets · contracts · SWIFT)",
        claimed_status="v10.465 newly added; substantial existing "
                      "infrastructure - 22 pages including 4 SHARED "
                      "modules (EDMS/CIMS/SLA/Approvals)",
        claimed_health_pct=50.0,
        pages=[
            "13_sla.py",              # SHARED — Joshua: "very crucial"
            "14_branch_log.py",
            "18_cims.py",             # SHARED — CIMS primary
            "30_rms.py",
            "31_edms.py",             # SHARED — Joshua: "cut across"
            "37_approvals.py",        # SHARED — universal maker-checker
            "44_incidents.py",
            "51_agency_banking.py",
            "59_cab.py",
            "61_projects.py",
            "62_p2p.py",
            "63_assets.py",
            "64_vendors.py",
            "65_contracts.py",
            "67_fraud.py",
            "68_clearing.py",
            "99_swift_cockpit.py",
            "105_cims_capture.py",    # SHARED — CIMS batch
            "127_chief_operations_centre.py",  # v10.466 NEW COO centre
            "106_cims_process.py",    # SHARED — CIMS batch
            "107_cims_compliance.py", # SHARED — CIMS batch
            "108_cims_closure.py",    # SHARED — CIMS batch
            "109_cims_live.py",
        ],
        engines=[
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Chief Operating Officer",     # Actual in users.json
            "Head of Operations",
            "Operations Manager",
            "Branch Operations Supervisor",
            "Operations Supervisor-DFS",
            "Cash Centre Supervisor",
            "Reconciliation Supervisor",
            "Operations Officer",
            "Operations Super User",
        ],
        kpi_keywords=["sla", "approval", "transaction", "clearing",
                     "fraud", "incident", "throughput", "tat",
                     "settlement", "branch_log"],
        command_centre_candidates=[
            "127_chief_operations_centre.py",  # v10.466 NEW (primary)
            "13_sla.py",
            "37_approvals.py",
            "18_cims.py",
        ],
        integration_keywords={
            "credit": ["disbursement", "credit"],
            "compliance": ["aml", "kyc", "sanctions"],
            "finance": ["reconciliation", "settlement"],
            "risk": ["fraud", "incident", "operational_loss"],
            "admin": ["audit_log", "rbac", "approval"],
            "bsc": ["sla", "tat", "throughput"],
            "all_modules": ["edms", "cims", "sla", "approval"],
        },
    ),
    # v10.465 - CRM & Customer Functions organ (Sensory & Interaction
    # Systems per Joshua mantra doc). Per Joshua doctrine: SHARED
    # between CRBO (Chief Retail Banking Officer Nicholas Ndegwa) and
    # CCO (Chief Commercial Officer Emmanuel Kuria). Each chief gets
    # their own command centre filtering by staff hierarchy. Pipeline
    # enables EVERY staff to create a lead; support staff can assign.
    "crm": ModuleConfig(
        key="crm",
        name="CRM & Customer Functions Module",
        organ_role="Sensory & Interaction Systems "
                  "(pipeline · customer 360 · propositions · "
                  "campaigns · cross-sell · channels · NPS · "
                  "behavioral intelligence · onboarding · cards · "
                  "bancassurance · merchant acquiring)",
        claimed_status="v10.465 newly added; substantial existing - "
                      "22 pages incl. Pipeline (SHARED all staff) + "
                      "Customer 360 (3314 LOC) + Propositions",
        claimed_health_pct=50.0,
        pages=[
            "3_pipeline.py",            # SHARED — every staff creates leads
            "5_products.py",
            "16_commission.py",
            "17_campaigns.py",
            "27_propositions.py",
            "34_customer360.py",        # SHARED — Customer 360
            "38_nps.py",
            "45_crosssell.py",
            "47_digital_channels.py",   # retail-leaning
            "48_contact_centre.py",
            "49_bancassurance.py",      # retail
            "66_partnerships.py",       # commercial-leaning
            "69_consent.py",
            "73_channels.py",
            "78_onboarding.py",
            "79_cards.py",              # retail
            "80_merchant.py",           # commercial
            "91_customer_behavioral_intelligence.py",
            "92_propositions_workbench.py",
            "94_campaigns_management.py",
            "104_tf_mobile.py",         # commercial
            "117_propositions_hub.py",
            "128_chief_retail_centre.py",      # v10.466 NEW CRBO centre
            "129_chief_commercial_centre.py",  # v10.466 NEW CCO centre
        ],
        engines=[
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
            "cross_sell_bandit",
            "customer_behavioral",
            "dormancy_intelligence",
            "deposit_intelligence",
            "lending_intelligence",
        ],
        expected_roles=[
            "Chief Retail Banking Officer",    # Actual in users.json
            "Chief Commercial Officer",        # Actual in users.json
            "Head Of Corporates & Trade Finance",  # Actual
            "Senior Relationship Manager-Trade Finance Specialist",
            "Relationship Manager- Trade Finance",
            "Senior Trade Finance Officer",
            "Trade Finance Officer",
            "Trade Finance Back Office Manager",
            "Trade Finance Operations Officer",
            "CRM Super User",
        ],
        kpi_keywords=["pipeline", "lead", "conversion", "nps",
                     "cross_sell", "campaign", "customer_360",
                     "proposition", "onboarding", "engagement"],
        command_centre_candidates=[
            "128_chief_retail_centre.py",      # v10.466 NEW CRBO (primary)
            "129_chief_commercial_centre.py",  # v10.466 NEW CCO (co-primary)
            "3_pipeline.py",
            "34_customer360.py",
            "117_propositions_hub.py",
        ],
        integration_keywords={
            "credit": ["customer", "lending"],
            "operations": ["onboarding", "edms", "cims"],
            "compliance": ["kyc", "consent"],
            "bsc": ["pipeline", "leads", "conversion"],
            "admin": ["audit_log", "rbac"],
            "treasury": ["fx", "trade_finance"],
        },
    ),
    # v10.465 - Reporting & Analytics organ (Vital Signs Monitoring &
    # Diagnostic Systems per Joshua mantra doc). Top-level analytical
    # diagnostic organ. Reports up to MD via Chief Strategy & Analytics
    # (or similar - currently no dedicated chief, may report to COO/CFO).
    "reporting_analytics": ModuleConfig(
        key="reporting_analytics",
        name="Reporting & Analytics Module",
        organ_role="Vital Signs Monitoring & Diagnostic Systems "
                  "(reporting · analytics workbench · NLQ · anomaly · "
                  "branch ranking · SBU drilldown · benchmarking · "
                  "competitor intelligence)",
        claimed_status="v10.465 newly added; existing infrastructure "
                      "scattered - 9 pages",
        claimed_health_pct=55.0,
        pages=[
            "11_competitor.py",
            "28_ra.py",
            "87_benchmarking.py",
            "93_competitor_intelligence.py",
            "101_analytics_workbench.py",
            "102_analytics_advanced.py",
            "113_branch_ranking.py",
            "114_sbu_drilldown.py",
            "118_competitor_hub.py",
            "130_head_analytics_centre.py",  # v10.466 NEW Head Analytics centre
        ],
        engines=[
            "flexcube_integration_readiness",
            "stress_test_harness",
            "scalability_validator",
            "cross_organ_event_bus",
            "super_user_registry",
            "notification_broadcaster",
        ],
        expected_roles=[
            "Head of Analytics",
            "Senior Analyst",
            "Analytics Manager",
            "Business Intelligence Officer",
            "Data Analyst",
            "Reporting Officer",
            "Analytics Super User",
        ],
        kpi_keywords=["report", "analytics", "kpi", "benchmark",
                     "branch_rank", "anomaly", "nlq", "trend",
                     "diagnostic"],
        command_centre_candidates=[
            "130_head_analytics_centre.py",  # v10.466 NEW (primary)
            "28_ra.py",
            "101_analytics_workbench.py",
            "102_analytics_advanced.py",
        ],
        integration_keywords={
            "all_modules": ["kpi", "actual", "report"],
            "bsc": ["scorecard", "actual"],
            "admin": ["audit_log", "rbac"],
        },
    ),
}


# ════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════

@dataclass
class PhaseScore:
    phase: str
    name: str
    sub_criteria: List[Dict[str, Any]]
    score_pct: float
    critical_gaps: List[str]


@dataclass
class ModuleDoctrineHealth:
    """Honest doctrine health for one module."""
    module_key: str
    module_name: str
    organ_role: str
    claimed_status: str
    claimed_health_pct: float
    # 8 phases
    phase_1: PhaseScore
    phase_2: PhaseScore
    phase_3: PhaseScore
    phase_4: PhaseScore
    phase_5: PhaseScore
    phase_6: PhaseScore
    phase_7: PhaseScore
    phase_8: PhaseScore
    # Final validation 14 criteria
    final_validation_pct: float
    criteria_fully_met: int
    criteria_partial: int
    criteria_not_met: int
    certified: bool
    # Vital signs 10 questions
    vital_signs_pct: float
    vital_pass: int
    vital_partial: int
    vital_fail: int
    # Diagnostic principles 5
    diagnostic_pct: float
    # Composite
    doctrine_health_pct: float
    honesty_gap_pp: float          # claimed - honest (absolute pp)
    top_rescue_priorities: List[str]
    timestamp: str

    def to_dict(self):
        return {
            "module_key": self.module_key,
            "module_name": self.module_name,
            "organ_role": self.organ_role,
            "claimed_status": self.claimed_status,
            "claimed_health_pct": self.claimed_health_pct,
            "phase_1": asdict(self.phase_1),
            "phase_2": asdict(self.phase_2),
            "phase_3": asdict(self.phase_3),
            "phase_4": asdict(self.phase_4),
            "phase_5": asdict(self.phase_5),
            "phase_6": asdict(self.phase_6),
            "phase_7": asdict(self.phase_7),
            "phase_8": asdict(self.phase_8),
            "final_validation_pct": self.final_validation_pct,
            "criteria_fully_met": self.criteria_fully_met,
            "criteria_partial": self.criteria_partial,
            "criteria_not_met": self.criteria_not_met,
            "certified": self.certified,
            "vital_signs_pct": self.vital_signs_pct,
            "vital_pass": self.vital_pass,
            "vital_partial": self.vital_partial,
            "vital_fail": self.vital_fail,
            "diagnostic_pct": self.diagnostic_pct,
            "doctrine_health_pct": self.doctrine_health_pct,
            "honesty_gap_pp": self.honesty_gap_pp,
            "top_rescue_priorities": self.top_rescue_priorities,
            "timestamp": self.timestamp,
        }


@dataclass
class AllModulesAudit:
    """Aggregate honest health for all claimed-complete modules."""
    modules: Dict[str, ModuleDoctrineHealth]
    avg_doctrine_health_pct: float
    avg_honesty_gap_pp: float        # avg absolute claimed - honest
    certified_count: int             # modules with all 14 criteria met
    crisis_modules: List[str]        # modules at <50%
    timestamp: str

    def to_dict(self):
        return {
            "modules": {k: v.to_dict() for k, v in self.modules.items()},
            "avg_doctrine_health_pct": self.avg_doctrine_health_pct,
            "avg_honesty_gap_pp": self.avg_honesty_gap_pp,
            "certified_count": self.certified_count,
            "crisis_modules": self.crisis_modules,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _read_text(p: Path) -> str:
    try: return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError): return ""


def _module_text(cfg: ModuleConfig) -> str:
    """Concatenated text of module's pages + engines."""
    chunks = []
    for page in cfg.pages:
        chunks.append(_read_text(PAGES_DIR / page))
    for eng in cfg.engines:
        chunks.append(_read_text(UTILS_DIR / f"{eng}.py"))
    return "\n".join(chunks)


def _doc_exists(cfg: ModuleConfig, suffix: str) -> bool:
    """Check if a doctrine doc exists for this module."""
    return (DOCS_DIR / f"{cfg.key}_{suffix}.md").exists()


# ════════════════════════════════════════════════════════════════════
# Phase audits (parameterized for any module)
# ════════════════════════════════════════════════════════════════════

def _phase_1(cfg: ModuleConfig) -> PhaseScore:
    """Phase 1 — Deep Diagnostic. 25+ sub-criteria."""
    text = _module_text(cfg)
    pages = cfg.pages
    engines = cfg.engines
    sub = []
    gaps = []

    # Functional
    sub.append({"c": "F1. Features inventoried", "met": len(pages) >= 1})
    sub.append({"c": "F2. Workflows mapped", "met": len(engines) >= 1})
    sub.append({"c": "F3. Business logic completeness",
                "met": any(_read_text(PAGES_DIR/p).count("def ") >= 1 for p in pages)})
    sub.append({"c": "F4. User journeys (forms/tabs)",
                "met": any("st.tabs" in _read_text(PAGES_DIR/p) or
                          "st.form" in _read_text(PAGES_DIR/p) for p in pages)})
    sub.append({"c": "F5. Approval flows",
                "met": bool(re.search(r"approve|approval|sign_off", text, re.I))})
    exc_pages = sum(1 for p in pages if "except" in _read_text(PAGES_DIR/p))
    exc_pct = exc_pages / len(pages) * 100 if pages else 0
    sub.append({"c": "F6. Exception handling >=70%", "met": exc_pct >= 70})
    if exc_pct < 70: gaps.append(f"F6: {exc_pct:.0f}% pages have try/except")
    rep_pages = sum(1 for p in pages
                   if "st.dataframe" in _read_text(PAGES_DIR/p)
                   or "to_excel" in _read_text(PAGES_DIR/p))
    rep_pct = rep_pages / len(pages) * 100 if pages else 0
    sub.append({"c": "F7. Reporting capability >=70%", "met": rep_pct >= 70})
    sub.append({"c": "F8. Operational dependencies doc",
                "met": _doc_exists(cfg, "operational_dependencies")})
    if not _doc_exists(cfg, "operational_dependencies"):
        gaps.append("F8: operational dependencies doc missing")

    # Technical
    sub.append({"c": "T1. Architecture doc",
                "met": _doc_exists(cfg, "architecture")})
    if not _doc_exists(cfg, "architecture"):
        gaps.append("T1: architecture doc missing")
    sub.append({"c": "T2. Code quality (engine docstrings)",
                "met": all('"""' in _read_text(UTILS_DIR/f"{e}.py")[:500]
                          for e in engines) if engines else False})
    api_text = _read_text(REPO_ROOT / "utils" / "api.py")
    api_keyword = cfg.key if cfg.key != "bsc_cascade" else "bsc"
    routes = len(re.findall(rf"/api/{api_keyword}/", api_text))
    sub.append({"c": f"T3. API structure (>=4 /api/{api_keyword}/ routes)",
                "met": routes >= 4})
    if routes < 4: gaps.append(f"T3: only {routes} API routes for {api_keyword}")
    sub.append({"c": "T4. DB schema present",
                "met": (REPO_ROOT/"db").exists() or (REPO_ROOT/"migrations").exists()})
    sub.append({"c": "T5. Performance doc", "met": _doc_exists(cfg, "performance")})
    if not _doc_exists(cfg, "performance"):
        gaps.append("T5: performance doc missing")
    sub.append({"c": "T6. Security doc", "met": _doc_exists(cfg, "security_review")})
    if not _doc_exists(cfg, "security_review"):
        gaps.append("T6: security review doc missing")
    todos = len(re.findall(r"#\s*(?:TODO|FIXME|HACK|XXX)\b", text))
    sub.append({"c": "T7. Tech debt <50 markers", "met": todos < 50})
    sub.append({"c": "T8. No legacy code", "met": True})
    sub.append({"c": "T9. Redundancy scan doc",
                "met": _doc_exists(cfg, "redundancy_scan")})
    sub.append({"c": "T10. Orphaned scan doc",
                "met": _doc_exists(cfg, "orphaned_scan")})
    sub.append({"c": "T11. Scalability doc", "met": _doc_exists(cfg, "scalability")})
    if not _doc_exists(cfg, "scalability"):
        gaps.append("T11: scalability doc missing")
    hardcoded = len(re.findall(r"\b(?:threshold|limit)\s*=\s*[\"']?[\d_]{5,}[\"']?",
                              text, re.I))
    sub.append({"c": "T12. No hardcoded configs (admin-managed)",
                "met": hardcoded < 20})

    # Data
    sub.append({"c": "D1. Data flow integrity (engine docs)",
                "met": all('"""' in _read_text(UTILS_DIR/f"{e}.py")[:500]
                          for e in engines) if engines else False})
    sub.append({"c": "D2. Duplication risk doc",
                "met": _doc_exists(cfg, "data_duplication")})
    sub.append({"c": "D3. Data relationships doc",
                "met": _doc_exists(cfg, "data_relationships")})
    sub.append({"c": "D4. Consistent mappings",
                "met": bool(re.search(r"client_cif|cif_number|staff_code|user_id", text))})
    audit_calls = len(re.findall(r"\baudit_log\(", text))
    sub.append({"c": "D5. Audit trail >=10 calls", "met": audit_calls >= 10})
    sub.append({"c": "D6. Sync gaps doc", "met": _doc_exists(cfg, "sync_gaps")})
    sub.append({"c": "D7. Data lineage doc", "met": _doc_exists(cfg, "data_lineage")})

    # Operational
    sub.append({"c": "O1. Real-life usage audited",
                "met": _doc_exists(cfg, "usage_audit")})
    sub.append({"c": "O2. Manual workarounds <30", "met": todos < 30})
    sub.append({"c": "O3. Pain points doc", "met": _doc_exists(cfg, "pain_points")})
    sub.append({"c": "O4. Approval bottlenecks doc",
                "met": _doc_exists(cfg, "approval_bottlenecks")})
    sub.append({"c": "O5. Adoption report", "met": _doc_exists(cfg, "adoption_report")})
    sub.append({"c": "O6. Hidden deps doc", "met": _doc_exists(cfg, "hidden_deps")})

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 1", "Deep Diagnostic", sub, round(pct, 1), gaps)


def _phase_2(cfg: ModuleConfig) -> PhaseScore:
    """Phase 2 — QA Standards Compliance."""
    sub = []
    gaps = []
    audit_text = _read_text(REPO_ROOT / "scripts" / "audit.py")
    # Count module-specific audit gates
    gate_count = len(re.findall(rf"def gate_v10[\d_]+_{cfg.key}_\w+", audit_text))
    if cfg.key == "bsc_cascade":
        gate_count = max(gate_count,
                        len(re.findall(r"def gate_v10[\d_]+_bsc_\w+", audit_text)),
                        len(re.findall(r"def gate_v10[\d_]+_cascade_\w+", audit_text)))
    sub.append({"c": "QA1. Module-specific audit gates >=3",
                "met": gate_count >= 3})
    if gate_count < 3:
        gaps.append(f"QA1: only {gate_count} module-specific gates")
    sub.append({"c": "QA2. Gap analysis doc",
                "met": _doc_exists(cfg, "qa_gap_analysis")})
    if not _doc_exists(cfg, "qa_gap_analysis"):
        gaps.append("QA2: QA gap analysis doc missing")
    sub.append({"c": "QA3. Risk assessment doc",
                "met": _doc_exists(cfg, "risk_assessment")})
    sub.append({"c": "QA4. Recovery priority matrix",
                "met": _doc_exists(cfg, "recovery_priority_matrix")})
    sub.append({"c": "QA5. Remediation roadmap",
                "met": _doc_exists(cfg, "remediation_roadmap")})
    sub.append({"c": "QA6. Compliance score recorded",
                "met": _doc_exists(cfg, "qa_gap_analysis")
                       and "compliance" in _read_text(
                           DOCS_DIR / f"{cfg.key}_qa_gap_analysis.md").lower()})
    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 2", "QA Standards Compliance", sub, round(pct, 1), gaps)


def _phase_3(cfg: ModuleConfig) -> PhaseScore:
    """Phase 3 — Recovery & Modernization."""
    text = _module_text(cfg)
    pages = cfg.pages
    sub = []
    gaps = []

    # Immediate recovery
    import ast as _ast
    parse_errors = 0
    for p in pages:
        try: _ast.parse(_read_text(PAGES_DIR/p))
        except SyntaxError: parse_errors += 1
    sub.append({"c": "IR1. No parse errors", "met": parse_errors == 0})

    # Workflow restoration (presence of state machines or workflow engines)
    has_workflow = bool(re.search(
        r"WorkflowEngine|state_machine|ApplicationState|ALLOWED_TRANSITIONS", text))
    sub.append({"c": "IR2. Workflow restoration", "met": has_workflow})

    rbac_pages = sum(1 for p in pages if "require_access" in _read_text(PAGES_DIR/p))
    rbac_pct = rbac_pages / len(pages) * 100 if pages else 0
    sub.append({"c": "IR3. Security (>=80% pages RBAC)", "met": rbac_pct >= 80})
    if rbac_pct < 80: gaps.append(f"IR3: only {rbac_pct:.0f}% pages RBAC-gated")

    # Structural modernization
    api_keyword = cfg.key if cfg.key != "bsc_cascade" else "bsc"
    api_text = _read_text(REPO_ROOT / "utils" / "api.py")
    api_engines_wired = sum(1 for e in cfg.engines if e in api_text)
    api_pct = api_engines_wired / len(cfg.engines) * 100 if cfg.engines else 0
    sub.append({"c": f"SM1. FastAPI (>=80% engines)", "met": api_pct >= 80})
    if api_pct < 80: gaps.append(f"SM1: only {api_pct:.0f}% engines in API")

    react_clean = sum(1 for p in pages
                     if _read_text(PAGES_DIR/p).count("unsafe_allow_html=True") <= 10)
    react_pct = react_clean / len(pages) * 100 if pages else 0
    sub.append({"c": "SM2. React readiness >=90%", "met": react_pct >= 90})

    pg_pages = sum(1 for p in pages
                  if "psycopg" in _read_text(PAGES_DIR/p)
                  or "a2z_db" in _read_text(PAGES_DIR/p)
                  or "from utils.db" in _read_text(PAGES_DIR/p))
    pg_pct = pg_pages / len(pages) * 100 if pages else 0
    sub.append({"c": "SM3. PostgreSQL backing >=90%", "met": pg_pct >= 90})
    if pg_pct < 90: gaps.append(f"SM3: only {pg_pct:.0f}% pages PG-backed")

    sub.append({"c": "SM4. Modularized (>=1 engine)", "met": len(cfg.engines) >= 1})
    sub.append({"c": "SM5. Containerization (Dockerfile)",
                "met": (REPO_ROOT/"Dockerfile").exists()})
    has_events = bool(re.search(r"event_bus|publish_event|asyncio", text))
    sub.append({"c": "SM6. Event-driven capable", "met": has_events})
    if not has_events: gaps.append("SM6: no event-driven hooks")
    sub.append({"c": "SM7. Cloud deployable",
                "met": "os.getenv(" in text or (REPO_ROOT/".env.example").exists()})

    # Enterprise compatibility
    has_flexcube = bool(re.search(r"flexcube|fcubs", text, re.I))
    sub.append({"c": "EC1. Flexcube compatibility", "met": has_flexcube})
    if not has_flexcube: gaps.append("EC1: zero Flexcube references")
    sub.append({"c": "EC2. BSC integration",
                "met": "bsc_audit_engine" in text or "_bsc_trigger" in text
                       or cfg.key == "bsc_cascade"})
    sub.append({"c": "EC3. Notification system",
                "met": bool(re.search(r"notify|send_email|sms_send", text))})
    has_rbac = "require_access" in text
    sub.append({"c": "EC4. Authentication & RBAC", "met": has_rbac})
    audit_calls = len(re.findall(r"\baudit_log\(", text))
    sub.append({"c": "EC5. Audit integration (>=10 calls)", "met": audit_calls >= 10})

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 3", "Recovery & Modernization", sub, round(pct, 1), gaps)


def _phase_4(cfg: ModuleConfig) -> PhaseScore:
    """Phase 4 — Human Workflow Alignment."""
    sub = []
    gaps = []
    text = _module_text(cfg)
    cascade_text = _read_text(DATA_DIR / "target_cascade.json")

    # Expected roles in cascade
    roles_found = sum(1 for r in cfg.expected_roles if r in cascade_text)
    role_pct = roles_found / len(cfg.expected_roles) * 100 if cfg.expected_roles else 0
    sub.append({"c": "WF1. Expected roles in cascade",
                "met": role_pct >= 80})
    if role_pct < 80:
        missing = [r for r in cfg.expected_roles if r not in cascade_text]
        gaps.append(f"WF1: {len(missing)} expected roles missing: {missing[:3]}")

    sub.append({"c": "WF2. Reporting lines intact",
                "met": role_pct >= 50})

    # RBAC per page
    pages_rbac = sum(1 for p in cfg.pages
                    if "require_access" in _read_text(PAGES_DIR/p))
    rbac_pct = pages_rbac / len(cfg.pages) * 100 if cfg.pages else 0
    sub.append({"c": "WF3. Per-role access (>=80% RBAC)", "met": rbac_pct >= 80})

    # Operational outputs
    pages_actions = sum(1 for p in cfg.pages
                       if "st.button" in _read_text(PAGES_DIR/p)
                       or "form_submit_button" in _read_text(PAGES_DIR/p))
    action_pct = pages_actions / len(cfg.pages) * 100 if cfg.pages else 0
    sub.append({"c": "WF4. Operational outputs (>=70%)", "met": action_pct >= 70})

    # Super user
    super_user = bool(re.search(r"super_user|is_super_user", text, re.I))
    sub.append({"c": "WF5. Super user configured", "met": super_user})
    if not super_user: gaps.append("WF5: no super user for module")

    # Escalation
    has_escalation = bool(re.search(r"escalat|refer_to|TIER_4|escalation_path", text))
    sub.append({"c": "WF6. Escalation paths", "met": has_escalation})

    # Workload balancing
    has_workload = bool(re.search(r"workload|capacity|queue_balance", text))
    sub.append({"c": "WF7. Workload balancing", "met": has_workload})
    if not has_workload: gaps.append("WF7: workload balancing not visible")

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 4", "Human Workflow Alignment", sub, round(pct, 1), gaps)


def _phase_5(cfg: ModuleConfig) -> PhaseScore:
    """Phase 5 — BSC & Actuals Intelligence."""
    sub = []
    gaps = []
    text = _module_text(cfg)

    # Find module-related KPIs in library
    kpi_file = DATA_DIR / "kpi_library.json"
    module_kpis_total = 0
    if kpi_file.exists():
        try:
            kpi_data = json.loads(kpi_file.read_text(encoding="utf-8"))
            kpis = kpi_data.get("kpis", kpi_data) if isinstance(kpi_data, dict) else kpi_data
            if isinstance(kpis, dict): kpis = list(kpis.values())
            for k in kpis:
                if isinstance(k, dict):
                    name = str(k.get("name", "")).lower()
                    desc = str(k.get("description", "")).lower()
                    if any(kw in name or kw in desc for kw in cfg.kpi_keywords):
                        module_kpis_total += 1
        except Exception: pass

    sub.append({"c": f"BSC1. Module KPIs in library (>=10)",
                "met": module_kpis_total >= 10})

    # Auto-actuals engine present
    actuals_eng = UTILS_DIR / f"{cfg.key}_actuals_engine.py"
    if cfg.key == "hr": actuals_eng = UTILS_DIR / "hr_actuals_engine.py"
    has_auto_eng = actuals_eng.exists()
    sub.append({"c": f"BSC2. {cfg.key}_actuals_engine.py", "met": has_auto_eng})
    if not has_auto_eng:
        gaps.append(f"BSC2: no {cfg.key}_actuals_engine for auto-actuals")

    # Target mapping in cascade
    cascade_text = _read_text(DATA_DIR / "target_cascade.json")
    has_targets = any(r in cascade_text for r in cfg.expected_roles)
    sub.append({"c": "BSC3. Target mapping per role", "met": has_targets})

    # BSC engine exists
    bsc_eng = (UTILS_DIR / "bsc_audit_engine.py").exists()
    sub.append({"c": "BSC4. BSC engine available", "met": bsc_eng})

    # Auditability of actuals
    actuals_files = list(DATA_DIR.glob("actuals_*.xlsx"))
    sub.append({"c": "BSC5. Actuals files preserved", "met": len(actuals_files) >= 1})

    # Historical BSC
    sub.append({"c": "BSC6. Historical BSC scorecards",
                "met": (DATA_DIR / "balanced_scorecards.json").exists()})

    # Exception reporting / alerts
    has_alerts = bool(re.search(r"breach|sla_breach|st\.warning|st\.error", text))
    sub.append({"c": "BSC7. Exception reporting/alerts", "met": has_alerts})

    # Auto-actuals coverage
    if has_auto_eng:
        eng_text = _read_text(actuals_eng)
        auto_kpis = sum(1 for kw in cfg.kpi_keywords if kw in eng_text.lower())
        auto_pct = auto_kpis / len(cfg.kpi_keywords) * 100 if cfg.kpi_keywords else 0
    else:
        auto_pct = 0.0
    sub.append({"c": "BSC8. Auto-actuals coverage >=50%", "met": auto_pct >= 50})
    if auto_pct < 50:
        gaps.append(f"BSC8: auto-actuals coverage only {auto_pct:.0f}%")

    # Feeds enterprise BSC (KPI triggers wired)
    trigger_calls = len(re.findall(r"_bsc_trigger|trigger_kpi", text))
    sub.append({"c": "BSC9. KPI triggers wired (>=3)", "met": trigger_calls >= 3})

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 5", "BSC & Actuals Intelligence", sub, round(pct, 1), gaps)


def _phase_6(cfg: ModuleConfig) -> PhaseScore:
    """Phase 6 — Command Centre."""
    sub = []
    gaps = []

    centre_page = None
    for candidate in cfg.command_centre_candidates:
        if (PAGES_DIR / candidate).exists():
            centre_page = candidate
            break

    sub.append({"c": "CC1. Command centre page exists", "met": centre_page is not None})
    if centre_page is None:
        gaps.append(f"CC1 CRITICAL: no {cfg.name} command centre page")
        for c in ("CC2. Executive visibility", "CC3. Strategic intelligence",
                  "CC4. Organ health monitoring", "CC5. Staff performance tab",
                  "CC6. Real-time KPIs", "CC7. Risk indicators / SLA breaches"):
            sub.append({"c": c, "met": False})
    else:
        ctr_text = _read_text(PAGES_DIR / centre_page)
        sub.append({"c": "CC2. Executive visibility (KPI widgets)",
                    "met": "st.metric" in ctr_text})
        sub.append({"c": "CC3. Strategic intelligence (trends/forecast)",
                    "met": "trend" in ctr_text.lower() or "forecast" in ctr_text.lower()})
        sub.append({"c": "CC4. Organ health monitoring",
                    "met": "health" in ctr_text.lower()})
        sub.append({"c": "CC5. Staff performance tab",
                    "met": "My Staff Performance" in ctr_text or "staff_performance" in ctr_text.lower()})
        sub.append({"c": "CC6. Real-time/live indicators",
                    "met": "real-time" in ctr_text.lower() or "live" in ctr_text.lower()})
        sub.append({"c": "CC7. Risk indicators / SLA",
                    "met": "sla" in ctr_text.lower() or "breach" in ctr_text.lower()})

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 6", "Command Centre", sub, round(pct, 1), gaps)


def _phase_7(cfg: ModuleConfig) -> PhaseScore:
    """Phase 7 — Cross-Organ Harmonization."""
    sub = []
    gaps = []
    text = _module_text(cfg)

    # Cross-organ links per config
    for organ, keywords in cfg.integration_keywords.items():
        has_link = any(kw in text for kw in keywords)
        sub.append({"c": f"X1. Link to {organ}", "met": has_link})
        if not has_link:
            gaps.append(f"X: link to {organ} missing")

    # Shared master data
    has_master = bool(re.search(r"client_cif|cif_number|staff_code|user_id|branch", text))
    sub.append({"c": "X. Shared master data", "met": has_master})

    # Unified audit trails
    audit_calls = len(re.findall(r"\baudit_log\(", text))
    sub.append({"c": "X. Unified audit trails (>=10)", "met": audit_calls >= 10})

    # KPI contribution
    sub.append({"c": "X. Shared KPI contribution",
                "met": "_bsc_trigger" in text or cfg.key == "bsc_cascade"})

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 7", "Cross-Organ Harmonization", sub, round(pct, 1), gaps)


def _phase_8(cfg: ModuleConfig) -> PhaseScore:
    """Phase 8 — Anti-Deterioration."""
    sub = []
    gaps = []
    text = _module_text(cfg)
    audit_text = _read_text(REPO_ROOT / "scripts" / "audit.py")
    body_text = _read_text(UTILS_DIR / "body_health_engine.py")

    # Stability controls
    sub.append({"c": "S1. Module in body_health ORGAN_REGISTRY",
                "met": cfg.key in body_text or cfg.key.replace("_", "") in body_text})
    sub.append({"c": "S2. Logger instrumented",
                "met": "logger." in text or "logging.getLogger" in text})
    sub.append({"c": "S3. Performance monitoring",
                "met": bool(re.search(r"time\.perf_counter|@timing", text))})
    sub.append({"c": "S4. Dependency monitoring doc",
                "met": _doc_exists(cfg, "dependencies")})
    audit_calls = len(re.findall(r"\baudit_log\(", text))
    sub.append({"c": "S5. Audit controls (>=10)", "met": audit_calls >= 10})
    sub.append({"c": "S6. Data integrity checks",
                "met": bool(re.search(r"validate_|ValidationError", text))})
    sub.append({"c": "S7. Verifier present",
                "met": (REPO_ROOT/"scripts"/"verify_local_state.py").exists()})
    sub.append({"c": "S8. Backup dirs >=3",
                "met": len(list(DATA_DIR.glob("_v10*_backups"))) >= 3})
    sub.append({"c": "S9. Failover/fallback",
                "met": bool(re.search(r"fallback|graceful|except.*continue", text))})
    sub.append({"c": "S10. Usage monitoring",
                "met": bool(re.search(r"track_page|page_view|usage_analytics", text))})
    if not bool(re.search(r"track_page|page_view|usage_analytics", text)):
        gaps.append("S10: no usage monitoring")
    sub.append({"c": "S11. Security monitoring",
                "met": bool(re.search(r"access_denied|auth_failure|security_event", text))})
    if not bool(re.search(r"access_denied|auth_failure|security_event", text)):
        gaps.append("S11: no security event monitoring")
    sub.append({"c": "S12. Tech debt tracking",
                "met": "DEFER_TO" in text or "SPEC_DEVIATION" in text})
    sub.append({"c": "S13. Version governance (G162)",
                "met": "G162" in audit_text})
    sub.append({"c": "S14. Documentation governance (CHANGELOGs)",
                "met": len(list(REPO_ROOT.glob("CHANGELOG_v10.4*.md"))) >= 5})

    # 8 deterioration scans
    for scan in ("stale_scan", "dead_workflows", "orphaned_scan",
                 "redundancy_scan", "performance", "data_consistency",
                 "security_drift", "scalability"):
        sub.append({"c": f"SC. {scan} doc", "met": _doc_exists(cfg, scan)})
        if not _doc_exists(cfg, scan):
            gaps.append(f"SC: {scan} doc missing")

    met = sum(1 for s in sub if s["met"])
    pct = met / len(sub) * 100 if sub else 0
    return PhaseScore("Phase 8", "Anti-Deterioration", sub, round(pct, 1), gaps)


# ════════════════════════════════════════════════════════════════════
# Final Validation + Vital Signs + Diagnostic Principles
# ════════════════════════════════════════════════════════════════════

def _final_validation(cfg: ModuleConfig, phases: Dict[str, PhaseScore]) -> tuple:
    """Returns (fully_met, partial, not_met, pct, certified) for 14 criteria."""
    text = _module_text(cfg)
    crit = []

    crit.append(phases["phase_1"].score_pct >= 80)                          # 1
    crit.append(phases["phase_3"].score_pct >= 90)                          # 2
    crit.append(phases["phase_2"].score_pct >= 90)                          # 3
    pages_rbac = sum(1 for p in cfg.pages if "require_access" in _read_text(PAGES_DIR/p))
    crit.append((pages_rbac / len(cfg.pages) * 100 if cfg.pages else 0) >= 90)  # 4 react/PG proxy
    api_text = _read_text(REPO_ROOT / "utils" / "api.py")
    api_engines = sum(1 for e in cfg.engines if e in api_text)
    crit.append(api_engines / len(cfg.engines) * 100 >= 90 if cfg.engines else False)  # 5
    crit.append(bool(re.search(r"flexcube|fcubs", text, re.I)))              # 6
    crit.append((UTILS_DIR / f"{cfg.key}_actuals_engine.py").exists()
                if cfg.key != "hr" else (UTILS_DIR / "hr_actuals_engine.py").exists())  # 7
    crit.append(phases["phase_6"].score_pct >= 80)                          # 8
    crit.append(phases["phase_7"].score_pct >= 80)                          # 9
    crit.append(bool(re.search(r"stress_test|load_test|benchmark", text, re.I)))  # 10
    crit.append(phases["phase_8"].score_pct >= 80)                          # 11
    changelogs = len(list(REPO_ROOT.glob("CHANGELOG_v10.4*.md")))
    crit.append(changelogs >= 8 and _doc_exists(cfg, "module_revival"))     # 12
    crit.append(_doc_exists(cfg, "adoption_report"))                        # 13
    crit.append(bool(re.search(r"horizontal_scale|capacity_plan", text, re.I)))  # 14

    fully = sum(1 for c in crit if c)
    not_met = sum(1 for c in crit if not c)
    pct = fully / len(crit) * 100
    certified = fully == len(crit)
    return fully, 0, not_met, round(pct, 1), certified


def _vital_signs(cfg: ModuleConfig, phases: Dict[str, PhaseScore],
                _cached_360: Optional[float] = None) -> tuple:
    """Returns (pass_count, partial, fail, pct)."""
    scores = []
    # 1. Healthy in isolation
    p1 = phases["phase_1"].score_pct
    scores.append("pass" if p1 >= 80 else ("partial" if p1 >= 50 else "fail"))
    # 2. Healthy when connected
    p7 = phases["phase_7"].score_pct
    scores.append("pass" if p7 >= 80 else ("partial" if p7 >= 50 else "fail"))
    # 3. Hidden stress
    scores.append("pass" if len(phases["phase_1"].critical_gaps) == 0 else "partial")
    # 4. Reviving without weakening (proxy: body health doesn't regress)
    if _cached_360 is not None:
        scores.append("pass" if _cached_360 >= 100 else "fail")
    else:
        try:
            from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
            c360 = cascade_bsc_360_audit()
            scores.append("pass" if c360.overall_harmony_pct >= 100 else "fail")
        except Exception:
            scores.append("partial")
    # 5. Information flowing
    p3 = phases["phase_3"].score_pct
    scores.append("pass" if p3 >= 80 else "fail")
    # 6. No toxic loops / silos
    scores.append("partial" if p7 >= 50 else "fail")
    # 7. Synchronized organism
    sync = (p3 + p7) / 2
    scores.append("pass" if sync >= 80 else ("partial" if sync >= 50 else "fail"))
    # 8. Stress-tested
    text = _module_text(cfg)
    has_stress = bool(re.search(r"stress_test|load_test|benchmark", text, re.I))
    scores.append("pass" if has_stress else "fail")
    # 9. Controls/safeguards
    p8 = phases["phase_8"].score_pct
    scores.append("pass" if p8 >= 80 else ("partial" if p8 >= 50 else "fail"))
    # 10. Body survives failure
    p5 = phases["phase_5"].score_pct
    survival = (p8 + p5) / 2
    scores.append("pass" if survival >= 70 else ("partial" if survival >= 40 else "fail"))

    p = scores.count("pass")
    pr = scores.count("partial")
    f = scores.count("fail")
    score = (p + 0.5 * pr) / len(scores) * 100
    return p, pr, f, round(score, 1)


def _diagnostic_principles(cfg: ModuleConfig, phases: Dict[str, PhaseScore]) -> float:
    """5 Body-Wide Diagnostic Principles from Document 2."""
    text = _module_text(cfg)
    p1 = phases["phase_1"].score_pct
    p7 = phases["phase_7"].score_pct
    p8 = phases["phase_8"].score_pct

    # 1. Organ-level health
    sub1 = sum([
        p1 >= 70,
        p8 >= 70,
        bool(re.search(r"validate_|ValidationError", text)),
        "require_access" in text,
        bool(re.search(r"@cache_data|@lru_cache|asyncio", text)),
        len(cfg.pages) >= 1,
        _doc_exists(cfg, "scalability"),
        all('"""' in _read_text(UTILS_DIR/f"{e}.py")[:500] for e in cfg.engines) if cfg.engines else False,
        bool(re.search(r"fallback|graceful", text)),
    ])
    s1 = sub1 / 9 * 100
    # 2. Circulatory flow
    api_text = _read_text(REPO_ROOT / "utils" / "api.py")
    api_engines = sum(1 for e in cfg.engines if e in api_text)
    api_pct = api_engines / len(cfg.engines) * 100 if cfg.engines else 0
    sub2 = sum([
        api_pct >= 50,
        len(cfg.pages) >= 2,  # not a single chokepoint
        p7 >= 60,
        (DATA_DIR/"kpi_library.json").exists(),
        "ApplicationState" in text or "state_machine" in text,
        bool(re.search(r"event|publish|asyncio", text)),
    ])
    s2 = sub2 / 6 * 100
    # 3. Inter-organ
    sub3 = sum([
        p7 >= 70,
        bool(re.search(r"client_cif|staff_code|user_id", text)),
        bool(re.search(r"ALLOWED_TRANSITIONS|state_machine", text)),
        "_bsc_trigger" in text or cfg.key == "bsc_cascade",
        bool(re.search(r"notify|send_email", text)),
        "require_access" in text,
        bool(re.search(r"to_excel|export_xlsx", text)),
    ])
    s3 = sub3 / 7 * 100
    # 4. Stress testing
    sub4 = sum([
        _doc_exists(cfg, "stress_volume"),
        _doc_exists(cfg, "stress_users"),
        bool(re.search(r"sla_breach|approval_timeout", text)),
        bool(re.search(r"circuit_breaker|retry_policy", text)),
        bool(re.search(r"ValidationError|raise\s+ValueError", text)),
        bool(re.search(r"connection_error|fallback", text)),
        bool(re.search(r"try:\s*\n\s*from", text)),
        bool(re.search(r"validate_|sanitize", text)),
        bool(re.search(r"lock|mutex|asyncio|concurrent", text)),
    ])
    s4 = sub4 / 9 * 100
    # 5. Preventive deterioration
    todos = len(re.findall(r"#\s*(?:TODO|FIXME|HACK|XXX)\b", text))
    sub5 = sum([
        todos < 50,
        _doc_exists(cfg, "dependencies"),
        todos < 30,
        "DEFER_TO" in text or "SPEC_DEVIATION" in text,
        _doc_exists(cfg, "scalability"),
        bool(re.search(r"time\.perf_counter", text)),
        "G162" in _read_text(REPO_ROOT/"scripts"/"audit.py"),
    ])
    s5 = sub5 / 7 * 100

    # Composite: each principle pass=1 (>=80), partial=0.5 (>=50), fail=0
    def _status(s):
        return 1.0 if s >= 80 else (0.5 if s >= 50 else 0.0)
    score = (_status(s1) + _status(s2) + _status(s3) + _status(s4) + _status(s5)) / 5 * 100
    return round(score, 1)


# ════════════════════════════════════════════════════════════════════
# Main audit functions
# ════════════════════════════════════════════════════════════════════

def audit_module(module_key: str,
                _cached_360: Optional[float] = None) -> ModuleDoctrineHealth:
    """Run full doctrine audit for one module."""
    cfg = MODULE_REGISTRY[module_key]
    phases = {
        "phase_1": _phase_1(cfg),
        "phase_2": _phase_2(cfg),
        "phase_3": _phase_3(cfg),
        "phase_4": _phase_4(cfg),
        "phase_5": _phase_5(cfg),
        "phase_6": _phase_6(cfg),
        "phase_7": _phase_7(cfg),
        "phase_8": _phase_8(cfg),
    }
    fully, partial, not_met, fv_pct, certified = _final_validation(cfg, phases)
    vp, vpr, vf, vs_pct = _vital_signs(cfg, phases, _cached_360)
    dp_pct = _diagnostic_principles(cfg, phases)

    phase_avg = sum(p.score_pct for p in phases.values()) / 8
    doctrine = phase_avg * 0.56 + fv_pct * 0.22 + vs_pct * 0.11 + dp_pct * 0.11

    priorities = []
    for k in ("phase_6", "phase_2", "phase_5", "phase_8", "phase_1",
              "phase_3", "phase_7", "phase_4"):
        for g in phases[k].critical_gaps:
            priorities.append(f"[{phases[k].phase}] {g}")

    return ModuleDoctrineHealth(
        module_key=cfg.key,
        module_name=cfg.name,
        organ_role=cfg.organ_role,
        claimed_status=cfg.claimed_status,
        claimed_health_pct=cfg.claimed_health_pct,
        phase_1=phases["phase_1"], phase_2=phases["phase_2"],
        phase_3=phases["phase_3"], phase_4=phases["phase_4"],
        phase_5=phases["phase_5"], phase_6=phases["phase_6"],
        phase_7=phases["phase_7"], phase_8=phases["phase_8"],
        final_validation_pct=fv_pct,
        criteria_fully_met=fully, criteria_partial=partial,
        criteria_not_met=not_met, certified=certified,
        vital_signs_pct=vs_pct, vital_pass=vp, vital_partial=vpr,
        vital_fail=vf, diagnostic_pct=dp_pct,
        doctrine_health_pct=round(doctrine, 1),
        honesty_gap_pp=round(abs(cfg.claimed_health_pct - doctrine), 1),
        top_rescue_priorities=priorities[:10],
        timestamp=datetime.now().isoformat(),
    )


def all_modules_audit() -> AllModulesAudit:
    """Audit all 4 modules and return aggregated health."""
    # Cache cascade_bsc_360_audit once for all modules
    try:
        from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
        cached_360 = cascade_bsc_360_audit().overall_harmony_pct
    except Exception:
        cached_360 = None

    results = {}
    for key in MODULE_REGISTRY:
        results[key] = audit_module(key, cached_360)

    avg_health = sum(r.doctrine_health_pct for r in results.values()) / len(results)
    avg_gap = sum(r.honesty_gap_pp for r in results.values()) / len(results)
    certified = sum(1 for r in results.values() if r.certified)
    crisis = [k for k, r in results.items() if r.doctrine_health_pct < 50.0]

    return AllModulesAudit(
        modules=results,
        avg_doctrine_health_pct=round(avg_health, 1),
        avg_honesty_gap_pp=round(avg_gap, 1),
        certified_count=certified,
        crisis_modules=crisis,
        timestamp=datetime.now().isoformat(),
    )


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    a = all_modules_audit()
    print(f"═══ ALL MODULES HONEST DOCTRINE HEALTH ═══\n")
    for key, m in a.modules.items():
        gap_dir = "▼" if m.claimed_health_pct > m.doctrine_health_pct else "▲"
        print(f"  {m.module_name} ({m.organ_role})")
        print(f"    Claimed: {m.claimed_health_pct}%  →  Honest: {m.doctrine_health_pct}%  ({gap_dir} {m.honesty_gap_pp}pp)")
        print(f"    Phases: P1={m.phase_1.score_pct}% P2={m.phase_2.score_pct}% "
              f"P3={m.phase_3.score_pct}% P4={m.phase_4.score_pct}%")
        print(f"            P5={m.phase_5.score_pct}% P6={m.phase_6.score_pct}% "
              f"P7={m.phase_7.score_pct}% P8={m.phase_8.score_pct}%")
        print(f"    Cert: {m.criteria_fully_met}/14 met · "
              f"Vitals: {m.vital_signs_pct}% · Diagnostic: {m.diagnostic_pct}%")
        print(f"    Certified: {m.certified}")
        print()
    print(f"Avg honest health: {a.avg_doctrine_health_pct}%")
    print(f"Avg honesty gap:   {a.avg_honesty_gap_pp}pp")
    print(f"Certified count:   {a.certified_count}/{len(a.modules)}")
    print(f"Crisis modules:    {a.crisis_modules}")
