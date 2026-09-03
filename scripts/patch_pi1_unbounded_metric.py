#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PI1 - a metric with no configured bound is not unbounded.

FROM THE BANK (2026-09-03): "on the productivity index, I see someone picked an
item that gave millions of points. We need to ensure someone does not confuse
count and value inputs."

THE BOUNDS MECHANISM WAS ALREADY THERE AND ALREADY GOOD. _DEFAULT_BOUNDS caps
accounts_opened at 60, customer_visits at 400, loans_disbursed at 500 million;
check_bounds reports every breach rather than the first; submit refuses with a
message that tells the officer what to do.

IT ONLY COVERS THE FIELDS SOMEBODY REMEMBERED TO LIST:

    cap = bounds.get(k)
    if cap is None or val <= float(cap):
        continue

A metric with no entry in _DEFAULT_BOUNDS is SKIPPED. Every activity an admin
adds through Administration arrives with no bound, so it accepts any number at
all - and a shilling figure typed into one of those scores millions of points
on the index.

WHAT THIS CHANGES: an unlisted metric falls back to a bound derived from its
TYPE, which the catalogue has always known:

    "int"     a count    -> 10,000     far beyond a real day, far below a
                                       shilling amount
    "amount"  KES        -> 500,000,000  the same as the listed KES fields

AN EXPLICIT BOUND STILL WINS. Anything in _DEFAULT_BOUNDS or in the admin's
field_bounds config is used exactly as before - this only fills the gap where
there was no answer at all.

WHY NOT SIMPLY REQUIRE A BOUND ON EVERY NEW ACTIVITY: because the admin screen
would then refuse to save an activity until somebody guessed a number, and the
guess would be worse than a sensible default. The default is generous enough
that a real day never meets it and mean enough that a KES figure always does.

Usage (from project root, .venv active):
    python scripts\patch_pi1_unbounded_metric.py            # dry run
    python scripts\patch_pi1_unbounded_metric.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "branch_log.py")
BACKUP_SUFFIX = ".pre_pi1"

OLD = '''        cap = bounds.get(k)
        if cap is None or val <= float(cap):
            continue'''

NEW = '''        # ── AN UNLISTED METRIC IS NOT AN UNBOUNDED ONE ──────────────────────
        # This used to `continue` when a metric had no configured bound, so
        # every activity an admin adds accepted any number at all. A shilling
        # figure typed into one of those scored millions of points on the
        # index.
        #
        # The catalogue has always declared whether a metric is a count or an
        # amount. Where nobody has set a bound, that type decides one.
        cap = bounds.get(k)
        if cap is None:
            _kind = str((schema.get(k, {}) or {}).get("type", "int") or "int")
            cap = _UNLISTED_AMOUNT if _kind == "amount" else _UNLISTED_COUNT
        if val <= float(cap):
            continue'''

CONST_ANCHOR = "def check_bounds(metrics: dict) -> list:"
CONST = '''# ── WHAT AN UNLISTED METRIC IS ALLOWED TO BE ────────────────────────────────
# Every activity an admin adds arrives with no entry in _DEFAULT_BOUNDS, and
# check_bounds used to skip anything it had no bound for. These are the fallback
# ceilings, chosen so that a real day never meets them and a shilling figure
# always does.
#
# Requiring the admin to set a bound on every new activity was the alternative,
# and it is worse: the screen would refuse to save until somebody guessed a
# number, and the guess would be less reliable than a sensible default.
_UNLISTED_COUNT = 10000
_UNLISTED_AMOUNT = 500000000


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "AN UNLISTED METRIC IS NOT AN UNBOUNDED ONE" in s:
        print("ABORT: PI1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the bounds check matched %d times." % s.count(OLD))
        return 1
    if s.count(CONST_ANCHOR) != 1:
        print("ABORT: check_bounds matched %d times." % s.count(CONST_ANCHOR))
        return 1

    s = s.replace(CONST_ANCHOR, CONST + CONST_ANCHOR, 1).replace(OLD, NEW, 1)
    print("  ok  an unlisted metric falls back to a bound from its type")

    if "bounds.get(k)" not in NEW:
        print("ABORT: an explicit bound must still win - this only fills the")
        print("       gap where there was no answer at all.")
        return 1
    if '_kind == "amount"' not in NEW:
        print("ABORT: a KES metric would be capped at the count ceiling, which")
        print("       would refuse legitimate shilling figures.")
        return 1
    if "if cap is None or val" in s:
        print("ABORT: the old skip survives somewhere.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: explicit bounds win, amounts keep their ceiling")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. An admin-added activity now has a ceiling.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
