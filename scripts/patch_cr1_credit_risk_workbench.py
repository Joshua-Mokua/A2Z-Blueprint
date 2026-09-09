#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Give credit risk its own screen, and stop it borrowing the analysts'.

Two rulings are already written into Sidebar.tsx:

    "Credit Analysis is the BANK credit analyst's module - Julius Korir's
     work. The department analyst and the committee members were borrowing it
     and seeing a screen built for somebody else's job."

    "I want his sidebar not to have the Department Review ... the CIS is their
     main workbench."

The menu was split and the page was not: both entries point at /lms. So credit
risk gets the segment analyst's desk - claim from the pool, request documents,
return for rework, mark ready for committee - none of which is their job, and
all of which buries the cases that are.

Points Credit Analysis at /credit-risk, which lists only committee-recommended
cases and offers only the decision. Department Review keeps /lms.

Copy CreditRiskWorkbench.tsx into frontend/web/src/pages/ first.

    python scripts/patch_cr1_credit_risk_workbench.py            # dry run
    python scripts/patch_cr1_credit_risk_workbench.py --apply
"""
import os
import re
import shutil
import sys

APP = os.path.join("frontend", "web", "src", "App.tsx")
SIDEBAR = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
PAGE = os.path.join("frontend", "web", "src", "pages", "CreditRiskWorkbench.tsx")

OLD_ITEM = ("      { path: '/lms',                 label: 'Credit Analysis',  "
            "   matchActive: (p) => p === '/lms' || p.startsWith('/lms/'), "
            "visibleFor: (_m, _a, _c, _md, credit) => credit },")


def main():
    apply = "--apply" in sys.argv
    for f in (APP, SIDEBAR):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1
    if not os.path.isfile(PAGE):
        print("%s is not there yet." % PAGE)
        print("Copy CreditRiskWorkbench.tsx into frontend\\web\\src\\pages\\ first.")
        return 1

    app = open(APP, encoding="utf-8").read()
    sb = open(SIDEBAR, encoding="utf-8").read()
    if "CreditRiskWorkbench" in app:
        print("Already applied.")
        return 1

    # Route it, beside the others.
    # This file imports pages as './pages/X', not '@/pages/X'. Match the shape
    # rather than assuming the alias - that assumption has cost five patches.
    m = re.search(r"^import \{ [A-Za-z]+ \} from '\./pages/[A-Za-z]+';$", app, re.M)
    if not m:
        print("Could not find a page import to sit beside.")
        return 1
    app = app.replace(
        m.group(0),
        "import { CreditRiskWorkbench } from './pages/CreditRiskWorkbench';\n"
        + m.group(0), 1)
    r = re.search(r'^(\s*)<Route path="/pipeline/new".*$', app, re.M)
    if not r:
        print("Could not find a route to sit beside.")
        return 1
    indent = r.group(1)
    app = (app[:r.end()]
           + "\n%s{/* Credit risk decides on committee-recommended cases. The"
             " analysts' desk stays at /lms. */}" % indent
           + '\n%s<Route path="/credit-risk" element={<CreditRiskWorkbench />} />'
             % indent
           + app[r.end():])

    # Point the menu entry at it.
    if sb.count(OLD_ITEM) != 1:
        # Whitespace in that file has moved before; match on the label instead.
        m2 = re.search(r"^\s*\{ path: '/lms',\s+label: 'Credit Analysis',.*$",
                       sb, re.M)
        if not m2:
            print("Could not find the Credit Analysis menu entry.")
            return 1
        old_item = m2.group(0)
    else:
        old_item = OLD_ITEM
    new_item = old_item.replace("path: '/lms',", "path: '/credit-risk',", 1)
    new_item = new_item.replace(
        "matchActive: (p) => p === '/lms' || p.startsWith('/lms/')",
        "matchActive: (p) => p.startsWith('/credit-risk')", 1)
    sb = sb.replace(old_item, new_item, 1)

    if "/credit-risk" not in sb:
        print("The menu entry was not repointed.")
        return 1
    if "path: '/lms'" not in sb:
        print("Department Review lost its route - it must keep /lms.")
        return 1
    if app.count("{") != app.count("}") or sb.count("{") != sb.count("}"):
        print("Braces unbalanced.")
        return 1
    print("Credit Analysis points at /credit-risk; Department Review keeps /lms.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Run tsc afterwards.")
        return 0

    for path, src in ((APP, app), (SIDEBAR, sb)):
        shutil.copy2(path, path + ".pre_cr1")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("Applied %s" % path)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
