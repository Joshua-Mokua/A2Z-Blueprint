# What already exists: credit analysis → credit admin → Trops

**Surveyed 2026-08-15, before writing a line.** Three times this week I started
building something the system already had — `/pick`, the rework flow, the
committee panels. Each cost more than the survey would have. So this is the
survey.

## The verdict up front

**Most of it is built.** The endpoints, the conditions model, the appeal
machinery and the three pages all exist. What is missing is mostly **joins**
between them — the same shape as every fault this week.

---

## What EXISTS and should not be rebuilt

### Endpoints

```
/api/lms/applications/{id}/decision              approve / decline, with
                                                 conditions and a reason
/api/lms/applications/{id}/confirm-to-credit-admin
/api/lms/applications/{id}/sign-offer
/api/lms/applications/{id}/validate-offer
/api/lms/applications/{id}/appeal                the originating side appeals
/api/lms/applications/{id}/appeal-decision       and it is answered
/api/lms/applications/{id}/pick                  self-pick, segment-limited
/api/lms/applications/{id}/committee-readiness   recommend / return for rework
/api/lms/applications/{id}/return-for-rework
/api/lms/applications/{id}/resubmit-after-rework
/api/lms/applications/{id}/request-info          ask for more, without killing
                                                 the case
/api/lms/applications/{id}/provide-info
```

### The conditions model

`api_lms_models.py:338` — a decision already carries `conditions: List[str]`
alongside verdict, date, authority, reason and comments. The decision block is
`{verdict, date, authority, reason, conditions, comments}`.

**So conditions do not need inventing.** What needs deciding is whether
pre-approval and pre-disbursement conditions are two lists or one list with a
kind — see the questions below.

### The pages

| page | what it already has |
|---|---|
| `Lms.tsx` | My cases / Pool, Pick, the review column |
| `LmsApplicationDetail.tsx` | Case Journey, Department Review, Department Credit Committee, the verdict panel, the rework loop |
| `CreditAdmin.tsx` | a list with `conditionProgress`, disbursement state |
| `CreditAdminCaseDetail.tsx` | conditions rendered, a fulfil/tick control, a disburse action with authority and comments |
| `Troops.tsx` | disbursement |

---

## What is MISSING — the joins, not the machinery

1. **A decision does not auto-flow to credit admin.** `decision` sets the
   status but nothing advances the case; `confirm-to-credit-admin` is a
   separate button somebody must find. Same shape as the committee fault: the
   state changes, the case does not move.

2. **"All conditions met" does not flow to Trops.** The tick control exists;
   nothing watches it and releases the case when the last one is ticked.

3. **"Disbursed" does not close the case as Won.** The disburse action exists;
   the pipeline deal is not closed by it.

4. **A decline does not close the case as Lost.** Anywhere in the journey.

5. **The Credit Analysis workbench is not My cases / Pool.** That shape exists
   on `Lms.tsx` for the department analyst and has not been carried to the bank
   analyst's view.

6. **No "push to Chief Credit Risk".** There is an approval-authority concept
   in the config; there is no route that escalates a case to it.

7. **Pre-approval vs pre-disbursement conditions are not distinguished.** One
   flat list today.

---

## Questions to settle before building

**One list or two?** Are pre-approval and pre-disbursement conditions two
separate lists on the decision, or one list where each condition carries a
`kind`? Two lists is simpler to render; one list is easier to extend when a
third kind appears.

**Who is the Chief Credit Risk?** A named person, a role, or an approval
authority tier already in the config? The escalation route needs a target it
can resolve the way committees resolve a chair.

**Does the appeal reopen the same case or create a new one?** The endpoints
exist; the ruling does not.

**On a decline, does the pipeline deal close as Lost immediately, or when the
appeal window passes?** If an appeal can reopen it, closing it at once means
reopening a closed deal.

---

## What to build, in order

Each step is a join, and each is small because the machinery underneath it is
already there.

1. **A decision moves the case.** Approve → credit admin; decline → Closed
   Lost with the reason. One endpoint, the pattern of `AA1`.
2. **Conditions gain a kind** — pre-approval or pre-disbursement.
3. **The last tick releases it.** All pre-approval conditions met → Trops.
4. **Disbursed closes it Won.**
5. **The Credit Analysis workbench** gets My cases / Pool, reusing `Lms.tsx`.
6. **The approval panel** — approve with conditions, return for information,
   or escalate to the Chief.
7. **Escalation to the Chief Credit Risk**, once its target is defined.

## And the gate, before each commit

```
python scripts\audit_readiness.py       # can the people actually act
python scripts\preflight_credit.py      # does the credit path behave
python scripts\walk_all_flows.py        # can every product be walked
python scripts\audit_200.py             # the wide sweep
python scripts\rehearse_pilot.py        # volume, every origin
```

Nothing commits with a failure in any of them. That is the discipline that was
missing when three suites passed and Eldoret still could not vote.
