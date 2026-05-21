"""tests/integration/test_v10_37_treasury_closure.py — v10.37.

Treasury arc closure (16/16 active): ENH-239 Islamic, ENH-240 Agentic,
ENH-TRS-R1..R6 (connectivity, digital assets, unified platform,
climate-adjusted limits) + G127 audit gate.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1037Imports(unittest.TestCase):
    def test_islamic_treasury_imports(self):
        from utils import islamic_treasury  # noqa

    def test_treasury_agents_imports(self):
        from utils import treasury_agents  # noqa

    def test_treasury_connectivity_imports(self):
        from utils import treasury_connectivity  # noqa

    def test_treasury_digital_assets_imports(self):
        from utils import treasury_digital_assets  # noqa

    def test_treasury_unified_platform_imports(self):
        from utils import treasury_unified_platform  # noqa

    def test_climate_treasury_limits_imports(self):
        from utils import climate_treasury_limits  # noqa


class TestV1037SelfTests(unittest.TestCase):
    def test_islamic_treasury_self_test(self):
        from utils import islamic_treasury
        islamic_treasury.self_test()

    def test_treasury_agents_self_test(self):
        from utils import treasury_agents
        treasury_agents.self_test()

    def test_treasury_connectivity_self_test(self):
        from utils import treasury_connectivity
        treasury_connectivity.self_test()

    def test_treasury_digital_assets_self_test(self):
        from utils import treasury_digital_assets
        treasury_digital_assets.self_test()

    def test_treasury_unified_platform_self_test(self):
        from utils import treasury_unified_platform
        treasury_unified_platform.self_test()

    def test_climate_treasury_limits_self_test(self):
        from utils import climate_treasury_limits
        climate_treasury_limits.self_test()


class TestV1037StandardsRegistry(unittest.TestCase):
    """All 16 Treasury standards must be active."""

    def test_all_treasury_standards_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        treasury_ids = (
            "ENH-231", "ENH-232", "ENH-233", "ENH-234",
            "ENH-235", "ENH-236", "ENH-237", "ENH-238",
            "ENH-239", "ENH-240",
            "ENH-TRS-R1", "ENH-TRS-R2", "ENH-TRS-R3",
            "ENH-TRS-R4", "ENH-TRS-R5", "ENH-TRS-R6")
        for tid in treasury_ids:
            matches = [
                s for s in STANDARDS_REGISTRY
                if s.standard_id == tid]
            self.assertEqual(
                len(matches), 1,
                f"standard {tid} not unique in registry")
            self.assertEqual(
                matches[0].status, "active",
                f"{tid} status is {matches[0].status}, "
                f"expected 'active'")

    def test_v10_37_batch_marker(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        v10_37_ids = (
            "ENH-239", "ENH-240",
            "ENH-TRS-R1", "ENH-TRS-R2", "ENH-TRS-R3",
            "ENH-TRS-R4", "ENH-TRS-R5", "ENH-TRS-R6")
        for tid in v10_37_ids:
            s = next(
                s for s in STANDARDS_REGISTRY
                if s.standard_id == tid)
            self.assertEqual(
                s.implementation_batch, "v10.37")


class TestV1037IslamicTreasury(unittest.TestCase):
    """ENH-239: Sharia-compliant products."""

    def test_six_product_types(self):
        from utils.islamic_treasury import IslamicProductType
        types = {t.value for t in IslamicProductType}
        self.assertEqual(types, {
            "MURABAHA", "WAKALA", "SUKUK", "MUDARABAH",
            "IJARAH", "QARD_HASAN"})

    def test_prohibited_industries_critical_set(self):
        from utils.islamic_treasury import PROHIBITED_INDUSTRIES
        # Critical haram sectors must be present
        for sector in ("alcohol", "gambling",
                       "conventional_banking"):
            self.assertIn(sector, PROHIBITED_INDUSTRIES)

    def test_murabaha_rejects_haram_counterparty(self):
        from utils.islamic_treasury import (
            IslamicProduct, IslamicProductType,
            value_murabaha, ShariaComplianceStatus)
        p = IslamicProduct(
            product_id="X", product_type=IslamicProductType.MURABAHA,
            counterparty="Casino X",
            principal_kes=Decimal("1000000"),
            contract_date="2026-05-01",
            maturity_date="2027-05-01",
            markup_pct=Decimal("5"),
            underlying_asset_description="slot machines",
            counterparty_business_sector="gambling")
        v = value_murabaha(p)
        self.assertEqual(
            v.sharia_compliance,
            ShariaComplianceStatus.NON_COMPLIANT)


class TestV1037TreasuryAgents(unittest.TestCase):
    """ENH-240: agentic orchestration with human approval."""

    def test_five_concrete_agents(self):
        from utils.treasury_agents import (
            LiquidityBufferAgent, HedgingAgent,
            CashShortfallAgent, PaymentReviewAgent,
            SweepingAgent)
        agents = (
            LiquidityBufferAgent(),
            HedgingAgent(),
            CashShortfallAgent(),
            PaymentReviewAgent(),
            SweepingAgent())
        names = {a.agent_name for a in agents}
        self.assertEqual(len(names), 5)

    def test_approval_workflow_states(self):
        from utils.treasury_agents import ApprovalStatus
        states = {s.value for s in ApprovalStatus}
        # Per Rule 7: human approval is structural
        for required in (
                "PENDING", "APPROVED", "REJECTED", "EXECUTED"):
            self.assertIn(required, states)

    def test_orchestrator_rejects_dup_agent(self):
        from utils.treasury_agents import (
            AgentOrchestrator, LiquidityBufferAgent)
        o = AgentOrchestrator()
        o.register_agent(LiquidityBufferAgent())
        with self.assertRaises(ValueError):
            o.register_agent(LiquidityBufferAgent())


class TestV1037Connectivity(unittest.TestCase):
    """ENH-TRS-R1+R3+R5: bank conn + MMF + ERP-API."""

    def test_supports_iso_20022_and_swift(self):
        from utils.treasury_connectivity import MessageFormat
        formats = {f.value for f in MessageFormat}
        for required in (
                "ISO_20022_CAMT_053", "SWIFT_MT940",
                "SWIFT_MT103", "KEPSS"):
            self.assertIn(required, formats)

    def test_credentials_required_provider_per_rule_7(self):
        from utils.treasury_connectivity import (
            TreasuryConnectivityEngine, Connector,
            ConnectorType, MessageFormat, Message,
            MessageDirection)
        eng = TreasuryConnectivityEngine()
        eng.register_connector(Connector(
            connector_id="c1",
            connector_type=ConnectorType.BANK_PARTNER,
            counterparty_name="Bank X", region="US",
            supported_formats=frozenset({
                MessageFormat.SWIFT_MT103})))
        eng.activate_connector("c1", at="2026-05-01T10:00:00Z")
        msg = Message(
            message_id="m1", connector_id="c1",
            direction=MessageDirection.OUTBOUND,
            format=MessageFormat.SWIFT_MT103,
            payload_summary="test")
        with self.assertRaises(ValueError) as ctx:
            eng.send_message(
                message=msg, require_credentials=True)
        self.assertIn("REQUIRES_PROVIDER", str(ctx.exception))


class TestV1037DigitalAssets(unittest.TestCase):
    """ENH-TRS-R2: stablecoins + digital assets."""

    def test_six_asset_types(self):
        from utils.treasury_digital_assets import DigitalAssetType
        self.assertEqual(len(list(DigitalAssetType)), 6)

    def test_bcbs_classification(self):
        from utils.treasury_digital_assets import (
            DEFAULT_BCBS_CLASSIFICATION,
            DigitalAssetType, BCBSCryptoGroup)
        self.assertEqual(
            DEFAULT_BCBS_CLASSIFICATION[DigitalAssetType.USDC],
            BCBSCryptoGroup.GROUP_1B_STABLECOIN)
        self.assertEqual(
            DEFAULT_BCBS_CLASSIFICATION[DigitalAssetType.BTC],
            BCBSCryptoGroup.GROUP_2_OTHER)

    def test_de_peg_detection_severe(self):
        from utils.treasury_digital_assets import (
            detect_de_peg, DigitalAssetType, DePegStatus)
        # 5% off peg → > 300bps → DE_PEGGED
        status, _ = detect_de_peg(
            asset=DigitalAssetType.USDC,
            current_rate_kes=Decimal("125.00"),
            expected_peg_kes=Decimal("130.00"))
        self.assertEqual(status, DePegStatus.DE_PEGGED)


class TestV1037UnifiedPlatform(unittest.TestCase):
    """ENH-TRS-R4: MX.3-style cross-asset facade."""

    def test_six_asset_classes(self):
        from utils.treasury_unified_platform import AssetClass
        self.assertEqual(len(list(AssetClass)), 6)

    def test_facade_doesnt_mutate_upstream(self):
        """Per Rule 7: facade is READ-ONLY."""
        from utils.treasury_unified_platform import (
            UnifiedTreasuryPlatform)
        from utils.islamic_treasury import IslamicTreasuryEngine
        islamic = IslamicTreasuryEngine()
        plat = UnifiedTreasuryPlatform(islamic_engine=islamic)
        # Facade calling positions() must not mutate islamic engine
        before_n = islamic.product_count
        plat.positions()
        self.assertEqual(islamic.product_count, before_n)


class TestV1037ClimateAdjustedLimits(unittest.TestCase):
    """ENH-TRS-R6: climate-adjusted treasury limits."""

    def test_haircut_bands_count(self):
        from utils.climate_treasury_limits import (
            CLIMATE_HAIRCUT_BANDS)
        self.assertEqual(len(CLIMATE_HAIRCUT_BANDS), 4)

    def test_haircut_bands_values(self):
        from utils.climate_treasury_limits import (
            CLIMATE_HAIRCUT_BANDS)
        haircuts = [hc for _, hc in CLIMATE_HAIRCUT_BANDS]
        self.assertEqual(haircuts, [
            Decimal("1"), Decimal("5"),
            Decimal("15"), Decimal("30")])

    def test_no_climate_engine_returns_base_unadjusted(self):
        from utils.climate_treasury_limits import (
            ClimateTreasuryLimitsEngine, TreasuryAssetClass)
        eng = ClimateTreasuryLimitsEngine()
        limit = eng.compute_adjusted_limit(
            TreasuryAssetClass.CORPORATE_FOSSIL)
        self.assertEqual(
            limit.adjusted_limit_pct, limit.base_limit_pct)


class TestV1037G127AuditGate(unittest.TestCase):
    """G127 audit gate must be registered + pass."""

    def test_g127_registered(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _ in GATES]
        self.assertIn("G127", gate_ids)

    def test_g127_after_g126(self):
        from scripts.audit import GATES
        gate_ids = [gid for gid, _ in GATES]
        self.assertGreater(
            gate_ids.index("G127"), gate_ids.index("G126"))

    def test_g127_passes(self):
        from scripts.audit import gate_treasury_arc_closed
        result = gate_treasury_arc_closed()
        self.assertTrue(
            result["passed"],
            f"G127 should pass; violations: "
            f"{result.get('violations')}")


class TestV1037ScenariosCovered(unittest.TestCase):
    """v10.37 adds new scenarios to scenario_simulator library."""

    def test_treasury_scenario_library_grew(self):
        from utils.scenario_simulator import (
            TREASURY_SCENARIO_LIBRARY)
        # v10.36 had 11 scenarios; v10.37 adds at least 8
        self.assertGreaterEqual(
            len(TREASURY_SCENARIO_LIBRARY), 19)

    def test_all_v10_37_scenarios_pass(self):
        from utils.scenario_simulator import (
            ScenarioRunner, TREASURY_SCENARIO_LIBRARY,
            ScenarioStatus, _build_test_engine_bundle)
        runner = ScenarioRunner(
            bundle_factory=_build_test_engine_bundle)
        results = runner.run_all(TREASURY_SCENARIO_LIBRARY)
        failures = [
            r for r in results
            if r.status not in (
                ScenarioStatus.PASS, ScenarioStatus.SKIPPED)]
        self.assertEqual(
            len(failures), 0,
            f"unexpected failures: "
            f"{[(r.scenario_id, r.status.value) for r in failures]}")


class TestV1037AuditScoreGuard(unittest.TestCase):
    """Audit score must be at least 127 after v10.37."""

    def test_audit_score_at_least_127(self):
        from scripts.audit import GATES
        # Run all gates; count passes
        n_total = len(GATES)
        n_passed = 0
        for gid, gate_fn in GATES:
            result = gate_fn()
            if result.get("passed"):
                n_passed += 1
        self.assertGreaterEqual(
            n_passed, 127,
            f"audit score {n_passed}/{n_total} < 127 — "
            f"v10.37 closure broken")


if __name__ == "__main__":
    unittest.main()
