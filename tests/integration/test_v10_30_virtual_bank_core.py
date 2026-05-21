"""tests/integration/test_v10_30_virtual_bank_core.py — v10.30.

Virtual Bank simulation framework batch 1: foundation — mock FLEXCUBE
adapter + banking entity simulator + deterministic seeding + day-end
batch. Cat B operational utility (no regulatory standards).
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1030Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import virtual_bank_core  # noqa

    def test_public_symbols(self):
        from utils import virtual_bank_core as m
        for sym in (
            # Seed
            "derive_seed", "deterministic_pseudo_random",
            # Entities
            "CustomerSegment", "AccountType", "AccountStatus",
            "LoanStatus", "ALLOWED_LOAN_TRANSITIONS",
            "is_valid_loan_transition",
            "VirtualCustomer", "VirtualAccount",
            "VirtualLoan", "VirtualBranch", "VirtualTransaction",
            # Time
            "SimulationTime",
            # Day-end
            "daily_interest_amount", "days_past_due",
            "loan_status_from_dpd",
            # Mock
            "MockResponse",
            # Engine
            "VirtualBankCore",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1030SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import virtual_bank_core
        virtual_bank_core.self_test()


class TestV1030Determinism(unittest.TestCase):
    """Same seed → same output, always."""

    def test_derive_seed_deterministic(self):
        from utils.virtual_bank_core import derive_seed
        s1 = derive_seed(
            base_seed="abc", namespace="ns", discriminator="d")
        s2 = derive_seed(
            base_seed="abc", namespace="ns", discriminator="d")
        self.assertEqual(s1, s2)

    def test_derive_seed_changes_with_inputs(self):
        from utils.virtual_bank_core import derive_seed
        s1 = derive_seed(
            base_seed="abc", namespace="ns", discriminator="d1")
        s2 = derive_seed(
            base_seed="abc", namespace="ns", discriminator="d2")
        self.assertNotEqual(s1, s2)

    def test_two_banks_same_seed_same_outputs(self):
        from utils.virtual_bank_core import (
            VirtualBankCore, VirtualBranch, VirtualCustomer,
            VirtualAccount, CustomerSegment, AccountType,
            AccountStatus)

        def make(seed):
            b = VirtualBankCore(
                entity_name="X", base_seed=seed,
                base_date="2026-01-01")
            b.add_branch(VirtualBranch(
                branch_code="BR1", branch_name="X", region="Y",
                branch_type="MAIN", n_staff=5))
            b.add_customer(VirtualCustomer(
                cif="C1", full_name="X",
                segment=CustomerSegment.RETAIL,
                branch_code="BR1", rm_code="RM1",
                onboarding_date="2025-01-01"))
            b.add_account(VirtualAccount(
                account_no="A1", cif="C1",
                branch_code="BR1",
                account_type=AccountType.SAVINGS,
                currency="KES",
                balance=Decimal("100000"),
                status=AccountStatus.ACTIVE,
                open_date="2025-01-01",
                interest_rate_pct=Decimal("3.65")))
            return b

        b1 = make("seedX")
        b2 = make("seedX")
        b1.tick(days=5)
        b2.tick(days=5)
        b1.run_day_end()
        b2.run_day_end()
        self.assertEqual(b1.board_summary(), b2.board_summary())


class TestV1030LoanLifecycle(unittest.TestCase):
    """Loan state machine aligned with CBK PG/04."""

    def test_dpd_to_status_mapping(self):
        from utils.virtual_bank_core import (
            loan_status_from_dpd, LoanStatus)
        self.assertEqual(
            loan_status_from_dpd(dpd=0), LoanStatus.PERFORMING)
        self.assertEqual(
            loan_status_from_dpd(dpd=45), LoanStatus.DELINQUENT_30)
        self.assertEqual(
            loan_status_from_dpd(dpd=75), LoanStatus.DELINQUENT_60)
        self.assertEqual(
            loan_status_from_dpd(dpd=120), LoanStatus.DELINQUENT_90)
        self.assertEqual(
            loan_status_from_dpd(dpd=200),
            LoanStatus.NON_PERFORMING)

    def test_application_cannot_skip_to_performing(self):
        from utils.virtual_bank_core import (
            is_valid_loan_transition, LoanStatus)
        self.assertFalse(is_valid_loan_transition(
            LoanStatus.APPLICATION, LoanStatus.PERFORMING))

    def test_closed_is_terminal(self):
        from utils.virtual_bank_core import (
            ALLOWED_LOAN_TRANSITIONS, LoanStatus)
        self.assertEqual(
            len(ALLOWED_LOAN_TRANSITIONS[LoanStatus.CLOSED]), 0)


class TestV1030DayEnd(unittest.TestCase):
    """Day-end batch processing."""

    def _make_bank(self):
        from utils.virtual_bank_core import (
            VirtualBankCore, VirtualBranch, VirtualCustomer,
            VirtualAccount, CustomerSegment, AccountType,
            AccountStatus)
        bank = VirtualBankCore(
            entity_name="Test", base_seed="t",
            base_date="2026-01-01")
        bank.add_branch(VirtualBranch(
            branch_code="BR1", branch_name="X",
            region="Y", branch_type="MAIN", n_staff=5))
        bank.add_customer(VirtualCustomer(
            cif="C1", full_name="X",
            segment=CustomerSegment.RETAIL,
            branch_code="BR1", rm_code="RM1",
            onboarding_date="2025-01-01"))
        bank.add_account(VirtualAccount(
            account_no="A1", cif="C1", branch_code="BR1",
            account_type=AccountType.SAVINGS,
            currency="KES",
            balance=Decimal("100000"),
            status=AccountStatus.ACTIVE,
            open_date="2025-01-01",
            interest_rate_pct=Decimal("3.65")))
        return bank

    def test_simple_interest_accrual(self):
        """100K @ 3.65% annual → 10.00 KES daily."""
        bank = self._make_bank()
        bank.run_day_end()
        acc = bank.get_account("A1")
        self.assertEqual(acc.balance, Decimal("100010.00"))

    def test_day_end_idempotent_same_day(self):
        bank = self._make_bank()
        bank.run_day_end()
        n1 = sum(1 for t in bank.all_transactions()
                   if t.txn_type == "INTEREST")
        bank.run_day_end()
        n2 = sum(1 for t in bank.all_transactions()
                   if t.txn_type == "INTEREST")
        self.assertEqual(n1, n2)

    def test_loan_aging_dpd_to_status(self):
        from utils.virtual_bank_core import (
            VirtualLoan, LoanStatus)
        bank = self._make_bank()
        bank.add_loan(VirtualLoan(
            loan_id="L1", cif="C1",
            branch_code="BR1", rm_code="RM1",
            principal=Decimal("500000"),
            outstanding=Decimal("450000"),
            rate_pct=Decimal("13.5"),
            tenor_months=24,
            disbursement_date="2025-06-01",
            next_due_date="2025-12-01",
            status=LoanStatus.PERFORMING,
            days_past_due=0))
        bank.tick(days=5)    # current = 2026-01-06, dpd = 36
        bank.run_day_end()
        loan = bank.get_loan("L1")
        self.assertEqual(loan.status, LoanStatus.DELINQUENT_30)


class TestV1030MockFlexcubeAdapter(unittest.TestCase):
    """Drop-in API surface matching utils/flexcube_adapter."""

    def _make_bank(self):
        from utils.virtual_bank_core import (
            VirtualBankCore, VirtualBranch, VirtualCustomer,
            VirtualAccount, CustomerSegment, AccountType,
            AccountStatus)
        bank = VirtualBankCore(
            entity_name="Test", base_seed="seed",
            base_date="2026-01-01")
        bank.add_branch(VirtualBranch(
            branch_code="BR1", branch_name="Westlands",
            region="Nairobi",
            branch_type="MAIN", n_staff=10))
        bank.add_customer(VirtualCustomer(
            cif="100000001", full_name="Alice",
            segment=CustomerSegment.RETAIL,
            branch_code="BR1", rm_code="RM1",
            onboarding_date="2025-01-01"))
        bank.add_account(VirtualAccount(
            account_no="ECO1000000001", cif="100000001",
            branch_code="BR1",
            account_type=AccountType.SAVINGS,
            currency="KES",
            balance=Decimal("50000"),
            status=AccountStatus.ACTIVE,
            open_date="2025-01-01"))
        return bank

    def test_fetch_account_balance_returns_balance(self):
        bank = self._make_bank()
        resp = bank.fetch_account_balance("ECO1000000001")
        self.assertEqual(resp.payload["balance"], "50000")
        self.assertTrue(resp.is_synthetic)

    def test_fetch_account_unknown_returns_error(self):
        """Per Rule 1 — unknown account surfaces explicit error."""
        bank = self._make_bank()
        resp = bank.fetch_account_balance("UNKNOWN")
        self.assertEqual(resp.payload.get("error"),
                          "account_not_found")

    def test_fetch_customer_returns_segment(self):
        bank = self._make_bank()
        resp = bank.fetch_customer("100000001")
        self.assertEqual(resp.payload["segment"], "RETAIL")

    def test_fetch_branch_metrics_aggregates(self):
        bank = self._make_bank()
        resp = bank.fetch_branch_metrics("BR1")
        self.assertEqual(resp.payload["n_accounts"], 1)
        self.assertEqual(resp.payload["total_deposits"], "50000")

    def test_responses_carry_seed_and_day_offset(self):
        """Per Rule 1 — every response carries traceability metadata."""
        bank = self._make_bank()
        bank.tick(days=7)
        resp = bank.fetch_account_balance("ECO1000000001")
        self.assertEqual(resp.sim_seed, "seed")
        self.assertEqual(resp.sim_day_offset, 7)


class TestV1030CoexistenceWithPriorEngines(unittest.TestCase):
    """v10.30 coexists with v10.23-v10.29 stack."""

    def test_all_engines_coexist(self):
        from utils.audit_core import AuditCoreEngine
        from utils.audit_trail_certification import (
            AuditTrailCertificationEngine)
        from utils.model_governance import ModelGovernanceEngine
        from utils.model_governance_runtime import (
            ModelGovernanceRuntimeEngine)
        from utils.virtual_bank_core import VirtualBankCore
        engines = [
            AuditCoreEngine(entity_name="X"),
            AuditTrailCertificationEngine(entity_name="X"),
            ModelGovernanceEngine(entity_name="X"),
            ModelGovernanceRuntimeEngine(entity_name="X"),
            VirtualBankCore(
                entity_name="X", base_seed="s",
                base_date="2026-01-01"),
        ]
        for e in engines:
            self.assertEqual(e.entity_name, "X")


if __name__ == "__main__":
    unittest.main()
