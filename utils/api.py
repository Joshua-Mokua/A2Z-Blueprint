"""utils/api.py — FastAPI backend for A2Z Blueprint MIS 360.

Runs alongside Streamlit on port 8502. Provides cached, pooled database
access for the heaviest pages. Pages that call this API load 3-5x faster
than pages that hit PostgreSQL directly.

HOW TO RUN (two terminals):
  Terminal 1: streamlit run app.py
  Terminal 2: python -m utils.api

OR use run_all.bat which starts both automatically.

ENDPOINTS:
  GET /api/health              — system health check
  GET /api/bsc/summary         — BSC scores summary (cached 5min)
  GET /api/bsc/staff/{username}— individual staff BSC
  GET /api/pipeline/summary    — pipeline summary metrics
  GET /api/pipeline/deals      — all deals with filters
  GET /api/credit/summary      — credit monitoring summary
  GET /api/credit/watchlist    — watchlist with pagination
  GET /api/aml/summary         — AML alerts summary
  GET /api/users/summary       — org summary
  GET /api/dashboard/md        — MD command centre data
"""

import os
import json
import time
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pathlib import Path
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger("a2z.api")

DATA_DIR = Path(__file__).parent.parent / "data"

app = FastAPI(
    title="A2Z Blueprint MIS 360 API",
    description="High-performance data layer for A2Z Blueprint",
    version="5.3.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Allow Streamlit (same machine) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501",
                   "http://localhost:8502", "http://127.0.0.1:8502"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)

# ── In-memory cache ───────────────────────────────────────────────
_cache: Dict[str, Any] = {}
_cache_ts: Dict[str, float] = {}
CACHE_TTL = {
    "bsc":       300,   # 5 minutes — scores don't change often
    "pipeline":   60,   # 1 minute — deals change frequently
    "credit":    120,   # 2 minutes
    "aml":       120,
    "users":     600,   # 10 minutes — org structure rarely changes
    "dashboard": 120,
    "partnerships": 60,
}

def _get_cache(key: str, ttl_key: str = "pipeline") -> Optional[Any]:
    if key in _cache:
        age = time.time() - _cache_ts.get(key, 0)
        if age < CACHE_TTL.get(ttl_key, 60):
            return _cache[key]
    return None

def _set_cache(key: str, value: Any) -> None:
    _cache[key] = value
    _cache_ts[key] = time.time()

def _load_json(fname: str) -> Any:
    """Load a JSON data file."""
    p = DATA_DIR / fname
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Error loading {fname}: {e}")
        return []

def _db_available() -> bool:
    """Check if PostgreSQL is available."""
    try:
        from utils.db import db as _db
        return _db.is_postgres_ready()
    except Exception:
        return False

def _safe_float(val) -> float:
    try:
        from decimal import Decimal
        if isinstance(val, Decimal):
            return float(val)
        return float(val) if val is not None else 0.0
    except Exception:
        return 0.0

def _safe_int(val) -> int:
    try:
        return int(val) if val is not None else 0
    except Exception:
        return 0

def _serialize(obj):
    """Make objects JSON serializable."""
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    return obj

# ── Health check ──────────────────────────────────────────────────
@app.get("/api/health")
def health():
    db_ok = _db_available()
    return {
        "status":    "healthy",
        "version":   "5.3.0",
        "db":        "postgresql" if db_ok else "json_fallback",
        "timestamp": datetime.now().isoformat(),
        "cache_keys": len(_cache),
    }

# ── BSC Endpoints ─────────────────────────────────────────────────
@app.get("/api/bsc/summary")
def bsc_summary():
    cached = _get_cache("bsc_summary", "bsc")
    if cached:
        return cached

    if _db_available():
        try:
            from utils.db import db as _db
            rows = _db.fetch_all("""
                SELECT dept,
                       COUNT(*)                              as staff_count,
                       ROUND(AVG(final_score)::numeric, 2)  as avg_score,
                       SUM(CASE WHEN final_score >= 4.0 THEN 1 ELSE 0 END) as exceeding,
                       SUM(CASE WHEN final_score < 2.5 THEN 1 ELSE 0 END)  as at_risk,
                       period
                FROM bsc_scores
                GROUP BY dept, period
                ORDER BY avg_score DESC
            """)
            result = {
                "by_dept":     _serialize(rows),
                "total_staff": sum(_safe_int(r.get("staff_count")) for r in rows),
                "overall_avg": round(
                    sum(_safe_float(r.get("avg_score",0)) * _safe_int(r.get("staff_count",1))
                        for r in rows) /
                    max(sum(_safe_int(r.get("staff_count",1)) for r in rows), 1), 2),
                "source":      "postgresql",
            }
            _set_cache("bsc_summary", result)
            return result
        except Exception as e:
            logger.error(f"BSC DB error: {e}")

    # JSON fallback
    scores = _load_json("feb_2026_staff_scores.json")
    if isinstance(scores, dict):
        all_scores = list(scores.values())
    else:
        all_scores = scores

    by_dept = {}
    for s in all_scores:
        d = s.get("dept", "Unknown")
        if d not in by_dept:
            by_dept[d] = {"dept": d, "staff_count": 0, "avg_score": 0.0,
                          "exceeding": 0, "at_risk": 0, "total": 0.0}
        by_dept[d]["staff_count"] += 1
        sc = _safe_float(s.get("final_score", 0))
        by_dept[d]["total"] += sc
        if sc >= 4.0: by_dept[d]["exceeding"] += 1
        if sc < 2.5:  by_dept[d]["at_risk"]   += 1

    for d in by_dept:
        by_dept[d]["avg_score"] = round(
            by_dept[d]["total"] / max(by_dept[d]["staff_count"], 1), 2)

    result = {
        "by_dept":     list(by_dept.values()),
        "total_staff": len(all_scores),
        "overall_avg": round(
            sum(_safe_float(s.get("final_score",0)) for s in all_scores) /
            max(len(all_scores), 1), 2),
        "source": "json",
    }
    _set_cache("bsc_summary", result)
    return result

@app.get("/api/bsc/staff/{username}")
def bsc_staff(username: str):
    if _db_available():
        try:
            from utils.db import db as _db
            row = _db.fetch_one(
                "SELECT * FROM bsc_scores WHERE username = %s ORDER BY computed_at DESC LIMIT 1",
                (username,)
            )
            if row:
                return _serialize(row)
        except Exception as e:
            logger.error(f"BSC staff DB error: {e}")

    scores = _load_json("feb_2026_staff_scores.json")
    if isinstance(scores, dict):
        return scores.get(username, {})
    return {}

# ── Pipeline Endpoints ────────────────────────────────────────────
@app.get("/api/pipeline/summary")
def pipeline_summary():
    cached = _get_cache("pipeline_summary", "pipeline")
    if cached:
        return cached

    if _db_available():
        try:
            from utils.db import db as _db
            rows = _db.fetch_all("""
                SELECT stage, deal_category,
                       COUNT(*)          as deal_count,
                       SUM(amount)       as total_value,
                       AVG(probability)  as avg_probability
                FROM pipeline_deals
                GROUP BY stage, deal_category
                ORDER BY total_value DESC
            """)
            totals = _db.fetch_one("""
                SELECT COUNT(*)    as total_deals,
                       SUM(amount) as pipeline_value,
                       SUM(CASE WHEN stage = 'Closed Won' THEN amount ELSE 0 END) as won_value,
                       SUM(CASE WHEN stage = 'Closed Lost' THEN 1 ELSE 0 END)    as lost_count
                FROM pipeline_deals
            """)
            result = {
                "by_stage":       _serialize(rows),
                "totals":         _serialize(totals),
                "source":         "postgresql",
            }
            _set_cache("pipeline_summary", result)
            return result
        except Exception as e:
            logger.error(f"Pipeline DB error: {e}")

    # JSON fallback
    raw = _load_json("pipeline.json")
    deals = raw if isinstance(raw, list) else raw.get("deals", [])
    by_stage = {}
    total_val = 0
    won_val   = 0
    for d in deals:
        st  = d.get("stage","Unknown")
        amt = _safe_float(d.get("amount",0))
        total_val += amt
        if st == "Closed Won": won_val += amt
        if st not in by_stage:
            by_stage[st] = {"stage":st,"deal_count":0,"total_value":0.0}
        by_stage[st]["deal_count"]  += 1
        by_stage[st]["total_value"] += amt

    result = {
        "by_stage":     list(by_stage.values()),
        "totals":       {"total_deals":len(deals),"pipeline_value":total_val,
                         "won_value":won_val,"lost_count":0},
        "source":       "json",
    }
    _set_cache("pipeline_summary", result)
    return result

@app.get("/api/pipeline/deals")
def pipeline_deals(
    stage:    Optional[str] = None,
    category: Optional[str] = None,
    unit:     Optional[str] = None,
    limit:    int = Query(default=500, le=5000),
    offset:   int = Query(default=0, ge=0),
):
    if _db_available():
        try:
            from utils.db import db as _db
            where  = []
            params = []
            if stage:    where.append("stage = %s");        params.append(stage)
            if category: where.append("deal_category = %s");params.append(category)
            if unit:     where.append("unit = %s");         params.append(unit)
            sql = "SELECT * FROM pipeline_deals"
            if where: sql += " WHERE " + " AND ".join(where)
            sql += f" ORDER BY open_date DESC LIMIT {limit} OFFSET {offset}"
            rows = _db.fetch_all(sql, tuple(params))
            return {"deals": _serialize(rows), "count": len(rows), "source": "postgresql"}
        except Exception as e:
            logger.error(f"Pipeline deals DB error: {e}")

    raw   = _load_json("pipeline.json")
    deals = raw if isinstance(raw, list) else raw.get("deals", [])
    if stage:    deals = [d for d in deals if d.get("stage")==stage]
    if category: deals = [d for d in deals if d.get("deal_category")==category]
    if unit:     deals = [d for d in deals if d.get("unit")==unit]
    return {"deals": deals[offset:offset+limit], "count": len(deals), "source": "json"}

# ── Credit Monitoring Endpoints ───────────────────────────────────
@app.get("/api/credit/summary")
def credit_summary():
    cached = _get_cache("credit_summary", "credit")
    if cached:
        return cached

    if _db_available():
        try:
            from utils.db import db as _db
            totals = _db.fetch_one("""
                SELECT COUNT(*)                                          as total_accounts,
                       ROUND(SUM(outstanding)::numeric/1e9, 2)          as outstanding_bn,
                       ROUND(SUM(loan_amount)::numeric/1e9, 2)          as loan_book_bn,
                       SUM(CASE WHEN npl_flag THEN 1 ELSE 0 END)        as npl_count,
                       ROUND(SUM(CASE WHEN npl_flag THEN outstanding ELSE 0 END)::numeric/
                             NULLIF(SUM(outstanding),0)*100, 2)         as npl_ratio_pct,
                       COUNT(DISTINCT branch)                           as branches
                FROM watchlist
            """)
            by_class = _db.fetch_all("""
                SELECT classification,
                       COUNT(*) as accounts,
                       ROUND(SUM(outstanding)::numeric/1e6, 1) as outstanding_m
                FROM watchlist
                GROUP BY classification
                ORDER BY outstanding_m DESC
            """)
            result = {
                "totals":   _serialize(totals),
                "by_class": _serialize(by_class),
                "source":   "postgresql",
            }
            _set_cache("credit_summary", result)
            return result
        except Exception as e:
            logger.error(f"Credit DB error: {e}")

    raw   = _load_json("credit_monitoring.json")
    accts = raw if isinstance(raw,list) else raw.get("watchlist",[])
    total_out = sum(_safe_float(a.get("outstanding",0)) for a in accts)
    npl_ct    = sum(1 for a in accts if _safe_int(a.get("npl_days",0))>=90)
    npl_out   = sum(_safe_float(a.get("outstanding",0))
                    for a in accts if _safe_int(a.get("npl_days",0))>=90)
    result = {
        "totals": {"total_accounts":len(accts),
                   "outstanding_bn":round(total_out/1e9,2),
                   "npl_count":npl_ct,
                   "npl_ratio_pct":round(npl_out/max(total_out,1)*100,2)},
        "by_class":[],
        "source":"json",
    }
    _set_cache("credit_summary", result)
    return result

@app.get("/api/credit/watchlist")
def credit_watchlist(
    classification: Optional[str] = None,
    stage:          Optional[str] = None,
    branch:         Optional[str] = None,
    npl_only:       bool = False,
    limit:          int = Query(default=200, le=1000),
    offset:         int = Query(default=0, ge=0),
):
    if _db_available():
        try:
            from utils.db import db as _db
            where  = []
            params = []
            if classification: where.append("classification = %s"); params.append(classification)
            if stage:          where.append("stage = %s");          params.append(stage)
            if branch:         where.append("branch_name ILIKE %s");params.append(f"%{branch}%")
            if npl_only:       where.append("npl_flag = true")
            sql = "SELECT * FROM watchlist"
            if where: sql += " WHERE " + " AND ".join(where)
            sql += f" ORDER BY dpd DESC LIMIT {limit} OFFSET {offset}"
            rows = _db.fetch_all(sql, tuple(params))
            return {"accounts":_serialize(rows),"count":len(rows),"source":"postgresql"}
        except Exception as e:
            logger.error(f"Watchlist DB error: {e}")

    raw   = _load_json("credit_monitoring.json")
    accts = raw if isinstance(raw,list) else raw.get("watchlist",[])
    if classification: accts = [a for a in accts if a.get("classification")==classification]
    if stage:          accts = [a for a in accts if a.get("stage")==stage]
    if npl_only:       accts = [a for a in accts if _safe_int(a.get("npl_days",0))>=90]
    return {"accounts":accts[offset:offset+limit],"count":len(accts),"source":"json"}

# ── AML Endpoints ─────────────────────────────────────────────────
@app.get("/api/aml/summary")
def aml_summary():
    cached = _get_cache("aml_summary","aml")
    if cached: return cached

    if _db_available():
        try:
            from utils.db import db as _db
            totals = _db.fetch_one("""
                SELECT COUNT(*)                                            as total_alerts,
                       SUM(CASE WHEN status='Open' THEN 1 ELSE 0 END)   as open_alerts,
                       SUM(CASE WHEN risk_level='High' THEN 1 ELSE 0 END) as high_risk,
                       SUM(CASE WHEN str_filed THEN 1 ELSE 0 END)          as strs_filed,
                       ROUND(SUM(amount)::numeric/1e6, 1)                  as total_amount_m
                FROM aml_alerts
            """)
            by_rule = _db.fetch_all("""
                SELECT rule_triggered, COUNT(*) as alerts,
                       SUM(CASE WHEN status='Open' THEN 1 ELSE 0 END) as open_count
                FROM aml_alerts
                GROUP BY rule_triggered
                ORDER BY alerts DESC
            """)
            result = {"totals":_serialize(totals),"by_rule":_serialize(by_rule),"source":"postgresql"}
            _set_cache("aml_summary",result)
            return result
        except Exception as e:
            logger.error(f"AML DB error: {e}")

    alerts = _load_json("aml_alerts.json")
    result = {
        "totals":{"total_alerts":len(alerts),
                  "open_alerts":sum(1 for a in alerts if a.get("status")=="Open"),
                  "high_risk":sum(1 for a in alerts if a.get("risk_level")=="High"),
                  "strs_filed":sum(1 for a in alerts if a.get("str_filed"))},
        "by_rule":[],"source":"json"
    }
    _set_cache("aml_summary",result)
    return result

# ── Users / Org Endpoints ─────────────────────────────────────────
@app.get("/api/users/summary")
def users_summary():
    cached = _get_cache("users_summary","users")
    if cached: return cached

    if _db_available():
        try:
            from utils.db import db as _db
            totals = _db.fetch_one("""
                SELECT COUNT(*)                                          as total_users,
                       SUM(CASE WHEN active THEN 1 ELSE 0 END)          as active_users,
                       SUM(CASE WHEN is_admin THEN 1 ELSE 0 END)        as admins,
                       COUNT(DISTINCT department)                        as departments,
                       COUNT(DISTINCT unit)                              as units
                FROM users
            """)
            by_dept = _db.fetch_all("""
                SELECT department, COUNT(*) as headcount
                FROM users WHERE active = true
                GROUP BY department
                ORDER BY headcount DESC
            """)
            result = {"totals":_serialize(totals),"by_dept":_serialize(by_dept),"source":"postgresql"}
            _set_cache("users_summary",result)
            return result
        except Exception as e:
            logger.error(f"Users DB error: {e}")

    users = _load_json("users.json")
    if isinstance(users,dict): users = list(users.values())
    result = {
        "totals":{"total_users":len(users),
                  "active_users":sum(1 for u in users if u.get("active",True)),
                  "admins":sum(1 for u in users if u.get("is_admin"))},
        "by_dept":[],"source":"json"
    }
    _set_cache("users_summary",result)
    return result

# ── MD Dashboard Endpoint ─────────────────────────────────────────
@app.get("/api/dashboard/md")
def md_dashboard():
    """Single endpoint for MD command centre — aggregates all key metrics."""
    cached = _get_cache("md_dashboard","dashboard")
    if cached: return cached

    bsc   = bsc_summary()
    pipe  = pipeline_summary()
    credit= credit_summary()
    aml   = aml_summary()
    users = users_summary()

    result = {
        "bsc":     {"overall_avg":bsc.get("overall_avg",0),
                    "total_staff":bsc.get("total_staff",0)},
        "pipeline":{"total_deals":pipe.get("totals",{}).get("total_deals",0),
                    "pipeline_value":pipe.get("totals",{}).get("pipeline_value",0),
                    "won_value":pipe.get("totals",{}).get("won_value",0)},
        "credit":  {"total_accounts":credit.get("totals",{}).get("total_accounts",0),
                    "outstanding_bn":credit.get("totals",{}).get("outstanding_bn",0),
                    "npl_ratio_pct":credit.get("totals",{}).get("npl_ratio_pct",0)},
        "aml":     {"open_alerts":aml.get("totals",{}).get("open_alerts",0),
                    "high_risk":aml.get("totals",{}).get("high_risk",0)},
        "org":     {"total_staff":users.get("totals",{}).get("total_users",0),
                    "departments":users.get("totals",{}).get("departments",0)},
        "generated_at": datetime.now().isoformat(),
    }
    _set_cache("md_dashboard",result)
    return result

# ── Cache management ──────────────────────────────────────────────
@app.post("/api/cache/clear")
def clear_cache():
    _cache.clear()
    _cache_ts.clear()
    return {"status":"cleared","message":"All API cache cleared"}

@app.get("/api/cache/stats")
def cache_stats():
    now = time.time()
    return {
        "cached_keys": list(_cache.keys()),
        "ages_seconds": {k: round(now - _cache_ts.get(k,now)) for k in _cache},
    }

# ── Entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("A2Z_API_PORT", "8502"))
    print(f"Starting A2Z API on http://localhost:{port}")
    print(f"  API docs: http://localhost:{port}/api/docs")
    print(f"  Health:   http://localhost:{port}/api/health")
    uvicorn.run(
        "utils.api:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="warning",
    )
