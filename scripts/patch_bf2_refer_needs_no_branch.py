#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BF2 - a referral is not blocked by a branch field that is not on the screen.

FROM THE BANK (2026-09-03), immediately after branch was turned on:

    "Please fix 1 field below - each problem is highlighted in red next to the
     relevant input"

and nothing was red. The officer had filled in everything the referral form
shows and could not send it.

THE BRANCH CHECK RUNS BEFORE THE REFER-MODE RETURN. BF1 put it at the top of
validate(), with the head-office check it replaced:

    if (creatorIsHeadOffice || requiredFields.includes('branch'))
        && !originatingBranch.trim())
      errors.originatingBranch = '...';

    if (referMode) {
      if (!referRecipient) errors.referRecipient = '...';
      return errors;                 <- already carries the branch error
    }

The refer form deliberately shows only the client and the recipient - "they
complete the deal once they accept it" - so there is no branch selector on it.
The error therefore has no input to attach itself to, which is why the banner
counted a field the officer could not see.

THAT IS MY FAULT AND NOT THE BANK'S. BF1 widened a check from head office to
everybody without noticing that the referral path returns early through it.

THE FIX: the branch is required when a DEAL is being raised, and not when a
lead is being handed to a colleague. The recipient completes the deal - branch
included - when they accept it.

Usage (from project root, .venv active):
    python scripts\patch_bf2_refer_needs_no_branch.py            # dry run
    python scripts\patch_bf2_refer_needs_no_branch.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")
BACKUP_SUFFIX = ".pre_bf2"

OLD = '''    if (!clientName.trim()) errors.clientName = 'Client name is required.';
    // BRANCH IS ASKED OF EVERYBODY when the bank has configured it as
    // required. It used to be asked only of head office, on the reasoning
    // that a branch officer's own posting was obvious - but the deal then
    // carried no branch at all and had to be inferred from the register.
    // Where the register was thin, the deal was left unassigned.
    if ((creatorIsHeadOffice || requiredFields.includes('branch'))
        && !originatingBranch.trim())
      errors.originatingBranch = 'Please select the originating branch.';

    // Refer mode: only the client and the recipient are required; everything
    // else is optional (the recipient completes the deal after accepting).
    if (referMode) {
      if (!referRecipient) errors.referRecipient = 'Choose a colleague to refer this to.';
      return errors;
    }'''

NEW = '''    if (!clientName.trim()) errors.clientName = 'Client name is required.';

    // Refer mode: only the client and the recipient are required; everything
    // else is optional (the recipient completes the deal after accepting).
    //
    // THIS RETURNS BEFORE THE BRANCH CHECK, DELIBERATELY. The refer form shows
    // no branch selector - the recipient chooses it when they accept - so a
    // branch error here has no input to attach itself to. The officer saw
    // "fix 1 field below" with nothing marked red, and could not send a
    // referral they had filled in correctly.
    if (referMode) {
      if (!referRecipient) errors.referRecipient = 'Choose a colleague to refer this to.';
      return errors;
    }

    // BRANCH IS ASKED OF EVERYBODY RAISING A DEAL when the bank has configured
    // it as required. It used to be asked only of head office, on the
    // reasoning that a branch officer's own posting was obvious - but the deal
    // then carried no branch at all and had to be inferred from the register.
    // Where the register was thin, the deal was left unassigned.
    if ((creatorIsHeadOffice || requiredFields.includes('branch'))
        && !originatingBranch.trim())
      errors.originatingBranch = 'Please select the originating branch.';'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "THIS RETURNS BEFORE THE BRANCH CHECK, DELIBERATELY" in s:
        print("ABORT: BF2 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the validate block matched %d times." % s.count(OLD))
        print("       BF1 must be applied first - BF2 reorders what it added.")
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a referral no longer needs a branch it cannot show")

    # The branch check must now come AFTER the refer return, or nothing changed.
    i_ref = s.index("if (referMode) {")
    i_br = s.index("errors.originatingBranch")
    if i_br < i_ref:
        print("ABORT: the branch check still runs before the refer return.")
        return 1
    # And it must still exist - this reorders, it does not remove.
    if "requiredFields.includes('branch')" not in s:
        print("ABORT: the branch requirement was removed rather than moved.")
        print("       A deal still needs a branch; only a referral does not.")
        return 1
    if s.count("errors.originatingBranch") != 1:
        print("ABORT: %d branch checks - there should be exactly one."
              % s.count("errors.originatingBranch"))
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("ABORT: braces unbalanced.")
        return 1
    print("  ok  post-checks: still required for a deal, after the return")

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
