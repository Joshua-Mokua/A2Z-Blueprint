#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BF1 - branch can be made compulsory, and is asked of everybody.

FROM THE BANK (2026-09-01): "we had said that branch is compulsory but I note
it is not, and 90% of the created deals are appearing as unassigned. From the
admin configuration where I was supposed to enforce the compulsory fields,
branch is missing."

TWO SEPARATE FAULTS, and the first explains why the second was never noticed.

ONE - THE ADMIN NEVER OFFERED IT. REQUIRABLE_FIELDS in AdminConfig.tsx lists
client name, product type, deal value, stage, segment, currency, relationship
status, MOU and sector. There is no branch. So the instruction "make branch
compulsory" could not be carried out from the screen built for exactly that.

TWO - THE FORM ONLY ASKS HEAD OFFICE. PipelineCreate.tsx validates the
originating branch with

    if (creatorIsHeadOffice && !originatingBranch.trim()) ...

and sends it only in that case:

    unit: creatorIsHeadOffice && originatingBranch ? originatingBranch : undefined

A branch officer raising a deal is never asked, and the deal carries no branch
at all. BR2 then has to infer one from the register, and where the register is
thin the deal is left unassigned - which is the ninety per cent.

WHAT THIS CHANGES:

    the admin gains a Branch toggle, so requiredness is a config decision
    the form asks EVERYBODY for a branch when it is configured as required
    the branch is sent whoever the creator is, not only head office

BRANCH IS NOT MADE COMPULSORY BY THIS PATCH. It becomes CONFIGURABLE, and the
bank turns it on from Administration. Forcing it here would change what an
officer must type on a live system without anybody deciding to.

Usage (from project root, .venv active):
    python scripts\patch_bf1_branch_is_required.py            # dry run
    python scripts\patch_bf1_branch_is_required.py --apply
"""
import os
import shutil
import sys

ADMIN = os.path.join("frontend", "web", "src", "pages", "AdminConfig.tsx")
CREATE = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")
BACKUP_SUFFIX = ".pre_bf1"

ADMIN_OLD = """  { key: 'sector', label: 'CBK sector (business)' },
];"""
ADMIN_NEW = """  { key: 'sector', label: 'CBK sector (business)' },
  // Added 2026-09-01. The bank asked for branch to be compulsory and found no
  // toggle for it - so the instruction could not be carried out from the screen
  // built to carry it out. Ninety per cent of deals were arriving unassigned.
  { key: 'branch', label: 'Originating branch' },
];"""

CREATE_OLD = ("    if (creatorIsHeadOffice && !originatingBranch.trim()) "
              "errors.originatingBranch = 'Please select the originating branch.';")
CREATE_NEW = (
    "    // BRANCH IS ASKED OF EVERYBODY when the bank has configured it as\n"
    "    // required. It used to be asked only of head office, on the reasoning\n"
    "    // that a branch officer's own posting was obvious - but the deal then\n"
    "    // carried no branch at all and had to be inferred from the register.\n"
    "    // Where the register was thin, the deal was left unassigned.\n"
    "    if ((creatorIsHeadOffice || requiredFields.includes('branch'))\n"
    "        && !originatingBranch.trim())\n"
    "      errors.originatingBranch = 'Please select the originating branch.';")

SEND_OLD = ("      unit:               creatorIsHeadOffice && originatingBranch "
            "? originatingBranch : undefined,")
SEND_NEW = ("      // Sent whoever the creator is. Withholding a branch the\n"
            "      // officer has just chosen, because of who they are, is how\n"
            "      // the deal ended up with none.\n"
            "      unit:               originatingBranch || undefined,")


def main():
    apply = "--apply" in sys.argv
    for f in (ADMIN, CREATE):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    a = open(ADMIN, encoding="utf-8").read()
    c = open(CREATE, encoding="utf-8").read()

    # ── EACH FILE IS ASKED ITS OWN QUESTION ─────────────────────────────────
    # These two files are NOT in the same state on the pilot. UI2 carries
    # AdminConfig.tsx and replays a copy captured before BF1 existed, so the
    # toggle is removed and must be put back. UI2 does NOT carry
    # PipelineCreate.tsx, so once the pilot has merged BF1 the change is
    # already there and its anchor is gone.
    #
    # Asking one question of both meant one answer had to be wrong. The build
    # stopped at "the branch validation matched 0 times".
    admin_done = "'branch', label: 'Originating branch'" in a
    create_done = "requiredFields.includes('branch')" in c
    if admin_done and create_done:
        print("ABORT: BF1 looks applied to both files.")
        return 1

    if not admin_done and a.count(ADMIN_OLD) != 1:
        print("ABORT: the admin field list matched %d times." % a.count(ADMIN_OLD))
        return 1
    if not create_done:
        for nm, anchor in (("the branch validation", CREATE_OLD),
                           ("the payload", SEND_OLD)):
            if c.count(anchor) != 1:
                print("ABORT: %s matched %d times." % (nm, c.count(anchor)))
                return 1

    # The form must be able to see the configured list.
    if "requiredFields" not in c:
        print("ABORT: PipelineCreate has no requiredFields to consult - the")
        print("       form cannot know whether the bank turned branch on.")
        return 1

    if not admin_done:
        a = a.replace(ADMIN_OLD, ADMIN_NEW, 1)
        print("  ok  the admin offers a branch toggle")
    else:
        print("  ok  the admin already offers it - left alone")
    if not create_done:
        c = c.replace(CREATE_OLD, CREATE_NEW, 1).replace(SEND_OLD, SEND_NEW, 1)
        print("  ok  the form asks everybody")
    else:
        print("  ok  the form already asks everybody - left alone")

    if not create_done and "creatorIsHeadOffice && originatingBranch" in c:
        print("ABORT: the payload still withholds the branch from a branch")
        print("       officer, which is the whole fault.")
        return 1
    if "requiredFields.includes('branch')" not in c:
        print("ABORT: the validation does not consult the configured list, so")
        print("       turning the toggle on would change nothing.")
        return 1
    for f, s in ((ADMIN, a), (CREATE, c)):
        if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
            print("ABORT: %s braces unbalanced." % os.path.basename(f))
            return 1
    print("  ok  post-checks: payload always carries it, toggle is consulted")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("\nBranch becomes CONFIGURABLE, not compulsory. Turn it on in")
        print("Administration once this is deployed.")
        return 0

    for path, src in ((ADMIN, a), (CREATE, c)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
