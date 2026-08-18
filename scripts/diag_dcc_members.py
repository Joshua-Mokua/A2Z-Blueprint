#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Where are the department committee's members? READ ONLY.

The voting panel shows "0/4 voted", four nameless rows and an empty dropdown.
That is the panel rendering what the config actually holds, so the question is
which of two places is empty - and they are different places:

    credit_workflow.committee_palette[B1].members   the PIPELINE gate's roster,
                                                    what the Admin screen edits
    credit_workflow.dcc.members                     the LMS roster, what the
                                                    voting panel reads

enable_dcc.py copies the first into the second. If the first is blank the
second will be too, and naming members in Admin without re-running it leaves
the panel reading yesterday's copy.

This shows both, side by side, so the answer is visible rather than inferred.

    python scripts\\diag_dcc_members.py
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def show(label, members):
    print("  %s: %d entr%s" % (label, len(members), "y" if len(members) == 1 else "ies"))
    if not members:
        print("     (none)")
        return 0
    real = 0
    for m in members:
        if not isinstance(m, dict):
            print("     %r  <- not an object" % (m,))
            continue
        code = str(m.get("staff_code", "") or "").strip()
        name = str(m.get("name", "") or "").strip()
        ident = str(m.get("id", "") or m.get("member_id", "") or "").strip()
        blank = not code and not name
        real += 0 if blank else 1
        print("     %-10s %-28s role=%-22s id=%-10s%s"
              % (code or "—", (name or "—")[:28], (m.get("role") or "—")[:22],
                 ident or "—", "   <- BLANK" if blank else ""))
    return real


def main():
    p = os.path.join("data", "lms_config.json")
    if not os.path.isfile(p):
        print("ABORT: %s not found." % p)
        return 1
    cfg = json.load(open(p, encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []

    print("=" * 78)
    print("DEPARTMENT COMMITTEE MEMBERS")
    print("=" * 78)

    print("\nTHE PALETTE (what the Admin screen edits):")
    total_real = 0
    for c in pal:
        if str(c.get("kind", "")).lower() == "branch":
            continue
        print("\n  %s — %s" % (c.get("code"), c.get("name")))
        if c.get("chaired_by"):
            print("     chair: %s" % c.get("chaired_by"))
        total_real += show("     members", c.get("members") or [])

    dcc = cw.get("dcc") or {}
    print("\n" + "-" * 78)
    print("THE LMS ROSTER (what the voting panel reads):")
    print("  enabled: %s" % bool(dcc.get("enabled")))
    print("  name   : %s" % (dcc.get("name") or "—"))
    print("  copied from: %s" % (dcc.get("source_committee") or "—"))
    dcc_real = show("  members", dcc.get("members") or [])

    print("\n" + "=" * 78)
    if dcc_real:
        print("The panel has %d real member(s). If the screen still shows blanks," % dcc_real)
        print("uvicorn is serving an older copy - restart it.")
        return 0
    if total_real:
        print("The PALETTE has real members but the LMS roster does not.")
        print("They were named in Admin after the roster was copied. Re-copy:")
        print("   python scripts\\enable_dcc.py --apply")
        return 1
    print("BOTH ARE EMPTY. Nobody has been named to a department committee -")
    print("the blank rows are placeholders, not people.")
    print("")
    print("Name them in Administration > Credit Committees, or seed from the")
    print("staff register the way the branch committees were:")
    print("   python scripts\\seed_committee_members.py --apply")
    print("   python scripts\\enable_dcc.py --apply")
    return 1


if __name__ == "__main__":
    sys.exit(main())
