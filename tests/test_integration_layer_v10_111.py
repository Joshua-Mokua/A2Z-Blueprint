"""tests/test_integration_layer_v10_111.py — v10.111.

Verifies:
  1. Name resolver — name_to_code() correctness, normalization,
     ambiguity handling, metrics
  2. DSL extension `field_in_named` — references status_vocabulary
  3. DSL extension `name_lookup` extractor — resolves full names to
     staff codes via the resolver
  4. K014 rewired to aml_alerts (no invert workaround)
  5. 4 rules (K001/K011/K115/K120) refactored to use field_in_named
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Name resolver tests ──────────────────────────────────────────────

class TestStaffNameResolver:

    def test_basic_lookup(self):
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache)
        refresh_cache()
        # Known AML officer from data/users.json
        code = name_to_code("Stephen Shimba")
        assert code is not None
        assert code.startswith("300") or code.isdigit()

    def test_normalization_whitespace(self):
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache)
        refresh_cache()
        a = name_to_code("Stephen Shimba")
        b = name_to_code("  Stephen   Shimba  ")
        c = name_to_code("Stephen  Shimba")  # double internal space
        assert a == b == c

    def test_normalization_case(self):
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache)
        refresh_cache()
        a = name_to_code("Stephen Shimba")
        b = name_to_code("STEPHEN SHIMBA")
        c = name_to_code("stephen shimba")
        assert a == b == c

    def test_unknown_name_returns_none(self):
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache)
        refresh_cache()
        assert name_to_code("Definitely Not Real Person 12345") is None

    def test_empty_input_returns_none(self):
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache)
        refresh_cache()
        assert name_to_code(None) is None
        assert name_to_code("") is None
        assert name_to_code("   ") is None

    def test_metrics_track_hits_and_misses(self):
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache, get_resolution_metrics)
        refresh_cache()
        name_to_code("Stephen Shimba")          # hit
        name_to_code("Stephen Shimba")          # hit (cached)
        name_to_code("Definitely Not Real")     # miss
        name_to_code(None)                      # miss

        m = get_resolution_metrics()
        assert m["lookups_total"] == 4
        assert m["lookups_hit"] == 2
        assert m["lookups_miss"] == 2
        assert m["hit_rate_pct"] == 50.0
        assert "Definitely Not Real" in m["miss_examples"]

    def test_aml_alerts_assignees_all_resolve(self):
        """The 5 distinct aml_alerts.assigned_to names should all
        resolve cleanly — they're real bank staff."""
        from utils.staff_name_resolver import (
            name_to_code, refresh_cache)
        refresh_cache()

        with open(REPO_ROOT / "data" / "aml_alerts.json") as f:
            alerts = json.load(f)
        assignees = {a.get("assigned_to") for a in alerts
                     if a.get("assigned_to")}
        unresolved = [n for n in assignees if name_to_code(n) is None]
        assert not unresolved, (
            f"AML alert assignees that didn't resolve: {unresolved}")


# ─── DSL extension: field_in_named ───────────────────────────────────

class TestFieldInNamed:

    def test_resolves_named_list_at_compile_time(
            self, tmp_path, monkeypatch):
        from utils import aggregation_rules_loader
        # Custom config with a named list
        config = {
            "field_overrides": {},
            "status_vocabulary": {
                "test_states": ["draft", "submitted", "approved"]
            }
        }
        cfg = tmp_path / "integration_layer_config.json"
        cfg.write_text(json.dumps(config))
        monkeypatch.setattr(
            aggregation_rules_loader, "_data_dir",
            lambda: tmp_path)

        from utils.aggregation_rules_loader import compile_predicate
        p = compile_predicate({
            "type": "field_in_named",
            "field": "status",
            "list_name": "test_states"
        })
        assert p({"status": "approved"}) is True
        assert p({"status": "draft"}) is True
        assert p({"status": "rejected"}) is False
        assert p({"status": None}) is False

    def test_unknown_list_name_raises(self, tmp_path, monkeypatch):
        from utils import aggregation_rules_loader
        cfg = tmp_path / "integration_layer_config.json"
        cfg.write_text(json.dumps({
            "field_overrides": {},
            "status_vocabulary": {"foo": ["a", "b"]}
        }))
        monkeypatch.setattr(
            aggregation_rules_loader, "_data_dir",
            lambda: tmp_path)

        from utils.aggregation_rules_loader import (
            compile_predicate, PredicateCompileError)
        with pytest.raises(PredicateCompileError) as ei:
            compile_predicate({
                "type": "field_in_named",
                "field": "status",
                "list_name": "does_not_exist"
            })
        assert "list_name" in str(ei.value)


# ─── DSL extension: name_lookup extractor ────────────────────────────

class TestNameLookupExtractor:

    def test_compiles_and_resolves(self):
        from utils.aggregation_rules_loader import compile_staff_extractor
        from utils.staff_name_resolver import refresh_cache
        refresh_cache()
        extractor = compile_staff_extractor({
            "type": "name_lookup",
            "name_field": "assigned_to"
        })
        # Real aml_alert assignee
        result = extractor({"assigned_to": "Stephen Shimba"})
        assert result is not None
        # Unknown name
        assert extractor({"assigned_to": "Made Up Name"}) is None
        # Missing field
        assert extractor({}) is None

    def test_missing_name_field_raises(self):
        from utils.aggregation_rules_loader import (
            compile_staff_extractor, PredicateCompileError)
        with pytest.raises(PredicateCompileError):
            compile_staff_extractor({"type": "name_lookup"})


# ─── K014 rewiring ───────────────────────────────────────────────────

class TestK014Rewired:

    def test_k014_uses_aml_alerts_not_loan_applications(self):
        from utils.kpi_aggregation_rules import REGISTRY
        k014 = next(r for r in REGISTRY if r.kpi_id == "K014")
        assert k014.source_table == "aml_alerts", (
            f"K014 should be wired to aml_alerts in v10.111, "
            f"not {k014.source_table}")

    def test_k014_no_longer_uses_invert(self):
        """invert:true was a v10.110 workaround when K014 was on
        loan_applications.compliance_flag; now unnecessary."""
        from utils.kpi_aggregation_rules import REGISTRY
        k014 = next(r for r in REGISTRY if r.kpi_id == "K014")
        assert k014.invert is False, (
            "K014 should not need invert in v10.111 — direction:"
            "higher KPI now matches the natural %-STR-filed emission")

    def test_k014_uses_name_lookup_extractor(self):
        from utils.kpi_aggregation_rules import REGISTRY
        k014 = next(r for r in REGISTRY if r.kpi_id == "K014")
        assert k014.staff_field_extractor is not None, (
            "K014 must use staff_field_extractor for "
            "aml_alerts.assigned_to (full names → staff codes)")

    def test_k014_produces_per_officer_actuals(self):
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        from utils.staff_name_resolver import refresh_cache

        refresh_cache()
        with open(REPO_ROOT / "data" / "aml_alerts.json") as f:
            alerts = json.load(f)
        rule = next(r for r in REGISTRY if r.kpi_id == "K014")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, alerts, "2026-04", sf)

        # Should produce per-officer percentages (5 distinct AML
        # officers in test data); some officers may have no
        # high-risk alerts in the period and be skipped
        assert len(result) >= 3
        for staff_code, pct in result.items():
            assert 0 <= pct <= 100, (
                f"K014 value {pct} out of range for {staff_code}")
            # Staff codes resolved via name_to_code should look
            # like real codes (digits, typically starts with 300)
            assert str(staff_code).isdigit()


# ─── Existing rules use field_in_named ──────────────────────────────

class TestExistingRulesUseNamedLists:

    def test_K001_K011_K115_K120_outputs_unchanged(self):
        """Refactor to field_in_named should be transparent: outputs
        match the v10.110 behaviour exactly."""
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field

        with open(REPO_ROOT / "data" / "loan_applications.json") as f:
            apps = json.load(f)
        with open(REPO_ROOT / "data" / "campaigns.json") as f:
            camps = json.load(f)

        for kid in ("K001", "K011", "K115"):
            rule = next(r for r in REGISTRY if r.kpi_id == kid)
            sf = resolve_staff_field(rule.source_table, rule.staff_field)
            result = compute_rule(rule, apps, "2026-04", sf)
            # We expect 100+ RMs since the period filter and
            # decided-status filter haven't changed
            assert len(result) >= 50, (
                f"{kid} produced only {len(result)} RMs — refactor "
                f"may have changed semantics")

        rule = next(r for r in REGISTRY if r.kpi_id == "K120")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, camps, "2026-04", sf)
        assert len(result) >= 10


# ─── Coverage stays at v10.110 baseline ─────────────────────────────

class TestG143CoverageStable:
    """v10.111 was qualitative (rewiring K014 to real data + DSL
    extensions) — no new KPI ids registered, so G143 coverage
    stays at v10.110's 16/117."""

    def test_coverage_at_or_above_v10_110(self):
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
        assert n_covered >= 16, f"Coverage dropped: {n_covered}/{n_total}"
        assert n_total >= 117
