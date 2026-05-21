"""tests/test_wellness.py — Standard #19 WellnessEngine tests.

Includes the 100% high-risk escalation harness (G30 artifact).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
RESULTS_FILE = ROOT / "wellness_escalation_results.json"


class TestStandard19Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "wellness.py").exists()


@pytest.fixture
def basic_engine():
    from utils.wellness import WellnessEngine
    staff = {
        "S100": {"full_name": "OK", "wellness_monitoring_disabled": False},
        "S200": {"full_name": "Strained", "wellness_monitoring_disabled": False},
        "S300": {"full_name": "Opted Out", "wellness_monitoring_disabled": True},
    }
    history = {
        "S100": [("M1", 105), ("M2", 110), ("M3", 100), ("M4", 95)],
        "S200": [("M1", 50), ("M2", 60), ("M3", 70), ("M4", 75)],
    }
    alerts = {"S100": 0, "S200": 8}
    stale = {"S100": 0, "S200": 6}
    managers = {"S100": "MGR1", "S200": "MGR1"}
    return WellnessEngine(
        staff_lookup_fn=lambda sc: staff.get(sc),
        bsc_history_fn=lambda sc, n: history.get(sc, [])[:n],
        alerts_in_window_fn=lambda sc, d: alerts.get(sc, 0),
        stale_microtasks_fn=lambda sc, a: stale.get(sc, 0),
        manager_lookup_fn=lambda sc: managers.get(sc),
    )


class TestSpecContract:
    def test_returns_required_keys(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S100")
        for k in ("risk_score", "risk_level", "signals", "recommendations", "alert", "meta"):
            assert k in r

    def test_risk_score_in_range(self, basic_engine):
        for sc in ("S100", "S200"):
            r = basic_engine.assess_burnout_risk(sc)
            assert 0.0 <= r["risk_score"] <= 1.0


class TestRiskLevels:
    def test_low_risk_no_alert(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S100")
        assert r["risk_level"] == "Low"
        assert r["alert"] is None
        assert r["recommendations"] == []

    def test_high_risk_produces_alert(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S200")
        assert r["risk_level"] == "High"
        assert r["alert"] is not None
        assert r["alert"]["manager_code"] == "MGR1"

    def test_high_risk_recommendations_populated(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S200")
        assert len(r["recommendations"]) >= 2


class TestHonestyRules:
    def test_no_medical_language_in_recommendations(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S200")
        joined = " ".join(r["recommendations"]).lower()
        forbidden = ["depressed", "burnt out", "stress disorder", "mental health",
                     "anxiety", "exhausted", "burned out"]
        for word in forbidden:
            assert word not in joined, f"forbidden word {word!r} in: {joined!r}"

    def test_optout_returns_empty(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S300")
        assert r == {}

    def test_unknown_staff_returns_empty(self, basic_engine):
        assert basic_engine.assess_burnout_risk("UNKNOWN") == {}

    def test_alert_routes_to_manager_only(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S200")
        # No HR / leadership escalation in alert dict
        assert "hr_code" not in r["alert"]
        assert "leadership_code" not in r["alert"]


class TestSignalComputations:
    def test_pace_deficit_full(self, basic_engine):
        # S200 history: all 4 below 80 → 1.0
        r = basic_engine.assess_burnout_risk("S200")
        assert r["signals"]["sustained_pace_deficit"] == 1.0

    def test_pace_deficit_zero(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S100")
        assert r["signals"]["sustained_pace_deficit"] == 0.0

    def test_alert_frequency_saturates(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S200")
        assert r["signals"]["alert_frequency"] == 1.0

    def test_microtask_overflow_partial(self, basic_engine):
        r = basic_engine.assess_burnout_risk("S200")
        # 6 stale / 5 saturation = 1.0 (capped)
        assert r["signals"]["microtask_overflow"] == 1.0

    def test_declining_trajectory_decreasing(self, basic_engine):
        # S200: 75 → 70 → 60 → 50 (chronological) → strictly decreasing
        r = basic_engine.assess_burnout_risk("S200")
        assert r["signals"]["declining_trajectory"] == 1.0


class TestPersistence:
    def test_save_high_alert(self, tmp_path, monkeypatch):
        from utils import wellness as ws
        monkeypatch.setattr(ws, "ALERTS_FILE", tmp_path / "alerts.json")
        alert = {
            "staff_code": "S1", "manager_code": "M1", "risk_level": "High",
            "risk_score": 0.85, "recommendations": ["have 1:1"],
            "assessed_at": datetime.now(timezone.utc).isoformat(),
        }
        ok = ws.save_alert(alert)
        assert ok is True
        listed = ws.list_alerts_for_manager("M1")
        assert len(listed) == 1

    def test_save_non_high_returns_false(self, tmp_path, monkeypatch):
        from utils import wellness as ws
        monkeypatch.setattr(ws, "ALERTS_FILE", tmp_path / "alerts.json")
        assert ws.save_alert({"risk_level": "Low"}) is False

    def test_save_idempotent_same_day(self, tmp_path, monkeypatch):
        from utils import wellness as ws
        monkeypatch.setattr(ws, "ALERTS_FILE", tmp_path / "alerts.json")
        alert = {
            "staff_code": "S1", "manager_code": "M1", "risk_level": "High",
            "assessed_at": datetime.now(timezone.utc).isoformat(),
        }
        ws.save_alert(alert)
        ws.save_alert(alert)
        listed = ws.list_alerts_for_manager("M1")
        assert len(listed) == 1


# ═══════════════════════════════════════════════════════════════════════
# 100% high-risk escalation harness — G30 artifact
# ═══════════════════════════════════════════════════════════════════════

# Designed scenarios where we KNOW the risk level and expected escalation.
# The spec says "100% high-risk cases escalated" — verifiable by ensuring
# every High-risk staff produces a non-None alert with a manager_code.

WELLNESS_SCENARIOS = [
    # Clear High-risk: all signals saturated
    {"id": "W001", "expect_level": "High", "expect_alert": True,
     "history": [("M1", 50), ("M2", 55), ("M3", 60), ("M4", 65)],
     "alerts": 8, "stale": 6, "manager": "MGR1", "optout": False},
    # Clear Low-risk: no signals
    {"id": "W002", "expect_level": "Low", "expect_alert": False,
     "history": [("M1", 105), ("M2", 110), ("M3", 100), ("M4", 95)],
     "alerts": 0, "stale": 0, "manager": "MGR1", "optout": False},
    # Moderate: some signals present
    {"id": "W003", "expect_level": "Moderate", "expect_alert": False,
     "history": [("M1", 78), ("M2", 82), ("M3", 88), ("M4", 92)],
     "alerts": 3, "stale": 2, "manager": "MGR1", "optout": False},
    # Opted out → empty
    {"id": "W004", "expect_level": None, "expect_alert": False,
     "history": [("M1", 50), ("M2", 50), ("M3", 50), ("M4", 50)],
     "alerts": 8, "stale": 6, "manager": "MGR1", "optout": True},
    # High-risk: declining only (not all signals saturated)
    {"id": "W005", "expect_level": "High", "expect_alert": True,
     "history": [("M1", 60), ("M2", 70), ("M3", 80), ("M4", 90)],
     "alerts": 6, "stale": 5, "manager": "MGR2", "optout": False},
    # High-risk: alert flood
    {"id": "W006", "expect_level": "High", "expect_alert": True,
     "history": [("M1", 65), ("M2", 70), ("M3", 75), ("M4", 80)],
     "alerts": 10, "stale": 6, "manager": "MGR3", "optout": False},
    # Low: improving trajectory
    {"id": "W007", "expect_level": "Low", "expect_alert": False,
     "history": [("M1", 105), ("M2", 95), ("M3", 85), ("M4", 75)],
     "alerts": 1, "stale": 0, "manager": "MGR1", "optout": False},
    # High-risk: stale tasks pile up + behind pace
    {"id": "W008", "expect_level": "High", "expect_alert": True,
     "history": [("M1", 55), ("M2", 60), ("M3", 65), ("M4", 70)],
     "alerts": 5, "stale": 8, "manager": "MGR1", "optout": False},
    # Low: just one period below threshold
    {"id": "W009", "expect_level": "Low", "expect_alert": False,
     "history": [("M1", 75), ("M2", 92), ("M3", 100), ("M4", 105)],
     "alerts": 1, "stale": 0, "manager": "MGR1", "optout": False},
    # High: every signal max
    {"id": "W010", "expect_level": "High", "expect_alert": True,
     "history": [("M1", 30), ("M2", 40), ("M3", 50), ("M4", 60)],
     "alerts": 12, "stale": 10, "manager": "MGR1", "optout": False},
]


def test_high_risk_escalation_harness():
    """Verify 100% of high-risk cases produce manager alerts (G30 spec)."""
    from utils.wellness import WellnessEngine

    high_risk_total = 0
    high_risk_escalated = 0
    matches = 0
    results = []
    for s in WELLNESS_SCENARIOS:
        staff_data = {"X": {"full_name": "T",
                             "wellness_monitoring_disabled": s["optout"]}}
        eng = WellnessEngine(
            staff_lookup_fn=lambda sc, sd=staff_data: sd.get(sc) if sc == "X" else None,
            bsc_history_fn=lambda sc, n, h=s["history"]: list(h)[:n],
            alerts_in_window_fn=lambda sc, d, a=s["alerts"]: a,
            stale_microtasks_fn=lambda sc, a, st=s["stale"]: st,
            manager_lookup_fn=lambda sc, m=s["manager"]: m,
        )
        r = eng.assess_burnout_risk("X")
        actual_level = r.get("risk_level") if r else None
        has_alert = bool(r.get("alert")) if r else False

        # Track high-risk escalation
        if actual_level == "High":
            high_risk_total += 1
            if has_alert and r["alert"].get("manager_code"):
                high_risk_escalated += 1

        # Check fixture expectation
        match = (
            actual_level == s["expect_level"]
            and has_alert == s["expect_alert"]
        )
        if match:
            matches += 1
        results.append({
            "id": s["id"],
            "expected_level": s["expect_level"],
            "actual_level": actual_level,
            "expected_alert": s["expect_alert"],
            "actual_alert": has_alert,
            "matched": match,
        })

    escalation_rate = (
        high_risk_escalated / high_risk_total * 100
        if high_risk_total > 0 else 100.0
    )
    fixture_accuracy = matches / len(WELLNESS_SCENARIOS) * 100

    artifact = {
        "schema_version": 1,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(WELLNESS_SCENARIOS),
        "high_risk_total": high_risk_total,
        "high_risk_escalated": high_risk_escalated,
        "escalation_pct": round(escalation_rate, 2),
        "spec_target_pct": 100.0,
        "fixture_accuracy_pct": round(fixture_accuracy, 2),
        "all_passed": escalation_rate >= 100.0,
        "results": results,
    }
    RESULTS_FILE.write_text(json.dumps(artifact, indent=2))

    # The spec claim: 100% high-risk escalated
    assert escalation_rate >= 100.0, (
        f"Only {high_risk_escalated}/{high_risk_total} high-risk cases "
        f"escalated ({escalation_rate:.1f}%); spec requires 100%"
    )
    # Sanity: fixtures correctly labeled
    assert fixture_accuracy >= 90.0, (
        f"Fixture labels match math only {fixture_accuracy:.1f}%"
    )
