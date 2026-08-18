#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stop .gitignore hiding the diagnostics. DRY RUN by default.

`.gitignore:158` carries `scripts/diag_*.py`, under a comment explaining the
intent: "Delivered patch kits land here as scripts/apply_*.py + README_*.md.
Ignore the delivery artifacts (the real change is the patched source file,
which you stage explicitly - never the patcher)."

THAT WAS RIGHT WHEN IT WAS WRITTEN. A diagnostic was a throwaway - written to
chase one fault, run twice, forgotten.

It is not right now. Diagnostics have become the main way a fault on the bank's
box gets understood from Nairobi. Today alone, diag_dcc_members.py,
diag_dcc_resolve.py and diag_why_no_vote.py were each written, tested, "sent" -
and simply did not arrive, because git could not see them. Each cost a round
trip and one of them cost an afternoon.

13 of 27 diagnostics on this box are invisible. The ones that ARE tracked got
there by somebody using `git add -f` and remembering. That is not a rule, it is
a habit, and habits fail quietly.

WHAT THIS CHANGES: `scripts/diag_*.py` stops being ignored. Nothing else moves
- apply_*.py, README_*.md, the payload folders and the probes stay ignored,
because those genuinely are delivery artifacts.

A diagnostic that turns out to be throwaway can be deleted. One that is needed
and invisible cannot be sent, and nobody finds out until the person on the
other end says "no such file".

    python scripts\\fix_gitignore_diagnostics.py
    python scripts\\fix_gitignore_diagnostics.py --apply
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime

GI = ".gitignore"
RULE = "scripts/diag_*.py"

NEW = """# Diagnostics are TOOLS, not delivery artifacts, and they must be sendable.
#
# This line used to read `scripts/diag_*.py`, alongside the patch-kit
# artifacts below. That made sense when a diagnostic was throwaway. It stopped
# making sense when diagnostics became the way a fault on the bank's box gets
# understood from here: three were written, tested and "sent" on 2026-08-18 and
# none arrived, because git could not see them.
#
# A diagnostic that turns out to be throwaway can be deleted. One that is
# needed and invisible cannot be sent, and nobody finds out until the person at
# the other end says "no such file".
"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(GI):
        print("ABORT: %s not found - run this from the project root." % GI)
        return 1

    lines = open(GI, encoding="utf-8").read().split("\n")
    hits = [i for i, l in enumerate(lines) if l.strip() == RULE]
    if not hits:
        print("Nothing to do - %r is not in .gitignore." % RULE)
        return 0
    if len(hits) > 1:
        print("ABORT: %r appears %d times. Fix by hand." % (RULE, len(hits)))
        return 1

    i = hits[0]
    print("=" * 74)
    print("THE RULE THAT HIDES THE DIAGNOSTICS")
    print("=" * 74)
    print("  .gitignore:%d   %s" % (i + 1, RULE))

    # Which files does removing it make visible?
    try:
        out = subprocess.run(["git", "ls-tree", "--name-only", "origin/main", "scripts/"],
                             capture_output=True, text=True).stdout.split()
        tracked = {x.split("/")[-1] for x in out}
    except Exception:
        tracked = set()
    on_disk = sorted(f for f in os.listdir("scripts")
                     if f.startswith("diag_") and f.endswith(".py"))
    hidden = [f for f in on_disk if f not in tracked]
    print("\n  diagnostics on this box   %d" % len(on_disk))
    print("  already tracked           %d" % (len(on_disk) - len(hidden)))
    print("  INVISIBLE to git          %d" % len(hidden))
    if hidden:
        print("")
        for f in hidden[:20]:
            print("     %s" % f)
        if len(hidden) > 20:
            print("     ... and %d more" % (len(hidden) - 20))

    lines[i] = NEW.rstrip("\n")
    out_text = "\n".join(lines)

    active_now = [l.strip() for l in out_text.split("\n")
                  if l.strip() and not l.strip().startswith("#")]
    for keep in ("scripts/apply_*.py", "README_*.md", "*.zip"):
        if keep not in active_now:
            print("\nABORT: %r fell out of .gitignore - those genuinely are" % keep)
            print("       delivery artifacts and should stay ignored.")
            return 1
    # The rule name appears inside the replacement COMMENT explaining why it
    # went - so searching the whole file finds it and refuses a correct edit.
    # Check the ACTIVE lines only: a comment is not a rule.
    active = [l.strip() for l in out_text.split("\n")
              if l.strip() and not l.strip().startswith("#")]
    if RULE in active:
        print("\nABORT: the rule is still active.")
        return 1
    print("\n  ok  the rule is replaced; the patch-kit rules are untouched")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = GI + ".pre_diag_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(GI, bak)
    open(GI, "w", encoding="utf-8", newline="").write(out_text)
    print("APPLIED %s   (backup: %s)" % (GI, os.path.basename(bak)))
    print("\n  %d diagnostic(s) are now visible. Add them:" % len(hidden))
    print("     git add .gitignore scripts/diag_*.py")
    print("     git commit -m \"chore: diagnostics are tools, not delivery artifacts\"")
    print("     git push origin main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
