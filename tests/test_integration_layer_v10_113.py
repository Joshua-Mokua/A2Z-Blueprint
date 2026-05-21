"""tests/test_integration_layer_v10_113.py — v10.113.

Verifies:
  1. Role resolver — 3-layer resolution (pinned → alias → direct)
  2. role_lookup DSL extractor compiles + works
  3. K129/K130 wired to incidents via name_lookup
  4. K131 wired to agent_fraud_alerts via role_lookup
  5. v10.112 pillar mislabel fixed (People & Capability → People & Learning)
  6. Admin Module Config has 6 tabs (Resolution Metrics + Agent Alerts Config added)
  7. G143 coverage advanced 24/125 → 27/128 (21.1%)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Role resolver ───────────────────────────────────────────────────

class TestStaffRoleResolver:

    def test_alias_layer_resolves(self):
        """Eco Bank: agent_fraud_alerts says 'Agency Banking Manager'
        but users.json has 'Manager Agency Banking'. Alias bridges."""
        from utils.staff_role_resolver import (
            role_to_code, refresh_cache)
        refresh_cache()
        code = role_to_code("Agency Banking Manager")
        assert code is not None
        # Verify it resolved to someone whose role IS 'Manager Agency Banking'
        with open(REPO_ROOT / "data" / "users.json") as f:
            users = json.load(f)
        match = next((u for u in users.values()
                      if u.get("staff_code") == code), None)
        assert match is not None
        assert match.get("role") == "Manager Agency Banking"

    def test_unknown_role_returns_none(self):
        from utils.staff_role_resolver import (
            role_to_code, refresh_cache)
        refresh_cache()
        assert role_to_code("Definitely Not A Real Role") is None

    def test_empty_input_returns_none(self):
        from utils.staff_role_resolver import (
            role_to_code, refresh_cache)
        refresh_cache()
        assert role_to_code(None) is None
        assert role_to_code("") is None
        assert role_to_code("   ") is None

    def test_pinned_layer_wins_over_alias(self, tmp_path, monkeypatch):
        """Admin pin trumps alias normalization."""
        from utils import staff_role_resolver
        # Build minimal config with both pin AND alias for same role
        config = {
            "field_overrides": {},
            "agent_alerts_config": {
                "role_aliases": {"Test Role": "Some Real Role"},
                "role_to_staff_code": {"Test Role": "999999"}
            }
        }
        cfg_path = tmp_path / "integration_layer_config.json"
        cfg_path.write_text(json.dumps(config))
        # Tiny users.json so register lookups can run
        users_path = tmp_path / "users.json"
        users_path.write_text(json.dumps({
            "x": {"staff_code": "111111", "role": "Some Real Role",
                  "active": True, "full_name": "Test User"}
        }))
        monkeypatch.setattr(staff_role_resolver, "_data_dir",
                            lambda: tmp_path)
        staff_role_resolver.refresh_cache()
        # Pin wins → 999999, NOT 111111 (which is what the alias
        # would resolve to)
        assert staff_role_resolver.role_to_code("Test Role") == "999999"

    def test_normalization_whitespace_and_case(self):
        from utils.staff_role_resolver import (
            role_to_code, refresh_cache)
        refresh_cache()
        a = role_to_code("Agency Banking Manager")
        b = role_to_code("  agency  banking   manager ")
        c = role_to_code("AGENCY BANKING MANAGER")
        assert a == b == c

    def test_metrics_track_via_layer(self):
        from utils.staff_role_resolver import (
            role_to_code, refresh_cache, get_resolution_metrics)
        refresh_cache()
        role_to_code("Agency Banking Manager")  # alias hit
        role_to_code("Agency Banking Manager")  # alias hit (re-cached)
        role_to_code("Definitely Unknown")      # miss
        m = get_resolution_metrics()
        assert m["lookups_total"] == 3
        assert m["lookups_hit"] == 2
        assert m["lookups_miss"] == 1
        assert m["resolved_via"]["alias"] == 2
        assert m["resolved_via"]["pinned"] == 0


# ─── role_lookup DSL extractor ───────────────────────────────────────

class TestRoleLookupExtractor:

    def test_compiles_and_resolves(self):
        from utils.aggregation_rules_loader import compile_staff_extractor
        from utils.staff_role_resolver import refresh_cache
        refresh_cache()
        extractor = compile_staff_extractor({
            "type": "role_lookup",
            "role_field": "assigned_to"
        })
        result = extractor({"assigned_to": "Agency Banking Manager"})
        assert result is not None
        assert result.isdigit()
        # Unknown
        assert extractor({"assigned_to": "Made Up Role"}) is None
        assert extractor({}) is None

    def test_missing_role_field_raises(self):
        from utils.aggregation_rules_loader import (
            compile_staff_extractor, PredicateCompileError)
        with pytest.raises(PredicateCompileError):
            compile_staff_extractor({"type": "role_lookup"})


# ─── K129/K130 — incidents wiring via name_lookup ────────────────────

class TestIncidentsWired:

    def test_K129_uses_incidents_with_name_lookup_and_invert(self):
        from utils.kpi_aggregation_rules import REGISTRY
        rule = next(r for r in REGISTRY if r.kpi_id == "K129")
        assert rule.source_table == "incidents"
        assert rule.staff_field_extractor is not None
        assert rule.invert is True, (
            "K129 inverts rate-of-breached to rate-of-clean")

    def test_K130_uses_incidents_count_with_name_lookup(self):
        from utils.kpi_aggregation_rules import REGISTRY
        rule = next(r for r in REGISTRY if r.kpi_id == "K130")
        assert rule.source_table == "incidents"
        assert rule.pattern == "COUNT"
        assert rule.staff_field_extractor is not None

    def test_K129_K130_produce_per_assignee_actuals(self):
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        from utils.staff_name_resolver import refresh_cache

        refresh_cache()
        with open(REPO_ROOT / "data" / "incidents.json") as f:
            incs = json.load(f)

        for kid in ("K129", "K130"):
            rule = next(r for r in REGISTRY if r.kpi_id == kid)
            sf = resolve_staff_field(rule.source_table, rule.staff_field)
            result = compute_rule(rule, incs, "2026-04", sf)
            assert len(result) >= 5
            for staff, val in result.items():
                assert str(staff).isdigit()
                if kid == "K129":
                    assert 0 <= val <= 100
                else:
                    assert val >= 1


# ─── K131 — agent_fraud_alerts via role_lookup ───────────────────────

class TestAgentFraudAlertsWired:

    def test_K131_uses_role_lookup(self):
        from utils.kpi_aggregation_rules import REGISTRY
        rule = next(r for r in REGISTRY if r.kpi_id == "K131")
        assert rule.source_table == "agent_fraud_alerts"
        assert rule.staff_field_extractor is not None

    def test_K131_resolves_via_alias(self):
        """Alias 'Agency Banking Manager' → 'Manager Agency Banking'
        must be in admin config for this to work."""
        from utils.kpi_aggregation_rules import REGISTRY, compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        from utils.staff_role_resolver import (
            refresh_cache, get_resolution_metrics)

        refresh_cache()
        with open(REPO_ROOT / "data" / "agent_fraud_alerts.json") as f:
            afa = json.load(f)
        rule = next(r for r in REGISTRY if r.kpi_id == "K131")
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        result = compute_rule(rule, afa, "2026-04", sf)

        # The Eco Bank seed config has the alias; result should be
        # non-empty with the (single) Manager Agency Banking holder
        assert len(result) >= 1
        m = get_resolution_metrics()
        # All resolutions should go via the alias layer (not direct,
        # not pinned, since admin_config has alias only by default)
        assert m["resolved_via"]["alias"] >= 1


# ─── v10.112 pillar correction ───────────────────────────────────────

class TestV10112PillarFixed:
    """v10.112 used 'People & Capability' for K121/K122/K125/K126/K127
    but the only declared HR pillar is 'People & Learning'. v10.113
    corrects."""

    def test_no_undeclared_pillar_in_library(self):
        with open(REPO_ROOT / "data" / "kpi_library.json") as f:
            lib = json.load(f)
        declared = {p.get("id") for p in lib.get("pillars", [])}
        for k in lib.get("kpis", []):
            pillar = k.get("pillar")
            if pillar:
                assert pillar in declared, (
                    f"KPI {k.get('id')} uses undeclared pillar "
                    f"{pillar!r}; declared pillars: {declared}")

    def test_v10_112_kpis_use_people_and_learning(self):
        with open(REPO_ROOT / "data" / "kpi_library.json") as f:
            lib = json.load(f)
        v112 = ("K121", "K122", "K125", "K126", "K127")
        for k in lib["kpis"]:
            if k.get("id") in v112:
                assert k.get("pillar") == "People & Learning", (
                    f"{k['id']} should be People & Learning, "
                    f"got {k.get('pillar')!r}")


# ─── Admin Module Config — Resolution Metrics + Agent Alerts ─────────

class TestAdminTabsAdded:

    def test_six_tabs_registered(self):
        from pages import _admin_module_specs  # noqa
        from utils.admin_registry import get_registered_modules

        mods = get_registered_modules()
        spec = mods["integration_layer"]
        tab_names = [t["name"] for t in spec["tabs"]]
        assert "Agent Alerts Config" in tab_names
        assert "Resolution Metrics" in tab_names
        assert len(spec["tabs"]) == 6


# ─── G143 coverage advanced ──────────────────────────────────────────

class TestG143CoverageAdvanced:

    def test_coverage_27_or_higher(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            result = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        import re
        m = re.search(r"registered (\d+)\s*/\s*(\d+)", result["summary"])
        n_covered = int(m.group(1))
        n_total = int(m.group(2))
        assert n_covered >= 27, (
            f"v10.113 floor is 27 covered; got {n_covered}/{n_total}")
        assert n_total >= 128, f"got {n_total}"
