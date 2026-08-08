#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3e - HOTFIX for two defects I introduced in Phase 3d.

1. DUPLICATED ROW LOOP. The 3d patcher built its insert block by scanning for
   the next blank line after the fill code. That search ran past the block and
   swallowed the row-building loop, so the patcher inserted a SECOND identical
   copy of it. Every grid row was therefore emitted twice and the loop ran
   twice. This removes the duplicate - one loop, one `rows.append(row)`.

2. LOST CACHE. When 3d rewrote _roster_dims() to read staff_register.xlsx, the
   mtime cache from 3c was dropped. The map was rebuilt from df.iterrows() on
   every call, and _dims_for() was called once per row: at ~2,200 rows against
   a 363-row register that is roughly 790,000 pandas row reads per request.
   Together with the duplicate loop, that is why the Head of Branches view hung.

   Fixed two ways: the map is memoised for 300s (matching get_staff_roster()'s
   own cache horizon), and the row loop now resolves it ONCE per request and
   does plain dict lookups.

This patcher rewrites the two affected regions wholesale rather than anchoring
inside them, because anchoring inside a region that exists twice is what caused
the problem in the first place. It refuses to run unless it finds exactly the
duplicate it expects.

Verified: py_compile clean, exactly one row loop remains, roster lookup resolved
once per request.

Usage (from project root, .venv active):
    python scripts\\patch_p3e_hotfix.py            # dry run
    python scripts\\patch_p3e_hotfix.py --apply    # write + .pre_p3e backup
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_p3e"

HELPER_NEW = r'''_DIMS_CACHE = None
_DIMS_AT = 0.0
_DIMS_TTL = 300.0   # seconds; matches the roster loader's own cache horizon


def _roster_dims() -> dict:
    """Canonical {canon(staff_code) -> {department, branch, full_name, role}}.

    SOURCE OF TRUTH: data/staff_register.xlsx, read through
    utils.api_pipeline_scope.get_staff_roster() — the SAME loader the pipeline
    hierarchy and visibility engine uses. It carries Department, Branch, Unit,
    Region and Reports To Code, so the grid's dimensions cannot drift from the
    hierarchy the rest of the system reports against.

    (An earlier revision of this joined data/staff_roster.json — a 362-row
    shadow of the same population without the reporting column. Two readers,
    two files, one concept: exactly the drift this codebase keeps paying for.)

    The Daily Log record's own `unit` is free text typed at submit time and is
    inconsistent in live data ("Fortis" / "Fortis Branch" / "Consumer" /
    "EKE-CONSUMER BANKING DEPARTMENT"); it is used only as a fallback.

    Keyed on utils.staff_code.canon so KE0439 / KE439 / 439 all resolve.
    """
    global _DIMS_CACHE, _DIMS_AT
    import time as _time
    from utils.staff_code import canon as _canon

    # P3e: memoised. Without this the map was rebuilt from df.iterrows() on
    # EVERY call. get_staff_roster() has its own TTL cache; this memoises the
    # derived lookup so a request does one build, not one per row.
    if _DIMS_CACHE is not None and (_time.monotonic() - _DIMS_AT) < _DIMS_TTL:
        return _DIMS_CACHE

    out: dict = {}
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        if df is None or len(df) == 0:
            return out
        cols = set(df.columns)

        def pick(row, *names):
            for n in names:
                if n in cols:
                    v = row.get(n)
                    if v is not None and str(v).strip() and str(v) != "nan":
                        return str(v).strip()
            return ""

        for _, row in df.iterrows():
            code = pick(row, "Staff Code", "staff_code")
            if not code:
                continue
            out[_canon(code)] = {
                "department": pick(row, "Department", "department"),
                "branch":     pick(row, "Branch", "Unit", "branch", "unit"),
                "full_name":  pick(row, "Staff Name", "staff_name", "full_name"),
                "role":       pick(row, "Role", "role"),
                "code":       code,
            }
    except Exception:
        return _DIMS_CACHE or out

    _DIMS_CACHE, _DIMS_AT = out, _time.monotonic()
    return out


def _dims_for(staff_code) -> dict:
    """Roster dimensions for a staff code, empty dict when unmatched."""
    from utils.staff_code import canon as _canon
    return _roster_dims().get(_canon(staff_code)) or {}


'''

MID_NEW = r'''    mkeys = metric_keys()

    # Resolve the roster ONCE per request; the row loop then does plain dict
    # lookups instead of re-deriving the map for every row.
    from utils.staff_code import canon as _canon_code
    _dims = _roster_dims()

    if include_missing:
        from datetime import date as _date, timedelta as _td
        from utils.staff_code import canon as _canon
        try:
            from utils import workcal as _wc
        except Exception:
            _wc = None

        dims = _dims
        if _is_admin(user):
            scope_codes = set(dims.keys())
        elif _is_manager(user):
            try:
                from utils.api_pipeline_scope import get_visible_staff_codes
                scope_codes = {_canon(c) for c in get_visible_staff_codes({
                    "staff_code": me.get("staff_code", ""),
                    "role": me.get("role", ""),
                    "is_admin": bool(user.get("is_admin")),
                })}
            except Exception:
                scope_codes = {_canon(c) for c in by_staff}
        else:
            scope_codes = {_canon(me.get("staff_code", ""))}
        scope_codes.discard("")

        # Working days in the window, newest-inclusive.
        today = _date.today()
        window = [today - _td(days=i) for i in range(int(days))]
        work_days = [d for d in window if (_wc.is_working_day(d) if _wc else d.weekday() != 6)]

        # Index existing logs by canonical code + date so the fill never
        # duplicates a day someone actually filed.
        filed = {}
        for code, ls in by_staff.items():
            for l in ls:
                filed.setdefault(_canon(code), set()).add(str(l.get("log_date"))[:10])

        for ck in scope_codes:
            d = dims.get(ck) or {}
            have = filed.get(ck, set())
            bucket = by_staff.setdefault(d.get("code") or ck, [])
            for day in work_days:
                iso = day.isoformat()
                if iso in have:
                    continue
                blank = {
                    "log_date": iso,
                    "staff_code": d.get("code") or ck,
                    "staff_name": d.get("full_name", ""),
                    "role": d.get("role", ""),
                    "unit": d.get("branch", ""),
                    "status": "missing",
                    "validated": False,
                    "auto_submitted": False,
                    "index": 0.0,
                    "remarks": "",
                    "manager_note": "",
                }
                for k in mkeys:
                    blank[k] = 0
                bucket.append(blank)
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    api = open(API, encoding="utf-8").read()

    if "_DIMS_CACHE" in api:
        print("ABORT: _DIMS_CACHE already present - Phase 3e looks applied.")
        return 1
    if "include_missing" not in api:
        print("ABORT: apply patch_p3d_roster_complete.py first.")
        return 1

    n_loops = api.count("for sc, staff_logs in by_staff.items():")
    n_appends = api.count("rows.append(row)")
    print("  found %d row loops and %d rows.append(row) (expected 2 and 2)"
          % (n_loops, n_appends))
    if n_loops != 2 or n_appends != 2:
        print("ABORT: this file does not carry the 3d duplication - nothing to fix.")
        return 1

    # 1. drop the duplicated loop: keep the first, delete the second.
    first = api.index("    rows = []")
    a = api.index("    for sc, staff_logs in by_staff.items():", first)
    b = api.index("    for sc, staff_logs in by_staff.items():", a + 10)
    end_b = api.index("rows.append(row)", b) + len("rows.append(row)\n")
    block_a = api[a:api.index("rows.append(row)", a) + len("rows.append(row)\n")]
    block_b = api[b:end_b]
    if [x.strip() for x in block_a.split("\n") if x.strip()] != \
       [x.strip() for x in block_b.split("\n") if x.strip()]:
        print("ABORT: the two loops are not identical - refusing to delete either.")
        return 1
    api = api[:b] + api[end_b:]
    print("  ok  removed the duplicated row loop")

    # 2. replace the helper region with the memoised version
    try:
        i = api.index("def _roster_dims() -> dict:")
        j = api.index('@router.get("/history-grid")')
    except ValueError:
        print("ABORT: could not locate the roster helper region.")
        return 1
    api = api[:i] + HELPER_NEW + api[j:]
    print("  ok  roster map memoised (300s TTL)")

    # 3. replace the mkeys..rows region so the lookup is resolved once
    try:
        k = api.index("    mkeys = metric_keys()")
        l = api.index("    rows = []", k)
    except ValueError:
        print("ABORT: could not locate the mkeys region.")
        return 1
    api = api[:k] + MID_NEW + api[l:]
    print("  ok  roster lookup hoisted out of the row loop")

    # 4. the per-row lookup lives inside the loop body, outside the region
    #    replaced above. Now that the duplicate is gone it appears exactly once.
    row_old = '            _d = _dims_for(r.get("staff_code"))'
    row_new = '            _d = _dims.get(_canon_code(r.get("staff_code"))) or {}'
    if api.count(row_old) != 1:
        print("ABORT: per-row lookup matched %d times (expected 1)." % api.count(row_old))
        return 1
    api = api.replace(row_old, row_new, 1)
    print("  ok  per-row lookup -> dict access on the hoisted map")

    if api.count("for sc, staff_logs in by_staff.items():") != 1:
        print("ABORT: post-check - row loop count is not 1.")
        return 1
    if "_dims_for(r.get" in api:
        print("ABORT: post-check - per-row _dims_for call still present.")
        return 1

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
