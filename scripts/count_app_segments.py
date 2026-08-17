#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
What client types do the loan applications actually carry? READ ONLY.

A Department Analyst is meant to see only their own segment. The filter derives
an application's segment from its client_type and recognises exactly three
words - consumer, commercial, cib. Anything else returns "" and is DELIBERATELY
NOT HIDDEN, on the reasoning that a legacy case should not vanish.

That reasoning is sound and its consequence is not: if most cases carry
"Individual" or "Business" - the FLEXCUBE words, not the segment words - then
every one of them is unknown, nothing is hidden, and a Consumer analyst sees
the whole book. Which is what the pilot reported: 271 cases instead of hers.

This counts what is actually there, so the mapping is chosen against the data
rather than against a guess.

    python scripts\\count_app_segments.py
"""
import collections
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    try:
        import utils.api_lms_models as M
        from utils.api_lms_scope import _app_segment
    except Exception as exc:
        print("ABORT: cannot load the application store: %s" % exc)
        return 1

    lam = None
    for name in dir(M):
        obj = getattr(M, name)
        if isinstance(obj, type) and "Manager" in name:
            try:
                lam = obj()
                break
            except Exception:
                continue
    apps = list(getattr(lam, "apps", []) or []) if lam else []
    if not apps:
        print("No applications found.")
        return 0

    print("=" * 74)
    print("APPLICATION CLIENT TYPES")
    print("=" * 74)
    print("  applications: %d" % len(apps))

    raw = collections.Counter(
        str(a.get("client_type", "") or "").strip() or "(empty)" for a in apps)
    seg = collections.Counter(_app_segment(a) or "(unknown)" for a in apps)

    print("\n  RAW client_type as stored:")
    for k, n in raw.most_common(15):
        print("     %-28s %5d" % (k[:28], n))

    print("\n  RESOLVED segment (what the filter sees):")
    for k, n in seg.most_common():
        print("     %-28s %5d" % (k, n))

    unknown = seg.get("(unknown)", 0)
    if unknown:
        print("")
        print("  *** %d application(s) resolve to NO SEGMENT, so they are shown" % unknown)
        print("      to EVERY analyst regardless of theirs. That is the 271.")
        print("")
        print("      The words above tell you the mapping to add. If they read")
        print("      Individual / Business, those are FLEXCUBE client types and")
        print("      need translating to the bank's segments - which is a")
        print("      decision about what the bank means, not a guess a script")
        print("      should make.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
