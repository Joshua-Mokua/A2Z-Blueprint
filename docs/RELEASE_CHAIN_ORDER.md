# The release chain, verified against the pilot's tree

**2026-08-14.** Every patcher below was replayed against a clean copy of
`origin/alex-dev` in this exact order. Result: **24 applied, 0 failed**,
`py_compile` clean, `tsc --noEmit` clean.

This is the check that was missing all week. Three broken releases came from
building first and discovering the failure during the replay; two minutes of
replaying against the target would have caught each one.

## The order

Add these to `CHAIN` in `build_alex_release.py`, in this order, after the
existing entries:

```
patch_md1_deal_field_mapping          # v2 - anchored where the pilot has it
patch_cq1_committee_queue
patch_cm1_committee_can_view
patch_dq1_committee_queue_source      # v3 - the guard that rejected its own fallback
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
patch_dc1_supported_case_goes_on
patch_dj1_dcc_votes_in_journey
patch_ui1_credit_frontend             # LAST - the whole front end, one patch
```

## Why the order matters

**MD1 before MV1.** MV1 adds `committee_votes` to a field list MD1 creates.

**CQ1 before DQ1 before QF1.** Each amends the committee queue the previous
one built.

**VT1 before CH1 before DP1.** The chair rule amends the vote endpoint; the
named-deputy rule amends the chair rule.

**RB1 before RD1.** RD1 anchors on the `_updates` line RB1 introduces. Getting
this backwards produced two assignments, the second discarding the first, and a
recommendation that recorded itself and went nowhere.

**UI1 LAST, and alone.** The frontend patchers each carried a whole file
captured after the previous had been applied, so replaying them in sequence
made the later ones report "already applied" over work that was mostly
missing - seven aborts in the first run. UI1 replaces all of them with one
patch carrying the final state of twelve files.

## Superseded - do NOT add these

```
patch_vu1_voting_panel          folded into UI1
patch_vu2_api_client_anchored   folded into UI1
patch_hk1_hooks_before_return   folded into UI1
patch_rt1_review_route          folded into UI1
patch_cv1_voting_bench          folded into UI1
patch_fp1_funnel_polish         folded into UI1
patch_tb1_analyst_tabs          folded into UI1
patch_dr1_department_review     folded into UI1
patch_pk1_pool_pick_and_dcc_empty  folded into UI1
patch_dv1_analyst_verdict       folded into UI1
patch_cf1_confirm_before_recommend folded into UI1
patch_sb1_department_review_nav folded into UI1
patch_br1_a2z_and_committee_tab folded into UI1
```

Add them to `NOT_FOR_RELEASE` so the builder stops warning that they exist
outside the chain.

## What does NOT travel, and is correct

**The Deals Warehouse menu entry.** UI1's sidebar has it removed, and the
patcher aborts if it would add one - that mistake reached the pilot once before
through a whole-file sidebar patch.

**Origin Channels.** Its 15 patchers remain in `NOT_FOR_RELEASE`. If the bank
should have it, they need their own replay check first: they touch
`PipelineCreate.tsx`, which is where the `fetchOriginSources` failure came from.

## Config the pilot must run after merging

Code alone will not make the committee work. On his box:

```
python scripts\pilot_apply.py --apply --hide-modules
python scripts\name_dcc_members.py --committee B1 --members <names> --deputies <names> --apply
python scripts\enable_dcc.py --apply
python scripts\diag_dcc_members.py
python scripts\preflight_credit.py
```

`preflight_credit.py` is the gate: it drives the real endpoints and reports what
a person would see. Zero failures means the path works on his box, not just
ours.

## One gap, stated plainly

**The owner has no button to send a reworked case back.** RB1 returns the case
to the branch and records why; `resubmit-after-rework` exists and works, but
nothing on the branch side calls it yet. Until that button is built, a returned
case comes back only through the API.

Worth building before the branches use rework in anger.
