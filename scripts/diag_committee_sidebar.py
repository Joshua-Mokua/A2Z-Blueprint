#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Which sidebar entries will each committee member actually see? READ ONLY.

RULING (2026-08-22): "will their login have the Manager Queues or the
Department Review to access?"

The previous diagnostic answered "yes" by matching role words, which was a
GUESS dressed as a finding. This reads the ACTUAL rule out of Sidebar.tsx and
applies it to each member's real role string.

    Department Review   shown when isCreditStaff
                        = admin, or MD/CEO, or the role matches
                          credit|analys|underwrit|recover|collection|
                          treasur|disburs
                        AND the role is NOT credit risk / credit admin /
                          remedial / recover  (they get CIS instead)

    Manager Queues      shown when isMgr

A COMMITTEE SEAT GRANTS NEITHER. Membership lives in lms_config.json; the
sidebar is decided by the ROLE STRING on the user record. A head of consumer
banking can chair a credit committee and still not see Department Review,
because "Head of Consumer Banking" contains none of those words.

That is not a bug to route around. It is the question worth answering before
telling eight people to log in and look for a menu that is not there.

    python scripts\diag_committee_sidebar.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.getcwd())

CREDIT = re.compile(r"credit|analys|underwrit|recover|collection|treasur|disburs", re.I)
CIS_ONLY = re.compile(r"credit risk|credit admin|remedial|recover", re.I)
MD = ("managing director", "chief executive")
MGR = re.compile(r"manager|head|director|chief|supervisor|lead", re.I)


def main():
    cfg_path = os.path.join("data", "lms_config.json")
    if not os.path.isfile(cfg_path):
        print("ABORT: %s not found." % cfg_path)
        return 1
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []

    try:
        from utils.core import UserManager
        users = UserManager().users or {}
    except Exception as exc:
        print("ABORT: cannot read the user store: %s" % str(exc)[:60])
        return 1

    by_code = {}
    for login, rec in users.items():
        c = str(rec.get("staff_code", "")).strip().lower()
        if c:
            by_code[c] = (login, rec)

    print("=" * 88)
    print("WHAT EACH COMMITTEE MEMBER WILL SEE IN THE SIDEBAR")
    print("=" * 88)
    print("  The rule is read from Sidebar.tsx, not guessed from the role.\n")

    missing = []
    for c in pal:
        members = [m for m in (c.get("members") or [])
                   if str(m.get("staff_code", "")).strip()]
        if not members:
            continue
        print("  %s  %s" % (c.get("code"), c.get("name")))
        print("     %-26s %-34s %-8s %s"
              % ("MEMBER", "ROLE", "DEPT REV", "MGR QUEUES"))
        for m in members:
            code = str(m.get("staff_code", "")).strip().lower()
            login, rec = by_code.get(code, (None, {}))
            role = str(rec.get("role", "") or m.get("role", "") or "")
            is_admin = bool(rec.get("is_admin"))
            is_md = any(t in role.lower() for t in MD)
            credit = is_admin or is_md or bool(CREDIT.search(role))
            cis_only = bool(CIS_ONLY.search(role))
            dept = credit and not cis_only
            mgr = is_admin or is_md or bool(MGR.search(role))

            flag = ""
            if not login:
                flag = "  <- NO LOGIN"
            elif not dept:
                flag = "  <- cannot reach the committee"
                missing.append((c.get("code"), m.get("name"), role))
            print("     %-26s %-34s %-8s %-10s%s"
                  % (str(m.get("name"))[:26], role[:34],
                     "yes" if dept else "NO", "yes" if mgr else "no", flag))
        print("")

    print("=" * 88)
    if missing:
        print("SOME MEMBERS CANNOT REACH THE COMMITTEE SCREEN")
        print("=" * 88)
        for code, name, role in missing:
            print("  * %-28s %s" % (name, role))
        print("\n  Department Review is where the committee tab lives. Without")
        print("  it these members can be seated, be sent cases and still have")
        print("  no way to open one.")
        print("\n  THE FIX IS A DECISION, NOT A SCRIPT:")
        print("     - widen the sidebar rule so a seated committee member")
        print("       always sees Department Review, whatever their role; or")
        print("     - accept that only credit-titled staff sit on committees.")
        print("\n  The first is probably right - a committee is a governance")
        print("  body, not a department - but it changes who sees a screen in")
        print("  a bank, so it is yours to make.")
        return 1
    print("EVERY SEATED MEMBER CAN REACH DEPARTMENT REVIEW")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
