#!/usr/bin/env python3
"""
CBS cache refresh cron script.

Runs the stale-account refresh job directly (no HTTP round-trip needed).
Designed to be called from crontab on the VM:

  # Re-fetch stale CBS accounts every hour
  0 * * * * /var/www/a2z-blueprint/A2Z-Blueprint/venv/bin/python \
      /var/www/a2z-blueprint/A2Z-Blueprint/scripts/refresh_cbs_cache.py \
      >> /var/log/a2z/cbs_cache_refresh.log 2>&1

  # Or mark all stale at midnight, then let the 1am run do a full refresh:
  0  0 * * * ... refresh_cbs_cache.py --mark-stale
  0  1 * * * ... refresh_cbs_cache.py --limit 2000

Environment variables (same as the main app — source .env before running):
  FLEXCUBE_SCRIPTS_URL   — required for live refresh
  CBS_CACHE_TTL_HOURS    — rows older than this are auto-marked stale (default 24)
  A2Z_USE_DB             — must be 'true' for Postgres cache to be active
  A2Z_DB_HOST / _PORT / _NAME / _USER / _PASSWORD — Postgres connection

Usage:
  python scripts/refresh_cbs_cache.py                  # refresh up to 200 stale rows
  python scripts/refresh_cbs_cache.py --limit 500      # larger batch
  python scripts/refresh_cbs_cache.py --mark-stale     # mark all stale, no refresh
  python scripts/refresh_cbs_cache.py --status         # print cache stats and exit
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from the repo root or from scripts/
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))


def main():
    parser = argparse.ArgumentParser(description="Refresh CBS account cache from FlexCube")
    parser.add_argument("--limit",      type=int, default=200, help="Max accounts to refresh (default 200)")
    parser.add_argument("--mark-stale", action="store_true",   help="Mark all cached accounts as stale without refreshing")
    parser.add_argument("--status",     action="store_true",   help="Print cache stats and exit")
    args = parser.parse_args()

    from utils.cbs_cache import cache_stats, mark_all_stale, refresh_stale_accounts, ensure_table

    ensure_table()

    if args.status:
        stats = cache_stats()
        print(json.dumps(stats, indent=2, default=str))
        return

    if args.mark_stale:
        count = mark_all_stale()
        print(f"[cbs_cache] Marked {count} accounts as stale.")
        return

    print(f"[cbs_cache] Starting refresh (limit={args.limit}) ...")
    result = refresh_stale_accounts(limit=args.limit)
    print(json.dumps(result, indent=2, default=str))

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
