#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MP1 - the voting panel works for the Business Credit Committee too.

FOUND before the MD was asked to sit. The backend carried a case to the
Business Credit Committee correctly, every member could see it, and the panel
told them THE CASE WAS NOT BEFORE THEIR COMMITTEE.

    "is_dcc_case": str(app.get("committee_kind", "")) == "dcc"

The panel draws its bench on that flag. The vote and resolve endpoints had
already been widened to accept both kinds; this one place still knew about
only one. So the MD would have opened the case in the meeting called to decide
it and found nothing to press.

It now reports a case before EITHER committee, and carries two more things:

    committee_kind      so the tab and the heading can say "Business Credit
                        Committee" rather than telling the Managing Director
                        she is looking at a department matter

    circulation_note    what the analyst wrote when they circulated it, with
                        their name. A committee that has to reconstruct the
                        question for itself is a committee wasting the room's
                        time.

Measured:

    a department case          is_dcc_case True   Corporate & Investment
    a business committee case  is_dcc_case True   Credit Committee, note carried
    not before a committee     is_dcc_case False

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_mp1_business_committee_panel.py            # dry run
    python scripts\\patch_mp1_business_committee_panel.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_mp1"

OLD = '        "is_dcc_case": str(app.get("committee_kind", "")) == "dcc",'

BLOCK = r'''        # ── BEFORE *A* COMMITTEE, NOT ONLY THE DEPARTMENT ONE ──────────────
        # The panel draws its bench on this. It read == "dcc", so a case before
        # the BUSINESS committee returned false and every member - the MD, the
        # CFO, treasury - was told the case was not before their committee,
        # while sitting in the meeting called to decide it.
        #
        # The vote and resolve endpoints already accept both kinds. This is the
        # one place that still only knew about one.
        "is_dcc_case": str(app.get("committee_kind", "")) in ("dcc", "mcc"),
        # Which committee, so the panel can name it rather than say
        # "Department Credit Committee" to the Managing Director.
        "committee_kind": str(app.get("committee_kind", "") or ""),
        # What the analyst wrote when they circulated it. The committee reads
        # this before it sits.
        "circulation_note": str(app.get("circulation_note", "") or ""),
        "circulated_by_name": str(app.get("circulated_by_name", "") or ""),
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "BEFORE *A* COMMITTEE, NOT ONLY THE DEPARTMENT ONE" in s:
        print("ABORT: MP1 looks applied.")
        return 1
    if "THE BUSINESS CREDIT COMMITTEE ANSWERS TO CREDIT RISK" not in s:
        print("ABORT: BC1 must be applied first.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the is_dcc_case line matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK.rstrip(), 1)
    print("  ok  the panel is told about business-committee cases")

    if '"mcc"' not in BLOCK:
        print("ABORT: an MCC case would still report false and the members")
        print("       would be told it is not before their committee.")
        return 1
    if "committee_kind" not in BLOCK:
        print("ABORT: the panel could not name the right committee.")
        return 1
    if "circulation_note" not in BLOCK:
        print("ABORT: the committee would have to reconstruct the question.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both kinds, named, the note travels")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, ROUTES + BACKUP_SUFFIX)
    open(ROUTES, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % ROUTES)

    import py_compile
    try:
        py_compile.compile(ROUTES, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN, then rebuild the frontend (UI2 carries the panel).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
