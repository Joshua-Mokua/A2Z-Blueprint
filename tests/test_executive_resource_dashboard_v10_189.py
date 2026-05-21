"""tests.test_executive_resource_dashboard_v10_189 — ENH-165.

Capstone test suite for the Resource Optimization arc. Covers
engine shape, registry/hub wiring, graceful-degradation when
engines are absent, sub-index extraction from each upstream
engine's board_summary, composite health math, snapshot
semantics, deferrals, no-regression on all 9 prior arc
standards.
"""
from __future__ import annotations

import importlib
import inspect


# ---------------------------------------------------------------- shape


class TestModuleShape:

    def test_module_imports(self):
        m = importlib.import_module(
            'utils.executive_resource_dashboard')
        assert m is not None

    def test_engine_class_exposed(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        assert inspect.isclass(ExecutiveResourceDashboard)

    def test_dataclasses_exposed(self):
        from utils.executive_resource_dashboard import (
            DashboardSection, ExecutiveDashboard,
        )
        for cls in (DashboardSection, ExecutiveDashboard):
            assert hasattr(cls, '__dataclass_fields__')

    def test_weights_constant_sums_to_1(self):
        from utils.executive_resource_dashboard import (
            HEALTH_INDEX_WEIGHTS,
        )
        assert abs(sum(HEALTH_INDEX_WEIGHTS.values()) - 1.0) < 1e-9

    def test_engine_public_methods(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        public = {n for n in dir(ExecutiveResourceDashboard)
                  if not n.startswith('_')}
        assert {
            'snapshot', 'list_snapshots', 'board_summary',
        }.issubset(public)


# ------------------------------------------------------------ registry


class TestRegistry:

    def test_enh_165_active(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-165')
        assert s.status == 'active'

    def test_enh_165_engine_named(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-165')
        assert 'executive_resource_dashboard' in s.affected_engines

    def test_enh_165_batch_v10_189(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-165')
        assert getattr(s, 'implementation_batch', None) == 'v10.189'


# -------------------------------------------------------- hub integration


class TestHubIntegration:

    def test_tier32_entry_present(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        assert '"executive_resource_dashboard"' in src
        assert '"ExecutiveResourceDashboard"' in src
        assert 'ENH-165' in src

    def test_tier32_appears_after_integrity_culture(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        idx_ic = src.find('"integrity_culture"')
        idx_erd = src.find('"executive_resource_dashboard"')
        assert idx_ic != -1 and idx_erd != -1
        assert idx_erd > idx_ic


# --------------------------------------------------- helpers


def _empty():
    from utils.executive_resource_dashboard import (
        ExecutiveResourceDashboard,
    )
    return ExecutiveResourceDashboard()


def _full_engines():
    """Wire up real engines as the dashboard would see them."""
    from utils.tsl_optimization import (
        TSLOptimizationEngine, TSLTarget, TSLChannelType,
    )
    from utils.utilization_dashboard import (
        UtilizationDashboardEngine, UtilizationObservation,
    )
    from utils.wellbeing_integration import (
        WellbeingIntegrationEngine,
    )
    from utils.integrity_culture import (
        IntegrityCultureEngine, CultureSubmission,
    )
    tsl = TSLOptimizationEngine()
    tsl.set_target(TSLTarget(
        channel_key='cc', channel_type=TSLChannelType.CALL_CENTER,
        target_pct=0.80, threshold_seconds=20.0, aht_seconds=180.0,
    ))
    tsl.optimize_staffing(channel_key='cc', arrivals_per_hour=100.0)
    util = UtilizationDashboardEngine()
    util.submit_observation(UtilizationObservation(
        channel_key='cc', team_key='t1', manager_id='m1',
        agents_available=10, agents_busy=6,
        observed_arrivals_per_hour=100.0,
        observed_aht_seconds=180.0,
    ))
    well = WellbeingIntegrationEngine(
        wellness_assessor=lambda s: {"risk_level": "Low"},
    )
    well.assess_team_signal('team_a', [f's{i}' for i in range(8)])
    culture = IntegrityCultureEngine()
    culture.score_team(CultureSubmission(
        team_code='team_a', n_respondents=10,
        transparency_score=85, trust_score=80,
        sentiment_score=78, code_of_conduct_score=85,
        period_label='2026-Q1',
    ))
    return tsl, util, well, culture


# ------------------------------------- empty / graceful degradation


class TestGracefulDegradation:

    def test_empty_dashboard_no_engines(self):
        snap = _empty().snapshot("e1")
        assert snap.n_engines_attached == 0
        assert snap.n_engines_available == 0
        assert snap.resource_optimization_health_index is None

    def test_empty_dashboard_all_sections_unavailable(self):
        snap = _empty().snapshot("e2")
        for s in snap.sections:
            assert s.available is False
            assert s.payload is None

    def test_empty_dashboard_no_components(self):
        snap = _empty().snapshot("e3")
        assert snap.health_index_components == {}

    def test_section_count_is_nine(self):
        snap = _empty().snapshot("e4")
        assert len(snap.sections) == 9

    def test_section_ids_are_distinct(self):
        snap = _empty().snapshot("e5")
        ids = [s.section_id for s in snap.sections]
        assert len(set(ids)) == 9


# ----------------------------------------------- sub-index extraction


class TestSubIndexExtraction:

    def test_tsl_sub_index_populated(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        tsl, _, _, _ = _full_engines()
        snap = ExecutiveResourceDashboard(
            tsl_engine=tsl, integrity_culture_engine=_full_engines()[3],
        ).snapshot("t1")
        assert 'tsl_health' in snap.health_index_components

    def test_utilization_sub_index_populated(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        _, util, _, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            utilization_engine=util,
            integrity_culture_engine=culture,
        ).snapshot("u1")
        assert 'utilization_health' in snap.health_index_components

    def test_wellbeing_sub_index_populated(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        _, _, well, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            wellbeing_engine=well,
            integrity_culture_engine=culture,
        ).snapshot("w1")
        assert 'wellbeing_health' in snap.health_index_components

    def test_culture_sub_index_populated(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        _, _, well, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            wellbeing_engine=well,
            integrity_culture_engine=culture,
        ).snapshot("c1")
        assert 'culture_health' in snap.health_index_components


# -------------------------------------------- composite math


class TestCompositeMath:

    def test_single_component_returns_none(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        _, _, _, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            integrity_culture_engine=culture,
        ).snapshot("solo")
        assert snap.resource_optimization_health_index is None

    def test_two_components_publishes_composite(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        _, _, well, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            wellbeing_engine=well,
            integrity_culture_engine=culture,
        ).snapshot("duo")
        assert snap.resource_optimization_health_index is not None
        assert 0 <= snap.resource_optimization_health_index <= 100

    def test_full_engines_composite_in_range(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        tsl, util, well, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            tsl_engine=tsl, utilization_engine=util,
            wellbeing_engine=well, integrity_culture_engine=culture,
        ).snapshot("full")
        assert snap.resource_optimization_health_index is not None
        assert 0 <= snap.resource_optimization_health_index <= 100

    def test_weights_recorded_on_snapshot(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard, HEALTH_INDEX_WEIGHTS,
        )
        snap = ExecutiveResourceDashboard().snapshot("w")
        assert snap.health_index_weights == HEALTH_INDEX_WEIGHTS

    def test_components_only_includes_available(self):
        # When only wellbeing + culture attached, components dict
        # should only have those two keys
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        _, _, well, culture = _full_engines()
        snap = ExecutiveResourceDashboard(
            wellbeing_engine=well,
            integrity_culture_engine=culture,
        ).snapshot("c")
        assert set(snap.health_index_components.keys()) == {
            'wellbeing_health', 'culture_health',
        }


# ------------------------------------------ snapshot semantics


class TestSnapshotSemantics:

    def test_snapshot_id_required(self):
        try:
            _empty().snapshot("")
            assert False, "should reject"
        except ValueError:
            pass

    def test_snapshots_appended(self):
        e = _empty()
        e.snapshot("a")
        e.snapshot("b")
        e.snapshot("c")
        assert len(e.list_snapshots()) == 3

    def test_no_mutation_of_upstream_engines(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        tsl, util, well, culture = _full_engines()
        n_before_culture = len(culture.list_scores())
        n_before_well = len(well.list_signals())
        ExecutiveResourceDashboard(
            tsl_engine=tsl, utilization_engine=util,
            wellbeing_engine=well, integrity_culture_engine=culture,
        ).snapshot("readonly")
        # No new scores / signals added
        assert len(culture.list_scores()) == n_before_culture
        assert len(well.list_signals()) == n_before_well


# ----------------------------------------------- safe call


class TestSafeCallGracefulFailure:

    def test_engine_with_failing_board_summary_section_unavailable(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        class _Broken:
            def board_summary(self):
                raise RuntimeError("simulated outage")
        snap = ExecutiveResourceDashboard(
            integrity_culture_engine=_Broken(),
        ).snapshot("broken")
        culture_section = next(
            s for s in snap.sections if s.section_id == 'culture'
        )
        assert culture_section.available is False

    def test_engine_without_board_summary_method(self):
        from utils.executive_resource_dashboard import (
            ExecutiveResourceDashboard,
        )
        class _Sparse:
            pass  # no board_summary method
        snap = ExecutiveResourceDashboard(
            tsl_engine=_Sparse(),
        ).snapshot("sparse")
        tsl_section = next(
            s for s in snap.sections if s.section_id == 'tsl'
        )
        assert tsl_section.available is False


# ----------------------------------------------- serialization


class TestSerialization:

    def test_dashboard_to_dict(self):
        import json
        snap = _empty().snapshot("ser")
        d = snap.to_dict()
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2['snapshot_id'] == 'ser'
        assert len(d2['sections']) == 9

    def test_section_to_dict(self):
        snap = _empty().snapshot("sec")
        sec = snap.sections[0]
        d = sec.to_dict()
        assert 'section_id' in d
        assert 'available' in d


# ------------------------------------- deferrals + board summary


class TestHonestDeferrals:

    def test_all_four_deferrals_present(self):
        bs = _empty().board_summary()
        deferrals = bs.get('deferrals', {})
        for key in (
            'REAL_TIME_REFRESH',
            'DRILL_DOWN_NAVIGATION',
            'PREDICTIVE_FORECAST_OVERLAY',
            'CUSTOM_KPI_DEFINITIONS',
        ):
            assert key in deferrals

    def test_regulatory_basis_named(self):
        rb = _empty().board_summary()['regulatory_basis']
        assert 'BSC' in rb
        assert 'CBK' in rb

    def test_board_exposes_weights(self):
        from utils.executive_resource_dashboard import (
            HEALTH_INDEX_WEIGHTS,
        )
        bs = _empty().board_summary()
        assert bs['health_index_weights'] == HEALTH_INDEX_WEIGHTS


# ----------------------------------------------------- no regression


class TestNoRegression:
    """All 9 prior arc standards still active. Capstone test."""

    def test_enh_156_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-156').status == 'active'

    def test_enh_157_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-157').status == 'active'

    def test_enh_158_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-158').status == 'active'

    def test_enh_159_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-159').status == 'active'

    def test_enh_160_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-160').status == 'active'

    def test_enh_161_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-161').status == 'active'

    def test_enh_162_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-162').status == 'active'

    def test_enh_163_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-163').status == 'active'

    def test_enh_164_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-164').status == 'active'
