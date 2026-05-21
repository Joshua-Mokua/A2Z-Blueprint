"""
================================================================================
A2Z MIS 360 — Standard #380: SLA Monitoring Engine
================================================================================

Risk classification: Cat B (deterministic real-time SLA tracking)

Real-time SLA monitoring engine. Every transaction / event tagged
to an SLA produces an observation; engine computes running compliance
against SLA target.

Public API:
    record_event(sla_id, event_id, started_at, completed_at, ...)
    compute_compliance(sla_id, period)    -- {compliance_pct, observations, breaches}
    near_breach_alerts(sla_id)            -- events within near-breach window
    monitoring_summary(period)            -- bank-wide compliance summary

Near-breach threshold byte-for-byte:
    NEAR_BREACH_PCT_OF_TARGET = Decimal("80")
    (event consuming ≥80% of allowed time/threshold = near-breach signal)

Honesty rules:
    Rule 1: compliance_pct = None when observations==0 (undefined)
    Rule 6: events with missing started_at/completed_at excluded
            with count surfaced in `excluded_count`

================================================================================
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

NEAR_BREACH_PCT_OF_TARGET: Decimal = Decimal("80")

OBSERVATION_STATUSES: Tuple[str, ...] = (
    "WITHIN_SLA",
    "NEAR_BREACH",
    "BREACHED",
    "EXEMPT",
)


# ────────────────────────────────────────────────────────────────────
# Data classes
# ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SlaObservation:
    """Single SLA event observation."""
    sla_id: str
    event_id: str
    started_at: str         # ISO datetime
    completed_at: Optional[str]  # ISO datetime; None if in-flight
    elapsed_value: Decimal  # actual measured value (e.g. days, percent)
    target_value: Decimal
    direction: str          # "min" or "max"
    status: str             # one of OBSERVATION_STATUSES


# ────────────────────────────────────────────────────────────────────
# SlaMonitoringEngine
# ────────────────────────────────────────────────────────────────────

class SlaMonitoringEngine:
    """
    Real-time SLA monitoring. Records observations and computes
    running compliance.
    """

    def __init__(self, observations_path: Optional[Path] = None):
        self.observations_path = (
            observations_path
            if observations_path is not None
            else Path(__file__).parent.parent / "data" / "sla_observations.json"
        )

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            d = _db.dual_load(
                self.observations_path,
                table="sla_observations",
                index_cols=("observation_id",))
            return d if isinstance(d, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.observations_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(
                self.observations_path,
                data=records,
                table="sla_observations",
                pk_col="observation_id")
            return True
        except Exception:
            return False

    def _classify_observation(
        self,
        elapsed: Decimal,
        target: Decimal,
        direction: str,
    ) -> str:
        """
        Classify observation per direction:

        - direction='max' (e.g. response time, max 30 days):
            elapsed > target → BREACHED
            elapsed >= 80% of target → NEAR_BREACH
            else → WITHIN_SLA

        - direction='min' (e.g. uptime, min 99.5%):
            Assumes percentage-style metric (0-100). Near-breach margin
            is fraction of "danger zone" (100 − target):
                elapsed < target → BREACHED
                elapsed in [target, target + 0.2×(100−target)] → NEAR_BREACH
                else → WITHIN_SLA

            For target=99.5: danger=0.5pp; near-breach in [99.5, 99.6];
            99.7 → WITHIN_SLA.
        """
        if direction == "max":
            if elapsed > target:
                return "BREACHED"
            ratio_pct = (elapsed / target) * Decimal("100")
            if ratio_pct >= NEAR_BREACH_PCT_OF_TARGET:
                return "NEAR_BREACH"
            return "WITHIN_SLA"
        else:  # direction == "min"
            if elapsed < target:
                return "BREACHED"
            # Danger zone = (100 − target). Near-breach margin = 20% of danger zone.
            # Cap at 100 (percent metric assumption).
            danger_zone = Decimal("100") - target
            if danger_zone <= 0:
                # target == 100% — only exactly-at-target is near-breach
                margin = Decimal("0")
            else:
                margin = danger_zone * (Decimal("100") - NEAR_BREACH_PCT_OF_TARGET) / Decimal("100")
            if elapsed <= target + margin:
                return "NEAR_BREACH"
            return "WITHIN_SLA"

    def record_event(
        self,
        sla_id: str,
        event_id: str,
        started_at: str,
        completed_at: Optional[str],
        elapsed_value: Decimal,
        target_value: Decimal,
        direction: str,
    ) -> Dict[str, Any]:
        """
        Record observation. Returns {recorded, observation, status}.

        Rule 6: missing started_at/completed_at → status="EXEMPT"
        with reason captured (caller can decide to retry later).
        """
        # Rule 6: missing data → exempt observation
        if not started_at or elapsed_value is None or target_value is None:
            return {
                "recorded": False,
                "reason": "missing_required_fields",
                "sla_id": sla_id,
                "event_id": event_id,
            }

        try:
            elapsed_d = Decimal(str(elapsed_value))
            target_d = Decimal(str(target_value))
        except (ValueError, TypeError):
            return {
                "recorded": False,
                "reason": "non_decimal_values",
                "sla_id": sla_id,
                "event_id": event_id,
            }

        if target_d <= 0:
            return {
                "recorded": False,
                "reason": "target_value_not_positive",
                "sla_id": sla_id,
                "event_id": event_id,
            }

        status = self._classify_observation(elapsed_d, target_d, direction)

        records = self._load()
        observation = {
            "sla_id": sla_id,
            "event_id": event_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "elapsed_value": str(elapsed_d),
            "target_value": str(target_d),
            "direction": direction,
            "status": status,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(observation)
        ok = self._save(records)

        return {
            "recorded": ok,
            "observation": observation,
            "status": status,
        }

    def compute_compliance(
        self,
        sla_id: str,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compute compliance % for an SLA over a period.

        Returns:
            {compliance_pct, total_observations, within_sla,
             near_breach, breached, exempt, excluded_count, reason}

        Rule 1: compliance_pct = None when no qualifying observations
        """
        records = self._load()

        # Filter by sla_id and period.
        # Period boundaries match against the event's started_at (the
        # time the event actually occurred), not recorded_at (when the
        # observation was logged). This ensures that past-period queries
        # for events recorded today still return correctly.
        filtered = []
        excluded = 0
        for r in records:
            if r.get("sla_id") != sla_id:
                continue
            event_time = r.get("started_at") or r.get("completed_at") or r.get("recorded_at", "")
            if period_start and event_time < period_start:
                continue
            if period_end and event_time > period_end:
                continue
            if r.get("status") not in OBSERVATION_STATUSES:
                excluded += 1
                continue
            filtered.append(r)

        total = len(filtered)
        if total == 0:
            return {
                "compliance_pct": None,
                "total_observations": 0,
                "within_sla": 0,
                "near_breach": 0,
                "breached": 0,
                "exempt": 0,
                "excluded_count": excluded,
                "reason": "no_observations_for_period",
            }

        within = sum(1 for r in filtered if r["status"] == "WITHIN_SLA")
        near = sum(1 for r in filtered if r["status"] == "NEAR_BREACH")
        breached = sum(1 for r in filtered if r["status"] == "BREACHED")
        exempt = sum(1 for r in filtered if r["status"] == "EXEMPT")

        # Compliance: WITHIN_SLA + NEAR_BREACH count as compliant; BREACHED does not.
        # EXEMPT excluded from denominator (not a real observation).
        denominator = within + near + breached
        if denominator == 0:
            return {
                "compliance_pct": None,
                "total_observations": total,
                "within_sla": within,
                "near_breach": near,
                "breached": breached,
                "exempt": exempt,
                "excluded_count": excluded,
                "reason": "all_observations_exempt",
            }

        compliance_pct = (Decimal(within + near) / Decimal(denominator)) * Decimal("100")

        return {
            "compliance_pct": compliance_pct.quantize(Decimal("0.01")),
            "total_observations": total,
            "within_sla": within,
            "near_breach": near,
            "breached": breached,
            "exempt": exempt,
            "excluded_count": excluded,
            "reason": None,
        }

    def near_breach_alerts(self, sla_id: str) -> List[Dict[str, Any]]:
        """Return active near-breach observations for an SLA."""
        records = self._load()
        return [
            r for r in records
            if r.get("sla_id") == sla_id and r.get("status") == "NEAR_BREACH"
        ]

    def monitoring_summary(
        self,
        period_start: Optional[str] = None,
        period_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bank-wide SLA monitoring summary across all SLAs in period."""
        records = self._load()

        # Filter by period — use event time (started_at) not recorded_at
        filtered = [
            r for r in records
            if (not period_start or
                (r.get("started_at") or r.get("recorded_at", "")) >= period_start)
            and (not period_end or
                 (r.get("started_at") or r.get("recorded_at", "")) <= period_end)
        ]

        # Group by sla_id
        by_sla: Dict[str, Dict[str, int]] = {}
        for r in filtered:
            sla_id = r.get("sla_id")
            if not sla_id:
                continue
            if sla_id not in by_sla:
                by_sla[sla_id] = {
                    "WITHIN_SLA": 0, "NEAR_BREACH": 0,
                    "BREACHED": 0, "EXEMPT": 0,
                }
            status = r.get("status", "EXEMPT")
            if status in by_sla[sla_id]:
                by_sla[sla_id][status] += 1

        # Top breaching SLAs
        top_breaching = sorted(
            by_sla.items(),
            key=lambda x: x[1]["BREACHED"],
            reverse=True,
        )[:5]

        return {
            "total_observations": len(filtered),
            "unique_slas": len(by_sla),
            "by_sla": by_sla,
            "top_breaching": [{"sla_id": k, **v} for k, v in top_breaching],
        }


# ────────────────────────────────────────────────────────────────────
# Self-test
# ────────────────────────────────────────────────────────────────────

def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sla_observations.json"
        engine = SlaMonitoringEngine(observations_path=path)

        # Test 1: WITHIN_SLA — response time well under target
        result = engine.record_event(
            sla_id="SLA-001",
            event_id="EVT-001",
            started_at="2026-04-01T10:00:00",
            completed_at="2026-04-05T10:00:00",
            elapsed_value=Decimal("4"),  # 4 days
            target_value=Decimal("30"),  # max 30 days
            direction="max",
        )
        assert result["recorded"]
        assert result["status"] == "WITHIN_SLA", f"Got {result['status']}"

        # Test 2: NEAR_BREACH — 25 of 30 days = 83% of target
        result = engine.record_event(
            sla_id="SLA-001", event_id="EVT-002",
            started_at="2026-04-01T10:00:00",
            completed_at="2026-04-26T10:00:00",
            elapsed_value=Decimal("25"),
            target_value=Decimal("30"),
            direction="max",
        )
        assert result["status"] == "NEAR_BREACH", f"Got {result['status']}"

        # Test 3: BREACHED — 35 of 30 days
        result = engine.record_event(
            sla_id="SLA-001", event_id="EVT-003",
            started_at="2026-04-01T10:00:00",
            completed_at="2026-05-06T10:00:00",
            elapsed_value=Decimal("35"),
            target_value=Decimal("30"),
            direction="max",
        )
        assert result["status"] == "BREACHED"

        # Test 4: uptime min direction — 99.7% > 99.5% target → WITHIN_SLA
        result = engine.record_event(
            sla_id="SLA-002", event_id="EVT-004",
            started_at="2026-04-01T00:00:00",
            completed_at="2026-04-30T23:59:59",
            elapsed_value=Decimal("99.7"),
            target_value=Decimal("99.5"),
            direction="min",
        )
        assert result["status"] == "WITHIN_SLA"

        # Test 5: uptime min direction — 99.0% < 99.5% target → BREACHED
        result = engine.record_event(
            sla_id="SLA-002", event_id="EVT-005",
            started_at="2026-04-01T00:00:00",
            completed_at="2026-04-30T23:59:59",
            elapsed_value=Decimal("99.0"),
            target_value=Decimal("99.5"),
            direction="min",
        )
        assert result["status"] == "BREACHED"

        # Test 6: compute_compliance on SLA-001 (3 observations: within, near, breached)
        comp = engine.compute_compliance("SLA-001")
        assert comp["total_observations"] == 3
        assert comp["within_sla"] == 1
        assert comp["near_breach"] == 1
        assert comp["breached"] == 1
        # Compliance = (1 + 1) / (1 + 1 + 1) = 66.67%
        assert comp["compliance_pct"] is not None
        assert abs(comp["compliance_pct"] - Decimal("66.67")) < Decimal("0.1")

        # Test 7: Rule 1 — no observations
        comp = engine.compute_compliance("NONEXISTENT-SLA")
        assert comp["compliance_pct"] is None
        assert comp["reason"] == "no_observations_for_period"

        # Test 8: Rule 6 — missing data
        result = engine.record_event(
            sla_id="SLA-001", event_id="EVT-BAD",
            started_at="", completed_at=None,
            elapsed_value=None, target_value=Decimal("30"),
            direction="max",
        )
        assert not result["recorded"]
        assert result["reason"] == "missing_required_fields"

        # Test 9: monitoring summary
        summary = engine.monitoring_summary()
        assert summary["unique_slas"] == 2  # SLA-001 + SLA-002
        assert summary["total_observations"] == 5

    print("  ✅ sla_monitoring self-test PASS")


if __name__ == "__main__":
    _self_test()
