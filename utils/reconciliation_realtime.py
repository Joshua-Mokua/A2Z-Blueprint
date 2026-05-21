"""utils/reconciliation_realtime.py — v10.21 Phase 2 batch 3 (RMS arc batch 4).

╔════════════════════════════════════════════════════════════════════════╗
║  RECONCILIATION REALTIME — DASHBOARD + AI LEARNING + CONTINUOUS +     ║
║                              AUDIT CERTIFICATION + SUB-MONTHLY         ║
╠════════════════════════════════════════════════════════════════════════╣
║  Risk class: Cat A (certification + sign-off impacts financial close;  ║
║              continuous mode affects intraday capital + liquidity)     ║
║  Implements 5 of 17 RMS standards from registry — final RMS batch:      ║
║    ENH-184:     Real-time Reconciliation Dashboard                      ║
║    ENH-188:     AI-Powered Reconciliation Learning                      ║
║    ENH-189:     Continuous/Real-time Reconciliation                     ║
║    ENH-190:     Reconciliation Audit & Certification                    ║
║    ENH-RMS-R7:  Sub-Monthly Daily Reconciliation Support                ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    Kenya Banking Act §39 — books and records integrity                 ║
║    CBK Prudential Guideline CBK/PG/02 — operational risk              ║
║    CBK CRMF April 2021 §6 — internal controls + reconciliation        ║
║    CBK CRMF §6.5 — daily reconciliation cadence requirement           ║
║    SOX §404 — internal control over financial reporting               ║
║    SOX §302 — corporate responsibility for financial reports          ║
║    PCAOB AS 2110 — risk assessment + walkthroughs                     ║
║    COSO ERM — three lines of defense                                  ║
║    Basel BCBS 239 §11 — completeness, timeliness, adaptability        ║
║    Basel BCBS 239 §12 — accuracy and integrity                        ║
║    EU AI Act Art 10 — AI training data quality                         ║
║    EU AI Act Art 12 — record-keeping for high-risk systems            ║
║    Kenya Data Protection Act 2019 §28 — retention                      ║
╠════════════════════════════════════════════════════════════════════════╣
║  Composes with v10.18 (matching) + v10.19 (workflow + memory + guards) ║
║                  + v10.20 (CBK/Nostro/IC/KEPSS specialized).            ║
║                                                                         ║
║  Honesty Rule 7: ML learning is callable hook. No fabricated learned   ║
║  improvements without injected feature_extractor + training_callable.  ║
║  Honesty Rule 1: certification sign-offs are explicit + immutable      ║
║  audit-trail entries — never silent override.                           ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, getcontext
from enum import Enum
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "AI learning loop is via callable hook (Rule 7). Feature extraction + "
    "model training are per-deployment. Default behavior records feedback "
    "for downstream training without making any model claims.")


# ════════════════════════════════════════════════════════════════════════
# Reconciliation cadence (ENH-RMS-R7 + ENH-189)
# ════════════════════════════════════════════════════════════════════════

class ReconCadence(Enum):
    """How often reconciliation runs.

    Per CBK CRMF §6.5: daily reconciliation cadence is the minimum
    expected for material accounts. Sub-monthly (daily / intra-day) is
    the regulatory direction; monthly-only is no longer adequate.
    """
    REAL_TIME = "REAL_TIME"          # streaming, latency < 1 sec
    MINUTELY = "MINUTELY"            # every minute
    HOURLY = "HOURLY"                # every hour
    INTRADAY = "INTRADAY"            # multiple times per day
    DAILY = "DAILY"                  # end-of-day
    WEEKLY = "WEEKLY"                # end-of-week
    MONTHLY = "MONTHLY"              # end-of-month
    AD_HOC = "AD_HOC"


# CBK CRMF cadence policy — minimum acceptable per account materiality
CADENCE_POLICY: Mapping[str, ReconCadence] = {
    "GL_TO_CBS": ReconCadence.DAILY,
    "NOSTRO": ReconCadence.DAILY,           # CBK CRMF §6.4 + §6.5
    "VOSTRO": ReconCadence.DAILY,
    "INTERBANK_KEPSS": ReconCadence.REAL_TIME,
    "PESALINK": ReconCadence.REAL_TIME,
    "MOBILE_MONEY": ReconCadence.HOURLY,
    "CARD_NETWORK": ReconCadence.DAILY,
    "INTERCOMPANY": ReconCadence.DAILY,
    "SUSPENSE": ReconCadence.DAILY,
    "REGULATORY_RETURNS": ReconCadence.DAILY,
}


def is_cadence_compliant(
    *, account_type: str, actual_cadence: ReconCadence,
) -> bool:
    """Check whether actual cadence meets the policy minimum.

    Cadence ordering for compliance check: REAL_TIME > MINUTELY > HOURLY
    > INTRADAY > DAILY > WEEKLY > MONTHLY. Faster cadence is always
    compliant if policy allows slower.
    """
    cadence_order = {
        ReconCadence.REAL_TIME: 0,
        ReconCadence.MINUTELY: 1,
        ReconCadence.HOURLY: 2,
        ReconCadence.INTRADAY: 3,
        ReconCadence.DAILY: 4,
        ReconCadence.WEEKLY: 5,
        ReconCadence.MONTHLY: 6,
        ReconCadence.AD_HOC: 7,
    }
    required = CADENCE_POLICY.get(account_type, ReconCadence.DAILY)
    return cadence_order[actual_cadence] <= cadence_order[required]


# ════════════════════════════════════════════════════════════════════════
# Continuous reconciliation (ENH-189)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class StreamingWatermark:
    """Watermark for continuous/streaming reconciliation.

    Tracks how far through the source stream we've processed. Items with
    timestamp ≤ watermark are committed; later-arriving data triggers
    backfill.
    """
    source_id: str
    watermark_utc: str               # ISO-8601 — high-watermark timestamp
    last_event_id: Optional[str] = None
    n_events_processed: int = 0
    notes: str = ""


@dataclass(frozen=True)
class LateArrivalRecord:
    """A record arriving with timestamp older than current watermark."""
    record_id: str
    source_id: str
    record_timestamp_utc: str
    received_at_utc: str
    watermark_at_receipt_utc: str
    lateness_seconds: int
    notes: str = ""

    def is_acceptable_lag(
        self, *, max_lateness_seconds: int = 3600,
    ) -> bool:
        return self.lateness_seconds <= max_lateness_seconds


def detect_late_arrival(
    *,
    record_id: str,
    source_id: str,
    record_timestamp_utc: str,
    received_at_utc: str,
    watermark: StreamingWatermark,
) -> Optional[LateArrivalRecord]:
    """Detect if a record is late vs the current watermark."""
    try:
        rec_ts = datetime.fromisoformat(
            record_timestamp_utc.replace("Z", "+00:00"))
        wm_ts = datetime.fromisoformat(
            watermark.watermark_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    if rec_ts >= wm_ts:
        return None    # not late
    received_dt = datetime.fromisoformat(
        received_at_utc.replace("Z", "+00:00"))
    lateness = int((received_dt - rec_ts).total_seconds())
    return LateArrivalRecord(
        record_id=record_id, source_id=source_id,
        record_timestamp_utc=record_timestamp_utc,
        received_at_utc=received_at_utc,
        watermark_at_receipt_utc=watermark.watermark_utc,
        lateness_seconds=lateness,
        notes=f"received {lateness}s after record timestamp")


# ════════════════════════════════════════════════════════════════════════
# AI-powered learning (ENH-188)
# ════════════════════════════════════════════════════════════════════════

class FeedbackOutcome(Enum):
    """Human-confirmed outcome on a proposed match (training signal)."""
    CONFIRMED_MATCH = "CONFIRMED_MATCH"
    REJECTED_NOT_A_MATCH = "REJECTED_NOT_A_MATCH"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class LearningFeedback:
    """One feedback record produced by a human reviewer.

    Per ENH-188 the engine collects feedback during operations.
    Downstream training (ML model fitting, threshold recalibration) is
    per-deployment via the train_callable hook.
    """
    feedback_id: str
    proposed_pair_id: str
    source_transaction_id: str
    target_transaction_id: str
    proposed_match_score: Decimal
    proposed_algorithm: str
    actual_outcome: FeedbackOutcome
    reviewer_id: str
    timestamp: str                    # ISO-8601
    notes: str = ""


@dataclass(frozen=True)
class LearningStats:
    """Aggregate stats over collected feedback — used to monitor model fit."""
    n_feedback: int
    n_confirmed: int
    n_rejected: int
    n_uncertain: int
    confirmation_rate_pct: Decimal
    rejection_rate_pct: Decimal
    notes: str = ""


class LearningStore:
    """Collects feedback for downstream training.

    Per Rule 7: this engine does NOT do the actual model training. It
    captures + organizes feedback. The caller wires `train_callable` to
    actually fit a model. Without training callable, the store still
    surfaces stats (no fabricated improvements claimed).
    """

    def __init__(
        self, *,
        train_callable: Optional[
            Callable[[Sequence[LearningFeedback]], object]] = None,
    ):
        self._feedback: List[LearningFeedback] = []
        self.train_callable = train_callable

    def record_feedback(self, fb: LearningFeedback) -> None:
        self._feedback.append(fb)

    def feedback_count(self) -> int:
        return len(self._feedback)

    def stats(self) -> LearningStats:
        n = len(self._feedback)
        if n == 0:
            return LearningStats(
                n_feedback=0, n_confirmed=0, n_rejected=0, n_uncertain=0,
                confirmation_rate_pct=Decimal("0"),
                rejection_rate_pct=Decimal("0"))
        n_conf = sum(
            1 for f in self._feedback
            if f.actual_outcome == FeedbackOutcome.CONFIRMED_MATCH)
        n_rej = sum(
            1 for f in self._feedback
            if f.actual_outcome == FeedbackOutcome.REJECTED_NOT_A_MATCH)
        n_unc = sum(
            1 for f in self._feedback
            if f.actual_outcome == FeedbackOutcome.UNCERTAIN)
        return LearningStats(
            n_feedback=n, n_confirmed=n_conf, n_rejected=n_rej,
            n_uncertain=n_unc,
            confirmation_rate_pct=(
                Decimal(n_conf) / Decimal(n) * Decimal("100")),
            rejection_rate_pct=(
                Decimal(n_rej) / Decimal(n) * Decimal("100")))

    def trigger_training(self) -> Tuple[bool, str]:
        """Fire the injected train_callable. Honest about what happened."""
        if self.train_callable is None:
            return (
                False,
                "no train_callable injected — Rule 7 honesty: "
                "no model trained, feedback stored for later")
        try:
            self.train_callable(tuple(self._feedback))
            return (True, f"training fired with {len(self._feedback)} feedbacks")
        except Exception as e:
            return (
                False,
                f"training failed: {type(e).__name__}: {e}")


# ════════════════════════════════════════════════════════════════════════
# Audit certification (ENH-190)
# ════════════════════════════════════════════════════════════════════════

class CertifierRole(Enum):
    """Roles that can sign off reconciliation."""
    PREPARER = "PREPARER"            # operations user
    REVIEWER = "REVIEWER"            # team lead
    APPROVER = "APPROVER"            # finance manager
    CFO = "CFO"
    INTERNAL_AUDIT = "INTERNAL_AUDIT"
    EXTERNAL_AUDIT = "EXTERNAL_AUDIT"


class CertificationStatus(Enum):
    DRAFT = "DRAFT"
    PREPARED = "PREPARED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"
    SIGNED_OFF = "SIGNED_OFF"
    REJECTED = "REJECTED"
    AMENDED = "AMENDED"


# Allowed transitions — preparer → reviewer → approver → signed-off
ALLOWED_CERT_TRANSITIONS: Mapping[
    CertificationStatus, Tuple[CertificationStatus, ...]] = {
    CertificationStatus.DRAFT: (CertificationStatus.PREPARED,),
    CertificationStatus.PREPARED: (
        CertificationStatus.REVIEWED, CertificationStatus.REJECTED),
    CertificationStatus.REVIEWED: (
        CertificationStatus.APPROVED, CertificationStatus.REJECTED),
    CertificationStatus.APPROVED: (
        CertificationStatus.SIGNED_OFF, CertificationStatus.REJECTED),
    CertificationStatus.REJECTED: (CertificationStatus.AMENDED,),
    CertificationStatus.AMENDED: (CertificationStatus.PREPARED,),
    CertificationStatus.SIGNED_OFF: (),    # terminal
}


def is_valid_cert_transition(
    from_status: CertificationStatus,
    to_status: CertificationStatus,
) -> bool:
    return to_status in ALLOWED_CERT_TRANSITIONS.get(from_status, ())


@dataclass(frozen=True)
class CertificationSignoff:
    """One sign-off action by a certifier."""
    signoff_id: str
    certifier_user_id: str
    certifier_role: CertifierRole
    timestamp: str                    # ISO-8601
    decision: str                     # APPROVED / REJECTED / AMENDED
    notes: str = ""


@dataclass(frozen=True)
class AuditTrailEntry:
    """Immutable audit record — what changed, by whom, when."""
    entry_id: str
    event_type: str                   # e.g., MATCH, EXCEPTION_RESOLVE, SIGNOFF
    actor_user_id: str
    actor_role: str
    timestamp: str
    target_object_id: str             # e.g., reconciliation period or exception
    before_state: str = ""
    after_state: str = ""
    notes: str = ""


@dataclass(frozen=True)
class CertificationRecord:
    """One reconciliation period's certification.

    Tracks status + chain of sign-offs + audit trail entries.
    """
    cert_id: str
    period_label: str                 # e.g., "2026-04 monthly", "2026-04-23 daily"
    cadence: ReconCadence
    account_type: str                  # what was reconciled
    status: CertificationStatus
    signoffs: Tuple[CertificationSignoff, ...] = ()
    audit_entries: Tuple[AuditTrailEntry, ...] = ()
    n_exceptions_at_signoff: int = 0
    n_unresolved_at_signoff: int = 0
    notes: str = ""

    def has_role_signoff(self, role: CertifierRole) -> bool:
        return any(s.certifier_role == role for s in self.signoffs)

    def is_dual_approved(self) -> bool:
        """At minimum: PREPARER + REVIEWER (2 distinct people)."""
        roles = {s.certifier_role for s in self.signoffs}
        users = {s.certifier_user_id for s in self.signoffs}
        return (CertifierRole.PREPARER in roles
                  and CertifierRole.REVIEWER in roles
                  and len(users) >= 2)


# ════════════════════════════════════════════════════════════════════════
# Real-time dashboard (ENH-184)
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DashboardKPI:
    """One KPI metric for the recon dashboard."""
    kpi_name: str
    current_value: Decimal
    target_value: Optional[Decimal] = None
    threshold_amber: Optional[Decimal] = None
    threshold_red: Optional[Decimal] = None
    higher_is_better: bool = True
    unit: str = ""
    notes: str = ""

    def status_color(self) -> str:
        """Green / Amber / Red based on thresholds + direction."""
        if self.threshold_red is None and self.threshold_amber is None:
            return "GREEN"
        if self.higher_is_better:
            if (self.threshold_red is not None
                    and self.current_value < self.threshold_red):
                return "RED"
            if (self.threshold_amber is not None
                    and self.current_value < self.threshold_amber):
                return "AMBER"
            return "GREEN"
        # lower is better
        if (self.threshold_red is not None
                and self.current_value > self.threshold_red):
            return "RED"
        if (self.threshold_amber is not None
                and self.current_value > self.threshold_amber):
            return "AMBER"
        return "GREEN"


@dataclass(frozen=True)
class DashboardSnapshot:
    """A complete dashboard snapshot at a point in time."""
    snapshot_at_utc: str               # ISO-8601
    kpis: Tuple[DashboardKPI, ...]
    n_open_exceptions: int = 0
    n_sla_breaches: int = 0
    n_critical_alerts: int = 0
    auto_match_rate_pct: Decimal = Decimal("0")
    notes: str = ""


def build_dashboard_snapshot(
    *,
    snapshot_at_utc: str,
    auto_match_rate_pct: Decimal,
    n_open_exceptions: int,
    n_sla_breaches: int,
    n_critical_alerts: int,
    target_match_rate_pct: Decimal = Decimal("90"),
) -> DashboardSnapshot:
    """Build a DashboardSnapshot from key metrics."""
    kpis = (
        DashboardKPI(
            kpi_name="Auto-Match Rate",
            current_value=auto_match_rate_pct,
            target_value=target_match_rate_pct,
            threshold_amber=target_match_rate_pct - Decimal("10"),    # 80
            threshold_red=target_match_rate_pct - Decimal("20"),       # 70
            higher_is_better=True, unit="%"),
        DashboardKPI(
            kpi_name="Open Exceptions",
            current_value=Decimal(n_open_exceptions),
            threshold_amber=Decimal("100"),
            threshold_red=Decimal("500"),
            higher_is_better=False, unit="count"),
        DashboardKPI(
            kpi_name="SLA Breaches",
            current_value=Decimal(n_sla_breaches),
            threshold_amber=Decimal("5"),
            threshold_red=Decimal("20"),
            higher_is_better=False, unit="count"),
        DashboardKPI(
            kpi_name="Critical Alerts",
            current_value=Decimal(n_critical_alerts),
            threshold_amber=Decimal("0"),
            threshold_red=Decimal("3"),
            higher_is_better=False, unit="count"),
    )
    return DashboardSnapshot(
        snapshot_at_utc=snapshot_at_utc, kpis=kpis,
        n_open_exceptions=n_open_exceptions,
        n_sla_breaches=n_sla_breaches,
        n_critical_alerts=n_critical_alerts,
        auto_match_rate_pct=auto_match_rate_pct,
        notes=f"snapshot at {snapshot_at_utc}")


# ════════════════════════════════════════════════════════════════════════
# Engine — orchestrator for v10.21 surfaces
# ════════════════════════════════════════════════════════════════════════

class ReconciliationRealtimeEngine:
    """Aggregator: dashboard + learning + continuous + audit certification."""

    def __init__(
        self, *,
        entity_name: str = "Ecobank Kenya",
        learning_store: Optional[LearningStore] = None,
    ):
        self.entity_name = entity_name
        self.learning_store = learning_store or LearningStore()
        self._watermarks: Dict[str, StreamingWatermark] = {}
        self._late_arrivals: List[LateArrivalRecord] = []
        self._certifications: Dict[str, CertificationRecord] = {}
        self._snapshots: List[DashboardSnapshot] = []

    # ── Dashboard (ENH-184) ────────────────────────────────────────────
    def add_snapshot(self, snap: DashboardSnapshot) -> None:
        self._snapshots.append(snap)

    def latest_snapshot(self) -> Optional[DashboardSnapshot]:
        return self._snapshots[-1] if self._snapshots else None

    def snapshots_since(
        self, *, since_utc: str,
    ) -> Tuple[DashboardSnapshot, ...]:
        return tuple(
            s for s in self._snapshots
            if s.snapshot_at_utc >= since_utc)

    # ── Continuous reconciliation (ENH-189) ───────────────────────────
    def update_watermark(self, wm: StreamingWatermark) -> None:
        self._watermarks[wm.source_id] = wm

    def get_watermark(
        self, source_id: str) -> Optional[StreamingWatermark]:
        return self._watermarks.get(source_id)

    def record_late_arrival(self, late: LateArrivalRecord) -> None:
        self._late_arrivals.append(late)

    def excessive_late_arrivals(
        self, *, max_lateness_seconds: int = 3600,
    ) -> Tuple[LateArrivalRecord, ...]:
        return tuple(
            la for la in self._late_arrivals
            if not la.is_acceptable_lag(
                max_lateness_seconds=max_lateness_seconds))

    # ── Sub-monthly cadence (ENH-RMS-R7) ──────────────────────────────
    def check_cadence_compliance(
        self, *, account_type: str, actual_cadence: ReconCadence,
    ) -> Tuple[bool, str]:
        """Returns (is_compliant, reason)."""
        compliant = is_cadence_compliant(
            account_type=account_type, actual_cadence=actual_cadence)
        required = CADENCE_POLICY.get(account_type, ReconCadence.DAILY)
        return (
            compliant,
            (f"actual {actual_cadence.value} meets policy minimum "
              f"{required.value}" if compliant
              else f"actual {actual_cadence.value} below policy "
              f"minimum {required.value} per CBK CRMF §6.5"))

    # ── Certification (ENH-190) ────────────────────────────────────────
    def register_certification(self, c: CertificationRecord) -> None:
        if c.cert_id in self._certifications:
            raise ValueError(f"certification {c.cert_id} already exists")
        self._certifications[c.cert_id] = c

    def transition_certification(
        self, *, cert_id: str, to_status: CertificationStatus,
        actor_user_id: str, actor_role: CertifierRole, timestamp: str,
        notes: str = "",
    ) -> CertificationRecord:
        if cert_id not in self._certifications:
            raise KeyError(f"certification {cert_id} not found")
        existing = self._certifications[cert_id]
        if not is_valid_cert_transition(existing.status, to_status):
            allowed = ALLOWED_CERT_TRANSITIONS.get(existing.status, ())
            raise ValueError(
                f"invalid certification transition {existing.status.value}"
                f" → {to_status.value}; allowed: {[s.value for s in allowed]}")

        signoff = CertificationSignoff(
            signoff_id=f"SO-{len(existing.signoffs) + 1:04d}",
            certifier_user_id=actor_user_id,
            certifier_role=actor_role,
            timestamp=timestamp,
            decision=to_status.value,
            notes=notes)
        audit = AuditTrailEntry(
            entry_id=f"AT-{len(existing.audit_entries) + 1:04d}",
            event_type="CERT_TRANSITION",
            actor_user_id=actor_user_id, actor_role=actor_role.value,
            timestamp=timestamp,
            target_object_id=cert_id,
            before_state=existing.status.value,
            after_state=to_status.value,
            notes=notes)
        updated = CertificationRecord(
            cert_id=existing.cert_id,
            period_label=existing.period_label,
            cadence=existing.cadence,
            account_type=existing.account_type,
            status=to_status,
            signoffs=existing.signoffs + (signoff,),
            audit_entries=existing.audit_entries + (audit,),
            n_exceptions_at_signoff=existing.n_exceptions_at_signoff,
            n_unresolved_at_signoff=existing.n_unresolved_at_signoff,
            notes=existing.notes)
        self._certifications[cert_id] = updated
        return updated

    def get_certification(self, cert_id: str) -> CertificationRecord:
        if cert_id not in self._certifications:
            raise KeyError(f"certification {cert_id} not found")
        return self._certifications[cert_id]

    # ── Learning loop (ENH-188) ────────────────────────────────────────
    def record_learning_feedback(self, fb: LearningFeedback) -> None:
        self.learning_store.record_feedback(fb)

    def learning_stats(self) -> LearningStats:
        return self.learning_store.stats()

    def trigger_learning(self) -> Tuple[bool, str]:
        return self.learning_store.trigger_training()

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, object]:
        latest = self.latest_snapshot()
        n_signed_off = sum(
            1 for c in self._certifications.values()
            if c.status == CertificationStatus.SIGNED_OFF)
        n_rejected = sum(
            1 for c in self._certifications.values()
            if c.status == CertificationStatus.REJECTED)

        return {
            "entity": self.entity_name,
            "n_snapshots": len(self._snapshots),
            "latest_snapshot_at": (
                latest.snapshot_at_utc if latest else None),
            "latest_match_rate_pct": (
                latest.auto_match_rate_pct if latest else None),
            "n_late_arrivals": len(self._late_arrivals),
            "n_excessive_late": len(self.excessive_late_arrivals()),
            "n_certifications": len(self._certifications),
            "n_certifications_signed_off": n_signed_off,
            "n_certifications_rejected": n_rejected,
            "n_learning_feedback": self.learning_store.feedback_count(),
            "n_watermark_sources": len(self._watermarks),
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_cadence_policy_loaded():
    assert CADENCE_POLICY["NOSTRO"] == ReconCadence.DAILY
    assert CADENCE_POLICY["INTERBANK_KEPSS"] == ReconCadence.REAL_TIME


def _test_cadence_real_time_meets_daily():
    """REAL_TIME (faster) compliant vs DAILY policy."""
    assert is_cadence_compliant(
        account_type="NOSTRO", actual_cadence=ReconCadence.REAL_TIME)


def _test_cadence_monthly_fails_daily():
    assert not is_cadence_compliant(
        account_type="NOSTRO", actual_cadence=ReconCadence.MONTHLY)


def _test_cadence_daily_meets_daily():
    assert is_cadence_compliant(
        account_type="NOSTRO", actual_cadence=ReconCadence.DAILY)


def _test_cadence_unknown_account_defaults_daily():
    """Unknown account types default to DAILY policy."""
    assert is_cadence_compliant(
        account_type="UNKNOWN", actual_cadence=ReconCadence.HOURLY)
    assert not is_cadence_compliant(
        account_type="UNKNOWN", actual_cadence=ReconCadence.WEEKLY)


def _test_late_arrival_detected():
    wm = StreamingWatermark(
        source_id="GL", watermark_utc="2026-04-23T10:00:00Z")
    late = detect_late_arrival(
        record_id="R1", source_id="GL",
        record_timestamp_utc="2026-04-23T09:55:00Z",   # before watermark
        received_at_utc="2026-04-23T10:00:30Z",
        watermark=wm)
    assert late is not None
    # Lateness = 10:00:30 - 09:55:00 = 5min30s = 330s
    assert late.lateness_seconds == 330


def _test_late_arrival_not_late():
    wm = StreamingWatermark(
        source_id="GL", watermark_utc="2026-04-23T10:00:00Z")
    late = detect_late_arrival(
        record_id="R1", source_id="GL",
        record_timestamp_utc="2026-04-23T10:01:00Z",
        received_at_utc="2026-04-23T10:01:05Z", watermark=wm)
    assert late is None


def _test_late_arrival_acceptable_lag():
    late = LateArrivalRecord(
        record_id="R1", source_id="GL",
        record_timestamp_utc="2026-04-23T09:55:00Z",
        received_at_utc="2026-04-23T10:00:00Z",
        watermark_at_receipt_utc="2026-04-23T10:00:00Z",
        lateness_seconds=300)
    assert late.is_acceptable_lag(max_lateness_seconds=600)
    assert not late.is_acceptable_lag(max_lateness_seconds=200)


def _test_learning_store_records():
    ls = LearningStore()
    fb = LearningFeedback(
        feedback_id="F1", proposed_pair_id="PP1",
        source_transaction_id="S1", target_transaction_id="T1",
        proposed_match_score=Decimal("0.85"),
        proposed_algorithm="AMOUNT_DATE_TOLERANCE",
        actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
        reviewer_id="user_42", timestamp="2026-04-23T10:00:00Z")
    ls.record_feedback(fb)
    assert ls.feedback_count() == 1


def _test_learning_stats_aggregation():
    ls = LearningStore()
    for i in range(8):
        ls.record_feedback(LearningFeedback(
            feedback_id=f"F{i}", proposed_pair_id=f"P{i}",
            source_transaction_id=f"S{i}", target_transaction_id=f"T{i}",
            proposed_match_score=Decimal("0.8"),
            proposed_algorithm="X",
            actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
            reviewer_id="u", timestamp="t"))
    for i in range(2):
        ls.record_feedback(LearningFeedback(
            feedback_id=f"R{i}", proposed_pair_id=f"P{i+10}",
            source_transaction_id=f"S{i+10}", target_transaction_id=f"T{i+10}",
            proposed_match_score=Decimal("0.6"),
            proposed_algorithm="X",
            actual_outcome=FeedbackOutcome.REJECTED_NOT_A_MATCH,
            reviewer_id="u", timestamp="t"))
    stats = ls.stats()
    assert stats.n_feedback == 10
    assert stats.n_confirmed == 8
    assert stats.n_rejected == 2
    assert stats.confirmation_rate_pct == Decimal("80")


def _test_learning_no_train_callable_honest():
    """Rule 7: no train_callable → trigger_training returns honest signal."""
    ls = LearningStore()
    fired, msg = ls.trigger_training()
    assert not fired
    assert "no train_callable" in msg.lower()


def _test_learning_train_callable_invoked():
    calls = []
    def fake_trainer(feedbacks):
        calls.append(len(feedbacks))
    ls = LearningStore(train_callable=fake_trainer)
    ls.record_feedback(LearningFeedback(
        feedback_id="F1", proposed_pair_id="P1",
        source_transaction_id="S", target_transaction_id="T",
        proposed_match_score=Decimal("0.9"),
        proposed_algorithm="X",
        actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
        reviewer_id="u", timestamp="t"))
    fired, msg = ls.trigger_training()
    assert fired
    assert calls == [1]


def _test_learning_train_callable_failure_handled():
    def failing(_):
        raise RuntimeError("model fit failed")
    ls = LearningStore(train_callable=failing)
    fired, msg = ls.trigger_training()
    assert not fired
    assert "RuntimeError" in msg


def _test_cert_terminal_signed_off():
    assert ALLOWED_CERT_TRANSITIONS[CertificationStatus.SIGNED_OFF] == ()


def _test_cert_valid_path():
    """DRAFT → PREPARED → REVIEWED → APPROVED → SIGNED_OFF is valid."""
    path = [
        (CertificationStatus.DRAFT, CertificationStatus.PREPARED),
        (CertificationStatus.PREPARED, CertificationStatus.REVIEWED),
        (CertificationStatus.REVIEWED, CertificationStatus.APPROVED),
        (CertificationStatus.APPROVED, CertificationStatus.SIGNED_OFF),
    ]
    for f, t in path:
        assert is_valid_cert_transition(f, t)


def _test_cert_invalid_skip():
    """Cannot skip from DRAFT directly to SIGNED_OFF."""
    assert not is_valid_cert_transition(
        CertificationStatus.DRAFT, CertificationStatus.SIGNED_OFF)


def _test_dashboard_kpi_status_higher_is_better():
    # Match rate 75% with 80% amber threshold → AMBER
    k = DashboardKPI(
        kpi_name="Auto-Match", current_value=Decimal("75"),
        threshold_amber=Decimal("80"), threshold_red=Decimal("70"),
        higher_is_better=True, unit="%")
    assert k.status_color() == "AMBER"
    # 95% → GREEN
    k2 = DashboardKPI(
        kpi_name="Auto-Match", current_value=Decimal("95"),
        threshold_amber=Decimal("80"), threshold_red=Decimal("70"),
        higher_is_better=True, unit="%")
    assert k2.status_color() == "GREEN"
    # 65% → RED
    k3 = DashboardKPI(
        kpi_name="Auto-Match", current_value=Decimal("65"),
        threshold_amber=Decimal("80"), threshold_red=Decimal("70"),
        higher_is_better=True, unit="%")
    assert k3.status_color() == "RED"


def _test_dashboard_kpi_status_lower_is_better():
    # SLA breaches 8 with red=20, amber=5 → AMBER (8 > 5)
    k = DashboardKPI(
        kpi_name="SLA Breaches", current_value=Decimal("8"),
        threshold_amber=Decimal("5"), threshold_red=Decimal("20"),
        higher_is_better=False, unit="count")
    assert k.status_color() == "AMBER"
    # 25 → RED
    k2 = DashboardKPI(
        kpi_name="SLA Breaches", current_value=Decimal("25"),
        threshold_amber=Decimal("5"), threshold_red=Decimal("20"),
        higher_is_better=False, unit="count")
    assert k2.status_color() == "RED"


def _test_build_dashboard_snapshot():
    snap = build_dashboard_snapshot(
        snapshot_at_utc="2026-04-23T10:00:00Z",
        auto_match_rate_pct=Decimal("92"),
        n_open_exceptions=50,
        n_sla_breaches=2,
        n_critical_alerts=0)
    assert len(snap.kpis) == 4
    assert snap.auto_match_rate_pct == Decimal("92")


def _test_engine_certification_lifecycle():
    eng = ReconciliationRealtimeEngine()
    eng.register_certification(CertificationRecord(
        cert_id="CERT-2026-04",
        period_label="2026-04 monthly",
        cadence=ReconCadence.MONTHLY,
        account_type="GL_TO_CBS",
        status=CertificationStatus.DRAFT))
    eng.transition_certification(
        cert_id="CERT-2026-04",
        to_status=CertificationStatus.PREPARED,
        actor_user_id="alice", actor_role=CertifierRole.PREPARER,
        timestamp="t1")
    eng.transition_certification(
        cert_id="CERT-2026-04",
        to_status=CertificationStatus.REVIEWED,
        actor_user_id="bob", actor_role=CertifierRole.REVIEWER,
        timestamp="t2")
    cert = eng.get_certification("CERT-2026-04")
    assert cert.status == CertificationStatus.REVIEWED
    assert len(cert.signoffs) == 2
    assert len(cert.audit_entries) == 2
    assert cert.is_dual_approved()


def _test_engine_invalid_cert_transition_raises():
    eng = ReconciliationRealtimeEngine()
    eng.register_certification(CertificationRecord(
        cert_id="C1", period_label="p", cadence=ReconCadence.DAILY,
        account_type="X", status=CertificationStatus.DRAFT))
    try:
        eng.transition_certification(
            cert_id="C1", to_status=CertificationStatus.SIGNED_OFF,
            actor_user_id="x", actor_role=CertifierRole.CFO,
            timestamp="t")
        assert False
    except ValueError as e:
        assert "invalid certification transition" in str(e)


def _test_engine_check_cadence_compliance():
    eng = ReconciliationRealtimeEngine()
    ok, msg = eng.check_cadence_compliance(
        account_type="NOSTRO", actual_cadence=ReconCadence.DAILY)
    assert ok
    bad, msg2 = eng.check_cadence_compliance(
        account_type="NOSTRO", actual_cadence=ReconCadence.MONTHLY)
    assert not bad
    assert "below policy minimum" in msg2.lower()


def _test_engine_board_summary_empty():
    eng = ReconciliationRealtimeEngine()
    s = eng.board_summary()
    assert s["n_snapshots"] == 0
    assert s["latest_snapshot_at"] is None


def _test_engine_board_summary_aggregates():
    eng = ReconciliationRealtimeEngine()
    eng.add_snapshot(build_dashboard_snapshot(
        snapshot_at_utc="2026-04-23T10:00:00Z",
        auto_match_rate_pct=Decimal("92"),
        n_open_exceptions=50, n_sla_breaches=2, n_critical_alerts=0))
    eng.record_learning_feedback(LearningFeedback(
        feedback_id="F1", proposed_pair_id="P1",
        source_transaction_id="S", target_transaction_id="T",
        proposed_match_score=Decimal("0.9"),
        proposed_algorithm="X",
        actual_outcome=FeedbackOutcome.CONFIRMED_MATCH,
        reviewer_id="u", timestamp="t"))
    s = eng.board_summary()
    assert s["n_snapshots"] == 1
    assert s["latest_match_rate_pct"] == Decimal("92")
    assert s["n_learning_feedback"] == 1


def _test_decimal_purity():
    snap = build_dashboard_snapshot(
        snapshot_at_utc="t", auto_match_rate_pct=Decimal("92"),
        n_open_exceptions=10, n_sla_breaches=1, n_critical_alerts=0)
    assert isinstance(snap.auto_match_rate_pct, Decimal)
    for kpi in snap.kpis:
        assert isinstance(kpi.current_value, Decimal)


def self_test() -> None:
    tests = [
        _test_cadence_policy_loaded,
        _test_cadence_real_time_meets_daily,
        _test_cadence_monthly_fails_daily,
        _test_cadence_daily_meets_daily,
        _test_cadence_unknown_account_defaults_daily,
        _test_late_arrival_detected,
        _test_late_arrival_not_late,
        _test_late_arrival_acceptable_lag,
        _test_learning_store_records,
        _test_learning_stats_aggregation,
        _test_learning_no_train_callable_honest,
        _test_learning_train_callable_invoked,
        _test_learning_train_callable_failure_handled,
        _test_cert_terminal_signed_off,
        _test_cert_valid_path,
        _test_cert_invalid_skip,
        _test_dashboard_kpi_status_higher_is_better,
        _test_dashboard_kpi_status_lower_is_better,
        _test_build_dashboard_snapshot,
        _test_engine_certification_lifecycle,
        _test_engine_invalid_cert_transition_raises,
        _test_engine_check_cadence_compliance,
        _test_engine_board_summary_empty,
        _test_engine_board_summary_aggregates,
        _test_decimal_purity,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ reconciliation_realtime self-test: {len(failed)} failures",
              file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ reconciliation_realtime self-test passed ({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
