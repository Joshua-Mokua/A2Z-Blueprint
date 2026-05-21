"""utils/sar_filing.py — ENH-194 SAR/STR Filing Engine.

================================================================================
A2Z MIS 360 — ENH-194 SAR/STR Filing Engine
================================================================================

Builds and tracks Suspicious Activity Reports (SARs) and Suspicious
Transaction Reports (STRs) for filing with the Kenya Financial Reporting
Centre (FRC). Consumes ENH-193 AmlMonitoringResult outputs with
outcome=ESCALATE_TO_SAR or ESCALATE_TO_BLOCK and produces FRC-filing-
ready payloads.

REGULATORY ALIGNMENT
--------------------
- Kenya Proceeds of Crime and Anti-Money Laundering Act (POCAMLA) §44 —
  reporting institution must file SAR within **7 days** of the suspicion
  forming. Engine tracks `suspicion_formed_at` + computes
  `filing_deadline` automatically.
- FATF Recommendation 20 — Suspicious Transaction Reporting
- CBK Prudential Guideline CBK/PG/15 — AML/CFT compliance
- FRC Reporting Format — required SAR fields per FRC's published
  reporting template

FILING LIFECYCLE
----------------
A SAR/STR moves through this state machine:

    DRAFT
        →  SUBMITTED (operator confirms + timestamp recorded)
            →  ACKNOWLEDGED (FRC acknowledges receipt — usually within 48h)
                →  INVESTIGATION_OPENED (FRC opens case)
                    →  INVESTIGATION_CLOSED (FRC closes; outcome recorded)

The state machine enforces forward-only transitions with one exception:
DRAFT can be WITHDRAWN before SUBMITTED (e.g. if alerted analyst
re-classifies as false positive). Once SUBMITTED, the report cannot be
withdrawn — POCAMLA requires the institution to maintain the filing
even if subsequent investigation clears the customer.

CRITICAL DESIGN DECISION — composition over duplication
-------------------------------------------------------
This engine does NOT detect suspicious activity (that's ENH-193's job)
nor screen sanctions (ENH-192) nor onboard customers (ENH-191). It
PRODUCES A REGULATORY ARTIFACT from inputs supplied by upstream
engines. Each FilingDecision has a `provenance` field pointing back to
the upstream `AmlMonitoringResult.customer_id` + monitored_at_utc so
auditors can reconstruct the trail.

Same compose-don't-duplicate pattern as v10.160 ENH-191 (over
kyc_aml_risk) and v10.162 ENH-193 (over transaction_monitoring).

HONEST DEFERRAL — FRC ELECTRONIC SUBMISSION
-------------------------------------------
The actual submission to FRC is done via FRC's secure web portal or
encrypted email channel — neither has a public Python API. v10.163
ships the BUILD + TRACK + EXPORT capability:
- Build a structured FilingPayload from upstream data
- Track lifecycle through the 6 states
- Export to FRC-required JSON format for operator manual upload

The `submission_method` field on the FilingPayload reads MANUAL_PORTAL
explicitly so operators don't assume electronic auto-submit. When/if
FRC publishes a programmatic submission API, an ENH-194+ increment can
add wire-level submission. Out of scope for this drop.

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ReportType(str, Enum):
    """SAR vs STR distinction per FRC.

    SAR — Suspicious Activity Report: behavioural patterns, account
    activity, customer profile changes (no specific transaction
    necessarily required).

    STR — Suspicious Transaction Report: focused on specific
    transactions or sequences. Most ENH-193 alerts produce STRs.
    """
    SAR = "SAR"
    STR = "STR"


class FilingStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATION_OPENED = "INVESTIGATION_OPENED"
    INVESTIGATION_CLOSED = "INVESTIGATION_CLOSED"
    WITHDRAWN = "WITHDRAWN"  # only DRAFT → WITHDRAWN allowed


class TransitionOutcome(str, Enum):
    OK = "OK"
    REJECTED_INVALID_TRANSITION = "REJECTED_INVALID_TRANSITION"
    REJECTED_REASON_REQUIRED = "REJECTED_REASON_REQUIRED"
    REJECTED_REPORT_NOT_FOUND = "REJECTED_REPORT_NOT_FOUND"


# Allowed transitions per POCAMLA §44 + FRC procedural guidance
ALLOWED_TRANSITIONS: Mapping[FilingStatus, Tuple[FilingStatus, ...]] = {
    FilingStatus.DRAFT: (FilingStatus.SUBMITTED, FilingStatus.WITHDRAWN),
    FilingStatus.SUBMITTED: (FilingStatus.ACKNOWLEDGED,),
    FilingStatus.ACKNOWLEDGED: (FilingStatus.INVESTIGATION_OPENED,
                                  FilingStatus.INVESTIGATION_CLOSED),
    FilingStatus.INVESTIGATION_OPENED: (FilingStatus.INVESTIGATION_CLOSED,),
    FilingStatus.INVESTIGATION_CLOSED: (),  # terminal
    FilingStatus.WITHDRAWN: (),  # terminal
}

# POCAMLA §44 — 7-day filing deadline from suspicion formation
POCAMLA_FILING_DEADLINE_DAYS = 7


# ---------------------------------------------------------------------------
# Input + provenance dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubjectIdentity:
    """The customer/business subject of the report.

    For KYC subjects: nat_id is the national ID.
    For KYB subjects: nat_id is the BRS certificate number.
    """
    subject_id: str   # internal customer_id
    legal_name: str
    subject_kind: str  # "INDIVIDUAL" | "BUSINESS"
    nat_id: str = ""
    nationality: str = "KE"
    date_of_birth_or_incorporation: str = ""
    occupation_or_industry: str = ""
    address: str = ""


@dataclass(frozen=True)
class TransactionEvidence:
    """A specific transaction cited in the SAR/STR."""
    txn_id: str
    txn_date: str  # YYYY-MM-DD
    amount_kes: Decimal
    txn_type: str   # CASH_DEPOSIT, WIRE_OUT, etc.
    counterparty_name: str = ""
    counterparty_country: str = ""
    description: str = ""


@dataclass(frozen=True)
class AlertProvenance:
    """Trace back to the upstream alert that triggered this filing."""
    monitoring_engine: str  # "ENH-193 AmlMonitoringEngine"
    customer_id: str
    monitored_at_utc: str
    rule_ids: Tuple[str, ...]
    rule_names: Tuple[str, ...]
    severity: str
    escalation_reason: str = ""


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FilingPayload:
    """The structured SAR/STR payload + lifecycle metadata."""
    filing_id: str
    report_type: ReportType
    subject: SubjectIdentity
    transactions: Tuple[TransactionEvidence, ...]
    suspicion_narrative: str
    risk_indicators: Tuple[str, ...]   # e.g. ("R2", "EDD_TIER", "HIGH_RISK_GEO")
    suspicion_formed_at_utc: str
    filing_deadline_utc: str           # POCAMLA §44 — 7d after suspicion
    filed_at_utc: Optional[str]        # populated on SUBMITTED
    acknowledged_at_utc: Optional[str]
    investigation_opened_at_utc: Optional[str]
    investigation_closed_at_utc: Optional[str]
    investigation_outcome: str         # "" | "CLOSED_NO_ACTION" | "CLOSED_REFERRED" | "CLOSED_PROSECUTION"
    status: FilingStatus
    provenance: AlertProvenance
    submission_method: str             # honest deferral surface
    filed_by_user: str = ""
    transition_log: Tuple[Mapping[str, Any], ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filing_id": self.filing_id,
            "report_type": self.report_type.value,
            "subject": {
                "subject_id": self.subject.subject_id,
                "legal_name": self.subject.legal_name,
                "subject_kind": self.subject.subject_kind,
                "nat_id": self.subject.nat_id,
                "nationality": self.subject.nationality,
                "date_of_birth_or_incorporation":
                    self.subject.date_of_birth_or_incorporation,
                "occupation_or_industry":
                    self.subject.occupation_or_industry,
                "address": self.subject.address,
            },
            "transactions": [
                {
                    "txn_id": t.txn_id,
                    "txn_date": t.txn_date,
                    "amount_kes": str(t.amount_kes),
                    "txn_type": t.txn_type,
                    "counterparty_name": t.counterparty_name,
                    "counterparty_country": t.counterparty_country,
                    "description": t.description,
                }
                for t in self.transactions
            ],
            "suspicion_narrative": self.suspicion_narrative,
            "risk_indicators": list(self.risk_indicators),
            "suspicion_formed_at_utc": self.suspicion_formed_at_utc,
            "filing_deadline_utc": self.filing_deadline_utc,
            "filed_at_utc": self.filed_at_utc,
            "acknowledged_at_utc": self.acknowledged_at_utc,
            "investigation_opened_at_utc": (
                self.investigation_opened_at_utc),
            "investigation_closed_at_utc": (
                self.investigation_closed_at_utc),
            "investigation_outcome": self.investigation_outcome,
            "status": self.status.value,
            "provenance": {
                "monitoring_engine": self.provenance.monitoring_engine,
                "customer_id": self.provenance.customer_id,
                "monitored_at_utc": self.provenance.monitored_at_utc,
                "rule_ids": list(self.provenance.rule_ids),
                "rule_names": list(self.provenance.rule_names),
                "severity": self.provenance.severity,
                "escalation_reason": self.provenance.escalation_reason,
            },
            "submission_method": self.submission_method,
            "filed_by_user": self.filed_by_user,
            "transition_log": [dict(t) for t in self.transition_log],
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SarFilingEngine:
    """SAR/STR Filing Engine.

    Workflow:
        engine = SarFilingEngine()
        # Build a draft from upstream AmlMonitoringResult + applicant data
        filing = engine.build_filing(
            monitoring_result=aml_result,        # from ENH-193
            subject=subject_identity,            # from ENH-191 KYC data
            transactions=transaction_evidence,   # from upstream transaction stream
            suspicion_narrative="...",           # operator-supplied
        )
        # Returns DRAFT filing with auto-computed deadline

        # Operator reviews + submits
        engine.transition(filing.filing_id, FilingStatus.SUBMITTED,
                            user="compliance_officer")
        # Returns updated filing or rejection

        # FRC acknowledges
        engine.transition(filing_id, FilingStatus.ACKNOWLEDGED, user="...")
        # ... etc through the lifecycle
    """

    SUBMISSION_METHOD_NOTE = (
        "MANUAL_PORTAL — FRC has no public programmatic submission API. "
        "Operator exports the filing via to_dict() and uploads via FRC's "
        "secure web portal or encrypted email. v10.163 ships build+track+"
        "export capability; wire-level submission is a future increment "
        "if/when FRC publishes a submission API.")

    def __init__(self) -> None:
        self._filings: Dict[str, FilingPayload] = {}
        self._next_id = 1

    # ------------------------------------------------------------------
    # Build — DRAFT a new filing
    # ------------------------------------------------------------------

    def build_filing(
        self,
        monitoring_result: Any,  # AmlMonitoringResult from ENH-193
        subject: SubjectIdentity,
        transactions: List[TransactionEvidence],
        suspicion_narrative: str,
        report_type: Optional[ReportType] = None,
        suspicion_formed_at_utc: Optional[str] = None,
    ) -> FilingPayload:
        """Build a DRAFT SAR/STR filing from upstream monitoring data.

        Args:
          monitoring_result: AmlMonitoringResult from ENH-193. The
            engine reads .customer_id, .tiered_alerts, .monitored_at_utc
            for provenance.
          subject: SubjectIdentity for the customer being reported.
          transactions: List of TransactionEvidence cited in the report.
            For pure SARs (behavioural patterns with no specific
            transactions), pass [].
          suspicion_narrative: Free-text operator-written explanation
            of why this is suspicious. POCAMLA + FATF require a
            narrative; cannot be empty.
          report_type: Override SAR/STR auto-detection. If None,
            engine infers from whether transactions list is empty
            (SAR) or non-empty (STR).
          suspicion_formed_at_utc: ISO timestamp. If None, defaults to
            monitoring_result.monitored_at_utc — the time the
            engine first flagged the activity.
        """
        if not suspicion_narrative or not suspicion_narrative.strip():
            raise ValueError(
                "suspicion_narrative is mandatory per POCAMLA §44 + "
                "FATF Rec 20 — operator-written explanation required")

        if not subject.subject_id or not subject.legal_name:
            raise ValueError(
                "subject must have subject_id and legal_name")

        # Default report type from whether transactions are cited
        if report_type is None:
            report_type = (ReportType.STR
                            if transactions
                            else ReportType.SAR)

        # Suspicion formation time defaults to upstream monitoring time
        if suspicion_formed_at_utc is None:
            suspicion_formed_at_utc = getattr(
                monitoring_result, "monitored_at_utc",
                datetime.now(timezone.utc).isoformat())

        # Compute POCAMLA §44 deadline — 7 days
        try:
            formed_dt = datetime.fromisoformat(
                suspicion_formed_at_utc.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            formed_dt = datetime.now(timezone.utc)
            suspicion_formed_at_utc = formed_dt.isoformat()
        deadline_dt = formed_dt + timedelta(
            days=POCAMLA_FILING_DEADLINE_DAYS)

        # Pull provenance from monitoring result
        rule_ids = []
        rule_names = []
        severity = "UNKNOWN"
        escalation_reason = ""
        if hasattr(monitoring_result, "tiered_alerts"):
            for ta in monitoring_result.tiered_alerts:
                rule_ids.append(getattr(ta, "rule_id", ""))
                rule_names.append(getattr(ta, "rule_name", ""))
                # Pick highest severity
                ta_sev = getattr(ta, "tier_aware_severity", None)
                if ta_sev:
                    sev_str = (ta_sev.value if hasattr(ta_sev, "value")
                               else str(ta_sev))
                    if self._severity_rank(sev_str) > \
                            self._severity_rank(severity):
                        severity = sev_str
                # First non-empty escalation reason wins
                er = getattr(ta, "escalation_reason", "")
                if er and not escalation_reason:
                    escalation_reason = er

        provenance = AlertProvenance(
            monitoring_engine="ENH-193 AmlMonitoringEngine",
            customer_id=getattr(monitoring_result, "customer_id",
                                  subject.subject_id),
            monitored_at_utc=getattr(monitoring_result,
                                        "monitored_at_utc",
                                        suspicion_formed_at_utc),
            rule_ids=tuple(rule_ids),
            rule_names=tuple(rule_names),
            severity=severity,
            escalation_reason=escalation_reason,
        )

        filing_id = f"SAR-{self._next_id:06d}"
        self._next_id += 1

        # Risk indicators — composite from rule_ids + tier
        risk_indicators: List[str] = list(rule_ids)
        tier = getattr(monitoring_result, "customer_tier", None)
        if tier:
            risk_indicators.append(f"TIER_{tier}")
        if escalation_reason and "edd_tier" in escalation_reason:
            risk_indicators.append("EDD_ESCALATION")

        filing = FilingPayload(
            filing_id=filing_id,
            report_type=report_type,
            subject=subject,
            transactions=tuple(transactions),
            suspicion_narrative=suspicion_narrative.strip(),
            risk_indicators=tuple(risk_indicators),
            suspicion_formed_at_utc=suspicion_formed_at_utc,
            filing_deadline_utc=deadline_dt.isoformat(),
            filed_at_utc=None,
            acknowledged_at_utc=None,
            investigation_opened_at_utc=None,
            investigation_closed_at_utc=None,
            investigation_outcome="",
            status=FilingStatus.DRAFT,
            provenance=provenance,
            submission_method=self.SUBMISSION_METHOD_NOTE,
            filed_by_user="",
            transition_log=(
                {"to_status": "DRAFT",
                 "at_utc": datetime.now(timezone.utc).isoformat(),
                 "user": "system",
                 "reason": "filing built from upstream "
                             "AmlMonitoringResult"},
            ),
            meta={
                "engine_version": "ENH-194-v10.163",
                "pocamla_deadline_days": POCAMLA_FILING_DEADLINE_DAYS,
            },
        )
        self._filings[filing_id] = filing
        return filing

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        filing_id: str,
        new_status: FilingStatus,
        user: str,
        reason: str = "",
        investigation_outcome: str = "",
    ) -> Tuple[TransitionOutcome, Optional[FilingPayload]]:
        """Move a filing through its lifecycle. Returns the outcome
        and the updated filing (or None on rejection)."""
        if filing_id not in self._filings:
            return (TransitionOutcome.REJECTED_REPORT_NOT_FOUND, None)

        current = self._filings[filing_id]
        if new_status not in ALLOWED_TRANSITIONS.get(current.status, ()):
            return (TransitionOutcome.REJECTED_INVALID_TRANSITION,
                    current)

        # WITHDRAWN requires a reason (audit trail)
        if new_status == FilingStatus.WITHDRAWN and not reason.strip():
            return (TransitionOutcome.REJECTED_REASON_REQUIRED, current)

        now_utc = datetime.now(timezone.utc).isoformat()
        new_log_entry = {
            "to_status": new_status.value,
            "at_utc": now_utc,
            "user": user,
            "reason": reason,
        }

        # Build the updated filing — frozen dataclasses force a new instance
        kwargs = {
            "filing_id": current.filing_id,
            "report_type": current.report_type,
            "subject": current.subject,
            "transactions": current.transactions,
            "suspicion_narrative": current.suspicion_narrative,
            "risk_indicators": current.risk_indicators,
            "suspicion_formed_at_utc": current.suspicion_formed_at_utc,
            "filing_deadline_utc": current.filing_deadline_utc,
            "filed_at_utc": current.filed_at_utc,
            "acknowledged_at_utc": current.acknowledged_at_utc,
            "investigation_opened_at_utc": (
                current.investigation_opened_at_utc),
            "investigation_closed_at_utc": (
                current.investigation_closed_at_utc),
            "investigation_outcome": current.investigation_outcome,
            "status": new_status,
            "provenance": current.provenance,
            "submission_method": current.submission_method,
            "filed_by_user": current.filed_by_user,
            "transition_log": current.transition_log + (new_log_entry,),
            "meta": current.meta,
        }

        # Per-state timestamp updates
        if new_status == FilingStatus.SUBMITTED:
            kwargs["filed_at_utc"] = now_utc
            kwargs["filed_by_user"] = user
        elif new_status == FilingStatus.ACKNOWLEDGED:
            kwargs["acknowledged_at_utc"] = now_utc
        elif new_status == FilingStatus.INVESTIGATION_OPENED:
            kwargs["investigation_opened_at_utc"] = now_utc
        elif new_status == FilingStatus.INVESTIGATION_CLOSED:
            kwargs["investigation_closed_at_utc"] = now_utc
            kwargs["investigation_outcome"] = (
                investigation_outcome or "CLOSED_NO_ACTION")

        updated = FilingPayload(**kwargs)
        self._filings[filing_id] = updated
        return (TransitionOutcome.OK, updated)

    # ------------------------------------------------------------------
    # Retrieval / portfolio summary
    # ------------------------------------------------------------------

    def filing_by_id(self, filing_id: str) -> FilingPayload:
        if filing_id not in self._filings:
            raise KeyError(f"filing not found: {filing_id}")
        return self._filings[filing_id]

    def all_filings(self) -> Tuple[FilingPayload, ...]:
        return tuple(self._filings.values())

    def overdue_filings(self) -> Tuple[FilingPayload, ...]:
        """Filings still in DRAFT past the POCAMLA §44 7-day deadline.

        These are real regulatory exposure for the bank — operator-
        actionable list.
        """
        now_utc = datetime.now(timezone.utc).isoformat()
        return tuple(
            f for f in self._filings.values()
            if f.status == FilingStatus.DRAFT
            and f.filing_deadline_utc < now_utc)

    def board_summary(self) -> Dict[str, Any]:
        filings = list(self._filings.values())
        n_total = len(filings)
        status_counts: Dict[str, int] = {}
        type_counts: Dict[str, int] = {ReportType.SAR.value: 0,
                                          ReportType.STR.value: 0}
        for f in filings:
            status_counts[f.status.value] = (
                status_counts.get(f.status.value, 0) + 1)
            type_counts[f.report_type.value] += 1

        n_overdue = len(self.overdue_filings())
        n_submitted = status_counts.get(FilingStatus.SUBMITTED.value, 0)
        n_acknowledged = status_counts.get(
            FilingStatus.ACKNOWLEDGED.value, 0)
        n_investigation_open = status_counts.get(
            FilingStatus.INVESTIGATION_OPENED.value, 0)
        n_closed = status_counts.get(
            FilingStatus.INVESTIGATION_CLOSED.value, 0)

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-194 SarFilingEngine",
            "n_filings_total": n_total,
            "n_overdue_drafts": n_overdue,
            "n_submitted": n_submitted,
            "n_acknowledged_by_frc": n_acknowledged,
            "n_under_investigation": n_investigation_open,
            "n_investigation_closed": n_closed,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "submission_method": self.SUBMISSION_METHOD_NOTE,
            "regulatory_basis": (
                "Kenya POCAMLA §44 (7-day deadline), FATF Rec 20, "
                "FRC Reporting Format, CBK PG/15"),
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _severity_rank(s: str) -> int:
        return {"LOW": 1, "MEDIUM": 2, "HIGH": 3,
                  "CRITICAL": 4}.get(s, 0)
