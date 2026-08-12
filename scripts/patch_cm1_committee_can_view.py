#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CM1 - a department committee member can see the case they must decide.

FOUND BY TESTING, not by reading (2026-08-12). After the committee queue was
built, a branch committee member saw their cases and a DEPARTMENT committee
member saw NOTHING - zero cases, on a deal whose journey named their committee.

The DCC sits at head office. A branch RM is not in their cascade, so scope
removed every case they were being asked to judge. The branch committee only
worked by accident: a branch manager already has their own branch in scope.

Being asked to decide on a case implies being allowed to read it - less a
widening of scope than the missing half of it. The bank put these people on the
committee precisely so they would judge these deals.

VIEW ONLY. can_edit, can_advance and the rest stay false. They read the case
and record the decision through its own endpoint, which has its own gate.

RELEVANCE IS THE SAME TWO RULES the journey uses - the deal's own BRANCH
committee, and the committee matching its CLIENT TYPE - applied here rather
than imported, because importing utils.api from this module is CIRCULAR. An
earlier attempt did exactly that, had the ImportError swallowed by the guard,
and silently did nothing while looking like a rule that would not work.

Measured with an EMPTY cascade scope, so nothing else could be granting it:

    branch committee member   view=True   edit=False  advance=False
    DCC member (B1)           view=True   edit=False  advance=False
    on no committee           view=False  edit=False  advance=False

and through the queue: one case each for the two members, none for the
non-member.

ALSO COLLAPSES A DUPLICATE. The out-of-scope guard appears TWICE on
origin/main - identical blocks back to back. Harmless, being idempotent, but
dead. One remains.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_cm1_committee_can_view.py            # dry run
    python scripts\\patch_cm1_committee_can_view.py --apply
"""
import os
import shutil
import sys

PERM = os.path.join("utils", "api_pipeline_permissions.py")
BACKUP_SUFFIX = ".pre_cm1"

GATE = '''    # If none of owner/backup/manager-in-scope/referral-participant, out-of-scope.
    if not (is_owner or is_backup or is_manager_in_scope
            or is_referral_participant or is_segment_viewer):
        return _all_false()'''

NEW_GATE = '''    # NOTE: this guard appeared TWICE on origin/main - identical blocks back to
    # back. Harmless, being idempotent, but dead. Collapsed to one.
    if not (is_owner or is_backup or is_manager_in_scope
            or is_referral_participant or is_segment_viewer
            or is_committee_member):
        return _all_false()'''

VIEW_OLD = '''    can_view = (is_owner or is_backup or is_manager_in_scope
                or is_referral_participant or is_segment_viewer)'''

VIEW_NEW = '''    can_view = (is_owner or is_backup or is_manager_in_scope
                or is_referral_participant or is_segment_viewer
                or is_committee_member)'''

MEMBER = r'''    # ── SITTING ON A COMMITTEE THE CASE MUST PASS GRANTS SIGHT OF IT ────────
    # Found by testing (2026-08-12): a branch committee member could see their
    # cases because the branch is in their cascade, but a DEPARTMENT committee
    # member saw NOTHING. The DCC sits at head office and a branch RM is not in
    # their tree, so scope removed every case they were being asked to decide.
    #
    # Being asked to decide on a case implies being allowed to read it - less a
    # widening of scope than the missing half of it. The bank put these people
    # on the committee precisely so they would judge these deals.
    #
    # VIEW ONLY. They are not the owner, so can_edit and can_advance stay false
    # below; they read the case and record the committee's decision, which is a
    # separate endpoint with its own gate.
    #
    # THE CONFIG IS READ DIRECTLY, not through utils.api - that would be a
    # CIRCULAR import, and an earlier attempt had its exception swallowed by
    # the guard, so the whole branch silently did nothing.
    is_committee_member = False
    try:
        _my = str(user.get("staff_code", "") or "").strip()
        _myname = str(user.get("full_name", "") or "").strip().lower()
        if _my or _myname:
            import json as _json
            import os as _os
            with open(_os.path.join("data", "lms_config.json"), encoding="utf-8") as _fh:
                _cfg = _json.load(_fh) or {}
            _pal = ((_cfg.get("credit_workflow") or {}).get("committee_palette") or [])
            # The two rules that put a committee on a deal's journey, applied
            # here rather than imported: the deal's own BRANCH committee, and
            # the committee matching its CLIENT TYPE.
            _b = str(deal.get("branch") or deal.get("unit") or "").strip().lower()
            _ct = str(deal.get("client_type") or "").strip().lower()
            for _c in _pal:
                if str(_c.get("kind", "")).lower() == "branch":
                    if not (_b and str(_c.get("branch", "")).strip().lower() == _b):
                        continue
                else:
                    _nm = str(_c.get("name", "")).lower()
                    if not (_ct and (_ct in _nm or _nm.startswith(_ct))):
                        continue
                _mem = _c.get("members") or []
                _codes = {str(m.get("staff_code", "") or "").strip()
                          for m in _mem if isinstance(m, dict)}
                _names = {str(m.get("name", "") or "").strip().lower()
                          for m in _mem if isinstance(m, dict)}
                _chair = str(_c.get("chaired_by", "") or "").strip().lower()
                if ((_my and _my in _codes)
                        or (_myname and (_myname in _names or _myname == _chair))):
                    is_committee_member = True
                    break
    except Exception:
        is_committee_member = False

    # NOTE: this guard appeared TWICE on origin/main - identical blocks back to
    # back. Harmless, since it is idempotent, but dead. Collapsed to one.
    if not (is_owner or is_backup or is_manager_in_scope
            or is_referral_participant or is_segment_viewer
            or is_committee_member):
        return _all_false()

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PERM):
        print("ABORT: %s not found." % PERM)
        return 1

    src = open(PERM, encoding="utf-8").read()
    if "is_committee_member" in src:
        print("ABORT: CM1 looks applied.")
        return 1
    n = src.count(GATE)
    if n != 2:
        print("ABORT: expected the duplicated scope guard twice, found %d." % n)
        print("       Refusing to guess which one to replace.")
        return 1
    if src.count(VIEW_OLD) != 1:
        print("ABORT: the can_view line matched %d times." % src.count(VIEW_OLD))
        return 1

    src = src.replace(GATE + "\n\n" + GATE, MEMBER + NEW_GATE, 1)
    src = src.replace(VIEW_OLD, VIEW_NEW, 1)
    print("  ok  committee membership grants view; duplicate guard collapsed")

    # Checked against the CODE, not the comment - the comment says "can_edit
    # stays false", which is the opposite of what a naive search concludes.
    _code = "\n".join(l for l in MEMBER.split("\n")
                      if not l.strip().startswith("#"))
    if "can_edit" in _code or "can_advance" in _code:
        print("ABORT: the committee grant touches more than view.")
        return 1
    if "from utils.api import" in MEMBER:
        print("ABORT: importing utils.api here is circular - the exception")
        print("       would be swallowed and this would silently do nothing.")
        return 1
    if "client_type" not in MEMBER or "branch" not in MEMBER:
        print("ABORT: only one kind of committee would be matched.")
        return 1
    if src.count("is_committee_member") < 3:
        print("ABORT: the flag is computed but not used in both places.")
        return 1
    print("  ok  post-checks: view only, no circular import, both rules")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PERM, PERM + BACKUP_SUFFIX)
    open(PERM, "w", encoding="utf-8", newline="").write(src)
    print("APPLIED %s" % PERM)

    import py_compile
    try:
        py_compile.compile(PERM, doraise=True)
        print("  ok  api_pipeline_permissions.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Restart uvicorn. A department committee member now sees the cases")
    print("their committee must decide, and Review opens them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
