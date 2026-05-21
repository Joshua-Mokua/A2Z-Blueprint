"""
================================================================================
A2Z MIS 360 — Standards #360-#364: Specialized Segment Propositions
================================================================================

Risk classification: Cat B (deterministic eligibility + product catalog)

Segment-specific propositions for the 5 specialized banking segments
mapped in Continuation.docx:
    #360 Women Banking          (UN SDG 5)
    #361 Diaspora Banking       (multi-currency, SWIFT/M-PESA/ACH)
    #362 Asset Finance          (vehicle / machinery / equipment)
    #363 Agri-business          (AFC Act, weather-indexed insurance)
    #364 Youth Banking          (18-35, mobile-first, financial literacy)

This module is data-driven: each segment is configured by a frozen
dataclass with eligibility rules, product catalog, and KPI surface.
The engine's API works for any registered segment without segment-
specific code paths (Rule 6 fail-closed on unknown segment).

Public API:
    check_eligibility(segment_code, customer_attrs) -> {eligible, reasons}
    list_products(segment_code) -> [product configs]
    register_product(segment_code, product_config) -> {registered, ...}
    segment_proposition_summary(segment_code) -> aggregated view

Eligibility check returns explicit reasons (Rule 1: surface reasons,
never silent boolean).

DEFAULT segment configs byte-for-byte (per Continuation.docx):

WOMEN (#360):
    eligibility:  gender_self_id == 'F'
    products:     savings (SDG 5 aligned), business growth loan,
                  investment guidance, mentorship program

DIASPORA (#361):
    eligibility:  resident_country != domicile_country
    products:     remittance corridor account, multi-currency savings,
                  diaspora mortgage, foreign-currency investments
    channels:     SWIFT, M-PESA, ACH

ASSET_FINANCE (#362):
    eligibility:  asset_purchase_intent == True; income_kes >= 50000
    products:     vehicle finance, machinery finance, equipment finance
    collateral:   asset itself + 20% margin

AGRI (#363):
    eligibility:  primary_income_source == 'agriculture'
    products:     crop loan, weather-indexed insurance, supply-chain finance
    regulator:    AFC Act compliance

YOUTH (#364):
    eligibility:  age >= 18 AND age <= 35
    products:     zero-fee account, student loan, micro-savings,
                  financial-literacy modules

Honesty rules:
    Rule 1: missing customer_attrs surface explicit "missing_attr" reason
    Rule 6: unknown segment_code rejected
    Rule 4: register_product requires actor + reason

================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

from utils.specialized_segments_tagging import SEGMENT_CODES


# ────────────────────────────────────────────────────────────────────
# Data classes — frozen segment configurations
# ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SegmentEligibility:
    """Eligibility rule descriptor for a specialized segment."""
    required_attrs: Tuple[str, ...]
    rule_description: str


@dataclass(frozen=True)
class SegmentProduct:
    """A product offering tied to a specialized segment."""
    product_code: str
    product_name: str
    product_type: str       # e.g. SAVINGS / LOAN / INSURANCE / INVESTMENT
    min_amount_kes: Optional[Decimal] = None
    max_amount_kes: Optional[Decimal] = None
    notes: str = ""


# ────────────────────────────────────────────────────────────────────
# Default segment proposition catalog — byte-for-byte
# ────────────────────────────────────────────────────────────────────

DEFAULT_SEGMENT_ELIGIBILITY: Dict[str, SegmentEligibility] = {
    "WOMEN": SegmentEligibility(
        required_attrs=("gender_self_id",),
        rule_description="gender_self_id == 'F' (UN SDG 5 alignment)",
    ),
    "DIASPORA": SegmentEligibility(
        required_attrs=("resident_country", "domicile_country"),
        rule_description="resident_country != domicile_country",
    ),
    "ASSET_FINANCE": SegmentEligibility(
        required_attrs=("asset_purchase_intent", "income_kes"),
        rule_description="asset_purchase_intent == True AND income_kes >= 50000",
    ),
    "AGRI": SegmentEligibility(
        required_attrs=("primary_income_source",),
        rule_description="primary_income_source == 'agriculture' (AFC Act)",
    ),
    "YOUTH": SegmentEligibility(
        required_attrs=("age",),
        rule_description="18 <= age <= 35",
    ),
    "SME": SegmentEligibility(
        required_attrs=("annual_turnover_kes", "employee_count"),
        rule_description="annual_turnover_kes <= 100M AND employee_count <= 99",
    ),
}

DEFAULT_SEGMENT_PRODUCTS: Dict[str, Tuple[SegmentProduct, ...]] = {
    "WOMEN": (
        SegmentProduct("WB-SAV-001", "Women Empowerment Savings", "SAVINGS",
                        min_amount_kes=Decimal("500"),
                        notes="No-fee savings; bonus interest milestone-based"),
        SegmentProduct("WB-LOAN-001", "Women Business Growth Loan", "LOAN",
                        min_amount_kes=Decimal("50000"),
                        max_amount_kes=Decimal("5000000"),
                        notes="Concessional rate; mentorship bundled"),
        SegmentProduct("WB-INV-001", "Investment Guidance Program", "INVESTMENT",
                        notes="Quarterly advisory + portfolio review"),
    ),
    "DIASPORA": (
        SegmentProduct("DB-REM-001", "Diaspora Remittance Account", "SAVINGS",
                        notes="No-fee inbound remittance via SWIFT/M-PESA/ACH"),
        SegmentProduct("DB-MCY-001", "Multi-Currency Savings", "SAVINGS",
                        notes="Multi-currency (major fiat + domestic); auto-conversion at preferential rate"),
        SegmentProduct("DB-MTG-001", "Diaspora Mortgage", "LOAN",
                        min_amount_kes=Decimal("3000000"),
                        notes="Domestic property purchase for non-resident"),
        SegmentProduct("DB-INV-001", "Foreign-Currency Investment Bond", "INVESTMENT",
                        min_amount_kes=Decimal("500000"),
                        notes="GoK FX-denominated bond + treasury bills"),
    ),
    "ASSET_FINANCE": (
        SegmentProduct("AF-VEH-001", "Vehicle Finance", "LOAN",
                        min_amount_kes=Decimal("500000"),
                        max_amount_kes=Decimal("15000000"),
                        notes="LTV up to 80%; vehicle as collateral"),
        SegmentProduct("AF-MAC-001", "Machinery Finance", "LOAN",
                        min_amount_kes=Decimal("1000000"),
                        notes="Industrial / agricultural equipment"),
        SegmentProduct("AF-EQU-001", "Equipment Lease", "LOAN",
                        notes="Lease-to-own structure; preserves working capital"),
    ),
    "AGRI": (
        SegmentProduct("AG-CROP-001", "Crop Production Loan", "LOAN",
                        min_amount_kes=Decimal("20000"),
                        max_amount_kes=Decimal("2000000"),
                        notes="Seasonal; aligned with crop calendar"),
        SegmentProduct("AG-INS-001", "Weather-Indexed Insurance", "INSURANCE",
                        notes="Parametric trigger; auto-payout on weather index"),
        SegmentProduct("AG-SCF-001", "Supply-Chain Finance", "LOAN",
                        notes="Invoice discounting for agri-suppliers"),
    ),
    "YOUTH": (
        SegmentProduct("YB-ACC-001", "Zero-Fee Youth Account", "SAVINGS",
                        notes="No monthly fees; M-PESA integrated"),
        SegmentProduct("YB-EDU-001", "Student Loan", "LOAN",
                        min_amount_kes=Decimal("50000"),
                        max_amount_kes=Decimal("500000"),
                        notes="Education finance; 12-month grace post-graduation"),
        SegmentProduct("YB-SAV-001", "Micro-Savings", "SAVINGS",
                        min_amount_kes=Decimal("100"),
                        notes="Round-up + auto-savings rules"),
        SegmentProduct("YB-LIT-001", "Financial Literacy Module", "INVESTMENT",
                        notes="Free educational content + simulator"),
    ),
    "SME": (
        SegmentProduct("SME-WC-001", "SME Working Capital", "LOAN",
                        notes="Revolving credit line"),
        SegmentProduct("SME-INV-001", "SME Investment Loan", "LOAN",
                        notes="Asset acquisition + expansion finance"),
    ),
}


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

class SegmentPropositionsEngine:
    """
    Specialized segment propositions: eligibility checks + product
    catalog management. Data-driven across all 6 segments.
    """

    def __init__(
        self,
        custom_products_path: Optional[Path] = None,
        eligibility_rules: Optional[Dict[str, SegmentEligibility]] = None,
    ):
        self.custom_products_path = (
            custom_products_path
            if custom_products_path is not None
            else Path(__file__).parent.parent / "data" / "segment_custom_products.json"
        )
        # Eligibility rules (overridable for testing)
        self.eligibility_rules = (
            dict(eligibility_rules) if eligibility_rules is not None
            else dict(DEFAULT_SEGMENT_ELIGIBILITY)
        )

    def _load_custom_products(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            records = _db.dual_load(
                self.custom_products_path,
                table="segment_custom_products",
                index_cols=("product_code",))
            if not isinstance(records, list):
                return {}
            # Re-group flat records by segment_code
            from collections import defaultdict
            by_segment: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for r in records:
                sc = r.get("segment_code")
                if sc:
                    by_segment[sc].append(r)
            return dict(by_segment)
        except Exception:
            return {}

    def _save_custom_products(self, data: Dict[str, List[Dict[str, Any]]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.custom_products_path.parent.mkdir(parents=True, exist_ok=True)
            # Flatten dict-of-lists to list-of-records (each record carries segment_code)
            flat: List[Dict[str, Any]] = []
            for sc, records in data.items():
                for r in records:
                    rec = dict(r)
                    rec["segment_code"] = sc
                    flat.append(rec)
            _db.dual_save(
                self.custom_products_path,
                data=flat,
                table="segment_custom_products",
                pk_col="product_code")
            return True
        except Exception:
            return False

    def check_eligibility(
        self,
        segment_code: str,
        customer_attrs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Check segment eligibility against customer attributes.

        Returns: {eligible, reasons: [...], missing_attrs: [...]}.

        Rule 1: missing attrs surfaced; Rule 6: unknown segment rejected.
        """
        if segment_code not in SEGMENT_CODES:
            return {
                "eligible": False,
                "reasons": [f"unknown_segment_code:{segment_code}"],
                "missing_attrs": [],
            }

        rule = self.eligibility_rules.get(segment_code)
        if rule is None:
            return {
                "eligible": False,
                "reasons": ["no_rule_registered"],
                "missing_attrs": [],
            }

        # Check required attrs present
        missing = [a for a in rule.required_attrs if a not in customer_attrs]
        if missing:
            return {
                "eligible": False,
                "reasons": ["missing_required_attrs"],
                "missing_attrs": missing,
                "rule_description": rule.rule_description,
            }

        # Per-segment rule evaluation (only known ones; Rule 6 keeps unknown segments out earlier)
        if segment_code == "WOMEN":
            eligible = customer_attrs.get("gender_self_id") == "F"
            return {
                "eligible": eligible,
                "reasons": [] if eligible else ["gender_self_id_not_F"],
                "missing_attrs": [],
                "rule_description": rule.rule_description,
            }

        if segment_code == "DIASPORA":
            res = customer_attrs.get("resident_country")
            dom = customer_attrs.get("domicile_country")
            eligible = bool(res) and bool(dom) and res != dom
            return {
                "eligible": eligible,
                "reasons": [] if eligible else ["resident_eq_domicile"],
                "missing_attrs": [],
                "rule_description": rule.rule_description,
            }

        if segment_code == "ASSET_FINANCE":
            intent = bool(customer_attrs.get("asset_purchase_intent"))
            try:
                income = Decimal(str(customer_attrs.get("income_kes", 0)))
            except (ValueError, TypeError):
                return {"eligible": False, "reasons": ["income_kes_not_decimal"],
                         "missing_attrs": [], "rule_description": rule.rule_description}
            eligible = intent and income >= Decimal("50000")
            reasons = []
            if not intent:
                reasons.append("asset_purchase_intent_false")
            if income < Decimal("50000"):
                reasons.append(f"income_below_50000:{income}")
            return {"eligible": eligible, "reasons": reasons,
                     "missing_attrs": [], "rule_description": rule.rule_description}

        if segment_code == "AGRI":
            src = customer_attrs.get("primary_income_source")
            eligible = src == "agriculture"
            return {
                "eligible": eligible,
                "reasons": [] if eligible else [f"primary_income_source_not_agriculture:{src}"],
                "missing_attrs": [],
                "rule_description": rule.rule_description,
            }

        if segment_code == "YOUTH":
            try:
                age = int(customer_attrs.get("age", 0))
            except (ValueError, TypeError):
                return {"eligible": False, "reasons": ["age_not_integer"],
                         "missing_attrs": [], "rule_description": rule.rule_description}
            eligible = 18 <= age <= 35
            return {
                "eligible": eligible,
                "reasons": [] if eligible else [f"age_outside_18_35:{age}"],
                "missing_attrs": [],
                "rule_description": rule.rule_description,
            }

        if segment_code == "SME":
            try:
                turnover = Decimal(str(customer_attrs.get("annual_turnover_kes", 0)))
                employees = int(customer_attrs.get("employee_count", 0))
            except (ValueError, TypeError):
                return {"eligible": False, "reasons": ["sme_attrs_invalid_types"],
                         "missing_attrs": [], "rule_description": rule.rule_description}
            eligible = turnover <= Decimal("100000000") and employees <= 99
            reasons = []
            if turnover > Decimal("100000000"):
                reasons.append(f"turnover_above_100M:{turnover}")
            if employees > 99:
                reasons.append(f"employees_above_99:{employees}")
            return {"eligible": eligible, "reasons": reasons,
                     "missing_attrs": [], "rule_description": rule.rule_description}

        # Should never reach here given segment_code guard
        return {"eligible": False, "reasons": ["unsupported_segment"],
                 "missing_attrs": [], "rule_description": rule.rule_description}

    def list_products(self, segment_code: str) -> List[Dict[str, Any]]:
        """List default + custom products for a segment."""
        if segment_code not in SEGMENT_CODES:
            return []

        # Default products (frozen)
        out = []
        for p in DEFAULT_SEGMENT_PRODUCTS.get(segment_code, ()):
            d = asdict(p)
            # Stringify Decimals
            if d.get("min_amount_kes") is not None:
                d["min_amount_kes"] = str(d["min_amount_kes"])
            if d.get("max_amount_kes") is not None:
                d["max_amount_kes"] = str(d["max_amount_kes"])
            d["source"] = "default_catalog"
            out.append(d)

        # Custom products (overrides + additions)
        custom = self._load_custom_products().get(segment_code, [])
        for c in custom:
            entry = dict(c)
            entry["source"] = "custom_catalog"
            out.append(entry)

        return out

    def register_product(
        self,
        segment_code: str,
        product_config: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register custom product for a segment."""
        if segment_code not in SEGMENT_CODES:
            return {"registered": False, "error": f"invalid_segment_code:{segment_code}"}
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        # Required fields
        for f in ("product_code", "product_name", "product_type"):
            if f not in product_config or not product_config[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        custom = self._load_custom_products()
        existing = custom.get(segment_code, [])

        # Reject duplicates
        if any(p.get("product_code") == product_config["product_code"] for p in existing):
            return {"registered": False, "error": "duplicate_product_code"}

        record = dict(product_config)
        record["registered_by"] = actor
        record["registered_at"] = datetime.utcnow().isoformat()
        record["reason"] = reason
        existing.append(record)
        custom[segment_code] = existing
        ok = self._save_custom_products(custom)
        return {"registered": ok, "segment_code": segment_code,
                 "product_code": product_config["product_code"]}

    def segment_proposition_summary(
        self, segment_code: str
    ) -> Dict[str, Any]:
        """Aggregated proposition view for a segment."""
        if segment_code not in SEGMENT_CODES:
            return {"error": f"invalid_segment_code:{segment_code}"}

        rule = self.eligibility_rules.get(segment_code)
        products = self.list_products(segment_code)
        from collections import Counter
        type_counts = Counter(p["product_type"] for p in products)

        return {
            "segment_code": segment_code,
            "eligibility_rule": rule.rule_description if rule else None,
            "required_attrs": list(rule.required_attrs) if rule else [],
            "product_count": len(products),
            "by_product_type": dict(type_counts),
            "products": products,
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SegmentPropositionsEngine(
            custom_products_path=Path(tmpdir) / "custom.json"
        )

        # Test 1: WOMEN eligibility — gender F → eligible
        r = engine.check_eligibility("WOMEN", {"gender_self_id": "F"})
        assert r["eligible"], r

        # Test 2: WOMEN eligibility — gender M → not eligible, reason captured
        r = engine.check_eligibility("WOMEN", {"gender_self_id": "M"})
        assert not r["eligible"]
        assert "gender_self_id_not_F" in r["reasons"]

        # Test 3: DIASPORA eligibility — resident != domicile
        r = engine.check_eligibility("DIASPORA", {
            "resident_country": "US", "domicile_country": "KE"
        })
        assert r["eligible"]

        # Test 4: DIASPORA — same country, not eligible
        r = engine.check_eligibility("DIASPORA", {
            "resident_country": "KE", "domicile_country": "KE"
        })
        assert not r["eligible"]

        # Test 5: YOUTH age ranges
        assert engine.check_eligibility("YOUTH", {"age": 25})["eligible"]
        assert engine.check_eligibility("YOUTH", {"age": 17})["eligible"] is False
        assert engine.check_eligibility("YOUTH", {"age": 36})["eligible"] is False

        # Test 6: AGRI — primary_income_source
        assert engine.check_eligibility("AGRI", {
            "primary_income_source": "agriculture"
        })["eligible"]
        assert not engine.check_eligibility("AGRI", {
            "primary_income_source": "salary"
        })["eligible"]

        # Test 7: ASSET_FINANCE — both conditions
        r = engine.check_eligibility("ASSET_FINANCE", {
            "asset_purchase_intent": True, "income_kes": 75000
        })
        assert r["eligible"]
        r = engine.check_eligibility("ASSET_FINANCE", {
            "asset_purchase_intent": True, "income_kes": 30000
        })
        assert not r["eligible"]
        assert any("income_below_50000" in x for x in r["reasons"])

        # Test 8: SME
        r = engine.check_eligibility("SME", {
            "annual_turnover_kes": 50000000, "employee_count": 25
        })
        assert r["eligible"]
        r = engine.check_eligibility("SME", {
            "annual_turnover_kes": 200000000, "employee_count": 25
        })
        assert not r["eligible"]

        # Test 9: Rule 6 — unknown segment rejected
        r = engine.check_eligibility("INVALID", {})
        assert not r["eligible"]
        assert any("unknown_segment_code" in x for x in r["reasons"])

        # Test 10: Rule 1 — missing required attrs surfaced
        r = engine.check_eligibility("WOMEN", {})
        assert not r["eligible"]
        assert "gender_self_id" in r["missing_attrs"]
        assert "missing_required_attrs" in r["reasons"]

        # Test 11: list_products returns default catalog
        women_products = engine.list_products("WOMEN")
        assert len(women_products) >= 3
        assert all(p["source"] == "default_catalog" for p in women_products)
        product_codes = {p["product_code"] for p in women_products}
        assert "WB-SAV-001" in product_codes

        # Test 12: register custom product
        result = engine.register_product(
            "WOMEN",
            {
                "product_code": "WB-CUSTOM-001",
                "product_name": "Custom Women Product",
                "product_type": "INVESTMENT",
            },
            actor="alice",
            reason="new product launch",
        )
        assert result["registered"], result

        # Test 13: now custom appears in list
        women_products = engine.list_products("WOMEN")
        custom = [p for p in women_products if p["source"] == "custom_catalog"]
        assert len(custom) == 1
        assert custom[0]["product_code"] == "WB-CUSTOM-001"

        # Test 14: duplicate product code rejected
        result = engine.register_product(
            "WOMEN",
            {
                "product_code": "WB-CUSTOM-001",
                "product_name": "Dup",
                "product_type": "SAVINGS",
            },
            actor="alice", reason="test",
        )
        assert not result["registered"]
        assert result["error"] == "duplicate_product_code"

        # Test 15: segment_proposition_summary
        summary = engine.segment_proposition_summary("WOMEN")
        assert summary["segment_code"] == "WOMEN"
        assert summary["product_count"] >= 4  # 3 default + 1 custom

    print("  ✅ segment_propositions self-test PASS")


if __name__ == "__main__":
    _self_test()
