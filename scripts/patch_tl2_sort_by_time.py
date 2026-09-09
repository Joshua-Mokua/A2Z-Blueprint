#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Order the case journey by time, not by however it was stored.

TL1 reverses the list. That gives newest-first only if the list was already in
order - and it is not: committee votes, stage changes and case events are
appended by different code paths, so an event recorded late with an earlier
timestamp lands in the wrong place and stays there when reversed.

An analyst reading a case has to reconstruct the order in their head. On a
credit file that is not a presentation problem.

Sorted by the timestamp, newest first. Events with no timestamp keep their
relative order and sit at the bottom, where an undated entry belongs.

    python scripts/patch_tl2_sort_by_time.py            # dry run
    python scripts/patch_tl2_sort_by_time.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "components", "Timeline.tsx")

OLD = """  // Newest first. The event people open this for is the last one, and a long
  // journey buries it. Reversed on a copy so the caller's array is untouched.
  const ordered = [...events].reverse();"""

NEW = """  // Newest first, BY TIME. Reversing assumed the list was already in order,
  // and it is not: committee votes, stage changes and case events are appended
  // by different paths, so one recorded late with an earlier timestamp sat in
  // the wrong place and stayed there when reversed.
  //
  // An analyst should not have to reconstruct the order of a credit file in
  // their head.
  //
  // Undated events keep their relative order and sit at the bottom, which is
  // where an entry with no time belongs. Sorted on a copy, so the caller's
  // array is untouched.
  const ordered = [...events]
    .map((e, i) => ({ e, i, t: Date.parse(String(e.at ?? '')) }))
    .sort((a, b) => {
      const av = Number.isNaN(a.t) ? null : a.t;
      const bv = Number.isNaN(b.t) ? null : b.t;
      if (av === null && bv === null) return a.i - b.i;
      if (av === null) return 1;
      if (bv === null) return -1;
      return bv - av || a.i - b.i;
    })
    .map((x) => x.e);"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "Newest first, BY TIME" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The ordering block matched %d times." % s.count(OLD))
        print("Apply patch_tl1_newest_first.py first - this replaces it.")
        return 1

    s = s.replace(OLD, NEW, 1)

    if "[...events]" not in NEW:
        print("It would sort the caller's array in place.")
        return 1
    if "Number.isNaN" not in NEW:
        print("An unparseable timestamp would sort unpredictably.")
        return 1
    if "a.i - b.i" not in NEW:
        print("Events with the same timestamp would shuffle between renders.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("Braces unbalanced.")
        return 1
    print("The journey is ordered by time, newest first.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_tl2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
