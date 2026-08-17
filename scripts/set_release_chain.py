#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Set the release chain to the order verified against the pilot's tree.

The 24 patchers below were replayed against a clean copy of origin/alex-dev on
2026-08-14: 24 applied, 0 failed, py_compile clean, tsc --noEmit clean. This
writes exactly that order into build_alex_release.py, and moves the thirteen
superseded frontend patchers into NOT_FOR_RELEASE so the builder stops warning
that they exist outside the chain.

WHY THE ORDER IS NOT NEGOTIABLE

    MD1 before MV1        MV1 adds a field to a list MD1 creates
    CQ1 -> DQ1 -> QF1     each amends the queue the previous built
    VT1 -> CH1 -> DP1     the chair rule amends the vote endpoint; the named
                          deputy amends the chair rule
    RB1 before RD1        RD1 anchors on the line RB1 introduces. Reversed,
                          two assignments appear and the second discards the
                          first - a recommendation that records itself and
                          goes nowhere
    UI1 LAST, and alone   the frontend patchers each carried a whole file
                          captured after the previous had applied, so replaying
                          them in sequence made later ones report "already
                          applied" over work that was mostly missing

    python scripts\\set_release_chain.py
    python scripts\\set_release_chain.py --apply
"""
import os
import re
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP = BUILDER + ".pre_chain"

ORDER = [
    "patch_md1_deal_field_mapping",
    "patch_cq1_committee_queue",
    "patch_cm1_committee_can_view",
    "patch_dq1_committee_queue_source",
    "patch_qf1_committee_queue_stage",
    "patch_vt1_member_voting",
    "patch_ch1_chair_mandatory",
    "patch_dp1_named_deputy_chairs",
    "patch_fn1_funnel_follows_selection",
    "patch_hd1_cards_follow_selection",
    "patch_mv1_committee_votes_persist",
    "patch_vf1_vote_recorded_and_final",
    "patch_aa1_auto_advance_on_decision",
    "patch_aj1_auto_advance_journey",
    "patch_vs1_vote_syncs_to_db",
    "patch_pg1_all_writes_reach_postgres",
    "patch_sg1_analyst_sees_own_segment",
    "patch_rw1_return_for_rework",
    "patch_rb1_rework_returns_case",
    "patch_rj1_rework_in_journey",
    "patch_rd1_recommend_once_and_submit",
    "patch_dc1_supported_case_goes_on",
    "patch_dj1_dcc_votes_in_journey",
    "patch_ui1_credit_frontend",
]

SUPERSEDED = [
    "patch_vu1_voting_panel", "patch_vu2_api_client_anchored",
    "patch_hk1_hooks_before_return", "patch_rt1_review_route",
    "patch_cv1_voting_bench", "patch_fp1_funnel_polish",
    "patch_tb1_analyst_tabs", "patch_dr1_department_review",
    "patch_pk1_pool_pick_and_dcc_empty", "patch_dv1_analyst_verdict",
    "patch_cf1_confirm_before_recommend", "patch_sb1_department_review_nav",
    "patch_br1_a2z_and_committee_tab", "patch_lb1_cancellation_labels",
    "patch_dq2_committee_fallback",
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1
    s = open(BUILDER, encoding="utf-8").read()

    missing = [p for p in ORDER
               if not os.path.isfile(os.path.join("scripts", p + ".py"))]
    if missing:
        print("ABORT: these patchers are not on disk:")
        for m in missing:
            print("   %s" % m)
        print("\nMove them into scripts\\ before setting the chain.")
        return 1
    print("  ok  all %d patchers are on disk" % len(ORDER))

    # Remove every one of ours from CHAIN, then insert the proven run at the end.
    out = s
    for p in ORDER + SUPERSEDED:
        out = re.sub(r'\n\s*"%s",' % re.escape(p), "", out)

    m = re.search(r"\nCHAIN\s*=\s*\[(.*?)\n\]", out, re.S)
    if not m:
        print("ABORT: cannot find CHAIN in the builder.")
        return 1
    body = m.group(1).rstrip()
    indent = "    "
    block = "".join('\n%s"%s",' % (indent, p) for p in ORDER)
    out = out[:m.start(1)] + body + block + out[m.end(1):]

    # Superseded ones go into NOT_FOR_RELEASE, or the builder warns each run.
    n = re.search(r"\nNOT_FOR_RELEASE\s*=\s*\{(.*?)\n\}", out, re.S)
    if n:
        nbody = n.group(1).rstrip()
        add = [p for p in SUPERSEDED if '"%s"' % p not in nbody]
        nblock = "".join('\n%s"%s",' % (indent, p) for p in add)
        out = out[:n.start(1)] + nbody + nblock + out[n.end(1):]
        print("  ok  %d superseded patcher(s) excluded" % len(add))

    import ast
    try:
        ast.parse(out)
    except SyntaxError as exc:
        print("ABORT: the builder would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1

    # Prove the order survived the edit.
    m2 = re.search(r"\nCHAIN\s*=\s*\[(.*?)\n\]", out, re.S)
    got = re.findall(r'"([^"]+)"', m2.group(1))
    tail = got[-len(ORDER):]
    if tail != ORDER:
        print("ABORT: the chain does not end in the verified order.")
        for a, b in zip(tail, ORDER):
            if a != b:
                print("   expected %s, found %s" % (b, a))
                break
        return 1
    print("  ok  the chain ends in the verified order (%d entries total)" % len(got))
    if len(got) != len(set(got)):
        dupes = [x for x in set(got) if got.count(x) > 1]
        print("ABORT: duplicated in CHAIN: %s" % ", ".join(dupes[:4]))
        return 1
    print("  ok  no duplicates")

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
