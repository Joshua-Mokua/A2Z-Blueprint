#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WHS - the release strips the Deals Warehouse menu entry. For the builder.

FOUND 2026-08-21, checking a release before it went out: "nothing on the
warehouse should travel to Alex, confirm."

Most of it does not. The pilot has no Warehouse.tsx, no route, no
api_warehouse.py, no deals_warehouse.py, and NO CHAIN PATCHER WRITES ANY OF
THEM. The three warehouse client functions inside api.ts are dead code without
a page to call them.

BUT UI2's Sidebar.tsx CARRIES THE MENU ENTRY. Shipped as it is, an RM gets a
"Deals Warehouse" item in the navigation that leads to a blank page - which is
worse than not having it, because it looks like something broke rather than
something that was deliberately held back.

WHY THE ENTRY IS IN UI2 AT ALL, and why it must stay there: it is a REAL menu
item on the developer's box, where the warehouse is built and used daily. An
earlier fix removed it from UI2's copy, which kept the pilot clear and deleted
a working menu item from the developer's own screen every time UI2 was applied.

A PATCH APPLIED IN TWO PLACES CANNOT MAKE A DECISION THAT IS ONLY RIGHT IN ONE
OF THEM. "Not for the pilot yet" is a release decision, so it belongs to the
release builder - which is here.

The strip runs after the replay and before the safety check, and the safety
check then confirms zero entries survive. If it ever fails to strip, the build
ABORTS rather than shipping a link to nothing.

Usage (from project root, .venv active):
    python scripts\patch_whs_strip_at_build.py            # dry run
    python scripts\patch_whs_strip_at_build.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP_SUFFIX = ".pre_whs"

ANCHOR = '''    print("\\n" + "=" * 72)
    print("SAFETY CHECK")
    print("=" * 72)'''

BLOCK = '''    # ── THE WAREHOUSE MENU ENTRY DOES NOT TRAVEL ────────────────────────────
    # The pilot has no warehouse page, route or backend - it is deliberately
    # held back until it is well built. UI2 carries the menu entry because it
    # is a REAL item on the developer's box, so it is stripped HERE, at build,
    # rather than baked out of a patch that is applied in both places.
    #
    # An RM given a menu item that leads nowhere concludes the system is
    # broken, not that a feature is pending.
    _bar = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
    if os.path.isfile(_bar):
        _txt = open(_bar, encoding="utf-8").read()
        _had = _txt.count("Deals Warehouse")
        if _had:
            _kept = [l for l in _txt.split("\\n")
                     if "label: 'Deals Warehouse'" not in l]
            open(_bar, "w", encoding="utf-8", newline="").write("\\n".join(_kept))
            _left = "\\n".join(_kept).count("Deals Warehouse")
            print("\\n  stripped the Deals Warehouse menu entry (%d -> %d)"
                  % (_had, _left))
            if _left:
                print("\\nABORT: the entry survived the strip. The pilot would")
                print("       get a menu item leading to a page that is not")
                print("       there.")
                return 1

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    s = open(BUILDER, encoding="utf-8").read()
    if "THE WAREHOUSE MENU ENTRY DOES NOT TRAVEL" in s:
        print("ABORT: WHS looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the safety-check anchor matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  the build strips the menu entry before staging")

    if "label: 'Deals Warehouse'" not in BLOCK:
        print("ABORT: the strip does not target the menu entry.")
        return 1
    if "return 1" not in BLOCK:
        print("ABORT: a strip that fails must ABORT the build, not warn.")
        return 1
    if "import os" not in s.split("def main")[0]:
        print("ABORT: os is not imported at module level in the builder.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: targets the entry, aborts if it survives")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + BACKUP_SUFFIX)
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nThe next build strips the entry. Your own sidebar keeps it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
