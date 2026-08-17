#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3g - HOTFIX: the history grid was discarding every row it built.

This is the tail of the P3d/P3e defect chain and the reason the grid stayed
empty even after the scope fix in 3f.

P3d duplicated the row-building loop, so the function looked like:

        rows = []
        for sc, staff_logs in by_staff.items():     # loop A
            ...
                rows.append(row)
        rows = []                                   # <- belonged to the duplicate
        for sc, staff_logs in by_staff.items():     # loop B (the duplicate)
            ...
                rows.append(row)

P3e correctly deleted loop B, but left the `rows = []` that had preceded it.
The surviving code therefore built every row in loop A and then immediately
threw them all away one line later:

            rows.append(row)
    rows = []                                       # <- orphan

    rows.sort(...)
    return {"rows": rows, ...}                      # always empty

Symptom: "No logs in this period" for every user at every scope, including
Bank-wide, with 145 logs sitting in the store and a roster fill that had
correctly synthesised rows for all 363 staff. Nothing downstream was wrong;
the result was being cleared at the last moment.

This removes the orphan line. Nothing else changes.

Verified: py_compile clean; exactly one `rows = []` remains in the function,
and it precedes the loop.

Usage (from project root, .venv active):
    python scripts\\patch_p3g_rows_reset.py            # dry run
    python scripts\\patch_p3g_rows_reset.py --apply    # write + .pre_p3g backup
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_p3g"

OLD = "            rows.append(row)\n    rows = []\n"
NEW = "            rows.append(row)\n"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1

    api = open(API, encoding="utf-8").read()

    n = api.count(OLD)
    if n == 0:
        print("ABORT: orphan `rows = []` not found - either already fixed, or this")
        print("       file never carried the P3d duplication.")
        return 1
    if n != 1:
        print("ABORT: orphan pattern matched %d times (expected 1)." % n)
        return 1

    api = api.replace(OLD, NEW, 1)
    print("  ok  removed the orphan `rows = []` after the row loop")

    # Structural post-check, bounded to the endpoint.
    s = api.index("def branch_log_history_grid(")
    e = api.index('"deadline_time": deadline_time(),', s)
    fn = api[s:e]
    n_reset = fn.count("    rows = []")
    n_loops = fn.count("for sc, staff_logs in by_staff.items():")
    n_append = fn.count("rows.append(row)")
    print("  checks: rows=[] x%d, loops x%d, append x%d (expect 1, 1, 1)"
          % (n_reset, n_loops, n_append))
    if (n_reset, n_loops, n_append) != (1, 1, 1):
        print("ABORT: structure is not as expected - nothing written.")
        return 1
    if fn.index("    rows = []") > fn.index("for sc, staff_logs in by_staff.items():"):
        print("ABORT: `rows = []` no longer precedes the loop.")
        return 1
    print("  ok  the single reset precedes the loop")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nRestart uvicorn, then reload the History tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
