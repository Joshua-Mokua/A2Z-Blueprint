#!/usr/bin/env python3
"""
CBS nightly ETL + cache refresh cron script.

Primary job: download CORP + INDI EOD CSVs from FlexCube and upsert into
cbs_accounts (Postgres). Secondary: refresh any on-demand cache rows that
went stale since the last run.

Crontab on the VM:
  # Full ETL nightly at 01:00 (after EOD export generates)
  0 1 * * * cd /var/www/a2z-blueprint/A2Z-Blueprint && \
    set -a && source .env && set +a && \
    venv/bin/python scripts/refresh_cbs_cache.py \
    >> /var/log/a2z/cbs_etl.log 2>&1

  # Or skip trigger if server auto-generates CSVs at midnight:
  0 1 * * * ... refresh_cbs_cache.py --no-trigger

Required env:
  FLEXCUBE_EOD_BASE_URL   e.g. http://10.8.32.3:400
  A2Z_USE_DB=true  +  A2Z_DB_* connection vars

Usage:
  python scripts/refresh_cbs_cache.py               # full ETL + cache refresh
  python scripts/refresh_cbs_cache.py --no-trigger  # skip POST, just download
  python scripts/refresh_cbs_cache.py --status       # print stats and exit
  python scripts/refresh_cbs_cache.py --cache-only  # only refresh stale cache rows
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-trigger",  action="store_true", help="Skip POST /command/export:customers")
    p.add_argument("--status",      action="store_true", help="Print ETL + cache stats and exit")
    p.add_argument("--cache-only",  action="store_true", help="Only refresh stale on-demand cache rows")
    p.add_argument("--cache-limit", type=int, default=200, help="Max stale cache rows to refresh")
    args = p.parse_args()

    if args.status:
        from utils.cbs_etl import etl_status
        from utils.cbs_cache import cache_stats
        print(json.dumps({"etl": etl_status(), "cache": cache_stats()}, indent=2, default=str))
        return

    if args.cache_only:
        from utils.cbs_cache import refresh_stale_accounts
        result = refresh_stale_accounts(limit=args.cache_limit)
        print(json.dumps(result, indent=2, default=str))
        return

    # Full ETL
    from utils.cbs_etl import run_etl
    print("[cbs_etl] Starting EOD import ...")
    result = run_etl(trigger=not args.no_trigger)
    print(json.dumps(result, indent=2, default=str))

    # Also refresh any leftover stale on-demand cache entries
    from utils.cbs_cache import refresh_stale_accounts
    cache_result = refresh_stale_accounts(limit=args.cache_limit)
    print(json.dumps({"cache_refresh": cache_result}, indent=2, default=str))

    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
