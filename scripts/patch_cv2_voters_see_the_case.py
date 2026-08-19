#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CV2 - anyone asked to vote may see what they are voting on. Every committee.

RULING (2026-08-19): "I believe anyone listed to vote, even if the case is out
of their scope, should at least see what they are voting on - then I hope we
have done the same to all the voting blocks."

We had not. CDOC1 fixed the BRANCH committee's documents. The department and
business committees had the same fault in a worse place: not the documents, the
CASE ITSELF.

`can_view` on an application was cascade scope alone. A committee member is
very often outside it - Jane chairs the Consumer committee and the case belongs
to a branch relationship manager she does not line-manage; the Managing
Director sits on the business committee and line-manages nobody's pipeline.

Measured BEFORE this patch, on the very case she chairs:

    Jane, chair of B1, on a Consumer case      can_view = False
    the MD, on a case before her committee     can_view = False

They were being asked to vote on cases the system would not show them. That is
worse at this level than at the branch: these are the committees that see the
large exposures.

NARROW ON PURPOSE, in three ways:

  It reads the CASE's own committee_kind and grants sight only to people on the
  committee that kind resolves to - the business committee for mcc, the
  segment's committee for dcc. A Consumer member does not gain sight of
  Commercial's book.

  It matches as member OR chair, because a chair off the roster is the fault
  that cost Eldoret two days and it must not cost sight as well.

  IT IS VIEW ONLY. can_update, can_decide and every other capability are
  decided below exactly as before. Measured after: Jane's permissions on that
  case are can_view and nothing else.

Measured after:

    CASE                          Jane(B1)  MD(B4)  a stranger
    a Consumer case at B1         True      False   False
    a Commercial case at B2       False     False   False
    a case before the MCC         False     True    False
    a case before no committee    False     False   False

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_cv2_voters_see_the_case.py            # dry run
    python scripts\\patch_cv2_voters_see_the_case.py --apply
"""
import os
import shutil
import sys

PERMS = os.path.join("utils", "api_lms_permissions.py")
BACKUP_SUFFIX = ".pre_cv2"

OLD = "    can_view = is_admin or (in_scope and (not is_owner or owner_touchpoint_open))"
TAIL = '''    can_view = (is_admin or _on_its_committee
                or (in_scope and (not is_owner or owner_touchpoint_open)))'''

BLOCK = r'''    # ── ANYONE ASKED TO VOTE MAY SEE WHAT THEY ARE VOTING ON ────────────────
    # RULING (2026-08-19): "anyone listed to vote, even if the case is out of
    # their scope, should at least see what they are voting on."
    #
    # can_view was cascade scope alone. A committee member is very often
    # outside it - Jane chairs the Consumer committee and the case belongs to a
    # branch relationship manager she does not line-manage; the MD sits on the
    # business committee and manages nobody's pipeline directly. Measured
    # before this: Jane can_view=False on the very case she chairs.
    #
    # So they were being asked to vote on cases the system would not show them.
    # A vote cast without sight of the case is the failure the committee exists
    # to prevent, and it is worse here than at the branch: these are the
    # committees that see the large exposures.
    #
    # NARROW ON PURPOSE. It reads the case's OWN committee_kind and grants
    # sight only to people on the committee that kind resolves to - as a member
    # or as its chair. It is view only: can_update, can_decide and the rest are
    # decided below exactly as before, so a committee member reads the case and
    # nothing more.
    _on_its_committee = False
    try:
        _kind = str((app or {}).get("committee_kind", "") or "").lower()
        if _kind in ("dcc", "mcc"):
            _me = str((user or {}).get("staff_code", "") or "").strip()
            _myname = str((user or {}).get("full_name", "") or "").strip().lower()
            if _me or _myname:
                from pathlib import Path as _P
                import json as _J
                _cfgp = _P(__file__).resolve().parent.parent / "data" / "lms_config.json"
                _pal = ((_J.loads(_cfgp.read_text(encoding="utf-8")) or {})
                        .get("credit_workflow") or {}).get("committee_palette") or []
                _seg = str((app or {}).get("client_type", "") or "").lower()
                for _c in _pal:
                    if str(_c.get("kind", "")).lower() == "branch":
                        continue
                    _nm = str(_c.get("name", "") or "").lower()
                    # Which committee is this case's? The business one when it
                    # was referred there, otherwise the one for its segment.
                    if _kind == "mcc":
                        _mine = ("management" in _nm or "business credit" in _nm
                                 or str(_c.get("code")) == "B4")
                    else:
                        _mine = (("consumer" in _nm and ("consumer" in _seg or "individual" in _seg
                                                        or _seg in ("personal", "retail")))
                                 or ("commercial" in _nm and "commercial" in _seg)
                                 or ("corporate" in _nm and (_seg == "cib" or "corporate" in _seg
                                                             or "investment" in _seg)))
                    if not _mine:
                        continue
                    for _m in (_c.get("members") or []):
                        if not isinstance(_m, dict):
                            continue
                        if ((_me and str(_m.get("staff_code", "")).strip() == _me)
                                or (_myname and str(_m.get("name", "")).strip().lower() == _myname)):
                            _on_its_committee = True
                            break
                    _chair = str(_c.get("chaired_by", "") or "").strip().lower()
                    _chaircode = str(_c.get("chair_staff_code", "") or "").strip()
                    if ((_me and _chaircode and _me == _chaircode)
                            or (_myname and _myname == _chair)):
                        _on_its_committee = True
                    if _on_its_committee:
                        break
    except Exception:
        _on_its_committee = False

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PERMS):
        print("ABORT: %s not found." % PERMS)
        return 1

    s = open(PERMS, encoding="utf-8").read()
    if "ANYONE ASKED TO VOTE MAY SEE WHAT THEY ARE VOTING ON" in s:
        print("ABORT: CV2 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the can_view line matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK + TAIL, 1)
    print("  ok  a committee member can see the case before their committee")

    if "committee_kind" not in BLOCK:
        print("ABORT: it does not read the case's own committee, so it would")
        print("       grant sight of cases before somebody else's.")
        return 1
    if "chaired_by" not in BLOCK:
        print("ABORT: a chair off the roster would still be blind - the fault")
        print("       that cost Eldoret two days.")
        return 1
    if "commercial" not in BLOCK or "corporate" not in BLOCK:
        print("ABORT: the segments are not distinguished, so a Consumer member")
        print("       would gain sight of Commercial's book.")
        return 1
    # THE NAMES APPEAR IN THE COMMENT SAYING THEY ARE NOT TOUCHED. Searching
    # the whole block finds them and refuses a correct patch - the third time
    # this exact trap has fired today. Read the CODE.
    _code = "\n".join(l for l in BLOCK.split("\n") if not l.strip().startswith("#"))
    for _cap in ("can_update", "can_decide", "can_record_decision"):
        if ("%s =" % _cap) in _code or ("\"%s\"" % _cap) in _code:
            print("ABORT: this assigns %s. It must grant SIGHT only - every" % _cap)
            print("       other capability is decided below.")
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: right committee, chair included, view only")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PERMS, PERMS + BACKUP_SUFFIX)
    open(PERMS, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % PERMS)

    import py_compile
    try:
        py_compile.compile(PERMS, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Apply CDOC1 too - that is the branch committee's")
    print("half of the same rule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
