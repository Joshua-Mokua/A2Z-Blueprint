"""tests/test_volume_six_batch.py — Standards #41-#42 (v5.53).

Coverage:
  Standard #41 — Dormancy Intelligence
                  (Cat B status engine + Cat D prediction with Rule 7)
  Standard #42 — EDMS Intelligence
                  (Cat A schema + Cat C workflow with legal-hold honesty)

Plus one artifact-handoff harness:
  test_dormancy_classification_correctness_meets_99_percent →
    dormancy_classification_results.json (G51)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


# ═══════════════════════════════════════════════════════════════════════
# Standard #41 — Dormancy Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard41Status:
    """Cat B status engine."""

    def test_module_exists(self):
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine()
        assert hasattr(eng, "analyze_dormancy_risk")
        assert hasattr(eng, "predict_dormancy")
        assert hasattr(eng, "classify_account")

    def test_spec_literal_thresholds(self):
        """CBK regulation thresholds byte-for-byte."""
        from utils.dormancy_intelligence import (
            WARNING_THRESHOLD_DAYS, DORMANCY_THRESHOLD_DAYS, RESTRICTED_THRESHOLD_DAYS,
        )
        assert WARNING_THRESHOLD_DAYS == 300
        assert DORMANCY_THRESHOLD_DAYS == 365
        assert RESTRICTED_THRESHOLD_DAYS == 730

    def test_status_enum(self):
        from utils.dormancy_intelligence import (
            ALL_STATUSES, STATUS_ACTIVE, STATUS_WARNING, STATUS_DORMANT, STATUS_RESTRICTED,
        )
        assert ALL_STATUSES == ["ACTIVE", "WARNING", "DORMANT", "RESTRICTED"]

    def test_classification_at_thresholds(self):
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine()
        # Just under warning
        r = eng.classify_account({"last_transaction_date": "2025-07-04"}, "2026-04-29")
        assert r["status"] == "ACTIVE"
        # At warning
        r = eng.classify_account({"last_transaction_date": "2025-07-03"}, "2026-04-29")
        assert r["status"] == "WARNING"
        # At dormancy
        r = eng.classify_account({"last_transaction_date": "2025-04-29"}, "2026-04-29")
        assert r["status"] == "DORMANT"
        # At restricted
        r = eng.classify_account({"last_transaction_date": "2024-04-29"}, "2026-04-29")
        assert r["status"] == "RESTRICTED"

    def test_missing_date_classifies_active_with_note(self):
        """Rule 6 — no escalation without observable signal."""
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine(account_lookup_fn=lambda: [{"account_number": "X1"}])
        r = eng.analyze_dormancy_risk("2026-04-29")
        assert r["summary"]["active"] == 1
        assert r["active"][0]["_data_quality_note"] == "no_last_transaction_date"

    def test_summary_counts(self):
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        accounts = [
            {"account_number": "A1", "last_transaction_date": "2026-04-15"},  # ACTIVE
            {"account_number": "A2", "last_transaction_date": "2025-07-03"},  # WARNING (300d)
            {"account_number": "A3", "last_transaction_date": "2025-04-29"},  # DORMANT (365d)
            {"account_number": "A4", "last_transaction_date": "2024-04-29"},  # RESTRICTED (730d)
        ]
        eng = DormancyIntelligenceEngine(account_lookup_fn=lambda: accounts)
        r = eng.analyze_dormancy_risk("2026-04-29")
        assert r["summary"]["active"]     == 1
        assert r["summary"]["warning"]    == 1
        assert r["summary"]["dormant"]    == 1
        assert r["summary"]["restricted"] == 1

    def test_days_to_dormancy_field(self):
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine()
        r = eng.classify_account({"last_transaction_date": "2025-07-03"}, "2026-04-29")
        # 300 days inactive → 65 days to dormancy
        assert r["days_to_dormancy"] == 65


class TestStandard41Prediction:
    """Cat D prediction with Rule 7 scaffolding."""

    def test_no_model_loaded_returns_ml_score_none(self):
        """Rule 7 — refuse to predict when no ML model loaded."""
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine(feature_lookup_fn=lambda an: {
            "balance_decline_pct": 0.5, "days_since_last_tx": 60,
            "digital_adoption_score": 0.1, "product_type": "SAVINGS",
            "age_segment": "YOUTH",
        })
        r = eng.predict_dormancy("A001")
        assert r["ml_score"] is None
        assert r["ml_level"] is None
        assert r["reason"] == "no_ml_model_loaded"

    def test_no_model_returns_rule_based_score_separately(self):
        """Rule 7 — rule-based fallback surfaced separately, not silently substituted."""
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine(feature_lookup_fn=lambda an: {
            "balance_decline_pct": 0.5, "days_since_last_tx": 60,
            "digital_adoption_score": 0.1, "product_type": "SAVINGS",
            "age_segment": "YOUTH",
        })
        r = eng.predict_dormancy("A001")
        # All 5 components fire → score = 30+25+20+15+10 = 100
        assert r["rule_based_score"] == 100
        assert r["rule_based_level"] == "HIGH"

    def test_no_model_surfaces_spec_deviation(self):
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        eng = DormancyIntelligenceEngine(feature_lookup_fn=lambda an: {})
        r = eng.predict_dormancy("A001")
        assert r["meta"]["spec_deviation"] is not None
        assert "downstream work" in r["meta"]["spec_deviation"]

    def test_rule_based_is_deterministic(self):
        """Rule 7 — rule-based fallback is deterministic."""
        from utils.dormancy_intelligence import DormancyIntelligenceEngine
        features = {"balance_decline_pct": 0.4, "days_since_last_tx": 50}
        eng = DormancyIntelligenceEngine(feature_lookup_fn=lambda an: features)
        r1 = eng.predict_dormancy("A001")
        r2 = eng.predict_dormancy("A001")
        assert r1["rule_based_score"] == r2["rule_based_score"]

    def test_ml_model_loaded_returns_basis_ml(self):
        """When ML model injected, ml_score is set."""
        from utils.dormancy_intelligence import DormancyIntelligenceEngine

        class FakeModel:
            def predict(self, features):
                return 75.0

        eng = DormancyIntelligenceEngine(
            feature_lookup_fn=lambda an: {},
            model_loader_fn=lambda: FakeModel(),
        )
        r = eng.predict_dormancy("A001")
        assert r["ml_score"] == 75.0
        assert r["ml_level"] == "HIGH"
        assert r["reason"] is None
        assert r["meta"]["spec_deviation"] is None
        # rule_based still computed for comparison
        assert "rule_based_score" in r

    def test_ml_failure_falls_back_with_explicit_reason(self):
        """ML error → fallback with explicit reason in meta."""
        from utils.dormancy_intelligence import DormancyIntelligenceEngine

        class FailModel:
            def predict(self, features):
                raise ValueError("model corrupted")

        eng = DormancyIntelligenceEngine(
            feature_lookup_fn=lambda an: {},
            model_loader_fn=lambda: FailModel(),
        )
        r = eng.predict_dormancy("A001")
        assert r["ml_score"] is None
        assert "ml_model_error" in r["reason"]
        assert "ValueError" in r["reason"]


class TestStandard41Schema:
    """Cat A schema verification."""

    def test_schema_has_all_required_columns(self):
        from utils.dormancy_intelligence import build_schema_ddl, ddl_contains_required_columns
        ddl = build_schema_ddl()
        missing = ddl_contains_required_columns(ddl)
        for table, cols in missing.items():
            assert cols == [], f"{table} missing columns: {cols}"

    def test_schema_has_three_tables(self):
        from utils.dormancy_intelligence import build_schema_ddl
        ddl = build_schema_ddl()
        assert "customer.account_dormancy" in ddl
        assert "customer.dormancy_actions" in ddl
        assert "performance.dormancy_kpi_targets" in ddl


# ═══════════════════════════════════════════════════════════════════════
# Standard #42 — EDMS Intelligence
# ═══════════════════════════════════════════════════════════════════════

class TestStandard42Schema:
    """Cat A schema verification."""

    def test_schema_has_all_required_columns(self):
        from utils.edms import build_schema_ddl, ddl_contains_required_columns
        ddl = build_schema_ddl()
        missing = ddl_contains_required_columns(ddl)
        for table, cols in missing.items():
            assert cols == [], f"{table} missing columns: {cols}"

    def test_schema_has_three_tables(self):
        from utils.edms import build_schema_ddl
        ddl = build_schema_ddl()
        assert "document.records" in ddl
        assert "document.access_log" in ddl
        assert "document.retention_policies" in ddl


class TestStandard42Catalogs:
    """Spec literal catalog preservation."""

    def test_classifications(self):
        from utils.edms import CLASSIFICATIONS
        assert CLASSIFICATIONS == ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]

    def test_default_retention_8_types(self):
        from utils.edms import DEFAULT_RETENTION
        expected = {"LOAN_APPLICATION", "KYC", "CONTRACT", "AUDIT_REPORT",
                    "REGULATORY_REPORT", "TRANSACTION_LOG", "EMAIL_BUSINESS", "INTERNAL_MEMO"}
        assert set(DEFAULT_RETENTION.keys()) == expected
        # Spec values byte-for-byte
        assert DEFAULT_RETENTION["LOAN_APPLICATION"]   == 10
        assert DEFAULT_RETENTION["KYC"]                ==  7
        assert DEFAULT_RETENTION["CONTRACT"]           == 15
        assert DEFAULT_RETENTION["AUDIT_REPORT"]       == 10
        assert DEFAULT_RETENTION["REGULATORY_REPORT"]  == 10
        assert DEFAULT_RETENTION["TRANSACTION_LOG"]    ==  7
        assert DEFAULT_RETENTION["EMAIL_BUSINESS"]     ==  5
        assert DEFAULT_RETENTION["INTERNAL_MEMO"]      ==  3

    def test_deletion_methods(self):
        from utils.edms import DELETION_METHODS
        assert DELETION_METHODS == ["HARD_DELETE", "SOFT_DELETE", "ARCHIVE"]


class TestStandard42Workflow:
    """Cat C workflow honesty rules."""

    def _eng(self):
        from utils.edms import EDMSEngine
        return EDMSEngine()

    def test_upload_known_type_uses_spec_retention(self):
        eng = self._eng()
        r = eng.upload_document(
            file_meta={"file_hash_sha256": "x"},
            classification="CONFIDENTIAL",
            document_type="LOAN_APPLICATION",
            uploader="staff_001",
        )
        assert r["success"] is True
        assert r["retention_years"] == 10
        assert r["used_default_retention"] is False

    def test_upload_unknown_type_uses_fallback(self):
        eng = self._eng()
        r = eng.upload_document(
            file_meta={"file_hash_sha256": "x"},
            classification="INTERNAL",
            document_type="UNKNOWN_TYPE_XYZ",
            uploader="staff_001",
        )
        assert r["success"] is True
        assert r["used_default_retention"] is True
        assert r["retention_years"] == 7    # DEFAULT_FALLBACK_RETENTION_YEARS

    def test_upload_invalid_classification_rejected(self):
        eng = self._eng()
        r = eng.upload_document(
            file_meta={}, classification="WEIRD", document_type="KYC", uploader="x",
        )
        assert r["success"] is False
        assert "invalid classification" in r["error"]

    def test_access_unknown_doc_returns_not_found(self):
        eng = self._eng()
        r = eng.access_document("DOC_DOES_NOT_EXIST", "user_x", "VIEW")
        assert r["granted"] is False
        assert r["reason"] == "not_found"

    def test_access_invalid_type_rejected(self):
        eng = self._eng()
        r = eng.access_document("ANY", "user_x", "TELEPORT")
        assert r["granted"] is False
        assert "invalid access_type" in r["reason"]

    def test_access_logs_every_attempt(self):
        eng = self._eng()
        initial = len(eng._access_log)
        eng.access_document("X", "user_a", "VIEW")
        eng.access_document("Y", "user_b", "DOWNLOAD")
        assert len(eng._access_log) == initial + 2

    def test_legal_hold_blocks_modify(self):
        """Rule 4 — legal hold ALWAYS wins over MODIFY/DELETE."""
        eng = self._eng()
        upload = eng.upload_document(
            file_meta={"file_hash_sha256": "z"},
            classification="CONFIDENTIAL",
            document_type="CONTRACT",
            uploader="staff_001",
        )
        doc_id = upload["document_id"]
        eng.place_legal_hold(doc_id, "Lawsuit", "legal_team")
        r = eng.access_document(doc_id, "manager_001", "DELETE")
        assert r["granted"] is False
        assert r["reason"] == "legal_hold_active"

    def test_legal_hold_permits_view(self):
        """Read-only access is OK during legal hold (preserves accessibility)."""
        eng = self._eng()
        upload = eng.upload_document(
            file_meta={"file_hash_sha256": "z"},
            classification="CONFIDENTIAL",
            document_type="CONTRACT",
            uploader="staff_001",
        )
        eng.place_legal_hold(upload["document_id"], "Hold", "legal")
        r = eng.access_document(upload["document_id"], "manager", "VIEW")
        assert r["granted"] is True

    def test_expiry_skips_legal_hold_documents(self):
        """Rule 4 — legal hold ALWAYS protects from expiry."""
        eng = self._eng()
        eng._records["DOC_HELD"] = {
            "document_id":    "DOC_HELD",
            "document_type":  "EMAIL_BUSINESS",
            "retention_until": "2020-01-01",   # past
            "legal_hold":     True,
            "archived":       False,
            "deleted_at":     None,
        }
        r = eng.expire_documents_past_retention(dry_run=False, as_of_date="2026-04-29")
        assert r["summary"]["skipped_legal_hold"] == 1
        assert r["summary"]["deleted"] == 0
        assert r["summary"]["archived"] == 0
        # Document state unchanged
        assert eng._records["DOC_HELD"]["legal_hold"] is True
        assert eng._records["DOC_HELD"]["archived"] is False

    def test_expiry_archives_default_method(self):
        eng = self._eng()
        eng._records["DOC_FREE"] = {
            "document_id":    "DOC_FREE",
            "document_type":  "EMAIL_BUSINESS",
            "retention_until": "2020-01-01",
            "legal_hold":     False,
            "archived":       False,
            "deleted_at":     None,
        }
        r = eng.expire_documents_past_retention(dry_run=False, as_of_date="2026-04-29")
        assert r["summary"]["archived"] == 1
        assert eng._records["DOC_FREE"]["archived"] is True

    def test_dry_run_does_not_modify(self):
        """Rule 4 — default-strict; dry_run=True computes actions but doesn't apply."""
        eng = self._eng()
        eng._records["DOC_DRY"] = {
            "document_id":    "DOC_DRY",
            "document_type":  "EMAIL_BUSINESS",
            "retention_until": "2020-01-01",
            "legal_hold":     False,
            "archived":       False,
            "deleted_at":     None,
        }
        r = eng.expire_documents_past_retention(dry_run=True, as_of_date="2026-04-29")
        assert r["summary"]["archived"] == 1    # would archive
        assert eng._records["DOC_DRY"]["archived"] is False    # but didn't


# ═══════════════════════════════════════════════════════════════════════
# G51 harness — Dormancy Classification correctness
# ═══════════════════════════════════════════════════════════════════════

def test_dormancy_classification_correctness_meets_99_percent():
    """Run all DI fixtures and produce dormancy_classification_results.json (G51)."""
    from utils.dormancy_intelligence import DormancyIntelligenceEngine

    fixtures_path = FIXTURES_DIR / "dormancy_classification_scenarios.json"
    assert fixtures_path.exists(), f"fixtures missing: {fixtures_path}"

    with open(fixtures_path) as f:
        data = json.load(f)
    fixtures = data["fixtures"]

    eng = DormancyIntelligenceEngine()
    results = []
    matches = 0
    total = len(fixtures)

    for fx in fixtures:
        r = eng.classify_account(fx["account"], fx["as_of_date"])
        exp = fx["expected"]
        ok = (
            r.get("status")           == exp["status"]
            and r.get("days_inactive")    == exp["days_inactive"]
            and r.get("days_to_dormancy") == exp["days_to_dormancy"]
        )
        if ok:
            matches += 1
        results.append({
            "id":     fx["id"],
            "label":  fx["label"],
            "matched": ok,
            "diffs": [] if ok else [
                f"status={r.get('status')} expected {exp['status']}",
                f"days_inactive={r.get('days_inactive')} expected {exp['days_inactive']}",
                f"days_to_dormancy={r.get('days_to_dormancy')} expected {exp['days_to_dormancy']}",
            ],
        })

    accuracy = (matches / total * 100) if total > 0 else 0
    artifact = {
        "total_scenarios":  total,
        "correct":          matches,
        "accuracy_pct":     accuracy,
        "spec_target_pct":  99.0,
        "results":          results,
        # Diagnostic fields
        "fixtures_total":   total,
        "fixtures_matched": matches,
        "match_rate_pct":   accuracy,
    }

    out_path = ROOT / "dormancy_classification_results.json"
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2)

    assert accuracy >= 99.0, \
        f"dormancy classification correctness {accuracy:.1f}% < 99%; see {out_path}"
