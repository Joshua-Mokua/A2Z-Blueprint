#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does the branch triad resolve? — Fortis by default. READ ONLY.

Part 1 runs OFFLINE against the staff register: no login, no API, no uvicorn.
It answers the only question that matters — for each staff member in the
branch, who does daily_log_validators_for() say may validate them?

Part 2 (optional, --api) logs in as each triad member using the standard
convention (username = staff code, password = "EcoStaff" + last 4 CHARACTERS
of the code, e.g. KE754 -> EcoStaffE754, KE1034 -> EcoStaff1034) and calls
/api/branch-log/validation-queue so you can see the live result.

    python scripts\\test_branch_triad.py
    python scripts\\test_branch_triad.py Westlands
    python scripts\\test_branch_triad.py Fortis --api 2026-08-07
"""
import os
import sys

sys.path.insert(0, os.getcwd())

API = "http://localhost:8502"


def pw_for(code: str) -> str:
    """EcoStaff + last 4 characters of the staff code."""
    return "EcoStaff" + str(code).strip()[-4:]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    branch = args[0] if args else "Fortis"
    day = args[1] if len(args) > 1 else ""
    use_api = "--api" in sys.argv

    try:
        import pandas as pd
    except ImportError:
        print("pandas not available.")
        return 1

    reg = os.path.join("data", "staff_register.xlsx")
    if not os.path.isfile(reg):
        print("ABORT: %s not found." % reg)
        return 1
    df = pd.read_excel(reg)

    ucol = "Branch" if "Branch" in df.columns else "Unit"
    people = df[df[ucol].astype(str).str.strip().str.lower() == branch.strip().lower()]
    if people.empty:
        vals = sorted({str(v).strip() for v in df[ucol].dropna()})
        print("No staff found in %r. Available %s values:" % (branch, ucol))
        for v in vals:
            print("   ", v)
        return 1

    print("=" * 78)
    print("BRANCH: %s   (%d staff in the register)" % (branch, len(people)))
    print("=" * 78)

    from utils.org_validator import _triad_roles, daily_log_validators_for
    wanted = [w.strip().lower() for w in _triad_roles()]
    print("triad roles configured: %s" % _triad_roles())
    print("")

    print("-- roles present in this branch --")
    hits = []
    for _, r in people.iterrows():
        role = str(r.get("Role", "")).strip()
        code = str(r.get("Staff Code", "")).strip()
        mark = "  <-- TRIAD" if role.lower() in wanted else ""
        print("   %-9s %-28s %-46s%s"
              % (code, str(r.get("Staff Name", ""))[:28], role[:46], mark))
        if role.lower() in wanted:
            hits.append((code, str(r.get("Staff Name", "")), role))

    print("")
    if not hits:
        print("*** NO TRIAD MEMBER MATCHED in %s." % branch)
        print("    The role strings above did not match the configured list.")
        print("    Fix by editing data/org_config.json ->")
        print("    daily_log_branch_validator_roles, not by changing code.")
    else:
        print("triad members resolved: %d" % len(hits))
        for c, n, ro in hits:
            print("   %-9s %-26s %s" % (c, n[:26], ro))

    print("")
    print("-- who validates whom (first 8 staff) --")
    for _, r in people.head(8).iterrows():
        code = str(r.get("Staff Code", "")).strip()
        res = daily_log_validators_for(code)
        vs = res.get("validators", [])
        names = ", ".join(str(v.get("validator_name") or v.get("validator_code"))[:22]
                          for v in vs) or "(none)"
        print("   %-9s %-24s mode=%-12s -> %s"
              % (code, str(r.get("Staff Name", ""))[:24], res.get("mode", ""), names))

    if not use_api:
        print("")
        print("Add --api to also log in as each triad member and call the live queue.")
        return 0

    # ── Part 2: live API ────────────────────────────────────────────────────
    try:
        import requests
    except ImportError:
        print("requests not installed:  pip install requests")
        return 1

    print("")
    print("=" * 78)
    print("LIVE QUEUE (logging in as each triad member)")
    print("=" * 78)
    for code, name, role in hits:
        u, p = code, pw_for(code)
        try:
            lr = requests.post(API + "/api/auth/login",
                               json={"username": u, "password": p}, timeout=30)
        except Exception as exc:
            print("%-9s could not reach the API (%s)" % (code, exc))
            continue
        if lr.status_code != 200 or "access_token" not in lr.json():
            print("%-9s %-24s login FAILED (HTTP %s) — tried password %r"
                  % (code, name[:24], lr.status_code, p))
            continue
        tok = lr.json()["access_token"]
        url = API + "/api/branch-log/validation-queue" + ("?date=" + day if day else "")
        qr = requests.get(url, headers={"Authorization": "Bearer " + tok}, timeout=60)
        if qr.status_code != 200:
            print("%-9s queue HTTP %s  %s" % (code, qr.status_code, qr.text[:120]))
            continue
        d = qr.json()
        print("%-9s %-24s mode=%-12s rows=%-4d pending=%d"
              % (code, name[:24], d.get("mode", ""), len(d.get("rows") or []),
                 d.get("pending", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
