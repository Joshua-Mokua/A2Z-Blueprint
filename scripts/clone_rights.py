#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Give one person the same rights as another. DRY RUN by default.

RULING (2026-08-18): "add Kamami from Consumer to have the consumer analyst
rights as well - she supports when Catherine is away ... the admin should be
able to clone a profile to give view and access."

Cover arrangements are ordinary and constant - somebody is away, somebody
stands in - and the alternative is an admin reconstructing a permission set by
hand from memory. That is how a stand-in ends up seeing less than they need, or
more, and neither is discovered until it matters.

WHAT IS COPIED, and it is deliberately only these:

    role                  drives the segment an analyst is limited to, and
                          which pool roles they match
    department            the register-side segment fallback
    managed_units         the cascade: whose work they can see
    managed_roles
    managed_staff_codes
    can_view_all

WHAT IS NOT COPIED, and each for a reason:

    password, staff_code, email, full_name   they are a different person
    active                                   a cover should not silently
                                             reactivate a disabled account
    committee membership                     sitting on a committee is a
                                             named appointment, not a right.
                                             Use name_dcc_members.py.
    full_funnel                              sight of the whole bank is granted
                                             deliberately, one person at a
                                             time. Use grant_full_funnel.py.

It shows the before and after for every field it touches, so an admin sees
exactly what changes before agreeing to it.

    python scripts\\clone_rights.py --from Catherine --to Kamami
    python scripts\\clone_rights.py --from Catherine --to Kamami --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

USERS = os.path.join("data", "users.json")

COPY = ["role", "department", "managed_units", "managed_roles",
        "managed_staff_codes", "can_view_all"]


def find(users, term):
    t = term.strip().lower()
    exact = [k for k in users if k.lower() == t
             or str(users[k].get("staff_code", "")).lower() == t]
    if len(exact) == 1:
        return exact[0], None
    hits = [k for k in users
            if t in k.lower()
            or t in str(users[k].get("full_name", "") or "").lower()]
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, "nobody matches %r" % term
    return None, "%r matches %d people: %s" % (
        term, len(hits),
        "; ".join("%s (%s)" % (k, users[k].get("full_name") or "") for k in hits[:6]))


def main():
    apply = "--apply" in sys.argv
    src = dst = ""
    for flag in ("--from", "--to"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--from":
                    src = sys.argv[i + 1].strip()
                else:
                    dst = sys.argv[i + 1].strip()
    if not src or not dst:
        print("ABORT: --from <person> and --to <person> are both required.")
        print("   python scripts\\clone_rights.py --from Catherine --to Kamami")
        return 1

    from utils.core import UserManager
    users = UserManager().users or {}

    skey, err = find(users, src)
    if err:
        print("ABORT: --from: %s" % err)
        return 1
    dkey, err = find(users, dst)
    if err:
        print("ABORT: --to: %s" % err)
        return 1
    if skey == dkey:
        print("ABORT: those are the same person.")
        return 1

    s, d = users[skey], users[dkey]
    print("=" * 76)
    print("CLONING RIGHTS")
    print("=" * 76)
    print("  from  %-16s %s (%s)" % (skey, s.get("full_name") or "", s.get("staff_code") or "-"))
    print("  to    %-16s %s (%s)" % (dkey, d.get("full_name") or "", d.get("staff_code") or "-"))
    print("")
    print("  %-22s %-24s %s" % ("FIELD", "THEIRS NOW", "WILL BECOME"))
    changes = 0
    for f in COPY:
        was, will = d.get(f), s.get(f)
        same = was == will
        if not same:
            changes += 1
        print("  %-22s %-24s %s%s"
              % (f, str(was)[:24], str(will)[:30], "" if not same else "   (unchanged)"))

    # What this actually means, in plain words.
    try:
        from utils.api_lms_scope import _analyst_segment
        seg_before = _analyst_segment(str(d.get("role", "")), str(d.get("staff_code", "")))
        seg_after = _analyst_segment(str(s.get("role", "")), str(d.get("staff_code", "")))
        print("")
        print("  segment they are limited to: %r -> %r"
              % (seg_before or "(unrestricted)", seg_after or "(unrestricted)"))
    except Exception:
        pass

    print("")
    print("  NOT copied: password, staff code, email, name, active,")
    print("  committee seats, full_funnel. A cover is a set of rights, not")
    print("  an identity - and a committee seat is an appointment.")

    if not changes:
        print("\n  Nothing would change.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for f in COPY:
        v = s.get(f)
        d[f] = list(v) if isinstance(v, list) else v

    bak = USERS + ".pre_clone_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(USERS, bak)
    json.dump(users, open(USERS, "w", encoding="utf-8"), indent=2)
    print("\ncloned %d field(s).  (backup: %s)" % (changes, os.path.basename(bak)))
    print("RESTART UVICORN - the user store is read at start.")
    print("\nCheck with:  python scripts\\verify_login.py --user %s" % dkey)
    return 0


if __name__ == "__main__":
    sys.exit(main())
