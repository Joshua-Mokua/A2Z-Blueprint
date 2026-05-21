"""
================================================================================
A2Z MIS 360 — Standard #327: Automated Competitor Data Collection
================================================================================

Risk classification: Cat C (data ingestion foundation; no live scraping in v10.x)

Automated competitor data collection layer. v10.278 ships a deterministic
ingestion + structured-extraction registry. Production-grade web scraping
+ NLP entity extraction is deferred to deployment phase per
SPEC_DEVIATION_NOTE — the engine accepts manually-curated competitor
records via API and acts as the structured store that other v10.278
engines compose over.

Public API:
    register_competitor(competitor_data, actor) -> Dict
    record_data_point(competitor_id, data_point, actor) -> Dict
    list_competitors(active_only=True) -> List[Dict]
    list_data_points(competitor_id=None, data_type=None,
                      from_date=None, to_date=None) -> List
    market_size_estimate(period) -> Dict (sum of tracked competitors' sizes)

DATA_SOURCE_TYPES byte-for-byte:
    WEBSITE_SCRAPE   -- structured field from competitor's public website
    APP_STORE        -- iOS/Android app metadata + ratings
    REGULATORY_FILE  -- CBK published statistics, KDIC, NSE filings
    MEDIA_REPORT     -- press release, news article
    MANUAL_ENTRY     -- analyst-curated entry (default in v10.278)
    PARTNER_FEED     -- paid market intelligence feed

DATA_TYPES byte-for-byte:
    DEPOSIT_RATE       LENDING_RATE       FEE
    PRODUCT_FEATURE    DIGITAL_LAUNCH     APP_RATING
    BRANCH_COUNT       MARKET_SHARE       NPS_SCORE
    LEADERSHIP_CHANGE  M_AND_A            REGULATORY_ACTION

COMPETITOR_TIER byte-for-byte:
    TIER_1   -- top 5 banks (KCB, Equity, Co-op, ABSA, NCBA)
    TIER_2   -- mid-tier (Standard Chartered, Stanbic, I&M, DTB, Family)
    TIER_3   -- smaller banks + digital-only / fintechs

Honesty rules:
    Rule 1: empty data store returns explicit reason="no_competitor_data"
            rather than fabricating market share figures
    Rule 6: invalid data_source / data_type / tier rejected
    Rule 7: SPEC_DEVIATION_NOTE — production NLP scraping deferred

================================================================================
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SPEC_DEVIATION_NOTE: str = (
    "Continuation.docx #327 specifies automated NLP scraping of competitor "
    "websites + app stores + regulatory filings. v10.278 ships the "
    "structured store + ingestion API; production-grade scraping (with "
    "robots.txt compliance, anti-bot evasion, NLP entity extraction) is "
    "deferred to deployment phase. Until then, MANUAL_ENTRY is the default "
    "data_source — analysts curate entries from the same public sources "
    "the eventual scraper will hit. The downstream engines (#328 rates, "
    "#329 digital intel, #332 gap analysis, etc.) work identically over "
    "manually-curated and machine-extracted data."
)


DATA_SOURCE_TYPES: Tuple[str, ...] = (
    "WEBSITE_SCRAPE", "APP_STORE", "REGULATORY_FILE",
    "MEDIA_REPORT", "MANUAL_ENTRY", "PARTNER_FEED",
)

DATA_TYPES: Tuple[str, ...] = (
    "DEPOSIT_RATE", "LENDING_RATE", "FEE",
    "PRODUCT_FEATURE", "DIGITAL_LAUNCH", "APP_RATING",
    "BRANCH_COUNT", "MARKET_SHARE", "NPS_SCORE",
    "LEADERSHIP_CHANGE", "M_AND_A", "REGULATORY_ACTION",
)

COMPETITOR_TIERS: Tuple[str, ...] = ("TIER_1", "TIER_2", "TIER_3")


class CompetitorDataCollectionEngine:
    """Structured competitor data store + ingestion API."""

    def __init__(
        self,
        competitors_path: Optional[Path] = None,
        data_points_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.competitors_path = competitors_path or base / "competitors.json"
        self.data_points_path = data_points_path or base / "competitor_data_points.json"

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

    def register_competitor(
        self,
        competitor_data: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"registered": False, "error": "actor_required"}
        for f in ("competitor_id", "name", "tier"):
            if f not in competitor_data or not competitor_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if competitor_data["tier"] not in COMPETITOR_TIERS:
            return {
                "registered": False,
                "error": f"invalid_tier:{competitor_data['tier']}",
                "valid_tiers": list(COMPETITOR_TIERS),
            }

        records = self._load(self.competitors_path,
                                "competitors", ("competitor_id",))
        if any(r.get("competitor_id") == competitor_data["competitor_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_competitor_id"}

        record = {
            "competitor_id": competitor_data["competitor_id"],
            "name": competitor_data["name"],
            "tier": competitor_data["tier"],
            "website": competitor_data.get("website", ""),
            "app_store_ids": competitor_data.get("app_store_ids", {}),
            "active": competitor_data.get("active", True),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.competitors_path, records,
                          "competitors", "competitor_id")
        return {"registered": ok,
                  "competitor_id": competitor_data["competitor_id"]}

    def record_data_point(
        self,
        competitor_id: str,
        data_point: Dict[str, Any],
        actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("data_type", "value", "data_source", "as_of"):
            if f not in data_point:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if data_point["data_type"] not in DATA_TYPES:
            return {
                "recorded": False,
                "error": f"invalid_data_type:{data_point['data_type']}",
                "valid_types": list(DATA_TYPES),
            }
        if data_point["data_source"] not in DATA_SOURCE_TYPES:
            return {
                "recorded": False,
                "error": f"invalid_data_source:{data_point['data_source']}",
                "valid_sources": list(DATA_SOURCE_TYPES),
            }

        # Verify competitor exists
        competitors = self._load(self.competitors_path,
                                       "competitors", ("competitor_id",))
        if not any(c.get("competitor_id") == competitor_id for c in competitors):
            return {"recorded": False, "error": "competitor_not_found"}

        records = self._load(self.data_points_path,
                                "competitor_data_points", ("data_point_id",))
        dp_id = (f"DP-{competitor_id}-{data_point['data_type']}-"
                     f"{int(datetime.utcnow().timestamp() * 1000)}")
        record = {
            "data_point_id": dp_id,
            "competitor_id": competitor_id,
            "data_type": data_point["data_type"],
            "data_source": data_point["data_source"],
            "value": str(data_point["value"]),
            "unit": data_point.get("unit", ""),
            "metadata": data_point.get("metadata", {}),
            "as_of": data_point["as_of"],
            "segment_code": data_point.get("segment_code"),
            "actor": actor,
            "recorded_at": datetime.utcnow().isoformat(),
            "source_url": data_point.get("source_url", ""),
        }
        records.append(record)
        ok = self._save(self.data_points_path, records,
                          "competitor_data_points", "data_point_id")
        return {"recorded": ok, "data_point_id": dp_id}

    def list_competitors(
        self, active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.competitors_path,
                                "competitors", ("competitor_id",))
        if active_only:
            return [r for r in records if r.get("active", True)]
        return records

    def list_data_points(
        self,
        competitor_id: Optional[str] = None,
        data_type: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records = self._load(self.data_points_path,
                                "competitor_data_points", ("data_point_id",))
        out = []
        for r in records:
            if competitor_id and r.get("competitor_id") != competitor_id:
                continue
            if data_type and r.get("data_type") != data_type:
                continue
            as_of = r.get("as_of", "")
            if from_date and as_of < from_date:
                continue
            if to_date and as_of > to_date:
                continue
            out.append(r)
        return out

    def market_size_estimate(self, period: str) -> Dict[str, Any]:
        """Sum of MARKET_SHARE data points across competitors. Returns explicit
        reason when no data present."""
        records = self.list_data_points(
            data_type="MARKET_SHARE", from_date=period, to_date=period + "Z",
        )
        if not records:
            return {
                "period": period,
                "competitor_count_with_data": 0,
                "reason": "no_market_share_data",
            }
        # Group by competitor; take latest per competitor in window
        latest: Dict[str, Dict[str, Any]] = {}
        for r in records:
            cid = r["competitor_id"]
            if cid not in latest or r.get("as_of", "") > latest[cid].get("as_of", ""):
                latest[cid] = r

        total_pct = Decimal("0")
        for r in latest.values():
            try:
                total_pct += Decimal(str(r["value"]))
            except (ValueError, TypeError):
                continue

        return {
            "period": period,
            "competitor_count_with_data": len(latest),
            "total_pct_tracked": str(total_pct.quantize(Decimal("0.01"))),
            "untracked_pct": str(
                max(Decimal("0"),
                      Decimal("100") - total_pct).quantize(Decimal("0.01"))
            ),
        }


def _self_test() -> None:
    import tempfile

    assert "MANUAL_ENTRY" in DATA_SOURCE_TYPES
    assert "MARKET_SHARE" in DATA_TYPES
    assert "TIER_1" in COMPETITOR_TIERS
    assert "v10.278" in SPEC_DEVIATION_NOTE

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CompetitorDataCollectionEngine(
            competitors_path=Path(tmpdir) / "c.json",
            data_points_path=Path(tmpdir) / "d.json",
        )

        # Test 1: register competitor
        r = engine.register_competitor(
            {"competitor_id": "KCB", "name": "Kenya Commercial Bank",
             "tier": "TIER_1", "website": "kcbgroup.com"},
            actor="analyst",
        )
        assert r["registered"]

        # Test 2: missing field
        r = engine.register_competitor({"competitor_id": "X"}, actor="a")
        assert not r["registered"]

        # Test 3: invalid tier
        r = engine.register_competitor(
            {"competitor_id": "X", "name": "Y", "tier": "TIER_X"},
            actor="a",
        )
        assert not r["registered"]

        # Test 4: duplicate
        r = engine.register_competitor(
            {"competitor_id": "KCB", "name": "Z", "tier": "TIER_1"},
            actor="a",
        )
        assert not r["registered"]

        # Test 5: record data point
        r = engine.record_data_point(
            "KCB",
            {"data_type": "MARKET_SHARE", "value": "23.5",
             "data_source": "REGULATORY_FILE",
             "as_of": "2026-Q1", "unit": "pct"},
            actor="analyst",
        )
        assert r["recorded"]

        # Test 6: invalid data_type
        r = engine.record_data_point(
            "KCB",
            {"data_type": "INVALID", "value": "1",
             "data_source": "MANUAL_ENTRY", "as_of": "2026-Q1"},
            actor="a",
        )
        assert not r["recorded"]

        # Test 7: data point for unregistered competitor
        r = engine.record_data_point(
            "UNKNOWN",
            {"data_type": "DEPOSIT_RATE", "value": "5.5",
             "data_source": "WEBSITE_SCRAPE", "as_of": "2026-Q1"},
            actor="a",
        )
        assert not r["recorded"]
        assert "competitor_not_found" in r["error"]

        # Test 8: list filtering
        engine.register_competitor(
            {"competitor_id": "EQUITY", "name": "Equity Bank",
             "tier": "TIER_1"}, actor="a",
        )
        engine.record_data_point(
            "EQUITY",
            {"data_type": "MARKET_SHARE", "value": "18.0",
             "data_source": "REGULATORY_FILE", "as_of": "2026-Q1"},
            actor="a",
        )
        records = engine.list_data_points(data_type="MARKET_SHARE")
        assert len(records) == 2

        # Test 9: market_size_estimate
        ms = engine.market_size_estimate("2026-Q1")
        assert ms["competitor_count_with_data"] == 2
        assert Decimal(ms["total_pct_tracked"]) == Decimal("41.50")

        # Test 10: empty estimate
        ms = engine.market_size_estimate("2099-Q1")
        assert ms["competitor_count_with_data"] == 0
        assert ms["reason"] == "no_market_share_data"

        # Test 11: list_competitors
        active = engine.list_competitors()
        assert len(active) == 2

    print("  ✅ competitor_data_collection self-test PASS")


if __name__ == "__main__":
    _self_test()
