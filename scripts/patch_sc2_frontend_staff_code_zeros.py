#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SC2 - KE0539 and KE539 are the same person, on the SCREEN as well.

FROM THE BANK (2026-09-03): "the issue of a deal still pointing out that the
owner of the portfolio is not the owner still persists, due to the 0 we
resolved earlier."

SC1 FIXED HALF OF IT. It taught _resolve_owner_name to compare staff codes on
their digits, so CBS returning KE0539 against a register holding KE539 no
longer failed to find the person. That was the backend.

THE SCREEN STILL COMPARES THE STRINGS. PipelineCreate.tsx has three of them:

    po.portfolio_owner_code !== me
    detectedOwner.portfolio_owner_code !== me

"KE0539" !== "KE539" is true, so the form still decides the portfolio belongs
to somebody else, still raises a conflict, and still asks the officer to refer
the deal to themselves.

FIXING A COMPARISON IN ONE LAYER AND NOT THE OTHER is how this came back. The
backend now knows they are the same person and the frontend does not, so the
name resolves and the conflict fires anyway - which reads as a stranger bug
rather than the same one.

    KE0539 vs KE539    the same person
    ke0539 vs KE539    the same person
    KE5390 vs KE539    DIFFERENT - the digits differ, and that distinction
                       must survive

Usage (from project root, .venv active):
    python scripts\patch_sc2_frontend_staff_code_zeros.py            # dry run
    python scripts\patch_sc2_frontend_staff_code_zeros.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")
BACKUP_SUFFIX = ".pre_sc2"

HELPER_ANCHOR = "export function PipelineCreate() {"

HELPER = """/** KE0539 and KE539 are the same person.
 *
 *  The padding was introduced for DSA codes, which need four digits. It was
 *  never meant to turn a three-digit staff code into a different person - but
 *  a string comparison cannot tell a leading zero from a different number.
 *
 *  The backend learned this in SC1. The screen did not, so a portfolio owner
 *  the server had just identified was still reported as somebody else and the
 *  officer was asked to refer a deal to themselves.
 *
 *  KE5390 is NOT KE539: the digits differ, and that distinction survives.
 */
function sameStaff(a: string | undefined, b: string | undefined): boolean {
  const norm = (v: string | undefined) => {
    const m = /^([A-Za-z]*)0*(\\d+)$/.exec((v ?? '').trim());
    return m ? `${m[1].toUpperCase()}${m[2]}` : '';
  };
  const x = norm(a);
  return x !== '' && x === norm(b);
}

"""

REPLACEMENTS = [
    ("if (po.is_mapped && po.portfolio_owner_code && po.portfolio_owner_code !== me) {",
     "if (po.is_mapped && po.portfolio_owner_code\n"
     "            && !sameStaff(po.portfolio_owner_code, me)) {"),
    ("      && detectedOwner.portfolio_owner_code !== me;",
     "      && !sameStaff(detectedOwner.portfolio_owner_code, me);"),
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "function sameStaff(" in s:
        print("ABORT: SC2 looks applied.")
        return 1
    if s.count(HELPER_ANCHOR) != 1:
        print("ABORT: the component anchor matched %d times." % s.count(HELPER_ANCHOR))
        return 1
    for old, _new in REPLACEMENTS:
        if s.count(old) != 1:
            print("ABORT: a comparison matched %d times:" % s.count(old))
            print("       %s" % old[:70])
            return 1

    s = s.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    for old, new in REPLACEMENTS:
        s = s.replace(old, new, 1)
    print("  ok  the screen compares digits, not padding")

    # Every comparison must be gone - one left behind reproduces the fault on
    # whichever path it guards.
    import re
    left = re.findall(r"portfolio_owner_code\s*!==\s*me", s)
    if left:
        print("ABORT: %d raw comparison(s) remain. One left behind brings the"
              % len(left))
        print("       fault back on whichever path it guards.")
        return 1
    if "KE5390" not in HELPER and "digits differ" not in HELPER:
        print("ABORT: the helper must document that a different number is")
        print("       still a different person.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("ABORT: braces unbalanced.")
        return 1
    print("  ok  post-checks: no raw comparison survives, balanced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
