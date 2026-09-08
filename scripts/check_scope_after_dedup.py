#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Show whose scope fields were lost when duplicate rows were merged.

De-duplicating the register keeps one row per staff code. If the kept row is
missing Department, Unit or Reports To, that person's view collapses - a
head-office analyst sees their whole Department, so losing Department empties
their screen entirely.

    python scripts/check_scope_after_dedup.py

Read only. Run it after any change to how duplicates are resolved.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

SCOPE = ("Department", "Unit", "Branch", "Reports To", "Role")


def main():
    from utils.api_pipeline_scope import get_staff_roster
    df = get_staff_roster()
    have = [c for c in SCOPE if c in df.columns]
    if not have:
        print("The register has none of %s." % ", ".join(SCOPE))
        return 1

    print("=" * 86)
    print("PEOPLE WHOSE SCOPE FIELDS ARE MISSING")
    print("=" * 86)
    print("  rows          %d" % len(df))
    print("  scope fields  %s\n" % ", ".join(have))

    bad = []
    for _i, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if not code:
            continue
        missing = [c for c in have if not str(r.get(c) or "").strip()]
        if missing:
            bad.append((code, str(r.get("Staff Name") or "").strip(),
                        str(r.get("Role") or "").strip(), missing))

    if not bad:
        print("  Every entry carries all of them.")
        return 0

    # The ones that matter most: credit and management roles, whose screens
    # depend on department or cascade scope.
    key = [x for x in bad
           if any(w in x[2].lower() for w in
                  ("analyst", "manager", "head", "officer", "credit", "director"))]

    print("  missing something  %d" % len(bad))
    print("  of those, in a role whose screen depends on it: %d\n" % len(key))

    print("  %-9s %-26s %-30s %s" % ("CODE", "NAME", "ROLE", "MISSING"))
    for code, name, role, missing in (key or bad)[:30]:
        print("  %-9s %-26s %-30s %s"
              % (code, name[:26], role[:30], ", ".join(missing)))
    if len(key or bad) > 30:
        print("     ... and %d more" % (len(key or bad) - 30))

    print("\n" + "=" * 86)
    print("  A head-office analyst sees their whole Department. Without it")
    print("  their screen is empty and nothing explains why.")
    print("")
    print("  Fill these in the register. Where the code had duplicates, check")
    print("  the other row still carries what the kept one lost.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
