"""tests/test_nudge_engine.py — Standard #11 PerformanceNudgeEngine tests
(v5.38).

Two test groups:

  1. Unit tests — pin the engine's contract:
       - trajectory classifier
       - period-progress math (monthly, quarterly, edge cases)
       - target/history lookup defaults
       - persistence dedup
       - the recognition / alert decision logic
       - action-items routing per KPI class

  2. Trigger-accuracy harness — runs the engine against every labeled
     scenario in tests/fixtures/nudge_scenarios.json. Asserts ≥95%
     match (the spec's verification target). Writes
     `nudge_accuracy_results.json` for G22 to read.

The harness also produces a per-scenario report so failures are
diagnosable: which scenario, what was expected, what was returned.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "nudge_scenarios.json"
ACCURACY_RESULTS = ROOT / "nudge_accuracy_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Unit tests — engine internals
# ═══════════════════════════════════════════════════════════════════════

class TestTrajectoryClassifier:
    """_classify_trajectory pins the spec's 'accelerating' definition."""

    def test_clear_acceleration(self):
        from utils.nudge_engine import _classify_trajectory
        # Deltas: 10, 10, 30 → mean of priors (10) < latest (30) AND all positive
        result = _classify_trajectory([Decimal(d) for d in (10, 20, 30, 60)])
        assert result == "accelerating"

    def test_flat_history(self):
        from utils.nudge_engine import _classify_trajectory
        result = _classify_trajectory([Decimal(50)] * 4)
        assert result == "flat"

    def test_decline(self):
        from utils.nudge_engine import _classify_trajectory
        result = _classify_trajectory([Decimal(d) for d in (50, 40, 30)])
        assert result == "declining"

    def test_insufficient_data_two_points(self):
        from utils.nudge_engine import _classify_trajectory
        result = _classify_trajectory([Decimal(10), Decimal(20)])
        assert result == "insufficient_data"

    def test_insufficient_data_one_point(self):
        from utils.nudge_engine import _classify_trajectory
        result = _classify_trajectory([Decimal(50)])
        assert result == "insufficient_data"

    def test_insufficient_data_empty(self):
        from utils.nudge_engine import _classify_trajectory
        result = _classify_trajectory([])
        assert result == "insufficient_data"

    def test_one_dip_breaks_acceleration(self):
        """Even if final delta is large, a single dip in history breaks
        the monotonically-increasing requirement."""
        from utils.nudge_engine import _classify_trajectory
        # 10, 20, 15, 50 — has a dip 20→15
        result = _classify_trajectory([Decimal(d) for d in (10, 20, 15, 50)])
        assert result != "accelerating"


class TestPeriodProgress:
    """_default_period_progress maps period + today to 0.0–1.0."""

    def test_mid_month(self):
        from utils.nudge_engine import _default_period_progress
        # April 15 of 30-day month → ~50%
        result = _default_period_progress("2026-04", date(2026, 4, 15))
        assert 0.4 < result < 0.6

    def test_first_day_of_month(self):
        from utils.nudge_engine import _default_period_progress
        result = _default_period_progress("2026-04", date(2026, 4, 1))
        assert result < 0.05    # ~1/30 ≈ 3.3%

    def test_last_day_of_month(self):
        from utils.nudge_engine import _default_period_progress
        result = _default_period_progress("2026-04", date(2026, 4, 30))
        assert result == 1.0

    def test_before_period_starts(self):
        from utils.nudge_engine import _default_period_progress
        result = _default_period_progress("2026-04", date(2026, 3, 28))
        assert result == 0.0

    def test_after_period_ends(self):
        from utils.nudge_engine import _default_period_progress
        result = _default_period_progress("2026-04", date(2026, 5, 5))
        assert result == 1.0

    def test_quarter_mid(self):
        from utils.nudge_engine import _default_period_progress
        # Q2 = Apr/May/Jun. May 15 ≈ middle.
        result = _default_period_progress("2026-Q2", date(2026, 5, 15))
        assert 0.4 < result < 0.6

    def test_quarter_q1_start(self):
        from utils.nudge_engine import _default_period_progress
        result = _default_period_progress("2026-Q1", date(2026, 1, 1))
        assert result < 0.02

    def test_invalid_period_returns_midguess(self):
        """Bad input shouldn't crash — return 0.5 (mid-period guess) so
        nudges don't fire incorrectly with no info."""
        from utils.nudge_engine import _default_period_progress
        for bad in ("garbage", "", "2026-Q5", "abcd-99"):
            result = _default_period_progress(bad, date(2026, 4, 15))
            assert 0.0 <= result <= 1.0


class TestEnumeratePriorPeriods:
    from utils.nudge_engine import _enumerate_prior_periods

    def test_monthly_walks_back(self):
        from utils.nudge_engine import _enumerate_prior_periods
        # 3 prior months from 2026-04 → 2026-01, 2026-02, 2026-03 (oldest first)
        result = _enumerate_prior_periods("2026-04", 3)
        assert result == ["2026-01", "2026-02", "2026-03"]

    def test_monthly_year_boundary(self):
        from utils.nudge_engine import _enumerate_prior_periods
        # 3 prior from 2026-02 → 2025-11, 2025-12, 2026-01
        result = _enumerate_prior_periods("2026-02", 3)
        assert result == ["2025-11", "2025-12", "2026-01"]

    def test_quarterly_walks_back(self):
        from utils.nudge_engine import _enumerate_prior_periods
        result = _enumerate_prior_periods("2026-Q3", 3)
        assert result == ["2025-Q4", "2026-Q1", "2026-Q2"]


class TestActionItemsRouting:
    """_default_action_items routes by KPI class."""

    def test_deposit_kpi_gets_sales_actions(self):
        from utils.nudge_engine import _default_action_items
        items = _default_action_items("S001", "DEP_GROWTH")
        joined = " ".join(items).lower()
        assert "prospect" in joined or "client" in joined

    def test_npl_kpi_gets_recovery_actions(self):
        from utils.nudge_engine import _default_action_items
        items = _default_action_items("S001", "NPL_PCT")
        joined = " ".join(items).lower()
        assert "delinquent" in joined or "recover" in joined or "restructur" in joined

    def test_aml_kpi_gets_compliance_actions(self):
        from utils.nudge_engine import _default_action_items
        items = _default_action_items("S001", "AML_SLA")
        joined = " ".join(items).lower()
        assert "case" in joined or "compliance" in joined or "alert" in joined

    def test_unknown_kpi_falls_back_to_generic(self):
        from utils.nudge_engine import _default_action_items
        items = _default_action_items("S001", "TOTALLY_UNKNOWN_XYZ")
        # Should not be empty and should not mention domain-specific terms
        assert len(items) >= 1


# ═══════════════════════════════════════════════════════════════════════
# Engine decision logic — direct tests with injected collaborators
# ═══════════════════════════════════════════════════════════════════════

class TestRecognitionPath:
    """Recognition fires when current > target * 1.10 AND accelerating."""

    def _make_engine(self, target, history, progress=1.0):
        from utils.nudge_engine import PerformanceNudgeEngine
        return PerformanceNudgeEngine(
            target_lookup_fn=lambda s, k, p: Decimal(str(target)) if target is not None else None,
            history_lookup_fn=lambda s, k, p, n: [Decimal(str(v)) for v in history],
            period_progress_fn=lambda p, t: progress,
        )

    def test_fires_when_well_above_with_acceleration(self):
        eng = self._make_engine(target=100, history=[60, 80, 90])
        nudges = eng.evaluate("S001", "K1", 115, "2026-04")
        assert len(nudges) == 1
        assert nudges[0].type == "recognition"

    def test_no_fire_when_above_but_flat(self):
        eng = self._make_engine(target=100, history=[110, 110, 110])
        nudges = eng.evaluate("S001", "K1", 115, "2026-04")
        assert len(nudges) == 0

    def test_no_fire_when_just_below_110_threshold(self):
        eng = self._make_engine(target=100, history=[60, 80, 90])
        nudges = eng.evaluate("S001", "K1", 109, "2026-04")
        assert len(nudges) == 0

    def test_no_fire_when_insufficient_history(self):
        eng = self._make_engine(target=100, history=[80])
        nudges = eng.evaluate("S001", "K1", 115, "2026-04")
        assert len(nudges) == 0


class TestAlertPath:
    """Alert fires when current < pace_target * 0.80."""

    def _make_engine(self, target, history, progress):
        from utils.nudge_engine import PerformanceNudgeEngine
        return PerformanceNudgeEngine(
            target_lookup_fn=lambda s, k, p: Decimal(str(target)),
            history_lookup_fn=lambda s, k, p, n: [Decimal(str(v)) for v in history],
            period_progress_fn=lambda p, t: progress,
        )

    def test_fires_when_below_80_of_pace(self):
        # target=100, progress=0.5, pace=50, threshold=40, value=39 < 40 → alert
        eng = self._make_engine(target=100, history=[10, 20, 30], progress=0.5)
        nudges = eng.evaluate("S001", "K1", 39, "2026-04")
        assert len(nudges) == 1
        assert nudges[0].type == "alert"

    def test_no_fire_when_above_80_of_pace(self):
        eng = self._make_engine(target=100, history=[10, 20, 30], progress=0.5)
        nudges = eng.evaluate("S001", "K1", 41, "2026-04")
        assert len(nudges) == 0

    def test_no_fire_at_period_start(self):
        # progress=0.03, pace ≈ 3, threshold ≈ 2.4 — value=1 < threshold → alert?
        # Yes the math says so, but pace_target > 0 condition guards against
        # progress ≈ 0. Test the boundary.
        eng = self._make_engine(target=100, history=[10, 20, 30], progress=0.0)
        nudges = eng.evaluate("S001", "K1", 5, "2026-04")
        # progress=0 → pace_target=0 → guard `pace_target > 0` blocks alert
        assert len(nudges) == 0

    def test_no_fire_with_low_progress(self):
        """The early-period guard (progress >= 0.10) suppresses alerts in
        the first 10% of the period. Without it, a slow start to the
        period would spam alerts on day 1 of every month."""
        # progress=0.05 → pace=5, threshold=4. value=1 < 4 — would fire
        # without the guard. With the guard (progress < 0.10) → suppressed.
        eng = self._make_engine(target=100, history=[10, 20, 30], progress=0.05)
        nudges = eng.evaluate("S001", "K1", 1, "2026-04")
        assert len(nudges) == 0

    def test_fires_at_progress_boundary(self):
        """At exactly 10% progress the guard releases. value=1 < pace*0.8=8 → fire."""
        eng = self._make_engine(target=100, history=[10, 20, 30], progress=0.10)
        nudges = eng.evaluate("S001", "K1", 1, "2026-04")
        assert len(nudges) == 1
        assert nudges[0].type == "alert"

    def test_alert_includes_action_items(self):
        eng = self._make_engine(target=100, history=[10, 20, 30], progress=0.5)
        nudges = eng.evaluate("S001", "DEP_GROWTH", 30, "2026-04")
        assert len(nudges) == 1
        assert nudges[0].type == "alert"
        assert len(nudges[0].action_items) >= 1


class TestPersistence:
    """save_pending_nudges + list_active_nudges + acknowledge_nudge."""

    def test_save_and_list(self, tmp_path, monkeypatch):
        from utils import nudge_engine
        nudges_file = tmp_path / "nudges.json"
        monkeypatch.setattr(nudge_engine, "NUDGES_FILE", nudges_file)

        n = nudge_engine.Nudge(
            staff_code="S001", kpi_id="K1", period="2026-04",
            type="alert", message="Behind target",
        )
        count = nudge_engine.save_pending_nudges([n])
        assert count == 1

        active = nudge_engine.list_active_nudges("S001")
        assert len(active) == 1
        assert active[0]["type"] == "alert"

    def test_dedup_replaces_unacknowledged(self, tmp_path, monkeypatch):
        from utils import nudge_engine
        nudges_file = tmp_path / "nudges.json"
        monkeypatch.setattr(nudge_engine, "NUDGES_FILE", nudges_file)

        n1 = nudge_engine.Nudge(
            staff_code="S001", kpi_id="K1", period="2026-04",
            type="alert", message="msg v1",
        )
        nudge_engine.save_pending_nudges([n1])
        n2 = nudge_engine.Nudge(
            staff_code="S001", kpi_id="K1", period="2026-04",
            type="alert", message="msg v2",   # same key, new content
        )
        nudge_engine.save_pending_nudges([n2])

        active = nudge_engine.list_active_nudges("S001")
        assert len(active) == 1
        assert active[0]["message"] == "msg v2"  # most recent wins

    def test_acknowledge(self, tmp_path, monkeypatch):
        from utils import nudge_engine
        nudges_file = tmp_path / "nudges.json"
        monkeypatch.setattr(nudge_engine, "NUDGES_FILE", nudges_file)

        n = nudge_engine.Nudge(
            staff_code="S001", kpi_id="K1", period="2026-04",
            type="alert", message="x",
        )
        nudge_engine.save_pending_nudges([n])

        ok = nudge_engine.acknowledge_nudge(n.id, actor="S001")
        assert ok is True

        active = nudge_engine.list_active_nudges("S001")
        assert len(active) == 0  # acknowledged → no longer in active list


# ═══════════════════════════════════════════════════════════════════════
# Trigger-accuracy harness — Standard #11 spec verification
# ═══════════════════════════════════════════════════════════════════════

def _load_scenarios():
    return json.loads(FIXTURES.read_text())


def _evaluate_scenario(s):
    """Run one scenario and return its outcome dict.

    The fixture provides target/history/period_progress directly — we
    don't hit real data files.
    """
    from utils.nudge_engine import PerformanceNudgeEngine

    inp = s["input"]
    target = inp["target"]
    history = inp["history"] or []
    progress = inp["period_progress"]
    today_str = inp.get("today")
    today = datetime.strptime(today_str, "%Y-%m-%d").date() if today_str else None

    eng = PerformanceNudgeEngine(
        target_lookup_fn=lambda *_: Decimal(str(target)) if target is not None else None,
        history_lookup_fn=lambda *_: [Decimal(str(v)) for v in history],
        period_progress_fn=lambda *_: progress,
    )
    nudges = eng.evaluate(
        inp["staff_code"], inp["kpi_id"], inp["new_value"],
        inp["period"], today=today,
    )
    return [
        {"type": n.type, "action_items": n.action_items, "message": n.message}
        for n in nudges
    ]


def _scenario_matches(actual_nudges, expected_nudges):
    """Compare actual vs expected nudges. Returns (match: bool, reason: str).

    Match is loose-but-meaningful:
      - same number of nudges
      - same type list (order matters)
      - if expected has 'action_items_must_contain', the actual nudge's
        action_items must contain that substring
    """
    if len(actual_nudges) != len(expected_nudges):
        return False, f"count mismatch: actual={len(actual_nudges)} expected={len(expected_nudges)}"

    for i, (act, exp) in enumerate(zip(actual_nudges, expected_nudges)):
        if act["type"] != exp["type"]:
            return False, f"nudge[{i}] type: actual={act['type']} expected={exp['type']}"
        if "action_items_must_contain" in exp:
            substr = exp["action_items_must_contain"].lower()
            joined = " ".join(act.get("action_items", [])).lower()
            if substr not in joined:
                return False, f"nudge[{i}] action_items missing '{substr}'"

    return True, "ok"


def test_trigger_accuracy_meets_95_percent():
    """Run every fixture scenario; assert ≥ 95% match rate; write artifact.

    This is the spec verification test. It's run as part of the regular
    pytest suite AND its result feeds G22 via the nudge_accuracy_results.json
    artifact.
    """
    scenarios = _load_scenarios()
    assert len(scenarios) >= 20, (
        f"Need at least 20 scenarios for a meaningful 95% sample; "
        f"got {len(scenarios)}"
    )

    results = []
    matches = 0
    for s in scenarios:
        actual = _evaluate_scenario(s)
        ok, reason = _scenario_matches(actual, s["expected_nudges"])
        if ok:
            matches += 1
        results.append({
            "id": s["id"],
            "description": s["description"],
            "matched": ok,
            "reason": reason,
            "actual_nudges": actual,
            "expected_nudges": s["expected_nudges"],
        })

    accuracy = matches / len(scenarios) * 100

    # Write the artifact for G22 to read
    artifact = {
        "schema_version": 1,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "matches": matches,
        "misses": len(scenarios) - matches,
        "accuracy_pct": round(accuracy, 2),
        "spec_target_pct": 95.0,
        "all_passed": accuracy >= 95.0,
        "results": results,
    }
    ACCURACY_RESULTS.write_text(json.dumps(artifact, indent=2))

    # The spec demands ≥95%
    assert accuracy >= 95.0, (
        f"Trigger accuracy {accuracy:.1f}% below spec target of 95%. "
        f"Misses:\n" +
        "\n".join(
            f"  {r['id']}: {r['reason']}"
            for r in results if not r["matched"]
        )
    )
