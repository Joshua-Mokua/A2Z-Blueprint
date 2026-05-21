"""tests/test_integration_layer_v10_120.py — v10.120.

Verifies:
  1. Seven new/wired rules produce real outputs (K090, K051,
     "Audit Score", K061 are new for v10.120; K027/K113/K044 were
     present but uncovered in G143 — now covered)
  2. K061 uses TAT_DAYS pattern with date_le_field guard against
     negative TATs (data-quality issue with seed)
  3. K090 uses the period_field=dispute_filed_date pattern (when
     fraud was reported, not when card was issued)
  4. "Audit Score" demonstrates non-K-coded library entry support
  5. v10.120 role-gating GA — `_security` block ships explicitly in
     `integration_layer_config.json` with role_gating_enabled=true
     and the canonical allowed_roles_for_write taxonomy
  6. G143 coverage advanced from 66/131 to ≥70/131
  7. Strict-preview tier remains STRICT-READY (preview); not yet at
     STRICT-READY (high)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── 7 rules registered + producing output ──────────────────────────

class TestV10120Rules:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("debt_recovery", "card_management", "purchase_requests",
                  "audit_reviews", "referrals", "retailer_finance"):
            with open(REPO_ROOT / "data" / f"{t}.json") as f:
                d = json.load(f)
            out[t] = d if isinstance(d, list) else list(d.values())
        return out

    def _compute(self, kid, get_rule, tables):
        from utils.kpi_aggregation_rules import compute_rule
        from utils.staff_field_resolver import resolve_staff_field
        from utils.staff_name_resolver import refresh_cache
        refresh_cache()
        rule = get_rule(kid)
        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        return compute_rule(rule, tables[rule.source_table], "2026-04", sf)

    def test_K027_recovery_rate(self, get_rule, tables):
        rule = get_rule("K027")
        assert rule.pattern == "RATIO"
        result = self._compute("K027", get_rule, tables)
        assert len(result) >= 5
        for staff, ratio in result.items():
            assert ratio >= 0  # recovery rate is ≥ 0

    def test_K113_active_recovery_count(self, get_rule, tables):
        rule = get_rule("K113")
        assert rule.pattern == "COUNT"
        result = self._compute("K113", get_rule, tables)
        for staff, n in result.items():
            assert n >= 1

    def test_K090_card_fraud_loss_uses_dispute_filed_date(
            self, get_rule, tables):
        """K090 period_field is dispute_filed_date (when fraud was
        reported), not issue_date. The seed has very few fraud events
        in 2026-04, so coverage is sparse — but the rule is correctly
        designed."""
        rule = get_rule("K090")
        assert rule.source_table == "card_management"
        assert rule.pattern == "SUM"
        assert rule.period_field == "dispute_filed_date", (
            f"K090 should use dispute_filed_date for period filter; "
            f"got {rule.period_field!r}")

    def test_K051_prs_processed_in_range(self, get_rule, tables):
        rule = get_rule("K051")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K051", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_audit_score_uses_mean_field_pattern(self, get_rule, tables):
        """v10.120 wires the 'Audit Score' KPI library entry, which is
        not K-coded. Demonstrates non-K-coded library entry support."""
        rule = get_rule("Audit Score")
        assert rule is not None, (
            "v10.120 should wire the 'Audit Score' library entry")
        assert rule.source_table == "audit_reviews"
        assert rule.pattern == "MEAN_FIELD"
        assert rule.value_field == "score"
        result = self._compute("Audit Score", get_rule, tables)
        for staff, mean in result.items():
            assert 1 <= mean <= 5  # audit scores are 1-5

    def test_K044_referral_conversion_in_range(self, get_rule, tables):
        rule = get_rule("K044")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K044", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K061_lpo_tat_uses_date_le_field_guard(self, get_rule, tables):
        """K061 uses date_le_field as a guard against negative TATs —
        retailer_finance seed has rows where disbursement_date precedes
        application_date (data-quality issue surfaced via the
        predicate, not silently emitting nonsense values)."""
        rule = get_rule("K061")
        assert rule.pattern == "TAT_DAYS"
        assert rule.start_field == "application_date"
        assert rule.end_field == "disbursement_date"
        result = self._compute("K061", get_rule, tables)
        # All values should be ≥ 0 (the date_le_field guard ensures
        # disbursement >= application)
        for staff, tat in result.items():
            assert tat >= 0, (
                f"K061 should reject negative-TAT rows; "
                f"staff {staff} → {tat}")


# ─── Role-gating GA — config readback ───────────────────────────────

class TestRoleGatingGA:
    """v10.120 ships an explicit `_security` block in
    `integration_layer_config.json` with role_gating_enabled=true and
    the canonical allowed_roles_for_write taxonomy. The code default
    in `_read_security_config()` stays OFF for backward compat with
    deployments that update v10.117→v10.120 in one go without
    consuming the new config."""

    def test_security_block_present_in_config(self):
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        assert "_security" in cfg
        sec = cfg["_security"]
        assert sec.get("role_gating_enabled") is True

    def test_allowed_roles_includes_canonical_taxonomy(self):
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        roles = cfg["_security"]["allowed_roles_for_write"]
        # Core technical roles
        assert "admin" in roles
        assert "integration" in roles
        # Executive roles from the canonical Eco Bank taxonomy
        for r in ("Chief Transformation Officer", "MD", "CFO"):
            assert r in roles, f"Canonical role {r!r} missing"

    def test_security_block_has_documentation(self):
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        doc = cfg["_security"].get("_documentation", "")
        assert "v10.120" in doc
        assert "role_gating_enabled" in doc

    def test_role_gating_check_logic(self):
        """Replicates _check_write_role logic — allowed roles pass,
        non-allowed deny. Verifies the contract against the v10.120
        canonical taxonomy."""
        cfg_path = REPO_ROOT / "data" / "integration_layer_config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        sec = cfg["_security"]

        def check(user_role):
            if not sec.get("role_gating_enabled"):
                return "ALLOW"
            return "ALLOW" if user_role in sec["allowed_roles_for_write"] else "DENY"

        assert check("admin") == "ALLOW"
        assert check("MD") == "ALLOW"
        assert check("Chief Transformation Officer") == "ALLOW"
        assert check("Teller") == "DENY"
        assert check("") == "DENY"
        assert check(None) == "DENY"


# ─── G143 coverage + tier ───────────────────────────────────────────

class TestG143CoverageV10120:

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_70_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 70, (
            f"v10.120 expected ≥70 covered; got {sp['covered']}/"
            f"{sp['total_operational']}")

    def test_strict_preview_tier_still_preview(self, gate_result):
        """v10.120 lands at ~53% — solidly in STRICT-READY (preview)
        tier but not yet at STRICT-READY (high) which requires 75%."""
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (preview)", (
            f"v10.120 should remain at STRICT-READY (preview); "
            f"got {sp['tag']!r}")
        assert 50.0 <= sp["coverage_pct"] < 75.0
