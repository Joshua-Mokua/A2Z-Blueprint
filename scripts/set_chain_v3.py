#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Set the release chain to the order verified against the pilot's own tree.

VERIFIED 2026-08-18 against a clean copy of origin/alex-dev:

    51 applied, 0 failed (47 verified + QC1, CDOC1, CV2, TR1)
    py_compile clean on seven modules
    tsc --noEmit clean, vite build clean
    every one of fifteen markers present on the built tree
    Alex's auth files byte-identical: AuthProvider, Login, auth.ts, TopBar,
        core.py
    no Deals Warehouse entry in the sidebar

THREE THINGS THE REPLAY FOUND, which is why it is done before every build:

  MD1 v2 AND DQ1 v3 are the versions that apply. The plain ones abort.

  MV1's ANCHOR NO LONGER EXISTS. MD1 v2 lays the field list out differently,
  so the original MV1 aborted - and the release would have carried every
  committee fix EXCEPT the one that makes votes survive a database round trip.
  Use patch_mv1_committee_votes_persist_v2.

  CV1 REQUIRED A SCRIPT THE RELEASE DOES NOT SHIP. name_dcc_members.py is a
  tool we run to configure a committee, not part of the product; on the
  pilot's tree it simply is not there, and CV1 aborted the whole chain over
  it. It now patches the routes and skips the namer when absent.

TWO ENTRIES ARE REPAIRS, not additions, and must sit exactly where they are:

    fix_readiness_overwrite   straight after RD1 - removes a second
                              `_updates = {...}` that discards the first.
                              Without it, recommending a case builds the
                              referral and throws it away one line later.

    remove_cd1_tick           straight after CD1 - removes a tick endpoint
                              that duplicates credit-admin/conditions/fulfill.
                              Two ways to tick one condition is worse than
                              either: the disbursement gate watches one.

UI2 IS LAST AND CARRIES THE WHOLE FRONT END. Nine earlier frontend patches are
folded into it and excluded below. That rule exists because whole-file patches
captured at different moments overwrite each other - I learned it once with
UI1, added eight more on top, and recreated the fault exactly. THERE IS ONE
FRONTEND PATCH.

    python scripts\\set_chain_v3.py
    python scripts\\set_chain_v3.py --apply
"""
import os
import re
import shutil
import sys

BUILDER = os.path.join("scripts", "build_alex_release.py")
BACKUP = BUILDER + ".pre_chain_v3"

ORDER = [
    'patch_md1_deal_field_mapping',
    'patch_cq1_committee_queue',
    'patch_cm1_committee_can_view',
    'patch_dq1_committee_queue_source',
    'patch_qf1_committee_queue_stage',
    'patch_vt1_member_voting',
    'patch_ch1_chair_mandatory',
    'patch_dp1_named_deputy_chairs',
    'patch_fn1_funnel_follows_selection',
    'patch_hd1_cards_follow_selection',
    'patch_mv1_committee_votes_persist_v2',
    'patch_vf1_vote_recorded_and_final',
    'patch_aa1_auto_advance_on_decision',
    'patch_aj1_auto_advance_journey',
    'patch_vs1_vote_syncs_to_db',
    'patch_pg1_all_writes_reach_postgres',
    'patch_sg1_analyst_sees_own_segment',
    'patch_mv2_committee_sees_its_cases',
    'patch_rw1_return_for_rework',
    'patch_rb1_rework_returns_case',
    'patch_rj1_rework_in_journey',
    'patch_rd1_recommend_once_and_submit',
    'fix_readiness_overwrite',
    'patch_dc1_supported_case_goes_on',
    'patch_dj1_dcc_votes_in_journey',
    'patch_gt1_committee_gate_position',
    'patch_cr1_memo_before_analysis',
    'patch_gv1_gate_carries_voting',
    'patch_lk1_branch_keeps_its_case',
    # Both touch api.py and are independent of each other; they sit here
    # because BR2 changes how a branch is FOUND, and everything downstream
    # that routes to a branch committee depends on it.
    'patch_br2_branch_from_unit_or_owner',
    'patch_lg1_legal_officers',
    # QC1 narrows the committee queue; CDOC1 and CV2 let a voter READ what they
    # are voting on - the branch half and the department/business half of one
    # rule. TR1 is the treasury rate desk and mounts two routers that were
    # written and never mounted.
    'patch_qc1_committee_queue_only_committees',
    'patch_cdoc1_committee_reads_the_case',
    'patch_cv2_voters_see_the_case',
    'patch_tr1_treasury_rate_desk',
    'patch_dm1_decision_moves_case',
    'patch_cd1_conditions_and_tick',
    'remove_cd1_tick',
    'patch_ac1_accept_decline',
    'patch_ec1_escalate_to_chief',
    'patch_dr2_committee_per_case',
    'patch_rq1_required_documents',
    'patch_mc1_management_credit_committee',
    'patch_bc1_business_credit_committee',
    # MP1 sits straight after BC1: BC1 makes the business committee decide,
    # MP1 makes its members able to press the button. Apart, the MD can see the
    # case and find nothing to vote with.
    'patch_mp1_business_committee_panel',
    'patch_vp1_vote_is_personal',
    'patch_bv1_committee_vote_integrity',
    'patch_cv1_credit_voice',
    'patch_cl1_condition_library',
    'patch_wn1_disbursed_closes_won',
    'patch_ui2_credit_frontend',
    # AFTER UI2: it routes a page UI2 carries, and it edits the pilot's OWN
    # App.tsx by anchor rather than replacing it - ours imports pages the
    # pilot does not have, including Warehouse.
    'patch_rt2_rate_desk_route',
]

# Folded into UI2, or ours rather than the bank's.
EXCLUDE = [
    'patch_ui1_credit_frontend',
    'patch_sf1_pool_segment_filter',
    'patch_ap1_approval_panel',
    'patch_lb2_stage_labels',
    'patch_pv1_pool_access_panel',
    'patch_cr2_credit_risk_review',
    'patch_cr3_credit_risk_page',
    'patch_cn1_condition_library',
    'patch_cfgblock_release',
    'patch_mv1_committee_votes_persist',
    'patch_vu1_voting_panel',
    'patch_vu2_api_client_anchored',
    'patch_hk1_hooks_before_return',
    'patch_rt1_review_route',
    'patch_cv1_voting_bench',
    'patch_fp1_funnel_polish',
    'patch_tb1_analyst_tabs',
    'patch_dr1_department_review',
    'patch_pk1_pool_pick_and_dcc_empty',
    'patch_dv1_analyst_verdict',
    'patch_cf1_confirm_before_recommend',
    'patch_sb1_department_review_nav',
    'patch_br1_a2z_and_committee_tab',
    'patch_lb1_cancellation_labels',
    'patch_dq2_committee_fallback',
]

REPAIRS = (("fix_readiness_overwrite", "patch_rd1_recommend_once_and_submit"),
           ("remove_cd1_tick", "patch_cd1_conditions_and_tick"))


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(BUILDER):
        print("ABORT: %s not found." % BUILDER)
        return 1

    missing = [p for p in ORDER
               if not os.path.isfile(os.path.join("scripts", p + ".py"))]
    if missing:
        print("ABORT: these are not on disk:")
        for m in missing:
            print("   %s" % m)
        return 1
    print("  ok  all %d patchers are on disk" % len(ORDER))

    s = open(BUILDER, encoding="utf-8").read()
    out = s
    for p in ORDER + EXCLUDE:
        out = re.sub(r'\n\s*"%s",' % re.escape(p), "", out)

    m = re.search(r"\nCHAIN\s*=\s*\[(.*?)\n\]", out, re.S)
    if not m:
        print("ABORT: cannot find CHAIN in the builder.")
        return 1
    # APPEND, DO NOT REPLACE. The first version of this wrote only ORDER into
    # CHAIN and dropped the seventy patchers already there - every leaderboard,
    # funnel, daily-log and validation patch the pilot has been running since
    # the first release. The builder refused, which is what that guard is for.
    #
    # Ours are stripped from wherever they sat above and re-appended in the
    # verified order; everything else keeps its place and its order.
    body = m.group(1).rstrip()
    block = "".join('\n    "%s",' % p for p in ORDER)
    out = out[:m.start(1)] + body + block + out[m.end(1):]

    n = re.search(r"\nNOT_FOR_RELEASE\s*=\s*\{(.*?)\n\}", out, re.S)
    if n:
        nb = n.group(1).rstrip()
        add = [p for p in EXCLUDE if '"%s"' % p not in nb]
        out = (out[:n.start(1)] + nb
               + "".join('\n    "%s",' % p for p in add) + out[n.end(1):])
        print("  ok  %d superseded patcher(s) excluded" % len(add))

    import ast
    try:
        ast.parse(out)
    except SyntaxError as exc:
        print("ABORT: the builder would not parse - line %s: %s"
              % (exc.lineno, exc.msg))
        return 1

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
    # Nothing that was already in the chain may be lost. Dropping a patcher
    # the pilot is running is not a smaller mistake than adding a bad one.
    before = set(re.findall(r'"([^"]+)"', m.group(1)))
    lost = sorted(before - set(got) - set(EXCLUDE))
    if lost:
        print("ABORT: %d patcher(s) would be dropped from the chain:" % len(lost))
        for x in lost[:8]:
            print("   %s" % x)
        return 1
    if len(got) != len(set(got)):
        dupes = sorted({x for x in got if got.count(x) > 1})
        print("ABORT: duplicated: %s" % ", ".join(dupes[:4]))
        return 1
    for repair, after in REPAIRS:
        if repair not in got:
            print("ABORT: %s is missing - the release would carry a known"
                  % repair)
            print("       broken state.")
            return 1
        if got.index(repair) != got.index(after) + 1:
            print("ABORT: %s must run IMMEDIATELY after %s." % (repair, after))
            return 1
    # UI2 CARRIES WHOLE FILES, so anything that EDITS one of them must run
    # after it or be overwritten. RT2 is the exception that proves it: it edits
    # App.tsx, which UI2 deliberately does NOT carry - ours imports pages the
    # pilot does not have, including Warehouse - so RT2 must follow UI2 and
    # patch the pilot's own file by anchor.
    _ui2 = "patch_ui2_credit_frontend"
    _after_ui2_ok = {"patch_rt2_rate_desk_route"}
    if _ui2 not in got:
        print("ABORT: UI2 is not in the chain.")
        return 1
    _tail = got[got.index(_ui2) + 1:]
    _bad = [x for x in _tail if x not in _after_ui2_ok]
    if _bad:
        print("ABORT: these run AFTER UI2 and would be overwritten by it:")
        for x in _bad[:6]:
            print("   %s" % x)
        return 1
    for old, new in (("patch_mv1_committee_votes_persist",
                      "patch_mv1_committee_votes_persist_v2"),):
        if old in got:
            print("ABORT: %s aborts against MD1 v2. Use %s." % (old, new))
            return 1
    print("  ok  %d entries, verified order, repairs placed, UI2 last" % len(got))

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
