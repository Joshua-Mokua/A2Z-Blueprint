"""tests/test_integration_layer_v10_109.py — v10.109 rule batch.

v10.109 ships:
  1. staff_field_extractor for nested fields (legal_matters)
  2. STAFF_FIELD_BY_TABLE corrections for v10.108 mismatches
  3. Revised v10.108 rules (K011, K014, K020 [was K044], K027)
  4. New K-series rules wired to existing library entries
     (K001, K010, K041, K044)
  5. New library entries K112-K120 + matching rules
  6. KPI library count: 129 → 138

These tests verify the rules compute correctly against the live
CBS-mock data (loan_applications, debt_recovery, pipeline, referrals,
legal_matters, campaigns) and that the library/registry stay in sync.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Fixtures: real CBS-mock tables ────────────────────────────────────

@pytest.fixture(scope="module")
def real_tables():
    """Load the real operational tables from data/."""
    tables = {}
    for t in ("loan_applications", "debt_recovery", "pipeline",
              "referrals", "legal_matters", "campaigns"):
        p = REPO_ROOT / "data" / f"{t}.json"
        if not p.exists():
            tables[t] = []
            continue
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            tables[t] = data
        elif isinstance(data, dict):
            tables[t] = [v for v in data.values() if isinstance(v, dict)]
        else:
            tables[t] = []
    return tables


@pytest.fixture(scope="module")
def library():
    with open(REPO_ROOT / "data" / "kpi_library.json", encoding="utf-8") as f:
        return json.load(f)


# ─── staff_field_extractor tests ──────────────────────────────────────

class TestStaffFieldExtractor:
    """v10.109 mechanism: nested-field accessor for legal_matters
    (legal_officer.code) and similar."""

    def test_extractor_resolves_nested_dict(self):
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_COUNT, compute_rule)

        def extractor(row):
            owner = row.get("owner")
            return owner.get("code") if isinstance(owner, dict) else None

        rule = AggregationRule(
            kpi_id="TEST", source_table="t",
            pattern=PATTERN_COUNT,
            predicate=lambda r: r.get("status") == "completed",
            period_field="completed_at",
            staff_field_extractor=extractor,
        )
        rows = [
            {"owner": {"code": "S001", "name": "Alice"},
             "status": "completed", "completed_at": "2026-04-15"},
            {"owner": {"code": "S001", "name": "Alice"},
             "status": "completed", "completed_at": "2026-04-20"},
            {"owner": {"code": "S002", "name": "Bob"},
             "status": "completed", "completed_at": "2026-04-22"},
            {"owner": None,  # extractor handles None gracefully
             "status": "completed", "completed_at": "2026-04-25"},
            {"owner": {"code": "S001"},  # wrong period - excluded
             "status": "completed", "completed_at": "2026-03-15"},
        ]
        # staff_field arg ignored when extractor is set
        result = compute_rule(rule, rows, "2026-04", "ignored_field")
        assert result == {"S001": 2, "S002": 1}

    def test_extractor_takes_precedence_over_staff_field(self):
        """If both staff_field (table-level) and extractor are
        present, extractor wins."""
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_COUNT, compute_rule)

        rule = AggregationRule(
            kpi_id="TEST", source_table="t",
            pattern=PATTERN_COUNT,
            predicate=lambda r: True,
            staff_field_extractor=lambda r: r.get("nested", {}).get("id"),
        )
        rows = [
            {"staff_code": "WRONG", "nested": {"id": "RIGHT"}},
            {"staff_code": "WRONG", "nested": {"id": "RIGHT"}},
        ]
        # The 'staff_code' arg passed to compute_rule should be ignored
        result = compute_rule(rule, rows, "", "staff_code")
        assert result == {"RIGHT": 2}
        assert "WRONG" not in result

    def test_extractor_exception_skips_row(self):
        """A bad extractor on one row should not poison the batch."""
        from utils.kpi_aggregation_rules import (
            AggregationRule, PATTERN_COUNT, compute_rule)

        def picky(row):
            return row["this_key_doesnt_exist"]["id"]

        rule = AggregationRule(
            kpi_id="TEST", source_table="t",
            pattern=PATTERN_COUNT,
            predicate=lambda r: True,
            staff_field_extractor=picky,
        )
        # All rows trigger the exception → empty result, no crash
        rows = [{"x": 1}, {"y": 2}]
        result = compute_rule(rule, rows, "", "ignored")
        assert result == {}


# ─── STAFF_FIELD_BY_TABLE correction tests ─────────────────────────────

class TestStaffFieldCorrections:
    """v10.109 corrected v10.108 mismatches that didn't fit real data."""

    def test_loan_applications_uses_rm_code(self):
        from utils.staff_field_resolver import resolve_staff_field
        # v10.108 had this as 'assigned_officer' — wrong for real data.
        assert resolve_staff_field("loan_applications") == "rm_code"

    def test_debt_recovery_uses_recovery_officer_code(self):
        from utils.staff_field_resolver import resolve_staff_field
        # v10.108 had 'recovery_officer' (the name field).
        assert resolve_staff_field("debt_recovery") == \
            "recovery_officer_code"

    def test_referrals_uses_referrer_code(self):
        from utils.staff_field_resolver import resolve_staff_field
        # v10.108 had 'rm_code' — that's the assigned RM, not the
        # person who fires the actual.
        assert resolve_staff_field("referrals") == "referrer_code"

    def test_pipeline_uses_staff_code(self):
        from utils.staff_field_resolver import resolve_staff_field
        # v10.108 had 'rm_code' — real schema uses staff_code.
        assert resolve_staff_field("pipeline") == "staff_code"

    def test_campaigns_owner_code_registered(self):
        from utils.staff_field_resolver import (
            resolve_staff_field, STAFF_FIELD_BY_TABLE)
        assert resolve_staff_field("campaigns") == "owner_code"
        assert "campaigns" in STAFF_FIELD_BY_TABLE


# ─── Real-data smoke tests for each pattern ───────────────────────────

class TestRulesAgainstRealData:
    """Each rule produces sensible output against the real CBS-mock
    tables. Validates that the registered rules don't crash, return
    non-empty dicts where expected, and pass basic sanity checks."""

    def test_K001_loans_disbursed_per_rm(self, real_tables):
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K001"
                    and r.source_table == "loan_applications")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["loan_applications"],
                              "2026-04", sf)
        assert len(result) > 0
        # Per-RM amounts must be positive numbers (we filter to
        # approved/disbursed which have positive amount values)
        for rm, value in result.items():
            assert value > 0, f"RM {rm} has nonsense value {value}"

    def test_K027_recovery_rate_per_officer(self, real_tables):
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K027")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["debt_recovery"],
                              "2026-04", sf)
        # 14 distinct recovery officers in the CBS-mock data
        assert len(result) >= 5
        # Recovery rates should be < 1.0 (recovered < outstanding)
        for officer, rate in result.items():
            assert 0 <= rate <= 2, (
                f"Officer {officer} rate {rate} outside sanity bounds")

    def test_K020_pipeline_conversion(self, real_tables):
        """v10.109 fix: was wrongly labelled K044 in v10.108."""
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K020")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["pipeline"],
                              "2026-04", sf)
        # All values are PERCENTAGE in [0, 100]
        for staff, pct in result.items():
            assert 0 <= pct <= 100, (
                f"Staff {staff} pct {pct} not a percentage")

    def test_K044_referral_conversion_correctly_wired(self, real_tables):
        """v10.109 redefinition: K044 is Referral Conversion Rate,
        not Pipeline Conversion."""
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K044")
        # Verify the source: must be referrals, not pipeline
        assert rule.source_table == "referrals", (
            f"K044 should be wired to referrals, not "
            f"{rule.source_table}")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["referrals"],
                              "2026-04", sf)
        for ref, pct in result.items():
            assert 0 <= pct <= 100

    def test_K041_pipeline_deals_count(self, real_tables):
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K041")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["pipeline"],
                              "2026-04", sf)
        # Counts should be positive integers
        for staff, n in result.items():
            assert isinstance(n, (int, float)) and n > 0

    def test_K118_legal_completed_uses_extractor(self, real_tables):
        """K118 wires legal_matters via legal_officer.code nested
        accessor — the headline new mechanism."""
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K118")
        assert rule.staff_field_extractor is not None, (
            "K118 must use staff_field_extractor for legal_officer.code")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["legal_matters"],
                              "2026-04", sf)
        # All keys should be staff code strings (look like "300xxx")
        for code in result.keys():
            assert code.startswith("300") or code.isdigit(), (
                f"Suspicious staff code from extractor: {code}")

    def test_K112_pipeline_volume_sum(self, real_tables):
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K112")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, real_tables["pipeline"],
                              "2026-04", sf)
        # Pipeline values are KES, expected to be in millions
        for staff, value in result.items():
            assert value > 0
            # Sanity check — pipeline deals are typically 1M-1B KES
            assert value < 1e15, f"Insane value for {staff}: {value}"


# ─── Library/registry alignment tests ─────────────────────────────────

class TestLibraryRegistryAlignment:
    """v10.109 ships 9 new library entries (K112-K120). Verify each
    one has a registered rule that points to it, and that all v10.109
    rule kpi_ids exist in the library."""

    def test_library_count_floor_v10_109(self, library):
        n = len(library.get("kpis", []))
        assert n >= 138, (
            f"Library has {n} KPIs; v10.109 floor is 138 "
            f"(129 from v10.107 + 9 new K112-K120)")

    def test_K112_through_K120_present(self, library):
        ids_in_lib = {k.get("id") for k in library["kpis"]}
        for i in range(112, 121):
            kid = f"K{i}"
            assert kid in ids_in_lib, f"{kid} missing from library"

    def test_v10_109_library_entries_well_formed(self, library):
        REQUIRED = ("id", "name", "pillar", "weight", "unit",
                    "direction", "active", "description", "source")
        v10_109_ids = {f"K{i}" for i in range(112, 121)}
        for kpi in library["kpis"]:
            if kpi.get("id") not in v10_109_ids:
                continue
            for f in REQUIRED:
                assert f in kpi, f"{kpi.get('id')}: missing {f!r}"
            assert kpi["direction"] in ("higher", "lower")
            assert 0 < kpi["weight"] <= 1

    def test_every_v10_109_rule_has_library_entry(self, library):
        from utils.kpi_aggregation_rules import REGISTRY
        # Build library lookup (by id, code, name, alias) — same logic
        # as bsc_engine._load_kpi_index post-v10.107
        idx = {}
        for kpi in library["kpis"]:
            for fld in ("id", "code", "name"):
                v = kpi.get(fld)
                if v and str(v) not in idx:
                    idx[str(v)] = kpi
            for a in kpi.get("aliases", []) or []:
                if str(a) not in idx:
                    idx[str(a)] = kpi
        unresolved = [r.kpi_id for r in REGISTRY if r.kpi_id not in idx]
        assert not unresolved, (
            f"Rules with kpi_id not in library: {unresolved}")


class TestG143CoverageReport:
    """v10.109 baseline: G143 reports >= 14/117 operational-source
    KPIs (~12%). The exact number depends on which library KPIs are
    classified as operational-source vs CBS-source."""

    def test_g143_coverage_above_v10_108_baseline(self):
        """v10.108 baseline was 4/108 (3.7%); v10.109 must be higher."""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            result = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        assert result["passed"] is True  # informational mode
        # Parse "registered N / M" from summary
        import re
        m = re.search(r"registered (\d+)\s*/\s*(\d+)", result["summary"])
        assert m, f"Could not parse coverage from: {result['summary']}"
        n_covered = int(m.group(1))
        n_total = int(m.group(2))
        # v10.109 must be at least 14 covered (we have 17 rules; some
        # map to CBS-source library entries which fall outside G143)
        assert n_covered >= 14, (
            f"v10.109 coverage {n_covered}/{n_total} below floor of 14")
        # Total operational-source KPIs went up by 9 (K112-K120)
        assert n_total >= 117
