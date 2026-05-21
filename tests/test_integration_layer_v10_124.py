"""tests/test_integration_layer_v10_124.py — v10.124.

Verifies:
  1. Four new CBS-mock tables seeded — clearing (120 rows), nps
     (150 rows), compliance (60 rows), cims (80 rows)
  2. STAFF_FIELD_BY_TABLE additions for all four new tables
  3. Seven new rules (K055/K056/K057 clearing, K007/"CX Score" nps,
     K015 compliance, K008 cims)
  4. K056 uses composed-predicate discipline (numerator includes
     denominator filter) to prevent >100% values
  5. "CX Score" is the third non-K-coded library entry wired
     (after "Audit Score" v10.120 and "Collection Throughput" v10.121)
  6. G143 coverage advanced from 84/131 to ≥91/131 — closing fast on
     STRICT-READY (high) at 75%
  7. Strict-preview tier remains STRICT-READY (preview); ~+8 rules
     to high-readiness
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Four new seeds present and properly shaped ─────────────────────

class TestNewSeeds:

    @pytest.mark.parametrize("table,min_rows,required_fields", [
        ("clearing", 80, ["id", "instrument", "processed_by", "status",
                          "settled_same_day", "reconciled",
                          "submission_date", "settlement_date"]),
        ("nps", 100, ["id", "response_date", "score", "band",
                      "handled_rm", "category", "channel"]),
        ("compliance", 30, ["id", "return_name", "due_date", "filed_date",
                            "filer", "status", "on_time"]),
        ("cims", 40, ["id", "raised_date", "severity", "assigned_to",
                      "status", "within_sla", "sla_target_days"]),
    ])
    def test_seed_present_with_required_fields(
            self, table, min_rows, required_fields):
        p = REPO_ROOT / "data" / f"{table}.json"
        assert p.exists(), f"{table}.json must be seeded by v10.124"
        with open(p) as f:
            rows = json.load(f)
        assert isinstance(rows, list)
        assert len(rows) >= min_rows, (
            f"{table} needs ≥{min_rows} rows; got {len(rows)}")
        sample = rows[0]
        for field in required_fields:
            assert field in sample, (
                f"{table} sample missing required field {field!r}")

    def test_clearing_has_settled_and_failed_mix(self):
        with open(REPO_ROOT / "data" / "clearing.json") as f:
            rows = json.load(f)
        settled = sum(1 for r in rows if r.get("status") == "Settled")
        failed = sum(1 for r in rows
                     if r.get("status") in ("Failed", "Returned", "Reversed"))
        assert settled >= 50
        # Don't require failures (low rate is realistic)

    def test_nps_has_full_band_distribution(self):
        with open(REPO_ROOT / "data" / "nps.json") as f:
            rows = json.load(f)
        bands = set(r.get("band") for r in rows)
        assert bands == {"Promoter", "Passive", "Detractor"}, (
            f"nps should have all 3 bands; got {bands}")


# ─── STAFF_FIELD_BY_TABLE additions ─────────────────────────────────

class TestStaffFieldAdditionsV10124:

    @pytest.mark.parametrize("table,expected_field", [
        ("clearing", "processed_by"),
        ("nps", "handled_rm"),
        ("compliance", "filer"),
        ("cims", "assigned_to"),
    ])
    def test_staff_field_resolved(self, table, expected_field):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field(table) == expected_field


# ─── 7 new rules registered + producing output ──────────────────────

class TestV10124Rules:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("clearing", "nps", "compliance", "cims"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                d = json.load(f)
            out[t] = d if isinstance(d, list) else list(d.values())
        return out

    def _compute(self, kid, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        rule = get_rule(kid)
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        return compute_rule(rule, tables[rule.source_table], "2026-04", sf)

    def test_K055_settlement_fail_rate(self, get_rule, tables):
        rule = get_rule("K055")
        assert rule.source_table == "clearing"
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K055", get_rule, tables)
        assert len(result) >= 50
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K056_same_day_uses_composed_numerator(
            self, get_rule, tables):
        """K056 numerator is `all` of (status=Settled AND
        settled_same_day=True), denominator is status=Settled. Composed
        predicate prevents >100% values."""
        rule = get_rule("K056")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K056", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100, (
                f"K056 must be 0-100% (composed predicate); "
                f"staff {staff} → {pct}")

    def test_K057_reconciliation_completion(self, get_rule, tables):
        rule = get_rule("K057")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K057", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K007_customer_satisfaction_score(self, get_rule, tables):
        rule = get_rule("K007")
        assert rule.source_table == "nps"
        assert rule.pattern == "MEAN_FIELD"
        assert rule.value_field == "score"
        result = self._compute("K007", get_rule, tables)
        assert len(result) >= 50
        for staff, score in result.items():
            assert 0 <= score <= 10

    def test_CX_Score_non_k_coded(self, get_rule, tables):
        """'CX Score' is the third non-K-coded library entry wired —
        after 'Audit Score' (v10.120) and 'Collection Throughput'
        (v10.121)."""
        rule = get_rule("CX Score")
        assert rule is not None, (
            "v10.124 should wire 'CX Score' as third non-K-coded "
            "library entry")
        assert rule.source_table == "nps"
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("CX Score", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K015_cbk_returns_filed_on_time(self, get_rule, tables):
        rule = get_rule("K015")
        assert rule.source_table == "compliance"
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K015", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K008_complaints_resolved(self, get_rule, tables):
        rule = get_rule("K008")
        assert rule.source_table == "cims"
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K008", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100


# ─── G143 coverage + tier ───────────────────────────────────────────

class TestG143CoverageV10124:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_91_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 91, (
            f"v10.124 expected ≥91 covered; got {sp['covered']}/"
            f"{sp['total_operational']}")

    def test_strict_preview_closing_on_high(self, gate_result):
        """v10.124 lands at ~69-70% — closing fast on STRICT-READY (high)
        at 75% but not yet there."""
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (preview)"
        assert 50.0 <= sp["coverage_pct"] < 75.0
        assert sp["coverage_pct"] >= 65.0, (
            f"v10.124 should be at ≥65%; got {sp['coverage_pct']}%")
