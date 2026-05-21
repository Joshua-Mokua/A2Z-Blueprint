"""
================================================================================
A2Z MIS 360 — Standard #392: Personalization Engine (AI-Powered)
================================================================================

Risk classification: Cat C (deterministic personalization with Rule 7
                              hook for ML-driven customization)

ML-based content personalization: subject lines, messaging, offers,
CTAs. Per-customer optimization. v10.279 ships deterministic
heuristics with a Rule 7 ML hook factory.

Public API:
    register_variant(variant_data, actor, reason)
    select_variant(campaign_id, customer_attrs, ml_score_fn=None)
        -> Dict with variant + reason
    make_personalization_fn(behavioral_profile=None) -> Callable
    list_variants(campaign_id) -> List

PERSONALIZATION_DIMENSIONS byte-for-byte (5):
    SUBJECT_LINE, BODY_COPY, OFFER, CTA_TEXT, SEND_TIME

VARIANT_STATES byte-for-byte (4):
    DRAFT, ACTIVE, RETIRED, ARCHIVED

SPEC_DEVIATION_NOTE — production ML-driven personalization deferred.

Honesty rules:
    Rule 1: empty variants → reason="no_variants_registered"
    Rule 4: actor + reason mandatory
    Rule 6: invalid dimension / state rejected
    Rule 7: SPEC_DEVIATION_NOTE for ML deferral

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #392 specifies ML-based content personalization. "
    "v10.279 ships deterministic variant selection with a Rule 7 ML hook "
    "factory. Production ML personalization requires labeled historical "
    "engagement data + supervised model with fairness constraints, "
    "deferred to deployment phase. Until then, select_variant() falls "
    "back to behavioral_tier-based heuristics."
)


PERSONALIZATION_DIMENSIONS: Tuple[str, ...] = (
    "SUBJECT_LINE", "BODY_COPY", "OFFER", "CTA_TEXT", "SEND_TIME",
)

VARIANT_STATES: Tuple[str, ...] = ("DRAFT", "ACTIVE", "RETIRED", "ARCHIVED")

ALLOWED_VARIANT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":    ("ACTIVE", "ARCHIVED"),
    "ACTIVE":   ("RETIRED", "ARCHIVED"),
    "RETIRED":  ("ARCHIVED",),
    "ARCHIVED": (),
}


class CampaignsPersonalizationEngine:
    """Variant registry + selection (with optional ML hook)."""

    def __init__(self, variants_path: Optional[Path] = None):
        base = Path(__file__).parent.parent / "data"
        self.variants_path = variants_path or base / "campaign_variants.json"

    def _load(self) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(self.variants_path,
                                       table="campaign_variants",
                                       index_cols=("variant_id",))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, records: List[Dict[str, Any]]) -> bool:
        try:
            from utils.db import db as _db
            self.variants_path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(self.variants_path, data=records,
                              table="campaign_variants", pk_col="variant_id")
            return True
        except Exception:
            return False

    def register_variant(
        self, variant_data: Dict[str, Any],
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("variant_id", "campaign_id", "dimension", "content"):
            if f not in variant_data:
                return {"registered": False, "error": f"missing_field:{f}"}
        if variant_data["dimension"] not in PERSONALIZATION_DIMENSIONS:
            return {
                "registered": False,
                "error": f"invalid_dimension:{variant_data['dimension']}",
                "valid_dimensions": list(PERSONALIZATION_DIMENSIONS),
            }
        records = self._load()
        if any(r.get("variant_id") == variant_data["variant_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_variant_id"}
        records.append({
            "variant_id": variant_data["variant_id"],
            "campaign_id": variant_data["campaign_id"],
            "dimension": variant_data["dimension"],
            "content": variant_data["content"],
            "target_segment": variant_data.get("target_segment"),
            "target_spending_tier": variant_data.get("target_spending_tier"),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(records)
        return {"registered": ok, "variant_id": variant_data["variant_id"]}

    def transition_variant_state(
        self, variant_id: str, new_state: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False, "error": "actor_and_reason_required"}
        if new_state not in VARIANT_STATES:
            return {"transitioned": False, "error": f"invalid_state:{new_state}"}
        records = self._load()
        for r in records:
            if r.get("variant_id") == variant_id:
                current = r.get("state", "DRAFT")
                if new_state not in ALLOWED_VARIANT_TRANSITIONS.get(current, ()):
                    return {"transitioned": False,
                              "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                ok = self._save(records)
                return {"transitioned": ok}
        return {"transitioned": False, "error": "variant_not_found"}

    def select_variant(
        self, campaign_id: str, dimension: str,
        customer_attrs: Dict[str, Any],
        ml_score_fn: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Decimal]] = None,
    ) -> Dict[str, Any]:
        if dimension not in PERSONALIZATION_DIMENSIONS:
            return {"selected": False,
                      "error": f"invalid_dimension:{dimension}"}
        active = [
            r for r in self._load()
            if r.get("campaign_id") == campaign_id
            and r.get("dimension") == dimension
            and r.get("state") == "ACTIVE"
        ]
        if not active:
            return {
                "selected": False,
                "campaign_id": campaign_id,
                "dimension": dimension,
                "reason": "no_active_variants",
            }

        # Filter by segment + spending tier match
        seg = customer_attrs.get("segment")
        tier = customer_attrs.get("spending_tier")
        candidates = []
        for v in active:
            target_seg = v.get("target_segment")
            target_tier = v.get("target_spending_tier")
            if target_seg and target_seg != seg:
                continue
            if target_tier and target_tier != tier:
                continue
            candidates.append(v)
        if not candidates:
            candidates = active  # fallback to all active

        # Score with ML if provided, else deterministic
        if ml_score_fn is not None:
            try:
                scored = [(v, ml_score_fn(v, customer_attrs)) for v in candidates]
                best = max(scored, key=lambda x: x[1])
                return {
                    "selected": True,
                    "variant_id": best[0]["variant_id"],
                    "content": best[0]["content"],
                    "scoring_method": "ml_score_fn",
                    "score": str(best[1]),
                    "candidate_count": len(candidates),
                }
            except Exception as e:
                # ML failed → fall back deterministic
                pass

        # Deterministic: pick variant with most-specific targeting
        def _specificity(v: Dict[str, Any]) -> int:
            s = 0
            if v.get("target_segment"):
                s += 1
            if v.get("target_spending_tier"):
                s += 1
            return s

        candidates.sort(key=_specificity, reverse=True)
        chosen = candidates[0]
        return {
            "selected": True,
            "variant_id": chosen["variant_id"],
            "content": chosen["content"],
            "scoring_method": "deterministic_specificity",
            "candidate_count": len(candidates),
        }

    def make_personalization_fn(
        self, behavioral_profile: Optional[Any] = None,
    ) -> Callable[[Dict[str, Any], Dict[str, Any]], Decimal]:
        """Returns an ml_score_fn matching select_variant's contract.

        Signature: fn(variant, customer_attrs) -> Decimal score [0..100].
        Deterministic heuristic in v10.279; production ML hook target.
        """
        def _score_fn(variant: Dict[str, Any],
                          customer_attrs: Dict[str, Any]) -> Decimal:
            score = Decimal("50")  # neutral baseline
            # Segment match boost
            if variant.get("target_segment") == customer_attrs.get("segment"):
                score += Decimal("20")
            # Spending tier match boost
            if variant.get("target_spending_tier") == customer_attrs.get("spending_tier"):
                score += Decimal("15")
            # behavioral_profile integration if available
            if behavioral_profile is not None and customer_attrs.get("customer_id"):
                try:
                    cust_id = customer_attrs["customer_id"]
                    loyalty = behavioral_profile.customer_loyalty_score(cust_id)
                    if loyalty.get("score") is not None:
                        score += min(Decimal("15"),
                                          Decimal(loyalty["score"]) / Decimal("10"))
                except Exception:
                    pass
            return min(Decimal("100"), score)
        return _score_fn

    def list_variants(self, campaign_id: str) -> List[Dict[str, Any]]:
        return [r for r in self._load()
                  if r.get("campaign_id") == campaign_id]


def _self_test() -> None:
    import tempfile

    assert "SUBJECT_LINE" in PERSONALIZATION_DIMENSIONS
    assert ALLOWED_VARIANT_TRANSITIONS["ARCHIVED"] == ()
    assert "v10.279" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CampaignsPersonalizationEngine(
            variants_path=Path(tmpdir) / "v.json",
        )

        # Test 1: register variants
        r = engine.register_variant(
            {"variant_id": "V-1", "campaign_id": "CAMP-001",
             "dimension": "SUBJECT_LINE",
             "content": "Welcome to our exclusive Diaspora program",
             "target_segment": "DIASPORA"},
            actor="x", reason="r",
        )
        assert r["registered"]
        engine.register_variant(
            {"variant_id": "V-2", "campaign_id": "CAMP-001",
             "dimension": "SUBJECT_LINE",
             "content": "Generic welcome — explore our services"},
            actor="x", reason="r",
        )

        # Test 2: invalid dimension
        r = engine.register_variant(
            {"variant_id": "X", "campaign_id": "Y",
             "dimension": "INVALID", "content": "z"},
            actor="x", reason="r",
        )
        assert not r["registered"]

        # Test 3: select before activation → no_active_variants
        s = engine.select_variant(
            "CAMP-001", "SUBJECT_LINE",
            {"customer_id": "C1", "segment": "DIASPORA"},
        )
        assert not s["selected"]
        assert s["reason"] == "no_active_variants"

        # Test 4: activate variants
        engine.transition_variant_state(
            "V-1", "ACTIVE", actor="x", reason="r",
        )
        engine.transition_variant_state(
            "V-2", "ACTIVE", actor="x", reason="r",
        )

        # Test 5: select for DIASPORA → V-1 (more specific)
        s = engine.select_variant(
            "CAMP-001", "SUBJECT_LINE",
            {"customer_id": "C1", "segment": "DIASPORA"},
        )
        assert s["selected"]
        assert s["variant_id"] == "V-1"

        # Test 6: select for YOUTH → V-2 (no specific match → fallback)
        s = engine.select_variant(
            "CAMP-001", "SUBJECT_LINE",
            {"customer_id": "C2", "segment": "YOUTH"},
        )
        assert s["selected"]
        assert s["variant_id"] == "V-2"

        # Test 7: Rule 7 hook
        score_fn = engine.make_personalization_fn()
        s = engine.select_variant(
            "CAMP-001", "SUBJECT_LINE",
            {"customer_id": "C1", "segment": "DIASPORA"},
            ml_score_fn=score_fn,
        )
        assert s["selected"]
        assert s["scoring_method"] == "ml_score_fn"
        assert s["variant_id"] == "V-1"

        # Test 8: invalid dimension at select
        s = engine.select_variant(
            "CAMP-001", "INVALID", {"customer_id": "C1"},
        )
        assert not s["selected"]

        # Test 9: list_variants
        variants = engine.list_variants("CAMP-001")
        assert len(variants) == 2

    print("  ✅ campaigns_personalization self-test PASS")


if __name__ == "__main__":
    _self_test()
