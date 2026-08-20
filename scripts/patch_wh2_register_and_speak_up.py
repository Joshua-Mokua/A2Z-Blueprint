#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WH2 - register the warehouse table, and stop the write failing in silence.

WH1 put the warehouse on Postgres and the round trip still failed:

    created                   WH5192E1F2A6
    found in the TABLE        *** NO - the write did not reach it

THE ARCHITECTURE WAS RIGHT AND I WAS WRONG, twice.

FIRST: utils/db.py keeps a TABLE_REGISTRY, and `upsert` refuses any table not
in it - with a clear message naming the file and the constant to edit. I added
a table without registering it, and the gate correctly refused the write. That
gate is a good design and it did its job.

SECOND, and worse: I wrapped the write in `except Exception: return False`. So
a deliberate, well-worded refusal became nothing at all - no log, no message,
no clue. The store reported "database not reachable" when the database was
reachable and had told us precisely what was wrong.

That is the anti-pattern written into the top of half the patchers in this
repo - "a silent except is a latent bug" - and I wrote one into the store that
had just cost the team its data.

WHAT THIS CHANGES:

    deals_warehouse is registered in TABLE_USE_DB, so the write is allowed

    a failed database write LOGS AND PRINTS the reason, every time. It still
    does not raise - a warehouse that takes the app down when Postgres hiccups
    is worse than one that falls back - but nobody has to guess again.

    a failed database READ logs too, before falling back to the file

Usage (from project root, .venv active):
    python scripts\\patch_wh2_register_and_speak_up.py            # dry run
    python scripts\\patch_wh2_register_and_speak_up.py --apply
"""
import os
import shutil
import sys

DB = os.path.join("utils", "db.py")
MOD = os.path.join("utils", "deals_warehouse.py")
BACKUP_SUFFIX = ".pre_wh2"

REG_OLD = '''    "pipeline_deals":   True,
    "loan_applications":True,'''

WRITE_OLD = '''        return True
    except Exception:
        return False


def _db_read():'''

READ_OLD = '''    try:
        rows = db.fetch_all("SELECT * FROM deals_warehouse")
    except Exception:
        return None'''
READ_NEW = '''    try:
        rows = db.fetch_all("SELECT * FROM deals_warehouse")
    except Exception as exc:
        try:
            import logging
            logging.getLogger(__name__).error(
                "deals_warehouse: the database read failed, falling back to "
                "the file: %s", exc)
        except Exception:
            pass
        return None'''

REG_BLOCK = r'''    "pipeline_deals":   True,
    "loan_applications":True,
    # The deals warehouse was JSON-only and was LOST on 2026-08-20 - every
    # sacco and entity the team had entered, with nothing to recover from.
    # Registered here so it goes where the rest of the bank's data goes.
    #
    # WORTH NOTING: the registry refused the first attempt to write it, which
    # is the gate doing its job. What hid that was a silent `except` in the
    # caller, not a fault here.
    "deals_warehouse":  True,'''

WRITE_BLOCK = r'''        return True
    except Exception as exc:
        # NEVER SILENT. The first version of this returned False and said
        # nothing, so a registry rejection - a correct, deliberate refusal
        # with a clear message - looked exactly like "no database". The write
        # failed for two days' worth of reasons nobody could see.
        #
        # It still does not RAISE, because a warehouse that takes the app down
        # when Postgres hiccups is worse than one that falls back. But it says
        # so, every time, where somebody will read it.
        try:
            import logging
            logging.getLogger(__name__).error(
                "deals_warehouse: the database write FAILED, the file is now "
                "the only copy: %s", exc)
        except Exception:
            pass
        print("*** deals_warehouse: database write failed: %s" % exc)
        return False


'''


def main():
    apply = "--apply" in sys.argv
    for f in (DB, MOD):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    d = open(DB, encoding="utf-8").read()
    w = open(MOD, encoding="utf-8").read()
    if '"deals_warehouse"' in d and "NEVER SILENT" in w:
        print("ABORT: WH2 looks applied.")
        return 1
    if "POSTGRES IS THE STORE" not in w:
        print("ABORT: WH1 must be applied first.")
        return 1

    if '"deals_warehouse"' not in d:
        if d.count(REG_OLD) != 1:
            print("ABORT: the table registry matched %d times." % d.count(REG_OLD))
            return 1
        d = d.replace(REG_OLD, REG_BLOCK, 1)
        print("  ok  deals_warehouse is registered")
    if "NEVER SILENT" not in w:
        if w.count(WRITE_OLD) != 1 or w.count(READ_OLD) != 1:
            print("ABORT: anchors matched %d / %d times."
                  % (w.count(WRITE_OLD), w.count(READ_OLD)))
            return 1
        w = w.replace(WRITE_OLD, WRITE_BLOCK + "def _db_read():", 1)
        w = w.replace(READ_OLD, READ_NEW, 1)
        print("  ok  a failed write and a failed read both say why")

    if "except Exception:\n        return False" in w:
        print("ABORT: a silent except survives in this module - that is the")
        print("       fault this patch exists to remove.")
        return 1
    if "raise" in WRITE_BLOCK.split("return False")[0]:
        print("ABORT: the write would raise. A warehouse that takes the app")
        print("       down when Postgres hiccups is worse than one that falls")
        print("       back - it must log, not raise.")
        return 1
    import ast
    for name, src in ((DB, d), (MOD, w)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("ABORT: %s would not parse - line %s: %s"
                  % (os.path.basename(name), exc.lineno, exc.msg))
            return 1
    print("  ok  post-checks: registered, loud, does not raise")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((DB, d), (MOD, w)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    for path in (DB, MOD):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1
    print("  ok  compiles")
    print("\nRESTART UVICORN, then:  python scripts\\verify_warehouse_store.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
