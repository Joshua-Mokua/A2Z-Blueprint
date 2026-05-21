"""utils.api_crud — Generic CRUD route factory (Standard #2, v5.31).

Implements the 8-endpoint pattern from the master addendum's Standard #2:

    list      GET    /api/v1/{module}              -> rows with pagination
    get       GET    /api/v1/{module}/{id}         -> single row
    create    POST   /api/v1/{module}              -> insert + return new row
    update    PUT    /api/v1/{module}/{id}         -> upsert + return row
    delete    DELETE /api/v1/{module}/{id}         -> soft/hard delete
    export    POST   /api/v1/{module}/export       -> all rows (paginated)
    search    POST   /api/v1/{module}/search       -> rows matching criteria
    dashboard GET    /api/v1/{module}/dashboard    -> module summary metrics

Every route:
    * is JWT-gated (Depends(get_current_user)) — closes V-001
    * runs the table name through _check_table() — closes V-002
    * builds SQL with psycopg2.sql.Identifier — never f-strings on identifiers
    * audit-logs every mutating call via core_audit.audit_log
    * falls back to a2z_db.load_json when PG is unreachable
    * returns _serialize(...) so Decimals and dates JSON-encode cleanly

Typical wiring (in utils/api.py):

    from utils.api_crud import make_crud_router

    router = make_crud_router(
        module      = "pipeline_deals",      # endpoint path segment
        table       = "pipeline_deals",      # PG table name (must be in TABLE_USE_DB)
        json_file   = "pipeline.json",       # fallback file
        list_key    = "deals",               # JSON file's top-level array key
        searchable  = ["stage", "deal_category", "unit"],
        order_by    = "open_date DESC",
    )
    app.include_router(router)

The factory does NOT make schema decisions for you. The caller passes
`searchable` (a whitelist of column names allowed in the WHERE clause)
and the factory uses _qid() to build safe queries from that whitelist.
"""
from __future__ import annotations

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from utils.auth_jwt import get_current_user
from utils.db import db as a2z_db, _check_table, _qid
from utils.core_audit import audit_log

logger = logging.getLogger("a2z.api.crud")


# ── Helpers (mirroring utils/api.py's private helpers; kept here so this
# module can be imported standalone without circular import on api.py) ──

def _serialize(obj: Any) -> Any:
    """Make Decimals, dates and datetimes JSON-serialisable."""
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


def _audit(action: str, user: dict, detail: str = "") -> None:
    """Audit logging helper — same shape as utils/api.py._audit but
    importable here without circular dependency."""
    try:
        username = (user or {}).get("username", "anonymous")
        audit_log(action, username, detail, module="api.v1")
    except Exception as e:
        logger.debug(f"audit_log failed: {e}")


def _db_available() -> bool:
    """Returns True if PG is reachable. Falls back to JSON otherwise."""
    try:
        return a2z_db.is_postgres_ready()
    except Exception:
        return False


# ── Router registry — for the audit gate to introspect ────────────────
# Each call to make_crud_router records its module name so G16 can
# count v1 endpoints without parsing FastAPI's internal state.

_REGISTERED_MODULES: List[str] = []

def register_module(module: str) -> None:
    """Internal: track that a v1 router was created for this module."""
    if module not in _REGISTERED_MODULES:
        _REGISTERED_MODULES.append(module)


def get_registered_modules() -> List[str]:
    """Return the list of modules that have v1 CRUD routers."""
    return list(_REGISTERED_MODULES)


# ── Pydantic models for request bodies ────────────────────────────────

class _SearchCriteria(BaseModel):
    """Search request body. Caller can pass any subset of the columns
    declared `searchable` in make_crud_router(). Unknown keys are ignored
    (whitelist enforcement)."""
    criteria: Dict[str, Any] = {}
    limit:    int = 500
    offset:   int = 0


class _ExportOpts(BaseModel):
    """Export request body. Same as a list call but lets you pass a
    larger limit and an optional format hint."""
    limit:  int = 5000
    offset: int = 0


# ══════════════════════════════════════════════════════════════════════
# THE FACTORY
# ══════════════════════════════════════════════════════════════════════

def make_crud_router(
    *,
    module:     str,
    table:      str,
    json_file:  Optional[str] = None,
    list_key:   Optional[str] = None,
    searchable: Optional[List[str]] = None,
    order_by:   str = "id",
    pk_column:  str = "id",
    primary_key_type: type = str,
) -> APIRouter:
    """Generate the 8 CRUD endpoints for a tracked table.

    Args:
        module:           URL path segment (e.g. "pipeline_deals" → /api/v1/pipeline_deals)
        table:            PG table name; MUST be in TABLE_USE_DB
        json_file:        JSON fallback filename under data/ (e.g. "pipeline.json")
        list_key:         If the JSON file is a dict like {"deals": [...]}, the array key.
                          If the JSON file is just a list, leave None.
        searchable:       Whitelist of column names allowed in search criteria.
                          Anything outside this list is ignored. Defaults to [].
        order_by:         ORDER BY clause for list/export. Caller's responsibility
                          to use only known column names; we don't escape this.
                          For safety, default to "id".
        pk_column:        Primary key column name. Defaults to "id".
        primary_key_type: Python type of the PK; controls FastAPI's path validation.

    Returns:
        FastAPI APIRouter ready to include in the main app.
    """
    # Refuse unknown tables up front. If someone wires a typo here, fail
    # at import time rather than first request time.
    _check_table(table)
    searchable = list(searchable or [])
    register_module(module)  # for the G16 audit gate

    router = APIRouter(prefix=f"/api/v1/{module}", tags=[f"v1:{module}"])

    # ──────────────────────────────────────────────────────────────────
    # JSON fallback helpers — closure over module/json_file/list_key
    # ──────────────────────────────────────────────────────────────────
    def _load_rows_from_json() -> List[Dict[str, Any]]:
        """Load all rows from the JSON fallback. Returns [] if no file."""
        if not json_file:
            return []
        raw = a2z_db.load_json(json_file, default=[])
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict) and list_key and list_key in raw:
            val = raw[list_key]
            return val if isinstance(val, list) else []
        return []

    def _save_rows_to_json(rows: List[Dict[str, Any]]) -> bool:
        """Persist back to JSON. Wraps with list_key if needed."""
        if not json_file:
            return False
        if list_key:
            payload: Any = {list_key: rows}
        else:
            payload = rows
        return a2z_db.save_json(json_file, payload)

    # ──────────────────────────────────────────────────────────────────
    # 1. LIST  — GET /api/v1/{module}
    # ──────────────────────────────────────────────────────────────────
    @router.get("", summary=f"List {module} rows (paginated)")
    def list_rows(
        limit:  int = Query(default=500, le=5000, ge=1),
        offset: int = Query(default=0, ge=0),
        user:   dict = Depends(get_current_user),
    ):
        _audit(f"API_V1_{module.upper()}_LIST", user, f"limit={limit} offset={offset}")
        if _db_available():
            try:
                from psycopg2 import sql as _sql
                # Build "SELECT * FROM <table> ORDER BY <order> LIMIT %s OFFSET %s"
                # using sql.Identifier so the table name can never inject.
                # order_by is a known constant per-router (not user input).
                query = _sql.SQL(
                    "SELECT * FROM {tbl} ORDER BY {ob} LIMIT %s OFFSET %s"
                ).format(
                    tbl=_qid(table),
                    ob=_sql.SQL(order_by),  # trusted — caller config, not user
                )
                rows = a2z_db.fetch_all(query, (limit, offset))
                return {"rows": _serialize(rows), "count": len(rows), "source": "postgresql"}
            except Exception as e:
                logger.error(f"v1 {module} LIST DB error: {e}")

        # JSON fallback
        rows = _load_rows_from_json()
        return {
            "rows":   rows[offset:offset + limit],
            "count":  len(rows),
            "source": "json",
        }

    # ──────────────────────────────────────────────────────────────────
    # 2. GET    — GET /api/v1/{module}/{id}
    # ──────────────────────────────────────────────────────────────────
    @router.get("/{row_id}", summary=f"Get one {module} row by id")
    def get_row(
        row_id: primary_key_type,
        user:   dict = Depends(get_current_user),
    ):
        _audit(f"API_V1_{module.upper()}_GET", user, f"id={row_id}")
        if _db_available():
            try:
                from psycopg2 import sql as _sql
                query = _sql.SQL(
                    "SELECT * FROM {tbl} WHERE {pk} = %s LIMIT 1"
                ).format(tbl=_qid(table), pk=_qid(pk_column))
                rows = a2z_db.fetch_all(query, (row_id,))
                if not rows:
                    raise HTTPException(status_code=404, detail=f"{module} {row_id} not found")
                return _serialize(rows[0])
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"v1 {module} GET DB error: {e}")

        # JSON fallback
        rows = _load_rows_from_json()
        for row in rows:
            if str(row.get(pk_column)) == str(row_id):
                return row
        raise HTTPException(status_code=404, detail=f"{module} {row_id} not found")

    # ──────────────────────────────────────────────────────────────────
    # 3. CREATE — POST /api/v1/{module}
    # ──────────────────────────────────────────────────────────────────
    @router.post("", status_code=201, summary=f"Create a new {module} row")
    async def create_row(
        request: Request,
        user:    dict = Depends(get_current_user),
    ):
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")
        if pk_column not in body:
            raise HTTPException(status_code=400, detail=f"Missing required field: {pk_column}")

        _audit(f"API_V1_{module.upper()}_CREATE", user, f"id={body.get(pk_column)}")

        if _db_available():
            try:
                from psycopg2 import sql as _sql
                import json as _json
                cols = list(body.keys())
                # Whitelist columns implicitly via _qid (which only escapes,
                # but PG rejects unknown columns at INSERT time anyway)
                vals = [
                    _json.dumps(v) if isinstance(v, (dict, list)) else v
                    for v in body.values()
                ]
                placeholders = _sql.SQL(", ").join([_sql.Placeholder()] * len(cols))
                query = _sql.SQL(
                    "INSERT INTO {tbl} ({cols}) VALUES ({vals}) "
                    "ON CONFLICT ({pk}) DO NOTHING RETURNING *"
                ).format(
                    tbl=_qid(table),
                    cols=_sql.SQL(", ").join([_qid(c) for c in cols]),
                    vals=placeholders,
                    pk=_qid(pk_column),
                )
                rows = a2z_db.fetch_all(query, tuple(vals))
                if not rows:
                    raise HTTPException(
                        status_code=409,
                        detail=f"{module} with {pk_column}={body.get(pk_column)} already exists",
                    )
                return _serialize(rows[0])
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"v1 {module} CREATE DB error: {e}")
                raise HTTPException(status_code=500, detail="DB write failed")

        # JSON fallback
        rows = _load_rows_from_json()
        if any(str(r.get(pk_column)) == str(body[pk_column]) for r in rows):
            raise HTTPException(
                status_code=409,
                detail=f"{module} with {pk_column}={body[pk_column]} already exists",
            )
        rows.append(body)
        if not _save_rows_to_json(rows):
            raise HTTPException(status_code=500, detail="JSON write failed")
        return body

    # ──────────────────────────────────────────────────────────────────
    # 4. UPDATE — PUT /api/v1/{module}/{id}
    # ──────────────────────────────────────────────────────────────────
    @router.put("/{row_id}", summary=f"Upsert a {module} row")
    async def update_row(
        row_id:  primary_key_type,
        request: Request,
        user:    dict = Depends(get_current_user),
    ):
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Body must be a JSON object")
        body[pk_column] = row_id  # path id wins over body id

        _audit(f"API_V1_{module.upper()}_UPDATE", user, f"id={row_id}")

        if _db_available():
            try:
                from psycopg2 import sql as _sql
                import json as _json
                cols = list(body.keys())
                vals = [
                    _json.dumps(v) if isinstance(v, (dict, list)) else v
                    for v in body.values()
                ]
                # Build "INSERT ... ON CONFLICT (pk) DO UPDATE SET col = EXCLUDED.col"
                set_clause = _sql.SQL(", ").join([
                    _sql.SQL("{c} = EXCLUDED.{c}").format(c=_qid(c))
                    for c in cols if c != pk_column
                ])
                placeholders = _sql.SQL(", ").join([_sql.Placeholder()] * len(cols))
                query = _sql.SQL(
                    "INSERT INTO {tbl} ({cols}) VALUES ({vals}) "
                    "ON CONFLICT ({pk}) DO UPDATE SET {set_clause} "
                    "RETURNING *"
                ).format(
                    tbl=_qid(table),
                    cols=_sql.SQL(", ").join([_qid(c) for c in cols]),
                    vals=placeholders,
                    pk=_qid(pk_column),
                    set_clause=set_clause,
                )
                rows = a2z_db.fetch_all(query, tuple(vals))
                return _serialize(rows[0]) if rows else body
            except Exception as e:
                logger.error(f"v1 {module} UPDATE DB error: {e}")
                raise HTTPException(status_code=500, detail="DB write failed")

        # JSON fallback
        rows = _load_rows_from_json()
        replaced = False
        for i, row in enumerate(rows):
            if str(row.get(pk_column)) == str(row_id):
                rows[i] = body
                replaced = True
                break
        if not replaced:
            rows.append(body)
        if not _save_rows_to_json(rows):
            raise HTTPException(status_code=500, detail="JSON write failed")
        return body

    # ──────────────────────────────────────────────────────────────────
    # 5. DELETE — DELETE /api/v1/{module}/{id}
    # ──────────────────────────────────────────────────────────────────
    @router.delete("/{row_id}", summary=f"Delete a {module} row")
    def delete_row(
        row_id: primary_key_type,
        user:   dict = Depends(get_current_user),
    ):
        _audit(f"API_V1_{module.upper()}_DELETE", user, f"id={row_id}")

        if _db_available():
            try:
                from psycopg2 import sql as _sql
                query = _sql.SQL(
                    "DELETE FROM {tbl} WHERE {pk} = %s RETURNING {pk}"
                ).format(tbl=_qid(table), pk=_qid(pk_column))
                rows = a2z_db.fetch_all(query, (row_id,))
                if not rows:
                    raise HTTPException(status_code=404, detail=f"{module} {row_id} not found")
                return {"deleted": True, pk_column: row_id}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"v1 {module} DELETE DB error: {e}")
                raise HTTPException(status_code=500, detail="DB delete failed")

        # JSON fallback
        rows = _load_rows_from_json()
        new_rows = [r for r in rows if str(r.get(pk_column)) != str(row_id)]
        if len(new_rows) == len(rows):
            raise HTTPException(status_code=404, detail=f"{module} {row_id} not found")
        if not _save_rows_to_json(new_rows):
            raise HTTPException(status_code=500, detail="JSON write failed")
        return {"deleted": True, pk_column: row_id}

    # ──────────────────────────────────────────────────────────────────
    # 6. EXPORT — POST /api/v1/{module}/export
    # ──────────────────────────────────────────────────────────────────
    @router.post("/export", summary=f"Export {module} rows (large page allowed)")
    def export_rows(
        opts: _ExportOpts = _ExportOpts(),
        user: dict = Depends(get_current_user),
    ):
        _audit(f"API_V1_{module.upper()}_EXPORT", user, f"limit={opts.limit} offset={opts.offset}")
        # Reuse list logic but cap at 5000
        if _db_available():
            try:
                from psycopg2 import sql as _sql
                query = _sql.SQL(
                    "SELECT * FROM {tbl} ORDER BY {ob} LIMIT %s OFFSET %s"
                ).format(tbl=_qid(table), ob=_sql.SQL(order_by))
                rows = a2z_db.fetch_all(query, (min(opts.limit, 5000), opts.offset))
                return {
                    "rows":      _serialize(rows),
                    "count":     len(rows),
                    "exported_at": datetime.utcnow().isoformat() + "Z",
                    "source":    "postgresql",
                }
            except Exception as e:
                logger.error(f"v1 {module} EXPORT DB error: {e}")

        rows = _load_rows_from_json()
        return {
            "rows":      rows[opts.offset:opts.offset + min(opts.limit, 5000)],
            "count":     len(rows),
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "source":    "json",
        }

    # ──────────────────────────────────────────────────────────────────
    # 7. SEARCH — POST /api/v1/{module}/search
    # ──────────────────────────────────────────────────────────────────
    @router.post("/search", summary=f"Search {module} rows by column criteria")
    def search_rows(
        opts: _SearchCriteria = _SearchCriteria(),
        user: dict = Depends(get_current_user),
    ):
        _audit(f"API_V1_{module.upper()}_SEARCH", user,
               f"keys={list(opts.criteria.keys())} limit={opts.limit}")

        # Whitelist criteria — drop anything not in `searchable`
        crit = {k: v for k, v in opts.criteria.items() if k in searchable}
        limit  = max(1,   min(opts.limit,  5000))
        offset = max(0,   opts.offset)

        if _db_available():
            try:
                from psycopg2 import sql as _sql
                where_parts = []
                params: list = []
                for col, val in crit.items():
                    where_parts.append(_sql.SQL("{c} = %s").format(c=_qid(col)))
                    params.append(val)
                where_clause = _sql.SQL(" WHERE ") + _sql.SQL(" AND ").join(where_parts) \
                    if where_parts else _sql.SQL("")
                query = (_sql.SQL("SELECT * FROM {tbl}") + where_clause +
                         _sql.SQL(" ORDER BY {ob} LIMIT %s OFFSET %s")
                         ).format(tbl=_qid(table), ob=_sql.SQL(order_by))
                params.extend([limit, offset])
                rows = a2z_db.fetch_all(query, tuple(params))
                return {
                    "rows":     _serialize(rows),
                    "count":    len(rows),
                    "criteria": crit,
                    "source":   "postgresql",
                }
            except Exception as e:
                logger.error(f"v1 {module} SEARCH DB error: {e}")

        # JSON fallback — apply criteria in Python
        rows = _load_rows_from_json()
        if crit:
            rows = [r for r in rows if all(r.get(k) == v for k, v in crit.items())]
        return {
            "rows":     rows[offset:offset + limit],
            "count":    len(rows),
            "criteria": crit,
            "source":   "json",
        }

    # ──────────────────────────────────────────────────────────────────
    # 8. DASHBOARD — GET /api/v1/{module}/dashboard
    # ──────────────────────────────────────────────────────────────────
    @router.get("/dashboard", summary=f"Summary metrics for {module}")
    def dashboard(user: dict = Depends(get_current_user)):
        _audit(f"API_V1_{module.upper()}_DASHBOARD", user)

        if _db_available():
            try:
                from psycopg2 import sql as _sql
                count_q = _sql.SQL("SELECT COUNT(*) FROM {tbl}").format(tbl=_qid(table))
                count_rows = a2z_db.fetch_all(count_q, ())
                total = (count_rows[0].get("count") if count_rows else 0) or 0
                return {
                    "module":       module,
                    "table":        table,
                    "total_rows":   int(total),
                    "searchable":   searchable,
                    "generated_at": datetime.utcnow().isoformat() + "Z",
                    "source":       "postgresql",
                }
            except Exception as e:
                logger.error(f"v1 {module} DASHBOARD DB error: {e}")

        rows = _load_rows_from_json()
        return {
            "module":       module,
            "table":        table,
            "total_rows":   len(rows),
            "searchable":   searchable,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source":       "json",
        }

    return router
