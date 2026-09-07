#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Two accounts, one staff code - look at both, then retire the stale one. DRY RUN.

FOUND (2026-09-07): staff code CN205 has two user rows -

    username=CN205       "Billy Owiny Ochieng"   Direct Sales Agent   Kisumu
    username=BOOCHIENG   "OCHIENG Billy"         Staff                (no branch)

The register is built from that table and inherits both. A lookup by staff code
takes whichever comes first, gets the incomplete one, reads a blank branch, and
every branch test on his deals refuses - correctly, because it cannot tell
which row is him.

    python scripts\fix_duplicate_staff_code.py --code CN205
    python scripts\fix_duplicate_staff_code.py --code CN205 --retire BOOCHIENG --apply

IT DEACTIVATES, IT DOES NOT DELETE. A login that has raised a deal, validated a
day or cast a vote is referenced by every one of those records. Deleting it
leaves an audit trail pointing at a person who no longer exists; deactivating
it takes the account out of the register and out of every scope lookup while
the history stays readable.

IT REFUSES TO RETIRE THE ACTIVE ONE. Before touching anything it counts what
each account owns - deals, validations, log entries. If the one you named has
the work and the other does not, it stops and says so: the stale row is the one
with nothing behind it, and getting that backwards would take a real officer
out of the system.

WHAT TO DO AFTER: nothing. The register rebuilds without the retired row, the
staff code resolves to one person, and his branch reads correctly - so a Kisumu
manager can validate his deals again.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    code = retire = ""
    for flag in ("--code", "--retire"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--code":
                    code = sys.argv[i + 1].strip()
                else:
                    retire = sys.argv[i + 1].strip()
    if not code:
        print("ABORT: --code CN205")
        return 1

    from utils.core import UserManager, PipelineManager
    um = UserManager()
    users = um.users or {}

    rows = [(login, rec) for login, rec in users.items()
            if str(rec.get("staff_code", "")).strip().lower() == code.lower()]

    print("=" * 86)
    print("ACCOUNTS SHARING STAFF CODE %s" % code)
    print("=" * 86)
    if not rows:
        print("  Nobody has that staff code.")
        return 1
    if len(rows) == 1:
        print("  Only one account. Nothing to clean up here.")
        return 0

    deals = PipelineManager().deals or []
    try:
        from utils.branch_log import BranchLogManager
        logs = BranchLogManager().logs or []
    except Exception:
        logs = []

    counts = {}
    for login, rec in rows:
        owned = [d for d in deals
                 if str(d.get("staff_code", "")).strip().lower() == code.lower()]
        by_login = [d for d in deals
                    if str(d.get("created_by", "") or "").strip().lower()
                    == login.lower()]
        valid = [d for d in deals
                 if str(d.get("validated_by", "") or "").strip().lower()
                 == login.lower()]
        mylogs = [l for l in logs
                  if str(l.get("staff_code", "")).strip().lower() == code.lower()]
        counts[login] = {"created": len(by_login), "validated": len(valid),
                         "logs": len(mylogs), "owned_by_code": len(owned)}

    for login, rec in rows:
        c = counts[login]
        print("\n  username   %s" % login)
        print("     name       %s" % rec.get("full_name"))
        print("     role       %s" % rec.get("role"))
        print("     branch     %s" % (rec.get("branch") or "*** NONE"))
        print("     unit       %s" % (rec.get("unit") or "-"))
        print("     active     %s" % rec.get("active"))
        print("     last login %s" % (rec.get("last_login") or "never"))
        print("     deals it created      %d" % c["created"])
        print("     days it validated     %d" % c["validated"])

    # Which looks stale? The one with no branch and nothing behind it.
    def score(login, rec):
        c = counts[login]
        return (1 if str(rec.get("branch") or "").strip() else 0) \
            + (1 if rec.get("last_login") else 0) \
            + (1 if c["created"] or c["validated"] else 0)

    ranked = sorted(rows, key=lambda lr: score(lr[0], lr[1]))
    stale_login = ranked[0][0]
    keep_login = ranked[-1][0]
    print("\n  " + "-" * 82)
    print("  LOOKS STALE   %s" % stale_login)
    print("  LOOKS REAL    %s" % keep_login)
    if score(*ranked[0]) == score(*ranked[-1]):
        print("\n  *** THEY LOOK THE SAME. Neither has a branch, a login or any")
        print("      work behind it - or both do. This needs a person from the")
        print("      branch to say which is him, not a script.")
        return 1

    if not retire:
        print("\n  To retire the stale one:")
        print("     python scripts\\fix_duplicate_staff_code.py --code %s \\" % code)
        print("         --retire %s --apply" % stale_login)
        return 0

    if retire not in users:
        print("\nABORT: there is no account %r." % retire)
        return 1
    if retire == keep_login:
        print("\nABORT: %r is the account with the branch and the work behind" % retire)
        print("       it. Retiring it would take a real officer out of the")
        print("       system. Did you mean %r?" % stale_login)
        return 1

    c = counts[retire]
    if c["created"] or c["validated"]:
        print("\n  *** %s HAS WORK BEHIND IT: %d deal(s) created, %d day(s)"
              % (retire, c["created"], c["validated"]))
        print("      validated. Deactivating keeps all of it readable - the")
        print("      account simply stops being a person the system can pick.")

    print("\n  RETIRING %s" % retire)
    print("     %s (%s)" % (users[retire].get("full_name"), users[retire].get("role")))
    print("     it will be marked inactive, NOT deleted - the audit trail keeps")
    print("     pointing at a person who still exists.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    users[retire]["active"] = False
    users[retire]["retired_reason"] = (
        "duplicate of staff code %s; the complete account is %s"
        % (code, keep_login))
    users[retire]["retired_at"] = datetime.now().isoformat(timespec="seconds")
    try:
        um.save()
    except Exception:
        try:
            um._save()
        except Exception as exc:
            print("\nABORT: could not save the user store: %s" % str(exc)[:50])
            return 1
    print("\nretired %s." % retire)
    print("\nRESTART UVICORN. The register rebuilds without it, %s resolves to"
          % code)
    print("one person, and his branch reads correctly - so a Kisumu manager")
    print("can validate his deals again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
