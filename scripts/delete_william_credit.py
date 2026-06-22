#!/usr/bin/env python3
"""
delete_william_credit.py — remove William Mwanake's (MD, code 300001) watchlist
credit rows. The MD should not own a distressed-credit book; earlier cleanup
hard-protected 300001 from the role-based delete, so his rows survived and the
name-resync stamped his real name onto them. This removes just those rows.

His login / users.json record / staff register entry are untouched — only
watchlist credit-account rows owned by 300001 are deleted.

SAFE: dry-run unless --apply. Backs up the table before deleting.

    python scripts\\delete_william_credit.py            # dry-run
    python scripts\\delete_william_credit.py --apply    # backup + delete
"""
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WILLIAM = "300001"


def main():
    apply = "--apply" in sys.argv
    from utils.db import db

    rows = db.fetch_all(
        "SELECT id, rm_name, branch_name, outstanding FROM watchlist "
        "WHERE rm_code = %s", (WILLIAM,))
    total = db.fetch_one("SELECT COUNT(*) AS n FROM watchlist", ())
    print(f"watchlist total rows: {total['n']}")
    print(f"rows owned by William ({WILLIAM}): {len(rows)}")
    if rows:
        out = sum(float(r.get("outstanding") or 0) for r in rows)
        branches = sorted({str(r.get("branch_name")) for r in rows})
        print(f"  rm_name on those rows: {rows[0].get('rm_name')}")
        print(f"  branches: {branches}")
        print(f"  total outstanding removed: {out:,.2f}")

    if not rows:
        print("\nNothing to delete.")
        return
    if not apply:
        print("\n[DRY-RUN] No DB change. Re-run with --apply to back up + delete.")
        return

    full = db.fetch_all("SELECT * FROM watchlist", ())
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_DIR / f"watchlist_db_table.pre_william_{ts}.json"
    backup.write_text(json.dumps(full, default=str, indent=2), encoding="utf-8")
    print(f"\n[backup] {len(full)} rows -> {backup.name}")

    ids = [r["id"] for r in rows]
    with db.transaction() as conn:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            ph = ",".join(["%s"] * len(chunk))
            db.execute(f"DELETE FROM watchlist WHERE id IN ({ph})", tuple(chunk), conn=conn)

    after = db.fetch_one("SELECT COUNT(*) AS n FROM watchlist", ())
    print(f"[apply] deleted {len(ids)} William rows. watchlist now: {after['n']} rows.")
    print("Restart API + run harness — every credit account now owned by a real, non-exec RM.")


if __name__ == "__main__":
    main()
