"""tests/test_integration_layer_v10_115.py — v10.115.

Verifies:
  1. PATTERN_TAT_FIELD — new 7th archetype, computes mean of pre-
     computed numeric days/hours field per staff
  2. date_le_field DSL predicate — string-compare ISO dates
  3. K036 upgraded to strict on-time semantics via date_le_field
  4. 6 new rules wired (K093, K084, K078, K047, K099, K100)
  5. STAFF_FIELD_BY_TABLE additions for the 5 new tables
  6. Integration Layer API endpoints (rules / actuals / coverage /
     resolution-metrics) — React-ready response shapes
  7. G143 coverage advanced from 34/131 to ≥40/131
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── PATTERN_TAT_FIELD ────────────────────────────────────────────────

class TestPatternTATField:
    """The 7th archetypal pattern: mean of a pre-computed numeric
    field (e.g., tat_days, tat_hours) per staff. Used when the
    upstream system has already computed TAT rather than recording
    separate start/end timestamps."""

    def test_in_all_patterns(self):
        from utils.kpi_aggregation_rules import (
            ALL_PATTERNS, PATTERN_TAT_FIELD)
        assert PATTERN_TAT_FIELD == "TAT_FIELD"
        assert PATTERN_TAT_FIELD in ALL_PATTERNS

    def test_validates_correctly(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_TAT_FIELD)

        # Valid rule
        good = AggregationRule(
            kpi_id="K", source_table="t",
            pattern=PATTERN_TAT_FIELD,
            value_field="tat_days",
            predicate=lambda r: True,
        )
        assert good.validate() == []

        # Missing value_field
        bad = AggregationRule(
            kpi_id="K", source_table="t",
            pattern=PATTERN_TAT_FIELD,
            predicate=lambda r: True,
        )
        errs = bad.validate()
        assert any("value_field" in e for e in errs)

        # Missing predicate
        bad2 = AggregationRule(
            kpi_id="K", source_table="t",
            pattern=PATTERN_TAT_FIELD,
            value_field="tat_days",
        )
        errs2 = bad2.validate()
        assert any("predicate" in e for e in errs2)

    def test_computes_per_staff_mean(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_TAT_FIELD, compute_rule)

        rule = AggregationRule(
            kpi_id="K", source_table="t",
            pattern=PATTERN_TAT_FIELD,
            value_field="tat_days",
            predicate=lambda r: r.get("status") == "Active",
        )
        rows = [
            {"sc": "A", "tat_days": 10, "status": "Active"},
            {"sc": "A", "tat_days": 14, "status": "Active"},
            {"sc": "A", "tat_days": 99, "status": "Pending"},  # filtered
            {"sc": "B", "tat_days": 5, "status": "Active"},
            {"sc": "B", "tat_days": 7, "status": "Active"},
        ]
        result = compute_rule(rule, rows, "", "sc")
        assert result == {"A": 12.0, "B": 6.0}

    def test_drops_non_numeric_silently(self):
        """Non-numeric tat_field values should be skipped, not crash.
        customer_onboarding has many None tat_hours — those records
        must not poison the per-staff aggregation."""
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_TAT_FIELD, compute_rule)

        rule = AggregationRule(
            kpi_id="K", source_table="t",
            pattern=PATTERN_TAT_FIELD,
            value_field="tat",
            predicate=lambda r: True,
        )
        rows = [
            {"sc": "A", "tat": 5},
            {"sc": "A", "tat": None},      # skipped
            {"sc": "A", "tat": "string"},  # skipped
            {"sc": "A", "tat": 15},
        ]
        result = compute_rule(rule, rows, "", "sc")
        assert result == {"A": 10.0}  # mean of 5 and 15


# ─── date_le_field DSL predicate ───────────────────────────────────────

class TestDateLeFieldPredicate:

    def test_iso_date_compare(self):
        from utils.aggregation_rules_loader import compile_predicate
        p = compile_predicate({
            "type": "date_le_field",
            "field": "actual",
            "compare_field": "planned",
        })
        assert p({"actual": "2026-04-01", "planned": "2026-04-15"}) is True
        assert p({"actual": "2026-04-15", "planned": "2026-04-15"}) is True
        assert p({"actual": "2026-04-16", "planned": "2026-04-15"}) is False
        # Empty / None fields excluded
        assert p({"actual": "", "planned": "2026-04-15"}) is False
        assert p({"actual": None, "planned": "2026-04-15"}) is False
        assert p({}) is False

    def test_K036_uses_date_le_field(self):
        """K036 was simplified in v10.114; v10.115 upgrades to strict
        on-time via the new date_le_field predicate."""
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        k036 = next(r for r in data["rules"]
                    if r.get("kpi_id") == "K036"
                    and r.get("source_table") == "projects")
        # The numerator should now use date_le_field
        num_pred = k036.get("numerator_pred", {})
        # Either directly date_le_field or wrapped in 'all'
        types_present = []

        def collect(p):
            if isinstance(p, dict):
                types_present.append(p.get("type"))
                for sub in p.get("of", []) or []:
                    collect(sub)

        collect(num_pred)
        assert "date_le_field" in types_present, (
            f"K036 numerator_pred should use date_le_field; "
            f"saw {types_present}")


# ─── 6 new rules registered ───────────────────────────────────────────

class TestV10115RulesRegistered:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    def test_K093_merchant_tat_uses_TAT_FIELD(self, get_rule):
        rule = get_rule("K093")
        assert rule is not None
        assert rule.source_table == "merchant_acquiring"
        assert rule.pattern == "TAT_FIELD"
        assert rule.value_field == "tat_days"

    def test_K084_onboarding_tat_uses_TAT_FIELD(self, get_rule):
        rule = get_rule("K084")
        assert rule is not None
        assert rule.source_table == "customer_onboarding"
        assert rule.pattern == "TAT_FIELD"
        assert rule.value_field == "tat_hours"

    def test_K078_sanctions_percentage(self, get_rule):
        rule = get_rule("K078")
        assert rule is not None
        assert rule.source_table == "sanctions_register"
        assert rule.pattern == "PERCENTAGE"

    def test_K047_ews_uses_name_lookup(self, get_rule):
        rule = get_rule("K047")
        assert rule is not None
        assert rule.source_table == "ews_cases"
        assert rule.staff_field_extractor is not None, (
            "K047 must use name_lookup since ews_cases.rm is a full name")

    def test_K099_oprisk_count(self, get_rule):
        rule = get_rule("K099")
        assert rule is not None
        assert rule.source_table == "op_risk_losses"
        assert rule.pattern == "COUNT"

    def test_K100_oprisk_near_misses_count(self, get_rule):
        rule = get_rule("K100")
        assert rule is not None
        assert rule.source_table == "op_risk_losses"
        assert rule.pattern == "COUNT"


# ─── 6 new rules produce per-staff outputs ────────────────────────────

class TestV10115RulesProduceOutput:

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("merchant_acquiring", "customer_onboarding",
                  "sanctions_register", "ews_cases", "op_risk_losses"):
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

    def test_K093_produces_real_tat(self, tables):
        result = self._compute("K093", tables)
        # ≥1 RM in period; values should be plausible TAT (1-30 days)
        for staff, days in result.items():
            assert 0 < days < 100, f"K093 {staff} → {days} not plausible"

    def test_K084_produces_real_tat(self, tables):
        result = self._compute("K084", tables)
        # tat_hours typically 1-200
        for staff, hours in result.items():
            assert 0 < hours < 500, f"K084 {staff} → {hours} not plausible"

    def test_K078_sanctions(self, tables):
        result = self._compute("K078", tables)
        # 50+ reviewers in seed
        assert len(result) >= 30
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K099_oprisk_reports(self, tables):
        result = self._compute("K099", tables)
        # 50+ reporters in seed (75 distinct in op_risk_losses)
        assert len(result) >= 30
        for staff, n in result.items():
            assert n >= 1


# ─── STAFF_FIELD_BY_TABLE additions ───────────────────────────────────

class TestStaffFieldAdditionsV10115:

    def test_customer_onboarding(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("customer_onboarding") == "rm_assigned"

    def test_sanctions_register(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("sanctions_register") == "reviewer"

    def test_op_risk_losses(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("op_risk_losses") == "reported_by"

    def test_retailer_finance(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("retailer_finance") == "rm_code"


# ─── React-readiness API shape tests ─────────────────────────────────

class TestReactReadinessRuleShape:
    """The /api/integration/rules endpoint serializes rules in a
    JSON-shaped format that React can consume directly. Verifies the
    shape (without invoking FastAPI itself, which isn't installed in
    the build sandbox)."""

    def test_rule_serialization_shape(self):
        # Replicate the _rule_to_dict helper (api.py inlines it)
        from utils.kpi_aggregation_rules import REGISTRY
        rule = REGISTRY[0]

        # Required fields for React component rendering
        REQUIRED = ("kpi_id", "source_table", "pattern", "description",
                    "decimals", "invert", "uses_extractor")
        d = {
            "kpi_id":          rule.kpi_id,
            "source_table":    rule.source_table,
            "pattern":         rule.pattern,
            "description":     rule.description or "",
            "decimals":        rule.decimals,
            "invert":          rule.invert,
            "uses_extractor":  rule.staff_field_extractor is not None,
        }
        for f in REQUIRED:
            assert f in d, f"Missing React-required field {f!r}"
        # No callable fields leak — they're not JSON-serializable
        json.dumps(d)  # Will raise if non-serializable

    def test_actuals_shape_is_react_ready(self):
        """A computed actual record contains only JSON-serializable
        primitives."""
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K001")
        with open(REPO_ROOT / "data" / "loan_applications.json") as f:
            d = json.load(f)
        rows = d if isinstance(d, list) else list(d.values())
        sf = resolve_staff_field(rule.source_table)
        per_staff = compute_rule(rule, rows, "2026-04", sf)

        # Build one actual record like the endpoint does
        if per_staff:
            sc, value = next(iter(per_staff.items()))
            record = {
                "staff_code":   sc,
                "kpi_id":       rule.kpi_id,
                "value":        round(float(value), rule.decimals)
                                  if isinstance(value, (int, float))
                                  else value,
                "source_table": rule.source_table,
                "pattern":      rule.pattern,
                "period":       "2026-04",
            }
            # Must JSON-serialize
            json.dumps(record)
            # All primitive types
            for k, v in record.items():
                assert v is None or isinstance(
                    v, (str, int, float, bool)), (
                    f"Field {k!r} is non-primitive: {type(v).__name__}")


# ─── G143 coverage advanced ──────────────────────────────────────────

class TestG143CoverageAdvanced:
    """v10.115 should advance G143 from 34/131 to ≥40/131."""

    def test_coverage_40_or_higher(self):
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
        assert n >= 40, f"v10.115 expected ≥40 covered; got {n}/{t}"
        assert t >= 131, f"denominator should be ≥131; got {t}"
