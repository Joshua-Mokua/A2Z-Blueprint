"""utils/api_client.py — Streamlit-side API client.

Pages import this instead of hitting PostgreSQL directly.
Falls back gracefully to direct DB/JSON if API is unavailable.

Usage in a page:
    from utils.api_client import api

    summary = api.bsc_summary()
    deals   = api.pipeline_deals(stage="Proposal")
    credit  = api.credit_summary()
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("a2z.api_client")

API_BASE = f"http://localhost:{os.getenv('A2Z_API_PORT', '8502')}"
TIMEOUT  = 5  # seconds — fast fail if API is down


def _get(endpoint: str, params: dict = None) -> Optional[Dict]:
    """GET from FastAPI with timeout. Returns None if unavailable."""
    try:
        import requests
        url = f"{API_BASE}{endpoint}"
        r   = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug(f"API unavailable ({endpoint}): {e}")
    return None


def _post(endpoint: str, data: dict = None) -> Optional[Dict]:
    """POST to FastAPI."""
    try:
        import requests
        r = requests.post(f"{API_BASE}{endpoint}", json=data or {}, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


class APIClient:
    """High-level API client. All methods fall back to direct data access."""

    def is_available(self) -> bool:
        """True if the FastAPI server is running."""
        result = _get("/api/health")
        return result is not None and result.get("status") == "healthy"

    def health(self) -> Dict:
        return _get("/api/health") or {"status": "unavailable", "db": "unknown"}

    # ── BSC ───────────────────────────────────────────────────────
    def bsc_summary(self) -> Dict:
        result = _get("/api/bsc/summary")
        if result:
            return result
        # Direct fallback
        return self._bsc_summary_direct()

    def bsc_staff(self, username: str) -> Dict:
        result = _get(f"/api/bsc/staff/{username}")
        if result:
            return result
        return {}

    def _bsc_summary_direct(self) -> Dict:
        """Direct fallback — reads from DB or JSON without API."""
        try:
            from utils.db import db as _db
            if _db.table_uses_db("bsc_scores"):
                rows = _db.fetch_all(
                    "SELECT dept, COUNT(*) as staff_count, "
                    "ROUND(AVG(final_score)::numeric,2) as avg_score "
                    "FROM bsc_scores GROUP BY dept ORDER BY avg_score DESC"
                )
                total  = sum(r.get("staff_count",0) for r in rows)
                avg    = sum(float(r.get("avg_score",0))*r.get("staff_count",1)
                             for r in rows) / max(total,1)
                return {"by_dept":rows,"total_staff":total,"overall_avg":round(avg,2),"source":"db_direct"}
        except Exception:
            pass
        DATA = Path(__file__).parent.parent / "data"
        scores = json.loads((DATA/"feb_2026_staff_scores.json").read_text())
        if isinstance(scores, dict): scores = list(scores.values())
        avg = sum(float(s.get("final_score",0)) for s in scores) / max(len(scores),1)
        return {"by_dept":[],"total_staff":len(scores),"overall_avg":round(avg,2),"source":"json"}

    # ── Pipeline ──────────────────────────────────────────────────
    def pipeline_summary(self) -> Dict:
        return _get("/api/pipeline/summary") or {}

    def pipeline_deals(self, stage: str = None, category: str = None,
                       unit: str = None, limit: int = 500) -> List:
        params = {}
        if stage:    params["stage"]    = stage
        if category: params["category"] = category
        if unit:     params["unit"]     = unit
        params["limit"] = limit
        result = _get("/api/pipeline/deals", params)
        if result:
            return result.get("deals", [])
        # Direct fallback
        try:
            from utils.db import db as _db
            if _db.table_uses_db("pipeline_deals"):
                return _db.fetch_all("SELECT * FROM pipeline_deals ORDER BY open_date DESC LIMIT %s",
                                     (limit,))
        except Exception:
            pass
        DATA  = Path(__file__).parent.parent / "data"
        raw   = json.loads((DATA/"pipeline.json").read_text())
        deals = raw if isinstance(raw,list) else raw.get("deals",[])
        return deals[:limit]

    # ── Credit ────────────────────────────────────────────────────
    def credit_summary(self) -> Dict:
        return _get("/api/credit/summary") or {}

    def credit_watchlist(self, classification: str = None, npl_only: bool = False,
                         limit: int = 200) -> List:
        params = {"limit": limit}
        if classification: params["classification"] = classification
        if npl_only:       params["npl_only"] = "true"
        result = _get("/api/credit/watchlist", params)
        if result:
            return result.get("accounts", [])
        return []

    # ── AML ───────────────────────────────────────────────────────
    def aml_summary(self) -> Dict:
        return _get("/api/aml/summary") or {}

    # ── Dashboard ─────────────────────────────────────────────────
    def md_dashboard(self) -> Dict:
        return _get("/api/dashboard/md") or {}

    # ── Cache ─────────────────────────────────────────────────────
    def clear_cache(self) -> bool:
        result = _post("/api/cache/clear")
        return result is not None

    def cache_stats(self) -> Dict:
        return _get("/api/cache/stats") or {}


# Singleton
api = APIClient()
