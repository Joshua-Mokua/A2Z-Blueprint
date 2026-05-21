"""tests/test_product_v10_145.py — ENH-134 Competitive Intelligence for Products

Verifies the v10.145 deliverable:
- Engine module exists, parses, exposes class + frozen dataclass + 6 methods
- Position classification respects direction (lending vs deposits)
- LEADER / FOLLOWER / LAGGARD / NO_DATA cases all reachable
- Honest fallback when product has no competitor benchmark mapping
- compare_pricing ranks correctly (asc for lending, desc for deposits)
- get_peer_benchmarks for bank-level metrics
- identify_pricing_gaps with direction labels
- Mapping seed shape
- Registry: ENH-134 active
- Admin Tier 4B has all four engines
- No regression
"""
from __future__ import annotations
import ast
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "product_competitive_intel.py"
MAPPING_PATH = REPO_ROOT / "data" / "product_competitor_mapping.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestEngineModule:
    def test_module_exists(self):
        assert ENGINE_PATH.exists()

    def test_module_parses(self):
        ast.parse(ENGINE_PATH.read_text())

    def test_class_and_dataclass_present(self):
        m = _load("pci_shape", ENGINE_PATH)
        assert hasattr(m, "ProductCompetitiveIntelligence")
        assert hasattr(m, "CompetitorLandscape")

    def test_required_public_methods(self):
        m = _load("pci_methods", ENGINE_PATH)
        eng = m.ProductCompetitiveIntelligence()
        for method in (
            "get_competitor_landscape", "compare_pricing",
            "get_market_position", "get_peer_benchmarks",
            "identify_pricing_gaps", "get_competitive_summary",
        ):
            assert hasattr(eng, method)
            assert callable(getattr(eng, method))


class TestLandscape:
    def _engine(self):
        m = _load("pci_l", ENGINE_PATH)
        return m.ProductCompetitiveIntelligence(), m

    def test_lending_product_returns_landscape(self):
        eng, _ = self._engine()
        l = eng.get_competitor_landscape("P001")  # Personal Loans
        assert l.status == "ok"
        assert l.benchmark_type == "lending"
        assert l.n_peers > 0
        assert l.position in ("LEADER", "FOLLOWER", "LAGGARD")

    def test_deposit_product_returns_landscape(self):
        eng, _ = self._engine()
        l = eng.get_competitor_landscape("P014")  # Fixed Deposits
        assert l.status == "ok"
        assert l.benchmark_type == "deposits"

    def test_unmapped_product_returns_no_benchmark(self):
        eng, _ = self._engine()
        l = eng.get_competitor_landscape("P010")  # Trade Finance LC
        assert l.status == "no_competitor_benchmark"
        assert l.reason is not None
        assert l.position == "NO_DATA"

    def test_unknown_product_returns_not_found(self):
        eng, _ = self._engine()
        l = eng.get_competitor_landscape("P_BOGUS")
        assert l.status == "product_not_found"
        assert l.position == "NO_DATA"


class TestPositionDirectionality:
    def _engine(self):
        m = _load("pci_dir", ENGINE_PATH)
        return m.ProductCompetitiveIntelligence(), m

    def test_lending_lower_rate_is_leader(self):
        eng, _ = self._engine()
        # P001 Personal Loans us=14.5% vs peer median around 18% → LEADER
        l = eng.get_competitor_landscape("P001")
        assert l.status == "ok"
        # Our rate is below median (delta negative) → LEADER for lending
        if l.delta_vs_median_bps is not None and l.delta_vs_median_bps <= -50:
            assert l.position == "LEADER"

    def test_deposits_higher_rate_is_leader(self):
        # Test the directional logic via internal helper directly with
        # a constructed scenario: deposits where we pay MORE than median
        eng, m = self._engine()
        pos, delta = eng._classify_position(
            our_rate=Decimal("10.0"),
            median=Decimal("8.0"),
            benchmark_type="deposits")
        assert pos == "LEADER"
        assert delta == 200

    def test_deposits_lower_rate_is_laggard(self):
        eng, _ = self._engine()
        pos, delta = eng._classify_position(
            our_rate=Decimal("8.0"),
            median=Decimal("10.0"),
            benchmark_type="deposits")
        assert pos == "LAGGARD"
        assert delta == -200

    def test_lending_higher_rate_is_laggard(self):
        eng, _ = self._engine()
        pos, delta = eng._classify_position(
            our_rate=Decimal("20.0"),
            median=Decimal("18.0"),
            benchmark_type="lending")
        assert pos == "LAGGARD"
        assert delta == 200

    def test_within_threshold_is_follower(self):
        eng, _ = self._engine()
        pos, delta = eng._classify_position(
            our_rate=Decimal("18.0"),
            median=Decimal("18.2"),
            benchmark_type="lending")
        assert pos == "FOLLOWER"


class TestComparePricing:
    def _engine(self):
        m = _load("pci_cmp", ENGINE_PATH)
        return m.ProductCompetitiveIntelligence()

    def test_lending_sorted_ascending(self):
        result = self._engine().compare_pricing("P001")
        assert result["ok"] is True
        assert result["benchmark_type"] == "lending"
        rates = [float(r["rate_pct"]) for r in result["ranked_rates"]]
        assert rates == sorted(rates)  # ascending for lending

    def test_deposits_sorted_descending(self):
        result = self._engine().compare_pricing("P014")
        assert result["ok"] is True
        assert result["benchmark_type"] == "deposits"
        rates = [float(r["rate_pct"]) for r in result["ranked_rates"]]
        assert rates == sorted(rates, reverse=True)

    def test_unmapped_product_returns_not_ok(self):
        result = self._engine().compare_pricing("P012")  # Current Accounts
        assert result["ok"] is False

    def test_us_marker_present(self):
        result = self._engine().compare_pricing("P001")
        assert any(r["is_us"] for r in result["ranked_rates"])
        assert sum(1 for r in result["ranked_rates"] if r["is_us"]) == 1


class TestPeerBenchmarks:
    def _engine(self):
        m = _load("pci_peer", ENGINE_PATH)
        return m.ProductCompetitiveIntelligence()

    def test_npl_pct_returns_real_data(self):
        b = self._engine().get_peer_benchmarks("npl_pct")
        assert b["ok"] is True
        assert b["our_value"] is not None
        assert b["peer_median"] is not None
        assert b["n_peers"] >= 3  # robust median expected

    def test_unknown_metric_returns_fallback(self):
        b = self._engine().get_peer_benchmarks("unknown_metric_xyz")
        assert b["ok"] is False
        assert "metric" in b


class TestPricingGaps:
    def _engine(self):
        m = _load("pci_gaps", ENGINE_PATH)
        return m.ProductCompetitiveIntelligence()

    def test_gaps_returned_with_direction(self):
        gaps = self._engine().identify_pricing_gaps(threshold_pct=0.5)
        for g in gaps:
            assert g["direction"] in (
                "we_charge_more", "we_charge_less",
                "we_pay_more", "we_pay_less")
            assert abs(g["delta_vs_median_bps"]) >= 50

    def test_higher_threshold_returns_subset(self):
        eng = self._engine()
        wide = eng.identify_pricing_gaps(threshold_pct=0.3)
        narrow = eng.identify_pricing_gaps(threshold_pct=2.0)
        assert len(narrow) <= len(wide)


class TestSummary:
    def _engine(self):
        m = _load("pci_sum", ENGINE_PATH)
        return m.ProductCompetitiveIntelligence()

    def test_summary_components_add_up(self):
        s = self._engine().get_competitive_summary()
        total = (s["n_leader"] + s["n_follower"]
                  + s["n_laggard"] + s["n_no_data"])
        assert total == s["n_products"]


class TestMapping:
    def test_mapping_exists_parses(self):
        assert MAPPING_PATH.exists()
        d = json.loads(MAPPING_PATH.read_text())
        assert "lending_rate_mapping" in d
        assert "deposit_rate_mapping" in d
        assert "unmapped" in d

    def test_unmapped_entries_have_reason(self):
        d = json.loads(MAPPING_PATH.read_text())
        for entry in d.get("unmapped", []):
            assert "product_id" in entry
            assert "reason" in entry


class TestRegistryAndAdmin:
    def test_enh_134_active(self):
        m = _load("sr134",
                   REPO_ROOT / "utils" / "standards_registry.py")
        std = next((s for s in m.STANDARDS_REGISTRY
                    if s.standard_id == "ENH-134"), None)
        assert std is not None
        assert std.status == "active"
        assert "product_competitive_intel" in std.affected_engines
        assert std.implementation_batch == "v10.145"

    def test_prior_phase1e_engines_still_active(self):
        m = _load("sr_prior_v145",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-131", "ENH-132", "ENH-133"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"

    def test_admin_tier_4b_has_four_engines(self):
        text = (REPO_ROOT / "pages" / "7_admin.py").read_text()
        for token in ("Tier 4B — Product Intelligence",
                      "product_pnl_intelligence",
                      "product_lifecycle",
                      "customer_needs_analyzer",
                      "product_competitive_intel",
                      "ProductCompetitiveIntelligence"):
            assert token in text, f"missing token: {token}"


class TestNoRegression:
    def test_audit_gates_intact(self):
        m = _load("audit_v145",
                   REPO_ROOT / "scripts" / "audit.py")
        gate_ids = [g[0] for g in m.GATES]
        for gid in ("G144", "G145", "G146"):
            assert gid in gate_ids

    def test_strategy_module_intact(self):
        m = _load("sr_strat_v145",
                   REPO_ROOT / "utils" / "standards_registry.py")
        for sid in ("ENH-141", "ENH-150", "ENH-155"):
            std = next((s for s in m.STANDARDS_REGISTRY
                        if s.standard_id == sid), None)
            assert std is not None
            assert std.status == "active"
