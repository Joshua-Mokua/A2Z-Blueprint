#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Put today's patchers in the release chain. DRY RUN by default.

WHY A SCRIPT AND NOT A ONE-LINER. The one-liner reported "added 6" and changed
nothing: it computed the list BEFORE attempting the replace, and the anchor did
not match, so it wrote the file back identical and announced success. The
release then built with 76 patchers and none of the day's fixes.

This one reads the file, makes the edit, and CHECKS THE RESULT before writing.
If the anchor is missing it says so instead of claiming a success.

ORDER MATTERS. FIX1 is a delta on DOC1, AN1 and ATT1 - replayed before them it
finds nothing to patch and aborts the whole build. They go in the order below,
after the origin/channels work they sit on top of.

    python scripts\\add_to_release_chain.py
    python scripts\\add_to_release_chain.py --apply
"""
import os
import re
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")

# In dependency order. FIX1 last - it patches what the three before it install.
TO_ADD = [
    "patch_doc1_document_roles",
    "patch_hide1_module_visibility",
    "patch_seg1_analyst_segment",
    "patch_an1_analyst_attach_scope",
    "patch_att1_analyst_attach_ui",
    "patch_fix1_submit_and_docs",
]

# Warehouse and Analytics-delta patchers that must NOT travel.
#   wh3  - warehouse, held back entirely
#   pie1 - touches Analytics.tsx, which is on the deployment delta list, and
#          OR6 is already excluded for exactly that reason
TO_EXCLUDE = [
    "patch_wh3_shelf_polish",
    "patch_pie1_origin_donut",
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    src = open(BUILDER, encoding="utf-8").read()
    original = src

    # ── the CHAIN ───────────────────────────────────────────────────────────
    def _append_to_list(text, list_name, names):
        """Append entries just before a list's closing bracket.

        Anchoring on a NAMED ENTRY was the first approach and it failed on the
        first file it met - the entry was not where I assumed. The closing
        bracket of the list itself is the one landmark that is always there.
        """
        m = re.search(r"\n%s\s*=\s*[\[{]" % re.escape(list_name), text)
        if not m:
            return None
        opener = text[m.end() - 1]
        closer = "]" if opener == "[" else "}"
        depth, end = 0, -1
        for i in range(m.end() - 1, len(text)):
            if text[i] in "[{":
                depth += 1
            elif text[i] in "]}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            return None
        # Match the indentation already used inside the list.
        seg = text[m.end():end]
        ind = re.search(r"\n(\s+)\S", seg)
        indent = ind.group(1) if ind else "    "
        block = "".join('%s"%s",\n' % (indent, n) for n in names)
        # Insert before the closing bracket, on its own lines.
        return text[:end].rstrip() + "\n" + block + text[end:]

    add = [p for p in TO_ADD if '"%s"' % p not in src]
    if add:
        out = _append_to_list(src, "CHAIN", add)
        if out is None:
            print("ABORT: could not locate the CHAIN list in %s." % BUILDER)
            return 1
        src = out

    # ── NOT_FOR_RELEASE ─────────────────────────────────────────────────────
    excl = [p for p in TO_EXCLUDE if '"%s"' % p not in src]
    if excl:
        out = _append_to_list(src, "NOT_FOR_RELEASE", excl)
        if out is None:
            print("ABORT: could not locate NOT_FOR_RELEASE in %s." % BUILDER)
            return 1
        src = out

    if src == original:
        print("Nothing to change - everything is already placed.")
        return 0

    # ── VERIFY BEFORE WRITING. This is the step the one-liner skipped. ──────
    missing = [p for p in TO_ADD + TO_EXCLUDE if '"%s"' % p not in src]
    if missing:
        print("ABORT: the edit did not take for: %s" % ", ".join(missing))
        return 1
    try:
        import ast
        ast.parse(src)
    except SyntaxError as exc:
        print("ABORT: the edit broke the file: %s" % exc)
        return 1

    print("=" * 72)
    print("RELEASE CHAIN")
    print("=" * 72)
    if add:
        print("  ADD to CHAIN, in this order:")
        for p in add:
            print("     %s" % p)
    if excl:
        print("  ADD to NOT_FOR_RELEASE:")
        for p in excl:
            print("     %s" % p)
    print("")
    print("  FIX1 goes LAST - it patches what DOC1, AN1 and ATT1 install, and")
    print("  replayed before them it would find nothing and abort the build.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BUILDER + ".pre_chain")
    open(BUILDER, "w", encoding="utf-8", newline="").write(src)
    print("\nAPPLIED %s" % BUILDER)
    print("Now re-run the builder - it should report %d patchers and no"
          % (76 + len(add)))
    print("'exist but are NOT in the release chain' warning.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
