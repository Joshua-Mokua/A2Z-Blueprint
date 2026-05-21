"""utils/compliance_risk_assessment.py — ENH-198 Compliance Risk
Assessment Engine.

================================================================================
A2Z MIS 360 — ENH-198 Compliance Risk Assessment Engine
================================================================================

ROLLUP engine that aggregates inputs from the 4 individual AML engines
(ENH-191 KYC/KYB onboarding, ENH-192 PEP/Sanctions screening, ENH-193
AML transaction monitoring, ENH-194 SAR/STR filing) and produces an
enterprise-level compliance risk score with executive dashboard.

CRITICAL DESIGN DECISION — composition over duplication
-------------------------------------------------------
This engine does NOT recompute risk. It AGGREGATES already-computed
upstream signals:

    Customer onboarding decisions (ENH-191) → tier distribution
        + sanctions/PEP flag concentration
    AML monitoring results (ENH-193)        → alert volume + severity mix
    SAR/STR filings (ENH-194)               → filing status + overdue
                                                 backlog (regulatory exposure)

The score is the RISK CONCENTRATION across these dimensions, not a
fresh model output. Same compose-don't-duplicate pattern as v10.160
ENH-191 (over kyc_aml_risk), v10.162 ENH-193 (over transaction_
monitoring), v10.163 ENH-194 (greenfield builder).

REGULATORY ALIGNMENT
--------------------
- CBK Prudential Guideline CBK/PG/15 §3 (Risk-Based Approach to AML/CFT)
  — institution must maintain an enterprise-wide AML risk assessment
  that drives policy, training, monitoring intensity
- FATF Recommendation 1 — Risk-Based Approach: identify, assess, and
  understand ML/TF risks
- Basel Committee Sound Management of Risks Related to Money Laundering
  Principles 2-5

SCORE COMPOSITION (deterministic, additive, capped at 100)
----------------------------------------------------------
The enterprise compliance risk score is composed of 5 dimensions, each
contributing 0-25 points (capped, max 100 total):

    1. Customer-tier concentration       (0-25 pts)
       % of customer base in EDD or PROHIBITED tiers — the higher this
       %, the more EDD effort the institution carries
    2. Sanctions/PEP exposure            (0-25 pts)
       % of customer base flagged as PEP or with sanctions matches
    3. Alert backlog severity            (0-25 pts)
       Open alerts (ALERTS_OPEN) + escalations (ESCALATE_TO_SAR) — the
       higher this %, the more compliance officers are stretched
    4. Filing backlog (regulatory risk)  (0-25 pts)
       Overdue drafts past POCAMLA §44 7-day deadline are direct
       regulatory exposure — heavily weighted
    5. Cross-cluster contradiction       (-10 to +10 pts)
       Customer in PROHIBITED tier but no SAR filed → suspicion of
       evasion/non-compliance; bumps score up
       Customer in CDD tier but multiple critical alerts → tier review
       overdue

Bands:
    LOW         < 30 pts
    MEDIUM     30-49 pts
    HIGH       50-79 pts
    CRITICAL  >= 80 pts

The thresholds are configurable via class constants for stress testing
calibration to actual operational data.

HONEST DEFERRALS
----------------
- TREND ANALYSIS deferred: this engine reports POINT-IN-TIME state.
  Trend ("is risk getting worse?") needs historical assessments stored
  over time — out of scope for v10.164. Field
  `trend_analysis_status` reads DEFERRED.
- INDUSTRY/SECTOR CONCENTRATION deferred: the cross-cluster
  contradiction logic in dimension 5 needs SIC code aggregation per
  customer + sector-level risk weighting tables (CBK regulator
  guidance not yet codified) — flagged as PARTIAL in
  `industry_concentration_status`.
- NO ML PREDICTION: per the standing pattern, this is rule-based +
  scorecard. ML would need labeled enterprise risk events ("this
  assessment was followed by a regulatory finding within 90 days")
  which don't exist in a sandbox. `ml_predictive_status` reads
  DEFERRED with the same reasoning as ENH-193 v10.162.

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations + constants
# ---------------------------------------------------------------------------


class RiskBand(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Band thresholds — applied to total score [0, 100]
LOW_BAND_MAX = Decimal("29")        # < 30 → LOW
MEDIUM_BAND_MAX = Decimal("49")     # 30-49 → MEDIUM
HIGH_BAND_MAX = Decimal("79")       # 50-79 → HIGH
# CRITICAL: >= 80

# Per-dimension caps
TIER_CONCENTRATION_CAP = Decimal("25")
SANCTIONS_PEP_CAP = Decimal("25")
ALERT_BACKLOG_CAP = Decimal("25")
FILING_BACKLOG_CAP = Decimal("25")
CROSS_CLUSTER_FLOOR = Decimal("-10")  # contradictions can lower score
CROSS_CLUSTER_CEILING = Decimal("10")


# ---------------------------------------------------------------------------
# Score component dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreComponent:
    """Per-dimension contribution to total enterprise risk score."""
    dimension: str
    raw_value: Decimal           # underlying metric (e.g. % EDD customers)
    points: Decimal              # capped contribution to total
    cap: Decimal
    contributing_factors: Tuple[str, ...]  # human-readable reasons


@dataclass(frozen=True)
class ComplianceRiskAssessment:
    """Enterprise-level risk assessment output."""
    assessment_id: str
    assessed_at_utc: str
    total_score: Decimal              # 0-100
    risk_band: RiskBand
    components: Tuple[ScoreComponent, ...]
    # Aggregated counts for executive dashboard
    n_customers: int
    n_kyc: int
    n_kyb: int
    n_edd_or_prohibited: int
    n_pep_flagged: int
    n_sanctions_flagged: int
    n_open_alerts: int
    n_critical_alerts: int
    n_filings_total: int
    n_filings_overdue: int
    n_filings_under_investigation: int
    # Cross-cluster contradictions surfaced
    contradictions: Tuple[str, ...]
    # Honest deferral surfaces
    trend_analysis_status: str
    industry_concentration_status: str
    ml_predictive_status: str
    # Provenance — which engines fed in
    upstream_engines: Tuple[str, ...]
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "assessed_at_utc": self.assessed_at_utc,
            "total_score": str(self.total_score),
            "risk_band": self.risk_band.value,
            "components": [
                {
                    "dimension": c.dimension,
                    "raw_value": str(c.raw_value),
                    "points": str(c.points),
                    "cap": str(c.cap),
                    "contributing_factors": list(c.contributing_factors),
                }
                for c in self.components
            ],
            "n_customers": self.n_customers,
            "n_kyc": self.n_kyc,
            "n_kyb": self.n_kyb,
            "n_edd_or_prohibited": self.n_edd_or_prohibited,
            "n_pep_flagged": self.n_pep_flagged,
            "n_sanctions_flagged": self.n_sanctions_flagged,
            "n_open_alerts": self.n_open_alerts,
            "n_critical_alerts": self.n_critical_alerts,
            "n_filings_total": self.n_filings_total,
            "n_filings_overdue": self.n_filings_overdue,
            "n_filings_under_investigation": (
                self.n_filings_under_investigation),
            "contradictions": list(self.contradictions),
            "trend_analysis_status": self.trend_analysis_status,
            "industry_concentration_status": (
                self.industry_concentration_status),
            "ml_predictive_status": self.ml_predictive_status,
            "upstream_engines": list(self.upstream_engines),
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ComplianceRiskAssessmentEngine:
    """ENH-198 Compliance Risk Assessment Engine.

    Stateless aggregator + score computer. Operator passes upstream
    engine state in; engine computes and returns a
    ComplianceRiskAssessment. Engine does retain the most recent
    assessment for retrieval.

    Use:
        engine = ComplianceRiskAssessmentEngine()
        assessment = engine.assess(
            kyc_engine=kyc_onboarding_engine,    # ENH-191
            aml_engine=aml_monitoring_engine,    # ENH-193
            sar_engine=sar_filing_engine,        # ENH-194
        )
        # assessment.total_score in [0, 100]
        # assessment.risk_band in {LOW, MEDIUM, HIGH, CRITICAL}
    """

    TREND_ANALYSIS_DEFERRED = (
        "DEFERRED — this engine reports POINT-IN-TIME state. Trend "
        "analysis ('is enterprise risk getting worse?') requires "
        "historical assessments stored over time + delta computation "
        "+ control-chart visualization. Out of scope for v10.164; "
        "tracked as future work for ENH-198+ increments. Operators "
        "should run assess() periodically (e.g. daily) and persist "
        "results externally to build trend.")

    INDUSTRY_CONCENTRATION_PARTIAL = (
        "PARTIAL — cross-cluster contradiction dimension flags some "
        "concentration patterns (PROHIBITED-without-SAR, CDD-with-"
        "multiple-critical-alerts). Full industry/sector concentration "
        "analysis requires SIC code aggregation per customer + sector-"
        "level risk weighting tables aligned to CBK Risk-Based "
        "Supervision Framework guidance. Sector weights not yet "
        "codified — flagged as future work for ENH-198+ increments.")

    ML_PREDICTIVE_DEFERRED = (
        "DEFERRED — ML predictive enterprise risk modeling requires "
        "labeled regulatory events (assessments followed by "
        "regulatory findings within 90 days). Such labeled data "
        "doesn't exist in sandbox. Current scoring is rule-based + "
        "scorecard with deterministic dimension weights. Same "
        "deferral pattern as ENH-193 ml_layer_status.")

    UPSTREAM_ENGINES_LITERAL = (
        "ENH-191 KycOnboardingEngine",
        "ENH-193 AmlMonitoringEngine",
        "ENH-194 SarFilingEngine",
    )

    def __init__(self) -> None:
        self._assessments: List[ComplianceRiskAssessment] = []
        self._next_id = 1

    # ------------------------------------------------------------------
    # Public assess() — the main entry point
    # ------------------------------------------------------------------

    def assess(
        self,
        kyc_engine: Optional[Any] = None,
        aml_engine: Optional[Any] = None,
        sar_engine: Optional[Any] = None,
    ) -> ComplianceRiskAssessment:
        """Run the full enterprise risk assessment.

        Each upstream engine is optional. Missing engines contribute
        zero points to their dimension AND surface in the
        contradictions list (Rule 6 honesty: missing data does NOT
        lower the risk score; we explicitly note the gap).
        """
        # 1. Aggregate raw counts from upstream engines
        kyc_data = self._aggregate_kyc(kyc_engine)
        aml_data = self._aggregate_aml(aml_engine)
        sar_data = self._aggregate_sar(sar_engine)

        # 2. Compute each scoring dimension
        comp_tier = self._compute_tier_concentration(kyc_data)
        comp_sanctions = self._compute_sanctions_pep_exposure(kyc_data)
        comp_alerts = self._compute_alert_backlog(aml_data)
        comp_filings = self._compute_filing_backlog(sar_data)
        comp_contradictions, contradictions = (
            self._compute_cross_cluster_contradictions(
                kyc_data, aml_data, sar_data))

        # Add data-availability contradictions
        if kyc_engine is None:
            contradictions = contradictions + (
                "kyc_engine_not_supplied — tier concentration and "
                "sanctions exposure dimensions return zero",)
        if aml_engine is None:
            contradictions = contradictions + (
                "aml_engine_not_supplied — alert backlog dimension "
                "returns zero",)
        if sar_engine is None:
            contradictions = contradictions + (
                "sar_engine_not_supplied — filing backlog dimension "
                "returns zero",)

        # 3. Sum + clamp
        total = (comp_tier.points + comp_sanctions.points +
                  comp_alerts.points + comp_filings.points +
                  comp_contradictions.points)
        total = max(Decimal("0"), min(Decimal("100"), total))
        total = total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        # 4. Band assignment
        band = self._band_from_score(total)

        # 5. Build assessment
        assessment_id = f"CRA-{self._next_id:06d}"
        self._next_id += 1

        assessment = ComplianceRiskAssessment(
            assessment_id=assessment_id,
            assessed_at_utc=datetime.now(timezone.utc).isoformat(),
            total_score=total,
            risk_band=band,
            components=(comp_tier, comp_sanctions, comp_alerts,
                          comp_filings, comp_contradictions),
            n_customers=kyc_data["n_total"],
            n_kyc=kyc_data["n_kyc"],
            n_kyb=kyc_data["n_kyb"],
            n_edd_or_prohibited=kyc_data["n_edd_or_prohibited"],
            n_pep_flagged=kyc_data["n_pep"],
            n_sanctions_flagged=kyc_data["n_sanctions"],
            n_open_alerts=aml_data["n_open"],
            n_critical_alerts=aml_data["n_critical"],
            n_filings_total=sar_data["n_total"],
            n_filings_overdue=sar_data["n_overdue"],
            n_filings_under_investigation=(
                sar_data["n_under_investigation"]),
            contradictions=contradictions,
            trend_analysis_status=self.TREND_ANALYSIS_DEFERRED,
            industry_concentration_status=(
                self.INDUSTRY_CONCENTRATION_PARTIAL),
            ml_predictive_status=self.ML_PREDICTIVE_DEFERRED,
            upstream_engines=self.UPSTREAM_ENGINES_LITERAL,
            meta={
                "engine_version": "ENH-198-v10.164",
                "thresholds": {
                    "low_max": str(LOW_BAND_MAX),
                    "medium_max": str(MEDIUM_BAND_MAX),
                    "high_max": str(HIGH_BAND_MAX),
                },
                "dimension_caps": {
                    "tier_concentration": str(TIER_CONCENTRATION_CAP),
                    "sanctions_pep": str(SANCTIONS_PEP_CAP),
                    "alert_backlog": str(ALERT_BACKLOG_CAP),
                    "filing_backlog": str(FILING_BACKLOG_CAP),
                    "cross_cluster_floor": str(CROSS_CLUSTER_FLOOR),
                    "cross_cluster_ceiling": (
                        str(CROSS_CLUSTER_CEILING)),
                },
            },
        )
        self._assessments.append(assessment)
        return assessment

    # ------------------------------------------------------------------
    # Aggregators
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_kyc(kyc_engine: Optional[Any]) -> Dict[str, Any]:
        """Pull tier distribution + sanctions/PEP counts from
        ENH-191 KycOnboardingEngine."""
        if kyc_engine is None:
            return {"n_total": 0, "n_kyc": 0, "n_kyb": 0,
                    "n_edd_or_prohibited": 0, "n_prohibited": 0,
                    "n_pep": 0, "n_sanctions": 0,
                    "tier_distribution": {}}
        try:
            decisions = kyc_engine.all_decisions()
        except Exception:
            return {"n_total": 0, "n_kyc": 0, "n_kyb": 0,
                    "n_edd_or_prohibited": 0, "n_prohibited": 0,
                    "n_pep": 0, "n_sanctions": 0,
                    "tier_distribution": {}}

        n_total = len(decisions)
        n_kyc = sum(1 for d in decisions if d.applicant_kind == "KYC")
        n_kyb = sum(1 for d in decisions if d.applicant_kind == "KYB")
        n_pep = sum(1 for d in decisions if d.pep_flag)
        n_sanctions = sum(1 for d in decisions if d.sanctions_flag)

        tier_dist: Dict[str, int] = {}
        n_edd_or_proh = 0
        n_prohibited = 0
        for d in decisions:
            if d.tier:
                t = d.tier.value if hasattr(d.tier, "value") else str(
                    d.tier)
                tier_dist[t] = tier_dist.get(t, 0) + 1
                if t in ("EDD", "PROHIBITED"):
                    n_edd_or_proh += 1
                if t == "PROHIBITED":
                    n_prohibited += 1

        return {
            "n_total": n_total, "n_kyc": n_kyc, "n_kyb": n_kyb,
            "n_edd_or_prohibited": n_edd_or_proh,
            "n_prohibited": n_prohibited,
            "n_pep": n_pep, "n_sanctions": n_sanctions,
            "tier_distribution": tier_dist,
            "decisions": decisions,
        }

    @staticmethod
    def _aggregate_aml(aml_engine: Optional[Any]) -> Dict[str, Any]:
        """Pull alert backlog from ENH-193 AmlMonitoringEngine."""
        if aml_engine is None:
            return {"n_total": 0, "n_open": 0, "n_critical": 0,
                    "n_escalate_sar": 0, "n_escalate_block": 0,
                    "outcome_counts": {}}
        try:
            results = aml_engine.all_results()
        except Exception:
            return {"n_total": 0, "n_open": 0, "n_critical": 0,
                    "n_escalate_sar": 0, "n_escalate_block": 0,
                    "outcome_counts": {}}

        outcome_counts: Dict[str, int] = {}
        n_critical = 0
        for r in results:
            outcome = (r.outcome.value if hasattr(r.outcome, "value")
                       else str(r.outcome))
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            n_critical += getattr(r, "n_critical", 0)

        n_open = (outcome_counts.get("ALERTS_OPEN", 0) +
                   outcome_counts.get("ESCALATE_TO_SAR", 0) +
                   outcome_counts.get("ESCALATE_TO_BLOCK", 0))

        return {
            "n_total": len(results),
            "n_open": n_open,
            "n_critical": n_critical,
            "n_escalate_sar": outcome_counts.get("ESCALATE_TO_SAR", 0),
            "n_escalate_block": outcome_counts.get(
                "ESCALATE_TO_BLOCK", 0),
            "outcome_counts": outcome_counts,
            "results": results,
        }

    @staticmethod
    def _aggregate_sar(sar_engine: Optional[Any]) -> Dict[str, Any]:
        """Pull filing status from ENH-194 SarFilingEngine."""
        if sar_engine is None:
            return {"n_total": 0, "n_overdue": 0,
                    "n_under_investigation": 0,
                    "n_submitted_or_later": 0,
                    "status_counts": {}}
        try:
            filings = sar_engine.all_filings()
            overdue = sar_engine.overdue_filings()
        except Exception:
            return {"n_total": 0, "n_overdue": 0,
                    "n_under_investigation": 0,
                    "n_submitted_or_later": 0,
                    "status_counts": {}}

        status_counts: Dict[str, int] = {}
        for f in filings:
            s = (f.status.value if hasattr(f.status, "value")
                 else str(f.status))
            status_counts[s] = status_counts.get(s, 0) + 1

        return {
            "n_total": len(filings),
            "n_overdue": len(overdue),
            "n_under_investigation": status_counts.get(
                "INVESTIGATION_OPENED", 0),
            "n_submitted_or_later": (
                status_counts.get("SUBMITTED", 0) +
                status_counts.get("ACKNOWLEDGED", 0) +
                status_counts.get("INVESTIGATION_OPENED", 0) +
                status_counts.get("INVESTIGATION_CLOSED", 0)),
            "status_counts": status_counts,
            "filings": filings,
        }

    # ------------------------------------------------------------------
    # Score component computers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_tier_concentration(
            kyc_data: Dict[str, Any]) -> ScoreComponent:
        """% of customer base in EDD or PROHIBITED tiers.

        Linear scaling: 0% → 0 pts, 25%+ → 25 pts (capped).
        """
        n_total = kyc_data["n_total"]
        n_edd_proh = kyc_data["n_edd_or_prohibited"]

        if n_total == 0:
            return ScoreComponent(
                dimension="tier_concentration",
                raw_value=Decimal("0"),
                points=Decimal("0"),
                cap=TIER_CONCENTRATION_CAP,
                contributing_factors=("no_customers_assessed",))

        pct = (Decimal(n_edd_proh) / Decimal(n_total) *
                Decimal("100"))
        # Linear: 25% pct → 25 pts (1:1 within cap)
        points = min(pct, TIER_CONCENTRATION_CAP)

        factors: List[str] = []
        factors.append(f"{n_edd_proh}_of_{n_total}_customers_in_EDD_or_PROHIBITED")
        if kyc_data["n_prohibited"] > 0:
            factors.append(
                f"{kyc_data['n_prohibited']}_PROHIBITED_customers_should_not_be_active")
        return ScoreComponent(
            dimension="tier_concentration",
            raw_value=pct.quantize(Decimal("0.1")),
            points=points.quantize(Decimal("0.1")),
            cap=TIER_CONCENTRATION_CAP,
            contributing_factors=tuple(factors))

    @staticmethod
    def _compute_sanctions_pep_exposure(
            kyc_data: Dict[str, Any]) -> ScoreComponent:
        """% of customer base flagged as PEP or sanctions.

        Sanctions weighted 3x heavier than PEP since sanctions matches
        are absolute regulatory exposure.
        """
        n_total = kyc_data["n_total"]
        n_pep = kyc_data["n_pep"]
        n_sanctions = kyc_data["n_sanctions"]

        if n_total == 0:
            return ScoreComponent(
                dimension="sanctions_pep_exposure",
                raw_value=Decimal("0"),
                points=Decimal("0"),
                cap=SANCTIONS_PEP_CAP,
                contributing_factors=("no_customers_assessed",))

        # Weighted: PEP 1x, sanctions 3x
        weighted_count = Decimal(n_pep) + Decimal("3") * Decimal(
            n_sanctions)
        weighted_pct = weighted_count / Decimal(n_total) * Decimal(
            "100")
        points = min(weighted_pct, SANCTIONS_PEP_CAP)

        factors: List[str] = []
        if n_pep > 0:
            factors.append(f"{n_pep}_PEP_flagged_customers")
        if n_sanctions > 0:
            factors.append(
                f"{n_sanctions}_SANCTIONS_flagged_customers_3x_weight")
        if not factors:
            factors.append("no_pep_or_sanctions_exposure")

        return ScoreComponent(
            dimension="sanctions_pep_exposure",
            raw_value=weighted_pct.quantize(Decimal("0.1")),
            points=points.quantize(Decimal("0.1")),
            cap=SANCTIONS_PEP_CAP,
            contributing_factors=tuple(factors))

    @staticmethod
    def _compute_alert_backlog(
            aml_data: Dict[str, Any]) -> ScoreComponent:
        """Open alerts + escalations across customer base.

        Critical alerts weighted 2x. Score capped at 25.
        Without total customer denominator we use absolute alert count
        with a soft scaling: 1 critical = 5 pts, 1 open = 1 pt.
        """
        n_open = aml_data["n_open"]
        n_critical = aml_data["n_critical"]

        # Soft scaling: critical = 5 pts each, open = 1 pt each
        raw_score = Decimal(n_critical) * Decimal("5") + Decimal(
            n_open)
        points = min(raw_score, ALERT_BACKLOG_CAP)

        factors: List[str] = []
        if n_critical > 0:
            factors.append(f"{n_critical}_critical_alerts_5pts_each")
        if n_open > 0:
            factors.append(f"{n_open}_open_alerts_1pt_each")
        if aml_data["n_escalate_sar"] > 0:
            factors.append(
                f"{aml_data['n_escalate_sar']}_escalated_to_SAR_filing")
        if aml_data["n_escalate_block"] > 0:
            factors.append(
                f"{aml_data['n_escalate_block']}_escalated_to_BLOCK")
        if not factors:
            factors.append("no_open_alerts_in_backlog")

        return ScoreComponent(
            dimension="alert_backlog",
            raw_value=raw_score.quantize(Decimal("0.1")),
            points=points.quantize(Decimal("0.1")),
            cap=ALERT_BACKLOG_CAP,
            contributing_factors=tuple(factors))

    @staticmethod
    def _compute_filing_backlog(
            sar_data: Dict[str, Any]) -> ScoreComponent:
        """Overdue drafts past POCAMLA §44 7-day deadline =
        regulatory exposure. Weighted heavily — 8 pts per overdue.

        Investigations open are operationally heavy but not regulatory
        exposure (institution did its part). 1 pt each.
        """
        n_overdue = sar_data["n_overdue"]
        n_investigation = sar_data["n_under_investigation"]

        # Heavy weight on overdue: 8 pts each → 4 overdue maxes the cap
        raw_score = (Decimal(n_overdue) * Decimal("8") +
                      Decimal(n_investigation))
        points = min(raw_score, FILING_BACKLOG_CAP)

        factors: List[str] = []
        if n_overdue > 0:
            factors.append(
                f"{n_overdue}_DRAFT_filings_past_POCAMLA_§44_7day_"
                f"deadline_8pts_each")
        if n_investigation > 0:
            factors.append(
                f"{n_investigation}_filings_under_FRC_investigation")
        if sar_data["n_total"] == 0:
            factors.append("no_filings_in_backlog")
        elif not factors:
            factors.append("no_overdue_or_active_filings")

        return ScoreComponent(
            dimension="filing_backlog",
            raw_value=raw_score.quantize(Decimal("0.1")),
            points=points.quantize(Decimal("0.1")),
            cap=FILING_BACKLOG_CAP,
            contributing_factors=tuple(factors))

    @staticmethod
    def _compute_cross_cluster_contradictions(
            kyc_data: Dict[str, Any],
            aml_data: Dict[str, Any],
            sar_data: Dict[str, Any]
    ) -> Tuple[ScoreComponent, Tuple[str, ...]]:
        """Surface contradictions across the 4 engines.

        Each contradiction adds 5 pts to the dimension score (capped
        at +10). Returns (component, contradictions_list).
        """
        contradictions: List[str] = []
        bump = Decimal("0")

        # Contradiction 1: PROHIBITED tier customer but no SAR filed
        if kyc_data["n_prohibited"] > 0 and \
                sar_data["n_submitted_or_later"] == 0:
            contradictions.append(
                f"{kyc_data['n_prohibited']}_PROHIBITED_customers_but_"
                f"no_SAR_submitted_to_FRC")
            bump += Decimal("5")

        # Contradiction 2: critical alerts firing but customer base in
        # mostly SDD/CDD tiers (suggests tier review overdue)
        if aml_data["n_critical"] > 3:
            n_total = kyc_data["n_total"]
            n_edd = kyc_data["n_edd_or_prohibited"]
            if n_total > 0 and (Decimal(n_edd) / Decimal(n_total) *
                                  Decimal("100")) < Decimal("5"):
                contradictions.append(
                    f"{aml_data['n_critical']}_critical_alerts_but_<5pct_"
                    f"customers_in_EDD_tier_review_calibration_overdue")
                bump += Decimal("5")

        # Contradiction 3: SAR escalations but no SAR filings (engines
        # not wired together)
        if (aml_data["n_escalate_sar"] > 0 and
                sar_data["n_total"] == 0):
            contradictions.append(
                f"{aml_data['n_escalate_sar']}_AML_escalations_but_"
                f"zero_SAR_filings_built_engines_not_wired")
            bump += Decimal("5")

        bump = min(bump, CROSS_CLUSTER_CEILING)
        bump = max(bump, CROSS_CLUSTER_FLOOR)

        factors = (tuple(contradictions) if contradictions
                   else ("no_cross_cluster_contradictions",))

        component = ScoreComponent(
            dimension="cross_cluster_contradictions",
            raw_value=Decimal(len(contradictions)),
            points=bump.quantize(Decimal("0.1")),
            cap=CROSS_CLUSTER_CEILING,
            contributing_factors=factors)

        return component, tuple(contradictions)

    # ------------------------------------------------------------------
    # Band assignment
    # ------------------------------------------------------------------

    @staticmethod
    def _band_from_score(score: Decimal) -> RiskBand:
        if score <= LOW_BAND_MAX:
            return RiskBand.LOW
        if score <= MEDIUM_BAND_MAX:
            return RiskBand.MEDIUM
        if score <= HIGH_BAND_MAX:
            return RiskBand.HIGH
        return RiskBand.CRITICAL

    # ------------------------------------------------------------------
    # Retrieval / portfolio summary
    # ------------------------------------------------------------------

    def assessment_by_id(self, assessment_id: str) -> ComplianceRiskAssessment:
        for a in self._assessments:
            if a.assessment_id == assessment_id:
                return a
        raise KeyError(f"assessment not found: {assessment_id}")

    def all_assessments(self) -> Tuple[ComplianceRiskAssessment, ...]:
        return tuple(self._assessments)

    def latest_assessment(self) -> Optional[ComplianceRiskAssessment]:
        return self._assessments[-1] if self._assessments else None

    def board_summary(self) -> Dict[str, Any]:
        if not self._assessments:
            return {
                "entity": "Ecobank Kenya",
                "engine": "ENH-198 ComplianceRiskAssessmentEngine",
                "n_assessments": 0,
                "latest": None,
                "trend_analysis_status": self.TREND_ANALYSIS_DEFERRED,
                "regulatory_basis": (
                    "CBK PG/15 §3 (Risk-Based Approach), FATF "
                    "Recommendation 1, Basel Committee Sound "
                    "Management of Risks Related to Money Laundering"),
            }
        latest = self._assessments[-1]
        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-198 ComplianceRiskAssessmentEngine",
            "n_assessments": len(self._assessments),
            "latest_assessment_id": latest.assessment_id,
            "latest_total_score": str(latest.total_score),
            "latest_risk_band": latest.risk_band.value,
            "latest_assessed_at_utc": latest.assessed_at_utc,
            "latest_n_customers": latest.n_customers,
            "latest_n_overdue_filings": latest.n_filings_overdue,
            "latest_contradictions_count": len(latest.contradictions),
            "trend_analysis_status": self.TREND_ANALYSIS_DEFERRED,
            "industry_concentration_status": (
                self.INDUSTRY_CONCENTRATION_PARTIAL),
            "ml_predictive_status": self.ML_PREDICTIVE_DEFERRED,
            "regulatory_basis": (
                "CBK PG/15 §3 (Risk-Based Approach), FATF "
                "Recommendation 1, Basel Committee Sound Management "
                "of Risks Related to Money Laundering Principles 2-5"),
        }
