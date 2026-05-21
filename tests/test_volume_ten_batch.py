"""
================================================================================
A2Z MIS 360 — Volume Ten Batch Tests (Standards #57-#60 Compliance Intelligence)
================================================================================

Tests Standards #57 KYC/AML Risk Scoring, #58 Sanctions Screening,
#59 Transaction Monitoring, #60 FATCA/CRS Reporting.

Run via:
    pytest tests/test_volume_ten_batch.py -v

Total: 55 unit tests covering deterministic classification, fuzzy matching,
       rule-based AML detection, and FATCA/CRS reportable-status logic.
================================================================================
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover
    pytest = None  # type: ignore

from utils.kyc_aml_risk import (
    KycAmlRiskEngine, KycRiskAssessment,
    PROHIBITED_JURISDICTIONS, HIGH_RISK_JURISDICTIONS, MEDIUM_RISK_JURISDICTIONS,
    PRODUCT_PTS, CUSTOMER_TYPE_PTS, CHANNEL_PTS,
    RISK_BAND_LOW_MAX, RISK_BAND_MEDIUM_MAX, RISK_BAND_HIGH_MAX, RISK_BAND_PROHIBITED_MIN,
    CDD_LEVEL_BY_BAND,
)
from utils.sanctions_screening import (
    SanctionsScreeningEngine, SanctionsRecord, ScreeningHit,
    SUPPORTED_SANCTIONS_LISTS, ALLOWED_TRANSITIONS,
    HIT_STATUS_NEW, HIT_STATUS_UNDER_REVIEW, HIT_STATUS_CLEARED_FALSE, HIT_STATUS_CONFIRMED_TRUE,
    SCREENING_HIT_THRESHOLD, fuzzy_match_score,
    SCHEMA_SANCTIONS_LIST_TABLE, SCHEMA_SANCTIONS_RECORD_TABLE, SCHEMA_SCREENING_RESULT_TABLE,
)
from utils.transaction_monitoring import (
    TransactionMonitoringEngine, Transaction, Alert,
    CASH_REPORTING_THRESHOLD_KES, STRUCTURING_LOWER_KES, STRUCTURING_UPPER_KES,
    STRUCTURING_MIN_COUNT, STRUCTURING_WINDOW_DAYS, RAPID_MOVEMENT_THRESHOLD_KES,
    RULE_CATALOG, ALLOWED_ALERT_TRANSITIONS,
    ALERT_STATUS_OPEN, ALERT_STATUS_INVESTIGATING, ALERT_STATUS_SAR_FILED, ALERT_STATUS_DISMISSED,
    SEVERITY_HIGH, SEVERITY_CRITICAL,
    _to_decimal as txn_decimal, _parse_dt,
)
from utils.fatca_crs import (
    FatcaCrsReportingEngine, SelfCertification, AccountBalance, ReportableSnapshot,
    FATCA_INDIVIDUAL_THRESHOLD_USD, FATCA_ENTITY_THRESHOLD_USD,
    CRS_PARTICIPATING_JURISDICTIONS, HOME_JURISDICTION,
    STATUS_REPORTABLE_FATCA, STATUS_REPORTABLE_CRS, STATUS_REPORTABLE_BOTH,
    STATUS_NOT_REPORTABLE, STATUS_UNDOCUMENTED, FATCA_FORM,
    SCHEMA_SELF_CERT_TABLE, SCHEMA_REPORTABLE_TABLE, SCHEMA_SUBMISSION_TABLE,
    SPEC_DEVIATION_NOTE as FATCA_CRS_SPEC_DEVIATION_NOTE,
)


# ============================================================================
# #57 KYC/AML Risk Scoring (12 tests)
# ============================================================================

class TestKycAmlRiskScoring:

    def test_low_risk_local_individual(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({
            "customer_id": "C1", "country_code": "KE", "citizenship_code": "KE",
            "products": ["SAVINGS"], "customer_type": "INDIVIDUAL_LOCAL",
            "onboarding_channel": "FACE_TO_FACE_BRANCH",
        })
        assert a.risk_band == "LOW"
        assert a.cdd_level == "SIMPLIFIED_DUE_DILIGENCE"
        assert not a.auto_prohibited

    def test_band_thresholds(self):
        assert RISK_BAND_LOW_MAX == 19
        assert RISK_BAND_MEDIUM_MAX == 49
        assert RISK_BAND_HIGH_MAX == 79
        assert RISK_BAND_PROHIBITED_MIN == 80

    def test_prohibited_jurisdictions_byte_for_byte(self):
        assert "KP" in PROHIBITED_JURISDICTIONS
        assert "IR" in PROHIBITED_JURISDICTIONS

    def test_high_risk_jurisdictions_byte_for_byte(self):
        for cc in ("AF", "MM", "SY", "YE", "SS"):
            assert cc in HIGH_RISK_JURISDICTIONS

    def test_pep_foreign_high_risk(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({
            "customer_id": "C2", "country_code": "KE", "citizenship_code": "PK",
            "products": ["PRIVATE_BANKING"], "customer_type": "PEP_FOREIGN",
            "onboarding_channel": "INTRODUCED_THIRD_PARTY", "pep_flag": True,
        })
        assert a.risk_band == "HIGH"
        assert a.cdd_level == "ENHANCED_DUE_DILIGENCE"

    def test_prohibited_jurisdiction_auto_prohibits(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({"customer_id": "C3", "country_code": "KP",
                               "customer_type": "INDIVIDUAL_LOCAL"})
        assert a.risk_band == "PROHIBITED"
        assert a.auto_prohibited

    def test_sanctions_hit_auto_prohibits(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({"customer_id": "C4", "country_code": "KE",
                               "sanctions_hit": True, "customer_type": "INDIVIDUAL_LOCAL"})
        assert a.risk_band == "PROHIBITED"
        assert a.sanctions_flag
        assert a.auto_prohibited_reason == "sanctions_list_hit"

    def test_rule6_missing_country(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({"customer_id": "C5", "country_code": None,
                               "customer_type": "INDIVIDUAL_LOCAL"})
        assert a.component_scores["geography"] >= 15

    def test_rule6_unknown_product(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({"customer_id": "C6", "country_code": "KE",
                               "products": ["WEIRD_PRODUCT"], "customer_type": "CORPORATE_PRIVATE"})
        assert a.component_scores["product"] >= 5

    def test_band_boundaries(self):
        e = KycAmlRiskEngine()
        a1 = e.assess_customer({"customer_id": "B1", "country_code": "TR",
                                "customer_type": "INDIVIDUAL_LOCAL", "onboarding_channel": "FACE_TO_FACE_BRANCH"})
        assert a1.risk_score == 15 and a1.risk_band == "LOW"

    def test_pep_flag_bumps_score(self):
        e = KycAmlRiskEngine()
        a = e.assess_customer({"customer_id": "C7", "country_code": "KE",
                               "products": ["SAVINGS"], "customer_type": "INDIVIDUAL_LOCAL",
                               "pep_flag": True, "onboarding_channel": "FACE_TO_FACE_BRANCH"})
        assert a.component_scores["customer_type"] >= 20

    def test_portfolio_summary(self):
        e = KycAmlRiskEngine()
        aa = [
            e.assess_customer({"customer_id": "P1", "country_code": "KE", "customer_type": "INDIVIDUAL_LOCAL"}),
            e.assess_customer({"customer_id": "P2", "country_code": "KP", "customer_type": "INDIVIDUAL_LOCAL"}),
        ]
        s = KycAmlRiskEngine.portfolio_risk_summary(aa)
        assert s["total_customers"] == 2
        assert s["auto_prohibited_count"] == 1


# ============================================================================
# #58 Sanctions Screening (13 tests)
# ============================================================================

def _records():
    return [
        SanctionsRecord(record_id=1, list_id="OFAC_SDN", entity_name="John Smuggler", aliases=["J Smuggler"]),
        SanctionsRecord(record_id=2, list_id="UN_CONSOLIDATED", entity_name="ABC Terror Front"),
        SanctionsRecord(record_id=3, list_id="EU_CONSOLIDATED", entity_name="Maria Sanctioned"),
    ]


class TestSanctionsScreening:

    def test_supported_lists(self):
        for lst in ("OFAC_SDN", "UN_CONSOLIDATED", "EU_CONSOLIDATED", "UK_HMT", "CBK_DOMESTIC"):
            assert lst in SUPPORTED_SANCTIONS_LISTS

    def test_exact_match_creates_hit(self):
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C1", "John Smuggler")
        assert len(hits) == 1
        assert hits[0].match_score == 100
        assert hits[0].hit_status == HIT_STATUS_NEW

    def test_alias_match(self):
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C2", "J Smuggler")
        assert len(hits) == 1
        assert hits[0].matched_entity_name == "J Smuggler"

    def test_fuzzy_threshold(self):
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C3", "Maria Sanctionned")
        assert len(hits) == 1
        assert hits[0].match_score >= SCREENING_HIT_THRESHOLD

    def test_no_match_below_threshold(self):
        eng = SanctionsScreeningEngine(_records())
        assert eng.screen("C4", "Unrelated Name") == []

    def test_workflow_default_strict_no_auto_clear(self):
        """Rule 4: cannot directly clear NEW_HIT."""
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C5", "John Smuggler")
        ok, reason = eng.transition_hit(hits[0].screening_id, HIT_STATUS_CLEARED_FALSE, "off1", "fp")
        assert not ok
        assert "transition_not_allowed" in reason

    def test_workflow_normal_path(self):
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C6", "John Smuggler")
        sid = hits[0].screening_id
        assert eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "off1")[0]
        assert eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "off1", "different_dob")[0]

    def test_clearance_requires_reason(self):
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C7", "John Smuggler")
        sid = hits[0].screening_id
        eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "off1")
        ok, reason = eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "off1", None)
        assert not ok
        assert "clearance_reason_required" in reason

    def test_terminal_state_immutable(self):
        eng = SanctionsScreeningEngine(_records())
        hits = eng.screen("C8", "John Smuggler")
        sid = hits[0].screening_id
        eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "off1")
        eng.transition_hit(sid, HIT_STATUS_CONFIRMED_TRUE, "off1", "verified")
        ok, _ = eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "off1", "oops")
        assert not ok

    def test_transition_table_completeness(self):
        for status in (HIT_STATUS_NEW, HIT_STATUS_UNDER_REVIEW, HIT_STATUS_CLEARED_FALSE, HIT_STATUS_CONFIRMED_TRUE):
            assert status in ALLOWED_TRANSITIONS
        # Terminal states have no successors
        assert ALLOWED_TRANSITIONS[HIT_STATUS_CLEARED_FALSE] == ()
        assert ALLOWED_TRANSITIONS[HIT_STATUS_CONFIRMED_TRUE] == ()

    def test_unknown_list_filtered(self):
        bad = SanctionsRecord(record_id=99, list_id="FAKE", entity_name="X")
        eng = SanctionsScreeningEngine([bad] + _records())
        s = eng.screening_summary()
        assert s["total_records"] == 3

    def test_fuzzy_match_score_function(self):
        assert fuzzy_match_score("abc", "abc") == 100
        assert fuzzy_match_score("", "abc") == 0
        assert fuzzy_match_score("hello", "world") < 50

    def test_schema_definitions(self):
        for sch in (SCHEMA_SANCTIONS_LIST_TABLE, SCHEMA_SANCTIONS_RECORD_TABLE, SCHEMA_SCREENING_RESULT_TABLE):
            assert "table" in sch and "columns" in sch
            assert "PRIMARY KEY" in sch["columns"][0][1]


# ============================================================================
# #59 Transaction Monitoring (14 tests)
# ============================================================================

def _txn(**kw):
    return Transaction(
        txn_id=kw.pop("txn_id", "T1"),
        customer_id=kw.pop("customer_id", "C1"),
        account_id=kw.pop("account_id", "A1"),
        amount_kes=txn_decimal(kw.pop("amount_kes", 100000)),
        txn_type=kw.pop("txn_type", "TRANSFER"),
        txn_datetime=_parse_dt(kw.pop("txn_datetime", "2026-01-01T10:00:00+00:00")),
        counterparty_country=kw.pop("counterparty_country", None),
        counterparty_name=kw.pop("counterparty_name", None),
        direction=kw.pop("direction", "DEBIT"),
        customer_pep=kw.pop("customer_pep", False),
        account_dormant=kw.pop("account_dormant", False),
    )


class TestTransactionMonitoring:

    def test_cbk_threshold_byte_for_byte(self):
        assert CASH_REPORTING_THRESHOLD_KES == Decimal("1000000")

    def test_structuring_thresholds_byte_for_byte(self):
        assert STRUCTURING_LOWER_KES == Decimal("800000")
        assert STRUCTURING_UPPER_KES == Decimal("999999")
        assert STRUCTURING_MIN_COUNT == 3
        assert STRUCTURING_WINDOW_DAYS == 7

    def test_r1_cash_threshold_breach(self):
        eng = TransactionMonitoringEngine()
        alerts = eng.scan([_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
        assert any(a.rule_id == "R1" for a in alerts)

    def test_r1_no_alert_at_exact_threshold(self):
        """Rule 1 precision: equal to threshold does NOT trigger (strict >)."""
        eng = TransactionMonitoringEngine()
        alerts = eng.scan([_txn(amount_kes=Decimal("1000000"), txn_type="CASH_DEPOSIT")])
        assert not any(a.rule_id == "R1" for a in alerts)

    def test_r2_structuring(self):
        eng = TransactionMonitoringEngine()
        txns = [
            _txn(txn_id=f"T{i}", customer_id="C1", txn_type="CASH_DEPOSIT",
                 amount_kes=900000, txn_datetime=f"2026-01-0{i}T10:00:00+00:00")
            for i in range(1, 5)
        ]
        alerts = eng.scan(txns)
        assert any(a.rule_id == "R2" for a in alerts)

    def test_r3_rapid_movement(self):
        eng = TransactionMonitoringEngine()
        txns = [
            _txn(txn_id="T1", amount_kes=6000000, direction="CREDIT",
                 txn_datetime="2026-01-01T10:00:00+00:00"),
            _txn(txn_id="T2", amount_kes=6000000, direction="DEBIT",
                 txn_datetime="2026-01-02T10:00:00+00:00"),
        ]
        alerts = eng.scan(txns)
        assert any(a.rule_id == "R3" for a in alerts)

    def test_r4_prohibited_jurisdiction(self):
        eng = TransactionMonitoringEngine()
        alerts = eng.scan([_txn(txn_type="WIRE_OUT", counterparty_country="KP", amount_kes=50000)])
        r4 = [a for a in alerts if a.rule_id == "R4"]
        assert len(r4) == 1
        assert r4[0].severity == SEVERITY_CRITICAL

    def test_r5_dormant_activity(self):
        eng = TransactionMonitoringEngine()
        alerts = eng.scan([_txn(amount_kes=200000, account_dormant=True, txn_type="CASH_DEPOSIT")])
        assert any(a.rule_id == "R5" for a in alerts)

    def test_r7_velocity(self):
        eng = TransactionMonitoringEngine()
        txns = [_txn(txn_id=f"T{i}", amount_kes=50000,
                     txn_datetime=f"2026-01-01T{i:02d}:00:00+00:00") for i in range(0, 22)]
        alerts = eng.scan(txns)
        assert any(a.rule_id == "R7" for a in alerts)

    def test_r8_pep_large(self):
        eng = TransactionMonitoringEngine()
        alerts = eng.scan([_txn(amount_kes=2500000, customer_pep=True, txn_type="WIRE_OUT")])
        assert any(a.rule_id == "R8" for a in alerts)

    def test_workflow_no_auto_dismiss(self):
        eng = TransactionMonitoringEngine()
        eng.scan([_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
        aid = eng._alerts[0].alert_id
        ok, reason = eng.transition_alert(aid, ALERT_STATUS_DISMISSED, "off1", "false_pos")
        assert not ok
        assert "transition_not_allowed" in reason

    def test_workflow_normal_path(self):
        eng = TransactionMonitoringEngine()
        eng.scan([_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
        aid = eng._alerts[0].alert_id
        assert eng.transition_alert(aid, ALERT_STATUS_INVESTIGATING, "off1")[0]
        assert eng.transition_alert(aid, ALERT_STATUS_DISMISSED, "off1", "documented")[0]

    def test_rule_catalog_completeness(self):
        for rid in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"):
            assert rid in RULE_CATALOG
            assert "name" in RULE_CATALOG[rid]
            assert "severity" in RULE_CATALOG[rid]

    def test_alert_summary(self):
        eng = TransactionMonitoringEngine()
        eng.scan([_txn(amount_kes=1500000, txn_type="CASH_DEPOSIT")])
        s = eng.alert_summary()
        assert s["total_alerts"] >= 1
        assert s["open_alerts"] >= 1


# ============================================================================
# #60 FATCA/CRS Reporting (16 tests)
# ============================================================================

class TestFatcaCrsReporting:

    def test_fatca_thresholds_byte_for_byte(self):
        assert FATCA_INDIVIDUAL_THRESHOLD_USD == Decimal("50000")
        assert FATCA_ENTITY_THRESHOLD_USD == Decimal("250000")
        assert FATCA_FORM == "8966"

    def test_us_person_individual_above_threshold(self):
        cert = SelfCertification(customer_id="C1", us_person=True, us_tin="X", certification_date="2025-01-01")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C1", "A1", Decimal("75000"))], {"C1": cert}
        )
        assert snaps[0].status == STATUS_REPORTABLE_FATCA

    def test_us_person_below_threshold_not_reportable(self):
        cert = SelfCertification(customer_id="C2", us_person=True, us_tin="X", certification_date="2025-01-01")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C2", "A1", Decimal("40000"))], {"C2": cert}
        )
        assert snaps[0].status == STATUS_NOT_REPORTABLE

    def test_crs_jurisdiction_reportable(self):
        cert = SelfCertification(customer_id="C3", us_person=False, tax_residences=["GB"],
                                 certification_date="2025-01-01")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C3", "A1", Decimal("10000"))], {"C3": cert}
        )
        assert snaps[0].status == STATUS_REPORTABLE_CRS
        assert "GB" in snaps[0].crs_jurisdictions

    def test_kenya_resident_not_reportable(self):
        cert = SelfCertification(customer_id="C4", us_person=False, tax_residences=["KE"],
                                 certification_date="2025-01-01")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C4", "A1", Decimal("5000000"))], {"C4": cert}
        )
        assert snaps[0].status == STATUS_NOT_REPORTABLE

    def test_both_fatca_and_crs(self):
        cert = SelfCertification(customer_id="C5", us_person=True, us_tin="X",
                                 tax_residences=["DE"], certification_date="2025-01-01")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C5", "A1", Decimal("100000"))], {"C5": cert}
        )
        assert snaps[0].status == STATUS_REPORTABLE_BOTH

    def test_rule6_undocumented(self):
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C6", "A1", Decimal("100000"))], {}
        )
        assert snaps[0].status == STATUS_UNDOCUMENTED

    def test_inactive_cert_undocumented(self):
        cert = SelfCertification(customer_id="C7", us_person=True, active=False)
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C7", "A1", Decimal("100000"))], {"C7": cert}
        )
        assert snaps[0].status == STATUS_UNDOCUMENTED

    def test_balance_aggregation(self):
        cert = SelfCertification(customer_id="C8", us_person=True, us_tin="X")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025",
            [AccountBalance("C8", "A1", Decimal("30000")), AccountBalance("C8", "A2", Decimal("25000"))],
            {"C8": cert},
        )
        assert snaps[0].aggregated_balance_usd == Decimal("55000")
        assert snaps[0].status == STATUS_REPORTABLE_FATCA

    def test_entity_threshold(self):
        cert = SelfCertification(customer_id="E1", us_person=True, us_tin="X",
                                 entity_type="ENTITY")
        # 100k entity - below 250k threshold
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("E1", "A1", Decimal("100000"), entity_type="ENTITY")],
            {"E1": cert},
        )
        assert snaps[0].status == STATUS_NOT_REPORTABLE
        # 300k entity - above
        snaps2 = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("E1", "A1", Decimal("300000"), entity_type="ENTITY")],
            {"E1": cert},
        )
        assert snaps2[0].status == STATUS_REPORTABLE_FATCA

    def test_decimal_precision_strict_threshold(self):
        cert = SelfCertification(customer_id="C9", us_person=True, us_tin="X")
        # Exactly 50000 - NOT reportable (strict greater-than)
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("C9", "A1", Decimal("50000.00"))], {"C9": cert}
        )
        assert snaps[0].status == STATUS_NOT_REPORTABLE

    def test_payload_skeleton_fatca(self):
        cert = SelfCertification(customer_id="X1", us_person=True, us_tin="X")
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("X1", "A1", Decimal("100000"))], {"X1": cert}
        )
        p = FatcaCrsReportingEngine.build_payload_skeleton(snaps, "FATCA")
        assert p["regime"] == "FATCA"
        assert p["form"] == "8966"
        assert p["submitter_jurisdiction"] == HOME_JURISDICTION

    def test_payload_skeleton_crs(self):
        cert = SelfCertification(customer_id="X2", tax_residences=["FR"])
        snaps = FatcaCrsReportingEngine.build_period_snapshot(
            "2025", [AccountBalance("X2", "A1", Decimal("50000"))], {"X2": cert}
        )
        p = FatcaCrsReportingEngine.build_payload_skeleton(snaps, "CRS")
        assert p["regime"] == "CRS"

    def test_unsupported_regime(self):
        p = FatcaCrsReportingEngine.build_payload_skeleton([], "INVALID")
        assert "error" in p

    def test_spec_deviation_byte_for_byte(self):
        expected = (
            "Full FATCA Form 8966 XML and OECD CRS XML generation is deferred to v7; "
            "v6 ships deterministic classification, balance aggregation, and skeleton envelope"
        )
        assert FATCA_CRS_SPEC_DEVIATION_NOTE == expected

    def test_schema_present(self):
        for sch in (SCHEMA_SELF_CERT_TABLE, SCHEMA_REPORTABLE_TABLE, SCHEMA_SUBMISSION_TABLE):
            assert "table" in sch and "columns" in sch
            assert "PRIMARY KEY" in sch["columns"][0][1]


# ============================================================================
# G59 Harness — KYC/AML scenario fixture (artifact-handoff)
# ============================================================================

def test_g59_harness_kyc_scenarios():
    """G59 harness: load fixtures, run engine, write artifact at known path."""
    import json
    import os
    fixtures_path = os.path.join(os.path.dirname(__file__), "fixtures", "kyc_aml_scenarios.json")
    with open(fixtures_path) as f:
        scenarios = json.load(f)
    eng = KycAmlRiskEngine()
    results = []
    correct = 0
    for sc in scenarios:
        a = eng.assess_customer(sc["customer"])
        ok = (a.risk_band == sc["expected_band"])
        if ok:
            correct += 1
        results.append({
            "id": sc["id"],
            "expected_band": sc["expected_band"],
            "actual_band": a.risk_band,
            "actual_score": a.risk_score,
            "match": ok,
        })
    artifact = {
        "harness": "kyc_aml_scenarios",
        "total": len(scenarios),
        "correct": correct,
        "accuracy_pct": round((correct / len(scenarios)) * 100, 1) if scenarios else 0,
        "results": results,
    }
    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kyc_aml_results.json")
    with open(out_path, "w") as f:
        json.dump(artifact, f, indent=2)
    assert correct == len(scenarios), f"Expected 100%, got {correct}/{len(scenarios)}"
