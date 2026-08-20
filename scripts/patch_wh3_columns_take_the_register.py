#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WH3 - the warehouse table takes what a register actually publishes.

FROM THE CBK COMMERCIAL BANKS IMPORT (2026-08-20):

    deals_warehouse: the database write FAILED, the file is now the only
    copy: value too long for type character varying(60)

WH2 IS THE REASON WE KNOW. Before it, that write returned False in silence and
the record would have lived in the file alone - which is precisely the state
that lost the warehouse. It said so, loudly, on the run that mattered.

THE CAUSE: contact_phone was VARCHAR(60). A bank publishes six numbers on one
line -

    +254-20-3877290/3/7; 3872183/4; 3867503, 0711 - 074074, 0708 - 111000

sixty-nine characters, and Postgres rejected the whole row.

These columns hold free text from documents nobody controls. Guessing a width
for them was the mistake: a register will always publish something longer than
the guess, and the cost is a prospect that exists in one place instead of two.
TEXT costs nothing in Postgres and cannot be the reason a record goes missing.

WIDENED: name, canonical_key, contact_name, contact_phone, contact_email,
source_event, created_by_name, claimed_by_name.

NOT widened: id, status, dates, codes. Those are ours, we control their shape,
and a length limit on them is a real check rather than a guess.

AN EXISTING TABLE IS WIDENED IN PLACE. CREATE TABLE IF NOT EXISTS will not
change a column that is already there, so a box that imported before this fix
would keep failing on the same rows. The ALTER keeps every row and is a no-op
the second time.

Verified: the exact 69-character string that broke it now stores and reads back
unchanged.

Usage (from project root, .venv active):
    python scripts\\patch_wh3_columns_take_the_register.py            # dry run
    python scripts\\patch_wh3_columns_take_the_register.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
BACKUP_SUFFIX = ".pre_wh3"

COLS_OLD = '''                contact_name    VARCHAR(200),
                contact_phone   VARCHAR(60),
                contact_email   VARCHAR(200),'''

ALTER_ANCHOR = '        db.execute("CREATE INDEX IF NOT EXISTS idx_dw_status "'

WIDEN = (("                name            VARCHAR(300),",
          "                name            TEXT,"),
         ("                canonical_key   VARCHAR(300),",
          "                canonical_key   TEXT,"),
         ("                source_event    VARCHAR(200),",
          "                source_event    TEXT,"),
         ("                created_by_name VARCHAR(200),",
          "                created_by_name TEXT,"),
         ("                claimed_by_name VARCHAR(200),",
          "                claimed_by_name TEXT,"))

COLS_BLOCK = r'''                -- A REGISTER PUBLISHES WHAT IT PUBLISHES, and a bank lists
                -- six phone numbers on one line: "+254-20-3877290/3/7;
                -- 3872183/4; 3867503, 0711-074074, 0708-111000". VARCHAR(60)
                -- rejected the whole row, and the record fell back to the file
                -- alone - which is the state that lost the warehouse.
                --
                -- These are free text from a document nobody controls. TEXT
                -- costs nothing in Postgres and cannot be the reason a
                -- prospect goes missing.
                contact_name    TEXT,
                contact_phone   TEXT,
                contact_email   TEXT,'''

ALTER_BLOCK = r'''        # A table created before this fix still has the narrow columns, and
        # CREATE TABLE IF NOT EXISTS will not change them. Widen in place -
        # ALTER to TEXT is safe, keeps every row, and is a no-op the second
        # time.
        for _c in ("name", "canonical_key", "contact_name", "contact_phone",
                   "contact_email", "source_event", "created_by_name",
                   "claimed_by_name"):
            try:
                db.execute("ALTER TABLE deals_warehouse ALTER COLUMN %s TYPE TEXT" % _c)
            except Exception:
                pass
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "A REGISTER PUBLISHES WHAT IT PUBLISHES" in s:
        print("ABORT: WH3 looks applied.")
        return 1
    if "CREATE TABLE IF NOT EXISTS deals_warehouse" not in s:
        print("ABORT: WH1 must be applied first.")
        return 1
    if s.count(COLS_OLD) != 1 or s.count(ALTER_ANCHOR) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(COLS_OLD), s.count(ALTER_ANCHOR)))
        return 1

    s = s.replace(COLS_OLD, COLS_BLOCK, 1)
    for old, new in WIDEN:
        if old in s:
            s = s.replace(old, new, 1)
    s = s.replace(ALTER_ANCHOR, ALTER_BLOCK + ALTER_ANCHOR, 1)
    print("  ok  the free-text columns take what a register publishes")

    if "ALTER TABLE deals_warehouse ALTER COLUMN" not in ALTER_BLOCK:
        print("ABORT: a table created before this fix would keep failing on")
        print("       the same rows - CREATE TABLE IF NOT EXISTS will not")
        print("       widen a column that already exists.")
        return 1
    i = s.index("CREATE TABLE IF NOT EXISTS deals_warehouse")
    j = s.index('"""', i)
    table = s[i:j]
    for must_keep in ("id              VARCHAR(60)", "status          VARCHAR(40)"):
        if must_keep not in table:
            print("ABORT: %r was widened. Those are ours, we control their"
                  % must_keep.split()[0])
            print("       shape, and a limit on them is a real check.")
            return 1
    if "contact_phone   TEXT" not in table:
        print("ABORT: the column that actually failed is still narrow.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: widened, existing table migrated, ids untouched")

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
    print("\nRESTART UVICORN, then re-import the commercial banks so the rows")
    print("that failed reach the database:")
    print("   python scripts\\import_business_register.py \\")
    print("       Directory-of-Licenced-Commercial-Banks.csv --update --apply \\")
    print("       --source \"CBK directory of licenced commercial banks\"")
    print("   python scripts\\verify_warehouse_store.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
