"""
================================================================================
A2Z MIS 360 — Standard #65: Operations Dashboard Engine
================================================================================

Risk classification: Cat B (deterministic KPI aggregation, no ML)

Aggregates operations KPIs across branches and back-office units. Produces a
unified ops scorecard with traffic-light status against targets.

Five KPI families (deterministic):
    - VOLUME           : transactions processed
    - QUALITY          : error rate, rework rate
    - TIMELINESS       : same-day completion %, SLA met %
    - PRODUCTIVITY     : transactions per FTE
    - COST             : cost per transaction

Status thresholds (vs target):
    GREEN      : actual >= target × 0.95 (within 5% below or any above)
    AMBER      : actual >= target × 0.85 (5-15% below target)
    RED        : actual <  target × 0.85 (more than 15% below target)
    NO_DATA    : actual is None or target is None or target <= 0

Note: for KPIs where lower is better (error rate, cost), thresholds invert.

Honesty rules applied:
    Rule 1: ratios = None when denominator <= 0 (e.g. cost-per-txn with zero txns)
    Rule 6: missing target → status = NO_DATA (NEVER assumed met)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

# Spec literals
KPI_FAMILIES: Tuple[str, ...] = (
    "VOLUME", "QUALITY", "TIMELINESS", "PRODUCTIVITY", "COST",
)

# KPIs where lower is better (lower-is-better)
LOWER_IS_BETTER_KPIS: Tuple[str, ...] = (
    "ERROR_RATE_PCT", "REWORK_RATE_PCT",
    "COST_PER_TRANSACTION_KES", "CYCLE_TIME_HOURS",
)

# Status thresholds (proportion of target)
STATUS_GREEN_THRESHOLD = Decimal("0.95")
STATUS_AMBER_THRESHOLD = Decimal("0.85")

STATUS_GREEN = "GREEN"
STATUS_AMBER = "AMBER"
STATUS_RED = "RED"
STATUS_NO_DATA = "NO_DATA"

VALID_STATUSES: Tuple[str, ...] = (STATUS_GREEN, STATUS_AMBER, STATUS_RED, STATUS_NO_DATA)

# Operating units types
UNIT_TYPES: Tuple[str, ...] = ("BRANCH", "BACK_OFFICE", "CALL_CENTER", "OPERATIONS_HUB")


@dataclass
class OpsKpiReading:
    kpi_id: str
    kpi_family: str
    kpi_name: str  # e.g. "ERROR_RATE_PCT"
    unit_id: str
    unit_type: str
    actual: Optional[Decimal]
    target: Optional[Decimal]
    period: str
    direction: str = "HIGHER_IS_BETTER"  # or LOWER_IS_BETTER
    unit_of_measure: str = ""  # e.g. "txn", "%", "KES"


def _to_decimal(amount: Any) -> Optional[Decimal]:
    if amount is None:
        return None
    if isinstance(amount, Decimal):
        return amount
    return Decimal(str(amount))


class OperationsDashboardEngine:
    """Deterministic operations KPI aggregation + status computation."""

    @staticmethod
    def compute_status(
        actual: Optional[Decimal],
        target: Optional[Decimal],
        direction: str = "HIGHER_IS_BETTER",
    ) -> Dict[str, Any]:
        """
        Compute traffic-light status for one KPI reading.
        Rule 1: returns NO_DATA when target<=0 or actual is None.
        """
        if actual is None or target is None:
            return {"status": STATUS_NO_DATA, "achievement_pct": None, "reason": "missing_actual_or_target"}
        if target <= Decimal("0"):
            return {"status": STATUS_NO_DATA, "achievement_pct": None, "reason": "target_zero_or_negative"}

        if direction == "LOWER_IS_BETTER":
            # achievement = target / actual (so lower actual = better)
            if actual <= Decimal("0"):
                # Actual is zero or negative — effectively unbounded "perfect"
                return {"status": STATUS_GREEN, "achievement_pct": None, "reason": "actual_zero_or_negative"}
            achievement = (target / actual)
        else:
            achievement = (actual / target)

        # Status thresholds
        if achievement >= STATUS_GREEN_THRESHOLD:
            status = STATUS_GREEN
        elif achievement >= STATUS_AMBER_THRESHOLD:
            status = STATUS_AMBER
        else:
            status = STATUS_RED

        return {
            "status": status,
            "achievement_pct": round(float(achievement) * 100, 2),
            "actual": str(actual),
            "target": str(target),
            "direction": direction,
        }

    @classmethod
    def unit_scorecard(
        cls,
        readings: List[OpsKpiReading],
        unit_id: str,
    ) -> Dict[str, Any]:
        """Per-unit scorecard with traffic-light status per KPI."""
        unit_readings = [r for r in readings if r.unit_id == unit_id]
        if not unit_readings:
            return {
                "unit_id": unit_id,
                "kpi_count": 0,
                "kpis": [],
                "rolled_status": STATUS_NO_DATA,
                "reason": "no_readings_for_unit",
            }

        kpis = []
        green = amber = red = no_data = 0
        for r in unit_readings:
            st = cls.compute_status(r.actual, r.target, r.direction)
            kpis.append({
                "kpi_id": r.kpi_id,
                "kpi_name": r.kpi_name,
                "kpi_family": r.kpi_family,
                **st,
            })
            if st["status"] == STATUS_GREEN: green += 1
            elif st["status"] == STATUS_AMBER: amber += 1
            elif st["status"] == STATUS_RED: red += 1
            else: no_data += 1

        # Rolled status: any RED → RED, else any AMBER → AMBER, else GREEN; NO_DATA only if all NO_DATA
        if red > 0:
            rolled = STATUS_RED
        elif amber > 0:
            rolled = STATUS_AMBER
        elif green > 0:
            rolled = STATUS_GREEN
        else:
            rolled = STATUS_NO_DATA

        return {
            "unit_id": unit_id,
            "kpi_count": len(unit_readings),
            "rolled_status": rolled,
            "status_counts": {STATUS_GREEN: green, STATUS_AMBER: amber, STATUS_RED: red, STATUS_NO_DATA: no_data},
            "kpis": kpis,
        }

    @classmethod
    def portfolio_summary(
        cls,
        readings: List[OpsKpiReading],
        unit_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bank-wide rollup, optionally filtered by unit_type."""
        filtered = readings if unit_type is None else [r for r in readings if r.unit_type == unit_type]
        unit_ids = sorted({r.unit_id for r in filtered})

        family_summary: Dict[str, Dict[str, int]] = {
            f: {STATUS_GREEN: 0, STATUS_AMBER: 0, STATUS_RED: 0, STATUS_NO_DATA: 0}
            for f in KPI_FAMILIES
        }
        unit_rolls = []
        for uid in unit_ids:
            sc = cls.unit_scorecard(filtered, uid)
            unit_rolls.append({"unit_id": uid, "rolled_status": sc["rolled_status"]})
            for k in sc["kpis"]:
                fam = k["kpi_family"]
                if fam in family_summary:
                    family_summary[fam][k["status"]] = family_summary[fam].get(k["status"], 0) + 1

        # Bank-wide rollup
        all_statuses = [u["rolled_status"] for u in unit_rolls]
        if STATUS_RED in all_statuses:
            bank_status = STATUS_RED
        elif STATUS_AMBER in all_statuses:
            bank_status = STATUS_AMBER
        elif STATUS_GREEN in all_statuses:
            bank_status = STATUS_GREEN
        else:
            bank_status = STATUS_NO_DATA

        return {
            "unit_type_filter": unit_type,
            "total_units": len(unit_ids),
            "bank_status": bank_status,
            "by_family": family_summary,
            "units": unit_rolls,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_reading(**kw):
    defaults = dict(
        kpi_id="K1", kpi_family="VOLUME", kpi_name="TXN_COUNT",
        unit_id="BR001", unit_type="BRANCH",
        actual=_to_decimal(950), target=_to_decimal(1000),
        period="2025_M12", direction="HIGHER_IS_BETTER",
    )
    defaults.update(kw)
    return OpsKpiReading(**defaults)


def _test_status_green_higher_better():
    r = OperationsDashboardEngine.compute_status(_to_decimal(950), _to_decimal(1000))
    assert r["status"] == STATUS_GREEN  # 95% achievement


def _test_status_amber_higher_better():
    r = OperationsDashboardEngine.compute_status(_to_decimal(900), _to_decimal(1000))
    assert r["status"] == STATUS_AMBER  # 90%


def _test_status_red_higher_better():
    r = OperationsDashboardEngine.compute_status(_to_decimal(500), _to_decimal(1000))
    assert r["status"] == STATUS_RED  # 50%


def _test_lower_is_better():
    """Error rate: lower is better. actual=2%, target=5% → GREEN (target/actual=2.5)."""
    r = OperationsDashboardEngine.compute_status(
        _to_decimal(2), _to_decimal(5), direction="LOWER_IS_BETTER"
    )
    assert r["status"] == STATUS_GREEN


def _test_lower_is_better_breach():
    """Error rate actual=10%, target=5% → RED."""
    r = OperationsDashboardEngine.compute_status(
        _to_decimal(10), _to_decimal(5), direction="LOWER_IS_BETTER"
    )
    assert r["status"] == STATUS_RED


def _test_no_data_target_zero_rule1():
    r = OperationsDashboardEngine.compute_status(_to_decimal(100), _to_decimal(0))
    assert r["status"] == STATUS_NO_DATA
    assert r["reason"] == "target_zero_or_negative"


def _test_no_data_missing_actual_rule6():
    """Rule 6: missing actual → NO_DATA, not assumed met."""
    r = OperationsDashboardEngine.compute_status(None, _to_decimal(100))
    assert r["status"] == STATUS_NO_DATA


def _test_unit_scorecard_basic():
    readings = [
        _make_reading(kpi_id="K1", actual=_to_decimal(1000)),  # GREEN
        _make_reading(kpi_id="K2", actual=_to_decimal(800)),  # AMBER actually 80% < 85
        _make_reading(kpi_id="K3", actual=_to_decimal(500)),  # RED
    ]
    sc = OperationsDashboardEngine.unit_scorecard(readings, "BR001")
    assert sc["kpi_count"] == 3
    assert sc["rolled_status"] == STATUS_RED  # any RED → RED


def _test_rolled_status_amber():
    readings = [
        _make_reading(kpi_id="K1", actual=_to_decimal(1000)),  # GREEN
        _make_reading(kpi_id="K2", actual=_to_decimal(900)),  # AMBER
    ]
    sc = OperationsDashboardEngine.unit_scorecard(readings, "BR001")
    assert sc["rolled_status"] == STATUS_AMBER


def _test_unit_no_readings():
    sc = OperationsDashboardEngine.unit_scorecard([], "BR001")
    assert sc["rolled_status"] == STATUS_NO_DATA


def _test_portfolio_summary():
    readings = [
        _make_reading(kpi_id="K1", unit_id="BR001", actual=_to_decimal(1000)),
        _make_reading(kpi_id="K2", unit_id="BR002", actual=_to_decimal(500)),
    ]
    s = OperationsDashboardEngine.portfolio_summary(readings)
    assert s["total_units"] == 2
    assert s["bank_status"] == STATUS_RED  # BR002 has 50% achievement


def _test_kpi_families_byte_for_byte():
    for f in ("VOLUME", "QUALITY", "TIMELINESS", "PRODUCTIVITY", "COST"):
        assert f in KPI_FAMILIES


def self_test() -> bool:
    tests = [
        _test_status_green_higher_better,
        _test_status_amber_higher_better,
        _test_status_red_higher_better,
        _test_lower_is_better,
        _test_lower_is_better_breach,
        _test_no_data_target_zero_rule1,
        _test_no_data_missing_actual_rule6,
        _test_unit_scorecard_basic,
        _test_rolled_status_amber,
        _test_unit_no_readings,
        _test_portfolio_summary,
        _test_kpi_families_byte_for_byte,
    ]
    print("=" * 60)
    print("Operations Dashboard Engine — Self-Tests (#65)")
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
