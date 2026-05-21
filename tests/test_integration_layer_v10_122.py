"""tests/test_integration_layer_v10_122.py — v10.122.

Verifies:
  1. Two new CBS-mock tables seeded — sla_tickets (100 rows) + branch_log
     (87 rows) — both with proper staff-code fields
  2. STAFF_FIELD_BY_TABLE additions for both newly-seeded tables
  3. Four new rules (K039 SLA Tickets, K040 Open Ticket Age,
     K013 Branch Daily Log Completion, K053 Daily Log Submission Rate)
  4. K039/K053 use composed predicate discipline (numerator includes
     denominator filter)
  5. K040 uses MEAN_FIELD pattern (third production rule using the
     v10.118 alias name for non-TAT semantics)
  6. G143 coverage advanced from 74/131 to ≥78/131
  7. Strict-preview tier remains STRICT-READY (preview); approaching
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


# ─── Two new seeds present and properly shaped ──────────────────────

class TestNewSeeds:

    def test_sla_tickets_seeded(self):
        p = REPO_ROOT / "data" / "sla_tickets.json"
        assert p.exists(), "sla_tickets.json must be seeded by v10.122"
        with open(p) as f:
            tickets = json.load(f)
        assert isinstance(tickets, list)
        assert len(tickets) >= 50, (
            f"sla_tickets needs meaningful volume; got {len(tickets)}")
        sample = tickets[0]
        # Required fields for K039/K040
        for f in ("id", "assignee", "status", "sla_target_hours",
                  "actual_hours", "actual_days", "within_sla",
                  "raised_date", "priority"):
            assert f in sample, (
                f"sla_tickets missing required field {f!r}")

    def test_branch_log_seeded(self):
        p = REPO_ROOT / "data" / "branch_log.json"
        assert p.exists(), "branch_log.json must be seeded by v10.122"
        with open(p) as f:
            logs = json.load(f)
        assert isinstance(logs, list)
        assert len(logs) >= 30
        sample = logs[0]
        for f in ("id", "branch", "submitted_by", "log_date",
                  "submission_date", "status", "on_time"):
            assert f in sample, f"branch_log missing field {f!r}"

    def test_sla_tickets_have_resolved_status_for_K039(self):
        """K039 needs Resolved/Closed tickets in the denominator."""
        with open(REPO_ROOT / "data" / "sla_tickets.json") as f:
            tickets = json.load(f)
        resolved = [t for t in tickets
                    if t.get("status") in ("Resolved", "Closed")]
        assert len(resolved) >= 20, (
            f"K039 denominator needs ≥20 resolved/closed tickets; "
            f"got {len(resolved)}")

    def test_branch_log_has_mix_of_on_time_and_late(self):
        """K053 needs mix of on_time=True and on_time=False to produce
        meaningful percentages (not all 0% or all 100%)."""
        with open(REPO_ROOT / "data" / "branch_log.json") as f:
            logs = json.load(f)
        on_time = sum(1 for l in logs if l.get("on_time") is True)
        late = sum(1 for l in logs if l.get("on_time") is False)
        assert on_time >= 5 and late >= 3, (
            f"branch_log needs both on-time and late entries for K053; "
            f"on_time={on_time}, late={late}")


# ─── STAFF_FIELD_BY_TABLE additions ─────────────────────────────────

class TestStaffFieldAdditionsV10122:

    def test_sla_tickets(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("sla_tickets") == "assignee"

    def test_branch_log(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("branch_log") == "submitted_by"


# ─── 4 new rules registered + producing output ──────────────────────

class TestV10122Rules:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("sla_tickets", "branch_log"):
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

    def test_K039_sla_tickets_uses_composed_numerator(
            self, get_rule, tables):
        """K039 numerator is `all` of (status in [Resolved, Closed]
        AND within_sla=True), denominator is status in [Resolved, Closed].
        Composed numerator prevents >100% values."""
        rule = get_rule("K039")
        assert rule is not None
        assert rule.source_table == "sla_tickets"
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K039", get_rule, tables)
        assert len(result) >= 20, (
            f"K039 should cover ≥20 assignees; got {len(result)}")
        for staff, pct in result.items():
            assert 0 <= pct <= 100, (
                f"K039 must be 0-100% (composed predicate); "
                f"staff {staff} → {pct}")

    def test_K040_uses_MEAN_FIELD_pattern(self, get_rule, tables):
        """K040 is the third production rule using the v10.118 MEAN_FIELD
        pattern name (after K073 in v10.118 and 'Audit Score' in v10.120).
        Computes mean ticket resolution days per assignee."""
        rule = get_rule("K040")
        assert rule is not None
        assert rule.pattern == "MEAN_FIELD"
        assert rule.value_field == "actual_days"
        result = self._compute("K040", get_rule, tables)
        for staff, mean_days in result.items():
            assert mean_days >= 0, (
                f"K040 mean ticket age should be ≥ 0; got {mean_days}")

    def test_K013_branch_log_count(self, get_rule, tables):
        rule = get_rule("K013")
        assert rule.pattern == "COUNT"
        result = self._compute("K013", get_rule, tables)
        assert len(result) >= 5
        for staff, n in result.items():
            assert n >= 1

    def test_K053_branch_log_submission_rate(self, get_rule, tables):
        rule = get_rule("K053")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K053", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100


# ─── G143 coverage + tier ───────────────────────────────────────────

class TestG143CoverageV10122:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_78_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 78, (
            f"v10.122 expected ≥78 covered; got {sp['covered']}/"
            f"{sp['total_operational']}")

    def test_strict_preview_still_preview_approaching_high(self, gate_result):
        """v10.122 lands at ~59% — closing on STRICT-READY (high) but
        still needs ≥75% for tier promotion."""
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (preview)"
        assert 50.0 <= sp["coverage_pct"] < 75.0
