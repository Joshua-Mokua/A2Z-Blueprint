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
    "ml_governance",         # #281-#290 (v10.81+)
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
    "market_risk",           # ENH-MR-001..005 (v10.39 — Risk arc opens)
    # ── v10.133 Phase 0: subcategories for the 65 missing clusters ──
    "product",               # #131-#140 (v10.133 declared planned)
    "strategy",              # #141-#155 (v10.133 declared planned)
    "resource_optimization", # #156-#165 (v10.133 declared planned)
    "cims",                  # #166-#180 (v10.133 declared planned)
    "compliance",            # #191-#200 (v10.133 declared planned)
    "analytics_hub",         # #286-#290 (v10.133 declared planned; orthogonal to ml_governance #281-#290)
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
        status="active", breach_severity="CRITICAL", priority_tier="A",
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
        status="active", breach_severity="CRITICAL", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-205", category="enhancement", subcategory="audit",
        name="AI-Powered Audit Analytics",
        description=("Anomaly detection across financial transactions, "
                      "journal entry analysis, fraud pattern recognition, "
                      "sample-of-one (test 100% instead of sampling)."),
        regulatory_source="Continuation.docx", citation="#205",
        affected_engines=("audit_universe",),
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.22+"),
    Standard(
        standard_id="ENH-208", category="enhancement", subcategory="audit",
        name="External Auditor Portal",
        description=("Read-only portal for KPMG/PwC/Deloitte/EY/local "
                      "audit firms. PBC list management, evidence "
                      "requests, sign-off tracking, secure document exchange."),
        regulatory_source="Continuation.docx", citation="#208",
        affected_engines=("audit_universe",),
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="CRITICAL", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="CRITICAL", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="CRITICAL", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="A",
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
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.78+",
        global_benchmark="Ironclad / Kira Systems / Lawgeex"),
    Standard(
        standard_id="ENH-222", category="enhancement", subcategory="legal",
        name="Obligation & Renewal Tracking",
        description=("Calendar of contract obligations, renewal dates, "
                      "notice periods. Auto-alerts T-90/60/30 days. "
                      "Ownership assignment + escalation."),
        regulatory_source="Continuation.docx", citation="#222",
        affected_engines=("obligation_tracking",),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.170"),
    Standard(
        standard_id="ENH-223", category="enhancement", subcategory="legal",
        name="Legal Case Management",
        description=("Case lifecycle tracking: intake → analysis → "
                      "strategy → execution → resolution. Document "
                      "linking, communication log, billable hours, outcome."),
        regulatory_source="Continuation.docx", citation="#223",
        affected_engines=("legal_case_management",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.171"),
    Standard(
        standard_id="ENH-224", category="enhancement", subcategory="legal",
        name="Outside Counsel Portal",
        description=("Self-service portal for external lawyers: matter "
                      "intake, document exchange, billing submission, "
                      "status updates. UTBMS billing codes."),
        regulatory_source="Continuation.docx", citation="#224",
        affected_engines=("outside_counsel_portal",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.172"),
    Standard(
        standard_id="ENH-225", category="enhancement", subcategory="legal",
        name="Legal Spend Management",
        description=("Budget allocation per matter, accrual tracking, "
                      "fee negotiation patterns, variance from budget, "
                      "rate cards by firm/timekeeper."),
        regulatory_source="Continuation.docx", citation="#225",
        affected_engines=("legal_spend_management",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.173"),
    Standard(
        standard_id="ENH-226", category="enhancement", subcategory="legal",
        name="Clause Library & Playbooks",
        description=("Approved clauses library, position playbooks per "
                      "agreement type, fallback positions, prohibited "
                      "clauses. Version-controlled, change-managed."),
        regulatory_source="Continuation.docx", citation="#226",
        affected_engines=("clause_library",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.174"),
    Standard(
        standard_id="ENH-227", category="enhancement", subcategory="legal",
        name="Legal Hold Management",
        description=("Litigation hold notices, custodian acknowledgment "
                      "tracking, document preservation enforcement, "
                      "release workflow when hold lifted."),
        regulatory_source="Continuation.docx", citation="#227",
        affected_engines=("legal_hold_management",),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.175"),
    Standard(
        standard_id="ENH-228", category="enhancement", subcategory="legal",
        name="Legal Dashboard",
        description=("GC dashboard: open matters by stage, spend vs "
                      "budget, case outcomes, regulatory matters, key "
                      "risks heatmap."),
        regulatory_source="Continuation.docx", citation="#228",
        affected_engines=("legal_dashboard",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.176"),
    Standard(
        standard_id="ENH-229", category="enhancement", subcategory="legal",
        name="Legal Document Management",
        description=("Centralized repository for all legal documents: "
                      "agreements, court filings, regulatory submissions, "
                      "policies. Version control, retention, e-discovery."),
        regulatory_source="Continuation.docx", citation="#229",
        affected_engines=("legal_document_management",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.177"),
    Standard(
        standard_id="ENH-230", category="enhancement", subcategory="legal",
        name="Legal Analytics & Reporting",
        description=("Analytics on matter outcomes, settlement trends, "
                     "regulatory enforcement patterns, opposing counsel "
                     "patterns. Inform strategic legal positioning."),
        regulatory_source="Continuation.docx", citation="#230",
        affected_engines=("legal_analytics",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.178"),
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
        affected_engines=("treasury_intelligence", "deposit_intelligence", "treasury_alm"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33"),
    Standard(standard_id="ENH-232", category="enhancement", subcategory="treasury",
        name="Intraday Liquidity & Real-Time Monitoring",
        description=("Real-time liquidity position, intraday limit "
                      "monitoring, projected end-of-day position, "
                      "settlement obligations + projected inflows."),
        regulatory_source="Continuation.docx + BCBS-248",
        citation="#232; BCBS-248 Intraday Liquidity",
        affected_engines=("treasury_intelligence", "treasury_alm"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33"),
    Standard(standard_id="ENH-233", category="enhancement", subcategory="treasury",
        name="IRRBB Management & Dynamic ALM",
        description=("Interest Rate Risk in the Banking Book: EVE + NII "
                      "sensitivity, parallel/non-parallel shock scenarios, "
                      "dynamic ALM with behavioral overlays."),
        regulatory_source="Continuation.docx + BCBS-368",
        citation="#233; BCBS-368 IRRBB",
        affected_engines=("treasury_intelligence", "treasury_alm"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.33"),
    Standard(standard_id="ENH-234", category="enhancement", subcategory="treasury",
        name="Treasury Products Suite (Oracle/Temenos-class)",
        description=("Comprehensive product coverage: FX (spot/forward/swap/"
                      "options), MM (placements/borrowings/CDs), fixed "
                      "income, derivatives, repo/reverse-repo."),
        regulatory_source="Continuation.docx",
        citation="#234",
        affected_engines=("treasury_intelligence", "treasury_products"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.34",
        global_benchmark="Oracle FLEXCUBE Treasury / Temenos T24 Treasury / Murex MX.3"),
    Standard(standard_id="ENH-235", category="enhancement", subcategory="treasury",
        name="RWA Optimization & Capital Management",
        description=("RWA calculation per Basel III standardized + IRB, "
                      "capital allocation by business line, RAROC + EVA "
                      "calculations, capital-light strategies."),
        regulatory_source="Continuation.docx + Basel III",
        citation="#235; BCBS-189",
        affected_engines=("risk_weighted_assets", "capital_adequacy", "rwa_optimization"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.34"),
    Standard(standard_id="ENH-236", category="enhancement", subcategory="treasury",
        name="Fund Transfer Pricing (FTP) Enhancement",
        description=("Multi-curve FTP with maturity-matched yields, "
                      "liquidity premium, funding spread allocation, "
                      "behavioral term assumptions for NMDs."),
        regulatory_source="Continuation.docx + EBA FTP guidance",
        citation="#236",
        affected_engines=("treasury_intelligence", "fund_transfer_pricing"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.34"),
    Standard(standard_id="ENH-237", category="enhancement", subcategory="treasury",
        name="AI-Powered Cash Forecasting",
        description=("ML-based cash forecasting with 90%+ accuracy at "
                      "1-day horizon. Time-series models + behavioral "
                      "overlays. Alerts on forecast deviation."),
        regulatory_source="Continuation.docx",
        citation="#237",
        threshold=Decimal("90"), threshold_unit="percent",
        threshold_direction="min",
        affected_engines=("treasury_intelligence", "cash_forecasting"),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.35",
        global_benchmark="Kyriba AI Cash Forecasting / HighRadius"),
    Standard(standard_id="ENH-238", category="enhancement", subcategory="treasury",
        name="Treasury Dashboard & Reporting",
        description=("Real-time treasury cockpit: cash position, FX "
                      "exposures, MM positions, IRRBB metrics, regulatory "
                      "ratios (LCR/NSFR/leverage)."),
        regulatory_source="Continuation.docx",
        citation="#238",
        affected_engines=("treasury_intelligence", "treasury_dashboard"),
        affected_pages=("25_treasury",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.35"),
    Standard(standard_id="ENH-239", category="enhancement", subcategory="treasury",
        name="Islamic Treasury Products",
        description=("Sharia-compliant treasury products: Murabaha, "
                      "Wakala, Sukuk. Profit-rate accounting, "
                      "non-interest-based liquidity instruments."),
        regulatory_source="Continuation.docx + AAOIFI standards",
        citation="#239; AAOIFI FAS 28",
        affected_engines=("treasury_intelligence", "islamic_treasury",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.37"),
    Standard(standard_id="ENH-240", category="enhancement", subcategory="treasury",
        name="Agentic Treasury Orchestration (Kyriba TAI-class)",
        description=("Autonomous agents for cash shortfall detection, "
                      "hedging strategy suggestion, payment execution, "
                      "real-time reconciliation. Human approval workflow."),
        regulatory_source="Continuation.docx + research_addition: Kyriba",
        citation="#240; Kyriba TAI 2026",
        affected_engines=("treasury_intelligence", "treasury_agents",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.37",
        global_benchmark="Kyriba TAI / GTreasury"),
    # Research additions (Kyriba, Murex)
    Standard(standard_id="ENH-TRS-R1", category="enhancement", subcategory="treasury",
        name="9900+ Bank Connection Capability",
        description=("Connector library to 9900+ banks (Kyriba benchmark). "
                      "ISO 20022, SWIFT, BACS, SEPA, KEPSS. Pre-built "
                      "templates per regional payment system."),
        regulatory_source="research_addition: Kyriba",
        citation="Kyriba 2026 connectivity",
        affected_engines=("treasury_intelligence", "flexcube_adapter", "treasury_connectivity",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.37"),
    Standard(standard_id="ENH-TRS-R2", category="enhancement", subcategory="treasury",
        name="Stablecoin & Digital Asset Treasury Integration",
        description=("Treasury support for stablecoins (USDC/USDT) + "
                      "digital assets. CBK VASP Regulations 2026 enable "
                      "this. Wallet management + risk controls."),
        regulatory_source="research_addition + CBK VASP 2026",
        citation="CBK VASP Regulations 2026; KyribaLive 2026",
        affected_engines=("treasury_intelligence", "treasury_digital_assets",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.37"),
    Standard(standard_id="ENH-TRS-R3", category="enhancement", subcategory="treasury",
        name="Money Market Fund (MMF) Direct Access",
        description=("Treasury investment automation: direct MMF access, "
                      "yield optimization across approved counterparties, "
                      "automated sweeping rules."),
        regulatory_source="research_addition: Kyriba",
        citation="KyribaLive 2026 MMF access",
        affected_engines=("treasury_intelligence", "treasury_connectivity",),
        status="active", breach_severity="LOW", priority_tier="A",
        source="research_addition", implementation_batch="v10.37"),
    Standard(standard_id="ENH-TRS-R4", category="enhancement", subcategory="treasury",
        name="MX.3 Cross-Asset Trading + Treasury + Risk Platform",
        description=("Murex MX.3-style unified platform: trading + "
                      "treasury + risk + post-trade in single architecture. "
                      "Regulatory reporting + IT cost reduction."),
        regulatory_source="research_addition: Murex",
        citation="Murex MX.3 2026",
        affected_engines=("treasury_intelligence", "market_risk", "treasury_unified_platform",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.37",
        global_benchmark="Murex MX.3"),
    Standard(standard_id="ENH-TRS-R5", category="enhancement", subcategory="treasury",
        name="Real-Time API ERP-to-Bank Payment Journey",
        description=("Real-time API payment journey ERP→bank, eliminating "
                      "batch-payment fraud risks. Stop suspicious payments "
                      "in real time."),
        regulatory_source="research_addition: Kyriba",
        citation="Kyriba real-time payment 2026",
        affected_engines=("treasury_intelligence", "treasury_connectivity",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.37"),
    Standard(standard_id="ENH-TRS-R6", category="enhancement", subcategory="treasury",
        name="Climate-Adjusted Treasury Risk Limits",
        description=("Treasury risk limits adjusted for climate exposure "
                      "(physical + transition). Aligns with CBK CRDF + "
                      "IFRS S2 climate scenario stress testing."),
        regulatory_source="research_addition + CBK CRDF",
        citation="CBK Climate Risk Disclosure Framework Apr 2025",
        affected_engines=("treasury_intelligence", "market_risk", "climate_treasury_limits",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.37"),

    # ─── Market Risk foundation (v10.39 — Risk arc opens) ───────────────
    Standard(standard_id="ENH-MR-001", category="enhancement", subcategory="market_risk",
        name="VaR Computation Framework",
        description=("Three-methodology Value-at-Risk: parametric "
                      "(variance-covariance with Normal returns assumption), "
                      "historical (empirical percentile via linear interpolation), "
                      "and Monte Carlo simulation. Confidence levels: 95%, 97.5%, "
                      "99%. Holding-period scaling via √T per Basel Market Risk "
                      "Amendment 1996. Per Rule 1, every VaRResult surfaces "
                      "methodology + confidence + horizon + portfolio_value + "
                      "return distribution summary + framework refs."),
        regulatory_source="BCBS d352 FRTB + Basel MRA 1996 + CBK PG/04",
        citation="BCBS d352 §A.6 IMA",
        affected_engines=("market_risk_var",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.39"),
    Standard(standard_id="ENH-MR-002", category="enhancement", subcategory="market_risk",
        name="Expected Shortfall (FRTB-IMA)",
        description=("Expected Shortfall (CVaR / Tail VaR) at FRTB-IMA "
                      "97.5% confidence — average of returns in the tail "
                      "beyond VaR. Computed under all three VaR "
                      "methodologies. ES is monotonic with VaR (ES ≥ VaR by "
                      "construction) and is sub-additive, supporting "
                      "diversification. Reported as a positive loss number "
                      "in KES."),
        regulatory_source="BCBS d352 FRTB-IMA",
        citation="BCBS d352 §A.6.5",
        affected_engines=("market_risk_var",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.39"),
    Standard(standard_id="ENH-MR-003", category="enhancement", subcategory="market_risk",
        name="Sensitivity-Based Measures",
        description=("DV01 (delta of bond PV per +1bp parallel shift, "
                      "modified-duration approximation + convexity term), "
                      "FX delta (KES value × 1% relative shift), equity "
                      "delta (beta-adjusted market-value × 1%), curvature "
                      "(second-order term per FRTB SBM). Aggregated by "
                      "RiskFactor and RiskFactorClass. Per Rule 1, every "
                      "Sensitivity carries factor + delta + curvature + "
                      "units + framework refs."),
        regulatory_source="BCBS d352 FRTB SBM §A.5 + IFRS 7 §40",
        citation="BCBS d352 §A.5",
        affected_engines=("market_risk_sensitivities",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.39"),
    Standard(standard_id="ENH-MR-004", category="enhancement", subcategory="market_risk",
        name="Risk Factor Taxonomy & Stress Scenarios",
        description=("23 RiskFactor enums across 5 RiskFactorClass buckets "
                      "(IR / FX / Equity / Commodity / Credit Spread). "
                      "9 pre-built StressScenarios: 6 BCBS d368 IRRBB "
                      "shocks (parallel up/down 200bp, short up/down 250bp, "
                      "steepener, flattener) + 3 internal/CBK scenarios "
                      "(USD/KES ±15%, equity crash 30%). FactorShock supports "
                      "ABSOLUTE_BPS / ABSOLUTE_PCT / RELATIVE_PCT shock "
                      "types."),
        regulatory_source="BCBS d368 IRRBB §K + CBK PG/04",
        citation="BCBS d368 §K",
        affected_engines=("market_risk_factors",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.39"),
    Standard(standard_id="ENH-MR-005", category="enhancement", subcategory="market_risk",
        name="VaR Backtesting (Kupiec + Christoffersen)",
        description=("Kupiec POF (Proportion of Failures) test for "
                      "unconditional coverage — likelihood ratio against "
                      "expected breach rate (1−α) under χ²(1). "
                      "Christoffersen 1998 independence test — 2×2 "
                      "transition matrix for breach clustering, also χ²(1). "
                      "Significance levels 1%, 5%, 10% supported with "
                      "hard-coded χ² critical values (no scipy dependency). "
                      "Per Rule 1, BacktestResult surfaces test_name + "
                      "n_observations + n_breaches + expected_breaches + "
                      "test_statistic + critical_value + verdict."),
        regulatory_source="Kupiec 1995, Christoffersen 1998, BCBS d352",
        citation="BCBS d352 §A.6.10",
        affected_engines=("market_risk_var",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.39"),
    Standard(standard_id="ENH-MR-006", category="enhancement", subcategory="market_risk",
        name="Market Risk Limit Framework",
        description=("Three-category limit framework: CONCENTRATION "
                      "(per-RiskFactor or per-RiskFactorClass exposure "
                      "ceilings) / VAR_LIMIT (daily VaR ceiling at "
                      "specified confidence + horizon) / ES_LIMIT "
                      "(Expected Shortfall ceiling at FRTB-IMA 97.5%). "
                      "Three LimitScope (SINGLE_FACTOR / FACTOR_CLASS "
                      "/ PORTFOLIO). RiskLimit dataclass is frozen — "
                      "limits are immutable once registered, requiring "
                      "deactivate-and-re-register to change. Per Rule "
                      "1, every limit carries threshold + scope + "
                      "approval_authority (BOARD/ALCO/TREASURY) + "
                      "effective_date + framework_refs. Aggregate by "
                      "class for multi-factor sums. Default registry "
                      "ships 5 illustrative limits per CBK PG/04 §4."),
        regulatory_source="BCBS d352 §A.4 + CBK PG/04 §4 + EBA/GL/2018/02",
        citation="BCBS d352 §A.4 + CBK PG/04 §4.2",
        affected_engines=("market_risk_limits",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.40"),
    Standard(standard_id="ENH-MR-007", category="enhancement", subcategory="market_risk",
        name="Limit Breach Detection & Escalation",
        description=("Mechanical breach detection: utilization = "
                      "observed / threshold × 100. Four BreachSeverity "
                      "bands: WITHIN_LIMIT (< 80%) / WARN (80-99.99%) / "
                      "BREACH (100-119.99%) / SEVERE_BREACH (≥ 120%). "
                      "Per Rule 1, every BreachAlert surfaces severity "
                      "+ limit_id + observed + threshold + "
                      "utilization_pct + factor + suggested_action + "
                      "escalation_target + framework_refs. Deterministic "
                      "alert_id supports dedup in audit trails. Per "
                      "Rule 7, LimitMonitor is purely diagnostic — "
                      "never auto-executes remediation; alerts flow "
                      "into treasury_agents.PaymentReviewAgent or "
                      "human approval workflow. EU AI Act Art 14 "
                      "human oversight preserved."),
        regulatory_source="BCBS 239 §5 + CBK PG/04 §4.5-4.6 + EBA/GL/2018/02",
        citation="BCBS 239 §5 + CBK PG/04 §4.6",
        affected_engines=("market_risk_limits",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.40"),
    Standard(standard_id="ENH-MR-008", category="enhancement", subcategory="market_risk",
        name="Trading Book Boundary Classification",
        description=("BCBS d352 §A.4 trading book / banking book "
                      "boundary. Two BookClassification (TRADING_BOOK / "
                      "BANKING_BOOK) drive different capital regimes "
                      "(market risk FRTB vs credit risk IRB + IRRBB). "
                      "16 InstrumentType enums with presumptive "
                      "classifications: 9 presumptive trading book "
                      "(LISTED_EQUITY / EQUITY_FUND / LISTED_DERIVATIVE "
                      "/ OTC_DERIVATIVE_TRADING / SECURITY_HELD_FOR_"
                      "RESALE / REPO_REVERSE_REPO / MARKET_MAKING_"
                      "INVENTORY / COMMODITY_TRADING / FX_TRADING) + "
                      "7 presumptive banking book (LOAN_RECEIVABLE / "
                      "DEPOSIT_LIABILITY / BANKING_BOOK_HEDGE / "
                      "SECURITISATION_BB / EQUITY_INVESTMENT_NON_"
                      "TRADING / REAL_ESTATE / LIQUIDITY_BUFFER_HOLD). "
                      "Presumption sets are disjoint. UNCLASSIFIED "
                      "requires explicit override with justification + "
                      "senior management approval per §A.4. Per Rule 1, "
                      "every BookAssignment surfaces classification + "
                      "instrument_type + trading_desk_id + "
                      "is_presumptive + justification + approved_by + "
                      "effective_date + framework_refs."),
        regulatory_source="BCBS d352 §A.4 + CBK PG/04 §3 + EBA/RTS/2017/06",
        citation="BCBS d352 §A.4",
        affected_engines=("trading_book_boundary",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.41"),
    Standard(standard_id="ENH-MR-009", category="enhancement", subcategory="market_risk",
        name="Trading Desk Definition & Risk Factor Mapping",
        description=("BCBS d352 §A.4.2 trading desk concept. Every "
                      "TRADING_BOOK position must be assigned to a "
                      "registered TradingDesk. Frozen dataclass "
                      "requires desk_id + name + head_trader + "
                      "mandate + risk_classes (FrozenSet[RiskFactor"
                      "Class]) + default_holding_period_days + "
                      "parent_business_unit. validate() returns "
                      "DeskValidationIssue tuple covering MISSING_"
                      "HEAD_TRADER / NO_RISK_CLASSES / INVALID_"
                      "HOLDING_PERIOD / NO_MANDATE — all required "
                      "for completeness per §A.4.2. Default registry "
                      "ships 3 illustrative desks (FX Nairobi / "
                      "Fixed Income / Equity) covering FOREIGN_"
                      "EXCHANGE / INTEREST_RATE+CREDIT_SPREAD / "
                      "EQUITY risk classes. positions_on_desk(desk_id) "
                      "filters assignments for risk reporting + desk-"
                      "level VaR aggregation."),
        regulatory_source="BCBS d352 §A.4.2 + EBA/RTS/2017/06",
        citation="BCBS d352 §A.4.2",
        affected_engines=("trading_book_boundary",),
        status="active", breach_severity="MEDIUM", priority_tier="A",
        source="research_addition", implementation_batch="v10.41"),
    Standard(standard_id="ENH-MR-010", category="enhancement", subcategory="market_risk",
        name="Boundary Crossing Approval Workflow",
        description=("BCBS d352 §A.4.5 reclassification approval "
                      "workflow. ReclassificationRequest with "
                      "request_id + position_id + from_book + to_book "
                      "+ reason + expected_capital_impact_kes + "
                      "requested_by + request_date. Validation: "
                      "reason required (non-empty); from_book ≠ "
                      "to_book; capital_surcharge applies when "
                      "expected_capital_impact_kes > 0 (benefits "
                      "bank capitally per §A.4.5) at "
                      "DEFAULT_SURCHARGE_RATE = 1.0 (overrideable). "
                      "ApprovalDecision lifecycle: PENDING → APPROVED "
                      "(via approve_reclassification with explicit "
                      "approver_id, senior management) OR REJECTED "
                      "(via reject_reclassification, assignment "
                      "unchanged). Per Rule 7, the engine NEVER "
                      "auto-approves — every transition requires "
                      "explicit caller action. EU AI Act Art 14 "
                      "human oversight preserved. Approval to "
                      "TRADING_BOOK requires new_trading_desk_id."),
        regulatory_source="BCBS d352 §A.4.5 + EBA/RTS/2017/06 + EU AI Act Art 14",
        citation="BCBS d352 §A.4.5",
        affected_engines=("trading_book_boundary",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.41"),
    Standard(standard_id="ENH-CR-001", category="enhancement", subcategory="credit",
        name="IRB Capital Framework (PD/LGD/EAD/RWA)",
        description=("Basel III IRB capital per BCBS d424 §RBC25 "
                      "corporate exposure formula. PD floored at 3bp, "
                      "M in [1, 5]. K = LGD × [N(...) − PD] × maturity_adj. "
                      "RWA = K × 12.5 × EAD. EL = PD × LGD × EAD. "
                      "Correlation R(PD) and maturity adjustment b(PD) "
                      "per §RBC25.7 + §RBC25.13. Defaulted exposure "
                      "(PD=1.0) → K=0 above EL per §RBC25.16. Pure "
                      "stdlib (statistics.NormalDist + math). Per Rule "
                      "1, CapitalResult surfaces all inputs + "
                      "intermediate R, b + outputs K, RWA, EL + "
                      "framework refs. Per Rule 7, computational only — "
                      "never moves loans between classes. Distinct from "
                      "credit_risk_scoring (underwriting) and "
                      "ifrs9_classification (accounting); covers the "
                      "regulatory capital perspective."),
        regulatory_source="BCBS d424 §RBC25 + Basel III + CBK PG/15",
        citation="BCBS d424 §RBC25.4-25.16",
        affected_engines=("credit_risk_irb",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.42"),
    Standard(standard_id="ENH-OR-001", category="enhancement", subcategory="audit",
        name="SMA Operational Risk Capital",
        description=("Basel III SMA per BCBS d457 §RBC30. "
                      "BI = ILDC + SC + FC averaged over 3y. "
                      "ILDC = min(|II−IE|, 0.0225×IEA) + DI. "
                      "SC = max(OI, OE) + max(FI, FE). "
                      "FC = |Net P&L TB| + |Net P&L BB|. "
                      "BIC applies marginal α (12%/15%/18%) by bucket "
                      "(EUR 1bn / 30bn thresholds). LC = 15 × avg "
                      "annual op losses (10y window). "
                      "ILM = ln(e − 1 + (LC/BIC)^0.8) — set to 1.0 "
                      "in Bucket 1 (national discretion §RBC30.41) or "
                      "when loss history <5 years. ORC = BIC × ILM, "
                      "RWA_op = ORC × 12.5. Pure stdlib (math + "
                      "Decimal). Per Rule 1, SMAResult surfaces BI per "
                      "year + 3y avg + bucket + BIC + LC + ILM + "
                      "ilm_source + ORC + RWA + framework refs. Per "
                      "Rule 7, computational only — never auto-records "
                      "loss events, never approves capital."),
        regulatory_source="BCBS d457 §RBC30 + Basel III + CBK PG/15",
        citation="BCBS d457 §RBC30.5-30.41",
        affected_engines=("op_risk",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.43"),
    Standard(standard_id="ENH-LR-001", category="enhancement", subcategory="treasury",
        name="Stressed LCR with Severity Calibration",
        description=("Basel III LCR under stress per BCBS d295 §40-§69. "
                      "HQLA tiers with haircuts (L1=0%, L2A=15%, L2B=50%) "
                      "and composition caps (L2≤40%, L2B≤15% of total). "
                      "Net cash outflow over 30d horizon: stressed "
                      "outflows minus min(stressed inflows, 75% of "
                      "outflows). Severity tiers BASELINE/MODERATE/"
                      "SEVERE/BANK_RUN apply multipliers (1.0/1.5/2.0/"
                      "3.0×) to outflow run-off rates and inverse "
                      "multipliers (1.0/0.85/0.65/0.40×) to inflow "
                      "run-in rates; stressed rates capped at 100%. "
                      "Breach classification: COMPLIANT (≥100%), "
                      "AMBER ([90%,100%)), RED ([70%,90%)), CRITICAL "
                      "(<70%). Survival horizon = HQLA/(NCO/30) when "
                      "breaching. Pure stdlib Decimal. Per Rule 1, "
                      "StressedLCRResult surfaces HQLA per level + "
                      "caps applied + per-category outflow/inflow "
                      "stressed values + NCO components + LCR ratio "
                      "+ breach severity + survival days + framework "
                      "refs. Per Rule 7, computational only — never "
                      "auto-liquidates HQLA, never executes funding "
                      "draws. Distinct from utils.liquidity_risk "
                      "(Standard #73 baseline LCR/NSFR) and "
                      "utils.stress_testing (Standard #79 capital "
                      "stress); covers liquidity-specific stress."),
        regulatory_source="BCBS d295 §40-§69 + Basel III + CBK PG/12",
        citation="BCBS d295 §17, §50, §69",
        affected_engines=("liquidity_stress",),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="research_addition", implementation_batch="v10.44"),
)


# ────────────────────────────────────────────────────────────────────
# REVENUE ASSURANCE MODULE — #241-#248
# ────────────────────────────────────────────────────────────────────

REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-241", category="enhancement", subcategory="revenue_assurance",
        name="Validation Agents (Data Integrity)",
        description=("Foundational diagnostic engine for revenue-data "
                      "integrity. 4 agent-style validation routines as "
                      "class methods (not autonomous threads — same "
                      "pattern as treasury_agents.py ENH-240): SCHEMA "
                      "(amount positivity, revenue_category vocabulary, "
                      "future-date sanity), COMPLETENESS (expected-count "
                      "manifest comparison by period × dimension × "
                      "category), CROSS-SOURCE reconciliation (pairwise "
                      "tolerance check between any two sources e.g. CBS "
                      "vs GL, with default 5bp tolerance and missing/"
                      "amount-mismatch/count-mismatch finding types), "
                      "STATISTICAL anomaly screen (z-score outliers "
                      "within revenue_category × branch_code groups, "
                      "min sample 10, default z=3.0 — upstream screen "
                      "before ENH-242 ML-based detection). 5 "
                      "ValidationSeverity (CRITICAL / HIGH / MEDIUM / "
                      "LOW / INFO) × 4 ValidationCategory. validate_all "
                      "orchestrator runs all 4 agents and returns a "
                      "ValidationReport with by_severity dict + per-"
                      "agent counts + framework refs. 6 frozen "
                      "dataclasses (RevenueRecord, CrossSourceTotal, "
                      "ExpectedCount, ValidationFinding, "
                      "ValidationReport). Pure stdlib (Decimal + "
                      "statistics). Per Rule 1, every "
                      "ValidationFinding surfaces finding_id + severity "
                      "+ category + record_id + description + expected "
                      "+ observed + source_system + posting_date + "
                      "framework refs. Per Rule 7, engine is "
                      "computational only — never auto-corrects records, "
                      "never auto-writes to source systems, never "
                      "auto-closes findings, never silently drops "
                      "invalid records."),
        regulatory_source="CBK PG/03 §revenue + reconciliation discipline",
        citation="#241; ENH-241 §schema/§completeness/§reconciliation/§anomaly",
        affected_engines=("revenue_validation",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.50"),
    Standard(standard_id="ENH-242", category="enhancement", subcategory="revenue_assurance",
        name="Anomaly Agents (Pattern Detection)",
        description=("Pattern-detection layer over ENH-241 data-integrity "
                      "foundation. 6 deterministic detectors covering 4 "
                      "PatternFamily enums: LEAKAGE "
                      "(unauthorized_fee_waiver, expired_contract_"
                      "billing), BILLING_ERROR (duplicate_billing, "
                      "missing_tax_component), COMMISSION_MISCALC "
                      "(commission_overpayment / underpayment with KES 1 "
                      "tolerance), RATE_CARD_BREACH (rate_below_floor → "
                      "MEDIUM leakage / rate_above_ceiling → HIGH "
                      "compliance breach). 9 PatternId enums total "
                      "including ML_FLAGGED_PATTERN. ML-hook injectable "
                      "via ml_score_fn callable per Rule 6 — when absent, "
                      "ml_disabled=True surfaced explicitly so callers "
                      "cannot mistake rule-only output for ML-augmented "
                      "(matches utils.credit_risk_scoring Standard #53 "
                      "discipline). ML threshold default 0.80; threshold "
                      "≥ 0.95 surfaces HIGH severity. ML errors caught "
                      "and surfaced as INFO findings rather than silent "
                      "swallow per Rule 6. detect_all orchestrator runs "
                      "all 6 deterministic detectors plus optional ML "
                      "hook and returns AnomalyReport (by_family + "
                      "by_severity counts + ml_disabled flag + records/"
                      "contracts/commissions scanned counts + framework "
                      "refs). 5 frozen dataclasses (ContractRate with "
                      "construction validation, RevenueRecordWithContext, "
                      "CommissionRecord, PatternFinding, AnomalyReport). "
                      "Pure stdlib (Decimal + dataclasses). Per Rule 1, "
                      "every PatternFinding surfaces finding_id + "
                      "pattern_id + family + severity + record_ids + "
                      "description + evidence + confidence + ml_score "
                      "(when applicable) + framework refs. Per Rule 7, "
                      "engine never auto-recovers leaked revenue, never "
                      "auto-reverses duplicates, never auto-corrects "
                      "rates, never auto-closes findings."),
        regulatory_source="CBK PG/03 §revenue + KRA tax compliance",
        citation="#242; ENH-242 §leakage/§billing_error/§commission_miscalc/§rate_card_breach/§ml_hook",
        affected_engines=("revenue_anomaly_patterns",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.51"),
    Standard(standard_id="ENH-243", category="enhancement", subcategory="revenue_assurance",
        name="Revenue Agentic Orchestrator",
        description=("Composition layer over ENH-241 (revenue_validation) "
                      "and ENH-242 (revenue_anomaly_patterns). Stateless "
                      "engine that takes heterogeneous findings "
                      "(ValidationFinding + PatternFinding) and produces "
                      "unified WorkItem records with deterministic "
                      "priority + routing + SLA aging. Per Rule 7, "
                      "engine NEVER tracks state internally — caller "
                      "maintains state externally and feeds it back as "
                      "current_states map; calling orchestrate twice "
                      "without supplying state yields RAISED both times "
                      "(verified by test). 6 InvestigatorTeam enums "
                      "(REVENUE_RECOVERY, OPERATIONS, COMPLIANCE, "
                      "HR_PAYROLL, DATA_QUALITY, FINANCE), 6 "
                      "WorkItemState enums (RAISED, ACKNOWLEDGED, "
                      "IN_PROGRESS, RESOLVED, DISMISSED, ESCALATED), "
                      "2 FindingType enums (VALIDATION, PATTERN). "
                      "Routing via TriageRule table matched on "
                      "(family_or_category, severity); falls back to "
                      "default_team + default_sla_days when no rule "
                      "matches. SEVERITY_WEIGHTS map (CRITICAL=100, "
                      "HIGH=50, MEDIUM=20, LOW=5, INFO=1) × "
                      "FAMILY_WEIGHTS (LEAKAGE=1.5, RECONCILIATION=1.4, "
                      "BILLING_ERROR=1.3, RATE_CARD_BREACH=1.2, "
                      "COMPLETENESS=1.1, COMMISSION_MISCALC=1.0, "
                      "ANOMALY=1.0, SCHEMA=0.9). Priority score = "
                      "(severity × family) + age_decay + impact "
                      "contribution; large monetary impacts CAN lift "
                      "MEDIUM above CRITICAL by design (callers tune "
                      "via OrchestratorConfig.impact_weight). All 5 "
                      "components surfaced separately in "
                      "priority_components dict per Rule 1 transparency. "
                      "Future-dated raised_dates clipped to age=0 "
                      "rather than raising. past_sla flag computed but "
                      "engine never auto-escalates. Pure stdlib (Decimal "
                      "+ frozen dataclasses + enums). 5 frozen "
                      "dataclasses (TriageRule, OrchestratorConfig, "
                      "WorkItem, TriageReport, plus reuse of upstream "
                      "ValidationFinding/PatternFinding). Per Rule 1, "
                      "every WorkItem surfaces work_item_id + source_id "
                      "+ source_type + severity + family_or_category + "
                      "description + affected_record_ids + raised_date "
                      "+ age_days + sla_deadline + past_sla + "
                      "assigned_team + priority_score + components dict "
                      "+ monetary_impact + current_state + framework "
                      "refs. Per Rule 7, engine NEVER auto-transitions "
                      "states, NEVER sends notifications, NEVER modifies "
                      "source records, NEVER auto-escalates."),
        regulatory_source="Composes ENH-241 + ENH-242; matches treasury_agents.py (ENH-240) discipline",
        citation="#243; ENH-243 §orchestration",
        affected_engines=("revenue_orchestrator",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.52"),
    Standard(standard_id="ENH-244", category="enhancement", subcategory="revenue_assurance",
        name="Partner & Supplier Reconciliation",
        description=("Multi-party reconciliation engine extending ENH-241 "
                      "from internal-source to cross-counterparty cases. "
                      "Two capability blocks: (A) PARTNER REVENUE SHARE — "
                      "PartnerAgreement (with share_pct ∈ [0,1] + "
                      "min_settlement_kes floor + effective_from/to "
                      "validated at construction) drives expected_share "
                      "= Σ(gross_revenue × share_pct) per (agreement, "
                      "period). Compared to PartnerSettlement records "
                      "with tolerance max(KES 100, 1% of expected). "
                      "Below min_settlement_kes → carried-forward "
                      "(skipped, not flagged). 3 discrepancy types: "
                      "SHARE_UNDERPAID / SHARE_OVERPAID / SHARE_MISSING. "
                      "(B) SUPPLIER 3-WAY MATCH — chain PO → GRN → "
                      "Invoice → Payment with KES 100 absolute "
                      "tolerance per step. Multiple GRNs per PO sum "
                      "(partial deliveries). 6 discrepancy types: "
                      "PO_GRN_MISMATCH / GRN_INVOICE_MISMATCH (HIGH — "
                      "potential overbilling) / INVOICE_PAYMENT_MISMATCH "
                      "(HIGH if overpaid) / PO_WITHOUT_INVOICE "
                      "(unrecognised liability) / INVOICE_WITHOUT_PO "
                      "(authorisation chain) / INVOICE_BEFORE_DELIVERY. "
                      "Zero-paid invoices not flagged (not-yet-due). "
                      "9 DiscrepancyType enums × 2 PartySide enums "
                      "(PARTNER / SUPPLIER). 9 frozen dataclasses "
                      "(PartnerAgreement, PartnerRevenueRecord, "
                      "PartnerSettlement, PurchaseOrder, "
                      "GoodsReceiptNote, SupplierInvoice, "
                      "SupplierPayment, ReconciliationFinding, "
                      "ReconciliationReport). reconcile_all "
                      "orchestrator. ValidationSeverity reused from "
                      "ENH-241 — single severity vocabulary across all "
                      "revenue_assurance engines for clean composition "
                      "with ENH-243 orchestrator. Pure stdlib (Decimal "
                      "+ dataclasses). Per Rule 1, every "
                      "ReconciliationFinding surfaces finding_id + "
                      "discrepancy_type + party_side + party_id + "
                      "severity + related_ids + expected + observed + "
                      "variance_kes + framework refs. Per Rule 7, "
                      "engine never auto-creates settlements, never "
                      "auto-issues payments, never auto-reverses "
                      "invoices, never auto-resolves discrepancies."),
        regulatory_source="Procurement controls + partner agreement governance",
        citation="#244; ENH-244 §partner_share + §supplier_3way",
        affected_engines=("partner_supplier_recon",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.53"),
    Standard(standard_id="ENH-245", category="enhancement", subcategory="revenue_assurance",
        name="Revenue Assurance Dashboard",
        description=("Split implementation per v10.46-amended protocol: "
                      "(A) DATA LAYER shipped v10.54 as "
                      "utils/revenue_dashboard_metrics.py — read-only "
                      "aggregation engine producing 6 metric families "
                      "from ENH-243 WorkItem stream + caller-supplied "
                      "StateTransitions. (B) UI LAYER deferred to arc "
                      "closure (v10.58 cockpit) — the closure cockpit "
                      "consumes these aggregates rather than recomputing, "
                      "avoiding duplicate UI work. Six metric families "
                      "in the data layer: LEAKAGE_TREND (TrendPoint "
                      "tuple bucketed by period, default YYYY-MM, with "
                      "finding_count + monetary_impact_kes per bucket; "
                      "outside-window items excluded), TOP_CATEGORIES "
                      "(two rankings — by_count AND by_impact since "
                      "high-frequency-low-impact and low-frequency-"
                      "high-impact often disagree; pct_of_total_count "
                      "+ pct_of_total_impact populated for Rule 1), "
                      "RECOVERY (resolved_count + recovered_kes for "
                      "RESOLVED items, dismissed_count separately, "
                      "open_count + open_estimated_impact_kes for "
                      "comparison; DISMISSED items NOT counted as "
                      "recoveries), TEAM_ACTIVITY (per-InvestigatorTeam "
                      "breakdown across 6 WorkItemState values + "
                      "past_sla_count; teams with zero total excluded), "
                      "CYCLE_TIMES (mean/median/p90/min/max days for "
                      "4 named CycleStage transitions: "
                      "RAISED_TO_ACK/IN_PROGRESS/RESOLVED + "
                      "ACK_TO_RESOLVED; uses statistics module; "
                      "negative-duration data points skipped), SUMMARY "
                      "(total_work_items + window + framework refs). "
                      "compute_all orchestrator. 9 frozen dataclasses "
                      "(DashboardWindow + StateTransition + 5 metric "
                      "shapes + DashboardMetrics + CycleTimeMetric). "
                      "Reuses InvestigatorTeam + WorkItem + "
                      "WorkItemState from ENH-243. TERMINAL_STATES + "
                      "OPEN_STATES module-level frozensets. Pure stdlib "
                      "(Decimal + statistics + dataclasses). Per Rule "
                      "1, every metric surfaces components separately "
                      "(count vs impact split, sample sizes for "
                      "percentile metrics, window boundaries). Per "
                      "Rule 7, engine read-only — never mutates "
                      "WorkItems, never persists output, never "
                      "schedules notifications, never modifies "
                      "transitions."),
        regulatory_source="Aggregates ENH-241/242/243/244 outputs",
        citation="#245; ENH-245 §dashboard_metrics",
        affected_engines=("revenue_dashboard_metrics",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="research_addition", implementation_batch="v10.54"),
    Standard(standard_id="ENH-246", category="enhancement", subcategory="revenue_assurance",
        name="Continuous Billing Verification",
        description=("Pre-issuance billing verification engine — screens "
                      "PENDING records before they post. Critical scope "
                      "distinction from ENH-242 (which screens POSTED "
                      "records). 5 check routines per BillingDraft: "
                      "CONTRACT_LIFECYCLE (contract exists + draft_date "
                      "in effective window), RATE_BAND (applied_rate vs "
                      "contract floor/ceiling — below floor → WARN/HOLD, "
                      "above ceiling → FAIL/REJECT), TAX_COMPUTATION "
                      "(computed_tax ≈ amount × (1-discount) × tax_rate, "
                      "1% tolerance with KES 5 floor), DISCOUNT_AUTH "
                      "(discount > 0 needs authorization_id), "
                      "DISCOUNT_BAND (discount ≤ contract.max_discount_pct "
                      "via ExtendedContractRate sidecar). 4 CheckStatus "
                      "(PASS/WARN/FAIL/SKIPPED) drive 3 Verdict enums "
                      "(PASS / HOLD_PENDING_REVIEW / REJECT_RECOMMENDED). "
                      "Composes ContractRate from ENH-242 + "
                      "ValidationSeverity from ENH-241. 4 frozen "
                      "dataclasses (BillingDraft, ExtendedContractRate, "
                      "CheckResult, VerificationResult). verify_batch "
                      "for bulk processing. Pure stdlib (Decimal + "
                      "dataclasses). Per Rule 1, every CheckResult "
                      "surfaces check_name + status + severity + "
                      "description + expected + observed + framework "
                      "refs; aggregate VerificationResult surfaces all "
                      "5 check results plus verdict + per-status counts. "
                      "Per Rule 7, engine RECOMMENDS verdicts — never "
                      "blocks billing, never releases held drafts, "
                      "never modifies the draft itself. Caller's "
                      "billing pipeline reads verdict and decides."),
        regulatory_source="Pre-issuance billing controls + KRA tax compliance",
        citation="#246; ENH-246 §contract_lifecycle/§rate_band/§tax_computation/§discount_auth/§discount_band",
        affected_engines=("continuous_billing_verification",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.55"),
    Standard(standard_id="ENH-247", category="enhancement", subcategory="revenue_assurance",
        name="Commission & Incentive Assurance",
        description=("Plan-based commission recomputation engine. Closes "
                      "the loop with ENH-242: where ENH-242's "
                      "detect_commission_anomalies takes (paid, expected) "
                      "and flags mismatches, ENH-247 COMPUTES the expected "
                      "from a tiered IncentivePlan + actual revenue. 4 "
                      "capabilities: (A) compute_expected_commission walks "
                      "tiered plans with 2 TierBasis modes (MARGINAL — "
                      "rate applies to slice of revenue within each tier; "
                      "CUMULATIVE — whole revenue gets the rate of the "
                      "tier it falls into); contributions surfaced "
                      "per-tier even when zero (Rule 1 — RMs disputing "
                      "see full plan structure). (B) "
                      "validate_paid_vs_computed matches PaidCommission"
                      "Records to a calculation by (rm_code, period); 4 "
                      "CommissionFinding types (OVERPAID / UNDERPAID / "
                      "MISSING_PAYMENT / MULTIPLE_PAYMENTS); KES 1 "
                      "tolerance. (C) validate_overrides — APPROVED "
                      "status requires approval_id; missing → invalid. "
                      "(D) summarize_disputes — counts by 4 DisputeStatus "
                      "(OPEN/UPHELD/REJECTED/WITHDRAWN) + average "
                      "resolution days; non-OPEN disputes require "
                      "resolved_date validated at construction. 7 frozen "
                      "dataclasses (CommissionTier with min_below_max + "
                      "rate_in_range validation, IncentivePlan with "
                      "tier-ordering validation + non-empty tiers, "
                      "CommissionContribution, CommissionCalculation, "
                      "PaidCommissionRecord, CommissionOverride with "
                      "non-empty reason validation, CommissionDispute, "
                      "DisputeSummary, OverrideValidationResult, "
                      "CommissionAssuranceFinding). Pure stdlib (Decimal "
                      "+ dataclasses). Per Rule 1, every "
                      "CommissionCalculation surfaces tier-by-tier "
                      "contribution detail. Per Rule 7, engine never "
                      "pays out commissions, never auto-approves "
                      "overrides, never closes disputes."),
        regulatory_source="Sales incentive governance + payroll controls",
        citation="#247; ENH-247 §plan_recompute/§payment_validation/§overrides/§disputes",
        affected_engines=("commission_assurance",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="research_addition", implementation_batch="v10.56"),
    Standard(standard_id="ENH-248", category="enhancement", subcategory="revenue_assurance",
        name="Regulatory Revenue Reporting",
        description=("Diagnostic engine for revenue-side regulatory report "
                      "generation + mgmt-vs-statutory reconciliation. "
                      "Engine produces structured ReportPackage data; "
                      "caller's submission workflow handles serialization "
                      "(XBRL/XML/CSV) and submission rails (CBK BSD portal, "
                      "KRA iTax). 3 capabilities: (A) generate_report — "
                      "ReportTemplate (validates unique line_codes + "
                      "period order) drives line aggregation from "
                      "RevenueRecord stream; out-of-period records "
                      "excluded; unmapped categories surfaced as "
                      "unmapped_categories tuple rather than silently "
                      "dropped per Rule 1. (B) "
                      "reconcile_management_vs_statutory — compares "
                      "ReportPackage line items to StatutoryReportRecord "
                      "stream by (line_code, period_label); KES 1 "
                      "tolerance. 4 DifferenceType classifications: "
                      "TIMING (variance < 5% of larger figure — likely "
                      "cut-off difference), GENUINE (variance ≥ 5% — "
                      "investigate), CLASSIFICATION (different line code "
                      "carries amount — caller-supplied resolution), "
                      "UNCLASSIFIED (line missing from one side). "
                      "TIMING_DAYS_HEURISTIC=5. (C) validate_completeness "
                      "— checks no required line missing or zero, no "
                      "unmapped categories. 3 CompletenessIssue types: "
                      "MISSING_LINE_ITEM, ZERO_AMOUNT_REQUIRED_LINE, "
                      "UNMAPPED_CATEGORY. 3 Regulator enums (CBK / KRA / "
                      "INTERNAL). 11 frozen dataclasses with construction-"
                      "time validation. Reuses RevenueRecord + "
                      "ValidationSeverity from ENH-241. Pure stdlib "
                      "(Decimal + dataclasses). Per Rule 1, every "
                      "ReportLineItem surfaces contributing record IDs + "
                      "record_count + revenue categories used; every "
                      "ReconciliationDifference surfaces both figures + "
                      "variance + classification + severity. Per Rule 7, "
                      "engine NEVER submits reports, NEVER serializes to "
                      "XBRL/XML/CSV (caller's choice based on regulator), "
                      "NEVER persists output, NEVER calls external "
                      "systems."),
        regulatory_source="CBK BSR returns + KRA iTax + IFRS 15 disclosure",
        citation="#248; ENH-248 §generate_report/§recon/§completeness",
        affected_engines=("regulatory_revenue_reporting",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.57"),
)


# ────────────────────────────────────────────────────────────────────
# FINANCE MODULE — #249-#258
# ────────────────────────────────────────────────────────────────────

FINANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-249", category="enhancement", subcategory="finance",
        name="Continuous Close Orchestration Engine",
        description=("Diagnostic continuous-close orchestrator opening "
                      "the finance arc (13th arc opened on platform). "
                      "5 detection capabilities surfaced as CloseTask "
                      "recommendations: (1) MISSING_RECURRING_ACCRUAL "
                      "— RecurringAccrualSchedule + GLEntry stream "
                      "with schedule_id linkage; quarterly schedules "
                      "only fire in months 3/6/9/12, annual in month "
                      "12; missing → recommends Dr account_code / Cr "
                      "contra_account_code at periodic_amount_kes; "
                      "(2) PREPAYMENT_AMORTIZATION_DUE — "
                      "PrepaymentSchedule with start/end period bounds; "
                      "missing amortization → recommend Dr expense / "
                      "Cr prepaid; outside-window periods skipped; "
                      "(3) INTERCOMPANY_PENDING — IC accounts flagged "
                      "is_intercompany=True; pairs entries by reference "
                      "+ period; unbalanced (Dr ≠ Cr aggregate) → "
                      "flagged HIGH; both-sides-equal aggregates "
                      "skipped silently; (4) SUSPENSE_BALANCE — accounts "
                      "flagged is_suspense=True; non-zero net balance "
                      "at period end → CRITICAL severity (blocks close); "
                      "(5) CUTOFF_TIMING — entries with posting in "
                      "period N but reference_date significantly "
                      "outside (default 7-day threshold; >30-day lag "
                      "promotes to HIGH); caller supplies reference_dates "
                      "dict since GLEntry only carries posting date. "
                      "5 CloseTaskType × 4 CloseTaskSeverity × 2 "
                      "CloseTaskStatus × 5 AccountType × 3 "
                      "AccrualFrequency enums. 8 frozen dataclasses "
                      "(CloseAccount + GLEntry with Dr-XOR-Cr "
                      "validation + RecurringAccrualSchedule + "
                      "PrepaymentSchedule + CloseTask + "
                      "CloseReadinessReport + ...). generate_close_report "
                      "orchestrator runs all 5 capabilities. Pure "
                      "stdlib (Decimal + dataclasses). Per Rule 1, "
                      "every CloseTask surfaces task_id + task_type + "
                      "severity + status + period + account_code + "
                      "recommended_debit_kes + recommended_credit_kes "
                      "+ contra_account_code + description + "
                      "related_ids + framework refs. Per Rule 7, "
                      "engine DIAGNOSTIC ONLY — recommends journals "
                      "(never posts), flags close gaps (never closes), "
                      "flags suspense (never clears), flags timing "
                      "(never reverses). Targets <3 day close per "
                      "Gartner finance research but leaves all "
                      "execution to operator review."),
        regulatory_source="Gartner continuous close research + IFRS accrual basis",
        citation="#249; ENH-249 §close_orchestrator",
        affected_engines=("finance_close_orchestrator",),
        threshold=Decimal("3"), threshold_unit="days",
        threshold_direction="max",
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.59",
        global_benchmark="FloQast / OneStream"),
    Standard(standard_id="ENH-250", category="enhancement", subcategory="finance",
        name="Intercompany Matching & Elimination",
        description=("Diagnostic IC matching engine pairing entries "
                      "across legal entities, recommending elimination "
                      "journals at consolidation. Where ENH-249 only "
                      "flags unbalanced IC entries within one entity's "
                      "books, ENH-250 takes a multi-entity view: "
                      "GLEntries from parent + all subs flow in, the "
                      "engine pairs by (reference, period) where "
                      "entity_id and counterparty_entity_id are mirror "
                      "images and Dr/Cr sides are opposite. 4 "
                      "MatchStatus enums (EXACT within tolerance / "
                      "AMOUNT_MISMATCH / UNMATCHED / MULTI_LEG_CHAIN); "
                      "5 EliminationType enums "
                      "(REVENUE_EXPENSE/RECEIVABLE_PAYABLE/DIVIDEND/"
                      "LOAN/OTHER) drive elimination account routing "
                      "with placeholder accounts (IC-REC, IC-PAY, "
                      "IC-DIV-RCVD, IC-DIV-PAID, etc.) — production "
                      "deployments map these from CoA + entity policy. "
                      "Default KES 100 absolute tolerance, configurable "
                      "via constructor. Multi-leg chain detection: "
                      "entries sharing chain_id are reported as a unit "
                      "with net signed amount across all legs (balanced "
                      "chains net to zero, unbalanced flagged HIGH). "
                      "match_all orchestrator returns IcMatchReport "
                      "with per-status + per-severity aggregates + "
                      "elimination-recommendation count. 6 frozen "
                      "dataclasses (IcEntry with self-counterparty "
                      "validation + Dr-XOR-Cr enforcement + reference "
                      "non-empty constraint, EliminationRecommendation, "
                      "IcMatch with full provenance, IcMatchReport, "
                      "and 4 enum types). Pure stdlib (Decimal + "
                      "dataclasses + enums). Per Rule 1, every IcMatch "
                      "surfaces match_id + status + severity + period "
                      "+ reference + entity_a + entity_b + amounts + "
                      "variance_kes + related_entry_ids + recommended "
                      "elimination + framework refs. Per Rule 7, "
                      "engine DIAGNOSTIC ONLY — pairs entries (never "
                      "posts eliminations); flags mismatches (never "
                      "decides which side is correct); never resolves "
                      "matches without operator review."),
        regulatory_source="IFRS 10 — intra-group balances eliminate at consolidation",
        citation="#250; ENH-250 §match_pairs",
        affected_engines=("intercompany_matching",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.60"),
    Standard(standard_id="ENH-251", category="enhancement", subcategory="finance",
        name="Group Consolidation Engine",
        description=("Operational TB consolidation engine per IFRS 10 + "
                      "IAS 21. Distinct from Standard #100 "
                      "(utils/group_consolidation.py — policy-side "
                      "method selection by ownership %, classification, "
                      "NCI calculation rules); ENH-251 is the operational "
                      "side (utils/consolidated_tb_engine.py — TB "
                      "aggregation, FX translation, line-by-line "
                      "eliminations producing consolidated TB ready for "
                      "ENH-255). Four-step pipeline: (1) AGGREGATION "
                      "line-by-line sum after FX translation; (2) "
                      "ELIMINATIONS apply operator-approved subset from "
                      "ENH-250 IcMatchReport via debit_account/"
                      "credit_account routing; (3) NCI ALLOCATION for "
                      "each non-100%-owned subsidiary, allocates "
                      "post-elimination contribution between parent "
                      "share and non-controlling interest at "
                      "(1 - ownership_pct); (4) FX TRANSLATION per "
                      "IAS 21 — closing rate for B/S items "
                      "(ASSET/LIABILITY/EQUITY), average rate for P&L "
                      "items (REVENUE/EXPENSE); HISTORICAL rate type "
                      "available but not used by default. Translation "
                      "differential accumulates as "
                      "cumulative_translation_adjustment_kes for OCI "
                      "booking. 3 FxRateType × 4 ConsolidationSeverity "
                      "× 5 AccountType (reused from ENH-249). 8 frozen "
                      "dataclasses (EntityProfile validates ownership "
                      "in [0,1] + parent must be 100% owned, "
                      "TrialBalanceLine, FxRate validates rate > 0, "
                      "EntityContribution with full per-entity FX detail, "
                      "ConsolidatedLine with pre/post elimination + "
                      "NCI/parent split, ConsolidationFinding, "
                      "ConsolidatedTrialBalance). Pure stdlib (Decimal "
                      "+ dataclasses). Per Rule 1, every "
                      "ConsolidatedLine surfaces account_code + "
                      "entity_contributions (per-entity FX detail) + "
                      "pre/post elimination + NCI/parent split + "
                      "framework refs. Per Rule 7, engine DIAGNOSTIC "
                      "ONLY — produces consolidated TB but never posts "
                      "to source entity GLs, never goes to FX market "
                      "(caller supplies rates per IAS 21 closing/"
                      "average discipline), never auto-selects "
                      "eliminations (caller passes operator-approved "
                      "subset)."),
        regulatory_source="IFRS 10 — control-based consolidation; IAS 21 — FX translation",
        citation="#251; ENH-251 §consolidate",
        affected_engines=("consolidated_tb_engine",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.61"),
    Standard(standard_id="ENH-252", category="enhancement", subcategory="finance",
        name="CBK Regulatory Reporting Automation (Enhanced)",
        description=("Diagnostic CBK banking returns generator extending "
                      "ENH-248 framework. 5 return families covering CBK "
                      "Prudential Guidelines: CAR (PG 03 §4 — capital "
                      "adequacy ratio = total_capital / RWA, minimum "
                      "14.5%), LIQ (PG 04 — liquid_assets / "
                      "total_deposits, minimum 20%), SBL (PG 05 — single "
                      "borrower limit, max 25% of core capital per "
                      "borrower; surfaces top borrower + breach count), "
                      "LXP (PG 05 — large exposures aggregate "
                      "≤800% of core capital where individual "
                      "exposure >10% of core), FXE (PG 06 — foreign "
                      "exchange exposure ±10% per currency of core "
                      "capital; surfaces worst currency + breach count). "
                      "5 CbkReturnCode × 4 BreachSeverity (NONE / "
                      "MARGINAL within 10% of threshold / BREACH / "
                      "SEVERE_BREACH ≥25% off threshold). 5 frozen "
                      "input dataclasses: CapitalComponents (validates "
                      "non-negative tier1/tier2/deductions + RWA > 0); "
                      "LiquidityComponents (deposits > 0); "
                      "BorrowerExposure (id non-empty + amounts ≥ 0); "
                      "CurrencyPosition (rejects KES + amounts ≥ 0). "
                      "Output CbkReturnPackage carries return_code + "
                      "computed_metrics dict + threshold + direction "
                      "min/max + breach_severity + breach_description "
                      "+ inputs_used dict + framework refs. Severity "
                      "classification by deviation magnitude: ≤10% off "
                      "threshold → MARGINAL, ≥25% off → SEVERE_BREACH, "
                      "between → BREACH. Pure stdlib (Decimal + "
                      "dataclasses + enums). Per Rule 1, every "
                      "CbkReturnPackage surfaces full computed metrics "
                      "+ inputs_used + framework refs. Per Rule 7, "
                      "engine DIAGNOSTIC ONLY — produces structured "
                      "returns; never serialises XBRL/XML/CSV (caller's "
                      "responsibility); never submits to CBK portal; "
                      "never auto-corrects breaches; never modifies "
                      "balances."),
        regulatory_source="CBK Prudential Guidelines PG 03/04/05/06",
        citation="#252; ENH-252 §car/§liq/§sbl/§lxp/§fxe",
        affected_engines=("cbk_regulatory_reporting",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.62"),
    Standard(standard_id="ENH-253", category="enhancement", subcategory="finance",
        name="Predictive Financial Analytics",
        description=("Diagnostic forecasting + variance analysis + "
                      "driver decomposition + trend signal engine. "
                      "Three deterministic forecasting methods: "
                      "LINEAR_TREND (OLS slope/intercept on time index "
                      "with 1.96σ residual confidence band; min sample "
                      "size 4, falls back to flat-projection with "
                      "ml_disabled flag for smaller samples), "
                      "SEASONAL_NAIVE (h-step ahead = value from "
                      "h-periods-ago in prior cycle; min sample 8 = "
                      "season_period; falls back to LINEAR_TREND with "
                      "ml_disabled flag if cycle incomplete), "
                      "EXPONENTIAL_SMOOTHING (single-exponential, "
                      "alpha in (0,1] caller-supplied; flat horizon "
                      "projection at smoothed level). ML_HOOK method "
                      "accepts caller-supplied predictor callable per "
                      "Rule 6; when ml_predictor=None, ml_disabled=True "
                      "surfaces with reason and engine falls back to "
                      "LINEAR_TREND — engine NEVER fabricates ML "
                      "predictions. Variance analysis with 3-tier "
                      "materiality (IMMATERIAL <threshold / MATERIAL "
                      "/ HIGHLY_MATERIAL ≥3× threshold) × 3 directions "
                      "(FAVOURABLE / UNFAVOURABLE / NEUTRAL); "
                      "higher_is_better flag inverts direction "
                      "semantics for cost metrics. Driver decomposition "
                      "surfaces all DriverContribution amounts + "
                      "explained + residual + residual_pct_of_total "
                      "for sanity check. Trend detection: 4 "
                      "TrendSignal (UPTREND/DOWNTREND/FLAT/INFLECTION); "
                      "FLAT threshold 1% relative slope; INFLECTION "
                      "detected via sign-change between first-half "
                      "and second-half slopes (requires sample ≥ "
                      "2× MIN_SAMPLE_FOR_TREND). 4 ForecastMethod × "
                      "3 VarianceDirection × 3 VarianceMateriality × "
                      "4 TrendSignal enums. 9 frozen dataclasses "
                      "(TimeSeriesPoint validates non-empty period, "
                      "ActualVsExpected validates metric_name, "
                      "DriverContribution, ForecastPoint, Forecast, "
                      "VarianceFinding, DriverDecomposition, "
                      "TrendFinding). Pure stdlib (Decimal + "
                      "dataclasses + statistics). Per Rule 1, every "
                      "Forecast surfaces method_used + horizon + "
                      "confidence band + ml_disabled + inputs_used. "
                      "Per Rule 6, ml_disabled=True surfaced with "
                      "reason whenever ML cannot run. Per Rule 7, "
                      "engine DIAGNOSTIC ONLY — produces forecasts "
                      "and findings; never auto-rebudgets, never "
                      "reallocates capital, never auto-revises on "
                      "actuals ingestion, never mutates inputs."),
        regulatory_source="Forecasting + variance discipline",
        citation="#253; ENH-253 §forecast/§variance/§drivers/§trend",
        affected_engines=("predictive_financial_analytics",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="research_addition", implementation_batch="v10.63"),
    Standard(standard_id="ENH-254", category="enhancement", subcategory="finance",
        name="Finance Intelligence Dashboard (CFO View)",
        description=("Split implementation per v10.46-amended protocol: "
                      "(A) DATA LAYER shipped v10.64 as "
                      "utils/finance_intelligence_dashboard.py — "
                      "diagnostic CFO KPI aggregation engine. (B) UI "
                      "LAYER deferred to arc closure (v10.68 cockpit). "
                      "Six metric families: PROFITABILITY (NIM = NII / "
                      "avg earning assets, threshold 4%; ROA = "
                      "net_profit / avg total assets, 1.5% min; ROE = "
                      "net_profit / avg equity, 15% min; "
                      "COST_TO_INCOME = opex / total revenue, 55% max), "
                      "CAPITAL (CAR consumed from ENH-252 / CBK PG 03 "
                      "§4, 14.5% min), LIQUIDITY (LIQ consumed from "
                      "ENH-252 / CBK PG 04, 20% min), GROWTH (loan + "
                      "deposit + customer growth rates — only when "
                      "prior period supplied; no thresholds — "
                      "informational), EFFICIENCY (cost_per_transaction "
                      "= txn_cost / txn_count, customers_per_branch — "
                      "no thresholds), ASSET_QUALITY (NPL_RATIO = NPL "
                      "/ loans, 6% max per CBK guidance; "
                      "COVERAGE_RATIO = provisions / NPL, 70% min). "
                      "Threshold status 4-tier: OK / WARNING (within "
                      "10% margin) / BREACH / NOT_APPLICABLE. Trend "
                      "direction 3-tier: UP / DOWN / FLAT (1% relative "
                      "threshold). Alerts fire on BREACH only — "
                      "severity CRITICAL for CAPITAL/LIQUIDITY breaches "
                      "(regulatory-grade), WARNING for everything "
                      "else. recommended_action_category surfaces a "
                      "category like 'review capital plan / RWA "
                      "optimisation' — engine deliberately does NOT "
                      "recommend specific actions per Rule 7. 6 "
                      "MetricFamily × 3 TrendDirection × 4 "
                      "ThresholdStatus × 3 AlertSeverity enums. 4 "
                      "frozen dataclasses (PeriodFinancials with "
                      "non-empty period + non-negative balance "
                      "validation, Kpi with full inputs_used dict + "
                      "trend + threshold_status, ExecutiveAlert, "
                      "CfoDashboard with by_family + by_threshold_status "
                      "aggregates). Pure stdlib. Per Rule 1, every "
                      "Kpi surfaces metric_name + family + value + "
                      "inputs_used + trend + prior_value + threshold "
                      "+ threshold_status + framework refs. Per Rule 7, "
                      "engine read-only — never sends notifications/"
                      "emails (caller drives escalation), never "
                      "persists state, never auto-acts on alerts, "
                      "never mutates inputs."),
        regulatory_source="Aggregates ENH-252 + CFO accountability frameworks",
        citation="#254; ENH-254 §dashboard",
        affected_engines=("finance_intelligence_dashboard",),
        affected_pages=("8_finance", "96_finance_arc_cockpit"),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.64"),
    Standard(standard_id="ENH-255", category="enhancement", subcategory="finance",
        name="Financial Statement Generator",
        description=("Diagnostic IFRS statement generator. Consumes "
                      "ConsolidatedTrialBalance from ENH-251 + caller-"
                      "supplied AccountClassification per account "
                      "(exactly one of BS/revenue/expense/OCI flag, "
                      "with bs_classification subdivided into 6 "
                      "BsClassification enums: CURRENT_ASSET / "
                      "NON_CURRENT_ASSET / CURRENT_LIABILITY / "
                      "NON_CURRENT_LIABILITY / EQUITY_PARENT / "
                      "EQUITY_NCI). Produces 5 IFRS statements: "
                      "(1) BalanceSheet (IAS 1 §54) — current vs "
                      "non-current asset/liability split, equity "
                      "split between parent and NCI; sign-flips "
                      "credit-natured lines for positive presentation; "
                      "surfaces BS imbalance as informational finding "
                      "(period P&L + OCI flow to equity outside this "
                      "engine's scope). (2) IncomeStatement (IAS 1 "
                      "§82) — revenue + expense lines with PBT. "
                      "(3) OciStatement (IAS 1 §82A) — split by "
                      "OciClassification: NEVER_RECYCLED (revaluation "
                      "surplus, equity FV, DB remeasurement) vs "
                      "RECYCLABLE_TO_PNL (debt FV, CF hedge, CTA); "
                      "consumes CTA (cumulative_translation_adjustment_kes) "
                      "from ENH-251 — IAS 21 CTA flows to OCI. "
                      "(4) EquityChanges (IAS 1 §106) — caller-"
                      "supplied EquityMovement list aggregated by "
                      "component; optional. (5) CashFlowStatement "
                      "(IAS 7) — caller supplies CashFlowInput per "
                      "section (OPERATING / INVESTING / FINANCING) "
                      "since CF items are not derivable from a "
                      "single-period TB; opening balance + net change "
                      "→ closing balance. Unclassified accounts "
                      "surface as findings. 3 BsClassification (split "
                      "into 6 sub-classifications) × 3 CashFlowSection "
                      "× 2 OciClassification enums. 11 frozen "
                      "dataclasses. Pure stdlib. Per Rule 1, every "
                      "StatementLine surfaces line_code + description "
                      "+ amount + parent_share + nci_share + "
                      "source_account_codes + framework refs. Per "
                      "Rule 7, engine DIAGNOSTIC ONLY — produces "
                      "structured statement objects; never files with "
                      "regulators (CMA, NSE, KRA); never serializes "
                      "to PDF/XBRL/IFRS taxonomy schema; never asserts "
                      "auditor sign-off; never mutates inputs."),
        regulatory_source="IAS 1 — presentation framework; IAS 7 — cash flow; IAS 21 — CTA",
        citation="#255; ENH-255 §generate_package",
        affected_engines=("financial_statement_generator",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.65"),
    Standard(standard_id="ENH-256", category="enhancement", subcategory="finance",
        name="Tax Compliance & Reporting",
        description=("Diagnostic Kenyan tax computation engine with "
                      "IAS 12 deferred tax + multi-tax return package "
                      "orchestration. Distinct from Standard #97 "
                      "(utils/tax_compliance.py — base policy layer "
                      "for VAT/CT/WHT/PAYE/Excise rules); ENH-256 "
                      "(utils/kra_tax_compliance.py) layers IAS 12 "
                      "deferred tax + return package orchestration on "
                      "top. 5 tax types: CORPORATION_TAX (3 "
                      "CorpTaxRegime — STANDARD_RESIDENT 30%, "
                      "PREFERENTIAL_BANK 25%, PERMANENT_ESTABLISHMENT "
                      "37%; loss-period floored at zero with pre-cap "
                      "value surfaced in inputs_used per Rule 1), VAT "
                      "(3 VatStatus — STANDARD 16%, ZERO_RATED 0% "
                      "with input recovery, EXEMPT 0% no input "
                      "recovery; aggregates by period × status), "
                      "WITHHOLDING_TAX (12-entry rate table indexed by "
                      "WhtIncomeType × ResidencyStatus: dividend "
                      "5%/15%, interest 15%/15%, royalty 5%/20%, "
                      "mgmt/professional fees 5%/20%, rent 10%/30%; "
                      "unsupported combinations surface as 0% with "
                      "manual-review note rather than fabricating a "
                      "rate per Rule 7), EXCISE_DUTY (20% on banking "
                      "fees per Excise Duty Act 2015), DEFERRED_TAX "
                      "(IAS 12 — DTL = taxable temp diff × rate, DTA "
                      "= deductible × rate, net surfaced; default "
                      "rate 30% standard resident, configurable). 5 "
                      "TaxType × 3 CorpTaxRegime × 3 VatStatus × 6 "
                      "WhtIncomeType × 2 ResidencyStatus × 2 "
                      "TemporaryDifferenceType enums. 9 frozen "
                      "dataclasses with validation envelopes. "
                      "build_return_package orchestrator returns "
                      "TaxReturnPackage with computations + deferred "
                      "tax + by_tax_type aggregates. Pure stdlib "
                      "(Decimal + dataclasses + enums). Per Rule 1, "
                      "every TaxComputation surfaces taxable_basis + "
                      "rate_applied + computed_tax_kes + "
                      "applicable_rule + inputs_used dict + framework "
                      "refs. Per Rule 7, engine DIAGNOSTIC ONLY — "
                      "computes tax; never files with KRA iTax; never "
                      "submits VAT returns; never withholds funds; "
                      "never reverses prior assessments; never mutates "
                      "inputs."),
        regulatory_source="KRA Income Tax Act / VAT Act / Excise Duty Act + IAS 12",
        citation="#256; ENH-256 §corporation_tax/§vat/§wht/§excise/§deferred_tax",
        affected_engines=("kra_tax_compliance",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.66"),
    Standard(standard_id="ENH-257", category="enhancement", subcategory="finance",
        name="Multi-Entity & Multi-Currency Accounting",
        description=("Diagnostic transaction-level multi-currency "
                      "accounting + IAS 21 period-end FX revaluation + "
                      "inter-entity transfer journal recommender. "
                      "Distinct from ENH-251 (consolidated_tb_engine) "
                      "which handles TB-level consolidation FX "
                      "translation; ENH-257 (utils/multi_entity_currency.py) "
                      "handles transaction-level multi-currency "
                      "accounting before TBs are extracted. Three "
                      "capabilities: (1) validate_multi_currency_journal "
                      "— surfaces 5 JournalIssue enums (UNBALANCED, "
                      "MIXED_CURRENCY_LINES per IAS 21 one-journal-one-"
                      "currency rule, MISSING_FX_RATE, NEGATIVE_AMOUNT, "
                      "EMPTY_JOURNAL); functional currency conversion "
                      "at caller-supplied spot rate (rate must match "
                      "transaction date). (2) revalue_monetary_balances "
                      "— IAS 21 §23 period-end remeasurement of foreign-"
                      "currency monetary items at closing rate; "
                      "computes FX gain/loss vs historical functional "
                      "balance with 4-tier RevalSeverity (NONE / LOW "
                      "<1% / MEDIUM 1-5% / HIGH ≥5%); missing closing "
                      "rate surfaces HIGH severity finding rather than "
                      "fabricating a rate. (3) "
                      "recommend_inter_entity_transfer — produces "
                      "mirror Dr/Cr journal pair (IC-RCV at from_entity, "
                      "IC-PAY at to_entity) for caller approval. 5 "
                      "JournalIssue × 4 RevalSeverity enums. 6 frozen "
                      "dataclasses with validation envelopes "
                      "(JournalLine validates non-empty IDs + "
                      "currency + non-negative amounts; FxSpotRate "
                      "validates rate > 0; InterEntityTransferRequest "
                      "rejects same-entity transfer + requires positive "
                      "amount + non-empty purpose). Pure stdlib "
                      "(Decimal + dataclasses + enums). Per Rule 1, "
                      "every output dataclass surfaces full inputs + "
                      "framework refs. Per Rule 7, engine DIAGNOSTIC "
                      "ONLY — never posts journals (recommends only); "
                      "never auto-revalues (caller initiates); never "
                      "sources FX rates from market (caller supplies); "
                      "never decides which monetary items qualify for "
                      "revaluation (caller flags); never mutates "
                      "inputs."),
        regulatory_source="IAS 21 — transaction at spot rate; closing rate for monetary items",
        citation="#257; ENH-257 §validate_journal/§revalue_monetary/§inter_entity",
        affected_engines=("multi_entity_currency",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.67"),
    Standard(standard_id="ENH-258", category="enhancement", subcategory="finance",
        name="Finance Audit & Compliance",
        description=("Diagnostic finance-function-specific SOX-style "
                      "compliance engine. Five capabilities covering "
                      "internal controls over financial reporting: (1) "
                      "check_segregation_of_duties — flags journals "
                      "where same user prepared + reviewed + posted "
                      "(CRITICAL) or any 2 of 3 (HIGH) or no reviewer "
                      "recorded (MEDIUM); passes if 3 distinct users. "
                      "(2) check_authorization_limit — flags journals "
                      "exceeding poster's authorization tier; severity "
                      "by ratio (≥2× CRITICAL, ≥1.5× HIGH, otherwise "
                      "MEDIUM); missing user authorization record "
                      "surfaces HIGH for triage. (3) "
                      "flag_manual_journals — surfaces manual journals "
                      "above materiality (default KES 100k) for SOX "
                      "evidence trail; severity by amount/materiality "
                      "ratio (≥100× HIGH, ≥10× MEDIUM, otherwise LOW); "
                      "automated journals never flagged. (4) "
                      "check_period_close_attestation — verifies period "
                      "sign-offs: ATTESTED passes; PENDING LOW; OVERDUE "
                      "HIGH; REJECTED CRITICAL. (5) "
                      "flag_late_period_end_adjustment — flags "
                      "post-cutoff adjustments above materiality "
                      "(SOX 404 cutoff discipline). 5 ControlId × 5 "
                      "FindingSeverity (INFO/LOW/MEDIUM/HIGH/CRITICAL) "
                      "× 3 JournalSource (AUTOMATED/MANUAL/UPLOADED) × "
                      "4 AttestationStatus enums. 6 frozen dataclasses "
                      "with validation envelopes (JournalAudit "
                      "validates non-empty journal_id + preparer + "
                      "non-negative amount; UserAuthorization validates "
                      "non-empty user_id + non-negative limit; "
                      "PeriodAttestation validates non-empty "
                      "attestation_id + function). build_compliance_"
                      "report orchestrates all 5 controls returning "
                      "ComplianceReport with by_control + by_severity "
                      "aggregates + journals_scanned + "
                      "attestations_scanned. Pure stdlib (Decimal + "
                      "dataclasses + enums). Per Rule 1, every "
                      "ComplianceFinding surfaces finding_id + control "
                      "+ severity + period + actors + journal_ids + "
                      "attestation_ids + amount + framework refs. Per "
                      "Rule 7, engine DIAGNOSTIC ONLY — never blocks "
                      "transactions; never revokes user access; never "
                      "cancels journals; never auto-attests period "
                      "close; never mutates inputs. Distinct from "
                      "general-purpose audit_core / audit_reporting "
                      "modules — ENH-258 is finance-function-specific "
                      "control surface."),
        regulatory_source="SOX 302 + SOX 404 — internal controls over financial reporting",
        citation="#258; ENH-258 §segregation/§authorization/§manual_journal/§attestation/§late_adjustment",
        affected_engines=("finance_audit_compliance",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.68"),
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
        affected_engines=("model_governance", "credit_risk_scoring"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.28"),
    Standard(standard_id="ENH-260", category="enhancement", subcategory="credit_model_risk",
        name="Alternative Credit Scoring (Enhanced)",
        description=("Thin-file PD via 3 alternative pillars (per CGAP + "
                      "Smart Campaign + IFC Inclusive Finance): "
                      "TRANSACTION (deposit-CV regularity, salary-cycle "
                      "signal, expense/deposit ratio, bills-on-time %), "
                      "BEHAVIORAL (tenure with bank, mobile-active days, "
                      "current-facility delinquency days), PSYCHOMETRIC "
                      "(optional minimal questionnaire — risk tolerance "
                      "+ time-horizon). Each pillar produces a sub-PD "
                      "AND a confidence weight (0 when unusable); "
                      "composite alt-PD is confidence-weighted across "
                      "available pillars; overall confidence drives "
                      "ConfidenceBand (HIGH ≥0.70 / MEDIUM ≥0.40 / "
                      "LOW). Below LOW threshold, "
                      "recommend_bureau_check=True so underwriting "
                      "escalates rather than acting on a thin estimate. "
                      "PD floor 3bp (matches BCBS d424 IRB floor for "
                      "downstream composition with credit_risk_irb). "
                      "Pure stdlib (math + Decimal). Per Rule 1, "
                      "AltScoringResult surfaces all 3 PillarScore "
                      "objects (per-pillar PD + confidence + features "
                      "used + skip reason) + composite + grade + "
                      "missing_pillars + framework refs. Per Rule 7, "
                      "engine never auto-approves, never auto-declines, "
                      "never writes to bureau."),
        regulatory_source="CGAP + Smart Campaign + IFC + CBK PG/03",
        citation="#260; CGAP Thin-File Lending Guidance",
        affected_engines=("credit_alt_scoring",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.47"),
    Standard(standard_id="ENH-261", category="enhancement", subcategory="credit_model_risk",
        name="Continuous Model Monitoring",
        description=("PSI (Population Stability Index), CSI (Characteristic "
                      "Stability Index), KS test, accuracy drift, fairness "
                      "metrics tracked on production models continuously."),
        regulatory_source="Continuation.docx + Fed SR 11-7",
        citation="#261; SR 11-7 ongoing monitoring",
        affected_engines=("model_governance", "credit_risk_scoring"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.28"),
    Standard(standard_id="ENH-262", category="enhancement", subcategory="credit_model_risk",
        name="AI Model Validation & Testing Suite",
        description=("Automated validation suite: backtesting, stress "
                      "testing, sensitivity analysis, scenario testing, "
                      "challenger model comparison."),
        regulatory_source="Continuation.docx",
        citation="#262",
        affected_engines=("model_governance",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.28"),
    Standard(standard_id="ENH-263", category="enhancement", subcategory="credit_model_risk",
        name="Credit Decision Explainability (Enhanced)",
        description=("SHAP/LIME enhancement: counterfactual explanations, "
                      "global vs local interpretability, customer-facing "
                      "reason narrative."),
        regulatory_source="Continuation.docx + CFPB",
        citation="#263; CFPB Circular 2023-03",
        affected_engines=("model_governance", "credit_risk_scoring"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.28"),
    Standard(standard_id="ENH-264", category="enhancement", subcategory="credit_model_risk",
        name="Vendor Model Management",
        description=("Third-party model risk: vendor due diligence, "
                      "validation of vendor models, monitoring of "
                      "vendor model performance, contractual audit rights."),
        regulatory_source="Continuation.docx + OCC 2011-12",
        citation="#264; OCC 2011-12 vendor models",
        affected_engines=("model_governance_runtime",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.29"),
    Standard(standard_id="ENH-265", category="enhancement", subcategory="credit_model_risk",
        name="Continuous Bias Monitoring",
        description=("Demographic parity, equal opportunity, predictive "
                      "parity tracked across protected groups. Auto-alert "
                      "on threshold breach. CFPB / EU AI Act compliance."),
        regulatory_source="Continuation.docx + CFPB + EU AI Act",
        citation="#265; ECOA disparate impact; EU AI Act Art. 14",
        affected_engines=("model_governance", "credit_risk_scoring"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.28"),
    Standard(standard_id="ENH-266", category="enhancement", subcategory="credit_model_risk",
        name="Automated Model Retraining Workflow",
        description=("Drift-triggered retraining pipeline: data validation, "
                      "training, validation, approval workflow, "
                      "champion-challenger deployment."),
        regulatory_source="Continuation.docx",
        citation="#266",
        affected_engines=("model_governance_runtime",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.29"),
    Standard(standard_id="ENH-267", category="enhancement", subcategory="credit_model_risk",
        name="Credit Risk Appetite Integration",
        description=("Risk appetite limits hard-coded into decisioning: "
                      "concentration, vintage, sector, geography. "
                      "Real-time limit checks at application time."),
        regulatory_source="Continuation.docx + Basel III",
        citation="#267; Basel III ICAAP",
        affected_engines=("credit_risk_scoring", "cross_sell_bandit"),
        status="active", breach_severity="CRITICAL", priority_tier="A",
        source="continuation_doc", implementation_batch="v10.32"),
    Standard(standard_id="ENH-268", category="enhancement", subcategory="credit_model_risk",
        name="Credit Committee Governance",
        description=("Credit committee diagnostic governance per CBK PG/03 "
                      "§6. Static CommitteeCharter (members + voting rule "
                      "+ min_quorum_count + required_roles + "
                      "authority_limit_kes + independent_member_min + "
                      "escalation_target). 7 CommitteeRole enums (CHAIR, "
                      "CRO, CCO, CFO, HEAD_OF_CREDIT, INDEPENDENT_MEMBER, "
                      "EXECUTIVE_MEMBER). 4 VotingRule enums "
                      "(SIMPLE_MAJORITY ties→REJECT defensively, "
                      "SUPERMAJORITY_TWO_THIRDS, UNANIMOUS, "
                      "CHAIR_TIEBREAKER). 4 VoteValue enums (YES, NO, "
                      "ABSTAIN, RECUSED). 4 QuorumStatus enums (MET, "
                      "NOT_MET_HEADCOUNT, NOT_MET_REQUIRED_ROLE, "
                      "NOT_MET_INDEPENDENT_MIN). 6 DecisionOutcome enums "
                      "(APPROVED, APPROVED_WITH_CONDITIONS, REJECTED, "
                      "DEFERRED, ESCALATED, QUORUM_FAILED). Authority "
                      "limit check supersedes voting — facilities above "
                      "limit ESCALATE without committee vote. Policy "
                      "override approvals trigger escalation per §6.7 "
                      "(approved decision still escalates upward for "
                      "ratification; rationale mandatory at construction). "
                      "Recused votes count as present but excluded from "
                      "tally; duplicate or absent-member votes ignored. "
                      "Pure stdlib (Decimal + frozen dataclasses). Per "
                      "Rule 1, every DecisionResult surfaces members "
                      "present + roles + quorum status + reason + tally "
                      "+ outcome + rationale + conditions + override + "
                      "escalation + framework refs. Per Rule 7, engine "
                      "diagnostic only — never auto-approves, never "
                      "auto-disburses, never modifies charter at runtime."),
        regulatory_source="CBK PG/03 §6 + sound credit governance practice",
        citation="#268; CBK PG/03 §6.4 + §6.6 + §6.7",
        affected_engines=("credit_committee",),
        status="active", breach_severity="HIGH", priority_tier="A",
        source="research_addition", implementation_batch="v10.48"),
)


# ────────────────────────────────────────────────────────────────────
# TRADE FINANCE MODULE — #269-#280
# ────────────────────────────────────────────────────────────────────

TRADE_FINANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(standard_id="ENH-269", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Core Instruments Engine",
        description=("Diagnostic trade finance instrument lifecycle "
                      "+ validation engine. Five capabilities: (1) "
                      "validate_issuance — pre-issuance field-level + "
                      "business-rule validation per InstrumentType "
                      "(LC requires lc_type + advising_bank warning "
                      "+ description_of_goods + incoterms + tenor "
                      "≤365d hard / ≤270d warning; SBLC + BG more "
                      "permissive; DOC_COLLECTION requires goods + "
                      "incoterms; CLEAN_COLLECTION minimal). 3 "
                      "ValidationOutcome (VALID/WARNING/INVALID) "
                      "scaled by deviation. (2) "
                      "validate_state_transition — InstrumentState "
                      "machine with 9 states (DRAFT/APPROVED/ISSUED/"
                      "AMENDED/ACTIVE/DRAWN/EXPIRED/CANCELLED/"
                      "REJECTED) and explicit allowed-transitions "
                      "matrix; DRAWN/EXPIRED/CANCELLED/REJECTED are "
                      "terminal. (3) validate_amendment — amendments "
                      "permitted only from ISSUED/AMENDED/ACTIVE; "
                      "LC + SBLC require beneficiary_consent per "
                      "UCP 600 §10 / ISP98 §2.06; > 25% amount uplift "
                      "raises soft warning to delegate to ENH-273 "
                      "limits engine. (4) compute_exposure — IFRS 9 "
                      "+ IAS 37 contingent liability measurement; "
                      "FUNDED vs UNFUNDED ExposureClassification; "
                      "drawn/undrawn portion split for LC; full "
                      "notional unfunded for SBLC/BG; clean "
                      "collection has zero contingent liability. "
                      "(5) age_pending_actions — surfaces 5 "
                      "AgingBucket states (DRAFT_STALE >7d, "
                      "APPROVED_NOT_ISSUED >3d, EXPIRY_IMMINENT ≤7d "
                      "to expiry, EXPIRED_OPEN past expiry but state "
                      "not closed, NORMAL); thresholds operator-"
                      "configurable. 5 InstrumentType × 9 "
                      "InstrumentState × 7 LcType (SIGHT/USANCE/"
                      "RED_CLAUSE/GREEN_CLAUSE/TRANSFERABLE/"
                      "BACK_TO_BACK/REVOLVING) × 6 BgType (PAYMENT/"
                      "PERFORMANCE/BID_BOND/ADVANCE_PAYMENT/"
                      "RETENTION_MONEY/WARRANTY) × 2 "
                      "ExposureClassification × 5 AgingBucket × 3 "
                      "ValidationOutcome enums. 4 frozen dataclasses "
                      "with construction-time validation: "
                      "TradeInstrument (rejects empty IDs, "
                      "applicant=beneficiary, drawn>notional, expiry "
                      "before issue, missing lc_type/bg_type by "
                      "type); AmendmentRequest (requires non-empty "
                      "reason + at least one changed field); 5 "
                      "frozen output dataclasses (IssuanceValidation, "
                      "TransitionValidation, AmendmentValidation, "
                      "ExposureMeasurement, AgingFinding) all "
                      "carrying framework_refs. Pure stdlib (Decimal "
                      "+ dataclasses + enums + date). Per Rule 1, "
                      "every output surfaces instrument_id + type + "
                      "outcome + reasons + framework refs (UCP 600 / "
                      "ISP98 / URDG 758 / URC 522 by type). Per Rule "
                      "7, engine DIAGNOSTIC ONLY — never issues "
                      "instruments (operator approval workflow); "
                      "never amends (validate_amendment surfaces "
                      "consent requirement, never applies); never "
                      "honors drawdowns; never pays beneficiaries; "
                      "never books accounting entries; never sends "
                      "SWIFT messages (ENH-272 territory); never "
                      "auto-cancels or auto-expires aged instruments; "
                      "never mutates inputs."),
        regulatory_source="ICC UCP 600 / ISP98 / URDG 758 / URC 522 / IFRS 9 + IAS 37",
        citation="#269; ENH-269 §validate_issuance/§validate_state_transition/§validate_amendment/§compute_exposure/§age_pending_actions",
        affected_engines=("trade_finance_instruments",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.70"),
    Standard(standard_id="ENH-270", category="enhancement", subcategory="trade_finance",
        name="AI-Powered Document Checking Agent",
        description=("Diagnostic UCP 600 document examination "
                      "engine for LC drawdown presentations. "
                      "Two-layer architecture: deterministic UCP "
                      "600 rule-based checks (categorical 70% "
                      "coverage — catches the obvious "
                      "discrepancies) + optional ML hook for "
                      "long-tail severity refinement (nuanced 30% "
                      "where rules over-flag false positives or "
                      "under-flag subtle non-conformances). ML "
                      "hook follows v10.76 contract — caller-"
                      "injected Callable[[Sequence[Candidate"
                      "Finding]], Sequence[ClassificationResult]] "
                      "with graceful fallback when hook raises or "
                      "returns wrong length; every output carries "
                      "ml_disabled bool + FindingMethod enum "
                      "(DETERMINISTIC_RULE / STATISTICAL_FALLBACK "
                      "/ ML_INJECTED). Five capabilities: "
                      "check_amount_tolerance (UCP 600 §30 "
                      "tolerance band; default ±5% if LC silent; "
                      "over-amount HIGH severity, under-amount "
                      "LOW since often acceptable as partial "
                      "drawdown; missing-amount-field CRITICAL), "
                      "check_dates_and_periods (UCP 600 §6 "
                      "expiry CRITICAL; §29 latest shipment "
                      "HIGH; §14(c) presentation period default "
                      "21 days HIGH), check_required_documents_"
                      "present (UCP 600 §14 — every required "
                      "DocumentType from LC.required_documents "
                      "must appear; missing = CRITICAL), "
                      "check_cross_document_consistency (UCP "
                      "600 §14(d) data conflict detection across "
                      "documents — currency consistency HIGH, "
                      "port-of-loading/discharge consistency "
                      "MEDIUM, description-of-goods overlap "
                      "MEDIUM via 60% token-overlap heuristic), "
                      "assess_presentation (orchestrator: runs "
                      "all 4 checks, collects CandidateFinding "
                      "stream, applies ML classifier or "
                      "statistical fallback, returns "
                      "PresentationAssessment with 5-tier "
                      "PresentationOutcome — CONFORMING / "
                      "DISCREPANT_WAIVABLE / DISCREPANT_REFUSAL_"
                      "LIKELY / REFUSED / INSUFFICIENT_DATA). 9 "
                      "DocumentType × 5 DiscrepancySeverity × "
                      "13 CheckCategory × 3 FindingMethod × 5 "
                      "PresentationOutcome enums. 4 input + 2 "
                      "intermediate + 2 output frozen "
                      "dataclasses. Pure stdlib runtime (re + "
                      "datetime + Decimal). ML training "
                      "pipeline ships separately in scripts/"
                      "training/train_document_classifier.py — "
                      "demonstrates end-to-end feature "
                      "engineering + stratified train/test "
                      "split + sklearn LogisticRegression "
                      "baseline + bootstrap confidence "
                      "intervals + pickle persistence + "
                      "metadata JSON; sklearn dependency in "
                      "requirements-ml.txt separate from "
                      "production runtime requirements; "
                      "trained model is SYNTHETIC-trained "
                      "until real adjudication data replaces "
                      "synthetic labeling — operators see "
                      "ml_disabled=True or False per v10.76 "
                      "contract surfacing model "
                      "demonstration vs production status. "
                      "Per Rule 1, every output surfaces UCP "
                      "600 article reference + method + "
                      "ml_disabled + framework_refs. Per Rule "
                      "7, engine DIAGNOSTIC ONLY — never "
                      "approves drawdowns (operator examines "
                      "+ decides per UCP 600 §16 within 5 "
                      "banking days), never issues notice of "
                      "refusal, never communicates with "
                      "beneficiary or applicant, never parses "
                      "PDFs or OCRs documents (upstream "
                      "structured-extraction territory — "
                      "engine consumes PresentedDocument with "
                      "already-extracted fields), never "
                      "retrains models in-place (training "
                      "pipeline is separate infrastructure), "
                      "never mutates inputs."),
        regulatory_source="UCP 600 §6 / §14 / §28 / §29 / §30 — ICC document examination standards",
        citation="#270; ENH-270 §check_amount_tolerance/§check_dates_and_periods/§check_required_documents_present/§check_cross_document_consistency/§assess_presentation; v10.76 ML hook contract",
        affected_engines=("trade_finance_document_checking",),
        threshold=Decimal("1"), threshold_unit="hours",
        threshold_direction="max",
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.78",
        global_benchmark="Conpend / Bolero / Marco Polo"),
    Standard(standard_id="ENH-271", category="enhancement", subcategory="trade_finance",
        name="Corporate Trade Portal (Front Office)",
        description=("Front-office data-validation + routing "
                      "engine for the corporate self-service "
                      "trade portal. UI lives in the trade "
                      "finance arc closure cockpit page at "
                      "v10.80; this engine is the data layer. "
                      "Five capabilities: (1) validate_lc_"
                      "application — corporate LC application "
                      "submission validation; field-level "
                      "FieldFinding objects (4-tier severity: "
                      "CRITICAL / HIGH / MEDIUM / LOW); 3-tier "
                      "ApplicationCompleteness outcome (COMPLETE "
                      "/ INCOMPLETE / INVALID); checks required "
                      "fields, currency format (ISO 4217 3-letter), "
                      "amount sanity (positive + below caller-"
                      "configurable upper bound, default 10b "
                      "KES), date ordering (latest_shipment ≤ "
                      "expiry, expiry > submission), preliminary "
                      "fee estimate (0.5% issuance — "
                      "indicative only, not a posted fee). (2) "
                      "classify_amendment_request — 8-type "
                      "AmendmentType classification (EXPIRY_"
                      "EXTENSION / AMOUNT_INCREASE / AMOUNT_"
                      "DECREASE / BENEFICIARY_CHANGE / GOODS_"
                      "DESCRIPTION_CHANGE / TERMS_CHANGE / "
                      "WITHDRAW / UNKNOWN); 3-tier "
                      "AmendmentImpact (LOW / MEDIUM / HIGH); "
                      "required_approvals tuple (operations / "
                      "credit_committee / limit_review / "
                      "compliance_screening / rm_approval) — "
                      "operator sees full picture, not just "
                      "primary type. (3) track_instrument_status "
                      "— read-only snapshot of TradeInstrument "
                      "from ENH-269 with milestones (issue / "
                      "expiry / latest_shipment / state) and "
                      "days-until calculations; surfaces None "
                      "for is_within_presentation_period when "
                      "actual shipment date not in instrument "
                      "record (per Rule 1 — surface gap rather "
                      "than fabricate). (4) validate_document_"
                      "upload — structural metadata validation "
                      "(filename extension allowed-list, size "
                      "limits, declared type, required metadata "
                      "keys); 4-tier DocumentValidationOutcome "
                      "(ACCEPTED / REJECTED_TYPE / REJECTED_"
                      "SIZE / REJECTED_METADATA); does NOT "
                      "touch file contents (upstream extraction "
                      "territory). (5) classify_message_routing "
                      "— word-boundary regex match against "
                      "caller-supplied keyword → "
                      "MessageRoutingDestination map "
                      "(operationally maintained per bank "
                      "routing policy — same discipline as "
                      "ENH-274 sanctions lists, ENH-278 "
                      "taxonomies); 4-tier MessageRoutingDestination "
                      "(OPS_QUEUE / RM_QUEUE / "
                      "ESCALATION_QUEUE / INFO_ONLY); most-"
                      "escalated destination wins on multi-"
                      "match; 3-char keyword floor; engine "
                      "bundles no keywords. 4 input dataclasses "
                      "(LCApplication, AmendmentRequest, "
                      "DocumentUpload, CorporateMessage) + 1 "
                      "intermediate (FieldFinding) + 5 output "
                      "dataclasses (LCApplicationValidation, "
                      "AmendmentClassification, "
                      "InstrumentStatusSnapshot, "
                      "DocumentUploadValidation, "
                      "MessageRoutingClassification). 3 × 4 × "
                      "8 × 3 × 4 × 4 enum cardinality "
                      "(ApplicationCompleteness × "
                      "FieldFindingSeverity × AmendmentType × "
                      "AmendmentImpact × DocumentValidationOutcome × "
                      "MessageRoutingDestination). Pure stdlib "
                      "(re + datetime + Decimal). Per Rule 1, "
                      "every output surfaces validation findings "
                      "+ routing rationale + framework_refs "
                      "(UCP 600 §6 / §10 / §14(e) / §29; ISO "
                      "4217). Per Rule 7, engine NEVER issues "
                      "LCs (operations layer territory after "
                      "corporate submits + bank approves), "
                      "never amends LCs (operations layer), "
                      "never stores documents (document "
                      "management system territory), never "
                      "sends messages or notifications "
                      "(messaging system territory), never "
                      "posts fees or accounting entries (ENH-"
                      "275 territory), never decides "
                      "accept/reject on applications (RM + "
                      "Credit decide based on engine output), "
                      "never mutates inputs."),
        regulatory_source="UCP 600 §6 (expiry) / §10 (amendments) / §14(e) (description requirement) / §29 (latest shipment); ISO 4217 (currency codes)",
        citation="#271; ENH-271 §validate_lc_application/§classify_amendment_request/§track_instrument_status/§validate_document_upload/§classify_message_routing",
        affected_engines=("trade_finance_corporate_portal",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.79"),
    Standard(standard_id="ENH-272", category="enhancement", subcategory="trade_finance",
        name="SWIFT Integration",
        description=("Diagnostic SWIFT MT message validation engine "
                      "for the four trade-finance message types most "
                      "relevant to LC + guarantee + payment workflows: "
                      "MT700 (issue of documentary credit), MT707 (LC "
                      "amendment), MT760 (issuance of demand "
                      "guarantee/standby LC), MT103 (single customer "
                      "credit transfer for settlement). Five "
                      "capabilities: (1) parse_message — splits raw "
                      "MT block 4 body into tagged fields ({:NN[X]:value} "
                      "format) preserving multi-line values + field "
                      "order; auto-strips block 4 wrapper if present. "
                      "(2) validate_mt700_structure — mandatory field "
                      "checks (~12 mandatory tags including :27: :40A: "
                      ":20: :31C: :31D: :50: :59: :32B: :45A: :46A: "
                      ":49:); regex-based format conformance per tag "
                      "(e.g. :27: '1/1' pattern, :32B: 'CCC###,##' "
                      "currency+amount, :31C: 'YYMMDD' date); cross-"
                      "field consistency check (issue date :31C: ≤ "
                      "expiry date :31D:). (3) validate_mt707_structure "
                      "— amendment-specific (mandatory :21: receiver's "
                      "reference linking to original LC, :26E: "
                      "amendment number, optional new amount/expiry "
                      "fields). (4) validate_mt760_structure — "
                      "guarantee-specific (mandatory :40C: applicable "
                      "rules — URDG/ISP98/UCP/OTHER, :77C: details of "
                      "guarantee). (5) validate_mt103_structure — "
                      "payment-specific (mandatory :23B: bank operation "
                      "code, :32A: value-date+currency+amount, :71A: "
                      "details of charges — BEN/OUR/SHA). Plus cross-"
                      "checker: cross_check_mt700_against_instrument "
                      "consumes TradeInstrument from ENH-269 and "
                      "compares :20: vs instrument_id, :32B: currency+"
                      "amount vs instrument fields, :50: applicant + "
                      ":59: beneficiary via substring match; surfaces "
                      "DIVERGENT outcome when fields don't align. 4 "
                      "SwiftMessageType × 5 FieldStatus (PRESENT/"
                      "MISSING_MANDATORY/MISSING_OPTIONAL/MALFORMED/"
                      "UNEXPECTED) × 3 MessageValidationOutcome × 3 "
                      "CrossCheckOutcome (ALIGNED/DIVERGENT/"
                      "UNCHECKABLE) enums. Frozen dataclasses: "
                      "FieldSpec (per-tag constraint), SwiftField "
                      "(parsed tag+value), ParsedMessage, FieldFinding, "
                      "MessageValidation, CrossCheckFinding, "
                      "CrossCheckReport. completeness_pct surfaces % "
                      "of mandatory fields present (Decimal). Pure "
                      "stdlib (re for tag parsing). Per Rule 1, every "
                      "output surfaces field-by-field findings + "
                      "framework refs (SWIFT MT Standards + ICC UCP "
                      "600/URDG 758/ISP98 alignment per message type). "
                      "Per Rule 7, engine DIAGNOSTIC ONLY — never "
                      "sends MT messages over SWIFTNet (caller's "
                      "responsibility); never auto-corrects malformed "
                      "fields; never generates messages from instrument "
                      "records (would require LO/SR routing decisions "
                      "outside scope); never submits to SWIFT for "
                      "validation (offline/local); never modifies "
                      "network routing; never mutates inputs."),
        regulatory_source="SWIFT MT Standards + ICC UCP 600 / ISP98 / URDG 758",
        citation="#272; SWIFT MT700/707/760/103; ENH-272 §parse/§validate_mt700/§validate_mt707/§validate_mt760/§validate_mt103/§cross_check",
        affected_engines=("trade_finance_swift",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.72"),
    Standard(standard_id="ENH-273", category="enhancement", subcategory="trade_finance",
        name="Limits & Risk Management",
        description=("Diagnostic pre-deal + post-deal limit "
                      "utilization engine across 4 dimensions. "
                      "Consumes TradeInstrument from ENH-269 + "
                      "operator-set limits per dimension. Distinct "
                      "from ENH-252 (CBK bank-wide single-borrower "
                      "aggregate) — ENH-273 operates at trade-finance "
                      "product level for per-instrument allocation "
                      "decisions. Four dimensions: COUNTRY (foreign "
                      "country sovereign + counterparty risk via "
                      "CountryAttribution mapping beneficiary to "
                      "ISO-3166 code), COUNTERPARTY (per-corporate "
                      "exposure aggregated by APPLICANT, not "
                      "beneficiary, since applicant carries the "
                      "default risk to the bank in trade finance), "
                      "PRODUCT (concentration in single InstrumentType "
                      "— LC/SBLC/BG/Doc/Clean Collection), TENOR (4 "
                      "TenorBucket — SHORT ≤90d / MEDIUM 91-180d / "
                      "LONG 181-365d / EXTRA_LONG >365d; long-tenor "
                      "concentration worsens liquidity profile). "
                      "Each dimension is opt-in: if no limits "
                      "configured, dimension returns nothing (caller "
                      "chose not to track); if limits configured but "
                      "specific bucket missing, surfaces 'policy gap' "
                      "BREACH. 4-tier UtilizationSeverity by % of "
                      "limit consumed: HEALTHY ≤70%, ELEVATED 70-85%, "
                      "HIGH 85-100%, BREACH >100%; thresholds "
                      "operator-configurable. Closed instruments "
                      "(EXPIRED/CANCELLED/REJECTED/DRAWN) excluded "
                      "from exposure computation since they no longer "
                      "consume limits. Pre-deal check returns 4 "
                      "PreDealOutcome (APPROVE_LIKELY when post-deal "
                      "HEALTHY, REVIEW_NEEDED when ELEVATED, "
                      "SENIOR_APPROVAL when HIGH, BLOCK_RECOMMENDED "
                      "when BREACH); identifies binding_dimension "
                      "(tightest constraint affected by proposed). "
                      "build_portfolio_report orchestrates all 4 "
                      "dimensions returning PortfolioLimitReport with "
                      "by_severity + by_dimension aggregates + "
                      "breached_count. 4 LimitDimension × 4 "
                      "TenorBucket × 4 UtilizationSeverity × 4 "
                      "PreDealOutcome enums. 5 frozen input "
                      "dataclasses (CountryLimit, CounterpartyLimit, "
                      "ProductLimit, TenorLimit, CountryAttribution) "
                      "with construction-time validation (non-empty "
                      "IDs, positive limits). 3 frozen output "
                      "dataclasses (LimitUtilization, PreDealCheck, "
                      "PortfolioLimitReport). Pure stdlib (Decimal + "
                      "dataclasses + enums). Per Rule 1, every "
                      "LimitUtilization surfaces dimension + "
                      "exposure + limit + utilization% + headroom + "
                      "severity + contributing_instrument_ids + "
                      "framework refs. Per Rule 7, engine DIAGNOSTIC "
                      "ONLY — never approves or rejects deals "
                      "(computes utilization only); never blocks "
                      "instrument issuance; never posts limit "
                      "allocations to source systems; never amends "
                      "operator-set limits; never sources market "
                      "data; never auto-rebalances portfolio; never "
                      "mutates inputs."),
        regulatory_source="Basel — country/single-name concentration; CBK PG/04 SBL (composes with ENH-252)",
        citation="#273; ENH-273 §country/§counterparty/§product/§tenor/§check_pre_deal",
        affected_engines=("trade_finance_limits",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.71"),
    Standard(standard_id="ENH-274", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Compliance Engine",
        description=("Diagnostic sanctions + dual-use + restricted-port "
                      "screening engine for trade finance instruments. "
                      "Surfaces compliance exposure across 5 "
                      "ScreeningDimension: PARTY (applicant + "
                      "beneficiary + advising bank against caller-"
                      "supplied SanctionsListEntry from OFAC SDN / UN "
                      "Consolidated / EU Restrictive Measures / UK "
                      "HMT), COUNTRY (applicant + beneficiary + "
                      "transit countries against CountryEmbargo with "
                      "ISO-3166-alpha-2 codes), PORT (loading + "
                      "discharge against RestrictedPort UN/LOCODE-"
                      "preferred), VESSEL (name + IMO against "
                      "DesignatedVessel — IMO match preferred for "
                      "reliability, name fallback when IMO unknown), "
                      "GOODS (description against "
                      "ProhibitedGoodsKeyword from Wassenaar / EU "
                      "Regulation 2021/821 / Kenyan Strategic Trade "
                      "Authorisation with category tagging — "
                      "DUAL_USE_NUCLEAR / DUAL_USE_BIO / WEAPONS / "
                      "etc.). Operates with caller-supplied list "
                      "data; engine does NOT bundle sanctions data — "
                      "list maintenance is operationally separate "
                      "(updated daily by ops). Matching: 4 MatchType "
                      "(EXACT — identifier == identifier; NORMALIZED "
                      "— after lowercase + whitespace collapse + "
                      "punctuation strip; SUBSTRING — bidirectional "
                      "substring with min 4-char floor to avoid false "
                      "positives on short fragments; ALIAS — matched "
                      "via SanctionsListEntry.aliases tuple). Goods "
                      "matching uses word-boundary regex to prevent "
                      "false positives ('antibiotic' does not match "
                      "'ant' keyword). 5 HitSeverity (CRITICAL OFAC/UN "
                      "/ HIGH EU/UK / MEDIUM internal / LOW review-"
                      "only / INFO informational) attributed by "
                      "caller per source list. screen_instrument "
                      "orchestrator returns ScreeningReport with 4 "
                      "ScreeningOutcome (CLEAR no hits / "
                      "REVIEW_NEEDED any LOW+ / SENIOR_APPROVAL any "
                      "HIGH / BLOCK_RECOMMENDED any CRITICAL) + "
                      "by_dimension and by_severity aggregates. "
                      "Caller-supplied alias expansion via party "
                      "aliases tuple. 5 ScreeningDimension × 5 "
                      "HitSeverity × 4 ScreeningOutcome × 4 "
                      "MatchType enums. 5 frozen input dataclasses "
                      "(SanctionsListEntry, CountryEmbargo, "
                      "RestrictedPort, DesignatedVessel, "
                      "ProhibitedGoodsKeyword) + TradeFinanceParty + "
                      "TradeFinanceShipment for screening targets. "
                      "Pure stdlib (re for word-boundary matching). "
                      "Per Rule 1, every ScreeningHit surfaces "
                      "dimension + matched_field_label + matched_"
                      "value + matched_against + source_list_id + "
                      "match_type + severity + framework refs (always "
                      "cite source list authority). Per Rule 7, "
                      "engine DIAGNOSTIC ONLY — never blocks "
                      "transactions; never reports to OFAC / KFIU / "
                      "FRC (these are operator duties under Kenya "
                      "POCAMLA + Proceeds of Crime and Anti-Money "
                      "Laundering Act); never freezes assets or "
                      "accounts; never submits SARs (Suspicious "
                      "Activity Reports); never amends sanctions "
                      "lists; never decides true vs false positive "
                      "(caller adjudicates each hit per L1/L2/L3 "
                      "review process); never mutates inputs."),
        regulatory_source="OFAC SDN / UN Consolidated / EU Restrictive Measures / UK HMT / Wassenaar Arrangement / Kenya POCAMLA",
        citation="#274; ENH-274 §screen_party/§screen_country/§screen_port/§screen_vessel/§screen_goods/§screen_instrument",
        affected_engines=("trade_finance_compliance",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="research_addition", implementation_batch="v10.73"),
    Standard(standard_id="ENH-275", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Accounting & Integration",
        description=("Diagnostic accounting + capital integration "
                      "engine. Consumes TradeInstrument from ENH-269. "
                      "5 capabilities: (1) compute_ccf — Basel III "
                      "Credit Conversion Factor lookup by 6 "
                      "BaselCcfBucket (DOCUMENTARY_LC_SHORT 0.20, "
                      "DOCUMENTARY_LC_LONG 0.50, SBLC_GUARANTEE 1.00, "
                      "PERFORMANCE_BG 0.50, DOC_COLLECTION 0.20, "
                      "CLEAN_COLLECTION 0.00) per CBK PG/04 + Basel "
                      "III CRE 22.20-30; partial-draw aware (undrawn "
                      "× CCF for LC + DOC_COLLECTION); bucket "
                      "override accepted for caller discretion (e.g. "
                      "payment vs performance BG). (2) compute_"
                      "capital_impact — applies caller-supplied "
                      "risk_weight (validated 0..1.5) to credit "
                      "equivalent → RWA → capital required at 8% "
                      "Basel minimum. (3) generate_journal_template "
                      "— IFRS 9 + IAS 37 journal templates per 7 "
                      "JournalEvent (ISSUE booking contingent + fee "
                      "income; DRAWDOWN reversing contingent + "
                      "creating receivable + cash payment; EXPIRE "
                      "reversing contingent; CANCEL identical to "
                      "EXPIRE; AMEND_INCREASE / AMEND_DECREASE "
                      "delta posting; FEE_RECOGNITION standalone "
                      "fee accrual). 6 AccountClass (CONTINGENT_"
                      "LIABILITY / RECEIVABLE / PAYABLE / FEE_INCOME "
                      "/ FX_REVALUATION / CASH); 2 JournalSide "
                      "(DEBIT / CREDIT). (4) validate_journal_"
                      "balance — confirms DR sum == CR sum across "
                      "templates; 3 BalanceCheckOutcome (BALANCED / "
                      "UNBALANCED / EMPTY) with explicit difference. "
                      "(5) build_off_balance_sheet_disclosure — "
                      "IAS 37 disclosure helper rolling up notional "
                      "+ contingent liability + credit equivalent "
                      "+ by-instrument-type breakdown for active "
                      "instruments only (ISSUED/AMENDED/ACTIVE "
                      "states; closed states excluded). 6 "
                      "BaselCcfBucket × 7 JournalEvent × 6 "
                      "AccountClass × 2 JournalSide × 3 "
                      "BalanceCheckOutcome enums. 6 frozen output "
                      "dataclasses with construction-time validation "
                      "(JournalLine rejects negative amount_kes — "
                      "sign carried by side). Pure stdlib (Decimal "
                      "+ dataclasses + enums). Per Rule 1, every "
                      "output surfaces instrument_id + journal_event "
                      "+ Decimal amounts + framework_refs (IFRS 9 "
                      "§5.5 + IAS 37 §10 + IFRS 15 fee revenue + "
                      "Basel III CRE 22.20-30 + CBK PG/04). Per "
                      "Rule 7, engine DIAGNOSTIC ONLY — never posts "
                      "journals to GL (operator approves + posts "
                      "via core banking workflow); never updates "
                      "capital ratios in GL; never modifies risk "
                      "weights (operator-set per CBK / Basel "
                      "discretion); never submits regulatory "
                      "capital returns (cbk_regulatory_reporting "
                      "territory); never mutates inputs."),
        regulatory_source="IFRS 9 §5.5 / IAS 37 §10 / IFRS 15 / Basel III CRE 22.20-30 / CBK PG/02 + PG/04",
        citation="#275; ENH-275 §compute_ccf/§compute_capital_impact/§generate_journal_template/§validate_journal_balance/§build_off_balance_sheet_disclosure",
        affected_engines=("trade_finance_accounting",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.75"),
    Standard(standard_id="ENH-276", category="enhancement", subcategory="trade_finance",
        name="Multi-Bank Connectivity & Digital Networks",
        description=("Diagnostic adapter surface for inbound "
                      "trade-finance network messages — "
                      "we.trade / Marco Polo / Contour / Bolero "
                      "/ SWIFT GPI / SWIFT FIN / OTHER. Engine "
                      "validates structure + maps foreign "
                      "protocol fields to internal schema + "
                      "classifies routing actions + detects "
                      "anomalies + rolls up reports. Caller-"
                      "supplied protocol_required_fields "
                      "(operationally maintained per network "
                      "version updates — same discipline as "
                      "ENH-274 sanctions lists, ENH-278 "
                      "taxonomies; defaults supplied for the 6 "
                      "major networks reflecting publicly-"
                      "documented field lists 2025-2026). Five "
                      "capabilities: (1) validate_inbound_"
                      "message_structure — required fields per "
                      "protocol; 4-tier MessageValidationStatus "
                      "(VALID / MISSING_REQUIRED_FIELDS / "
                      "MALFORMED / UNKNOWN_PROTOCOL); empty "
                      "strings treated as MALFORMED not VALID. "
                      "(2) map_to_internal_schema — projects "
                      "via caller-supplied FieldMapping "
                      "sequence; surfaces unmapped_inbound_"
                      "fields + missing_required_internal_"
                      "fields per Rule 1 — engine never "
                      "fabricates values, never silently drops; "
                      "skips empty inbound values. (3) "
                      "classify_routing_action — caller-"
                      "supplied message_type → RoutingAction "
                      "map (NEW_LC_ISSUANCE / AMENDMENT_"
                      "NOTIFICATION / DRAWDOWN_NOTIFICATION / "
                      "DOCUMENT_DISPATCH / STATUS_UPDATE / "
                      "PAYMENT_INSTRUCTION / UNKNOWN); UNKNOWN "
                      "surfaced rather than guessing when "
                      "message_type missing. (4) detect_"
                      "protocol_anomalies — duplicate "
                      "message_id (HIGH severity), out-of-"
                      "sequence per (network × sender) stream "
                      "(MEDIUM), version_mismatch against "
                      "caller-supplied supported_versions per "
                      "network (MEDIUM), unknown_sender against "
                      "caller-supplied known_senders set "
                      "(MEDIUM). (5) build_connectivity_report "
                      "— orchestrator: by_network_count + "
                      "by_status_count + by_action_count + "
                      "anomaly_count_by_type + top_5 "
                      "error_types. 7 TradeNetwork × 4 "
                      "MessageValidationStatus × 7 "
                      "RoutingAction × 4 AnomalyType × 3 "
                      "AnomalySeverity enums. 2 input + 1 "
                      "intermediate + 5 output frozen "
                      "dataclasses. Pure stdlib (Counter + "
                      "datetime). Per Rule 1, every output "
                      "surfaces validation findings + protocol "
                      "references + matched fields with "
                      "sources. Per Rule 7, engine NEVER sends "
                      "outbound messages or notifications, "
                      "never connects to external networks, "
                      "never processes payments or settles "
                      "obligations, never decides accept/reject "
                      "on inbound messages (operator examines "
                      "findings + decides per banking "
                      "workflow), never mutates messages or "
                      "augments fields beyond explicit caller-"
                      "supplied mappings (no implicit "
                      "fabrication), never retains message "
                      "contents (audit-log responsibility lives "
                      "elsewhere)."),
        regulatory_source="we.trade / Marco Polo / Contour / Bolero / SWIFT GPI / SWIFT FIN — published protocol specifications 2025-2026",
        citation="#276; ENH-276 §validate_inbound_message_structure/§map_to_internal_schema/§classify_routing_action/§detect_protocol_anomalies/§build_connectivity_report",
        affected_engines=("trade_finance_connectivity",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="research_addition", implementation_batch="v10.79",
        global_benchmark="we.trade / Marco Polo / Contour"),
    Standard(standard_id="ENH-277", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Dashboard",
        description=("Trade ops dashboard fulfilled by the "
                      "trade_finance arc closure cockpit page "
                      "at pages/97_trade_finance_arc_cockpit.py "
                      "(activated v10.80). The cockpit "
                      "consumes outputs from the 10 trade "
                      "finance arc engines (ENH-269 through "
                      "ENH-280 minus ENH-279 which is deferred) "
                      "and renders pipeline view + processing "
                      "time analytics + exception aging + "
                      "top-corporates ranking + country "
                      "exposure heat-map. Per Rule 7, cockpit "
                      "is operator-driven (no auto-action) and "
                      "wraps all engine invocations in "
                      "require_access() + audit_log() per the "
                      "G130 UI integration ratchet pattern. "
                      "Engine target: trade_finance_arc_cockpit "
                      "(Streamlit page, not a class) — the "
                      "dashboard responsibility lives in the "
                      "UI layer because dashboards are "
                      "presentation concerns, not engine-"
                      "computation concerns. The 10 underlying "
                      "engines compute the data; the cockpit "
                      "page composes views from that data."),
        regulatory_source="Internal — operations dashboard requirements",
        citation="#277; pages/97_trade_finance_arc_cockpit.py",
        affected_engines=(
            "trade_finance_instruments",
            "trade_finance_limits",
            "trade_finance_swift",
            "trade_finance_compliance",
            "trade_finance_accounting",
            "trade_finance_reporting",
            "trade_finance_sustainability",
            "trade_finance_document_checking",
            "trade_finance_corporate_portal",
            "trade_finance_connectivity"),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="research_addition", implementation_batch="v10.80"),
    Standard(standard_id="ENH-278", category="enhancement", subcategory="trade_finance",
        name="Sustainable Trade Finance",
        description=("Diagnostic ESG / climate / sustainability "
                      "screening engine for trade finance "
                      "instruments. Operates entirely with caller-"
                      "supplied data — taxonomy + exclusion list + "
                      "emission factors + ESG attribution maps "
                      "operationally maintained per KGFT (Kenya "
                      "Green Finance Taxonomy 2025) update cadences "
                      "+ KBA Sustainable Finance Initiative + EU "
                      "Taxonomy + ICC SDG Trade Finance Standards + "
                      "PCAF (Partnership for Carbon Accounting "
                      "Financials) data hierarchy + rating agency "
                      "feeds (MSCI ESG / Sustainalytics / ISS ESG). "
                      "Engine bundles no lists, classifications, or "
                      "factors — same discipline as ENH-274 "
                      "sanctions-list pattern. Five capabilities: "
                      "(1) classify_instrument_sustainability — "
                      "word-boundary regex match against caller-"
                      "supplied TaxonomyEntry sequence (keyword + "
                      "tier + source + justification); 4-tier "
                      "SustainabilityTier (GREEN / TRANSITION / "
                      "BROWN / UNCLASSIFIED) where UNCLASSIFIED is "
                      "the no-match outcome (TaxonomyEntry rejects "
                      "UNCLASSIFIED at construction); ALL matches "
                      "surfaced per Rule 1 (operator sees every "
                      "signal not just engine pick); primary_tier "
                      "is most-conservative-tier-present (BROWN > "
                      "TRANSITION > GREEN > UNCLASSIFIED) so worst-"
                      "case signal flagged first; conflicting bool "
                      "flag when matches span multiple tiers. (2) "
                      "screen_exclusion_list — word-boundary match "
                      "against caller-supplied ExclusionEntry "
                      "sequence (KBA SFI prohibited sectors, "
                      "internal policy, regulator-mandated "
                      "exclusions); 4-tier ExclusionSeverity "
                      "(CRITICAL absolute / HIGH bank-level / "
                      "MEDIUM senior-approval / LOW review-only); "
                      "5-tier SustainabilityScreeningOutcome "
                      "ladder (ELIGIBLE_GREEN / ELIGIBLE_TRANSITION "
                      "/ REVIEW_NEEDED / SENIOR_APPROVAL / "
                      "EXCLUDED). (3) compute_ghg_attribution — "
                      "PCAF Global GHG Accounting & Reporting "
                      "Standard for Financed Emissions: amount × "
                      "emission_factor where factor is sector-"
                      "specific kg CO2e per KES financed; caller-"
                      "supplied sector_attribution + "
                      "emission_factors maps; 3-tier "
                      "GhgAttributionStatus (ATTRIBUTED / "
                      "SECTOR_UNKNOWN / FACTOR_UNKNOWN) — surfaces "
                      "gap rather than fabricating zero. (4) "
                      "assess_counterparty_esg_risk — applicant + "
                      "beneficiary risk lookup via caller-supplied "
                      "EsgRiskTier attribution map (LOW / MEDIUM / "
                      "HIGH / SEVERE / UNRATED); worst-of-pair "
                      "surfaced (UNRATED treated as least severe so "
                      "rating gap visible not masked). (5) "
                      "build_sustainability_report — portfolio "
                      "orchestrator: green/transition/brown/"
                      "unclassified shares + total attributed "
                      "emissions + unattributed_count + top-5 "
                      "emitting sectors + exclusion hit counts "
                      "(total + critical) + ESG risk distribution; "
                      "active states only (ISSUED/AMENDED/ACTIVE) "
                      "— closed instruments excluded from current "
                      "snapshot. 4 SustainabilityTier × 4 "
                      "ExclusionSeverity × 5 EsgRiskTier × 5 "
                      "SustainabilityScreeningOutcome × 3 "
                      "GhgAttributionStatus enums. 9 frozen output "
                      "dataclasses. Pure stdlib (re for word-"
                      "boundary regex; Decimal for emissions math; "
                      "no third-party dependencies). MIN_KEYWORD_"
                      "LENGTH = 3 character floor on taxonomy + "
                      "exclusion keywords (rejected at "
                      "construction) — same discipline as ENH-274 "
                      "to prevent substring false positives. Per "
                      "Rule 1, every output surfaces matched_"
                      "keywords + sources + framework_refs (KGFT / "
                      "KBA SFI / EU Taxonomy / ICC SDG / PCAF / "
                      "TCFD / Equator Principles). Per Rule 7, "
                      "engine DIAGNOSTIC ONLY — never sets "
                      "classifications (taxonomy is caller-"
                      "supplied; engine looks up only); never "
                      "blocks transactions (operator adjudicates "
                      "per outcome ladder); never amends taxonomy "
                      "or exclusion list (operationally separate); "
                      "never reports to CBK / regulators (climate "
                      "disclosure flows through ENH-CLIM-* "
                      "engines); never adjusts pricing or terms "
                      "(RM / pricing system territory); never "
                      "sources emission factors or ESG ratings "
                      "(caller supplies); never mutates inputs."),
        regulatory_source="KGFT Kenya Green Finance Taxonomy 2025 / KBA Sustainable Finance Initiative / EU Taxonomy / ICC SDG Trade Finance Standards / PCAF Global GHG Accounting & Reporting Standard / TCFD / Equator Principles",
        citation="#278; ENH-278 §classify_instrument_sustainability/§screen_exclusion_list/§compute_ghg_attribution/§assess_counterparty_esg_risk/§build_sustainability_report",
        affected_engines=("trade_finance_sustainability",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="research_addition", implementation_batch="v10.77"),
    Standard(standard_id="ENH-279", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Mobile App",
        description=("DEFERRED at v10.80 trade_finance arc "
                      "closure as a UI delivery concern that "
                      "doesn't fit the diagnostic-engine "
                      "pattern. Scope-resolution rationale: "
                      "the corporate portal data layer (ENH-271 "
                      "trade_finance_corporate_portal) supports "
                      "both web and mobile UI clients via the "
                      "same Python data-layer API "
                      "(LCApplication / AmendmentRequest / "
                      "DocumentUpload / CorporateMessage input "
                      "dataclasses; LCApplicationValidation / "
                      "AmendmentClassification / "
                      "InstrumentStatusSnapshot / "
                      "DocumentUploadValidation / "
                      "MessageRoutingClassification output "
                      "dataclasses). Any mobile-specific "
                      "delivery (iOS / Android native, React "
                      "Native, PWA) is a UI client concern "
                      "consuming that API, not an engine-"
                      "architecture concern. The diagnostic-"
                      "engine codebase does not own UI "
                      "delivery for any platform — web cockpit "
                      "pages are presentational thin wrappers "
                      "around the engines, and mobile clients "
                      "would be the same shape on a different "
                      "presentation stack. Status remains "
                      "'planned' rather than 'active' because "
                      "no engine-side artifact is needed; "
                      "mobile delivery is a separately-funded "
                      "UI workstream when business prioritizes. "
                      "G137 closure gate verifies this "
                      "deferral note is documented (the gate "
                      "tolerates 11/12 active + 1/12 explicitly "
                      "deferred-with-rationale)."),
        regulatory_source="Internal — UI delivery roadmap, separate workstream",
        citation="#279; ENH-271 supports mobile UI clients via data-layer API",
        affected_engines=("trade_finance_corporate_portal",),
        status="active", breach_severity="LOW", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.289"),
    Standard(standard_id="ENH-280", category="enhancement", subcategory="trade_finance",
        name="Trade Finance Reporting & Analytics",
        description=("Diagnostic reporting + analytics engine for "
                      "trade finance portfolios with optional ML "
                      "extension hooks for accuracy improvement over "
                      "time. Six capabilities: (1) compute_trade_"
                      "volumes — deterministic aggregation by period "
                      "+ instrument type + counterparty + country "
                      "(beneficiary-side via caller-supplied "
                      "country_attribution map; UNKNOWN tagged when "
                      "absent). (2) compute_country_exposure — "
                      "Herfindahl-Hirschman Index Σ(share²) on per-"
                      "country exposure for active instruments only "
                      "(ISSUED/AMENDED/ACTIVE) + top_3_share + top_5_"
                      "share + 3-tier ConcentrationSeverity "
                      "(DIVERSIFIED HHI ≤0.15 / MODERATE 0.15-0.25 / "
                      "CONCENTRATED >0.25). (3) compute_sector_"
                      "concentration — applicant-side sector "
                      "Herfindahl + top_3_share + severity. (4) "
                      "detect_volume_anomalies — ML-extensible "
                      "anomaly detection on time-series period "
                      "totals; statistical fallback uses Modified "
                      "Z-score on log-volume (Iglewicz & Hoaglin "
                      "1993) with median absolute deviation for "
                      "robustness to outliers self-suppressing; "
                      "saturated to [0,1] score range; 3 "
                      "AnomalySeverity (NORMAL <0.50 / WATCH "
                      "0.50-0.75 / ALERT ≥0.75); short series "
                      "(<4 periods) returns no findings; flat "
                      "series returns no findings. (5) forecast_"
                      "volume_trajectory — ML-extensible n-period "
                      "forecast; statistical fallback uses Ordinary "
                      "Least Squares regression on most recent 12 "
                      "periods with negative-value clipping to "
                      "zero (volumes can't be negative); horizon "
                      "validated 1..36 (>36 unreliable for any "
                      "method, rejected by policy); short history "
                      "(<3 periods) returns flat last-observation "
                      "forecast. (6) build_management_report — "
                      "orchestrator returning ManagementReport "
                      "with all 5 outputs + overall_ml_disabled "
                      "aggregation flag. ML EXTENSION CONTRACT: "
                      "engine constructor accepts optional "
                      "ml_anomaly_scorer (Sequence[Decimal] → "
                      "Sequence[float]) and ml_forecaster "
                      "(Sequence[Decimal] + horizon → "
                      "Sequence[Decimal]) callables. When "
                      "injected hook raises or returns wrong "
                      "length, engine falls back gracefully to "
                      "statistical method and surfaces ml_disabled "
                      "= True so operator knows the heuristic "
                      "ran. Per Rule 6, every AnomalyFinding + "
                      "VolumeForecast carries explicit ml_disabled "
                      "flag (True iff statistical fallback) + "
                      "method enum (STATISTICAL_FALLBACK / "
                      "ML_INJECTED / DETERMINISTIC). 3 "
                      "AnomalySeverity × 3 ConcentrationSeverity × "
                      "3 AnalysisMethod enums. 6 frozen output "
                      "dataclasses. Pure stdlib (Decimal + "
                      "statistics module for fallback math). PATH "
                      "TO ACCURACY IMPROVEMENT: engine is consumer "
                      "side of separate ML training pipeline (not "
                      "in this engine) which collects historical "
                      "period totals + operator adjudications, "
                      "trains anomaly scorers + forecasters with "
                      "holdout evaluation, versions and serializes "
                      "models, health-checks for drift before "
                      "injection. Until pipeline matures, "
                      "statistical fallback runs and ml_disabled "
                      "is True in every output. Per Rule 1, every "
                      "output surfaces method + ml_disabled + "
                      "framework refs. Per Rule 7, engine "
                      "DIAGNOSTIC ONLY — never acts on anomaly "
                      "findings (operator adjudicates each); "
                      "never submits regulatory reports (cbk_"
                      "regulatory_reporting territory); never "
                      "publishes management dashboards (cockpit "
                      "page consumes); never retrains models in-"
                      "place (training is separate infrastructure); "
                      "never mutates inputs."),
        regulatory_source="HHI concentration discipline / Iglewicz & Hoaglin 1993 modified z-score / OLS regression / CBK + BIS reporting expectations",
        citation="#280; ENH-280 §compute_trade_volumes/§compute_country_exposure/§compute_sector_concentration/§detect_volume_anomalies/§forecast_volume_trajectory/§build_management_report",
        affected_engines=("trade_finance_reporting",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.76"),
    Standard(standard_id="ENH-281", category="enhancement", subcategory="ml_governance",
        name="MLOps Model Registry",
        description=("Diagnostic operational-lifecycle engine "
                      "for tracking ML model versions across the "
                      "platform. Distinct from utils.model_"
                      "governance (closed at G124) which handles "
                      "model risk classification + validation "
                      "testing + drift detection (PSI / KS / "
                      "Wasserstein) + bias monitoring + "
                      "explainability. This engine handles the "
                      "operational deployment lifecycle — version "
                      "chains per model_id, artifact hashes, "
                      "training-data hashes, framework versions, "
                      "promotion readiness assessment. The "
                      "boundary is deliberate: a model can be "
                      "VALIDATED (per model_governance) but not "
                      "yet PROMOTED (per this registry). "
                      "Operational status PROPOSED → SHADOW → "
                      "ACTIVE → DEPRECATED → RETIRED is "
                      "orthogonal to the validation lifecycle "
                      "DRAFT → REVIEW → APPROVED → DECOMMISSIONED. "
                      "Both stages must clear independently before "
                      "a model serves production. Five "
                      "capabilities: (1) register_new_model_"
                      "version — input validation (SHA-256 hash "
                      "format + framework recognition + metric "
                      "Decimal/non-NaN sanity) + entry "
                      "construction with status=PROPOSED; "
                      "RegistrationOutcome REGISTERED / "
                      "REJECTED_INVALID. Per Rule 7, engine never "
                      "persists — caller appends to their "
                      "registry storage. (2) lookup_active_"
                      "version — single ACTIVE per model_id (or "
                      "None); surfaces multiple_active_violation "
                      "as governance breach when active_count > 1 "
                      "(operations must demote all but one — "
                      "engine never auto-demotes). (3) "
                      "list_versions — filter by model_id and "
                      "optional status_filter; sorted most-recent-"
                      "first by created_at_iso. (4) compare_"
                      "versions — diagnostic delta surface: "
                      "MetricDelta per shared metric (b - a), "
                      "framework_match flag, framework_version_"
                      "match flag, training_data_hash_match flag, "
                      "artifact_hash_match flag. Per Rule 1, all "
                      "axes surface explicitly. Per Rule 7, "
                      "engine never recommends one over the "
                      "other. (5) validate_promotion_readiness — "
                      "caller-supplied PromotionGate sequence "
                      "evaluated against candidate (and current_"
                      "active for non-regression). Three gate "
                      "types: MINIMUM_METRIC (candidate.metric ≥ "
                      "or ≤ threshold via GateComparison "
                      "GTE/LTE), NON_REGRESSION (candidate.metric "
                      "vs active.metric ± regression_tolerance), "
                      "METADATA_REQUIRED (named field present + "
                      "non-empty). Per-gate GateFinding with "
                      "PASS/FAIL/INSUFFICIENT_DATA severity. "
                      "Outcome READY (all PASS) / BLOCKED (any "
                      "FAIL) / INSUFFICIENT_DATA (any "
                      "INSUFFICIENT). Per Rule 1, every gate "
                      "finding surfaced (not just first failure). "
                      "Per Rule 7, engine never auto-promotes — "
                      "operator decides. Caller-supplied data "
                      "discipline (matches ENH-274 sanctions / "
                      "ENH-278 taxonomies / ENH-271 keyword "
                      "catalogues / ENH-276 protocol fields): "
                      "registry sequence + PromotionGate sequence "
                      "+ recognized_frameworks all caller-"
                      "supplied; engine bundles defaults for "
                      "frameworks (sklearn / torch / tensorflow / "
                      "onnx / xgboost / lightgbm / statsmodels / "
                      "transformers / custom) but caller REPLACES "
                      "via constructor. 5 ModelStatus × 3 "
                      "GateType × 2 GateComparison × 3 "
                      "GateFindingSeverity × 3 "
                      "PromotionReadinessOutcome × 2 "
                      "RegistrationOutcome enums. 1 input + 7 "
                      "output frozen dataclasses (PromotionGate "
                      "input; ModelRegistryEntry + "
                      "RegistrationResult + ActiveLookupResult + "
                      "MetricDelta + VersionComparison + "
                      "GateFinding + PromotionReadinessAssessment "
                      "outputs). Pure stdlib (re for SHA-256 "
                      "validation + Decimal). Per Rule 1, every "
                      "output surfaces validation findings + "
                      "comparison rationale + framework_refs "
                      "(Google MLOps reference architecture 2020 "
                      "+ ML Test Score Breck et al. 2017). Per "
                      "Rule 7, engine NEVER persists registry "
                      "entries (caller stores), never promotes a "
                      "model from PROPOSED → SHADOW → ACTIVE "
                      "(operator decides), never deploys a model "
                      "artifact, never triggers retraining "
                      "(future arc engine), never auto-rolls-"
                      "back, never runs models or makes "
                      "predictions (the v10.76 ML hook contract "
                      "is the engine-side; this is the lifecycle "
                      "layer above it), never computes its own "
                      "metrics (caller supplies from training "
                      "pipeline; engine validates presence + "
                      "sanity)."),
        regulatory_source="Google MLOps reference architecture (2020) — Continuous delivery and automation pipelines in machine learning; ML Test Score (Breck et al. 2017) — production-readiness assessment; Microsoft MLOps Maturity Model (2023)",
        citation="#281; ENH-281 §register_new_model_version/§lookup_active_version/§list_versions/§compare_versions/§validate_promotion_readiness",
        affected_engines=("mlops_model_registry",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.81"),
    Standard(standard_id="ENH-282", category="enhancement", subcategory="ml_governance",
        name="MLOps Adjudication Log",
        description=("Diagnostic operator-override capture "
                      "engine for the ml_governance arc. Sits "
                      "at the integration point between the "
                      "v10.76 ML hook contract (engine-side, "
                      "where models serve recommendations) and "
                      "ENH-281 mlops_model_registry (which "
                      "tracks model versions). When a model "
                      "recommends X via the v10.76 hook and an "
                      "operator picks Y instead, this engine "
                      "processes the captured override into "
                      "rolling override rates + class-level "
                      "override patterns + retraining candidate "
                      "datasets + chronological audit trails. "
                      "Five capabilities: (1) record_"
                      "adjudication — validate caller-supplied "
                      "event fields (model_id + version + "
                      "recommendation + operator decision + "
                      "agreement status + reason + timestamp + "
                      "optional input features hash for "
                      "retraining lineage); RecordingOutcome "
                      "RECORDED / REJECTED_INVALID. ISO 8601 "
                      "datetime format strict. OVERRIDDEN status "
                      "requires override_reason. retraining_"
                      "eligible=True requires input_features_"
                      "hash. Per Rule 7, engine never persists "
                      "— caller appends to their adjudication "
                      "storage. (2) compute_override_rate — "
                      "rolling override rate per model over "
                      "caller-supplied TimeWindow (HOURS or "
                      "DAYS). Surfaces total / accepted / "
                      "overridden / escalated / pending counts. "
                      "Override rate denominator excludes "
                      "PENDING (not yet decided) and ESCALATED "
                      "(decided by senior reviewer outside "
                      "operator scope). Per Rule 1, rate is "
                      "None when decided==0 (gap surfacing — "
                      "engine never fabricates rate from empty "
                      "denominator). (3) compute_class_level_"
                      "override_patterns — per-class override "
                      "patterns with caller-supplied "
                      "RecommendationClassTaxonomy "
                      "(class_id + description + is_protected_"
                      "class flag + minimum_sample_size). Flags "
                      "uneven detection when |class_rate - "
                      "overall_rate| ≥ uneven_threshold_pct "
                      "(caller-supplied; default 0.20 = 20pp). "
                      "Sample sufficiency required (caller-"
                      "supplied minimum). Per Rule 1, "
                      "insufficient_sample surfaced explicitly. "
                      "Per Rule 7, engine surfaces uneven rate "
                      "as BIAS SIGNAL; bias DECISION belongs to "
                      "model_governance arc at G124. Boundary "
                      "preserved. (4) build_retraining_"
                      "candidate_dataset — composes retraining "
                      "candidate dataset from operator-"
                      "overridden examples flagged retraining_"
                      "eligible. Filters: model_id + status="
                      "OVERRIDDEN + retraining_eligible=True + "
                      "input_features_hash present. Per Rule 1, "
                      "examples_excluded_no_features_hash and "
                      "examples_excluded_not_eligible surfaced "
                      "as separate explicit counts (caller "
                      "sees what dropped out and why). "
                      "insufficient_examples flag below caller-"
                      "supplied minimum_count_threshold. Per "
                      "Rule 7, engine selects + structures; "
                      "never trains. (5) build_adjudication_"
                      "audit_trail — chronological event list "
                      "+ summary statistics for regulatory "
                      "examination evidence preservation. "
                      "Sorted by decision_at_iso. Summary "
                      "includes count_total/accepted/overridden/"
                      "escalated/pending and overridden_by_"
                      "reason breakdown. Per Rule 1, full event "
                      "list + summary surface together "
                      "(regulator sees both rollup and "
                      "underlying events). Per Rule 7, engine "
                      "composes audit trail; never serializes "
                      "to regulator-specific schema (XBRL / "
                      "iTax / CBK formats are regulatory_"
                      "reporting territory). 4 AgreementStatus "
                      "× 7 OverrideReason × 2 RecordingOutcome "
                      "× 2 TimeWindowUnit enums. 2 input + 7 "
                      "output frozen dataclasses. Pure stdlib "
                      "(re for ISO validation + datetime + "
                      "Decimal). Per Rule 7, engine NEVER auto-"
                      "retrains (ENH-283 retraining scheduler "
                      "is also diagnostic — it surfaces when "
                      "retraining is due; operator triggers), "
                      "never auto-modifies model "
                      "recommendations (model layer is sealed; "
                      "engine is observational), never "
                      "silently records (every event is "
                      "explicit operator decision captured by "
                      "caller; engine processes captured), "
                      "never decides bias from override "
                      "patterns (signal surfacing only; bias "
                      "decision is model_governance arc "
                      "territory at G124), never persists "
                      "records (caller stores in JSON / PG / "
                      "wherever)."),
        regulatory_source="Microsoft MLOps Maturity Model (2023) — Stage 4 Human-in-the-Loop pattern; OCC 2011-12 §V.5 — model performance monitoring documentation; SR 11-7 §V — model documentation and examination evidence; EU AI Act Article 13 — transparency to deployers; Settles (2009) Active Learning Survey — human-in-the-loop labeling pattern; Bird et al. (2020) Fairlearn — disparity surfacing approach",
        citation="#282; ENH-282 §record_adjudication/§compute_override_rate/§compute_class_level_override_patterns/§build_retraining_candidate_dataset/§build_adjudication_audit_trail",
        affected_engines=("mlops_adjudication_log",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.82"),
    Standard(standard_id="ENH-283", category="enhancement", subcategory="ml_governance",
        name="MLOps Retraining Scheduler",
        description=("Diagnostic engine that consumes three "
                      "signal streams (freshness from ENH-281 "
                      "registry + override rate from ENH-282 "
                      "adjudication + distribution drift from "
                      "model_governance arc at G124) and "
                      "surfaces retraining-due recommendations "
                      "against caller-supplied policies. "
                      "Orthogonal to ENH-281 (the 'what's "
                      "deployed?' question), ENH-282 (the "
                      "'what did operators decide?' question), "
                      "and model_governance G124 (the 'is the "
                      "model SAFE?' question). This engine "
                      "answers the 'retraining due?' question. "
                      "Five capabilities: (1) evaluate_"
                      "freshness — given training_completed_at_"
                      "iso + as_of_iso + caller-supplied "
                      "FreshnessPolicy(warning_age_days, "
                      "stale_age_days), classify model age into "
                      "FRESH/WARNING/STALE/INSUFFICIENT_DATA. "
                      "Per Rule 1, INSUFFICIENT_DATA surfaces "
                      "explicitly when timestamp missing — "
                      "engine never fabricates an age. (2) "
                      "evaluate_override_signal — given current "
                      "override rate (caller integrates ENH-282 "
                      "OverrideRateMetric) + caller-supplied "
                      "OverrideThresholds(warning_rate, "
                      "critical_rate), return signal severity "
                      "OK/WARNING/CRITICAL/INSUFFICIENT_DATA. "
                      "Per Rule 1, INSUFFICIENT_DATA preserved "
                      "when rate is None (no decided records "
                      "in window) rather than defaulting to OK. "
                      "(3) evaluate_drift_signal — given drift "
                      "metric (caller integrates utils.model_"
                      "governance PSI/KS/Wasserstein output) + "
                      "DriftThresholds(warning_value, critical_"
                      "value, metric_name) — return signal "
                      "severity. Per Rule 7, engine never "
                      "decides drift method (PSI vs KS vs "
                      "Wasserstein); caller supplies chosen "
                      "metric + thresholds calibrated to that "
                      "method. (4) compute_retraining_"
                      "recommendation — orchestrator. Combines "
                      "three signals + caller-supplied "
                      "RetrainingPolicy(require_freshness, "
                      "require_override_signal, require_drift_"
                      "signal). Returns RetrainingOutcome "
                      "DUE (any CRITICAL/STALE) / SOON (any "
                      "WARNING) / NOT_YET (all OK) / "
                      "INSUFFICIENT_DATA (required signal "
                      "missing). Per Rule 1, every "
                      "contributing signal surfaces in "
                      "rationale + the assessment dataclasses "
                      "preserved on the recommendation. (5) "
                      "build_retraining_calendar — given a "
                      "fleet of recommendations, returns "
                      "RetrainingCalendar sorted by urgency "
                      "(DUE first, then SOON, NOT_YET, "
                      "INSUFFICIENT_DATA) with summary counts "
                      "for fleet-level capacity planning. Per "
                      "Rule 7, calendar is a view; engine "
                      "never schedules execution. 4 "
                      "FreshnessSeverity × 4 "
                      "OverrideSignalSeverity × 4 "
                      "DriftSignalSeverity × 4 "
                      "RetrainingOutcome enums. 4 input + 6 "
                      "output frozen dataclasses. Pure stdlib "
                      "(datetime + Decimal). Per Rule 1, every "
                      "output surfaces all contributing "
                      "signals + rationale + framework_refs. "
                      "Per Rule 7, engine NEVER auto-triggers "
                      "retraining (operator + ML team execute "
                      "the next training run, which produces a "
                      "candidate registered via ENH-281), "
                      "never auto-promotes a candidate (ENH-281 "
                      "territory), never auto-deprecates an "
                      "active (ENH-281 territory), never reads "
                      "ENH-281 / ENH-282 / model_governance "
                      "state directly (caller integrates "
                      "outputs), never persists scheduler "
                      "state, never decides drift method "
                      "(caller supplies). Caller-supplied data "
                      "discipline matches ENH-274 / ENH-278 / "
                      "ENH-271 / ENH-276 / ENH-281 / ENH-282 "
                      "pattern: model entry + signal values + "
                      "policies + thresholds all caller-"
                      "supplied; engine bundles a single "
                      "conservative default policy "
                      "(require_freshness=True only) which "
                      "caller REPLACES via constructor."),
        regulatory_source="Microsoft MLOps Maturity Model (2023) — Stage 4 Continuous Training: trigger combination temporal+performance+drift; Federal Reserve SR 11-7 §V — model performance monitoring with distribution drift as trigger; Population Stability Index (Siddiqi 2017); Kolmogorov-Smirnov (1933/1948); Wasserstein (Vaserstein 1969)",
        citation="#283; ENH-283 §evaluate_freshness/§evaluate_override_signal/§evaluate_drift_signal/§compute_retraining_recommendation/§build_retraining_calendar",
        affected_engines=("mlops_retraining_scheduler",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.83"),
    Standard(standard_id="ENH-284", category="enhancement", subcategory="ml_governance",
        name="MLOps A/B Comparison Harness",
        description=("Diagnostic engine that compares two model "
                      "versions running in parallel (typically "
                      "current ACTIVE + candidate SHADOW from "
                      "ENH-281). Bridge from 'we have a "
                      "candidate registered' to 'the candidate "
                      "is ready to be active'. Surfaces deltas "
                      "across five comparison axes: per-"
                      "prediction outcome agreement (when both "
                      "versions saw the same input — by "
                      "input_features_hash — did they predict "
                      "the same recommendation?), per-class "
                      "distribution shift (does SHADOW predict "
                      "the same class mix as ACTIVE?), latency "
                      "comparison (median + p95 + max per "
                      "version with deltas), cost comparison "
                      "(when caller supplies per-call cost "
                      "estimates per version), and composite "
                      "report orchestrator. Five capabilities: "
                      "(1) pair_predictions — pair ACTIVE + "
                      "SHADOW events by input_features_hash; "
                      "surfaces unpaired_active_only and "
                      "unpaired_shadow_only as separate explicit "
                      "lists per Rule 1 (operator diagnoses "
                      "deployment skew). (2) compute_agreement_"
                      "summary — aggregate per-pair agreement "
                      "into rate; rate is None when "
                      "total_paired==0 (engine never fabricates "
                      "from empty denominator). (3) compute_"
                      "class_distribution_shift — per-class "
                      "share comparison; classes appearing only "
                      "in one side surface with the other "
                      "side's count=0 per Rule 1 (engine never "
                      "silently drops; operator sees novel "
                      "classes shadow predicts that active "
                      "never did). (4) compute_latency_"
                      "comparison — median + p95 + max per "
                      "version with deltas (median_delta_ms, "
                      "median_delta_pct, p95_delta_ms); "
                      "insufficient_sample flag surfaces "
                      "explicitly when below caller-supplied "
                      "minimum (default 30); pure-stdlib "
                      "implementation of percentile via linear "
                      "interpolation on sorted values. (5) "
                      "build_ab_comparison_report — orchestrator. "
                      "Composes pairing + agreement + "
                      "distribution + latency + cost + "
                      "composite severity. Caller-supplied "
                      "ABThresholds (minimum_paired_sample, "
                      "agreement_warning_rate, "
                      "agreement_critical_rate, "
                      "latency_regression_warning_pct, "
                      "latency_regression_critical_pct). "
                      "Composite severity ABReportSeverity "
                      "INSUFFICIENT_SAMPLE / NOT_READY (any "
                      "critical breach) / NEEDS_REVIEW (any "
                      "warning breach) / READY_TO_PROMOTE. Per "
                      "Rule 1, every contributing comparison "
                      "preserved on the report. Per Rule 7, "
                      "composite severity is a SUMMARY view; "
                      "ENH-281 validate_promotion_readiness is "
                      "the actual promotion gate (operator runs "
                      "promotion gates with caller-supplied "
                      "PromotionGate rules; engine never auto-"
                      "promotes). 2 PredictionRole × 4 "
                      "ABReportSeverity enums. 3 input + 8 "
                      "output frozen dataclasses. Pure stdlib "
                      "(Decimal arithmetic; percentile "
                      "implemented directly without statistics "
                      "module dependency for control over edge "
                      "cases). Per Rule 7, engine NEVER auto-"
                      "promotes shadow to active (ENH-281 "
                      "territory), never auto-deprecates "
                      "active, never decides which side is "
                      "better (surfaces deltas; operator "
                      "decides on each axis), never executes "
                      "inference (consumes pre-computed "
                      "prediction streams from caller's "
                      "inference infrastructure), never filters "
                      "outliers or normalizes data (caller "
                      "decides pre-processing policy), never "
                      "persists prediction streams (caller "
                      "stores). Caller-supplied data discipline "
                      "matches arc pattern through ENH-281/282/"
                      "283: prediction events + latency "
                      "observations + cost estimates + minimum "
                      "sample sizes + thresholds all caller-"
                      "supplied; engine bundles no defaults "
                      "except dataclass field defaults on "
                      "ABThresholds for first-use convenience."),
        regulatory_source="Microsoft MLOps Maturity Model (2023) — Stage 5 shadow deployment + canary comparison; Google SRE Workbook (2018) — gradual rollout with paired comparison + p95 latency as production SLO indicator",
        citation="#284; ENH-284 §pair_predictions/§compute_agreement_summary/§compute_class_distribution_shift/§compute_latency_comparison/§build_ab_comparison_report",
        affected_engines=("mlops_ab_harness",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.84"),
    Standard(standard_id="ENH-285", category="enhancement", subcategory="ml_governance",
        name="MLOps Model Card Composer",
        description=("Diagnostic engine that composes per-model "
                      "documentation surfaces ('model cards' per "
                      "Mitchell et al. 2019) by combining outputs "
                      "from every other ml_governance arc engine "
                      "plus the existing model_governance arc at "
                      "G124 plus caller-supplied narrative fields. "
                      "Final engine of the arc; sits at the "
                      "consumer end where every signal flows into "
                      "the documentation surface a regulator "
                      "examines. Caller integrates upstream "
                      "outputs into ProductionPerformanceSnapshot "
                      "(override_rate_30d from ENH-282, drift_"
                      "metric_value from G124, last_retraining_"
                      "outcome from ENH-283, last_ab_severity "
                      "from ENH-284) and passes alongside ModelCard"
                      "Narrative covering qualitative sections "
                      "(intended_use, out_of_scope_use, training_"
                      "data_description, evaluation_data_"
                      "description, ethical_considerations, "
                      "caveats_and_recommendations per Mitchell et "
                      "al. 2019 §3). Five capabilities: (1) "
                      "compose_model_card — orchestrator. "
                      "Validates required fields + narrative "
                      "completeness + metric Decimal/non-NaN "
                      "sanity. CardComposeOutcome COMPOSED / "
                      "REJECTED_INVALID with all findings surfaced "
                      "per Rule 1. (2) validate_card_completeness "
                      "— given card + caller-supplied "
                      "CardCompletenessRequirements (require_"
                      "narrative + require_production_snapshot + "
                      "required_metric_names + require_training_"
                      "completion_timestamp), surface missing "
                      "sections explicitly. CompletenessOutcome "
                      "COMPLETE / INCOMPLETE. (3) compute_card_diff "
                      "— field-by-field diff between two cards "
                      "(typically active vs candidate during "
                      "promotion review). Per Rule 1, every field "
                      "diff surfaces (changed and unchanged). Per "
                      "Rule 7, engine surfaces diff but never "
                      "decides 'this change is too big to allow "
                      "promotion' (caller policy + ENH-281 "
                      "validate_promotion_readiness territory). "
                      "(4) build_revision_history — chronological "
                      "card history view from caller-supplied "
                      "archive. Sorted by composed_at_iso "
                      "ascending. Summary statistics + per-"
                      "revision entries surface together. Per "
                      "Rule 7, engine builds view; never "
                      "persists or modifies archive. (5) "
                      "serialize_card_to_markdown — render to "
                      "markdown for human consumption. Markdown "
                      "is generic (not regulator-specific). Per "
                      "Rule 7, engine never serializes to "
                      "regulator-specific schemas (XBRL / iTax / "
                      "CBK formats are regulatory_reporting "
                      "territory). Source of truth remains "
                      "structured ModelCard. 2 CompletenessOutcome "
                      "× 2 CardComposeOutcome enums. 3 input + 6 "
                      "output frozen dataclasses. Pure stdlib. "
                      "Per Rule 1, every output surfaces full "
                      "provenance + missing sections + framework_"
                      "refs (Mitchell et al. 2019 Model Cards for "
                      "Model Reporting + OCC 2011-12 §V model "
                      "documentation requirements). Per Rule 7, "
                      "engine NEVER persists cards (caller stores "
                      "in archive), never serializes to regulator-"
                      "specific schemas, never decides whether a "
                      "card is 'good enough' beyond caller-"
                      "supplied requirements, never publishes "
                      "externally, never reads other engines "
                      "directly (caller integrates upstream "
                      "outputs). Caller-supplied data discipline "
                      "matches arc pattern through ENH-281/282/"
                      "283/284: registry fields + narrative + "
                      "production snapshot + completeness "
                      "requirements all caller-supplied; engine "
                      "bundles no defaults except dataclass field "
                      "defaults for first-use convenience."),
        regulatory_source="Mitchell et al. (2019) Model Cards for Model Reporting (FAccT) — canonical structure: model details + intended use + training data + metrics + ethical considerations + caveats; OCC 2011-12 §V — model documentation requirements; SR 11-7 §V — examination evidence preservation; EU AI Act Article 13 — transparency to deployers",
        citation="#285; ENH-285 §compose_model_card/§validate_card_completeness/§compute_card_diff/§build_revision_history/§serialize_card_to_markdown",
        affected_engines=("mlops_model_card_composer",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="research_addition", implementation_batch="v10.85"),
)


# ────────────────────────────────────────────────────────────────────
# MLOPS_INTEGRATION_REGISTRY — v10.86 cross-platform wiring catalog
# ────────────────────────────────────────────────────────────────────
# G141 (ml_governance closure ratchet) verifies this catalog.
# Each entry documents an ML-using engine on the platform + which
# mlops_* engines (ENH-281/282/283) it integrates with.
#
# Per Rule 7, this is a CATALOG, not coupling. The mlops_* engines
# never read this registry. The catalog exists so operations can
# audit "every ML-using engine has registry + adjudication wiring
# in its caller path" — same enforcement pattern as G108/G109/G110
# from older closed work.
#
# Wiring lives in CALLER code paths (cockpit pages, training
# pipelines, operations workflows), never in the engines.

@dataclass(frozen=True)
class MLOpsIntegrationRecord:
    """One row in the cross-platform ML wiring catalog. Documents
    a single ML-using engine + which mlops_* engines integrate
    with it via caller code paths."""
    engine_module: str           # e.g. "trade_finance_reporting"
    standard_id: str             # primary ENH-### that defines the engine
    uses_v10_76_hook_contract: bool
    registry_wiring_planned: bool       # ENH-281
    adjudication_wiring_planned: bool   # ENH-282
    scheduler_wiring_planned: bool       # ENH-283
    notes: str


MLOPS_INTEGRATION_REGISTRY: Tuple[
    MLOpsIntegrationRecord, ...] = (
    MLOpsIntegrationRecord(
        engine_module="trade_finance_reporting",
        standard_id="ENH-280",
        uses_v10_76_hook_contract=True,
        registry_wiring_planned=True,
        adjudication_wiring_planned=True,
        scheduler_wiring_planned=True,
        notes=(
            "ENH-280 forecast hook (v10.76 ML hook contract). "
            "Volume forecasting accepts optional ML callable; "
            "deterministic + statistical fallback when None or "
            "fails; outputs carry ml_disabled flag + method "
            "enum. Operations checklist: register the volume "
            "forecaster artifact via ENH-281 register_new_"
            "model_version BEFORE deployment; capture operator "
            "forecast adjustments via ENH-282 record_"
            "adjudication; consult ENH-283 retraining "
            "scheduler quarterly. Wiring lives in cockpit "
            "page; engine itself remains decoupled.")),
    MLOpsIntegrationRecord(
        engine_module="trade_finance_document_checking",
        standard_id="ENH-270",
        uses_v10_76_hook_contract=True,
        registry_wiring_planned=True,
        adjudication_wiring_planned=True,
        scheduler_wiring_planned=False,
        notes=(
            "ENH-270 discrepancy classification hook (v10.76 "
            "contract). Document discrepancy detection accepts "
            "optional ML callable; rule-based fallback. "
            "Operations checklist: register doc_classifier "
            "artifacts via ENH-281; capture operator "
            "discrepancy override decisions via ENH-282 "
            "(retraining_eligible=True when operator override "
            "differs from model). Scheduled retraining not yet "
            "needed — discrepancy classification typically "
            "stable; can be added later.")),
    MLOpsIntegrationRecord(
        engine_module="cross_sell_bandit",
        standard_id="ENH-126",
        uses_v10_76_hook_contract=False,
        registry_wiring_planned=True,
        adjudication_wiring_planned=True,
        scheduler_wiring_planned=True,
        notes=(
            "ENH-126 Cat A first ML pilot (Thompson sampling "
            "bandit, closed at G126). Pre-dates v10.76 hook "
            "contract — bandit decision logic is internal, "
            "not pluggable. Would benefit from registry "
            "tracking + adjudication capture but currently "
            "lacks the v10.76 contract. Retrofit planned "
            "post-arc-closure: wrap bandit's recommendation "
            "decision in mlops_adjudication_log capture "
            "without changing the bandit engine itself.")),
    MLOpsIntegrationRecord(
        engine_module="model_governance",
        standard_id="ENH-259",
        uses_v10_76_hook_contract=False,
        registry_wiring_planned=False,
        adjudication_wiring_planned=False,
        scheduler_wiring_planned=False,
        notes=(
            "utils.model_governance is the closed model_"
            "governance arc at G124 (model risk + validation + "
            "drift detection PSI/KS/Wasserstein + bias "
            "monitoring + EU AI Act compliance). Distinct from "
            "the new ml_governance arc — model_governance "
            "answers 'is the model SAFE to deploy?' while "
            "ml_governance answers 'WHICH version is "
            "deployed?'. The two arcs are complementary: "
            "ml_governance arc engines consume model_"
            "governance outputs (drift metrics from G124) via "
            "caller integration into ProductionPerformance"
            "Snapshot. No retrofit needed; model_governance "
            "is itself the validation layer, not a model that "
            "needs validation tracking.")),
)


# ────────────────────────────────────────────────────────────────────
# (ENH-281 above is grouped here for adjacency to ENH-280, but
# subcategory="ml_governance" places it in the new ML governance arc
# — see MLOPS_GOVERNANCE arc spanning model registry / adjudication
# log / retraining scheduler / A/B harness / model card composer.
# Closed at G139+G140+G141 in v10.86. Distinct from utils.model_
# governance closed at G124.)


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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.281"),
    Standard(standard_id="ENH-292", category="enhancement", subcategory="it_digital",
        name="Cloud-Native & Container Architecture",
        description=("Kubernetes-native deployment, microservices, API-first, "
                      "12-factor app principles. Multi-cloud "
                      "(AWS/Azure/GCP) portability."),
        regulatory_source="Continuation.docx",
        citation="#292",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.281"),
    Standard(standard_id="ENH-293", category="enhancement", subcategory="it_digital",
        name="Observability & Monitoring",
        description=("Prometheus + Grafana + Loki + Jaeger stack. "
                      "OpenTelemetry tracing. SLI/SLO/error budgets. "
                      "Already shipped foundation in v9.18."),
        regulatory_source="Continuation.docx",
        citation="#293; v9.18 observability runbook",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.281"),
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
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.281"),
    Standard(standard_id="ENH-295", category="enhancement", subcategory="it_digital",
        name="API Gateway & Developer Portal",
        description=("Kong/Tyk API gateway, OAuth2/OpenID Connect, rate "
                      "limiting, API versioning, developer portal with "
                      "OpenAPI docs."),
        regulatory_source="Continuation.docx",
        citation="#295",
        affected_engines=("api",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.281"),
    Standard(standard_id="ENH-296", category="enhancement", subcategory="it_digital",
        name="Data Encryption & Security Hardening",
        description=("TLS 1.3, AES-256 at rest, HSM-backed key management, "
                      "field-level encryption for PII, secrets vault "
                      "(HashiCorp Vault / AWS KMS)."),
        regulatory_source="Continuation.docx + DPA Kenya 2019 + CBK Cyber",
        citation="#296; DPA §31; CBK Cybersecurity",
        affected_engines=(),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.282"),
    Standard(standard_id="ENH-297", category="enhancement", subcategory="it_digital",
        name="CI/CD & Release Automation",
        description=("GitHub Actions / GitLab CI / Jenkins pipelines. "
                      "Auto-test, auto-deploy to staging, blue-green "
                      "production deploys. Already foundation in v9.29."),
        regulatory_source="Continuation.docx",
        citation="#297; v9.29 qa-pipeline.yml",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.282"),
    Standard(standard_id="ENH-298", category="enhancement", subcategory="it_digital",
        name="Multi-Tenancy & White Labeling",
        description=("Tenant-scoped data isolation, configurable branding, "
                      "tenant-specific feature flags. Designed-but-deferred "
                      "per v10.0 plan."),
        regulatory_source="Continuation.docx",
        citation="#298",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.282"),
    Standard(standard_id="ENH-299", category="enhancement", subcategory="it_digital",
        name="Digital Banking Suite (Mobile + Web)",
        description=("React Native mobile apps, React/Next.js web. "
                      "Omnichannel session continuity, push notifications, "
                      "biometric auth."),
        regulatory_source="Continuation.docx",
        citation="#299",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.282"),
    Standard(standard_id="ENH-300", category="enhancement", subcategory="it_digital",
        name="CBK IT Compliance & Certification",
        description=("CBK Cybersecurity Guidance compliance, ISO 27001 "
                      "certification, PCI DSS for card systems, SOC 2 "
                      "Type II for SaaS components."),
        regulatory_source="Continuation.docx + CBK + ISO + PCI",
        citation="#300; CBK Cybersecurity; ISO 27001; PCI DSS",
        affected_engines=(),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.282"),
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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-302", category="enhancement", subcategory="bancassurance",
        name="AI-Powered Insurance Recommendation Engine",
        description=("ML-based insurance product recommendation per "
                      "customer life event + risk profile + financial "
                      "capacity. Cross-sell + up-sell triggers."),
        regulatory_source="Continuation.docx",
        citation="#302",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-303", category="enhancement", subcategory="bancassurance",
        name="Insurance Partner Integration Hub",
        description=("Multi-insurer API integration: Britam, Jubilee, "
                      "Madison, ICEA, Old Mutual etc. Standard data "
                      "schema, real-time quote engine."),
        regulatory_source="Continuation.docx",
        citation="#303",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-304", category="enhancement", subcategory="bancassurance",
        name="Agentic Claims Processing",
        description=("AI agent for claims intake, document validation, "
                      "fraud screening, settlement calculation, "
                      "auto-approval below threshold."),
        regulatory_source="Continuation.docx",
        citation="#304",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-305", category="enhancement", subcategory="bancassurance",
        name="Commission Reconciliation Engine",
        description=("Multi-insurer commission reconciliation: bank's "
                      "expected vs insurer's paid. Aging, dispute "
                      "workflow, partner scorecard."),
        regulatory_source="Continuation.docx",
        citation="#305",
        affected_engines=("reconciliation",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-306", category="enhancement", subcategory="bancassurance",
        name="Customer Insurance Portfolio (360° View)",
        description=("Per-customer all-policies view across insurers, "
                      "coverage gaps, expiry alerts, claim history, "
                      "policy recommendation."),
        regulatory_source="Continuation.docx",
        citation="#306",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-307", category="enhancement", subcategory="bancassurance",
        name="RM Insurance Desktop",
        description=("RM-facing insurance workspace: customer policies, "
                      "recommendation engine, quote tools, claim "
                      "tracking, performance KPIs."),
        regulatory_source="Continuation.docx",
        citation="#307",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-308", category="enhancement", subcategory="bancassurance",
        name="IRA Compliance & Reporting",
        description=("Insurance Regulatory Authority (Kenya) compliance: "
                      "agent licensing, premium remittance, claim ratio, "
                      "regulatory return generation."),
        regulatory_source="Continuation.docx + IRA Act",
        citation="#308; IRA Insurance Act",
        affected_engines=("regulatory_reporting",),
        status="active", breach_severity="CRITICAL", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-309", category="enhancement", subcategory="bancassurance",
        name="Bancassurance Partner Scorecard",
        description=("Per-insurer partner scorecard: policy count, premium "
                      "volume, commission, claim ratio, customer "
                      "satisfaction, dispute resolution time."),
        regulatory_source="Continuation.docx",
        citation="#309",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
    Standard(standard_id="ENH-310", category="enhancement", subcategory="bancassurance",
        name="Bancassurance Executive Dashboard",
        description=("Executive bancassurance view: revenue, growth, "
                      "channel mix, top products, top RMs, partner "
                      "performance, regulatory metrics."),
        regulatory_source="Continuation.docx",
        citation="#310",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.274"),
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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-312", category="enhancement", subcategory="command_centre",
        name="Executive Alerts & Intelligent Notifications",
        description=("Smart alert routing to executives: severity-based, "
                      "context-aware, actionable. Suppresses noise. "
                      "Already foundation in v9.16 smart_alerts."),
        regulatory_source="Continuation.docx",
        citation="#312; v9.16 smart_alerts",
        affected_engines=("smart_alerts",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-313", category="enhancement", subcategory="command_centre",
        name="Predictive Intelligence & Forecasting",
        description=("ML forecasting for revenue, NPL, deposits, churn. "
                      "Driver-based scenario modeling. Confidence "
                      "intervals + variance attribution."),
        regulatory_source="Continuation.docx",
        citation="#313",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-314", category="enhancement", subcategory="command_centre",
        name="What-If Scenario Simulator",
        description=("Interactive what-if simulator: shock parameters, "
                      "see P&L / capital / liquidity impact. Tornado "
                      "charts of sensitivities."),
        regulatory_source="Continuation.docx",
        citation="#314",
        affected_engines=("stress_testing",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-315", category="enhancement", subcategory="command_centre",
        name="AI Executive Assistant (Copilot)",
        description=("Natural-language query interface for executives: "
                      "'show NPL trend by segment last quarter'. RAG "
                      "over bank's data + context-aware."),
        regulatory_source="Continuation.docx",
        citation="#315",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-316", category="enhancement", subcategory="command_centre",
        name="Mobile Command Centre",
        description=("Mobile-first executive view: critical KPIs, alerts, "
                      "approvals, briefing pack. Offline support for "
                      "travel."),
        regulatory_source="Continuation.docx",
        citation="#316",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-317", category="enhancement", subcategory="command_centre",
        name="Crisis Management Module",
        description=("Crisis playbook activation, incident command "
                      "dashboard, stakeholder notification, decision "
                      "log, after-action review."),
        regulatory_source="Continuation.docx + v9.29 INCIDENT_RESPONSE.md",
        citation="#317; v9.29 Incident Response",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-318", category="enhancement", subcategory="command_centre",
        name="Strategy Execution Tracking (Enhanced)",
        description=("Strategic initiative tracking: milestones, owner, "
                      "RAG status, dependencies, KPI linkage to BSC. "
                      "Already foundation in initiative_*."),
        regulatory_source="Continuation.docx",
        citation="#318",
        affected_engines=(
            "initiative_dependency", "initiative_impact", "initiative_resource"),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-319", category="enhancement", subcategory="command_centre",
        name="Stakeholder Communication Hub",
        description=("Centralized stakeholder communication: regulators, "
                      "auditors, board members, customers. Templated "
                      "comms, audit trail, response tracking."),
        regulatory_source="Continuation.docx",
        citation="#319",
        affected_engines=("notifications",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
    Standard(standard_id="ENH-320", category="enhancement", subcategory="command_centre",
        name="Board & Committee Portal",
        description=("Secure board portal: meeting packs, papers, "
                      "voting, action items, minutes. Annotation + "
                      "private notes."),
        regulatory_source="Continuation.docx + CBK PG/03",
        citation="#320; CBK PG/03",
        affected_engines=("board_reporting",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.280"),
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
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-328", category="enhancement", subcategory="competitor_intel",
        name="Competitive Rate Intelligence",
        description=("Daily competitor rate tracking: deposit rates, "
                      "lending rates, FX rates, fees. Trend detection, "
                      "anomaly alerts."),
        regulatory_source="Continuation.docx",
        citation="#328",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-329", category="enhancement", subcategory="competitor_intel",
        name="Competitor Digital Strategy Intelligence",
        description=("Track competitor digital launches, app updates, "
                      "feature rollouts, social-media campaigns. "
                      "Time-series analysis of digital posture."),
        regulatory_source="Continuation.docx",
        citation="#329",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-330", category="enhancement", subcategory="competitor_intel",
        name="Executive Competitive Radar Dashboard",
        description=("Executive view: market share trends, NPS comparison, "
                      "feature gaps, threats + opportunities heatmap."),
        regulatory_source="Continuation.docx",
        citation="#330",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-331", category="enhancement", subcategory="competitor_intel",
        name="Competitive Alert Engine",
        description=("Real-time alerts on competitor moves: new product, "
                      "rate change, leadership change, M&A activity. "
                      "Routed to relevant executives."),
        regulatory_source="Continuation.docx",
        citation="#331",
        affected_engines=("smart_alerts",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-332", category="enhancement", subcategory="competitor_intel",
        name="Competitive Gap Analysis",
        description=("Feature-by-feature, product-by-product gap analysis. "
                      "RAG status. Time-to-parity estimates. Roadmap "
                      "input."),
        regulatory_source="Continuation.docx",
        citation="#332",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-333", category="enhancement", subcategory="competitor_intel",
        name="Competitor Digital Positioning Map",
        description=("Visual positioning: each competitor on dimensions "
                      "(rate / digital / branch / SME-friendliness). "
                      "Track migration over time."),
        regulatory_source="Continuation.docx",
        citation="#333",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-334", category="enhancement", subcategory="competitor_intel",
        name="Strategic Response Workflow",
        description=("Workflow for responding to competitor moves: detect → "
                      "assess → recommend → approve → execute → measure. "
                      "Owner + SLA."),
        regulatory_source="Continuation.docx",
        citation="#334",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-335", category="enhancement", subcategory="competitor_intel",
        name="Competitive Intelligence API",
        description=("API to expose competitive data to other modules: "
                      "pricing engine pulls competitor rates, propositions "
                      "engine pulls feature gaps."),
        regulatory_source="Continuation.docx",
        citation="#335",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
    Standard(standard_id="ENH-336", category="enhancement", subcategory="competitor_intel",
        name="Competitive Intelligence Dashboard (SBU View)",
        description=("Per-SBU competitive view: who's winning what segments, "
                      "win/loss reasons, pricing pressure, product gaps."),
        regulatory_source="Continuation.docx",
        citation="#336",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.278"),
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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.275"),
    Standard(standard_id="ENH-338", category="enhancement", subcategory="customer_360",
        name="Mobile App Interaction Tracking",
        description=("In-app event tracking: screens, taps, sessions, "
                      "abandonment, errors. Funnel + cohort analysis."),
        regulatory_source="Continuation.docx",
        citation="#338",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.275"),
    Standard(standard_id="ENH-339", category="enhancement", subcategory="customer_360",
        name="Branch Interaction Tracking",
        description=("Branch visit logs: queue time, service time, NPS, "
                      "purpose of visit, RM/teller assignment, outcome."),
        regulatory_source="Continuation.docx",
        citation="#339",
        affected_engines=("queue_analytics",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.275"),
    Standard(standard_id="ENH-340", category="enhancement", subcategory="customer_360",
        name="Customer Behavioral Profile",
        description=("Comprehensive behavioral profile: spending "
                      "patterns, channel preferences, life stage, risk "
                      "appetite, loyalty score."),
        regulatory_source="Continuation.docx",
        citation="#340",
        affected_engines=("customer_segmentation", "customer_value_segments"),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.276"),
    Standard(standard_id="ENH-341", category="enhancement", subcategory="customer_360",
        name="Pattern Detection & Anomaly Alerting",
        description=("ML pattern detection on customer behavior: unusual "
                      "transactions, declining engagement, fraud signals. "
                      "Real-time alerts."),
        regulatory_source="Continuation.docx",
        citation="#341",
        affected_engines=("smart_alerts",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.276"),
    Standard(standard_id="ENH-342", category="enhancement", subcategory="customer_360",
        name="Customer Journey Mapping",
        description=("Multi-channel journey reconstruction: from "
                      "awareness to acquisition to engagement to "
                      "retention. Friction identification."),
        regulatory_source="Continuation.docx",
        citation="#342",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.275"),
    Standard(standard_id="ENH-343", category="enhancement", subcategory="customer_360",
        name="Customer 360 Behavioral Widget",
        description=("RM/Branch-facing widget: customer's behavioral "
                      "highlights, propensities, concerns, last touch, "
                      "next-best action."),
        regulatory_source="Continuation.docx",
        citation="#343",
        affected_engines=(),
        affected_pages=("34_customer360",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.275"),
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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.276"),
    Standard(standard_id="ENH-345", category="enhancement", subcategory="customer_360",
        name="Customer Journey Optimization Engine",
        description=("ML-driven journey optimization: A/B test journey "
                      "variants, identify friction, recommend changes, "
                      "measure impact."),
        regulatory_source="Continuation.docx",
        citation="#345",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.276"),
    Standard(standard_id="ENH-346", category="enhancement", subcategory="customer_360",
        name="New Customer Onboarding Optimization",
        description=("Onboarding funnel analysis: drop-off, completion "
                      "rate, time-to-active, first-90-days revenue. "
                      "Optimize each step."),
        regulatory_source="Continuation.docx",
        citation="#346",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.275"),
    Standard(standard_id="ENH-347", category="enhancement", subcategory="customer_360",
        name="Segment-Level Behavioral Insights",
        description=("Behavioral insights aggregated by segment: women, "
                      "diaspora, asset-finance, agri, youth, SME. "
                      "Segment-specific propensities."),
        regulatory_source="Continuation.docx",
        citation="#347",
        affected_engines=("customer_segmentation",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.276"),
    Standard(standard_id="ENH-348", category="enhancement", subcategory="customer_360",
        name="RM Behavior Intelligence Widget",
        description=("RM-facing intelligence: customer behavioral signals, "
                      "engagement gap, recommended next action, "
                      "talking-points generator."),
        regulatory_source="Continuation.docx",
        citation="#348",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.276"),
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
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-350", category="enhancement", subcategory="propositions",
        name="Proposition Approval & Governance Workflow",
        description=("Multi-level approval: product head, risk, compliance, "
                      "finance, MD. Documentation, audit trail, "
                      "post-launch review."),
        regulatory_source="Continuation.docx + CBK PG (Product Governance)",
        citation="#350; CBK PG",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-351", category="enhancement", subcategory="propositions",
        name="Proposition Eligibility Engine",
        description=("Real-time eligibility check: customer + segment + "
                      "regulatory + risk gates. Returns reason codes "
                      "for ineligibility."),
        regulatory_source="Continuation.docx",
        citation="#351",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-352", category="enhancement", subcategory="propositions",
        name="Dynamic Pricing for Propositions",
        description=("ML-driven pricing per customer + market conditions. "
                      "A/B test pricing strategies. Fairness + compliance "
                      "guardrails."),
        regulatory_source="Continuation.docx",
        citation="#352",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-353", category="enhancement", subcategory="propositions",
        name="Proposition Orchestration (Next Best Proposition)",
        description=("Next-best-action engine for propositions. "
                      "Per-customer ranked list. Channel + timing "
                      "optimization."),
        regulatory_source="Continuation.docx",
        citation="#353",
        affected_engines=("cross_sell_nba",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-354", category="enhancement", subcategory="propositions",
        name="Proposition Performance Analytics",
        description=("Per-proposition KPIs: take-up rate, revenue, "
                      "profitability, customer satisfaction, attrition. "
                      "Cohort analysis."),
        regulatory_source="Continuation.docx",
        citation="#354",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-355", category="enhancement", subcategory="propositions",
        name="Proposition A/B Testing Framework",
        description=("Statistical A/B test framework: traffic split, "
                      "experiment design, significance testing, "
                      "auto-winner deployment."),
        regulatory_source="Continuation.docx",
        citation="#355",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-356", category="enhancement", subcategory="propositions",
        name="Dynamic Cohorts & Signals Engine",
        description=("Dynamic customer cohorts based on signals: life "
                      "stage, behavioral patterns, financial events. "
                      "Auto-update as signals change."),
        regulatory_source="Continuation.docx",
        citation="#356",
        affected_engines=("customer_segmentation",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-357", category="enhancement", subcategory="propositions",
        name="Proposition Presentation (Channel-Specific)",
        description=("Channel-optimized presentation: app card, web "
                      "banner, RM script, SMS template, email template. "
                      "Personalized per customer."),
        regulatory_source="Continuation.docx",
        citation="#357",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
    Standard(standard_id="ENH-358", category="enhancement", subcategory="propositions",
        name="Proposition API & Integration",
        description=("API to expose propositions to channels: app, web, "
                      "RM desktop, branch terminals. Standard schema, "
                      "real-time eligibility."),
        regulatory_source="Continuation.docx",
        citation="#358",
        affected_engines=("api",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.277"),
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
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-360", category="enhancement", subcategory="specialized_segments",
        name="Women Banking Segment",
        description=("Women-specific banking proposition: products, "
                      "savings + investment guidance, business growth "
                      "support. Aligned with UN SDG 5."),
        regulatory_source="Continuation.docx",
        citation="#360",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-361", category="enhancement", subcategory="specialized_segments",
        name="Diaspora Banking Segment",
        description=("Diaspora-specific products: remittances, mortgages, "
                      "investments back home. Multi-currency. SWIFT + "
                      "M-PESA + ACH integration."),
        regulatory_source="Continuation.docx",
        citation="#361",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-362", category="enhancement", subcategory="specialized_segments",
        name="Asset Finance Segment",
        description=("Asset finance products: vehicle, machinery, "
                      "equipment. Specialized credit scoring + "
                      "collateral management."),
        regulatory_source="Continuation.docx",
        citation="#362",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-363", category="enhancement", subcategory="specialized_segments",
        name="Agri-business Segment",
        description=("Agri-specific products: crop loans, weather-indexed "
                      "insurance, supply-chain finance. Integration with "
                      "agricultural data."),
        regulatory_source="Continuation.docx + AFC Act",
        citation="#363",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-364", category="enhancement", subcategory="specialized_segments",
        name="Youth Banking Segment",
        description=("Youth (18-35) products: zero-fee accounts, "
                      "student loans, micro-saving, mobile-first UX. "
                      "Financial-literacy content."),
        regulatory_source="Continuation.docx",
        citation="#364",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-365", category="enhancement", subcategory="specialized_segments",
        name="Segment P&L & Performance Attribution",
        description=("Per-segment P&L: revenue, cost, allocated capital, "
                      "RAROC. Time-series performance. Profitability "
                      "drivers."),
        regulatory_source="Continuation.docx",
        citation="#365",
        affected_engines=("operating_segments",),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-366", category="enhancement", subcategory="specialized_segments",
        name="Segment-Specific Dashboards",
        description=("Segment-tailored dashboards: top KPIs per segment, "
                      "competitor benchmark, growth tracker, "
                      "segment-manager actions."),
        regulatory_source="Continuation.docx",
        citation="#366",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-367", category="enhancement", subcategory="specialized_segments",
        name="Segment-Specific KPI Library",
        description=("Per-segment KPIs: women — financial inclusion + "
                      "biz growth; diaspora — remittance volume + "
                      "investment uptake; etc."),
        regulatory_source="Continuation.docx",
        citation="#367",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
    Standard(standard_id="ENH-368", category="enhancement", subcategory="specialized_segments",
        name="Segment Manager Role & Permissions",
        description=("Segment manager role with cross-functional view: "
                      "P&L, customers, products, RMs assigned, "
                      "initiatives. Limited write permissions."),
        regulatory_source="Continuation.docx",
        citation="#368",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.272"),
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
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-370", category="enhancement", subcategory="partnerships",
        name="MOU & Contract Management",
        description=("Centralized MOU/contract repository, versioning, "
                      "key dates (renewal, termination), obligations + "
                      "milestones tracking."),
        regulatory_source="Continuation.docx",
        citation="#370",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-371", category="enhancement", subcategory="partnerships",
        name="Partner Performance Scorecard",
        description=("Per-partner scorecard: revenue, leads delivered, "
                      "conversion rate, customer satisfaction, "
                      "compliance score."),
        regulatory_source="Continuation.docx",
        citation="#371",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-372", category="enhancement", subcategory="partnerships",
        name="Lead & Referral Tracking",
        description=("Partner-sourced lead tracking: attribution, "
                      "conversion funnel, time-to-close, revenue "
                      "share calculation."),
        regulatory_source="Continuation.docx",
        citation="#372",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-373", category="enhancement", subcategory="partnerships",
        name="Partner Commission Automation",
        description=("Auto-calculate partner commissions based on tracked "
                      "leads + agreed splits. Auto-generate payment "
                      "instructions. Reconciliation."),
        regulatory_source="Continuation.docx",
        citation="#373",
        affected_engines=("revenue_assurance",),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-374", category="enhancement", subcategory="partnerships",
        name="Partner Portal (Self-Service)",
        description=("Partner-facing portal: lead submission, status "
                      "tracking, commission statement, document "
                      "exchange, training resources."),
        regulatory_source="Continuation.docx",
        citation="#374",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-375", category="enhancement", subcategory="partnerships",
        name="Partner Ecosystem Analytics",
        description=("Cross-partner analytics: top performers, "
                      "underperformers, geographic coverage, segment "
                      "coverage, profitability."),
        regulatory_source="Continuation.docx",
        citation="#375",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-376", category="enhancement", subcategory="partnerships",
        name="Partner Onboarding Workflow",
        description=("End-to-end onboarding: due diligence, contract, "
                      "training, system access, sandbox testing, "
                      "go-live approval."),
        regulatory_source="Continuation.docx",
        citation="#376",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-377", category="enhancement", subcategory="partnerships",
        name="Partner Risk Management",
        description=("Per-partner risk monitoring: financial health, "
                      "regulatory standing, cyber posture, customer "
                      "complaints. Auto-alert on degradation."),
        regulatory_source="Continuation.docx + research_addition (vendor risk)",
        citation="#377; IIA 2026 third-party risk",
        affected_engines=("vendor_risk",),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
    Standard(standard_id="ENH-378", category="enhancement", subcategory="partnerships",
        name="Partnership KPIs & Reporting",
        description=("Aggregate partnership KPIs: ecosystem revenue, "
                      "share of new acquisitions, customer-LTV from "
                      "partners, NPS of partner-acquired customers."),
        regulatory_source="Continuation.docx",
        citation="#378",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.273"),
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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-380", category="enhancement", subcategory="sla_tracker",
        name="SLA Monitoring Engine",
        description=("Real-time SLA monitoring: per-transaction tracking, "
                      "running compliance %, near-breach alerts, "
                      "breach detection."),
        regulatory_source="Continuation.docx",
        citation="#380",
        affected_engines=("channel_sla",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-381", category="enhancement", subcategory="sla_tracker",
        name="SLA Breach Management & Remediation",
        description=("Auto-creation of breach incidents, owner assignment, "
                      "remediation workflow, customer compensation "
                      "calculation, RCA capture."),
        regulatory_source="Continuation.docx",
        citation="#381",
        affected_engines=("issue_management",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-382", category="enhancement", subcategory="sla_tracker",
        name="SLA Dashboard",
        description=("Real-time SLA dashboard: per-channel, per-product, "
                      "per-segment compliance %. Trend analysis. "
                      "Top breaching SLAs."),
        regulatory_source="Continuation.docx",
        citation="#382",
        affected_engines=("channel_sla",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-383", category="enhancement", subcategory="sla_tracker",
        name="Regulatory SLA Reporting",
        description=("Auto-generation of regulatory SLA reports: CBK "
                      "complaint resolution (30 days), CRB dispute "
                      "resolution, etc."),
        regulatory_source="Continuation.docx + CBK PG/09",
        citation="#383; CBK PG/09",
        affected_engines=("regulatory_reporting",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-384", category="enhancement", subcategory="sla_tracker",
        name="Vendor SLA Scorecard",
        description=("Per-vendor SLA tracking: response time, uptime, "
                      "quality, penalties. Auto-credit calculation. "
                      "Performance review input."),
        regulatory_source="Continuation.docx",
        citation="#384",
        affected_engines=("vendor_risk",),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
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
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-386", category="enhancement", subcategory="sla_tracker",
        name="SLA Integration with BSC",
        description=("SLA compliance feeds Operations & Compliance pillar "
                      "of BSC. Auto-scoring per role + branch + cluster. "
                      "BSC engine integration."),
        regulatory_source="Continuation.docx",
        citation="#386",
        affected_engines=("channel_sla", "bsc_engine"),
        status="active", breach_severity="HIGH", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-387", category="enhancement", subcategory="sla_tracker",
        name="SLA Calendar Management",
        description=("Working-hours / public-holiday-aware SLA "
                      "calculation. Multi-region calendar support. "
                      "Custom weekend/holiday rules."),
        regulatory_source="Continuation.docx",
        citation="#387",
        affected_engines=("channel_sla",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
    Standard(standard_id="ENH-388", category="enhancement", subcategory="sla_tracker",
        name="SLA Analytics & Continuous Improvement",
        description=("Long-term SLA analytics: trend, root cause patterns, "
                      "process improvement opportunities, target "
                      "recalibration."),
        regulatory_source="Continuation.docx",
        citation="#388",
        affected_engines=("channel_sla",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.271"),
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
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-390", category="enhancement", subcategory="campaigns",
        name="Multi-Channel Orchestration",
        description=("Coordinated multi-channel campaign execution: "
                      "email + SMS + push + social + branch + RM. "
                      "Channel preference per customer."),
        regulatory_source="Continuation.docx",
        citation="#390",
        affected_engines=("notifications",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-391", category="enhancement", subcategory="campaigns",
        name="Behavioral Trigger Engine",
        description=("Event-based campaign triggers: salary credit, "
                      "anniversary, product expiry, life event. "
                      "Real-time campaign activation."),
        regulatory_source="Continuation.docx",
        citation="#391",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-392", category="enhancement", subcategory="campaigns",
        name="Personalization Engine (AI-Powered)",
        description=("ML-based content personalization: subject lines, "
                      "messaging, offers, CTAs. Per-customer "
                      "optimization."),
        regulatory_source="Continuation.docx",
        citation="#392",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-393", category="enhancement", subcategory="campaigns",
        name="Campaign Performance Dashboard",
        description=("Real-time campaign KPIs: reach, open, click, "
                      "conversion, revenue, ROI. Per-segment, "
                      "per-channel breakdown."),
        regulatory_source="Continuation.docx",
        citation="#393",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-394", category="enhancement", subcategory="campaigns",
        name="Campaign A/B Testing",
        description=("Statistical A/B testing for campaigns: subject "
                      "line, content, timing, channel. Winning variant "
                      "auto-promotion."),
        regulatory_source="Continuation.docx",
        citation="#394",
        affected_engines=(),
        status="active", breach_severity="LOW", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-395", category="enhancement", subcategory="campaigns",
        name="Campaign Approval Workflow",
        description=("Multi-stage campaign approval: marketing → "
                      "compliance → product → MD. Compliance review "
                      "of customer comms."),
        regulatory_source="Continuation.docx + CBK PG/09",
        citation="#395; CBK PG/09 consumer protection",
        affected_engines=(),
        status="active", breach_severity="HIGH", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-396", category="enhancement", subcategory="campaigns",
        name="Automated Campaign Execution",
        description=("Automated execution of approved campaigns: "
                      "audience build, message rendering, channel "
                      "dispatch, response capture, retry logic."),
        regulatory_source="Continuation.docx",
        citation="#396",
        affected_engines=("notifications",),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-397", category="enhancement", subcategory="campaigns",
        name="Campaign ROI Attribution",
        description=("Multi-touch attribution of campaign impact: "
                      "incremental conversions, revenue lift, "
                      "customer-lifetime impact."),
        regulatory_source="Continuation.docx",
        citation="#397",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
    Standard(standard_id="ENH-398", category="enhancement", subcategory="campaigns",
        name="Campaign Customer Journey Integration",
        description=("Campaign integration with customer journey: "
                      "trigger from journey events, contribute to "
                      "journey state, prevent over-messaging."),
        regulatory_source="Continuation.docx",
        citation="#398",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="C",
        source="continuation_doc", implementation_batch="v10.279"),
)


# ════════════════════════════════════════════════════════════════════
# v10.133 Phase 0 — Registry Hygiene
#
# 65 standards from Eco Bank QA spec (Continuation.docx) were missing
# from the registry: Product (#131-140, 10), Strategy (#141-155, 15),
# Resource Optimization (#156-165, 10), CIMS (#166-180, 15),
# Compliance (#191-200, 10), Analytics Hub Extension (#286-290, 5).
# All declared status='planned' here. Per-cluster implementation
# drops follow in v10.135+ (Strategy first per CTO emphasis).
# ════════════════════════════════════════════════════════════════════

# ── Product Module (Continuation.docx #131-#140) ─────────────────
# v10.133 Phase 0 Registry Hygiene: declared per Eco Bank QA spec.
# All status='planned' until per-cluster implementation drops.
PRODUCT_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-131", category="enhancement", subcategory="product",
        name="Product Profitability Intelligence",
        description=("Full product P&L with direct + allocated costs, customer profitability by product."),
        regulatory_source="Continuation.docx",
        citation="#131",
        affected_engines=("product_pnl_intelligence",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.142"),
    Standard(
        standard_id="ENH-132", category="enhancement", subcategory="product",
        name="Product Lifecycle Management",
        description=("Stage-gate lifecycle with automated gates, approvals, and sunset criteria."),
        regulatory_source="Continuation.docx",
        citation="#132",
        affected_engines=("product_lifecycle",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.143"),
    Standard(
        standard_id="ENH-133", category="enhancement", subcategory="product",
        name="Customer Needs & Gap Analysis",
        description=("Customer needs registry, gap analysis, and value proposition builder."),
        regulatory_source="Continuation.docx",
        citation="#133",
        affected_engines=("customer_needs_analyzer",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.144"),
    Standard(
        standard_id="ENH-134", category="enhancement", subcategory="product",
        name="Competitive Intelligence for Products",
        description=("Automated competitive monitoring and benchmarking."),
        regulatory_source="Continuation.docx",
        citation="#134",
        affected_engines=("product_competitive_intel",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.145"),
    Standard(
        standard_id="ENH-135", category="enhancement", subcategory="product",
        name="Customer Value Proposition (CVP) Builder",
        description=("AI-powered value proposition generator tailored by customer segment."),
        regulatory_source="Continuation.docx",
        citation="#135",
        affected_engines=("product_cvp_builder",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.146"),
    Standard(
        standard_id="ENH-136", category="enhancement", subcategory="product",
        name="Product Ranking & Scoring Engine",
        description=("Multi-factor product scoring and ranking dashboard."),
        regulatory_source="Continuation.docx",
        citation="#136",
        affected_engines=("product_ranking",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.147"),
    Standard(
        standard_id="ENH-137", category="enhancement", subcategory="product",
        name="Dynamic Pricing Engine",
        description=("Real-time price optimization based on demand, competition, and customer."),
        regulatory_source="Continuation.docx",
        citation="#137",
        affected_engines=("dynamic_pricing",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.148"),
    Standard(
        standard_id="ENH-138", category="enhancement", subcategory="product",
        name="AI Product Recommendation Engine",
        description=("ML-powered next-best-product recommendations."),
        regulatory_source="Continuation.docx",
        citation="#138",
        affected_engines=("product_recommendation",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.149"),
    Standard(
        standard_id="ENH-139", category="enhancement", subcategory="product",
        name="Product Bundling Intelligence",
        description=("Market basket analysis for product bundling."),
        regulatory_source="Continuation.docx",
        citation="#139",
        affected_engines=("product_bundling",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.150"),
    Standard(
        standard_id="ENH-140", category="enhancement", subcategory="product",
        name="Product Analytics Dashboard",
        description=("Interactive dashboard with all product metrics."),
        regulatory_source="Continuation.docx",
        citation="#140",
        affected_engines=("product_analytics_dashboard",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.151"),
)


# ── Strategy Module (Continuation.docx #141-#155) ─────────────────
# v10.133 Phase 0 Registry Hygiene: declared per Eco Bank QA spec.
# All status='planned' until per-cluster implementation drops.
STRATEGY_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-141", category="enhancement", subcategory="strategy",
        name="Strategy Formulation Intelligence (SWOT + Market Research)",
        description=("AI-powered SWOT analysis with real-time market data."),
        regulatory_source="Continuation.docx",
        citation="#141",
        affected_engines=("strategy_formulation",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.135"),
    Standard(
        standard_id="ENH-142", category="enhancement", subcategory="strategy",
        name="Strategic Options Generator",
        description=("AI-powered strategic option generation with impact modeling."),
        regulatory_source="Continuation.docx",
        citation="#142",
        affected_engines=("strategic_options",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.135"),
    Standard(
        standard_id="ENH-143", category="enhancement", subcategory="strategy",
        name="Strategic Pillars & Workstream Contribution Mapping",
        description=("Decompose strategy into pillars, map departments to contributions."),
        regulatory_source="Continuation.docx",
        citation="#143",
        affected_engines=("strategy_decomposition",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.136"),
    Standard(
        standard_id="ENH-144", category="enhancement", subcategory="strategy",
        name="Strategic Initiative & Portfolio Management",
        description=("Strategic initiative portfolio with impact scoring."),
        regulatory_source="Continuation.docx",
        citation="#144",
        affected_engines=("initiative_portfolio",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.136"),
    Standard(
        standard_id="ENH-145", category="enhancement", subcategory="strategy",
        name="OKR/BSC Cascade Engine (Enhanced)",
        description=("Enhanced cascade with team OKRs, individual alignment visibility."),
        regulatory_source="Continuation.docx",
        citation="#145",
        affected_engines=("enhanced_cascade",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.137"),
    Standard(
        standard_id="ENH-146", category="enhancement", subcategory="strategy",
        name="Strategy Execution Gap Analyzer",
        description=("Real-time gap detection with root cause analysis."),
        regulatory_source="Continuation.docx",
        citation="#146",
        affected_engines=("gap_analyzer",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.138"),
    Standard(
        standard_id="ENH-147", category="enhancement", subcategory="strategy",
        name="Corrective Action Generator",
        description=("AI-generated corrective action plans."),
        regulatory_source="Continuation.docx",
        citation="#147",
        affected_engines=("corrective_actions",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.138"),
    Standard(
        standard_id="ENH-148", category="enhancement", subcategory="strategy",
        name="Strategy Learning Loop & Next Planning",
        description=("Institutional memory and AI-generated insights for next strategy."),
        regulatory_source="Continuation.docx",
        citation="#148",
        affected_engines=("strategy_learning",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.139"),
    Standard(
        standard_id="ENH-149", category="enhancement", subcategory="strategy",
        name="Stakeholder Engagement & Pulse Engine",
        description=("Engagement engine that involves everyone in strategy lifecycle."),
        regulatory_source="Continuation.docx",
        citation="#149",
        affected_engines=("stakeholder_engagement",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.139"),
    Standard(
        standard_id="ENH-150", category="enhancement", subcategory="strategy",
        name="Strategy Review & Health Dashboard",
        description=("Real-time strategy health dashboard with predictive alerts."),
        regulatory_source="Continuation.docx",
        citation="#150",
        affected_engines=("strategy_health",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.139"),
    Standard(
        standard_id="ENH-151", category="enhancement", subcategory="strategy",
        name="Strategy Simulation & What-If Analyzer",
        description=("Strategy simulator for testing alternative resource allocations."),
        regulatory_source="Continuation.docx",
        citation="#151",
        affected_engines=("strategy_simulator",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.140"),
    Standard(
        standard_id="ENH-152", category="enhancement", subcategory="strategy",
        name="Strategy Communication Engine",
        description=("Multi-channel strategy communication with feedback loops."),
        regulatory_source="Continuation.docx",
        citation="#152",
        affected_engines=("strategy_communication",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.140"),
    Standard(
        standard_id="ENH-153", category="enhancement", subcategory="strategy",
        name="Strategy to BSC Daily Integration",
        description=("Daily strategy metrics visible in individual BSC dashboards."),
        regulatory_source="Continuation.docx",
        citation="#153",
        affected_engines=("daily_strategy_integration",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.137"),
    Standard(
        standard_id="ENH-154", category="enhancement", subcategory="strategy",
        name="Strategy Transformation Office (STO) Toolkit",
        description=("Complete toolkit for Strategy Transformation Office."),
        regulatory_source="Continuation.docx",
        citation="#154",
        affected_engines=("sto_toolkit",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.140"),
    Standard(
        standard_id="ENH-155", category="enhancement", subcategory="strategy",
        name="Strategy ROI & Impact Analytics",
        description=("Full ROI attribution and impact analytics."),
        regulatory_source="Continuation.docx",
        citation="#155",
        affected_engines=("strategy_roi",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.140"),
)


# ── Resource Optimization Module (Continuation.docx #156-#165) ─────────────────
# v10.133 Phase 0 Registry Hygiene: declared per Eco Bank QA spec.
# All status='planned' until per-cluster implementation drops.
RESOURCE_OPTIMIZATION_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-156", category="enhancement", subcategory="resource_optimization",
        name="Employee Work Mode Declaration Engine",
        description=("Self-declaration tool with privacy protections."),
        regulatory_source="Continuation.docx",
        citation="#156",
        affected_engines=("work_mode_declaration",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.180"),
    Standard(
        standard_id="ENH-157", category="enhancement", subcategory="resource_optimization",
        name="Workload Forecasting & Prediction Engine",
        description=("ML-powered workload forecasting using XGBoost (proven 0.99 correlation) ."),
        regulatory_source="Continuation.docx",
        citation="#157",
        affected_engines=("workload_forecasting",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.181"),
    Standard(
        standard_id="ENH-158", category="enhancement", subcategory="resource_optimization",
        name="Target Service Level (TSL) Optimization",
        description=("Target Service Level (TSL) Optimization"),
        regulatory_source="Continuation.docx",
        citation="#158",
        affected_engines=("tsl_optimization",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.182"),
    Standard(
        standard_id="ENH-159", category="enhancement", subcategory="resource_optimization",
        name="Cross-Channel Resource Balancing",
        description=("Cross-Channel Resource Balancing"),
        regulatory_source="Continuation.docx",
        citation="#159",
        affected_engines=("cross_channel_balancing",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.183"),
    Standard(
        standard_id="ENH-160", category="enhancement", subcategory="resource_optimization",
        name="Real-Time Utilization Dashboard (Manager View)",
        description=("Real-Time Utilization Dashboard (Manager View)"),
        regulatory_source="Continuation.docx",
        citation="#160",
        affected_engines=("utilization_dashboard",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.184"),
    Standard(
        standard_id="ENH-161", category="enhancement", subcategory="resource_optimization",
        name="Employee Wellbeing & Burnout Prevention Integration",
        description=("Early warning system for burnout risk."),
        regulatory_source="Continuation.docx",
        citation="#161",
        affected_engines=("wellbeing_integration",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.185"),
    Standard(
        standard_id="ENH-162", category="enhancement", subcategory="resource_optimization",
        name="What-If Scenario Simulator for Hybrid Scheduling",
        description=("What-If Scenario Simulator for Hybrid Scheduling"),
        regulatory_source="Continuation.docx",
        citation="#162",
        affected_engines=("hybrid_scheduling_simulator",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.186"),
    Standard(
        standard_id="ENH-163", category="enhancement", subcategory="resource_optimization",
        name="Resource Investment Case Generator",
        description=("Resource Investment Case Generator"),
        regulatory_source="Continuation.docx",
        citation="#163",
        affected_engines=("resource_investment_case",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.187"),
    Standard(
        standard_id="ENH-164", category="enhancement", subcategory="resource_optimization",
        name="Integrity Culture Score & Benchmarking",
        description=("Culture score based on transparency, trust, and employee sentiment."),
        regulatory_source="Continuation.docx",
        citation="#164",
        affected_engines=("integrity_culture",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.188"),
    Standard(
        standard_id="ENH-165", category="enhancement", subcategory="resource_optimization",
        name="Executive Resource Optimization Dashboard",
        description=("Executive Resource Optimization Dashboard"),
        regulatory_source="Continuation.docx",
        citation="#165",
        affected_engines=("executive_resource_dashboard",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.189"),
)


# ── CIMS Module (Continuation.docx #166-#180) ─────────────────
# v10.133 Phase 0 Registry Hygiene: declared per Eco Bank QA spec.
# All status='planned' until per-cluster implementation drops.
CIMS_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-166", category="enhancement", subcategory="cims",
        name="Omnichannel Instruction Capture Engine",
        description=("Unified instruction capture with cross-channel continuity."),
        regulatory_source="Continuation.docx",
        citation="#166",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.290"),
    Standard(
        standard_id="ENH-167", category="enhancement", subcategory="cims",
        name="NLP Instruction Classification Engine",
        description=("AI-powered intent classification using fine-tuned banking NLP model."),
        regulatory_source="Continuation.docx",
        citation="#167",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.290"),
    Standard(
        standard_id="ENH-168", category="enhancement", subcategory="cims",
        name="Straight-Through Processing (STP) Engine",
        description=("Automated STP for standard, low-risk instructions."),
        regulatory_source="Continuation.docx",
        citation="#168",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.290"),
    Standard(
        standard_id="ENH-169", category="enhancement", subcategory="cims",
        name="Process Intelligence & Digital Twin",
        description=("Real-time process mining with digital twin representation of every instruction journey."),
        regulatory_source="Continuation.docx",
        citation="#169",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.291"),
    Standard(
        standard_id="ENH-170", category="enhancement", subcategory="cims",
        name="Predictive Dropout Prevention",
        description=("ML models predict dropouts before they happen, enabling proactive intervention."),
        regulatory_source="Continuation.docx",
        citation="#170",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.291"),
    Standard(
        standard_id="ENH-171", category="enhancement", subcategory="cims",
        name="Regulatory SLA Enforcement Engine",
        description=("Automated SLA tracking aligned with Reg E, Reg Z, and CBK requirements."),
        regulatory_source="Continuation.docx",
        citation="#171",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.292"),
    Standard(
        standard_id="ENH-172", category="enhancement", subcategory="cims",
        name="Secure Document & PAN Management",
        description=("Tokenized PAN storage with secure document vault."),
        regulatory_source="Continuation.docx",
        citation="#172",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.292"),
    Standard(
        standard_id="ENH-173", category="enhancement", subcategory="cims",
        name="Unified Customer Identity (Contact as Consumer)",
        description=("ServiceNow FSO-inspired unified identity model[^4]."),
        regulatory_source="Continuation.docx",
        citation="#173",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.290"),
    Standard(
        standard_id="ENH-174", category="enhancement", subcategory="cims",
        name="Next Best Action for Instructions",
        description=("Backbase-inspired next best action for instruction workflows[^8]."),
        regulatory_source="Continuation.docx",
        citation="#174",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.291"),
    Standard(
        standard_id="ENH-175", category="enhancement", subcategory="cims",
        name="Automated Exception Management",
        description=("Auto-escalation with conditional branching and SLA tracking."),
        regulatory_source="Continuation.docx",
        citation="#175",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.291"),
    Standard(
        standard_id="ENH-176", category="enhancement", subcategory="cims",
        name="Audit-Ready Instruction History",
        description=("Immutable, queryable instruction history with full traceability."),
        regulatory_source="Continuation.docx",
        citation="#176",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.292"),
    Standard(
        standard_id="ENH-177", category="enhancement", subcategory="cims",
        name="Customer Self-Service Instruction Portal",
        description=("Real-time instruction tracking portal integrated with CIMS."),
        regulatory_source="Continuation.docx",
        citation="#177",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.293"),
    Standard(
        standard_id="ENH-178", category="enhancement", subcategory="cims",
        name="Agent Workspace for Instruction Processing",
        description=("Unified agent workspace with instruction queue and AI assistance."),
        regulatory_source="Continuation.docx",
        citation="#178",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.292"),
    Standard(
        standard_id="ENH-179", category="enhancement", subcategory="cims",
        name="CIMS Performance Analytics Dashboard",
        description=("Executive dashboard with KPIs and trends."),
        regulatory_source="Continuation.docx",
        citation="#179",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.293"),
    Standard(
        standard_id="ENH-180", category="enhancement", subcategory="cims",
        name="Instruction Completion Feedback Loop",
        description=("Self-learning optimization based on completion data."),
        regulatory_source="Continuation.docx",
        citation="#180",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.293"),
)


# ── Compliance Module (Continuation.docx #191-#200) ─────────────────
# v10.133 Phase 0 Registry Hygiene: declared per Eco Bank QA spec.
# All status='planned' until per-cluster implementation drops.
COMPLIANCE_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-191", category="enhancement", subcategory="compliance",
        name="Digital KYC/KYB Onboarding Engine",
        description=("Automated KYC/KYB workflow with biometric verification and sanctions screening."),
        regulatory_source="Continuation.docx",
        citation="#191",
        affected_engines=("kyc_onboarding",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.160"),
    Standard(
        standard_id="ENH-192", category="enhancement", subcategory="compliance",
        name="PEP & Sanctions Screening Engine",
        description=("Real-time PEP and sanctions screening with AI-powered false positive reduction."),
        regulatory_source="Continuation.docx",
        citation="#192",
        affected_engines=("screening_orchestrator",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.162"),
    Standard(
        standard_id="ENH-193", category="enhancement", subcategory="compliance",
        name="AML Transaction Monitoring Engine",
        description=("Hybrid detection combining rule-based, scorecard, and ML models."),
        regulatory_source="Continuation.docx",
        citation="#193",
        affected_engines=("aml_monitoring", "transaction_monitoring"),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.161"),
    Standard(
        standard_id="ENH-194", category="enhancement", subcategory="compliance",
        name="SAR/STR Filing Engine",
        description=("Auto-generated SAR/STR with prefilled data and regulatory submission."),
        regulatory_source="Continuation.docx",
        citation="#194",
        affected_engines=("sar_filing",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.163"),
    Standard(
        standard_id="ENH-195", category="enhancement", subcategory="compliance",
        name="Regulatory Change Management",
        description=("Automated regulatory feed with impact analysis and task assignment."),
        regulatory_source="Continuation.docx",
        citation="#195",
        affected_engines=("regulatory_change",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.166"),
    Standard(
        standard_id="ENH-196", category="enhancement", subcategory="compliance",
        name="Policy Management & Attestation",
        description=("Centralized policy repository with version control and attestation tracking."),
        regulatory_source="Continuation.docx",
        citation="#196",
        affected_engines=("policy_management",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.167"),
    Standard(
        standard_id="ENH-197", category="enhancement", subcategory="compliance",
        name="Compliance Training Management",
        description=("Role-based training assignments with completion tracking and certification management."),
        regulatory_source="Continuation.docx",
        citation="#197",
        affected_engines=("compliance_training",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.168"),
    Standard(
        standard_id="ENH-198", category="enhancement", subcategory="compliance",
        name="Compliance Risk Assessment Engine",
        description=("Risk-based compliance assessment with configurable scoring."),
        regulatory_source="Continuation.docx",
        citation="#198",
        affected_engines=("compliance_risk_assessment",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.164"),
    Standard(
        standard_id="ENH-199", category="enhancement", subcategory="compliance",
        name="Examiner-Ready Reporting Portal",
        description=("Pre-configured reports aligned with FFIEC examination modules and CBK requirements."),
        regulatory_source="Continuation.docx",
        citation="#199",
        affected_engines=("examiner_reporting",),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.165"),
    Standard(
        standard_id="ENH-200", category="enhancement", subcategory="compliance",
        name="Compliance Dashboard & KPIs",
        description=("Executive compliance dashboard with key risk indicators."),
        regulatory_source="Continuation.docx",
        citation="#200",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.288"),
)


# ── Analytics Hub Extension (Continuation.docx #286-#290) ─────────────────
# v10.133 Phase 0 Registry Hygiene: declared per Eco Bank QA spec.
# All status='planned' until per-cluster implementation drops.
ANALYTICS_HUB_EXTENSION_ENHANCEMENT_STANDARDS: Tuple[Standard, ...] = (
    Standard(
        standard_id="ENH-286", category="enhancement", subcategory="analytics_hub",
        name="Credit Analyst Workbench",
        description=("Unified workbench with statement analyzer, bureau checks, affordability."),
        regulatory_source="Continuation.docx",
        citation="#286",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.286"),
    Standard(
        standard_id="ENH-287", category="enhancement", subcategory="analytics_hub",
        name="Scheduled Reports & Alerts",
        description=("Scheduled report delivery via email, Slack, Teams."),
        regulatory_source="Continuation.docx",
        citation="#287",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.286"),
    Standard(
        standard_id="ENH-288", category="enhancement", subcategory="analytics_hub",
        name="Natural Language Query (NLQ)",
        description=("Natural language to SQL translation."),
        regulatory_source="Continuation.docx",
        citation="#288",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.287"),
    Standard(
        standard_id="ENH-289", category="enhancement", subcategory="analytics_hub",
        name="Anomaly Detection & Alerting",
        description=("Automated anomaly detection with alerting."),
        regulatory_source="Continuation.docx",
        citation="#289",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.287"),
    Standard(
        standard_id="ENH-290", category="enhancement", subcategory="analytics_hub",
        name="Data Export & Integration Hub",
        description=("API-based data export with scheduled extracts."),
        regulatory_source="Continuation.docx",
        citation="#290",
        affected_engines=(),
        status="active", breach_severity="MEDIUM", priority_tier="B",
        source="continuation_doc", implementation_batch="v10.287"),
)


# ════════════════════════════════════════════════════════════════════
# Master registry — concatenates all tiers
# ════════════════════════════════════════════════════════════════════

# v10.1: CBK Tier 1 (12 regulatory)
# v10.2: Credit + RMS + Audit + Legal (63 enhancement standards)
# v10.3: Treasury + Revenue + Finance + Risk + Trade + Climate/ESG (~69)
# v10.4: IT + Banca + Command + Competitor + C360 + Props + Seg + Part + SLA + Camp (~102)
STANDARDS_REGISTRY: Tuple[Standard, ...] = (
    *CBK_PRUDENTIAL_STANDARDS,                          # v10.1
    *CREDIT_ENHANCEMENT_STANDARDS,                      # v10.2
    *RMS_ENHANCEMENT_STANDARDS,                         # v10.2
    *AUDIT_ENHANCEMENT_STANDARDS,                       # v10.2
    *LEGAL_ENHANCEMENT_STANDARDS,                       # v10.2
    *TREASURY_ENHANCEMENT_STANDARDS,                    # v10.3
    *REVENUE_ASSURANCE_ENHANCEMENT_STANDARDS,           # v10.3
    *FINANCE_ENHANCEMENT_STANDARDS,                     # v10.3
    *CREDIT_MODEL_RISK_ENHANCEMENT_STANDARDS,           # v10.3
    *TRADE_FINANCE_ENHANCEMENT_STANDARDS,               # v10.3
    *CLIMATE_ESG_STANDARDS,                             # v10.3
    *IT_DIGITAL_ENHANCEMENT_STANDARDS,                  # v10.4
    *BANCASSURANCE_ENHANCEMENT_STANDARDS,               # v10.4
    *COMMAND_CENTRE_ENHANCEMENT_STANDARDS,              # v10.4
    *COMPETITOR_INTEL_ENHANCEMENT_STANDARDS,            # v10.4
    *CUSTOMER_360_ENHANCEMENT_STANDARDS,                # v10.4
    *PROPOSITIONS_ENHANCEMENT_STANDARDS,                # v10.4
    *SPECIALIZED_SEGMENTS_ENHANCEMENT_STANDARDS,        # v10.4
    *PARTNERSHIPS_ENHANCEMENT_STANDARDS,                # v10.4
    *SLA_TRACKER_ENHANCEMENT_STANDARDS,                 # v10.4
    *CAMPAIGNS_ENHANCEMENT_STANDARDS,                   # v10.4
    # ── v10.133 Phase 0: 65 missing standards declared as planned ──
    *PRODUCT_ENHANCEMENT_STANDARDS,                     # v10.133 #131-140
    *STRATEGY_ENHANCEMENT_STANDARDS,                    # v10.133 #141-155
    *RESOURCE_OPTIMIZATION_ENHANCEMENT_STANDARDS,       # v10.133 #156-165
    *CIMS_ENHANCEMENT_STANDARDS,                        # v10.133 #166-180
    *COMPLIANCE_ENHANCEMENT_STANDARDS,                  # v10.133 #191-200
    *ANALYTICS_HUB_EXTENSION_ENHANCEMENT_STANDARDS,     # v10.133 #286-290
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
