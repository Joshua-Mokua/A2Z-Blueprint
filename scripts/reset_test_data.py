"""scripts/reset_test_data.py — wipe pipeline + credit/LMS + cascaded targets
for a fresh end-to-end test, keeping staff + config + BSC baseline.

Backs up every file and the Postgres table BEFORE mutating
(backup-before-mutation). DRY-RUN by default; pass --confirm to execute.

WIPES:
  data/pipeline.json          -> []   (+ Postgres pipeline_deals truncated)
  data/loan_applications.json -> []
  data/credit_admin.json      -> []
  data/credit_monitoring.json -> watchlist emptied
  data/target_cascade.json    -> {}   (cascaded targets)
  data/bank_targets.json      -> {}   (ONLY with --include-bank-targets)

KEEPS (never touched): staff_register.xlsx, org_config.json,
  pipeline_settings.json, lms_config.json, all *_config.json, kpi_library.json,
  users.json, BSC actuals/scores, EDMS.

USAGE (project root, venv active):
  python scripts/reset_test_data.py                         # dry-run
  python scripts/reset_test_data.py --confirm               # execute
  python scripts/reset_test_data.py --confirm --include-bank-targets
"""
from __future__ import annotations
import argparse, json, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))  # so `from utils.db import db` works under `python scripts/...`

EMPTY_LIST = lambda d: []
EMPTY_DICT = lambda d: {}
def _empty_monitoring(d):
    out = dict(d) if isinstance(d, dict) else {}
    out["watchlist"] = []
    out["last_updated"] = datetime.now().isoformat()
    return out

WIPE = [
    ("pipeline_deals.json", EMPTY_LIST),       # canonical PipelineManager store
    ("pipeline_activities.json", EMPTY_LIST),   # deal activity log (same manager)
    ("pipeline.json", EMPTY_LIST),              # legacy store (defensive; skipped if absent)
    ("loan_applications.json", EMPTY_LIST),
    ("credit_admin.json", EMPTY_LIST),
    ("credit_monitoring.json", _empty_monitoring),
    ("target_cascade.json", EMPTY_DICT),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="actually wipe (else dry-run)")
    ap.add_argument("--include-bank-targets", action="store_true",
                    help="also wipe bank_targets.json (fully fresh cascade)")
    args = ap.parse_args()

    wipe = list(WIPE)
    if args.include_bank_targets:
        wipe.append(("bank_targets.json", EMPTY_DICT))

    mode = "EXECUTING" if args.confirm else "DRY RUN"
    print(f"=== Data reset ({mode}) ===")

    for fname, _ in wipe:
        p = DATA / fname
        if not p.exists():
            print(f"  SKIP {fname} (missing)"); continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            n = len(d) if hasattr(d, "__len__") else 0
            print(f"  {fname}: {n} entries -> emptied")
        except Exception as e:
            print(f"  {fname}: ERROR reading ({e})")

    try:
        from utils.db import db as _db
        if _db.is_postgres_ready():
            rows = _db.fetch_all("SELECT COUNT(*) AS n FROM pipeline_deals")
            n = (rows[0].get("n") if rows else 0) or 0
            print(f"  Postgres pipeline_deals: {n} rows -> truncated")
        else:
            print("  Postgres: not ready -> pipeline_deals NOT truncated")
    except Exception as e:
        print(f"  Postgres: unavailable ({e})")

    if not args.confirm:
        print("\nDRY RUN — nothing changed. Re-run with --confirm to execute.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = DATA / f"_reset_backup_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for fname, builder in wipe:
        p = DATA / fname
        if not p.exists():
            continue
        shutil.copy2(p, backup_dir / fname)               # backup first
        d = json.loads(p.read_text(encoding="utf-8"))
        p.write_text(json.dumps(builder(d), indent=2), encoding="utf-8")

    try:
        from utils.db import db as _db
        if _db.is_postgres_ready():
            rows = _db.fetch_all("SELECT * FROM pipeline_deals")
            (backup_dir / "pipeline_deals_postgres.json").write_text(
                json.dumps(rows, indent=2, default=str), encoding="utf-8")
            _db.execute("DELETE FROM pipeline_deals")
            print(f"  truncated pipeline_deals ({len(rows)} rows backed up)")
    except Exception as e:
        print(f"  Postgres truncate skipped: {e}")

    print(f"\nDONE. Backups: {backup_dir.relative_to(ROOT)}")
    print("Restart the API — pipeline / credit / cascade are now empty for fresh testing.")


if __name__ == "__main__":
    main()
