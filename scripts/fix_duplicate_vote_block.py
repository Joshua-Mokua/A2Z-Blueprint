#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Remove the duplicated vote-recording block that causes the 409.

WHAT WENT WRONG. An early version of VF1 carried the vote-RECORDING lines
inside its block as well as the vote-once check. Applying it left api.py with
the recording twice:

    cast = dict(all_votes.get(code) or {})
    cast[key] = {...}            <-- the original: records this vote
    all_votes[code] = cast
    if key in cast:  raise 409   <-- the check, now looking at a vote that
                                     was recorded four lines above
    cast[key] = {...}            <-- the duplicate
    all_votes[code] = cast

So every FIRST vote is refused. No amount of clearing data helps, because the
refusal is in the code path, not the record: the check is asking whether a vote
exists immediately after putting one there.

THIS REMOVES THE FIRST RECORDING PAIR, leaving the check first and one
recording after it - the order the endpoint was written to have.

It refuses to act unless it finds exactly the broken shape, so it cannot damage
a file that is already correct or has moved on.

    python scripts\\fix_duplicate_vote_block.py
    python scripts\\fix_duplicate_vote_block.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP = API + ".pre_dupfix"

RECORD = "    cast[key] = {"
STORE = "    all_votes[code] = cast"
CHECK = "    if key in cast:"


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1
    s = open(API, encoding="utf-8").read()

    i = s.find("def cast_committee_vote")
    if i < 0:
        print("ABORT: cast_committee_vote is not in this file. Apply VT1 first.")
        return 1
    j = s.find("\n@app.", i)
    if j < 0:
        j = len(s)
    seg = s[i:j]

    n_rec = seg.count(RECORD)
    n_chk = seg.count(CHECK)
    print("  recording blocks : %d" % n_rec)
    print("  vote-once checks : %d" % n_chk)

    if n_rec == 1 and n_chk == 1:
        if seg.index(CHECK) < seg.index(RECORD):
            print("\n  Already correct: one recording, and the check comes first.")
            print("  The 409 has another cause.")
            return 0
        print("\n  One recording, but the check FOLLOWS it. Use")
        print("  fix_vote_once_position.py instead - this repairs duplication.")
        return 1
    if n_rec != 2:
        print("\nABORT: expected two recording blocks, found %d. Not repairing" % n_rec)
        print("       blind - paste this output and we will look together.")
        return 1

    # Remove the FIRST recording pair: from the first `cast[key] = {` through
    # the `all_votes[code] = cast` that follows it.
    first = seg.index(RECORD)
    store_after = seg.find(STORE, first)
    if store_after < 0:
        print("ABORT: no `all_votes[code] = cast` after the first recording.")
        return 1
    end = store_after + len(STORE)
    # Keep everything before, drop the pair, keep the rest.
    new_seg = seg[:first] + seg[end:].lstrip("\n")
    new_seg = new_seg.replace("\n\n\n", "\n\n")

    if new_seg.count(RECORD) != 1 or new_seg.count(STORE) != 1:
        print("ABORT: after removal there are %d recording(s) and %d store(s)."
              % (new_seg.count(RECORD), new_seg.count(STORE)))
        return 1
    if new_seg.index(CHECK) > new_seg.index(RECORD):
        print("ABORT: the check would still follow the recording.")
        return 1

    out = s[:i] + new_seg + s[j:]
    import ast
    try:
        ast.parse(out)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("\n  ok  one recording remains, the check comes first, and it parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, BACKUP)
    open(API, "w", encoding="utf-8", newline="").write(out)
    print("APPLIED %s   (backup: %s)" % (API, os.path.basename(BACKUP)))
    print("\nRestart uvicorn. A first vote is accepted; a second from the same")
    print("person is refused.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
