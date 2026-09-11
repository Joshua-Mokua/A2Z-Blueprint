#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""What is actually in this codebase, right now, on this machine.

Alex says everything is applied; the users see old behaviour. That means the
running code and what we think is running have drifted. This ends the argument:
run it on the box that serves the bank's uvicorn, and it reports the true state
of every fix by looking at the code itself - not at what anyone remembers
committing.

    python whats_actually_live.py

Read only. Send the output back.
"""
import os
import subprocess
import sys


def has(path, needle):
    try:
        return needle in open(path, encoding="utf-8", errors="replace").read()
    except Exception:
        return None


CHECKS = [
    # label, file, a string that only exists if the fix is present
    ("Rework stage in flows (config)", "data/pipeline_settings.json", '"Rework"'),
    ("submit gate accepts Rework", "utils/api.py", 'lower() == "rework"'),
    ("document list merges the deal", "utils/api_lms_routes.py", "_merged_provided"),
    ("  (or older _provided merge)", "utils/api_lms_routes.py", '"provided": _provided'),
    ("ready advances the deal (RC3)", "utils/api_lms_routes.py", "READY MEANS THE DEAL MOVES"),
    ("ready advance is tolerant (FX2)", "utils/api_lms_routes.py", "department committee even when"),
    ("rework returns the case (RW3)", "utils/api_lms_routes.py", "AND REWORK MEANS RETURNED"),
    ("one handover module (HV1)", "utils/handover.py", "def send_back"),
    ("seek input (SI1)", "utils/api_lms_routes.py", "seek-input"),
    ("email the handovers (EM1/_tell)", "utils/api_lms_routes.py", "_tell("),
    ("credit admin can ask (CR2)", "utils/api_credit_admin_routes.py", "request-from-branch"),
    ("analyst decides own case (DC1)", "utils/api_lms_routes.py", "no manager step in that flow"),
    ("committee marks the case (CS2)", "utils/api.py", "AND SAY SO ON THE CREDIT CASE"),
    ("dept-only reaches credit risk (CS3)", "utils/api.py", "ONLY A DEPARTMENT COMMITTEE SENDS"),
    ("deal follows the case (SOT1)", "utils/core.py", "WHERE A CASE STANDS"),
    ("show the server reason (ERR1)", "frontend/web/src/lib/api.ts", "The server explains its refusals"),
    ("credit risk workbench All tab (CW2)", "frontend/web/src/pages/CreditRiskWorkbench.tsx", "tab === 'all'"),
    ("Credit Analysis workbench page", "frontend/web/src/pages/CreditRiskWorkbench.tsx", "Credit Risk"),
]


def main():
    print("=" * 82)
    print("WHAT IS ACTUALLY IN THIS CODEBASE")
    print("=" * 82)
    br = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True)
    head = subprocess.run(["git", "log", "--oneline", "-1"], capture_output=True)
    print("  branch:  %s" % (br.stdout or b"?").decode("utf-8", "replace").strip())
    print("  HEAD:    %s" % (head.stdout or b"?").decode("utf-8", "replace").strip())
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True)
    d = [l for l in (dirty.stdout or b"").decode("utf-8", "replace").splitlines()
         if l and not l.startswith("??")]
    print("  uncommitted changes: %d%s" % (len(d),
          "  <- applied but NOT committed" if d else ""))
    print()

    present = missing = 0
    for label, path, needle in CHECKS:
        r = has(path, needle)
        if r is None:
            print("  ????  %-40s (file not found: %s)" % (label, path))
        elif r:
            print("  LIVE  %-40s" % label)
            present += 1
        else:
            print("  ----  %-40s missing" % label)
            missing += 1

    print("\n" + "=" * 82)
    print("  live %d, missing %d" % (present, missing))
    print("=" * 82)
    print("""
  HOW TO READ THIS

  - Run it on the box whose uvicorn the bank actually uses.
  - "applied but NOT committed" with everything LIVE means the fixes are on
    this box but were never pushed - the fix is: git add -A && git commit &&
    git push. Then anyone pulling gets them.
  - Fixes showing "missing" here are genuinely not in this code, whatever was
    reported. Re-apply those.
  - A frontend fix (ERR1, CW2, the workbench) showing LIVE still needs
    'pnpm build' before users see it - the source is patched but the served
    bundle may be old. If in doubt, rebuild.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
