#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does every login point at the right person? READ ONLY. Exit 1 on a mismatch.

RULING (2026-08-12): "a staff named Joshua Kyuma was seeing his profile on all
the pages, but on the balanced scorecard he was seeing that of Joshua Muthama.
Probably the issue is on the staff payroll, which we might have guessed for
Joshua sometime."

WHY THIS SHOWS UP ONLY ON THE SCORECARD. Most pages display the name carried in
the SESSION, which is right. The scorecard resolves the person by STAFF CODE and
looks them up in the register - so a user record carrying the wrong code shows
the correct name everywhere and the wrong scorecard in one place. The
inconsistency is invisible until somebody opens their own scorecard and does not
recognise the numbers.

That makes it a bad class of bug: silent, and wrong in the direction of somebody
seeing another person's performance.

WHAT THIS CHECKS, for every login:

    the staff code on the user record exists in the register
    the name on the user record matches the name against that code
    no two logins share a staff code
    no two register rows share a staff code
    people who share a SURNAME or a FIRST NAME are listed, because that is
        where a guessed code does its damage and nobody notices

IT NAMES THE CORRECTION rather than making it - a script that rewrites identity
records unattended is not something to run on a payroll.

    python scripts\\diag_identity.py
    python scripts\\diag_identity.py --name Joshua
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())


def check_analyst_segments():
    """Can every credit analyst be told apart by segment?

    A Consumer and a Commercial analyst can share the role "Credit Analyst",
    so the DEPARTMENT is the only thing that separates them. An analyst whose
    segment does not resolve is treated as having none - which quietly removes
    their ability to submit a case to the Department Credit Committee.
    """
    from utils.core import UserManager
    from utils.api_lms_scope import _analyst_segment
    users = UserManager().users or {}
    rows = []
    for uname, u in users.items():
        role = str(u.get("role") or "")
        if "analyst" not in role.lower():
            continue
        code = str(u.get("staff_code") or "")
        rows.append((uname, role, code,
                     _analyst_segment(role, code),
                     _analyst_segment(role)))
    if not rows:
        print("  no analyst logins found")
        return
    print("  %-18s %-30s %-9s %-11s %s"
          % ("login", "role", "code", "segment", "was (role only)"))
    for uname, role, code, seg, old in sorted(rows):
        flag = "  " if seg else "**"
        print("  %s%-16s %-30s %-9s %-11s %s"
              % (flag, uname[:16], role[:30], code[:9], seg or "NONE",
                 old or "NONE"))
    broken = [r for r in rows if not r[3]]
    if broken:
        print("\n  %d analyst(s) resolve to NO segment even with their staff code."
              % len(broken))
        print("  They cannot submit to the Department Credit Committee. Check")
        print("  their Department in the register reads Consumer, Commercial or")
        print("  Corporate.")


def main():
    focus = ""
    if "--name" in sys.argv:
        i = sys.argv.index("--name")
        if i + 1 < len(sys.argv):
            focus = sys.argv[i + 1].strip().lower()

    try:
        from utils.core import UserManager
        from utils.api_pipeline_scope import get_staff_roster
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    try:
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unavailable: %s" % exc)
        return 1

    reg = {}
    for _i, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if code:
            reg[code] = {"name": str(r.get("Staff Name") or "").strip(),
                         "role": str(r.get("Role") or "").strip(),
                         "unit": str(r.get("Unit") or "").strip()}

    users = UserManager().users or {}

    print("=" * 78)
    print("IDENTITY CHECK")
    print("=" * 78)
    print("  register  %d staff" % len(reg))
    print("  logins    %d" % len(users))

    problems = []

    # 1. Duplicate codes in the register itself.
    dupes = [c for c, n in Counter(
        str(r.get("Staff Code") or "").strip()
        for _i, r in df.iterrows()).items() if c and n > 1]
    if dupes:
        problems.append("register has duplicate staff codes: %s" % ", ".join(dupes[:6]))

    # 2. Two logins claiming one staff code. This is the shape that puts one
    #    person on another's scorecard.
    by_code = defaultdict(list)
    for uname, u in users.items():
        code = str(u.get("staff_code") or "").strip()
        if code:
            by_code[code].append(uname)
    shared = {c: names for c, names in by_code.items() if len(names) > 1}

    # 3. Name on the login vs name against its code.
    mismatches = []
    orphans = []
    for uname, u in users.items():
        code = str(u.get("staff_code") or "").strip()
        uname_full = str(u.get("full_name") or u.get("name") or "").strip()
        if not code:
            continue
        row = reg.get(code)
        if not row:
            orphans.append((uname, code, uname_full))
            continue
        a = " ".join(uname_full.lower().split())
        b = " ".join(row["name"].lower().split())
        if a and b and a != b:
            # Same person written two ways is not a mismatch worth shouting
            # about; a DIFFERENT SURNAME is.
            if set(a.split()) & set(b.split()):
                mismatches.append((uname, code, uname_full, row["name"], "partial"))
            else:
                mismatches.append((uname, code, uname_full, row["name"], "different"))

    print("\n" + "-" * 78)
    print("LOGINS WHOSE NAME DOES NOT MATCH THEIR STAFF CODE")
    print("-" * 78)
    if not mismatches:
        print("  none")
    for uname, code, shown, actual, kind in mismatches:
        flag = "***" if kind == "different" else "   "
        print("  %s %-16s code %-8s login says %-28s register says %s"
              % (flag, uname, code, shown[:28], actual[:28]))
        if kind == "different":
            problems.append("%s (code %s) is named %r but that code belongs to %r"
                            % (uname, code, shown, actual))

    if shared:
        print("\n" + "-" * 78)
        print("STAFF CODES CLAIMED BY MORE THAN ONE LOGIN")
        print("-" * 78)
        for code, names in shared.items():
            print("  *** %-8s %s   -> %s"
                  % (code, ", ".join(names), reg.get(code, {}).get("name", "not in register")))
            problems.append("code %s is claimed by %d logins" % (code, len(names)))

    if orphans:
        print("\n" + "-" * 78)
        print("LOGINS POINTING AT A CODE THAT IS NOT IN THE REGISTER")
        print("-" * 78)
        for uname, code, shown in orphans[:10]:
            print("      %-16s code %-8s %s" % (uname, code, shown[:30]))
        problems.append("%d login(s) point at a code not in the register" % len(orphans))

    # 4. WHERE A GUESS DOES ITS DAMAGE: people who share a name fragment.
    print("\n" + "-" * 78)
    print("PEOPLE SHARING A NAME - where a guessed code goes unnoticed")
    print("-" * 78)
    parts = defaultdict(list)
    for code, r in reg.items():
        for p in r["name"].split():
            if len(p) > 2:
                parts[p.lower()].append((code, r["name"], r["role"]))
    shown_any = False
    for part, people in sorted(parts.items()):
        if len(people) < 2:
            continue
        if focus and part != focus:
            continue
        if not focus and len(people) < 3:
            continue
        shown_any = True
        print("  %s (%d)" % (part.title(), len(people)))
        for code, nm, role in sorted(people)[:8]:
            login = ", ".join(by_code.get(code, [])) or "no login"
            print("      %-8s %-30s %-26s [%s]" % (code, nm[:30], role[:26], login))
    if not shown_any:
        print("  none to show")

    if "--segments" in sys.argv:
        print("\n" + "-" * 78)
        print("ANALYST SEGMENT RESOLUTION")
        print("-" * 78)
        try:
            check_analyst_segments()
        except Exception as exc:
            print("  could not check: %s" % exc)

    print("\n" + "=" * 78)
    if not problems:
        print("Every login resolves to the person it claims.")
        return 0
    print("%d PROBLEM(S):\n" % len(problems))
    for p in problems:
        print("   * %s" % p)
    print("")
    print("NOT corrected automatically. Rewriting identity records unattended is")
    print("not something to run against a payroll - fix the staff_code on the")
    print("login in users.json, or the row in the register, whichever is wrong.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
