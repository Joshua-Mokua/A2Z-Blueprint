"""tests/test_integration_layer_v10_118.py — v10.118.

Verifies:
  1. MEAN_FIELD pattern alias — same engine as TAT_FIELD; both names
     resolve to identical dispatch (validation + computation)
  2. Seven new rules registered (K105, K098, K049, K086, K085, K073, K091)
  3. K073 uses the new MEAN_FIELD pattern name in production
  4. K049 uses name_lookup extractor on aml_alerts (no new
     STAFF_FIELD_BY_TABLE entry needed — extractor handles the
     full-name field)
  5. G143 coverage advanced from 51/131 to ≥58/131
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── MEAN_FIELD pattern alias ────────────────────────────────────────

class TestMeanFieldAlias:
    """v10.118 introduces MEAN_FIELD as a name alias for TAT_FIELD.
    Both resolve to identical engine dispatch — validation, dispatch,
    and computation. The alias clarifies that the pattern works for
    any per-staff numeric average, not just TAT semantics."""

    def test_mean_field_in_all_patterns(self):
        from utils.kpi_aggregation_rules import (
            ALL_PATTERNS, PATTERN_MEAN_FIELD, PATTERN_TAT_FIELD)
        assert PATTERN_MEAN_FIELD == "MEAN_FIELD"
        assert PATTERN_MEAN_FIELD in ALL_PATTERNS
        assert PATTERN_TAT_FIELD in ALL_PATTERNS

    def test_is_mean_pattern_recognises_both(self):
        from utils.kpi_aggregation_rules import _is_mean_pattern
        assert _is_mean_pattern("TAT_FIELD")
        assert _is_mean_pattern("MEAN_FIELD")
        assert not _is_mean_pattern("SUM")
        assert not _is_mean_pattern("COUNT")
        assert not _is_mean_pattern("PERCENTAGE")

    def test_validation_identical(self):
        """Both names enforce same validation rules."""
        from utils.kpi_aggregation_rules import AggregationRule

        # Valid — both pass
        for pat in ("TAT_FIELD", "MEAN_FIELD"):
            ok = AggregationRule(
                kpi_id="K", source_table="t", pattern=pat,
                value_field="v", predicate=lambda r: True)
            assert ok.validate() == [], (
                f"{pat} should validate clean; got {ok.validate()}")

        # Missing value_field — both fail
        for pat in ("TAT_FIELD", "MEAN_FIELD"):
            bad = AggregationRule(
                kpi_id="K", source_table="t", pattern=pat,
                predicate=lambda r: True)
            errs = bad.validate()
            assert any("value_field" in e for e in errs)
            assert any(pat in e for e in errs), (
                f"{pat} validation error should mention {pat!r}: {errs}")

    def test_compute_identical(self):
        """Both names produce same per-staff aggregations."""
        from utils.kpi_aggregation_rules import (
            AggregationRule, compute_rule)

        rows = [
            {"sc": "A", "v": 10},
            {"sc": "A", "v": 14},
            {"sc": "B", "v": 5},
            {"sc": "B", "v": 7},
            {"sc": "B", "v": "string"},   # non-numeric, dropped
            {"sc": "B", "v": None},        # non-numeric, dropped
        ]
        r_tat = AggregationRule(
            kpi_id="K", source_table="t", pattern="TAT_FIELD",
            value_field="v", predicate=lambda r: True)
        r_mean = AggregationRule(
            kpi_id="K", source_table="t", pattern="MEAN_FIELD",
            value_field="v", predicate=lambda r: True)
        out_tat = compute_rule(r_tat, rows, "", "sc")
        out_mean = compute_rule(r_mean, rows, "", "sc")
        assert out_tat == out_mean
        assert out_tat == {"A": 12.0, "B": 6.0}


# ─── 7 new rules registered ──────────────────────────────────────────

class TestV10118RulesRegistered:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    def test_K105_board_action_items_ratio(self, get_rule):
        rule = get_rule("K105")
        assert rule is not None
        assert rule.source_table == "board_papers"
        assert rule.pattern == "RATIO"
        assert rule.numerator_field == "actions_closed"
        assert rule.denominator_field == "action_items"

    def test_K098_oprisk_net_losses_sum(self, get_rule):
        rule = get_rule("K098")
        assert rule is not None
        assert rule.source_table == "op_risk_losses"
        assert rule.pattern == "SUM"
        assert rule.value_field == "net_loss_kes"

    def test_K049_aml_uses_name_lookup_extractor(self, get_rule):
        """K049 uses name_lookup extractor on aml_alerts.assigned_to —
        no new STAFF_FIELD_BY_TABLE entry needed since the extractor
        handles the full-name field."""
        rule = get_rule("K049")
        assert rule is not None
        assert rule.source_table == "aml_alerts"
        assert rule.pattern == "PERCENTAGE"
        assert rule.staff_field_extractor is not None

    def test_K086_first_login_bool_fraction(self, get_rule):
        rule = get_rule("K086")
        assert rule is not None
        assert rule.source_table == "customer_onboarding"
        assert rule.pattern == "BOOL_FRACTION"
        assert rule.bool_field == "first_login_within_7d"

    def test_K085_onboarding_completion_percentage(self, get_rule):
        rule = get_rule("K085")
        assert rule is not None
        assert rule.source_table == "customer_onboarding"
        assert rule.pattern == "PERCENTAGE"

    def test_K073_uses_MEAN_FIELD_pattern_name(self, get_rule):
        """K073 is the first rule to use the new MEAN_FIELD pattern
        name in production. Demonstrates the alias works end-to-end."""
        rule = get_rule("K073")
        assert rule is not None
        assert rule.source_table == "cbk_returns"
        assert rule.pattern == "MEAN_FIELD", (
            f"K073 should use the v10.118 MEAN_FIELD pattern name; "
            f"got {rule.pattern!r}")
        assert rule.value_field == "accuracy_score"

    def test_K091_active_pos_merchants_count(self, get_rule):
        rule = get_rule("K091")
        assert rule is not None
        assert rule.source_table == "merchant_acquiring"
        assert rule.pattern == "COUNT"


# ─── 7 rules produce real outputs ────────────────────────────────────

class TestV10118RulesProduceOutput:

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("board_papers", "op_risk_losses", "aml_alerts",
                  "customer_onboarding", "cbk_returns",
                  "merchant_acquiring"):
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

    def test_K105_action_items_ratio_in_range(self, tables):
        result = self._compute("K105", tables)
        for staff, ratio in result.items():
            assert 0 <= ratio <= 1.5, (
                f"K105 ratio outside expected range: "
                f"{staff} → {ratio}")

    def test_K098_net_losses_positive(self, tables):
        result = self._compute("K098", tables)
        assert len(result) >= 30
        for staff, loss in result.items():
            assert loss != 0, (
                f"Net losses should be non-zero per reporter; "
                f"got {loss} for {staff}")

    def test_K049_aml_closed_in_range(self, tables):
        result = self._compute("K049", tables)
        # aml_alerts has many distinct assignees; name resolver
        # reduces them to staff_codes — at least a few should resolve
        for staff, pct in result.items():
            assert 0 <= pct <= 100
            assert str(staff).isdigit()  # name_lookup → staff_code

    def test_K086_first_login_in_range(self, tables):
        result = self._compute("K086", tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K085_completion_in_range(self, tables):
        result = self._compute("K085", tables)
        assert len(result) >= 20
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K073_accuracy_uses_mean_field_engine(self, tables):
        """K073 uses MEAN_FIELD pattern; should produce mean of
        accuracy_score per reviewer where submitted=True."""
        result = self._compute("K073", tables)
        assert len(result) >= 20
        for staff, score in result.items():
            assert 0 <= score <= 100, (
                f"accuracy_score is 0-100; mean should also be: "
                f"{staff} → {score}")

    def test_K091_active_merchants_count(self, tables):
        result = self._compute("K091", tables)
        for staff, n in result.items():
            assert n >= 1


# ─── G143 coverage advanced ──────────────────────────────────────────

class TestG143CoverageAdvanced:
    """v10.118 should advance G143 from 51/131 to ≥58/131."""

    def test_coverage_58_or_higher(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            result = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        assert result["passed"] is True
        import re
        m = re.search(r"registered (\d+)\s*/\s*(\d+)", result["summary"])
        n = int(m.group(1))
        t = int(m.group(2))
        assert n >= 58, f"v10.118 expected ≥58 covered; got {n}/{t}"
        assert t >= 131
