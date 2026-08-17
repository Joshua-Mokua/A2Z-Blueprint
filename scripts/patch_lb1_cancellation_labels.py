#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
LB1 (v2) - the cancellation buttons name what is being decided.

FROM THE PILOT: "why is approve then close?" - because what is approved is the
CANCELLATION REQUEST, not the deal. The button said only "Approve", sitting
beside a deal, on a screen that now also carries committee work. Approving a
deal and approving its cancellation are opposite acts and one word carried the
whole distinction.

    before   Reject (deal continues)     Approve - close as Lost
    after    Decline cancellation        Approve cancellation - close as Lost
             - deal continues

WHY THERE IS A v2, AND IT IS WORTH RECORDING. The first version shipped the
WHOLE FILE, captured from a tree that did not have the committee queue in it.
Applying it silently REMOVED the Committee tab somebody had just installed -
the same trap as HIDE1 and the sidebar, and the same lesson: a patcher that
carries a whole file carries whatever was missing from it.

This one edits two strings and touches nothing else.

Verified: tsc --noEmit clean, and the committee tab survives.

Usage (from project root, .venv active):
    python scripts\\patch_lb1_cancellation_labels.py            # dry run
    python scripts\\patch_lb1_cancellation_labels.py --apply
"""
import os
import shutil
import sys

MQ = os.path.join("frontend", "web", "src", "pages", "PipelineManagerQueues.tsx")
BACKUP_SUFFIX = ".pre_lb1"

EDITS = [
    ("            Reject (deal continues)",
     "            Decline cancellation \u2014 deal continues"),
    ("            Approve \u2014 close as Lost",
     "            Approve cancellation \u2014 close as Lost"),
]



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MQ):
        print("ABORT: %s not found." % MQ)
        return 1

    src = open(MQ, encoding="utf-8").read()
    if "Approve cancellation" in src:
        print("ABORT: LB1 looks applied.")
        return 1

    # Note what is here BEFORE the edit, so the patcher can prove it did not
    # take anything away - which is exactly what v1 did.
    had_committee_tab = src.count("activeTab === 'committee'")

    for old, new in EDITS:
        if src.count(old) != 1:
            print("ABORT: %r matched %d times." % (old.strip()[:40], src.count(old)))
            return 1
        src = src.replace(old, new, 1)
    print("  ok  both labels name the request, not the deal")

    if src.count("activeTab === 'committee'") != had_committee_tab:
        print("ABORT: the Committee tab count changed from %d to %d - this")
        print("       patcher must not add or remove anything else."
              % (had_committee_tab, src.count("activeTab === 'committee'")))
        return 1
    if had_committee_tab:
        print("  ok  the Committee tab is untouched (%d reference(s))" % had_committee_tab)
    for op, cl in (("{", "}"), ("(", ")")):
        if src.count(op) != src.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MQ, MQ + BACKUP_SUFFIX)
    open(MQ, "w", encoding="utf-8", newline="").write(src)
    print("APPLIED %s" % MQ)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
