"""tests/test_growth_path_engine.py — Standard #12 GrowthPathEngine tests
(v5.39).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - generate_development_plan returns the spec-mandated keys
       - promotion_readiness ∈ [0, 1]
       - skill gaps sorted by gap descending, capped
       - tenure parsing across formats
       - skill factor bounds
       - default-role fallback when role isn't in the matrix
       - persistence helpers (save/get/list)
       - empty-plan contract for unknown staff_code

  2. Generator + gate consistency tests:
       - scripts/generate_growth_plans.py exists and is well-formed
       - data/role_skill_matrix.json + data/training_catalog.json present
       - G23 wired in audit.py
       - results artifact schema

The harness does NOT rerun the generator (1438 staff is too slow for
unit tests and the generator side-effects users.json by reading it).
The integration test is the live audit run we already verified.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
RESULTS = ROOT / "growth_plans_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestStandard12Files:
    """Required files for Standard #12."""

    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "growth_path_engine.py").exists()

    def test_generator_script_exists(self):
        assert (ROOT / "scripts" / "generate_growth_plans.py").exists()

    def test_role_skill_matrix_seeded(self):
        path = DATA / "role_skill_matrix.json"
        assert path.exists(), (
            "data/role_skill_matrix.json must exist — it's the source of "
            "required-skill levels per role"
        )
        data = json.loads(path.read_text())
        assert isinstance(data, dict) and len(data) >= 5, (
            f"Role-skill matrix must have at least 5 roles; got {len(data)}"
        )
        # 'default' role must exist (engine falls back to it)
        assert "default" in data, (
            "matrix must include 'default' for roles HR hasn't curated"
        )

    def test_training_catalog_seeded(self):
        path = DATA / "training_catalog.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert isinstance(data, dict) and len(data) >= 5


# ═══════════════════════════════════════════════════════════════════════
# Engine internals — unit tests with injected collaborators
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_engine():
    from utils.growth_path_engine import GrowthPathEngine

    staff = {
        "S001": {"role": "Branch Manager", "band": "M3",
                 "role_start_date": "2024-01-15"},
        "S002": {"role": "Credit Analyst", "band": "M5",
                 "hire_date": "2025-08-01"},
        "S003": {"role": "Unknown Role X", "band": "M5",
                 "hire_date": "2024-01-15"},
    }
    bsc = {"S001": [4.5, 4.3, 4.4], "S002": [3.0, 3.2, 3.1], "S003": [4.0]}
    skills = {
        "S001": {"Risk Management": 3.5, "Customer Service": 4.0,
                 "Leadership": 3.5},
        "S002": {"Credit Analysis": 4.0, "Risk Management": 2.5},
        "S003": {"Customer Service": 3.0, "Operations": 3.0},
    }
    role_req = {
        "Branch Manager":  {"Risk Management": 4.0, "Customer Service": 4.0,
                            "Leadership": 4.5, "Product Knowledge": 3.5},
        "Credit Analyst":  {"Credit Analysis": 4.5, "Risk Management": 4.0,
                            "Financial Modelling": 3.0},
        "default":         {"Customer Service": 3.5, "Operations": 3.5,
                            "Compliance": 3.5},
    }
    training = {
        "Risk Management":   ["Complete CISI Risk Level 1"],
        "Leadership":        ["Enroll in Leadership Programme"],
        "Customer Service":  ["NPS Champions e-learning"],
        "Product Knowledge": ["Quarterly product briefing"],
        "Credit Analysis":   ["CISI Credit certification"],
        "Financial Modelling": ["Excel for Finance"],
        "Operations":        ["Operations 101"],
        "Compliance":        ["Annual AML refresher"],
    }
    return GrowthPathEngine(
        staff_lookup_fn=     lambda sc: staff.get(sc),
        bsc_history_fn=      lambda sc, n: bsc.get(sc, [])[:n],
        skill_assessment_fn= lambda sc: skills.get(sc, {}),
        role_requirements_fn=lambda r:  role_req.get(r) or role_req.get("default", {}),
        training_catalog_fn= lambda s, c, r: training.get(s, []),
    )


class TestPlanContract:
    """generate_development_plan returns the spec-mandated keys."""

    def test_plan_has_spec_required_keys(self, mock_engine):
        plan = mock_engine.generate_development_plan("S001")
        assert "promotion_readiness" in plan
        assert "skill_gaps" in plan
        assert "recommended_actions" in plan
        # Plus our meta extension
        assert "meta" in plan

    def test_promotion_readiness_in_range(self, mock_engine):
        plan = mock_engine.generate_development_plan("S001")
        assert isinstance(plan["promotion_readiness"], float)
        assert 0.0 <= plan["promotion_readiness"] <= 1.0

    def test_skill_gaps_is_list_of_dicts(self, mock_engine):
        plan = mock_engine.generate_development_plan("S001")
        assert isinstance(plan["skill_gaps"], list)
        for g in plan["skill_gaps"]:
            for k in ("skill", "current", "required", "gap"):
                assert k in g, f"skill gap missing key {k!r}"

    def test_skill_gaps_sorted_by_gap_desc(self, mock_engine):
        plan = mock_engine.generate_development_plan("S001")
        gaps = plan["skill_gaps"]
        for i in range(len(gaps) - 1):
            assert gaps[i]["gap"] >= gaps[i + 1]["gap"], (
                "skill_gaps must be sorted by gap size descending"
            )

    def test_recommended_actions_capped(self, mock_engine):
        from utils.growth_path_engine import DEFAULT_MAX_ACTIONS
        plan = mock_engine.generate_development_plan("S001")
        assert len(plan["recommended_actions"]) <= DEFAULT_MAX_ACTIONS

    def test_unknown_staff_returns_empty_dict(self, mock_engine):
        plan = mock_engine.generate_development_plan("UNKNOWN_X")
        assert plan == {}, (
            "spec contract: unknown staff returns empty dict (no exception)"
        )

    def test_default_role_fallback(self, mock_engine):
        """Staff with role not in the matrix should still get a plan
        (fallback to 'default' role requirements)."""
        plan = mock_engine.generate_development_plan("S003")
        assert plan != {}
        assert "skill_gaps" in plan


class TestPromotionReadinessMath:
    """Verify the composite scoring is deterministic and bounded."""

    def test_strong_performer_high_readiness(self, mock_engine):
        # S001: bsc_avg=4.4, tenure=27m capped to 24 → factor 1.0,
        # skill_factor ≈ 0.69. Readiness ≈ 0.5*0.85 + 0.3*1.0 + 0.2*0.69 ≈ 0.86
        plan = mock_engine.generate_development_plan("S001",
                                                    today=date(2026, 4, 15))
        assert 0.80 <= plan["promotion_readiness"] <= 0.95

    def test_weaker_performer_lower_readiness(self, mock_engine):
        # S002: bsc_avg=3.1 → factor 0.525; tenure=8m → 0.333; skills
        # 4.0+2.5+0=6.5/11.5=0.565. Readiness ≈ 0.5*0.525 + 0.3*0.333 + 0.2*0.565 ≈ 0.475
        plan = mock_engine.generate_development_plan("S002",
                                                    today=date(2026, 4, 15))
        assert 0.40 <= plan["promotion_readiness"] <= 0.55


class TestEngineHelpers:
    """Internal helpers — bounds, parsing."""

    def test_skill_factor_all_met(self):
        from utils.growth_path_engine import _compute_skill_factor_and_gaps
        f, g = _compute_skill_factor_and_gaps(
            {"A": 5.0, "B": 4.0}, {"A": 5.0, "B": 4.0}
        )
        assert f == 1.0
        assert g == []

    def test_skill_factor_all_missing(self):
        from utils.growth_path_engine import _compute_skill_factor_and_gaps
        f, g = _compute_skill_factor_and_gaps({}, {"A": 5.0})
        assert f == 0.0
        assert len(g) == 1 and g[0]["skill"] == "A"

    def test_skill_factor_no_requirements(self):
        from utils.growth_path_engine import _compute_skill_factor_and_gaps
        f, g = _compute_skill_factor_and_gaps({"A": 5.0}, {})
        assert f == 1.0
        assert g == []

    def test_skill_factor_partial_meet(self):
        from utils.growth_path_engine import _compute_skill_factor_and_gaps
        f, g = _compute_skill_factor_and_gaps(
            {"A": 4.0, "B": 2.0}, {"A": 4.0, "B": 4.0}
        )
        # satisfied = min(4,4) + min(2,4) = 6; required = 8 → 0.75
        assert f == 0.75
        # B has gap 2, A has no gap
        assert len(g) == 1 and g[0]["skill"] == "B"
        assert g[0]["gap"] == 2.0

    def test_tenure_role_start_preferred(self):
        from utils.growth_path_engine import _compute_tenure_months
        m = _compute_tenure_months(
            {"role_start_date": "2024-04-15", "hire_date": "2010-01-01"},
            date(2026, 4, 15),
        )
        # role_start preferred → 24 months
        assert m == 24

    def test_tenure_hire_date_fallback(self):
        from utils.growth_path_engine import _compute_tenure_months
        m = _compute_tenure_months({"hire_date": "2025-08-01"},
                                   date(2026, 4, 15))
        assert m == 8

    def test_tenure_no_dates(self):
        from utils.growth_path_engine import _compute_tenure_months
        m = _compute_tenure_months({}, date(2026, 4, 15))
        assert m == 0

    def test_tenure_future_date_clamped(self):
        from utils.growth_path_engine import _compute_tenure_months
        m = _compute_tenure_months({"hire_date": "2030-01-01"},
                                   date(2026, 4, 15))
        # Future date → 0 (don't credit unverifiable tenure)
        assert m == 0

    def test_tenure_multiple_formats(self):
        from utils.growth_path_engine import _parse_date
        d = _parse_date("2024-04-15")
        assert d == date(2024, 4, 15)
        d = _parse_date("15/04/2024")
        assert d == date(2024, 4, 15)


class TestPersistenceHelpers:
    """save_plans / get_plan / list_staff_with_plans."""

    def test_save_and_get(self, tmp_path, monkeypatch):
        from utils import growth_path_engine
        monkeypatch.setattr(growth_path_engine, "PLANS_FILE",
                            tmp_path / "growth_plans.json")
        plans = {
            "S001": {"promotion_readiness": 0.75, "skill_gaps": [],
                     "recommended_actions": ["x"]},
            "S002": {"promotion_readiness": 0.50, "skill_gaps": [],
                     "recommended_actions": []},
        }
        n = growth_path_engine.save_plans(plans)
        assert n == 2
        plan = growth_path_engine.get_plan("S001")
        assert plan and plan["promotion_readiness"] == 0.75

    def test_list_staff_with_plans(self, tmp_path, monkeypatch):
        from utils import growth_path_engine
        monkeypatch.setattr(growth_path_engine, "PLANS_FILE",
                            tmp_path / "growth_plans.json")
        growth_path_engine.save_plans({"S001": {}, "S002": {}, "S003": {}})
        codes = growth_path_engine.list_staff_with_plans()
        assert set(codes) == {"S001", "S002", "S003"}


# ═══════════════════════════════════════════════════════════════════════
# Generator + G23 wiring
# ═══════════════════════════════════════════════════════════════════════

class TestGeneratorScript:
    """The driver that materializes plans must be well-formed."""

    SCRIPT = ROOT / "scripts" / "generate_growth_plans.py"

    def test_writes_expected_artifact(self):
        src = self.SCRIPT.read_text()
        assert "growth_plans_results.json" in src, (
            "Generator must write growth_plans_results.json — G23 reads it"
        )

    def test_writes_plans_data_file(self):
        src = self.SCRIPT.read_text()
        assert "growth_plans.json" in src

    def test_seeds_skills_when_missing(self):
        src = self.SCRIPT.read_text()
        assert "seed_staff_skills" in src or "staff_skills" in src

    def test_uses_unique_staff_codes_for_coverage(self):
        src = self.SCRIPT.read_text()
        # Coverage measured against unique staff codes, not active count
        assert "unique_staff_codes" in src, (
            "Generator must compute coverage against unique staff_codes "
            "to handle duplicates correctly"
        )

    def test_reports_duplicate_staff_codes(self):
        src = self.SCRIPT.read_text()
        assert "duplicate_staff_codes" in src


class TestG23Wiring:
    AUDIT = ROOT / "scripts" / "audit.py"

    def test_g23_function_defined(self):
        src = self.AUDIT.read_text()
        assert "def gate_growth_path_coverage" in src, (
            "G23 must be a top-level function in scripts/audit.py"
        )

    def test_g23_in_gates_list(self):
        src = self.AUDIT.read_text()
        assert '("G23", gate_growth_path_coverage)' in src

    def test_g23_reads_correct_artifact(self):
        src = self.AUDIT.read_text()
        # Look for the artifact filename in the gate function area
        assert "growth_plans_results.json" in src

    def test_generator_in_foundational(self):
        src = self.AUDIT.read_text()
        assert '"scripts/generate_growth_plans.py"' in src, (
            "Generator must be in FOUNDATIONAL — it does file I/O on data/"
        )


class TestResultsArtifactSchema:
    """If growth_plans_results.json exists, validate its schema."""

    def test_artifact_schema_when_present(self):
        if not RESULTS.exists():
            pytest.skip("results artifact not yet generated")
        data = json.loads(RESULTS.read_text())
        for required in ("schema_version", "active_staff", "unique_staff_codes",
                         "plans_generated", "coverage_pct", "spec_target_pct",
                         "all_passed"):
            assert required in data, f"results artifact missing key {required!r}"
        # Coverage between 0 and 100
        assert 0 <= data["coverage_pct"] <= 100
        # spec target is 100
        assert data["spec_target_pct"] == 100.0


# ═══════════════════════════════════════════════════════════════════════
# Live integration smoke test — runs the engine against real data
# ═══════════════════════════════════════════════════════════════════════

class TestLiveEngineSmoke:
    """Smoke test: the engine returns a well-formed plan for a real
    user_code from users.json (when data is present)."""

    def test_real_staff_gets_plan(self):
        users_file = DATA / "users.json"
        if not users_file.exists():
            pytest.skip("users.json not present")
        users = json.loads(users_file.read_text())

        # Pick an active user with a staff_code
        sample_staff_code = None
        for username, info in users.items():
            if isinstance(info, dict) and info.get("active"):
                sc = str(info.get("staff_code", ""))
                if sc:
                    sample_staff_code = sc
                    break
        if not sample_staff_code:
            pytest.skip("no active staff with staff_code found")

        from utils.growth_path_engine import GrowthPathEngine
        plan = GrowthPathEngine().generate_development_plan(sample_staff_code)

        # The plan must at minimum have the spec-required keys
        assert plan, f"engine returned empty for active staff {sample_staff_code}"
        for k in ("promotion_readiness", "skill_gaps", "recommended_actions"):
            assert k in plan
        assert 0 <= plan["promotion_readiness"] <= 1
