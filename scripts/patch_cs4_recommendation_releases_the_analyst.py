#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A department recommendation releases the analyst's hold on the case.

When a department committee recommends a case, CS2 marks it
committee_recommended - and leaves the analyst's name on it. Her part is
done, but the case shows under HER My cases and in nobody's Pool, so credit
risk cannot see it. D0868 / LMS00035 sat exactly like that.

Now the recommendation clears the assignment. The analyst is kept on the
record as analyst_before_recommendation, so nothing about who did the work
is lost.

    python scripts/patch_cs4_recommendation_releases_the_analyst.py            # dry run
    python scripts/patch_cs4_recommendation_releases_the_analyst.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''                    _lam_for_cttee().update(_app_id, {
                        "status": "committee_recommended",
                        "committee_recommended_by": code,
                        "committee_recommended_at": _dt_now_iso(),
                    })'''

NEW = '''                    # Her part is done. Leaving her name on it kept the case
                    # under her My cases and out of every pool, so credit risk
                    # could not see it - D0868 sat like that.
                    _held = (_lam_for_cttee().get(_app_id) or {}).get("analyst") or {}
                    _lam_for_cttee().update(_app_id, {
                        "status": "committee_recommended",
                        "committee_recommended_by": code,
                        "committee_recommended_at": _dt_now_iso(),
                        "analyst_before_recommendation": _held,
                        "analyst": {},
                    })'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "analyst_before_recommendation" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("CS2's update matched %d times - CS2 must be applied first."
              % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if '"analyst": {}' not in NEW:
        print("The assignment would not be cleared.")
        return 1
    if "analyst_before_recommendation" not in NEW:
        print("Who did the work would be lost.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A department recommendation releases the analyst; the record keeps")
    print("who it was.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cs4")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Cases recommended BEFORE this keep their analyst -")
    print("release_case_to_pool.py clears those.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
