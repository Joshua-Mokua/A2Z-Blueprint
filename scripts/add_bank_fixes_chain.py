#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Add the five bank-reported fixes to the release chain. DRY RUN by default.

Reported by the bank on 2026-09-01 and 09-03, all confirmed and each verified
against a copy of the pilot's own branch:

    BF1  branch can be made compulsory, and is asked of everybody
         The admin never offered a branch toggle, and the form asked only head
         office - so a branch officer's deal carried no branch and ninety per
         cent arrived unassigned.

    SC2  KE0539 and KE539 are the same person, on the SCREEN as well
         SC1 fixed the server last week. Three raw string comparisons in
         PipelineCreate kept raising the conflict anyway, so the officer was
         still asked to refer a deal to themselves.

    DV1  a document is served as what it is
         Everything went out as application/octet-stream with
         Content-Disposition: attachment, so nothing previewed and Word files
         errored in a viewer that was never going to render them.

    PI1  a metric with no configured bound is not an unbounded one
         check_bounds skipped any metric it had no cap for, so every activity
         an admin adds accepted any number - and a shilling figure typed into
         one scored millions on the productivity index.

    DV2  a dated, reasoned delegation for validation cover
         Validation authority is derived from the reporting line and had no
         answer for absence. Requested for Osoro Hilda at Kisumu.

ORDER: BF1 and SC2 edit files UI2 carries, so they must run AFTER it or UI2
overwrites them. DV1, PI1 and DV2 touch backend files UI2 does not carry and
can sit anywhere; they go with the others for readability.

    python scripts\add_bank_fixes_chain.py
    python scripts\add_bank_fixes_chain.py --apply
"""
import os
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")

NEW = [
    ("patch_dv1_documents_are_viewable", "utils/api.py"),
    ("patch_pi1_unbounded_metric", "utils/branch_log.py"),
    ("patch_dv2_delegated_validators", "utils/org_validator.py"),
    ("patch_bf1_branch_is_required", "AdminConfig + PipelineCreate (after UI2)"),
    ("patch_sc2_frontend_staff_code_zeros", "PipelineCreate (after UI2)"),
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    s = open(BUILDER, encoding="utf-8").read()

    missing = [p for p, _w in NEW
               if not os.path.isfile(os.path.join("scripts", "%s.py" % p))]
    if missing:
        print("ABORT: not on disk: %s" % ", ".join(missing))
        return 1

    already = [p for p, _w in NEW if '"%s"' % p in s]
    todo = [(p, w) for p, w in NEW if p not in already]

    print("=" * 76)
    print("THE BANK-REPORTED FIXES")
    print("=" * 76)
    for p, what in NEW:
        print("  %-42s %s" % (p, "already in the chain" if p in already else what))
    if not todo:
        print("\n  All five are already in the chain.")
        return 0

    i_ui2 = s.rfind('"patch_ui2_credit_frontend"')
    if i_ui2 < 0:
        print("ABORT: UI2 is not in the chain. BF1 and SC2 edit files it")
        print("       carries and must run after it, or it overwrites them.")
        return 1
    line_end = s.index("\n", i_ui2)
    s = s[:line_end] + "".join('\n    "%s",' % p for p, _w in todo) + s[line_end:]
    print("\n  ok  %d patcher(s) added after UI2" % len(todo))

    for p, _w in todo:
        if s.index('"patch_ui2_credit_frontend"') > s.index('"%s"' % p):
            print("ABORT: %s would run before UI2 and be overwritten." % p)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: every one runs after UI2")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0
    shutil.copy2(BUILDER, BUILDER + ".pre_bankfixes")
    open(BUILDER, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % BUILDER)
    print("\nNext:  python scripts\\preflight_build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
