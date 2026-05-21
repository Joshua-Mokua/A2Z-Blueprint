"""tests/test_volume_seven_batch.py — Standards #43-#48 (v5.52).

Coverage:
  Standard #43 — Deposit Intelligence
  Standard #44 — Lending Intelligence
  Standard #45 — Channel Income Intelligence
  Standard #46 — Treasury Intelligence
  Standard #47 — Product Profitability (with V3 honesty inheritance)
  Standard #48 — Automated BI / AI Commentary (Cat D scaffolding)

Plus two artifact-handoff harnesses:
  test_deposit_lending_correctness_meets_99_percent → produces deposit_lending_results.json (G47)
  test_product_profitability_correctness_meets_99_percent → produces product_profitability_results.json (G49)
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


# ═══════════════════════════════════════════════════════════════════════
# Standard #43 — Deposit Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard43:
    def test_module_exists(self):
        from utils.deposit_intelligence import DepositIntelligenceEngine
        eng = DepositIntelligenceEngine()
        assert hasattr(eng, "aggregate")
        assert hasattr(eng, "mtd_qtd_ytd")
        assert hasattr(eng, "heatmap_data")

    def test_spec_literal_segments(self):
        from utils.deposit_intelligence import SEGMENTS, PRODUCTS, CURRENCIES
        assert SEGMENTS == ["CORPORATE", "GIB", "MSME", "RETAIL"]
        assert PRODUCTS == ["FD", "CURRENT", "SAVINGS", "CALL"]
        assert CURRENCIES == ["KES", "USD", "GBP", "EUR"]

    def test_aggregate_by_segment(self):
        from utils.deposit_intelligence import DepositIntelligenceEngine
        snapshots = [
            {"balance": 1_000_000, "segment": "CORPORATE", "product": "FD", "currency": "KES"},
            {"balance":   500_000, "segment": "RETAIL",    "product": "SAVINGS", "currency": "KES"},
        ]
        eng = DepositIntelligenceEngine(balance_snapshot_fn=lambda p: snapshots)
        r = eng.aggregate("2026-04", dimensions=("segment",))
        assert r["total"] == 1_500_000.00
        assert r["buckets"]["CORPORATE"] == 1_000_000.00
        assert r["buckets"]["RETAIL"] == 500_000.00

    def test_unknown_dimension_exposed(self):
        from utils.deposit_intelligence import DepositIntelligenceEngine
        snapshots = [
            {"balance": 100_000, "product": "FD", "currency": "KES"}    # missing segment
        ]
        eng = DepositIntelligenceEngine(balance_snapshot_fn=lambda p: snapshots)
        r = eng.aggregate("2026-04", dimensions=("segment", "product"))
        assert r["meta"]["unknown_buckets"] == 1
        assert "UNKNOWN|FD" in r["buckets"]

    def test_kes_billion_precision(self):
        from utils.deposit_intelligence import DepositIntelligenceEngine
        snapshots = [
            {"balance": "11500000000.50", "segment": "CORPORATE", "product": "FD", "currency": "KES"},
            {"balance": "11500000000.51", "segment": "CORPORATE", "product": "FD", "currency": "KES"},
        ]
        eng = DepositIntelligenceEngine(balance_snapshot_fn=lambda p: snapshots)
        r = eng.aggregate("2026-04", dimensions=("segment",))
        assert r["total"] == 23_000_000_001.01

    def test_heatmap_structure(self):
        from utils.deposit_intelligence import DepositIntelligenceEngine
        snapshots = [
            {"balance": 1_000_000, "segment": "CORPORATE", "product": "FD",      "currency": "KES"},
            {"balance":   500_000, "segment": "CORPORATE", "product": "CURRENT", "currency": "KES"},
            {"balance":   300_000, "segment": "RETAIL",    "product": "SAVINGS", "currency": "KES"},
        ]
        eng = DepositIntelligenceEngine(balance_snapshot_fn=lambda p: snapshots)
        r = eng.heatmap_data("2026-04")
        assert "x_axis" in r and "y_axis" in r and "matrix" in r
        assert r["grand_total"] == 1_800_000.00


# ═══════════════════════════════════════════════════════════════════════
# Standard #44 — Lending Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard44:
    def test_module_exists(self):
        from utils.lending_intelligence import LendingIntelligenceEngine
        eng = LendingIntelligenceEngine()
        assert hasattr(eng, "disbursement_by_product")
        assert hasattr(eng, "npl_by_product")
        assert hasattr(eng, "interest_income_breakdown")

    def test_spec_literal_loan_products(self):
        from utils.lending_intelligence import LOAN_PRODUCTS, NPL_DAYS_THRESHOLD
        assert LOAN_PRODUCTS == ["MORTGAGE", "PERSONAL", "BUSINESS", "MOBILE",
                                  "VIRTUAL", "TRADE", "ASSET"]
        assert NPL_DAYS_THRESHOLD == 90

    def test_disbursement_variance_pct(self):
        from utils.lending_intelligence import LendingIntelligenceEngine
        eng = LendingIntelligenceEngine(
            disbursement_lookup_fn=lambda p: [{"amount": 1_000_000, "product": "MORTGAGE"}],
            target_lookup_fn=lambda p: {"MORTGAGE": 1_200_000},
        )
        r = eng.disbursement_by_product("2026-04")
        m = r["products"]["MORTGAGE"]
        assert m["actual"] == 1_000_000.00
        assert m["variance"] == -200_000.00
        assert abs(m["variance_pct"] - (-16.67)) < 0.01

    def test_zero_target_variance_pct_none(self):
        """Rule 1 — undefined ratio when target = 0."""
        from utils.lending_intelligence import LendingIntelligenceEngine
        eng = LendingIntelligenceEngine(
            disbursement_lookup_fn=lambda p: [{"amount": 100, "product": "MORTGAGE"}],
            target_lookup_fn=lambda p: {"MORTGAGE": 0},
        )
        r = eng.disbursement_by_product("2026-04")
        assert r["products"]["MORTGAGE"]["variance_pct"] is None

    def test_npl_ratio_with_data(self):
        from utils.lending_intelligence import LendingIntelligenceEngine
        outstanding = [
            {"outstanding": 1_000_000_000, "product": "MORTGAGE", "days_past_due":  0},
            {"outstanding":   100_000_000, "product": "MORTGAGE", "days_past_due": 95},
        ]
        eng = LendingIntelligenceEngine(outstanding_lookup_fn=lambda d: outstanding)
        r = eng.npl_by_product("2026-04-29")
        m = r["products"]["MORTGAGE"]
        # 100M / 1.1B = 9.0909%
        assert abs(m["npl_ratio"] - 9.0909) < 0.001

    def test_npl_ratio_none_when_no_outstanding(self):
        """Rule 1 — undefined ratio when total outstanding = 0."""
        from utils.lending_intelligence import LendingIntelligenceEngine, LOAN_PRODUCTS
        eng = LendingIntelligenceEngine(outstanding_lookup_fn=lambda d: [])
        r = eng.npl_by_product("2026-04-29")
        assert r["totals"]["npl_ratio"] is None
        for prod in LOAN_PRODUCTS:
            assert r["products"][prod]["npl_ratio"] is None


# ═══════════════════════════════════════════════════════════════════════
# Standard #45 — Channel Income
# ═══════════════════════════════════════════════════════════════════════

class TestStandard45:
    def test_module_exists(self):
        from utils.channel_income import ChannelIncomeEngine
        eng = ChannelIncomeEngine()
        assert hasattr(eng, "income_by_channel")
        assert hasattr(eng, "cost_to_serve")
        assert hasattr(eng, "channel_optimization_recommendations")

    def test_spec_literal_channels(self):
        from utils.channel_income import CHANNELS
        assert CHANNELS == ["BRANCH", "ATM", "MOBILE", "INTERNET", "AGENT", "USSD", "POS"]

    def test_cost_basis_surfaced(self):
        from utils.channel_income import ChannelIncomeEngine
        eng = ChannelIncomeEngine(
            transaction_lookup_fn=lambda p, c: {"count": 1000} if c == "BRANCH" else {},
        )
        r = eng.cost_to_serve("2026-04", "BRANCH")
        assert "cost_basis" in r["meta"]
        assert "cost_basis_doc" in r["meta"]
        # BRANCH default: FTE 80 + infra 15 + processing 5 = 100/txn
        assert r["cost_per_transaction"] == 100.00

    def test_invalid_channel_caught(self):
        from utils.channel_income import ChannelIncomeEngine
        eng = ChannelIncomeEngine()
        r = eng.cost_to_serve("2026-04", "FAX")
        assert "error" in r


# ═══════════════════════════════════════════════════════════════════════
# Standard #46 — Treasury Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard46:
    def test_module_exists(self):
        from utils.treasury_intelligence import TreasuryIntelligenceEngine
        eng = TreasuryIntelligenceEngine()
        assert hasattr(eng, "income_by_instrument")
        assert hasattr(eng, "liquidity_metrics")
        assert hasattr(eng, "alm_dashboard_data")
        assert hasattr(eng, "yield_curve")

    def test_spec_literal_instruments(self):
        from utils.treasury_intelligence import INSTRUMENTS, LCR_MIN_THRESHOLD_PCT, NSFR_MIN_THRESHOLD_PCT
        assert INSTRUMENTS == ["T_BILL", "T_BOND", "FX_SPOT", "FX_FORWARD", "REPO", "INTERBANK"]
        assert int(LCR_MIN_THRESHOLD_PCT) == 100
        assert int(NSFR_MIN_THRESHOLD_PCT) == 100

    def test_lcr_passes_threshold(self):
        from utils.treasury_intelligence import TreasuryIntelligenceEngine
        eng = TreasuryIntelligenceEngine(
            lcr_inputs_fn=lambda d: {"hqla": "5000000000", "net_outflows_30d": "4000000000"},
        )
        r = eng.liquidity_metrics("2026-04-29")
        assert r["lcr"]["lcr_pct"] == 125.00
        assert r["lcr"]["passes_threshold"] is True

    def test_lcr_none_when_no_outflows(self):
        """Rule 1 — undefined ratio when denominator = 0."""
        from utils.treasury_intelligence import TreasuryIntelligenceEngine
        eng = TreasuryIntelligenceEngine(
            lcr_inputs_fn=lambda d: {"hqla": "5000000000", "net_outflows_30d": "0"},
        )
        r = eng.liquidity_metrics("2026-04-29")
        assert r["lcr"]["lcr_pct"] is None
        assert r["lcr"]["passes_threshold"] is None

    def test_alm_buckets(self):
        from utils.treasury_intelligence import TreasuryIntelligenceEngine
        position = {
            "assets_by_bucket":      {"O/N": 1_000_000_000, "1M": 5_000_000_000},
            "liabilities_by_bucket": {"O/N": 2_000_000_000, "1M": 3_000_000_000},
        }
        eng = TreasuryIntelligenceEngine(alm_position_fn=lambda d: position)
        r = eng.alm_dashboard_data("2026-04-29")
        on_bucket = next(b for b in r["buckets"] if b["bucket"] == "O/N")
        assert on_bucket["gap"] == -1_000_000_000.00


# ═══════════════════════════════════════════════════════════════════════
# Standard #47 — Product Profitability (V3 honesty inheritance)
# ═══════════════════════════════════════════════════════════════════════

class TestStandard47:
    def test_module_exists(self):
        from utils.product_profitability import ProductProfitabilityEngine
        eng = ProductProfitabilityEngine()
        assert hasattr(eng, "calculate_product_pnl")
        assert hasattr(eng, "cross_sell_intelligence")
        assert hasattr(eng, "product_lifecycle")

    def test_spec_literal_categories(self):
        from utils.product_profitability import PRODUCT_CATEGORIES
        assert PRODUCT_CATEGORIES == ["LOANS", "DEPOSITS", "TRADE", "TREASURY", "FEES", "DIGITAL"]

    def test_clean_portfolio_no_warning(self):
        """All FTP-on inputs → no warning, not provisional."""
        from utils.product_profitability import ProductProfitabilityEngine
        pnl = [
            {"customer_id": "C1", "total_revenue": 1_000_000, "direct_costs": 200_000,
             "indirect_costs": 100_000, "pbt": 700_000, "transaction_count": 50, "ftp_mode": "on"},
        ]
        eng = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl)
        r = eng.calculate_product_pnl("LOANS", "2026-04")
        assert r["data_quality_warning"] is None
        assert r["provisional"] is False
        assert r["meta"]["upstream_ftp_modes"]["on"] == 1
        assert r["meta"]["upstream_ftp_modes"]["off"] == 0

    def test_warning_cites_standard_11_and_rule_2(self):
        """Mixed FTP → warning must cite Standard #11 + Rule 2 (V3 inheritance)."""
        from utils.product_profitability import ProductProfitabilityEngine
        pnl = [
            {"customer_id": "C1", "total_revenue": 1_000_000, "direct_costs": 200_000,
             "indirect_costs": 100_000, "pbt": 700_000, "transaction_count": 50, "ftp_mode": "on"},
            {"customer_id": "C2", "total_revenue":   500_000, "direct_costs": 100_000,
             "indirect_costs":  50_000, "pbt": 350_000, "transaction_count": 20, "ftp_mode": "off"},
        ]
        eng = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl)
        r = eng.calculate_product_pnl("LOANS", "2026-04")
        assert r["data_quality_warning"] is not None
        assert "Mandatory Standard #11" in r["data_quality_warning"]
        assert "Rule 2" in r["data_quality_warning"]

    def test_provisional_at_50_pct_threshold(self):
        """>50% off-mode → provisional=True (extends V3 portfolio pattern to product dim)."""
        from utils.product_profitability import ProductProfitabilityEngine
        pnl = [
            {"customer_id": "C1", "total_revenue": 1_000_000, "direct_costs": 0, "indirect_costs": 0,
             "pbt": 1_000_000, "transaction_count": 1, "ftp_mode": "off"},
            {"customer_id": "C2", "total_revenue": 1_000_000, "direct_costs": 0, "indirect_costs": 0,
             "pbt": 1_000_000, "transaction_count": 1, "ftp_mode": "off"},
            {"customer_id": "C3", "total_revenue":   500_000, "direct_costs": 0, "indirect_costs": 0,
             "pbt":   500_000, "transaction_count": 1, "ftp_mode": "on"},
        ]
        eng = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl)
        r = eng.calculate_product_pnl("LOANS", "2026-04")
        assert r["provisional"] is True
        assert r["meta"]["ftp_off_share"] > 0.5

    def test_pbt_margin_none_on_zero_revenue(self):
        """Rule 1 — undefined margin on zero revenue."""
        from utils.product_profitability import ProductProfitabilityEngine
        pnl = [
            {"customer_id": "C1", "total_revenue": 0, "direct_costs": 100_000,
             "indirect_costs": 50_000, "pbt": -150_000, "transaction_count": 1, "ftp_mode": "on"},
        ]
        eng = ProductProfitabilityEngine(customer_pnl_lookup_fn=lambda p, per: pnl)
        r = eng.calculate_product_pnl("DIGITAL", "2026-04")
        assert r["pbt_margin"] is None


# ═══════════════════════════════════════════════════════════════════════
# Standard #48 — Automated BI / AI Commentary (Cat D)
# ═══════════════════════════════════════════════════════════════════════

class TestStandard48:
    def test_module_exists(self):
        from utils.business_intelligence import AutomatedBusinessIntelligence
        eng = AutomatedBusinessIntelligence()
        assert hasattr(eng, "generate_commentary")

    def test_no_llm_provider_returns_rule_based(self):
        """Cat D pattern — no LLM provider → basis='rule_based' + fallback_reason."""
        from utils.business_intelligence import AutomatedBusinessIntelligence
        eng = AutomatedBusinessIntelligence()
        r = eng.generate_commentary(
            {"interest_income": 100_000_000},
            "2026-04",
            {"interest_income": 95_000_000},
        )
        assert r["basis"] == "rule_based"
        assert r["meta"]["fallback_reason"] == "no_llm_provider_configured"
        assert r["meta"]["spec_deviation"] is not None

    def test_llm_provider_returns_basis_llm(self):
        """When LLM provider injected, basis='llm', no spec_deviation."""
        from utils.business_intelligence import AutomatedBusinessIntelligence
        eng = AutomatedBusinessIntelligence(
            llm_provider_fn=lambda prompt: "Generated narrative."
        )
        r = eng.generate_commentary({"x": 1}, "2026-04", {"x": 1})
        assert r["basis"] == "llm"
        assert r["meta"]["spec_deviation"] is None

    def test_llm_failure_falls_back_with_explicit_reason(self):
        """LLM error → fall back to rule-based BUT surface the failure reason."""
        from utils.business_intelligence import AutomatedBusinessIntelligence
        def fail(prompt):
            raise ConnectionError("API down")
        eng = AutomatedBusinessIntelligence(llm_provider_fn=fail)
        r = eng.generate_commentary({"x": 100}, "2026-04", {"x": 80})
        assert r["basis"] == "rule_based"
        assert "llm_provider_error" in r["meta"]["fallback_reason"]

    def test_rule_based_is_deterministic(self):
        """Same input → same output (no randomness)."""
        from utils.business_intelligence import AutomatedBusinessIntelligence
        eng = AutomatedBusinessIntelligence()
        m = {"interest_income": 100_000_000}
        p = {"interest_income": 95_000_000}
        r1 = eng.generate_commentary(m, "2026-04", p)
        r2 = eng.generate_commentary(m, "2026-04", p)
        assert r1["commentary"] == r2["commentary"]

    def test_variance_math_matches_spec_example(self):
        """Spec example: ~-2.3% variance on interest income."""
        from utils.business_intelligence import AutomatedBusinessIntelligence
        eng = AutomatedBusinessIntelligence()
        r = eng.generate_commentary(
            {"interest_income": 75_000_000},
            "2026-04-29",
            {"interest_income": 76_780_000},
        )
        v = r["variances"][0]
        assert v["variance"] == -1_780_000.00
        assert abs(v["variance_pct"] - (-2.32)) < 0.01


# ═══════════════════════════════════════════════════════════════════════
# G47 harness — Deposit + Lending aggregation correctness
# ═══════════════════════════════════════════════════════════════════════

def test_deposit_lending_correctness_meets_99_percent():
    """Run all DL fixtures and produce deposit_lending_results.json artifact."""
    from utils.deposit_intelligence import DepositIntelligenceEngine
    from utils.lending_intelligence import LendingIntelligenceEngine

    fixtures_path = FIXTURES_DIR / "deposit_lending_scenarios.json"
    assert fixtures_path.exists(), f"fixtures missing: {fixtures_path}"

    with open(fixtures_path) as f:
        data = json.load(f)
    fixtures = data["fixtures"]

    results = []
    matches = 0
    total = len(fixtures)

    for fx in fixtures:
        engine = fx["engine"]
        method = fx["method"]
        inp = fx["input"]
        exp = fx["expected"]

        if engine == "deposit" and method == "aggregate":
            eng = DepositIntelligenceEngine(
                balance_snapshot_fn=lambda p, snaps=inp["snapshots"]: snaps,
            )
            r = eng.aggregate(inp["period"], dimensions=tuple(inp["dimensions"]))
            ok = (
                r.get("total") == exp["total"]
                and r.get("row_count") == exp["row_count"]
                and r.get("meta", {}).get("unknown_buckets") == exp["unknown_buckets"]
            )
            # Verify each expected bucket
            if ok:
                for k, v in exp.get("buckets", {}).items():
                    if r.get("buckets", {}).get(k) != v:
                        ok = False
                        break

        elif engine == "lending" and method == "disbursement_by_product":
            eng = LendingIntelligenceEngine(
                disbursement_lookup_fn=lambda p, d=inp["disbursements"]: d,
                target_lookup_fn=lambda p, t=inp["targets"]: t,
            )
            r = eng.disbursement_by_product(inp["period"])
            ok = True
            for prod, exp_vals in exp.items():
                if prod == "totals":
                    continue
                actual = r["products"].get(prod, {})
                for field in ("actual", "target", "variance"):
                    if exp_vals.get(field) is not None and actual.get(field) != exp_vals[field]:
                        ok = False
                # variance_pct: handle None and float
                if "variance_pct" in exp_vals:
                    a = actual.get("variance_pct")
                    e = exp_vals["variance_pct"]
                    if e is None:
                        if a is not None:
                            ok = False
                    elif abs((a or 0) - e) > 0.05:
                        ok = False
            if "totals" in exp:
                for field in ("actual", "target", "variance"):
                    if exp["totals"].get(field) is not None and r["totals"].get(field) != exp["totals"][field]:
                        ok = False

        elif engine == "lending" and method == "npl_by_product":
            eng = LendingIntelligenceEngine(
                outstanding_lookup_fn=lambda d, o=inp["outstanding"]: o,
            )
            r = eng.npl_by_product(inp["as_of_date"])
            ok = True
            for prod, exp_vals in exp.items():
                if prod == "totals":
                    actual = r["totals"]
                else:
                    actual = r["products"].get(prod, {})
                for field in ("outstanding", "npl_amount"):
                    if exp_vals.get(field) is not None and actual.get(field) != exp_vals[field]:
                        ok = False
                if "npl_ratio" in exp_vals:
                    a = actual.get("npl_ratio")
                    e = exp_vals["npl_ratio"]
                    if e is None:
                        if a is not None:
                            ok = False
                    elif abs((a or 0) - e) > 0.01:
                        ok = False

        elif engine == "lending" and method == "interest_income_breakdown":
            eng = LendingIntelligenceEngine(
                interest_lookup_fn=lambda p, i=inp["interest"]: i,
            )
            r = eng.interest_income_breakdown(inp["period"])
            ok = (r.get("total_interest_income") == exp["total_interest_income"])
            for prod, exp_vals in exp.items():
                if prod == "total_interest_income":
                    continue
                actual = r["products"].get(prod, {})
                if exp_vals.get("interest_income") is not None and actual.get("interest_income") != exp_vals["interest_income"]:
                    ok = False
                if "share_pct" in exp_vals:
                    a = actual.get("share_pct")
                    e = exp_vals["share_pct"]
                    if e is None:
                        if a is not None:
                            ok = False
                    elif abs((a or 0) - e) > 0.05:
                        ok = False
        else:
            ok = False

        if ok:
            matches += 1
        results.append({
            "id":     fx["id"],
            "label":  fx["label"],
            "engine": engine,
            "method": method,
            "match":  ok,
        })

    match_rate = (matches / total * 100) if total > 0 else 0
    artifact = {
        # _accuracy_gate-compatible fields (matches G18-G42 pattern)
        "total_scenarios":   total,
        "correct":           matches,
        "accuracy_pct":      match_rate,
        "spec_target_pct":   99.0,
        "results":           [
            {"id": r["id"], "label": r["label"],
             "matched": r["match"],
             "diffs": [] if r["match"] else [f"{r['engine']}.{r['method']} mismatch"]}
            for r in results
        ],
        # Also keep the V7-specific fields for diagnostics
        "fixtures_total":    total,
        "fixtures_matched":  matches,
        "match_rate_pct":    match_rate,
    }

    out_path = ROOT / "deposit_lending_results.json"
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2)

    assert match_rate >= 99.0, \
        f"deposit/lending correctness {match_rate:.1f}% < 99%; see {out_path}"


# ═══════════════════════════════════════════════════════════════════════
# G49 harness — Product Profitability with V3 honesty inheritance
# ═══════════════════════════════════════════════════════════════════════

def test_product_profitability_correctness_meets_99_percent():
    """Run all PP fixtures including V3 honesty inheritance verification."""
    from utils.product_profitability import ProductProfitabilityEngine

    fixtures_path = FIXTURES_DIR / "product_profitability_scenarios.json"
    assert fixtures_path.exists(), f"fixtures missing: {fixtures_path}"

    with open(fixtures_path) as f:
        data = json.load(f)
    fixtures = data["fixtures"]

    results = []
    matches = 0
    total = len(fixtures)

    for fx in fixtures:
        inp = fx["input"]
        exp = fx["expected"]
        eng = ProductProfitabilityEngine(
            customer_pnl_lookup_fn=lambda p, per, cp=inp["customer_pnl"]: cp,
        )
        r = eng.calculate_product_pnl(inp["product_code"], inp["period"])

        ok = True
        # Core PnL fields
        for field in ("total_revenue", "direct_costs", "indirect_costs", "pbt"):
            if field in exp and r.get(field) != exp[field]:
                ok = False
        # pbt_margin (None or near-equal)
        if "pbt_margin" in exp:
            a = r.get("pbt_margin")
            e = exp["pbt_margin"]
            if e is None:
                if a is not None:
                    ok = False
            elif a is None or abs(a - e) > 0.01:
                ok = False
        # Honesty inheritance fields
        if "provisional" in exp and r.get("provisional") != exp["provisional"]:
            ok = False
        if "data_quality_warning_present" in exp:
            present = r.get("data_quality_warning") is not None
            if present != exp["data_quality_warning_present"]:
                ok = False
        if "ftp_modes" in exp:
            actual_modes = r["meta"]["upstream_ftp_modes"]
            for k, v in exp["ftp_modes"].items():
                if actual_modes.get(k) != v:
                    ok = False
        if "ftp_off_share" in exp:
            a = r["meta"]["ftp_off_share"]
            if abs(a - exp["ftp_off_share"]) > 0.001:
                ok = False
        # Counts
        if "customer_count" in exp and r.get("customer_count") != exp["customer_count"]:
            ok = False
        if "transaction_count" in exp and r.get("transaction_count") != exp["transaction_count"]:
            ok = False
        # Warning content checks
        if exp.get("warning_mentions_standard_11"):
            if not (r.get("data_quality_warning") and "Mandatory Standard #11" in r["data_quality_warning"]):
                ok = False
        if exp.get("warning_mentions_rule_2"):
            if not (r.get("data_quality_warning") and "Rule 2" in r["data_quality_warning"]):
                ok = False

        if ok:
            matches += 1
        results.append({"id": fx["id"], "label": fx["label"], "match": ok})

    match_rate = (matches / total * 100) if total > 0 else 0
    artifact = {
        # _accuracy_gate-compatible fields
        "total_scenarios":   total,
        "correct":           matches,
        "accuracy_pct":      match_rate,
        "spec_target_pct":   99.0,
        "results":           [
            {"id": r["id"], "label": r["label"],
             "matched": r["match"],
             "diffs": [] if r["match"] else ["product PnL mismatch"]}
            for r in results
        ],
        # V7-specific diagnostics
        "fixtures_total":    total,
        "fixtures_matched":  matches,
        "match_rate_pct":    match_rate,
    }

    out_path = ROOT / "product_profitability_results.json"
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2)

    assert match_rate >= 99.0, \
        f"product profitability correctness {match_rate:.1f}% < 99%; see {out_path}"
