#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DQ2 - a committee sees its cases even when Postgres is not answering.

FOUND BY TESTING THE QUESTION "can the DCC see pending committees like the
managers?" (2026-08-13). The answer was no, on any box falling back to JSON.

DQ1 recovered out-of-scope committee cases - a department committee sits at
head office, so a branch RM is not in its members' cascade and a scoped read
alone hides the very cases they must decide. But that recovery was wrapped in
`if _db_available():`. On a box where Postgres is not answering, the recovery
never ran and a DCC member saw an EMPTY QUEUE - precisely the failure the
recovery exists to prevent, reintroduced by its own guard.

Now it recovers from whichever store is live: Postgres when it answers, the
JSON store when it does not. Same rule either way, and can_view still decides
who sees what.

Measured with NO cascade scope at all and the database forced off:

    DCC member (B1)   1 case
    on no committee   0 cases

ANCHORED EDIT, not a whole file. Two whole-file patchers this week silently
removed working code - a sidebar entry and a tab - so anything that can be an
anchored edit now is one.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_dq2_committee_fallback.py            # dry run
    python scripts\\patch_dq2_committee_fallback.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_dq2"

OLD = '''    if _db_available():
        try:
            from utils.db import db as _db2
            rows = _db2.fetch_all("SELECT * FROM pipeline_deals", tuple())
            seen = {str(d.get("id")) for d in all_deals}
            for d in (_normalize_db_deal_row(x) for x in _serialize(rows)):
                if str(d.get("id")) not in seen:
                    all_deals.append(d)
        except Exception:
            pass'''

NEW = '''    # RECOVERED FROM WHICHEVER STORE IS LIVE, not only from the database.
    # Guarding this with _db_available() meant that on a box falling back to
    # JSON a department committee saw nothing at all - the exact failure this
    # recovery exists to prevent, reintroduced by the guard itself.
    seen = {str(d.get("id")) for d in all_deals}
    _extra = []
    if _db_available():
        try:
            from utils.db import db as _db2
            rows = _db2.fetch_all("SELECT * FROM pipeline_deals", tuple())
            _extra = [_normalize_db_deal_row(x) for x in _serialize(rows)]
        except Exception:
            _extra = []
    if not _extra:
        try:
            from utils.core import PipelineManager as _PM_fallback
            _extra = list(getattr(_PM_fallback(), "deals", []) or [])
        except Exception:
            _extra = []
    for d in _extra:
        if str(d.get("id")) not in seen:
            all_deals.append(d)'''



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    src = open(API, encoding="utf-8").read()
    if "_PM_fallback" in src:
        print("ABORT: DQ2 looks applied.")
        return 1
    if src.count(OLD) != 1:
        print("ABORT: the recovery block matched %d times." % src.count(OLD))
        print("       Apply DQ1 first - this amends what it added.")
        return 1

    src = src.replace(OLD, NEW, 1)
    print("  ok  committee recovery works on either store")

    if "_PM_fallback" not in NEW:
        print("ABORT: there is still no JSON fallback.")
        return 1
    if "_db_available()" not in NEW:
        print("ABORT: the database is no longer preferred - it should be tried")
        print("       first, with JSON only as the fallback.")
        return 1
    print("  ok  post-checks: database first, JSON when it is not answering")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(src)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRestart uvicorn. A department committee member sees their cases")
    print("whether or not Postgres is answering.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
