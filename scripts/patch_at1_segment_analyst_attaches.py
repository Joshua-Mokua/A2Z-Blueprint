#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AT1 - the segment's analyst may attach papers to the segment's cases.

FROM THE PILOT (2026-08-25): the Consumer credit analyst tries to attach the
CRB report and the call memo and gets

    403  Only somebody working this case can attach documents to it.

THE GATE ASKS WHETHER SHE IS THE ASSIGNED ANALYST ON THAT CASE:

    can_edit or can_submit_to_dcc or can_decide or is_assigned_analyst

and is_assigned_analyst is an exact match of her staff code against
app["analyst"]["code"]. A case that has not yet been assigned to her - or was
assigned to a colleague covering - refuses her papers.

THAT IS THE WRONG QUESTION. The ruling is that "the analysts should be allowed
to introduce and upload documents along the journey" - the analyst FOR THE
SEGMENT, not only the one whose name is on the case. A CRB report is not a
decision; it is evidence, and evidence arriving early is the point.

WHAT THIS ADDS: a fifth way through the gate - the caller's segment matches
the case's segment. Nothing else changes.

    consumer analyst   -> consumer cases
    commercial analyst -> commercial cases
    cib analyst        -> cib cases

AN ANALYST WITH NO SEGMENT GETS NOTHING NEW. _analyst_segment returns "" for
anybody it cannot place - a Quality Analyst, a Business Analyst, a role the
register spells unusually - and "" must never match, or it would open every
case in the bank to them. The empty string is checked for explicitly rather
than relied upon to be falsy in the right direction.

A CASE WITH NO SEGMENT IS ALSO NOT MATCHED. _app_segment deliberately does not
map "Business", because a business customer may be Commercial or CIB and
guessing would put a corporate case in front of a consumer analyst. Those keep
the old behaviour: only somebody actually working them may attach.

THIS GRANTS ATTACHMENT ONLY. Deciding, submitting and editing are untouched -
a segment analyst who is not on the case still cannot move it.

Usage (from project root, .venv active):
    python scripts\patch_at1_segment_analyst_attaches.py            # dry run
    python scripts\patch_at1_segment_analyst_attaches.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_at1"

# THE ANCHOR IS READ FROM THE FILE, NOT ASSUMED.
# The first version hardcoded `can_edit` / `can_decide` / `is_assigned_analyst`,
# which is how the gate reads on the developer's box. On the pilot it reads
# `can_update` / `can_record_decision` and computes `_is_assigned_analyst` into
# a local. The patch matched zero times and stopped a release mid-replay.
#
# Two trees, one patch: match on the ONE line that is identical in both - the
# 403 detail string - and insert above the `if not (` that precedes it.
DETAIL = 'detail="Only somebody working this case can attach documents to it."'


BLOCK = '''    # ── THE SEGMENT'S ANALYST MAY BRING PAPERS ──────────────────────────────
    # RULING: "the analysts should be allowed to introduce and upload documents
    # along the journey in case they are there."
    #
    # The tests below ask whether this person is working THIS case. That is
    # right for deciding and submitting, and wrong for evidence: a CRB report
    # or a call memo is not a decision, and the Consumer analyst should not be
    # refused her own segment's paperwork because the case is assigned to a
    # colleague covering, or not yet assigned at all.
    #
    # BOTH SIDES MUST RESOLVE. An analyst the register cannot place returns ""
    # from _analyst_segment, and a case whose client_type is "Business" returns
    # "" from _app_segment - deliberately, because a business customer may be
    # Commercial or CIB and guessing would put a corporate case in front of a
    # consumer analyst. Neither empty string may match, or the gate would open
    # every case in the bank to somebody it could not identify.
    _seg_ok = False
    try:
        from utils.api_lms_scope import _analyst_segment, _app_segment
        _mine = (_analyst_segment(str(user.get("role", "") or ""),
                                  str(user.get("staff_code", "") or "")) or "")
        _theirs = (_app_segment(app) or "")
        _seg_ok = bool(_mine) and bool(_theirs) and _mine == _theirs
    except Exception as exc:  # surfaced, never silent (CGR1)
        logger.warning("segment check failed while attaching to %s: %s",
                       app_id, exc)

'''



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "THE SEGMENT'S ANALYST MAY BRING PAPERS" in s:
        print("ABORT: AT1 looks applied.")
        return 1
    if s.count(DETAIL) != 1:
        print("ABORT: the 403 message appears %d times - expected exactly one."
              % s.count(DETAIL))
        return 1

    # Walk BACK from the message to the `if not (` that guards it, and insert
    # above that. This works whichever names the permissions have.
    i = s.index(DETAIL)
    j = s.rfind("\n    if not (", 0, i)
    if j < 0:
        print("ABORT: could not find the guard above the 403 message.")
        return 1
    guard = s[j:i]
    if "raise HTTPException" not in guard:
        print("ABORT: the text between the guard and the message is not what")
        print("       was expected - refusing to insert blind.")
        return 1

    s = s[:j + 1] + BLOCK + s[j + 1:]
    print("  ok  the segment check is inserted above the attach guard")

    # And the guard itself must now consult it.
    i2 = s.index(DETAIL)
    j2 = s.rfind("\n    if not (", 0, i2)
    k2 = s.index("):", j2)
    cond = s[j2:k2]
    if "_seg_ok" not in cond:
        s = s[:k2] + "\n            or _seg_ok" + s[k2:]
        print("  ok  the guard consults it")

    if 'bool(_mine) and bool(_theirs)' not in BLOCK:
        print("ABORT: an unplaced analyst or an unsegmented case would match.")
        return 1
    if "logger.warning" not in BLOCK:
        print("ABORT: a failed segment check must say so.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: empty never matches, logged, parses")

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
    print("\nRESTART UVICORN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
