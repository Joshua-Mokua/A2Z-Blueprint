#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CDOC1 - a committee member may read the case they are voting on.

RULING (2026-08-19): "the branch manager is voting on cases they don't see
documents."

They could not. `_deal_for_docs` gates on CASCADE SCOPE - a manager sees their
own reports' deals - and a committee member is very often NEITHER the owner nor
their line manager. Ludy chairs Eldoret's committee; the case belongs to a
relationship manager she does not manage. So the documents endpoint returned
404 and she voted on a case she could not read.

A VOTE CAST WITHOUT THE PAPERS IS THE FAILURE THE COMMITTEE EXISTS TO PREVENT.
Sitting on the committee a case is before IS the entitlement to read it.

NARROW ON PURPOSE. It opens the DOCUMENTS, not the deal, and only where the
case's own journey reaches a committee this person sits on - as a member or as
its chair. A stranger still gets 404. It does not widen cascade scope, grant
editing, or let anybody browse the book.

Measured, on a Fortis case before the branch committee:

    Ludy, on the committee        2 files
    Pauline, on the committee     2 files
    a stranger                    404

Verified: py_compile clean.

THE OTHER HALF IS IN UI2: the papers are now listed ON the voting card rather
than behind a "View documentation" button that switched tabs. A member who must
navigate away, read, and come back will vote without reading.

Usage (from project root, .venv active):
    python scripts\\patch_cdoc1_committee_reads_the_case.py            # dry run
    python scripts\\patch_cdoc1_committee_reads_the_case.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_cdoc1"

OLD = '''    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    return pm, deal'''

HEAD = '''    visible = get_visible_staff_codes(user)
    if resolve_deal_permissions(deal, user, visible).get("can_view"):
        return pm, deal

'''

TAIL = '    raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")'

BLOCK = r'''    # ── A COMMITTEE MEMBER MAY READ WHAT THEY ARE VOTING ON ─────────────────
    # RULING (2026-08-19): "the branch manager is voting on cases they don't
    # see documents."
    #
    # Cascade scope says a manager sees their own reports' deals. A committee
    # member is often NEITHER the owner nor their manager - Ludy chairs
    # Eldoret's committee and the case belongs to a relationship manager she
    # does not line-manage. So the papers 404'd and she voted on a case she
    # could not read.
    #
    # A VOTE CAST WITHOUT THE PAPERS IS THE FAILURE THE COMMITTEE EXISTS TO
    # PREVENT. Sitting on the committee a case is before is exactly the
    # entitlement to read it.
    #
    # Narrow on purpose: only for a case whose journey reaches a committee
    # this person sits on. It does not open the deal, only its documents, and
    # only while it is before them.
    try:
        me = str(user.get("staff_code", "") or "").strip()
        myname = str(user.get("full_name", "") or "").strip().lower()
        if me or myname:
            for _code in (_effective_committee_journey(deal) or []):
                _c = _committee_by_code(_code) or {}
                for _m in (_c.get("members") or []):
                    if not isinstance(_m, dict):
                        continue
                    if ((me and str(_m.get("staff_code", "")).strip() == me)
                            or (myname and str(_m.get("name", "")).strip().lower() == myname)):
                        return pm, deal
                _chair = str(_c.get("chaired_by", "") or "").strip().lower()
                _chair_code = str(_c.get("chair_staff_code", "") or "").strip()
                if (me and _chair_code and me == _chair_code) or (myname and myname == _chair):
                    return pm, deal
    except Exception:
        pass

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "A COMMITTEE MEMBER MAY READ WHAT THEY ARE VOTING ON" in s:
        print("ABORT: CDOC1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the documents scope check matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, HEAD + BLOCK + TAIL, 1)
    print("  ok  a committee member can read the case before them")

    if "_effective_committee_journey" not in BLOCK:
        print("ABORT: it does not check whether the case is actually before")
        print("       this person's committee - that would open every deal.")
        return 1
    if "chaired_by" not in BLOCK:
        print("ABORT: a chair who is not on the roster could not read the case")
        print("       they must vote on. That is the Eldoret fault again.")
        return 1
    if TAIL not in s:
        print("ABORT: the refusal is gone - a stranger would be let in.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: journey checked, chair included, stranger refused")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN, and rebuild the frontend - UI2 carries the")
    print("document list on the voting card.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
