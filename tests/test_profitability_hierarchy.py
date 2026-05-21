"""tests/test_profitability_hierarchy.py — Standard #22 tests (v5.47).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - TIERS catalog matches spec (platinum 0.8, negative -inf)
       - Tier boundaries are correct ≥-fence-posts
       - classify() returns spec-mandated keys
       - Honesty rule 1: margin=None → unclassified
       - Honesty rule 2: ftp_mode='off' + negative PBT → unclassified
                         with reason that names Mandatory Standard #11
       - min_revenue_for_tier secondary criterion
       - Defensive contract (unknown customer, bad inputs)
       - Determinism (same inputs → same output)
       - Pyramid aggregation correctness
       - Persistence helpers

  2. Classification correctness harness:
       - test_classification_correctness_meets_99_percent runs every
         fixture in tests/fixtures/hierarchy_scenarios.json. Asserts
         ≥99% match (correct tier AND correct action AND, where
         specified, reason contains expected substring). Writes
         hierarchy_classification_results.json for G33.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "hierarchy_scenarios.json"
RESULTS_FILE = ROOT / "hierarchy_classification_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestStandard22Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "profitability_hierarchy.py").exists()

    def test_fixtures_exist(self):
        assert FIXTURES.exists()
        data = json.loads(FIXTURES.read_text())
        assert isinstance(data, list) and len(data) >= 20


# ═══════════════════════════════════════════════════════════════════════
# Spec compliance
# ═══════════════════════════════════════════════════════════════════════

class TestSpecCompliance:
    def test_tiers_has_platinum(self):
        from utils.profitability_hierarchy import TIERS
        assert "platinum" in TIERS
        assert TIERS["platinum"]["threshold"] == 0.8
        assert TIERS["platinum"]["action"] == "Retain at all costs"

    def test_tiers_has_negative(self):
        from utils.profitability_hierarchy import TIERS
        assert "negative" in TIERS
        assert TIERS["negative"]["threshold"] == -float("inf")
        assert TIERS["negative"]["action"] == "Exit relationship"

    def test_class_attribute_mirrors_module_dict(self):
        from utils.profitability_hierarchy import (
            CustomerProfitabilityHierarchy, TIERS,
        )
        assert CustomerProfitabilityHierarchy.TIERS == TIERS

    def test_intermediate_tiers_present(self):
        from utils.profitability_hierarchy import TIERS
        for t in ("gold", "silver", "bronze"):
            assert t in TIERS
            assert "threshold" in TIERS[t]
            assert "action" in TIERS[t]


# ═══════════════════════════════════════════════════════════════════════
# Tier boundaries (fence-posts)
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def basic_engine():
    from utils.profitability_hierarchy import CustomerProfitabilityHierarchy

    def mk_pnl(margin, pbt=None, revenue=1000000, ftp_mode="on"):
        return {
            "pbt": float(pbt) if pbt is not None else float(margin) * revenue,
            "pbt_margin": margin,
            "total_revenue": float(revenue),
            "meta": {"ftp_mode": ftp_mode, "balance_basis": "average"},
        }

    pnls = {
        "PLAT_HIGH":   mk_pnl(0.95),
        "PLAT_BOUND":  mk_pnl(0.80),
        "GOLD":        mk_pnl(0.65),
        "GOLD_BOUND":  mk_pnl(0.50),
        "SILVER":      mk_pnl(0.35),
        "SILV_BOUND":  mk_pnl(0.20),
        "BRONZE":      mk_pnl(0.10),
        "BRZ_BOUND":   mk_pnl(0.00),
        "NEG":         mk_pnl(-0.50),
        "NEG_HUGE":    mk_pnl(-10.0),
    }
    return CustomerProfitabilityHierarchy(
        pnl_lookup_fn=lambda c, p: pnls.get(c),
        all_customers_fn=lambda: list(pnls.keys()),
    )


class TestTierBoundaries:
    def test_platinum_high(self, basic_engine):
        assert basic_engine.classify("PLAT_HIGH", "2026-04")["tier"] == "platinum"

    def test_platinum_boundary_inclusive(self, basic_engine):
        """Margin EXACTLY 0.80 is platinum (≥, not >)."""
        assert basic_engine.classify("PLAT_BOUND", "2026-04")["tier"] == "platinum"

    def test_gold(self, basic_engine):
        assert basic_engine.classify("GOLD", "2026-04")["tier"] == "gold"

    def test_gold_boundary_inclusive(self, basic_engine):
        assert basic_engine.classify("GOLD_BOUND", "2026-04")["tier"] == "gold"

    def test_silver(self, basic_engine):
        assert basic_engine.classify("SILVER", "2026-04")["tier"] == "silver"

    def test_silver_boundary_inclusive(self, basic_engine):
        assert basic_engine.classify("SILV_BOUND", "2026-04")["tier"] == "silver"

    def test_bronze(self, basic_engine):
        assert basic_engine.classify("BRONZE", "2026-04")["tier"] == "bronze"

    def test_bronze_boundary_zero_inclusive(self, basic_engine):
        """Margin exactly 0.0 is bronze, NOT negative."""
        assert basic_engine.classify("BRZ_BOUND", "2026-04")["tier"] == "bronze"

    def test_negative(self, basic_engine):
        assert basic_engine.classify("NEG", "2026-04")["tier"] == "negative"

    def test_negative_extreme(self, basic_engine):
        assert basic_engine.classify("NEG_HUGE", "2026-04")["tier"] == "negative"


# ═══════════════════════════════════════════════════════════════════════
# Spec contract
# ═══════════════════════════════════════════════════════════════════════

class TestSpecContract:
    def test_classify_returns_required_keys(self, basic_engine):
        c = basic_engine.classify("PLAT_HIGH", "2026-04")
        for k in ("customer_id", "period", "tier", "margin", "pbt",
                  "revenue", "action", "reason", "meta"):
            assert k in c

    def test_action_strings_match_spec(self, basic_engine):
        plat = basic_engine.classify("PLAT_HIGH", "2026-04")
        assert plat["action"] == "Retain at all costs"
        neg = basic_engine.classify("NEG", "2026-04")
        assert neg["action"] == "Exit relationship"

    def test_meta_block_has_upstream_provenance(self, basic_engine):
        c = basic_engine.classify("PLAT_HIGH", "2026-04")
        assert "upstream_ftp_mode" in c["meta"]
        assert "upstream_balance_basis" in c["meta"]
        assert "tier_thresholds" in c["meta"]


# ═══════════════════════════════════════════════════════════════════════
# Honesty rules (Mandatory Standard #11)
# ═══════════════════════════════════════════════════════════════════════

class TestHonestyRules:
    def test_none_margin_returns_unclassified(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": -100, "pbt_margin": None, "total_revenue": 0,
                "meta": {"ftp_mode": "on"},
            },
        )
        c = eng.classify("X", "2026-04")
        assert c["tier"] == "unclassified"
        assert "None" in c["reason"] or "revenue" in c["reason"]

    def test_ftp_off_negative_pbt_unclassified(self):
        """The CANONICAL master-prompt-Standard-11 demonstration:
        a deposit-funder customer mis-priced by naive gross-interest
        math must NOT be auto-tagged for exit."""
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": -6500, "pbt_margin": -3.25, "total_revenue": 2000,
                "meta": {"ftp_mode": "off"},
            },
        )
        c = eng.classify("X", "2026-04")
        assert c["tier"] == "unclassified", (
            f"Engine wrongly tagged FTP-blind deposit-funder as {c['tier']!r}"
        )
        assert "Mandatory Standard #11" in c["reason"]

    def test_ftp_on_negative_classifies_as_negative(self):
        """Same numbers, FTP-aware upstream → engine WILL tag negative."""
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": -6500, "pbt_margin": -3.25, "total_revenue": 2000,
                "meta": {"ftp_mode": "on"},
            },
        )
        c = eng.classify("X", "2026-04")
        assert c["tier"] == "negative"
        assert c["action"] == "Exit relationship"

    def test_ftp_off_positive_pbt_classifies_normally(self):
        """ftp_mode='off' alone doesn't trigger unclassified —
        the heuristic only fires when PBT is also negative."""
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": 50000, "pbt_margin": 0.30, "total_revenue": 166666,
                "meta": {"ftp_mode": "off"},
            },
        )
        c = eng.classify("X", "2026-04")
        assert c["tier"] == "silver"

    def test_unclassified_has_reason(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": -100, "pbt_margin": None, "total_revenue": 0,
                "meta": {"ftp_mode": "on"},
            },
        )
        c = eng.classify("X", "2026-04")
        assert c["reason"]    # non-empty
        assert c["action"] == "Re-evaluate when upstream data is complete"


# ═══════════════════════════════════════════════════════════════════════
# Secondary criterion (min_revenue_for_tier)
# ═══════════════════════════════════════════════════════════════════════

class TestSecondaryCriterion:
    def test_demotion_when_below_floor(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": 80, "pbt_margin": 0.80, "total_revenue": 100,
                "meta": {"ftp_mode": "on"},
            },
            min_revenue_for_tier={"platinum": 50000},
        )
        c = eng.classify("X", "2026-04")
        # Demoted from platinum → gold
        assert c["tier"] == "gold"

    def test_no_demotion_when_above_floor(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": 800000, "pbt_margin": 0.80, "total_revenue": 1000000,
                "meta": {"ftp_mode": "on"},
            },
            min_revenue_for_tier={"platinum": 50000},
        )
        c = eng.classify("X", "2026-04")
        assert c["tier"] == "platinum"

    def test_invalid_tier_in_secondary_raises(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        with pytest.raises(ValueError):
            CustomerProfitabilityHierarchy(
                min_revenue_for_tier={"diamond": 1_000_000},
            )

    def test_meta_records_secondary_criterion(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: {
                "pbt": 80000, "pbt_margin": 0.80, "total_revenue": 100000,
                "meta": {"ftp_mode": "on"},
            },
            min_revenue_for_tier={"platinum": 50000},
        )
        c = eng.classify("X", "2026-04")
        assert c["meta"]["tier_secondary_criterion"] == {"platinum": 50000}

    def test_no_secondary_criterion_records_none(self, basic_engine):
        c = basic_engine.classify("PLAT_HIGH", "2026-04")
        assert c["meta"]["tier_secondary_criterion"] is None


# ═══════════════════════════════════════════════════════════════════════
# Defensive contract
# ═══════════════════════════════════════════════════════════════════════

class TestDefensiveContract:
    def test_unknown_customer_returns_empty(self, basic_engine):
        assert basic_engine.classify("UNKNOWN", "2026-04") == {}

    def test_empty_customer_id_returns_empty(self, basic_engine):
        assert basic_engine.classify("", "2026-04") == {}

    def test_empty_period_returns_empty(self, basic_engine):
        assert basic_engine.classify("PLAT_HIGH", "") == {}

    def test_pnl_lookup_returns_none_returns_empty(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(pnl_lookup_fn=lambda c, p: None)
        assert eng.classify("ANY", "2026-04") == {}


# ═══════════════════════════════════════════════════════════════════════
# Pyramid aggregation
# ═══════════════════════════════════════════════════════════════════════

class TestPyramid:
    def test_pyramid_counts(self, basic_engine):
        p = basic_engine.build_pyramid("2026-04")
        # 10 customers across 5 tiers (2 each in fixture)
        assert p["total_customers"] == 10
        assert p["tiers"]["platinum"]["count"] == 2
        assert p["tiers"]["gold"]["count"] == 2
        assert p["tiers"]["silver"]["count"] == 2
        assert p["tiers"]["bronze"]["count"] == 2
        assert p["tiers"]["negative"]["count"] == 2

    def test_pyramid_shares_sum_to_one(self, basic_engine):
        p = basic_engine.build_pyramid("2026-04")
        total_share = sum(b["share"] for b in p["tiers"].values())
        assert abs(total_share - 1.0) < 1e-6

    def test_pyramid_includes_unclassified_bucket(self, basic_engine):
        p = basic_engine.build_pyramid("2026-04")
        assert "unclassified" in p["tiers"]

    def test_pyramid_unavailable_customers_tracked(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: (
                {"pbt": 1000, "pbt_margin": 0.50, "total_revenue": 2000,
                 "meta": {"ftp_mode": "on"}}
                if c == "OK" else None
            ),
            all_customers_fn=lambda: ["OK", "MISSING_1", "MISSING_2"],
        )
        p = eng.build_pyramid("2026-04")
        assert p["total_customers"] == 1
        assert p["meta"]["requested_count"] == 3
        assert p["meta"]["unavailable_count"] == 2

    def test_pyramid_actions_match_spec(self, basic_engine):
        p = basic_engine.build_pyramid("2026-04")
        assert p["tiers"]["platinum"]["action"] == "Retain at all costs"
        assert p["tiers"]["negative"]["action"] == "Exit relationship"

    def test_empty_pyramid(self):
        from utils.profitability_hierarchy import CustomerProfitabilityHierarchy
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p: None,
            all_customers_fn=lambda: [],
        )
        p = eng.build_pyramid("2026-04")
        assert p["total_customers"] == 0

    def test_empty_period_returns_empty(self, basic_engine):
        assert basic_engine.build_pyramid("") == {}


# ═══════════════════════════════════════════════════════════════════════
# Determinism (the "Pyramid updates daily" claim implies idempotence)
# ═══════════════════════════════════════════════════════════════════════

class TestDeterminism:
    def test_two_runs_produce_same_pyramid(self, basic_engine):
        p1 = basic_engine.build_pyramid("2026-04")
        p2 = basic_engine.build_pyramid("2026-04")
        # Strip volatile timestamps
        def strip(d):
            if isinstance(d, dict):
                return {k: strip(v) for k, v in d.items()
                        if k not in ("generated_at", "classified_at")}
            if isinstance(d, list):
                return [strip(x) for x in d]
            return d
        assert strip(p1) == strip(p2)


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_save_and_get(self, tmp_path, monkeypatch):
        from utils import profitability_hierarchy as ph
        monkeypatch.setattr(ph, "PYRAMID_FILE", tmp_path / "pyramid.json")
        snap = {"total_customers": 5, "tiers": {}}
        ok = ph.save_pyramid("2026-04", snap)
        assert ok is True
        got = ph.get_pyramid("2026-04")
        assert got and got["total_customers"] == 5

    def test_save_empty_returns_false(self, tmp_path, monkeypatch):
        from utils import profitability_hierarchy as ph
        monkeypatch.setattr(ph, "PYRAMID_FILE", tmp_path / "pyramid.json")
        assert ph.save_pyramid("2026-04", {}) is False

    def test_save_empty_period_returns_false(self, tmp_path, monkeypatch):
        from utils import profitability_hierarchy as ph
        monkeypatch.setattr(ph, "PYRAMID_FILE", tmp_path / "pyramid.json")
        assert ph.save_pyramid("", {"total_customers": 1}) is False


# ═══════════════════════════════════════════════════════════════════════
# Classification correctness harness — Standard #22 spec verification
# ═══════════════════════════════════════════════════════════════════════

def test_classification_correctness_meets_99_percent():
    """Run every fixture; assert ≥99% match; write G33 artifact.

    A fixture passes when:
      - actual tier == expected tier
      - actual action string == expected action string
      - if expected.reason_contains is set, actual.reason contains it

    "Pyramid updates daily" is a deployed-runtime metric (whether a
    daily scheduler runs), and OUT OF SCOPE for verification in code.
    What IS verifiable is structural classification correctness on a
    labeled fixture set — that's the G33 bar.
    """
    from utils.profitability_hierarchy import CustomerProfitabilityHierarchy

    scenarios = json.loads(FIXTURES.read_text())
    assert len(scenarios) >= 20

    correct = 0
    results = []
    for s in scenarios:
        pnl = s["input"]["pnl"]
        eng = CustomerProfitabilityHierarchy(
            pnl_lookup_fn=lambda c, p, _pnl=pnl: _pnl,
        )
        c = eng.classify("X", "2026-04")
        expected = s["expected"]

        actual_tier = c.get("tier")
        actual_action = c.get("action")
        tier_ok = actual_tier == expected["tier"]
        action_ok = actual_action == expected["action"]
        reason_ok = True
        if "reason_contains" in expected:
            reason_ok = expected["reason_contains"] in c.get("reason", "")

        match = tier_ok and action_ok and reason_ok
        if match:
            correct += 1

        results.append({
            "id":              s["id"],
            "actual_tier":     actual_tier,
            "expected_tier":   expected["tier"],
            "actual_action":   actual_action,
            "expected_action": expected["action"],
            "tier_ok":         tier_ok,
            "action_ok":       action_ok,
            "reason_ok":       reason_ok,
            "matched":         match,
        })

    total = len(scenarios)
    accuracy = correct / total * 100

    artifact = {
        "schema_version":  1,
        "run_at":          datetime.now(timezone.utc).isoformat(),
        "total_scenarios": total,
        "correct":         correct,
        "accuracy_pct":    round(accuracy, 2),
        "spec_target_pct": 99.0,
        "all_passed":      accuracy >= 99.0,
        "results":         results,
    }
    RESULTS_FILE.write_text(json.dumps(artifact, indent=2))

    assert accuracy >= 99.0, (
        f"Classification correctness {accuracy:.1f}% < 99%; failures:\n"
        + "\n".join(
            f"  {r['id']}: tier {r['actual_tier']!r} "
            f"(expected {r['expected_tier']!r}), "
            f"tier_ok={r['tier_ok']}, action_ok={r['action_ok']}, "
            f"reason_ok={r['reason_ok']}"
            for r in results if not r["matched"]
        )
    )
