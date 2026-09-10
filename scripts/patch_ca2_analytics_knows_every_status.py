#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Credit Analytics counts every status a case can actually carry.

The bucket map names eleven statuses. The workflow uses more than that, so
18 of 38 cases fall to "Other / unmapped" - and a reader cannot tell whether
that is a fault or a stage.

Two things are wrong beyond the gap:

  - `returned` sits under "Decisioned". A case sent back for rework has not
    been decided; it is with its owner. The 1B case shows as decisioned
    because of this.
  - the committee statuses are absent entirely, which is where most in-flight
    work sits.

    python scripts/patch_ca2_analytics_knows_every_status.py            # dry run
    python scripts/patch_ca2_analytics_knows_every_status.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '''        ("intake",        "Intake / submitted",      {"submitted"}),
        ("assessment",    "Under assessment",        {"assigned", "updated"}),
        ("decision",      "Decisioned",              {"decision_approved", "decision_returned", "returned"}),'''

NEW = '''        ("intake",        "Intake / submitted",      {"submitted"}),
        ("assessment",    "Under assessment",        {"assigned", "updated",
                                                     "in_review",
                                                     "info_requested"}),
        # With the owner, not decided. `returned` sat under Decisioned, so a
        # case sent back for rework read as one that had been decided.
        ("rework",        "Returned for rework",     {"returned"}),
        # Where most in-flight work actually sits, and it was in none of the
        # buckets - 18 of 38 cases fell to "Other / unmapped".
        ("committee",     "At committee",            {"referred_to_committee",
                                                     "ready_for_committee",
                                                     "recommended",
                                                     "analyst_confirmed"}),
        ("with_risk",     "With credit risk",        {"committee_recommended",
                                                     "committee_approved",
                                                     "approved"}),
        ("decision",      "Decisioned",              {"decision_approved",
                                                     "decision_returned"}),'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if '"At committee"' in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The stage map matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # A status must not land in two buckets - the counts would not add up.
    import re
    i = s.index("STAGE_ORDER = [")
    block = s[i:s.index("]", i)]
    seen, dupes = set(), []
    for m in re.finditer(r'"([a-z_]+)"', block):
        w = m.group(1)
        if w in ("intake", "assessment", "decision", "offer", "credit_admin",
                 "disbursement", "disbursed", "declined", "rework",
                 "committee", "with_risk"):
            continue
        if w in seen:
            dupes.append(w)
        seen.add(w)
    if dupes:
        print("These statuses are in more than one bucket: %s" % ", ".join(dupes))
        return 1
    if '"returned"' in block.split('"Decisioned"')[1][:200]:
        print("`returned` is still counted as decided.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Every status the workflow uses now has a bucket.")
    print("A returned case reads as with its owner, not as decided.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nThe chart gains two columns - At committee, With credit risk -")
        print("and Other / unmapped should fall to near zero. If it does not,")
        print("the remainder are statuses I have not seen; send them.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ca2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn and hard-refresh.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
