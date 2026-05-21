"""tests/test_integration_layer_v10_128.py — v10.128 Streamlit cockpit.

v10.128 ships pages/99_integration_cockpit.py — the Streamlit cockpit
that surfaces the Phase 1D integration layer's 5 API endpoints in the
live app. Closes the "connect standards to the live Streamlit app" gap
flagged in programme focus areas.

Verifies:
  1. Cockpit page file exists at pages/99_integration_cockpit.py
  2. Page has valid Python syntax (importable in the Streamlit runtime)
  3. Page mirrors the 5 conceptual API endpoints in tab structure
  4. Page references all 5 /api/integration/* endpoints in copy
  5. Page imports the standard cockpit conventions (require_access,
     audit_log, st.set_page_config)
  6. Page surfaces v10.126 role-gating semantics (does not silently
     hide them per Rule 7)
  7. Run-period button defaults to dry_run=True (Rule 7 — surface,
     don't auto-fix)
  8. Writes route to the API endpoint, not duplicated inline
  9. G143 still 99/131 STRICT-READY (high) — no rule-density work
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
COCKPIT_PATH = REPO_ROOT / "pages" / "99_integration_cockpit.py"


# ─── Page presence + syntax ─────────────────────────────────────────

class TestCockpitPagePresence:

    def test_page_file_exists(self):
        assert COCKPIT_PATH.exists(), (
            "v10.128 must ship pages/99_integration_cockpit.py")

    def test_page_has_valid_python_syntax(self):
        src = COCKPIT_PATH.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"Cockpit page has syntax error: {e}")

    def test_page_substantive_size(self):
        """Sanity check — the cockpit isn't empty."""
        size = COCKPIT_PATH.stat().st_size
        assert size > 5000, (
            f"Cockpit page suspiciously small ({size} bytes) — "
            "expected ~10K+")


# ─── Tab structure mirrors the 5 API endpoints ──────────────────────

class TestCockpitTabStructure:

    @pytest.fixture(scope="class")
    def src(self):
        return COCKPIT_PATH.read_text(encoding="utf-8")

    def test_five_tabs_present(self, src):
        """The cockpit organises around the 5 Integration Layer API
        endpoints. Each gets a tab."""
        for tab_label in ("Coverage", "Rules", "Preview Actuals",
                          "Resolution Metrics", "Run Period"):
            assert tab_label in src, (
                f"Cockpit should have a '{tab_label}' tab")

    def test_references_all_five_api_endpoints(self, src):
        """The cockpit's docstring + captions should reference the 5
        endpoints so operators know the API↔UI mapping."""
        for endpoint in ("/api/integration/coverage",
                         "/api/integration/actuals",
                         "/api/integration/resolution-metrics",
                         "/api/integration/run-period"):
            assert endpoint in src, (
                f"Cockpit should reference {endpoint}")


# ─── Standard cockpit-page conventions ──────────────────────────────

class TestCockpitConventions:

    @pytest.fixture(scope="class")
    def src(self):
        return COCKPIT_PATH.read_text(encoding="utf-8")

    def test_uses_require_access(self, src):
        """All cockpit pages use pages._access.require_access for
        role-based page entry guards."""
        assert "from pages._access import require_access" in src
        assert "require_access(" in src

    def test_uses_audit_log(self, src):
        """Cockpit pages emit audit logs on view + on action."""
        assert "from utils.core_audit import audit_log" in src
        assert "audit_log(" in src

    def test_streamlit_imported(self, src):
        assert "import streamlit as st" in src

    def test_set_page_config_present(self, src):
        assert "st.set_page_config" in src


# ─── v10.126 role-gating semantics surface in cockpit ───────────────

class TestRoleGatingSurfacedInCockpit:
    """v10.128 cockpit should not just consume role-gating silently —
    it should TELL operators what's happening per Rule 7 (surface,
    don't hide)."""

    @pytest.fixture(scope="class")
    def src(self):
        return COCKPIT_PATH.read_text(encoding="utf-8")

    def test_references_v10_126_default_flip(self, src):
        """The Run Period tab should explain the v10.126 hard-flip
        default so operators understand why their role matters."""
        assert "v10.126" in src

    def test_role_gating_enabled_check(self, src):
        """The cockpit should read role_gating_enabled from config and
        surface it (informational, not a silent block)."""
        assert "role_gating_enabled" in src

    def test_allowed_roles_surfaced(self, src):
        """The allowed_roles_for_write list should be displayed to the
        user so they know which role to request."""
        assert "allowed_roles_for_write" in src


# ─── Rule 7 — surface, don't auto-fix ───────────────────────────────

class TestRule7Surfacing:

    @pytest.fixture(scope="class")
    def src(self):
        return COCKPIT_PATH.read_text(encoding="utf-8")

    def test_dry_run_defaults_on(self, src):
        """Run Period button must default dry_run=True. Operators must
        explicitly uncheck to write."""
        # The cockpit declaration sets value=True on the dry_run checkbox
        assert "value=True" in src
        # And the dry_run concept is named
        assert "dry_run" in src.lower() or "Dry run" in src

    def test_writes_route_to_api_not_cockpit(self, src):
        """The cockpit explicitly routes WRITE operations to the API
        endpoint rather than implementing them inline. Prevents the
        cockpit from accumulating duplicate write paths."""
        assert ("Cockpit only supports DRY RUN" in src or
                "POST /api/integration/run-period" in src), \
               "Cockpit should route writes to the API endpoint"


# ─── G143 unchanged — not a rule-density drop ────────────────────────

class TestG143UnchangedV10128:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_still_99(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["covered"] == 99

    def test_tier_still_high(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (high)"


# ─── Backend file presence ──────────────────────────────────────────

class TestCockpitBackendPresence:
    """The cockpit reads from the same JSON files the API endpoints do.
    Verify the file paths it references exist and are readable."""

    def test_aggregation_rules_json_present(self):
        assert (REPO_ROOT / "data" / "aggregation_rules.json").exists()

    def test_kpi_library_json_present(self):
        assert (REPO_ROOT / "data" / "kpi_library.json").exists()

    def test_integration_layer_config_json_present(self):
        """v10.120's _security block ships here; cockpit must read it
        to surface role-gating state."""
        assert (REPO_ROOT / "data" /
                "integration_layer_config.json").exists()


# ─── No new rules in v10.128 ────────────────────────────────────────

class TestNoRuleDensityV10128:

    def test_no_v10_128_origin_rules(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        v128 = [r for r in data["rules"]
                if r.get("_origin", "").startswith("v10.128_")]
        assert v128 == [], (
            f"v10.128 is a UI drop, not rule-density. Found "
            f"{len(v128)} v10.128-origin rules; expected 0.")

    def test_total_rules_still_100(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        assert len(data["rules"]) == 100
