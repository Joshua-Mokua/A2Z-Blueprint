#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WHS - the warehouse entry is stripped AT BUILD, not baked out of the source.

FOUND 2026-08-19: "I also note that the warehouse disappeared from my front end,
yet it was supposed to be the case on the bank side and not here."

UI2 carries whole files, and its copy of Sidebar.tsx had the Deals Warehouse
entry removed. That kept the pilot clear of it - and removed a working menu
item from the DEVELOPER'S OWN SCREEN every time UI2 was applied here.

A PATCH THAT IS APPLIED IN TWO PLACES CANNOT MAKE A DECISION THAT IS ONLY RIGHT
IN ONE OF THEM. "Not for the pilot" is a release decision, so it belongs to the
release builder.

UI2 now keeps the entry. This teaches the builder to remove it from the
Sidebar.tsx it stages, on the release branch only, and to say so while it does.
The warehouse PATCHERS were already excluded, so the pilot has no warehouse page
at all - this stops the menu offering a route to a page that is not there.

Usage (from project root, .venv active):
    python scripts\strip_warehouse_at_build.py            # dry run
    python scripts\strip_warehouse_at_build.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP_SUFFIX = ".pre_whs"

ANCHOR = '''    blocked = [f for f in staged if f in DATA_BLOCK or "backup" in f.lower()]
    staged = [f for f in staged if f not in blocked]'''

BLOCK = '''    blocked = [f for f in staged if f in DATA_BLOCK or "backup" in f.lower()]
    staged = [f for f in staged if f not in blocked]

    # ── THE WAREHOUSE MENU ENTRY DOES NOT TRAVEL ────────────────────────────
    # The warehouse patchers are excluded above, so the pilot has no warehouse
    # PAGE. If the sidebar still offered a route to it, the menu would point at
    # nothing.
    #
    # This used to be handled by shipping a sidebar with the entry already
    # removed - which also removed it from the DEVELOPER'S screen every time
    # that patch was applied here. Stripping at build keeps the decision where
    # it belongs: this is a release choice, not a source one.
    _bar = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
    if _bar in staged or _bar.replace(os.sep, "/") in staged:
        try:
            _txt = open(_bar, encoding="utf-8").read()
            _keep = [l for l in _txt.split("\\n") if "Deals Warehouse" not in l]
            if len(_keep) != len(_txt.split("\\n")):
                open(_bar, "w", encoding="utf-8", newline="").write("\\n".join(_keep))
                print("  removed the Deals Warehouse menu entry from the release")
                print("  sidebar (the page itself is not in this release).")
        except Exception as _exc:  # noqa: BLE001
            print("  *** could not strip the warehouse entry: %s" % _exc)
            print("      CHECK THE SIDEBAR BEFORE PUSHING.")'''


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
        print("ABORT: the staging block matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK, 1)
    print("  ok  the builder strips the warehouse entry when staging")

    if "Deals Warehouse" not in BLOCK:
        print("ABORT: nothing would be stripped.")
        return 1
    if "CHECK THE SIDEBAR BEFORE PUSHING" not in BLOCK:
        print("ABORT: a failure here would be silent, and the entry would ship.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the builder would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: strips, and says so if it cannot")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + BACKUP_SUFFIX)
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nYour own sidebar keeps the warehouse. The release will not have it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
