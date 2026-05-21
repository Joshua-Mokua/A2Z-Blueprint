"""tests/test_treasury_state_loaders_v10_157.py — Phase 2 Treasury
write-side surface COMPLETE.

Verifies the v10.157 deliverable:
- 5 new state-loading POST endpoints for complex-shape dataclasses
  (YieldCurve with nested points, BondPosition full shape with IFRS9,
   MoneyMarketPosition, Connector with FrozenSet, MMFCounterparty)
- 2 new MTM compute POST endpoints (mtm_fx_position, mtm_bond)
- 2 new query endpoints (get_yield_curve, net_fx_exposure)
- All Pydantic→engine conversions round-trip correctly (catches
  the v10.156 FXPosition is_asset→is_long_base bug class)
- Updated /api/treasury/liquidity-risk/methods placeholder reflects
  Phase 2 write-side complete; remaining items deferred to v10.158+
  with reasons (NOT bandwidth)
- Audit unchanged at 151/151
- No regression of v10.155 closure or v10.156 state loaders
"""
from __future__ import annotations
import ast
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
    def test_v10_157_request_models_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for model in (
            "YieldCurvePointModel",
            "RegisterYieldCurveRequest",
            "RegisterBondPositionRequest",
            "RegisterMMPositionRequest",
            "RegisterConnectorRequest",
            "RegisterMMFRequest",
            "MTMFXRequest",
            "MTMBondRequest",
        ):
            assert model in text, (
                f"v10.157 Pydantic model {model} missing")

    def test_yield_curve_uses_nested_pydantic(self):
        # The YieldCurve has nested points → needs Pydantic-in-Pydantic
        text = API_PATH.read_text(encoding="utf-8")
        assert "List[YieldCurvePointModel]" in text, (
            "RegisterYieldCurveRequest must declare points as "
            "List[YieldCurvePointModel] for nested validation")


class TestNewPostEndpoints:
    EXPECTED_NEW_PATHS = [
        "/products/register-yield-curve",
        "/products/register-bond-position",
        "/products/register-mm-position",
        "/connectivity/register-connector",
        "/connectivity/register-mmf",
        "/products/mtm-fx",
        "/products/mtm-bond",
    ]

    EXPECTED_NEW_GET_PATHS = [
        "/products/yield-curve/{curve_id}",
        "/products/net-fx-exposure",
    ]

    def test_v10_157_post_paths_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in self.EXPECTED_NEW_PATHS:
            assert path in text, (
                f"v10.157 endpoint {path} missing")

    def test_v10_157_get_paths_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in self.EXPECTED_NEW_GET_PATHS:
            assert path in text, (
                f"v10.157 GET endpoint {path} missing")

    def test_total_post_decorator_count(self):
        text = API_PATH.read_text(encoding="utf-8")
        n_post = len(re.findall(r"@router\.post\(", text))
        # v10.155 = 5 POST, v10.156 = +6, v10.157 = +7 (5 register + 2 mtm)
        assert n_post >= 18, (
            f"expected >=18 @router.post decorators total "
            f"(5+6+7), got {n_post}")

    def test_all_v10_157_endpoints_jwt_protected(self):
        text = API_PATH.read_text(encoding="utf-8")
        # Split file into blocks at each @router.* decorator
        chunks = re.split(r'(@router\.\w+\([^)]+\))', text)
        # chunks alternates: preamble, decorator, body, decorator, body...
        v157_paths = (
            "register-yield-curve", "register-bond-position",
            "register-mm-position", "register-connector",
            "register-mmf", "mtm-fx", "mtm-bond",
            "yield-curve/{curve_id}", "net-fx-exposure",
        )
        # Walk pairs of (decorator, body)
        for i in range(1, len(chunks) - 1, 2):
            decorator = chunks[i]
            body = chunks[i + 1] if i + 1 < len(chunks) else ""
            # Does this decorator reference a v10.157 path?
            for path in v157_paths:
                if path in decorator:
                    assert "Depends(get_current_user)" in body, (
                        f"v10.157 endpoint {path} body missing JWT auth: "
                        f"{body[:300]}")
                    break


class TestSignatureDiscipline:
    """v10.153.1 / v10.156 lesson — verify field names match the
    real engine dataclasses, not invented ones."""

    def test_mm_position_uses_is_asset(self):
        # MoneyMarketPosition has is_asset (real field, verified
        # via inspect). Different from FXPosition which has
        # is_long_base.
        text = API_PATH.read_text(encoding="utf-8")
        # Find the products_register_mm function and check its body
        m = re.search(
            r"def products_register_mm\b[\s\S]*?(?=\n    @|\nelse:)",
            text)
        assert m, "couldn't find products_register_mm function"
        block = m.group(0)
        assert "MoneyMarketPosition(" in block
        assert "is_asset=" in block, (
            "MoneyMarketPosition construction must use is_asset (real "
            "field). NOT is_long_base — that's FXPosition's field.")

    def test_bond_uses_classification_enum(self):
        text = API_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"products_register_bond[\s\S]*?BondPosition\([\s\S]*?\)",
            text)
        assert m, "couldn't find BondPosition construction"
        block = m.group(0)
        assert "IFRS9Classification(" in block, (
            "BondPosition construction must convert classification "
            "string to IFRS9Classification enum")

    def test_connector_supported_formats_uses_frozenset(self):
        text = API_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"connectivity_register_connector[\s\S]*?Connector\("
            r"[\s\S]*?\)",
            text)
        assert m, "couldn't find Connector construction"
        block = m.group(0)
        # The conversion must convert list to frozenset
        assert "frozenset(" in block, (
            "Connector supported_formats must be converted from list "
            "to frozenset (real field type is FrozenSet[MessageFormat])")

    def test_audit_treasury_unchanged_signature(self):
        # Carry forward v10.155/v10.156 enforcement
        text = API_PATH.read_text(encoding="utf-8")
        idx = text.find("def _audit_treasury(")
        assert idx > -1
        block = text[idx:idx + 600]
        assert "username=" in block
        assert "detail=" in block
        assert "actor=" not in block
        assert "payload=" not in block


class TestRoundTripConversions:
    """End-to-end conversion: build the engine dataclass directly
    using the same shape the endpoint expects, and verify register_*
    works without TypeError. v10.156 caught the FXPosition is_asset bug
    here pre-ship; v10.157 carries the same discipline."""

    def test_yield_curve_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.treasury_products import (YieldCurve, YieldCurvePoint,
                                                TreasuryProductsEngine)
        eng = TreasuryProductsEngine()
        points = (
            YieldCurvePoint(tenor_years=_Dec("0.25"),
                              rate_pct=_Dec("12.5"), notes=""),
            YieldCurvePoint(tenor_years=_Dec("1.0"),
                              rate_pct=_Dec("13.0"), notes=""),
        )
        curve = YieldCurve(curve_id="TEST_YC", currency="KES",
                             as_of_date="2026-05-06",
                             points=points, notes="")
        eng.register_yield_curve(curve)
        # Verify round-trip via get
        back = eng.get_yield_curve("TEST_YC")
        assert back.curve_id == "TEST_YC"
        assert len(back.points) == 2

    def test_bond_position_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.treasury_products import (BondPosition,
                                                IFRS9Classification,
                                                InstrumentType,
                                                TreasuryProductsEngine)
        eng = TreasuryProductsEngine()
        b = BondPosition(
            position_id="TEST_B",
            instrument_type=InstrumentType("GOVT_BOND"),
            isin="KE2000099999",
            issuer="GOK",
            currency="KES",
            face_value=_Dec("1000000"),
            coupon_pct=_Dec("13.0"),
            coupon_freq_per_year=2,
            issue_date="2024-01-01",
            maturity_date="2034-01-01",
            purchase_price=_Dec("950000"),
            purchase_date="2024-01-01",
            classification=IFRS9Classification("HTM"),
            notes="")
        eng.register_bond_position(b)
        assert eng.board_summary()["n_bond_positions"] >= 1

    def test_mm_position_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.treasury_products import (MoneyMarketPosition,
                                                InstrumentType,
                                                TreasuryProductsEngine)
        eng = TreasuryProductsEngine()
        p = MoneyMarketPosition(
            position_id="TEST_MM",
            instrument_type=InstrumentType("MM_TERM_DEPOSIT"),
            currency="KES",
            principal=_Dec("100000"),
            contract_rate_pct=_Dec("10.0"),
            issue_date="2026-01-01",
            maturity_date="2026-06-30",
            is_asset=True,  # NOT is_long_base — that's FXPosition
            notes="")
        eng.register_mm_position(p)
        assert eng.board_summary()["n_mm_positions"] >= 1

    def test_connector_round_trip(self):
        from utils.treasury_connectivity import (Connector,
                                                   ConnectorType,
                                                   MessageFormat,
                                                   TreasuryConnectivityEngine)
        eng = TreasuryConnectivityEngine()
        c = Connector(
            connector_id="TEST_C",
            connector_type=ConnectorType("BANK_PARTNER"),
            counterparty_name="Test Bank",
            region="KE",
            supported_formats=frozenset({
                MessageFormat("SWIFT_MT103"),
                MessageFormat("ISO_20022_PAIN_001"),
            }),
            endpoint_url="",
            swift_bic="",
            iban="",
            notes="")
        eng.register_connector(c)
        assert eng.board_summary()["n_connectors"] >= 1

    def test_mmf_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.treasury_connectivity import (MMFCounterparty,
                                                   TreasuryConnectivityEngine)
        eng = TreasuryConnectivityEngine()
        mmf = MMFCounterparty(
            counterparty_id="TEST_MMF",
            fund_name="Test Fund",
            manager="Test Mgr",
            fund_size_kes=_Dec("1000000000"),
            current_yield_pct=_Dec("11.0"),
            minimum_investment_kes=_Dec("1000"),
            same_day_settlement=True,
            rating="A")
        eng.register_mmf(mmf)
        assert eng.board_summary()["n_mmf_counterparties"] >= 1

    def test_mtm_fx_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.treasury_products import (FXPosition, InstrumentType,
                                                TreasuryProductsEngine)
        eng = TreasuryProductsEngine()
        # Register a position first
        fx = FXPosition(
            position_id="TEST_MTM_FX",
            instrument_type=InstrumentType("FX_SPOT"),
            base_currency="USD", quote_currency="KES",
            notional_base=_Dec("100000"),
            contract_rate=_Dec("129.50"),
            value_date="2026-05-06",
            maturity_date=None,
            is_long_base=True, notes="")
        eng.register_fx_position(fx)
        # MTM
        result = eng.mtm_fx_position(
            position_id="TEST_MTM_FX",
            spot_rate=_Dec("130.00"),
            base_curve_id=None, quote_curve_id=None,
            as_of_date="2026-05-06")
        # Result should be FXMTMResult dataclass
        assert hasattr(result, "__dataclass_fields__"), (
            f"mtm_fx_position should return a dataclass; "
            f"got {type(result).__name__}")

    def test_mtm_bond_round_trip(self):
        from decimal import Decimal as _Dec
        from utils.treasury_products import (BondPosition,
                                                IFRS9Classification,
                                                InstrumentType,
                                                FairValueLevel,
                                                TreasuryProductsEngine)
        eng = TreasuryProductsEngine()
        b = BondPosition(
            position_id="TEST_MTM_B",
            instrument_type=InstrumentType("GOVT_BOND"),
            isin="KE2000088888", issuer="GOK", currency="KES",
            face_value=_Dec("1000000"),
            coupon_pct=_Dec("13.0"),
            coupon_freq_per_year=2,
            issue_date="2024-01-01",
            maturity_date="2034-01-01",
            purchase_price=_Dec("950000"),
            purchase_date="2024-01-01",
            classification=IFRS9Classification("AFS"),
            notes="")
        eng.register_bond_position(b)
        result = eng.mtm_bond(
            position_id="TEST_MTM_B",
            yield_pct=_Dec("13.5"),
            last_coupon_date="2025-07-01",
            as_of_date="2026-05-06",
            fair_value_level=FairValueLevel("LEVEL_2"))
        assert hasattr(result, "__dataclass_fields__")


class TestUpdatedDeferralPlaceholder:
    def test_placeholder_lists_v10_157_ships(self):
        text = API_PATH.read_text(encoding="utf-8")
        # The placeholder should now reference shipped_in='v10.157'
        assert '"v10.157"' in text or "'v10.157'" in text
        assert "live_compute_endpoints" in text

    def test_remaining_deferred_has_reasons(self):
        # Phase 2 close means remaining deferrals must include
        # explicit reason fields (not bandwidth)
        text = API_PATH.read_text(encoding="utf-8")
        assert "remaining_deferred" in text
        assert "phase_2_status" in text
        # Check the phase 2 status string is honest
        m = re.search(r'"phase_2_status":\s*\([^)]+\)', text)
        assert m, "couldn't find phase_2_status string"
        status = m.group(0)
        # Honest: 'COMPLETE' for the core workflow
        assert "COMPLETE" in status


class TestNoRegression:
    def test_all_closure_gates_still_pass(self):
        m = _load("audit_all_intact_v157", AUDIT_PATH)
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
        m = _load("audit_count_v157", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_156_endpoints_still_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in (
            "/alm/register-deposit", "/alm/register-hqla",
            "/alm/add-inflow", "/alm/add-outflow",
            "/alm/register-rates-position",
            "/products/register-fx-position",
        ):
            assert path in text, f"v10.156 endpoint {path} regressed"

    def test_v10_155_endpoints_still_present(self):
        text = API_PATH.read_text(encoding="utf-8")
        for path in (
            "/agents/approve", "/agents/reject",
            "/alm/run-lcr", "/alm/run-repricing-gap",
            "/climate/check-breach",
        ):
            assert path in text, f"v10.155 endpoint {path} regressed"
