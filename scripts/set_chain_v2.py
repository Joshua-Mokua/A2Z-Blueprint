#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Put the credit-to-disbursement patchers into the release chain, in order.

The builder refused to build without this, which is the guard doing its job:
nine patchers existed and were not in CHAIN, so a release would have carried
the committee fixes and none of the credit work.

THE ORDER IS NOT COSMETIC. It was verified against a clean copy of
origin/alex-dev on 2026-08-15: 34 applied, 0 failed, py_compile clean on seven
modules, tsc --noEmit clean. Two entries are REPAIRS and must sit where they
are:

    fix_readiness_overwrite   immediately after RD1 - removes a second
                              `_updates = {...}` that discards the first.
                              Without it, recommending a case builds the
                              referral and throws it away one line later.

    remove_cd1_tick           immediately after CD1 - removes a tick endpoint
                              duplicating credit-admin/conditions/fulfill.
                              Two ways to tick one condition is worse than
                              either: the disbursement gate watches one.

patch_cfgblock_release is EXCLUDED deliberately. It edits the builder on our
side so the bank's committee config stops travelling; it has no business
running against the pilot's tree.

    python scripts\\set_chain_v2.py
    python scripts\\set_chain_v2.py --apply
"""
import os
import re
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP = BUILDER + ".pre_chain_v2"

# Everything after the committee block already in CHAIN, in the verified order.
ORDER = [
    "patch_gt1_committee_gate_position",
    "patch_cr1_memo_before_analysis",
    "patch_dm1_decision_moves_case",
    "patch_cd1_conditions_and_tick",
    "remove_cd1_tick",
    "patch_ac1_accept_decline",
    "patch_ec1_escalate_to_chief",
    "patch_dr2_committee_per_case",
    "patch_wn1_disbursed_closes_won",
    "patch_sf1_pool_segment_filter",
    "patch_ap1_approval_panel",
]

# Ours, not the pilot's.
EXCLUDE = ["patch_cfgblock_release"]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    missing = [p for p in ORDER
               if not os.path.isfile(os.path.join("scripts", p + ".py"))]
    if missing:
        print("ABORT: not on disk: %s" % ", ".join(missing))
        return 1
    print("  ok  all %d patchers are on disk" % len(ORDER))

    s = open(BUILDER, encoding="utf-8").read()
    out = s
    for p in ORDER + EXCLUDE:
        out = re.sub(r'\n\s*"%s",' % re.escape(p), "", out)

    m = re.search(r"\nCHAIN\s*=\s*\[(.*?)\n\]", out, re.S)
    if not m:
        print("ABORT: cannot find CHAIN.")
        return 1
    body = m.group(1).rstrip()
    block = "".join('\n    "%s",' % p for p in ORDER)
    out = out[:m.start(1)] + body + block + out[m.end(1):]

    # fix_readiness_overwrite belongs after RD1, which is ALREADY in the chain
    # from the previous release - so it is inserted in place rather than
    # appended. Appending would put a repair after the thing it repairs by
    # eleven entries, and the release would carry the broken state through
    # every patcher in between.
    if '"fix_readiness_overwrite"' not in out:
        anchor = '"patch_rd1_recommend_once_and_submit",'
        if anchor not in out:
            print("ABORT: RD1 is not in the chain, so its repair has nowhere")
            print("       to go. Apply the previous release chain first.")
            return 1
        out = out.replace(anchor, anchor + '\n    "fix_readiness_overwrite",', 1)
        print("  ok  fix_readiness_overwrite inserted directly after RD1")

    n = re.search(r"\nNOT_FOR_RELEASE\s*=\s*\{(.*?)\n\}", out, re.S)
    if n:
        nb = n.group(1).rstrip()
        add = [p for p in EXCLUDE if '"%s"' % p not in nb]
        out = (out[:n.start(1)] + nb
               + "".join('\n    "%s",' % p for p in add) + out[n.end(1):])
        print("  ok  %d builder-side patcher(s) excluded" % len(add))

    import ast
    try:
        ast.parse(out)
    except SyntaxError as exc:
        print("ABORT: the builder would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1

    m2 = re.search(r"\nCHAIN\s*=\s*\[(.*?)\n\]", out, re.S)
    got = re.findall(r'"([^"]+)"', m2.group(1))
    if got[-len(ORDER):] != ORDER:
        print("ABORT: the chain does not end in the verified order.")
        return 1
    if len(got) != len(set(got)):
        dupes = sorted({x for x in got if got.count(x) > 1})
        print("ABORT: duplicated in CHAIN: %s" % ", ".join(dupes[:5]))
        return 1
    # The two repairs must sit immediately after what they repair.
    for repair, after in (("fix_readiness_overwrite", "patch_rd1_recommend_once_and_submit"),
                          ("remove_cd1_tick", "patch_cd1_conditions_and_tick")):
        if repair not in got:
            print("ABORT: %s is not in the chain. Without it the release" % repair)
            print("       carries a known-broken state.")
            return 1
        if after in got and got.index(repair) != got.index(after) + 1:
            print("ABORT: %s must run IMMEDIATELY after %s." % (repair, after))
            return 1
    print("  ok  %d entries, order verified, repairs in position" % len(got))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(BUILDER, BACKUP)
    open(BUILDER, "w", encoding="utf-8", newline="").write(out)
    print("APPLIED %s   (backup: %s)" % (BUILDER, os.path.basename(BACKUP)))
    print("\nNext:  python scripts\\build_alex_release.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
