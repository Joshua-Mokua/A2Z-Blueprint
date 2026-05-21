"""tests/test_integration_layer_v10_112.py — v10.112.

Verifies:
  1. Sample HR data exists with expected schemas + sane distributions
  2. 8 new library entries K121-K128 are well-formed
  3. 8 HR rules registered and produce per-staff outputs against the
     seed data
  4. G143 coverage advanced from 16/117 to ≥24/125
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── HR seed data integrity ────────────────────────────────────────────

class TestHRSeedData:
    """The three HR tables exist with required fields populated."""

    @pytest.fixture(scope="class")
    def training(self):
        with open(REPO_ROOT / "data" / "training_completions.json") as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def reviews(self):
        with open(REPO_ROOT / "data" / "performance_reviews.json") as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def leaves(self):
        with open(REPO_ROOT / "data" / "leave_requests.json") as f:
            return json.load(f)

    def test_training_completions_well_formed(self, training):
        assert len(training) >= 5000, (
            f"training_completions has {len(training)} records; expected ≥5000")
        sample = training[0]
        for f in ("id", "staff_code", "training_id", "mandatory",
                  "completed", "status", "hours"):
            assert f in sample, f"training record missing field {f!r}"
        # Status distribution should include all 3 states
        statuses = {t["status"] for t in training}
        assert {"Completed", "InProgress", "NotStarted"} <= statuses

    def test_performance_reviews_well_formed(self, reviews):
        assert len(reviews) >= 1438, (
            f"performance_reviews has {len(reviews)} records; "
            f"expected ≥1438 (one per active staff)")
        sample = reviews[0]
        for f in ("id", "reviewee_code", "reviewer_code", "period",
                  "due_date", "status", "submitted_on_time"):
            assert f in sample, f"review record missing field {f!r}"
        statuses = {r["status"] for r in reviews}
        assert {"approved", "submitted", "draft"} <= statuses

    def test_leave_requests_well_formed(self, leaves):
        assert len(leaves) >= 500, (
            f"leave_requests has {len(leaves)} records; expected ≥500")
        sample = leaves[0]
        for f in ("id", "staff_code", "leave_type", "start_date",
                  "end_date", "days", "status"):
            assert f in sample, f"leave record missing field {f!r}"
        statuses = {l["status"] for l in leaves}
        assert {"approved", "pending", "rejected"} <= statuses

    def test_seed_data_references_real_staff_codes(
            self, training, reviews, leaves):
        """All staff codes in HR data must exist in the staff
        register (otherwise rules will produce orphan actuals)."""
        with open(REPO_ROOT / "data" / "users.json") as f:
            users = json.load(f)
        valid_codes = {u["staff_code"] for u in users.values()
                       if u.get("staff_code")}

        for record_set, key, label in (
                (training, "staff_code", "training_completions"),
                (reviews, "reviewee_code", "performance_reviews"),
                (leaves, "staff_code", "leave_requests")):
            invalid = [r[key] for r in record_set
                       if r.get(key) and r[key] not in valid_codes]
            assert not invalid, (
                f"{label} has {len(invalid)} records with staff_codes "
                f"not in users.json: {invalid[:3]}")


# ─── Library entries K121-K128 ─────────────────────────────────────────

class TestLibraryK121K128:

    @pytest.fixture(scope="class")
    def library(self):
        with open(REPO_ROOT / "data" / "kpi_library.json") as f:
            return json.load(f)

    def test_all_eight_entries_present(self, library):
        ids = {k.get("id") for k in library["kpis"]}
        for i in range(121, 129):
            assert f"K{i}" in ids, f"K{i} missing from library"

    def test_entries_well_formed(self, library):
        REQUIRED = ("id", "name", "pillar", "weight", "unit",
                    "direction", "active", "description", "source")
        v112 = {f"K{i}" for i in range(121, 129)}
        for k in library["kpis"]:
            if k.get("id") not in v112:
                continue
            for f in REQUIRED:
                assert f in k, f"{k.get('id')}: missing {f!r}"
            assert k["direction"] in ("higher", "lower")
            assert 0 < k["weight"] <= 1
            assert k["source"] in (
                "training_completions", "performance_reviews",
                "leave_requests")

    def test_library_count_at_or_above_146(self, library):
        n = len(library["kpis"])
        assert n >= 146, (
            f"Library has {n} KPIs; v10.112 floor is 146 "
            f"(138 from v10.109 + 8 from v10.112)")


# ─── 8 HR rules registered + produce output ───────────────────────────

class TestHRRulesProduceOutput:
    """Each HR rule produces a non-empty per-staff dict against the
    seed data."""

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("training_completions", "performance_reviews",
                  "leave_requests"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                out[t] = json.load(f)
        return out

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def compute(self, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        def _compute(rule, period="2026-04"):
            rows = tables[rule.source_table]
            sf = resolve_staff_field(rule.source_table, rule.staff_field)
            return compute_rule(rule, rows, period, sf)
        return _compute

    def test_K121_mandatory_training_rate(self, get_rule, compute):
        rule = get_rule("K121")
        assert rule is not None
        assert rule.source_table == "training_completions"
        result = compute(rule)
        assert len(result) > 100, f"K121 only {len(result)} staff"
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K122_training_count(self, get_rule, compute):
        rule = get_rule("K122")
        assert rule is not None
        result = compute(rule)
        assert len(result) > 100
        for staff, n in result.items():
            assert n >= 1
            assert isinstance(n, (int, float))

    def test_K123_review_on_time_rate(self, get_rule, compute):
        rule = get_rule("K123")
        result = compute(rule)
        assert len(result) > 500
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K124_reviews_approved(self, get_rule, compute):
        rule = get_rule("K124")
        result = compute(rule)
        assert len(result) > 500
        for staff, n in result.items():
            assert n >= 1

    def test_K125_leave_days(self, get_rule, compute):
        rule = get_rule("K125")
        result = compute(rule)
        assert len(result) > 50
        for staff, days in result.items():
            assert days > 0

    def test_K126_leave_count(self, get_rule, compute):
        rule = get_rule("K126")
        result = compute(rule)
        assert len(result) > 50
        for staff, n in result.items():
            assert n >= 1

    def test_K127_training_hours(self, get_rule, compute):
        rule = get_rule("K127")
        result = compute(rule)
        assert len(result) > 100
        for staff, h in result.items():
            assert h > 0

    def test_K128_review_submission_rate(self, get_rule, compute):
        rule = get_rule("K128")
        result = compute(rule)
        assert len(result) > 500
        for staff, pct in result.items():
            assert 0 <= pct <= 100


# ─── G143 coverage advanced ───────────────────────────────────────────

class TestG143CoverageAdvanced:
    """v10.112 should advance G143 from 16/117 to at least 24/125."""

    def test_coverage_24_or_higher(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            result = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        assert result["passed"] is True
        import re
        m = re.search(r"registered (\d+)\s*/\s*(\d+)", result["summary"])
        n_covered = int(m.group(1))
        n_total = int(m.group(2))
        assert n_covered >= 24, (
            f"v10.112 should hit ≥24/total; got {n_covered}/{n_total}")
        assert n_total >= 125, (
            f"v10.112 should add 8 to operational denominator; "
            f"got {n_total}")
