"""utils/examiner_reporting.py — ENH-199 Examiner-Ready Reporting Portal.

================================================================================
A2Z MIS 360 — ENH-199 Examiner-Ready Reporting Portal
================================================================================

PACKAGER engine that bundles the AML cluster's outputs into examination
packages aligned with FFIEC examination modules + CBK examination
requirements. Closes the loop with the regulator's view.

CRITICAL DESIGN DECISION — packaging over duplication
-----------------------------------------------------
This engine does NOT generate new reports. It STRUCTURES + ASSEMBLES
artifacts already produced by upstream engines:

    ENH-191 KYC/KYB OnboardingDecision   → CDD documentation module
    ENH-192 ScreeningOrchestrator        → screening evidence module
    ENH-193 AmlMonitoringResult          → transaction monitoring module
    ENH-194 SAR/STR FilingPayload        → filings module
    ENH-198 ComplianceRiskAssessment     → enterprise risk module
    
    +
    
    Existing utils/cbk_regulatory_reporting (Standard ENH-252) for CBK
    Returns context. Engine doesn't call into it directly here — that
    engine is for prudential reporting (capital, liquidity, exposures).
    The AML examination package is a separate examination module
    structured per FFIEC.

Produces a structured ExaminationPackage that the institution exports
for upload to the examiner's evidence portal or for printing.

Same compose-don't-duplicate pattern as v10.160 ENH-191, v10.162
ENH-193, v10.163 ENH-194, v10.164 ENH-198.

REGULATORY ALIGNMENT
--------------------
- FFIEC BSA/AML Examination Manual — examination module structure
  (Customer Due Diligence, Suspicious Activity Reporting, Risk
  Assessment, Independent Testing, Training)
- CBK Risk-Based Supervision Framework — examination evidence
  requirements
- POCAMLA §53 — institution must maintain records and make them
  available for examiner review
- FATF Methodology for Assessing Compliance with the FATF
  Recommendations — Immediate Outcome 4 (preventive measures)

EXAMINATION MODULES SHIPPED
--------------------------
1. CUSTOMER_DUE_DILIGENCE (CDD) — KYC/KYB onboarding decisions,
   tier distribution, EDD-trigger reasons
2. SCREENING (PEP/Sanctions) — screening evidence, hit dispositions
3. TRANSACTION_MONITORING — alert volumes, escalation outcomes,
   tier-aware severity adjustments
4. SAR_STR_FILING — filing inventory, lifecycle status, POCAMLA
   §44 deadline compliance
5. ENTERPRISE_RISK — enterprise compliance risk score, dimension
   breakdown, contradictions
6. EVIDENCE_INDEX — cross-references mapping each transaction or
   customer to all relevant artifacts (the "audit trail" module)

FFIEC modules NOT shipped (deferred):
- INDEPENDENT_TESTING (audit cycle evidence) — needs ENH-195+ outputs;
  flagged in package.deferred_modules
- TRAINING (compliance training records) — needs ENH-197 outputs;
  flagged in package.deferred_modules

HONEST DEFERRALS
----------------
- TRAINING_MODULE: needs ENH-197 (Compliance Training) which is still
  planned. Status DEFERRED in package.
- INDEPENDENT_TESTING_MODULE: typically populated by Internal Audit
  workpapers (ENH-201..210 cluster). The AML examiner-ready package
  surfaces a hook for these but doesn't generate them.
- EXPORT TO PORTAL FORMAT: package generates structured JSON
  (to_dict). Printing to FFIEC PDF or CBK examiner-portal-specific
  XML is operator-side work — same submission_method honesty as
  v10.163 SAR filing.

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ExaminationModuleType(str, Enum):
    """FFIEC BSA/AML examination module categories."""
    CDD = "CUSTOMER_DUE_DILIGENCE"
    SCREENING = "SCREENING"
    TRANSACTION_MONITORING = "TRANSACTION_MONITORING"
    SAR_STR_FILING = "SAR_STR_FILING"
    ENTERPRISE_RISK = "ENTERPRISE_RISK"
    EVIDENCE_INDEX = "EVIDENCE_INDEX"
    INDEPENDENT_TESTING = "INDEPENDENT_TESTING"   # deferred
    TRAINING = "TRAINING"                          # deferred


class ModuleStatus(str, Enum):
    POPULATED = "POPULATED"
    EMPTY_NO_DATA = "EMPTY_NO_DATA"
    DEFERRED = "DEFERRED"
    PARTIAL = "PARTIAL"


class PackageStatus(str, Enum):
    DRAFT = "DRAFT"
    EXAMINER_READY = "EXAMINER_READY"
    EXPORTED = "EXPORTED"


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExaminationModule:
    """One examination module within a package."""
    module_type: ExaminationModuleType
    status: ModuleStatus
    summary_metrics: Mapping[str, Any]   # operator-readable metrics
    artifacts: Tuple[Mapping[str, Any], ...]  # serialised upstream artifacts
    findings: Tuple[str, ...]             # auto-generated examiner notes
    source_engines: Tuple[str, ...]
    deferred_reason: str = ""             # populated when status=DEFERRED


@dataclass(frozen=True)
class ExaminationPackage:
    """Full examination package ready for examiner consumption."""
    package_id: str
    institution_name: str
    examination_period_start: str   # YYYY-MM-DD
    examination_period_end: str
    generated_at_utc: str
    status: PackageStatus
    modules: Tuple[ExaminationModule, ...]
    cluster_health_summary: Mapping[str, Any]   # quick overview
    deferred_modules: Tuple[str, ...]
    upstream_engines: Tuple[str, ...]
    export_format_status: str       # honest deferral surface
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_id": self.package_id,
            "institution_name": self.institution_name,
            "examination_period_start": (
                self.examination_period_start),
            "examination_period_end": self.examination_period_end,
            "generated_at_utc": self.generated_at_utc,
            "status": self.status.value,
            "modules": [
                {
                    "module_type": m.module_type.value,
                    "status": m.status.value,
                    "summary_metrics": dict(m.summary_metrics),
                    "artifacts": [dict(a) for a in m.artifacts],
                    "findings": list(m.findings),
                    "source_engines": list(m.source_engines),
                    "deferred_reason": m.deferred_reason,
                }
                for m in self.modules
            ],
            "cluster_health_summary": dict(self.cluster_health_summary),
            "deferred_modules": list(self.deferred_modules),
            "upstream_engines": list(self.upstream_engines),
            "export_format_status": self.export_format_status,
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ExaminerReportingEngine:
    """ENH-199 Examiner-Ready Reporting Portal engine.

    Stateless packager. Operator passes upstream engine instances in
    via build_package(); engine assembles the examination package and
    returns it. Engine retains generated packages for retrieval.

    Use:
        engine = ExaminerReportingEngine()
        package = engine.build_package(
            institution_name="Ecobank Kenya",
            period_start="2026-01-01",
            period_end="2026-03-31",
            kyc_engine=kyc_engine,
            screening_engine=screening_engine,   # optional ENH-192
            aml_engine=aml_engine,
            sar_engine=sar_engine,
            cra_engine=cra_engine,
        )
    """

    EXPORT_FORMAT_NOTE = (
        "STRUCTURED_JSON — package generates structured JSON via "
        "to_dict() suitable for transformation. FFIEC PDF format and "
        "CBK examiner-portal-specific XML formats are operator-side "
        "transformations. v10.165 ships build+structure+export; "
        "format-specific renderers are future increments. Same "
        "submission_method discipline as v10.163 SAR filing.")

    UPSTREAM_ENGINES_LITERAL = (
        "ENH-191 KycOnboardingEngine",
        "ENH-192 ScreeningOrchestrator",
        "ENH-193 AmlMonitoringEngine",
        "ENH-194 SarFilingEngine",
        "ENH-198 ComplianceRiskAssessmentEngine",
    )

    def __init__(self) -> None:
        self._packages: Dict[str, ExaminationPackage] = {}
        self._next_id = 1

    # ------------------------------------------------------------------
    # Public build_package — main entry point
    # ------------------------------------------------------------------

    def build_package(
        self,
        institution_name: str,
        period_start: str,
        period_end: str,
        kyc_engine: Optional[Any] = None,
        screening_engine: Optional[Any] = None,
        aml_engine: Optional[Any] = None,
        sar_engine: Optional[Any] = None,
        cra_engine: Optional[Any] = None,
    ) -> ExaminationPackage:
        """Assemble a full examination package.

        Each engine is optional. Modules whose source engine is missing
        get status=EMPTY_NO_DATA with a finding noting the gap (Rule 6
        honesty: missing engine doesn't fabricate examination evidence).
        """
        if not institution_name.strip():
            raise ValueError("institution_name is required")
        if not period_start or not period_end:
            raise ValueError("period_start and period_end are required")

        modules: List[ExaminationModule] = []

        # 1. CDD module
        modules.append(self._build_cdd_module(kyc_engine))

        # 2. Screening module
        modules.append(self._build_screening_module(screening_engine))

        # 3. Transaction Monitoring module
        modules.append(self._build_aml_module(aml_engine))

        # 4. SAR/STR Filing module
        modules.append(self._build_sar_module(sar_engine))

        # 5. Enterprise Risk module
        modules.append(self._build_enterprise_risk_module(cra_engine))

        # 6. Evidence Index module
        modules.append(
            self._build_evidence_index_module(
                kyc_engine, aml_engine, sar_engine))

        # Deferred modules (FFIEC requires them but engines aren't
        # active yet)
        modules.append(self._build_deferred_module(
            ExaminationModuleType.INDEPENDENT_TESTING,
            "INDEPENDENT_TESTING typically populated by Internal "
            "Audit workpapers (ENH-201..210 cluster). The AML "
            "examiner-ready package surfaces this hook but doesn't "
            "generate audit workpapers — those come from the Audit "
            "module's existing engines."))

        modules.append(self._build_deferred_module(
            ExaminationModuleType.TRAINING,
            "TRAINING module needs ENH-197 (Compliance Training "
            "Management) which is still planned. v10.197+ will "
            "activate this module."))

        # Cluster health summary — quick overview
        health = self._build_cluster_health_summary(modules)

        deferred_module_names = tuple(
            m.module_type.value for m in modules
            if m.status == ModuleStatus.DEFERRED)

        package_id = f"EXAM-{self._next_id:06d}"
        self._next_id += 1

        # Determine package status
        all_populated = all(
            m.status in (ModuleStatus.POPULATED, ModuleStatus.PARTIAL)
            for m in modules
            if m.status != ModuleStatus.DEFERRED)
        status = (PackageStatus.EXAMINER_READY if all_populated
                  else PackageStatus.DRAFT)

        package = ExaminationPackage(
            package_id=package_id,
            institution_name=institution_name,
            examination_period_start=period_start,
            examination_period_end=period_end,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            status=status,
            modules=tuple(modules),
            cluster_health_summary=health,
            deferred_modules=deferred_module_names,
            upstream_engines=self.UPSTREAM_ENGINES_LITERAL,
            export_format_status=self.EXPORT_FORMAT_NOTE,
            meta={
                "engine_version": "ENH-199-v10.165",
                "ffiec_alignment": (
                    "FFIEC BSA/AML Examination Manual"),
                "cbk_alignment": (
                    "CBK Risk-Based Supervision Framework"),
                "pocamla_alignment": "POCAMLA §53 records retention",
            },
        )
        self._packages[package_id] = package
        return package

    # ------------------------------------------------------------------
    # Module builders
    # ------------------------------------------------------------------

    def _build_cdd_module(self, kyc_engine: Optional[Any]
                            ) -> ExaminationModule:
        if kyc_engine is None:
            return ExaminationModule(
                module_type=ExaminationModuleType.CDD,
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    "CDD module empty — kyc_engine not supplied. "
                    "Examiner cannot assess Customer Due Diligence "
                    "without onboarding decisions.",
                ),
                source_engines=("ENH-191 KycOnboardingEngine",))

        try:
            decisions = kyc_engine.all_decisions()
            summary = kyc_engine.board_summary()
        except Exception as e:
            return ExaminationModule(
                module_type=ExaminationModuleType.CDD,
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    f"CDD module error reading kyc_engine: "
                    f"{type(e).__name__}: {e}",
                ),
                source_engines=("ENH-191 KycOnboardingEngine",))

        artifacts = tuple(d.to_dict() for d in decisions)

        findings: List[str] = []
        n_total = len(decisions)
        n_edd = sum(1 for d in decisions
                    if d.tier and d.tier.value == "EDD")
        n_prohibited = sum(1 for d in decisions
                            if d.tier and d.tier.value == "PROHIBITED")
        n_pending_bio = sum(1 for d in decisions
                             if d.outcome.value == "PENDING_BIOMETRICS")

        if n_total == 0:
            findings.append("No CDD decisions in package period.")
        else:
            findings.append(
                f"{n_total} CDD decisions made; {n_edd} EDD-tier; "
                f"{n_prohibited} PROHIBITED.")
            if n_pending_bio > 0:
                findings.append(
                    f"{n_pending_bio} customers in PENDING_BIOMETRICS "
                    f"— recoverable but examiner may flag if aged.")
            if n_prohibited > 0:
                findings.append(
                    f"{n_prohibited} PROHIBITED tier customers should "
                    f"not have active accounts — verify account "
                    f"closure or freeze status.")

        return ExaminationModule(
            module_type=ExaminationModuleType.CDD,
            status=(ModuleStatus.POPULATED if n_total > 0
                    else ModuleStatus.EMPTY_NO_DATA),
            summary_metrics={
                "n_decisions": n_total,
                "n_kyc": summary.get("n_kyc", 0),
                "n_kyb": summary.get("n_kyb", 0),
                "tier_counts": dict(summary.get("tier_counts", {})),
                "outcome_counts": dict(
                    summary.get("outcome_counts", {})),
                "n_pep_flagged": summary.get("n_pep_flagged", 0),
                "n_sanctions_flagged": summary.get(
                    "n_sanctions_flagged", 0),
            },
            artifacts=artifacts,
            findings=tuple(findings),
            source_engines=("ENH-191 KycOnboardingEngine",))

    def _build_screening_module(
            self, screening_engine: Optional[Any]
    ) -> ExaminationModule:
        if screening_engine is None:
            return ExaminationModule(
                module_type=ExaminationModuleType.SCREENING,
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    "Screening module empty — screening_engine not "
                    "supplied. PEP/Sanctions screening evidence "
                    "absent from package.",
                ),
                source_engines=("ENH-192 ScreeningOrchestrator",))

        try:
            screenings = screening_engine.all_screenings()
            summary = screening_engine.board_summary()
        except Exception:
            screenings = ()
            summary = {}

        artifacts = tuple(
            s.to_dict() for s in screenings
            if hasattr(s, "to_dict"))

        findings: List[str] = []
        n_total = len(screenings)
        if n_total == 0:
            findings.append("No screenings in package period.")
        else:
            findings.append(f"{n_total} screenings performed.")

        return ExaminationModule(
            module_type=ExaminationModuleType.SCREENING,
            status=(ModuleStatus.POPULATED if n_total > 0
                    else ModuleStatus.EMPTY_NO_DATA),
            summary_metrics=dict(summary) if summary else {},
            artifacts=artifacts,
            findings=tuple(findings),
            source_engines=("ENH-192 ScreeningOrchestrator",))

    def _build_aml_module(self, aml_engine: Optional[Any]
                            ) -> ExaminationModule:
        if aml_engine is None:
            return ExaminationModule(
                module_type=(
                    ExaminationModuleType.TRANSACTION_MONITORING),
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    "Transaction Monitoring module empty — "
                    "aml_engine not supplied.",
                ),
                source_engines=("ENH-193 AmlMonitoringEngine",))

        try:
            results = aml_engine.all_results()
            summary = aml_engine.board_summary()
        except Exception:
            results = ()
            summary = {}

        artifacts = tuple(r.to_dict() for r in results)

        findings: List[str] = []
        n_total = len(results)
        n_critical = summary.get("n_total_critical_alerts", 0)
        n_sar = sum(1 for r in results
                    if r.outcome.value == "ESCALATE_TO_SAR")
        n_block = sum(1 for r in results
                      if r.outcome.value == "ESCALATE_TO_BLOCK")

        if n_total == 0:
            findings.append("No monitoring runs in package period.")
        else:
            findings.append(
                f"{n_total} customers monitored; {n_critical} critical "
                f"alerts; {n_sar} escalated to SAR; {n_block} to BLOCK.")
            if "DEFERRED" in summary.get("ml_layer_status", ""):
                findings.append(
                    "ML layer for alert prioritization explicitly "
                    "DEFERRED per v10.162 design — current detection "
                    "rule-based + tier-aware scorecard.")

        return ExaminationModule(
            module_type=(
                ExaminationModuleType.TRANSACTION_MONITORING),
            status=(ModuleStatus.POPULATED if n_total > 0
                    else ModuleStatus.EMPTY_NO_DATA),
            summary_metrics={
                "n_customers_monitored": n_total,
                "n_critical_alerts": n_critical,
                "n_sar_escalations": n_sar,
                "n_block_escalations": n_block,
                "outcome_counts": dict(
                    summary.get("outcome_counts", {})),
                "ml_layer_status": summary.get(
                    "ml_layer_status", ""),
            },
            artifacts=artifacts,
            findings=tuple(findings),
            source_engines=("ENH-193 AmlMonitoringEngine",))

    def _build_sar_module(self, sar_engine: Optional[Any]
                            ) -> ExaminationModule:
        if sar_engine is None:
            return ExaminationModule(
                module_type=ExaminationModuleType.SAR_STR_FILING,
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    "SAR/STR Filing module empty — sar_engine not "
                    "supplied. POCAMLA §44 compliance evidence absent.",
                ),
                source_engines=("ENH-194 SarFilingEngine",))

        try:
            filings = sar_engine.all_filings()
            overdue = sar_engine.overdue_filings()
            summary = sar_engine.board_summary()
        except Exception:
            filings = ()
            overdue = ()
            summary = {}

        artifacts = tuple(f.to_dict() for f in filings)

        findings: List[str] = []
        n_total = len(filings)
        n_overdue = len(overdue)
        n_submitted = summary.get("n_submitted", 0)

        if n_total == 0:
            findings.append("No SAR/STR filings in package period.")
        else:
            findings.append(f"{n_total} filings; {n_submitted} submitted.")
            if n_overdue > 0:
                findings.append(
                    f"⚠ {n_overdue} DRAFT filings past POCAMLA §44 "
                    f"7-day deadline — DIRECT REGULATORY EXPOSURE. "
                    f"Examiner will flag.")

        return ExaminationModule(
            module_type=ExaminationModuleType.SAR_STR_FILING,
            status=(ModuleStatus.POPULATED if n_total > 0
                    else (ModuleStatus.PARTIAL if n_overdue > 0
                          else ModuleStatus.EMPTY_NO_DATA)),
            summary_metrics={
                "n_filings_total": n_total,
                "n_overdue_drafts": n_overdue,
                "n_submitted": n_submitted,
                "n_acknowledged_by_frc": summary.get(
                    "n_acknowledged_by_frc", 0),
                "n_under_investigation": summary.get(
                    "n_under_investigation", 0),
                "n_investigation_closed": summary.get(
                    "n_investigation_closed", 0),
                "submission_method": summary.get(
                    "submission_method", ""),
            },
            artifacts=artifacts,
            findings=tuple(findings),
            source_engines=("ENH-194 SarFilingEngine",))

    def _build_enterprise_risk_module(
            self, cra_engine: Optional[Any]) -> ExaminationModule:
        if cra_engine is None:
            return ExaminationModule(
                module_type=ExaminationModuleType.ENTERPRISE_RISK,
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    "Enterprise Risk module empty — cra_engine not "
                    "supplied.",
                ),
                source_engines=(
                    "ENH-198 ComplianceRiskAssessmentEngine",))

        try:
            latest = cra_engine.latest_assessment()
            summary = cra_engine.board_summary()
        except Exception:
            latest = None
            summary = {}

        if latest is None:
            return ExaminationModule(
                module_type=ExaminationModuleType.ENTERPRISE_RISK,
                status=ModuleStatus.EMPTY_NO_DATA,
                summary_metrics={},
                artifacts=(),
                findings=(
                    "No assessments performed in package period. "
                    "Run cra_engine.assess(...) before building "
                    "examiner package.",
                ),
                source_engines=(
                    "ENH-198 ComplianceRiskAssessmentEngine",))

        artifacts = (latest.to_dict(),)

        findings: List[str] = [
            f"Latest enterprise risk score: {latest.total_score} / "
            f"100 (band: {latest.risk_band.value}).",
        ]
        if latest.contradictions:
            findings.append(
                f"{len(latest.contradictions)} cross-cluster "
                f"contradictions surfaced by ENH-198.")

        # Surface deferral statuses
        if "DEFERRED" in latest.trend_analysis_status:
            findings.append(
                "Trend analysis explicitly DEFERRED — "
                "point-in-time only.")

        return ExaminationModule(
            module_type=ExaminationModuleType.ENTERPRISE_RISK,
            status=ModuleStatus.POPULATED,
            summary_metrics={
                "latest_assessment_id": latest.assessment_id,
                "latest_total_score": str(latest.total_score),
                "latest_risk_band": latest.risk_band.value,
                "latest_assessed_at_utc": latest.assessed_at_utc,
                "n_contradictions": len(latest.contradictions),
                "n_assessments_in_period": summary.get(
                    "n_assessments", 0),
                "trend_analysis_status": (
                    latest.trend_analysis_status),
                "ml_predictive_status": latest.ml_predictive_status,
            },
            artifacts=artifacts,
            findings=tuple(findings),
            source_engines=(
                "ENH-198 ComplianceRiskAssessmentEngine",))

    def _build_evidence_index_module(
            self,
            kyc_engine: Optional[Any],
            aml_engine: Optional[Any],
            sar_engine: Optional[Any]) -> ExaminationModule:
        """Cross-reference: for each customer with activity, list all
        the artifacts spanning KYC/AML/SAR. The audit-trail module."""
        index: Dict[str, Dict[str, List[str]]] = {}
        source_engines: List[str] = []

        if kyc_engine is not None:
            source_engines.append("ENH-191 KycOnboardingEngine")
            try:
                for d in kyc_engine.all_decisions():
                    cid = d.applicant_id
                    index.setdefault(cid, {})
                    index[cid].setdefault("kyc_decisions", [])
                    index[cid]["kyc_decisions"].append(
                        f"{d.outcome.value}@{d.decided_at_utc}")
            except Exception:
                pass

        if aml_engine is not None:
            source_engines.append("ENH-193 AmlMonitoringEngine")
            try:
                for r in aml_engine.all_results():
                    cid = r.customer_id
                    index.setdefault(cid, {})
                    index[cid].setdefault("aml_results", [])
                    index[cid]["aml_results"].append(
                        f"{r.outcome.value}@{r.monitored_at_utc}")
            except Exception:
                pass

        if sar_engine is not None:
            source_engines.append("ENH-194 SarFilingEngine")
            try:
                for f in sar_engine.all_filings():
                    cid = f.subject.subject_id
                    index.setdefault(cid, {})
                    index[cid].setdefault("sar_filings", [])
                    index[cid]["sar_filings"].append(
                        f"{f.filing_id}@{f.status.value}")
            except Exception:
                pass

        artifacts = tuple(
            {"customer_id": cid, **artifact_lists}
            for cid, artifact_lists in index.items())

        findings: List[str] = []
        if not index:
            findings.append("Evidence index empty — no engines wired.")
        else:
            findings.append(
                f"Evidence index covers {len(index)} customers "
                f"across {len(source_engines)} engines.")
            n_with_sars = sum(1 for c in index.values()
                              if "sar_filings" in c)
            if n_with_sars > 0:
                findings.append(
                    f"{n_with_sars} customers have SAR filings "
                    f"linked to monitoring/onboarding records.")

        return ExaminationModule(
            module_type=ExaminationModuleType.EVIDENCE_INDEX,
            status=(ModuleStatus.POPULATED if index
                    else ModuleStatus.EMPTY_NO_DATA),
            summary_metrics={
                "n_customers_indexed": len(index),
                "n_engines_referenced": len(source_engines),
            },
            artifacts=artifacts,
            findings=tuple(findings),
            source_engines=tuple(source_engines))

    def _build_deferred_module(
            self,
            module_type: ExaminationModuleType,
            reason: str) -> ExaminationModule:
        return ExaminationModule(
            module_type=module_type,
            status=ModuleStatus.DEFERRED,
            summary_metrics={},
            artifacts=(),
            findings=(),
            source_engines=(),
            deferred_reason=reason)

    # ------------------------------------------------------------------
    # Cluster health summary
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cluster_health_summary(
            modules: List[ExaminationModule]) -> Dict[str, Any]:
        n_populated = sum(1 for m in modules
                          if m.status == ModuleStatus.POPULATED)
        n_partial = sum(1 for m in modules
                        if m.status == ModuleStatus.PARTIAL)
        n_empty = sum(1 for m in modules
                      if m.status == ModuleStatus.EMPTY_NO_DATA)
        n_deferred = sum(1 for m in modules
                         if m.status == ModuleStatus.DEFERRED)

        # Pull headline metrics from key modules
        cdd = next((m for m in modules
                    if m.module_type ==
                       ExaminationModuleType.CDD), None)
        sar = next((m for m in modules
                    if m.module_type ==
                       ExaminationModuleType.SAR_STR_FILING), None)
        risk = next((m for m in modules
                     if m.module_type ==
                        ExaminationModuleType.ENTERPRISE_RISK), None)

        return {
            "n_modules_total": len(modules),
            "n_populated": n_populated,
            "n_partial": n_partial,
            "n_empty_no_data": n_empty,
            "n_deferred": n_deferred,
            "n_decisions": (
                cdd.summary_metrics.get("n_decisions", 0)
                if cdd else 0),
            "n_filings_overdue": (
                sar.summary_metrics.get("n_overdue_drafts", 0)
                if sar else 0),
            "latest_risk_score": (
                risk.summary_metrics.get("latest_total_score", "—")
                if risk else "—"),
            "latest_risk_band": (
                risk.summary_metrics.get("latest_risk_band", "—")
                if risk else "—"),
        }

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def package_by_id(self, package_id: str) -> ExaminationPackage:
        if package_id not in self._packages:
            raise KeyError(f"package not found: {package_id}")
        return self._packages[package_id]

    def all_packages(self) -> Tuple[ExaminationPackage, ...]:
        return tuple(self._packages.values())

    def board_summary(self) -> Dict[str, Any]:
        n_total = len(self._packages)
        if n_total == 0:
            return {
                "entity": "Ecobank Kenya",
                "engine": "ENH-199 ExaminerReportingEngine",
                "n_packages": 0,
                "latest": None,
                "regulatory_basis": (
                    "FFIEC BSA/AML Examination Manual, CBK Risk-Based "
                    "Supervision Framework, POCAMLA §53 records "
                    "retention, FATF Methodology Immediate Outcome 4"),
                "export_format_status": self.EXPORT_FORMAT_NOTE,
            }
        latest = list(self._packages.values())[-1]
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-199 ExaminerReportingEngine",
            "n_packages": n_total,
            "latest_package_id": latest.package_id,
            "latest_status": latest.status.value,
            "latest_period": (
                f"{latest.examination_period_start} to "
                f"{latest.examination_period_end}"),
            "latest_modules": len(latest.modules),
            "latest_health": dict(latest.cluster_health_summary),
            "regulatory_basis": (
                "FFIEC BSA/AML Examination Manual, CBK Risk-Based "
                "Supervision Framework, POCAMLA §53 records "
                "retention, FATF Methodology Immediate Outcome 4"),
            "export_format_status": self.EXPORT_FORMAT_NOTE,
        }
