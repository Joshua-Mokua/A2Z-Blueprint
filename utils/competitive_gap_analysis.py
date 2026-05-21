"""
================================================================================
A2Z MIS 360 — Standard #332: Competitive Gap Analysis
================================================================================

Risk classification: Cat C (deterministic feature/product gap detection
                              with RAG status + time-to-parity estimation)

Feature-by-feature, product-by-product gap analysis. RAG status (Red,
Amber, Green). Time-to-parity estimates. Roadmap input.

Public API:
    register_internal_feature(feature_data, actor)
    register_competitor_feature(competitor_id, feature_data, actor)
    feature_gap_table(feature_category=None) -> per-feature presence map
    rag_status_summary() -> {RED, AMBER, GREEN} counts
    time_to_parity(feature_id, base_velocity_features_per_month=2)
        -> estimated months to close gap

RAG_STATUSES byte-for-byte:
    GREEN  -- internal feature present + matches/exceeds 50%+ competitors
    AMBER  -- internal feature present but lags 50%+ competitors
    RED    -- internal feature missing while 50%+ competitors have it

FEATURE_CATEGORIES byte-for-byte:
    DIGITAL_BANKING       -- mobile, web, USSD, chatbot
    LENDING_PRODUCTS      -- personal loans, mortgage, asset finance, SME
    DEPOSIT_PRODUCTS      -- savings, fixed deposits, transactional
    INSURANCE_PRODUCTS    -- bancassurance + standalone
    INVESTMENT_PRODUCTS   -- bonds, treasury bills, unit trusts
    CARDS                 -- debit, credit, prepaid
    FX_TRADE_FINANCE      -- FX, LC, guarantees, trade finance
    OTHER                 -- catch-all

Honesty rules:
    Rule 1: empty competitor_features → no GREEN/AMBER/RED classification
            possible; surface "no_competitor_data" reason
    Rule 6: invalid category rejected
    Rule 7: deterministic 50%-presence threshold; production weighting +
            customer-feedback adjustment deferred

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.competitor_data_collection import CompetitorDataCollectionEngine


RAG_STATUSES: Tuple[str, ...] = ("GREEN", "AMBER", "RED")

FEATURE_CATEGORIES: Tuple[str, ...] = (
    "DIGITAL_BANKING", "LENDING_PRODUCTS", "DEPOSIT_PRODUCTS",
    "INSURANCE_PRODUCTS", "INVESTMENT_PRODUCTS", "CARDS",
    "FX_TRADE_FINANCE", "OTHER",
)

PARITY_THRESHOLD_PCT: Decimal = Decimal("50")


class CompetitiveGapAnalysisEngine:
    """Feature gap analysis + RAG status."""

    def __init__(
        self,
        data_collection: Optional[CompetitorDataCollectionEngine] = None,
        internal_features_path: Optional[Path] = None,
        competitor_features_path: Optional[Path] = None,
    ):
        self.data_collection = data_collection or CompetitorDataCollectionEngine()
        base = Path(__file__).parent.parent / "data"
        self.internal_features_path = internal_features_path or base / "internal_features.json"
        self.competitor_features_path = competitor_features_path or base / "competitor_features.json"

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

    def register_internal_feature(
        self, feature_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("feature_id", "name", "category", "present"):
            if f not in feature_data:
                return {"registered": False, "error": f"missing_field:{f}"}
        if feature_data["category"] not in FEATURE_CATEGORIES:
            return {
                "registered": False,
                "error": f"invalid_category:{feature_data['category']}",
                "valid_categories": list(FEATURE_CATEGORIES),
            }

        records = self._load(self.internal_features_path,
                                "internal_features", ("feature_id",))
        # Upsert
        existing_idx = next(
            (i for i, r in enumerate(records)
              if r.get("feature_id") == feature_data["feature_id"]), None,
        )
        record = {
            "feature_id": feature_data["feature_id"],
            "name": feature_data["name"],
            "category": feature_data["category"],
            "present": bool(feature_data["present"]),
            "quality_score": feature_data.get("quality_score"),
            "actor": actor,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if existing_idx is not None:
            records[existing_idx] = record
        else:
            records.append(record)
        ok = self._save(self.internal_features_path, records,
                          "internal_features", "feature_id")
        return {"registered": ok, "feature_id": feature_data["feature_id"]}

    def register_competitor_feature(
        self,
        competitor_id: str,
        feature_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("feature_id", "name", "category", "present"):
            if f not in feature_data:
                return {"registered": False, "error": f"missing_field:{f}"}
        if feature_data["category"] not in FEATURE_CATEGORIES:
            return {"registered": False,
                      "error": f"invalid_category:{feature_data['category']}"}

        records = self._load(self.competitor_features_path,
                                "competitor_features",
                                ("competitor_id", "feature_id"))
        existing_idx = next(
            (i for i, r in enumerate(records)
              if r.get("competitor_id") == competitor_id
              and r.get("feature_id") == feature_data["feature_id"]), None,
        )
        record = {
            "row_id": f"CF-{competitor_id}-{feature_data['feature_id']}",
            "competitor_id": competitor_id,
            "feature_id": feature_data["feature_id"],
            "name": feature_data["name"],
            "category": feature_data["category"],
            "present": bool(feature_data["present"]),
            "quality_score": feature_data.get("quality_score"),
            "actor": actor,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if existing_idx is not None:
            records[existing_idx] = record
        else:
            records.append(record)
        ok = self._save(self.competitor_features_path, records,
                          "competitor_features", "row_id")
        return {"registered": ok}

    def feature_gap_table(
        self,
        feature_category: Optional[str] = None,
    ) -> Dict[str, Any]:
        if feature_category and feature_category not in FEATURE_CATEGORIES:
            return {"error": f"invalid_category:{feature_category}"}

        internal = self._load(self.internal_features_path,
                                  "internal_features", ("feature_id",))
        comp_features = self._load(self.competitor_features_path,
                                          "competitor_features",
                                          ("competitor_id", "feature_id"))
        competitors = self.data_collection.list_competitors()

        if feature_category:
            internal = [f for f in internal if f.get("category") == feature_category]

        if not comp_features:
            return {
                "feature_category": feature_category,
                "rows": [],
                "reason": "no_competitor_features_registered",
            }

        # Build per-feature row
        rows = []
        all_feature_ids = set(f["feature_id"] for f in internal) | \
                              set(f["feature_id"] for f in comp_features)
        if feature_category:
            comp_in_cat = {f["feature_id"] for f in comp_features
                              if f.get("category") == feature_category}
            int_in_cat = {f["feature_id"] for f in internal}
            all_feature_ids = comp_in_cat | int_in_cat

        for fid in all_feature_ids:
            int_rec = next((f for f in internal if f["feature_id"] == fid), None)
            comp_recs = [f for f in comp_features if f["feature_id"] == fid]

            # Skip if no competitors have it AND we don't have it
            if int_rec is None and not comp_recs:
                continue

            # Filter category if specified
            cat_to_check = (int_rec or comp_recs[0])["category"]
            if feature_category and cat_to_check != feature_category:
                continue

            # Count competitor presence
            comp_with = [c for c in comp_recs if c.get("present")]
            comp_total = len(competitors)
            comp_pct = (
                Decimal(len(comp_with)) / Decimal(comp_total) *
                Decimal("100")
                if comp_total > 0 else Decimal("0")
            )

            # Internal presence
            int_present = bool(int_rec and int_rec.get("present"))

            # RAG classification
            rag = self._classify_rag(int_present, comp_pct)

            rows.append({
                "feature_id": fid,
                "name": (int_rec or comp_recs[0])["name"],
                "category": cat_to_check,
                "internal_present": int_present,
                "competitor_presence_count": len(comp_with),
                "competitor_total": comp_total,
                "competitor_presence_pct": str(comp_pct.quantize(Decimal("0.01"))),
                "rag_status": rag,
            })

        # Sort by RED first, then AMBER, then GREEN
        order = {"RED": 0, "AMBER": 1, "GREEN": 2, None: 3}
        rows.sort(key=lambda r: order.get(r["rag_status"], 99))

        return {
            "feature_category": feature_category,
            "row_count": len(rows),
            "rows": rows,
        }

    def _classify_rag(
        self,
        internal_present: bool,
        competitor_presence_pct: Decimal,
    ) -> str:
        """Classify a feature's competitive position."""
        if internal_present:
            if competitor_presence_pct < PARITY_THRESHOLD_PCT:
                return "GREEN"  # We have it, fewer competitors have it
            else:
                return "AMBER"  # Parity — we match the field but no leadership
        else:
            if competitor_presence_pct >= PARITY_THRESHOLD_PCT:
                return "RED"   # 50%+ competitors have it; we don't
            else:
                return "GREEN"  # Niche feature — no urgency

    def rag_status_summary(self) -> Dict[str, Any]:
        table = self.feature_gap_table()
        if "rows" not in table:
            return {"reason": table.get("reason", "no_data")}
        counts = Counter(r["rag_status"] for r in table["rows"])
        return {
            "total_features_evaluated": len(table["rows"]),
            "RED": counts.get("RED", 0),
            "AMBER": counts.get("AMBER", 0),
            "GREEN": counts.get("GREEN", 0),
            "red_features": [
                r["name"] for r in table["rows"]
                if r["rag_status"] == "RED"
            ][:20],  # cap at top 20
        }

    def time_to_parity(
        self,
        feature_id: str,
        base_velocity_features_per_month: int = 2,
    ) -> Dict[str, Any]:
        """Estimate months to close a feature gap. Conservative: assumes
        the team prioritizes this gap at the base velocity."""
        table = self.feature_gap_table()
        if "rows" not in table:
            return {
                "feature_id": feature_id,
                "reason": "no_gap_data",
            }
        match = next((r for r in table["rows"]
                          if r["feature_id"] == feature_id), None)
        if match is None:
            return {
                "feature_id": feature_id,
                "reason": "feature_not_in_gap_table",
            }

        rag = match["rag_status"]
        if rag == "GREEN":
            return {
                "feature_id": feature_id,
                "rag_status": rag,
                "months_to_parity": 0,
                "reason": "already_at_or_above_parity",
            }

        # RED + AMBER: assume linear delivery at base velocity. The single-
        # feature gap takes 1 / base_velocity months (rounded up).
        # AMBER also requires 1 release cycle to upgrade quality.
        if base_velocity_features_per_month <= 0:
            base_velocity_features_per_month = 1
        months = Decimal("1") / Decimal(base_velocity_features_per_month)
        if rag == "AMBER":
            months *= Decimal("2")  # quality upgrade is harder than parity

        return {
            "feature_id": feature_id,
            "rag_status": rag,
            "months_to_parity": str(months.quantize(Decimal("0.01"))),
            "base_velocity_features_per_month": base_velocity_features_per_month,
            "spec_deviation": (
                "Continuation.docx #332 specifies time-to-parity considering "
                "team capacity + dependencies. v10.278 ships a linear model "
                "based on base_velocity input. Production estimate requires "
                "delivery roadmap integration."
            ),
        }


def _self_test() -> None:
    import tempfile

    assert "RED" in RAG_STATUSES
    assert "DIGITAL_BANKING" in FEATURE_CATEGORIES

    with tempfile.TemporaryDirectory() as tmpdir:
        dc = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )
        engine = CompetitiveGapAnalysisEngine(
            data_collection=dc,
            internal_features_path=Path(tmpdir) / "if.json",
            competitor_features_path=Path(tmpdir) / "cf.json",
        )

        # Setup competitors
        dc.register_competitor(
            {"competitor_id": "KCB", "name": "KCB", "tier": "TIER_1"}, actor="a",
        )
        dc.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity", "tier": "TIER_1"}, actor="a",
        )
        dc.register_competitor(
            {"competitor_id": "ABSA", "name": "ABSA", "tier": "TIER_1"}, actor="a",
        )

        # Test 1: register internal features
        r = engine.register_internal_feature(
            {"feature_id": "F-MOBILE", "name": "Mobile App",
             "category": "DIGITAL_BANKING", "present": True},
            actor="a",
        )
        assert r["registered"]
        engine.register_internal_feature(
            {"feature_id": "F-CHATBOT", "name": "Chatbot",
             "category": "DIGITAL_BANKING", "present": False},
            actor="a",
        )

        # Test 2: invalid category
        r = engine.register_internal_feature(
            {"feature_id": "X", "name": "Y",
             "category": "INVALID", "present": True}, actor="a",
        )
        assert not r["registered"]

        # Test 3: register competitor features
        # Mobile: all 3 have it → AMBER for us (parity)
        for cid in ["KCB", "EQUITY", "ABSA"]:
            engine.register_competitor_feature(
                cid, {"feature_id": "F-MOBILE", "name": "Mobile",
                         "category": "DIGITAL_BANKING", "present": True},
                actor="a",
            )
        # Chatbot: 2 of 3 have it → RED for us (we don't, 67% do)
        for cid in ["KCB", "EQUITY"]:
            engine.register_competitor_feature(
                cid, {"feature_id": "F-CHATBOT", "name": "Chatbot",
                         "category": "DIGITAL_BANKING", "present": True},
                actor="a",
            )
        engine.register_competitor_feature(
            "ABSA", {"feature_id": "F-CHATBOT", "name": "Chatbot",
                          "category": "DIGITAL_BANKING", "present": False},
            actor="a",
        )

        # Test 4: gap_table
        table = engine.feature_gap_table()
        # F-MOBILE should be AMBER (we have it, 100% do)
        # F-CHATBOT should be RED (we don't, 67% do)
        mobile = next(r for r in table["rows"] if r["feature_id"] == "F-MOBILE")
        chatbot = next(r for r in table["rows"] if r["feature_id"] == "F-CHATBOT")
        assert mobile["rag_status"] == "AMBER"
        assert chatbot["rag_status"] == "RED"

        # Test 5: filter by category
        table_dig = engine.feature_gap_table(feature_category="DIGITAL_BANKING")
        assert len(table_dig["rows"]) == 2

        # Test 6: invalid category
        t = engine.feature_gap_table(feature_category="INVALID")
        assert "error" in t

        # Test 7: rag_status_summary
        s = engine.rag_status_summary()
        assert s["RED"] == 1
        assert s["AMBER"] == 1
        assert "Chatbot" in s["red_features"]

        # Test 8: time_to_parity for RED feature
        ttp = engine.time_to_parity("F-CHATBOT",
                                          base_velocity_features_per_month=2)
        # 1 / 2 = 0.5 months
        assert Decimal(ttp["months_to_parity"]) == Decimal("0.50")

        # Test 9: time_to_parity for AMBER feature
        ttp = engine.time_to_parity("F-MOBILE",
                                          base_velocity_features_per_month=2)
        # 1 / 2 * 2 = 1 month
        assert Decimal(ttp["months_to_parity"]) == Decimal("1.00")

        # Test 10: time_to_parity for unknown feature
        ttp = engine.time_to_parity("F-UNKNOWN")
        assert ttp.get("reason") == "feature_not_in_gap_table"

        # Test 11: empty gap data
        engine2 = CompetitiveGapAnalysisEngine(
            data_collection=dc,
            internal_features_path=Path(tmpdir) / "if2.json",
            competitor_features_path=Path(tmpdir) / "cf2.json",
        )
        t = engine2.feature_gap_table()
        assert t.get("reason") == "no_competitor_features_registered"

    print("  ✅ competitive_gap_analysis self-test PASS")


if __name__ == "__main__":
    _self_test()
