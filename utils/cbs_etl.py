"""
utils.cbs_etl — FlexCube EOD bulk account import.

Triggers the end-of-day customer export on the FlexCube intranet server,
downloads the two resulting CSVs (CORP + INDI), and upserts all rows into
the local Postgres cbs_accounts table.

After the ETL runs, cbs_manager queries Postgres directly — zero FlexCube
round-trips per user lookup.

Required env vars:
  FLEXCUBE_EOD_BASE_URL   — base URL of the FlexCube intranet server
                            e.g.  http://eke-intranetlive:400
                            (no trailing slash)

Optional env vars:
  FLEXCUBE_EOD_TRIGGER_TIMEOUT — timeout for the export trigger call in seconds
                                  (default 900 = 15 min; command blocks until done)
  FLEXCUBE_EOD_TIMEOUT_SECONDS — timeout for CSV download requests (default 60)

CSV field → DB column mapping:
  CUST_AC_NO          → account_number  (PRIMARY KEY)
  F12_CIF             → f12_cif
  F12_AC_NO           → f12_ac_no
  BRANCH_CODE         → branch_code
  CUST_CATEGORY       → cust_category
  ETI_CIF_CLASS_CATEGORY → cif_class
  ETIBISEG2           → sub_segment
  ACC_OFCR            → rm_code
  OFFICER_NAME        → rm_name
  ACY_WITHDRAWABLE_BAL → available_balance
  LCY_CURR_BALANCE    → lcy_balance
  RECORD_STAT         → account_status
  ACCOUNT_CLASS       → account_class
  AC_DESC             → account_type_name
  AC_OPEN_DATE        → date_opened
  DORMANCY_DATE       → dormancy_date
  AC_STAT_DORMANT     → is_dormant
  ADDRESS_LINE1       → address
  CHEQUE_BOOK_FACILITY → cheque_book
  ATM_FACILITY        → atm_facility
  TELEPHONE           → phone
  E_MAIL              → email
  INTRODUCER          → introducer
  (derived from filename) → customer_type  ('CORP' or 'INDI')
"""

import csv
import io
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger("a2z.cbs_etl")

_DOWNLOAD_TIMEOUT = int(os.getenv("FLEXCUBE_EOD_TIMEOUT_SECONDS",  "60"))
# The export command is synchronous — Laravel blocks until done then returns "done".
# 5-10 min observed; default 900s (15 min) gives headroom.
_TRIGGER_TIMEOUT  = int(os.getenv("FLEXCUBE_EOD_TRIGGER_TIMEOUT",  "900"))


# ── Table DDL ─────────────────────────────────────────────────────────────

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cbs_accounts (
    account_number      VARCHAR(100)  PRIMARY KEY,
    f12_cif             VARCHAR(50),
    f12_ac_no           VARCHAR(100),
    branch_code         VARCHAR(20),
    customer_type       VARCHAR(10),
    cust_category       VARCHAR(50),
    cif_class           VARCHAR(50),
    sub_segment         VARCHAR(50),
    rm_code             VARCHAR(20),
    rm_name             VARCHAR(255),
    available_balance   NUMERIC(20,2),
    lcy_balance         NUMERIC(20,2),
    account_status      VARCHAR(10),
    account_class       VARCHAR(50),
    account_type_name   VARCHAR(255),
    date_opened         DATE,
    dormancy_date       DATE,
    is_dormant          BOOLEAN       NOT NULL DEFAULT FALSE,
    address             TEXT,
    cheque_book         BOOLEAN       NOT NULL DEFAULT FALSE,
    atm_facility        BOOLEAN       NOT NULL DEFAULT FALSE,
    phone               TEXT,
    email               TEXT,
    introducer          VARCHAR(50),
    last_etl_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    etl_source          VARCHAR(10)
);
CREATE INDEX IF NOT EXISTS cbs_acc_cif_idx    ON cbs_accounts (f12_cif);
CREATE INDEX IF NOT EXISTS cbs_acc_branch_idx ON cbs_accounts (branch_code);
CREATE INDEX IF NOT EXISTS cbs_acc_rm_idx     ON cbs_accounts (rm_code);
CREATE INDEX IF NOT EXISTS cbs_acc_status_idx ON cbs_accounts (account_status);
"""

_ETL_LOG_SQL = """
CREATE TABLE IF NOT EXISTS cbs_etl_log (
    id              SERIAL      PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    corp_rows       INTEGER,
    indi_rows       INTEGER,
    total_upserted  INTEGER,
    errors          INTEGER,
    status          VARCHAR(20),
    message         TEXT
);
"""


# ── Helpers ───────────────────────────────────────────────────────────────

def _base_url() -> str:
    url = os.getenv("FLEXCUBE_EOD_BASE_URL", "").rstrip("/")
    if not url:
        raise EtlConfigError(
            "FLEXCUBE_EOD_BASE_URL is not set. "
            "Add it to .env and restart: e.g. http://eke-intranetlive:400"
        )
    return url


def _month_suffix(dt: Optional[datetime] = None) -> str:
    """Returns MM-YYYY for the given datetime (default: now)."""
    d = dt or datetime.now(timezone.utc)
    return f"{d.month:02d}-{d.year}"


def _csv_filename(customer_type: str, dt: Optional[datetime] = None) -> str:
    return f"EKE-{customer_type}-CUSTOMERS-{_month_suffix(dt)}.csv"


def _safe_decimal(v) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def _safe_date(v) -> Optional[str]:
    if not v or str(v).strip() in ("", "None", "nan"):
        return None
    s = str(v).strip()
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _yn_bool(v) -> bool:
    return str(v).strip().upper() in ("Y", "YES", "1", "TRUE")


def _row_to_record(row: dict, customer_type: str) -> dict:
    """Map one CSV row (dict) to a cbs_accounts DB record."""
    return {
        "account_number":   str(row.get("CUST_AC_NO", "")).strip(),
        "f12_cif":          str(row.get("F12_CIF", "")).strip(),
        "f12_ac_no":        str(row.get("F12_AC_NO", "")).strip(),
        "branch_code":      str(row.get("BRANCH_CODE", "")).strip(),
        "customer_type":    customer_type,
        "cust_category":    str(row.get("CUST_CATEGORY", "")).strip(),
        "cif_class":        str(row.get("ETI_CIF_CLASS_CATEGORY", "")).strip(),
        "sub_segment":      str(row.get("ETIBISEG2", "")).strip(),
        "rm_code":          str(row.get("ACC_OFCR", "")).strip(),
        "rm_name":          str(row.get("OFFICER_NAME", "")).strip(),
        "available_balance": _safe_decimal(row.get("ACY_WITHDRAWABLE_BAL")),
        "lcy_balance":      _safe_decimal(row.get("LCY_CURR_BALANCE")),
        "account_status":   str(row.get("RECORD_STAT", "")).strip(),
        "account_class":    str(row.get("ACCOUNT_CLASS", "")).strip(),
        "account_type_name": str(row.get("AC_DESC", "")).strip(),
        "date_opened":      _safe_date(row.get("AC_OPEN_DATE")),
        "dormancy_date":    _safe_date(row.get("DORMANCY_DATE")),
        "is_dormant":       _yn_bool(row.get("AC_STAT_DORMANT")),
        "address":          str(row.get("ADDRESS_LINE1", "")).strip(),
        "cheque_book":      _yn_bool(row.get("CHEQUE_BOOK_FACILITY")),
        "atm_facility":     _yn_bool(row.get("ATM_FACILITY")),
        "phone":            str(row.get("TELEPHONE", "")).strip(),
        "email":            str(row.get("E_MAIL", "")).strip(),
        "introducer":       str(row.get("INTRODUCER", "")).strip(),
        "etl_source":       customer_type,
    }


# ── DB helpers ────────────────────────────────────────────────────────────

def _db():
    from utils.db import db
    return db


def ensure_tables() -> None:
    _db().execute(_CREATE_TABLE_SQL)
    _db().execute(_ETL_LOG_SQL)


def _upsert_record(rec: dict) -> None:
    """Upsert one account record, always updating last_etl_at."""
    cols = list(rec.keys())
    vals = [rec[c] for c in cols]

    placeholders = ", ".join(["%s"] * len(cols))
    update_parts = ", ".join(
        f"{c} = EXCLUDED.{c}"
        for c in cols
        if c not in ("account_number",)
    )
    sql = (
        f"INSERT INTO cbs_accounts ({', '.join(cols)}, last_etl_at) "
        f"VALUES ({placeholders}, NOW()) "
        f"ON CONFLICT (account_number) DO UPDATE SET {update_parts}, last_etl_at = NOW()"
    )
    _db().execute(sql, tuple(vals))


def _upsert_batch(records: list) -> tuple[int, int]:
    """Batch upsert via execute_values — one round trip + one commit per
    batch instead of per row. Falls back to row-by-row (which isolates and
    skips the bad row) if the batch statement itself fails."""
    from psycopg2.extras import execute_values

    cols = list(records[0].keys())
    update_cols = [c for c in cols if c != "account_number"]
    sql = (
        f"INSERT INTO cbs_accounts ({', '.join(cols)}, last_etl_at) VALUES %s "
        f"ON CONFLICT (account_number) DO UPDATE SET "
        + ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)
        + ", last_etl_at = EXCLUDED.last_etl_at"
    )
    template = "(" + ", ".join(["%s"] * len(cols)) + ", NOW())"
    values = [tuple(rec[c] for c in cols) for rec in records]

    try:
        with _db().transaction() as conn:
            with conn.cursor() as cur:
                execute_values(cur, sql, values, template=template, page_size=len(values))
        return len(records), 0
    except Exception as exc:
        logger.warning("cbs_etl: batch of %d failed (%s) — retrying row by row",
                        len(records), exc)
        ok = err = 0
        for rec in records:
            try:
                _upsert_record(rec)
                ok += 1
            except Exception as row_exc:
                logger.warning("cbs_etl: upsert failed for %s: %s",
                                rec.get("account_number"), row_exc)
                err += 1
        return ok, err


def _log_run(corp_rows: int, indi_rows: int, errors: int,
             status: str, message: str = "") -> None:
    try:
        _db().execute(
            "INSERT INTO cbs_etl_log "
            "(finished_at, corp_rows, indi_rows, total_upserted, errors, status, message) "
            "VALUES (NOW(), %s, %s, %s, %s, %s, %s)",
            (corp_rows, indi_rows, corp_rows + indi_rows, errors, status, message),
        )
    except Exception as exc:
        logger.warning("cbs_etl: could not write etl_log: %s", exc)


# ── Public exceptions ─────────────────────────────────────────────────────

class EtlConfigError(Exception):
    """FLEXCUBE_EOD_BASE_URL not set."""

class EtlDownloadError(Exception):
    """CSV download failed (HTTP error or network issue)."""


# ── Core ETL steps ────────────────────────────────────────────────────────

def trigger_export() -> bool:
    """
    GET /command/export:customers and wait for the synchronous response.

    The Laravel command blocks for 5-10 min then returns dd("done").
    We wait up to FLEXCUBE_EOD_TRIGGER_TIMEOUT seconds (default 900).
    CSVs are ready to download immediately after this returns.
    """
    url = f"{_base_url()}/command/export:customers"
    logger.info("cbs_etl: triggering export — this blocks until done (~5-10 min) …")
    try:
        resp = requests.get(url, timeout=_TRIGGER_TIMEOUT)
        resp.raise_for_status()
        body = resp.text.strip().strip('"').lower()
        if body != "done":
            logger.warning("cbs_etl: unexpected trigger response body: %r", resp.text[:100])
        logger.info("cbs_etl: export complete (response=%r)", body)
        return True
    except requests.RequestException as exc:
        raise EtlDownloadError(f"Export trigger failed: {exc}") from exc


def download_csv(customer_type: str, dt: Optional[datetime] = None) -> str:
    """
    Download one of the two CSV files (CORP or INDI) and return its text.

    Tries the current month first; if that 404s, tries the previous month
    (useful in the first few days of a new month before EOD re-runs).
    """
    base = _base_url()
    attempts = [dt or datetime.now(timezone.utc)]
    # Previous month fallback
    first = attempts[0]
    if first.month == 1:
        prev = first.replace(year=first.year - 1, month=12, day=1)
    else:
        prev = first.replace(month=first.month - 1, day=1)
    attempts.append(prev)

    last_exc = None
    for attempt_dt in attempts:
        filename = _csv_filename(customer_type, attempt_dt)
        url = f"{base}/eod-download/{filename}"
        try:
            resp = requests.get(url, timeout=_DOWNLOAD_TIMEOUT)
            if resp.status_code == 404:
                logger.info("cbs_etl: %s not found at %s, trying previous month", filename, url)
                last_exc = EtlDownloadError(f"404 for {filename}")
                continue
            resp.raise_for_status()
            logger.info("cbs_etl: downloaded %s (%d bytes)", filename, len(resp.content))
            return resp.text
        except requests.RequestException as exc:
            last_exc = EtlDownloadError(f"Download failed for {filename}: {exc}")
            continue

    raise last_exc or EtlDownloadError(f"Could not download {customer_type} CSV")


_UPSERT_BATCH_SIZE = 1000


def parse_and_upsert(csv_text: str, customer_type: str) -> tuple[int, int]:
    """
    Parse CSV text and upsert into cbs_accounts, in batches of
    _UPSERT_BATCH_SIZE (one round trip + one commit per batch — large EOD
    exports can be 100k+ rows, and per-row commits would take hours).

    Returns (rows_upserted, rows_skipped_due_to_error).
    """
    upserted = errors = 0
    # The FlexCube export has a stray blank line before the real header row
    # (and a UTF-8 BOM on the header itself) — strip both, else DictReader
    # treats the blank line as the header and every row lands under the
    # None restkey instead of its real column names.
    csv_text = csv_text.lstrip("﻿\r\n \t")
    reader = csv.DictReader(io.StringIO(csv_text))
    batch: list = []

    def flush():
        nonlocal upserted, errors
        if not batch:
            return
        ok, err = _upsert_batch(batch)
        upserted += ok
        errors += err
        batch.clear()

    for row in reader:
        acct = row.get("CUST_AC_NO", "").strip()
        if not acct:
            errors += 1
            continue
        try:
            batch.append(_row_to_record(row, customer_type))
        except Exception as exc:
            logger.warning("cbs_etl: map failed for %s: %s", acct, exc)
            errors += 1
            continue
        if len(batch) >= _UPSERT_BATCH_SIZE:
            flush()
            logger.info("cbs_etl: %s — %d upserted so far", customer_type, upserted)
    flush()
    return upserted, errors


# ── Main entry ────────────────────────────────────────────────────────────

def run_etl(
    trigger: bool = True,
    dt: Optional[datetime] = None,
) -> dict:
    """
    Full ETL run: trigger → download CORP + INDI → upsert → log.

    Args:
        trigger: whether to GET /command/export:customers first
        dt:      override the month used for filenames (default: now)

    Returns a stats dict consumed by the API endpoint and cron script.
    """
    if not _db().is_postgres_ready():
        return {"status": "error", "message": "Postgres not available",
                "corp_rows": 0, "indi_rows": 0, "errors": 0}

    ensure_tables()
    corp_upserted = indi_upserted = total_errors = 0

    try:
        if trigger:
            trigger_export()
            # No sleep needed — trigger_export() is synchronous; CSVs are
            # ready the moment it returns "done".
    except EtlDownloadError as exc:
        # Trigger failure is non-fatal — CSV may already be present from nightly run
        logger.warning("cbs_etl: trigger failed (continuing with existing file): %s", exc)

    errors: list[str] = []

    for ctype in ("CORP", "INDI"):
        try:
            text = download_csv(ctype, dt)
            upserted, errs = parse_and_upsert(text, ctype)
            total_errors += errs
            if ctype == "CORP":
                corp_upserted = upserted
            else:
                indi_upserted = upserted
            logger.info("cbs_etl: %s — upserted=%d errors=%d", ctype, upserted, errs)
        except EtlDownloadError as exc:
            errors.append(str(exc))
            logger.error("cbs_etl: %s download failed: %s", ctype, exc)

    status = "ok" if not errors else ("partial" if (corp_upserted + indi_upserted) > 0 else "error")
    message = "; ".join(errors) if errors else ""

    _log_run(corp_upserted, indi_upserted, total_errors, status, message)

    return {
        "status":        status,
        "corp_upserted": corp_upserted,
        "indi_upserted": indi_upserted,
        "total_upserted": corp_upserted + indi_upserted,
        "errors":        total_errors,
        "message":       message,
        "month":         _month_suffix(dt or datetime.now(timezone.utc)),
    }


def etl_status() -> dict:
    """Last ETL run stats + total account count in DB."""
    if not _db().is_postgres_ready():
        return {"available": False, "reason": "Postgres not configured"}
    try:
        ensure_tables()
        total = _db().fetch_scalar("SELECT COUNT(*) FROM cbs_accounts") or 0
        corp  = _db().fetch_scalar("SELECT COUNT(*) FROM cbs_accounts WHERE customer_type = 'CORP'") or 0
        indi  = _db().fetch_scalar("SELECT COUNT(*) FROM cbs_accounts WHERE customer_type = 'INDI'") or 0
        last  = _db().fetch_one(
            "SELECT started_at, finished_at, total_upserted, errors, status, message "
            "FROM cbs_etl_log ORDER BY id DESC LIMIT 1"
        )
        configured = bool(os.getenv("FLEXCUBE_EOD_BASE_URL", "").strip())
        return {
            "available":        True,
            "configured":       configured,
            "total_accounts":   int(total),
            "corp_accounts":    int(corp),
            "indi_accounts":    int(indi),
            "last_run":         {k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                 for k, v in (last or {}).items()},
        }
    except Exception as exc:
        return {"available": False, "reason": str(exc)}
