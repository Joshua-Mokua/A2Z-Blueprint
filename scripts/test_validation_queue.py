#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test the daily-log validation queue as a real logged-in user. READ ONLY.

Prompts for credentials (password hidden), logs in against the live API, then
calls /api/branch-log/validation-queue for a date and prints what a manager
would see.

    python scripts\\test_validation_queue.py
    python scripts\\test_validation_queue.py 2026-08-07

Run it as a script rather than pasting a python -c one-liner: a pasted
one-liner swallows the input() prompt.
"""
import getpass
import sys

API = "http://localhost:8502"


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        import requests
    except ImportError:
        print("requests not installed:  pip install requests")
        return 1

    user = input("username: ").strip()
    if not user:
        print("no username entered — nothing to do.")
        return 1
    pw = getpass.getpass("password: ")

    try:
        r = requests.post(API + "/api/auth/login",
                          json={"username": user, "password": pw}, timeout=30)
    except Exception as exc:
        print("could not reach %s — is uvicorn running?  (%s)" % (API, exc))
        return 1

    if r.status_code != 200:
        print("login failed: HTTP %s  %s" % (r.status_code, r.text[:200]))
        return 1
    body = r.json()
    tok = body.get("access_token")
    if not tok:
        print("login returned no access_token. Response keys: %s" % list(body))
        return 1
    print("logged in as %s (%s)" % (user, body.get("role", "?")))

    url = API + "/api/branch-log/validation-queue"
    if day:
        url += "?date=" + day
    q = requests.get(url, headers={"Authorization": "Bearer " + tok}, timeout=60)
    if q.status_code != 200:
        print("queue failed: HTTP %s  %s" % (q.status_code, q.text[:300]))
        return 1
    d = q.json()

    print("")
    print("date          : %s" % d.get("date"))
    print("working day   : %s %s" % (d.get("working_day"), d.get("label") or ""))
    print("validator mode: %s   <- 'triad' at a branch, 'line_manager' at HO"
          % (d.get("mode") or "(none resolved)"))
    print("rows          : %d" % len(d.get("rows") or []))
    print("pending        : %d" % d.get("pending", 0))
    print("")

    rows = d.get("rows") or []
    if not rows:
        print("No one to validate. Either this user is not a validator for anyone,")
        print("or the date is a rest day.")
        return 0

    print("%-9s %-26s %-30s %-10s %-8s %s"
          % ("CODE", "NAME", "ROLE", "STATUS", "INDEX", "ACTIONABLE"))
    print("-" * 100)
    for x in rows[:40]:
        print("%-9s %-26s %-30s %-10s %-8s %s"
              % (x.get("staff_code", "")[:9],
                 str(x.get("staff_name", ""))[:26],
                 str(x.get("role", ""))[:30],
                 str(x.get("status", ""))[:10],
                 x.get("index", 0),
                 x.get("can_act")))
    if len(rows) > 40:
        print("... %d more" % (len(rows) - 40))
    return 0


if __name__ == "__main__":
    sys.exit(main())
