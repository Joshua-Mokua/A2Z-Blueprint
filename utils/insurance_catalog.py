"""
================================================================================
A2Z MIS 360 — Standard #301: Insurance Product Catalog & Policy Lifecycle
================================================================================

Risk classification: Cat A + Cat C (financial — premium handling,
                                       customer policy lifecycle)

Multi-insurer insurance product catalog with policy issuance, premium
collection, renewal, claims tracking, and customer policy 360 view.
This is the foundational engine for the bancassurance cluster.

Public API:
    register_product(insurer_id, product_data, actor, reason)
    issue_policy(customer_id, product_code, policy_data, actor)
    transition_policy_state(policy_id, new_state, actor, reason)
    list_customer_policies(customer_id, state="ACTIVE")
    record_premium(policy_id, amount_kes, due_date, actor)
    customer_policy_360(customer_id) -> consolidated view

INSURANCE_PRODUCT_TYPES byte-for-byte (Continuation.docx #301 + regulator):
    LIFE                    -- term life, whole life, endowment
    HEALTH                  -- medical, dental, vision
    MOTOR                   -- comprehensive, third-party
    PROPERTY                -- household, commercial property
    TRAVEL                  -- travel insurance
    PERSONAL_ACCIDENT       -- PA cover
    EDUCATION               -- education endowment
    PENSION                 -- retirement annuities
    BUSINESS                -- SME insurance bundles
    MARINE                  -- marine + cargo

POLICY_STATES byte-for-byte:
    QUOTED                  -- quote generated; customer reviewing
    APPLIED                 -- application submitted; underwriting pending
    UNDERWRITING            -- in underwriting review
    ACTIVE                  -- inforce; premiums being collected
    LAPSED                  -- premium overdue beyond grace period
    SUSPENDED               -- temporarily suspended (compliance/dispute)
    EXPIRED                 -- term ended; not renewed (terminal)
    CANCELLED               -- formally cancelled before term end (terminal)
    SURRENDERED             -- customer surrendered (terminal, with refund)

ALLOWED_POLICY_TRANSITIONS (Rule 4 strict):
    QUOTED       → APPLIED | CANCELLED
    APPLIED      → UNDERWRITING | CANCELLED
    UNDERWRITING → ACTIVE | CANCELLED
    ACTIVE       → LAPSED | SUSPENDED | EXPIRED | CANCELLED | SURRENDERED
    LAPSED       → ACTIVE | EXPIRED | CANCELLED       (revival possible
                                                       within grace period)
    SUSPENDED    → ACTIVE | CANCELLED
    EXPIRED      → ()                                  -- terminal
    CANCELLED    → ()                                  -- terminal
    SURRENDERED  → ()                                  -- terminal

PREMIUM_FREQUENCIES byte-for-byte:
    SINGLE          -- one-time premium
    MONTHLY         -- monthly
    QUARTERLY       -- 3-monthly
    SEMI_ANNUAL     -- 6-monthly
    ANNUAL          -- yearly

DEFAULT_GRACE_PERIOD_DAYS = 30  -- regulator standard for life products

Honesty rules:
    Rule 4: actor + reason mandatory; no skip transitions
    Rule 6: invalid type/state/frequency rejected (fail-closed)
    Rule 1: customer_policy_360 returns empty list for unknown customer

================================================================================
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 28


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

INSURANCE_PRODUCT_TYPES: Tuple[str, ...] = (
    "LIFE", "HEALTH", "MOTOR", "PROPERTY", "TRAVEL",
    "PERSONAL_ACCIDENT", "EDUCATION", "PENSION", "BUSINESS", "MARINE",
)

POLICY_STATES: Tuple[str, ...] = (
    "QUOTED", "APPLIED", "UNDERWRITING", "ACTIVE",
    "LAPSED", "SUSPENDED", "EXPIRED", "CANCELLED", "SURRENDERED",
)

ALLOWED_POLICY_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "QUOTED":       ("APPLIED", "CANCELLED"),
    "APPLIED":      ("UNDERWRITING", "CANCELLED"),
    "UNDERWRITING": ("ACTIVE", "CANCELLED"),
    "ACTIVE":       ("LAPSED", "SUSPENDED", "EXPIRED", "CANCELLED", "SURRENDERED"),
    "LAPSED":       ("ACTIVE", "EXPIRED", "CANCELLED"),
    "SUSPENDED":    ("ACTIVE", "CANCELLED"),
    "EXPIRED":      (),
    "CANCELLED":    (),
    "SURRENDERED":  (),
}

PREMIUM_FREQUENCIES: Tuple[str, ...] = (
    "SINGLE", "MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL",
)

DEFAULT_GRACE_PERIOD_DAYS: int = 30


class InsuranceCatalogEngine:
    """Multi-insurer product catalog + policy lifecycle."""

    def __init__(
        self,
        products_path: Optional[Path] = None,
        policies_path: Optional[Path] = None,
        premiums_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.products_path = products_path or base / "insurance_products.json"
        self.policies_path = policies_path or base / "insurance_policies.json"
        self.premiums_path = premiums_path or base / "insurance_premiums.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    # ── Products ───────────────────────────────────────────────────

    def register_product(
        self,
        insurer_id: str,
        product_data: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register insurance product in catalog."""
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        for f in ("product_code", "product_name", "product_type"):
            if f not in product_data or not product_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        if product_data["product_type"] not in INSURANCE_PRODUCT_TYPES:
            return {
                "registered": False,
                "error": f"invalid_product_type:{product_data['product_type']}",
                "valid_types": list(INSURANCE_PRODUCT_TYPES),
            }

        records = self._load(self.products_path, "insurance_products",
                                ("product_code",))
        if any(r.get("product_code") == product_data["product_code"]
                 for r in records):
            return {"registered": False, "error": "duplicate_product_code"}

        record = {
            "product_code": product_data["product_code"],
            "insurer_id": insurer_id,
            "product_name": product_data["product_name"],
            "product_type": product_data["product_type"],
            "description": product_data.get("description", ""),
            "min_sum_assured_kes": str(product_data.get("min_sum_assured_kes", 0)),
            "max_sum_assured_kes": str(product_data.get("max_sum_assured_kes", 0)),
            "default_term_months": int(product_data.get("default_term_months", 12)),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.products_path, records,
                          "insurance_products", "product_code")
        return {"registered": ok, "product_code": product_data["product_code"]}

    def list_products(
        self,
        insurer_id: Optional[str] = None,
        product_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.products_path, "insurance_products",
                                ("product_code",))
        out = []
        for r in records:
            if insurer_id and r.get("insurer_id") != insurer_id:
                continue
            if product_type and r.get("product_type") != product_type:
                continue
            out.append(r)
        return out

    # ── Policies ───────────────────────────────────────────────────

    def issue_policy(
        self,
        customer_id: str,
        product_code: str,
        policy_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        """Issue new policy in QUOTED state."""
        if not actor:
            return {"issued": False, "error": "actor_required"}

        for f in ("policy_id", "sum_assured_kes",
                    "premium_kes", "premium_frequency",
                    "effective_date", "expiry_date"):
            if f not in policy_data or policy_data[f] in (None, ""):
                return {"issued": False, "error": f"missing_field:{f}"}

        if policy_data["premium_frequency"] not in PREMIUM_FREQUENCIES:
            return {
                "issued": False,
                "error": f"invalid_frequency:{policy_data['premium_frequency']}",
            }

        # Validate product exists
        products = self._load(self.products_path, "insurance_products",
                                  ("product_code",))
        product = next(
            (p for p in products if p.get("product_code") == product_code),
            None,
        )
        if product is None:
            return {"issued": False, "error": f"unknown_product:{product_code}"}

        # Validate dates
        try:
            eff = date.fromisoformat(policy_data["effective_date"])
            exp = date.fromisoformat(policy_data["expiry_date"])
        except (ValueError, TypeError):
            return {"issued": False, "error": "invalid_date_format"}
        if exp <= eff:
            return {"issued": False, "error": "expiry_not_after_effective"}

        # Validate sum assured
        try:
            sa = Decimal(str(policy_data["sum_assured_kes"]))
            premium = Decimal(str(policy_data["premium_kes"]))
        except (ValueError, TypeError):
            return {"issued": False, "error": "amounts_not_decimal"}
        if sa <= 0 or premium <= 0:
            return {"issued": False, "error": "amounts_must_be_positive"}

        records = self._load(self.policies_path, "insurance_policies",
                                ("policy_id",))
        if any(r.get("policy_id") == policy_data["policy_id"] for r in records):
            return {"issued": False, "error": "duplicate_policy_id"}

        record = {
            "policy_id": policy_data["policy_id"],
            "customer_id": customer_id,
            "product_code": product_code,
            "insurer_id": product["insurer_id"],
            "state": "QUOTED",
            "sum_assured_kes": str(sa),
            "premium_kes": str(premium),
            "premium_frequency": policy_data["premium_frequency"],
            "effective_date": policy_data["effective_date"],
            "expiry_date": policy_data["expiry_date"],
            "grace_period_days": int(policy_data.get(
                "grace_period_days", DEFAULT_GRACE_PERIOD_DAYS)),
            "issued_by": actor,
            "issued_at": datetime.utcnow().isoformat(),
            "transitions": [{
                "to": "QUOTED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
                "reason": "policy_issued",
            }],
        }
        records.append(record)
        ok = self._save(self.policies_path, records,
                          "insurance_policies", "policy_id")
        return {"issued": ok, "policy_id": policy_data["policy_id"]}

    def transition_policy_state(
        self,
        policy_id: str,
        new_state: str,
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Transition policy state (Rule 4 no-skip)."""
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in POLICY_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}

        records = self._load(self.policies_path, "insurance_policies",
                                ("policy_id",))
        for r in records:
            if r.get("policy_id") == policy_id:
                current = r.get("state", "QUOTED")
                allowed = ALLOWED_POLICY_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {
                        "transitioned": False,
                        "error": f"transition_not_allowed:{current}_to_{new_state}",
                        "current_state": current,
                        "allowed": list(allowed),
                    }
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.policies_path, records,
                                  "insurance_policies", "policy_id")
                return {"transitioned": ok, "from": current, "to": new_state}

        return {"transitioned": False, "error": "policy_not_found"}

    def list_customer_policies(
        self,
        customer_id: str,
        state: Optional[str] = "ACTIVE",
    ) -> List[Dict[str, Any]]:
        records = self._load(self.policies_path, "insurance_policies",
                                ("policy_id",))
        out = []
        for r in records:
            if r.get("customer_id") != customer_id:
                continue
            if state and r.get("state") != state:
                continue
            out.append(r)
        return out

    # ── Premiums ───────────────────────────────────────────────────

    def record_premium(
        self,
        policy_id: str,
        amount_kes: Decimal,
        due_date: str,
        actor: str,
        paid_date: Optional[str] = None,
        notes: str = "",
    ) -> Dict[str, Any]:
        """Record premium installment."""
        if not actor:
            return {"recorded": False, "error": "actor_required"}

        try:
            amt = Decimal(str(amount_kes))
        except (ValueError, TypeError):
            return {"recorded": False, "error": "amount_not_decimal"}
        if amt <= 0:
            return {"recorded": False, "error": "amount_must_be_positive"}

        try:
            date.fromisoformat(due_date)
            if paid_date:
                date.fromisoformat(paid_date)
        except (ValueError, TypeError):
            return {"recorded": False, "error": "invalid_date_format"}

        # Validate policy exists
        policies = self._load(self.policies_path, "insurance_policies",
                                  ("policy_id",))
        if not any(p.get("policy_id") == policy_id for p in policies):
            return {"recorded": False, "error": "policy_not_found"}

        records = self._load(self.premiums_path, "insurance_premiums",
                                ("policy_id", "due_date"))
        record = {
            "premium_id": f"PR-{policy_id}-{due_date}",
            "policy_id": policy_id,
            "amount_kes": str(amt),
            "due_date": due_date,
            "paid_date": paid_date,
            "status": "PAID" if paid_date else "PENDING",
            "actor": actor,
            "notes": notes,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.premiums_path, records,
                          "insurance_premiums", "premium_id")
        return {"recorded": ok, "premium_id": record["premium_id"]}

    def overdue_premiums(self, as_of: Optional[date] = None) -> List[Dict[str, Any]]:
        """Pending premiums past due date."""
        as_of = as_of or date.today()
        records = self._load(self.premiums_path, "insurance_premiums",
                                ("policy_id", "due_date"))
        out = []
        for r in records:
            if r.get("status") != "PENDING":
                continue
            try:
                due = date.fromisoformat(r["due_date"])
            except (ValueError, TypeError):
                continue
            if due < as_of:
                out.append({
                    "premium_id": r["premium_id"],
                    "policy_id": r["policy_id"],
                    "due_date": r["due_date"],
                    "days_overdue": (as_of - due).days,
                    "amount_kes": r["amount_kes"],
                })
        out.sort(key=lambda x: x["days_overdue"], reverse=True)
        return out

    # ── 360° View ──────────────────────────────────────────────────

    def customer_policy_360(self, customer_id: str) -> Dict[str, Any]:
        """Consolidated customer policy view across insurers."""
        policies = self.list_customer_policies(customer_id, state=None)

        if not policies:
            return {
                "customer_id": customer_id,
                "policies": [],
                "by_state": {},
                "by_product_type": {},
                "by_insurer": {},
                "total_sum_assured_kes": "0",
                "total_annual_premium_kes": "0",
            }

        # Build product code → type lookup
        products = self._load(self.products_path, "insurance_products",
                                  ("product_code",))
        product_lookup = {p["product_code"]: p for p in products}

        from collections import Counter
        by_state = Counter(p.get("state") for p in policies)
        by_insurer = Counter(p.get("insurer_id") for p in policies)
        by_type = Counter()
        total_sa = Decimal("0")
        total_annual = Decimal("0")

        FREQUENCY_PER_YEAR = {
            "SINGLE": 0,  # not annual
            "MONTHLY": 12, "QUARTERLY": 4,
            "SEMI_ANNUAL": 2, "ANNUAL": 1,
        }

        for p in policies:
            prod = product_lookup.get(p.get("product_code"), {})
            ptype = prod.get("product_type", "UNKNOWN")
            by_type[ptype] += 1
            try:
                total_sa += Decimal(p["sum_assured_kes"])
                premium = Decimal(p["premium_kes"])
                freq_count = FREQUENCY_PER_YEAR.get(p.get("premium_frequency"), 0)
                total_annual += premium * Decimal(freq_count)
            except (ValueError, TypeError, KeyError):
                continue

        return {
            "customer_id": customer_id,
            "policies": policies,
            "policy_count": len(policies),
            "by_state": dict(by_state),
            "by_product_type": dict(by_type),
            "by_insurer": dict(by_insurer),
            "total_sum_assured_kes": str(total_sa.quantize(Decimal("0.01"))),
            "total_annual_premium_kes": str(total_annual.quantize(Decimal("0.01"))),
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = InsuranceCatalogEngine(
            products_path=Path(tmpdir) / "p.json",
            policies_path=Path(tmpdir) / "po.json",
            premiums_path=Path(tmpdir) / "pr.json",
        )

        # Test 1: register product
        r = engine.register_product(
            "INS-BRITAM",
            {"product_code": "BR-LIFE-001", "product_name": "Britam Term Life",
             "product_type": "LIFE",
             "min_sum_assured_kes": "100000",
             "max_sum_assured_kes": "10000000",
             "default_term_months": 240},
            actor="bd_lead", reason="initial catalog setup",
        )
        assert r["registered"], r

        # Test 2: invalid product type rejected
        r = engine.register_product(
            "INS-BRITAM",
            {"product_code": "BR-X", "product_name": "X",
             "product_type": "INVALID"},
            actor="bd", reason="bad",
        )
        assert not r["registered"]
        assert "invalid_product_type" in r["error"]

        # Test 3: duplicate product code rejected
        r = engine.register_product(
            "INS-OTHER",
            {"product_code": "BR-LIFE-001", "product_name": "Dup",
             "product_type": "LIFE"},
            actor="bd", reason="dup",
        )
        assert not r["registered"]

        # Test 4: list products
        products = engine.list_products(insurer_id="INS-BRITAM")
        assert len(products) == 1
        products = engine.list_products(product_type="LIFE")
        assert len(products) == 1

        # Test 5: issue policy
        r = engine.issue_policy(
            "CUST-001", "BR-LIFE-001",
            {"policy_id": "POL-001",
             "sum_assured_kes": "1000000",
             "premium_kes": "12000",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )
        assert r["issued"], r

        # Test 6: unknown product rejected
        r = engine.issue_policy(
            "CUST-002", "UNKNOWN-PROD",
            {"policy_id": "POL-X",
             "sum_assured_kes": "100",
             "premium_kes": "10",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )
        assert not r["issued"]
        assert "unknown_product" in r["error"]

        # Test 7: invalid frequency rejected
        r = engine.issue_policy(
            "CUST-003", "BR-LIFE-001",
            {"policy_id": "POL-X2",
             "sum_assured_kes": "100",
             "premium_kes": "10",
             "premium_frequency": "WEEKLY",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )
        assert not r["issued"]

        # Test 8: expiry before effective rejected
        r = engine.issue_policy(
            "CUST-004", "BR-LIFE-001",
            {"policy_id": "POL-X3",
             "sum_assured_kes": "100",
             "premium_kes": "10",
             "premium_frequency": "ANNUAL",
             "effective_date": "2027-01-01",
             "expiry_date": "2026-01-01"},
            actor="rm",
        )
        assert not r["issued"]

        # Test 9: state lifecycle QUOTED → APPLIED → UNDERWRITING → ACTIVE
        for new_state, reason in [("APPLIED", "customer signed"),
                                       ("UNDERWRITING", "submitted to insurer"),
                                       ("ACTIVE", "underwriting passed")]:
            t = engine.transition_policy_state(
                "POL-001", new_state, actor="rm", reason=reason
            )
            assert t["transitioned"], (new_state, t)

        # Test 10: skip rejected ACTIVE → APPLIED
        t = engine.transition_policy_state(
            "POL-001", "APPLIED", actor="rm", reason="skip"
        )
        assert not t["transitioned"]
        assert "transition_not_allowed" in t["error"]

        # Test 11: ACTIVE → LAPSED → ACTIVE (revival)
        t = engine.transition_policy_state(
            "POL-001", "LAPSED", actor="ops",
            reason="premium overdue 35 days"
        )
        assert t["transitioned"]
        t = engine.transition_policy_state(
            "POL-001", "ACTIVE", actor="ops",
            reason="customer revived; outstanding paid"
        )
        assert t["transitioned"]

        # Test 12: ACTIVE → SURRENDERED → terminal
        t = engine.transition_policy_state(
            "POL-001", "SURRENDERED", actor="ops",
            reason="customer surrendered for cash value"
        )
        assert t["transitioned"]
        # Terminal — cannot transition
        t = engine.transition_policy_state(
            "POL-001", "ACTIVE", actor="ops",
            reason="trying to revive surrendered"
        )
        assert not t["transitioned"]

        # Test 13: record premium
        engine.issue_policy(
            "CUST-001", "BR-LIFE-001",
            {"policy_id": "POL-002",
             "sum_assured_kes": "500000",
             "premium_kes": "6000",
             "premium_frequency": "ANNUAL",
             "effective_date": "2026-01-01",
             "expiry_date": "2027-01-01"},
            actor="rm",
        )
        engine.transition_policy_state("POL-002", "APPLIED", "rm", "ok")
        engine.transition_policy_state("POL-002", "UNDERWRITING", "rm", "ok")
        engine.transition_policy_state("POL-002", "ACTIVE", "rm", "ok")

        pr = engine.record_premium(
            "POL-002", Decimal("6000"),
            due_date="2026-01-01",
            actor="finance",
            paid_date="2026-01-05",
        )
        assert pr["recorded"]

        # Test 14: overdue premium detection
        pr = engine.record_premium(
            "POL-002", Decimal("6000"),
            due_date="2026-04-01",  # past
            actor="finance",
            paid_date=None,
        )
        assert pr["recorded"]
        overdue = engine.overdue_premiums(as_of=date(2026, 5, 7))
        # POL-002 has a PENDING due 2026-04-01, overdue by 36 days
        assert any(o["policy_id"] == "POL-002" for o in overdue)

        # Test 15: customer_policy_360
        view = engine.customer_policy_360("CUST-001")
        assert view["policy_count"] == 2
        assert "BR-LIFE-001" in [p.get("product_code") for p in view["policies"]]
        # POL-001 surrendered, POL-002 active
        assert view["by_state"]["SURRENDERED"] == 1
        assert view["by_state"]["ACTIVE"] == 1
        assert view["by_product_type"]["LIFE"] == 2

        # Test 16: Rule 1 — unknown customer returns empty
        empty = engine.customer_policy_360("UNKNOWN")
        assert empty["policies"] == []
        assert Decimal(empty["total_sum_assured_kes"]) == Decimal("0")

    print("  ✅ insurance_catalog self-test PASS")


if __name__ == "__main__":
    _self_test()
