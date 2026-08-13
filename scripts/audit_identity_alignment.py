#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Do the three identity stores agree? READ ONLY.

THE ROOT CAUSE BEHIND A WEEK OF SYMPTOMS. Almost every "it does not work for
this person" fault in this pilot has been the same shape - a permission asked
one store about somebody and got an answer that did not match another store:

    the analyst who could not submit to the DCC   role string vs segment
    validations no manager could see              staff_code vs the register
    the administrator refused with a 403          role claim vs the user record
    the committee member with an empty queue      name in users.json vs
                                                  the name in committee members

Each was fixed on its own. None of them was the actual problem, which is that
NOTHING CHECKS THAT THE STORES AGREE, so a mismatch is invisible until a person
sits in front of a screen that does nothing.

THREE STORES

    data/users.json           who can log in - full_name, staff_code, role
    staff register (xlsx)     the org - Staff Code, Staff Name, Role, Unit
    data/lms_config.json      committee members - staff_code, name

A permission crosses all three. This reports every place they disagree, worst
first, and says what each disagreement breaks.

    python scripts\\audit_identity_alignment.py
    python scripts\\audit_identity_alignment.py --fixable
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

CRIT, WARN = [], []


def crit(what, detail=""):
    CRIT.append((what, detail))


def warn(what, detail=""):
    WARN.append((what, detail))


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    only_fixable = "--fixable" in sys.argv

    try:
        from utils.core import UserManager
        from utils.api_pipeline_scope import get_staff_roster
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    users = UserManager().users or {}
    try:
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unreadable: %s" % exc)
        return 1

    roster = {}
    roster_names = {}
    for _i, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if not code:
            continue
        roster[code] = {
            "name": str(r.get("Staff Name") or "").strip(),
            "role": str(r.get("Role") or "").strip(),
            "unit": str(r.get("Unit") or "").strip(),
        }
        roster_names.setdefault(roster[code]["name"].lower(), []).append(code)

    try:
        cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    except Exception:
        cfg = {}
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])

    print("=" * 78)
    print("IDENTITY ALIGNMENT")
    print("=" * 78)
    print("  logins            %d" % len(users))
    print("  staff register    %d" % len(roster))
    print("  committees        %d" % len(pal))

    # ── 1. LOGIN -> REGISTER ────────────────────────────────────────────────
    rule("1. DOES EVERY LOGIN POINT AT A REAL STAFF CODE")
    no_code, bad_code, name_differs = [], [], []
    for k, v in users.items():
        code = str(v.get("staff_code", "") or "").strip()
        nm = str(v.get("full_name") or v.get("name") or "").strip()
        if not code:
            no_code.append(k)
        elif code not in roster:
            bad_code.append((k, code))
        elif nm and roster[code]["name"] and nm.lower() != roster[code]["name"].lower():
            name_differs.append((k, nm, roster[code]["name"]))

    if no_code:
        crit("%d login(s) carry NO staff code" % len(no_code),
             "every scoped screen is empty for them - no pipeline, no queue, "
             "no daily log roll-up. %s" % ", ".join(no_code[:6]))
    if bad_code:
        crit("%d login(s) point at a code NOT in the register" % len(bad_code),
             "they resolve to nobody, so cascade scope gives them nothing and "
             "no manager can see their work: %s"
             % ", ".join("%s->%s" % t for t in bad_code[:5]))
    if name_differs:
        warn("%d login(s) have a different name from the register" % len(name_differs),
             "anything matching on NAME rather than code - committee "
             "membership, chairs - will silently miss them")
    if not (no_code or bad_code or name_differs):
        print("  ok  every login resolves to a register entry with the same name")
    else:
        for k, nm, rn in name_differs[:6]:
            print("     %-22s login %r vs register %r" % (k, nm, rn))

    # ── 2. COMMITTEE MEMBERS -> REGISTER AND LOGINS ─────────────────────────
    rule("2. CAN EVERY COMMITTEE MEMBER ACTUALLY LOG IN AND BE MATCHED")
    login_by_code = {}
    login_names = set()
    for k, v in users.items():
        c = str(v.get("staff_code", "") or "").strip()
        if c:
            login_by_code.setdefault(c, k)
        n = str(v.get("full_name") or v.get("name") or "").strip().lower()
        if n:
            login_names.add(n)

    ghost_members, unloggable, chair_unmatched = [], [], []
    for c in pal:
        cname = str(c.get("name") or c.get("code"))
        for m in (c.get("members") or []):
            if not isinstance(m, dict):
                continue
            code = str(m.get("staff_code", "") or "").strip()
            nm = str(m.get("name", "") or "").strip()
            if code and code not in roster:
                ghost_members.append((cname, nm or code, code))
            elif code and code not in login_by_code:
                unloggable.append((cname, nm or code, code))
        chair = str(c.get("chaired_by", "") or "").strip()
        if chair and chair.lower() not in login_names:
            chair_unmatched.append((cname, chair))

    if ghost_members:
        crit("%d committee member(s) are not in the register" % len(ghost_members),
             "they cannot be scoped to anything: %s"
             % ", ".join("%s/%s" % (a, b) for a, b, _c in ghost_members[:4]))
    if unloggable:
        crit("%d committee member(s) have NO LOGIN" % len(unloggable),
             "they are on the committee and cannot sign in to decide: %s"
             % ", ".join("%s/%s" % (a, b) for a, b, _c in unloggable[:4]))
    if chair_unmatched:
        crit("%d chair(s) do not match any login BY NAME" % len(chair_unmatched),
             "the queue matches a chair on their name, so these people see an "
             "empty committee queue however many cases are waiting")
        for cn, ch in chair_unmatched[:6]:
            print("     %-42s chaired_by %r" % (cn[:42], ch))
    if not (ghost_members or unloggable or chair_unmatched):
        print("  ok  every member and chair resolves to a login")

    # ── 3. THE FRAGILE JOIN ─────────────────────────────────────────────────
    rule("3. WHERE THE JOIN IS ON A NAME RATHER THAN A CODE")
    print("  Committee CHAIRS are stored as a name (chaired_by), and matched")
    print("  against a login's full_name. Two people called Joyce, or a login")
    print("  reading 'Joyce' against a register reading 'Joyce Gituura Meeme',")
    print("  and the match fails silently.")
    dupes = {n: c for n, c in roster_names.items() if len(c) > 1}
    if dupes:
        warn("%d name(s) belong to more than one person in the register" % len(dupes),
             "a name-based match cannot tell them apart: %s"
             % ", ".join(list(dupes)[:4]))
    chairs_by_name = sum(1 for c in pal if str(c.get("chaired_by", "") or "").strip())
    no_chair_code = sum(1 for c in pal
                        if str(c.get("chaired_by", "") or "").strip()
                        and not str(c.get("chair_staff_code", "") or "").strip())
    print("\n  committees with a chair:            %d" % chairs_by_name)
    print("  of those WITHOUT a chair staff code: %d" % no_chair_code)
    if no_chair_code:
        crit("%d chair(s) are identified ONLY by name" % no_chair_code,
             "storing chair_staff_code alongside would make this join exact "
             "and end a whole class of silent failure")

    # ── VERDICT ─────────────────────────────────────────────────────────────
    rule("VERDICT")
    if not CRIT and not WARN:
        print("The three stores agree.")
        return 0
    if CRIT:
        print("%d THING(S) THAT WILL SILENTLY BREAK SOMEBODY:\n" % len(CRIT))
        for what, detail in CRIT:
            print("   * %s" % what)
            if detail and not only_fixable:
                print("     %s" % detail)
    if WARN and not only_fixable:
        print("\n%d thing(s) worth knowing:\n" % len(WARN))
        for what, detail in WARN:
            print("   - %s" % what)
            if detail:
                print("     %s" % detail)
    print("")
    print("None of these show up as an error. They show up as a person saying")
    print("the screen does nothing - which is how each one reached the pilot.")
    return 1 if CRIT else 0


if __name__ == "__main__":
    sys.exit(main())
