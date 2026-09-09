#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Bring main level with what is running at the bank.

Everything from 4-8 September was applied straight onto alex-dev. Main has not
moved since 4 September 15:48, so the next release built from it would replay
old code over eighteen live fixes - silently, because a patcher that writes a
whole function does not know it is undoing something.

This takes the PATCHERS from alex-dev - Alex's corrected versions, not the
originals, since several needed fixing before they would run - and applies them
here in dependency order.

    python scripts/harmonise_main_with_pilot.py            # dry run
    python scripts/harmonise_main_with_pilot.py --apply

Run from main, on a clean tree.
"""
import os
import subprocess
import sys

# In the order they must run. Several depend on the one before.
PATCHERS = [
    "patch_dd1_roster_keeps_the_complete_row",
    "patch_dd2_keep_the_row_that_carries_scope",
    "patch_dup1_prefer_the_complete_row",
    "patch_va1_branch_manager_can_act",
    "patch_bv4_button_matches_the_rule",
    "patch_ch3_chair_must_be_a_member",
    "patch_cad1_head_of_cad_is_credit_admin",
    "patch_ld1_referrals_start_at_initiation",
    "patch_am1_amend_deal_value",
    "patch_pv2_pool_statuses_per_role",
    "patch_dc1_analyst_decides_own_case",
    "patch_rc3_ready_moves_the_deal",
    "allow_claim_after_committee",
    "patch_ag2_fix_the_field_name",
    # frontend - after the backend, and each edits a file UI2 carries
    "patch_dv3_documents_carry_the_token",
    "patch_am2_amend_panel",
    "patch_rw1_rework_returns_to_the_analyst",
    "patch_tl1_newest_first",
    "patch_ct1_customer_type_requirable",
]


def sh(*args):
    """Run a command and decode as UTF-8 whatever Windows thinks the codec is."""
    r = subprocess.run(args, capture_output=True)
    class R:
        returncode = r.returncode
        stdout = (r.stdout or b"").decode("utf-8", "replace")
        stderr = (r.stderr or b"").decode("utf-8", "replace")
    return R


def main():
    apply = "--apply" in sys.argv

    br = sh("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if br != "main":
        print("On %r. Switch to main first." % br)
        return 1
    dirty = [l for l in sh("git", "status", "--short").stdout.splitlines()
             if not l.startswith("??")]
    if dirty:
        print("The tree has uncommitted changes. Commit or revert them first:")
        for l in dirty[:10]:
            print("   ", l)
        return 1

    print("=" * 74)
    print("PATCHERS TO TAKE FROM THE PILOT AND APPLY HERE")
    print("=" * 74)
    missing = []
    for p in PATCHERS:
        here = os.path.isfile(os.path.join("scripts", "%s.py" % p))
        there = sh("git", "cat-file", "-e",
                   "origin/alex-dev:scripts/%s.py" % p).returncode == 0
        state = "on disk" if here else ("from alex-dev" if there else "MISSING")
        if not here and not there:
            missing.append(p)
        print("  %-46s %s" % (p, state))
    if missing:
        print("\nThese exist nowhere: %s" % ", ".join(missing))
        return 1

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nIt will fetch alex-dev, take only the scripts/ paths listed")
        print("above, and run each. Nothing else from that branch is touched.")
        return 0

    print("\nFetching alex-dev...")
    r = sh("git", "fetch", "origin", "alex-dev")
    if r.returncode != 0:
        print("fetch failed: %s" % r.stderr[:200])
        return 1

    need = [p for p in PATCHERS
            if not os.path.isfile(os.path.join("scripts", "%s.py" % p))]
    if need:
        args = ["git", "checkout", "origin/alex-dev", "--"] + \
               ["scripts/%s.py" % p for p in need]
        r = sh(*args)
        if r.returncode != 0:
            print("could not take the patchers: %s" % r.stderr[:200])
            return 1
        print("Took %d patcher(s) from alex-dev." % len(need))

    print("\n" + "=" * 74)
    ok = skipped = failed = 0
    for p in PATCHERS:
        r = sh(sys.executable, os.path.join("scripts", "%s.py" % p), "--apply")
        out = (r.stdout or "") + (r.stderr or "")
        if "Already applied" in out or "looks applied" in out:
            print("  already   %s" % p)
            skipped += 1
        elif "Applied" in out or "APPLIED" in out or "CREATED" in out:
            print("  applied   %s" % p)
            ok += 1
        else:
            print("  FAILED    %s" % p)
            for l in out.strip().splitlines()[-3:]:
                print("               %s" % l[:70])
            failed += 1

    print("\napplied %d, already there %d, failed %d" % (ok, skipped, failed))
    if failed:
        print("\nStop here and look at the failures. Do not commit a partial")
        print("harmonisation - a half-applied main is worse than one that is")
        print("simply behind.")
        return 1

    print("\nNow, in order:")
    print("   pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    print("   git add utils/ frontend/web/src scripts/")
    print("   git commit -m \"chore: bring main level with the pilot\"")
    print("   git push origin main")
    print("\nThen verify: no marker should be missing from main afterwards.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
