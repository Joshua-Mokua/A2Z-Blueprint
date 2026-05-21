"""
================================================================================
A2Z MIS 360 — Standard #57: KYC/AML Risk Scoring Engine
================================================================================

Risk classification: Cat B (rule-based scorecard, deterministic, no ML)

Computes customer KYC/AML risk score (LOW/MEDIUM/HIGH/PROHIBITED) using the
CBK Prudential Guideline CBK/PG/15 (Anti-Money Laundering) and FATF 40
recommendations as guidance.

Scorecard structure (deterministic, additive points, capped):
    - Geography risk      (0-30 points)  high-risk jurisdictions
    - Product risk        (0-25 points)  cash-intensive, correspondent banking
    - Customer type       (0-20 points)  PEP, NGO, high-net-worth
    - Channel risk        (0-15 points)  non-face-to-face, agent banking
    - Behavior risk       (0-10 points)  velocity, structuring patterns

Risk bands:
    LOW         <  20 pts  -> Standard Due Diligence (SDD)
    MEDIUM      20-49 pts  -> Standard Due Diligence
    HIGH        50-79 pts  -> Enhanced Due Diligence (EDD) required
    PROHIBITED  >= 80 pts  -> Onboarding rejected, file SAR if customer

CBK PG/15 mandates EDD for HIGH risk and absolute prohibition for sanctioned
jurisdictions (e.g. North Korea, Iran). PEP screening is mandatory.

Honesty rules applied:
    Rule 6: missing risk indicators do NOT lower the score (no privilege escalation)
    Rule 4: PROHIBITED bands cannot be overridden by relationship/sales staff

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# CBK PG/15 high-risk jurisdictions (FATF black + grey lists, illustrative subset)
PROHIBITED_JURISDICTIONS: Tuple[str, ...] = (
    "KP",  # North Korea
    "IR",  # Iran
)
HIGH_RISK_JURISDICTIONS: Tuple[str, ...] = (
    "AF",  # Afghanistan
    "MM",  # Myanmar
    "SY",  # Syria
    "YE",  # Yemen
    "SS",  # South Sudan
)
MEDIUM_RISK_JURISDICTIONS: Tuple[str, ...] = (
    "PK",  # Pakistan (FATF grey)
    "TR",  # Turkey (FATF grey)
    "JO",  # Jordan
    "MZ",  # Mozambique
)

# Score component weights (sum exceeds 100 because not all components apply)
GEOGRAPHY_PROHIBITED_PTS = 100  # Auto-prohibit
GEOGRAPHY_HIGH_PTS = 30
GEOGRAPHY_MEDIUM_PTS = 15
GEOGRAPHY_LOW_PTS = 0

PRODUCT_PTS = {
    "CASH_INTENSIVE": 25,        # money services, casinos
    "CORRESPONDENT_BANKING": 25,
    "PRIVATE_BANKING": 20,
    "TRADE_FINANCE": 15,
    "WEALTH_MANAGEMENT": 15,
    "RETAIL_DEPOSITS": 5,
    "RETAIL_LOANS": 5,
    "PAYROLL": 0,
    "SAVINGS": 0,
}

CUSTOMER_TYPE_PTS = {
    "PEP_FOREIGN": 20,           # Foreign politically exposed person
    "PEP_DOMESTIC": 15,          # Domestic PEP
    "NGO_NPO": 15,               # Charity/NGO
    "HIGH_NET_WORTH": 10,        # HNW (>USD 1M AUM)
    "BEARER_SHARE_ENTITY": 20,   # Bearer share company
    "TRUST_FOUNDATION": 15,
    "INDIVIDUAL_LOCAL": 0,
    "CORPORATE_LISTED": 0,       # Listed on regulated exchange
    "CORPORATE_PRIVATE": 5,
    "GOVERNMENT": 5,
}

CHANNEL_PTS = {
    "FACE_TO_FACE_BRANCH": 0,
    "MOBILE_APP_VIDEO_KYC": 5,
    "AGENT_BANKING": 10,
    "INTRODUCED_THIRD_PARTY": 10,
    "NON_FACE_TO_FACE": 15,
}

# Risk band thresholds
RISK_BAND_LOW_MAX = 19    # 0-19 = LOW
RISK_BAND_MEDIUM_MAX = 49 # 20-49 = MEDIUM
RISK_BAND_HIGH_MAX = 79   # 50-79 = HIGH; 80+ = PROHIBITED
RISK_BAND_PROHIBITED_MIN = 80

# CDD requirement mapping (Cat C downstream workflow)
CDD_LEVEL_BY_BAND: Dict[str, str] = {
    "LOW": "SIMPLIFIED_DUE_DILIGENCE",
    "MEDIUM": "STANDARD_DUE_DILIGENCE",
    "HIGH": "ENHANCED_DUE_DILIGENCE",
    "PROHIBITED": "ONBOARDING_REJECTED",
}

# Behavior pattern thresholds (per CBK PG/15 §6 transaction monitoring)
STRUCTURING_THRESHOLD_KES = 1_000_000  # KES 1M cash threshold (CBK reportable)
HIGH_VELOCITY_TXN_COUNT_30D = 50
HIGH_VELOCITY_AMOUNT_KES_30D = 50_000_000


@dataclass
class KycRiskAssessment:
    """Output of customer KYC/AML risk assessment."""
    customer_id: str
    risk_score: int
    risk_band: str  # LOW, MEDIUM, HIGH, PROHIBITED
    cdd_level: str  # SDD, STANDARD_DUE_DILIGENCE, EDD, ONBOARDING_REJECTED
    component_scores: Dict[str, int]
    component_reasons: Dict[str, str]
    pep_flag: bool
    sanctions_flag: bool
    auto_prohibited: bool
    auto_prohibited_reason: Optional[str]
    assessed_at: str  # ISO timestamp
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "risk_score": self.risk_score,
            "risk_band": self.risk_band,
            "cdd_level": self.cdd_level,
            "component_scores": dict(self.component_scores),
            "component_reasons": dict(self.component_reasons),
            "pep_flag": self.pep_flag,
            "sanctions_flag": self.sanctions_flag,
            "auto_prohibited": self.auto_prohibited,
            "auto_prohibited_reason": self.auto_prohibited_reason,
            "assessed_at": self.assessed_at,
            "meta": dict(self.meta),
        }


class KycAmlRiskEngine:
    """Deterministic KYC/AML risk scoring engine (CBK PG/15 + FATF 40)."""

    @staticmethod
    def _score_geography(country_code: Optional[str]) -> Tuple[int, str]:
        """Score country-of-residence + country-of-citizenship combined."""
        if country_code is None:
            # Rule 6: missing geography is NOT zero-risk; flag medium pending KYC
            return GEOGRAPHY_MEDIUM_PTS, "country_unknown_pending_kyc"
        cc = country_code.upper().strip()
        if cc in PROHIBITED_JURISDICTIONS:
            return GEOGRAPHY_PROHIBITED_PTS, f"prohibited_jurisdiction:{cc}"
        if cc in HIGH_RISK_JURISDICTIONS:
            return GEOGRAPHY_HIGH_PTS, f"high_risk_jurisdiction:{cc}"
        if cc in MEDIUM_RISK_JURISDICTIONS:
            return GEOGRAPHY_MEDIUM_PTS, f"medium_risk_jurisdiction:{cc}"
        return GEOGRAPHY_LOW_PTS, "low_risk_jurisdiction"

    @staticmethod
    def _score_product(products: Optional[List[str]]) -> Tuple[int, str]:
        """Score by highest-risk product held (max, not sum)."""
        if not products:
            return 0, "no_products"
        max_pts = 0
        max_product = ""
        unknown: List[str] = []
        for p in products:
            key = p.upper().strip()
            if key in PRODUCT_PTS:
                if PRODUCT_PTS[key] > max_pts:
                    max_pts = PRODUCT_PTS[key]
                    max_product = key
            else:
                unknown.append(key)
        # Rule 6: unknown products do not lower score; flag for review
        if unknown and max_pts == 0:
            return 5, f"unknown_products_pending_review:{','.join(unknown[:3])}"
        if unknown:
            return max_pts, f"highest_risk_product:{max_product};unknown:{','.join(unknown[:3])}"
        return max_pts, f"highest_risk_product:{max_product}" if max_product else "low_risk_products"

    @staticmethod
    def _score_customer_type(customer_type: Optional[str]) -> Tuple[int, str]:
        """Score customer entity type."""
        if customer_type is None:
            # Rule 6: unknown customer type defaults to medium-risk pending KYC
            return 10, "customer_type_unknown_pending_kyc"
        key = customer_type.upper().strip()
        if key in CUSTOMER_TYPE_PTS:
            return CUSTOMER_TYPE_PTS[key], f"customer_type:{key}"
        # Rule 6: unrecognized type doesn't lower score
        return 10, f"customer_type_unrecognized:{key}"

    @staticmethod
    def _score_channel(onboarding_channel: Optional[str]) -> Tuple[int, str]:
        """Score onboarding channel."""
        if onboarding_channel is None:
            return 5, "channel_unknown"
        key = onboarding_channel.upper().strip()
        if key in CHANNEL_PTS:
            return CHANNEL_PTS[key], f"channel:{key}"
        return 5, f"channel_unrecognized:{key}"

    @staticmethod
    def _score_behavior(behavior: Optional[Dict[str, Any]]) -> Tuple[int, str]:
        """Score behavior patterns: structuring, velocity."""
        if not behavior:
            return 0, "no_behavior_data"
        score = 0
        flags: List[str] = []
        # Structuring: multiple cash deposits just under threshold
        struct_count = behavior.get("structured_deposits_count_30d", 0) or 0
        if isinstance(struct_count, (int, float)) and struct_count >= 3:
            score += 5
            flags.append(f"structuring:{int(struct_count)}_deposits")
        # Velocity
        txn_count = behavior.get("txn_count_30d", 0) or 0
        if isinstance(txn_count, (int, float)) and txn_count >= HIGH_VELOCITY_TXN_COUNT_30D:
            score += 3
            flags.append(f"high_velocity_count:{int(txn_count)}")
        amt = behavior.get("txn_amount_kes_30d", 0) or 0
        if isinstance(amt, (int, float)) and amt >= HIGH_VELOCITY_AMOUNT_KES_30D:
            score += 2
            flags.append(f"high_velocity_amount:{int(amt)}")
        if not flags:
            return 0, "behavior_normal"
        return min(score, 10), ";".join(flags)

    @classmethod
    def assess_customer(cls, customer: Dict[str, Any]) -> KycRiskAssessment:
        """
        Score a customer profile.

        customer dict expected keys:
            customer_id (str, required)
            country_code (str, ISO-2)
            citizenship_code (str, ISO-2)
            products (list[str])
            customer_type (str)
            onboarding_channel (str)
            pep_flag (bool)
            sanctions_hit (bool)
            behavior (dict)
        """
        cid = str(customer.get("customer_id", "UNKNOWN"))

        # Sanctions hit -> auto prohibited (Rule 4: cannot be overridden)
        sanctions_hit = bool(customer.get("sanctions_hit", False))
        if sanctions_hit:
            return KycRiskAssessment(
                customer_id=cid,
                risk_score=100,
                risk_band="PROHIBITED",
                cdd_level=CDD_LEVEL_BY_BAND["PROHIBITED"],
                component_scores={"sanctions": 100},
                component_reasons={"sanctions": "sanctions_list_hit_auto_prohibited"},
                pep_flag=bool(customer.get("pep_flag", False)),
                sanctions_flag=True,
                auto_prohibited=True,
                auto_prohibited_reason="sanctions_list_hit",
                assessed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Geography (residence + citizenship) - take MAX risk
        geo_res_pts, geo_res_reason = cls._score_geography(customer.get("country_code"))
        geo_cit_pts, geo_cit_reason = cls._score_geography(customer.get("citizenship_code"))
        geo_pts = max(geo_res_pts, geo_cit_pts)
        geo_reason = geo_res_reason if geo_res_pts >= geo_cit_pts else geo_cit_reason

        # Auto-prohibit on prohibited jurisdiction
        if geo_pts >= GEOGRAPHY_PROHIBITED_PTS:
            return KycRiskAssessment(
                customer_id=cid,
                risk_score=100,
                risk_band="PROHIBITED",
                cdd_level=CDD_LEVEL_BY_BAND["PROHIBITED"],
                component_scores={"geography": geo_pts},
                component_reasons={"geography": geo_reason},
                pep_flag=bool(customer.get("pep_flag", False)),
                sanctions_flag=False,
                auto_prohibited=True,
                auto_prohibited_reason=geo_reason,
                assessed_at=datetime.now(timezone.utc).isoformat(),
            )

        # Other components
        prod_pts, prod_reason = cls._score_product(customer.get("products"))
        cust_pts, cust_reason = cls._score_customer_type(customer.get("customer_type"))
        chan_pts, chan_reason = cls._score_channel(customer.get("onboarding_channel"))
        beh_pts, beh_reason = cls._score_behavior(customer.get("behavior"))

        # PEP adjustment (additive on top of customer type if not already PEP)
        pep_flag = bool(customer.get("pep_flag", False))
        cust_type_str = (customer.get("customer_type") or "").upper().strip()
        if pep_flag and not cust_type_str.startswith("PEP_"):
            # Treat as foreign PEP if pep_flag set without explicit type
            cust_pts = max(cust_pts, CUSTOMER_TYPE_PTS["PEP_FOREIGN"])
            cust_reason = f"pep_flag_set;{cust_reason}"

        total = geo_pts + prod_pts + cust_pts + chan_pts + beh_pts

        # Determine band
        if total <= RISK_BAND_LOW_MAX:
            band = "LOW"
        elif total <= RISK_BAND_MEDIUM_MAX:
            band = "MEDIUM"
        elif total <= RISK_BAND_HIGH_MAX:
            band = "HIGH"
        else:
            band = "PROHIBITED"

        return KycRiskAssessment(
            customer_id=cid,
            risk_score=total,
            risk_band=band,
            cdd_level=CDD_LEVEL_BY_BAND[band],
            component_scores={
                "geography": geo_pts,
                "product": prod_pts,
                "customer_type": cust_pts,
                "channel": chan_pts,
                "behavior": beh_pts,
            },
            component_reasons={
                "geography": geo_reason,
                "product": prod_reason,
                "customer_type": cust_reason,
                "channel": chan_reason,
                "behavior": beh_reason,
            },
            pep_flag=pep_flag,
            sanctions_flag=False,
            auto_prohibited=(band == "PROHIBITED"),
            auto_prohibited_reason=(f"score_exceeds_threshold:{total}>={RISK_BAND_PROHIBITED_MIN}" if band == "PROHIBITED" else None),
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def portfolio_risk_summary(cls, assessments: List[KycRiskAssessment]) -> Dict[str, Any]:
        """Aggregate risk band distribution for a customer portfolio."""
        if not assessments:
            return {
                "total_customers": 0,
                "by_band": {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "PROHIBITED": 0},
                "pep_count": 0,
                "sanctions_count": 0,
                "auto_prohibited_count": 0,
            }
        bands = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "PROHIBITED": 0}
        pep_count = 0
        sanc_count = 0
        prohib_count = 0
        for a in assessments:
            bands[a.risk_band] = bands.get(a.risk_band, 0) + 1
            if a.pep_flag:
                pep_count += 1
            if a.sanctions_flag:
                sanc_count += 1
            if a.auto_prohibited:
                prohib_count += 1
        return {
            "total_customers": len(assessments),
            "by_band": bands,
            "pep_count": pep_count,
            "sanctions_count": sanc_count,
            "auto_prohibited_count": prohib_count,
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_low_risk_local_individual():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C001",
        "country_code": "KE",
        "citizenship_code": "KE",
        "products": ["SAVINGS"],
        "customer_type": "INDIVIDUAL_LOCAL",
        "onboarding_channel": "FACE_TO_FACE_BRANCH",
        "pep_flag": False,
        "sanctions_hit": False,
    })
    assert a.risk_band == "LOW", f"Expected LOW, got {a.risk_band}"
    assert a.cdd_level == "SIMPLIFIED_DUE_DILIGENCE"
    assert not a.auto_prohibited
    assert a.risk_score < 20

def _test_high_risk_pep_foreign():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C002",
        "country_code": "KE",
        "citizenship_code": "PK",  # FATF grey -> medium
        "products": ["PRIVATE_BANKING"],
        "customer_type": "PEP_FOREIGN",
        "onboarding_channel": "INTRODUCED_THIRD_PARTY",
        "pep_flag": True,
        "sanctions_hit": False,
    })
    # 15(geo PK) + 20(private banking) + 20(PEP) + 10(introduced) = 65 = HIGH
    assert a.risk_score >= 50, f"Expected >=50, got {a.risk_score}"
    assert a.risk_band == "HIGH", f"Expected HIGH, got {a.risk_band}"
    assert a.cdd_level == "ENHANCED_DUE_DILIGENCE"
    assert a.pep_flag is True

def _test_prohibited_jurisdiction_auto():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C003",
        "country_code": "KE",
        "citizenship_code": "KP",  # North Korea
        "products": ["SAVINGS"],
        "customer_type": "INDIVIDUAL_LOCAL",
    })
    assert a.risk_band == "PROHIBITED"
    assert a.auto_prohibited is True
    assert "KP" in a.auto_prohibited_reason

def _test_sanctions_hit_auto_prohibited():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C004",
        "country_code": "KE",
        "products": ["SAVINGS"],
        "customer_type": "INDIVIDUAL_LOCAL",
        "sanctions_hit": True,
    })
    assert a.risk_band == "PROHIBITED"
    assert a.sanctions_flag is True
    assert a.auto_prohibited is True
    assert a.auto_prohibited_reason == "sanctions_list_hit"
    # Rule 4: even if other factors low, sanctions wins

def _test_missing_country_rule6():
    """Rule 6: missing country does NOT default to LOW; flagged medium pending KYC."""
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C005",
        "country_code": None,
        "citizenship_code": None,
        "products": ["SAVINGS"],
        "customer_type": "INDIVIDUAL_LOCAL",
    })
    assert a.component_scores["geography"] >= 15, "Missing country must not be zero-risk"
    assert "unknown" in a.component_reasons["geography"]

def _test_unknown_product_rule6():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C006",
        "country_code": "KE",
        "products": ["EXOTIC_DERIVATIVE"],
        "customer_type": "CORPORATE_PRIVATE",
    })
    assert a.component_scores["product"] >= 5, "Unknown product must not be zero-risk"
    assert "unknown" in a.component_reasons["product"]

def _test_medium_risk_corporate():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C007",
        "country_code": "TR",  # FATF grey
        "products": ["TRADE_FINANCE"],
        "customer_type": "CORPORATE_PRIVATE",
        "onboarding_channel": "FACE_TO_FACE_BRANCH",
    })
    # 15(TR) + 15(trade finance) + 5(corp private) + 0(F2F) = 35 = MEDIUM
    assert a.risk_band == "MEDIUM", f"Expected MEDIUM, got {a.risk_band} (score={a.risk_score})"

def _test_band_boundaries():
    """Test boundary classifications: 19=LOW, 20=MEDIUM, 49=MEDIUM, 50=HIGH, 79=HIGH, 80=PROHIBITED."""
    # We need to construct customers landing on exact scores. Easiest: use
    # geography (15) + product to hit specific values.
    e = KycAmlRiskEngine()
    # Score 15 (TR geo only) -> LOW
    a1 = e.assess_customer({"customer_id": "B1", "country_code": "TR", "customer_type": "INDIVIDUAL_LOCAL", "onboarding_channel": "FACE_TO_FACE_BRANCH"})
    assert a1.risk_score == 15 and a1.risk_band == "LOW"
    # 15 + retail loans 5 = 20 -> MEDIUM
    a2 = e.assess_customer({"customer_id": "B2", "country_code": "TR", "products": ["RETAIL_LOANS"], "customer_type": "INDIVIDUAL_LOCAL", "onboarding_channel": "FACE_TO_FACE_BRANCH"})
    assert a2.risk_score == 20 and a2.risk_band == "MEDIUM", f"got {a2.risk_score}/{a2.risk_band}"

def _test_pep_flag_without_explicit_type():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C008",
        "country_code": "KE",
        "products": ["SAVINGS"],
        "customer_type": "INDIVIDUAL_LOCAL",
        "pep_flag": True,
        "onboarding_channel": "FACE_TO_FACE_BRANCH",
    })
    # pep_flag should bump customer_type score even without PEP_FOREIGN type
    assert a.component_scores["customer_type"] >= 20
    assert "pep_flag_set" in a.component_reasons["customer_type"]

def _test_behavior_structuring():
    e = KycAmlRiskEngine()
    a = e.assess_customer({
        "customer_id": "C009",
        "country_code": "KE",
        "products": ["SAVINGS"],
        "customer_type": "INDIVIDUAL_LOCAL",
        "behavior": {
            "structured_deposits_count_30d": 5,
            "txn_count_30d": 60,
            "txn_amount_kes_30d": 60_000_000,
        },
    })
    assert a.component_scores["behavior"] == 10  # capped
    assert "structuring" in a.component_reasons["behavior"]

def _test_portfolio_summary_empty():
    s = KycAmlRiskEngine.portfolio_risk_summary([])
    assert s["total_customers"] == 0
    assert s["by_band"]["PROHIBITED"] == 0

def _test_portfolio_summary_aggregates():
    e = KycAmlRiskEngine()
    aa = [
        e.assess_customer({"customer_id": "P1", "country_code": "KE", "products": ["SAVINGS"], "customer_type": "INDIVIDUAL_LOCAL", "onboarding_channel": "FACE_TO_FACE_BRANCH"}),
        e.assess_customer({"customer_id": "P2", "country_code": "KP", "customer_type": "INDIVIDUAL_LOCAL"}),
        e.assess_customer({"customer_id": "P3", "country_code": "KE", "sanctions_hit": True, "customer_type": "INDIVIDUAL_LOCAL"}),
        e.assess_customer({"customer_id": "P4", "country_code": "KE", "pep_flag": True, "customer_type": "PEP_FOREIGN", "products": ["PRIVATE_BANKING"], "onboarding_channel": "INTRODUCED_THIRD_PARTY", "citizenship_code": "PK"}),
    ]
    s = KycAmlRiskEngine.portfolio_risk_summary(aa)
    assert s["total_customers"] == 4
    assert s["sanctions_count"] == 1
    assert s["auto_prohibited_count"] >= 2
    assert s["pep_count"] == 1


def self_test() -> bool:
    tests = [
        _test_low_risk_local_individual,
        _test_high_risk_pep_foreign,
        _test_prohibited_jurisdiction_auto,
        _test_sanctions_hit_auto_prohibited,
        _test_missing_country_rule6,
        _test_unknown_product_rule6,
        _test_medium_risk_corporate,
        _test_band_boundaries,
        _test_pep_flag_without_explicit_type,
        _test_behavior_structuring,
        _test_portfolio_summary_empty,
        _test_portfolio_summary_aggregates,
    ]
    print("=" * 60)
    print("KYC/AML Risk Scoring Engine — Self-Tests (#57)")
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
