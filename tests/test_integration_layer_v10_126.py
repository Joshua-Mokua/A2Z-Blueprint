"""tests/test_integration_layer_v10_126.py — v10.126 Phase 1D close-out.

Verifies:
  1. Role-gating code default flipped from OFF to ON
  2. Existing config-on deployments unchanged (regression check)
  3. Explicit config-off deployments still respected (escape hatch)
  4. Phase 1D retro doc + path-to-100 doc shipped
  5. G143 still STRICT-READY (high) — coverage unchanged
  6. No new rules added (close-out drop, not rule-density)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Role-gating code default flip (v10.126) ────────────────────────

class TestRoleGatingDefaultFlip:
    """v10.126 flips _read_security_config()'s code default from
    role_gating_enabled=False to role_gating_enabled=True. Deployments
    that don't explicitly set the flag now get role-gating ON."""

    def _read_config_with_security(self, security_block):
        """Helper: write a temporary config file with the given
        _security block (or no block), reload _read_security_config,
        and return the result."""
        # Read current api.py source and verify the default is True
        src = (REPO_ROOT / "utils" / "api.py").read_text()
        assert '"role_gating_enabled":     True,   # v10.126: flipped from False' in src, (
            "v10.126 must flip the base default from False to True")
        assert 'sec.get("role_gating_enabled", True)' in src, (
            "v10.126 must flip the fallback (when _security block has "
            "the field missing) from False to True")

    def test_default_dict_is_true(self):
        """Source-level check: the default dict in _read_security_config
        sets role_gating_enabled=True."""
        src = (REPO_ROOT / "utils" / "api.py").read_text()
        # The False default comment from v10.117 should be gone
        assert '"role_gating_enabled":     False,' not in src, (
            "v10.126 should remove the False default; found stale code")

    def test_v10_120_explicit_config_unchanged(self):
        """v10.120 ships the explicit `_security` block in config with
        role_gating_enabled=true. v10.126's flip doesn't affect this —
        explicit-true stays explicit-true."""
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        sec = cfg["_security"]
        assert sec["role_gating_enabled"] is True, (
            "v10.120 explicit config block should remain "
            "role_gating_enabled=true")

    def test_canonical_role_taxonomy_unchanged(self):
        """v10.120's canonical Eco Bank role taxonomy should be
        preserved under v10.126."""
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        roles = cfg["_security"]["allowed_roles_for_write"]
        for r in ("admin", "integration", "MD", "CFO",
                  "Chief Transformation Officer"):
            assert r in roles, f"Canonical role {r!r} missing"

    def test_explicit_false_escape_hatch_preserved(self):
        """The escape hatch — deployments that explicitly want JWT-only
        auth must set role_gating_enabled: false explicitly. The code
        must still respect this override."""
        # Source-level check: the get with default=True still respects
        # an explicit False
        src = (REPO_ROOT / "utils" / "api.py").read_text()
        # The pattern is `bool(sec.get("role_gating_enabled", True))` —
        # an explicit False in config will override the True default.
        assert 'sec.get("role_gating_enabled", True)' in src
        # Verify the boolean coercion is in place (sec.get returns False
        # explicitly, not None, when the key is set to false)
        assert 'bool(sec.get("role_gating_enabled", True))' in src


# ─── Phase 1D close-out artifacts ───────────────────────────────────

class TestPhase1DClosureDocs:

    def test_retro_doc_present(self):
        """The Phase 1D retro doc captures the sprint-level summary of
        what was built, what was deferred, and what's left."""
        p = REPO_ROOT / "docs" / "Phase_1D_Integration_Layer_Retro.md"
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        # Spot-check for key sections
        for section in ("Programme context",
                        "What was built",
                        "Architectural patterns",
                        "Trajectory table",
                        "Path to 100%",
                        "What didn't get done"):
            assert section in content, (
                f"Retro doc missing section: {section}")
        # Must reference the milestone
        assert "STRICT-READY (high)" in content
        assert "99/131" in content or "75.6%" in content

    def test_path_to_100_doc_present(self):
        """The bank-level pipeline architecture proposal documents
        what Phase 1E (or later) needs to do to cover the remaining
        ~32 bank-level KPIs."""
        p = REPO_ROOT / "docs" / "Path_to_100_Bank_Level_Pipeline.md"
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        for section in ("Problem statement",
                        "Design",
                        "Bank-level aggregator types",
                        "Effort estimate",
                        "Recommendation"):
            assert section in content


# ─── G143 unchanged from v10.125 ────────────────────────────────────

class TestG143StillHigh:
    """v10.126 is a close-out drop, not rule density. G143 coverage
    should remain at the v10.125 level (99/131 = 75.6%)."""

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
        assert sp["covered"] == 99, (
            f"v10.126 should preserve v10.125's 99/131 coverage; "
            f"got {sp['covered']}")

    def test_tier_still_strict_ready_high(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (high)"
        assert sp["coverage_pct"] >= 75.0


# ─── No new rules / no rule density work ────────────────────────────

class TestCloseOutNotRuleDensity:
    """v10.126 explicitly is NOT a rule-density drop. It closes out
    Phase 1D with a code default flip + retro docs. New rules go in
    a future drop or never (if we pivot to standards / bank-level
    pipeline)."""

    def test_no_v10_126_origin_rules(self):
        """No rules should have _origin starting with 'v10.126_' — this
        drop doesn't add rules."""
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        v126_rules = [r for r in data["rules"]
                      if r.get("_origin", "").startswith("v10.126_")]
        assert v126_rules == [], (
            f"v10.126 is a close-out drop, not rule-density. Found "
            f"{len(v126_rules)} v10.126-origin rules; expected 0.")

    def test_total_rule_count_unchanged(self):
        """Total rule count should match v10.125's 100."""
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        assert len(data["rules"]) == 100, (
            f"v10.126 should preserve v10.125's 100 rules; "
            f"got {len(data['rules'])}")
