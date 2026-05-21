"""scripts/generate_teller_activity.py — CLI for v10.317 Teller
activity generator.

Usage:
    # Generate one quarter
    python scripts/generate_teller_activity.py --period 2026-Q2

    # Generate the full demo history (2025-Q3 through 2026-Q2)
    python scripts/generate_teller_activity.py --history

    # Preview without submitting
    python scripts/generate_teller_activity.py --period 2026-Q2 --dry-run

    # Coverage report
    python scripts/generate_teller_activity.py --report --period 2026-Q1
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.teller_activity_generator import (
    coverage_report,
    generate_history,
    generate_quarter,
    load_generator_config,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate simulated Teller BSC activity")
    parser.add_argument(
        "--period",
        help="Period to generate (e.g. 2026-Q2)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Generate all standard quarters "
              "(2025-Q3 through 2026-Q2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute values but don't submit",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print coverage report without generating",
    )
    args = parser.parse_args()

    cfg = load_generator_config()
    print(f"v10.317 Teller activity generator "
           f"(schema {cfg.schema_version})")
    print(f"  Bands: {len(cfg.bands)}, KPIs: "
           f"{len(cfg.kpi_targets)}")

    if args.report:
        period = args.period or "2026-Q1"
        r = coverage_report(period, cfg)
        print(f"\nCoverage report for {period}:")
        print(f"  Tellers: {r['tellers_count']}")
        print(f"  KPIs per Teller: {r['kpis_per_teller']}")
        print(f"  Total submissions expected: "
               f"{r['total_submissions_expected']}")
        print(f"  Band distribution:")
        for b, c in r["band_distribution"].items():
            print(f"    {b}: {c}")
        print(f"  KPI value ranges (sample 20):")
        for kpi, vals in r["kpi_value_samples"].items():
            if not vals:
                continue
            mn, mx = min(vals), max(vals)
            mean = sum(vals) / len(vals)
            print(f"    {kpi:<25s}  min={mn:.2f}, "
                   f"max={mx:.2f}, mean={mean:.2f}")
        return 0

    if args.history:
        t0 = time.time()
        results = generate_history(dry_run=args.dry_run)
        elapsed = time.time() - t0
        print(f"\nHistory generation complete in {elapsed:.1f}s "
               f"(dry_run={args.dry_run}):")
        total_sub = total_fail = 0
        for period, r in results.items():
            print(f"  {period}: {r.kpis_submitted} submitted, "
                   f"{r.submit_failures} failures")
            total_sub += r.kpis_submitted
            total_fail += r.submit_failures
        print(f"  TOTAL: {total_sub} submissions, "
               f"{total_fail} failures")
        return 0 if total_fail == 0 else 1

    if args.period:
        t0 = time.time()
        r = generate_quarter(args.period, dry_run=args.dry_run)
        elapsed = time.time() - t0
        print(f"\n{args.period} generation in {elapsed:.1f}s "
               f"(dry_run={args.dry_run}):")
        print(f"  Tellers: {r.tellers_processed}")
        print(f"  Submitted: {r.kpis_submitted}")
        print(f"  Skipped: {r.kpis_skipped}")
        print(f"  Failures: {r.submit_failures}")
        if r.errors:
            print(f"  Errors (first 5):")
            for code, kpi, reason in r.errors[:5]:
                print(f"    {code}/{kpi}: {reason}")
        return 0 if r.submit_failures == 0 else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
