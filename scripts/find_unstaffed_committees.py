#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Which committees can nobody see? READ ONLY.

THE ELDORET FAULT (2026-08-14). A branch submitted a case to its credit
committee and it appeared in nobody's queue. Managers had gathered for a second
day and could not touch a case.

The routing was right, the stage was right, the queue endpoint was right. The
committee had NO CHAIR AND NO MEMBERS - so there was nobody for the queue to
show it to, and nothing said so. The case went to a committee that exists on
paper and is staffed by no one.

Measured on the real code path:

    chair named, members named   the chair sees it
    chair named, no members      the chair sees it
    chair named only, not member the chair sees it
    NO CHAIR, NO MEMBERS         NOBODY SEES IT

An unstaffed committee is a silent black hole: cases enter it and stop, with no
error anywhere. This lists every one of them before a case is sent there.

    python scripts\\find_unstaffed_committees.py
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    p = os.path.join("data", "lms_config.json")
    if not os.path.isfile(p):
        print("ABORT: %s not found." % p)
        return 1
    cfg = json.load(open(p, encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])

    blind, thin, fine = [], [], []
    for c in pal:
        code = str(c.get("code") or "?")
        chair = str(c.get("chaired_by", "") or "").strip()
        mem = [m for m in (c.get("members") or [])
               if isinstance(m, dict)
               and (str(m.get("staff_code", "")).strip() or str(m.get("name", "")).strip())]
        where = str(c.get("branch") or c.get("name") or "")[:26]
        quorum = c.get("min_quorum_count") or 2
        if not chair and not mem:
            blind.append((code, where))
        elif len(mem) < quorum:
            thin.append((code, where, len(mem), quorum, chair or "no chair"))
        else:
            fine.append((code, where, len(mem)))

    print("=" * 78)
    print("COMMITTEE STAFFING")
    print("=" * 78)
    print("  properly staffed        %d" % len(fine))
    print("  below quorum            %d" % len(thin))
    print("  NOBODY AT ALL           %d" % len(blind))

    if blind:
        print("\n  *** THESE ARE BLACK HOLES. A case routed to one of them")
        print("      appears in NO queue and nothing reports an error:\n")
        for code, where in blind:
            print("     %-14s %s" % (code, where))
        print("\n      Name at least a chair:")
        print("        python scripts\\name_dcc_members.py --committee %s \\"
              % blind[0][0])
        print("            --members <names> --deputies <names> --apply")

    if thin:
        print("\n  Below quorum - they can be seen, but can never decide:\n")
        for code, where, n, q, chair in thin:
            print("     %-14s %-24s %d of %d   chair: %s"
                  % (code, where, n, q, chair[:22]))

    if not blind and not thin:
        print("\nEvery committee has somebody who can see and decide its cases.")
        return 0
    return 1 if blind else 0


if __name__ == "__main__":
    sys.exit(main())
