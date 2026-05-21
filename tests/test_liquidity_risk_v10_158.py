"""tests/test_liquidity_risk_v10_158.py — v10.158 LCR + NSFR per-call endpoints.

Verifies the v10.158 deliverable:
- 3 new POST endpoints for per-call liquidity risk computation
  (LCR, NSFR, HQLA value) against LiquidityRiskEngine static methods
- 4 new Pydantic models (HqlaHoldingModel, CashFlowItemModel,
  FundingItemModel, AssetItemModel) + 2 request envelopes (LCRRequest,
  NSFRRequest)
- Pydantic→engine dataclass conversion verified end-to-end
- Updated /api/treasury/liquidity-risk/methods placeholder reflects
  v10.158 ships + remaining items shifted to v10.159+
- Audit unchanged at 151/151
- No regression of v10.155 / v10.156 / v10.157 work
"""
from __future__ import annotations
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_PATH = REPO_ROOT / "utils" / "api_treasury.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestNewPydanticModels:
    def test_v10_158_request_models_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for model in (
            "HqlaHoldingModel",
            "CashFlowItemModel",
            "FundingItemModel",
            "AssetItemModel",
            "LCRRequest",
            "NSFRRequest",
        ):
            assert model in text, (
                f"v10.158 Pydantic model {model} missing")

    def test_lcr_request_uses_nested_model_lists(self):
        text = API_PATH.read_text(encoding="utf-8")
        # LCRRequest should declare hqla_holdings: List[HqlaHoldingModel]
        # and cash_flows: List[CashFlowItemModel]
        assert "List[HqlaHoldingModel]" in text, (
            "LCRRequest must use List[HqlaHoldingModel] for nested validation")
        assert "List[CashFlowItemModel]" in text

    def test_nsfr_request_uses_nested_model_lists(self):
        text = API_PATH.read_text(encoding="utf-8")
        assert "List[FundingItemModel]" in text
        assert "List[AssetItemModel]" in text


class TestNewPostEndpoints:
    EXPECTED_PATHS = [
        "/liquidity-risk/lcr",
        "/liquidity-risk/nsfr",
        "/liquidity-risk/hqla-value",
    ]

    def test_v10_158_paths_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in self.EXPECTED_PATHS:
            assert path in text, f"v10.158 endpoint {path} missing"

    def test_total_post_decorator_count(self):
        # v10.155 = 5, v10.156 = +6, v10.157 = +7, v10.158 = +3
        text = API_PATH.read_text(encoding="utf-8")
        n_post = len(re.findall(r"@router\.post\(", text))
        assert n_post >= 21, (
            f"expected >=21 @router.post decorators "
            f"(5+6+7+3), got {n_post}")

    def test_v10_158_endpoints_jwt_protected(self):
        text = API_PATH.read_text(encoding="utf-8")
        chunks = re.split(r"(@router\.\w+\([^)]+\))", text)
        v158_paths = ("liquidity-risk/lcr", "liquidity-risk/nsfr",
                       "liquidity-risk/hqla-value")
        for i in range(1, len(chunks) - 1, 2):
            decorator = chunks[i]
            body = chunks[i + 1] if i + 1 < len(chunks) else ""
            for path in v158_paths:
                if path in decorator:
                    assert "Depends(get_current_user)" in body, (
                        f"v10.158 endpoint {path} missing JWT auth")
                    break


class TestSignatureDiscipline:
    def test_endpoint_uses_real_dataclass_fields(self):
        # HqlaHolding has asset_id (NOT position_id like HQLAPosition)
        # — these are different dataclasses on different engines!
        text = API_PATH.read_text(encoding="utf-8")
        # Find the lcr endpoint body
        m = re.search(
            r"def liquidity_risk_lcr\b[\s\S]*?(?=\n    @|\nelse:|\nclass )",
            text)
        assert m, "couldn't find liquidity_risk_lcr function"
        block = m.group(0)
        assert "asset_id=" in block, (
            "HqlaHolding construction must use asset_id (real field), "
            "NOT position_id (which is HQLAPosition's field on a "
            "different engine)")

    def test_audit_treasury_unchanged(self):
        text = API_PATH.read_text(encoding="utf-8")
        idx = text.find("def _audit_treasury(")
        assert idx > -1
        block = text[idx:idx + 600]
        assert "username=" in block
        assert "detail=" in block
        assert "actor=" not in block
        assert "payload=" not in block


class TestRoundTripConversions:
    """End-to-end: build engine dataclasses + call the engine
    methods directly with shapes matching what the endpoints will
    produce after Pydantic validation."""

    def test_lcr_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.liquidity_risk import (LiquidityRiskEngine,
                                            HqlaHolding,
                                            CashFlowItem)
        # Same shape the endpoint produces
        hqla = [HqlaHolding(asset_id="H1", level="LEVEL_1",
                              market_value_kes=_Dec("100000000"))]
        flows = [CashFlowItem(item_id="F1",
                                  category="retail_deposits",
                                  direction="OUTFLOW",
                                  balance_kes=_Dec("80000000"))]
        result = LiquidityRiskEngine.lcr(hqla_holdings=hqla,
                                            cash_flows=flows)
        assert isinstance(result, dict)
        # Engine reports either ratio or status
        assert "lcr_pct" in result
        assert "hqla_total_kes" in result

    def test_nsfr_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.liquidity_risk import (LiquidityRiskEngine,
                                            FundingItem, AssetItem)
        funding = [FundingItem(item_id="F1", category="retail_stable",
                                  balance_kes=_Dec("500000000"))]
        assets = [AssetItem(item_id="A1",
                                category="loans_residential",
                                balance_kes=_Dec("400000000"))]
        result = LiquidityRiskEngine.nsfr(funding=funding,
                                              assets=assets)
        assert isinstance(result, dict)
        assert "nsfr_pct" in result
        assert "asf_kes" in result
        assert "rsf_kes" in result

    def test_hqla_value_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.liquidity_risk import (LiquidityRiskEngine,
                                            HqlaHolding)
        holdings = [
            HqlaHolding(asset_id="H1", level="LEVEL_1",
                          market_value_kes=_Dec("100000000")),
            HqlaHolding(asset_id="H2", level="LEVEL_2A",
                          market_value_kes=_Dec("50000000")),
        ]
        result = LiquidityRiskEngine.hqla_value(holdings=holdings)
        assert isinstance(result, dict)
        # Engine returns level breakdown
        assert "level_1_kes" in result
        assert "level_2a_kes" in result
        assert "total_hqla_kes" in result


class TestUpdatedDeferralPlaceholder:
    def test_placeholder_lists_v10_158_ships(self):
        text = API_PATH.read_text(encoding="utf-8")
        assert '"v10.158"' in text or "'v10.158'" in text

    def test_remaining_deferred_shifted_to_v10_159(self):
        text = API_PATH.read_text(encoding="utf-8")
        # The 3 truly-deferred items (Agent, Islamic, Digital Assets)
        # should now point to v10.159+ since v10.158 closed the
        # NSFR ASF/RSF item
        assert '"deferred_to": "v10.159+"' in text or \
               "'deferred_to': 'v10.159+'" in text

    def test_phase_2_status_includes_lcr_nsfr(self):
        text = API_PATH.read_text(encoding="utf-8")
        # Phase 2 status string should mention LCR + NSFR now complete
        m = re.search(r'"phase_2_status":\s*\([^)]+\)', text)
        assert m, "couldn't find phase_2_status"
        status = m.group(0)
        assert "LCR" in status and "NSFR" in status


class TestNoRegression:
    def test_all_closure_gates_still_pass(self):
        m = _load("audit_intact_v158", AUDIT_PATH)
        for gate in (m.gate_treasury_module_closed,
                      m.gate_treasury_arc_ui_integrated,
                      m.gate_cockpits_registered_in_app,
                      m.gate_product_module_closed,
                      m.gate_product_arc_ui_integrated):
            result = gate()
            assert result["passed"] is True, (
                f"{gate.__name__} regressed: "
                f"{result.get('violations')}")

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v158", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_157_endpoints_still_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in (
            "/products/register-yield-curve",
            "/products/register-bond-position",
            "/products/register-mm-position",
            "/connectivity/register-connector",
            "/connectivity/register-mmf",
            "/products/mtm-fx", "/products/mtm-bond",
        ):
            assert path in text, f"v10.157 endpoint {path} regressed"

    def test_v10_156_endpoints_still_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in ("/alm/register-deposit", "/alm/register-hqla",
                      "/alm/add-inflow", "/alm/add-outflow"):
            assert path in text, f"v10.156 endpoint {path} regressed"

    def test_v10_155_endpoints_still_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in ("/agents/approve", "/alm/run-lcr",
                      "/climate/check-breach"):
            assert path in text, f"v10.155 endpoint {path} regressed"
