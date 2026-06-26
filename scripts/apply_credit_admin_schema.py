#!/usr/bin/env python3
"""
scripts/apply_credit_admin_schema.py  —  Batch CA-1, step 1 (CA-1b: parse fix).

Creates the credit_admin table + indexes in PostgreSQL (idempotent — uses
IF NOT EXISTS, safe to re-run). Additive only. Run from the repo root, venv active.

    python scripts\\apply_credit_admin_schema.py

CA-1b fix: full-line SQL comments are stripped BEFORE splitting on ';', so the
CREATE TABLE (which is preceded by a comment block) is no longer discarded.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
SQL_FILE = Path(__file__).resolve().parent.parent / "sql" / "create_credit_admin.sql"


def _statements(sql: str):
    # Drop full-line `--` comments first, THEN split. (The old version filtered
    # whole ;-chunks that *started* with '--', which silently ate the CREATE
    # TABLE because a comment block preceded it.)
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    clean = "\n".join(lines)
    return [s.strip() for s in clean.split(";") if s.strip()]


def main():
    try:
        from utils.db import db
    except Exception as e:
        print(f"!! cannot import utils.db: {e}")
        sys.exit(2)

    if not db.is_postgres_ready():
        print("!! Postgres is not ready (A2Z_USE_DB!=true or no pool in THIS shell). "
              "Run  python scripts\\storage_readiness_probe.py  to confirm, then retry.")
        sys.exit(2)

    statements = _statements(SQL_FILE.read_text(encoding="utf-8"))
    if not any(s.upper().startswith("CREATE TABLE") for s in statements):
        print("!! parse error: no CREATE TABLE found — aborting before indexes.")
        sys.exit(1)

    for stmt in statements:
        db.execute(stmt + ";")
        print(f"  [ok] {stmt.splitlines()[0][:70]}")

    exists = db.fetch_scalar("SELECT to_regclass('public.credit_admin') IS NOT NULL")
    print(f"\n  credit_admin table present: {exists}")
    if not exists:
        print("  !! table not found after apply — investigate (permissions?).")
        sys.exit(1)
    print("  CA-1 step 1 complete. Next: python scripts\\migrate_credit_admin_to_pg.py")


if __name__ == "__main__":
    main()
