#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Correct records where a KES amount was typed into a COUNT field. DRY RUN by
default; --apply backs up the store first.

WHAT IT DOES, AND WHY ONLY THIS. It zeroes the single offending FIELD on rows
that breach the plausibility bounds, recomputes that row's index, and appends a
note recording the original value. It does not delete the log, does not touch
any other field, and does not guess what the number should have been.

That restraint is the point. "3,325,000 loans referred" is obviously a loan
VALUE, but whether it belonged in loans_disbursed, or was a typo, or was a test
entry, is not something a script can know. Zeroing the field removes a figure
that is certainly wrong from every ranking and every carried-forward balance,
while the note preserves what was there so a manager can restore the real number
if they know it.

A row that breaches because the BOUND is too low is a different problem: raise
the bound in data/branch_log_config.json -> field_bounds instead of running
this. Check the scan output first.

    python scripts\\fix_log_outliers.py           # show what would change
    python scripts\\fix_log_outliers.py --apply   # correct them
"""
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv

    try:
        from utils.branch_log import (
            BranchLogManager, check_bounds, field_bounds, metric_keys,
            compute_index, fields_schema,
        )
    except ImportError as exc:
        print("ABORT: %s" % exc)
        print("       Apply patch_bd_bounds.py first.")
        return 1

    labels = {f["key"]: f.get("label", f["key"]) for f in fields_schema()}
    bounds = field_bounds()
    blm = BranchLogManager()
    mkeys = list(metric_keys())

    targets = []
    for l in blm.logs:
        metrics = {k: l.get(k, 0) for k in mkeys}
        if not check_bounds(metrics):
            continue
        offending = []
        for k in mkeys:
            try:
                v = float(l.get(k) or 0)
            except (TypeError, ValueError):
                continue
            cap = bounds.get(k)
            if cap is not None and v > float(cap):
                offending.append((k, v))
        if offending:
            targets.append((l, offending))

    if not targets:
        print("No records breach the bounds. Nothing to correct.")
        return 0

    print("=" * 78)
    print("RECORDS TO CORRECT: %d" % len(targets))
    print("=" * 78)
    for l, offending in targets:
        before = float(l.get("index") or 0)
        preview = {k: l.get(k, 0) for k in mkeys}
        for k, _v in offending:
            preview[k] = 0
        after = compute_index(preview)
        print("")
        print("  %s  %-9s %-26s  id=%s"
              % (str(l.get("log_date"))[:10], l.get("staff_code"),
                 str(l.get("staff_name"))[:26], l.get("id")))
        for k, v in offending:
            print("     %-32s %s  ->  0" % (labels.get(k, k), format(int(v), ",")))
        print("     index %s  ->  %s" % (format(int(before), ","), format(int(after), ",")))
        if l.get("validated"):
            print("     NOTE: this row is already VALIDATED — correcting it changes a")
            print("           figure a manager signed off. Worth telling them.")

    if not apply:
        print("")
        print("DRY RUN — nothing written. Re-run with --apply to correct them.")
        print("If a row is genuine, raise its bound in data/branch_log_config.json")
        print("under field_bounds instead of running this.")
        return 0

    src = os.path.join("data", "branch_logs.json")
    bak = src + ".pre_outlier_fix"
    if os.path.isfile(src):
        shutil.copy2(src, bak)
        print("\nbacked up %s -> %s" % (src, bak))

    stamp = datetime.now().isoformat(timespec="seconds")
    for l, offending in targets:
        parts = []
        for k, v in offending:
            l[k] = 0
            parts.append("%s was %s" % (labels.get(k, k), format(int(v), ",")))
        l["index"] = compute_index({k: l.get(k, 0) for k in mkeys})
        note = ("[%s] Implausible value cleared by an administrator: %s. "
                "A count field cannot hold a currency amount; re-enter the correct "
                "figure if it is known." % (stamp[:10], "; ".join(parts)))
        l["remarks"] = ((str(l.get("remarks") or "") + " ").strip() + " " + note).strip()
        l["outlier_corrected_at"] = stamp

    blm._save()
    print("corrected %d records and recomputed their index." % len(targets))
    print("The original values are recorded in each row's remarks.")
    print("")
    print("Now re-run the impact analysis on clean data:")
    print("  python scripts\\\\seed_impact_tiers.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
