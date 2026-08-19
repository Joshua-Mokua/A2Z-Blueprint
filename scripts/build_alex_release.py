#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Build a release branch for alex-dev by REPLAYING PATCHERS, not by pushing main.

WHY NOT JUST PUSH. main and alex-dev have deliberately divergent files - your
own commit 7913483 says so: "LOCAL ONLY: never push these paths to alex-dev,
they would revert his SMTP/referral/AD work". Measured against alex-dev, a
fast-forward from main would:

    utils/api.py                    -326 lines
    utils/core.py                   -169 lines
    AuthProvider.tsx                -133 lines
    Login.tsx                        -22 lines

That is Alex's Active Directory authentication being deleted. It would take
login down on the bank's pilot.

THE PATCHERS ADD BY ANCHOR, so they land on HIS files and leave his auth alone.
Verified on a real alex-dev checkout: 21 daily-log patchers applied, AD
references 16 before and 16 after, zero diff on api.py, core.py, AuthProvider
and Login.

WHAT THIS DOES
  1. refuses unless your working tree is clean
  2. creates release/alex-<date> from origin/alex-dev
  3. copies scripts/ across from main (the patchers live there)
  4. replays the chain IN ORDER, reporting each one
  5. HARD-VERIFIES the delta files against origin/alex-dev and ABORTS if any of
     them moved - the check is the point, not a formality
  6. leaves the branch for you to build, test and push

It never pushes. Nothing reaches the bank without you looking at it first.

    python scripts\\build_alex_release.py            # plan only
    python scripts\\build_alex_release.py --apply
"""
import datetime
import os
import shutil
import subprocess
import sys

# In dependency order. A patcher that legitimately reports "already applied" is
# not a failure - alex-dev may already carry part of this.
CHAIN = [
    "patch_p3_history_grid", "patch_p3a_grid_polish", "patch_p3b_grid_filters",
    "patch_p3c_org_filters", "patch_p3d_roster_complete", "patch_p3e_hotfix",
    "patch_p3f_canonical_scope", "patch_p3g_rows_reset",
    "patch_v1_validation_backend", "patch_v1a_register_loader",
    "patch_v2_validation_tab", "patch_v2a_queue_perf",
    "patch_b1_branch_line", "patch_b2_branch_day",
    "patch_e1_exceptions", "patch_e2_exception_endpoints",
    "patch_b3_tier2_view", "patch_e3_followup", "patch_e4_notifications",
    "patch_r1_units", "patch_r1a_direct_reports",
    "patch_r2_rollup_view", "patch_r3_bankwide_followup",
    "patch_a1_leaderboard", "patch_a2_leaderboard_ui",
    "patch_bd_bounds", "patch_a3_analytics", "patch_g1_domain_store",
    "patch_a4_drilldown",
    "patch_p1_pipeline_validation", "patch_p2_pipeline_ui",
    "patch_rf1_referral_credit",
    "patch_a5_periods", "patch_a6_average_and_segments",
    "patch_a7_bm_and_layout", "patch_fmt_full_figures",
    "patch_a8_drill_header",
    "patch_f1_funnel_model", "patch_f2_funnel_ui",
    "patch_f3_one_probability_model",
    "patch_b1_stage_buckets", "patch_b2_bucket_funnel_ui",
    "patch_b3_funnel_shape_and_cleanup", "patch_b4_flow_classification",
    "patch_ux1_remove_captions", "patch_pa1_pipeline_analytics",
    "patch_ux2_ytd_default", "patch_pl1_pipeline_ranking",
    "patch_rf2a_referral_clock", "patch_pl2_pipeline_drill",
    "patch_rf2b_referral_bench_ui", "patch_rf3_auto_referral_field",
    "patch_p3_branch_pipeline_day",
    "patch_perf1_roster_cache",
    "patch_as1_unit_activities", "patch_as2_unit_weights",
    "patch_as3_admin_unit_config", "patch_as4_unit_admin_ui",
    "patch_ul1_unit_labels", "patch_ex1_exclude_md_office",
    "patch_or1_deal_origin", "patch_or2_origin_wiring",
     
    
     
     
     
     
     
    "patch_doc1_document_roles",
    "patch_hide1_module_visibility",
    "patch_seg1_analyst_segment",
    "patch_an1_analyst_attach_scope",
    "patch_att1_analyst_attach_ui",
    "patch_fix1_submit_and_docs",
    "patch_pb1_daily_log_and_docs",
    "patch_av1_advance_on_validation",
    "patch_jr1_journey_touchpoints",
    "patch_qm1_quorum_and_journey",
    "patch_sp1_credit_spine",
    "patch_rl1_role_from_store",
    "patch_un1_unit_rollup_click",
    "patch_rc1_recommend_and_docs",
    "patch_pf1_validate_and_gates",
    "patch_bl1_business_line",
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
    "patch_mv1_committee_votes_persist_v2",
    "patch_vf1_vote_recorded_and_final",
    "patch_aa1_auto_advance_on_decision",
    "patch_aj1_auto_advance_journey",
    "patch_vs1_vote_syncs_to_db",
    "patch_pg1_all_writes_reach_postgres",
    "patch_sg1_analyst_sees_own_segment",
    "patch_mv2_committee_sees_its_cases",
    "patch_rw1_return_for_rework",
    "patch_rb1_rework_returns_case",
    "patch_rj1_rework_in_journey",
    "patch_rd1_recommend_once_and_submit",
    "fix_readiness_overwrite",
    "patch_dc1_supported_case_goes_on",
    "patch_dj1_dcc_votes_in_journey",
    "patch_gt1_committee_gate_position",
    "patch_cr1_memo_before_analysis",
    "patch_gv1_gate_carries_voting",
    "patch_lk1_branch_keeps_its_case",
    "patch_br2_branch_from_unit_or_owner",
    "patch_lg1_legal_officers",
    "patch_qc1_committee_queue_only_committees",
    "patch_cdoc1_committee_reads_the_case",
    "patch_cv2_voters_see_the_case",
    "patch_tr1_treasury_rate_desk",
    "patch_dm1_decision_moves_case",
    "patch_cd1_conditions_and_tick",
    "remove_cd1_tick",
    "patch_ac1_accept_decline",
    "patch_ec1_escalate_to_chief",
    "patch_dr2_committee_per_case",
    "patch_rq1_required_documents",
    "patch_mc1_management_credit_committee",
    "patch_bc1_business_credit_committee",
    "patch_mp1_business_committee_panel",
    "patch_vp1_vote_is_personal",
    "patch_bv1_committee_vote_integrity",
    "patch_cv1_credit_voice",
    "patch_cl1_condition_library",
    "patch_wn1_disbursed_closes_won",
    "patch_ui2_credit_frontend",
    "patch_rt2_rate_desk_route",
]

# Patchers that deliberately do NOT ship to the pilot. Anything in scripts/ that
# is neither in CHAIN nor here is REPORTED, because a release tool that silently
# drops work is worse than one that fails - the first release missed five
# batches this way and nobody would have noticed until Alex asked where they
# were.
# Already on alex-dev from earlier pushes - verified 2026-08-10 by checking that
# their effects are present on his branch (workcal.business_days_between,
# datetime.parseTs). Re-running them would only abort as "already applied", but
# listing them keeps the guard meaningful instead of crying wolf every build.
NOT_FOR_RELEASE = {
    # THE WAREHOUSE IS HELD BACK (ruling 2026-08-11): "anything on the
    # warehouse is not to be released to Alex until I am certain it is well
    # built."
    "patch_dw1_warehouse",
    "patch_or3_origin_evidence",
    "patch_or4_origin_capture",
    "patch_or5_preserve_channel",
    "patch_ev1_origin_sources",
    "patch_ev2_events_page",
    "patch_ch1_origin_channels",
    "patch_ch2_channels_page",
    "patch_ch3_channel_tabs",
    "patch_ch4_lead_generators",
    "patch_ch5_channels_ui",
    "patch_ch6_owner_picker",
    "patch_ch7_deal_tracker",
    "patch_ch8_origin_roundtrip",
    "patch_mail1_smtp_negotiation",
    "patch_dq1_clean_warehouse",
    "patch_ic1_information_card",
    "patch_ic2_prospect_detail",
    "patch_cm1_completeness",
    "patch_cm2_matrix_ui",
    "patch_pw1_protected_records",
    "patch_cm3_matrix_table",
    "patch_ux1_record_card",
    "patch_wa1_one_card_analytics",
    "patch_rb1_second_register",
    "patch_lib1_library_order",
    "patch_land1_first_landing",
    "patch_pick1_shelf_pickers",
    "patch_dw2_warehouse_ui",
    # Analytics.tsx is on the deployment delta list, so OR6 stays on our side
    # until that ruling changes.
    "patch_or6_analytics_origins",
    # Local-only repair. Alex's branch_log.py already DEFINES
    # field_bounds and check_bounds - verified defs=2 on
    # origin/alex-dev. This would abort on his tree anyway.
    "hotfix_bounds_defs",
    "patch_a8_branch_segment_and_ui",
    "patch_phase2c_dayplanner",
    "patch_phase2cb_layout",
    "patch_phase2cc_compact",
    "patch_phase2cd_ribbon",
    "patch_tz1_dateonly",
    "patch_wc2a_daycontext",
    "patch_wc2b_wiring",
    "patch_wh3_shelf_polish",
    "patch_pie1_origin_donut",
    "patch_ui1_credit_frontend",
    "patch_sf1_pool_segment_filter",
    "patch_ap1_approval_panel",
    "patch_lb2_stage_labels",
    "patch_pv1_pool_access_panel",
    "patch_cr2_credit_risk_review",
    "patch_cr3_credit_risk_page",
    "patch_cn1_condition_library",
    "patch_cfgblock_release",
    "patch_mv1_committee_votes_persist",
    "patch_vu1_voting_panel",
    "patch_vu2_api_client_anchored",
    "patch_hk1_hooks_before_return",
    "patch_rt1_review_route",
    "patch_cv1_voting_bench",
    "patch_fp1_funnel_polish",
    "patch_tb1_analyst_tabs",
    "patch_dr1_department_review",
    "patch_pk1_pool_pick_and_dcc_empty",
    "patch_dv1_analyst_verdict",
    "patch_cf1_confirm_before_recommend",
    "patch_sb1_department_review_nav",
    "patch_br1_a2z_and_committee_tab",
    "patch_lb1_cancellation_labels",
    "patch_dq2_committee_fallback",
}

# Must be IDENTICAL to alex-dev when this finishes.
#
# utils/api.py is DELIBERATELY ABSENT (ruling 2026-08-10). This release adds
# endpoints to it - the funnel, pipeline analytics, the leaderboard and the
# referral bench all live there - so "must not differ at all" was never
# achievable and blocked every run. What actually matters is that ALEX'S
# AUTHENTICATION inside it is untouched, and the AD marker count proves that.
# Confirmed with Josh: nothing else in api.py is his alone; he cloned main.
DELTA = [
    "utils/core.py",
    "frontend/web/src/providers/AuthProvider.tsx",
    "frontend/web/src/pages/Login.tsx",
    "frontend/web/src/pages/ChangePassword.tsx",
    "frontend/web/src/types/auth.ts",
    "frontend/web/src/components/AppShell.tsx",
    # Sidebar.tsx is NO LONGER byte-frozen (2026-08-11). Diffed against
    # alex-dev, the only difference was TWO BRANDING STRINGS - "EKE Sales Pro"
    # and the "EKE Blueprint" fallback. Freezing the whole file to protect two
    # strings meant Alex could never receive a new menu entry, so Origin
    # Channels would have been unreachable on the pilot. His strings are
    # RESTORED after the replay instead - see BRANDING_STRINGS.
    "frontend/web/src/components/TopBar.tsx",
    # Ruling 2026-08-10: PipelineDealDetail must NOT travel. The formatting
    # patcher removes three K/M abbreviations from it; harmless in itself, but
    # the file stays on Alex's side, so it is reverted below rather than staged.
    # PipelineDealDetail TRAVELS from 2026-08-13. It was held back because a
    # formatting patcher removed three K/M abbreviations - neither version has
    # any K/M formatting now, so the reason was stale, and the cost had become
    # the entire committee voting panel, which lives in this file.
]

# Reverted to alex-dev's version after the replay, before staging. A patcher
# may legitimately touch these; the release must not carry them.
# Alex's branding, restored after the replay so a menu change can travel
# without renaming his product back to ours.
BRANDING_STRINGS = [
    ("label: 'A2Z Sales Pro'", "label: 'EKE Sales Pro'"),
    ("branding?.app_name ?? 'A2Z Blueprint'", "branding?.app_name ?? 'EKE Blueprint'"),
]

REVERT_AFTER_REPLAY = [
    # PipelineDealDetail TRAVELS from 2026-08-13. It was held back because a
    # formatting patcher removed three K/M abbreviations - neither version has
    # any K/M formatting now, so the reason was stale, and the cost had become
    # the entire committee voting panel, which lives in this file.
]

# api.py legitimately gains new endpoints, so it cannot be in DELTA above - but
# its AUTH must be untouched. This is the guard that matters.
AUTH_MARKERS = ("ad_enabled", "active_directory", "ldap", "AD_")


def sh(*args, check=True):
    return subprocess.run(args, capture_output=True, text=True, check=check).stdout


def count_auth(path):
    try:
        s = open(path, encoding="utf-8").read()
    except OSError:
        return 0
    return sum(s.count(m) for m in AUTH_MARKERS)


def main():
    apply = "--apply" in sys.argv
    if not os.path.isdir(".git"):
        print("ABORT: run from the project root.")
        return 1

    # Windows locks utils/__pycache__/*.pyc while uvicorn has the module
    # loaded. A patcher then dies mid-write with "Access is denied", leaving
    # api.py HALF-PATCHED - which the safety check correctly reads as a
    # protected file having moved. Cheaper to detect it here than to unpick it.
    stale = []
    for root, _dirs, files in os.walk("."):
        if os.path.basename(root) != "__pycache__":
            continue
        for f in files:
            if f.endswith(".pyc"):
                stale.append(os.path.join(root, f))
    locked = []
    for f in stale[:400]:
        try:
            os.rename(f, f + ".t")
            os.rename(f + ".t", f)
        except OSError:
            locked.append(f)
    if locked:
        print("ABORT: %d compiled files are LOCKED - a Python process is running."
              % len(locked))
        for f in locked[:5]:
            print("   %s" % f)
        print("")
        print("Stop uvicorn (and any Streamlit), then clear the caches:")
        print('   for /d /r . %d in (__pycache__) do @if exist "%d" rd /s /q "%d"')
        print("")
        print("A patcher that dies on a locked file leaves api.py half-written,")
        print("and the release is then indistinguishable from a broken one.")
        return 1

    dirty = sh("git", "status", "--porcelain").strip()
    tracked_dirty = [l for l in dirty.splitlines() if not l.startswith("??")]
    if tracked_dirty:
        print("ABORT: you have uncommitted changes to tracked files.")
        for l in tracked_dirty[:10]:
            print("   %s" % l)
        print("Commit or stash them first - this script switches branches.")
        return 1

    sh("git", "fetch", "origin", check=False)
    try:
        base = sh("git", "rev-parse", "--short", "origin/alex-dev").strip()
    except subprocess.CalledProcessError:
        print("ABORT: origin/alex-dev not found.")
        return 1
    here = sh("git", "rev-parse", "--abbrev-ref", "HEAD").strip()
    ahead = sh("git", "rev-list", "--count", "origin/alex-dev..HEAD").strip()

    branch = "release/alex-%s-%s" % (datetime.date.today().isoformat(), datetime.datetime.now().strftime("%H%M"))
    print("=" * 72)
    print("PLAN")
    print("=" * 72)
    print("  current branch      %s" % here)
    print("  alex-dev is at      %s" % base)
    print("  commits ahead of it %s" % ahead)
    print("  release branch      %s" % branch)
    print("  patchers to replay  %d" % len(CHAIN))
    print("")
    print("  Alex's AD auth is verified after the replay; the script ABORTS and")
    print("  deletes the branch if any authentication file has moved.")

    # Anything present but unlisted would ship nothing and say nothing.
    import glob
    on_disk = {os.path.splitext(os.path.basename(f))[0]
               for f in glob.glob(os.path.join("scripts", "patch_*.py"))}
    unlisted = sorted(on_disk - set(CHAIN) - NOT_FOR_RELEASE)
    if unlisted:
        print("")
        print("  *** %d patcher(s) exist but are NOT in the release chain:" % len(unlisted))
        for u in unlisted:
            print("        %s" % u)
        print("  They will NOT reach the pilot. Add them to CHAIN in the right")
        print("  order, or to NOT_FOR_RELEASE if that is deliberate.")
        if apply:
            print("\nABORT: refusing to build a release that silently omits work.")
            return 1

    missing = [p for p in CHAIN if not os.path.isfile(os.path.join("scripts", p + ".py"))]
    if missing:
        print("\nABORT: %d patchers are missing from scripts/:" % len(missing))
        for m in missing[:10]:
            print("   %s" % m)
        return 1
    print("  all %d patchers present" % len(CHAIN))

    if not apply:
        print("\nDRY RUN - no branch created. Re-run with --apply.")
        return 0

    # Keep a copy of the patchers: switching to alex-dev removes the ones that
    # were only ever committed on main.
    tmp = os.path.join(".git", "_release_scripts")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp)
    shutil.copytree("scripts", tmp)

    print("\ncreating %s from origin/alex-dev ..." % branch)
    sh("git", "checkout", "-q", "-B", branch, "origin/alex-dev")

    for name in os.listdir(tmp):
        src = os.path.join(tmp, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join("scripts", name))

    before_auth = count_auth("utils/api.py")
    print("AD markers in api.py before: %d\n" % before_auth)

    # Snapshot every path git knows about NOW. Anything untracked that already
    # existed before the replay is YOUR working clutter, not part of the
    # release, and must never be staged. The previous run used `git add -A`
    # from this point and swept 578 forensic scripts into a commit bound for
    # the bank.
    pre_untracked = set(sh("git", "ls-files", "--others",
                           "--exclude-standard").split())

    applied, skipped, failed = [], [], []
    for p in CHAIN:
        r = subprocess.run([sys.executable, os.path.join("scripts", p + ".py"), "--apply"],
                           capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0:
            applied.append(p)
            print("  applied  %s" % p)
        elif "looks applied" in out or "already" in out:
            skipped.append(p)
            print("  already  %s" % p)
        else:
            why = out.strip().splitlines()[-1] if out.strip() else "?"
            failed.append((p, why))
            print("  FAILED   %s" % p)
            # A failure part-way through means every later patcher builds on a
            # file that may be half-written. Stop here rather than produce a
            # release nobody can reason about.
            print("\nABORT: stopping at the first failure - continuing would")
            print("       stack patches onto a partly-written file.")
            print("       %s" % why)
            sh("git", "checkout", "-q", here, check=False)
            sh("git", "branch", "-D", branch, check=False)
            return 1

    print("\napplied %d · already present %d · failed %d"
          % (len(applied), len(skipped), len(failed)))
    for p, why in failed[:10]:
        print("   %s -> %s" % (p, why))

    # Restore Alex's branding in the sidebar. Doing this BEFORE the safety
    # check means the file is compared in the state it will actually ship in.
    _sb = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
    if os.path.isfile(_sb):
        _txt = open(_sb, encoding="utf-8").read()
        _n = 0
        for ours, theirs in BRANDING_STRINGS:
            if ours in _txt:
                _txt = _txt.replace(ours, theirs)
                _n += 1
        if _n:
            open(_sb, "w", encoding="utf-8", newline="").write(_txt)
            print("  restored %d branding string(s) in Sidebar.tsx" % _n)

    # Put back anything that must stay on Alex's side, before the check reads it.
    for f in REVERT_AFTER_REPLAY:
        r = subprocess.run(["git", "checkout", "origin/alex-dev", "--", f],
                           capture_output=True, text=True)
        if r.returncode == 0:
            print("  reverted %s (stays on Alex's side)" % f)

    # ── the guard that matters ───────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("SAFETY CHECK")
    print("=" * 72)
    moved = []
    for f in DELTA:
        d = sh("git", "diff", "--name-only", "origin/alex-dev", "--", f).strip()
        if d:
            moved.append(f)
    after_auth = count_auth("utils/api.py")
    print("  AD markers in api.py after: %d (was %d)%s"
          % (after_auth, before_auth,
             "  <- auth intact" if after_auth >= before_auth else "  *** AUTH LOST"))
    print("  utils/api.py                                         gains endpoints "
          "(auth verified above)")
    for f in DELTA:
        print("  %-52s %s" % (f, "MOVED" if f in moved else "untouched"))

    if moved or after_auth < before_auth:
        print("\nABORT: a protected file changed. This release would damage the")
        print("       pilot's authentication. Deleting the branch.")
        sh("git", "checkout", "-q", here, check=False)
        sh("git", "branch", "-D", branch, check=False)
        return 1

    print("\n  SAFE - authentication is intact.")

    # ── stage EXACTLY what the replay produced ───────────────────────────────
    modified = [l for l in sh("git", "diff", "--name-only").split() if l]
    now_untracked = set(sh("git", "ls-files", "--others", "--exclude-standard").split())
    created = sorted(now_untracked - pre_untracked)

    ALLOW_PREFIX = ("utils/", "frontend/web/src/", "scripts/", "data/", "docs/")
    staged, refused = [], []
    for f in sorted(set(modified) | set(created)):
        if f.startswith(ALLOW_PREFIX):
            staged.append(f)
        else:
            refused.append(f)

    # Data files carry OPERATIONAL state. Config the new features need may go;
    # simulated logs and deals must never overwrite the pilot's own records.
    # lms_config.json is THE BANK'S OWN committee membership - who chairs
    # each committee, who sits on it, who may vote. It is tracked on alex-dev
    # and was never blocked, so a release could carry OUR copy over THEIRS and
    # unstaff every committee at once. A release branch with 5 of 21 staffed
    # was sitting on two branches when this was found.
    #
    # It is also why `del data\lms_config.json` was needed before every build:
    # tracked on one branch, ignored on the other, colliding every time.
    #
    # users.json and the register are blocked for the same reason. This is the
    # bank's data, not ours, and no release should write it.
    DATA_BLOCK = ("data/branch_logs.json", "data/pipeline_deals.json",
                  "data/branch_days.json", "data/daily_log_exceptions.json",
                  "data/users.json", "data/staff_register.xlsx",
                  "data/lms_config.json")
    blocked = [f for f in staged if f in DATA_BLOCK or "backup" in f.lower()]
    staged = [f for f in staged if f not in blocked]

    print("\n" + "=" * 72)
    print("STAGING")
    print("=" * 72)
    print("  staging %d files the replay touched" % len(staged))
    for f in staged[:40]:
        print("     %s" % f)
    if len(staged) > 40:
        print("     ... and %d more" % (len(staged) - 40))
    if blocked:
        print("\n  NOT staged - operational data, would overwrite the pilot's own:")
        for f in blocked:
            print("     %s" % f)
    if refused:
        print("\n  NOT staged - outside the release paths (your working clutter):")
        for f in refused[:15]:
            print("     %s" % f)
        if len(refused) > 15:
            print("     ... and %d more" % (len(refused) - 15))

    if not staged:
        print("\nABORT: nothing to stage - the replay produced no changes.")
        sh("git", "checkout", "-q", here, check=False)
        sh("git", "branch", "-D", branch, check=False)
        return 1

    subprocess.run(["git", "add", "--"] + staged, check=True)
    subprocess.run(["git", "commit", "-q", "-m",
                    "release: daily log with tiered validation and roll-ups, "
                    "index and pipeline rankings, analytics, and the pipeline "
                    "journey funnel"], check=True)
    head = sh("git", "rev-parse", "--short", "HEAD").strip()
    n = len(sh("git", "show", "--stat", "--name-only", "--format=", "HEAD").split())
    print("\n  committed %s with %d files" % (head, n))

    print("\nNext, on this branch:")
    print("  pushd frontend\\web && pnpm install && pnpm tsc --noEmit && pnpm build && popd")
    print("  git push origin %s" % branch)
    print("\nThen ask Alex to merge %s into alex-dev - a pull request he can" % branch)
    print("read, rather than a force-push he cannot.")
    print("\nWhen you are done, return with:  git checkout %s" % here)
    return 0


if __name__ == "__main__":
    sys.exit(main())
