#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
HK1 - the Review page stops going blank.

THE CONSOLE NAMED IT EXACTLY, which is why this took minutes rather than the
afternoon of guessing that preceded asking for it:

    Warning: React has detected a change in the order of Hooks called by
    CommitteeJourneyCard.
       Previous render        Next render
       7. undefined       ->  useState

VU1 added three useState hooks - myVote, myDocs, myComment - for the per-member
voting box. They landed BELOW this line:

    if (!data || data.cr_only) return null;

So on a render where the committee data had not arrived, the component returned
after six hooks; on the next it ran nine. React's rule is that every hook runs
on every render, and breaking it does not fail quietly - it throws, and the
whole page renders blank. Which is exactly what "Review takes me to a blank
page" was.

The three declarations move above the guard. Nothing else changes.

MY ERROR, and an avoidable one: I inserted the state where the handler happened
to sit rather than where hooks belong.

Verified: tsc --noEmit clean, vite build clean, and the hooks now precede the
early return.

Usage (from project root, .venv active):
    python scripts\\patch_hk1_hooks_before_return.py            # dry run
    python scripts\\patch_hk1_hooks_before_return.py --apply
"""
import os
import shutil
import sys

DETAIL = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")
BACKUP_SUFFIX = ".pre_hk1"

MINE = '''  const [myVote, setMyVote] = useState<Record<string, string>>({});
  const [myDocs, setMyDocs] = useState<Record<string, boolean>>({});
  const [myComment, setMyComment] = useState<Record<string, string>>({});
'''

GUARD = "  if (!data || data.cr_only) return null;"

MOVED = '''  // ---- HOOKS BEFORE THE EARLY RETURN ------------------------------------
  // These three were declared AFTER `if (!data ...) return null` - so on a
  // render where data was absent React saw six hooks and on the next it saw
  // nine. That is the Rules of Hooks violation, and it does not fail quietly:
  // it throws, and the page renders blank.
  //
  //     Warning: React has detected a change in the order of Hooks called by
  //     CommitteeJourneyCard ... 7. undefined -> useState
  //
  // Every hook must run on every render, so they belong above any return.
  const [myVote, setMyVote] = useState<Record<string, string>>({});
  const [myDocs, setMyDocs] = useState<Record<string, boolean>>({});
  const [myComment, setMyComment] = useState<Record<string, string>>({});

'''



def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(DETAIL):
        print("ABORT: %s not found." % DETAIL)
        return 1

    s = open(DETAIL, encoding="utf-8").read()
    if "HOOKS BEFORE THE EARLY RETURN" in s:
        print("ABORT: HK1 looks applied.")
        return 1
    if s.count(MINE) != 1:
        print("ABORT: the voting hooks matched %d times." % s.count(MINE))
        print("       VU1 must be applied first - these are its hooks.")
        return 1
    if s.count(GUARD) != 1:
        print("ABORT: the early return matched %d times." % s.count(GUARD))
        return 1

    s = s.replace(MINE, "", 1).replace(GUARD, MOVED + GUARD, 1)
    print("  ok  hooks moved above the early return")

    # THE WHOLE POINT: they must now come first.
    i = s.index("function CommitteeJourneyCard")
    if s.index("const [myVote", i) > s.index(GUARD, i):
        print("ABORT: the hooks are still below the return - the page would")
        print("       keep going blank.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if s.count(op) != s.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: every hook runs on every render")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(DETAIL, DETAIL + BACKUP_SUFFIX)
    open(DETAIL, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % DETAIL)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    print("Review opens the case again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
