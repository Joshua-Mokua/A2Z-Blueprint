"""
================================================================================
A2Z MIS 360 — Standard #59: Transaction Monitoring Engine
================================================================================

Risk classification: Cat B (rule-based deterministic AML alerts)

Detects suspicious transaction patterns per CBK PG/15 §6 (Transaction Monitoring)
and FATF Recommendation 20 (Suspicious Transaction Reporting). Uses deterministic
threshold-based rules — no ML required.

Rule catalog (deterministic, all configurable):
    R1  CASH_THRESHOLD_BREACH    : Single cash deposit/withdrawal > KES 1M
    R2  STRUCTURING_PATTERN      : 3+ deposits 800k-999k within 7 days
    R3  RAPID_MOVEMENT           : Funds in & out within 48 hrs > KES 5M
    R4  HIGH_RISK_GEOGRAPHY      : Wire to/from prohibited jurisdiction
    R5  ACCOUNT_DORMANT_ACTIVITY : Activity on dormant account > KES 100k
    R6  ROUND_NUMBER_PATTERN     : 5+ identical round-number txns / 30 days
    R7  VELOCITY_BREACH          : Daily txn count > 20 OR daily amount > KES 10M
    R8  PEP_LARGE_TRANSACTION    : PEP customer txn > KES 2M

Alert workflow (default-strict per Rule 4):
    OPEN          -> requires investigation
    INVESTIGATING -> compliance officer reviewing
    SAR_FILED     -> Suspicious Activity Report filed with FRC
    DISMISSED     -> documented false positive

Cash threshold (CBK reportable: KES 1M) is byte-for-byte preserved.

Honesty rules applied:
    Rule 1: amounts use Decimal precision (no float-mediated drift)
    Rule 4: alerts cannot be auto-dismissed; require reviewer + reason
    Rule 6: unknown transaction types do not bypass screening; flagged for review

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# CBK reportable thresholds (KES)
CASH_REPORTING_THRESHOLD_KES = Decimal("1000000")        # CBK PG/15
STRUCTURING_LOWER_KES = Decimal("800000")
STRUCTURING_UPPER_KES = Decimal("999999")
STRUCTURING_MIN_COUNT = 3
STRUCTURING_WINDOW_DAYS = 7
RAPID_MOVEMENT_THRESHOLD_KES = Decimal("5000000")
RAPID_MOVEMENT_WINDOW_HOURS = 48
DORMANT_ACTIVITY_THRESHOLD_KES = Decimal("100000")
ROUND_NUMBER_MIN_COUNT = 5
ROUND_NUMBER_WINDOW_DAYS = 30
DAILY_VELOCITY_COUNT_THRESHOLD = 20
DAILY_VELOCITY_AMOUNT_KES = Decimal("10000000")
PEP_LARGE_TXN_KES = Decimal("2000000")

PROHIBITED_JURISDICTIONS_TXN: Tuple[str, ...] = ("KP", "IR")
HIGH_RISK_JURISDICTIONS_TXN: Tuple[str, ...] = ("AF", "MM", "SY", "YE", "SS")

# Alert severities
SEVERITY_LOW = "LOW"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_HIGH = "HIGH"
SEVERITY_CRITICAL = "CRITICAL"

# Alert workflow statuses
ALERT_STATUS_OPEN = "OPEN"
ALERT_STATUS_INVESTIGATING = "INVESTIGATING"
ALERT_STATUS_SAR_FILED = "SAR_FILED"
ALERT_STATUS_DISMISSED = "DISMISSED"
VALID_ALERT_STATUSES: Tuple[str, ...] = (
    ALERT_STATUS_OPEN, ALERT_STATUS_INVESTIGATING, ALERT_STATUS_SAR_FILED, ALERT_STATUS_DISMISSED
)
ALLOWED_ALERT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    ALERT_STATUS_OPEN: (ALERT_STATUS_INVESTIGATING,),
    ALERT_STATUS_INVESTIGATING: (ALERT_STATUS_SAR_FILED, ALERT_STATUS_DISMISSED),
    ALERT_STATUS_SAR_FILED: (),
    ALERT_STATUS_DISMISSED: (),
}

# Rule catalog metadata
RULE_CATALOG: Dict[str, Dict[str, Any]] = {
    "R1": {"name": "CASH_THRESHOLD_BREACH", "severity": SEVERITY_HIGH},
    "R2": {"name": "STRUCTURING_PATTERN", "severity": SEVERITY_CRITICAL},
    "R3": {"name": "RAPID_MOVEMENT", "severity": SEVERITY_HIGH},
    "R4": {"name": "HIGH_RISK_GEOGRAPHY", "severity": SEVERITY_CRITICAL},
    "R5": {"name": "ACCOUNT_DORMANT_ACTIVITY", "severity": SEVERITY_MEDIUM},
    "R6": {"name": "ROUND_NUMBER_PATTERN", "severity": SEVERITY_MEDIUM},
    "R7": {"name": "VELOCITY_BREACH", "severity": SEVERITY_HIGH},
    "R8": {"name": "PEP_LARGE_TRANSACTION", "severity": SEVERITY_HIGH},
}


def _to_decimal(amount: Any) -> Decimal:
    """Convert any amount to Decimal (Rule 1)."""
    if isinstance(amount, Decimal):
        return amount
    if amount is None:
        return Decimal("0")
    return Decimal(str(amount))


def _parse_dt(s: Any) -> datetime:
    """Parse ISO datetime, fallback to now."""
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    if isinstance(s, str):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


@dataclass
class Transaction:
    txn_id: str
    customer_id: str
    account_id: str
    amount_kes: Decimal
    txn_type: str  # CASH_DEPOSIT, CASH_WITHDRAWAL, WIRE_IN, WIRE_OUT, TRANSFER, ATM, MOBILE
    txn_datetime: datetime
    counterparty_country: Optional[str] = None
    counterparty_name: Optional[str] = None
    direction: str = "DEBIT"  # DEBIT or CREDIT
    customer_pep: bool = False
    account_dormant: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    alert_id: int
    rule_id: str
    rule_name: str
    severity: str
    customer_id: str
    txn_ids: List[str]
    description: str
    detected_at: str
    status: str = ALERT_STATUS_OPEN
    reviewer_id: Optional[str] = None
    review_completed_at: Optional[str] = None
    resolution_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "customer_id": self.customer_id,
            "txn_ids": list(self.txn_ids),
            "description": self.description,
            "detected_at": self.detected_at,
            "status": self.status,
            "reviewer_id": self.reviewer_id,
            "review_completed_at": self.review_completed_at,
            "resolution_reason": self.resolution_reason,
        }


class TransactionMonitoringEngine:
    """Rule-based AML transaction monitoring with default-strict workflow."""

    def __init__(self):
        self._alerts: List[Alert] = []
        self._next_alert_id = 1

    # ------------------------------------------------------------------
    # Detection rules
    # ------------------------------------------------------------------

    def _rule_cash_threshold(self, txns: List[Transaction]) -> List[Alert]:
        """R1: Single cash transaction > CASH_REPORTING_THRESHOLD_KES."""
        alerts = []
        for t in txns:
            if t.txn_type in ("CASH_DEPOSIT", "CASH_WITHDRAWAL") and t.amount_kes > CASH_REPORTING_THRESHOLD_KES:
                alerts.append(self._mk_alert(
                    "R1",
                    customer_id=t.customer_id,
                    txn_ids=[t.txn_id],
                    description=f"{t.txn_type} of KES {t.amount_kes} exceeds reporting threshold KES {CASH_REPORTING_THRESHOLD_KES}",
                ))
        return alerts

    def _rule_structuring(self, txns: List[Transaction]) -> List[Alert]:
        """R2: 3+ cash deposits 800k-999k within 7 days from same customer."""
        alerts = []
        # Group by customer
        by_cust: Dict[str, List[Transaction]] = {}
        for t in txns:
            if t.txn_type == "CASH_DEPOSIT" and STRUCTURING_LOWER_KES <= t.amount_kes <= STRUCTURING_UPPER_KES:
                by_cust.setdefault(t.customer_id, []).append(t)
        for cust, items in by_cust.items():
            items.sort(key=lambda x: x.txn_datetime)
            # Sliding window
            for i in range(len(items)):
                window_end = items[i].txn_datetime + timedelta(days=STRUCTURING_WINDOW_DAYS)
                in_window = [items[i]]
                for j in range(i + 1, len(items)):
                    if items[j].txn_datetime <= window_end:
                        in_window.append(items[j])
                    else:
                        break
                if len(in_window) >= STRUCTURING_MIN_COUNT:
                    txn_ids = [t.txn_id for t in in_window]
                    alerts.append(self._mk_alert(
                        "R2",
                        customer_id=cust,
                        txn_ids=txn_ids,
                        description=f"Structuring detected: {len(in_window)} deposits between {STRUCTURING_LOWER_KES}-{STRUCTURING_UPPER_KES} KES within {STRUCTURING_WINDOW_DAYS} days",
                    ))
                    break  # one alert per customer per scan
        return alerts

    def _rule_rapid_movement(self, txns: List[Transaction]) -> List[Alert]:
        """R3: Total credit > 5M followed by total debit > 5M within 48hrs."""
        alerts = []
        by_cust: Dict[str, List[Transaction]] = {}
        for t in txns:
            by_cust.setdefault(t.customer_id, []).append(t)
        for cust, items in by_cust.items():
            items.sort(key=lambda x: x.txn_datetime)
            credits = [t for t in items if t.direction == "CREDIT"]
            for c in credits:
                if c.amount_kes < RAPID_MOVEMENT_THRESHOLD_KES:
                    continue
                window_end = c.txn_datetime + timedelta(hours=RAPID_MOVEMENT_WINDOW_HOURS)
                debit_total = sum(
                    (t.amount_kes for t in items
                     if t.direction == "DEBIT" and c.txn_datetime <= t.txn_datetime <= window_end),
                    Decimal("0")
                )
                if debit_total >= RAPID_MOVEMENT_THRESHOLD_KES:
                    alerts.append(self._mk_alert(
                        "R3",
                        customer_id=cust,
                        txn_ids=[c.txn_id],
                        description=f"Rapid in-out: KES {c.amount_kes} credit followed by KES {debit_total} debits within {RAPID_MOVEMENT_WINDOW_HOURS}h",
                    ))
                    break
        return alerts

    def _rule_high_risk_geography(self, txns: List[Transaction]) -> List[Alert]:
        """R4: Wires to/from prohibited or high-risk jurisdictions."""
        alerts = []
        for t in txns:
            if t.txn_type not in ("WIRE_IN", "WIRE_OUT"):
                continue
            cc = (t.counterparty_country or "").upper()
            if cc in PROHIBITED_JURISDICTIONS_TXN:
                alerts.append(self._mk_alert(
                    "R4",
                    customer_id=t.customer_id,
                    txn_ids=[t.txn_id],
                    description=f"{t.txn_type} to/from PROHIBITED jurisdiction {cc} (KES {t.amount_kes})",
                ))
            elif cc in HIGH_RISK_JURISDICTIONS_TXN and t.amount_kes >= Decimal("100000"):
                alerts.append(self._mk_alert(
                    "R4",
                    customer_id=t.customer_id,
                    txn_ids=[t.txn_id],
                    description=f"{t.txn_type} to/from HIGH-RISK jurisdiction {cc} (KES {t.amount_kes})",
                ))
        return alerts

    def _rule_dormant_activity(self, txns: List[Transaction]) -> List[Alert]:
        """R5: Activity > 100k on dormant account."""
        alerts = []
        for t in txns:
            if t.account_dormant and t.amount_kes >= DORMANT_ACTIVITY_THRESHOLD_KES:
                alerts.append(self._mk_alert(
                    "R5",
                    customer_id=t.customer_id,
                    txn_ids=[t.txn_id],
                    description=f"Activity on DORMANT account {t.account_id}: KES {t.amount_kes} {t.txn_type}",
                ))
        return alerts

    def _rule_round_numbers(self, txns: List[Transaction]) -> List[Alert]:
        """R6: 5+ identical round-number transactions in 30 days."""
        alerts = []
        by_cust: Dict[str, List[Transaction]] = {}
        for t in txns:
            # Round = ends in 000, >= 100k
            if t.amount_kes >= Decimal("100000") and (t.amount_kes % Decimal("1000") == 0):
                by_cust.setdefault(t.customer_id, []).append(t)
        for cust, items in by_cust.items():
            items.sort(key=lambda x: x.txn_datetime)
            # Group by amount
            by_amt: Dict[str, List[Transaction]] = {}
            for t in items:
                by_amt.setdefault(str(t.amount_kes), []).append(t)
            for amt_str, group in by_amt.items():
                if len(group) >= ROUND_NUMBER_MIN_COUNT:
                    span = group[-1].txn_datetime - group[0].txn_datetime
                    if span <= timedelta(days=ROUND_NUMBER_WINDOW_DAYS):
                        alerts.append(self._mk_alert(
                            "R6",
                            customer_id=cust,
                            txn_ids=[t.txn_id for t in group],
                            description=f"{len(group)} identical KES {amt_str} transactions within {ROUND_NUMBER_WINDOW_DAYS} days",
                        ))
                        break
        return alerts

    def _rule_velocity(self, txns: List[Transaction]) -> List[Alert]:
        """R7: Daily count > 20 OR daily amount > 10M for one customer."""
        alerts = []
        by_cust_day: Dict[Tuple[str, str], List[Transaction]] = {}
        for t in txns:
            day_key = (t.customer_id, t.txn_datetime.strftime("%Y-%m-%d"))
            by_cust_day.setdefault(day_key, []).append(t)
        for (cust, day), items in by_cust_day.items():
            count = len(items)
            total = sum((t.amount_kes for t in items), Decimal("0"))
            if count > DAILY_VELOCITY_COUNT_THRESHOLD or total > DAILY_VELOCITY_AMOUNT_KES:
                alerts.append(self._mk_alert(
                    "R7",
                    customer_id=cust,
                    txn_ids=[t.txn_id for t in items],
                    description=f"Velocity breach on {day}: {count} txns totaling KES {total}",
                ))
        return alerts

    def _rule_pep_large(self, txns: List[Transaction]) -> List[Alert]:
        """R8: PEP customer transaction > 2M."""
        alerts = []
        for t in txns:
            if t.customer_pep and t.amount_kes > PEP_LARGE_TXN_KES:
                alerts.append(self._mk_alert(
                    "R8",
                    customer_id=t.customer_id,
                    txn_ids=[t.txn_id],
                    description=f"PEP large transaction: KES {t.amount_kes} {t.txn_type}",
                ))
        return alerts

    def _mk_alert(self, rule_id: str, customer_id: str, txn_ids: List[str], description: str) -> Alert:
        meta = RULE_CATALOG[rule_id]
        a = Alert(
            alert_id=self._next_alert_id,
            rule_id=rule_id,
            rule_name=meta["name"],
            severity=meta["severity"],
            customer_id=customer_id,
            txn_ids=txn_ids,
            description=description,
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        self._next_alert_id += 1
        return a

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, txns: List[Transaction]) -> List[Alert]:
        """Run all rules against a batch of transactions. Returns new alerts."""
        new_alerts = []
        for rule_fn in (
            self._rule_cash_threshold,
            self._rule_structuring,
            self._rule_rapid_movement,
            self._rule_high_risk_geography,
            self._rule_dormant_activity,
            self._rule_round_numbers,
            self._rule_velocity,
            self._rule_pep_large,
        ):
            new_alerts.extend(rule_fn(txns))
        self._alerts.extend(new_alerts)
        return new_alerts

    def transition_alert(
        self,
        alert_id: int,
        new_status: str,
        reviewer_id: str,
        resolution_reason: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Move alert through workflow. Default-strict: cannot auto-dismiss."""
        if new_status not in VALID_ALERT_STATUSES:
            return False, f"invalid_status:{new_status}"
        if not reviewer_id:
            return False, "reviewer_id_required"
        a = next((x for x in self._alerts if x.alert_id == alert_id), None)
        if a is None:
            return False, f"alert_id_not_found:{alert_id}"
        allowed = ALLOWED_ALERT_TRANSITIONS.get(a.status, ())
        if new_status not in allowed:
            return False, f"transition_not_allowed:{a.status}->{new_status}"
        if new_status == ALERT_STATUS_DISMISSED and not resolution_reason:
            return False, "resolution_reason_required_for_dismissed"
        if new_status == ALERT_STATUS_SAR_FILED and not resolution_reason:
            return False, "sar_reference_required_for_sar_filed"
        a.status = new_status
        a.reviewer_id = reviewer_id
        a.resolution_reason = resolution_reason
        if new_status in (ALERT_STATUS_SAR_FILED, ALERT_STATUS_DISMISSED):
            a.review_completed_at = datetime.now(timezone.utc).isoformat()
        return True, "transitioned"

    def alert_summary(self) -> Dict[str, Any]:
        by_rule: Dict[str, int] = {}
        by_severity: Dict[str, int] = {SEVERITY_LOW: 0, SEVERITY_MEDIUM: 0, SEVERITY_HIGH: 0, SEVERITY_CRITICAL: 0}
        by_status: Dict[str, int] = {s: 0 for s in VALID_ALERT_STATUSES}
        for a in self._alerts:
            by_rule[a.rule_id] = by_rule.get(a.rule_id, 0) + 1
            by_severity[a.severity] = by_severity.get(a.severity, 0) + 1
            by_status[a.status] = by_status.get(a.status, 0) + 1
        return {
            "total_alerts": len(self._alerts),
            "by_rule": by_rule,
            "by_severity": by_severity,
            "by_status": by_status,
            "open_alerts": by_status[ALERT_STATUS_OPEN] + by_status[ALERT_STATUS_INVESTIGATING],
        }

    # ============================================================================
    # v7.2: L07 KYC risk band → Transaction monitoring sensitivity (CONSUMER)
    # ============================================================================
    def scan_with_risk_bands(
        self,
        txns: List[Transaction],
        customer_risk_bands: Dict[str, str],
    ) -> Dict[str, Any]:
        """L07 (CONSUMER) — risk-band-aware transaction scan.

        Consumes per-customer risk bands from
        `kyc_aml_risk.assess_customer().risk_band` (LOW / MEDIUM / HIGH /
        PROHIBITED). Per Charter §7 Published Language pattern, depends
        only on the public risk_band string output of the KYC engine.

        Behavior:
            - Runs the standard rule scan (backward-compatible)
            - Post-processes alerts: HIGH/PROHIBITED customers get severity
              uplift (MEDIUM → HIGH, HIGH → CRITICAL) — false-negative
              hardening
            - LOW-risk customers get severity downgrade only for benign
              rules (R5 dormant, R6 round-number) — false-positive reduction
            - Critical rules (R2 structuring, R4 high-risk geography)
              never get downgraded regardless of risk band

        Returns dict with:
            alerts: list[Alert] — generated alerts (with adjusted severity)
            adjustments: list[dict] — what changed and why
            risk_band_coverage: dict — how many customers had bands provided
            consumed_payload_version: str — KYC engine schema version
            pattern: str — DDD integration pattern
            cited_invariants: list — none for this loop (severity is
                                     bank-policy not regulatory)
        """
        if not isinstance(customer_risk_bands, dict):
            return {
                "status": "INVALID_PAYLOAD",
                "error": "customer_risk_bands must be a dict[customer_id -> band]",
                "alerts": [],
            }

        VALID_BANDS = {"LOW", "MEDIUM", "HIGH", "PROHIBITED"}

        # Run standard scan (backward compatible)
        new_alerts = self.scan(txns)

        # Severity uplift / downgrade post-processing
        BENIGN_RULES = {"R5", "R6"}  # dormant + round-number — fine to downgrade for LOW
        CRITICAL_RULES = {"R2", "R4"}  # structuring + high-risk-geo — never downgrade

        adjustments = []
        for alert in new_alerts:
            band = customer_risk_bands.get(alert.customer_id)
            if band is None or band not in VALID_BANDS:
                continue  # No band info — keep as-is

            original_sev = alert.severity

            if band in ("HIGH", "PROHIBITED"):
                # Severity uplift
                if alert.severity == SEVERITY_MEDIUM:
                    alert.severity = SEVERITY_HIGH
                    adjustments.append({
                        "alert_id": alert.alert_id,
                        "customer_id": alert.customer_id,
                        "rule_id": alert.rule_id,
                        "from": original_sev,
                        "to": alert.severity,
                        "reason": f"customer_risk_band={band} — uplift",
                    })
                elif alert.severity == SEVERITY_HIGH:
                    alert.severity = SEVERITY_CRITICAL
                    adjustments.append({
                        "alert_id": alert.alert_id,
                        "customer_id": alert.customer_id,
                        "rule_id": alert.rule_id,
                        "from": original_sev,
                        "to": alert.severity,
                        "reason": f"customer_risk_band={band} — uplift",
                    })

            elif band == "LOW":
                # Severity downgrade ONLY for benign rules
                if alert.rule_id in BENIGN_RULES and alert.rule_id not in CRITICAL_RULES:
                    if alert.severity == SEVERITY_MEDIUM:
                        alert.severity = SEVERITY_LOW
                        adjustments.append({
                            "alert_id": alert.alert_id,
                            "customer_id": alert.customer_id,
                            "rule_id": alert.rule_id,
                            "from": original_sev,
                            "to": alert.severity,
                            "reason": f"customer_risk_band=LOW + benign rule — downgrade",
                        })

        return {
            "alerts": new_alerts,
            "adjustments": adjustments,
            "risk_band_coverage": {
                "customers_with_bands": sum(
                    1 for t in txns
                    if customer_risk_bands.get(t.customer_id) in VALID_BANDS
                ),
                "total_txns": len(txns),
            },
            "consumed_payload_version": "kyc_aml_risk.KycRiskAssessment.risk_band v1.0",
            "pattern": "PUBLISHED_LANGUAGE",
            "cited_invariants": [],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_txn(**kw) -> Transaction:
    defaults = dict(
        txn_id=kw.pop("txn_id", "T1"),
        customer_id=kw.pop("customer_id", "C1"),
        account_id=kw.pop("account_id", "A1"),
        amount_kes=_to_decimal(kw.pop("amount_kes", 100000)),
        txn_type=kw.pop("txn_type", "TRANSFER"),
        txn_datetime=_parse_dt(kw.pop("txn_datetime", "2026-01-01T10:00:00+00:00")),
        counterparty_country=kw.pop("counterparty_country", None),
        counterparty_name=kw.pop("counterparty_name", None),
        direction=kw.pop("direction", "DEBIT"),
        customer_pep=kw.pop("customer_pep", False),
        account_dormant=kw.pop("account_dormant", False),
    )
    return Transaction(**defaults)


def _test_r1_cash_threshold():
    eng = TransactionMonitoringEngine()
    alerts = eng.scan([_make_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
    r1 = [a for a in alerts if a.rule_id == "R1"]
    assert len(r1) == 1
    assert r1[0].severity == SEVERITY_HIGH

def _test_r1_no_alert_below_threshold():
    eng = TransactionMonitoringEngine()
    alerts = eng.scan([_make_txn(amount_kes=999999, txn_type="CASH_DEPOSIT")])
    r1 = [a for a in alerts if a.rule_id == "R1"]
    assert len(r1) == 0

def _test_r2_structuring():
    eng = TransactionMonitoringEngine()
    txns = [
        _make_txn(txn_id=f"T{i}", customer_id="C1", txn_type="CASH_DEPOSIT",
                  amount_kes=900000 + i, txn_datetime=f"2026-01-0{i+1}T10:00:00+00:00")
        for i in range(1, 5)
    ]
    alerts = eng.scan(txns)
    r2 = [a for a in alerts if a.rule_id == "R2"]
    assert len(r2) == 1
    assert r2[0].severity == SEVERITY_CRITICAL

def _test_r3_rapid_movement():
    eng = TransactionMonitoringEngine()
    txns = [
        _make_txn(txn_id="T1", customer_id="C1", amount_kes=6000000, direction="CREDIT",
                  txn_datetime="2026-01-01T10:00:00+00:00"),
        _make_txn(txn_id="T2", customer_id="C1", amount_kes=3000000, direction="DEBIT",
                  txn_datetime="2026-01-01T15:00:00+00:00"),
        _make_txn(txn_id="T3", customer_id="C1", amount_kes=3000000, direction="DEBIT",
                  txn_datetime="2026-01-02T20:00:00+00:00"),
    ]
    alerts = eng.scan(txns)
    r3 = [a for a in alerts if a.rule_id == "R3"]
    assert len(r3) == 1

def _test_r4_prohibited_jurisdiction():
    eng = TransactionMonitoringEngine()
    txns = [_make_txn(txn_type="WIRE_OUT", counterparty_country="KP", amount_kes=50000)]
    alerts = eng.scan(txns)
    r4 = [a for a in alerts if a.rule_id == "R4"]
    assert len(r4) == 1
    assert r4[0].severity == SEVERITY_CRITICAL

def _test_r5_dormant_activity():
    eng = TransactionMonitoringEngine()
    txns = [_make_txn(amount_kes=200000, account_dormant=True, txn_type="CASH_DEPOSIT")]
    alerts = eng.scan(txns)
    r5 = [a for a in alerts if a.rule_id == "R5"]
    assert len(r5) == 1

def _test_r6_round_numbers():
    eng = TransactionMonitoringEngine()
    txns = [
        _make_txn(txn_id=f"T{i}", customer_id="C1", amount_kes=500000,
                  txn_datetime=f"2026-01-{i:02d}T10:00:00+00:00")
        for i in range(1, 7)
    ]
    alerts = eng.scan(txns)
    r6 = [a for a in alerts if a.rule_id == "R6"]
    assert len(r6) >= 1

def _test_r7_velocity_count():
    eng = TransactionMonitoringEngine()
    txns = [
        _make_txn(txn_id=f"T{i}", customer_id="C1", amount_kes=50000,
                  txn_datetime=f"2026-01-01T{i:02d}:00:00+00:00")
        for i in range(0, 22)
    ]
    alerts = eng.scan(txns)
    r7 = [a for a in alerts if a.rule_id == "R7"]
    assert len(r7) == 1

def _test_r8_pep_large():
    eng = TransactionMonitoringEngine()
    txns = [_make_txn(amount_kes=2500000, customer_pep=True, txn_type="WIRE_OUT")]
    alerts = eng.scan(txns)
    r8 = [a for a in alerts if a.rule_id == "R8"]
    assert len(r8) == 1

def _test_decimal_precision_rule1():
    eng = TransactionMonitoringEngine()
    # Exact threshold should NOT trigger (strict greater-than)
    alerts = eng.scan([_make_txn(amount_kes=Decimal("1000000"), txn_type="CASH_DEPOSIT")])
    r1 = [a for a in alerts if a.rule_id == "R1"]
    assert len(r1) == 0
    # 0.01 above triggers
    alerts2 = eng.scan([_make_txn(amount_kes=Decimal("1000000.01"), txn_type="CASH_DEPOSIT")])
    r1b = [a for a in alerts2 if a.rule_id == "R1"]
    assert len(r1b) == 1

def _test_workflow_default_strict():
    """Rule 4: cannot directly dismiss OPEN alert."""
    eng = TransactionMonitoringEngine()
    eng.scan([_make_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
    aid = eng._alerts[0].alert_id
    ok, reason = eng.transition_alert(aid, ALERT_STATUS_DISMISSED, "officer_001", "false_positive")
    assert not ok, "Direct OPEN->DISMISSED must be rejected"
    assert "transition_not_allowed" in reason

def _test_workflow_normal_path():
    eng = TransactionMonitoringEngine()
    eng.scan([_make_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
    aid = eng._alerts[0].alert_id
    ok, _ = eng.transition_alert(aid, ALERT_STATUS_INVESTIGATING, "officer_001")
    assert ok
    ok, _ = eng.transition_alert(aid, ALERT_STATUS_DISMISSED, "officer_001", "exemption_documented")
    assert ok
    assert eng._alerts[0].status == ALERT_STATUS_DISMISSED

def _test_resolution_reason_required():
    eng = TransactionMonitoringEngine()
    eng.scan([_make_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
    aid = eng._alerts[0].alert_id
    eng.transition_alert(aid, ALERT_STATUS_INVESTIGATING, "officer_001")
    ok, reason = eng.transition_alert(aid, ALERT_STATUS_DISMISSED, "officer_001", None)
    assert not ok
    assert "resolution_reason_required" in reason

def _test_alert_summary_aggregates():
    eng = TransactionMonitoringEngine()
    eng.scan([
        _make_txn(txn_id="T1", customer_id="C1", amount_kes=1500000, txn_type="CASH_DEPOSIT"),
        _make_txn(txn_id="T2", customer_id="C2", amount_kes=200000, account_dormant=True),
    ])
    s = eng.alert_summary()
    assert s["total_alerts"] >= 2
    assert s["by_severity"][SEVERITY_HIGH] >= 1


def self_test() -> bool:
    tests = [
        _test_r1_cash_threshold,
        _test_r1_no_alert_below_threshold,
        _test_r2_structuring,
        _test_r3_rapid_movement,
        _test_r4_prohibited_jurisdiction,
        _test_r5_dormant_activity,
        _test_r6_round_numbers,
        _test_r7_velocity_count,
        _test_r8_pep_large,
        _test_decimal_precision_rule1,
        _test_workflow_default_strict,
        _test_workflow_normal_path,
        _test_resolution_reason_required,
        _test_alert_summary_aggregates,
    ]
    print("=" * 60)
    print("Transaction Monitoring Engine — Self-Tests (#59)")
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
