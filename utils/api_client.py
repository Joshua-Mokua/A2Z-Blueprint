"""utils/api_client.py — Streamlit-side API client.

Pages import this instead of hitting PostgreSQL directly.
Falls back gracefully to direct DB/JSON if API is unavailable.

V-001 update (v5.17): every protected endpoint now requires a bearer
JWT. The client stores a token in instance state (set via .login()) and
attaches it to every request. /api/health remains the only call that
works without auth — useful as an availability probe.

Usage in a page:
    from utils.api_client import api

    api.login("william001", "ECOStaff001")  # once per session
    summary = api.bsc_summary()
    deals   = api.pipeline_deals(stage="Proposal")
"""

import os
import json
import logging
import threading
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger("a2z.api_client")

API_BASE = f"http://localhost:{os.getenv('A2Z_API_PORT', '8502')}"
TIMEOUT  = 5  # seconds — fast fail if API is down


# Token store. The client class wraps it so each instance can hold a
# different identity in tests; in production there's a single `api`
# singleton and a single bearer token. A lock keeps reads/writes atomic
# in case Streamlit threads simultaneously refresh.
_token_lock = threading.Lock()


def _auth_headers(token: Optional[str]) -> Dict[str, str]:
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _get(endpoint: str, params: dict = None, token: Optional[str] = None) -> Optional[Dict]:
    """GET from FastAPI with timeout. Returns None if unavailable.

    Attaches Authorization: Bearer <token> when a token is supplied.
    Returns None on 401/403 so callers fall back to direct data access
    (the same way they do when the API is offline).
    """
    try:
        import requests
        url = f"{API_BASE}{endpoint}"
        r   = requests.get(url, params=params, headers=_auth_headers(token), timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (401, 403):
            logger.debug(f"API auth failed for {endpoint} (status {r.status_code}) — falling back")
    except Exception as e:
        logger.debug(f"API unavailable ({endpoint}): {e}")
    return None


def _post(endpoint: str, data: dict = None, token: Optional[str] = None) -> Optional[Dict]:
    """POST to FastAPI. Same auth + fallback behaviour as _get."""
    try:
        import requests
        r = requests.post(
            f"{API_BASE}{endpoint}",
            json=data or {},
            headers=_auth_headers(token),
            timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code in (401, 403):
            logger.debug(f"API auth failed for {endpoint} (status {r.status_code}) — falling back")
    except Exception:
        pass
    return None


class APIClient:
    """High-level API client. All methods fall back to direct data access.

    V-001 (v5.17): holds a bearer JWT obtained from /api/auth/login.
    Pages should call .login(username, password) once per Streamlit
    session before any other call, OR rely on the implicit fallback
    (every method falls back to direct DB/JSON access if the API rejects
    the request).
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._username: Optional[str] = None

    # ── Auth ──────────────────────────────────────────────────────
    def login(self, username: str, password: str) -> bool:
        """Exchange username + password for a bearer token and cache it.

        Returns True on success, False on failure. Failures are silent —
        callers fall back to direct DB/JSON access automatically.
        """
        try:
            import requests
            r = requests.post(
                f"{API_BASE}/api/auth/login",
                json={"username": username, "password": password},
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                payload = r.json()
                with _token_lock:
                    self._token = payload.get("access_token")
                    self._username = username
                return bool(self._token)
        except Exception as e:
            logger.debug(f"login() failed: {e}")
        return False

    def logout(self) -> None:
        """Discard the cached token. JWTs are stateless so there's no
        server call — the next request will simply fail auth."""
        with _token_lock:
            self._token = None
            self._username = None

    def is_authenticated(self) -> bool:
        return self._token is not None

    # ── Health (no auth) ─────────────────────────────────────────
    def is_available(self) -> bool:
        """True if the FastAPI server is running."""
        result = _get("/api/health")
        return result is not None and result.get("status") == "healthy"

    def health(self) -> Dict:
        return _get("/api/health") or {"status": "unavailable", "db": "unknown"}

    # ── BSC ───────────────────────────────────────────────────────
    def bsc_summary(self) -> Dict:
        result = _get("/api/bsc/summary", token=self._token)
        if result:
            return result
        return self._bsc_summary_direct()

    def bsc_staff(self, username: str) -> Dict:
        result = _get(f"/api/bsc/staff/{username}", token=self._token)
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
        try:
            from utils.db import db as _a2z_db
            DATA = Path(__file__).parent.parent / "data"
            scores = _a2z_db.load_json(DATA/"feb_2026_staff_scores.json", default=[])
        except Exception:
            scores = []
        if isinstance(scores, dict): scores = list(scores.values())
        avg = sum(float(s.get("final_score",0)) for s in scores) / max(len(scores),1)
        return {"by_dept":[],"total_staff":len(scores),"overall_avg":round(avg,2),"source":"json"}

    # ── Pipeline ──────────────────────────────────────────────────
    def pipeline_summary(self) -> Dict:
        return _get("/api/pipeline/summary", token=self._token) or {}

    def pipeline_deals(self, stage: str = None, category: str = None,
                       unit: str = None, limit: int = 500) -> List:
        params = {}
        if stage:    params["stage"]    = stage
        if category: params["category"] = category
        if unit:     params["unit"]     = unit
        params["limit"] = limit
        result = _get("/api/pipeline/deals", params, token=self._token)
        if result:
            return result.get("deals", [])
        try:
            from utils.db import db as _db
            if _db.table_uses_db("pipeline_deals"):
                return _db.fetch_all("SELECT * FROM pipeline_deals ORDER BY open_date DESC LIMIT %s",
                                     (limit,))
        except Exception:
            pass
        try:
            from utils.db import db as _a2z_db
            DATA  = Path(__file__).parent.parent / "data"
            raw   = _a2z_db.load_json(DATA/"pipeline.json", default={})
        except Exception:
            raw = {}
        deals = raw if isinstance(raw,list) else raw.get("deals",[])
        return deals[:limit]

    # ── Credit ────────────────────────────────────────────────────
    def credit_summary(self) -> Dict:
        return _get("/api/credit/summary", token=self._token) or {}

    def credit_watchlist(self, classification: str = None, npl_only: bool = False,
                         limit: int = 200) -> List:
        params = {"limit": limit}
        if classification: params["classification"] = classification
        if npl_only:       params["npl_only"] = "true"
        result = _get("/api/credit/watchlist", params, token=self._token)
        if result:
            return result.get("accounts", [])
        return []

    # ── AML ───────────────────────────────────────────────────────
    def aml_summary(self) -> Dict:
        return _get("/api/aml/summary", token=self._token) or {}

    # ── Dashboard ─────────────────────────────────────────────────
    def md_dashboard(self) -> Dict:
        return _get("/api/dashboard/md", token=self._token) or {}

    # ── Cache ─────────────────────────────────────────────────────
    def clear_cache(self) -> bool:
        result = _post("/api/cache/clear", token=self._token)
        return result is not None

    def cache_stats(self) -> Dict:
        return _get("/api/cache/stats", token=self._token) or {}


# Singleton
api = APIClient()
