"""
================================================================================
A2Z MIS 360 — Standard #116: IAS 24 Related Party Disclosures
================================================================================

Risk classification: Cat B (deterministic related-party identification + disclosure)

Provides:
    - classify_related_party(...)        -- 7 IAS 24.9 relationship categories
    - identify_kmp(...)                  -- key management personnel test
    - close_family_member_check(...)     -- spouse/child/dependent
    - validate_disclosure_completeness(...) -- 5 required disclosures
    - government_related_entity_relief(...) -- IAS 24.25-27 partial exemption

7 RELATED_PARTY_CATEGORIES byte-for-byte (IAS 24.9):
    PARENT_OR_SUBSIDIARY                 -- direct ownership control
    FELLOW_SUBSIDIARY                    -- common parent
    ASSOCIATE_OR_JOINT_VENTURE          -- significant influence
    KEY_MANAGEMENT_PERSONNEL_OR_FAMILY   -- KMP + close family
    POST_EMPLOYMENT_BENEFIT_PLAN        -- DB plan or similar
    PARTY_WITH_CONTROL_OVER_KMP         -- entity controlled by KMP
    GOVERNMENT_RELATED                   -- government-controlled entities

5 KMP_CRITERIA byte-for-byte (IAS 24.9):
    DIRECT_AUTHORITY_FOR_PLANNING
    DIRECT_AUTHORITY_FOR_DIRECTING
    DIRECT_AUTHORITY_FOR_CONTROLLING
    INCLUDES_DIRECTORS                   -- executive + non-executive
    INCLUDES_SENIOR_MANAGEMENT

4 CLOSE_FAMILY_MEMBERS byte-for-byte (IAS 24.9):
    SPOUSE_OR_DOMESTIC_PARTNER
    CHILDREN_OF_INDIVIDUAL_OR_PARTNER
    DEPENDENTS_OF_INDIVIDUAL_OR_PARTNER
    DEPENDENTS_OF_SPOUSE_OR_PARTNER

5 REQUIRED_DISCLOSURES byte-for-byte (IAS 24.18):
    NATURE_OF_RELATIONSHIP
    AMOUNT_OF_TRANSACTIONS
    OUTSTANDING_BALANCES_AND_TERMS
    PROVISIONS_FOR_DOUBTFUL_DEBTS
    EXPENSE_RECOGNISED_FOR_BAD_DEBTS

6 KMP_COMPENSATION_CATEGORIES byte-for-byte (IAS 24.17):
    SHORT_TERM_BENEFITS
    POST_EMPLOYMENT_BENEFITS
    OTHER_LONG_TERM_BENEFITS
    TERMINATION_BENEFITS
    SHARE_BASED_PAYMENTS

3 GOVERNMENT_RELATED_RELIEF byte-for-byte (IAS 24.25-27):
    INDIVIDUALLY_SIGNIFICANT_TRANSACTIONS
    COLLECTIVELY_SIGNIFICANT_TRANSACTIONS
    PARTIAL_EXEMPTION_FROM_FULL_DISCLOSURE

Honesty rules applied:
    Rule 1: classification=None when category missing
    Rule 6: unknown category surfaced (fail closed)
            transactions with related parties without disclosure = ERROR

================================================================================
"""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28

# 7 RELATED PARTY CATEGORIES byte-for-byte (IAS 24.9)
RELATED_PARTY_CATEGORIES: Tuple[str, ...] = (
    "PARENT_OR_SUBSIDIARY",
    "FELLOW_SUBSIDIARY",
    "ASSOCIATE_OR_JOINT_VENTURE",
    "KEY_MANAGEMENT_PERSONNEL_OR_FAMILY",
    "POST_EMPLOYMENT_BENEFIT_PLAN",
    "PARTY_WITH_CONTROL_OVER_KMP",
    "GOVERNMENT_RELATED",
)

# 5 KMP CRITERIA byte-for-byte (IAS 24.9)
KMP_CRITERIA: Tuple[str, ...] = (
    "DIRECT_AUTHORITY_FOR_PLANNING",
    "DIRECT_AUTHORITY_FOR_DIRECTING",
    "DIRECT_AUTHORITY_FOR_CONTROLLING",
    "INCLUDES_DIRECTORS",
    "INCLUDES_SENIOR_MANAGEMENT",
)

# 4 CLOSE FAMILY MEMBERS byte-for-byte (IAS 24.9)
CLOSE_FAMILY_MEMBERS: Tuple[str, ...] = (
    "SPOUSE_OR_DOMESTIC_PARTNER",
    "CHILDREN_OF_INDIVIDUAL_OR_PARTNER",
    "DEPENDENTS_OF_INDIVIDUAL_OR_PARTNER",
    "DEPENDENTS_OF_SPOUSE_OR_PARTNER",
)

# 5 REQUIRED DISCLOSURES byte-for-byte (IAS 24.18)
REQUIRED_DISCLOSURES: Tuple[str, ...] = (
    "NATURE_OF_RELATIONSHIP",
    "AMOUNT_OF_TRANSACTIONS",
    "OUTSTANDING_BALANCES_AND_TERMS",
    "PROVISIONS_FOR_DOUBTFUL_DEBTS",
    "EXPENSE_RECOGNISED_FOR_BAD_DEBTS",
)

# 5 KMP COMPENSATION CATEGORIES byte-for-byte (IAS 24.17)
KMP_COMPENSATION_CATEGORIES: Tuple[str, ...] = (
    "SHORT_TERM_BENEFITS",
    "POST_EMPLOYMENT_BENEFITS",
    "OTHER_LONG_TERM_BENEFITS",
    "TERMINATION_BENEFITS",
    "SHARE_BASED_PAYMENTS",
)

# 3 GOVERNMENT-RELATED RELIEF byte-for-byte (IAS 24.25-27)
GOVERNMENT_RELATED_RELIEF: Tuple[str, ...] = (
    "INDIVIDUALLY_SIGNIFICANT_TRANSACTIONS",
    "COLLECTIVELY_SIGNIFICANT_TRANSACTIONS",
    "PARTIAL_EXEMPTION_FROM_FULL_DISCLOSURE",
)


class RelatedPartyEngine:
    """Deterministic IAS 24 related party identification + disclosure."""

    @staticmethod
    def classify_related_party(category: str) -> Dict[str, Any]:
        """
        Validate related party category per IAS 24.9.
        Rule 6: unknown category rejected.
        """
        if category not in RELATED_PARTY_CATEGORIES:
            return {"valid": False,
                    "reason": f"unknown_category:{category}",
                    "valid_categories": list(RELATED_PARTY_CATEGORIES)}
        return {"valid": True, "category": category}

    @staticmethod
    def identify_kmp(
        criteria_met: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        IAS 24.9: KMP includes those with authority + responsibility for
        planning, directing, controlling. Includes directors and senior management.
        At least one authority criterion (planning/directing/controlling)
        AND inclusion as director or senior management = KMP.
        Rule 1: None when criteria dict empty.
        """
        if not criteria_met:
            return {"is_kmp": None, "computed": False,
                    "reason": "missing_criteria_dict"}
        has_authority = (criteria_met.get("DIRECT_AUTHORITY_FOR_PLANNING", False)
                          or criteria_met.get("DIRECT_AUTHORITY_FOR_DIRECTING", False)
                          or criteria_met.get("DIRECT_AUTHORITY_FOR_CONTROLLING", False))
        is_director_or_smgmt = (criteria_met.get("INCLUDES_DIRECTORS", False)
                                  or criteria_met.get("INCLUDES_SENIOR_MANAGEMENT", False))
        is_kmp = has_authority and is_director_or_smgmt
        return {
            "has_authority": has_authority,
            "is_director_or_senior_management": is_director_or_smgmt,
            "is_kmp": is_kmp,
            "rationale": ("authority_plus_role_per_IAS_24.9" if is_kmp
                          else "missing_authority_or_role"),
            "computed": True,
        }

    @staticmethod
    def close_family_member_check(relationship: str) -> Dict[str, Any]:
        """
        IAS 24.9: close family members may be expected to influence,
        or be influenced by, that person.
        Rule 6: unknown relationship rejected.
        """
        if relationship not in CLOSE_FAMILY_MEMBERS:
            return {"is_close_family": False,
                    "reason": f"not_in_close_family_list:{relationship}",
                    "valid_close_family": list(CLOSE_FAMILY_MEMBERS)}
        return {
            "relationship": relationship,
            "is_close_family": True,
            "rationale": "in_close_family_definition_per_IAS_24.9",
        }

    @staticmethod
    def validate_disclosure_completeness(
        disclosures_provided: Dict[str, bool],
    ) -> Dict[str, Any]:
        """
        IAS 24.18: ALL 5 required disclosures must be provided for material
        related party transactions.
        Rule 6: missing disclosures = NON-COMPLIANT (fail closed).
        """
        if not disclosures_provided:
            return {"complete": None, "computed": False,
                    "reason": "missing_disclosures_dict"}
        missing: List[str] = []
        for d in REQUIRED_DISCLOSURES:
            if not disclosures_provided.get(d, False):
                missing.append(d)
        complete = len(missing) == 0
        return {
            "required_disclosures": list(REQUIRED_DISCLOSURES),
            "missing_disclosures": missing,
            "complete": complete,
            "compliant": complete,
            "rationale": ("all_required_disclosures_per_IAS_24.18" if complete
                          else "missing_disclosures_non_compliant"),
            "computed": True,
        }

    @staticmethod
    def government_related_entity_relief(
        is_government_controlled: Optional[bool],
        transaction_significance: str = "INDIVIDUALLY_SIGNIFICANT",
    ) -> Dict[str, Any]:
        """
        IAS 24.25-27: government-related entities have partial relief from
        full disclosure of all transactions, but must still disclose:
        - Nature and amount of individually significant transactions
        - Qualitative info on collectively significant transactions
        Rule 1: None when input missing.
        """
        if is_government_controlled is None:
            return {"applies": None, "computed": False,
                    "reason": "missing_input"}
        if not is_government_controlled:
            return {
                "is_government_controlled": False,
                "applies": False,
                "rationale": "not_government_related_full_disclosure_required",
                "computed": True,
            }
        if transaction_significance not in (
                "INDIVIDUALLY_SIGNIFICANT", "COLLECTIVELY_SIGNIFICANT", "INSIGNIFICANT"):
            return {"applies": None, "computed": False,
                    "reason": f"unknown_significance:{transaction_significance}"}
        return {
            "is_government_controlled": True,
            "transaction_significance": transaction_significance,
            "applies": True,
            "disclosure_level": ("FULL" if transaction_significance == "INDIVIDUALLY_SIGNIFICANT"
                                 else "QUALITATIVE_ONLY" if transaction_significance == "COLLECTIVELY_SIGNIFICANT"
                                 else "EXEMPT"),
            "rationale": "partial_exemption_per_IAS_24.25-27",
            "computed": True,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_categories_byte_for_byte():
    expected = (
        "PARENT_OR_SUBSIDIARY",
        "FELLOW_SUBSIDIARY",
        "ASSOCIATE_OR_JOINT_VENTURE",
        "KEY_MANAGEMENT_PERSONNEL_OR_FAMILY",
        "POST_EMPLOYMENT_BENEFIT_PLAN",
        "PARTY_WITH_CONTROL_OVER_KMP",
        "GOVERNMENT_RELATED",
    )
    for c in expected:
        assert c in RELATED_PARTY_CATEGORIES
    assert len(RELATED_PARTY_CATEGORIES) == 7


def _test_kmp_criteria_byte_for_byte():
    expected = (
        "DIRECT_AUTHORITY_FOR_PLANNING",
        "DIRECT_AUTHORITY_FOR_DIRECTING",
        "DIRECT_AUTHORITY_FOR_CONTROLLING",
        "INCLUDES_DIRECTORS",
        "INCLUDES_SENIOR_MANAGEMENT",
    )
    for c in expected:
        assert c in KMP_CRITERIA
    assert len(KMP_CRITERIA) == 5


def _test_close_family_byte_for_byte():
    expected = (
        "SPOUSE_OR_DOMESTIC_PARTNER",
        "CHILDREN_OF_INDIVIDUAL_OR_PARTNER",
        "DEPENDENTS_OF_INDIVIDUAL_OR_PARTNER",
        "DEPENDENTS_OF_SPOUSE_OR_PARTNER",
    )
    for f in expected:
        assert f in CLOSE_FAMILY_MEMBERS
    assert len(CLOSE_FAMILY_MEMBERS) == 4


def _test_required_disclosures_byte_for_byte():
    expected = (
        "NATURE_OF_RELATIONSHIP",
        "AMOUNT_OF_TRANSACTIONS",
        "OUTSTANDING_BALANCES_AND_TERMS",
        "PROVISIONS_FOR_DOUBTFUL_DEBTS",
        "EXPENSE_RECOGNISED_FOR_BAD_DEBTS",
    )
    for d in expected:
        assert d in REQUIRED_DISCLOSURES
    assert len(REQUIRED_DISCLOSURES) == 5


def _test_kmp_compensation_byte_for_byte():
    expected = (
        "SHORT_TERM_BENEFITS",
        "POST_EMPLOYMENT_BENEFITS",
        "OTHER_LONG_TERM_BENEFITS",
        "TERMINATION_BENEFITS",
        "SHARE_BASED_PAYMENTS",
    )
    for c in expected:
        assert c in KMP_COMPENSATION_CATEGORIES


def _test_govt_relief_byte_for_byte():
    expected = (
        "INDIVIDUALLY_SIGNIFICANT_TRANSACTIONS",
        "COLLECTIVELY_SIGNIFICANT_TRANSACTIONS",
        "PARTIAL_EXEMPTION_FROM_FULL_DISCLOSURE",
    )
    for r in expected:
        assert r in GOVERNMENT_RELATED_RELIEF


def _test_classify_parent_subsidiary():
    r = RelatedPartyEngine.classify_related_party("PARENT_OR_SUBSIDIARY")
    assert r["valid"] is True


def _test_classify_government_related():
    r = RelatedPartyEngine.classify_related_party("GOVERNMENT_RELATED")
    assert r["valid"] is True


def _test_classify_unknown_rule6():
    r = RelatedPartyEngine.classify_related_party("WEIRD")
    assert r["valid"] is False


def _test_kmp_director_with_authority():
    """Director with planning authority → KMP."""
    r = RelatedPartyEngine.identify_kmp({
        "DIRECT_AUTHORITY_FOR_PLANNING": True,
        "INCLUDES_DIRECTORS": True,
    })
    assert r["is_kmp"] is True


def _test_kmp_senior_with_directing_authority():
    """Senior management with directing authority → KMP."""
    r = RelatedPartyEngine.identify_kmp({
        "DIRECT_AUTHORITY_FOR_DIRECTING": True,
        "INCLUDES_SENIOR_MANAGEMENT": True,
    })
    assert r["is_kmp"] is True


def _test_kmp_no_authority_not_kmp():
    """Director without authority → NOT KMP."""
    r = RelatedPartyEngine.identify_kmp({
        "INCLUDES_DIRECTORS": True,
    })
    assert r["is_kmp"] is False


def _test_kmp_authority_no_role_not_kmp():
    """Authority but neither director nor senior mgmt → NOT KMP."""
    r = RelatedPartyEngine.identify_kmp({
        "DIRECT_AUTHORITY_FOR_PLANNING": True,
    })
    assert r["is_kmp"] is False


def _test_kmp_empty_rule1():
    r = RelatedPartyEngine.identify_kmp({})
    assert r["is_kmp"] is None


def _test_close_family_spouse():
    r = RelatedPartyEngine.close_family_member_check("SPOUSE_OR_DOMESTIC_PARTNER")
    assert r["is_close_family"] is True


def _test_close_family_children():
    r = RelatedPartyEngine.close_family_member_check("CHILDREN_OF_INDIVIDUAL_OR_PARTNER")
    assert r["is_close_family"] is True


def _test_close_family_unknown():
    """Cousin / sibling not in IAS 24 close family list."""
    r = RelatedPartyEngine.close_family_member_check("COUSIN")
    assert r["is_close_family"] is False


def _test_disclosures_all_provided():
    all_provided = {d: True for d in REQUIRED_DISCLOSURES}
    r = RelatedPartyEngine.validate_disclosure_completeness(all_provided)
    assert r["complete"] is True
    assert r["compliant"] is True


def _test_disclosures_one_missing_rule6():
    """Missing one disclosure → non-compliant (fail closed)."""
    one_missing = {d: True for d in REQUIRED_DISCLOSURES}
    one_missing["NATURE_OF_RELATIONSHIP"] = False
    r = RelatedPartyEngine.validate_disclosure_completeness(one_missing)
    assert r["complete"] is False
    assert r["compliant"] is False


def _test_disclosures_empty_rule1():
    r = RelatedPartyEngine.validate_disclosure_completeness({})
    assert r["complete"] is None


def _test_govt_relief_applies():
    r = RelatedPartyEngine.government_related_entity_relief(
        True, transaction_significance="INDIVIDUALLY_SIGNIFICANT")
    assert r["applies"] is True
    assert r["disclosure_level"] == "FULL"


def _test_govt_relief_collectively_significant():
    r = RelatedPartyEngine.government_related_entity_relief(
        True, transaction_significance="COLLECTIVELY_SIGNIFICANT")
    assert r["disclosure_level"] == "QUALITATIVE_ONLY"


def _test_govt_relief_insignificant():
    r = RelatedPartyEngine.government_related_entity_relief(
        True, transaction_significance="INSIGNIFICANT")
    assert r["disclosure_level"] == "EXEMPT"


def _test_govt_relief_not_govt_controlled():
    r = RelatedPartyEngine.government_related_entity_relief(False)
    assert r["applies"] is False


def _test_govt_relief_missing_input_rule1():
    r = RelatedPartyEngine.government_related_entity_relief(None)
    assert r["applies"] is None


def self_test() -> bool:
    tests = [
        _test_categories_byte_for_byte,
        _test_kmp_criteria_byte_for_byte,
        _test_close_family_byte_for_byte,
        _test_required_disclosures_byte_for_byte,
        _test_kmp_compensation_byte_for_byte,
        _test_govt_relief_byte_for_byte,
        _test_classify_parent_subsidiary,
        _test_classify_government_related,
        _test_classify_unknown_rule6,
        _test_kmp_director_with_authority,
        _test_kmp_senior_with_directing_authority,
        _test_kmp_no_authority_not_kmp,
        _test_kmp_authority_no_role_not_kmp,
        _test_kmp_empty_rule1,
        _test_close_family_spouse,
        _test_close_family_children,
        _test_close_family_unknown,
        _test_disclosures_all_provided,
        _test_disclosures_one_missing_rule6,
        _test_disclosures_empty_rule1,
        _test_govt_relief_applies,
        _test_govt_relief_collectively_significant,
        _test_govt_relief_insignificant,
        _test_govt_relief_not_govt_controlled,
        _test_govt_relief_missing_input_rule1,
    ]
    print("=" * 60)
    print("Related Party Engine — Self-Tests (#116 IAS 24)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
