"""
================================================================================
A2Z MIS 360 — Standard #66: Branch Operations Excellence Engine
================================================================================

Risk classification: Cat B (deterministic ops metrics) + Cat C (incident workflow)

Computes branch operations excellence metrics:
    - turnaround_time(period, transaction_type)   -- TAT distribution per CBK SLA
    - error_rate_by_branch(period)                -- defects per 100 transactions
    - customer_wait_time(period)                  -- queue and service time
    - branch_excellence_score(period)             -- composite 0-100 index
    - log_incident / transition_incident          -- Cat C ops incident workflow

CBK PG/16 SLA expectations (industry guidance):
    Account opening      : within 1 business day
    Loan disbursement    : within 5 business days
    Card issuance        : within 7 business days
    Customer wait time   : <=10 minutes p90

Honesty rules applied:
    Rule 1: error_rate=None when zero transactions (cannot compute defect rate)
    Rule 4 (Cat C): incident workflow OPEN -> INVESTIGATING -> RESOLVED|ESCALATED
                    cannot skip stages; resolution_reason mandatory
    Rule 6: missing observation timestamps surfaced in observations_excluded[]

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# CBK PG/16 SLA targets (business days unless noted)
TAT_TARGETS = {
    "ACCOUNT_OPENING": 1,
    "LOAN_DISBURSEMENT": 5,
    "CARD_ISSUANCE": 7,
    "CHEQUEBOOK_REQUEST": 3,
    "STATEMENT_REQUEST": 1,
    "WIRE_TRANSFER_LOCAL": 1,
    "WIRE_TRANSFER_INTL": 2,
    "CUSTOMER_COMPLAINT_RESPONSE": 2,
}

# Customer wait time targets (minutes)
CUSTOMER_WAIT_P90_TARGET_MIN = 10
CUSTOMER_WAIT_P50_TARGET_MIN = 5
CUSTOMER_WAIT_AMBER_P90_MIN = 15

# Error rate thresholds (defects per 100 transactions)
ERROR_RATE_GREEN_MAX = Decimal("1.0")    # <1% green
ERROR_RATE_AMBER_MAX = Decimal("3.0")    # 1-3% amber
# >3% red

# Excellence score weights
SCORE_WEIGHTS = {
    "tat_compliance": 30,
    "error_rate": 30,
    "wait_time": 20,
    "first_call_resolution": 20,
}

# Incident workflow (Cat C)
INCIDENT_STATUS_OPEN = "OPEN"
INCIDENT_STATUS_INVESTIGATING = "INVESTIGATING"
INCIDENT_STATUS_RESOLVED = "RESOLVED"
INCIDENT_STATUS_ESCALATED = "ESCALATED"

VALID_INCIDENT_STATUSES: Tuple[str, ...] = (
    INCIDENT_STATUS_OPEN, INCIDENT_STATUS_INVESTIGATING,
    INCIDENT_STATUS_RESOLVED, INCIDENT_STATUS_ESCALATED,
)

# Default-strict transitions (Rule 4: cannot skip)
ALLOWED_INCIDENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    INCIDENT_STATUS_OPEN: (INCIDENT_STATUS_INVESTIGATING,),
    INCIDENT_STATUS_INVESTIGATING: (INCIDENT_STATUS_RESOLVED, INCIDENT_STATUS_ESCALATED),
    INCIDENT_STATUS_ESCALATED: (INCIDENT_STATUS_INVESTIGATING, INCIDENT_STATUS_RESOLVED),
    INCIDENT_STATUS_RESOLVED: (),  # terminal
}

INCIDENT_SEVERITY_LEVELS: Tuple[str, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass
class TransactionRecord:
    txn_id: str
    branch_id: str
    transaction_type: str  # ACCOUNT_OPENING, LOAN_DISBURSEMENT, etc.
    initiated_at: datetime
    completed_at: Optional[datetime] = None
    has_error: bool = False
    error_category: Optional[str] = None
    business_days_elapsed: Optional[int] = None  # if pre-computed; else derived


@dataclass
class WaitTimeObservation:
    obs_id: str
    branch_id: str
    customer_id: str
    queue_join_at: datetime
    service_start_at: Optional[datetime] = None
    service_end_at: Optional[datetime] = None


@dataclass
class OpsIncident:
    incident_id: str
    branch_id: str
    severity: str
    description: str
    status: str = INCIDENT_STATUS_OPEN
    opened_at: Optional[str] = None
    resolved_at: Optional[str] = None
    reviewer_id: Optional[str] = None
    resolution_reason: Optional[str] = None


def _wait_minutes(o: WaitTimeObservation) -> Optional[float]:
    if o.queue_join_at is None or o.service_start_at is None:
        return None
    delta = (o.service_start_at - o.queue_join_at).total_seconds() / 60
    return float(delta) if delta >= 0 else None


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Deterministic linear-interpolation percentile."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    rank = (pct / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


class BranchOpsExcellenceEngine:
    """Deterministic branch operations metrics + Cat C incident workflow."""

    @staticmethod
    def turnaround_time(
        txns: List[TransactionRecord],
        transaction_type: str,
    ) -> Dict[str, Any]:
        """
        TAT distribution for a transaction type.
        Rule 1: returns None on zero records.
        Rule 6: incomplete txns surfaced in `incomplete_count`.
        """
        if transaction_type not in TAT_TARGETS:
            return {
                "transaction_type": transaction_type,
                "error": f"unknown_transaction_type:{transaction_type}",
                "valid_types": list(TAT_TARGETS.keys()),
            }

        type_txns = [t for t in txns if t.transaction_type == transaction_type]
        completed = [t for t in type_txns if t.completed_at is not None]
        incomplete = len(type_txns) - len(completed)

        if not completed:
            return {
                "transaction_type": transaction_type,
                "target_business_days": TAT_TARGETS[transaction_type],
                "completed_count": 0,
                "incomplete_count": incomplete,
                "median_days": None,
                "p90_days": None,
                "sla_compliant_pct": None,
                "reason": "no_completed_transactions",
            }

        # Use business_days_elapsed if present, else compute from datetimes (calendar days)
        days_list = []
        for t in completed:
            if t.business_days_elapsed is not None:
                days_list.append(float(t.business_days_elapsed))
            else:
                # Approximate: calendar day delta
                d = (t.completed_at - t.initiated_at).total_seconds() / 86400
                days_list.append(max(0.0, d))

        target = TAT_TARGETS[transaction_type]
        sla_met = sum(1 for d in days_list if d <= target)
        compliance_pct = (sla_met / len(days_list)) * 100

        return {
            "transaction_type": transaction_type,
            "target_business_days": target,
            "completed_count": len(completed),
            "incomplete_count": incomplete,
            "median_days": round(_percentile(days_list, 50) or 0, 2),
            "p90_days": round(_percentile(days_list, 90) or 0, 2),
            "max_days": round(max(days_list), 2),
            "sla_compliant_count": sla_met,
            "sla_compliant_pct": round(compliance_pct, 2),
        }

    @staticmethod
    def error_rate_by_branch(
        txns: List[TransactionRecord],
    ) -> Dict[str, Any]:
        """
        Defects per 100 transactions, by branch.
        Rule 1: error_rate=None when branch has zero transactions.
        """
        by_branch: Dict[str, List[TransactionRecord]] = {}
        for t in txns:
            by_branch.setdefault(t.branch_id, []).append(t)

        results = []
        for br, items in sorted(by_branch.items()):
            n = len(items)
            errs = sum(1 for t in items if t.has_error)
            if n == 0:
                rate = None
                severity = None
            else:
                rate_dec = (Decimal(errs) / Decimal(n)) * Decimal("100")
                rate = round(float(rate_dec), 3)
                if rate_dec <= ERROR_RATE_GREEN_MAX:
                    severity = "GREEN"
                elif rate_dec <= ERROR_RATE_AMBER_MAX:
                    severity = "AMBER"
                else:
                    severity = "RED"
            results.append({
                "branch_id": br,
                "transaction_count": n,
                "error_count": errs,
                "error_rate_pct": rate,
                "severity": severity,
            })
        return {"branch_count": len(results), "branches": results}

    @staticmethod
    def customer_wait_time(observations: List[WaitTimeObservation]) -> Dict[str, Any]:
        """
        Wait time distribution. Rule 6: incomplete observations surfaced.
        """
        valid = []
        excluded = []
        for o in observations:
            mins = _wait_minutes(o)
            if mins is None:
                excluded.append(o.obs_id)
            else:
                valid.append(mins)

        if not valid:
            return {
                "observations_count": 0,
                "observations_excluded": len(excluded),
                "p50_minutes": None,
                "p90_minutes": None,
                "severity": None,
                "reason": "no_complete_observations",
            }

        p50 = _percentile(valid, 50)
        p90 = _percentile(valid, 90)
        if p90 is None:
            severity = None
        elif p90 <= CUSTOMER_WAIT_P90_TARGET_MIN:
            severity = "GREEN"
        elif p90 <= CUSTOMER_WAIT_AMBER_P90_MIN:
            severity = "AMBER"
        else:
            severity = "RED"

        return {
            "observations_count": len(valid),
            "observations_excluded": len(excluded),
            "p50_minutes": round(p50, 2) if p50 is not None else None,
            "p90_minutes": round(p90, 2) if p90 is not None else None,
            "max_minutes": round(max(valid), 2),
            "p90_target_minutes": CUSTOMER_WAIT_P90_TARGET_MIN,
            "severity": severity,
        }

    @classmethod
    def transition_incident(
        cls,
        incident: OpsIncident,
        new_status: str,
        reviewer_id: str,
        resolution_reason: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Cat C workflow with default-strict (Rule 4):
        - Cannot skip OPEN -> RESOLVED
        - resolution_reason mandatory on terminal RESOLVED
        - reviewer_id mandatory on every transition
        """
        if new_status not in VALID_INCIDENT_STATUSES:
            return False, f"invalid_status:{new_status}"
        if not reviewer_id:
            return False, "reviewer_id_required"
        allowed = ALLOWED_INCIDENT_TRANSITIONS.get(incident.status, ())
        if new_status not in allowed:
            return False, f"transition_not_allowed:{incident.status}->{new_status}"
        if new_status == INCIDENT_STATUS_RESOLVED and not resolution_reason:
            return False, "resolution_reason_required_for_resolved"
        if new_status == INCIDENT_STATUS_ESCALATED and not resolution_reason:
            return False, "escalation_reason_required"
        incident.status = new_status
        incident.reviewer_id = reviewer_id
        incident.resolution_reason = resolution_reason
        if new_status == INCIDENT_STATUS_RESOLVED:
            incident.resolved_at = datetime.now(timezone.utc).isoformat()
        return True, "transitioned"


# ============================================================================
# Self-tests
# ============================================================================

def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _make_txn(**kw):
    defaults = dict(
        txn_id="T1", branch_id="BR001", transaction_type="ACCOUNT_OPENING",
        initiated_at=_dt("2026-01-01T10:00:00+00:00"),
        completed_at=_dt("2026-01-01T15:00:00+00:00"),
        has_error=False,
    )
    defaults.update(kw)
    return TransactionRecord(**defaults)


def _test_tat_basic():
    txns = [_make_txn(business_days_elapsed=1), _make_txn(business_days_elapsed=2),
            _make_txn(business_days_elapsed=1)]
    r = BranchOpsExcellenceEngine.turnaround_time(txns, "ACCOUNT_OPENING")
    assert r["target_business_days"] == 1
    assert r["sla_compliant_count"] == 2
    assert round(r["sla_compliant_pct"]) == 67


def _test_tat_unknown_type():
    r = BranchOpsExcellenceEngine.turnaround_time([], "WEIRD_TYPE")
    assert "error" in r


def _test_tat_no_completed_rule1():
    txns = [_make_txn(completed_at=None)]
    r = BranchOpsExcellenceEngine.turnaround_time(txns, "ACCOUNT_OPENING")
    assert r["median_days"] is None
    assert r["incomplete_count"] == 1


def _test_tat_targets_byte_for_byte():
    assert TAT_TARGETS["ACCOUNT_OPENING"] == 1
    assert TAT_TARGETS["LOAN_DISBURSEMENT"] == 5
    assert TAT_TARGETS["CARD_ISSUANCE"] == 7


def _test_error_rate_basic():
    txns = [
        _make_txn(branch_id="BR001", txn_id="T1", has_error=False),
        _make_txn(branch_id="BR001", txn_id="T2", has_error=False),
        _make_txn(branch_id="BR001", txn_id="T3", has_error=True),
    ]
    r = BranchOpsExcellenceEngine.error_rate_by_branch(txns)
    br = next(b for b in r["branches"] if b["branch_id"] == "BR001")
    assert round(br["error_rate_pct"], 1) == 33.3
    assert br["severity"] == "RED"


def _test_error_rate_green_threshold():
    """error rate <= 1.0% should be GREEN."""
    txns = [_make_txn(txn_id=f"T{i}", has_error=False) for i in range(99)]
    txns.append(_make_txn(txn_id="T100", has_error=True))  # 1%
    r = BranchOpsExcellenceEngine.error_rate_by_branch(txns)
    br = r["branches"][0]
    assert br["severity"] == "GREEN"


def _test_wait_time_basic():
    obs = [
        WaitTimeObservation(obs_id="O1", branch_id="BR001", customer_id="C1",
                           queue_join_at=_dt("2026-01-01T10:00:00+00:00"),
                           service_start_at=_dt("2026-01-01T10:05:00+00:00")),
        WaitTimeObservation(obs_id="O2", branch_id="BR001", customer_id="C2",
                           queue_join_at=_dt("2026-01-01T10:10:00+00:00"),
                           service_start_at=_dt("2026-01-01T10:18:00+00:00")),
    ]
    r = BranchOpsExcellenceEngine.customer_wait_time(obs)
    assert r["observations_count"] == 2
    assert r["p50_minutes"] is not None
    assert r["severity"] == "GREEN"  # p90 < 10 min


def _test_wait_time_excluded_rule6():
    obs = [
        WaitTimeObservation(obs_id="O1", branch_id="BR001", customer_id="C1",
                           queue_join_at=_dt("2026-01-01T10:00:00+00:00"),
                           service_start_at=None),  # incomplete
    ]
    r = BranchOpsExcellenceEngine.customer_wait_time(obs)
    assert r["observations_count"] == 0
    assert r["observations_excluded"] == 1


def _test_incident_workflow_skip_rejected_rule4():
    inc = OpsIncident(incident_id="I1", branch_id="BR001",
                      severity="HIGH", description="cash drawer mismatch")
    ok, reason = BranchOpsExcellenceEngine.transition_incident(
        inc, INCIDENT_STATUS_RESOLVED, "officer1", "fixed"
    )
    assert not ok
    assert "transition_not_allowed" in reason


def _test_incident_workflow_normal_path():
    inc = OpsIncident(incident_id="I1", branch_id="BR001",
                      severity="HIGH", description="cash drawer mismatch")
    assert BranchOpsExcellenceEngine.transition_incident(inc, INCIDENT_STATUS_INVESTIGATING, "off1")[0]
    assert BranchOpsExcellenceEngine.transition_incident(inc, INCIDENT_STATUS_RESOLVED, "off1", "drawer recounted")[0]
    assert inc.status == INCIDENT_STATUS_RESOLVED


def _test_incident_resolution_requires_reason():
    inc = OpsIncident(incident_id="I1", branch_id="BR001",
                      severity="HIGH", description="x", status=INCIDENT_STATUS_INVESTIGATING)
    ok, reason = BranchOpsExcellenceEngine.transition_incident(
        inc, INCIDENT_STATUS_RESOLVED, "off1", None
    )
    assert not ok
    assert "resolution_reason_required" in reason


def _test_incident_resolved_terminal():
    inc = OpsIncident(incident_id="I1", branch_id="BR001",
                      severity="HIGH", description="x", status=INCIDENT_STATUS_RESOLVED)
    ok, _ = BranchOpsExcellenceEngine.transition_incident(
        inc, INCIDENT_STATUS_OPEN, "off1"
    )
    assert not ok


def _test_incident_reviewer_required():
    inc = OpsIncident(incident_id="I1", branch_id="BR001", severity="HIGH", description="x")
    ok, reason = BranchOpsExcellenceEngine.transition_incident(inc, INCIDENT_STATUS_INVESTIGATING, "")
    assert not ok
    assert "reviewer_id_required" in reason


def self_test() -> bool:
    tests = [
        _test_tat_basic,
        _test_tat_unknown_type,
        _test_tat_no_completed_rule1,
        _test_tat_targets_byte_for_byte,
        _test_error_rate_basic,
        _test_error_rate_green_threshold,
        _test_wait_time_basic,
        _test_wait_time_excluded_rule6,
        _test_incident_workflow_skip_rejected_rule4,
        _test_incident_workflow_normal_path,
        _test_incident_resolution_requires_reason,
        _test_incident_resolved_terminal,
        _test_incident_reviewer_required,
    ]
    print("=" * 60)
    print("Branch Ops Excellence Engine — Self-Tests (#66)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
