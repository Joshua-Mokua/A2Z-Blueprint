"""tests/test_gamification.py — Standard #17 GamificationEngine tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "badge_scenarios.json"
RELIABILITY_RESULTS = ROOT / "badge_accuracy_results.json"


class TestStandard17Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "gamification.py").exists()


@pytest.fixture
def basic_engine():
    from utils.gamification import GamificationEngine
    history = {
        "S100": [("2026-04", 110), ("2026-03", 105), ("2026-02", 100)],
        "S101": [("2026-04", 95), ("2026-03", 80)],
        "S102": [("2026-04", 102), ("2026-03", 65)],
        "S103": [("2026-04", 95), ("2026-03", 92), ("2026-02", 91),
                 ("2026-01", 93), ("2025-12", 96), ("2025-11", 90)],
        "S104": [("2026-04", 70), ("2026-03", 70), ("2026-02", 70)],
    }
    kpi_history_data = {
        "S100": [
            {"period": "2026-04", "kpis": [{"achievement_pct": 110}, {"achievement_pct": 105}]},
            {"period": "2026-03", "kpis": [{"achievement_pct": 102}, {"achievement_pct": 108}]},
            {"period": "2026-02", "kpis": [{"achievement_pct": 100}, {"achievement_pct": 101}]},
        ],
    }
    staff = {"S100": {"unit": "Mombasa"}, "S101": {"unit": "Nairobi"},
             "S104": {"unit": "Mombasa"}}
    return GamificationEngine(
        bsc_history_fn=lambda sc, n: history.get(sc, [])[:n],
        kpi_history_fn=lambda sc, n: kpi_history_data.get(sc, [])[:n],
        staff_lookup_fn=lambda sc: staff.get(sc),
        unit_roster_fn=lambda u: {"Mombasa": ["S100", "S104"], "Nairobi": ["S101"]}.get(u, []),
        all_units_fn=lambda: ["Mombasa", "Nairobi"],
    )


class TestSpecContract:
    def test_badges_catalog_has_spec_examples(self):
        from utils.gamification import BADGES, GamificationEngine
        assert "100_percent_achiever" in BADGES
        assert "most_improved" in BADGES
        # Class attribute mirrors module dict
        assert GamificationEngine.BADGES == BADGES

    def test_award_returns_badge_or_none(self, basic_engine):
        from utils.gamification import Badge
        b = basic_engine.award_badge("S100", "100_percent_achiever")
        assert isinstance(b, Badge)
        none_b = basic_engine.award_badge("S104", "100_percent_achiever")
        assert none_b is None


class TestBadgeTriggers:
    def test_100_percent_achiever_positive(self, basic_engine):
        b = basic_engine.award_badge("S100", "100_percent_achiever")
        assert b and b.badge_type == "100_percent_achiever"
        assert b.evidence["values"] == [110, 105, 100]

    def test_100_percent_achiever_negative(self, basic_engine):
        # S104 is at 70% — not eligible
        assert basic_engine.award_badge("S104", "100_percent_achiever") is None

    def test_most_improved_positive(self, basic_engine):
        b = basic_engine.award_badge("S101", "most_improved")
        assert b and b.evidence["delta"] == 15

    def test_most_improved_negative_small_delta(self, basic_engine):
        from utils.gamification import GamificationEngine
        eng = GamificationEngine(
            bsc_history_fn=lambda sc, n: [("2026-04", 92), ("2026-03", 91)],
        )
        # Delta 1.0 < threshold 1.5 → no badge
        assert eng.award_badge("X", "most_improved") is None

    def test_comeback_kid_positive(self, basic_engine):
        b = basic_engine.award_badge("S102", "comeback_kid")
        assert b and b.evidence["prev"] == 65 and b.evidence["current"] == 102

    def test_comeback_kid_negative(self, basic_engine):
        # S101 went 80 → 95, prev not below 70
        assert basic_engine.award_badge("S101", "comeback_kid") is None

    def test_consistent_high_positive(self, basic_engine):
        b = basic_engine.award_badge("S103", "consistent_high")
        assert b and len(b.evidence["periods"]) == 6

    def test_consistent_high_negative_short_history(self, basic_engine):
        # S100 only has 3 periods, not 6
        assert basic_engine.award_badge("S100", "consistent_high") is None

    def test_perfect_quarter_positive(self, basic_engine):
        b = basic_engine.award_badge("S100", "perfect_quarter")
        assert b is not None

    def test_perfect_quarter_negative_no_kpi_data(self, basic_engine):
        # S101 has no kpi_history data
        assert basic_engine.award_badge("S101", "perfect_quarter") is None

    def test_team_player_positive(self, basic_engine):
        # S100 at 110%, Mombasa = (110+70)/2 = 90, Nairobi = 95
        # Mombasa rank 2 of 2, top quartile cutoff = 1 → only Nairobi top quartile
        # So S100 (Mombasa) should NOT get team_player despite 110%+
        b = basic_engine.award_badge("S100", "team_player")
        assert b is None  # Mombasa not top quartile

    def test_unknown_badge_type_returns_none(self, basic_engine):
        assert basic_engine.award_badge("S100", "unknown_xyz") is None


class TestEvaluateAll:
    def test_evaluate_all_runs_every_check(self, basic_engine):
        badges = basic_engine.evaluate_all_badges("S100")
        types = {b.badge_type for b in badges}
        assert "100_percent_achiever" in types
        assert "perfect_quarter" in types

    def test_evaluate_all_for_no_badges(self, basic_engine):
        badges = basic_engine.evaluate_all_badges("S104")
        assert badges == []


class TestLeaderboard:
    def test_leaderboard_sorted_desc(self, basic_engine):
        lb = basic_engine.build_leaderboard("2026-04")
        assert len(lb) == 2
        assert lb[0].avg_achievement_pct >= lb[1].avg_achievement_pct
        assert lb[0].rank == 1

    def test_top_quartile_marked(self, basic_engine):
        lb = basic_engine.build_leaderboard("2026-04")
        top_count = sum(1 for r in lb if r.top_quartile)
        assert top_count >= 1

    def test_empty_period(self, basic_engine):
        lb = basic_engine.build_leaderboard("9999-12")
        assert lb == []


class TestPersistence:
    def test_save_badges(self, tmp_path, monkeypatch):
        from utils import gamification as gm
        from utils.gamification import Badge
        monkeypatch.setattr(gm, "BADGES_FILE", tmp_path / "badges.json")
        b = Badge(id="b1", staff_code="S1", badge_type="100_percent_achiever")
        n = gm.save_badges([b])
        assert n == 1
        listed = gm.list_badges_for_staff("S1")
        assert len(listed) == 1

    def test_save_badges_idempotent(self, tmp_path, monkeypatch):
        from utils import gamification as gm
        from utils.gamification import Badge
        monkeypatch.setattr(gm, "BADGES_FILE", tmp_path / "badges.json")
        b = Badge(id="b1", staff_code="S1", badge_type="100_percent_achiever")
        gm.save_badges([b])
        gm.save_badges([b])
        listed = gm.list_badges_for_staff("S1")
        assert len(listed) == 1

    def test_save_leaderboard(self, tmp_path, monkeypatch):
        from utils import gamification as gm
        from utils.gamification import LeaderboardRow
        monkeypatch.setattr(gm, "LEADERBOARDS_FILE", tmp_path / "lb.json")
        rows = [LeaderboardRow(rank=1, unit="Nairobi", avg_achievement_pct=95.0,
                                staff_count=10, top_quartile=True)]
        ok = gm.save_leaderboard("2026-04", rows)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════
# Reliability harness — Standard #17 spec verification
# ═══════════════════════════════════════════════════════════════════════

# We construct fixtures inline since the badge logic is small enough
# that 20 inline scenarios is cleaner than externalizing.

BADGE_SCENARIOS = [
    # 100_percent_achiever
    {"id": "B001", "staff": "S1", "history": [("M1", 110), ("M2", 105), ("M3", 100)],
     "badge": "100_percent_achiever", "expected": True},
    {"id": "B002", "staff": "S1", "history": [("M1", 110), ("M2", 99), ("M3", 100)],
     "badge": "100_percent_achiever", "expected": False},
    {"id": "B003", "staff": "S1", "history": [("M1", 110), ("M2", 105)],
     "badge": "100_percent_achiever", "expected": False},  # too short

    # most_improved
    {"id": "B004", "staff": "S1", "history": [("M1", 95), ("M2", 80)],
     "badge": "most_improved", "expected": True},
    {"id": "B005", "staff": "S1", "history": [("M1", 92), ("M2", 91)],
     "badge": "most_improved", "expected": False},
    {"id": "B006", "staff": "S1", "history": [("M1", 81.5), ("M2", 80)],
     "badge": "most_improved", "expected": True},  # exactly 1.5 ≥ threshold
    {"id": "B007", "staff": "S1", "history": [("M1", 80), ("M2", 95)],
     "badge": "most_improved", "expected": False},  # decline, not improvement

    # consistent_high
    {"id": "B008", "staff": "S1",
     "history": [("M1", 95), ("M2", 92), ("M3", 91), ("M4", 93), ("M5", 96), ("M6", 90)],
     "badge": "consistent_high", "expected": True},
    {"id": "B009", "staff": "S1",
     "history": [("M1", 95), ("M2", 92), ("M3", 89), ("M4", 93), ("M5", 96), ("M6", 90)],
     "badge": "consistent_high", "expected": False},  # M3 below 90

    # comeback_kid
    {"id": "B010", "staff": "S1", "history": [("M1", 102), ("M2", 65)],
     "badge": "comeback_kid", "expected": True},
    {"id": "B011", "staff": "S1", "history": [("M1", 102), ("M2", 75)],
     "badge": "comeback_kid", "expected": False},  # prev not below 70
    {"id": "B012", "staff": "S1", "history": [("M1", 99), ("M2", 60)],
     "badge": "comeback_kid", "expected": False},  # current not at 100

    # perfect_quarter (uses kpi_history)
    {"id": "B013", "staff": "S1",
     "kpi_history": [
         {"period": "M1", "kpis": [{"achievement_pct": 110}, {"achievement_pct": 105}]},
         {"period": "M2", "kpis": [{"achievement_pct": 102}, {"achievement_pct": 100}]},
         {"period": "M3", "kpis": [{"achievement_pct": 100}, {"achievement_pct": 101}]}],
     "badge": "perfect_quarter", "expected": True},
    {"id": "B014", "staff": "S1",
     "kpi_history": [
         {"period": "M1", "kpis": [{"achievement_pct": 110}, {"achievement_pct": 95}]},
         {"period": "M2", "kpis": [{"achievement_pct": 102}, {"achievement_pct": 100}]},
         {"period": "M3", "kpis": [{"achievement_pct": 100}, {"achievement_pct": 101}]}],
     "badge": "perfect_quarter", "expected": False},  # M1 has 95 < 100

    # Edge cases
    {"id": "B015", "staff": "S1", "history": [],
     "badge": "100_percent_achiever", "expected": False},  # no data
    {"id": "B016", "staff": "S1", "history": [("M1", 110)],
     "badge": "most_improved", "expected": False},  # only 1 period
    {"id": "B017", "staff": "S1", "history": [("M1", 100), ("M2", 100), ("M3", 100)],
     "badge": "100_percent_achiever", "expected": True},  # exactly at threshold

    # Unknown staff with no history
    {"id": "B018", "staff": "Unknown", "history": [],
     "badge": "consistent_high", "expected": False},

    # Multiple checks on same staff
    {"id": "B019", "staff": "S1", "history": [("M1", 150), ("M2", 145), ("M3", 140)],
     "badge": "100_percent_achiever", "expected": True},
    {"id": "B020", "staff": "S1", "history": [("M1", 75), ("M2", 70)],
     "badge": "comeback_kid", "expected": False},  # not yet at 100
]


def test_badge_accuracy_meets_90_percent():
    """Run every fixture; assert ≥90% match rate; write G28 artifact."""
    from utils.gamification import GamificationEngine

    matches = 0
    results = []
    for s in BADGE_SCENARIOS:
        history = s.get("history", [])
        kpi_history = s.get("kpi_history", [])
        eng = GamificationEngine(
            bsc_history_fn=lambda sc, n, h=history: list(h)[:n],
            kpi_history_fn=lambda sc, n, kh=kpi_history: list(kh)[:n],
        )
        b = eng.award_badge(s["staff"], s["badge"])
        actual = b is not None
        match = actual == s["expected"]
        if match:
            matches += 1
        results.append({
            "id": s["id"], "badge": s["badge"], "expected": s["expected"],
            "actual": actual, "matched": match,
            "reason": "ok" if match else f"expected={s['expected']}, got={actual}",
        })

    accuracy = matches / len(BADGE_SCENARIOS) * 100
    artifact = {
        "schema_version": 1,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(BADGE_SCENARIOS),
        "matches": matches,
        "accuracy_pct": round(accuracy, 2),
        "spec_target_pct": 90.0,
        "all_passed": accuracy >= 90.0,
        "results": results,
    }
    RELIABILITY_RESULTS.write_text(json.dumps(artifact, indent=2))

    assert accuracy >= 90.0, (
        f"Badge accuracy {accuracy:.1f}% < 90%. Failures:\n"
        + "\n".join(f"  {r['id']}: {r['reason']}" for r in results if not r["matched"])
    )
