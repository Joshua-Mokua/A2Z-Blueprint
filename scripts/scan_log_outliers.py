#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Find implausible values already in the daily-log store — READ ONLY.

Bounds now reject bad entries at submit, but records written before that are
still there, and they distort everything downstream: two rows in the live data
made one activity look responsible for 99% of the bank's index, and produced a
carried-forward balance of 1.5 million for one person.

This lists every breach so you can decide what to do with each — the script
never edits anything. Fixing them is a judgement call per row: a KES figure
typed into a count box should be zeroed or moved; a genuine outlier means the
bound is too low and belongs in config.

    python scripts\\scan_log_outliers.py
    python scripts\\scan_log_outliers.py --days 180
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    days = 90
    for i, a in enumerate(sys.argv):
        if a == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])

    try:
        from utils.branch_log import BranchLogManager, check_bounds, field_bounds, metric_keys
    except ImportError as exc:
        print("ABORT: %s" % exc)
        print("       Apply the bounds patch first.")
        return 1

    logs = BranchLogManager().get_history(days=days)
    print("scanning %d logs over the last %d days" % (len(logs), days))
    print("")

    bad = []
    for l in logs:
        metrics = {k: l.get(k, 0) for k in metric_keys()}
        breaches = check_bounds(metrics)
        if breaches:
            bad.append((l, breaches))

    if not bad:
        print("No implausible values found. Nothing to clean up.")
        return 0

    print("=" * 78)
    print("IMPLAUSIBLE RECORDS: %d of %d logs" % (len(bad), len(logs)))
    print("=" * 78)
    for l, breaches in sorted(bad, key=lambda t: str(t[0].get("log_date"))):
        print("")
        print("  %s  %-9s %-28s  id=%s"
              % (str(l.get("log_date"))[:10], l.get("staff_code"),
                 str(l.get("staff_name"))[:28], l.get("id")))
        print("     stored index: %s   validated: %s"
              % (l.get("index"), bool(l.get("validated"))))
        for b in breaches:
            print("     - %s" % b)

    print("")
    print("=" * 78)
    print("These rows still count toward every ranking, the carried-forward")
    print("balance and the impact analysis until they are corrected.")
    print("")
    print("Current bounds (data/branch_log_config.json -> field_bounds):")
    for k, v in sorted(field_bounds().items()):
        print("   %-24s %s" % (k, format(int(v), ",")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
