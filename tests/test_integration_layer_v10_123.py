"""tests/test_integration_layer_v10_123.py — v10.123.

Verifies:
  1. Three new CBS-mock tables seeded — hr (200 rows, manager-aggregated),
     agency_banking (80 rows, supervisor-aggregated), bsc_scores
     (123 rows, staff-aggregated)
  2. STAFF_FIELD_BY_TABLE additions for all three new tables
  3. Six new rules wired (K018, K030, K035, K016, K025, K017)
  4. K016 demonstrates per-rule staff_field override (staff_code instead
     of the hr-table default of manager_code)
  5. K030 corrected from RATIO (numeric-field summing) to PERCENTAGE
     (predicate-based) for boolean budget-flag aggregation
  6. K017 uses last_updated period filter (production may use period_end
     with previous-quarter resolver)
  7. G143 coverage advanced from 78/131 to ≥84/131
  8. Strict-preview tier remains STRICT-READY (preview); approaching
     STRICT-READY (high) at 75%
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Three new seeds present and properly shaped ────────────────────

class TestNewSeeds:

    def test_hr_seeded(self):
        p = REPO_ROOT / "data" / "hr.json"
        assert p.exists(), "hr.json must be seeded by v10.123"
        with open(p) as f:
            records = json.load(f)
        assert isinstance(records, list)
        assert len(records) >= 100, (
            f"hr seed needs meaningful volume; got {len(records)}")
        sample = records[0]
        for f in ("id", "staff_code", "manager_code", "department",
                  "retained_12m", "enps_score", "training_hours_ytd",
                  "budgeted_for_role", "active", "last_updated"):
            assert f in sample, f"hr missing required field {f!r}"

    def test_agency_banking_seeded(self):
        p = REPO_ROOT / "data" / "agency_banking.json"
        assert p.exists()
        with open(p) as f:
            agents = json.load(f)
        assert isinstance(agents, list)
        assert len(agents) >= 30
        sample = agents[0]
        for f in ("id", "agent_name", "supervisor_code", "uptime_pct",
                  "transactions_30d", "active", "last_audit_date"):
            assert f in sample, f"agency_banking missing field {f!r}"

    def test_bsc_scores_seeded(self):
        p = REPO_ROOT / "data" / "bsc_scores.json"
        assert p.exists()
        with open(p) as f:
            scores = json.load(f)
        assert isinstance(scores, list)
        assert len(scores) >= 50
        sample = scores[0]
        for f in ("id", "staff_code", "quarter", "period_end",
                  "total_score", "rating", "last_updated"):
            assert f in sample, f"bsc_scores missing field {f!r}"

    def test_hr_has_meaningful_retention_mix(self):
        """K018 needs both retained=True and retained=False for
        meaningful percentages (not all 100%)."""
        with open(REPO_ROOT / "data" / "hr.json") as f:
            records = json.load(f)
        retained = sum(1 for r in records if r.get("retained_12m") is True)
        not_retained = sum(1 for r in records
                           if r.get("retained_12m") is False)
        assert retained >= 50 and not_retained >= 10, (
            f"hr seed needs both retained and not-retained; "
            f"got retained={retained}, not={not_retained}")


# ─── STAFF_FIELD_BY_TABLE additions ─────────────────────────────────

class TestStaffFieldAdditionsV10123:

    def test_hr(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("hr") == "manager_code"

    def test_agency_banking(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("agency_banking") == "supervisor_code"

    def test_bsc_scores(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("bsc_scores") == "staff_code"


# ─── 6 new rules registered + producing output ──────────────────────

class TestV10123Rules:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("hr", "agency_banking", "bsc_scores"):
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

    def test_K018_staff_retention(self, get_rule, tables):
        rule = get_rule("K018")
        assert rule.source_table == "hr"
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K018", get_rule, tables)
        assert len(result) >= 50
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K030_headcount_percentage(self, get_rule, tables):
        """K030 was corrected from RATIO (which produced 0 staff because
        numeric-summing of bool/string fields fails) to PERCENTAGE
        (predicate-based aggregation of budgeted_for_role=True)."""
        rule = get_rule("K030")
        assert rule.pattern == "PERCENTAGE", (
            f"K030 should be PERCENTAGE for boolean budget aggregation; "
            f"got {rule.pattern}")
        result = self._compute("K030", get_rule, tables)
        assert len(result) >= 50
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K035_enps_mean_field(self, get_rule, tables):
        rule = get_rule("K035")
        assert rule.pattern == "MEAN_FIELD"
        assert rule.value_field == "enps_score"
        result = self._compute("K035", get_rule, tables)
        for staff, score in result.items():
            assert 0 <= score <= 10  # ENPS 0-10 scale

    def test_K016_uses_per_rule_staff_field_override(
            self, get_rule, tables):
        """K016 demonstrates per-rule staff_field override — aggregates
        per staff_code (not the hr-table default of manager_code) because
        staff own their own training hours, not their manager."""
        rule = get_rule("K016")
        assert rule.staff_field == "staff_code", (
            f"K016 should override hr's default manager_code with "
            f"staff_code; got {rule.staff_field!r}")
        assert rule.pattern == "SUM"
        result = self._compute("K016", get_rule, tables)
        # Each staff should have non-negative training hours
        for staff, hours in result.items():
            assert hours >= 0

    def test_K025_agent_network_uptime(self, get_rule, tables):
        rule = get_rule("K025")
        assert rule.source_table == "agency_banking"
        assert rule.pattern == "MEAN_FIELD"
        assert rule.value_field == "uptime_pct"
        result = self._compute("K025", get_rule, tables)
        assert len(result) >= 5
        for staff, uptime in result.items():
            assert 0 <= uptime <= 100

    def test_K017_bsc_score_previous_quarter(self, get_rule, tables):
        rule = get_rule("K017")
        assert rule.source_table == "bsc_scores"
        assert rule.pattern == "MEAN_FIELD"
        # Verify period_field correction (last_updated, not period_end)
        assert rule.period_field == "last_updated", (
            f"K017 should use last_updated for current-period selection; "
            f"got {rule.period_field!r}")
        result = self._compute("K017", get_rule, tables)
        # BSC scores are 1-5 scale typically
        for staff, score in result.items():
            assert 0 <= score <= 5


# ─── G143 coverage + tier ───────────────────────────────────────────

class TestG143CoverageV10123:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_84_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 84, (
            f"v10.123 expected ≥84 covered; got {sp['covered']}/"
            f"{sp['total_operational']}")

    def test_strict_preview_still_preview_approaching_high(
            self, gate_result):
        """v10.123 lands at ~64% — still STRICT-READY (preview); needs
        ≥75% (≥99/131) for STRICT-READY (high)."""
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (preview)"
        assert 50.0 <= sp["coverage_pct"] < 75.0
