"""tests/test_rm_profitability.py — Standard #23 tests (v5.48).

Two test groups:

  1. Unit tests pinning the engine's contract:
       - calculate_rm_portfolio_pnl returns spec-mandated keys
       - Aggregation correctness (sum of customer PBTs, weighted margin)
       - Honesty inheritance from Mandatory Standard #11:
           * FTP-off customer in portfolio → warning surfaced
           * >50% FTP-off → provisional flag set
           * Mixed FTP across RMs → peer caveat surfaces
       - Defensive contract (unknown RM, empty period, no customers)
       - Decimal precision at KES-billion-scale aggregation
       - Determinism (same inputs → same output)
       - get_rm_rank as standalone spec method
       - Tie-breaking (lex on rm_code)
       - Persistence helpers

  2. Aggregation correctness harness:
       - test_aggregation_correctness_meets_99_percent runs every
         fixture in tests/fixtures/rm_portfolio_scenarios.json.
         Asserts ≥99% match across PBT, revenue, margin, provisional
         flag, FTP counts, warning presence. Writes
         rm_aggregation_results.json for G34.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "rm_portfolio_scenarios.json"
RESULTS_FILE = ROOT / "rm_aggregation_results.json"


class TestStandard23Files:
    def test_engine_module_exists(self):
        assert (ROOT / "utils" / "rm_profitability.py").exists()

    def test_fixtures_exist(self):
        assert FIXTURES.exists()
        assert len(json.loads(FIXTURES.read_text())) >= 10


def _mk_pnl(pbt, margin=None, revenue=100000, ftp_mode="on", direct=0, indirect=0):
    return {
        "pbt":             float(pbt),
        "pbt_margin":      margin,
        "total_revenue":   float(revenue),
        "total_direct_costs":   float(direct),
        "total_indirect_costs": float(indirect),
        "meta": {"ftp_mode": ftp_mode, "balance_basis": "average"},
    }


@pytest.fixture
def basic_engine():
    from utils.rm_profitability import RMProfitabilityDashboard

    rms = {
        "RM001": {"staff_code": "RM001", "full_name": "Alice", "active": True, "role": "RM Corporate"},
        "RM002": {"staff_code": "RM002", "full_name": "Bob",   "active": True, "role": "RM Corporate"},
        "RM003": {"staff_code": "RM003", "full_name": "Cathy", "active": True, "role": "RM SME"},
    }
    rm_customers = {
        "RM001": ["C100", "C101", "C102"],
        "RM002": ["C200", "C201"],
        "RM003": [],
    }
    pnls = {
        ("C100", "2026-04"): _mk_pnl(500000, 0.50, 1000000, direct=400000, indirect=100000),
        ("C101", "2026-04"): _mk_pnl(300000, 0.30, 1000000, direct=600000, indirect=100000),
        ("C102", "2026-04"): _mk_pnl(200000, 0.20, 1000000, direct=700000, indirect=100000),
        ("C200", "2026-04"): _mk_pnl(800000, 0.40, 2000000, direct=1100000, indirect=100000),
        ("C201", "2026-04"): _mk_pnl(100000, 0.10, 1000000, direct=800000, indirect=100000),
    }
    return RMProfitabilityDashboard(
        rm_customer_lookup_fn=lambda rm: rm_customers.get(rm, []),
        customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
        all_rms_fn=            lambda: list(rms.keys()),
        rm_lookup_fn=          lambda rm: rms.get(rm),
    )


# ═══════════════════════════════════════════════════════════════════════
# Spec contract
# ═══════════════════════════════════════════════════════════════════════

class TestSpecContract:
    def test_returns_portfolio_pnl(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert "portfolio_pnl" in r

    def test_returns_peer_comparison_with_rank(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert "peer_comparison" in r
        assert "rank" in r["peer_comparison"]

    def test_get_rm_customers_returns_list(self, basic_engine):
        c = basic_engine.get_rm_customers("RM001")
        assert isinstance(c, list)
        assert len(c) == 3

    def test_get_rm_rank_method(self, basic_engine):
        # RM001 PBT 1M > RM002 PBT 900k > RM003 PBT 0
        assert basic_engine.get_rm_rank("RM001", "2026-04") == 1
        assert basic_engine.get_rm_rank("RM002", "2026-04") == 2
        assert basic_engine.get_rm_rank("RM003", "2026-04") == 3


# ═══════════════════════════════════════════════════════════════════════
# Aggregation math
# ═══════════════════════════════════════════════════════════════════════

class TestAggregation:
    def test_pbt_sum_correct(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        # 500k + 300k + 200k = 1M
        assert r["portfolio_pnl"]["total_pbt"] == 1000000.00

    def test_revenue_sum_correct(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["total_revenue"] == 3000000.00

    def test_direct_costs_sum_correct(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["total_direct_costs"] == 1700000.00

    def test_indirect_costs_sum_correct(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["total_indirect_costs"] == 300000.00

    def test_portfolio_margin_revenue_weighted(self, basic_engine):
        """Margin is total_pbt / total_revenue, NOT mean of margins."""
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        # 1M / 3M = 0.3333
        assert abs(r["portfolio_pnl"]["portfolio_margin"] - 0.3333) < 0.0001

    def test_customer_count(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["customer_count"] == 3


# ═══════════════════════════════════════════════════════════════════════
# Peer ranking
# ═══════════════════════════════════════════════════════════════════════

class TestPeerRanking:
    def test_top_rm_is_rank_1(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["peer_comparison"]["rank"] == 1

    def test_second_rm_is_rank_2(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM002", "2026-04")
        assert r["peer_comparison"]["rank"] == 2

    def test_total_rms_ranked(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["peer_comparison"]["total_rms_ranked"] == 3

    def test_secondary_rank_metrics_present(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert "rank_by_pbt_per_customer" in r["peer_comparison"]
        assert "rank_by_margin" in r["peer_comparison"]

    def test_tie_break_lexicographic(self):
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {
            "RM001": {"staff_code": "RM001", "full_name": "A", "active": True, "role": "RM"},
            "RM002": {"staff_code": "RM002", "full_name": "B", "active": True, "role": "RM"},
        }
        pnls = {
            ("CA", "2026-04"): _mk_pnl(500000, 0.50, 1000000),
            ("CB", "2026-04"): _mk_pnl(500000, 0.50, 1000000),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: {"RM001": ["CA"], "RM002": ["CB"]}.get(rm, []),
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001", "RM002"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r1 = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        r2 = eng.calculate_rm_portfolio_pnl("RM002", "2026-04")
        # Ties broken lex on rm_code → RM001 first
        assert r1["peer_comparison"]["rank"] == 1
        assert r2["peer_comparison"]["rank"] == 2


# ═══════════════════════════════════════════════════════════════════════
# Honesty inheritance from Mandatory Standard #11
# ═══════════════════════════════════════════════════════════════════════

class TestHonestyInheritance:
    def test_ftp_off_customer_surfaces_warning(self):
        """1 FTP-off customer in portfolio → data_quality_warning surfaces."""
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        pnls = {
            ("C1", "2026-04"): _mk_pnl(-6500, -3.25, 2000, ftp_mode="off"),
            ("C2", "2026-04"): _mk_pnl(100000, 0.20, 500000, ftp_mode="on"),
            ("C3", "2026-04"): _mk_pnl(200000, 0.40, 500000, ftp_mode="on"),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C1", "C2", "C3"],
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["data_quality_warning"] is not None
        assert "Mandatory Standard #11" in r["data_quality_warning"]

    def test_ftp_modes_counted_in_meta(self):
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        pnls = {
            ("C1", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="off"),
            ("C2", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="on"),
            ("C3", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="on"),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C1", "C2", "C3"],
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        modes = r["meta"]["upstream_ftp_modes"]
        assert modes["off"] == 1
        assert modes["on"] == 2

    def test_majority_ftp_off_provisional_true(self):
        """>50% FTP-off → portfolio.provisional = True."""
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        pnls = {
            ("C1", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="off"),
            ("C2", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="off"),
            ("C3", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="on"),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C1", "C2", "C3"],
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["provisional"] is True

    def test_exact_50_percent_not_provisional(self):
        """The threshold is >50%, so exactly 50% stays not-provisional."""
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        pnls = {
            ("C1", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="off"),
            ("C2", "2026-04"): _mk_pnl(100, 0.1, 1000, ftp_mode="on"),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C1", "C2"],
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["provisional"] is False

    def test_all_ftp_on_no_warning(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        # All FTP-on, has customers → no warning
        assert r["data_quality_warning"] is None

    def test_mixed_ftp_across_rms_caveat(self):
        """RM-level mixed FTP across RMs → peer comparison caveat surfaces."""
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {
            "RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"},
            "RM002": {"staff_code": "RM002", "full_name": "Y", "active": True, "role": "RM"},
        }
        pnls = {
            ("CA", "2026-04"): _mk_pnl(100000, 0.20, 500000, ftp_mode="on"),
            ("CB", "2026-04"): _mk_pnl(100, 0.10, 1000, ftp_mode="off"),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: {"RM001": ["CA"], "RM002": ["CB"]}.get(rm, []),
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001", "RM002"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r1 = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        # The caveat should surface for the FTP-on RM about the FTP-off peer
        caveats = r1["meta"]["peer_comparison_caveats"]
        assert any("Mandatory Standard #11" in c for c in caveats)


# ═══════════════════════════════════════════════════════════════════════
# Defensive contract
# ═══════════════════════════════════════════════════════════════════════

class TestDefensiveContract:
    def test_unknown_rm_returns_empty(self, basic_engine):
        assert basic_engine.calculate_rm_portfolio_pnl("UNKNOWN", "2026-04") == {}

    def test_empty_rm_code_returns_empty(self, basic_engine):
        assert basic_engine.calculate_rm_portfolio_pnl("", "2026-04") == {}

    def test_empty_period_returns_empty(self, basic_engine):
        assert basic_engine.calculate_rm_portfolio_pnl("RM001", "") == {}

    def test_rm_with_no_customers_warning(self, basic_engine):
        r = basic_engine.calculate_rm_portfolio_pnl("RM003", "2026-04")
        assert r["portfolio_pnl"]["customer_count"] == 0
        assert r["portfolio_pnl"]["total_pbt"] == 0.0
        assert r["data_quality_warning"] == "RM has no assigned customers"

    def test_all_pnls_missing_warning(self):
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C_GHOST_1", "C_GHOST_2"],
            customer_pnl_fn=       lambda c, p: None,
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["total_pbt"] == 0.0
        assert "All customer PnLs unavailable" in r["data_quality_warning"]
        assert r["meta"]["unavailable_count"] == 2

    def test_zero_revenue_portfolio_margin_none(self):
        """If aggregate revenue is 0, portfolio_margin is None (not 0, not inf)."""
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        pnls = {("C1", "2026-04"): _mk_pnl(-100, None, 0, ftp_mode="on")}
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C1"],
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["portfolio_margin"] is None
        assert r["portfolio_pnl"]["customers_unclassified"] == 1


# ═══════════════════════════════════════════════════════════════════════
# Decimal precision
# ═══════════════════════════════════════════════════════════════════════

class TestDecimalPrecision:
    def test_kes_billion_scale_aggregation(self):
        from utils.rm_profitability import RMProfitabilityDashboard
        rms = {"RM001": {"staff_code": "RM001", "full_name": "X", "active": True, "role": "RM"}}
        pnls = {
            ("C1", "2026-04"): _mk_pnl(1500000000, 0.30, 5000000000, direct=3000000000, indirect=500000000),
            ("C2", "2026-04"): _mk_pnl(2200000000, 0.40, 5500000000, direct=2800000000, indirect=500000000),
        }
        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=lambda rm: ["C1", "C2"],
            customer_pnl_fn=       lambda c, p: pnls.get((c, p)),
            all_rms_fn=            lambda: ["RM001"],
            rm_lookup_fn=          lambda rm: rms.get(rm),
        )
        r = eng.calculate_rm_portfolio_pnl("RM001", "2026-04")
        assert r["portfolio_pnl"]["total_pbt"] == 3700000000.00
        assert r["portfolio_pnl"]["total_revenue"] == 10500000000.00


# ═══════════════════════════════════════════════════════════════════════
# Determinism
# ═══════════════════════════════════════════════════════════════════════

class TestDeterminism:
    def test_two_runs_produce_same_output(self, basic_engine):
        p1 = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        p2 = basic_engine.calculate_rm_portfolio_pnl("RM001", "2026-04")
        def strip(d):
            if isinstance(d, dict):
                return {k: strip(v) for k, v in d.items() if k not in ("generated_at",)}
            if isinstance(d, list): return [strip(x) for x in d]
            return d
        assert strip(p1) == strip(p2)


# ═══════════════════════════════════════════════════════════════════════
# Persistence
# ═══════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_save_and_get(self, tmp_path, monkeypatch):
        from utils import rm_profitability as rm
        monkeypatch.setattr(rm, "RM_PORTFOLIOS_FILE", tmp_path / "rm.json")
        snap = {"portfolio_pnl": {"rm_code": "RM001", "total_pbt": 1000000}}
        ok = rm.save_portfolio("RM001", "2026-04", snap)
        assert ok is True
        got = rm.get_portfolio("RM001", "2026-04")
        assert got and got["portfolio_pnl"]["total_pbt"] == 1000000

    def test_save_empty_returns_false(self, tmp_path, monkeypatch):
        from utils import rm_profitability as rm
        monkeypatch.setattr(rm, "RM_PORTFOLIOS_FILE", tmp_path / "rm.json")
        assert rm.save_portfolio("RM001", "2026-04", {}) is False
        assert rm.save_portfolio("", "2026-04", {"x": 1}) is False
        assert rm.save_portfolio("RM001", "", {"x": 1}) is False


# ═══════════════════════════════════════════════════════════════════════
# Aggregation correctness harness — Standard #23 spec verification
# ═══════════════════════════════════════════════════════════════════════

def test_aggregation_correctness_meets_99_percent():
    """Run every fixture; assert ≥99% match; write G34 artifact."""
    from utils.rm_profitability import RMProfitabilityDashboard

    scenarios = json.loads(FIXTURES.read_text())
    assert len(scenarios) >= 10

    correct = 0
    results = []
    for s in scenarios:
        inp = s["input"]
        rm_code = inp["rm_code"]

        def _customers(rm, _c=inp["customers"], _r=rm_code):
            return _c if rm == _r else []

        def _pnl(c, p, _pnls=inp["pnls"]):
            return _pnls.get(c)

        eng = RMProfitabilityDashboard(
            rm_customer_lookup_fn=_customers,
            customer_pnl_fn=       _pnl,
            all_rms_fn=            lambda r=rm_code: [r],
            rm_lookup_fn=          lambda rm, r=rm_code: (
                {"staff_code": rm, "full_name": "Test", "active": True}
                if rm == r else None
            ),
        )
        r = eng.calculate_rm_portfolio_pnl(rm_code, "2026-04")
        expected = s["expected"]
        pf = r["portfolio_pnl"]

        issues = []
        # Customer count
        if "customer_count" in expected:
            if pf["customer_count"] != expected["customer_count"]:
                issues.append(f"customer_count: {pf['customer_count']} ≠ {expected['customer_count']}")

        # Money fields (within 0.5%)
        for field in ("total_revenue", "total_direct_costs", "total_indirect_costs", "total_pbt"):
            if field not in expected:
                continue
            actual = pf.get(field, 0)
            ev = expected[field]
            if ev == 0:
                if abs(actual - ev) > 0.01:
                    issues.append(f"{field}: {actual} ≠ {ev}")
            else:
                if abs(actual - ev) / abs(ev) > 0.005:
                    issues.append(f"{field}: {actual} not within 0.5% of {ev}")

        # Margin (within 0.001)
        if "portfolio_margin" in expected:
            ev = expected["portfolio_margin"]
            actual = pf.get("portfolio_margin")
            if ev is None:
                if actual is not None:
                    issues.append(f"margin: expected None, got {actual}")
            else:
                if actual is None or abs(actual - ev) > 0.001:
                    issues.append(f"margin: {actual} not within 0.001 of {ev}")

        # Provisional flag
        if "provisional" in expected:
            if pf["provisional"] != expected["provisional"]:
                issues.append(f"provisional: {pf['provisional']} ≠ {expected['provisional']}")

        # customers_unclassified
        if "customers_unclassified" in expected:
            if pf["customers_unclassified"] != expected["customers_unclassified"]:
                issues.append(
                    f"customers_unclassified: {pf['customers_unclassified']} "
                    f"≠ {expected['customers_unclassified']}"
                )

        # Warning presence
        if "warning_present" in expected:
            has = bool(r.get("data_quality_warning"))
            if has != expected["warning_present"]:
                issues.append(f"warning_present: {has} ≠ {expected['warning_present']}")
            elif expected["warning_present"] and "warning_contains" in expected:
                if expected["warning_contains"] not in (r.get("data_quality_warning") or ""):
                    issues.append(f"warning missing '{expected['warning_contains']}'")

        # FTP counts
        modes = r["meta"]["upstream_ftp_modes"]
        if "ftp_off_count" in expected:
            if modes.get("off", 0) != expected["ftp_off_count"]:
                issues.append(f"ftp_off: {modes.get('off', 0)} ≠ {expected['ftp_off_count']}")
        if "ftp_on_count" in expected:
            if modes.get("on", 0) != expected["ftp_on_count"]:
                issues.append(f"ftp_on: {modes.get('on', 0)} ≠ {expected['ftp_on_count']}")
        if "unavailable_count" in expected:
            if r["meta"]["unavailable_count"] != expected["unavailable_count"]:
                issues.append(
                    f"unavailable: {r['meta']['unavailable_count']} ≠ {expected['unavailable_count']}"
                )

        match = len(issues) == 0
        if match:
            correct += 1

        results.append({
            "id":     s["id"],
            "matched": match,
            "issues": issues,
            "actual_pbt":     pf.get("total_pbt"),
            "expected_pbt":   expected.get("total_pbt"),
            "actual_provisional": pf.get("provisional"),
            "expected_provisional": expected.get("provisional"),
            "warning_present": bool(r.get("data_quality_warning")),
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
        f"Aggregation correctness {accuracy:.1f}% < 99%; failures:\n"
        + "\n".join(
            f"  {r['id']}: {r['issues']}"
            for r in results if not r["matched"]
        )
    )
