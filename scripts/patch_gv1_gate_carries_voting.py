#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
GV1 - the committee gate tells the panel who may vote. URGENT.

FROM THE PILOT (2026-08-17): the branch chair could see the case in her queue
and had NO VOTING PANEL.

The panel renders the voting bench on `gate.can_vote`. Where that field is
absent it falls back to `canEdit` - which means "owner or admin" - so a
committee member who is neither sees a read-only card and nothing to vote with.
The one person the case was waiting for.

The server was never sending the field. The gate carried code, name, mode,
rule, members and record, and nothing about the viewer at all.

WHY THE TESTS DID NOT CATCH IT: every gate test drove the VOTE ENDPOINT, which
works - both votes were accepted, quorum was reached, the case advanced. What
nobody drove was the READ that decides whether the button is drawn. The
behaviour was right and the screen could not show it.

The gate now carries three things about the person looking at it:

    can_vote     are they on this committee, by staff code, by name, or as its
                 chair - the same three ways membership is matched everywhere
                 else
    votes_cast   how many have voted, so a member can see whether the committee
                 is waiting on them or on somebody else
    quorum       how many are needed

A NON-MEMBER GETS can_vote FALSE and no bench. The vote endpoint refuses them
independently - this only governs what is drawn, and a field in a response is
not a permission.

Verified on a copy of the pilot's own tree: the chair's gate returns
can_vote=True where it previously returned nothing.

Usage (from project root, .venv active):
    python scripts\\patch_gv1_gate_carries_voting.py            # dry run
    python scripts\\patch_gv1_gate_carries_voting.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_gv1"

OLD = '''    for code in codes:
        c = _committee_by_code(code)
        gates.append({
            "code": code,
            "name": c.get("name", code),
            "recording_mode": c.get("recording_mode", "voting"),
            "voting_rule": c.get("voting_rule", "SIMPLE_MAJORITY"),
            "members": c.get("members", []),
            "record": records.get(code),
        })'''

NEW = '''    _me = str(user.get("staff_code", "") or "").strip()
    _myname = str(user.get("full_name", "") or "").strip().lower()
    _all_votes = deal.get("committee_votes") or {}
    for code in codes:
        c = _committee_by_code(code)
        # ---- WHETHER *THIS* VIEWER MAY VOTE ------------------------------
        # The panel draws the voting bench on this. Without it, it falls back
        # to canEdit - "owner or admin" - so a committee member who is neither
        # sees a read-only card and nothing to vote with. That is what left a
        # branch chair unable to act on a case that was waiting for her.
        #
        # Membership is matched the same three ways it is matched everywhere
        # else: staff code, name, or being the chair.
        _members = c.get("members", []) or []
        _codes = {str(m.get("staff_code", "") or "").strip()
                  for m in _members if isinstance(m, dict)}
        _names = {str(m.get("name", "") or "").strip().lower()
                  for m in _members if isinstance(m, dict)}
        _chair = str(c.get("chaired_by", "") or "").strip().lower()
        _chair_code = str(c.get("chair_staff_code", "") or "").strip()
        _can_vote = bool(
            (_me and (_me in _codes or _me == _chair_code))
            or (_myname and (_myname in _names or _myname == _chair)))
        _cast = (_all_votes.get(code) or {}) if isinstance(_all_votes, dict) else {}
        try:
            _quorum = _committee_quorum(c)
        except Exception:
            _quorum = c.get("min_quorum_count") or 2
        gates.append({
            "code": code,
            "name": c.get("name", code),
            "recording_mode": c.get("recording_mode", "voting"),
            "voting_rule": c.get("voting_rule", "SIMPLE_MAJORITY"),
            "members": _members,
            "record": records.get(code),
            "can_vote": _can_vote,
            "votes_cast": len(_cast),
            "quorum": _quorum,
        })'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if '"can_vote": _can_vote' in s:
        print("ABORT: GV1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the gate builder matched %d times." % s.count(OLD))
        print("       This anchors on the shape the pilot's tree actually has.")
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  the gate says whether this viewer may vote")

    if "chair_staff_code" not in NEW or "chaired_by" not in NEW:
        print("ABORT: a chair not listed among the members would get no bench -")
        print("       which is the fault this exists to fix.")
        return 1
    if '"votes_cast"' not in NEW:
        print("ABORT: a member cannot tell whether the committee waits on them.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: chair recognised, progress carried, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. The committee member sees the voting bench.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
