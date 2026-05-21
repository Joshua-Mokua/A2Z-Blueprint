"""tests.test_resource_investment_case_v10_187 — ENH-163.

Covers engine shape, registry/hub wiring, NPV math, payback
math, IRR detection, validation of cost assumptions, no-savings
edge cases, qualitative benefits passthrough, deferrals
acknowledgement, JSON round-trip, no-regression on prior arc
standards.
"""
from __future__ import annotations

import importlib
import inspect


# ---------------------------------------------------------------- shape


class TestModuleShape:

    def test_module_imports(self):
        m = importlib.import_module('utils.resource_investment_case')
        assert m is not None

    def test_engine_class_exposed(self):
        from utils.resource_investment_case import (
            ResourceInvestmentCaseEngine,
        )
        assert inspect.isclass(ResourceInvestmentCaseEngine)

    def test_dataclasses_exposed(self):
        from utils.resource_investment_case import (
            CostAssumptions, InvestmentCase, AnnualCashFlow,
        )
        for cls in (CostAssumptions, InvestmentCase, AnnualCashFlow):
            assert hasattr(cls, '__dataclass_fields__')

    def test_engine_public_methods(self):
        from utils.resource_investment_case import (
            ResourceInvestmentCaseEngine,
        )
        public = {n for n in dir(ResourceInvestmentCaseEngine)
                  if not n.startswith('_')}
        assert {
            'generate_case', 'list_cases', 'board_summary',
        }.issubset(public)


# ------------------------------------------------------------ registry


class TestRegistry:

    def test_enh_163_active(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-163')
        assert s.status == 'active'

    def test_enh_163_engine_named(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-163')
        assert 'resource_investment_case' in s.affected_engines

    def test_enh_163_batch_v10_187(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-163')
        assert getattr(s, 'implementation_batch', None) == 'v10.187'


# -------------------------------------------------------- hub integration


class TestHubIntegration:

    def test_tier32_entry_present(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        assert '"resource_investment_case"' in src
        assert '"ResourceInvestmentCaseEngine"' in src
        assert 'ENH-163' in src

    def test_tier32_appears_after_hybrid_simulator(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        idx_hyb = src.find('"hybrid_scheduling_simulator"')
        idx_inv = src.find('"resource_investment_case"')
        assert idx_hyb != -1 and idx_inv != -1
        assert idx_inv > idx_hyb


# --------------------------------------------------- helpers


class _StubProjection:
    """Test stub matching ScenarioProjection duck-type."""
    def __init__(self, scenario_id, fte):
        self.scenario_id = scenario_id
        self.aggregate_effective_headcount = fte


def _engine():
    from utils.resource_investment_case import (
        ResourceInvestmentCaseEngine,
    )
    return ResourceInvestmentCaseEngine()


def _assumptions(**overrides):
    from utils.resource_investment_case import CostAssumptions
    defaults = dict(
        annual_cost_per_fte=1_500_000,
        one_time_implementation_cost=5_000_000,
        discount_rate=0.12,
        horizon_years=5,
        annual_other_costs=200_000,
        qualitative_benefits=("Benefit A", "Benefit B"),
    )
    defaults.update(overrides)
    return CostAssumptions(**defaults)


# ---------------------------------------- assumption validation


class TestAssumptionValidation:

    def test_negative_cost_per_fte_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "X", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(annual_cost_per_fte=-1),
            )
            assert False, "should reject"
        except ValueError:
            pass

    def test_negative_one_time_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "X", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(one_time_implementation_cost=-1),
            )
            assert False, "should reject"
        except ValueError:
            pass

    def test_discount_rate_above_100pct_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "X", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(discount_rate=1.5),
            )
            assert False, "should reject"
        except ValueError:
            pass

    def test_negative_discount_rate_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "X", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(discount_rate=-0.05),
            )
            assert False, "should reject"
        except ValueError:
            pass

    def test_zero_horizon_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "X", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(horizon_years=0),
            )
            assert False, "should reject"
        except ValueError:
            pass

    def test_excessive_horizon_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "X", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(horizon_years=100),
            )
            assert False, "should reject"
        except ValueError:
            pass

    def test_empty_case_id_rejected(self):
        ica = _engine()
        try:
            ica.generate_case(
                "", _StubProjection("b", 10), _StubProjection("a", 8),
                _assumptions(),
            )
            assert False, "should reject"
        except ValueError:
            pass


# ---------------------------------------------------- NPV math


class TestNPVMath:

    def test_savings_scenario_positive_npv(self):
        ica = _engine()
        case = ica.generate_case(
            "S1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        # 2 FTE saved @ 1.5M = 3M labour saving
        # less 200k other cost → 2.8M annual net
        # one-time 5M, discount 12%, 5y → NPV ~5.09M
        assert case.npv > 0
        assert abs(case.annual_net_cash_flow - 2_800_000) < 0.01

    def test_no_savings_scenario_negative_npv(self):
        ica = _engine()
        case = ica.generate_case(
            "S2", _StubProjection("b", 10), _StubProjection("a", 15),
            _assumptions(),
        )
        # 5 more FTE = 7.5M extra labour cost + 200k = 7.7M annual outflow
        assert case.npv < 0
        assert case.annual_net_cash_flow < 0

    def test_zero_one_time_npv_is_present_value_of_savings(self):
        ica = _engine()
        case = ica.generate_case(
            "S3", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(one_time_implementation_cost=0),
        )
        # NPV should be sum of discounted CFs (no upfront)
        assert case.npv > 0

    def test_zero_horizon_zero_savings_npv_negative_one_time(self):
        ica = _engine()
        case = ica.generate_case(
            "S4", _StubProjection("b", 10), _StubProjection("a", 10),
            _assumptions(horizon_years=1, one_time_implementation_cost=1000),
        )
        # No FTE delta, no other costs change either... but other_costs
        # is added every year by convention
        # annual_net = 0 - 200_000 = -200_000
        # NPV = -1000 + (-200_000)/1.12 = ~-179,571
        assert case.npv < 0

    def test_npv_decreases_with_higher_discount_rate(self):
        ica = _engine()
        case_low = ica.generate_case(
            "L", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(discount_rate=0.05),
        )
        case_high = ica.generate_case(
            "H", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(discount_rate=0.30),
        )
        assert case_low.npv > case_high.npv


# ------------------------------------------------- payback math


class TestPaybackMath:

    def test_undiscounted_payback_correct(self):
        ica = _engine()
        case = ica.generate_case(
            "P1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        # 5M / 2.8M = ~1.79 years
        assert abs(case.payback_years_undiscounted - 5_000_000 / 2_800_000) \
            < 0.001

    def test_no_savings_payback_none(self):
        ica = _engine()
        case = ica.generate_case(
            "P2", _StubProjection("b", 10), _StubProjection("a", 15),
            _assumptions(),
        )
        assert case.payback_years_undiscounted is None

    def test_discounted_payback_longer_than_undiscounted(self):
        ica = _engine()
        case = ica.generate_case(
            "P3", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        assert (case.payback_years_discounted
                > case.payback_years_undiscounted)

    def test_discounted_payback_none_when_horizon_too_short(self):
        ica = _engine()
        # 1 FTE saved @ 1.5M = 1.5M, less 200k = 1.3M annual
        # 5M one-time → discounted payback > 4y at 12%
        # If horizon = 2y, never recouped
        case = ica.generate_case(
            "P4", _StubProjection("b", 10), _StubProjection("a", 9),
            _assumptions(horizon_years=2),
        )
        assert case.payback_years_discounted is None


# ---------------------------------------------------- IRR


class TestIRR:

    def test_irr_for_savings_scenario(self):
        ica = _engine()
        case = ica.generate_case(
            "I1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        # Should be solvable; ~48% in our probe
        assert case.irr is not None
        assert case.irr > 0

    def test_irr_none_when_all_cash_flows_negative(self):
        ica = _engine()
        case = ica.generate_case(
            "I2", _StubProjection("b", 10), _StubProjection("a", 15),
            _assumptions(),
        )
        # All-negative CFs → no IRR
        assert case.irr is None


# --------------------------------------- cash flow series


class TestCashFlowSeries:

    def test_correct_number_of_records(self):
        ica = _engine()
        case = ica.generate_case(
            "CF1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(horizon_years=7),
        )
        assert len(case.annual_cash_flows) == 7

    def test_cumulative_nominal_starts_negative_when_one_time_present(self):
        ica = _engine()
        case = ica.generate_case(
            "CF2", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        # Year 1: -5M + 2.8M = -2.2M
        assert case.annual_cash_flows[0].cumulative_nominal < 0

    def test_cumulative_nominal_grows_year_by_year(self):
        ica = _engine()
        case = ica.generate_case(
            "CF3", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        cums = [cf.cumulative_nominal for cf in case.annual_cash_flows]
        assert all(cums[i] < cums[i+1] for i in range(len(cums)-1))

    def test_discounted_cf_smaller_than_nominal(self):
        ica = _engine()
        case = ica.generate_case(
            "CF4", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        for cf in case.annual_cash_flows:
            # Positive nominal CF, positive discount → disc < nom
            assert abs(cf.discounted_cash_flow) < abs(cf.nominal_cash_flow)


# ------------------------------------- qualitative benefits


class TestQualitativeBenefits:

    def test_benefits_pass_through_to_case(self):
        ica = _engine()
        case = ica.generate_case(
            "Q1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(qualitative_benefits=(
                "Wellbeing improvement", "ESG signal", "Attrition reduction",
            )),
        )
        assert "Wellbeing improvement" in case.qualitative_benefits
        assert "ESG signal" in case.qualitative_benefits
        assert "Attrition reduction" in case.qualitative_benefits

    def test_no_benefits_does_not_invent_any(self):
        ica = _engine()
        case = ica.generate_case(
            "Q2", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(qualitative_benefits=()),
        )
        assert case.qualitative_benefits == ()


# ---------------------------------------- ENH-162 composition


class TestScenarioProjectionComposition:
    """End-to-end with real ScenarioProjection objects from ENH-162."""

    def test_with_real_projections(self):
        from utils.hybrid_scheduling_simulator import (
            HybridSchedulingSimulator, HybridScenario, TeamAssignment,
            ProductivityProfile,
        )
        sim = HybridSchedulingSimulator()
        baseline = sim.project(HybridScenario(
            scenario_id="b_real",
            description="onsite baseline",
            team_assignments=(TeamAssignment(
                team_key='t1', channel_key='c1',
                work_mode_mix=(("ONSITE", 1.0),),
                headcount=10, forecast_arrivals_per_hour=100.0,
            ),),
        ))
        prof = ProductivityProfile(remote_factor=0.85, onsite_factor=1.0)
        alt = sim.project(HybridScenario(
            scenario_id="a_real",
            description="hybrid alternative",
            team_assignments=(TeamAssignment(
                team_key='t1', channel_key='c1',
                work_mode_mix=(("REMOTE", 0.6), ("ONSITE", 0.4)),
                headcount=10, forecast_arrivals_per_hour=100.0,
            ),),
            productivity_profile=prof,
        ))
        ica = _engine()
        case = ica.generate_case(
            "REAL", baseline, alt, _assumptions(),
        )
        assert case.baseline_scenario_id == "b_real"
        assert case.alternative_scenario_id == "a_real"


# --------------------------------------- deferrals + serialization


class TestDeferralsAcknowledgement:

    def test_case_carries_deferrals(self):
        ica = _engine()
        case = ica.generate_case(
            "D1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        assert "DETAILED_TAX_TREATMENT" in case.deferrals_acknowledged
        assert "INFLATION_INDEXATION" in case.deferrals_acknowledged
        assert "REVENUE_UPSIDE_FROM_SL" in case.deferrals_acknowledged
        assert "MULTI_YEAR_RAMP" in case.deferrals_acknowledged

    def test_board_summary_has_all_deferrals(self):
        bs = _engine().board_summary()
        for k in (
            "DETAILED_TAX_TREATMENT", "INFLATION_INDEXATION",
            "REVENUE_UPSIDE_FROM_SL", "MULTI_YEAR_RAMP",
        ):
            assert k in bs["deferrals"]

    def test_npv_formula_in_board_summary(self):
        bs = _engine().board_summary()
        assert "NPV" in bs.get("npv_formula", "")


class TestSerialization:

    def test_to_dict_round_trip(self):
        import json
        ica = _engine()
        case = ica.generate_case(
            "JSON1", _StubProjection("b", 10), _StubProjection("a", 8),
            _assumptions(),
        )
        d = case.to_dict()
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2["case_id"] == "JSON1"
        assert d2["npv"] == case.npv

    def test_assumptions_to_dict(self):
        a = _assumptions()
        d = a.to_dict()
        assert d["annual_cost_per_fte"] == 1_500_000
        assert d["discount_rate"] == 0.12


# ----------------------------------------------------- no regression


class TestNoRegression:

    def test_enh_156_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-156').status == 'active'

    def test_enh_162_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-162').status == 'active'

    def test_audit_clean(self):
        # Quick smoke: ENH-160 / ENH-161 still wired
        from utils.standards_registry import get_standard
        assert get_standard('ENH-160').status == 'active'
        assert get_standard('ENH-161').status == 'active'
