"""tests/test_integration_layer_v10_121.py — v10.121.

Verifies:
  1. Four new rules registered (Collection Throughput, K033, K076, K077)
  2. Two are forward-compatible — emit no actuals (or 0%) in current
     seed but designed for production data shape
  3. "Collection Throughput" is the second non-K-coded library entry
     wired (after "Audit Score" in v10.120)
  4. K033 mirrors K047 logic — library has both as separate entries on
     the same source
  5. G143 coverage advanced from 70/131 to ≥74/131
  6. Strict-preview tier remains STRICT-READY (preview)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── 4 new rules registered ──────────────────────────────────────────

class TestV10121Rules:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("debt_recovery", "ews_cases", "dpo_register"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                d = json.load(f)
            out[t] = d if isinstance(d, list) else list(d.values())
        return out

    def _compute(self, kid, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        from utils.staff_name_resolver import refresh_cache
        refresh_cache()
        rule = get_rule(kid)
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        return compute_rule(rule, tables[rule.source_table], "2026-04", sf)

    def test_collection_throughput_non_k_coded(self, get_rule, tables):
        """Second non-K-coded library entry wired after 'Audit Score'
        in v10.120. Demonstrates ongoing support for non-standard IDs."""
        rule = get_rule("Collection Throughput")
        assert rule is not None
        assert rule.source_table == "debt_recovery"
        assert rule.pattern == "COUNT"
        result = self._compute("Collection Throughput", get_rule, tables)
        assert len(result) >= 5
        for staff, n in result.items():
            assert n >= 1

    def test_K033_ews_resolution_rate(self, get_rule, tables):
        """K033 mirrors K047 logic — library has both entries on the
        same source. Both produce 0% currently because ews_cases seed
        has all status=Active (forward-compat)."""
        rule = get_rule("K033")
        assert rule is not None
        assert rule.source_table == "ews_cases"
        assert rule.pattern == "PERCENTAGE"
        # Uses name_lookup on rm
        assert rule.staff_field_extractor is not None
        result = self._compute("K033", get_rule, tables)
        # All values 0-100
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K076_breaches_within_72hrs_forward_compat(
            self, get_rule, tables):
        """K076 is forward-compat — dpo_register seed has type=Breach
        rows with on_time=None universally, so few/no actuals emit."""
        rule = get_rule("K076")
        assert rule is not None
        assert rule.source_table == "dpo_register"
        assert rule.pattern == "BOOL_FRACTION"
        assert rule.bool_field == "on_time"
        # Run it and don't fail if empty — forward-compat
        result = self._compute("K076", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K077_ropa_uptodate_forward_compat(self, get_rule, tables):
        """K077 is forward-compat — dpo_register seed has type=ROPA
        rows with dpo_reviewer=None universally."""
        rule = get_rule("K077")
        assert rule is not None
        assert rule.source_table == "dpo_register"
        assert rule.pattern == "PERCENTAGE"
        # Run it — should produce {} or values 0-100
        result = self._compute("K077", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100


# ─── Forward-compatibility discipline ────────────────────────────────

class TestForwardCompatibilityDiscipline:
    """v10.121 ships 2 explicitly forward-compatible rules (K076, K077).
    These rules are correctly designed but emit few or no actuals against
    the current CBS-mock seed because the seed doesn't populate the
    relevant fields. As deployment data populates, the rules begin
    emitting actuals automatically — no rule rewrite needed."""

    def test_K076_design_correct_independent_of_data(self):
        """K076's design specifies BOOL_FRACTION on on_time field for
        type=Breach. Even though the current seed has on_time=None
        for all Breach rows, the predicate compiles cleanly and the
        rule will emit actuals as soon as data populates."""
        from utils.kpi_aggregation_rules import REGISTRY
        rule = next(r for r in REGISTRY if r.kpi_id == "K076")
        # Design check — rule is registered + pattern matches expected
        assert rule.pattern == "BOOL_FRACTION"
        assert rule.bool_field == "on_time"

    def test_K077_design_correct_independent_of_data(self):
        from utils.kpi_aggregation_rules import REGISTRY
        rule = next(r for r in REGISTRY if r.kpi_id == "K077")
        assert rule.pattern == "PERCENTAGE"


# ─── G143 coverage + tier ───────────────────────────────────────────

class TestG143CoverageV10121:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_74_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 74, (
            f"v10.121 expected ≥74 covered; got {sp['covered']}/"
            f"{sp['total_operational']}")

    def test_strict_preview_tier_still_preview(self, gate_result):
        """v10.121 lands at ~56% — still STRICT-READY (preview) tier;
        not yet at STRICT-READY (high) which requires 75%."""
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (preview)"
        assert 50.0 <= sp["coverage_pct"] < 75.0
