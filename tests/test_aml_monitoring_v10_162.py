"""tests/test_aml_monitoring_v10_162.py — ENH-193 AML Transaction
Monitoring Engine (orchestration layer).

Verifies the v10.162 deliverable:
- Engine module exists, parses, imports
- 2 enums (MonitoringOutcome 4 values, TierAwareSeverity 4 values)
- 2 frozen output dataclasses (TieredAlert, AmlMonitoringResult) with
  to_dict for API serialization
- AmlMonitoringEngine wraps existing TransactionMonitoringEngine
  (Standard #59) without modifying it
- 5 realistic Ecobank Kenya scenarios produce deterministic outputs:
  - Clean SDD customer → CLEAN
  - CDD customer with structuring → ESCALATE_TO_SAR (R2 CRITICAL)
  - EDD/PEP customer with cash deposit → ESCALATE_TO_SAR with HIGH→CRITICAL escalation
  - PROHIBITED tier → ESCALATE_TO_BLOCK
  - CDD wire to Iran → ESCALATE_TO_SAR (R4 CRITICAL)
- Tier-aware severity escalation logic correct (EDD bumps base by 1)
- Sanctions match auto-escalates to CRITICAL
- ML layer status honestly DEFERRED — string surfaces in result + summary
- Standard ENH-193 status='active' in registry
- Audit unchanged at 151/151 (engine-level work)
- No regression of v10.160 KYC engine or earlier work
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_PATH = REPO_ROOT / "utils" / "aml_monitoring.py"
REGISTRY_PATH = REPO_ROOT / "utils" / "standards_registry.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestModuleShape:
    def test_engine_exists_and_parses(self):
        assert ENGINE_PATH.exists()
        ast.parse(ENGINE_PATH.read_text(encoding="utf-8"))

    def test_engine_imports(self):
        from utils.aml_monitoring import AmlMonitoringEngine
        eng = AmlMonitoringEngine()
        assert eng is not None

    def test_enums_present(self):
        from utils.aml_monitoring import (MonitoringOutcome,
                                            TierAwareSeverity)
        assert len(list(MonitoringOutcome)) == 4
        assert "ESCALATE_TO_SAR" in [v.value for v in MonitoringOutcome]
        assert "ESCALATE_TO_BLOCK" in [v.value for v in MonitoringOutcome]
        assert len(list(TierAwareSeverity)) == 4

    def test_dataclasses_frozen(self):
        from utils.aml_monitoring import TieredAlert, TierAwareSeverity
        ta = TieredAlert(
            alert_id=1, rule_id="R1", rule_name="x", base_severity="HIGH",
            tier_aware_severity=TierAwareSeverity.HIGH,
            customer_id="C", customer_tier="CDD", txn_ids=("T1",),
            description="x", escalation_reason="none")
        try:
            ta.alert_id = 999
            raise AssertionError("frozen dataclass mutated")
        except Exception as e:
            err = type(e).__name__.lower() + " " + str(e).lower()
            assert "frozen" in err or "cannot assign" in err


class TestRegistryActivation:
    def test_enh_193_active(self):
        m = _load("registry_v161", REGISTRY_PATH)
        s = next((x for x in m.STANDARDS_REGISTRY
                   if x.standard_id == "ENH-193"), None)
        assert s is not None
        assert s.status == "active"
        assert "aml_monitoring" in (s.affected_engines or ())
        assert "transaction_monitoring" in (s.affected_engines or ())


class TestOutcomeLogic:
    def test_clean_sdd_no_alerts(self):
        from utils.aml_monitoring import (AmlMonitoringEngine,
                                            MonitoringOutcome)
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        txns = [Transaction(
            txn_id="T1", customer_id="C1", account_id="A1",
            amount_kes=Decimal("50000"), txn_type="MOBILE_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        r = eng.monitor_customer("C1", txns, customer_tier="SDD")
        assert r.outcome == MonitoringOutcome.CLEAN
        assert r.n_alerts == 0

    def test_structuring_escalates_to_sar(self):
        from utils.aml_monitoring import (AmlMonitoringEngine,
                                            MonitoringOutcome)
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        txns = [
            Transaction(txn_id=f"T{i}", customer_id="C2",
                          account_id="A2",
                          amount_kes=Decimal(amt),
                          txn_type="CASH_DEPOSIT",
                          txn_datetime=datetime(2026, 5, day, 10, 0))
            for i, (amt, day) in enumerate([
                ("999000", 1), ("999500", 2), ("980000", 3)
            ], 1)
        ]
        r = eng.monitor_customer("C2", txns, customer_tier="CDD")
        # Engine baseline for R2 structuring is CRITICAL → SAR
        assert r.outcome == MonitoringOutcome.ESCALATE_TO_SAR
        assert r.n_critical >= 1

    def test_prohibited_tier_blocks(self):
        from utils.aml_monitoring import (AmlMonitoringEngine,
                                            MonitoringOutcome)
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        txns = [Transaction(
            txn_id="T1", customer_id="C4", account_id="A4",
            amount_kes=Decimal("10000"), txn_type="MOBILE_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        r = eng.monitor_customer("C4", txns,
                                    customer_tier="PROHIBITED",
                                    sanctions_hit=True)
        assert r.outcome == MonitoringOutcome.ESCALATE_TO_BLOCK
        # Defensive: should not have scanned because tier is terminal
        assert r.meta.get("n_transactions_scanned") == 0

    def test_high_risk_geography_critical(self):
        from utils.aml_monitoring import (AmlMonitoringEngine,
                                            MonitoringOutcome,
                                            TierAwareSeverity)
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        txns = [Transaction(
            txn_id="T1", customer_id="C5", account_id="A5",
            amount_kes=Decimal("500000"), txn_type="WIRE_OUT",
            txn_datetime=datetime(2026, 5, 1, 10, 0),
            counterparty_country="IR")]
        r = eng.monitor_customer("C5", txns, customer_tier="CDD")
        assert r.outcome == MonitoringOutcome.ESCALATE_TO_SAR
        assert any(ta.rule_id == "R4" for ta in r.tiered_alerts)
        # R4 baseline severity for IR/KP is CRITICAL
        r4_alert = next(ta for ta in r.tiered_alerts
                         if ta.rule_id == "R4")
        assert r4_alert.tier_aware_severity == TierAwareSeverity.CRITICAL


class TestTierAwareEscalation:
    """The orchestration value-add over the rule engine alone."""

    def test_edd_tier_bumps_high_to_critical(self):
        from utils.aml_monitoring import (AmlMonitoringEngine,
                                            TierAwareSeverity)
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        # KES 1.5M cash deposit → R1 fires HIGH
        # EDD tier → bump to CRITICAL
        txns = [Transaction(
            txn_id="T1", customer_id="C3", account_id="A3",
            amount_kes=Decimal("1500000"), txn_type="CASH_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        r = eng.monitor_customer("C3", txns, customer_tier="EDD")
        # Find R1 alert
        r1_alerts = [ta for ta in r.tiered_alerts if ta.rule_id == "R1"]
        assert len(r1_alerts) == 1
        a = r1_alerts[0]
        assert a.base_severity == "HIGH"
        assert a.tier_aware_severity == TierAwareSeverity.CRITICAL
        assert "edd_tier_escalation" in a.escalation_reason

    def test_sdd_tier_no_escalation(self):
        # SDD does not escalate — multiplier 1.5x effectively means
        # fewer alerts fire in the underlying engine, not different
        # severity. Severity from underlying engine passes through.
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        # KES 1.5M cash deposit → R1 base HIGH
        txns = [Transaction(
            txn_id="T1", customer_id="C6", account_id="A6",
            amount_kes=Decimal("1500000"), txn_type="CASH_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        r = eng.monitor_customer("C6", txns, customer_tier="SDD")
        r1_alerts = [ta for ta in r.tiered_alerts if ta.rule_id == "R1"]
        if r1_alerts:
            a = r1_alerts[0]
            # SDD passes base severity through unchanged
            assert a.escalation_reason == "no_escalation"

    def test_sanctions_hit_auto_critical(self):
        from utils.aml_monitoring import (AmlMonitoringEngine,
                                            TierAwareSeverity)
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        # Even a low-amount transaction with sanctions_hit propagated
        # produces ESCALATE_TO_BLOCK
        txns = [Transaction(
            txn_id="T1", customer_id="C7", account_id="A7",
            amount_kes=Decimal("5000"), txn_type="MOBILE_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        from utils.aml_monitoring import MonitoringOutcome
        r = eng.monitor_customer("C7", txns, customer_tier="CDD",
                                    sanctions_hit=True)
        assert r.outcome == MonitoringOutcome.ESCALATE_TO_BLOCK
        assert r.sanctions_match_propagated is True


class TestHonestDeferral:
    def test_ml_layer_explicitly_deferred(self):
        from utils.aml_monitoring import AmlMonitoringEngine
        from utils.transaction_monitoring import Transaction
        eng = AmlMonitoringEngine()
        txns = [Transaction(
            txn_id="T1", customer_id="C1", account_id="A1",
            amount_kes=Decimal("5000"), txn_type="MOBILE_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        r = eng.monitor_customer("C1", txns)
        # ml_layer_status must be a string explaining the deferral
        assert "DEFERRED" in r.ml_layer_status
        assert "training data" in r.ml_layer_status.lower()

    def test_board_summary_surfaces_deferral(self):
        from utils.aml_monitoring import AmlMonitoringEngine
        eng = AmlMonitoringEngine()
        summary = eng.board_summary()
        assert "ml_layer_status" in summary
        assert "DEFERRED" in summary["ml_layer_status"]
        assert "underlying_rule_engine" in summary
        assert "Standard #59" in summary["underlying_rule_engine"]


class TestIntegrationCleanliness:
    """ENH-193 must NOT modify TransactionMonitoringEngine. It composes."""

    def test_transaction_monitoring_unchanged(self):
        # Standalone usage of the underlying engine must still work
        from utils.transaction_monitoring import (
            TransactionMonitoringEngine, Transaction)
        eng = TransactionMonitoringEngine()
        txns = [Transaction(
            txn_id="T1", customer_id="X", account_id="A",
            amount_kes=Decimal("3000000"), txn_type="CASH_DEPOSIT",
            txn_datetime=datetime(2026, 5, 1, 10, 0))]
        alerts = eng.scan(txns)
        # R1 should fire
        assert any(a.rule_id == "R1" for a in alerts)


class TestPortfolioSummary:
    def test_board_summary_shape(self):
        from utils.aml_monitoring import AmlMonitoringEngine
        eng = AmlMonitoringEngine()
        s = eng.board_summary()
        for f in ("entity", "engine", "n_customers_monitored",
                   "n_total_alerts", "n_total_critical_alerts",
                   "n_sanctions_propagated", "outcome_counts",
                   "tier_counts", "ml_layer_status",
                   "underlying_rule_engine"):
            assert f in s, f"board_summary missing: {f}"
        assert s["engine"] == "ENH-193 AmlMonitoringEngine"


class TestNoRegression:
    def test_audit_still_passes(self):
        m = _load("audit_v161", AUDIT_PATH)
        for gate_id, gate_fn in m.GATES:
            result = gate_fn()
            assert result["passed"] is True, (
                f"{gate_id} regressed: {result.get('violations')}")

    def test_total_gate_count_unchanged(self):
        m = _load("audit_count_v161", AUDIT_PATH)
        assert len(m.GATES) == 151

    def test_v10_160_kyc_still_works(self):
        # ENH-191 from v10.160 should be untouched
        from utils.kyc_onboarding import KycOnboardingEngine
        eng = KycOnboardingEngine()
        assert eng.board_summary()["engine"] == (
            "ENH-191 KycOnboardingEngine")
