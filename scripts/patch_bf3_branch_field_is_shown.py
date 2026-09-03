#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BF3 - the branch field is SHOWN to whoever must fill it.

FROM THE BANK (2026-09-03): "when selecting New to Bank the branch option
disappears. Even a new-to-bank customer originates from a branch. We need that
field ASAP."

BF1 MADE THE BRANCH REQUIRED AND NEVER CHECKED IT WAS RENDERED. The selector is
wrapped in

    {creatorIsHeadOffice && (
      <div data-field="originatingBranch"> ... </div>
    )}

so a branch officer has never seen it. That was harmless while only head office
had to supply one. It is not harmless now: BF1 asks EVERYBODY for a branch when
the bank turns the toggle on, and an officer who cannot see the field cannot
fill it. They get "Please fix 1 field below" pointing at nothing - the same
shape of failure as the referral block, from the same mistake.

THIS IS THE SECOND TIME IN ONE DAY. BF1 widened a requirement and I checked the
validation, the payload and the type - and not whether the input exists on the
screen. A required field that is not rendered is worse than no requirement.

WHAT THIS CHANGES: the selector is shown when head office is creating, OR when
the bank has configured branch as required. Nothing else moves - same options,
same handler, same error line.

WHY NOT ALWAYS SHOW IT: because a bank that has not turned the toggle on has
not asked for it, and adding a field to a live create form is a change they did
not request.

Usage (from project root, .venv active):
    python scripts\patch_bf3_branch_field_is_shown.py            # dry run
    python scripts\patch_bf3_branch_field_is_shown.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")

OLD = '''              {creatorIsHeadOffice && (
                <div data-field="originatingBranch">'''

NEW = '''              {/* SHOWN TO WHOEVER MUST FILL IT. This used to be head office
                  only, which was fine while only head office had to supply a
                  branch. BF1 now asks EVERYBODY when the bank configures it as
                  required - and an officer who cannot see the field cannot
                  fill it, so they met "Please fix 1 field below" pointing at
                  nothing. A required field that is not rendered is worse than
                  no requirement at all. */}
              {(creatorIsHeadOffice || requiredFields.includes('branch')) && (
                <div data-field="originatingBranch">'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "SHOWN TO WHOEVER MUST FILL IT" in s:
        print("ABORT: BF3 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the branch block matched %d times." % s.count(OLD))
        return 1
    if "requiredFields" not in s:
        print("ABORT: the form cannot see the configured list.")
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  the branch selector is shown to whoever must fill it")

    # THE FIELD AND THE VALIDATION MUST AGREE. This is the check that would
    # have caught the original mistake: whatever condition makes the branch
    # REQUIRED must also make it VISIBLE.
    # THE FIELD AND THE VALIDATION MUST AGREE. This is the check that would
    # have caught the original mistake: the same words that make the branch
    # REQUIRED must also make it VISIBLE.
    COND = "creatorIsHeadOffice || requiredFields.includes('branch')"
    i_val = s.find("!originatingBranch.trim()")
    i_ren = s.find('<div data-field="originatingBranch"')
    if i_val < 0 or i_ren < 0:
        print("ABORT: could not find both the validation and the field.")
        return 1
    # Look back a short way from each - long enough for the condition, short
    # enough not to swallow the rest of the file.
    if COND not in s[max(0, i_val - 300):i_val]:
        print("ABORT: the validation does not use the expected condition.")
        return 1
    if COND not in s[max(0, i_ren - 700):i_ren]:
        print("ABORT: the field is not shown under the same condition that")
        print("       makes it required. Somebody would be asked for a field")
        print("       they cannot see - which is the whole bug.")
        return 1
    print("  ok  post-checks: required and shown under the SAME condition")

    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("ABORT: braces unbalanced.")
        return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_bf3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
