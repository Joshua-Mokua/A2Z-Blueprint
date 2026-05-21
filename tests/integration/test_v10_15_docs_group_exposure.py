"""tests/integration/test_v10_15_docs_group_exposure.py — v10.15.

Phase 2 batch 9 (Credit batch 5): document management + group exposure.
ENH-127, ENH-CRD-R4. Final 2 Credit standards before v10.16 closes the arc.
"""
from __future__ import annotations
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parents[2]))


class TestV1015Imports(unittest.TestCase):
    def test_doc_module_imports(self):
        from utils import document_management  # noqa
    def test_group_module_imports(self):
        from utils import group_exposure  # noqa

    def test_doc_public_symbols(self):
        from utils import document_management as m
        for sym in (
            "DocumentType", "DocumentState", "ALLOWED_DOC_TRANSITIONS",
            "is_valid_doc_transition",
            "DOC_RETENTION_YEARS", "DOC_VALIDITY_WINDOW_DAYS",
            "AuthenticityCheck", "AuthenticityResult",
            "AuthenticityCheckResult",
            "DocumentMetadata", "DocumentRecord",
            "compute_sha256", "verify_file_integrity", "verify_format",
            "is_document_expired", "extract_fields", "assess_document",
            "DocumentManagementEngine",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")

    def test_group_public_symbols(self):
        from utils import group_exposure as m
        for sym in (
            "ExposureType", "EXPOSURE_CCF",
            "RelationshipType", "LimitVerdict",
            "Exposure", "Obligor",
            "LimitCheckResult", "GroupExposureReport",
            "aggregate_obligor_exposure", "aggregate_group_exposure",
            "aggregate_insider_exposure",
            "check_single_obligor_limit", "check_group_limit",
            "check_insider_limit", "assess_group_exposure",
            "GroupExposureEngine",
            "SINGLE_OBLIGOR_LIMIT_PCT",
            "SINGLE_INSIDER_LIMIT_PCT",
            "AGGREGATE_INSIDER_LIMIT_PCT",
            "LARGE_EXPOSURE_REPORTING_THRESHOLD_PCT",
        ):
            self.assertTrue(hasattr(m, sym), f"missing: {sym}")


class TestV1015SelfTests(unittest.TestCase):
    def test_doc_self_test(self):
        from utils import document_management
        document_management.self_test()

    def test_group_self_test(self):
        from utils import group_exposure
        group_exposure.self_test()


class TestV1015RegistryAlignment(unittest.TestCase):
    def test_all_19_credit_active(self):
        """At v10.15 closure there were 19 Credit standards all active.
        Future credit additions (e.g., ENH-CBK-KESONIA in v10.17) grow
        the set, so we assert ≥19 active rather than ==19."""
        from utils.standards_registry import STANDARDS_REGISTRY
        active = [s for s in STANDARDS_REGISTRY
                    if s.subcategory == "credit" and s.status == "active"]
        self.assertGreaterEqual(
            len(active), 19,
            "Expected ≥19 active Credit standards (the v10.16 closure set)")

    def test_v10_15_specific(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        active_ids = {s.standard_id for s in STANDARDS_REGISTRY
                        if s.subcategory == "credit" and s.status == "active"}
        for sid in ("ENH-127", "ENH-CRD-R4"):
            self.assertIn(sid, active_ids)

    def test_no_credit_planned_remaining(self):
        from utils.standards_registry import STANDARDS_REGISTRY
        planned = [s for s in STANDARDS_REGISTRY
                     if s.subcategory == "credit" and s.status == "planned"]
        self.assertEqual(len(planned), 0)


class TestV1015DocumentLifecycle(unittest.TestCase):
    """ENH-127 — document lifecycle + authenticity."""

    def test_full_pass_verified(self):
        from utils.document_management import (
            DocumentMetadata, DocumentType, assess_document,
            DocumentState, compute_sha256)
        content = b"id document"
        metadata = DocumentMetadata(
            document_id="D1", applicant_id="A",
            document_type=DocumentType.NATIONAL_ID,
            file_name="id.png", file_size_bytes=len(content),
            file_format="png",
            sha256_hash=compute_sha256(content),
            submitted_at="2025-01-01T00:00:00Z")

        def extractor(doc_type, content):
            return ({"id_number": "12345678"}, Decimal("0.99"))

        r = assess_document(
            metadata=metadata, file_content=content,
            file_extractor=extractor,
            as_of=date(2025, 1, 15))
        self.assertEqual(r.state, DocumentState.VERIFIED)

    def test_no_extractor_extraction_pending(self):
        """Rule 7 — no extractor → DATA_EXTRACTION_PENDING, never silent default."""
        from utils.document_management import (
            DocumentMetadata, DocumentType, assess_document,
            DocumentState, compute_sha256)
        content = b"x"
        metadata = DocumentMetadata(
            document_id="D1", applicant_id="A",
            document_type=DocumentType.PAYSLIP,
            file_name="ps.pdf", file_size_bytes=1,
            file_format="pdf",
            sha256_hash=compute_sha256(content),
            submitted_at="t",
            issued_date="2025-01-01")
        r = assess_document(metadata=metadata, file_content=content,
                              as_of=date(2025, 1, 15))
        self.assertEqual(r.state, DocumentState.DATA_EXTRACTION_PENDING)

    def test_hash_mismatch_authenticity_failed(self):
        from utils.document_management import (
            DocumentMetadata, DocumentType, assess_document,
            DocumentState)
        metadata = DocumentMetadata(
            document_id="D1", applicant_id="A",
            document_type=DocumentType.NATIONAL_ID,
            file_name="id.png", file_size_bytes=10,
            file_format="png",
            sha256_hash="0" * 64,
            submitted_at="t")
        r = assess_document(
            metadata=metadata, file_content=b"different content",
            as_of=date(2025, 1, 15))
        self.assertEqual(r.state, DocumentState.AUTHENTICITY_FAILED)

    def test_expired_document_rejected(self):
        from utils.document_management import (
            DocumentMetadata, DocumentType, assess_document,
            DocumentState, compute_sha256)
        content = b"x"
        metadata = DocumentMetadata(
            document_id="D1", applicant_id="A",
            document_type=DocumentType.BANK_STATEMENT,
            file_name="x.pdf", file_size_bytes=1,
            file_format="pdf",
            sha256_hash=compute_sha256(content),
            submitted_at="t",
            issued_date="2024-01-01")    # 1 yr old, 90-day window
        r = assess_document(metadata=metadata, file_content=content,
                              as_of=date(2025, 6, 1))
        self.assertEqual(r.state, DocumentState.REJECTED)

    def test_pdf_required_for_financials(self):
        from utils.document_management import (
            DocumentType, verify_format, AuthenticityResult)
        r = verify_format(
            document_type=DocumentType.AUDITED_FINANCIALS,
            file_format="jpg")
        self.assertEqual(r.result, AuthenticityResult.FAILED)

    def test_retention_policy_kyc_seven_years(self):
        from utils.document_management import (
            DOC_RETENTION_YEARS, DocumentType)
        self.assertEqual(DOC_RETENTION_YEARS[DocumentType.NATIONAL_ID], 7)
        self.assertEqual(DOC_RETENTION_YEARS[DocumentType.KRA_PIN_CERTIFICATE], 7)


class TestV1015GroupExposure(unittest.TestCase):
    """ENH-CRD-R4 — single obligor + group + insider limits."""

    def test_constants_match_banking_act(self):
        from utils.group_exposure import (
            SINGLE_OBLIGOR_LIMIT_PCT, SINGLE_INSIDER_LIMIT_PCT,
            AGGREGATE_INSIDER_LIMIT_PCT)
        self.assertEqual(SINGLE_OBLIGOR_LIMIT_PCT, Decimal("25.0"))
        self.assertEqual(SINGLE_INSIDER_LIMIT_PCT, Decimal("5.0"))
        self.assertEqual(AGGREGATE_INSIDER_LIMIT_PCT, Decimal("20.0"))

    def test_single_obligor_25pct_breach(self):
        from utils.group_exposure import (
            check_single_obligor_limit, LimitVerdict)
        r = check_single_obligor_limit(
            current_exposure_kes=Decimal("260000000"),    # 26%
            core_capital_kes=Decimal("1000000000"))
        self.assertEqual(r.verdict, LimitVerdict.BREACHED)

    def test_group_aggregation_includes_subsidiaries(self):
        from utils.group_exposure import (
            Obligor, Exposure, ExposureType, RelationshipType,
            assess_group_exposure)
        obligors = [
            Obligor(obligor_id="P", name="Parent", is_individual=False,
                      group_id="G1",
                      relationship_to_bank=RelationshipType.GROUP_PARENT),
            Obligor(obligor_id="S", name="Sub", is_individual=False,
                      group_id="G1",
                      relationship_to_bank=RelationshipType.GROUP_SUBSIDIARY),
        ]
        exposures = [
            Exposure(
                exposure_id=f"E{i}", obligor_id=("P" if i < 2 else "S"),
                exposure_type=ExposureType.LOAN_TERM,
                outstanding_kes=Decimal("50000000"),
                limit_kes=Decimal("50000000"))
            for i in range(3)]
        r = assess_group_exposure(
            obligor_id="P", obligors=obligors, exposures=exposures,
            core_capital_kes=Decimal("1000000000"))
        self.assertIsNotNone(r.group_check)
        # 3 × 50M = 150M total group exposure
        self.assertEqual(r.group_check.current_exposure_kes,
                          Decimal("150000000"))

    def test_insider_5pct_breach(self):
        from utils.group_exposure import (
            check_insider_limit, LimitVerdict)
        r = check_insider_limit(
            insider_exposure_kes=Decimal("60000000"),   # 6%
            core_capital_kes=Decimal("1000000000"),
            is_aggregate=False)    # single insider 5% limit
        self.assertEqual(r.verdict, LimitVerdict.BREACHED)

    def test_credit_equivalent_lc_half_ccf(self):
        """LC: 50% CCF on undrawn portion."""
        from utils.group_exposure import Exposure, ExposureType
        e = Exposure(
            exposure_id="E1", obligor_id="O1",
            exposure_type=ExposureType.LETTER_OF_CREDIT,
            outstanding_kes=Decimal("500000"),
            limit_kes=Decimal("1000000"))
        # 500K + 500K × 0.5 = 750K
        self.assertEqual(e.credit_equivalent_kes(), Decimal("750000"))

    def test_large_exposure_flag_at_10pct(self):
        from utils.group_exposure import (
            Obligor, Exposure, ExposureType, assess_group_exposure)
        obligors = [Obligor(obligor_id="X", name="Test", is_individual=False)]
        exposures = [Exposure(
            exposure_id="E1", obligor_id="X",
            exposure_type=ExposureType.LOAN_TERM,
            outstanding_kes=Decimal("100000000"),
            limit_kes=Decimal("100000000"))]
        r = assess_group_exposure(
            obligor_id="X", obligors=obligors, exposures=exposures,
            core_capital_kes=Decimal("1000000000"))    # exactly 10%
        self.assertTrue(r.is_large_exposure)


class TestV1015Coexistence(unittest.TestCase):
    def test_all_v10_11_to_v10_15_engines_coexist(self):
        from utils.ai_underwriting import AIUnderwritingEngine
        from utils.applicant_data_sources import ApplicantDataAggregator
        from utils.credit_workflow import CreditWorkflowEngine
        from utils.portfolio_monitoring import PortfolioMonitoringEngine
        from utils.document_management import DocumentManagementEngine
        from utils.group_exposure import GroupExposureEngine
        engines = [
            AIUnderwritingEngine(entity_name="X"),
            ApplicantDataAggregator(entity_name="X"),
            CreditWorkflowEngine(entity_name="X"),
            PortfolioMonitoringEngine(entity_name="X"),
            DocumentManagementEngine(entity_name="X"),
            GroupExposureEngine(),
        ]
        for e in engines:
            self.assertTrue(hasattr(e, "entity_name") or hasattr(e, "_obligors"))


if __name__ == "__main__":
    unittest.main()
