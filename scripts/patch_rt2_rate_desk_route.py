#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
RT2 - route the Treasury Rate Desk on the pilot's own App.tsx.

UI2 carries whole files, and App.tsx cannot be one of them: it imports every
page THIS box has - Origin Channels, Warehouse, Prospect Detail - and the pilot
has none of them. Shipping it broke the build with "cannot find module", and
Warehouse is the page we have spent weeks keeping out of the pilot.

So a new page needs its route added by anchor, on whatever App.tsx the target
actually has. That is what this does, and nothing else.

Usage (from project root, .venv active):
    python scripts\apply_rt2_rate_desk_route.py            # dry run
    python scripts\apply_rt2_rate_desk_route.py --apply
"""
import os
import re
import shutil
import sys

APP = os.path.join("frontend", "web", "src", "App.tsx")
BACKUP_SUFFIX = ".pre_rt2"

# The pilot's App.tsx uses RELATIVE paths and named imports - `import { Troops }
# from './pages/Troops';` - while this box uses the '@/pages' alias. Assuming
# our own style is how a patch that works here fails there, so the import is
# built to match whatever the file already does.
IMPORT_DEFAULT_ALIAS = "import TreasuryRateDesk from '@/pages/TreasuryRateDesk';"
IMPORT_DEFAULT_REL = "import TreasuryRateDesk from './pages/TreasuryRateDesk';"
ROUTE_LINE = ('                    <Route path="/treasury/rates"        '
              'element={<TreasuryRateDesk />} />')


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(APP):
        print("ABORT: %s not found." % APP)
        return 1
    s = open(APP, encoding="utf-8").read()
    if "TreasuryRateDesk" in s:
        print("ABORT: RT2 looks applied.")
        return 1

    page = os.path.join("frontend", "web", "src", "pages", "TreasuryRateDesk.tsx")
    if not os.path.isfile(page):
        print("ABORT: %s is not here. Apply UI2 first - it carries the page."
              % page)
        return 1

    m = re.search(r"^import Troops from ['\"][^'\"]+['\"];$", s, re.M)
    if not m:
        m = re.search(r"^import .*Troops.*$", s, re.M)
    if not m:
        print("ABORT: cannot find the Troops import to anchor on.")
        return 1
    _line = IMPORT_DEFAULT_REL if "./pages/" in m.group(0) else IMPORT_DEFAULT_ALIAS
    s = s[:m.end()] + "\n" + _line + s[m.end():]

    r = re.search(r'^\s*<Route path="/troops".*$', s, re.M)
    if not r:
        print("ABORT: cannot find the /troops route to anchor on.")
        return 1
    s = s[:r.end()] + "\n" + ROUTE_LINE + s[r.end():]
    print("  ok  the rate desk is imported and routed")

    # The NAME appears several times in one import line and twice in a route
    # element. Counting the name found four and refused a correct edit. Count
    # the LINES that matter.
    _imports = len([l for l in s.split("\n")
                    if l.strip().startswith("import") and "TreasuryRateDesk" in l])
    _routes = len([l for l in s.split("\n")
                   if "<Route" in l and "TreasuryRateDesk" in l])
    if _imports != 1 or _routes != 1:
        print("ABORT: %d import(s) and %d route(s); expected one of each."
              % (_imports, _routes))
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if s.count(op) != s.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: one import, one route, balanced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(APP, APP + BACKUP_SUFFIX)
    open(APP, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % APP)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
