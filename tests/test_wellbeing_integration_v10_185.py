"""tests.test_wellbeing_integration_v10_185 — ENH-161 tests.

Covers engine shape, registry/hub wiring, n<5 suppression on
total cohort, n<5 suppression on assessable cohort (post opt-out),
opt-out exclusion, no-individual-leakage in outputs, GREEN /
AMBER / RED band logic, EAP escalation, sustained utilization
breach composition, multi-team summary, deferrals exposed,
no-regression on prior arc standards (ENH-156..ENH-160).
"""
from __future__ import annotations

import importlib
import inspect


# ---------------------------------------------------------------- shape


class TestModuleShape:

    def test_module_imports(self):
        m = importlib.import_module('utils.wellbeing_integration')
        assert m is not None

    def test_engine_class_exposed(self):
        from utils.wellbeing_integration import WellbeingIntegrationEngine
        assert inspect.isclass(WellbeingIntegrationEngine)

    def test_team_signal_dataclass_exposed(self):
        from utils.wellbeing_integration import TeamSignal
        fields = {f.name for f in TeamSignal.__dataclass_fields__.values()}
        assert {
            'team_code', 'n_total', 'n_assessed', 'n_optout',
            'band', 'risk_band_counts',
            'sustained_utilization_breach',
            'intervention_level', 'rationale', 'data_suppressed',
        }.issubset(fields)

    def test_band_enum_exposed(self):
        from utils.wellbeing_integration import TeamWellbeingBand
        names = {b.name for b in TeamWellbeingBand}
        assert names == {'GREEN', 'AMBER', 'RED'}

    def test_intervention_enum_exposed(self):
        from utils.wellbeing_integration import InterventionLevel
        names = {lv.name for lv in InterventionLevel}
        assert names == {
            'MONITOR', 'SOFT_INTERVENTION',
            'HARD_INTERVENTION', 'EAP_REFERRAL',
        }

    def test_min_team_size_constant(self):
        from utils.wellbeing_integration import MIN_TEAM_SIZE
        assert MIN_TEAM_SIZE == 5

    def test_engine_public_methods(self):
        from utils.wellbeing_integration import WellbeingIntegrationEngine
        public = {n for n in dir(WellbeingIntegrationEngine)
                  if not n.startswith('_')}
        assert {
            'assess_team_signal', 'multi_team_summary',
            'list_signals', 'board_summary',
        }.issubset(public)


# ------------------------------------------------------------ registry


class TestRegistry:

    def test_enh_161_active(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-161')
        assert s.status == 'active'

    def test_enh_161_engine_named(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-161')
        assert 'wellbeing_integration' in s.affected_engines

    def test_enh_161_batch_v10_185(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-161')
        assert getattr(s, 'implementation_batch', None) == 'v10.185'


# -------------------------------------------------------- hub integration


class TestHubIntegration:

    def test_tier32_entry_present(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        assert '"wellbeing_integration"' in src
        assert '"WellbeingIntegrationEngine"' in src
        assert 'ENH-161' in src

    def test_tier32_appears_after_utilization_dashboard(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        idx_util = src.find('"utilization_dashboard"')
        idx_well = src.find('"wellbeing_integration"')
        assert idx_util != -1 and idx_well != -1
        assert idx_well > idx_util


# ----------------------------------------------------- engine setup


def _make_engine(mapping=None, util_engine=None):
    """Test helper: build engine with a stub assessor."""
    from utils.wellbeing_integration import WellbeingIntegrationEngine
    if mapping is None:
        return WellbeingIntegrationEngine(
            wellness_assessor=lambda s: {"risk_level": "Low"},
            utilization_engine=util_engine,
        )
    return WellbeingIntegrationEngine(
        wellness_assessor=lambda s: mapping.get(s, {}),
        utilization_engine=util_engine,
    )


# ------------------------------------------------- privacy: suppression


class TestSuppressionOnTotalCohort:
    """n_total < 5 → suppressed before any per-employee access."""

    def test_n_2_suppressed(self):
        sig = _make_engine().assess_team_signal('t', ['s1', 's2'])
        assert sig.data_suppressed is True

    def test_n_4_suppressed(self):
        sig = _make_engine().assess_team_signal(
            't', ['s1', 's2', 's3', 's4'])
        assert sig.data_suppressed is True

    def test_n_5_not_suppressed(self):
        sig = _make_engine().assess_team_signal(
            't', ['s1', 's2', 's3', 's4', 's5'])
        assert sig.data_suppressed is False

    def test_suppressed_emits_no_individual_signals(self):
        sig = _make_engine().assess_team_signal('t', ['s1', 's2'])
        assert sig.risk_band_counts == {
            'Low': 0, 'Moderate': 0, 'High': 0}
        assert sig.n_assessed == 0


class TestSuppressionOnAssessableCohort:
    """n_assessed < 5 (post opt-out) → suppressed."""

    def test_all_optout_suppressed(self):
        mapping = {f's{i}': {} for i in range(6)}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.data_suppressed is True
        assert sig.n_optout == 6

    def test_4_assessed_2_optout_suppressed(self):
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(4)}
        mapping.update({'s4': {}, 's5': {}})
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.data_suppressed is True

    def test_5_assessed_1_optout_published(self):
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(5)}
        mapping['s5'] = {}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.data_suppressed is False
        assert sig.n_assessed == 5
        assert sig.n_optout == 1


class TestNoIndividualLeakage:
    """No staff code or per-individual score appears in outputs."""

    def test_to_dict_has_no_staff_codes(self):
        mapping = {
            'staff_001': {"risk_level": "Low"},
            'staff_002': {"risk_level": "Moderate"},
            'staff_003': {"risk_level": "High"},
            'staff_004': {"risk_level": "Low"},
            'staff_005': {"risk_level": "Low"},
        }
        sig = _make_engine(mapping).assess_team_signal(
            'team_X', list(mapping.keys()))
        d = sig.to_dict()
        flat = repr(d)
        for code in mapping:
            assert code not in flat, (
                f"individual code {code} leaked into TeamSignal.to_dict()")

    def test_rationale_does_not_name_individuals(self):
        mapping = {
            'whistleblower_007': {"risk_level": "High"},
            'staff_a': {"risk_level": "Low"},
            'staff_b': {"risk_level": "Low"},
            'staff_c': {"risk_level": "Low"},
            'staff_d': {"risk_level": "Low"},
        }
        sig = _make_engine(mapping).assess_team_signal(
            'team_X', list(mapping.keys()))
        assert 'whistleblower_007' not in sig.rationale


# ------------------------------------------------- band classification


class TestBandClassification:

    def test_all_low_is_green(self):
        from utils.wellbeing_integration import (
            TeamWellbeingBand, InterventionLevel,
        )
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(6)}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.band == TeamWellbeingBand.GREEN
        assert sig.intervention_level == InterventionLevel.MONITOR

    def test_one_high_pushes_to_amber(self):
        from utils.wellbeing_integration import (
            TeamWellbeingBand, InterventionLevel,
        )
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(5)}
        mapping['s5'] = {"risk_level": "High"}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.band == TeamWellbeingBand.AMBER
        assert sig.intervention_level == InterventionLevel.SOFT_INTERVENTION

    def test_three_high_is_red(self):
        from utils.wellbeing_integration import TeamWellbeingBand
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(3)}
        for i in range(3, 6):
            mapping[f's{i}'] = {"risk_level": "High"}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.band == TeamWellbeingBand.RED

    def test_high_majority_triggers_eap(self):
        from utils.wellbeing_integration import InterventionLevel
        # 3 High out of 6 → 50% → triggers EAP_REFERRAL escalation
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(3)}
        for i in range(3, 6):
            mapping[f's{i}'] = {"risk_level": "High"}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.intervention_level == InterventionLevel.EAP_REFERRAL

    def test_unknown_risk_level_treated_as_optout(self):
        # Defensive: don't fabricate a category for unknown values
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(5)}
        mapping['s5'] = {"risk_level": "Catastrophic"}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        # 5 Low + 1 unknown → 1 counted as opt-out
        assert sig.n_optout == 1
        assert sig.risk_band_counts['Low'] == 5


# ------------------------------------------- utilization composition


class TestUtilizationComposition:
    """sustained_utilization_breach via ENH-160 composition."""

    def test_no_util_engine_breach_false(self):
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(5)}
        sig = _make_engine(mapping).assess_team_signal(
            't', list(mapping.keys()))
        assert sig.sustained_utilization_breach is False

    def test_with_util_engine_breach_detected(self):
        from utils.utilization_dashboard import (
            UtilizationDashboardEngine, UtilizationObservation,
        )
        util = UtilizationDashboardEngine()
        util.submit_observation(UtilizationObservation(
            channel_key='c1', team_key='breach_team', manager_id='m1',
            agents_available=10, agents_busy=10,
            observed_arrivals_per_hour=10.0, observed_aht_seconds=60.0,
        ))
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(5)}
        e = _make_engine(mapping, util_engine=util)
        sig = e.assess_team_signal('breach_team', list(mapping.keys()))
        assert sig.sustained_utilization_breach is True

    def test_util_engine_failure_safe(self):
        # If utilization engine raises, we fall back to False, not crash
        class _Broken:
            def list_breaches(self_inner):
                raise RuntimeError("simulated outage")
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(5)}
        e = _make_engine(mapping, util_engine=_Broken())
        sig = e.assess_team_signal('t', list(mapping.keys()))
        assert sig.sustained_utilization_breach is False


# -------------------------------------------------- multi-team summary


class TestMultiTeamSummary:

    def test_summary_counts_suppressed_and_published(self):
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(6)}
        e = _make_engine(mapping)
        teams = [
            ('big_team', list(mapping.keys())),
            ('tiny', ['x', 'y']),
        ]
        out = e.multi_team_summary(teams)
        assert out['n_teams_total'] == 2
        assert out['n_teams_suppressed'] == 1
        assert out['n_teams_published'] == 1

    def test_summary_band_distribution(self):
        mapping = {f's{i}': {"risk_level": "Low"} for i in range(6)}
        e = _make_engine(mapping)
        out = e.multi_team_summary([('t', list(mapping.keys()))])
        assert out['bands_distribution']['green'] == 1
        assert out['bands_distribution']['red'] == 0


# ------------------------------------------------ honest deferrals


class TestHonestDeferrals:

    def test_all_four_deferrals_present(self):
        e = _make_engine()
        bs = e.board_summary()
        deferrals = bs.get('deferrals', {})
        for key in (
            'CLINICAL_VALIDATION',
            'SENTIMENT_FEED_NLP',
            'EAP_INTEGRATION_PUSH',
            'K_ANONYMITY_FORMAL',
        ):
            assert key in deferrals, f'deferral missing: {key}'

    def test_regulatory_basis_named(self):
        e = _make_engine()
        rb = e.board_summary().get('regulatory_basis', '')
        assert 'OSH' in rb or 'OSHA' in rb
        assert 'DPA' in rb or '§44' in rb

    def test_engine_does_not_diagnose(self):
        # board_summary must NOT use clinical-diagnosis language
        e = _make_engine()
        bs_text = repr(e.board_summary()).lower()
        assert 'diagnosis' not in bs_text
        assert 'diagnose' not in bs_text


# --------------------------------------------------- engine errors


class TestEngineConstruction:

    def test_missing_assessor_raises(self):
        from utils.wellbeing_integration import WellbeingIntegrationEngine
        try:
            WellbeingIntegrationEngine(wellness_assessor=None)
            assert False, "should have raised"
        except ValueError:
            pass

    def test_empty_team_code_raises(self):
        try:
            _make_engine().assess_team_signal('', ['s1'] * 6)
            assert False, "should have raised"
        except ValueError:
            pass


# ----------------------------------------------------- no regression


class TestNoRegression:
    """Prior Resource Optimization standards still active."""

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
