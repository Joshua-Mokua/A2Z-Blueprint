#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Read the decisions mailbox and act on every reply in it.

    python scripts/poll_email_decisions.py --dry-run     show what would happen
    python scripts/poll_email_decisions.py               act on them

Run it every minute from a scheduler, or by hand while testing. Every accepted
and refused reply is on the journey and the audit trail.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    dry = "--dry-run" in sys.argv
    from utils.email_decisions import poll_once
    try:
        c = poll_once(dry_run=dry)
    except Exception as exc:
        print("Could not read the mailbox: %s" % str(exc)[:80])
        print("Check imap_host / imap_user / imap_password in data/email_config.json")
        return 1
    print("  seen %d, acted %d, refused %d, not a decision %d"
          % (c["seen"], c["acted"], c["refused"], c["ignored"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
