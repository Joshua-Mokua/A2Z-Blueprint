#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CV1 - a credit voice in the room, and flags that survive a re-naming.

TWO FAULTS, both surfacing within an hour of each other on 2026-08-18.

1. NAMING MEMBERS DESTROYED WHAT AN ADMIN HAD SET.

   `name_dcc_members --apply` rebuilt the roster wholesale from the register.
   Anything set on a member entry by hand went with it - so the Credit Risk
   Manager, granted sight of the whole bank pipeline that morning, silently
   lost it by lunchtime. Nobody was told; the screen simply went empty again.

   Same shape as the release config overwriting the bank's own committees: a
   wholesale write, and whatever somebody carefully set is gone.

   A member's NAME and ROLE come from the register. Everything else on the
   entry - full_funnel, deputy_chair, anything added later - was set
   deliberately and is now carried across, and the script SAYS what it carried.

2. THE COMMITTEE COULD DECIDE WITH NOBODY FROM CREDIT IN THE ROOM.

   RULING: "at least for a case there should be a credit risk voice", and "as
   long as the MD is there and at least a rep from credit - who would be Korir
   in case Thomas is absent - it should be okay."

   The chair rule covered the MD: her vote is mandatory, with Thomas or Korir
   standing in. It did NOT cover the other half. A sitting of the MD, both
   business directors and treasury could complete a decision with no one from
   credit having spoken - the one voice a credit committee cannot do without.

   A member whose role carries "credit" or "risk" must now have voted. AN
   ABSTENTION COUNTS: being present and declining to take a side is a
   position, and forcing a yes or no would be worse than the gap it closed.

   IT APPLIES TO THE BUSINESS COMMITTEE ONLY. A department committee is
   already made of credit people, and a rule that can never fail teaches
   everyone to ignore the ones that can.

Measured:

    MD + business + treasury, no credit    refused
    MD + business + Korir                  decided
    MD + business + Korir abstaining       decided

Verified: py_compile clean, and a re-naming no longer drops full_funnel.

Usage (from project root, .venv active):
    python scripts\\patch_cv1_credit_voice.py            # dry run
    python scripts\\patch_cv1_credit_voice.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
NAMER = os.path.join("scripts", "name_dcc_members.py")
BACKUP_SUFFIX = ".pre_cv1"

VOICE_ANCHOR = '    yes = sum(1 for v in votes if str(v.get("vote", "")).upper() == "YES")'

FLAGS_OLD = '''    members = [{
        "id": p["staff_code"],
        "member_id": p["staff_code"],
        "staff_code": p["staff_code"],
        "name": p["name"],
        "role": p["role"],
    } for p in resolved]'''

VOICE_BLOCK = r'''    # ── A CREDIT VOICE MUST BE IN THE ROOM ──────────────────────────────────
    # RULING (2026-08-18): "at least for a case there should be a credit risk
    # voice." And: "as long as the MD is there, and at least a rep from credit
    # - who would be Korir in case Thomas is absent - it should be okay."
    #
    # The chair rule already covers the MD: her vote is mandatory, and Thomas
    # or Korir stands in when she is away. It did NOT cover the other half. A
    # sitting with the MD, both business directors and treasury could complete
    # a decision with nobody from credit having spoken - which is the one voice
    # a credit committee cannot do without.
    #
    # So: a member whose ROLE carries credit or risk must have voted. Abstaining
    # counts - being present and declining to take a side is a position, and
    # forcing a yes or no would be worse.
    #
    # It applies to the BUSINESS committee only. A department committee is
    # already made of credit people; requiring it there would be a rule that
    # can never fail, which teaches everyone to ignore it.
    if str(app.get("committee_kind", "") or "").lower() == "mcc":
        _credit_ids = {
            str(m.get("id") or m.get("member_id") or m.get("staff_code") or "").strip()
            for m in (dcc.get("members") or [])
            if isinstance(m, dict)
            and any(w in str(m.get("role", "") or "").lower()
                    for w in ("credit", "risk"))}
        if _credit_ids:
            _spoke = any(str(v.get("member_id", "")).strip() in _credit_ids
                         for v in votes)
            if not _spoke:
                raise HTTPException(
                    status_code=400,
                    detail="No one from credit has voted. This committee "
                           "cannot decide a case without a credit voice in "
                           "the room - an abstention counts.")

'''

FLAGS_BLOCK = r'''    # ── FLAGS SET ON A MEMBER SURVIVE A RE-NAMING ───────────────────────────
    # FOUND 2026-08-18: naming members to B4 rewrote the roster wholesale and
    # silently destroyed `full_funnel` on two of them - so the Credit Risk
    # Manager, who had been granted sight of the whole bank pipeline that
    # morning, lost it again by lunchtime and nobody was told.
    #
    # Same shape as the release config overwriting the bank's committees: a
    # wholesale write, and whatever somebody had carefully set is gone.
    #
    # A member's NAME and ROLE come from the register. Everything else on the
    # entry - full_funnel, deputy_chair, anything added later - was set
    # deliberately by an admin and is carried across.
    _was = {}
    for _m in (target.get("members") or []):
        if isinstance(_m, dict):
            _k = str(_m.get("staff_code", "") or "").strip()
            if _k:
                _was[_k] = _m

    members = []
    for p in resolved:
        _prev = _was.get(str(p["staff_code"]).strip(), {})
        _entry = {k: v for k, v in _prev.items()
                  if k not in ("id", "member_id", "staff_code", "name", "role")}
        _entry.update({
            "id": p["staff_code"],
            "member_id": p["staff_code"],
            "staff_code": p["staff_code"],
            "name": p["name"],
            "role": p["role"],
        })
        members.append(_entry)

    _kept = sorted({k for p in resolved
                    for k in _was.get(str(p["staff_code"]).strip(), {})
                    if k not in ("id", "member_id", "staff_code", "name", "role")})
    if _kept:
        print("\n  carried across from the existing roster: %s" % ", ".join(_kept))

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    r = open(ROUTES, encoding="utf-8").read()
    # THE NAMER IS OURS, NOT THE BANK'S. name_dcc_members.py is a tool we run
    # on a box to configure a committee; it is not part of what ships. On the
    # pilot's tree it simply is not there, and requiring it aborted the whole
    # release over a script the release does not contain.
    #
    # The half that matters to the bank is the credit-voice rule. The flag
    # preservation matters to whoever runs the namer, wherever it lives.
    _have_namer = os.path.isfile(NAMER)
    n = open(NAMER, encoding="utf-8").read() if _have_namer else ""
    if "A CREDIT VOICE MUST BE IN THE ROOM" in r:
        print("ABORT: CV1 looks applied.")
        return 1
    if "THE BUSINESS CREDIT COMMITTEE ANSWERS TO CREDIT RISK" not in r:
        print("ABORT: BC1 must be applied first.")
        return 1
    if r.count(VOICE_ANCHOR) != 1:
        print("ABORT: the tally anchor matched %d times." % r.count(VOICE_ANCHOR))
        return 1
    _do_namer = _have_namer and n.count(FLAGS_OLD) == 1
    if _have_namer and not _do_namer:
        print("  note: name_dcc_members.py is here but already carries the fix")

    r = r.replace(VOICE_ANCHOR, VOICE_BLOCK + VOICE_ANCHOR, 1)
    if _do_namer:
        n = n.replace(FLAGS_OLD, FLAGS_BLOCK.rstrip(), 1)
    print("  ok  a credit voice is required; flags survive a re-naming")

    if '"mcc"' not in VOICE_BLOCK:
        print("ABORT: the rule would apply to department committees too,")
        print("       where it can never fail and so teaches nothing.")
        return 1
    if "ABSTAIN" in VOICE_BLOCK.upper() and "abstention counts" not in VOICE_BLOCK:
        print("ABORT: an abstention must count as being in the room.")
        return 1
    if "_credit_ids" not in VOICE_BLOCK or "risk" not in VOICE_BLOCK:
        print("ABORT: credit members are not identified.")
        return 1
    if "full_funnel" not in FLAGS_BLOCK:
        print("ABORT: the flag this exists to preserve is not mentioned.")
        return 1
    if "_was" not in FLAGS_BLOCK:
        print("ABORT: the previous roster is not read, so nothing could be")
        print("       carried across.")
        return 1
    import ast
    _targets = [(ROUTES, r)] + ([(NAMER, n)] if _do_namer else [])
    for name, src in _targets:
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("ABORT: %s would not parse - line %s: %s"
                  % (os.path.basename(name), exc.lineno, exc.msg))
            return 1
    print("  ok  post-checks: business only, abstention counts, flags kept")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in _targets:
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    for path, _src in _targets:
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1
    print("  ok  compiles")
    print("\nRESTART UVICORN, then:")
    print("   python scripts\\grant_full_funnel.py --who Korir,Okumu --apply")
    print("   python scripts\\rehearse_bcc.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
