"""
v10.354 — One-shot script that snapshots CBS state as the YoY baseline.

Run from project root:
  python scripts/snapshot_cbs_baseline.py           # snapshot at today's date
  python scripts/snapshot_cbs_baseline.py 2025-12-31  # snapshot at a specific date

The baseline is written to data/cbs_baseline_<YYYY>_<MMM>_<DD>.json and is
read by utils.cbs_baseline.load_baseline() during YoY comparisons.

Re-running with the SAME date overwrites that snapshot (idempotent if CBS
state hasn't changed). Different dates produce separate files; load_baseline()
defaults to the most recent.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


def main(argv: list[str]) -> int:
    # sys.path setup so this can run from any cwd
    repo = Path(__file__).resolve().parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    from utils.cbs_baseline import snapshot_baseline, save_baseline, baseline_file_for

    if len(argv) > 1:
        try:
            as_of = date.fromisoformat(argv[1])
        except ValueError as exc:
            print(f"Invalid date '{argv[1]}': {exc}")
            print("Use ISO format: YYYY-MM-DD")
            return 2
    else:
        as_of = date.today()

    print(f"Snapshotting CBS baseline as of {as_of.isoformat()}...")
    baseline = snapshot_baseline(as_of_date=as_of)

    out_path = save_baseline(baseline)
    print(f"\n  Wrote: {out_path}")
    summary = baseline.get("summary", {})
    print(f"  RM count:       {summary.get('rm_count', 0):,}")
    print(f"  Branch count:   {summary.get('branch_count', 0):,}")
    print(f"  Source files:   {summary.get('source_count', 0)}")
    print(f"  Account-level:  {summary.get('has_account_level_data', False)}")

    if not summary.get("has_account_level_data"):
        print(
            "\n  Note: accounts.csv not found in CBS dir. Baseline captured "
            "bank-level aggregates only. Per-RM and per-branch sections are "
            "empty. This is expected in sandbox/partial-data environments "
            "and will populate fully when accounts.csv is generated."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
