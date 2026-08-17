# The release chain, verified against the pilot's tree

**2026-08-15.** All 34 patchers below were replayed against a clean copy of
`origin/alex-dev` in this exact order. Result: **34 applied, 0 failed**,
`py_compile` clean on seven modules, `tsc --noEmit` clean.

## The order

```
patch_md1_deal_field_mapping          # v2
patch_cq1_committee_queue
patch_cm1_committee_can_view
patch_dq1_committee_queue_source      # v3
patch_qf1_committee_queue_stage
patch_vt1_member_voting
patch_ch1_chair_mandatory
patch_dp1_named_deputy_chairs
patch_fn1_funnel_follows_selection
patch_hd1_cards_follow_selection
patch_mv1_committee_votes_persist
patch_vf1_vote_recorded_and_final
patch_aa1_auto_advance_on_decision
patch_aj1_auto_advance_journey
patch_vs1_vote_syncs_to_db
patch_pg1_all_writes_reach_postgres
patch_sg1_analyst_sees_own_segment
patch_rw1_return_for_rework
patch_rb1_rework_returns_case
patch_rj1_rework_in_journey
patch_rd1_recommend_once_and_submit
   fix_readiness_overwrite            # RUN IMMEDIATELY AFTER RD1
patch_dc1_supported_case_goes_on
patch_dj1_dcc_votes_in_journey
patch_gt1_committee_gate_position
patch_cr1_memo_before_analysis
patch_dm1_decision_moves_case
patch_cd1_conditions_and_tick
   remove_cd1_tick                    # RUN IMMEDIATELY AFTER CD1
patch_ac1_accept_decline
patch_ec1_escalate_to_chief
patch_dr2_committee_per_case
patch_wn1_disbursed_closes_won
patch_ui1_credit_frontend             # frontend, whole files
patch_sf1_pool_segment_filter
patch_ap1_approval_panel              # LAST
```

## Two that are not patchers

`fix_readiness_overwrite` and `remove_cd1_tick` REPAIR rather than add. They
must run at the points marked, not at the end:

**fix_readiness_overwrite** removes a second `_updates = {...}` that discards
the first. Without it, recommending a case records the referral and throws it
away one line later - the fault that had the pilot unable to submit.

**remove_cd1_tick** removes a tick endpoint that duplicates
`credit-admin/conditions/fulfill`. Two ways to tick one condition is worse than
either: the disbursement gate watches one of them.

## THE COMMITTEE FIX IS CONFIG, NOT CODE

Merging this will NOT fix Eldoret. The chair was never on their own committee's
roster, and membership is matched by staff code - so the chair's mandatory vote
could never be cast. That lives in `lms_config.json`, on the bank's box.

After merging, on the pilot box:

```
python scripts\seat_the_chairs.py                 # read it first
python scripts\seat_the_chairs.py --apply
python scripts\audit_readiness.py                 # the gate
python scripts\walkthrough_branch.py --branch Eldoret
```

`audit_readiness.py` answers the only question that matters: could each
committee, as configured, actually finish a case. It reads the real config and
the real logins - no fixtures - and names which of five reasons it could not.

## The config must stop travelling

`data/lms_config.json` is the bank's own committee membership and was NOT in
the builder's block list, so a release could carry our copy over theirs and
unstaff every committee. A release branch with 5 of 21 staffed was found sitting
on two branches.

`patch_cfgblock_release.py` adds it to `DATA_BLOCK`, beside `users.json` and the
staff register. **Apply this before building.**

## The gate before pushing

```
python scripts\audit_readiness.py      # can the people act
python scripts\preflight_credit.py     # does the credit path behave
python scripts\walk_all_flows.py       # every product, initiation to close
python scripts\audit_200.py            # the wide sweep
python scripts\rehearse_pilot.py --per-staff 3
```

Nothing pushes with a failure in any of them.

## Scripts the pilot needs, which the chain does not carry

The builder stages only files the replay touched, so these must be copied onto
the release branch by hand before pushing:

```
git checkout main -- scripts/seat_the_chairs.py scripts/seed_committee_members.py ^
    scripts/name_dcc_members.py scripts/find_unstaffed_committees.py ^
    scripts/audit_readiness.py scripts/walkthrough_branch.py ^
    scripts/diag_dcc_members.py scripts/diag_committee_queue.py ^
    scripts/diag_analyst_segment.py scripts/verify_login.py ^
    scripts/preflight_credit.py scripts/audit_200.py scripts/walk_all_flows.py
```

Without them the pilot can merge the code and still not fix its committees.
