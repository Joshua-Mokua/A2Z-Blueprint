"""tests/test_integration_layer_v10_125.py — v10.125.

**STRICT-READY (high) crossing milestone.**

Verifies:
  1. Five new CBS-mock tables seeded — partnerships, vendors, agent_fraud,
     collateral, 360_feedback
  2. STAFF_FIELD_BY_TABLE additions for all five new tables
  3. Two existing-table wires: "Staff Productivity" (4th non-K-coded
     library entry) on hr; K079 on sanctions_register
  4. Six fresh-seed-table rules (K043, K052, K054, K028, K048, K019)
  5. K028/K048 demonstrate library-duplicate handling — both library
     entries share the name "Collateral Review Completion (%)"; both
     wired with identical logic
  6. G143 coverage advanced from 91/131 to ≥99/131 — **STRICT-READY
     (high) tier crossing at 75%+**
  7. Strict-preview tier advances from STRICT-READY (preview) to
     STRICT-READY (high) — milestone for the integration layer
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Five new seeds present and properly shaped ─────────────────────

class TestNewSeeds:

    @pytest.mark.parametrize("table,min_rows,required_fields", [
        ("partnerships", 30, ["id", "rm_code", "activated", "status",
                              "activation_date", "last_review_date"]),
        ("vendors", 30, ["id", "owner_code", "compliant", "kyc_complete",
                         "contract_in_place", "insurance_valid", "status"]),
        ("agent_fraud", 30, ["id", "investigator", "cleared", "status",
                             "raised_date", "severity"]),
        ("collateral", 50, ["id", "credit_officer", "reviewed_in_period",
                            "review_status", "last_review_date",
                            "last_updated"]),
        ("360_feedback", 50, ["id", "ratee_code", "rater_code", "score",
                              "rater_relationship"]),
    ])
    def test_seed_present_with_required_fields(
            self, table, min_rows, required_fields):
        p = REPO_ROOT / "data" / f"{table}.json"
        assert p.exists(), f"{table}.json must be seeded by v10.125"
        with open(p) as f:
            rows = json.load(f)
        assert isinstance(rows, list)
        assert len(rows) >= min_rows
        sample = rows[0]
        for field in required_fields:
            assert field in sample, (
                f"{table} sample missing required field {field!r}")


# ─── STAFF_FIELD_BY_TABLE additions ─────────────────────────────────

class TestStaffFieldAdditionsV10125:

    @pytest.mark.parametrize("table,expected_field", [
        ("partnerships", "rm_code"),
        ("vendors", "owner_code"),
        ("agent_fraud", "investigator"),
        ("collateral", "credit_officer"),
        ("360_feedback", "ratee_code"),
    ])
    def test_staff_field_resolved(self, table, expected_field):
        from utils.staff_field_resolver import resolve_staff_field
        assert resolve_staff_field(table) == expected_field


# ─── 8 new rules registered + producing output ──────────────────────

class TestV10125Rules:

    @pytest.fixture(scope="class")
    def get_rule(self):
        from utils.kpi_aggregation_rules import REGISTRY

        def _get(kid):
            return next((r for r in REGISTRY if r.kpi_id == kid), None)
        return _get

    @pytest.fixture(scope="class")
    def tables(self):
        out = {}
        for t in ("hr", "sanctions_register", "partnerships", "vendors",
                  "agent_fraud", "collateral", "360_feedback"):
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

    def test_staff_productivity_fourth_non_k_coded(self, get_rule, tables):
        """'Staff Productivity' is the fourth non-K-coded library entry
        wired (after Audit Score v10.120, Collection Throughput v10.121,
        CX Score v10.124)."""
        rule = get_rule("Staff Productivity")
        assert rule is not None
        assert rule.source_table == "hr"
        assert rule.pattern == "MEAN_FIELD"
        result = self._compute("Staff Productivity", get_rule, tables)
        assert len(result) >= 50

    def test_K079_sanctions_count(self, get_rule, tables):
        rule = get_rule("K079")
        assert rule.source_table == "sanctions_register"
        assert rule.pattern == "COUNT"
        result = self._compute("K079", get_rule, tables)
        assert len(result) >= 20

    def test_K043_mou_activations(self, get_rule, tables):
        rule = get_rule("K043")
        assert rule.source_table == "partnerships"
        assert rule.pattern == "COUNT"
        result = self._compute("K043", get_rule, tables)
        # Period-field uses last_review_date which is set for all rows
        assert len(result) >= 10

    def test_K052_vendor_compliance(self, get_rule, tables):
        rule = get_rule("K052")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K052", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K054_agent_fraud_cleared(self, get_rule, tables):
        rule = get_rule("K054")
        assert rule.pattern == "PERCENTAGE"
        result = self._compute("K054", get_rule, tables)
        for staff, pct in result.items():
            assert 0 <= pct <= 100

    def test_K028_K048_library_duplicates(self, get_rule, tables):
        """K028 and K048 are duplicate library entries on collateral
        (both named 'Collateral Review Completion (%)'). Both rules
        wire identical logic; library may consolidate in a future
        cleanup."""
        k028 = get_rule("K028")
        k048 = get_rule("K048")
        assert k028.source_table == k048.source_table == "collateral"
        assert k028.pattern == k048.pattern == "PERCENTAGE"
        # Both must produce same outputs against same data
        r28 = self._compute("K028", get_rule, tables)
        r48 = self._compute("K048", get_rule, tables)
        assert r28 == r48, (
            "K028 and K048 should produce identical outputs since "
            "they wire identical logic on the same source")

    def test_K019_360_feedback(self, get_rule, tables):
        rule = get_rule("K019")
        assert rule.source_table == "360_feedback"
        assert rule.pattern == "MEAN_FIELD"
        result = self._compute("K019", get_rule, tables)
        for staff, score in result.items():
            assert 1 <= score <= 5  # 360 feedback 1-5 scale


# ─── G143 STRICT-READY (high) crossing ──────────────────────────────

class TestG143StrictReadyHighCrossing:
    """v10.125 milestone: strict-preview tier advances from
    STRICT-READY (preview) to STRICT-READY (high) at ≥75% coverage."""

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_99_or_higher(self, gate_result):
        assert gate_result["passed"] is True
        sp = gate_result["strict_preview"]
        assert sp["covered"] >= 99, (
            f"v10.125 STRICT-READY (high) requires ≥99 covered; "
            f"got {sp['covered']}/{sp['total_operational']}")

    def test_strict_preview_tier_advances_to_high(self, gate_result):
        """Tier promotion from STRICT-READY (preview) to
        STRICT-READY (high) at the 75% threshold."""
        sp = gate_result["strict_preview"]
        assert sp["tag"] == "STRICT-READY (high)", (
            f"v10.125 should land STRICT-READY (high); got {sp['tag']!r}")
        assert sp["coverage_pct"] >= 75.0

    def test_strict_thresholds_unchanged(self, gate_result):
        """Verify the threshold definitions haven't drifted."""
        sp = gate_result["strict_preview"]
        assert sp["preview_threshold_pct"] == 50.0
        assert sp["high_threshold_pct"] == 75.0
        assert sp["flip_target_pct"] == 100.0
