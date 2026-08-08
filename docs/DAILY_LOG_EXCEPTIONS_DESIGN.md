# Daily Log: exceptions, follow-up and notifications

**Status:** design, not built. Written 2026-08-08, after B2.
**Driving requirement (your words):** *"otherwise if it outvalidates then they may
not have an opportunity to explain when action is being taken."*

That sentence sets the shape of the whole thing. A missed day currently becomes
a silent deficit, and the first time the staff member hears about it is when
someone acts on the number. The exception record is what gives them a voice
before that happens.

---

## 1. Exception records — the core idea

A manager marks a non-submitter with a reason, inside the three-business-day
window. The reason decides whether the day still carries a target.

| Reason | Target that day | Counts toward branch target | Rationale |
|---|---|---|---|
| On leave | **0** | no | rostered off; a target would be fiction |
| Sick | **0** | no | same |
| Training / off-site | **0** | no | working, just not on branch metrics |
| Public duty / bereavement | **0** | no | same |
| System outage | **0** | no | the bank prevented the work |
| **Refused to submit** | **full** | **yes** | accountability is the point |
| **No explanation given** | **full** | **yes** | absence of a reason is not a reason |
| Other (free text, required) | manager chooses | follows the choice | escape hatch, but never silent |

The split is the whole design: **excusing an absence removes the target;
refusal does not.** If every reason zeroed the target, the exception becomes a
way to erase a deficit, and the log stops measuring anything.

This reuses the WC-2b mechanism exactly — `target_weight()` already returns 0
for rest days, and a legitimate exception is the same thing for one person.
`carried_forward()` then skips the day for that staff member, so no phantom
deficit accrues, and the branch target drops by that person's share.

**Rebalancing the branch target** falls out for free: the branch target is the
sum of its staff's daily targets, so a person on leave simply isn't in the sum.

---

## 2. Manager submits on behalf

Within the window the BM can submit a day *for* someone, flagged
`submitted_on_behalf_by`, with the reason attached. The staff member's own
figures are whatever the manager records (often zero).

This is deliberately **not** silent: the record shows who submitted it and why,
it appears in the staff member's own history with the manager's note, and it is
auditable. The point is that a zero day with "Refused — declined to log after
two reminders" is a very different artefact from a zero day with no comment,
both for the staff member and for whoever later reviews it.

---

## 3. Non-submitter follow-up list

Below the branch list for the Head of Branches: every staff member across all
branches who has not submitted, for the selected day, with

* days outstanding in **business** days (WC-2b), not calendar
* their branch and line manager
* whether an exception is already recorded
* a nudge action

Sorted by days outstanding descending — the oldest neglect first. This is the
accountability surface you asked for, and it is read-mostly: the Head of
Branches chases, the BM records.

---

## 4. Notifications

`utils/notifications.py` already provides `notify_staff(staff_code, subject,
body_html)`, `send_email`, and the digest path in
`send_notification_digests.py`. Daily Log events plug into that rather than
growing a second channel:

| Event | To | When |
|---|---|---|
| Log returned for amendment | the staff member | immediately |
| Branch day returned by tier 2 | the Branch Manager | immediately |
| You have not submitted | the staff member | deadline + 1 business day |
| Your team has N outstanding | the Branch Manager | daily digest |
| Branch day awaiting countersign | Head of Branches | daily digest |

Immediate for anything a person must act on; digest for anything that is a
standing state. Nobody should get an email per row.

---

## 5. Build order

1. **E1** — exception records + reason taxonomy, `target_weight` override per
   staff-day, `carried_forward` honouring it. Backend only; provably changes
   the deficit arithmetic.
2. **E2** — manager submit-on-behalf, with the reason and attribution.
3. **E3** — the non-submitter follow-up list for tier 2.
4. **E4** — notification hooks into the existing `notify_staff` path.

E1 first because everything else depends on what an exception *means*
arithmetically, and that is the part that is hard to change later once managers
have started recording them.

---

## Open question

The taxonomy above is my proposal, not your ruling. The one that matters is
which reasons zero the target — get that wrong in either direction and the
index stops meaning what people think it means.
