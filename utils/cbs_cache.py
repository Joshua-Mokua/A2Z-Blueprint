"""
utils.cbs_cache — Postgres-backed cache for FlexCube account lookups.

Every successful FlexCube query (CUSTOMERACCOUNTDETAILS + CUSTOMERACTIVELOANS)
is stored here so repeat lookups are served instantly from the local DB
instead of hitting the internal script API again.

Table: cbs_account_cache
  account_number  — PRIMARY KEY (FlexCube account number)
  cif             — customer CIF (for lookup by customer)
  customer_name   — denormalized for quick display without joining
  payload         — full JSON payload (account + loans)
  fetched_at      — when the row was first inserted
  refreshed_at    — when it was last re-fetched from FlexCube
  is_stale        — TRUE means the cron job should refresh this row
  source          — 'flexcube' or 'csv' (we only cache flexcube hits)

Cache TTL (CBS_CACHE_TTL_HOURS, default 24):
  Rows older than TTL are treated as stale — served from cache but the cron
  job will refresh them. The data is NOT withheld while stale; stale just
  means "please refresh when you next run".

Cron job:
  Call refresh_stale_accounts() from a scheduled script or crontab entry.
  It re-fetches each stale account from FlexCube and updates the row.
  Add to crontab on the VM:
    0 * * * * /var/www/a2z-blueprint/A2Z-Blueprint/scripts/refresh_cbs_cache.sh

DB gate:
  All functions check is_postgres_ready() first and no-op silently when
  Postgres is unavailable. The lookup path is never blocked by cache failures.
"""

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("a2z.cbs_cache")

_TTL_HOURS = int(os.getenv("CBS_CACHE_TTL_HOURS", "24"))

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cbs_account_cache (
    account_number  VARCHAR(100) PRIMARY KEY,
    cif             VARCHAR(50),
    customer_name   VARCHAR(255),
    payload         JSONB        NOT NULL,
    fetched_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    refreshed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_stale        BOOLEAN      NOT NULL DEFAULT FALSE,
    source          VARCHAR(20)  NOT NULL DEFAULT 'flexcube'
);
CREATE INDEX IF NOT EXISTS cbs_cache_cif_idx        ON cbs_account_cache (cif);
CREATE INDEX IF NOT EXISTS cbs_cache_stale_idx      ON cbs_account_cache (is_stale) WHERE is_stale = TRUE;
CREATE INDEX IF NOT EXISTS cbs_cache_refreshed_idx  ON cbs_account_cache (refreshed_at);
"""


# ── DB access ─────────────────────────────────────────────────────────────

def _db():
    from utils.db import db
    return db


def _ready() -> bool:
    try:
        return _db().is_postgres_ready()
    except Exception:
        return False


# ── Table bootstrap ───────────────────────────────────────────────────────

def ensure_table() -> bool:
    """Create cbs_account_cache if it doesn't exist. Returns True on success."""
    if not _ready():
        return False
    try:
        _db().execute(_CREATE_TABLE_SQL)
        return True
    except Exception as exc:
        logger.warning("cbs_cache: could not ensure table: %s", exc)
        return False


# ── Read ──────────────────────────────────────────────────────────────────

def get_cached(account_number: str) -> Optional[dict]:
    """
    Return cached payload for account_number, or None if not cached.

    Stale rows ARE returned (caller decides whether to trigger a background
    refresh). The 'cache_hit' and 'is_stale' keys are injected so the caller
    can surface this info in the API response.
    """
    if not _ready():
        return None
    try:
        row = _db().fetch_one(
            "SELECT payload, refreshed_at, is_stale FROM cbs_account_cache "
            "WHERE account_number = %s",
            (str(account_number).strip(),),
        )
        if row is None:
            return None
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        payload["_cache_hit"]     = True
        payload["_cache_stale"]   = bool(row["is_stale"])
        payload["_cache_age_h"]   = _age_hours(row["refreshed_at"])
        return payload
    except Exception as exc:
        logger.warning("cbs_cache: read failed for %s: %s", account_number, exc)
        return None


# ── Write ─────────────────────────────────────────────────────────────────

def store(account_number: str, payload: dict, source: str = "flexcube") -> bool:
    """
    Upsert a FlexCube result into the cache.

    On INSERT: sets fetched_at = NOW().
    On UPDATE: updates payload + refreshed_at, clears is_stale.
    Returns True on success, False on any DB error (non-blocking).
    """
    if not _ready():
        return False
    num  = str(account_number).strip()
    cif  = str(payload.get("cif") or payload.get("f12_cif") or "")
    name = str(payload.get("customer_name") or "")

    # Strip internal cache-meta keys before storing
    clean = {k: v for k, v in payload.items() if not k.startswith("_cache")}

    try:
        ensure_table()
        _db().execute(
            """
            INSERT INTO cbs_account_cache
                (account_number, cif, customer_name, payload, fetched_at, refreshed_at, is_stale, source)
            VALUES (%s, %s, %s, %s::jsonb, NOW(), NOW(), FALSE, %s)
            ON CONFLICT (account_number) DO UPDATE SET
                cif           = EXCLUDED.cif,
                customer_name = EXCLUDED.customer_name,
                payload       = EXCLUDED.payload,
                refreshed_at  = NOW(),
                is_stale      = FALSE,
                source        = EXCLUDED.source
            """,
            (num, cif, name, json.dumps(clean), source),
        )
        logger.debug("cbs_cache: stored %s (cif=%s)", num, cif)
        return True
    except Exception as exc:
        logger.warning("cbs_cache: write failed for %s: %s", num, exc)
        return False


# ── Stale management ──────────────────────────────────────────────────────

def mark_all_stale() -> int:
    """Mark every cached account as stale (forces full refresh on next cron run)."""
    if not _ready():
        return 0
    try:
        ensure_table()
        _db().execute("UPDATE cbs_account_cache SET is_stale = TRUE")
        count = _db().fetch_scalar("SELECT COUNT(*) FROM cbs_account_cache WHERE is_stale = TRUE")
        return int(count or 0)
    except Exception as exc:
        logger.warning("cbs_cache: mark_all_stale failed: %s", exc)
        return 0


def _mark_stale_by_ttl() -> int:
    """Auto-mark rows older than CBS_CACHE_TTL_HOURS as stale."""
    if not _ready():
        return 0
    try:
        _db().execute(
            "UPDATE cbs_account_cache SET is_stale = TRUE "
            "WHERE is_stale = FALSE AND refreshed_at < NOW() - INTERVAL '%s hours'",
            (_TTL_HOURS,),
        )
        return _db().fetch_scalar(
            "SELECT COUNT(*) FROM cbs_account_cache WHERE is_stale = TRUE"
        ) or 0
    except Exception as exc:
        logger.warning("cbs_cache: TTL mark-stale failed: %s", exc)
        return 0


# ── Cron refresh ──────────────────────────────────────────────────────────

def refresh_stale_accounts(limit: int = 200) -> dict:
    """
    Re-fetch stale accounts from FlexCube and update cache rows.
    Called by the cron script and the admin API endpoint.

    Returns a stats dict:
      refreshed  — successfully re-fetched and stored
      failed     — FlexCube returned nothing or raised an error
      skipped    — FlexCube not configured (FLEXCUBE_SCRIPTS_URL unset)
      total_stale — how many stale rows existed before this run
    """
    from utils.flexcube_script_client import is_configured

    if not _ready():
        return {"error": "Postgres not available", "refreshed": 0, "failed": 0, "skipped": 0, "total_stale": 0}

    if not is_configured():
        return {"error": "FLEXCUBE_SCRIPTS_URL not set", "refreshed": 0, "failed": 0, "skipped": 0, "total_stale": 0}

    # Auto-age rows past TTL before fetching the work list
    _mark_stale_by_ttl()

    try:
        rows = _db().fetch_all(
            "SELECT account_number FROM cbs_account_cache "
            "WHERE is_stale = TRUE ORDER BY refreshed_at ASC LIMIT %s",
            (limit,),
        )
    except Exception as exc:
        return {"error": str(exc), "refreshed": 0, "failed": 0, "skipped": 0, "total_stale": 0}

    total_stale = _db().fetch_scalar(
        "SELECT COUNT(*) FROM cbs_account_cache WHERE is_stale = TRUE"
    ) or 0

    refreshed = failed = 0
    for r in rows:
        acct_num = r["account_number"]
        try:
            from utils.cbs_manager import get_account_360
            payload = get_account_360(acct_num)
            if payload and payload.get("account_number"):
                store(acct_num, payload, source="flexcube")
                refreshed += 1
            else:
                # Account may have been closed — mark not stale so we don't loop
                _db().execute(
                    "UPDATE cbs_account_cache SET is_stale = FALSE WHERE account_number = %s",
                    (acct_num,),
                )
                failed += 1
        except Exception as exc:
            logger.warning("cbs_cache: refresh failed for %s: %s", acct_num, exc)
            failed += 1

    logger.info(
        "cbs_cache: refresh complete — refreshed=%d failed=%d total_stale=%d",
        refreshed, failed, total_stale,
    )
    return {
        "refreshed":   refreshed,
        "failed":      failed,
        "skipped":     0,
        "total_stale": total_stale,
        "batch_size":  len(rows),
        "ttl_hours":   _TTL_HOURS,
    }


# ── Status / diagnostics ──────────────────────────────────────────────────

def cache_stats() -> dict:
    """Summary stats for the admin debug panel."""
    if not _ready():
        return {"available": False, "reason": "Postgres not configured"}
    try:
        ensure_table()
        total  = _db().fetch_scalar("SELECT COUNT(*) FROM cbs_account_cache") or 0
        stale  = _db().fetch_scalar("SELECT COUNT(*) FROM cbs_account_cache WHERE is_stale = TRUE") or 0
        oldest = _db().fetch_scalar("SELECT MIN(refreshed_at) FROM cbs_account_cache")
        newest = _db().fetch_scalar("SELECT MAX(refreshed_at) FROM cbs_account_cache")
        return {
            "available":     True,
            "total_cached":  int(total),
            "stale_count":   int(stale),
            "fresh_count":   int(total) - int(stale),
            "oldest_entry":  oldest.isoformat() if oldest else None,
            "newest_entry":  newest.isoformat() if newest else None,
            "ttl_hours":     _TTL_HOURS,
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}


# ── Internal helper ───────────────────────────────────────────────────────

def _age_hours(ts) -> float:
    if ts is None:
        return 0.0
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    return round(delta.total_seconds() / 3600, 1)
