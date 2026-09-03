#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Let somebody validate a branch while the regular validators are away. DRY RUN.

    python scripts\delegate_validator.py
    python scripts\delegate_validator.py --staff "Osoro Hilda" --branches Kisumu ^
        --until 2026-09-30 --reason "cover while the regular validators are away" --apply
    python scripts\delegate_validator.py --revoke KE1234 --apply

VALIDATION AUTHORITY NORMALLY FOLLOWS THE REPORTING LINE - you validate the
branches whose Branch Manager reports to you. That is right, and it has no
answer for cover. This is the exception: explicit, dated, and reasoned.

EVERY DELEGATION EXPIRES. --until is required. A delegation with no end date is
not "for ever", it is an incomplete delegation, and the code that reads these
grants nothing without one.

THE REASON IS REQUIRED TOO. In six months somebody will ask why this person
could validate this branch, and "it is in the config" is not an answer.

Writes to org_config.json, which is the deployment's own file and does not
travel in a release - so a delegation made at the bank stays at the bank.
"""
import json
import os
import re
import shutil
import sys
from datetime import date, datetime

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "org_config.json")


def _digits(v):
    m = re.match(r"^([A-Za-z]*)0*(\d+)$", str(v or "").strip())
    return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""


def main():
    apply = "--apply" in sys.argv
    staff = branches = until = reason = revoke = ""
    for flag in ("--staff", "--branches", "--until", "--reason", "--revoke"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                v = sys.argv[i + 1]
                if flag == "--staff":
                    staff = v
                elif flag == "--branches":
                    branches = v
                elif flag == "--until":
                    until = v.strip()
                elif flag == "--reason":
                    reason = v
                else:
                    revoke = v.strip()

    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    rows = list(cfg.get("delegated_validators") or [])

    today = date.today().isoformat()
    print("=" * 78)
    print("WHO MAY VALIDATE BY DELEGATION")
    print("=" * 78)
    if not rows:
        print("  nobody")
    for r in rows:
        u = str(r.get("until") or "")
        state = ("EXPIRED" if (not u or u < today) else "active until %s" % u)
        print("  %-10s %-24s %-22s %s"
              % (r.get("staff_code"), str(r.get("name"))[:24],
                 ", ".join(r.get("branches") or [])[:22], state))
        if r.get("reason"):
            print("             %s" % str(r["reason"])[:62])

    if revoke:
        keep = [r for r in rows if _digits(r.get("staff_code")) != _digits(revoke)]
        if len(keep) == len(rows):
            print("\n  Nobody with code %r is delegated." % revoke)
            return 1
        print("\n  REVOKING %d delegation(s) for %s" % (len(rows) - len(keep), revoke))
        if not apply:
            print("\nDRY RUN - nothing written. Re-run with --apply.")
            return 0
        shutil.copy2(CFG, CFG + ".pre_deleg_%s" % datetime.now().strftime("%H%M%S"))
        cfg["delegated_validators"] = keep
        json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
        print("revoked. RESTART UVICORN.")
        return 0

    if not (staff or branches or until or reason):
        print("\n  Nothing changed. To delegate:")
        print('     python scripts\\delegate_validator.py --staff "Osoro Hilda" \\')
        print('         --branches Kisumu --until 2026-09-30 \\')
        print('         --reason "cover while the regular validators are away" --apply')
        return 0

    missing = [n for n, v in (("--staff", staff), ("--branches", branches),
                              ("--until", until), ("--reason", reason)) if not v]
    if missing:
        print("\nABORT: %s required." % ", ".join(missing))
        print("  An end date and a reason are not optional. A delegation")
        print("  without them becomes permanent authority nobody remembers")
        print("  granting, which is what an auditor asks about.")
        return 1
    try:
        if until < today:
            print("\nABORT: %s is in the past - that delegation would grant"
                  " nothing." % until)
            return 1
        datetime.strptime(until, "%Y-%m-%d")
    except ValueError:
        print("\nABORT: --until must be YYYY-MM-DD.")
        return 1

    # Resolve the person, so a delegation is never made to a name nobody has.
    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
    except Exception as exc:
        print("\nABORT: cannot read the staff register: %s" % str(exc)[:56])
        return 1
    people = []
    for _i, r in roster.iterrows():
        people.append({"name": str(r.get("Staff Name") or "").strip(),
                       "code": str(r.get("Staff Code") or "").strip(),
                       "branch": str(r.get("Branch") or r.get("Unit") or "").strip()})
    t = staff.strip().lower()
    hits = [p for p in people if _digits(p["code"]) == _digits(staff)] or \
           [p for p in people if t in p["name"].lower()]
    if len(hits) != 1:
        print("\nABORT: %r matches %d people." % (staff, len(hits)))
        for h in hits[:5]:
            print("     %-10s %s (%s)" % (h["code"], h["name"], h["branch"]))
        print("  Give the staff code.")
        return 1
    who = hits[0]

    brs = [b.strip() for b in branches.split(",") if b.strip()]
    print("\n  TO DELEGATE")
    print("     person     %s (%s), based at %s"
          % (who["name"], who["code"], who["branch"] or "?"))
    print("     branches   %s" % ", ".join(brs))
    print("     until      %s" % until)
    print("     reason     %s" % reason)
    print("\n  This ADDS authority. It cannot take a branch away from whoever")
    print("  already validates it by their reporting line.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(CFG, CFG + ".pre_deleg_%s" % datetime.now().strftime("%H%M%S"))
    rows = [r for r in rows if _digits(r.get("staff_code")) != _digits(who["code"])]
    rows.append({"staff_code": who["code"], "name": who["name"],
                 "branches": brs, "until": until, "reason": reason,
                 "added_at": today})
    cfg["delegated_validators"] = rows
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\ndelegated. RESTART UVICORN.")
    print("\nIt lapses on %s and grants nothing after that." % until)
    return 0


if __name__ == "__main__":
    sys.exit(main())
