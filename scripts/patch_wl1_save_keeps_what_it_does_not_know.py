#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WL1 - saving a committee keeps the fields the form does not send.

FOUND BY ALEX (2026-09-04) while a sweep refused to close D0682: B1's
chair_vote_required had silently reverted to unset. The cause is the admin
save:

    norm = {
        "code": ..., "name": ..., "chaired_by": ..., "branch": ...,
        "kind": ..., "recording_mode": ..., "voting_rule": ...,
        "amount_threshold_kes": ...,
        "members": [{"name", "role", "staff_code", "full_funnel"}],
    }

IT REBUILDS THE COMMITTEE FROM A FIXED LIST and writes that over the stored
one. Any field the list does not name is DROPPED - so an admin editing an
unrelated thing, or the screen re-posting what it loaded, silently erased:

    chair_vote_required   the committee could no longer close without its chair
    deputy_chair          on every member - the named deputy stopped existing
    min_quorum_count      any quorum override went back to the default

Nobody did anything wrong and nothing said a word. A setting made deliberately
on Tuesday was gone on Thursday.

ALEX HAS FIXED THIS ON THE PILOT. This is the same fix on main, and it is
URGENT for a reason that is easy to miss: THE NEXT RELEASE WOULD REPLAY THE OLD
VERSION OVER HIS. A patcher that writes a whole function does not know it is
undoing something, and the loss would be silent a second time.

WHAT THIS CHANGES: unknown keys are carried forward from what is already
stored, rather than dropped. The named fields are still normalised - a
voting_rule is still coerced to a string, an amount to a float - so nothing
about validation loosens. What changes is that a field nobody mentioned
survives.

THE SAME FOR MEMBERS, keyed on staff code, so deputy_chair and anything added
later travels with the person it belongs to.

Usage (from project root, .venv active):
    python scripts\patch_wl1_save_keeps_what_it_does_not_know.py            # dry run
    python scripts\patch_wl1_save_keeps_what_it_does_not_know.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip(),
             "staff_code": str(m.get("staff_code", "") or "").strip(),
             "full_funnel": bool(m.get("full_funnel", False))}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],
    }
    replaced = False'''

NEW = '''        "members": [
            {"name": str(m.get("name", "")).strip(), "role": str(m.get("role", "")).strip(),
             "staff_code": str(m.get("staff_code", "") or "").strip(),
             "full_funnel": bool(m.get("full_funnel", False))}
            for m in (c.get("members", []) or []) if isinstance(m, dict)
        ],
    }

    # ── KEEP WHAT THIS FUNCTION DOES NOT KNOW ABOUT ─────────────────────────
    # FOUND 2026-09-04: a sweep would not close D0682 because B1's
    # chair_vote_required had reverted to unset. Nobody changed it. The rebuild
    # above names eight fields and writes the result over the stored committee,
    # so ANY field it does not name is dropped - and an admin editing something
    # unrelated erased, silently:
    #
    #     chair_vote_required   the committee could no longer close without
    #                           its chair
    #     deputy_chair          on every member - the named deputy vanished
    #     min_quorum_count      a quorum override went back to the default
    #
    # A whitelist that is not updated when a feature is added quietly deletes
    # that feature's settings. The named fields above are still normalised;
    # what changes is that an unnamed one survives.
    _prev = next((x for x in palette
                  if str(x.get("code")) == code and isinstance(x, dict)), None)
    if _prev:
        for _k, _v in _prev.items():
            if _k not in norm:
                norm[_k] = _v
        # And per member, keyed on staff code, so deputy_chair travels with the
        # person it belongs to rather than with their position in a list.
        _was = {str(m.get("staff_code", "") or "").strip(): m
                for m in (_prev.get("members") or []) if isinstance(m, dict)}
        for _m in norm["members"]:
            _old = _was.get(str(_m.get("staff_code", "") or "").strip())
            if not isinstance(_old, dict):
                continue
            for _k, _v in _old.items():
                if _k not in _m:
                    _m[_k] = _v

    replaced = False'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "KEEP WHAT THIS FUNCTION DOES NOT KNOW ABOUT" in s:
        print("ABORT: WL1 looks applied.")
        return 1

    # THE PILOT FIXED THIS FIRST, with a NAMED carry list:
    #     for _carry in ("chair_vote_required", "min_quorum_count", "quorum"):
    # That solves the three fields it names. It is still a whitelist, so the
    # next feature's setting will be dropped the same way - but applying this
    # on top would give that tree two carry-forward blocks doing the same job,
    # and a release that quietly duplicates somebody's fix is worse than one
    # that leaves it alone.
    _i = s.find('@app.post("/api/admin/committee-palette", tags=')
    if _i > 0:
        _fn = s[_i:s.index("\n@app.", _i + 10)]
        if "_carry in (" in _fn or "existing_members" in _fn:
            print("ABORT: this tree already carries fields forward (the pilot's")
            print("       named-list fix). Leaving it alone rather than adding a")
            print("       second block that does the same job.")
            print("\n  WORTH KNOWING: that fix names three fields, so a setting")
            print("  added later is dropped again. Widening it to carry every")
            print("  unknown field is the durable version.")
            return 1
    if s.count(OLD) != 1:
        print("ABORT: the committee rebuild matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a field the form does not send is kept, not dropped")

    # The whole point: an unnamed field must survive.
    if "if _k not in norm" not in NEW:
        print("ABORT: unknown fields would still be dropped.")
        return 1
    # Members must be matched on staff code, not on list position - a reordered
    # list would otherwise move a deputy flag onto somebody else.
    if 'staff_code' not in NEW.split("_was =")[1][:200]:
        print("ABORT: members are not keyed on staff code. A reordered list")
        print("       would move deputy_chair onto the wrong person.")
        return 1
    # And normalisation must remain - this keeps extras, it does not stop
    # coercing the fields it does name.
    if '"voting_rule": str(' not in s:
        print("ABORT: the named fields are no longer normalised.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: keyed on staff code, normalisation intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_wl1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Settings already lost are not restored by this -")
    print("re-apply them once, and they will survive from now on.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
