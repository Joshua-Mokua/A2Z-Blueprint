"""utils/standards_registry.py — first-class standards registry (v10.1).

Per `docs/A2Z_V9_RETROSPECTIVE_FINAL_AND_V10_PLAN.md` Part 8: A2Z's planned
122 → 400 standards expansion is the v10.x main track. This module is the
single source of truth for the standards beyond the 122 engine modules.

Design principles:
- Pure: no I/O, no mutation of external state, no global side-effects
- Honest: each standard cites its regulatory or policy source explicitly
- Linked: standards reference engines via affected_engines tuple
- Audit-gated: G119+ verifies registry membership and required fields

References (regulatory primary sources):
- CBK Prudential Guidelines (PG/01 through PG/24)
- Central Bank of Kenya Banking Act, Cap 488
- Basel III: International framework for liquidity risk measurement,
  standards and monitoring (Dec 2010)
- BCBS publications: 189 (capital framework), 207 (Pillar 3), etc.
- IFRS: International Financial Reporting Standards (IASB)
- IAS: International Accounting Standards (IASB legacy)
- Kenya Data Protection Act, 2019 (Act No. 24 of 2019)
- IRS FATCA (US Foreign Account Tax Compliance Act)
- OECD CRS (Common Reporting Standard)
- OFAC SDN list (US Office of Foreign Assets Control)

This is NOT legal advice. The registry captures what A2Z's compliance
controls implement; bank's legal + compliance teams sign off on
applicability.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════════
# Standard dataclass
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Standard:
    """A single platform standard.

    Standards span 10 categories (engine + regulatory + technical +
    operational + architectural + KPI + data + test + process + doc +
    enhancement). v10.2 added 'enhancement' for Continuation.docx-sourced
    competitive-positioning standards.

    Each carries provenance (regulatory_source + citation), implementation
    pointers (affected_engines), and lifecycle metadata (status,
    audit_gate_id, priority_tier, implementation_batch).
    """
    standard_id: str  # e.g. "CBK-PG-01-CAR" or "ENH-119"
    category: str  # see CATEGORIES below
    name: str  # human-readable name
    description: str  # what the standard requires
    regulatory_source: str  # e.g. "CBK Prudential Guidelines" or "Continuation.docx"
    citation: str  # specific document/section
    threshold: Optional[Decimal] = None  # quantitative threshold if applicable
    threshold_unit: Optional[str] = None  # 'percent', 'KES', 'days', 'ratio'
    threshold_direction: Optional[str] = None  # 'min' (>=) or 'max' (<=)
    affected_engines: Tuple[str, ...] = ()  # engine module names
    affected_pages: Tuple[str, ...] = ()  # page module names
    audit_gate_id: Optional[str] = None  # e.g. "G119" if locked by gate
    status: str = "active"  # 'active', 'planned', 'deprecated', 'pending'
    breach_severity: str = "MEDIUM"  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    notes: str = ""  # honest acknowledgements, scope bounds
    # v10.2 additions per strategic plan Part IV:
    subcategory: str = ""  # module name: 'credit', 'rms', 'audit', 'legal', etc.
    priority_tier: str = ""  # 'A' (CRITICAL), 'B' (HIGH), 'C' (MEDIUM)
    source: str = "internal"  # 'continuation_doc', 'research_addition', 'cbk_regulatory', 'internal'
    implementation_batch: str = ""  # e.g. "v10.6+" target batch for deep impl
    global_benchmark: str = ""  # what platform/standard this benchmarks against


# ════════════════════════════════════════════════════════════════════
# Categories (per v10.0 plan Part 7 Theme 1 taxonomy)
# ════════════════════════════════════════════════════════════════════

CATEGORIES = (
    "engine",          # 122 existing engines (covered by Engine Hub)
    "regulatory",      # 60 planned (v10.1-v10.5)
    "technical",       # 40 planned (v10.6-v10.10)
    "operational",     # 30 planned (v10.11-v10.15)
    "architectural",   # 30 planned (v10.6-v10.10)
    "kpi",             # 25 planned (v10.16-v10.20)
    "data",            # 30 planned (v10.11-v10.15)
    "test",            # 20 planned (v10.16-v10.20)
    "process",         # 25 planned (v10.16-v10.20)
    "documentation",   # 18 planned (v10.16-v10.20)
    "enhancement",     # v10.2+ — Continuation.docx + research-additions for competitive positioning
)

# v10.2: enhancement subcategories (one per Continuation.docx module)
ENHANCEMENT_SUBCATEGORIES = (
    "credit",                # #119-#130 + research additions
    "rms",                   # #181-#190 + research additions (reconciliation)
    "audit",                 # #201-#210 + research additions
    "legal",                 # #221-#230
    "treasury",              # #231-#240 (v10.3)
    "revenue_assurance",     # #241-#248 (v10.3)
    "finance",               # #249-#258 (v10.3)
    "credit_model_risk",     # #259-#268 (v10.3)
    "trade_finance",         # #269-#280 (v10.3)
    "climate_esg",           # NEW - research-identified (v10.3)
    "it_digital",            # #291-#300 (v10.4)
    "bancassurance",         # #301-#310 (v10.4)
    "command_centre",        # #311-#320 (v10.4)
    "competitor_intel",      # #327-#336 (v10.4)
    "customer_360",          # #337-#348 (v10.4)
    "propositions",          # #349-#358 (v10.4)
    "specialized_segments",  # #359-#368 (v10.4)
    "partnerships",          # #369-#378 (v10.4)
    "sla_tracker",           # #379-#388 (v10.4)
    "campaigns",             # #389-#398 (v10.4)
)

PRIORITY_TIERS = ("A", "B", "C")  # A=CRITICAL, B=HIGH, C=MEDIUM

# Subcategories within regulatory (used by v10.1-v10.5)
REGULATORY_SUBCATEGORIES = (
    "cbk_prudential",  # Central Bank of Kenya Prudential Guidelines
    "basel_iii",       # Basel III framework
    "ifrs",            # International Financial Reporting Standards
    "ias",             # International Accounting Standards (legacy)
    "dpa_kenya",       # Kenya Data Protection Act 2019
    "kyc_aml",         # Know-Your-Customer + Anti-Money-Laundering
    "sanctions",       # Sanctions screening (OFAC + UN + EU + Kenya)
    "fatca_crs",       # FATCA + CRS reporting
)


# ════════════════════════════════════════════════════════════════════
# Tier 1 — CBK Prudential Guidelines (v10.1)
# ════════════════════════════════════════════════════════════════════

CBK_PRUDENTIAL_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="CBK-PG-01-CAR-CET1",
        category="regulatory",
        name="CBK Common Equity Tier 1 ratio",
        description=(
            "Common Equity Tier 1 capital must be at least 10.5% of "
            "risk-weighted assets (CBK target ratio = 8% statutory + 2.5% "
            "capital conservation buffer). Includes CET1 capital divided "
            "by total RWA per Basel III calculation."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/03 Capital Adequacy, Section 4.1",
        threshold=Decimal("10.5"),
        threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("capital_adequacy", "risk_weighted_assets"),
        affected_pages=("4_capital", "35_stress_testing"),
        audit_gate_id="G119",
        breach_severity="CRITICAL",
        notes="CBK PG/03 thresholds may be updated; verify with bank "
               "compliance team for current applicable values."),

    Standard(
        standard_id="CBK-PG-01-CAR-TOTAL",
        category="regulatory",
        name="CBK Total Capital ratio",
        description=(
            "Total capital (CET1 + AT1 + Tier 2) must be at least 14.5% "
            "of risk-weighted assets. CBK statutory minimum 10.5% + "
            "capital conservation buffer 2.5% + capital buffer 1.5%."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/03 Capital Adequacy, Section 4.2",
        threshold=Decimal("14.5"),
        threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("capital_adequacy", "risk_weighted_assets"),
        affected_pages=("4_capital",),
        audit_gate_id="G119",
        breach_severity="CRITICAL"),

    Standard(
        standard_id="CBK-PG-02-LEVERAGE",
        category="regulatory",
        name="CBK Leverage ratio",
        description=(
            "Leverage ratio = Tier 1 capital / Total exposure (on + "
            "off-balance-sheet). Must be at least 4.5%. Non-risk-weighted "
            "backstop to risk-based capital ratios."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/03 Capital Adequacy, Section 4.3",
        threshold=Decimal("4.5"),
        threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("capital_adequacy",),
        audit_gate_id="G119",
        breach_severity="HIGH"),

    Standard(
        standard_id="CBK-PG-05-LCR",
        category="regulatory",
        name="CBK Liquidity Coverage Ratio",
        description=(
            "LCR = High-Quality Liquid Assets / Net Cash Outflows over 30 "
            "days. Must be at least 100%. Ensures short-term liquidity "
            "resilience under stress scenarios."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/05 Liquidity Management, Section 5.1",
        threshold=Decimal("100"),
        threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("liquidity_risk", "treasury_intelligence"),
        affected_pages=("25_treasury",),
        audit_gate_id="G119",
        breach_severity="CRITICAL"),

    Standard(
        standard_id="CBK-PG-05-NSFR",
        category="regulatory",
        name="CBK Net Stable Funding Ratio",
        description=(
            "NSFR = Available Stable Funding / Required Stable Funding. "
            "Must be at least 100%. Long-term structural funding "
            "resilience over 1-year horizon."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/05 Liquidity Management, Section 5.2",
        threshold=Decimal("100"),
        threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("liquidity_risk", "treasury_intelligence"),
        audit_gate_id="G119",
        breach_severity="HIGH"),

    Standard(
        standard_id="CBK-PG-04-SBL",
        category="regulatory",
        name="CBK Single Borrower Limit",
        description=(
            "Maximum aggregate exposure to a single borrower or "
            "connected group of borrowers must not exceed 25% of core "
            "capital. Concentration risk control."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/04 Lending Limits, Section 4.1",
        threshold=Decimal("25"),
        threshold_unit="percent",
        threshold_direction="max",
        affected_engines=("credit_risk_scoring", "lending_intelligence"),
        affected_pages=("19_credit_monitoring", "21_loan_applications"),
        audit_gate_id="G119",
        breach_severity="CRITICAL"),

    Standard(
        standard_id="CBK-PG-04-INSIDER",
        category="regulatory",
        name="CBK Insider Lending Limit",
        description=(
            "Aggregate insider lending (directors, employees, related "
            "parties) must not exceed 100% of core capital. Individual "
            "insider exposure limits per CBK guidelines."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/04 Lending Limits, Section 5",
        threshold=Decimal("100"),
        threshold_unit="percent",
        threshold_direction="max",
        affected_engines=("related_party", "credit_risk_scoring"),
        audit_gate_id="G119",
        breach_severity="HIGH"),

    Standard(
        standard_id="CBK-PG-08-DORMANCY",
        category="regulatory",
        name="CBK Dormant Account Classification",
        description=(
            "Accounts with no customer-initiated activity for 24 months "
            "must be classified dormant. Process for reactivation, "
            "communication, and unclaimed-asset escheatment per CBK."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/08 Dormancy and Unclaimed Assets, Section 3",
        threshold=Decimal("24"),
        threshold_unit="months",
        threshold_direction="min",
        affected_engines=("dormancy_intelligence",),
        affected_pages=("34_customer360",),
        audit_gate_id="G119",
        breach_severity="MEDIUM"),

    Standard(
        standard_id="CBK-PG-09-CONSUMER-PROTECTION",
        category="regulatory",
        name="CBK Consumer Protection — Disclosure",
        description=(
            "All product terms (fees, interest rates, charges) must be "
            "disclosed to customer at point of sale + on demand. "
            "Reasonable-language disclosure requirement."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/09 Consumer Protection, Section 4",
        affected_engines=("notifications",),
        audit_gate_id="G119",
        breach_severity="HIGH"),

    Standard(
        standard_id="CBK-PG-09-COMPLAINT-RESOLUTION",
        category="regulatory",
        name="CBK Customer Complaint Resolution SLA",
        description=(
            "Customer complaints must be acknowledged within 7 days and "
            "resolved within 30 days. Bank must maintain complaint "
            "register for CBK inspection."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/09 Consumer Protection, Section 7",
        threshold=Decimal("30"),
        threshold_unit="days",
        threshold_direction="max",
        affected_engines=("queue_analytics", "issue_management"),
        audit_gate_id="G119",
        breach_severity="HIGH"),

    Standard(
        standard_id="CBK-PG-15-RISK-CLASS",
        category="regulatory",
        name="CBK Loan Risk Classification (5-tier)",
        description=(
            "Loans classified into 5 risk tiers: Normal (0-30 days past "
            "due), Watch (31-90), Substandard (91-180), Doubtful "
            "(181-365), Loss (>365). Drives provisioning rates."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/15 Risk Classification of Assets and Provisioning",
        affected_engines=(
            "ifrs9_classification", "credit_risk_scoring", "provisions"),
        affected_pages=("32_ifrs9", "20_debt_recovery"),
        audit_gate_id="G119",
        breach_severity="CRITICAL"),

    Standard(
        standard_id="CBK-PG-15-PROVISIONING",
        category="regulatory",
        name="CBK Loan Loss Provisioning Rates",
        description=(
            "Minimum provisioning rates per risk tier: Normal 1%, Watch "
            "3%, Substandard 20%, Doubtful 50%, Loss 100%. CBK floor "
            "above which IFRS 9 ECL takes precedence if higher."),
        regulatory_source="CBK Prudential Guidelines",
        citation="PG/15 Risk Classification of Assets and Provisioning",
        affected_engines=(
            "provisions", "ifrs9_classification", "credit_risk_scoring"),
        audit_gate_id="G119",
        breach_severity="CRITICAL"),
)


# ════════════════════════════════════════════════════════════════════
# v10.2 — Tier A enhancement standards (Credit + RMS + Audit + Legal)
# ════════════════════════════════════════════════════════════════════
#
# Source breakdown:
#   continuation_doc   — Joshua's Continuation.docx (#119-#130, #181-#190,
#                        #201-#210, #221-#230)
#   research_addition  — items identified via deep research (Apr-May 2026):
#                        CFPB / EU AI Act / Zest AI / Octus / IIA 2026
#                        Risk in Focus / Optro / TrustCloud.ai / Nominal /
#                        HighRadius / moveo.ai / 6clicks
#
# Per strategic plan §"Tier A modules": these are CRITICAL priority.
# All carry status='planned' and implementation_batch='v10.11+' or
# similar — registry entry now, deep work in Phase 2 (v10.6+).

# ────────────────────────────────────────────────────────────────────
# CREDIT MODULE — #119-#130 (Continuation.docx) + 7 research additions
# ────────────────────────────────────────────────────────────────────

CREDIT_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-119", category="enhancement", subcategory="credit",
        name="AI-Powered Credit Decisioning Engine",
        description=("ML-driven decision engine, sub-60s approval for 80% "
                      "of applications. SHAP/LIME explainability, dynamic "
                      "pricing by risk band, fraud detection at point of "
                      "application, affordability auto-check (1/3 rule)."),
        regulatory_source="Continuation.docx + CBK AI Guidance + EU AI Act",
        citation="#119; CBK Cybersecurity & AI Guidance; EU AI Act Art. 6",
        affected_engines=("credit_risk_scoring",),
        affected_pages=("21_loan_applications", "19_credit_monitoring"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+",
        global_benchmark="Zest AI / Blend / nCino"),
    Standard(
        standard_id="ENH-120", category="enhancement", subcategory="credit",
        name="Alternative Data Intelligence",
        description=("M-PESA, utility bills, GST, mobile-money behavioral "
                      "signals for thin-file borrowers. Targets 70%+ "
                      "unbanked population. 43% of global lenders use it."),
        regulatory_source="Continuation.docx",
        citation="#120; CIBI Inc. study on SME credit data gaps",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+",
        global_benchmark="Tala / Branch (Kenya)"),
    Standard(
        standard_id="ENH-121", category="enhancement", subcategory="credit",
        name="Digital Identity Verification (eKYC)",
        description=("Real-time ID verification + facial recognition + "
                      "liveness detection + document OCR. Sub-30-second "
                      "onboarding. IPRS integration for Kenyan IDs."),
        regulatory_source="Continuation.docx + CBK KYC requirements",
        citation="#121; CBK PG/KYC; IPRS",
        affected_engines=("kyc_aml_risk",),
        affected_pages=("34_customer360",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+",
        global_benchmark="Onfido / Jumio / Smile Identity (Africa)"),
    Standard(
        standard_id="ENH-122", category="enhancement", subcategory="credit",
        name="Real-Time Fraud Detection",
        description=("ML fraud scoring at application + transaction time. "
                      "Device fingerprinting, velocity checks, network "
                      "analysis, synthetic identity detection. <100ms."),
        regulatory_source="Continuation.docx + CBK Cybersecurity",
        citation="#122; CBK Cybersecurity Guidance Note",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+",
        global_benchmark="Feedzai / SAS Fraud Detection"),
    Standard(
        standard_id="ENH-123", category="enhancement", subcategory="credit",
        name="Dynamic Risk-Based Pricing",
        description=("Interest rate adjusted by individual risk band, "
                      "not one-size-fits-all. -2% to +5% from standard "
                      "rate per probability of default tier."),
        regulatory_source="Continuation.docx", citation="#123",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-124", category="enhancement", subcategory="credit",
        name="Explainable AI for Regulatory Compliance",
        description=("SHAP/LIME human-readable explanations for every "
                      "credit decision. CBK AI Guidance + customer-facing "
                      "adverse action rationale."),
        regulatory_source="Continuation.docx + CBK AI Guidance + CFPB",
        citation="#124; CFPB explainability mandate",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+",
        global_benchmark="Zest AI MAML / Equifax NeuroDecision"),
    Standard(
        standard_id="ENH-125", category="enhancement", subcategory="credit",
        name="End-to-End Digital Workflow Orchestration",
        description=("Enhanced swim lanes with SLA monitoring, auto-routing "
                      "by product/region/workload, conditional approvals, "
                      "digital offer letter signing."),
        regulatory_source="Continuation.docx", citation="#125",
        affected_engines=("credit_risk_scoring",),
        affected_pages=("21_loan_applications",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-126", category="enhancement", subcategory="credit",
        name="Dynamic Portfolio Monitoring & Early Warning",
        description=("Real-time portfolio health, payment-stress detection "
                      "BEFORE default, automated restructuring workflows, "
                      "segment-prioritized collections."),
        regulatory_source="Continuation.docx + CBK PG/15",
        citation="#126; CBK PG/15 Risk Classification",
        affected_engines=("credit_risk_scoring",),
        affected_pages=("19_credit_monitoring", "20_debt_recovery"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-127", category="enhancement", subcategory="credit",
        name="Digital Document Management & Verification",
        description=("OCR-based document intake (tax returns, bank "
                      "statements, pay stubs), auto-extraction, anomaly "
                      "flagging, fraud detection on uploaded artifacts."),
        regulatory_source="Continuation.docx", citation="#127",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-128", category="enhancement", subcategory="credit",
        name="Collections & Recovery Intelligence",
        description=("Risk-segmented collections (champion-challenger), "
                      "automated SMS/WhatsApp nudges, recovery agent "
                      "assignment by case score, restructuring workflow."),
        regulatory_source="Continuation.docx", citation="#128",
        affected_engines=("credit_risk_scoring", "notifications"),
        affected_pages=("20_debt_recovery",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-129", category="enhancement", subcategory="credit",
        name="Credit Bureau Integration",
        description=("Real-time TransUnion / Metropol / CreditInfo CRB "
                      "integration (Kenya). Continuous monitoring, data "
                      "quality checks, dispute workflow."),
        regulatory_source="Continuation.docx + Banking (CRB) Regulations 2020",
        citation="#129; CBK Banking (CRB) Regulations 2020",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-130", category="enhancement", subcategory="credit",
        name="Credit Committee Automation",
        description=("Digital credit memo generation, automated committee "
                      "scheduling, voting workflow, decision audit trail, "
                      "dissent capture, revote tracking."),
        regulatory_source="Continuation.docx + CBK PG/03",
        citation="#130; CBK PG/03 governance",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.11+"),
    # Research additions
    Standard(
        standard_id="ENH-CRD-R1", category="enhancement", subcategory="credit",
        name="LDA-Based Bias Search & Disparate Impact Testing",
        description=("Pre-deployment Linear Discriminant Analysis bias "
                      "testing + ongoing monitoring. CFPB / EU AI Act "
                      "regulatory expectation."),
        regulatory_source="research_addition: CFPB + EU AI Act",
        citation="CFPB ECOA disparate impact; EU AI Act Aug 2026 Art. 14",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+",
        global_benchmark="Zest AI fair lending / FairML"),
    Standard(
        standard_id="ENH-CRD-R2", category="enhancement", subcategory="credit",
        name="EU AI Act High-Risk Classification Compliance",
        description=("Conformity assessment + supervisory review for "
                      "credit-scoring AI (high-risk per EU AI Act). "
                      "Effective Aug 2026. Combines with banking "
                      "supervisory review per Recital 158."),
        regulatory_source="research_addition: EU AI Act",
        citation="EU AI Act Art. 6 + Recital 158; effective 2026-08",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+",
        notes="Applies if bank serves EU customers or is EU-affiliated"),
    Standard(
        standard_id="ENH-CRD-R3", category="enhancement", subcategory="credit",
        name="CFPB-Compliant Adverse Action Reason Codes",
        description=("Reason codes must reflect actual model inputs "
                      "(e.g. 'high number of recent credit inquiries') "
                      "NOT generic ('credit history')."),
        regulatory_source="research_addition: CFPB",
        citation="CFPB Circular 2023-03 black-box prohibition",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-CRD-R4", category="enhancement", subcategory="credit",
        name="Multi-Product Portfolio Underwriting (Group Exposure)",
        description=("For commercial lenders: related-party detection "
                      "across borrower group, multi-entity exposure "
                      "mapping, consolidated credit decisioning."),
        regulatory_source="research_addition + CBK PG/04",
        citation="Aloan SBA pattern; CBK PG/04 SBL",
        affected_engines=("credit_risk_scoring", "related_party"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+",
        global_benchmark="Aloan / UPTIQ / Abrigo"),
    Standard(
        standard_id="ENH-CRD-R5", category="enhancement", subcategory="credit",
        name="GenAI Credit Memo Drafting Agent",
        description=("Autonomous review of business loan applications, "
                      "financial statement analysis, draft initial "
                      "credit memo sections. Human officer retains final "
                      "authority."),
        regulatory_source="research_addition: Octus / Zest GenAI",
        citation="Octus / Zest AI GenAI lending 2026",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+",
        global_benchmark="Octus CreditAI / HomeVision MIRA"),
    Standard(
        standard_id="ENH-CRD-R6", category="enhancement", subcategory="credit",
        name="Continuous Portfolio Risk Monitoring (Unstructured Data)",
        description=("AI agents continuously scan news, market reports, "
                      "regulatory filings to identify emerging borrower "
                      "risks. Triggers early warning before financial "
                      "signals appear."),
        regulatory_source="research_addition: Neontri / GenAI banking",
        citation="GenAI portfolio monitoring 2026 best practice",
        affected_engines=("credit_risk_scoring", "smart_alerts"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-CRD-R7", category="enhancement", subcategory="credit",
        name="Confident Automation Pattern (80/20)",
        description=("80% high-confidence cases auto-decisioned with "
                      "rate; 20% ambiguous cases routed to analyst with "
                      "structured review pack pre-prepared."),
        regulatory_source="research_addition: Softlabs / industry pattern",
        citation="Softlabs AI underwriting pattern 2026",
        affected_engines=("credit_risk_scoring",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.11+"),
    Standard(
        standard_id="ENH-CBK-KESONIA", category="enhancement", subcategory="credit",
        name="KESONIA + Risk-Based Credit Pricing Model (RBCPM)",
        description=("Variable-rate KES loan pricing per CBK Revised RBCPM "
                      "(Aug 2025): Total Rate = KESONIA + K. KESONIA "
                      "(Kenya Shilling Overnight Interbank Average) is the "
                      "renamed overnight interbank rate, official 1 Sep 2025. "
                      "K is bank's borrower-specific risk premium. CBR "
                      "fallback when KESONIA unavailable. New variable-rate "
                      "loans: effective 1 Dec 2025. Existing variable-rate "
                      "loans: mandatory migration deadline 28 Feb 2026. "
                      "Excludes FCY loans + fixed-rate loans. KESONIA "
                      "Compounded Index for compound-in-arrears accrual."),
        regulatory_source="CBK Revised RBCPM 2025 + Banking Act §44",
        citation="CBK Revised Risk-Based Credit Pricing Model (Aug 2025)",
        affected_engines=("benchmark_rates", "risk_based_pricing",
                            "funds_transfer_pricing"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.17"),
)


# ────────────────────────────────────────────────────────────────────
# RMS RECONCILIATION — #181-#190 + 7 research additions
# ────────────────────────────────────────────────────────────────────

RMS_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-181", category="enhancement", subcategory="rms",
        name="Multi-Source Data Ingestion",
        description=("Reconcile across payment gateways, banking systems, "
                      "GL, merchant processors, card networks, internal "
                      "ledgers simultaneously. SWIFT, KEPSS, PesaLink, "
                      "M-PESA endpoints."),
        regulatory_source="Continuation.docx", citation="#181",
        affected_engines=("reconciliation", "flexcube_adapter"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+",
        global_benchmark="Duco / FloQast / HighRadius"),
    Standard(
        standard_id="ENH-182", category="enhancement", subcategory="rms",
        name="Intelligent Matching Engine",
        description=("AI-powered matching with confidence scoring. "
                      "Auto-accept high-confidence pairs, flag uncertain. "
                      "Targets 90%+ automation."),
        regulatory_source="Continuation.docx", citation="#182",
        affected_engines=("reconciliation",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+",
        global_benchmark="Nominal / HighRadius"),
    Standard(
        standard_id="ENH-183", category="enhancement", subcategory="rms",
        name="Exception Management & Workflow",
        description=("Auto-routing exceptions by type, age, and value. "
                      "SLA tracking per exception class. Aging buckets, "
                      "escalation rules, root-cause categorization."),
        regulatory_source="Continuation.docx", citation="#183",
        affected_engines=("reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-184", category="enhancement", subcategory="rms",
        name="Real-time Reconciliation Dashboard",
        description=("Live dashboard: matched count, unmatched aging, "
                      "exception categories, settlement status, SLA "
                      "breaches. Per-account, per-channel, per-day."),
        regulatory_source="Continuation.docx", citation="#184",
        affected_engines=("reconciliation",),
        affected_pages=("17_reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-185", category="enhancement", subcategory="rms",
        name="CBK Regulatory Reconciliation",
        description=("Daily settlement reconciliation per CBK requirements. "
                      "Auto-generation of CBK regulatory reports + "
                      "variance explanations. KEPSS daily settlement."),
        regulatory_source="Continuation.docx + CBK PG",
        citation="#185; CBK Daily Settlement Reconciliation",
        affected_engines=("reconciliation", "regulatory_reporting"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-186", category="enhancement", subcategory="rms",
        name="Nostro/Vostro Reconciliation",
        description=("Multi-currency Nostro/Vostro with FX revaluation, "
                      "unmatched-aging analysis, correspondent bank "
                      "performance tracking. SWIFT MT940/950 parsing."),
        regulatory_source="Continuation.docx", citation="#186",
        affected_engines=("reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-187", category="enhancement", subcategory="rms",
        name="Intercompany & Internal Suspense Reconciliation",
        description=("Subsidiary-to-subsidiary reconciliation, suspense "
                      "account aging, intercompany elimination workflow "
                      "integration with consolidation engine."),
        regulatory_source="Continuation.docx", citation="#187",
        affected_engines=("reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-188", category="enhancement", subcategory="rms",
        name="AI-Powered Reconciliation Learning",
        description=("Continuous-learning ML model that improves match "
                      "accuracy from operator dispositions. Auto-suggest "
                      "new matching rules from observed patterns."),
        regulatory_source="Continuation.docx", citation="#188",
        affected_engines=("reconciliation",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+",
        global_benchmark="moveo.ai TruePath"),
    Standard(
        standard_id="ENH-189", category="enhancement", subcategory="rms",
        name="Continuous/Real-time Reconciliation",
        description=("Continuous matching as transactions flow (not "
                      "month-end batch). Real-time variance detection "
                      "+ alerting. Aligns with FedNow/RTP/KEPSS."),
        regulatory_source="Continuation.docx + research_addition",
        citation="#189; FedNow/RTP industry trend",
        affected_engines=("reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+",
        global_benchmark="Nominal / Ledge real-time"),
    Standard(
        standard_id="ENH-190", category="enhancement", subcategory="rms",
        name="Reconciliation Audit & Certification",
        description=("Full audit trail for every match/unmatch decision, "
                      "operator certifications per period, exception "
                      "sign-off workflow, SOX-compliant evidence."),
        regulatory_source="Continuation.docx", citation="#190",
        affected_engines=("reconciliation", "audit_reporting"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.17+"),
    # Research additions
    Standard(
        standard_id="ENH-RMS-R1", category="enhancement", subcategory="rms",
        name="90%+ AI-Matching Threshold Target",
        description=("Industry best practice: 90%+ automation by AI "
                      "matching engine. Confidence-scored auto-acceptance. "
                      "Benchmarked against Nominal / HighRadius."),
        regulatory_source="research_addition: Nominal / HighRadius",
        citation="Nominal bank reconciliation 2026",
        threshold=Decimal("90"), threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("reconciliation",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-RMS-R2", category="enhancement", subcategory="rms",
        name="Memory-Layer Architecture",
        description=("Context-aware matching beyond rules. Without "
                      "context, rules-only systems hit 85-92% accuracy "
                      "ceiling. Memory layer enables learning from "
                      "historical resolutions."),
        regulatory_source="research_addition: moveo.ai pattern",
        citation="moveo.ai Financial reconciliation 2026",
        affected_engines=("reconciliation",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-RMS-R3", category="enhancement", subcategory="rms",
        name="Vendor Name Normalization Library",
        description=("Handles variations like 'AMZN MKTP' ↔ 'Amazon "
                      "Marketplace'. Critical for AI matching beyond "
                      "exact strings. Continuous learning from "
                      "user-confirmed mappings."),
        regulatory_source="research_addition: Nominal pattern",
        citation="Nominal vendor matching 2026",
        affected_engines=("reconciliation",),
        status="active", breach_severity="LOW", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-RMS-R4", category="enhancement", subcategory="rms",
        name="Timing-Difference Auto-Handling",
        description=("Recognizes transactions recorded one date, cleared "
                      "on another (28th → 2nd). Auto-tolerance per channel "
                      "(card vs ACH vs wire). No false-positive exceptions."),
        regulatory_source="research_addition: Nominal pattern",
        citation="Nominal timing differences 2026",
        affected_engines=("reconciliation",),
        status="active", breach_severity="LOW", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-RMS-R5", category="enhancement", subcategory="rms",
        name="Governed Execution Layer (TruePath-style)",
        description=("Every automated reconciliation action follows "
                      "internal policy + accounting rules + regulatory "
                      "requirements (SOX, SOC 2, GAAP). Policy-as-code."),
        regulatory_source="research_addition: moveo.ai TruePath",
        citation="moveo.ai TruePath 2026",
        affected_engines=("reconciliation", "audit_reporting"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-RMS-R6", category="enhancement", subcategory="rms",
        name="Real-time KEPSS / PesaLink Reconciliation",
        description=("Kenya equivalent of FedNow/RTP real-time settlement "
                      "reconciliation. Per-transaction settlement match, "
                      "instant variance alerts, CBK reporting integration."),
        regulatory_source="research_addition + CBK NPS Act",
        citation="CBK NPS Act + KEPSS rules; FedNow analogy",
        affected_engines=("reconciliation",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
    Standard(
        standard_id="ENH-RMS-R7", category="enhancement", subcategory="rms",
        name="Sub-Monthly Daily Reconciliation Support",
        description=("CBK requires daily settlement reconciliation. "
                      "Auto-certification for zero-balance accounts and "
                      "accounts with no period change."),
        regulatory_source="research_addition + CBK requirements",
        citation="CBK daily reconciliation; BlackLine pattern",
        threshold=Decimal("1"), threshold_unit="days",
        threshold_direction="max",
        affected_engines=("reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.17+"),
)


# ────────────────────────────────────────────────────────────────────
# AUDIT MODULE — #201-#210 + 7 research additions
# ────────────────────────────────────────────────────────────────────

AUDIT_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-201", category="enhancement", subcategory="audit",
        name="Audit Universe & Risk-Based Planning",
        description=("Comprehensive audit universe (entities, processes, "
                      "systems, third parties), risk-scored, audit cycle "
                      "planning, coverage analysis vs CBK + Basel scope."),
        regulatory_source="Continuation.docx + IIA Standards",
        citation="#201; IIA Standard 2010",
        affected_engines=("audit_universe", "audit_reporting"),
        affected_pages=("23_audit",),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-202", category="enhancement", subcategory="audit",
        name="Continuous Control Monitoring Engine",
        description=("24/7 automated control testing with real-time "
                      "evidence collection. Replaces point-in-time audits. "
                      "IIA 2026 Risk in Focus mandate."),
        regulatory_source="Continuation.docx + IIA 2026",
        citation="#202; IIA Risk in Focus 2026",
        affected_engines=("audit_universe", "issue_management"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+",
        global_benchmark="Vanta / Optro / TrustCloud.ai"),
    Standard(
        standard_id="ENH-203", category="enhancement", subcategory="audit",
        name="Electronic Working Papers",
        description=("Digital audit working papers, version control, "
                      "evidence linking, sign-off workflow, retention "
                      "per regulatory requirements (7+ years)."),
        regulatory_source="Continuation.docx", citation="#203",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-204", category="enhancement", subcategory="audit",
        name="Issue Tracking & Remediation",
        description=("Auto-creation of issues from failed controls, owner "
                      "assignment, due-date tracking, evidence-of-closure, "
                      "audit committee reporting."),
        regulatory_source="Continuation.docx", citation="#204",
        affected_engines=("issue_management", "audit_reporting"),
        affected_pages=("23_audit",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-205", category="enhancement", subcategory="audit",
        name="AI-Powered Audit Analytics",
        description=("Anomaly detection across financial transactions, "
                      "journal entry analysis, fraud pattern recognition, "
                      "sample-of-one (test 100% instead of sampling)."),
        regulatory_source="Continuation.docx", citation="#205",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-206", category="enhancement", subcategory="audit",
        name="Automated Control Testing",
        description=("Pre-defined automated tests (e.g. 'critical vulns "
                      "patched within 14 days'), pass/fail evidence "
                      "collection, control effectiveness scoring."),
        regulatory_source="Continuation.docx", citation="#206",
        threshold=Decimal("14"), threshold_unit="days",
        threshold_direction="max",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-207", category="enhancement", subcategory="audit",
        name="Auditor Dashboard & Mobile Access",
        description=("Auditor self-service dashboard, fieldwork mobile "
                      "app, evidence capture from phone, signature "
                      "workflow, offline support for branch audits."),
        regulatory_source="Continuation.docx", citation="#207",
        affected_engines=("audit_universe",),
        affected_pages=("23_audit",),
        status="planned", breach_severity="MEDIUM", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-208", category="enhancement", subcategory="audit",
        name="External Auditor Portal",
        description=("Read-only portal for KPMG/PwC/Deloitte/EY/local "
                      "audit firms. PBC list management, evidence "
                      "requests, sign-off tracking, secure document exchange."),
        regulatory_source="Continuation.docx", citation="#208",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-209", category="enhancement", subcategory="audit",
        name="Audit Committee Reporting",
        description=("Board-ready dashboards with risk-quantified metrics. "
                      "Drill-down from summary to evidence. Committee "
                      "meeting pack auto-generation, decision capture."),
        regulatory_source="Continuation.docx + CBK PG/03",
        citation="#209; CBK PG/03 governance",
        affected_engines=("audit_reporting", "board_reporting"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-210", category="enhancement", subcategory="audit",
        name="Audit Trail & Compliance Certification",
        description=("Cryptographic audit trail, hash-chain integrity, "
                      "tamper-evident logs, period-end compliance "
                      "certification, regulatory inspection-ready evidence."),
        regulatory_source="Continuation.docx + CBK + Basel",
        citation="#210; existing v8.x audit_log infrastructure",
        affected_engines=("audit_reporting", "audit_universe"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    # Research additions
    Standard(
        standard_id="ENH-AUD-R1", category="enhancement", subcategory="audit",
        name="Control-Graph Cross-Framework Mapping",
        description=("Single piece of evidence (e.g. MFA setting) maps to "
                      "multiple compliance frameworks (SOC 2, ISO 27001, "
                      "CMMC, CBK Cybersecurity, Basel III). Eliminates "
                      "duplicate evidence collection."),
        regulatory_source="research_addition: TrustCloud.ai / Optro",
        citation="TrustCloud.ai Control Graph; Optro CrossComply 2026",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-AUD-R2", category="enhancement", subcategory="audit",
        name="AI-Powered Third-Party / Vendor Risk Monitoring",
        description=("Continuous vendor risk monitoring (financial health, "
                      "cyber posture, regulatory actions). IIA 2026 "
                      "identified as critical priority. SaaS/cloud "
                      "vendor sprawl mitigation."),
        regulatory_source="research_addition: IIA 2026 + Gartner TPRM",
        citation="IIA Risk in Focus 2026; Gartner TPRM Magic Quadrant 2026",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+",
        global_benchmark="Optro / Vanta TPRM"),
    Standard(
        standard_id="ENH-AUD-R3", category="enhancement", subcategory="audit",
        name="Board-Ready Risk-Quantified Dashboards",
        description=("Move from 'Are we compliant?' to 'Where is our risk "
                      "in financial terms?'. Risk quantified in $ "
                      "exposure, remediation cost, breach probability."),
        regulatory_source="research_addition: TrustCloud.ai / Diligent",
        citation="TrustCloud.ai Assurance AI 2026",
        affected_engines=("audit_reporting", "board_reporting"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-AUD-R4", category="enhancement", subcategory="audit",
        name="Automated Remediation Ticketing Integration",
        description=("Failed control auto-creates ServiceNow / Jira / "
                      "GitLab ticket with priority based on risk score. "
                      "Closes loop from detection → assignment → fix → "
                      "verification."),
        regulatory_source="research_addition: ServiceNow GRC",
        citation="ServiceNow GRC continuous remediation 2026",
        affected_engines=("issue_management",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-AUD-R5", category="enhancement", subcategory="audit",
        name="24/7 Always-On Assurance",
        description=("Replaces annual / point-in-time audit cycles with "
                      "continuous evidence collection + validation. "
                      "IIA 2026 Risk in Focus structural shift."),
        regulatory_source="research_addition: IIA 2026 + 6clicks",
        citation="6clicks Always-On Assurance 2026",
        affected_engines=("audit_universe", "issue_management"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-AUD-R6", category="enhancement", subcategory="audit",
        name="Cybersecurity Audit Framework Integration",
        description=("IIA 2026 ranked cybersecurity #1 internal audit "
                      "priority (69% Middle East CAEs). Map to NIST CSF "
                      "/ ISO 27001 / CBK Cybersecurity Guidance Note."),
        regulatory_source="research_addition: IIA 2026 + CBK Cybersecurity",
        citation="IIA Risk in Focus 2026; CBK Cybersecurity Guidance",
        affected_engines=("audit_universe",),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-AUD-R7", category="enhancement", subcategory="audit",
        name="Connect-Validate-Respond Architecture",
        description=("Modern GRC operating model: Connect (aggregate data "
                      "sources) → Validate (automated test against control "
                      "criteria) → Respond (remediation workflow + "
                      "AI-prioritized alerting)."),
        regulatory_source="research_addition: TrustCloud.ai pattern",
        citation="FRC Continuous Monitoring 2026",
        affected_engines=(
            "audit_universe", "issue_management", "smart_alerts"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.22+"),
)


# ────────────────────────────────────────────────────────────────────
# LEGAL MODULE — #221-#230 (Continuation.docx)
# ────────────────────────────────────────────────────────────────────
# Tier C priority — implementation deferred to v10.78+ per strategic plan

LEGAL_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-221", category="enhancement", subcategory="legal",
        name="AI-Powered Contract Review",
        description=("NLP-based clause extraction, anomaly detection vs "
                      "playbook, risk-flagging, redline suggestions. "
                      "Used for loan agreements, vendor contracts, SLAs."),
        regulatory_source="Continuation.docx", citation="#221",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+",
        global_benchmark="Ironclad / Kira Systems / Lawgeex"),
    Standard(
        standard_id="ENH-222", category="enhancement", subcategory="legal",
        name="Obligation & Renewal Tracking",
        description=("Calendar of contract obligations, renewal dates, "
                      "notice periods. Auto-alerts T-90/60/30 days. "
                      "Ownership assignment + escalation."),
        regulatory_source="Continuation.docx", citation="#222",
        affected_engines=("notifications",),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-223", category="enhancement", subcategory="legal",
        name="Legal Case Management",
        description=("Case lifecycle tracking: intake → analysis → "
                      "strategy → execution → resolution. Document "
                      "linking, communication log, billable hours, outcome."),
        regulatory_source="Continuation.docx", citation="#223",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-224", category="enhancement", subcategory="legal",
        name="Outside Counsel Portal",
        description=("Self-service portal for external lawyers: matter "
                      "intake, document exchange, billing submission, "
                      "status updates. UTBMS billing codes."),
        regulatory_source="Continuation.docx", citation="#224",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-225", category="enhancement", subcategory="legal",
        name="Legal Spend Management",
        description=("Budget allocation per matter, accrual tracking, "
                      "fee negotiation patterns, variance from budget, "
                      "rate cards by firm/timekeeper."),
        regulatory_source="Continuation.docx", citation="#225",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-226", category="enhancement", subcategory="legal",
        name="Clause Library & Playbooks",
        description=("Approved clauses library, position playbooks per "
                      "agreement type, fallback positions, prohibited "
                      "clauses. Version-controlled, change-managed."),
        regulatory_source="Continuation.docx", citation="#226",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-227", category="enhancement", subcategory="legal",
        name="Legal Hold Management",
        description=("Litigation hold notices, custodian acknowledgment "
                      "tracking, document preservation enforcement, "
                      "release workflow when hold lifted."),
        regulatory_source="Continuation.docx", citation="#227",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-228", category="enhancement", subcategory="legal",
        name="Legal Dashboard",
        description=("GC dashboard: open matters by stage, spend vs "
                      "budget, case outcomes, regulatory matters, key "
                      "risks heatmap."),
        regulatory_source="Continuation.docx", citation="#228",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-229", category="enhancement", subcategory="legal",
        name="Legal Document Management",
        description=("Centralized repository for all legal documents: "
                      "agreements, court filings, regulatory submissions, "
                      "policies. Version control, retention, e-discovery."),
        regulatory_source="Continuation.docx", citation="#229",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
    Standard(
        standard_id="ENH-230", category="enhancement", subcategory="legal",
        name="Legal Analytics & Reporting",
        description=("Analytics on matter outcomes, settlement trends, "
                      "regulatory enforcement patterns, opposing counsel "
                      "patterns. Inform strategic legal positioning."),
        regulatory_source="Continuation.docx", citation="#230",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+"),
)


# ════════════════════════════════════════════════════════════════════
# v10.3 — Tier A continued + NEW Climate/ESG module
# ════════════════════════════════════════════════════════════════════
# Treasury (10+6) + Revenue Assurance (8) + Finance (10) + Credit/Model
# Risk (10) + Trade Finance (12) + Climate/ESG (13 research-identified) =
# ~69 standards. Climate/ESG critical: IFRS S1/S2 mandatory Jan 2027.

# ────────────────────────────────────────────────────────────────────
# TREASURY MODULE — #231-#240 + 6 research additions
# ────────────────────────────────────────────────────────────────────

TREASURY_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-231", category="enhancement", subcategory="treasury",
        name="NMD Behavioral Modeling & Deposit Analytics",
        description=("Behavioral modeling of non-maturity deposits (NMDs): "
                      "core/volatile decomposition, runoff curves, deposit "
                      "stickiness scoring. Inputs to LCR/NSFR + IRRBB."),
        regulatory_source="Continuation.docx + Basel BCBS",
        citation="#231; BCBS-368 IRRBB Annex 4",
        affected_engines=("treasury_intelligence", "deposit_intelligence"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-232", category="enhancement", subcategory="treasury",
        name="Intraday Liquidity & Real-Time Monitoring",
        description=("Real-time liquidity position, intraday limit "
                      "monitoring, projected end-of-day position, "
                      "settlement obligations + projected inflows."),
        regulatory_source="Continuation.docx + BCBS-248",
        citation="#232; BCBS-248 Intraday Liquidity",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-233", category="enhancement", subcategory="treasury",
        name="IRRBB Management & Dynamic ALM",
        description=("Interest Rate Risk in the Banking Book: EVE + NII "
                      "sensitivity, parallel/non-parallel shock scenarios, "
                      "dynamic ALM with behavioral overlays."),
        regulatory_source="Continuation.docx + BCBS-368",
        citation="#233; BCBS-368 IRRBB",
        affected_engines=("treasury_intelligence", "alm_engine"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-234", category="enhancement", subcategory="treasury",
        name="Treasury Products Suite (Oracle/Temenos-class)",
        description=("Comprehensive product coverage: FX (spot/forward/swap/"
                      "options), MM (placements/borrowings/CDs), fixed "
                      "income, derivatives, repo/reverse-repo."),
        regulatory_source="Continuation.docx",
        citation="#234",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+",
        global_benchmark="Oracle FLEXCUBE Treasury / Temenos T24 Treasury / Murex MX.3"),
    Standard(standard_id="ENH-235", category="enhancement", subcategory="treasury",
        name="RWA Optimization & Capital Management",
        description=("RWA calculation per Basel III standardized + IRB, "
                      "capital allocation by business line, RAROC + EVA "
                      "calculations, capital-light strategies."),
        regulatory_source="Continuation.docx + Basel III",
        citation="#235; BCBS-189",
        affected_engines=("risk_weighted_assets", "capital_adequacy"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-236", category="enhancement", subcategory="treasury",
        name="Fund Transfer Pricing (FTP) Enhancement",
        description=("Multi-curve FTP with maturity-matched yields, "
                      "liquidity premium, funding spread allocation, "
                      "behavioral term assumptions for NMDs."),
        regulatory_source="Continuation.docx + EBA FTP guidance",
        citation="#236",
        affected_engines=("ftp_engine", "treasury_intelligence"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-237", category="enhancement", subcategory="treasury",
        name="AI-Powered Cash Forecasting",
        description=("ML-based cash forecasting with 90%+ accuracy at "
                      "1-day horizon. Time-series models + behavioral "
                      "overlays. Alerts on forecast deviation."),
        regulatory_source="Continuation.docx",
        citation="#237",
        threshold=Decimal("90"), threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("treasury_intelligence", "cash_flow"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+",
        global_benchmark="Kyriba AI Cash Forecasting / HighRadius"),
    Standard(standard_id="ENH-238", category="enhancement", subcategory="treasury",
        name="Treasury Dashboard & Reporting",
        description=("Real-time treasury cockpit: cash position, FX "
                      "exposures, MM positions, IRRBB metrics, regulatory "
                      "ratios (LCR/NSFR/leverage)."),
        regulatory_source="Continuation.docx",
        citation="#238",
        affected_engines=("treasury_intelligence",),
        affected_pages=("25_treasury",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-239", category="enhancement", subcategory="treasury",
        name="Islamic Treasury Products",
        description=("Sharia-compliant treasury products: Murabaha, "
                      "Wakala, Sukuk. Profit-rate accounting, "
                      "non-interest-based liquidity instruments."),
        regulatory_source="Continuation.docx + AAOIFI standards",
        citation="#239; AAOIFI FAS 28",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="MEDIUM", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-240", category="enhancement", subcategory="treasury",
        name="Agentic Treasury Orchestration (Kyriba TAI-class)",
        description=("Autonomous agents for cash shortfall detection, "
                      "hedging strategy suggestion, payment execution, "
                      "real-time reconciliation. Human approval workflow."),
        regulatory_source="Continuation.docx + research_addition: Kyriba",
        citation="#240; Kyriba TAI 2026",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.27+",
        global_benchmark="Kyriba TAI / GTreasury"),
    # Research additions (Kyriba, Murex)
    Standard(standard_id="ENH-TRS-R1", category="enhancement", subcategory="treasury",
        name="9900+ Bank Connection Capability",
        description=("Connector library to 9900+ banks (Kyriba benchmark). "
                      "ISO 20022, SWIFT, BACS, SEPA, KEPSS. Pre-built "
                      "templates per regional payment system."),
        regulatory_source="research_addition: Kyriba",
        citation="Kyriba 2026 connectivity",
        affected_engines=("treasury_intelligence", "flexcube_adapter"),
        status="planned", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-TRS-R2", category="enhancement", subcategory="treasury",
        name="Stablecoin & Digital Asset Treasury Integration",
        description=("Treasury support for stablecoins (USDC/USDT) + "
                      "digital assets. CBK VASP Regulations 2026 enable "
                      "this. Wallet management + risk controls."),
        regulatory_source="research_addition + CBK VASP 2026",
        citation="CBK VASP Regulations 2026; KyribaLive 2026",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-TRS-R3", category="enhancement", subcategory="treasury",
        name="Money Market Fund (MMF) Direct Access",
        description=("Treasury investment automation: direct MMF access, "
                      "yield optimization across approved counterparties, "
                      "automated sweeping rules."),
        regulatory_source="research_addition: Kyriba",
        citation="KyribaLive 2026 MMF access",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="LOW", priority_tier="A",
        source="research_addition", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-TRS-R4", category="enhancement", subcategory="treasury",
        name="MX.3 Cross-Asset Trading + Treasury + Risk Platform",
        description=("Murex MX.3-style unified platform: trading + "
                      "treasury + risk + post-trade in single architecture. "
                      "Regulatory reporting + IT cost reduction."),
        regulatory_source="research_addition: Murex",
        citation="Murex MX.3 2026",
        affected_engines=("treasury_intelligence", "market_risk"),
        status="planned", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.27+",
        global_benchmark="Murex MX.3"),
    Standard(standard_id="ENH-TRS-R5", category="enhancement", subcategory="treasury",
        name="Real-Time API ERP-to-Bank Payment Journey",
        description=("Real-time API payment journey ERP→bank, eliminating "
                      "batch-payment fraud risks. Stop suspicious payments "
                      "in real time."),
        regulatory_source="research_addition: Kyriba",
        citation="Kyriba real-time payment 2026",
        affected_engines=("treasury_intelligence",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.27+"),
    Standard(standard_id="ENH-TRS-R6", category="enhancement", subcategory="treasury",
        name="Climate-Adjusted Treasury Risk Limits",
        description=("Treasury risk limits adjusted for climate exposure "
                      "(physical + transition). Aligns with CBK CRDF + "
                      "IFRS S2 climate scenario stress testing."),
        regulatory_source="research_addition + CBK CRDF",
        citation="CBK Climate Risk Disclosure Framework Apr 2025",
        affected_engines=("treasury_intelligence", "market_risk"),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.27+"),
)


# ────────────────────────────────────────────────────────────────────
# REVENUE ASSURANCE MODULE — #241-#248
# ────────────────────────────────────────────────────────────────────

REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-241", category="enhancement", subcategory="revenue_assurance",
        name="Validation Agents (Data Integrity)",
        description=("Autonomous data integrity agents: schema validation, "
                      "completeness checks, cross-system reconciliation, "
                      "anomaly detection on revenue data flows."),
        regulatory_source="Continuation.docx", citation="#241",
        affected_engines=("revenue_assurance",),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-242", category="enhancement", subcategory="revenue_assurance",
        name="Anomaly Agents (Pattern Detection)",
        description=("ML-based revenue anomaly detection: leakage patterns, "
                      "billing errors, commission miscalculation, "
                      "rate-card breaches."),
        regulatory_source="Continuation.docx", citation="#242",
        affected_engines=("revenue_assurance",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-243", category="enhancement", subcategory="revenue_assurance",
        name="Revenue Agentic Orchestrator",
        description=("Orchestration layer over validation + anomaly agents. "
                      "Auto-prioritizes findings, assigns to investigators, "
                      "tracks remediation."),
        regulatory_source="Continuation.docx", citation="#243",
        affected_engines=("revenue_assurance",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-244", category="enhancement", subcategory="revenue_assurance",
        name="Partner & Supplier Reconciliation",
        description=("Multi-party revenue share reconciliation, partner "
                      "settlement validation, supplier payment matching, "
                      "discrepancy investigation workflow."),
        regulatory_source="Continuation.docx", citation="#244",
        affected_engines=("revenue_assurance", "reconciliation"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-245", category="enhancement", subcategory="revenue_assurance",
        name="Revenue Assurance Dashboard",
        description=("Live dashboard: revenue leakage trend, top exception "
                      "categories, recovery YTD, cycle time, agent activity."),
        regulatory_source="Continuation.docx", citation="#245",
        affected_engines=("revenue_assurance",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-246", category="enhancement", subcategory="revenue_assurance",
        name="Continuous Billing Verification",
        description=("Real-time billing accuracy checks: rate vs contract, "
                      "fee + tax computation, discount application. "
                      "Alerts before invoice issued."),
        regulatory_source="Continuation.docx", citation="#246",
        affected_engines=("revenue_assurance",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-247", category="enhancement", subcategory="revenue_assurance",
        name="Commission & Incentive Assurance",
        description=("Sales commission accuracy validation, incentive plan "
                      "computation, override approval, dispute resolution."),
        regulatory_source="Continuation.docx", citation="#247",
        affected_engines=("revenue_assurance", "rm_profitability"),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
    Standard(standard_id="ENH-248", category="enhancement", subcategory="revenue_assurance",
        name="Regulatory Revenue Reporting",
        description=("Auto-generation of revenue regulatory reports (CBK + "
                      "tax authority + KRA). Reconciliation between "
                      "management + statutory reporting."),
        regulatory_source="Continuation.docx + CBK + KRA",
        citation="#248",
        affected_engines=("revenue_assurance", "regulatory_reporting"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.40+"),
)


# ────────────────────────────────────────────────────────────────────
# FINANCE MODULE — #249-#258
# ────────────────────────────────────────────────────────────────────

FINANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-249", category="enhancement", subcategory="finance",
        name="Continuous Close Orchestration Engine",
        description=("Continuous financial close (vs traditional month-end): "
                      "real-time accruals, automated journal posting, "
                      "intercompany matching. Targets <3 day close."),
        regulatory_source="Continuation.docx + Gartner Finance research",
        citation="#249; Gartner ERP-AI close 2028 forecast",
        affected_engines=("finance_close", "consolidation"),
        threshold=Decimal("3"), threshold_unit="days",
        threshold_direction="max",
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+",
        global_benchmark="FloQast / OneStream"),
    Standard(standard_id="ENH-250", category="enhancement", subcategory="finance",
        name="Intercompany Matching & Elimination",
        description=("Automated intercompany identification, matching, "
                      "and elimination journal posting. Multi-currency "
                      "with FX revaluation."),
        regulatory_source="Continuation.docx + IFRS 10",
        citation="#250; IFRS 10 Consolidation",
        affected_engines=("consolidation", "reconciliation"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-251", category="enhancement", subcategory="finance",
        name="Group Consolidation Engine",
        description=("Multi-entity consolidation per IFRS 10 + IAS 21. "
                      "Eliminations, minority interests, FX translation, "
                      "consolidation journals audit trail."),
        regulatory_source="Continuation.docx + IFRS 10 + IAS 21",
        citation="#251; IFRS 10; IAS 21",
        affected_engines=("consolidation",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-252", category="enhancement", subcategory="finance",
        name="CBK Regulatory Reporting Automation (Enhanced)",
        description=("Auto-generation of CBK returns: BSD-1 to BSD-13, "
                      "monthly + quarterly + annual returns. Variance + "
                      "reconciliation against management reports."),
        regulatory_source="Continuation.docx + CBK Banking Act",
        citation="#252; CBK BSD return formats",
        affected_engines=("regulatory_reporting", "finance_close"),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-253", category="enhancement", subcategory="finance",
        name="Predictive Financial Analytics",
        description=("ML forecasting of revenue, expenses, working capital, "
                      "P&L lines. Driver-based modeling. Variance "
                      "explanation against forecast."),
        regulatory_source="Continuation.docx", citation="#253",
        affected_engines=("forecast",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-254", category="enhancement", subcategory="finance",
        name="Finance Intelligence Dashboard (CFO View)",
        description=("Executive CFO dashboard: P&L, balance sheet, cash, "
                      "key ratios, variance to budget+forecast, drill-down "
                      "to entity/segment/product."),
        regulatory_source="Continuation.docx", citation="#254",
        affected_engines=("finance_close", "consolidation"),
        affected_pages=("8_finance",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-255", category="enhancement", subcategory="finance",
        name="Financial Statement Generator",
        description=("Auto-generation of IFRS-compliant financial "
                      "statements: balance sheet, P&L, OCI, equity, cash "
                      "flow, notes to FS. Multi-period comparatives."),
        regulatory_source="Continuation.docx + IAS 1 + IAS 7",
        citation="#255; IAS 1; IAS 7",
        affected_engines=("financial_statements", "consolidation"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-256", category="enhancement", subcategory="finance",
        name="Tax Compliance & Reporting",
        description=("Automated tax calculations (corporate tax, VAT, "
                      "withholding, excise), KRA returns, transfer pricing "
                      "documentation, deferred tax computations."),
        regulatory_source="Continuation.docx + KRA + IAS 12",
        citation="#256; KRA returns; IAS 12",
        affected_engines=("tax_compliance", "regulatory_reporting"),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-257", category="enhancement", subcategory="finance",
        name="Multi-Entity & Multi-Currency Accounting",
        description=("Multi-entity GL with company codes, multi-currency "
                      "with daily/period FX rates, IAS 21 functional/"
                      "presentation currency translation."),
        regulatory_source="Continuation.docx + IAS 21",
        citation="#257; IAS 21",
        affected_engines=("finance_close", "consolidation"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
    Standard(standard_id="ENH-258", category="enhancement", subcategory="finance",
        name="Finance Audit & Compliance",
        description=("Finance-specific audit trail, segregation of duties "
                      "enforcement, journal approval workflow, "
                      "manual-journal flagging, SOX-compliant evidence."),
        regulatory_source="Continuation.docx + SOX",
        citation="#258",
        affected_engines=("finance_close", "audit_reporting"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.42+"),
)


# ────────────────────────────────────────────────────────────────────
# CREDIT/MODEL RISK MODULE — #259-#268
# ────────────────────────────────────────────────────────────────────

CREDIT_MODEL_RISK_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-259", category="enhancement", subcategory="credit_model_risk",
        name="Model Risk Governance Framework",
        description=("End-to-end model lifecycle: development, validation, "
                      "approval, monitoring, retirement. Per OCC 2011-12 / "
                      "SR 11-7. Model inventory + risk tiering."),
        regulatory_source="Continuation.docx + OCC 2011-12 + SR 11-7",
        citation="#259; OCC 2011-12; Fed SR 11-7",
        affected_engines=("model_risk", "credit_risk_scoring"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-260", category="enhancement", subcategory="credit_model_risk",
        name="Alternative Credit Scoring (Enhanced)",
        description=("Enhanced alternative credit scoring beyond bureau: "
                      "transaction patterns + behavioral signals + "
                      "psychometrics. Validated for thin-file performance."),
        regulatory_source="Continuation.docx",
        citation="#260",
        affected_engines=("credit_risk_scoring",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-261", category="enhancement", subcategory="credit_model_risk",
        name="Continuous Model Monitoring",
        description=("PSI (Population Stability Index), CSI (Characteristic "
                      "Stability Index), KS test, accuracy drift, fairness "
                      "metrics tracked on production models continuously."),
        regulatory_source="Continuation.docx + Fed SR 11-7",
        citation="#261; SR 11-7 ongoing monitoring",
        affected_engines=("model_risk", "credit_risk_scoring"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-262", category="enhancement", subcategory="credit_model_risk",
        name="AI Model Validation & Testing Suite",
        description=("Automated validation suite: backtesting, stress "
                      "testing, sensitivity analysis, scenario testing, "
                      "challenger model comparison."),
        regulatory_source="Continuation.docx",
        citation="#262",
        affected_engines=("model_risk",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-263", category="enhancement", subcategory="credit_model_risk",
        name="Credit Decision Explainability (Enhanced)",
        description=("SHAP/LIME enhancement: counterfactual explanations, "
                      "global vs local interpretability, customer-facing "
                      "reason narrative."),
        regulatory_source="Continuation.docx + CFPB",
        citation="#263; CFPB Circular 2023-03",
        affected_engines=("model_risk", "credit_risk_scoring"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-264", category="enhancement", subcategory="credit_model_risk",
        name="Vendor Model Management",
        description=("Third-party model risk: vendor due diligence, "
                      "validation of vendor models, monitoring of "
                      "vendor model performance, contractual audit rights."),
        regulatory_source="Continuation.docx + OCC 2011-12",
        citation="#264; OCC 2011-12 vendor models",
        affected_engines=("model_risk",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-265", category="enhancement", subcategory="credit_model_risk",
        name="Continuous Bias Monitoring",
        description=("Demographic parity, equal opportunity, predictive "
                      "parity tracked across protected groups. Auto-alert "
                      "on threshold breach. CFPB / EU AI Act compliance."),
        regulatory_source="Continuation.docx + CFPB + EU AI Act",
        citation="#265; ECOA disparate impact; EU AI Act Art. 14",
        affected_engines=("model_risk", "credit_risk_scoring"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-266", category="enhancement", subcategory="credit_model_risk",
        name="Automated Model Retraining Workflow",
        description=("Drift-triggered retraining pipeline: data validation, "
                      "training, validation, approval workflow, "
                      "champion-challenger deployment."),
        regulatory_source="Continuation.docx",
        citation="#266",
        affected_engines=("model_risk",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-267", category="enhancement", subcategory="credit_model_risk",
        name="Credit Risk Appetite Integration",
        description=("Risk appetite limits hard-coded into decisioning: "
                      "concentration, vintage, sector, geography. "
                      "Real-time limit checks at application time."),
        regulatory_source="Continuation.docx + Basel III",
        citation="#267; Basel III ICAAP",
        affected_engines=("credit_risk_scoring", "risk_appetite"),
        status="planned", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
    Standard(standard_id="ENH-268", category="enhancement", subcategory="credit_model_risk",
        name="Credit Committee Governance",
        description=("Credit committee charter, voting rules, quorum, "
                      "escalation matrix, policy override tracking, "
                      "decision rationale capture."),
        regulatory_source="Continuation.docx + CBK PG/03",
        citation="#268; CBK PG/03 governance",
        affected_engines=("credit_committee",),
        status="planned", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33+"),
)


# ────────────────────────────────────────────────────────────────────
# TRADE FINANCE MODULE — #269-#280
# ────────────────────────────────────────────────────────────────────

TRADE_FINANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-269", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Core Instruments Engine",
        description=("LC, SBLC, guarantees, bills, collections, "
                      "documentary credit. Lifecycle management from "
                      "issuance to settlement."),
        regulatory_source="Continuation.docx + ICC UCP 600 + ISP98",
        citation="#269; ICC UCP 600; ISP98",
        affected_engines=("trade_finance",),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-270", category="enhancement", subcategory="trade_finance",
        name="AI-Powered Document Checking Agent",
        description=("AI agent for trade document discrepancy detection: "
                      "shipping docs, invoices, certificates of origin, "
                      "insurance. Reduces 5-day check to <1 hour."),
        regulatory_source="Continuation.docx",
        citation="#270",
        affected_engines=("trade_finance",),
        threshold=Decimal("1"), threshold_unit="hours",
        threshold_direction="max",
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+",
        global_benchmark="Conpend / Bolero / Marco Polo"),
    Standard(standard_id="ENH-271", category="enhancement", subcategory="trade_finance",
        name="Corporate Trade Portal (Front Office)",
        description=("Self-service corporate portal: LC application, "
                      "amendment, status tracking, document upload, "
                      "messaging, reporting."),
        regulatory_source="Continuation.docx",
        citation="#271",
        affected_engines=("trade_finance",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-272", category="enhancement", subcategory="trade_finance",
        name="SWIFT Integration",
        description=("MT700 (LC issuance), MT707 (LC amendment), MT760 "
                      "(guarantees), MT103 (payments). FIN message "
                      "validation + reconciliation."),
        regulatory_source="Continuation.docx + SWIFT MT/MX standards",
        citation="#272; SWIFT MT700/707/760/103",
        affected_engines=("trade_finance", "flexcube_adapter"),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-273", category="enhancement", subcategory="trade_finance",
        name="Limits & Risk Management",
        description=("Country limit, counterparty limit, product limit, "
                      "tenor limit. Real-time pre-deal limit check + "
                      "post-deal allocation."),
        regulatory_source="Continuation.docx + CBK PG/04",
        citation="#273; CBK PG/04 SBL",
        affected_engines=("trade_finance", "credit_risk_scoring"),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-274", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Compliance Engine",
        description=("Sanctions screening on parties + ports + vessels, "
                      "dual-use goods detection, SDR list checks, "
                      "anti-bribery + corruption."),
        regulatory_source="Continuation.docx + OFAC + UN + EU sanctions",
        citation="#274; OFAC SDN; UN Consolidated; EU sanctions",
        affected_engines=("trade_finance", "sanctions_screening"),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-275", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Accounting & Integration",
        description=("Trade product accounting per IFRS 9, off-balance-"
                      "sheet capture, contingent liability tracking, "
                      "integration with GL + finance close."),
        regulatory_source="Continuation.docx + IFRS 9",
        citation="#275; IFRS 9",
        affected_engines=("trade_finance", "finance_close"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-276", category="enhancement", subcategory="trade_finance",
        name="Multi-Bank Connectivity & Digital Networks",
        description=("Connect to we.trade, Marco Polo, Contour, Bolero "
                      "networks. SWIFT GPI tracking. Multi-bank "
                      "documentary credit operations."),
        regulatory_source="Continuation.docx",
        citation="#276",
        affected_engines=("trade_finance",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+",
        global_benchmark="we.trade / Marco Polo / Contour"),
    Standard(standard_id="ENH-277", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Dashboard",
        description=("Trade ops dashboard: pipeline, processing time, "
                      "exception aging, fee revenue, top corporates, "
                      "country exposure heat-map."),
        regulatory_source="Continuation.docx",
        citation="#277",
        affected_engines=("trade_finance",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-278", category="enhancement", subcategory="trade_finance",
        name="Sustainable Trade Finance",
        description=("Green / sustainable trade products: SLB tagged, "
                      "green LC, ESG-screened counterparties. Aligns "
                      "with KGFT taxonomy."),
        regulatory_source="Continuation.docx + KGFT",
        citation="#278; CBK Green Finance Taxonomy 2025",
        affected_engines=("trade_finance", "esg_intelligence"),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-279", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Mobile App",
        description=("Mobile app for corporate clients: LC application, "
                      "approval, status tracking, document upload via "
                      "phone camera."),
        regulatory_source="Continuation.docx",
        citation="#279",
        affected_engines=("trade_finance",),
        status="planned", breach_severity="LOW", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-280", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Reporting & Analytics",
        description=("Regulatory + management reporting: trade volumes, "
                      "country exposure, sector concentration, sanctions "
                      "hits, document discrepancies."),
        regulatory_source="Continuation.docx + CBK + BIS",
        citation="#280",
        affected_engines=("trade_finance", "regulatory_reporting"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
)


# ────────────────────────────────────────────────────────────────────
# CLIMATE/ESG MODULE — NEW (research-identified, not in Continuation.docx)
# ────────────────────────────────────────────────────────────────────
# CRITICAL: IFRS S1 + S2 mandatory January 2027 in Kenya per ICPAK roadmap.
# CBK published Kenya Green Finance Taxonomy (KGFT) + Climate Risk
# Disclosure Framework (CRDF) in April 2025.
# Implementation MUST start v10.6 (first Phase 2 sub-arc) to meet deadline.

CLIMATE_ESG_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-CLI-01", category="enhancement", subcategory="climate_esg",
        name="IFRS S1 General Sustainability Disclosures",
        description=("IFRS S1 disclosures on sustainability-related risks "
                      "and opportunities affecting cash flows. MANDATORY "
                      "for Public Interest Entities Jan 2027 in Kenya."),
        regulatory_source="research_addition + IFRS S1 + ICPAK Roadmap",
        citation="IFRS S1; ICPAK Sustainability Disclosure Roadmap 2023",
        affected_engines=("esg_intelligence", "regulatory_reporting"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+",
        notes="MANDATORY Jan 2027 — must implement before deadline"),
    Standard(standard_id="ENH-CLI-02", category="enhancement", subcategory="climate_esg",
        name="IFRS S2 Climate-Related Disclosures",
        description=("IFRS S2 climate-specific disclosures: physical + "
                      "transition risks, scope 1/2/3 emissions, climate "
                      "scenario analysis. MANDATORY Jan 2027."),
        regulatory_source="research_addition + IFRS S2",
        citation="IFRS S2; ICPAK Roadmap",
        affected_engines=("esg_intelligence",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+",
        notes="MANDATORY Jan 2027"),
    Standard(standard_id="ENH-CLI-03", category="enhancement", subcategory="climate_esg",
        name="Kenya Green Finance Taxonomy (KGFT) Engine",
        description=("Classification engine for green/sustainable assets "
                      "per KGFT. Tag loans/investments + track "
                      "green-finance ratio. CBK April 2025 publication."),
        regulatory_source="research_addition + CBK KGFT",
        citation="CBK Kenya Green Finance Taxonomy April 2025",
        affected_engines=("esg_intelligence", "credit_risk_scoring"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-04", category="enhancement", subcategory="climate_esg",
        name="Climate Risk Disclosure Framework (CRDF) Reporting",
        description=("Auto-generation of CRDF reports per CBK templates. "
                      "Voluntary now, mandatory Jan 2028. Quarterly "
                      "internal + annual external disclosure."),
        regulatory_source="research_addition + CBK CRDF",
        citation="CBK Climate Risk Disclosure Framework April 2025",
        affected_engines=("esg_intelligence", "regulatory_reporting"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-05", category="enhancement", subcategory="climate_esg",
        name="Physical Climate Risk Modeling (Acute + Chronic)",
        description=("Model physical climate risks: acute (floods, "
                      "droughts, storms) + chronic (sea-level rise, "
                      "temperature shifts). TCFD-aligned scenario "
                      "analysis."),
        regulatory_source="research_addition + TCFD",
        citation="TCFD Recommendations; CBK 2021 Climate Guidance",
        affected_engines=("esg_intelligence", "credit_risk_scoring"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-06", category="enhancement", subcategory="climate_esg",
        name="Transition Climate Risk Modeling",
        description=("Model transition risks: policy + technology + "
                      "market + reputation. Stranded asset analysis. "
                      "Carbon-tax sensitivity. Green-vs-brown portfolio."),
        regulatory_source="research_addition + TCFD + CBK CRDF",
        citation="TCFD; CBK CRDF",
        affected_engines=("esg_intelligence",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-07", category="enhancement", subcategory="climate_esg",
        name="Climate Scenario Stress Testing",
        description=("Run climate stress scenarios: NGFS Orderly, "
                      "Disorderly, Hot House World. Translate to credit "
                      "+ market + operational impacts. Basel framework."),
        regulatory_source="research_addition + BCBS June 2025 + NGFS",
        citation="BCBS Climate Disclosure June 2025; NGFS scenarios",
        affected_engines=("esg_intelligence", "stress_testing"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-08", category="enhancement", subcategory="climate_esg",
        name="Scope 1/2/3 Emissions Tracking",
        description=("GHG emissions: Scope 1 (own operations), Scope 2 "
                      "(purchased energy), Scope 3 (financed emissions "
                      "PCAF methodology). IFRS S2 requirement."),
        regulatory_source="research_addition + IFRS S2 + GHG Protocol + PCAF",
        citation="GHG Protocol; PCAF Standard 2022",
        affected_engines=("esg_intelligence",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-09", category="enhancement", subcategory="climate_esg",
        name="Green Asset Classification & Tagging",
        description=("Tag every loan/investment per KGFT taxonomy. "
                      "Track green-finance ratio. Enable green-finance "
                      "products + investor reporting."),
        regulatory_source="research_addition + CBK KGFT",
        citation="CBK KGFT taxonomy",
        affected_engines=("esg_intelligence", "credit_risk_scoring"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-10", category="enhancement", subcategory="climate_esg",
        name="Biodiversity & Nature-Related Risks (TNFD)",
        description=("TNFD-aligned biodiversity risk disclosure. KGFT "
                      "future expansion includes biodiversity. "
                      "Dependency + impact analysis."),
        regulatory_source="research_addition + TNFD + CBK KGFT",
        citation="TNFD Recommendations 2023; CBK KGFT future expansion",
        affected_engines=("esg_intelligence",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-11", category="enhancement", subcategory="climate_esg",
        name="Climate Governance (Board Oversight + Roles)",
        description=("Board-level climate oversight, sustainability "
                      "committee, executive responsibility, "
                      "compensation linkage. CBK 2021 guidance."),
        regulatory_source="research_addition + CBK Climate Guidance 2021",
        citation="CBK Climate-Related Risk Management Guidance 2021",
        affected_engines=("esg_intelligence", "board_reporting"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-12", category="enhancement", subcategory="climate_esg",
        name="Climate-Adjusted ECL (IFRS 9 Integration)",
        description=("Incorporate climate risk into IFRS 9 ECL calculations. "
                      "Forward-looking adjustments, sector-specific "
                      "PD/LGD shifts, scenario weights."),
        regulatory_source="research_addition + IFRS 9 + IFRS S2",
        citation="IFRS 9; IFRS S2 climate integration",
        affected_engines=("esg_intelligence", "ifrs9_classification",
                            "credit_risk_scoring"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
    Standard(standard_id="ENH-CLI-13", category="enhancement", subcategory="climate_esg",
        name="Greenwashing Risk Controls + Claim Verification",
        description=("Verify green claims with evidence, prevent "
                      "greenwashing. Auditor-verifiable green-finance "
                      "attribution. CBK anti-greenwashing requirement."),
        regulatory_source="research_addition + CBK CRDF",
        citation="CBK CRDF anti-greenwashing",
        affected_engines=("esg_intelligence", "audit_reporting"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.6+"),
)


# ════════════════════════════════════════════════════════════════════
# v10.4 — Tier B + Tier C remaining modules (10 modules, ~104 standards)
# ════════════════════════════════════════════════════════════════════
# IT (10) + Banca (10) + Command (10) + Competitor (10) + C360 (12) +
# Props (10) + Segments (10) + Partners (10) + SLA (10) + Camp (10) = 102

# ────────────────────────────────────────────────────────────────────
# IT & DIGITAL — #291-#300
# ────────────────────────────────────────────────────────────────────

IT_DIGITAL_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-291", category="enhancement", subcategory="it_digital",
        name="IT Service Management (ITSM) Framework",
        description=("ITIL-aligned ITSM: incident, problem, change, "
                      "release, asset, knowledge management. ServiceNow / "
                      "Jira Service Management integration."),
        regulatory_source="Continuation.docx + ITIL v4",
        citation="#291; ITIL v4",
        affected_engines=("issue_management",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-292", category="enhancement", subcategory="it_digital",
        name="Cloud-Native & Container Architecture",
        description=("Kubernetes-native deployment, microservices, API-first, "
                      "12-factor app principles. Multi-cloud "
                      "(AWS/Azure/GCP) portability."),
        regulatory_source="Continuation.docx",
        citation="#292",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-293", category="enhancement", subcategory="it_digital",
        name="Observability & Monitoring",
        description=("Prometheus + Grafana + Loki + Jaeger stack. "
                      "OpenTelemetry tracing. SLI/SLO/error budgets. "
                      "Already shipped foundation in v9.18."),
        regulatory_source="Continuation.docx",
        citation="#293; v9.18 observability runbook",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-294", category="enhancement", subcategory="it_digital",
        name="Disaster Recovery & Business Continuity",
        description=("RTO < 4 hours, RPO < 15 minutes. Multi-region active-"
                      "passive. Regular DR drills. CBK Cybersecurity "
                      "Guidance compliance."),
        regulatory_source="Continuation.docx + CBK Cybersecurity",
        citation="#294; CBK Cybersecurity Guidance",
        affected_engines=(),
        threshold=Decimal("4"), threshold_unit="hours",
        threshold_direction="max",
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-295", category="enhancement", subcategory="it_digital",
        name="API Gateway & Developer Portal",
        description=("Kong/Tyk API gateway, OAuth2/OpenID Connect, rate "
                      "limiting, API versioning, developer portal with "
                      "OpenAPI docs."),
        regulatory_source="Continuation.docx",
        citation="#295",
        affected_engines=("api",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-296", category="enhancement", subcategory="it_digital",
        name="Data Encryption & Security Hardening",
        description=("TLS 1.3, AES-256 at rest, HSM-backed key management, "
                      "field-level encryption for PII, secrets vault "
                      "(HashiCorp Vault / AWS KMS)."),
        regulatory_source="Continuation.docx + DPA Kenya 2019 + CBK Cyber",
        citation="#296; DPA §31; CBK Cybersecurity",
        affected_engines=(),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-297", category="enhancement", subcategory="it_digital",
        name="CI/CD & Release Automation",
        description=("GitHub Actions / GitLab CI / Jenkins pipelines. "
                      "Auto-test, auto-deploy to staging, blue-green "
                      "production deploys. Already foundation in v9.29."),
        regulatory_source="Continuation.docx",
        citation="#297; v9.29 qa-pipeline.yml",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-298", category="enhancement", subcategory="it_digital",
        name="Multi-Tenancy & White Labeling",
        description=("Tenant-scoped data isolation, configurable branding, "
                      "tenant-specific feature flags. Designed-but-deferred "
                      "per v10.0 plan."),
        regulatory_source="Continuation.docx",
        citation="#298",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-299", category="enhancement", subcategory="it_digital",
        name="Digital Banking Suite (Mobile + Web)",
        description=("React Native mobile apps, React/Next.js web. "
                      "Omnichannel session continuity, push notifications, "
                      "biometric auth."),
        regulatory_source="Continuation.docx",
        citation="#299",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
    Standard(standard_id="ENH-300", category="enhancement", subcategory="it_digital",
        name="CBK IT Compliance & Certification",
        description=("CBK Cybersecurity Guidance compliance, ISO 27001 "
                      "certification, PCI DSS for card systems, SOC 2 "
                      "Type II for SaaS components."),
        regulatory_source="Continuation.docx + CBK + ISO + PCI",
        citation="#300; CBK Cybersecurity; ISO 27001; PCI DSS",
        affected_engines=(),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.50+"),
)


# ────────────────────────────────────────────────────────────────────
# BANCASSURANCE — #301-#310
# ────────────────────────────────────────────────────────────────────

BANCASSURANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-301", category="enhancement", subcategory="bancassurance",
        name="Insurance Product Catalog & Policy Lifecycle",
        description=("Multi-insurer product catalog, policy issuance, "
                      "premium collection, renewal, claims tracking, "
                      "customer policy 360."),
        regulatory_source="Continuation.docx + IRA",
        citation="#301; IRA Kenya regulations",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-302", category="enhancement", subcategory="bancassurance",
        name="AI-Powered Insurance Recommendation Engine",
        description=("ML-based insurance product recommendation per "
                      "customer life event + risk profile + financial "
                      "capacity. Cross-sell + up-sell triggers."),
        regulatory_source="Continuation.docx",
        citation="#302",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-303", category="enhancement", subcategory="bancassurance",
        name="Insurance Partner Integration Hub",
        description=("Multi-insurer API integration: Britam, Jubilee, "
                      "Madison, ICEA, Old Mutual etc. Standard data "
                      "schema, real-time quote engine."),
        regulatory_source="Continuation.docx",
        citation="#303",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-304", category="enhancement", subcategory="bancassurance",
        name="Agentic Claims Processing",
        description=("AI agent for claims intake, document validation, "
                      "fraud screening, settlement calculation, "
                      "auto-approval below threshold."),
        regulatory_source="Continuation.docx",
        citation="#304",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-305", category="enhancement", subcategory="bancassurance",
        name="Commission Reconciliation Engine",
        description=("Multi-insurer commission reconciliation: bank's "
                      "expected vs insurer's paid. Aging, dispute "
                      "workflow, partner scorecard."),
        regulatory_source="Continuation.docx",
        citation="#305",
        affected_engines=("reconciliation",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-306", category="enhancement", subcategory="bancassurance",
        name="Customer Insurance Portfolio (360° View)",
        description=("Per-customer all-policies view across insurers, "
                      "coverage gaps, expiry alerts, claim history, "
                      "policy recommendation."),
        regulatory_source="Continuation.docx",
        citation="#306",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-307", category="enhancement", subcategory="bancassurance",
        name="RM Insurance Desktop",
        description=("RM-facing insurance workspace: customer policies, "
                      "recommendation engine, quote tools, claim "
                      "tracking, performance KPIs."),
        regulatory_source="Continuation.docx",
        citation="#307",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-308", category="enhancement", subcategory="bancassurance",
        name="IRA Compliance & Reporting",
        description=("Insurance Regulatory Authority (Kenya) compliance: "
                      "agent licensing, premium remittance, claim ratio, "
                      "regulatory return generation."),
        regulatory_source="Continuation.docx + IRA Act",
        citation="#308; IRA Insurance Act",
        affected_engines=("regulatory_reporting",),
        status="planned", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-309", category="enhancement", subcategory="bancassurance",
        name="Bancassurance Partner Scorecard",
        description=("Per-insurer partner scorecard: policy count, premium "
                      "volume, commission, claim ratio, customer "
                      "satisfaction, dispute resolution time."),
        regulatory_source="Continuation.docx",
        citation="#309",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
    Standard(standard_id="ENH-310", category="enhancement", subcategory="bancassurance",
        name="Bancassurance Executive Dashboard",
        description=("Executive bancassurance view: revenue, growth, "
                      "channel mix, top products, top RMs, partner "
                      "performance, regulatory metrics."),
        regulatory_source="Continuation.docx",
        citation="#310",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.55+"),
)


# ────────────────────────────────────────────────────────────────────
# COMMAND CENTRE — #311-#320
# ────────────────────────────────────────────────────────────────────

COMMAND_CENTRE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-311", category="enhancement", subcategory="command_centre",
        name="Strategic Pulse Dashboard",
        description=("Real-time MD/CEO dashboard: top KPIs, alerts, "
                      "trend signals, drill-down to root cause. "
                      "Mobile-first responsive."),
        regulatory_source="Continuation.docx",
        citation="#311",
        affected_engines=("board_reporting",),
        affected_pages=("28_command_centre",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-312", category="enhancement", subcategory="command_centre",
        name="Executive Alerts & Intelligent Notifications",
        description=("Smart alert routing to executives: severity-based, "
                      "context-aware, actionable. Suppresses noise. "
                      "Already foundation in v9.16 smart_alerts."),
        regulatory_source="Continuation.docx",
        citation="#312; v9.16 smart_alerts",
        affected_engines=("smart_alerts",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-313", category="enhancement", subcategory="command_centre",
        name="Predictive Intelligence & Forecasting",
        description=("ML forecasting for revenue, NPL, deposits, churn. "
                      "Driver-based scenario modeling. Confidence "
                      "intervals + variance attribution."),
        regulatory_source="Continuation.docx",
        citation="#313",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-314", category="enhancement", subcategory="command_centre",
        name="What-If Scenario Simulator",
        description=("Interactive what-if simulator: shock parameters, "
                      "see P&L / capital / liquidity impact. Tornado "
                      "charts of sensitivities."),
        regulatory_source="Continuation.docx",
        citation="#314",
        affected_engines=("stress_testing",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-315", category="enhancement", subcategory="command_centre",
        name="AI Executive Assistant (Copilot)",
        description=("Natural-language query interface for executives: "
                      "'show NPL trend by segment last quarter'. RAG "
                      "over bank's data + context-aware."),
        regulatory_source="Continuation.docx",
        citation="#315",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-316", category="enhancement", subcategory="command_centre",
        name="Mobile Command Centre",
        description=("Mobile-first executive view: critical KPIs, alerts, "
                      "approvals, briefing pack. Offline support for "
                      "travel."),
        regulatory_source="Continuation.docx",
        citation="#316",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-317", category="enhancement", subcategory="command_centre",
        name="Crisis Management Module",
        description=("Crisis playbook activation, incident command "
                      "dashboard, stakeholder notification, decision "
                      "log, after-action review."),
        regulatory_source="Continuation.docx + v9.29 INCIDENT_RESPONSE.md",
        citation="#317; v9.29 Incident Response",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-318", category="enhancement", subcategory="command_centre",
        name="Strategy Execution Tracking (Enhanced)",
        description=("Strategic initiative tracking: milestones, owner, "
                      "RAG status, dependencies, KPI linkage to BSC. "
                      "Already foundation in initiative_*."),
        regulatory_source="Continuation.docx",
        citation="#318",
        affected_engines=(
            "initiative_dependency", "initiative_impact", "initiative_resource"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-319", category="enhancement", subcategory="command_centre",
        name="Stakeholder Communication Hub",
        description=("Centralized stakeholder communication: regulators, "
                      "auditors, board members, customers. Templated "
                      "comms, audit trail, response tracking."),
        regulatory_source="Continuation.docx",
        citation="#319",
        affected_engines=("notifications",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
    Standard(standard_id="ENH-320", category="enhancement", subcategory="command_centre",
        name="Board & Committee Portal",
        description=("Secure board portal: meeting packs, papers, "
                      "voting, action items, minutes. Annotation + "
                      "private notes."),
        regulatory_source="Continuation.docx + CBK PG/03",
        citation="#320; CBK PG/03",
        affected_engines=("board_reporting",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.60+"),
)


# ────────────────────────────────────────────────────────────────────
# COMPETITOR INTEL — #327-#336
# ────────────────────────────────────────────────────────────────────

COMPETITOR_INTEL_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-327", category="enhancement", subcategory="competitor_intel",
        name="Automated Competitor Data Collection",
        description=("Automated scraping of competitor websites, app "
                      "stores, regulatory filings. NLP extraction of "
                      "rates, products, terms."),
        regulatory_source="Continuation.docx",
        citation="#327",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-328", category="enhancement", subcategory="competitor_intel",
        name="Competitive Rate Intelligence",
        description=("Daily competitor rate tracking: deposit rates, "
                      "lending rates, FX rates, fees. Trend detection, "
                      "anomaly alerts."),
        regulatory_source="Continuation.docx",
        citation="#328",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-329", category="enhancement", subcategory="competitor_intel",
        name="Competitor Digital Strategy Intelligence",
        description=("Track competitor digital launches, app updates, "
                      "feature rollouts, social-media campaigns. "
                      "Time-series analysis of digital posture."),
        regulatory_source="Continuation.docx",
        citation="#329",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-330", category="enhancement", subcategory="competitor_intel",
        name="Executive Competitive Radar Dashboard",
        description=("Executive view: market share trends, NPS comparison, "
                      "feature gaps, threats + opportunities heatmap."),
        regulatory_source="Continuation.docx",
        citation="#330",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-331", category="enhancement", subcategory="competitor_intel",
        name="Competitive Alert Engine",
        description=("Real-time alerts on competitor moves: new product, "
                      "rate change, leadership change, M&A activity. "
                      "Routed to relevant executives."),
        regulatory_source="Continuation.docx",
        citation="#331",
        affected_engines=("smart_alerts",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-332", category="enhancement", subcategory="competitor_intel",
        name="Competitive Gap Analysis",
        description=("Feature-by-feature, product-by-product gap analysis. "
                      "RAG status. Time-to-parity estimates. Roadmap "
                      "input."),
        regulatory_source="Continuation.docx",
        citation="#332",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-333", category="enhancement", subcategory="competitor_intel",
        name="Competitor Digital Positioning Map",
        description=("Visual positioning: each competitor on dimensions "
                      "(rate / digital / branch / SME-friendliness). "
                      "Track migration over time."),
        regulatory_source="Continuation.docx",
        citation="#333",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-334", category="enhancement", subcategory="competitor_intel",
        name="Strategic Response Workflow",
        description=("Workflow for responding to competitor moves: detect → "
                      "assess → recommend → approve → execute → measure. "
                      "Owner + SLA."),
        regulatory_source="Continuation.docx",
        citation="#334",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-335", category="enhancement", subcategory="competitor_intel",
        name="Competitive Intelligence API",
        description=("API to expose competitive data to other modules: "
                      "pricing engine pulls competitor rates, propositions "
                      "engine pulls feature gaps."),
        regulatory_source="Continuation.docx",
        citation="#335",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-336", category="enhancement", subcategory="competitor_intel",
        name="Competitive Intelligence Dashboard (SBU View)",
        description=("Per-SBU competitive view: who's winning what segments, "
                      "win/loss reasons, pricing pressure, product gaps."),
        regulatory_source="Continuation.docx",
        citation="#336",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
)


# ────────────────────────────────────────────────────────────────────
# CUSTOMER 360 — #337-#348
# ────────────────────────────────────────────────────────────────────

CUSTOMER_360_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-337", category="enhancement", subcategory="customer_360",
        name="Interaction Capture Framework",
        description=("Capture every customer touch: branch, ATM, call "
                      "center, app, web, email, SMS. Structured event "
                      "stream + searchable history."),
        regulatory_source="Continuation.docx",
        citation="#337",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-338", category="enhancement", subcategory="customer_360",
        name="Mobile App Interaction Tracking",
        description=("In-app event tracking: screens, taps, sessions, "
                      "abandonment, errors. Funnel + cohort analysis."),
        regulatory_source="Continuation.docx",
        citation="#338",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-339", category="enhancement", subcategory="customer_360",
        name="Branch Interaction Tracking",
        description=("Branch visit logs: queue time, service time, NPS, "
                      "purpose of visit, RM/teller assignment, outcome."),
        regulatory_source="Continuation.docx",
        citation="#339",
        affected_engines=("queue_analytics",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-340", category="enhancement", subcategory="customer_360",
        name="Customer Behavioral Profile",
        description=("Comprehensive behavioral profile: spending "
                      "patterns, channel preferences, life stage, risk "
                      "appetite, loyalty score."),
        regulatory_source="Continuation.docx",
        citation="#340",
        affected_engines=("customer_segmentation", "customer_value_segments"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-341", category="enhancement", subcategory="customer_360",
        name="Pattern Detection & Anomaly Alerting",
        description=("ML pattern detection on customer behavior: unusual "
                      "transactions, declining engagement, fraud signals. "
                      "Real-time alerts."),
        regulatory_source="Continuation.docx",
        citation="#341",
        affected_engines=("smart_alerts",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-342", category="enhancement", subcategory="customer_360",
        name="Customer Journey Mapping",
        description=("Multi-channel journey reconstruction: from "
                      "awareness to acquisition to engagement to "
                      "retention. Friction identification."),
        regulatory_source="Continuation.docx",
        citation="#342",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-343", category="enhancement", subcategory="customer_360",
        name="Customer 360 Behavioral Widget",
        description=("RM/Branch-facing widget: customer's behavioral "
                      "highlights, propensities, concerns, last touch, "
                      "next-best action."),
        regulatory_source="Continuation.docx",
        citation="#343",
        affected_engines=(),
        affected_pages=("34_customer360",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-344", category="enhancement", subcategory="customer_360",
        name="Decline Prediction & Intervention Engine",
        description=("Predict customer churn 90 days ahead. Automated "
                      "intervention triggers: outreach, retention "
                      "offers, RM assignment."),
        regulatory_source="Continuation.docx + research_addition",
        citation="#344",
        affected_engines=("churn_prediction", "customer_segmentation"),
        threshold=Decimal("90"), threshold_unit="days",
        threshold_direction="min",
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-345", category="enhancement", subcategory="customer_360",
        name="Customer Journey Optimization Engine",
        description=("ML-driven journey optimization: A/B test journey "
                      "variants, identify friction, recommend changes, "
                      "measure impact."),
        regulatory_source="Continuation.docx",
        citation="#345",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-346", category="enhancement", subcategory="customer_360",
        name="New Customer Onboarding Optimization",
        description=("Onboarding funnel analysis: drop-off, completion "
                      "rate, time-to-active, first-90-days revenue. "
                      "Optimize each step."),
        regulatory_source="Continuation.docx",
        citation="#346",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-347", category="enhancement", subcategory="customer_360",
        name="Segment-Level Behavioral Insights",
        description=("Behavioral insights aggregated by segment: women, "
                      "diaspora, asset-finance, agri, youth, SME. "
                      "Segment-specific propensities."),
        regulatory_source="Continuation.docx",
        citation="#347",
        affected_engines=("customer_segmentation",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
    Standard(standard_id="ENH-348", category="enhancement", subcategory="customer_360",
        name="RM Behavior Intelligence Widget",
        description=("RM-facing intelligence: customer behavioral signals, "
                      "engagement gap, recommended next action, "
                      "talking-points generator."),
        regulatory_source="Continuation.docx",
        citation="#348",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.65+"),
)


# ────────────────────────────────────────────────────────────────────
# PROPOSITIONS — #349-#358
# ────────────────────────────────────────────────────────────────────

PROPOSITIONS_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-349", category="enhancement", subcategory="propositions",
        name="Proposition Design Workbench",
        description=("Tool for product/proposition design: features, "
                      "pricing, eligibility, channels. Versioned, "
                      "approval workflow."),
        regulatory_source="Continuation.docx",
        citation="#349",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-350", category="enhancement", subcategory="propositions",
        name="Proposition Approval & Governance Workflow",
        description=("Multi-level approval: product head, risk, compliance, "
                      "finance, MD. Documentation, audit trail, "
                      "post-launch review."),
        regulatory_source="Continuation.docx + CBK PG (Product Governance)",
        citation="#350; CBK PG",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-351", category="enhancement", subcategory="propositions",
        name="Proposition Eligibility Engine",
        description=("Real-time eligibility check: customer + segment + "
                      "regulatory + risk gates. Returns reason codes "
                      "for ineligibility."),
        regulatory_source="Continuation.docx",
        citation="#351",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-352", category="enhancement", subcategory="propositions",
        name="Dynamic Pricing for Propositions",
        description=("ML-driven pricing per customer + market conditions. "
                      "A/B test pricing strategies. Fairness + compliance "
                      "guardrails."),
        regulatory_source="Continuation.docx",
        citation="#352",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-353", category="enhancement", subcategory="propositions",
        name="Proposition Orchestration (Next Best Proposition)",
        description=("Next-best-action engine for propositions. "
                      "Per-customer ranked list. Channel + timing "
                      "optimization."),
        regulatory_source="Continuation.docx",
        citation="#353",
        affected_engines=("cross_sell_nba",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-354", category="enhancement", subcategory="propositions",
        name="Proposition Performance Analytics",
        description=("Per-proposition KPIs: take-up rate, revenue, "
                      "profitability, customer satisfaction, attrition. "
                      "Cohort analysis."),
        regulatory_source="Continuation.docx",
        citation="#354",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-355", category="enhancement", subcategory="propositions",
        name="Proposition A/B Testing Framework",
        description=("Statistical A/B test framework: traffic split, "
                      "experiment design, significance testing, "
                      "auto-winner deployment."),
        regulatory_source="Continuation.docx",
        citation="#355",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-356", category="enhancement", subcategory="propositions",
        name="Dynamic Cohorts & Signals Engine",
        description=("Dynamic customer cohorts based on signals: life "
                      "stage, behavioral patterns, financial events. "
                      "Auto-update as signals change."),
        regulatory_source="Continuation.docx",
        citation="#356",
        affected_engines=("customer_segmentation",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-357", category="enhancement", subcategory="propositions",
        name="Proposition Presentation (Channel-Specific)",
        description=("Channel-optimized presentation: app card, web "
                      "banner, RM script, SMS template, email template. "
                      "Personalized per customer."),
        regulatory_source="Continuation.docx",
        citation="#357",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
    Standard(standard_id="ENH-358", category="enhancement", subcategory="propositions",
        name="Proposition API & Integration",
        description=("API to expose propositions to channels: app, web, "
                      "RM desktop, branch terminals. Standard schema, "
                      "real-time eligibility."),
        regulatory_source="Continuation.docx",
        citation="#358",
        affected_engines=("api",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.85+"),
)


# ────────────────────────────────────────────────────────────────────
# SPECIALIZED SEGMENTS — #359-#368
# ────────────────────────────────────────────────────────────────────

SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-359", category="enhancement", subcategory="specialized_segments",
        name="Specialized Segments Customer Tagging",
        description=("Tag customers by specialized segment: women, "
                      "diaspora, asset-finance, agri, youth, SME. "
                      "Multi-tag support, segment lifecycle."),
        regulatory_source="Continuation.docx",
        citation="#359",
        affected_engines=("customer_segmentation",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-360", category="enhancement", subcategory="specialized_segments",
        name="Women Banking Segment",
        description=("Women-specific banking proposition: products, "
                      "savings + investment guidance, business growth "
                      "support. Aligned with UN SDG 5."),
        regulatory_source="Continuation.docx",
        citation="#360",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-361", category="enhancement", subcategory="specialized_segments",
        name="Diaspora Banking Segment",
        description=("Diaspora-specific products: remittances, mortgages, "
                      "investments back home. Multi-currency. SWIFT + "
                      "M-PESA + ACH integration."),
        regulatory_source="Continuation.docx",
        citation="#361",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-362", category="enhancement", subcategory="specialized_segments",
        name="Asset Finance Segment",
        description=("Asset finance products: vehicle, machinery, "
                      "equipment. Specialized credit scoring + "
                      "collateral management."),
        regulatory_source="Continuation.docx",
        citation="#362",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-363", category="enhancement", subcategory="specialized_segments",
        name="Agri-business Segment",
        description=("Agri-specific products: crop loans, weather-indexed "
                      "insurance, supply-chain finance. Integration with "
                      "agricultural data."),
        regulatory_source="Continuation.docx + AFC Act",
        citation="#363",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-364", category="enhancement", subcategory="specialized_segments",
        name="Youth Banking Segment",
        description=("Youth (18-35) products: zero-fee accounts, "
                      "student loans, micro-saving, mobile-first UX. "
                      "Financial-literacy content."),
        regulatory_source="Continuation.docx",
        citation="#364",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-365", category="enhancement", subcategory="specialized_segments",
        name="Segment P&L & Performance Attribution",
        description=("Per-segment P&L: revenue, cost, allocated capital, "
                      "RAROC. Time-series performance. Profitability "
                      "drivers."),
        regulatory_source="Continuation.docx",
        citation="#365",
        affected_engines=("operating_segments",),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-366", category="enhancement", subcategory="specialized_segments",
        name="Segment-Specific Dashboards",
        description=("Segment-tailored dashboards: top KPIs per segment, "
                      "competitor benchmark, growth tracker, "
                      "segment-manager actions."),
        regulatory_source="Continuation.docx",
        citation="#366",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-367", category="enhancement", subcategory="specialized_segments",
        name="Segment-Specific KPI Library",
        description=("Per-segment KPIs: women — financial inclusion + "
                      "biz growth; diaspora — remittance volume + "
                      "investment uptake; etc."),
        regulatory_source="Continuation.docx",
        citation="#367",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
    Standard(standard_id="ENH-368", category="enhancement", subcategory="specialized_segments",
        name="Segment Manager Role & Permissions",
        description=("Segment manager role with cross-functional view: "
                      "P&L, customers, products, RMs assigned, "
                      "initiatives. Limited write permissions."),
        regulatory_source="Continuation.docx",
        citation="#368",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.90+"),
)


# ────────────────────────────────────────────────────────────────────
# PARTNERSHIPS & MOUs — #369-#378
# ────────────────────────────────────────────────────────────────────

PARTNERSHIPS_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-369", category="enhancement", subcategory="partnerships",
        name="Partner Master Data & Lifecycle Management",
        description=("Partner master record: type, contacts, contracts, "
                      "performance history, risk tier. Lifecycle states "
                      "(prospect → active → off-boarded)."),
        regulatory_source="Continuation.docx",
        citation="#369",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-370", category="enhancement", subcategory="partnerships",
        name="MOU & Contract Management",
        description=("Centralized MOU/contract repository, versioning, "
                      "key dates (renewal, termination), obligations + "
                      "milestones tracking."),
        regulatory_source="Continuation.docx",
        citation="#370",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-371", category="enhancement", subcategory="partnerships",
        name="Partner Performance Scorecard",
        description=("Per-partner scorecard: revenue, leads delivered, "
                      "conversion rate, customer satisfaction, "
                      "compliance score."),
        regulatory_source="Continuation.docx",
        citation="#371",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-372", category="enhancement", subcategory="partnerships",
        name="Lead & Referral Tracking",
        description=("Partner-sourced lead tracking: attribution, "
                      "conversion funnel, time-to-close, revenue "
                      "share calculation."),
        regulatory_source="Continuation.docx",
        citation="#372",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-373", category="enhancement", subcategory="partnerships",
        name="Partner Commission Automation",
        description=("Auto-calculate partner commissions based on tracked "
                      "leads + agreed splits. Auto-generate payment "
                      "instructions. Reconciliation."),
        regulatory_source="Continuation.docx",
        citation="#373",
        affected_engines=("revenue_assurance",),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-374", category="enhancement", subcategory="partnerships",
        name="Partner Portal (Self-Service)",
        description=("Partner-facing portal: lead submission, status "
                      "tracking, commission statement, document "
                      "exchange, training resources."),
        regulatory_source="Continuation.docx",
        citation="#374",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-375", category="enhancement", subcategory="partnerships",
        name="Partner Ecosystem Analytics",
        description=("Cross-partner analytics: top performers, "
                      "underperformers, geographic coverage, segment "
                      "coverage, profitability."),
        regulatory_source="Continuation.docx",
        citation="#375",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-376", category="enhancement", subcategory="partnerships",
        name="Partner Onboarding Workflow",
        description=("End-to-end onboarding: due diligence, contract, "
                      "training, system access, sandbox testing, "
                      "go-live approval."),
        regulatory_source="Continuation.docx",
        citation="#376",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-377", category="enhancement", subcategory="partnerships",
        name="Partner Risk Management",
        description=("Per-partner risk monitoring: financial health, "
                      "regulatory standing, cyber posture, customer "
                      "complaints. Auto-alert on degradation."),
        regulatory_source="Continuation.docx + research_addition (vendor risk)",
        citation="#377; IIA 2026 third-party risk",
        affected_engines=("vendor_risk",),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
    Standard(standard_id="ENH-378", category="enhancement", subcategory="partnerships",
        name="Partnership KPIs & Reporting",
        description=("Aggregate partnership KPIs: ecosystem revenue, "
                      "share of new acquisitions, customer-LTV from "
                      "partners, NPS of partner-acquired customers."),
        regulatory_source="Continuation.docx",
        citation="#378",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.92+"),
)


# ────────────────────────────────────────────────────────────────────
# SLA TRACKER — #379-#388
# ────────────────────────────────────────────────────────────────────

SLA_TRACKER_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-379", category="enhancement", subcategory="sla_tracker",
        name="SLA Registry & Definition Engine",
        description=("Central SLA registry: customer SLAs, internal SLAs, "
                      "vendor SLAs, regulatory SLAs. Definition with "
                      "metrics, targets, calc rules."),
        regulatory_source="Continuation.docx",
        citation="#379",
        affected_engines=("channel_sla",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-380", category="enhancement", subcategory="sla_tracker",
        name="SLA Monitoring Engine",
        description=("Real-time SLA monitoring: per-transaction tracking, "
                      "running compliance %, near-breach alerts, "
                      "breach detection."),
        regulatory_source="Continuation.docx",
        citation="#380",
        affected_engines=("channel_sla",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-381", category="enhancement", subcategory="sla_tracker",
        name="SLA Breach Management & Remediation",
        description=("Auto-creation of breach incidents, owner assignment, "
                      "remediation workflow, customer compensation "
                      "calculation, RCA capture."),
        regulatory_source="Continuation.docx",
        citation="#381",
        affected_engines=("issue_management",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-382", category="enhancement", subcategory="sla_tracker",
        name="SLA Dashboard",
        description=("Real-time SLA dashboard: per-channel, per-product, "
                      "per-segment compliance %. Trend analysis. "
                      "Top breaching SLAs."),
        regulatory_source="Continuation.docx",
        citation="#382",
        affected_engines=("channel_sla",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-383", category="enhancement", subcategory="sla_tracker",
        name="Regulatory SLA Reporting",
        description=("Auto-generation of regulatory SLA reports: CBK "
                      "complaint resolution (30 days), CRB dispute "
                      "resolution, etc."),
        regulatory_source="Continuation.docx + CBK PG/09",
        citation="#383; CBK PG/09",
        affected_engines=("regulatory_reporting",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-384", category="enhancement", subcategory="sla_tracker",
        name="Vendor SLA Scorecard",
        description=("Per-vendor SLA tracking: response time, uptime, "
                      "quality, penalties. Auto-credit calculation. "
                      "Performance review input."),
        regulatory_source="Continuation.docx",
        citation="#384",
        affected_engines=("vendor_risk",),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-385", category="enhancement", subcategory="sla_tracker",
        name="SLA Early Warning System",
        description=("Predictive SLA breach alerting: ML model predicts "
                      "likelihood of breach 24h ahead. Allows "
                      "intervention before breach occurs."),
        regulatory_source="Continuation.docx",
        citation="#385",
        affected_engines=("channel_sla", "smart_alerts"),
        threshold=Decimal("24"), threshold_unit="hours",
        threshold_direction="min",
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-386", category="enhancement", subcategory="sla_tracker",
        name="SLA Integration with BSC",
        description=("SLA compliance feeds Operations & Compliance pillar "
                      "of BSC. Auto-scoring per role + branch + cluster. "
                      "BSC engine integration."),
        regulatory_source="Continuation.docx",
        citation="#386",
        affected_engines=("channel_sla", "bsc_engine"),
        status="planned", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-387", category="enhancement", subcategory="sla_tracker",
        name="SLA Calendar Management",
        description=("Working-hours / public-holiday-aware SLA "
                      "calculation. Multi-region calendar support. "
                      "Custom weekend/holiday rules."),
        regulatory_source="Continuation.docx",
        citation="#387",
        affected_engines=("channel_sla",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
    Standard(standard_id="ENH-388", category="enhancement", subcategory="sla_tracker",
        name="SLA Analytics & Continuous Improvement",
        description=("Long-term SLA analytics: trend, root cause patterns, "
                      "process improvement opportunities, target "
                      "recalibration."),
        regulatory_source="Continuation.docx",
        citation="#388",
        affected_engines=("channel_sla",),
        status="planned", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.45+"),
)


# ────────────────────────────────────────────────────────────────────
# CAMPAIGNS MANAGEMENT — #389-#398
# ────────────────────────────────────────────────────────────────────

CAMPAIGNS_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-389", category="enhancement", subcategory="campaigns",
        name="Campaign Design Workbench",
        description=("Campaign design tool: target audience, message, "
                      "channels, timing, budget. Templates for common "
                      "campaign types. Approval workflow."),
        regulatory_source="Continuation.docx",
        citation="#389",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-390", category="enhancement", subcategory="campaigns",
        name="Multi-Channel Orchestration",
        description=("Coordinated multi-channel campaign execution: "
                      "email + SMS + push + social + branch + RM. "
                      "Channel preference per customer."),
        regulatory_source="Continuation.docx",
        citation="#390",
        affected_engines=("notifications",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-391", category="enhancement", subcategory="campaigns",
        name="Behavioral Trigger Engine",
        description=("Event-based campaign triggers: salary credit, "
                      "anniversary, product expiry, life event. "
                      "Real-time campaign activation."),
        regulatory_source="Continuation.docx",
        citation="#391",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-392", category="enhancement", subcategory="campaigns",
        name="Personalization Engine (AI-Powered)",
        description=("ML-based content personalization: subject lines, "
                      "messaging, offers, CTAs. Per-customer "
                      "optimization."),
        regulatory_source="Continuation.docx",
        citation="#392",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-393", category="enhancement", subcategory="campaigns",
        name="Campaign Performance Dashboard",
        description=("Real-time campaign KPIs: reach, open, click, "
                      "conversion, revenue, ROI. Per-segment, "
                      "per-channel breakdown."),
        regulatory_source="Continuation.docx",
        citation="#393",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-394", category="enhancement", subcategory="campaigns",
        name="Campaign A/B Testing",
        description=("Statistical A/B testing for campaigns: subject "
                      "line, content, timing, channel. Winning variant "
                      "auto-promotion."),
        regulatory_source="Continuation.docx",
        citation="#394",
        affected_engines=(),
        status="planned", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-395", category="enhancement", subcategory="campaigns",
        name="Campaign Approval Workflow",
        description=("Multi-stage campaign approval: marketing → "
                      "compliance → product → MD. Compliance review "
                      "of customer comms."),
        regulatory_source="Continuation.docx + CBK PG/09",
        citation="#395; CBK PG/09 consumer protection",
        affected_engines=(),
        status="planned", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-396", category="enhancement", subcategory="campaigns",
        name="Automated Campaign Execution",
        description=("Automated execution of approved campaigns: "
                      "audience build, message rendering, channel "
                      "dispatch, response capture, retry logic."),
        regulatory_source="Continuation.docx",
        citation="#396",
        affected_engines=("notifications",),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-397", category="enhancement", subcategory="campaigns",
        name="Campaign ROI Attribution",
        description=("Multi-touch attribution of campaign impact: "
                      "incremental conversions, revenue lift, "
                      "customer-lifetime impact."),
        regulatory_source="Continuation.docx",
        citation="#397",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
    Standard(standard_id="ENH-398", category="enhancement", subcategory="campaigns",
        name="Campaign Customer Journey Integration",
        description=("Campaign integration with customer journey: "
                      "trigger from journey events, contribute to "
                      "journey state, prevent over-messaging."),
        regulatory_source="Continuation.docx",
        citation="#398",
        affected_engines=(),
        status="planned", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.95+"),
)


# ════════════════════════════════════════════════════════════════════
# Master registry — concatenates all tiers
# ════════════════════════════════════════════════════════════════════

# v10.1: CBK Tier 1 (12 regulatory)
# v10.2: Credit + RMS + Audit + Legal (63 enhancement standards)
# v10.3: Treasury + Revenue + Finance + Risk + Trade + Climate/ESG (~69)
# v10.4: IT + Banca + Command + Competitor + C360 + Props + Seg + Part + SLA + Camp (~102)
STANDARDS_REGISTRY: Tuple[Standard, ...] = (
    *CBK_PRUDENTIAL_STANDARDS,                  # v10.1
    *CREDIT_ENHANCEMENT_STANDARDS,              # v10.2
    *RMS_ENHANCEMENT_STANDARDS,                 # v10.2
    *AUDIT_ENHANCEMENT_STANDARDS,               # v10.2
    *LEGAL_ENHANCEMENT_STANDARDS,               # v10.2
    *TREASURY_ENHANCEMENT_STANDARDS,            # v10.3
    *REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS,   # v10.3
    *FINANCE_ENHANCEMENT_STANDARDS,             # v10.3
    *CREDIT_MODEL_RISK_ENHANCEMENT_STANDARDS,   # v10.3
    *TRADE_FINANCE_ENHANCEMENT_STANDARDS,       # v10.3
    *CLIMATE_ESG_STANDARDS,                     # v10.3 (NEW)
    *IT_DIGITAL_ENHANCEMENT_STANDARDS,          # v10.4
    *BANCASSURANCE_ENHANCEMENT_STANDARDS,       # v10.4
    *COMMAND_CENTRE_ENHANCEMENT_STANDARDS,      # v10.4
    *COMPETITOR_INTEL_ENHANCEMENT_STANDARDS,    # v10.4
    *CUSTOMER_360_ENHANCEMENT_STANDARDS,        # v10.4
    *PROPOSITIONS_ENHANCEMENT_STANDARDS,        # v10.4
    *SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS,# v10.4
    *PARTNERSHIPS_ENHANCEMENT_STANDARDS,        # v10.4
    *SLA_TRACKER_ENHANCEMENT_STANDARDS,         # v10.4
    *CAMPAIGNS_ENHANCEMENT_STANDARDS,           # v10.4
)


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def list_standards(
    category: Optional[str] = None,
    regulatory_source: Optional[str] = None,
    affected_engine: Optional[str] = None,
) -> List[Standard]:
    """Return standards matching optional filters.

    Examples:
        list_standards(category="regulatory")           # all 12 (v10.1)
        list_standards(regulatory_source="CBK ...")     # CBK-only
        list_standards(affected_engine="capital_adequacy")  # capital-related
    """
    out = list(STANDARDS_REGISTRY)
    if category is not None:
        out = [s for s in out if s.category == category]
    if regulatory_source is not None:
        out = [s for s in out if regulatory_source.lower() in
               s.regulatory_source.lower()]
    if affected_engine is not None:
        out = [s for s in out if affected_engine in s.affected_engines]
    return out


def get_standard(standard_id: str) -> Optional[Standard]:
    """Return the standard with the given ID, or None if not found."""
    for s in STANDARDS_REGISTRY:
        if s.standard_id == standard_id:
            return s
    return None


def standards_summary() -> Dict[str, Any]:
    """Return a registry summary for admin UI / audit gates."""
    by_category: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    by_audit_gate: Dict[str, int] = {}
    by_subcategory: Dict[str, int] = {}
    by_priority_tier: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    for s in STANDARDS_REGISTRY:
        by_category[s.category] = by_category.get(s.category, 0) + 1
        by_severity[s.breach_severity] = (
            by_severity.get(s.breach_severity, 0) + 1)
        if s.audit_gate_id:
            by_audit_gate[s.audit_gate_id] = (
                by_audit_gate.get(s.audit_gate_id, 0) + 1)
        if s.subcategory:
            by_subcategory[s.subcategory] = (
                by_subcategory.get(s.subcategory, 0) + 1)
        if s.priority_tier:
            by_priority_tier[s.priority_tier] = (
                by_priority_tier.get(s.priority_tier, 0) + 1)
        if s.source:
            by_source[s.source] = by_source.get(s.source, 0) + 1
    return {
        "total": len(STANDARDS_REGISTRY),
        "target": 400,
        "by_category": by_category,
        "by_severity": by_severity,
        "by_audit_gate": by_audit_gate,
        "by_subcategory": by_subcategory,
        "by_priority_tier": by_priority_tier,
        "by_source": by_source,
        "categories_defined": list(CATEGORIES),
        "regulatory_subcategories_defined": list(REGULATORY_SUBCATEGORIES),
        "enhancement_subcategories_defined": list(ENHANCEMENT_SUBCATEGORIES),
        "priority_tiers_defined": list(PRIORITY_TIERS),
    }


def self_test() -> None:
    """Self-validation. Run as `python -m utils.standards_registry`."""
    summary = standards_summary()
    assert summary["total"] == len(STANDARDS_REGISTRY)
    assert all(s.standard_id for s in STANDARDS_REGISTRY)
    # Uniqueness
    ids = [s.standard_id for s in STANDARDS_REGISTRY]
    assert len(set(ids)) == len(ids), "Duplicate standard IDs"
    # Category validity
    for s in STANDARDS_REGISTRY:
        assert s.category in CATEGORIES, \
            f"Invalid category {s.category} on {s.standard_id}"
    # v10.1: at least 12 CBK standards
    cbk = [s for s in STANDARDS_REGISTRY
           if "CBK" in s.regulatory_source]
    assert len(cbk) >= 12, f"v10.1: expected ≥12 CBK standards, got {len(cbk)}"
    # v10.2: at least 63 enhancement standards (Credit + RMS + Audit + Legal)
    enh = [s for s in STANDARDS_REGISTRY if s.category == "enhancement"]
    assert len(enh) >= 63, \
        f"v10.2: expected ≥63 enhancement standards, got {len(enh)}"
    # v10.2: enhancement standards have required fields
    for s in enh:
        assert s.subcategory, f"{s.standard_id}: missing subcategory"
        assert s.subcategory in ENHANCEMENT_SUBCATEGORIES, \
            f"{s.standard_id}: invalid subcategory {s.subcategory}"
        assert s.priority_tier in PRIORITY_TIERS, \
            f"{s.standard_id}: invalid priority_tier {s.priority_tier}"
        assert s.source in (
            "continuation_doc", "research_addition", "cbk_regulatory",
            "internal"), \
            f"{s.standard_id}: invalid source {s.source}"
    print(f"✓ standards_registry self-test passed: total={summary['total']}, "
          f"by_category={summary['by_category']}, "
          f"by_priority_tier={summary['by_priority_tier']}")


if __name__ == "__main__":
    self_test()
