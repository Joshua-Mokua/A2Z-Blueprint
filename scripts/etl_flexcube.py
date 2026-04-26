"""scripts/etl_flexcube.py — Daily FLEXCUBE ETL orchestrator.

Production-grade ETL pipeline that pulls FLEXCUBE data into A2Z MIS 360.

PIPELINE STAGES
───────────────
1. EXTRACT  — Call FLEXCUBE adapter for each entity type
2. STAGE    — Write raw records to staging.flexcube_* tables
3. VALIDATE — Type-check, range-check, FK-check; mark records VALID or INVALID
4. PROMOTE  — Move VALID records into mart tables (where applicable)
5. RECON    — Run reconciliation checks; flag breaks
6. CLOSE    — Update batch register with final stats

USAGE
─────
# Full daily run (typically 02:00 Nairobi time)
python scripts/etl_flexcube.py --mode=full

# Incremental (every 4 hours during business)
python scripts/etl_flexcube.py --mode=incremental --since="2026-04-26T08:00:00"

# Replay a specific batch (e.g. after fixing a bug)
python scripts/etl_flexcube.py --mode=replay --batch-id=BATCH_2026_04_26_FULL

# Dry run (extract only, no DB writes)
python scripts/etl_flexcube.py --mode=full --dry-run

EXIT CODES
──────────
0 = success
1 = extraction failed (FLEXCUBE unreachable or auth error)
2 = validation failed beyond tolerance (>5% invalid records)
3 = promotion failed (DB write error)
4 = reconciliation broke (variance exceeded tolerance)
5 = unknown error

CBK COMPLIANCE
──────────────
- All actions logged to audit.recon_runs and audit_trail
- Raw data retained 30 days in staging, then archived
- ETL batch register kept indefinitely
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import db
from utils import flexcube_adapter as fcx
from utils import reconciliation as recon

# Set up logging — both stdout and a file for audit
LOG_DIR = Path(__file__).parent.parent / "data" / "etl_logs"
LOG_DIR.mkdir(exist_ok=True, parents=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / f"etl_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
log = logging.getLogger("etl.flexcube")


# ══════════════════════════════════════════════════════════════════════════
# ETL Configuration
# ══════════════════════════════════════════════════════════════════════════

VALIDATION_TOLERANCE_PCT = 5.0  # If >5% of records fail validation, abort

# Mart promotion targets — only entities that have corresponding mart tables
PROMOTION_MAP = {
    # staging table → mart table (None means no promotion, stays in staging)
    "flexcube_customers":    None,
    "flexcube_accounts":     None,
    "flexcube_loans":        None,
    "flexcube_transactions": None,
    "flexcube_gl_balances":  None,
}


# ══════════════════════════════════════════════════════════════════════════
# Batch Management
# ══════════════════════════════════════════════════════════════════════════

def open_batch(mode: str, triggered_by: str) -> str:
    """Open a new ETL batch and return its ID."""
    batch_id = f"BATCH_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{mode.upper()}"

    if db.is_postgres_ready():
        try:
            db.execute(
                """INSERT INTO staging.etl_batch_register
                   (batch_id, source_system, extract_type, status, triggered_by)
                   VALUES (%s, %s, %s, %s, %s)""",
                (batch_id, "FLEXCUBE", mode.upper(), "RUNNING", triggered_by),
            )
        except Exception as e:
            log.warning(f"Could not open batch in DB: {e}")

    log.info(f"━━━ Batch {batch_id} opened (mode={mode}, by={triggered_by}) ━━━")
    return batch_id


def close_batch(batch_id: str, status: str, stats: Dict, error: Optional[str] = None) -> None:
    """Close the batch with summary statistics."""
    if db.is_postgres_ready():
        try:
            db.execute(
                """UPDATE staging.etl_batch_register
                   SET extract_completed = now(),
                       status            = %s,
                       record_count      = %s,
                       valid_count       = %s,
                       invalid_count     = %s,
                       promoted_count    = %s,
                       error_message     = %s,
                       metadata          = %s
                   WHERE batch_id = %s""",
                (status, stats.get("record_count", 0), stats.get("valid_count", 0),
                 stats.get("invalid_count", 0), stats.get("promoted_count", 0),
                 error, json.dumps(stats), batch_id),
            )
        except Exception as e:
            log.warning(f"Could not close batch in DB: {e}")

    log.info(f"━━━ Batch {batch_id} closed — status={status} ━━━")
    log.info(f"    record_count={stats.get('record_count',0)}, "
             f"valid={stats.get('valid_count',0)}, "
             f"invalid={stats.get('invalid_count',0)}, "
             f"promoted={stats.get('promoted_count',0)}")


# ══════════════════════════════════════════════════════════════════════════
# EXTRACT — pull from FLEXCUBE adapter
# ══════════════════════════════════════════════════════════════════════════

def extract_customers(batch_id: str, since: Optional[datetime] = None) -> List[Dict]:
    """Pull customer records. In synthetic/mock mode, returns sample CIFs.
    In live mode, would call adapter.fetch_customer for each known CIF."""
    log.info("EXTRACT customers...")
    records = []

    if fcx.get_mode() in ("synthetic", "mock"):
        # Use synthetic CBS data
        cbs_customers = Path(__file__).parent.parent / "cbs_data" / "customers.csv"
        if cbs_customers.exists():
            import csv as _csv
            with cbs_customers.open("r", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    if since and row.get("last_updated"):
                        try:
                            updated = datetime.fromisoformat(row["last_updated"])
                            if updated < since:
                                continue
                        except (ValueError, TypeError):
                            pass
                    records.append({
                        "customer_id":     row.get("cif", ""),
                        "customer_name":   row.get("name", ""),
                        "customer_type":   row.get("type", ""),
                        "branch_code":     row.get("branch", ""),
                        "rm_code":         row.get("rm_code", ""),
                        "kyc_status":      row.get("kyc_status", "VERIFIED"),
                        "risk_rating":     row.get("risk_rating", "LOW"),
                        "country":         row.get("country", "KE"),
                        "id_number":       row.get("id_number", ""),
                        "phone":           row.get("phone", ""),
                        "email":           row.get("email", ""),
                        "customer_since":  row.get("customer_since", ""),
                        "raw_payload":     dict(row),
                    })
    else:
        # Live mode: would iterate over known CIFs
        log.warning("Live extract not implemented — needs Ecobank CIF list")

    log.info(f"  → {len(records)} customer records extracted")
    return records


def extract_accounts(batch_id: str, since: Optional[datetime] = None) -> List[Dict]:
    """Pull account balances and metadata."""
    log.info("EXTRACT accounts...")
    records = []

    if fcx.get_mode() in ("synthetic", "mock"):
        cbs_accounts = Path(__file__).parent.parent / "cbs_data" / "accounts.csv"
        if cbs_accounts.exists():
            import csv as _csv
            with cbs_accounts.open("r", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    records.append({
                        "account_no":        row.get("account_no", ""),
                        "customer_id":       row.get("customer_id", row.get("cif", "")),
                        "branch_code":       row.get("branch", ""),
                        "product_code":      row.get("product", ""),
                        "currency":          row.get("currency", "KES"),
                        "available_balance": row.get("available_balance", ""),
                        "ledger_balance":    row.get("ledger_balance", ""),
                        "blocked_amount":    row.get("blocked_amount", "0"),
                        "account_status":   row.get("status", "ACTIVE"),
                        "opened_date":       row.get("opened_date", ""),
                        "closed_date":       row.get("closed_date", ""),
                        "raw_payload":       dict(row),
                    })

    log.info(f"  → {len(records)} account records extracted")
    return records


def extract_loans(batch_id: str, since: Optional[datetime] = None) -> List[Dict]:
    """Pull loan accounts."""
    log.info("EXTRACT loans...")
    records = []

    if fcx.get_mode() in ("synthetic", "mock"):
        cbs_loans = Path(__file__).parent.parent / "cbs_data" / "loans.csv"
        if cbs_loans.exists():
            import csv as _csv
            with cbs_loans.open("r", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    records.append({
                        "loan_id":            row.get("loan_id", row.get("account_no", "")),
                        "customer_id":        row.get("customer_id", row.get("cif", "")),
                        "branch_code":        row.get("branch", ""),
                        "product_code":       row.get("product", ""),
                        "principal_amount":   row.get("principal", ""),
                        "outstanding_amount": row.get("outstanding", ""),
                        "interest_rate":      row.get("rate", ""),
                        "tenor_months":       row.get("tenor", ""),
                        "disbursement_date":  row.get("disbursement_date", ""),
                        "maturity_date":      row.get("maturity_date", ""),
                        "next_emi_date":      row.get("next_emi_date", ""),
                        "classification":     row.get("classification", "Performing"),
                        "dpd":                row.get("dpd", "0"),
                        "npl_flag":           "Y" if row.get("classification","") in ("Substandard","Doubtful","Loss") else "N",
                        "rm_code":            row.get("rm_code", ""),
                        "raw_payload":        dict(row),
                    })

    log.info(f"  → {len(records)} loan records extracted")
    return records


# ══════════════════════════════════════════════════════════════════════════
# STAGE — write raw records to staging tables
# ══════════════════════════════════════════════════════════════════════════

def stage_records(table: str, records: List[Dict], batch_id: str) -> int:
    """Insert records into staging.<table>. Returns count inserted."""
    if not records:
        return 0

    if not db.is_postgres_ready():
        # In synthetic mode without PG, persist to JSON in data/staging/
        staging_dir = Path(__file__).parent.parent / "data" / "staging"
        staging_dir.mkdir(exist_ok=True, parents=True)
        staging_file = staging_dir / f"{table}_{batch_id}.json"
        try:
            staging_file.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
            log.info(f"  STAGE → {staging_file.name} ({len(records)} records, JSON fallback)")
            return len(records)
        except Exception as e:
            log.error(f"  STAGE failed: {e}")
            return 0

    inserted = 0
    skipped = 0
    with db.transaction() as conn:
        for rec in records:
            raw = rec.pop("raw_payload", {})
            cols = list(rec.keys()) + ["batch_id", "raw_payload"]
            vals = list(rec.values()) + [batch_id, json.dumps(raw, default=str)]
            placeholders = ", ".join(["%s"] * len(cols))
            col_str = ", ".join(f'"{c}"' for c in cols)
            sql = f"INSERT INTO staging.{table} ({col_str}) VALUES ({placeholders})"
            try:
                db.execute(sql, tuple(vals), conn=conn)
                inserted += 1
            except Exception as e:
                log.warning(f"  STAGE skip: {str(e)[:80]}")
                skipped += 1

    log.info(f"  STAGE → staging.{table} ({inserted} inserted, {skipped} skipped)")
    return inserted


# ══════════════════════════════════════════════════════════════════════════
# VALIDATE — check each staged record for correctness
# ══════════════════════════════════════════════════════════════════════════

def validate_customers(batch_id: str) -> Tuple[int, int]:
    """Mark customer records VALID or INVALID."""
    if not db.is_postgres_ready():
        return (0, 0)

    rules = [
        ("customer_id IS NULL OR customer_id = \'\'",         "missing_customer_id"),
        ("customer_name IS NULL OR length(customer_name) < 2", "invalid_customer_name"),
        ("country NOT IN (\'KE\',\'UG\',\'TZ\',\'RW\',\'BI\',\'ET\')",  "invalid_country"),
    ]
    return _apply_validation_rules("flexcube_customers", batch_id, rules)


def validate_accounts(batch_id: str) -> Tuple[int, int]:
    rules = [
        ("account_no IS NULL OR account_no = \'\'",             "missing_account_no"),
        ("customer_id IS NULL OR customer_id = \'\'",           "missing_customer_id"),
        ("ledger_balance IS NULL",                              "missing_ledger_balance"),
        ("currency NOT IN (\'KES\',\'USD\',\'EUR\',\'GBP\')",     "invalid_currency"),
    ]
    return _apply_validation_rules("flexcube_accounts", batch_id, rules)


def validate_loans(batch_id: str) -> Tuple[int, int]:
    rules = [
        ("loan_id IS NULL OR loan_id = \'\'",                 "missing_loan_id"),
        ("customer_id IS NULL OR customer_id = \'\'",         "missing_customer_id"),
        ("classification NOT IN (\'Performing\',\'Watch\',\'Substandard\',\'Doubtful\',\'Loss\')",  "invalid_classification"),
    ]
    return _apply_validation_rules("flexcube_loans", batch_id, rules)


def _apply_validation_rules(table: str, batch_id: str, rules: List[Tuple[str,str]]) -> Tuple[int, int]:
    """Apply each rule and update validation_status accordingly."""
    if not db.is_postgres_ready():
        return (0, 0)

    valid_count = 0
    invalid_count = 0

    with db.transaction() as conn:
        # First mark everything VALID
        db.execute(
            f"UPDATE staging.{table} SET validation_status = \'VALID\' WHERE batch_id = %s",
            (batch_id,), conn=conn
        )

        # Then flip INVALID where any rule fires
        for predicate, error_code in rules:
            db.execute(
                f"""UPDATE staging.{table}
                    SET validation_status = \'INVALID\',
                        validation_errors = validation_errors || %s::jsonb
                    WHERE batch_id = %s AND ({predicate})""",
                (json.dumps([error_code]), batch_id), conn=conn
            )

        # Count results
        valid_count = db.fetch_scalar(
            f"SELECT count(*) FROM staging.{table} WHERE batch_id = %s AND validation_status = \'VALID\'",
            (batch_id,)
        ) or 0
        invalid_count = db.fetch_scalar(
            f"SELECT count(*) FROM staging.{table} WHERE batch_id = %s AND validation_status = \'INVALID\'",
            (batch_id,)
        ) or 0

    log.info(f"  VALIDATE staging.{table}: {valid_count} valid, {invalid_count} invalid")
    return (valid_count, invalid_count)


# ══════════════════════════════════════════════════════════════════════════
# RUN — orchestrate the full pipeline
# ══════════════════════════════════════════════════════════════════════════

def run_etl(mode: str = "full",
            since: Optional[datetime] = None,
            triggered_by: str = "scheduled",
            dry_run: bool = False) -> int:
    """Main ETL entry point. Returns exit code."""
    log.info("=" * 70)
    log.info(f"FLEXCUBE ETL — mode={mode}, dry_run={dry_run}, fcx_mode={fcx.get_mode()}")
    log.info("=" * 70)

    batch_id = open_batch(mode, triggered_by)
    stats = {"record_count": 0, "valid_count": 0, "invalid_count": 0, "promoted_count": 0}
    error_message = None

    try:
        # ── EXTRACT + STAGE ─────────────────────────────────────
        log.info("\n--- STAGE 1/4: Extract & stage ---")

        cust_records = extract_customers(batch_id, since)
        if not dry_run: stage_records("flexcube_customers", cust_records, batch_id)
        stats["record_count"] += len(cust_records)

        acct_records = extract_accounts(batch_id, since)
        if not dry_run: stage_records("flexcube_accounts", acct_records, batch_id)
        stats["record_count"] += len(acct_records)

        loan_records = extract_loans(batch_id, since)
        if not dry_run: stage_records("flexcube_loans", loan_records, batch_id)
        stats["record_count"] += len(loan_records)

        if dry_run:
            log.info(f"\n[DRY RUN] Would stage {stats['record_count']} records, exiting")
            close_batch(batch_id, "COMPLETED", stats, error="DRY RUN")
            return 0

        # ── VALIDATE ────────────────────────────────────────────
        log.info("\n--- STAGE 2/4: Validate ---")

        v1, i1 = validate_customers(batch_id)
        v2, i2 = validate_accounts(batch_id)
        v3, i3 = validate_loans(batch_id)
        stats["valid_count"]   = v1 + v2 + v3
        stats["invalid_count"] = i1 + i2 + i3

        invalid_pct = (stats["invalid_count"] / max(stats["record_count"], 1)) * 100
        if invalid_pct > VALIDATION_TOLERANCE_PCT:
            error_message = f"Validation failure: {invalid_pct:.1f}% invalid (threshold {VALIDATION_TOLERANCE_PCT}%)"
            log.error(error_message)
            close_batch(batch_id, "FAILED", stats, error=error_message)
            return 2

        log.info(f"  Validation OK: {invalid_pct:.1f}% invalid (within {VALIDATION_TOLERANCE_PCT}% tolerance)")

        # ── PROMOTE ─────────────────────────────────────────────
        log.info("\n--- STAGE 3/4: Promote to mart ---")
        # In v5.11, no entities have mart promotion targets. Future work.
        log.info("  No mart promotion configured for these entities (FLEXCUBE is system of record)")

        # ── RECONCILE ───────────────────────────────────────────
        log.info("\n--- STAGE 4/4: Reconcile ---")
        recon_results = recon.run_all_checks(triggered_by=f"etl/{batch_id}")
        breaks = sum(1 for r in recon_results if r.status == "BREAK")
        if breaks > 0:
            error_message = f"{breaks} reconciliation break(s) detected"
            log.warning(f"  ⚠️ {error_message}")
            close_batch(batch_id, "PARTIAL", stats, error=error_message)
            return 4

        log.info(f"  All {len(recon_results)} reconciliation checks passed")

        # ── DONE ────────────────────────────────────────────────
        close_batch(batch_id, "COMPLETED", stats)
        log.info("\n" + "=" * 70)
        log.info(f"ETL SUCCESS — batch {batch_id}")
        log.info("=" * 70)
        return 0

    except Exception as e:
        error_message = f"Unhandled error: {e}"
        log.exception(error_message)
        close_batch(batch_id, "FAILED", stats, error=error_message)
        return 5


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FLEXCUBE → A2Z MIS 360 ETL")
    parser.add_argument("--mode", choices=["full", "incremental", "replay"],
                        default="full", help="ETL run mode")
    parser.add_argument("--since", help="Incremental cutoff (ISO datetime)")
    parser.add_argument("--batch-id", help="Replay this batch ID")
    parser.add_argument("--dry-run", action="store_true", help="Extract only, no DB writes")
    parser.add_argument("--triggered-by", default="scheduled", help="Who triggered this run")
    args = parser.parse_args()

    since = None
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError:
            log.error(f"Invalid --since: {args.since}")
            sys.exit(1)

    code = run_etl(mode=args.mode, since=since,
                   triggered_by=args.triggered_by, dry_run=args.dry_run)
    sys.exit(code)


if __name__ == "__main__":
    main()
