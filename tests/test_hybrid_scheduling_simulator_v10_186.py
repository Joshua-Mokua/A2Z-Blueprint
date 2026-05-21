"""tests.test_hybrid_scheduling_simulator_v10_186 — ENH-162.

Covers engine shape, registry/hub wiring, work-mode-mix
validation, effective headcount math, TSL composition,
utilisation band proxy, wellbeing pressure flag, scenario
comparison, determinism, productivity profile, honest
deferrals, no-regression on prior arc standards.
"""
from __future__ import annotations

import importlib
import inspect


# ---------------------------------------------------------------- shape


class TestModuleShape:

    def test_module_imports(self):
        m = importlib.import_module('utils.hybrid_scheduling_simulator')
        assert m is not None

    def test_engine_class_exposed(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        assert inspect.isclass(HybridSchedulingSimulator)

    def test_dataclasses_exposed(self):
        from utils.hybrid_scheduling_simulator import (
            HybridScenario, TeamAssignment, ProductivityProfile,
            ScenarioProjection, TeamProjection, ScenarioComparison,
        )
        for cls in (HybridScenario, TeamAssignment, ProductivityProfile,
                    ScenarioProjection, TeamProjection, ScenarioComparison):
            assert hasattr(cls, '__dataclass_fields__')

    def test_work_mode_enum(self):
        from utils.hybrid_scheduling_simulator import WorkMode
        names = {m.name for m in WorkMode}
        assert {'REMOTE', 'HYBRID', 'ONSITE', 'FIELD'}.issubset(names)

    def test_engine_public_methods(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        public = {n for n in dir(HybridSchedulingSimulator)
                  if not n.startswith('_')}
        assert {
            'project', 'compare', 'list_projections', 'board_summary',
        }.issubset(public)


# ------------------------------------------------------------ registry


class TestRegistry:

    def test_enh_162_active(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-162')
        assert s.status == 'active'

    def test_enh_162_engine_named(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-162')
        assert 'hybrid_scheduling_simulator' in s.affected_engines

    def test_enh_162_batch_v10_186(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-162')
        assert getattr(s, 'implementation_batch', None) == 'v10.186'


# -------------------------------------------------------- hub integration


class TestHubIntegration:

    def test_tier32_entry_present(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        assert '"hybrid_scheduling_simulator"' in src
        assert '"HybridSchedulingSimulator"' in src
        assert 'ENH-162' in src

    def test_tier32_appears_after_wellbeing(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        idx_well = src.find('"wellbeing_integration"')
        idx_hyb = src.find('"hybrid_scheduling_simulator"')
        assert idx_well != -1 and idx_hyb != -1
        assert idx_hyb > idx_well


# --------------------------------------------------------- helpers


def _scenario(scenario_id, mix, headcount=10, forecast=100.0,
              productivity_profile=None, channel="retail_cc"):
    from utils.hybrid_scheduling_simulator import (
        HybridScenario, TeamAssignment,
    )
    return HybridScenario(
        scenario_id=scenario_id,
        description=f"scenario {scenario_id}",
        team_assignments=(TeamAssignment(
            team_key="t1", channel_key=channel,
            work_mode_mix=mix,
            headcount=headcount, forecast_arrivals_per_hour=forecast,
        ),),
        productivity_profile=productivity_profile,
    )


# ----------------------------------------------- mix validation


class TestMixValidation:

    def test_mix_must_sum_to_1(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        bad = _scenario('bad', (("REMOTE", 0.5), ("ONSITE", 0.3)))
        try:
            sim.project(bad)
            assert False, "should reject mix not summing to 1.0"
        except ValueError:
            pass

    def test_unknown_mode_rejected(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        bad = _scenario('bad', (("LUNAR", 1.0),))
        try:
            sim.project(bad)
            assert False, "should reject unknown mode"
        except ValueError:
            pass

    def test_negative_fraction_rejected(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        bad = _scenario('bad', (("ONSITE", 1.5), ("REMOTE", -0.5)))
        try:
            sim.project(bad)
            assert False, "should reject negative fraction"
        except ValueError:
            pass

    def test_empty_mix_rejected(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        bad = _scenario('bad', ())
        try:
            sim.project(bad)
            assert False, "should reject empty mix"
        except ValueError:
            pass

    def test_valid_mix_accepted(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        sim.project(_scenario('ok', (("REMOTE", 0.5), ("ONSITE", 0.5))))


# --------------------------------------------- effective headcount


class TestEffectiveHeadcount:

    def test_no_profile_means_raw_equals_effective(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        p = sim.project(_scenario('a', (("REMOTE", 1.0),), headcount=10))
        assert p.aggregate_effective_headcount == 10.0

    def test_profile_applied(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, ProductivityProfile,
        )
        sim = HybridSchedulingSimulator()
        prof = ProductivityProfile(remote_factor=0.85, onsite_factor=1.0)
        p = sim.project(_scenario(
            'a', (("REMOTE", 0.6), ("ONSITE", 0.4)),
            headcount=10, productivity_profile=prof,
        ))
        # 10 * (0.6*0.85 + 0.4*1.0) = 9.10
        assert abs(p.aggregate_effective_headcount - 9.10) < 1e-9

    def test_aggregate_sums_across_teams(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, HybridScenario, TeamAssignment,
        )
        sim = HybridSchedulingSimulator()
        sc = HybridScenario(
            scenario_id='multi', description='two teams',
            team_assignments=(
                TeamAssignment(
                    team_key='t1', channel_key='c1',
                    work_mode_mix=(("ONSITE", 1.0),),
                    headcount=10, forecast_arrivals_per_hour=10.0,
                ),
                TeamAssignment(
                    team_key='t2', channel_key='c2',
                    work_mode_mix=(("ONSITE", 1.0),),
                    headcount=15, forecast_arrivals_per_hour=10.0,
                ),
            ),
        )
        p = sim.project(sc)
        assert p.aggregate_effective_headcount == 25.0


# ---------------------------------------- TSL composition


class TestTSLComposition:

    def _sim_with_tsl(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        from utils.tsl_optimization import (
            TSLOptimizationEngine, TSLTarget, TSLChannelType,
        )
        tsl = TSLOptimizationEngine()
        tsl.set_target(TSLTarget(
            channel_key='retail_cc', channel_type=TSLChannelType.CALL_CENTER,
            target_pct=0.80, threshold_seconds=20.0, aht_seconds=180.0,
        ))
        return HybridSchedulingSimulator(tsl_engine=tsl)

    def test_no_tsl_engine_returns_none(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        p = sim.project(_scenario('a', (("ONSITE", 1.0),)))
        for t in p.team_projections:
            assert t.projected_sl is None
            assert t.sl_target is None
            assert t.meets_target is None

    def test_tsl_attached_populates_sl(self):
        sim = self._sim_with_tsl()
        p = sim.project(_scenario('a', (("ONSITE", 1.0),)))
        for t in p.team_projections:
            assert t.projected_sl is not None
            assert 0.0 <= t.projected_sl <= 1.0
            assert t.sl_target == 0.80
            assert isinstance(t.meets_target, bool)

    def test_unknown_channel_returns_none_sl(self):
        sim = self._sim_with_tsl()
        p = sim.project(_scenario('a', (("ONSITE", 1.0),),
                                  channel='unknown_channel'))
        for t in p.team_projections:
            assert t.projected_sl is None

    def test_zero_effective_headcount_returns_breach(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, ProductivityProfile,
        )
        sim = HybridSchedulingSimulator()
        # Zero productivity + 10 raw = 0 effective
        prof = ProductivityProfile(remote_factor=0.0, onsite_factor=0.0)
        p = sim.project(_scenario(
            'a', (("REMOTE", 1.0),), headcount=10,
            productivity_profile=prof,
        ))
        for t in p.team_projections:
            assert t.utilization_band_projected == 'breach'


# --------------------------------- utilisation band proxy


class TestUtilizationBandProxy:

    def test_low_load_under_used(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        p = sim.project(_scenario(
            'a', (("ONSITE", 1.0),), headcount=20, forecast=10.0,
        ))
        for t in p.team_projections:
            assert t.utilization_band_projected == 'under_used'

    def test_high_load_breach(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        # 1 agent, 100 cph * 180s = 5 erlangs offered, ratio 5.0 → breach
        p = sim.project(_scenario(
            'a', (("ONSITE", 1.0),), headcount=1, forecast=100.0,
        ))
        for t in p.team_projections:
            assert t.utilization_band_projected == 'breach'

    def test_pressure_flag_set_when_stretched(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        p = sim.project(_scenario(
            'a', (("ONSITE", 1.0),), headcount=1, forecast=100.0,
        ))
        for t in p.team_projections:
            assert t.wellbeing_pressure_flag is True

    def test_pressure_flag_clear_when_balanced(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        # 10 agents, 100 cph * 180s / 3600 = 5 erlangs, 5/10 = 0.50 → balanced
        p = sim.project(_scenario(
            'a', (("ONSITE", 1.0),), headcount=10, forecast=100.0,
        ))
        for t in p.team_projections:
            assert t.wellbeing_pressure_flag is False


# ------------------------------------------------- comparison


class TestScenarioComparison:

    def test_compare_returns_deltas(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, ProductivityProfile,
        )
        sim = HybridSchedulingSimulator()
        baseline = _scenario('base', (("ONSITE", 1.0),), headcount=10)
        prof = ProductivityProfile(remote_factor=0.85, onsite_factor=1.0)
        alt = _scenario('alt', (("REMOTE", 1.0),),
                        headcount=10, productivity_profile=prof)
        cmp = sim.compare(baseline, [alt])
        assert cmp.baseline_id == 'base'
        assert 'alt' in cmp.alternatives
        assert 'alt' in cmp.deltas
        assert abs(cmp.deltas['alt']['effective_headcount_delta']
                   - (-1.5)) < 1e-9

    def test_compare_multiple_alternatives(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, ProductivityProfile,
        )
        sim = HybridSchedulingSimulator()
        baseline = _scenario('base', (("ONSITE", 1.0),))
        alt1 = _scenario('a1', (("REMOTE", 1.0),),
                         productivity_profile=ProductivityProfile(
                             remote_factor=0.9))
        alt2 = _scenario('a2', (("REMOTE", 0.5), ("ONSITE", 0.5)),
                         productivity_profile=ProductivityProfile(
                             remote_factor=0.8, onsite_factor=1.0))
        cmp = sim.compare(baseline, [alt1, alt2])
        assert len(cmp.alternatives) == 2
        assert 'a1' in cmp.deltas
        assert 'a2' in cmp.deltas


# ----------------------------------------------- determinism


class TestDeterminism:

    def test_same_input_same_output(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        sc = _scenario('a', (("ONSITE", 1.0),), headcount=10)
        p1 = sim.project(sc)
        p2 = sim.project(sc)
        assert (p1.aggregate_effective_headcount
                == p2.aggregate_effective_headcount)
        assert p1.n_teams_under_pressure == p2.n_teams_under_pressure


# ------------------------------------------ empty / edge


class TestEdgeCases:

    def test_empty_team_assignments(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, HybridScenario,
        )
        sim = HybridSchedulingSimulator()
        sc = HybridScenario(
            scenario_id='empty', description='no teams',
            team_assignments=(),
        )
        p = sim.project(sc)
        assert p.aggregate_effective_headcount == 0.0
        assert p.n_teams_under_pressure == 0
        assert p.n_teams_with_target is None

    def test_to_dict_serialisable(self):
        import json
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        sim = HybridSchedulingSimulator()
        p = sim.project(_scenario('a', (("ONSITE", 1.0),)))
        d = p.to_dict()
        # Round-trip JSON
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2['scenario_id'] == 'a'


# ------------------------------------------- honest deferrals


class TestHonestDeferrals:

    def test_all_four_deferrals_present(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        bs = HybridSchedulingSimulator().board_summary()
        deferrals = bs.get('deferrals', {})
        for key in (
            'TRAVEL_TIME_REGRESSION',
            'PRODUCTIVITY_DELTA_FROM_MODE',
            'LIVE_WHATIF_DASHBOARD',
            'MULTI_OBJECTIVE_OPTIMIZATION',
        ):
            assert key in deferrals, f'deferral missing: {key}'

    def test_regulatory_basis_named(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator,
        )
        rb = HybridSchedulingSimulator().board_summary()['regulatory_basis']
        assert 'Hybrid' in rb
        assert 'BSC' in rb

    def test_productivity_profile_supplied_flag(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, ProductivityProfile,
        )
        sim = HybridSchedulingSimulator()
        p_no = sim.project(_scenario('a', (("ONSITE", 1.0),)))
        assert p_no.productivity_profile_supplied is False
        p_yes = sim.project(_scenario(
            'b', (("ONSITE", 1.0),),
            productivity_profile=ProductivityProfile(),
        ))
        assert p_yes.productivity_profile_supplied is True


# ----------------------------------------------------- no regression


class TestNoRegression:

    def test_enh_156_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-156').status == 'active'

    def test_enh_157_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-157').status == 'active'

    def test_enh_158_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-158').status == 'active'

    def test_enh_159_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-159').status == 'active'

    def test_enh_160_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-160').status == 'active'

    def test_enh_161_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-161').status == 'active'
