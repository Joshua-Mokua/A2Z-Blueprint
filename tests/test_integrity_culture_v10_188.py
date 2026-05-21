"""tests.test_integrity_culture_v10_188 — ENH-164 tests.

Covers engine shape, registry/hub wiring, weights validation,
suppression at n<5, score validation (0-100 range), composite
math, band classification, benchmark relative band, custom
weights, multi-team rollup, deferrals, no-regression on prior
arc standards.
"""
from __future__ import annotations

import importlib
import inspect


# ---------------------------------------------------------------- shape


class TestModuleShape:

    def test_module_imports(self):
        m = importlib.import_module('utils.integrity_culture')
        assert m is not None

    def test_engine_class_exposed(self):
        from utils.integrity_culture import IntegrityCultureEngine
        assert inspect.isclass(IntegrityCultureEngine)

    def test_dataclasses_exposed(self):
        from utils.integrity_culture import (
            CultureWeights, CultureSubmission, CultureScore,
        )
        for cls in (CultureWeights, CultureSubmission, CultureScore):
            assert hasattr(cls, '__dataclass_fields__')

    def test_band_enum(self):
        from utils.integrity_culture import CultureBand
        names = {b.name for b in CultureBand}
        assert names == {'STRONG', 'DEVELOPING', 'AT_RISK', 'CRITICAL'}

    def test_relative_band_enum(self):
        from utils.integrity_culture import RelativeBand
        names = {b.name for b in RelativeBand}
        assert names == {'LEADING', 'ON_PAR', 'LAGGING'}

    def test_min_respondents_constant(self):
        from utils.integrity_culture import MIN_RESPONDENTS
        assert MIN_RESPONDENTS == 5

    def test_engine_public_methods(self):
        from utils.integrity_culture import IntegrityCultureEngine
        public = {n for n in dir(IntegrityCultureEngine)
                  if not n.startswith('_')}
        assert {
            'score_team', 'score_multiple', 'list_scores',
            'latest_per_team', 'board_summary',
        }.issubset(public)


# ------------------------------------------------------------ registry


class TestRegistry:

    def test_enh_164_active(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-164')
        assert s.status == 'active'

    def test_enh_164_engine_named(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-164')
        assert 'integrity_culture' in s.affected_engines

    def test_enh_164_batch_v10_188(self):
        from utils.standards_registry import get_standard
        s = get_standard('ENH-164')
        assert getattr(s, 'implementation_batch', None) == 'v10.188'


# -------------------------------------------------------- hub integration


class TestHubIntegration:

    def test_tier32_entry_present(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        assert '"integrity_culture"' in src
        assert '"IntegrityCultureEngine"' in src
        assert 'ENH-164' in src

    def test_tier32_appears_after_resource_investment(self):
        with open('pages/7_admin.py', 'r') as f:
            src = f.read()
        idx_ric = src.find('"resource_investment_case"')
        idx_ic = src.find('"integrity_culture"')
        assert idx_ric != -1 and idx_ic != -1
        assert idx_ic > idx_ric


# --------------------------------------------------- helpers


def _engine(weights=None):
    from utils.integrity_culture import IntegrityCultureEngine
    return IntegrityCultureEngine(weights=weights)


def _sub(team='t1', n=10, t=80, tr=80, sn=80, cc=80, period='2026-Q1',
         bench=None):
    from utils.integrity_culture import CultureSubmission
    return CultureSubmission(
        team_code=team, n_respondents=n,
        transparency_score=t, trust_score=tr,
        sentiment_score=sn, code_of_conduct_score=cc,
        period_label=period, external_benchmark_score=bench,
    )


# ------------------------------------------------ weights


class TestCultureWeights:

    def test_default_weights_sum_to_1(self):
        from utils.integrity_culture import CultureWeights
        w = CultureWeights()
        w.validate()  # should not raise

    def test_unbalanced_weights_rejected(self):
        from utils.integrity_culture import CultureWeights
        try:
            CultureWeights(
                transparency=0.5, trust=0.3,
                sentiment=0.3, code_of_conduct=0.1,
            ).validate()
            assert False, "should reject"
        except ValueError:
            pass

    def test_negative_weight_rejected(self):
        from utils.integrity_culture import CultureWeights
        try:
            CultureWeights(
                transparency=-0.25, trust=0.5,
                sentiment=0.5, code_of_conduct=0.25,
            ).validate()
            assert False, "should reject"
        except ValueError:
            pass

    def test_engine_rejects_bad_weights_at_construction(self):
        from utils.integrity_culture import (
            IntegrityCultureEngine, CultureWeights,
        )
        try:
            IntegrityCultureEngine(weights=CultureWeights(
                transparency=0.6, trust=0.6,
                sentiment=0.0, code_of_conduct=0.0,
            ))
            assert False, "should reject"
        except ValueError:
            pass


# -------------------------------------- submission validation


class TestSubmissionValidation:

    def test_empty_team_code_rejected(self):
        try:
            _engine().score_team(_sub(team=''))
            assert False, "should reject"
        except ValueError:
            pass

    def test_empty_period_label_rejected(self):
        try:
            _engine().score_team(_sub(period=''))
            assert False, "should reject"
        except ValueError:
            pass

    def test_negative_n_respondents_rejected(self):
        try:
            _engine().score_team(_sub(n=-1))
            assert False, "should reject"
        except ValueError:
            pass

    def test_score_above_100_rejected(self):
        try:
            _engine().score_team(_sub(t=150))
            assert False, "should reject"
        except ValueError:
            pass

    def test_score_below_0_rejected(self):
        try:
            _engine().score_team(_sub(t=-10))
            assert False, "should reject"
        except ValueError:
            pass

    def test_benchmark_above_100_rejected(self):
        try:
            _engine().score_team(_sub(bench=150))
            assert False, "should reject"
        except ValueError:
            pass


# ------------------------------------------- suppression


class TestSuppression:

    def test_n_respondents_below_5_suppressed(self):
        r = _engine().score_team(_sub(n=4))
        assert r.data_suppressed is True
        assert r.composite_score is None
        assert r.band is None

    def test_n_respondents_5_published(self):
        r = _engine().score_team(_sub(n=5))
        assert r.data_suppressed is False
        assert r.composite_score is not None
        assert r.band is not None

    def test_suppressed_record_has_no_sub_scores(self):
        r = _engine().score_team(_sub(n=2))
        assert r.sub_scores == {}

    def test_suppressed_rationale_explicit(self):
        r = _engine().score_team(_sub(n=2))
        assert 'suppressed' in r.rationale.lower()

    def test_suppressed_record_carries_weights(self):
        # Even when suppressed, weights_used should be present
        # for transparency
        r = _engine().score_team(_sub(n=2))
        assert 'transparency' in r.weights_used


# --------------------------------------- composite math


class TestCompositeMath:

    def test_default_weights_equal_average(self):
        r = _engine().score_team(_sub(t=80, tr=80, sn=80, cc=80))
        assert abs(r.composite_score - 80.0) < 1e-9

    def test_known_composite(self):
        # 85*0.25 + 80*0.25 + 78*0.25 + 90*0.25 = 83.25
        r = _engine().score_team(
            _sub(t=85, tr=80, sn=78, cc=90))
        assert abs(r.composite_score - 83.25) < 1e-9

    def test_custom_weights_apply(self):
        from utils.integrity_culture import CultureWeights
        e = _engine(weights=CultureWeights(
            transparency=0.4, trust=0.3,
            sentiment=0.2, code_of_conduct=0.1,
        ))
        r = e.score_team(_sub(t=85, tr=80, sn=78, cc=90))
        # 85*0.4 + 80*0.3 + 78*0.2 + 90*0.1 = 34 + 24 + 15.6 + 9 = 82.6
        assert abs(r.composite_score - 82.6) < 1e-9

    def test_weights_used_recorded(self):
        from utils.integrity_culture import CultureWeights
        e = _engine(weights=CultureWeights(
            transparency=0.5, trust=0.3,
            sentiment=0.1, code_of_conduct=0.1,
        ))
        r = e.score_team(_sub())
        assert r.weights_used['transparency'] == 0.5
        assert r.weights_used['trust'] == 0.3


# ---------------------------------------- band classification


class TestBandClassification:

    def test_score_85_strong(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=85, tr=85, sn=85, cc=85))
        assert r.band == CultureBand.STRONG

    def test_score_70_developing(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=70, tr=70, sn=70, cc=70))
        assert r.band == CultureBand.DEVELOPING

    def test_score_50_at_risk(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=50, tr=50, sn=50, cc=50))
        assert r.band == CultureBand.AT_RISK

    def test_score_30_critical(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=30, tr=30, sn=30, cc=30))
        assert r.band == CultureBand.CRITICAL

    def test_boundary_80_is_strong(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=80, tr=80, sn=80, cc=80))
        assert r.band == CultureBand.STRONG

    def test_boundary_60_is_developing(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=60, tr=60, sn=60, cc=60))
        assert r.band == CultureBand.DEVELOPING

    def test_boundary_40_is_at_risk(self):
        from utils.integrity_culture import CultureBand
        r = _engine().score_team(_sub(t=40, tr=40, sn=40, cc=40))
        assert r.band == CultureBand.AT_RISK


# ----------------------------------------- benchmark


class TestBenchmark:

    def test_no_benchmark_returns_none(self):
        r = _engine().score_team(_sub(bench=None))
        assert r.delta_vs_benchmark is None
        assert r.relative_band is None

    def test_benchmark_leading_when_above_5(self):
        from utils.integrity_culture import RelativeBand
        # composite=80, benchmark=70 → delta=+10 → LEADING
        r = _engine().score_team(_sub(t=80, tr=80, sn=80, cc=80, bench=70))
        assert r.relative_band == RelativeBand.LEADING

    def test_benchmark_lagging_when_below_minus_5(self):
        from utils.integrity_culture import RelativeBand
        r = _engine().score_team(_sub(t=60, tr=60, sn=60, cc=60, bench=80))
        assert r.relative_band == RelativeBand.LAGGING

    def test_benchmark_on_par_when_within_5(self):
        from utils.integrity_culture import RelativeBand
        r = _engine().score_team(_sub(t=80, tr=80, sn=80, cc=80, bench=78))
        assert r.relative_band == RelativeBand.ON_PAR

    def test_delta_calculation(self):
        r = _engine().score_team(_sub(t=80, tr=80, sn=80, cc=80, bench=70))
        assert abs(r.delta_vs_benchmark - 10.0) < 1e-9


# ----------------------------------- multi-team rollup


class TestMultiTeam:

    def test_rollup_counts(self):
        e = _engine()
        out = e.score_multiple([
            _sub(team='a', n=10, t=85, tr=85, sn=85, cc=85),
            _sub(team='b', n=10, t=50, tr=50, sn=50, cc=50),
            _sub(team='c', n=2,  t=80, tr=80, sn=80, cc=80),
        ])
        assert out['n_submissions'] == 3
        assert out['n_suppressed'] == 1
        assert out['n_published'] == 2

    def test_rollup_band_distribution(self):
        e = _engine()
        out = e.score_multiple([
            _sub(team='a', n=10, t=85, tr=85, sn=85, cc=85),
            _sub(team='b', n=10, t=50, tr=50, sn=50, cc=50),
        ])
        assert out['bands_distribution']['strong'] == 1
        assert out['bands_distribution']['at_risk'] == 1

    def test_average_excludes_suppressed(self):
        e = _engine()
        out = e.score_multiple([
            _sub(team='a', n=10, t=80, tr=80, sn=80, cc=80),
            _sub(team='b', n=2, t=10, tr=10, sn=10, cc=10),
        ])
        assert abs(out['average_composite_score_published'] - 80.0) \
            < 1e-9


class TestLatestPerTeam:

    def test_latest_overwrites(self):
        e = _engine()
        e.score_team(_sub(team='alpha', n=10, t=50, tr=50, sn=50, cc=50,
                          period='Q1'))
        e.score_team(_sub(team='alpha', n=10, t=80, tr=80, sn=80, cc=80,
                          period='Q2'))
        latest = e.latest_per_team()
        assert latest['alpha'].period_label == 'Q2'
        assert latest['alpha'].composite_score == 80.0


# ------------------------------------- deferrals + serialization


class TestHonestDeferrals:

    def test_all_four_deferrals_present(self):
        bs = _engine().board_summary()
        deferrals = bs.get('deferrals', {})
        for key in (
            'NLP_TEXT_ANALYSIS',
            'REAL_TIME_BEHAVIORAL_TELEMETRY',
            'CROSS_INDUSTRY_BENCHMARK_DATA',
            'CULTURAL_SURVEY_AUTOMATION',
        ):
            assert key in deferrals, f'missing: {key}'

    def test_regulatory_basis_named(self):
        rb = _engine().board_summary()['regulatory_basis']
        assert 'Code of Conduct' in rb
        assert '§44' in rb or 'DPA' in rb

    def test_engine_does_not_diagnose(self):
        bs_text = repr(_engine().board_summary()).lower()
        # No clinical / NLP / monitoring claims
        assert 'sentiment analysis' not in bs_text
        assert 'real-time monitoring' not in bs_text


class TestSerialization:

    def test_to_dict_round_trip(self):
        import json
        e = _engine()
        r = e.score_team(_sub(bench=70))
        d = r.to_dict()
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2['team_code'] == 't1'
        assert d2['composite_score'] == r.composite_score
        assert d2['band'] == 'strong'

    def test_suppressed_serialises(self):
        import json
        r = _engine().score_team(_sub(n=2))
        d = r.to_dict()
        s = json.dumps(d)
        d2 = json.loads(s)
        assert d2['data_suppressed'] is True
        assert d2['composite_score'] is None
        assert d2['band'] is None


# ----------------------------------------------------- no regression


class TestNoRegression:

    def test_enh_156_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-156').status == 'active'

    def test_enh_161_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-161').status == 'active'

    def test_enh_162_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-162').status == 'active'

    def test_enh_163_still_active(self):
        from utils.standards_registry import get_standard
        assert get_standard('ENH-163').status == 'active'
