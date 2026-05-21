"""tests/test_integration_layer_v10_119.py — v10.119.

Verifies:
  1. New DSL predicates field_le_value + field_ge_value (12th and 13th
     predicate types) — compare numeric field to literal value
  2. Eight new rules registered (K046, K045, K042, K038, K037, K074,
     K050, K092)
  3. Rules exercise diverse patterns (MEAN_FIELD, PERCENTAGE with
     field_le_field, RATIO, BOOL_FRACTION via name_lookup, SUM)
  4. K037/K038 use the new field_ge_value/field_le_value predicates
  5. G143 coverage advanced from 58/131 to ≥66/131
  6. **G143 strict-preview tier crossed from BELOW STRICT THRESHOLD to
     STRICT-READY (preview)** — 50% milestone
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── New DSL predicates: field_le_value + field_ge_value ─────────────

class TestFieldVsValuePredicates:
    """v10.119 adds field_le_value and field_ge_value predicates that
    compare a numeric field to a literal value. Closes the gap where
    field_le_field couldn't handle constant comparisons (e.g.,
    pct_budget_used <= 100, pct_complete >= 100)."""

    def test_field_le_value_basic(self):
        from utils.aggregation_rules_loader import compile_predicate
        pred = compile_predicate({
            "type": "field_le_value", "field": "x", "value": 100})
        assert pred({"x": 50}) is True
        assert pred({"x": 100}) is True
        assert pred({"x": 101}) is False
        assert pred({"x": 0}) is True

    def test_field_le_value_handles_missing_or_non_numeric(self):
        """Consistent with field_le_field semantics — missing or
        non-numeric values exclude the row."""
        from utils.aggregation_rules_loader import compile_predicate
        pred = compile_predicate({
            "type": "field_le_value", "field": "x", "value": 100})
        assert pred({}) is False
        assert pred({"x": None}) is False
        assert pred({"x": "string"}) is False
        assert pred({"x": True}) is True  # bool is numeric in Python

    def test_field_ge_value_basic(self):
        from utils.aggregation_rules_loader import compile_predicate
        pred = compile_predicate({
            "type": "field_ge_value", "field": "x", "value": 100})
        assert pred({"x": 50}) is False
        assert pred({"x": 100}) is True
        assert pred({"x": 200}) is True

    def test_value_must_be_numeric(self):
        """Loader rejects non-numeric values at compile time, not at
        compute time. Surfaces config errors early."""
        from utils.aggregation_rules_loader import compile_predicate
        with pytest.raises(ValueError, match="value.*must be numeric"):
            compile_predicate({
                "type": "field_le_value",
                "field": "x",
                "value": "not_a_number"})
        with pytest.raises(ValueError, match="value.*must be numeric"):
            compile_predicate({
                "type": "field_ge_value",
                "field": "x",
                "value": None})


# ─── 8 new rules registered ──────────────────────────────────────────

class TestV10119RulesRegistered:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    def test_K046_credit_analysis_completeness_mean_field(self, get_rule):
        rule = get_rule("K046")
        assert rule is not None
        assert rule.source_table == "loan_applications"
        assert rule.pattern == "MEAN_FIELD"
        assert rule.value_field == "completeness_score"
        # Uses nested extractor on analyst.code
        assert rule.staff_field_extractor is not None

    def test_K045_loan_tat_compliance_percentage(self, get_rule):
        rule = get_rule("K045")
        assert rule is not None
        assert rule.source_table == "loan_applications"
        assert rule.pattern == "PERCENTAGE"

    def test_K042_deal_win_rate_percentage(self, get_rule):
        rule = get_rule("K042")
        assert rule is not None
        assert rule.source_table == "pipeline"
        assert rule.pattern == "PERCENTAGE"

    def test_K038_project_budget_adherence(self, get_rule):
        rule = get_rule("K038")
        assert rule is not None
        assert rule.source_table == "projects"
        assert rule.pattern == "PERCENTAGE"
        assert rule.staff_field_extractor is not None

    def test_K037_milestones_completed(self, get_rule):
        rule = get_rule("K037")
        assert rule is not None
        assert rule.source_table == "projects"
        assert rule.pattern == "COUNT"
        assert rule.staff_field_extractor is not None

    def test_K074_regulatory_findings_closed_ratio(self, get_rule):
        rule = get_rule("K074")
        assert rule is not None
        assert rule.source_table == "cbk_returns"
        assert rule.pattern == "RATIO"
        assert rule.numerator_field == "findings_closed"
        assert rule.denominator_field == "regulatory_findings"

    def test_K050_strs_filed_bool_fraction(self, get_rule):
        rule = get_rule("K050")
        assert rule is not None
        assert rule.source_table == "aml_alerts"
        assert rule.pattern == "BOOL_FRACTION"
        assert rule.bool_field == "str_filed"
        assert rule.staff_field_extractor is not None

    def test_K092_merchant_acquiring_revenue_sum(self, get_rule):
        rule = get_rule("K092")
        assert rule is not None
        assert rule.source_table == "merchant_acquiring"
        assert rule.pattern == "SUM"
        assert rule.value_field == "ytd_revenue_kes"


# ─── 8 rules produce sane outputs ────────────────────────────────────

class TestV10119RulesProduceOutput:

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("loan_applications", "pipeline", "projects",
                  "cbk_returns", "aml_alerts", "merchant_acquiring"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                d = json.load(f)
            out[t] = d if isinstance(d, list) else list(d.values())
        return out

    def _compute(self, kid, tables):
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        from utils.staff_name_resolver import refresh_cache
        refresh_cache()
        rule = next(r for r in REGISTRY if r.kpi_id == kid)
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        return compute_rule(rule, tables[rule.source_table], "2026-04", sf)

    def test_K046_completeness_score_in_range(self, tables):
        result = self._compute("K046", tables)
        for staff, mean in result.items():
            assert 50 <= mean <= 100, (
                f"completeness_score is 50-100; "
                f"mean should be too: {staff} → {mean}")

    def test_K045_loan_tat_compliance_in_range(self, tables):
        result = self._compute("K045", tables)
        assert len(result) >= 5
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K042_deal_win_rate_in_range(self, tables):
        result = self._compute("K042", tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K038_budget_adherence_in_range_no_overflow(self, tables):
        """K038 numerator was originally not constrained by the
        denominator's status filter, leading to >100% values when a PM
        had Cancelled projects within budget. Fixed in v10.119 by
        composing the numerator with `all` of (le_value AND not_in)."""
        result = self._compute("K038", tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100, (
                f"K038 should be 0-100% (composed numerator+status); "
                f"staff {staff} → {pct}")

    def test_K037_completed_count(self, tables):
        result = self._compute("K037", tables)
        for staff, n in result.items():
            assert n >= 1

    def test_K074_findings_ratio_in_range(self, tables):
        result = self._compute("K074", tables)
        for staff, ratio in result.items():
            # Ratio can theoretically exceed 1.0 if data has more
            # closed than identified findings in a period — but
            # should generally be 0-1
            assert 0 <= ratio

    def test_K050_strs_filed_in_range(self, tables):
        result = self._compute("K050", tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K092_merchant_revenue_positive(self, tables):
        result = self._compute("K092", tables)
        for staff, total in result.items():
            assert total > 0


# ─── G143 coverage + strict-preview crossing ─────────────────────────

class TestG143CoverageCrossesStrictPreview:
    """v10.119 should:
       (a) advance G143 from 58/131 to ≥66/131
       (b) **cross the 50% strict-preview threshold** — the strict
           preview tier should change from `BELOW STRICT THRESHOLD`
           to `STRICT-READY (preview)`.
    """

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_66_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 66, (
            f"v10.119 expected ≥66 covered; got {sp['covered']}/"
            f"{sp['total_operational']}")

    def test_strict_preview_tier_is_now_STRICT_READY_preview(self, gate_result):
        """The headline v10.119 milestone — crossing from
        BELOW STRICT THRESHOLD to STRICT-READY (preview)."""
        sp = gate_result["strict_preview"]
        pct = sp["coverage_pct"]
        assert pct >= 50.0, (
            f"v10.119 should cross 50% threshold; got {pct}%")
        assert sp["tag"] == "STRICT-READY (preview)", (
            f"v10.119 should be at STRICT-READY (preview) tier; "
            f"got {sp['tag']!r}")

    def test_pct_below_75_so_not_yet_high_tier(self, gate_result):
        """Sanity check: we crossed 50% but haven't yet hit 75%."""
        sp = gate_result["strict_preview"]
        assert sp["coverage_pct"] < 75.0, (
            f"v10.119 not expected to cross 75% yet; got {sp['coverage_pct']}%")
        assert sp["tag"] != "STRICT-READY (high)"
