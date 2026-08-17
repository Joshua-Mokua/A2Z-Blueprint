#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Could this committee, as it is actually configured, finish a case?

WHY THIS EXISTS, and it is worth reading before the next release.

Three test suites - 376 checks, 1,115 checks, 22 checks - all passed while
Eldoret's committee could not complete a single decision. Managers gathered on
two separate days and went home.

Every one of those tests BUILT ITS OWN COMMITTEE. When I needed one I wrote it,
and I always put the chair in the members list, because that is how a person
would build one by hand. The real seeder writes the chair to `chaired_by` and
the members to `members` and never joins them. So I was testing my own
assumption about the shape of the data, not the shape the system produces.

    A test that constructs its inputs verifies the author's model.
    Only a test that reads what the system generates verifies the system.

So this reads the real configuration and the real register and asks the only
question that matters: IF THESE PEOPLE VOTED, WOULD THE CASE MOVE? It runs the
actual quorum and chair rules over the actual roster - no fixtures anywhere.

    python scripts\\audit_readiness.py
    python scripts\\audit_readiness.py --verbose

Exit 0 when every committee could genuinely finish a case.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())

READY, BROKEN = [], []
VERBOSE = "--verbose" in sys.argv


def main():
    import utils.api as A
    from utils.core import UserManager

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    users = UserManager().users or {}

    by_code, by_name = {}, {}
    for k, v in users.items():
        c = str(v.get("staff_code", "") or "").strip()
        n = str(v.get("full_name", "") or "").strip().lower()
        if c:
            by_code[c] = k
        if n:
            by_name[n] = k

    print("=" * 78)
    print("COULD EACH COMMITTEE ACTUALLY FINISH A CASE")
    print("=" * 78)
    print("  Read from the real config and the real logins. No fixtures.\n")

    for c in pal:
        code = str(c.get("code") or "?")
        where = str(c.get("branch") or c.get("name") or "")[:24]
        chair = str(c.get("chaired_by", "") or "").strip()
        chair_code = str(c.get("chair_staff_code", "") or "").strip()
        quorum = c.get("min_quorum_count") or 2
        members = [m for m in (c.get("members") or []) if isinstance(m, dict)
                   and (str(m.get("staff_code", "")).strip()
                        or str(m.get("name", "")).strip())]

        faults = []

        # BCC1 IS A PLACEHOLDER, NOT A COMMITTEE. A product journey naming it
        # gets it substituted at runtime for the deal's OWN branch committee,
        # so it never sits and never needs members. Flagging it as broken sent
        # us looking for people to put on a thing that is not a committee -
        # a false alarm is worse than silence, because it costs the same
        # attention as a real one.
        if code == "BCC1":
            if VERBOSE:
                print("  skipped        BCC1         a routing placeholder, not a committee")
            continue

        # 1. Somebody must sit on it.
        if not members and not chair:
            faults.append("nobody sits on it - a case here is invisible to all")

        # 2. Enough of them to reach quorum.
        if members and len(members) < quorum:
            faults.append("%d member(s) against a quorum of %d" % (len(members), quorum))

        # 3. THE CHAIR MUST BE ABLE TO VOTE. Their vote is mandatory, and
        #    membership is matched by staff code - so a chair who is only named
        #    in chaired_by cannot cast the vote the rule demands. THIS IS THE
        #    ELDORET FAULT, and no earlier test asked it because every earlier
        #    test built a committee where the chair was already a member.
        if chair:
            seated = any(
                (chair_code and str(m.get("staff_code", "")).strip() == chair_code)
                or str(m.get("name", "")).strip().lower() == chair.lower()
                for m in members)
            if not seated:
                faults.append("the chair %s is not on the roster, so their "
                              "MANDATORY vote can never be cast" % chair)
            else:
                # And can they sign in?
                lg = by_code.get(chair_code) or by_name.get(chair.lower())
                if not lg:
                    faults.append("the chair %s has no login" % chair)

        # 4. Enough members can actually sign in to reach quorum.
        can_login = [m for m in members
                     if by_code.get(str(m.get("staff_code", "")).strip())
                     or by_name.get(str(m.get("name", "")).strip().lower())]
        if members and len(can_login) < quorum:
            faults.append("only %d of %d member(s) have a login, against a "
                          "quorum of %d" % (len(can_login), len(members), quorum))

        # 5. Is anyone on it also the deputy? A chair who is away stops
        #    everything unless somebody may stand in.
        deputies = [m for m in members if m.get("deputy_chair")]
        role_deputy = [m for m in members
                       if "operations" in str(m.get("role", "")).lower()]
        if chair and not deputies and not role_deputy:
            if VERBOSE:
                print("  note  %-12s no deputy - if %s is away it stops"
                      % (code, chair.split()[0] if chair else "the chair"))

        # 6. A branch committee must name its branch, or no deal reaches it.
        if str(c.get("kind", "")).lower() == "branch" and not str(c.get("branch", "")).strip():
            faults.append("no branch is set, so no deal can route to it")

        if faults:
            BROKEN.append((code, where, faults))
            print("  CANNOT FINISH  %-12s %s" % (code, where))
            for f in faults:
                print("                 - %s" % f)
        else:
            READY.append((code, where, len(members), quorum))
            if VERBOSE:
                print("  ready          %-12s %-24s %d members, quorum %d"
                      % (code, where, len(members), quorum))

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    print("  could finish a case    %d" % len(READY))
    print("  COULD NOT              %d" % len(BROKEN))

    if not BROKEN:
        print("\n  Every committee could genuinely complete a decision.")
        return 0

    print("\n  These would take a case in and never let it out:\n")
    for code, where, faults in BROKEN:
        print("     %-12s %-22s %s" % (code, where, faults[0][:38]))
    print("\n  Most are fixed by:")
    print("     python scripts\\seat_the_chairs.py --apply")
    print("     python scripts\\seed_committee_members.py --apply")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-6:]:
            print("   %s" % ln[:110])
        sys.exit(1)
