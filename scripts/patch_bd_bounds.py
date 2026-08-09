#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BD - plausibility bounds: stop KES amounts entering count fields.

FOUND IN LIVE DATA. Four of 164 logs carry money figures in COUNT boxes:

    KE1223   708,309,885 DFS registrations
    CN205      3,325,000 loans referred
    KE461      1,630,000 loans referred    -> index 4,890,106
    KE1262       500,000 DFS registrations -> index 1,500,014

The schema already distinguishes count from value - dfs_registrations is
type=int unit=count, deposits_mobilised is type=amount unit=KES - but NOTHING
ENFORCED IT AT ENTRY. So the index absorbed them silently, one row produced 4.89
million index points, and the impact analysis reported a single activity as 99%
of the bank's output. One of the four is already validated=True: a manager
approved 708 million registrations because the number never looked wrong.

WHAT THIS ADDS

  utils/branch_log.field_bounds()  - {field: max_per_day}, from
      data/branch_log_config.json under `field_bounds`, falling back to defaults
      SPLIT BY TYPE, because a count and a KES value need very different
      ceilings. A branch that genuinely does more can be raised without a deploy.

  utils/branch_log.check_bounds(metrics) - every breach, not the first, so
      someone correcting an entry fixes it in one pass instead of meeting the
      next problem on resubmit.

  submit() REJECTS, never clamps. A clamped number looks like a real one and
      the person who typed it would never learn they were wrong. The API
      surfaces it as 400 with the field names - the entry is wrong, not the
      server.

  DRAFTS ARE NOT CHECKED, deliberately. A half-typed number is not an error
      yet, and blocking mid-typing would be hostile. The same two lines appear
      in save_draft, so the enforcement is scoped to submit() only.

  scripts/scan_log_outliers.py - lists records already in the store that breach
      the bounds. READ ONLY: what to do with each is a judgement call, and a
      genuine outlier means the bound is too low, not that the row is wrong.

Verified against the real records: all four caught, a KES 2,000,000 deposit
passes, and multiple breaches report together.

STILL TO DO, not in this batch: the four existing rows still count toward every
ranking and every carried-forward balance until someone corrects them. Run the
scan and decide per row.

Usage (from project root, .venv active):
    python scripts\\patch_bd_bounds.py            # dry run
    python scripts\\patch_bd_bounds.py --apply    # write + .pre_bd backups
"""
import os
import shutil
import sys

BL = os.path.join("utils", "branch_log.py")
API = os.path.join("utils", "api_branch_log.py")
SCAN = os.path.join("scripts", "scan_log_outliers.py")
BACKUP_SUFFIX = ".pre_bd"

CLASS_ANCHOR = "class BranchLogManager"

API_OLD = '    rec = blm.submit(me["staff_code"], me["staff_name"], me["unit"], me["role"], values or {})'
API_NEW = '''    try:
        rec = blm.submit(me["staff_code"], me["staff_name"], me["unit"], me["role"],
                         values or {})
    except ValueError as exc:
        # Plausibility bounds. 400, not 500: the entry is wrong, not the server,
        # and the message names every field so it can be fixed in one pass.
        raise HTTPException(status_code=400, detail=str(exc))'''

GUARD_OLD = '''        remarks = str(values.get("remarks", "") or "")

        existing = next((l for l in self.logs'''
GUARD_NEW = '''        remarks = str(values.get("remarks", "") or "")

        # Reject, never clamp: a clamped number looks like a real one, and the
        # person who typed it would never learn they had made a mistake.
        # Drafts are deliberately NOT checked - a half-typed number is not an
        # error yet, and blocking mid-typing would be hostile.
        breaches = check_bounds(metrics)
        if breaches:
            raise ValueError(
                "This entry looks implausible and was not saved. "
                + "; ".join(breaches)
                + ". Correct it, or ask an admin to raise the limit if it is genuine."
            )

        existing = next((l for l in self.logs'''

BOUNDS_BLOCK = r'''# ── Plausibility bounds ──────────────────────────────────────────────────────
# A count field accepted 708,309,885 in live data, and a KES figure typed into a
# count box (500,000 DFS registrations in one day) produced a carried-forward
# balance of 1.5 million that then propagated into every ranking and analytic.
# The reconciliation gate only catches over-reporting against a branch control
# total, and only where one exists - nothing stopped the number entering.
#
# Bounds are per field and live in data/branch_log_config.json under
# `field_bounds`, so a branch that genuinely does more can be raised without a
# deploy. Type matters: a COUNT and a KES VALUE need very different ceilings,
# which is why the defaults below are split by type.
_DEFAULT_BOUNDS = {
    "transactions_count": 500,
    "customer_visits":    400,
    "digital_txns":       300,
    "nps_collected":      150,
    "accounts_opened":     60,
    "accounts_activated":  60,
    "cards_issued":       100,
    "dfs_registrations":  150,
    "loans_referred":      50,
    "bancassurance_sold":  50,
    "complaints_received": 100,
    "complaints_resolved": 100,
    "new_leads":          150,
    "cross_sell_success":  60,
    "teller_errors":       50,
    # KES values - generous, but a person booking more than this in one day is
    # an event worth a conversation, not a silent record.
    "loans_disbursed":    500000000,
    "deposits_mobilised": 500000000,
}


def field_bounds() -> dict:
    """{field_key: max_per_day}, from config, falling back to the defaults."""
    cfg = load_log_config().get("field_bounds") or {}
    out = dict(_DEFAULT_BOUNDS)
    for k, v in cfg.items():
        try:
            out[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def check_bounds(metrics: dict) -> list:
    """Human-readable breaches; empty when the entry is plausible.

    Reports EVERY breach rather than the first, so someone correcting an entry
    fixes it once instead of meeting the next problem on resubmit.
    """
    bounds = field_bounds()
    schema = {f["key"]: f for f in fields_schema()}
    out = []
    for k, v in (metrics or {}).items():
        try:
            val = float(v or 0)
        except (TypeError, ValueError):
            continue
        cap = bounds.get(k)
        if cap is None or val <= float(cap):
            continue
        f = schema.get(k, {})
        out.append("%s: %s %s exceeds the daily maximum of %s"
                   % (f.get("label", k), format(int(val), ","),
                      f.get("unit", ""), format(int(float(cap)), ",")))
    return out


'''

SCANNER = r'''#!/usr/bin/env python
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
'''


def main():
    apply = "--apply" in sys.argv
    for p in (BL, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    bl = open(BL, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "check_bounds" in bl:
        print("ABORT: branch_log already has check_bounds - BD looks applied.")
        return 1
    if bl.count(CLASS_ANCHOR) != 1:
        print("ABORT: class anchor matched %d times." % bl.count(CLASS_ANCHOR))
        return 1
    if api.count(API_OLD) != 1:
        print("ABORT: submit call matched %d times." % api.count(API_OLD))
        return 1
    # The guard lines appear in BOTH submit and save_draft; scope to submit.
    try:
        sub = bl.index("    def submit(self, staff_code")
        bl.index(GUARD_OLD, sub)
    except ValueError:
        print("ABORT: could not locate the guard point inside submit().")
        return 1

    bl = bl.replace(CLASS_ANCHOR, BOUNDS_BLOCK + CLASS_ANCHOR, 1)
    print("  ok  branch_log - field_bounds / check_bounds at MODULE level")

    sub = bl.index("    def submit(self, staff_code")
    i = bl.index(GUARD_OLD, sub)
    bl = bl[:i] + GUARD_NEW + bl[i + len(GUARD_OLD):]
    print("  ok  submit() rejects implausible entries (drafts untouched)")

    api = api.replace(API_OLD, API_NEW, 1)
    print("  ok  submit endpoint returns 400 naming the fields")

    # Post-checks that would have caught the mistake made while building this:
    # the block must be at MODULE level, not inside the class.
    if bl.index("def check_bounds(") > bl.index(CLASS_ANCHOR):
        print("ABORT: post-check - the bounds block landed INSIDE the class.")
        return 1
    if bl.count("check_bounds(metrics)") != 1:
        print("ABORT: post-check - the guard is not wired exactly once.")
        return 1
    if "def get_history" not in bl:
        print("ABORT: post-check - BranchLogManager lost get_history.")
        return 1
    print("  ok  post-checks: module-level block, one guard, class intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((BL, bl), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    open(SCAN, "w", encoding="utf-8", newline="").write(SCANNER)
    print("CREATED %s" % SCAN)

    import py_compile
    for path in (BL, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Now find what is already in the store:")
    print("  python scripts\\scan_log_outliers.py")
    print("Then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
