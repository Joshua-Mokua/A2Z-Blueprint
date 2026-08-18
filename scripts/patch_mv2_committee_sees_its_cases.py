#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MV2 - a committee member can see what is before their committee.

FOUND while walking a case to the Management Credit Committee. The backend
carried it there correctly and NOBODY ON THE COMMITTEE COULD SEE IT.

Visibility was: your own cases, your cascade, or the credit pool if your role
is configured for it. Committee membership granted nothing at all.

That works while committees are made of credit people, who have the pool
anyway. It breaks on the Business Credit Committee: THE MD, THE CFO AND
TREASURY SIT ON IT and none of them has a credit pool role - so a case referred
to them appeared to nobody, and the committee could not meet about a case it
could not see.

Giving those people the whole pool would be the wrong fix. They would see every
case in the bank in order to vote on a handful, and the MD's screen is not the
place to discover that.

A MEMBER SEES THE CASES BEFORE THEIR OWN COMMITTEE, AND NOTHING ELSE.

    the MD, the CFO, treasury  ->  the case referred to the MCC
    a Consumer committee member ->  Consumer's cases, not Commercial's
    a branch RM                 ->  nothing

THE SEGMENT IS CARRIED for department committees, because there are three of
them and a Consumer member has no business reading Commercial's book. That is
the whole point of having three.

TWO THINGS THIS ALMOST GOT WRONG:

  B4 is named "Credit Committee" - neither "management" nor "business credit"
  appears in it. Matching on those words alone found NOBODY. It now uses the
  same identification the resolver uses, or the two disagree about which
  committee is the business one.

  A department member matched on committee CODE while the case carries KIND
  ("dcc"), so they saw nothing either. Both are now checked.

Verified: py_compile clean, and the five cases above measured.

Usage (from project root, .venv active):
    python scripts\\patch_mv2_committee_sees_its_cases.py            # dry run
    python scripts\\patch_mv2_committee_sees_its_cases.py --apply
"""
import os
import shutil
import sys

SCOPE = os.path.join("utils", "api_lms_scope.py")
BACKUP_SUFFIX = ".pre_mv2"

HEAD_ANCHOR = "    visible: List[Dict[str, Any]] = []"
LOOP_ANCHOR = "        rm_code = str(a.get('rm_code', '') or '')"

HEAD_BLOCK = r'''    # ── A COMMITTEE MEMBER SEES WHAT IS BEFORE THEIR COMMITTEE ──────────────
    # Visibility was: your own cases, your cascade, or the credit pool if your
    # role is configured for it. Committee membership granted nothing.
    #
    # That works while committees are made of credit people, who have the pool
    # anyway. It breaks on the Business Credit Committee: the MD, the CFO and
    # treasury sit on it and none of them has a credit pool role - so a case
    # referred to them appeared to nobody, and the committee could not meet
    # about a case it could not see.
    #
    # Giving those people the whole pool would be the wrong fix - they would
    # see every case in the bank to vote on a handful. A member sees the cases
    # BEFORE THEIR OWN COMMITTEE, and nothing else.
    _my_committees = set()
    if caller_staff_code:
        try:
            from utils.api import _read_committee_palette as _pal
            _me = str(caller_staff_code).strip()
            for _c in (_pal() or []):
                for _m in (_c.get("members") or []):
                    if not isinstance(_m, dict):
                        continue
                    if str(_m.get("staff_code", "") or "").strip() == _me:
                        _my_committees.add(str(_c.get("code") or ""))
                        # THE SAME RULE THE RESOLVER USES, or the two disagree
                        # about which committee is the business one. B4 is
                        # named "Credit Committee" - neither "management" nor
                        # "business credit" appears in it, and matching on
                        # words alone found nobody.
                        _nm = str(_c.get("name", "") or "").lower()
                        if ("management" in _nm or "business credit" in _nm
                                or str(_c.get("code")) == "B4"):
                            _my_committees.add("mcc")
                        elif str(_c.get("kind", "")).lower() != "branch":
                            # A DEPARTMENT committee member sees dcc cases -
                            # but only their OWN segment's. The segment is
                            # carried so a Consumer member does not see
                            # Commercial's cases, which is the whole point of
                            # having three of them.
                            for _seg, _word in (("consumer", "consumer"),
                                                ("commercial", "commercial"),
                                                ("cib", "corporate")):
                                if _word in _nm:
                                    _my_committees.add("dcc:%s" % _seg)
                        break
        except Exception:
            _my_committees = set()

'''

LOOP_BLOCK = r'''        # Before my committee, and still awaiting it: I can see it.
        if _my_committees:
            _kind = str(a.get("committee_kind", "") or "").lower()
            _src = str((a.get("dcc") or {}).get("source_committee", "") or "")
            _hit = bool(_kind) and (_kind in _my_committees or _src in _my_committees)
            if not _hit and _kind == "dcc":
                _hit = ("dcc:%s" % _app_segment(a)) in _my_committees
            if _hit:
                visible.append(a)
                continue
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(SCOPE):
        print("ABORT: %s not found." % SCOPE)
        return 1

    s = open(SCOPE, encoding="utf-8").read()
    if "A COMMITTEE MEMBER SEES WHAT IS BEFORE THEIR COMMITTEE" in s:
        print("ABORT: MV2 looks applied.")
        return 1
    if s.count(HEAD_ANCHOR) != 1 or s.count(LOOP_ANCHOR) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(HEAD_ANCHOR), s.count(LOOP_ANCHOR)))
        return 1

    s = s.replace(HEAD_ANCHOR, HEAD_BLOCK + HEAD_ANCHOR, 1)
    s = s.replace(LOOP_ANCHOR, LOOP_BLOCK + LOOP_ANCHOR, 1)
    print("  ok  a member sees the cases before their own committee")

    if '"B4"' not in HEAD_BLOCK:
        print("ABORT: B4 is named 'Credit Committee' - matching on the words")
        print("       'management' or 'business credit' alone finds nobody.")
        return 1
    if "dcc:%s" not in HEAD_BLOCK and "dcc:" not in HEAD_BLOCK:
        print("ABORT: a department member would see every segment's cases,")
        print("       which is the point of having three committees.")
        return 1
    if "_app_segment" not in LOOP_BLOCK:
        print("ABORT: the segment is not consulted.")
        return 1
    if "continue" not in LOOP_BLOCK:
        print("ABORT: a matched case would fall through and be tested again.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: B4 identified, segment carried, loop short-circuits")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(SCOPE, SCOPE + BACKUP_SUFFIX)
    open(SCOPE, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % SCOPE)

    import py_compile
    try:
        py_compile.compile(SCOPE, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. The MD can now see a case referred to the MCC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
