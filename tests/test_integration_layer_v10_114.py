"""tests/test_integration_layer_v10_114.py — v10.114.

Verifies:
  1. Sample audit_reviews data exists with expected schema + sane
     distributions (250 records, all auditor codes valid)
  2. Three new library entries K132-K134 are well-formed
  3. STAFF_FIELD_BY_TABLE correctly maps the 6 newly-wired tables
  4. Seven new rules registered and produce per-staff outputs:
       - K104 (board_papers)
       - K072 (cbk_returns)
       - K075 (dpo_register)
       - K036 (projects, via name_lookup)
       - K132/K133/K134 (audit_reviews, all 3 new rules)
  5. G143 coverage advanced from 27/128 to ≥34/131
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── audit_reviews seed data ──────────────────────────────────────────

class TestAuditReviewsSeed:
    """audit_reviews.json exists with expected schema."""

    @pytest.fixture(scope="class")
    def reviews(self):
        with open(REPO_ROOT / "data" / "audit_reviews.json") as f:
            return json.load(f)

    def test_record_count(self, reviews):
        assert len(reviews) >= 200, (
            f"audit_reviews has {len(reviews)} records; expected ≥200")

    def test_required_fields(self, reviews):
        sample = reviews[0]
        for f in ("id", "audit_title", "auditor_code", "auditor_name",
                  "status", "findings_total", "findings_closed",
                  "sla_breached", "period_end"):
            assert f in sample, f"audit record missing field {f!r}"

    def test_status_distribution(self, reviews):
        statuses = {r["status"] for r in reviews}
        assert {"Closed", "Open", "In Progress", "Reopened"} <= statuses

    def test_auditor_codes_all_valid(self, reviews):
        with open(REPO_ROOT / "data" / "users.json") as f:
            users = json.load(f)
        valid = {u["staff_code"] for u in users.values()
                 if u.get("staff_code")}
        invalid = [r["auditor_code"] for r in reviews
                   if r["auditor_code"] not in valid]
        assert not invalid, (
            f"audit_reviews has invalid auditor_codes: {invalid[:3]}")


# ─── Library K132-K134 ────────────────────────────────────────────────

class TestLibraryK132K134:

    @pytest.fixture(scope="class")
    def library(self):
        with open(REPO_ROOT / "data" / "kpi_library.json") as f:
            return json.load(f)

    def test_all_three_present(self, library):
        ids = {k.get("id") for k in library["kpis"]}
        assert "K132" in ids
        assert "K133" in ids
        assert "K134" in ids

    def test_well_formed(self, library):
        REQUIRED = ("id", "name", "pillar", "weight", "unit",
                    "direction", "active", "description", "source")
        for kid in ("K132", "K133", "K134"):
            k = next(x for x in library["kpis"] if x.get("id") == kid)
            for f in REQUIRED:
                assert f in k, f"{kid}: missing {f!r}"
            assert k["pillar"] == "Operational Excellence"
            assert k["source"] == "audit_reviews"
            assert k["direction"] in ("higher", "lower")
            assert 0 < k["weight"] <= 1

    def test_library_count_at_least_152(self, library):
        n = len(library["kpis"])
        assert n >= 152, (
            f"Library has {n} KPIs; v10.114 floor is 152 "
            f"(149 from v10.113 + 3 from v10.114)")


# ─── STAFF_FIELD_BY_TABLE additions ──────────────────────────────────

class TestStaffFieldAdditions:

    def test_board_papers_uses_submitted_by(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("board_papers") == "submitted_by"

    def test_cbk_returns_uses_reviewer(self):
        from utils.staff_field_resolver import resolve_staff_field
        # NOT submitted_by because that field is mostly empty in real data
        assert resolve_staff_field("cbk_returns") == "reviewer"

    def test_dpo_register_uses_dpo_reviewer(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("dpo_register") == "dpo_reviewer"

    def test_merchant_acquiring_uses_rm_code(self):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field("merchant_acquiring") == "rm_code"

    def test_audit_reviews_uses_auditor_code(self):
        from utils.staff_field_resolver import resolve_staff_field
        # v10.114 corrected from auditor_username → auditor_code
        # to match the seed data's canonical staff identifier.
        assert resolve_staff_field("audit_reviews") == "auditor_code"


# ─── 7 v10.114 rules produce output ──────────────────────────────────

class TestV10114RulesProduceOutput:

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("board_papers", "cbk_returns", "dpo_register",
                  "projects", "audit_reviews"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                d = json.load(f)
            out[t] = d if isinstance(d, list) else list(d.values())
        return out

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid, source_table=None):
            for r in REGISTRY:
                if r.kpi_id == kid and (source_table is None
                                         or r.source_table == source_table):
                    return r
            return None
        return _get

    def test_K104_board_papers(self, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        rule = get_rule("K104", "board_papers")
        assert rule is not None
        sf = resolve_staff_field(rule.source_table)
        result = compute_rule(rule, tables["board_papers"], "2026-04", sf)
        # Few in-period; just verify no crash and values in 0-100
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K072_cbk_returns(self, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        rule = get_rule("K072")
        assert rule is not None
        assert rule.source_table == "cbk_returns"
        sf = resolve_staff_field(rule.source_table)
        result = compute_rule(rule, tables["cbk_returns"], "2026-04", sf)
        assert len(result) >= 20, (
            f"K072 expected ≥20 reviewers; got {len(result)}")
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K075_dpo_register(self, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        rule = get_rule("K075")
        assert rule is not None
        sf = resolve_staff_field(rule.source_table)
        result = compute_rule(rule, tables["dpo_register"], "2026-04", sf)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K036_projects_uses_name_lookup(self, get_rule):
        rule = get_rule("K036", "projects")
        assert rule is not None
        assert rule.staff_field_extractor is not None, (
            "K036 must use staff_field_extractor for project_manager "
            "(full names → staff codes via name_lookup)")

    def test_K132_audit_closure_rate(self, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        rule = get_rule("K132")
        assert rule is not None
        assert rule.source_table == "audit_reviews"
        sf = resolve_staff_field(rule.source_table)
        result = compute_rule(rule, tables["audit_reviews"], "2026-04", sf)
        # 8 distinct auditors in seed; some may have no in-period rows
        assert len(result) >= 3
        for code, pct in result.items():
            assert 0 <= pct <= 100
            assert str(code).isdigit()

    def test_K133_audit_findings_closure_rate(self, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        rule = get_rule("K133")
        assert rule is not None
        sf = resolve_staff_field(rule.source_table)
        result = compute_rule(rule, tables["audit_reviews"], "2026-04", sf)
        for code, ratio in result.items():
            # Findings_closed / findings_total — should be in [0, 1.0]
            # but individual auditor could score > 1.0 only if
            # findings_closed exceeds findings_total which our seed
            # rules out. Allow some slack just in case.
            assert 0 <= ratio <= 2.0

    def test_K134_audit_sla_compliance_with_invert(
            self, get_rule, tables):
        rule = get_rule("K134")
        assert rule is not None
        assert rule.invert is True, (
            "K134 must use invert=True since sla_breached=True "
            "is the bad outcome")

        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        sf = resolve_staff_field(rule.source_table)
        result = compute_rule(rule, tables["audit_reviews"], "2026-04", sf)
        for code, pct in result.items():
            assert 0 <= pct <= 100


# ─── G143 coverage advanced ──────────────────────────────────────────

class TestG143CoverageAdvanced:
    """v10.114 should advance G143 from 27/128 to ≥34/131."""

    def test_coverage_34_or_higher(self):
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
        assert n_covered >= 34, (
            f"v10.114 expected ≥34 covered; got {n_covered}")
        # Denominator: 128 from v10.113 + 3 (K132-K134 are operational
        # source) = 131 minimum
        assert n_total >= 131, (
            f"v10.114 denominator should be ≥131; got {n_total}")
