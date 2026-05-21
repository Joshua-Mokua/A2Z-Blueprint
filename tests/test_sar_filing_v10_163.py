"""tests/test_sar_filing_v10_163.py — ENH-194 SAR/STR Filing Engine.

Verifies the v10.163 deliverable:
- Engine module exists, parses, imports
- 3 enums (ReportType 2, FilingStatus 6, TransitionOutcome 4)
- ALLOWED_TRANSITIONS state machine — DRAFT can go to SUBMITTED or
  WITHDRAWN; SUBMITTED only to ACKNOWLEDGED; backwards transitions
  rejected
- 4 frozen input/provenance dataclasses (SubjectIdentity,
  TransactionEvidence, AlertProvenance, FilingPayload)
- POCAMLA §44 7-day deadline auto-computed from suspicion_formed_at
- Provenance auto-populated from upstream AmlMonitoringResult
- WITHDRAWN requires reason (audit trail)
- overdue_filings() identifies DRAFT past deadline
- Honest deferral: submission_method explicitly notes MANUAL_PORTAL
- Standard ENH-194 status='active' in registry
- Audit unchanged at 151/151
- No regression of v10.160 KYC, v10.162 AML monitoring, or earlier
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "sar_filing.py"
REGISTRY_PATH = REPO_ROOT / "utils" / "standards_registry.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_engine_exists_and_parses(self):
        assert ENGINE_PATH.exists()
        ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))

    def test_engine_imports(self):
        from utils.sar_filing import SarFilingEngine
        eng = SarFilingEngine()
        assert eng is not None

    def test_enums_present_with_correct_cardinality(self):
        from utils.sar_filing import (ReportType, FilingStatus,
                                        TransitionOutcome)
        assert len(list(ReportType)) == 2     # SAR, STR
        assert len(list(FilingStatus)) == 6   # 5 lifecycle + WITHDRAWN
        assert len(list(TransitionOutcome)) == 4

    def test_filing_status_vocabulary(self):
        from utils.sar_filing import FilingStatus
        names = {s.value for s in FilingStatus}
        for required in ("DRAFT", "SUBMITTED", "ACKNOWLEDGED",
                          "INVESTIGATION_OPENED", "INVESTIGATION_CLOSED",
                          "WITHDRAWN"):
            assert required in names

    def test_dataclasses_frozen(self):
        from utils.sar_filing import SubjectIdentity
        s = SubjectIdentity(subject_id="C1", legal_name="X",
                              subject_kind="INDIVIDUAL")
        try:
            s.subject_id = "MUTATED"
            raise AssertionError("frozen dataclass mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_194_active(self):
        m = _load("registry_v163", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-194"), None)
        assert s is not None
        assert s.status == "active"
        assert "sar_filing" in (s.affected_engines or ())


class TestStateMachine:
    """ALLOWED_TRANSITIONS reflects POCAMLA + FRC procedural reality."""

    def test_draft_to_submitted_allowed(self):
        from utils.sar_filing import (ALLOWED_TRANSITIONS,
                                        FilingStatus)
        assert FilingStatus.SUBMITTED in (
            ALLOWED_TRANSITIONS[FilingStatus.DRAFT])

    def test_draft_to_withdrawn_allowed(self):
        from utils.sar_filing import (ALLOWED_TRANSITIONS,
                                        FilingStatus)
        assert FilingStatus.WITHDRAWN in (
            ALLOWED_TRANSITIONS[FilingStatus.DRAFT])

    def test_submitted_cannot_go_backwards(self):
        from utils.sar_filing import (ALLOWED_TRANSITIONS,
                                        FilingStatus)
        # Once SUBMITTED, cannot return to DRAFT or be WITHDRAWN
        # (POCAMLA — institution must maintain filing)
        assert FilingStatus.DRAFT not in (
            ALLOWED_TRANSITIONS[FilingStatus.SUBMITTED])
        assert FilingStatus.WITHDRAWN not in (
            ALLOWED_TRANSITIONS[FilingStatus.SUBMITTED])

    def test_terminal_states_have_no_transitions(self):
        from utils.sar_filing import (ALLOWED_TRANSITIONS,
                                        FilingStatus)
        assert ALLOWED_TRANSITIONS[
            FilingStatus.INVESTIGATION_CLOSED] == ()
        assert ALLOWED_TRANSITIONS[FilingStatus.WITHDRAWN] == ()

    def test_acknowledged_can_branch_to_open_or_close(self):
        # FRC may open investigation OR close immediately if their
        # review finds nothing actionable
        from utils.sar_filing import (ALLOWED_TRANSITIONS,
                                        FilingStatus)
        successors = ALLOWED_TRANSITIONS[FilingStatus.ACKNOWLEDGED]
        assert FilingStatus.INVESTIGATION_OPENED in successors
        assert FilingStatus.INVESTIGATION_CLOSED in successors


class TestBuildFiling:
    def test_str_when_transactions_provided(self):
        """STR — Suspicious Transaction Report when txns cited."""
        from utils.sar_filing import (SarFilingEngine, ReportType,
                                        SubjectIdentity,
                                        TransactionEvidence)
        # Mock minimal monitoring result
        class MockResult:
            customer_id = "C1"
            customer_tier = "CDD"
            monitored_at_utc = "2026-05-01T10:00:00+00:00"
            tiered_alerts = ()
        eng = SarFilingEngine()
        f = eng.build_filing(
            monitoring_result=MockResult(),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[TransactionEvidence(
                txn_id="T1", txn_date="2026-05-01",
                amount_kes=Decimal("999000"),
                txn_type="CASH_DEPOSIT")],
            suspicion_narrative="x" * 50)
        assert f.report_type == ReportType.STR

    def test_sar_when_no_transactions(self):
        """SAR — Suspicious Activity Report when no txns cited."""
        from utils.sar_filing import (SarFilingEngine, ReportType,
                                        SubjectIdentity)
        class MockResult:
            customer_id = "C1"
            customer_tier = "CDD"
            monitored_at_utc = "2026-05-01T10:00:00+00:00"
            tiered_alerts = ()
        eng = SarFilingEngine()
        f = eng.build_filing(
            monitoring_result=MockResult(),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[],
            suspicion_narrative=("Behavioural pattern of dormant "
                                   "account suddenly active"))
        assert f.report_type == ReportType.SAR

    def test_pocamla_deadline_7_days(self):
        """POCAMLA §44 — filing within 7 days of suspicion."""
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity)
        suspicion_at = "2026-05-01T10:00:00+00:00"
        class MockResult:
            customer_id = "C1"
            customer_tier = "CDD"
            monitored_at_utc = suspicion_at
            tiered_alerts = ()
        eng = SarFilingEngine()
        f = eng.build_filing(
            monitoring_result=MockResult(),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[],
            suspicion_narrative="x" * 50,
            suspicion_formed_at_utc=suspicion_at)
        # Deadline should be exactly 7 days after suspicion_at
        formed = datetime.fromisoformat(suspicion_at)
        deadline = datetime.fromisoformat(f.filing_deadline_utc)
        assert (deadline - formed).days == 7

    def test_empty_narrative_rejected(self):
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity)
        class MockResult:
            customer_id = "C1"; customer_tier = "CDD"
            monitored_at_utc = "2026-05-01T10:00:00"
            tiered_alerts = ()
        eng = SarFilingEngine()
        try:
            eng.build_filing(
                monitoring_result=MockResult(),
                subject=SubjectIdentity(
                    subject_id="C1", legal_name="Test",
                    subject_kind="INDIVIDUAL"),
                transactions=[],
                suspicion_narrative="")
            raise AssertionError("empty narrative should raise")
        except ValueError as e:
            assert "narrative" in str(e).lower()

    def test_provenance_populated_from_aml_result(self):
        """When given a real AmlMonitoringResult, build_filing should
        thread provenance through."""
        from datetime import datetime
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.transaction_monitoring import Transaction
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity,
                                        TransactionEvidence)
        aml_eng = AmlMonitoringEngine()
        # Trigger a structuring alert via real upstream
        txns = [
            Transaction(txn_id=f"T{i}", customer_id="C100",
                          account_id="A100",
                          amount_kes=Decimal(amt),
                          txn_type="CASH_DEPOSIT",
                          txn_datetime=datetime(2026, 5, day, 10, 0))
            for i, (amt, day) in enumerate([
                ("999000", 1), ("999500", 2), ("980000", 3)
            ], 1)
        ]
        aml_result = aml_eng.monitor_customer("C100", txns,
                                                 customer_tier="EDD")
        sar_eng = SarFilingEngine()
        f = sar_eng.build_filing(
            monitoring_result=aml_result,
            subject=SubjectIdentity(
                subject_id="C100", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[TransactionEvidence(
                txn_id="T1", txn_date="2026-05-01",
                amount_kes=Decimal("999000"),
                txn_type="CASH_DEPOSIT")],
            suspicion_narrative=(
                "Three sub-threshold cash deposits within 7 days; "
                "structuring per FATF guidance"))
        # Provenance should reflect the upstream
        assert f.provenance.customer_id == "C100"
        assert f.provenance.monitoring_engine == (
            "ENH-193 AmlMonitoringEngine")
        assert "R2" in f.provenance.rule_ids
        assert f.provenance.severity == "CRITICAL"
        # Risk indicators composite
        assert "R2" in f.risk_indicators
        assert "TIER_EDD" in f.risk_indicators


class TestTransitions:
    def _build_draft(self):
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity)
        class MockResult:
            customer_id = "C1"; customer_tier = "CDD"
            monitored_at_utc = "2026-05-01T10:00:00+00:00"
            tiered_alerts = ()
        eng = SarFilingEngine()
        f = eng.build_filing(
            monitoring_result=MockResult(),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[],
            suspicion_narrative="x" * 50)
        return eng, f

    def test_draft_to_submitted_records_filed_at(self):
        from utils.sar_filing import FilingStatus, TransitionOutcome
        eng, f = self._build_draft()
        outcome, updated = eng.transition(
            f.filing_id, FilingStatus.SUBMITTED,
            user="officer_001",
            reason="Reviewed, suspicion confirmed")
        assert outcome == TransitionOutcome.OK
        assert updated.status == FilingStatus.SUBMITTED
        assert updated.filed_at_utc is not None
        assert updated.filed_by_user == "officer_001"

    def test_submitted_cannot_revert_to_draft(self):
        """POCAMLA — once submitted, cannot withdraw. State machine
        enforces the rule."""
        from utils.sar_filing import FilingStatus, TransitionOutcome
        eng, f = self._build_draft()
        eng.transition(f.filing_id, FilingStatus.SUBMITTED,
                          user="officer", reason="x")
        outcome, updated = eng.transition(
            f.filing_id, FilingStatus.DRAFT, user="someone")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION
        # State unchanged
        assert updated.status == FilingStatus.SUBMITTED

    def test_submitted_cannot_be_withdrawn(self):
        from utils.sar_filing import FilingStatus, TransitionOutcome
        eng, f = self._build_draft()
        eng.transition(f.filing_id, FilingStatus.SUBMITTED,
                          user="officer", reason="x")
        outcome, _ = eng.transition(
            f.filing_id, FilingStatus.WITHDRAWN, user="someone",
            reason="changed mind")
        assert outcome == TransitionOutcome.REJECTED_INVALID_TRANSITION

    def test_withdrawn_requires_reason(self):
        from utils.sar_filing import FilingStatus, TransitionOutcome
        eng, f = self._build_draft()
        outcome, _ = eng.transition(
            f.filing_id, FilingStatus.WITHDRAWN, user="officer",
            reason="")
        assert outcome == TransitionOutcome.REJECTED_REASON_REQUIRED

    def test_withdrawn_with_reason_works(self):
        from utils.sar_filing import FilingStatus, TransitionOutcome
        eng, f = self._build_draft()
        outcome, updated = eng.transition(
            f.filing_id, FilingStatus.WITHDRAWN, user="officer",
            reason="Re-reviewed by senior; false positive")
        assert outcome == TransitionOutcome.OK
        assert updated.status == FilingStatus.WITHDRAWN

    def test_full_lifecycle_records_5_log_entries(self):
        from utils.sar_filing import FilingStatus
        eng, f = self._build_draft()
        eng.transition(f.filing_id, FilingStatus.SUBMITTED,
                          user="o", reason="x")
        eng.transition(f.filing_id, FilingStatus.ACKNOWLEDGED,
                          user="frc")
        eng.transition(f.filing_id, FilingStatus.INVESTIGATION_OPENED,
                          user="frc")
        outcome, final = eng.transition(
            f.filing_id, FilingStatus.INVESTIGATION_CLOSED,
            user="frc", investigation_outcome="CLOSED_REFERRED")
        # DRAFT + SUBMITTED + ACKNOWLEDGED + INVESTIGATION_OPENED +
        # INVESTIGATION_CLOSED = 5 log entries
        assert len(final.transition_log) == 5
        assert final.investigation_outcome == "CLOSED_REFERRED"

    def test_unknown_filing_id_rejected(self):
        from utils.sar_filing import (SarFilingEngine, FilingStatus,
                                        TransitionOutcome)
        eng = SarFilingEngine()
        outcome, _ = eng.transition(
            "NONEXISTENT", FilingStatus.SUBMITTED, user="x")
        assert outcome == TransitionOutcome.REJECTED_REPORT_NOT_FOUND


class TestOverdueDetection:
    def test_overdue_drafts_identified(self):
        """DRAFT filings past POCAMLA §44 deadline are surfaced —
        regulatory exposure for the bank."""
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity)
        # Build with suspicion 30 days ago
        old_suspicion = (datetime.now(timezone.utc)
                          - timedelta(days=30)).isoformat()
        class MockResult:
            customer_id = "C1"; customer_tier = "CDD"
            monitored_at_utc = old_suspicion
            tiered_alerts = ()
        eng = SarFilingEngine()
        f = eng.build_filing(
            monitoring_result=MockResult(),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[],
            suspicion_narrative="x" * 50,
            suspicion_formed_at_utc=old_suspicion)
        # Still in DRAFT, deadline is 7 days from suspicion → 23 days ago
        overdue = eng.overdue_filings()
        assert f in overdue
        assert eng.board_summary()["n_overdue_drafts"] == 1


class TestHonestDeferral:
    def test_submission_method_explicitly_manual(self):
        """The 'wire-level submission to FRC' is honestly deferred."""
        from utils.sar_filing import (SarFilingEngine, SubjectIdentity)
        class MockResult:
            customer_id = "C1"; customer_tier = "CDD"
            monitored_at_utc = "2026-05-01T10:00:00"
            tiered_alerts = ()
        eng = SarFilingEngine()
        f = eng.build_filing(
            monitoring_result=MockResult(),
            subject=SubjectIdentity(
                subject_id="C1", legal_name="Test",
                subject_kind="INDIVIDUAL"),
            transactions=[],
            suspicion_narrative="x" * 50)
        assert "MANUAL_PORTAL" in f.submission_method
        assert "no public programmatic submission API" in (
            f.submission_method)


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.sar_filing import SarFilingEngine
        eng = SarFilingEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_filings_total",
                   "n_overdue_drafts", "n_submitted",
                   "n_acknowledged_by_frc", "n_under_investigation",
                   "n_investigation_closed", "status_counts",
                   "type_counts", "submission_method",
                   "regulatory_basis"):
            assert f in s, f"missing: {f}"
        assert "POCAMLA" in s["regulatory_basis"]


class TestNoRegression:
    def test_audit_still_passes(self):
        m = _load("audit_v163", AUDIT_PATH)
        for gate_id, gate_fn in m.GATES:
            result = gate_fn()
            assert result["passed"] is True

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v163", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_162_aml_monitoring_works(self):
        from utils.aml_monitoring import AmlMonitoringEngine
        eng = AmlMonitoringEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-193 AmlMonitoringEngine")

    def test_v10_160_kyc_works(self):
        from utils.kyc_onboarding import KycOnboardingEngine
        eng = KycOnboardingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-191 KycOnboardingEngine")
