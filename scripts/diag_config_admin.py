#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Who can edit configuration, and why is this person refused? READ ONLY.

FROM THE PILOT (2026-08-13): the admin gets

    API /admin/committee-palette failed: 403 Forbidden

A curl with no header returns 401, which proves the ROUTE EXISTS in the running
process. So the request arrives and require_config_admin refuses the token.
That gate is simple:

    the role string must contain one of: admin, director, chief, managing

and the role comes from the JWT, falling back to "Staff" when the token carries
no role claim. RL1 made the server read the role back from the user store when
the token says "Staff" - but only if the store HAS a record under that exact
username.

So a 403 is one of three things, and they need different fixes:

    THE SESSION IS OLD      the token predates RL1 and still says Staff.
                            Sign out and back in.
    THE ROLE DOES NOT MATCH e.g. "IT Officer" contains none of the four words.
                            Change the role, or widen the gate deliberately.
    THE USERNAME IS ABSENT  the AD login name is not a key in users.json, so
                            there is nothing to enrich from and the role stays
                            Staff for ever. This is the one that does not fix
                            itself with a re-login.

    python scripts\\diag_config_admin.py
    python scripts\\diag_config_admin.py --user jdoe
"""
import os
import sys

sys.path.insert(0, os.getcwd())

TOKENS = ("admin", "director", "chief", "managing")


def main():
    who = ""
    if "--user" in sys.argv:
        i = sys.argv.index("--user")
        if i + 1 < len(sys.argv):
            who = sys.argv[i + 1].strip()

    try:
        from utils.core import UserManager
    except Exception as exc:
        print("ABORT: cannot load the user store: %s" % exc)
        return 1
    users = UserManager().users or {}

    print("=" * 76)
    print("WHO CAN EDIT CONFIGURATION")
    print("=" * 76)
    print("  the gate: role contains one of %s" % ", ".join(TOKENS))
    print("  logins in the store: %d" % len(users))

    def passes(role):
        rl = str(role or "").lower()
        return any(t in rl for t in TOKENS)

    if who:
        rec = users.get(who)
        if not rec:
            hits = [k for k in users if who.lower() in k.lower()]
            print("\n  %r IS NOT A KEY IN users.json." % who)
            if hits:
                print("  Close matches: %s" % ", ".join(hits[:8]))
            print("")
            print("  *** IF THIS IS THE NAME THEY SIGN IN WITH, that is the")
            print("      whole fault. The server enriches a role from the store")
            print("      BY USERNAME; with no record there is nothing to read,")
            print("      the role stays 'Staff', and every config gate refuses")
            print("      them. Re-logging in will not help.")
            print("")
            print("      Fix: add them to users.json under the EXACT name their")
            print("      AD login presents, with their real role.")
            return 1
        role = rec.get("role")
        print("\n  login       %s" % who)
        print("  role        %r" % role)
        print("  staff_code  %r" % rec.get("staff_code"))
        print("  passes      %s" % passes(role))
        if not passes(role):
            print("")
            print("  *** THE ROLE DOES NOT CONTAIN ANY OF THE FOUR WORDS, so")
            print("      the gate refuses them however they sign in. Either")
            print("      give them a role that does, or widen the gate - but")
            print("      widen it deliberately, not to make one screen work.")
        else:
            print("")
            print("  The store says they should pass. So the 403 is the SESSION:")
            print("  their token predates the role fix and still says 'Staff'.")
            print("  Sign out and back in - the role is read at token verify.")
        return 0

    ok = sorted((k, v.get("role")) for k, v in users.items() if passes(v.get("role")))
    print("\n  %d login(s) can edit configuration:" % len(ok))
    for k, r in ok[:25]:
        print("     %-28s %s" % (k, r))
    if len(ok) > 25:
        print("     ... and %d more" % (len(ok) - 25))
    if not ok:
        print("     NONE. Nobody can edit configuration on this box.")
    print("")
    print("  If the person seeing the 403 is not on this list, that is the")
    print("  answer. If they ARE on it, their session is old - sign out and in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
