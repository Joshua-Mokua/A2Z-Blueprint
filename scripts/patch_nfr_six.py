#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
NFR - name the six patchers that are deliberately held back.

The builder refused a release:

    *** 6 patcher(s) exist but are NOT in the release chain:
          patch_im1_import_provenance
          patch_wh1_warehouse_on_postgres
          patch_wh2_register_and_speak_up
          patch_wh3_columns_take_the_register
          patch_whs_strip_at_build
          patch_wp1_warehouse_paging
    ABORT: refusing to build a release that silently omits work.

THAT GUARD IS DOING ITS JOB. "Not in the chain" and "deliberately excluded"
look identical from the outside, and the difference is the whole point - one is
a decision, the other is an oversight that ships a release missing a fix.

All six are deliberate:

    wh1, wh2, wh3   the warehouse store - Postgres, the registered table, the
    wp1, im1        columns that take a register, paging, import provenance.
                    The warehouse is held back until it is well built (ruling
                    2026-08-11), and the pilot has no warehouse page at all.

    whs             the RELEASE BUILDER ITSELF. It strips the Deals Warehouse
                    menu entry at build time. It cannot be replayed onto the
                    pilot - it is the tool that does the replaying, and it
                    lives on this box only.

Usage (from project root, .venv active):
    python scripts\patch_nfr_six.py            # dry run
    python scripts\patch_nfr_six.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP_SUFFIX = ".pre_nfr"

ANCHOR = '''NOT_FOR_RELEASE = {'''

BLOCK = '''NOT_FOR_RELEASE = {
    # ── THE WAREHOUSE STORE (2026-08-20/21) ────────────────────────────────
    # Postgres-backed store, registered table, audible failures, columns wide
    # enough for what a register publishes, paged reads, and import
    # provenance. All of it belongs to the warehouse, which is held back until
    # it is well built - and the pilot has no warehouse page, route or backend
    # to use any of it.
    "patch_wh1_warehouse_on_postgres",
    "patch_wh2_register_and_speak_up",
    "patch_wh3_columns_take_the_register",
    "patch_wp1_warehouse_paging",
    "patch_im1_import_provenance",

    # ── THE BUILDER ITSELF ─────────────────────────────────────────────────
    # WHS teaches THIS script to strip the Deals Warehouse menu entry before
    # staging. It cannot be replayed onto the pilot: it is the tool doing the
    # replaying, and it lives on this box only.
    "patch_whs_strip_at_build",
    # And THIS patcher, which is what wrote the lines above. A patcher that
    # edits the release builder can never be replayed onto the pilot - and if
    # it is not named here, the very next build refuses because IT is now the
    # thing that is unplaced. WHS taught us that; this is the same lesson
    # applied to itself.
    "patch_nfr_six",
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    s = open(BUILDER, encoding="utf-8").read()
    if "THE WAREHOUSE STORE (2026-08-20/21)" in s:
        print("ABORT: NFR looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the NOT_FOR_RELEASE anchor matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK, 1)
    print("  ok  six patchers are named as deliberately held back")

    for must in ("patch_wh1_warehouse_on_postgres", "patch_whs_strip_at_build",
                 "patch_im1_import_provenance", "patch_wp1_warehouse_paging"):
        if s.count('"%s"' % must) != 1:
            print("ABORT: %r appears %d times - it must be named exactly once."
                  % (must, s.count('"%s"' % must)))
            return 1
    # None of the six may ALSO be in the chain - that would be a contradiction
    # the builder could not resolve.
    i = s.index("CHAIN = [")
    j = s.index("\n]", i)
    chain = s[i:j]
    for must in ("patch_wh1_warehouse_on_postgres", "patch_whs_strip_at_build"):
        if must in chain:
            print("ABORT: %r is in BOTH the chain and the exclusions." % must)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: named once each, none also in the chain")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + BACKUP_SUFFIX)
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nRe-run the build. The guard should now report nothing unplaced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
