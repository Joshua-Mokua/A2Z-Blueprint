#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Email a case to somebody for their decision.

    python scripts/send_case_by_email.py --app LMS00035 --to KE1219 --dry-run
    python scripts/send_case_by_email.py --app LMS00035 --to KE1219
    python scripts/send_case_by_email.py --all-recommended --to KE1219

--dry-run prints the email that would go, and sends nothing.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    dry = "--dry-run" in sys.argv
    app_id = to = ""
    for flag in ("--app", "--to"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--app":
                    app_id = sys.argv[i + 1].strip()
                else:
                    to = sys.argv[i + 1].strip()
    all_rec = "--all-recommended" in sys.argv
    if not to or (not app_id and not all_rec):
        print("--app LMS00035 --to KE1219   or   --all-recommended --to KE1219")
        return 1

    from utils.email_decisions import send_for_decision
    from utils.api_lms_routes import _lam

    if all_rec:
        ids = [str(a.get("id")) for a in (getattr(_lam(), "apps", []) or [])
               if str(a.get("status") or "").lower() == "committee_recommended"]
    else:
        ids = [app_id]

    asked_by = {"full_name": "The system", "staff_code": "", "username": "system"}
    print("=" * 76)
    print("SEND FOR DECISION%s" % ("  (dry run)" if dry else ""))
    print("=" * 76)
    for i in ids:
        try:
            r = send_for_decision(i, to, asked_by, dry_run=dry)
        except Exception as exc:
            print("  %-11s FAILED  %s" % (i, str(exc)[:60]))
            continue
        if dry:
            print("  %-11s -> %s  (%d document%s)" % (
                i, r["to"], r["documents"], "" if r["documents"] == 1 else "s"))
            if len(ids) == 1:
                print("\n  SUBJECT: %s" % r["subject"])
                print("  REPLY-TO: %s\n" % r["reply_to"])
                print(r["body"])
        else:
            print("  %-11s %s %s  (%d document%s, token %s)" % (
                i, "sent to" if r.get("sent") else "NOT SENT to", r["to"],
                r["documents"], "" if r["documents"] == 1 else "s",
                r.get("token")))
    if not dry:
        print("\n  Replies are read by:  python scripts/poll_email_decisions.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
