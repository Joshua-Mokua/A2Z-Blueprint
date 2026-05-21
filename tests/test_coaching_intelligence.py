"""tests/test_coaching_intelligence.py — Standard #15 CoachingIntelligence
tests (v5.42).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - generate_coaching_script returns the spec-mandated keys
       - manager-staff relationship validation (cross-team rejection)
       - self-coaching rejection
       - unknown manager/staff rejection
       - section composition (agenda, talking_points, actions)
       - section caps and minimums
       - persistence helpers

  2. Trigger-reliability harness:
       - test_reliability_meets_90_percent runs every fixture in
         tests/fixtures/coaching_scenarios.json. Asserts ≥90%.
         Writes coaching_reliability_results.json for G26.

The "Managers use scripts in 80% of reviews" verification is a
deployed-runtime behavioral metric (whether managers open the
script). OUT OF SCOPE here. We measure structural reliability.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "coaching_scenarios.json"
RELIABILITY_RESULTS = ROOT / "coaching_reliability_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestStandard15Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "coaching_intelligence.py").exists()

    def test_fixtures_exist(self):
        assert FIXTURES.exists()
        data = json.loads(FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 20


# ═══════════════════════════════════════════════════════════════════════
# Engine — unit tests with injected collaborators
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def basic_engine():
    """Minimal valid engine — manager M1, staff S1 is direct report."""
    from utils.coaching_intelligence import CoachingIntelligence
    staff_table = {
        "M1": {"full_name": "Manager One", "role": "Branch Manager",
               "unit": "Mombasa"},
        "S1": {"full_name": "Staff One",   "role": "Personal Banker",
               "unit": "Mombasa"},
    }
    return CoachingIntelligence(
        is_direct_report_fn=lambda m, s: m == "M1" and s == "S1",
        staff_lookup_fn=    lambda sc: staff_table.get(sc),
        kpi_status_fn=      lambda sc: [
            {"kpi_id": "DEP_GROWTH", "current": 130, "target": 100,
             "achievement_pct": 130, "status": "exceeding"},
        ],
        nudges_fn=          lambda sc: [],
        growth_plan_fn=     lambda sc: {},
        microtasks_fn=      lambda sc: [],
        learning_cards_fn=  lambda sc: [],
    )


class TestSpecContract:
    def test_returns_required_keys(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S1")
        assert "meeting_agenda" in s
        assert "talking_points" in s
        assert "recommended_actions" in s

    def test_meeting_agenda_min_3_items(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S1")
        assert len(s["meeting_agenda"]) >= 3

    def test_talking_points_non_empty(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S1")
        assert len(s["talking_points"]) >= 1
        for p in s["talking_points"]:
            assert isinstance(p, str) and p.strip()

    def test_recommended_actions_non_empty(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S1")
        assert len(s["recommended_actions"]) >= 1


class TestRelationshipValidation:
    def test_cross_team_returns_empty(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S2")
        assert s == {}

    def test_self_coaching_rejected(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "M1")
        assert s == {}

    def test_unknown_manager_rejected(self, basic_engine):
        s = basic_engine.generate_coaching_script("UNKNOWN", "S1")
        assert s == {}

    def test_unknown_staff_rejected(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "UNKNOWN")
        assert s == {}


class TestObservableSignals:
    """Talking points must reference observable signals — never fabricate."""

    def test_exceeding_kpi_referenced(self):
        from utils.coaching_intelligence import CoachingIntelligence
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [
                {"kpi_id": "DEP_GROWTH", "current": 152, "target": 100,
                 "achievement_pct": 152, "status": "exceeding"},
            ],
            nudges_fn=lambda sc: [], growth_plan_fn=lambda sc: {},
            microtasks_fn=lambda sc: [], learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        joined = " ".join(s["talking_points"])
        assert "DEP_GROWTH" in joined
        assert "152" in joined

    def test_behind_kpi_referenced(self):
        from utils.coaching_intelligence import CoachingIntelligence
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [
                {"kpi_id": "NPL_PCT", "current": 30, "target": 100,
                 "achievement_pct": 30, "status": "behind"},
            ],
            nudges_fn=lambda sc: [], growth_plan_fn=lambda sc: {},
            microtasks_fn=lambda sc: [], learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        joined = " ".join(s["talking_points"])
        assert "NPL_PCT" in joined
        assert "blockers" in joined.lower()

    def test_skill_gap_referenced(self):
        from utils.coaching_intelligence import CoachingIntelligence
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [],
            nudges_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {
                "skill_gaps": [
                    {"skill": "Risk Management", "current": 2.5, "required": 4.0},
                ],
                "recommended_actions": ["CISI Foundation"],
            },
            microtasks_fn=lambda sc: [], learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        joined = " ".join(s["talking_points"])
        assert "Risk Management" in joined
        assert "2.5" in joined
        assert "4.0" in joined

    def test_no_signals_fallback_still_actionable(self):
        from utils.coaching_intelligence import CoachingIntelligence
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "New Joiner",
                                          "role": "Trainee", "unit": "X"},
            kpi_status_fn=lambda sc: [],
            nudges_fn=lambda sc: [], growth_plan_fn=lambda sc: {},
            microtasks_fn=lambda sc: [], learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        # Even with no data, fallback talking points should exist
        assert len(s["talking_points"]) >= 1
        assert len(s["meeting_agenda"]) >= 3


class TestActionRecommendations:
    def test_learning_card_recommends_peer_connection(self):
        from utils.coaching_intelligence import CoachingIntelligence
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [
                {"kpi_id": "DEP_GROWTH", "current": 50, "target": 100,
                 "achievement_pct": 50, "status": "behind"},
            ],
            nudges_fn=lambda sc: [], growth_plan_fn=lambda sc: {},
            microtasks_fn=lambda sc: [],
            learning_cards_fn=lambda sc: [
                {"card_type": "kpi", "kpi_id": "DEP_GROWTH",
                 "performer_staff_code": "S999", "achievement_pct": 152,
                 "requesting_staff": "S"},
            ],
        )
        s = eng.generate_coaching_script("M", "S")
        joined = " ".join(s["recommended_actions"])
        assert "S999" in joined
        assert "DEP_GROWTH" in joined

    def test_growth_plan_action_surfaced(self):
        from utils.coaching_intelligence import CoachingIntelligence
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [],
            nudges_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {
                "skill_gaps": [{"skill": "Leadership", "current": 2.0, "required": 4.0}],
                "recommended_actions": ["Enroll in Leadership Programme"],
            },
            microtasks_fn=lambda sc: [], learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        joined = " ".join(s["recommended_actions"])
        assert "Leadership Programme" in joined

    def test_actions_capped(self, basic_engine):
        from utils.coaching_intelligence import DEFAULT_ACTIONS_MAX
        s = basic_engine.generate_coaching_script("M1", "S1")
        assert len(s["recommended_actions"]) <= DEFAULT_ACTIONS_MAX


class TestCaps:
    def test_meeting_agenda_capped(self):
        from utils.coaching_intelligence import (
            CoachingIntelligence, DEFAULT_AGENDA_MAX,
        )
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [
                {"kpi_id": "K1", "current": 50, "target": 100, "achievement_pct": 50},
                {"kpi_id": "K2", "current": 130, "target": 100, "achievement_pct": 130},
            ],
            nudges_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {
                "skill_gaps": [{"skill": "X", "current": 2, "required": 4}],
                "recommended_actions": ["A"],
            },
            microtasks_fn=lambda sc: [{"priority": "High", "kpi_id": "K1"}],
            learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        assert len(s["meeting_agenda"]) <= DEFAULT_AGENDA_MAX

    def test_talking_points_capped(self):
        from utils.coaching_intelligence import (
            CoachingIntelligence, DEFAULT_TALKING_POINTS_MAX,
        )
        # Construct a scenario where many points could fire
        eng = CoachingIntelligence(
            is_direct_report_fn=lambda m, s: True,
            staff_lookup_fn=lambda sc: {"full_name": "X", "role": "Y", "unit": "Z"},
            kpi_status_fn=lambda sc: [
                {"kpi_id": f"K{i}", "current": 130, "target": 100,
                 "achievement_pct": 130} for i in range(5)
            ] + [
                {"kpi_id": f"BK{i}", "current": 30, "target": 100,
                 "achievement_pct": 30, "status": "behind"} for i in range(5)
            ],
            nudges_fn=lambda sc: [],
            growth_plan_fn=lambda sc: {
                "skill_gaps": [
                    {"skill": "S1", "current": 2, "required": 4},
                    {"skill": "S2", "current": 2, "required": 4},
                ],
            },
            microtasks_fn=lambda sc: [{"priority": "High"}] * 3,
            learning_cards_fn=lambda sc: [],
        )
        s = eng.generate_coaching_script("M", "S")
        assert len(s["talking_points"]) <= DEFAULT_TALKING_POINTS_MAX


class TestMetadata:
    def test_meta_block_present(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S1")
        assert "meta" in s
        meta = s["meta"]
        assert meta["manager_code"] == "M1"
        assert meta["staff_code"] == "S1"
        assert meta["staff_name"] == "Staff One"
        assert meta["staff_role"] == "Personal Banker"
        assert "for_date" in meta
        assert "signals_used" in meta
        assert "generated_at" in meta

    def test_signals_used_counts(self, basic_engine):
        s = basic_engine.generate_coaching_script("M1", "S1")
        signals = s["meta"]["signals_used"]
        assert "kpi_status_rows" in signals
        assert "active_nudges" in signals
        assert "growth_plan_present" in signals
        assert "active_microtasks" in signals
        assert "learning_cards" in signals


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_save_and_list(self, tmp_path, monkeypatch):
        from utils import coaching_intelligence as ci
        monkeypatch.setattr(ci, "SCRIPTS_FILE",
                            tmp_path / "coaching_scripts.json")

        script = {
            "meeting_agenda":      ["a", "b", "c"],
            "talking_points":      ["talk"],
            "recommended_actions": ["act"],
            "meta": {"manager_code": "M1", "staff_code": "S1",
                     "for_date": "2026-04-29",
                     "generated_at": "2026-04-29T00:00:00+00:00"},
        }
        ok = ci.save_script("M1", "S1", script)
        assert ok is True

        scripts = ci.list_scripts_for_manager("M1")
        assert len(scripts) == 1
        assert scripts[0]["staff_code"] == "S1"

    def test_save_idempotent_same_day(self, tmp_path, monkeypatch):
        from utils import coaching_intelligence as ci
        monkeypatch.setattr(ci, "SCRIPTS_FILE",
                            tmp_path / "coaching_scripts.json")

        s1 = {
            "meeting_agenda": ["a"], "talking_points": ["v1"],
            "recommended_actions": ["x"],
            "meta": {"manager_code": "M1", "staff_code": "S1",
                     "for_date": "2026-04-29", "generated_at": "00:00"},
        }
        s2 = {
            "meeting_agenda": ["a"], "talking_points": ["v2"],
            "recommended_actions": ["x"],
            "meta": {"manager_code": "M1", "staff_code": "S1",
                     "for_date": "2026-04-29", "generated_at": "01:00"},
        }
        ci.save_script("M1", "S1", s1)
        ci.save_script("M1", "S1", s2)
        scripts = ci.list_scripts_for_manager("M1")
        # Same (manager, staff, date) → only one record, latest wins
        assert len(scripts) == 1
        assert scripts[0]["talking_points"] == ["v2"]

    def test_save_empty_returns_false(self, tmp_path, monkeypatch):
        from utils import coaching_intelligence as ci
        monkeypatch.setattr(ci, "SCRIPTS_FILE",
                            tmp_path / "coaching_scripts.json")
        assert ci.save_script("M1", "S1", {}) is False


# ═══════════════════════════════════════════════════════════════════════
# Trigger-reliability harness — Standard #15 spec verification
# ═══════════════════════════════════════════════════════════════════════

def _build_engine_for_scenario(scenario):
    from utils.coaching_intelligence import CoachingIntelligence
    inp = scenario["input"]
    staff_block = inp.get("staff")
    manager_code = inp["manager_code"]
    staff_code = inp["staff_code"]

    # Lookup mock: returns staff_block for the staff code, returns
    # a generic manager record for the manager code, returns None
    # for anything else (so unknown/cross-team paths exercise the
    # rejection branches).
    def staff_lookup(sc):
        if sc == staff_code:
            return staff_block
        if sc == manager_code:
            return {"full_name": "Manager", "role": "BM", "unit": "X"}
        return None

    return CoachingIntelligence(
        is_direct_report_fn=lambda m, s: inp["is_report"],
        staff_lookup_fn=staff_lookup,
        kpi_status_fn=lambda sc: inp["kpi_status"],
        nudges_fn=lambda sc: inp["nudges"],
        growth_plan_fn=lambda sc: inp["growth_plan"],
        microtasks_fn=lambda sc: inp["microtasks"],
        learning_cards_fn=lambda sc: inp["learning_cards"],
    )


def _scenario_matches(actual, expected):
    """Compare actual script to expected fixture rules.
    Returns (match, reason)."""
    if expected.get("empty"):
        if actual != {}:
            return False, f"expected empty, got non-empty"
        return True, "ok"
    if expected.get("non_empty") and not actual:
        return False, "expected non-empty, got {}"

    tps = actual.get("talking_points", [])
    agenda = actual.get("meeting_agenda", [])
    actions = actual.get("recommended_actions", [])

    tp_joined = " ".join(tps).lower()
    act_joined = " ".join(actions).lower()

    if "agenda_min" in expected and len(agenda) < expected["agenda_min"]:
        return False, f"agenda len {len(agenda)} < min {expected['agenda_min']}"
    if "talking_points_min" in expected and len(tps) < expected["talking_points_min"]:
        return False, f"talking_points len {len(tps)} < min"
    if "talking_points_max" in expected and len(tps) > expected["talking_points_max"]:
        return False, f"talking_points len {len(tps)} > max"

    for r in expected.get("talking_points_must_contain", []):
        if r.lower() not in tp_joined:
            return False, f"talking_points missing required: {r!r}"
    if "talking_points_any_of" in expected:
        if not any(o.lower() in tp_joined for o in expected["talking_points_any_of"]):
            return False, f"talking_points missing any of {expected['talking_points_any_of']}"
    for ex in expected.get("talking_points_must_not_contain", []):
        if ex.lower() in tp_joined:
            return False, f"talking_points contains forbidden: {ex!r}"

    for r in expected.get("actions_must_contain", []):
        if r.lower() not in act_joined:
            return False, f"actions missing required: {r!r}"
    if "actions_any_of" in expected:
        if not any(o.lower() in act_joined for o in expected["actions_any_of"]):
            return False, f"actions missing any of {expected['actions_any_of']}"

    return True, "ok"


def test_reliability_meets_90_percent():
    """Run every fixture; assert ≥90% match rate; write artifact."""
    scenarios = json.loads(FIXTURES.read_text())
    assert len(scenarios) >= 20, (
        f"Need ≥20 scenarios for a meaningful sample; got {len(scenarios)}"
    )

    results = []
    matches = 0
    for s in scenarios:
        eng = _build_engine_for_scenario(s)
        inp = s["input"]
        actual = eng.generate_coaching_script(
            inp["manager_code"], inp["staff_code"], today=date(2026, 4, 29),
        )
        ok, reason = _scenario_matches(actual, s["expected"])
        if ok:
            matches += 1
        results.append({
            "id":          s["id"],
            "description": s["description"],
            "matched":     ok,
            "reason":      reason,
            "actual_brief": {
                "talking_points":      actual.get("talking_points") if actual else None,
                "recommended_actions": actual.get("recommended_actions") if actual else None,
                "agenda_count":        len(actual.get("meeting_agenda", [])) if actual else 0,
            },
            "expected": s["expected"],
        })

    reliability = matches / len(scenarios) * 100
    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": len(scenarios),
        "matches":         matches,
        "misses":          len(scenarios) - matches,
        "reliability_pct": round(reliability, 2),
        "spec_target_pct": 90.0,
        "all_passed":      reliability >= 90.0,
        "results":         results,
    }
    RELIABILITY_RESULTS.write_text(json.dumps(artifact, indent=2))

    assert reliability >= 90.0, (
        f"Reliability {reliability:.1f}% below spec target of 90%. Misses:\n" +
        "\n".join(
            f"  {r['id']}: {r['reason']}"
            for r in results if not r["matched"]
        )
    )
