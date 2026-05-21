"""tests/test_liquidity_risk_vocabulary_v10_159.py — v10.159 vocabulary
discovery endpoint + production-readiness verification.

Closes the v10.158 gap: operators couldn't discover which category
strings the engine recognises without reading the source code. This
drop adds a GET /api/treasury/liquidity-risk/vocabulary endpoint
that publishes the full Basel III vocabulary as structured JSON.

Verifies:
- The vocabulary endpoint exists and is JWT-protected
- It publishes all 5 weight tables (HQLA / outflow / inflow / ASF / RSF)
- It publishes thresholds + caps from the engine constants (live, not
  baked-in copies)
- Categories from the published vocabulary actually produce COMPUTED
  ratios when used as request payloads (the production-readiness check)
- Honest design note about CBK-specific extensions being future work
- Audit unchanged at 151/151
"""
from __future__ import annotations
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_PATH = REPO_ROOT / "utils" / "api_treasury.py"
ENGINE_PATH = REPO_ROOT / "utils" / "liquidity_risk.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestVocabularyEndpointShape:
    def test_endpoint_path_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        assert "/liquidity-risk/vocabulary" in text

    def test_endpoint_is_get_not_post(self):
        text = API_PATH.read_text(encoding="utf-8")
        # vocabulary is read-only discovery; should be GET
        assert '@router.get("/liquidity-risk/vocabulary")' in text, (
            "vocabulary should be GET (read-only discovery), not POST")

    def test_endpoint_jwt_protected(self):
        text = API_PATH.read_text(encoding="utf-8")
        # Find the vocabulary endpoint body
        idx = text.find('@router.get("/liquidity-risk/vocabulary")')
        assert idx > -1
        block = text[idx:idx + 5000]
        # Truncate at next decorator
        next_dec = re.search(r'@router\.', block[40:])
        if next_dec:
            block = block[:next_dec.start() + 40]
        assert "Depends(get_current_user)" in block, (
            "vocabulary endpoint must be JWT-protected")


class TestVocabularyContent:
    """The endpoint must publish every category and weight that the
    engine recognises — not a stale documentation snapshot, the live
    constants from utils/liquidity_risk.py at request time."""

    def test_publishes_all_5_tables(self):
        text = API_PATH.read_text(encoding="utf-8")
        # The endpoint must reference every weight table from the engine
        for table in ("HQLA_HAIRCUT_PCT", "OUTFLOW_RATES_PCT",
                      "INFLOW_RATES_PCT", "ASF_FACTORS_PCT",
                      "RSF_FACTORS_PCT"):
            assert table in text, (
                f"vocabulary endpoint must reference {table}")

    def test_publishes_thresholds(self):
        text = API_PATH.read_text(encoding="utf-8")
        for const in ("LCR_MIN_PCT", "NSFR_MIN_PCT",
                      "LEVEL_2_TOTAL_CAP_PCT", "LEVEL_2B_CAP_PCT",
                      "INFLOW_CAP_PCT_OF_OUTFLOWS"):
            assert const in text, (
                f"vocabulary endpoint must expose {const}")

    def test_lists_endpoint_field_for_each_table(self):
        # Each section should tell the operator which Pydantic model
        # field uses these category strings — not just dump the
        # vocabulary, link it to the request shape
        text = API_PATH.read_text(encoding="utf-8")
        # Find the vocabulary function
        m = re.search(r"def liquidity_risk_vocabulary"
                       r"[\s\S]*?(?=\n    @|\nelse:)",
                       text)
        assert m, "vocabulary function not found"
        block = m.group(0)
        # Should have 'endpoint_field' references mapping vocabulary
        # back to Pydantic model field names
        assert block.count("endpoint_field") >= 5, (
            "vocabulary should map each table back to its Pydantic "
            "request field — found "
            f"{block.count('endpoint_field')} occurrences, expected >=5")

    def test_includes_honest_design_note_about_cbk(self):
        text = API_PATH.read_text(encoding="utf-8")
        m = re.search(r"def liquidity_risk_vocabulary"
                       r"[\s\S]*?(?=\n    @|\nelse:)",
                       text)
        assert m
        block = m.group(0)
        # Must honestly note that CBK-specific categories are future work
        assert "CBK" in block or "Kenya-specific" in block, (
            "vocabulary should honestly note CBK-specific category "
            "extensions are future work (regulatory review needed)")


class TestProductionReadinessLCR:
    """The point of v10.159 is to make v10.158 endpoints production-
    ready. These tests verify that with categories from the published
    vocabulary, real LCR computations produce real ratios — not
    NO_DATA."""

    def test_lcr_with_basel_categories_returns_computed_ratio(self):
        from decimal import Decimal as _Dec
        from utils.liquidity_risk import (LiquidityRiskEngine,
                                            HqlaHolding, CashFlowItem,
                                            OUTFLOW_RATES_PCT,
                                            INFLOW_RATES_PCT)

        # Build a realistic Ecobank Kenya snapshot using ENGINE'S
        # ACTUAL VOCABULARY (the categories v10.159 publishes)
        hqla = [
            HqlaHolding(asset_id="GOK_BILLS",
                          level="LEVEL_1",
                          market_value_kes=_Dec("10000000000")),
            HqlaHolding(asset_id="GOK_BONDS",
                          level="LEVEL_2A",
                          market_value_kes=_Dec("5000000000")),
        ]
        flows = [
            CashFlowItem(item_id="O1",
                            category="RETAIL_DEPOSITS_STABLE",
                            direction="OUTFLOW",
                            balance_kes=_Dec("50000000000")),
            CashFlowItem(item_id="O2",
                            category="CORPORATE_NON_FINANCIAL",
                            direction="OUTFLOW",
                            balance_kes=_Dec("10000000000")),
            CashFlowItem(item_id="I1",
                            category="RETAIL_LOAN_INFLOWS",
                            direction="INFLOW",
                            balance_kes=_Dec("8000000000")),
        ]
        result = LiquidityRiskEngine.lcr(hqla_holdings=hqla,
                                            cash_flows=flows)

        # With real categories, status should be GREEN/AMBER/RED, NOT NO_DATA
        assert result["status"] != "NO_DATA", (
            f"expected real LCR computation; got NO_DATA: {result}")
        assert result["lcr_pct"] is not None, (
            f"lcr_pct should not be None when categories are valid")

        # Also verify the categories used are in the published vocabulary
        for cf in flows:
            if cf.direction == "OUTFLOW":
                assert cf.category in OUTFLOW_RATES_PCT, (
                    f"test data uses category {cf.category} not in "
                    f"engine vocabulary")
            else:
                assert cf.category in INFLOW_RATES_PCT


class TestProductionReadinessNSFR:
    def test_nsfr_with_basel_categories_returns_computed_ratio(self):
        from decimal import Decimal as _Dec
        from utils.liquidity_risk import (LiquidityRiskEngine,
                                            FundingItem, AssetItem,
                                            ASF_FACTORS_PCT,
                                            RSF_FACTORS_PCT)

        funding = [
            FundingItem(item_id="F1", category="TIER_1_CAPITAL",
                          balance_kes=_Dec("15000000000")),
            FundingItem(item_id="F2",
                          category="RETAIL_DEPOSITS_LT_1Y",
                          balance_kes=_Dec("80000000000")),
        ]
        assets = [
            AssetItem(item_id="A1", category="CASH",
                          balance_kes=_Dec("5000000000")),
            AssetItem(item_id="A2",
                          category="RETAIL_LOANS_GTE_1Y",
                          balance_kes=_Dec("60000000000")),
            AssetItem(item_id="A3", category="MORTGAGE_LOANS",
                          balance_kes=_Dec("12000000000")),
        ]
        result = LiquidityRiskEngine.nsfr(funding=funding,
                                              assets=assets)

        assert result["status"] != "NO_DATA", (
            f"expected real NSFR computation; got NO_DATA: {result}")
        assert result["nsfr_pct"] is not None
        # Verify categories used are in published vocabulary
        for fi in funding:
            assert fi.category in ASF_FACTORS_PCT
        for ai in assets:
            assert ai.category in RSF_FACTORS_PCT


class TestVocabularyMatchesEngine:
    """The vocabulary endpoint imports live constants from
    utils/liquidity_risk.py — if those constants change, the
    vocabulary should reflect the new values without code change
    in api_treasury.py."""

    def test_engine_has_expected_minimum_categories(self):
        # Verify engine has at least the Basel III standard set
        from utils.liquidity_risk import (
            HQLA_HAIRCUT_PCT, OUTFLOW_RATES_PCT, INFLOW_RATES_PCT,
            ASF_FACTORS_PCT, RSF_FACTORS_PCT)
        # 3 HQLA levels (1, 2A, 2B)
        assert len(HQLA_HAIRCUT_PCT) >= 3
        # At least 5 outflow categories
        assert len(OUTFLOW_RATES_PCT) >= 5
        # At least 3 inflow categories
        assert len(INFLOW_RATES_PCT) >= 3
        # At least 4 ASF categories
        assert len(ASF_FACTORS_PCT) >= 4
        # At least 6 RSF categories
        assert len(RSF_FACTORS_PCT) >= 6

    def test_endpoint_imports_constants_from_engine(self):
        # The endpoint must import from utils.liquidity_risk, not
        # hardcode the values
        text = API_PATH.read_text(encoding="utf-8")
        m = re.search(r"def liquidity_risk_vocabulary"
                       r"[\s\S]*?(?=\n    @|\nelse:)",
                       text)
        assert m
        block = m.group(0)
        assert "from utils.liquidity_risk import" in block, (
            "vocabulary endpoint must import constants from engine "
            "(live values), not hardcode them in api_treasury.py")


class TestNoRegression:
    def test_all_closure_gates_still_pass(self):
        m = _load("audit_intact_v159", AUDIT_PATH)
        for gate in (m.gate_treasury_module_closed,
                      m.gate_treasury_arc_ui_integrated,
                      m.gate_cockpits_registered_in_app,
                      m.gate_product_module_closed,
                      m.gate_product_arc_ui_integrated):
            result = gate()
            assert result["passed"] is True, (
                f"{gate.__name__} regressed")

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v159", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_158_endpoints_still_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in ("/liquidity-risk/lcr",
                      "/liquidity-risk/nsfr",
                      "/liquidity-risk/hqla-value"):
            assert path in text, f"v10.158 {path} regressed"

    def test_audit_treasury_still_correct(self):
        text = API_PATH.read_text(encoding="utf-8")
        idx = text.find("def _audit_treasury(")
        block = text[idx:idx + 600]
        assert "username=" in block
        assert "actor=" not in block
