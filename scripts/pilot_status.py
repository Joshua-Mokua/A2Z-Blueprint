#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
What is actually running on this box? READ ONLY. Safe to run any time.

WHY THIS EXISTS. Fixes have been shipped, confirmed as applied, and then the
same faults came back - which wastes everybody's time and leaves the person who
shipped them looking as though they had not. Nobody was at fault: there was no
way to SEE what a box was running, so "applied" meant "I merged it" and the
rebuild or the restart or the config step was missed.

This prints one page. Run it and send the whole output back. It answers, for
each shipped fix, whether the code is present AND whether the configuration it
needs has been done - because most of these need both, and code alone changes
nothing a user would notice.

    python scripts\\pilot_status.py

It changes nothing. It cannot break anything. Run it as often as you like.
"""
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

OK, MISSING, PARTIAL = "OK     ", "MISSING", "PARTIAL"
_rows = []


def row(state, what, detail=""):
    _rows.append((state, what, detail))
    print("  [%s] %-46s %s" % (state, what[:46], detail))


def head(t):
    print("\n" + "-" * 76)
    print(t)
    print("-" * 76)


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def jload(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def git(*args):
    try:
        return subprocess.check_output(("git",) + args, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def main():
    print("=" * 76)
    print("PILOT STATUS  -  %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 76)

    head("WHICH CODE IS THIS")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    print("  branch          %s" % (branch or "(unknown)"))
    print("  commit          %s" % (git("rev-parse", "--short", "HEAD") or "(unknown)"))
    print("  last commit     %s" % (git("log", "-1", "--pretty=%s")[:60] or "(unknown)"))
    # --oneline and --pretty fight each other; --pretty alone is what works.
    merged = git("log", "-25", "--merges", "--pretty=%s")
    rel = [l for l in merged.split("\n") if "release/" in l]
    if rel:
        print("  last release    %s" % rel[0][:60])
        if len(rel) > 1:
            print("  before that     %s" % rel[1][:60])
    else:
        print("  last release    NONE FOUND - has a release been merged?")

    api = read(os.path.join("utils", "api.py"))
    if not api:
        print("\n  Cannot read utils/api.py - run this from the project root.")
        return 1

    # ── THE CODE ────────────────────────────────────────────────────────────
    # Each marker is a string that only exists if that fix is present. Checking
    # the code rather than the commit log, because a merge can be reverted, a
    # file can be restored from a backup, and the log would still look right.
    head("FIXES - IS THE CODE HERE")
    perms = read(os.path.join("utils", "api_lms_permissions.py"))
    routes = read(os.path.join("utils", "api_lms_routes.py"))
    blog = read(os.path.join("utils", "branch_log.py"))
    sidebar = read(os.path.join("frontend", "web", "src", "components", "Sidebar.tsx"))
    viewer = read(os.path.join("frontend", "web", "src", "components",
                               "DocumentViewerModal.tsx"))

    checks = [
        ("Analyst can submit to the DCC", "staff_code" in perms and "_analyst_segment" in perms
         and perms.count("staff_code") >= 2),
        ("Documents can be assigned to a role", "DOC_ATTACHERS" in api),
        ("Submit button names the real next stage", "anchor_stage" in api),
        ("Analyst can attach on a case", "_AnalystDocUpload" in routes),
        ("Analyst can request a document", "documents_requested" in routes),
        ("Daily log keeps earlier hours", "HOURLY IS MERGED" in blog),
        ("Legacy .doc explained, not just refused", "legacy-doc" in viewer),
        ("Modules can be hidden by config", "hidden.has(item.path)" in sidebar),
        ("Deal advances when validated", "ADVANCE ON VALIDATION" in api),
    ]
    for label, present in checks:
        row(OK if present else MISSING, label,
            "" if present else "not in this build")

    # ── THE BUILD ───────────────────────────────────────────────────────────
    # Code on disk is not code in the browser. This is the step most often
    # missed, and the one that makes a fix look unapplied when it is not.
    head("FRONTEND - HAS IT BEEN REBUILT SINCE")
    dist = os.path.join("frontend", "web", "dist")
    src = os.path.join("frontend", "web", "src")
    if not os.path.isdir(dist):
        row(MISSING, "frontend/web/dist", "never built - run pnpm build")
    else:
        newest_src, newest_dist = 0, 0
        for base, _d, files in os.walk(src):
            for f in files:
                newest_src = max(newest_src, os.path.getmtime(os.path.join(base, f)))
        for base, _d, files in os.walk(dist):
            for f in files:
                newest_dist = max(newest_dist, os.path.getmtime(os.path.join(base, f)))
        if newest_dist >= newest_src:
            row(OK, "frontend build is newer than the source", "")
        else:
            row(MISSING, "frontend build is OLDER than the source",
                "run: pnpm build  - the browser is showing old code")

    # ── THE CONFIGURATION ───────────────────────────────────────────────────
    # Several fixes do nothing until somebody configures them. Shipping the
    # code and stopping there is why "nothing changed" is a fair report.
    head("CONFIGURATION - HAS THE SETUP BEEN DONE")
    lms = jload(os.path.join("data", "lms_config.json"))
    pal = ((lms.get("credit_workflow") or {}).get("committee_palette") or [])
    branch_cttees = [c for c in pal if str(c.get("kind", "")).lower() == "branch"]
    if branch_cttees:
        row(OK, "Branch credit committees exist", "%d" % len(branch_cttees))
    else:
        row(MISSING, "Branch credit committees",
            "none - POST /api/admin/committee-palette/generate-branch")

    ps = jload(os.path.join("data", "pipeline_settings.json"))
    flows = ps.get("product_flows") or {}
    with_gate = [p for p, e in flows.items() if (e or {}).get("committee_journey")]
    row(OK if with_gate else MISSING, "Products with a committee gate",
        ", ".join(with_gate[:4]) if with_gate
        else "none - Admin > product flow > + Add committee gate")

    # A flow with no closing stage cannot be closed by anyone, ever.
    noclose = []
    for p, e in flows.items():
        stages = [str(s.get("stage", "")) for s in ((e or {}).get("stages") or [])]
        if stages and not any("closed" in s.lower() for s in stages):
            noclose.append(p)
    if noclose:
        # A flow with no Closed Won / Closed Lost gives the owner nowhere to
        # close TO. The deal is not stuck by a bug - there is no exit.
        row(MISSING, "Products that can never be closed (%d)" % len(noclose),
            ", ".join(noclose[:4]) + (" +%d more" % (len(noclose) - 4)
                                      if len(noclose) > 4 else ""))
    else:
        row(OK, "Every product flow has a closing stage", "")

    # Documents assigned to somebody other than the deal owner.
    assigned = 0
    for _p, e in flows.items():
        for d in ((e or {}).get("required_documents") or []):
            if isinstance(d, dict) and str(d.get("attached_by", "owner")) != "owner":
                assigned += 1
    row(OK if assigned else MISSING, "Documents assigned to an analyst",
        "%d" % assigned if assigned
        else "none - every document still falls to the deal owner")

    org = jload(os.path.join("data", "org_config.json"))
    hidden = org.get("hidden_modules")
    row(OK if hidden else MISSING, "Modules hidden for the bank",
        ", ".join(hidden) if hidden else "not set in data/org_config.json")

    # ── THE VERDICT ─────────────────────────────────────────────────────────
    miss = [r for r in _rows if r[0] == MISSING]
    print("\n" + "=" * 76)
    if not miss:
        print("EVERYTHING SHIPPED IS PRESENT AND CONFIGURED.")
        print("If a user still reports a fault, it is something new - say so and")
        print("send this page with it.")
        return 0

    print("%d ITEM(S) NOT IN PLACE:" % len(miss))
    for _s, what, detail in miss:
        print("   * %-44s %s" % (what[:44], detail))
    print("")
    print("Most of these are one step each. Send this whole page back rather")
    print("than a description - it says exactly which step, and it removes the")
    print("guessing on both sides.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
