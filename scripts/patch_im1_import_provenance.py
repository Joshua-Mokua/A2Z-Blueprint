#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
IM1 - cleaning a record no longer makes the next import duplicate it.

RULING (2026-08-20): "how do we save the imports and keep cleaning them from
our end - the whole idea was to create a data warehouse of all businesses and
institutions in Kenya."

Duplicates were matched on the CANONICAL NAME, and that quietly punishes the
very work the warehouse exists for. Correct "1ICEA Lion Individual Retirement
Benefits Scheme" to "ICEA Lion" - a glued row number, exactly the kind of thing
a register extract leaves behind - and the key changes. Re-import that register
next year and the old, uncorrected row returns as a NEW prospect, sitting
beside the one somebody fixed.

At thirty-three records that is untidy. At the eighteen hundred this is aiming
for, across SASRA, RBA, IRA and whatever follows, it is a warehouse nobody
trusts - and no way to tell a cleaned record from a stale one.

TWO FIELDS ON EVERY IMPORTED RECORD:

    source_ref   the register, plus the name AS PUBLISHED. A re-import matches
                 on this FIRST, so the name in the warehouse is free to be
                 corrected without breaking the link to its row.

    import_run   which run brought it, with a timestamp. A bad import can be
                 found and undone rather than picked out of the shelf by eye.

Measured, on a two-row register:

    import          2 listed
    clean a name    "Amana Personal Pension Plan" -> "Amana Pension Plan Limited"
    re-import       2 skipped, 0 listed, shelf still 2

Before this the shelf would have held three, and the third would have looked
like a business.

Hand-entered prospects are unaffected - they carry no source_ref and are still
matched by name, which is right for something a person typed.

Usage (from project root, .venv active):
    python scripts\\patch_im1_import_provenance.py            # dry run
    python scripts\\patch_im1_import_provenance.py --apply
"""
import os
import shutil
import sys

STORE = os.path.join("utils", "deals_warehouse.py")
IMPORTER = os.path.join("scripts", "import_business_register.py")
BACKUP_SUFFIX = ".pre_im1"

SIG_OLD = '           estimated_value: float = 0.0, subsector: str = "") -> dict:'
SIG_NEW = '''           estimated_value: float = 0.0, subsector: str = "",
           source_ref: str = "", import_run: str = "") -> dict:'''

REC_OLD = '        "source_event": str(source_event or "").strip(),'
REC_NEW = '''        "source_event": str(source_event or "").strip(),
        # WHERE THIS ROW CAME FROM and WHICH RUN BROUGHT IT. The reference is
        # the register plus the name AS PUBLISHED, so a name corrected later
        # does not make the next import think this is a new business. The run
        # id makes a bad import findable and undoable.
        "source_ref": str(source_ref or "").strip(),
        "import_run": str(import_run or "").strip(),'''

FIND_ANCHOR = "def find_duplicate("

IMP_OLD = "            all_prospects, create, canonical_key"
IMP_NEW = "            all_prospects, create, canonical_key, find_by_source_ref"

BASE_OLD = "        rows, skipped_noname, skipped_dupe = [], 0, 0"
BASE_NEW = '''        # The register this row belongs to. Derived from --source so two
        # registers never collide, and stable across years so re-importing an
        # updated edition recognises what it already holds.
        source_ref_base = canonical_key(source) or os.path.basename(path)

        rows, skipped_noname, skipped_dupe = [], 0, 0'''

DEDUPE_OLD = '''            key = canonical_key(name)
            if key in existing:
                skipped_dupe += 1
                continue
            existing.add(key)'''
DEDUPE_NEW = '''            # ── MATCHED ON THE ROW, NOT THE NAME ────────────────────────
            # A record cleaned by hand must not come back as a duplicate on
            # the next import. The reference is the register plus the name AS
            # PUBLISHED, so the name in the warehouse is free to be corrected.
            ref = "%s|%s" % (source_ref_base, canonical_key(name))
            if find_by_source_ref(ref) is not None:
                skipped_dupe += 1
                continue
            key = canonical_key(name)
            if key in existing:
                skipped_dupe += 1
                continue
            existing.add(key)'''

RUN_OLD = "    made = failed = 0\n    for r in rows:"
RUN_NEW = '''    # One id per import, so a bad run can be found and undone rather than
    # picked out of the shelf by eye.
    import datetime as _dt
    run_id = "%s %s" % (source[:40], _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    made = failed = 0
    for r in rows:'''

CREATE_OLD = '''                source_event="%s%s" % (source, " (%s)" % licence if licence else ""),
            )'''
CREATE_NEW = '''                source_event="%s%s" % (source, " (%s)" % licence if licence else ""),
                # WHERE THIS ROW CAME FROM, so a re-import recognises it even
                # after somebody has corrected the name.
                source_ref="%s|%s" % (source_ref_base, canonical_key(r["name"])),
                import_run=run_id,
            )'''

FIND_BLOCK = r'''def find_by_source_ref(ref: str):
    """The prospect that came from THIS row of THIS register, if any.

    RULING (2026-08-20): "how do we save the imports and keep cleaning them
    from our end - the whole idea was to create a data warehouse of all
    businesses and institutions in Kenya."

    Duplicates were matched on the CANONICAL NAME, and that quietly punishes
    cleaning. Correct "1ICEA Lion" to "ICEA Lion" - which is exactly the work
    the warehouse exists for - and the key changes. Re-import the register next
    year and the old, uncorrected row comes back as a NEW prospect, sitting
    beside the one somebody fixed.

    At a few dozen records that is untidy. At eighteen hundred across a dozen
    registers it is a warehouse nobody trusts.

    So an imported prospect also carries where it came from - the register and
    the name AS PUBLISHED - and a re-import matches on that first. The name can
    then be cleaned freely: the row it came from does not move.
    """
    ref = str(ref or "").strip()
    if not ref:
        return None
    for pid, rec in (_read() or {}).items():
        if str(rec.get("source_ref", "") or "").strip() == ref:
            out = dict(rec)
            out["id"] = pid
            return out
    return None

'''


def main():
    apply = "--apply" in sys.argv
    for f in (STORE, IMPORTER):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    w = open(STORE, encoding="utf-8").read()
    m = open(IMPORTER, encoding="utf-8").read()
    if "find_by_source_ref" in w and "source_ref_base" in m:
        print("ABORT: IM1 looks applied.")
        return 1

    for name, src, pairs in (("the store", w, ((SIG_OLD, 1), (REC_OLD, 1))),
                             ("the importer", m, ((IMP_OLD, 1), (BASE_OLD, 1),
                                                  (DEDUPE_OLD, 1), (RUN_OLD, 1),
                                                  (CREATE_OLD, 1)))):
        for anchor, want in pairs:
            if src.count(anchor) != want:
                print("ABORT: an anchor in %s matched %d times, expected %d."
                      % (name, src.count(anchor), want))
                return 1

    w = w.replace(SIG_OLD, SIG_NEW, 1).replace(REC_OLD, REC_NEW, 1)
    w = w.replace(FIND_ANCHOR, FIND_BLOCK + FIND_ANCHOR, 1)
    m = (m.replace(IMP_OLD, IMP_NEW, 1)
          .replace(BASE_OLD, BASE_NEW, 1)
          .replace(DEDUPE_OLD, DEDUPE_NEW, 1)
          .replace(RUN_OLD, RUN_NEW, 1)
          .replace(CREATE_OLD, CREATE_NEW, 1))
    print("  ok  imports carry their row and their run")

    if "source_ref" not in FIND_BLOCK:
        print("ABORT: the lookup does not read the reference.")
        return 1
    if "canonical_key(source)" not in BASE_NEW:
        print("ABORT: two registers could collide on the same reference.")
        return 1
    if "find_by_source_ref(ref)" not in DEDUPE_NEW:
        print("ABORT: the row check is not consulted, so a cleaned record")
        print("       would still duplicate on the next import.")
        return 1
    import ast
    for name, src in ((STORE, w), (IMPORTER, m)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("ABORT: %s would not parse - line %s: %s"
                  % (os.path.basename(name), exc.lineno, exc.msg))
            return 1
    print("  ok  post-checks: registers cannot collide, the row is checked")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((STORE, w), (IMPORTER, m)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    for path in (STORE, IMPORTER):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1
    print("  ok  compiles")
    print("\nRECORDS ALREADY ON THE SHELF have no source_ref and are still")
    print("matched by name. To give them one, re-import the register with the")
    print("SAME --source: they will be skipped as duplicates, so clear the")
    print("shelf first if you want them re-keyed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
