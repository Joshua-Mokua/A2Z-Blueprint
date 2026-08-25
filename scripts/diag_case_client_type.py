#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
What client_type do the cases actually carry? READ ONLY.

736 of 742 applications resolve to NO segment, and client type is mandatory at
deal creation - so the value is there and the mapping is not recognising it.

_app_segment already documents one deliberate gap:

    "BUSINESS IS DELIBERATELY NOT MAPPED. A business customer may be Commercial
     or CIB depending on size, and guessing would put a corporate case in front
     of a consumer analyst - worse than showing too much."

That is a sound decision. But it means every business case has no segment, and
a segment gate would show them to nobody - or to everybody, depending on how
the caller treats "".

    python scripts\diag_case_client_type.py

Prints every distinct client_type on the cases, how many carry it, and what
each maps to today. That is the list a decision has to be made against.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    from utils.api_lms_scope import _app_segment
    try:
        from utils.api_lms_routes import _lam
        apps = getattr(_lam(), "apps", []) or []
    except Exception as exc:
        print("ABORT: cannot read the applications: %s" % str(exc)[:60])
        return 1

    tally, unmapped = {}, {}
    for a in apps:
        ct = str(a.get("client_type", "") or "").strip()
        seg = _app_segment(a) or ""
        key = ct or "(blank)"
        tally.setdefault(key, {"n": 0, "seg": seg})
        tally[key]["n"] += 1
        if not seg:
            unmapped[key] = unmapped.get(key, 0) + 1

    print("=" * 78)
    print("CLIENT TYPE ON THE CASES, AND WHAT IT MAPS TO")
    print("=" * 78)
    print("  applications  %d\n" % len(apps))
    print("  %-30s %-8s %s" % ("CLIENT TYPE", "CASES", "SEGMENT TODAY"))
    for k, v in sorted(tally.items(), key=lambda x: -x[1]["n"]):
        print("  %-30s %-8d %s" % (k[:30], v["n"], v["seg"] or "*** none"))

    n_un = sum(unmapped.values())
    print("\n  with no segment   %d of %d" % (n_un, len(apps)))

    print("\n" + "=" * 78)
    if not n_un:
        print("EVERY CASE HAS A SEGMENT")
        print("=" * 78)
        return 0
    print("A DECISION IS NEEDED ON THESE")
    print("=" * 78)
    for k, n in sorted(unmapped.items(), key=lambda x: -x[1]):
        print("  %-30s %d case(s)" % (k[:30], n))
    print("\n  'Business' is unmapped ON PURPOSE - a business customer may be")
    print("  Commercial or CIB depending on size, and guessing would put a")
    print("  corporate case in front of a consumer analyst.")
    print("\n  So the question is not how to map it, but what ELSE the case")
    print("  carries that says which: a product, a unit, an amount band, the")
    print("  owner's department. If nothing does, then the deal-creation form")
    print("  is asking for a client type where it needs a SEGMENT - and that")
    print("  is a change to what the RM is asked, not to how it is read.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
