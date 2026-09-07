#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Show the case journey newest first.

A journey with sixteen events makes the reader scroll to the bottom to find
what just happened. The most recent event is the one people open this for.

Numbering follows the display, so "1." is the latest.

    python scripts/patch_tl1_newest_first.py            # dry run
    python scripts/patch_tl1_newest_first.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "components", "Timeline.tsx")

OLD = """  return (
    <ol className="relative border-l border-gray-200 ml-3 space-y-4 py-1">
      {events.map((e, i) => {"""

NEW = """  // Newest first. The event people open this for is the last one, and a long
  // journey buries it. Reversed on a copy so the caller's array is untouched.
  const ordered = [...events].reverse();

  return (
    <ol className="relative border-l border-gray-200 ml-3 space-y-4 py-1">
      {ordered.map((e, i) => {"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "const ordered" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The render block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # The original array must not be mutated - other views read the same list
    # and would silently get it backwards.
    if "[...events].reverse()" not in s:
        print("The reverse would mutate the caller's array.")
        return 1
    if "events.map" in s:
        print("Something still renders the unordered list.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("Braces unbalanced.")
        return 1
    print("Newest first, on a copy.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_tl1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
