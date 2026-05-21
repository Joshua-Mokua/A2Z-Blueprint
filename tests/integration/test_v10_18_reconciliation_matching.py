"""tests/integration/test_v10_18_reconciliation_matching.py — v10.18.

Phase 2 batch 3 (RMS deep-impl arc batch 1): reconciliation matching engine.
ENH-181, ENH-182, ENH-RMS-R1, ENH-RMS-R3.
"""
from __future__ import annotations
import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1018Imports(unittest.TestCase):
    def test_module_imports(self):
        from utils import reconciliation_matching  # noqa

    def test_public_symbols(self):
        from utils import reconciliation_matching as m
        for sym in (
            "DataSource", "MatchAlgorithm", "MatchConfidence",
            "Transaction", "MatchResult", "MatchingRunReport",
            "normalize_vendor_name", "name_similarity",
            "ingest_transactions", "match_pair",
            "ReconciliationMatchingEngine",
            "AUTO_MATCH_THRESHOLD",
            "REVIEW_QUEUE_THRESHOLD",
            "INVESTIGATION_THRESHOLD",
            "DEFAULT_AMOUNT_TOLERANCE_KES",
            "DEFAULT_DATE_TOLERANCE_DAYS",
            "DEFAULT_FUZZY_NAME_THRESHOLD",
            "SPEC_DEVIATION_NOTE",
        ):
            self.assertTrue(hasattr(m, sym), f"missing public: {sym}")


class TestV1018SelfTest(unittest.TestCase):
    def test_self_test_passes(self):
        from utils import reconciliation_matching
        reconciliation_matching.self_test()


class TestV1018RegistryAlignment(unittest.TestCase):
    def test_4_rms_active(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "rms" and s.status == "active"]
        self.assertGreaterEqual(len(active), 4)

    def test_v10_18_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "rms" and s.status == "active"}
        for sid in ("ENH-181", "ENH-182", "ENH-RMS-R1", "ENH-RMS-R3"):
            self.assertIn(sid, active_ids)


class TestV1018VendorNameNormalization(unittest.TestCase):
    """ENH-RMS-R3 — Vendor name normalization library."""

    def test_kenya_legal_suffixes_stripped(self):
        from utils.reconciliation_matching import normalize_vendor_name
        self.assertEqual(normalize_vendor_name("ACME LIMITED"), "ACME")
        self.assertEqual(normalize_vendor_name("ACME LTD"), "ACME")
        self.assertEqual(normalize_vendor_name("ACME PLC"), "ACME")

    def test_compound_suffix_strip(self):
        from utils.reconciliation_matching import normalize_vendor_name
        # Investments + Limited both stripped
        self.assertEqual(
            normalize_vendor_name("ACME INVESTMENTS LIMITED"),
            "ACME")

    def test_synonyms_expanded(self):
        from utils.reconciliation_matching import normalize_vendor_name
        # PVT → PRIVATE, INTL → INTERNATIONAL
        self.assertIn("PRIVATE", normalize_vendor_name("ACME PVT LIMITED"))
        self.assertIn("INTERNATIONAL",
                          normalize_vendor_name("ACME INTL LTD"))

    def test_similarity_idempotent(self):
        from utils.reconciliation_matching import name_similarity
        # ACME LIMITED and ACME LTD normalize to same form → similarity 1.0
        self.assertEqual(
            name_similarity("ACME LIMITED", "ACME LTD"),
            Decimal("1"))


class TestV1018Ingestion(unittest.TestCase):
    """ENH-181 — Multi-source data ingestion."""

    def test_default_parser_handles_alt_field_names(self):
        """Ingestion accepts 'id'/'transaction_id', 'date'/'value_date', etc."""
        from utils.reconciliation_matching import (
            DataSource, ingest_transactions)
        rows = [
            {"transaction_id": "T1", "value_date": "2026-01-15",
              "amount_kes": "1000", "name": "ACME"},
            {"id": "T2", "date": "2026-01-15",
              "amount": Decimal("500"), "narration": "Payment"},
        ]
        parsed, errors = ingest_transactions(
            source=DataSource.GL, rows=rows)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(len(errors), 0)

    def test_errors_surfaced_not_silent(self):
        """Rule 1: bad rows produce explicit errors, not silent skip."""
        from utils.reconciliation_matching import (
            DataSource, ingest_transactions)
        rows = [
            {"transaction_id": "OK", "value_date": "2026-01-15",
              "amount": "100"},
            {"transaction_id": "BAD"},   # missing date + amount
        ]
        parsed, errors = ingest_transactions(
            source=DataSource.GL, rows=rows)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(errors), 1)

    def test_custom_parser_invoked(self):
        from utils.reconciliation_matching import (
            DataSource, Transaction, ingest_transactions)

        def parser(row):
            return Transaction(
                transaction_id=row["custom_id"],
                source=DataSource.NOSTRO,
                value_date=row["custom_date"],
                amount_kes=Decimal(row["custom_amt"]))

        rows = [
            {"custom_id": "X1", "custom_date": "2026-02-01",
              "custom_amt": "777"}]
        parsed, errors = ingest_transactions(
            source=DataSource.NOSTRO, rows=rows, parser=parser)
        self.assertEqual(parsed[0].transaction_id, "X1")
        self.assertEqual(parsed[0].amount_kes, Decimal("777"))


class TestV1018Matching(unittest.TestCase):
    """ENH-182 — Intelligent matching engine."""

    def _txn(self, id_, **kw):
        from utils.reconciliation_matching import (
            DataSource, Transaction)
        defaults = dict(
            source=DataSource.GL, value_date="2026-01-15",
            amount_kes=Decimal("1000"), counterparty_name="ACME LTD")
        defaults.update(kw)
        return Transaction(transaction_id=id_, **defaults)

    def test_exact_reference_match(self):
        from utils.reconciliation_matching import (
            match_pair, MatchAlgorithm)
        a = self._txn("S", reference="REF-001")
        b = self._txn("T", reference="REF-001",
                        amount_kes=Decimal("9999"))   # diff amount but same ref
        r = match_pair(source=a, target=b)
        self.assertEqual(r.algorithm, MatchAlgorithm.EXACT_REFERENCE)
        self.assertTrue(r.is_auto_matched)

    def test_amount_date_tolerance_with_name_high_confidence(self):
        """Combined signals: tolerance + good name → AUTO."""
        from utils.reconciliation_matching import (
            match_pair, MatchAlgorithm)
        a = self._txn("S", amount_kes=Decimal("1000.00"),
                        counterparty_name="ACME LIMITED")
        b = self._txn("T", amount_kes=Decimal("1000.50"),
                        value_date="2026-01-17",
                        counterparty_name="ACME LTD")
        r = match_pair(source=a, target=b)
        self.assertEqual(r.algorithm, MatchAlgorithm.AMOUNT_NAME_COMBINED)
        self.assertTrue(r.is_auto_matched)

    def test_signed_amount_match(self):
        """Source debit -1000 matches target credit +1000."""
        from utils.reconciliation_matching import (
            match_pair, MatchAlgorithm)
        a = self._txn("S", amount_kes=Decimal("-1000"))
        b = self._txn("T", amount_kes=Decimal("1000"))
        r = match_pair(source=a, target=b)
        self.assertEqual(r.algorithm, MatchAlgorithm.EXACT_AMOUNT_DATE)

    def test_unmatched_explicit_not_silent(self):
        """No match → UNMATCHED with target_id=None, not silent skip."""
        from utils.reconciliation_matching import (
            match_pair, MatchAlgorithm)
        a = self._txn("S", amount_kes=Decimal("1000"),
                        counterparty_name="ALPHA")
        b = self._txn("T", amount_kes=Decimal("9999"),
                        value_date="2026-06-01",
                        counterparty_name="BETA")
        r = match_pair(source=a, target=b)
        self.assertEqual(r.algorithm, MatchAlgorithm.UNMATCHED)
        self.assertIsNone(r.target_transaction_id)
        self.assertIsNone(r.match_score)

    def test_ml_ranker_hook_invoked(self):
        """Rule 7: ML ranker callable when rule-based fails."""
        from utils.reconciliation_matching import (
            match_pair, MatchAlgorithm)
        calls = []
        def fake_ml(s, t):
            calls.append((s.transaction_id, t.transaction_id))
            return Decimal("0.92")
        a = self._txn("S", amount_kes=Decimal("1000"),
                        counterparty_name="ALPHA")
        b = self._txn("T", amount_kes=Decimal("9999"),
                        value_date="2026-06-01",
                        counterparty_name="BETA")
        r = match_pair(source=a, target=b, ml_ranker=fake_ml)
        self.assertEqual(r.algorithm, MatchAlgorithm.ML_RANKED)
        self.assertEqual(len(calls), 1)


class TestV1018AutoMatchTarget(unittest.TestCase):
    """ENH-RMS-R1 — 90% auto-match target."""

    def test_auto_match_threshold_90(self):
        from utils.reconciliation_matching import AUTO_MATCH_THRESHOLD
        self.assertEqual(AUTO_MATCH_THRESHOLD, Decimal("0.90"))

    def test_run_at_target_meets_threshold(self):
        """9/10 exact-ref matches → 90% auto-match → meets target."""
        from utils.reconciliation_matching import (
            DataSource, Transaction, ReconciliationMatchingEngine)
        eng = ReconciliationMatchingEngine()
        sources = []
        targets = []
        for i in range(9):
            ref = f"REF-{i}"
            sources.append(Transaction(
                transaction_id=f"S{i}", source=DataSource.GL,
                value_date="2026-01-15", amount_kes=Decimal("1000"),
                reference=ref))
            targets.append(Transaction(
                transaction_id=f"T{i}", source=DataSource.BANK_STATEMENT,
                value_date="2026-01-15", amount_kes=Decimal("1000"),
                reference=ref))
        # 10th source with no candidate
        sources.append(Transaction(
            transaction_id="S9", source=DataSource.GL,
            value_date="2026-01-15", amount_kes=Decimal("999"),
            counterparty_name="LONELY"))
        results, report = eng.match_run(
            source_transactions=sources, target_transactions=targets)
        self.assertEqual(report.auto_match_rate_pct, Decimal("90"))
        self.assertTrue(report.meets_target_rate)

    def test_below_target_flagged(self):
        from utils.reconciliation_matching import (
            DataSource, Transaction, ReconciliationMatchingEngine)
        eng = ReconciliationMatchingEngine()
        sources = [Transaction(
            transaction_id=f"S{i}", source=DataSource.GL,
            value_date="2026-01-15", amount_kes=Decimal(str(1000 + i)))
            for i in range(10)]
        targets = [Transaction(
            transaction_id="T0", source=DataSource.BANK_STATEMENT,
            value_date="2026-01-15", amount_kes=Decimal("1000"))]
        _, report = eng.match_run(
            source_transactions=sources, target_transactions=targets)
        self.assertFalse(report.meets_target_rate)


class TestV1018EngineGreedyAssignment(unittest.TestCase):
    """No double-assignment of targets."""

    def test_target_not_double_assigned(self):
        from utils.reconciliation_matching import (
            DataSource, Transaction, ReconciliationMatchingEngine,
            MatchAlgorithm)
        eng = ReconciliationMatchingEngine()
        # 2 sources both could match T1
        sources = [
            Transaction(transaction_id=f"S{i}", source=DataSource.GL,
                          value_date="2026-01-15",
                          amount_kes=Decimal("1000"),
                          counterparty_name="ACME")
            for i in range(2)]
        targets = [Transaction(
            transaction_id="T0", source=DataSource.BANK_STATEMENT,
            value_date="2026-01-15", amount_kes=Decimal("1000"),
            counterparty_name="ACME")]
        results, report = eng.match_run(
            source_transactions=sources, target_transactions=targets)
        self.assertEqual(report.n_matches, 1)
        self.assertEqual(report.n_unmatched, 1)


class TestV1018Coexistence(unittest.TestCase):
    """v10.18 coexists with v10.6-v10.17 engines."""

    def test_coexistence_with_credit_kesonia(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        from utils.benchmark_rates import BenchmarkRateRegistry
        from utils.reconciliation_matching import (
            ReconciliationMatchingEngine)
        u = AIUnderwritingEngine(entity_name="X")
        b = BenchmarkRateRegistry(entity_name="X")
        r = ReconciliationMatchingEngine(entity_name="X")
        self.assertEqual(u.entity_name, b.entity_name)
        self.assertEqual(b.entity_name, r.entity_name)


if __name__ == "__main__":
    unittest.main()
