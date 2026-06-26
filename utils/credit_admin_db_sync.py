"""
utils/credit_admin_db_sync.py  —  Batch CA-1 (DORMANT in CA-1).

PostgreSQL write-sync + read-normalizer for credit_admin cases, modeled
byte-for-intent on api._db_sync_pipeline_deal (the proven pipeline template).

CA-1 status: these functions are ADDED but NOT yet called by any route.
Only scripts/migrate_credit_admin_to_pg.py calls _db_sync_credit_admin_case
(for the one-time backfill). Wiring into the live mutation routes and the
DB-first read flip is Batch CA-2 — kept separate so CA-1 cannot change any
runtime behaviour and cannot break the 295/295 harness.

Design choice vs pipeline: the COMPLETE case is stored in `data` JSONB, so no
sub-flow field (collateral / legal / perfection / insurance / authorizations /
override) is ever lost. Scalar columns are query/index helpers only.
"""
from __future__ import annotations
import json as _json
import logging
from datetime import date as _date
from typing import Optional

_log = logging.getLogger("a2z.credit_admin")

# Scalar columns lifted to the table for query/index. Order == INSERT column order.
_SCALAR_ORDER = [
    "id", "application_id", "client_name", "product", "amount",
    "rm_code", "rm_name", "approval_date", "all_conditions_met",
    "ready_for_disbursement", "disbursed", "disbursement_date",
    "last_updated", "data",
]


def _date_or_none(v):
    """Coerce '' / None / whitespace to NULL; pass through real date strings."""
    v = (str(v).strip() if v is not None else "")
    return v or None


def _row_from_case(case: dict) -> Optional[dict]:
    """Build the DB row dict (scalars + complete-case JSONB) from a case."""
    cid = str(case.get("id", "") or "")
    if not cid:
        return None
    today = _date.today().isoformat()
    return {
        "id":                     cid,
        "application_id":         case.get("application_id"),
        "client_name":            case.get("client_name"),
        "product":                case.get("product"),
        "amount":                 case.get("amount"),
        "rm_code":                case.get("rm_code"),
        "rm_name":                case.get("rm_name"),
        "approval_date":          _date_or_none(case.get("approval_date")),
        "all_conditions_met":     bool(case.get("all_conditions_met")),
        "ready_for_disbursement": bool(case.get("ready_for_disbursement")),
        "disbursed":              bool(case.get("disbursed")),
        "disbursement_date":      _date_or_none(case.get("disbursement_date")),
        "last_updated":           _date_or_none(case.get("last_updated")) or today,
        # COMPLETE, lossless mirror of the whole case:
        "data":                   _json.dumps(case, default=str),
    }


def _db_sync_credit_admin_case(case: Optional[dict], conflict: str = "update",
                               swallow: bool = True) -> None:
    """Upsert a credit_admin case into Postgres.

    conflict='update' (default): mirror/upsert — ON CONFLICT (id) DO UPDATE.
                                  Best-effort: logs on failure (matches pipeline
                                  mirror semantics).
    conflict='raise':            create path — ON CONFLICT DO NOTHING; if the
                                  insert is suppressed (id already present) we
                                  raise, so a colliding create can never be a
                                  silent overwrite. The PK is the hard guarantee.
    swallow=True (default):      log-and-continue on error (live mirror).
    swallow=False:               re-raise on error — used by the one-time
                                  backfill so it reports a TRUTHFUL ok/fail tally
                                  instead of a false 'all ok'.

    No-op when Postgres is unavailable.
    """
    if not case:
        return
    try:
        from utils.db import db as _db
    except Exception as e:
        _log.error(f"credit_admin sync: cannot import db: {e}")
        return
    if not _db.is_postgres_ready():
        return

    row = _row_from_case(case)
    if row is None:
        return
    cols = _SCALAR_ORDER
    placeholders = ", ".join(["%s"] * len(cols))
    values = tuple(row[c] for c in cols)

    try:
        if conflict == "raise":
            sql = (f"INSERT INTO credit_admin ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO NOTHING RETURNING id")
            got = _db.fetch_one(sql, values)
            if not got:
                raise RuntimeError(
                    f"duplicate key: credit_admin id {row['id']} already in Postgres")
        else:
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
            sql = (f"INSERT INTO credit_admin ({', '.join(cols)}) "
                   f"VALUES ({placeholders}) "
                   f"ON CONFLICT (id) DO UPDATE SET {updates}")
            _db.execute(sql, values)
    except Exception as e:
        # Do NOT swallow silently — drift between JSON and PG is exactly what a
        # silent except causes. Log loudly; re-raise on the create path, or when
        # the caller explicitly asked (swallow=False, e.g. the backfill).
        _log.error(f"credit_admin DB sync FAILED for {row['id']}: {e}")
        if conflict == "raise" or not swallow:
            raise


def _normalize_db_credit_admin_row(row: Optional[dict]) -> Optional[dict]:
    """Reconstruct the full case dict from a PG row.

    The complete case lives in `data` JSONB, so we start from there and lose
    nothing. Scalar columns are not re-merged (data is authoritative); we only
    backfill `id` defensively.
    """
    if not row:
        return None
    data = row.get("data")
    if isinstance(data, str):
        try:
            data = _json.loads(data)
        except Exception:
            data = {}
    case = dict(data) if isinstance(data, dict) else {}
    if not case.get("id") and row.get("id"):
        case["id"] = row["id"]
    return case
