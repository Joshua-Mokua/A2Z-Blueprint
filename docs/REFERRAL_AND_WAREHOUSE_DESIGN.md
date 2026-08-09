# Referral bench, referral credit, and the Deals Warehouse

**Status:** design, not built. Written 2026-08-09.
**Ruling captured:** referrals **credit on acceptance only**.

---

## 1. What exists today

`/branch-log/auto-activities` already reads each deal's `referral_chain` and
emits `"Referral made"` into the day's timeline, alongside `"Deal created"` and
stage changes.

**It displays, it does not credit.** Nothing increments `loans_referred`, so the
index does not move and the staff member still types the count by hand, with
nothing reconciling the two. Everything below rests on closing that gap.

---

## 2. The credit model

> Credit on acceptance only.

| Event | Referrer's index | Why |
|---|---|---|
| referral sent | nothing | an unaccepted referral is an intention, not an outcome |
| accepted | **credited** | the receiving officer has taken the work on |
| returned | nothing | it was not fit to pursue |
| still unactioned (>24 working hours) | nothing yet | escalates; credit follows whenever the decision lands |

**Which day does the credit land on?** The **day the referral was sent**, not the
day it was accepted. The work happened that day.

Because referrals escalate rather than expire, that decision may arrive long
after the day has locked — so the credit is **derived at read time**, never
written. See section 3.

**Automatic, not typed.** RULING (2026-08-09): the referral field on the daily
log becomes **uneditable**, because it is auto-derived. Otherwise the same
referral is counted twice — once by hand, once by machine.

Two halves, and neither works alone:

* the Day Planner renders it as a computed chip, not an input
* **the submit endpoint ignores any posted value for an auto field** — read-only
  in the UI alone is not enforcement, since a crafted request would still write

Implemented as an `auto: true` flag in the field schema, alongside `type` and
`weight`, rather than a hardcoded exception for this one key — so the next
auto-derived metric needs no new code.

SEQUENCING MATTERS: the field can only go read-only AFTER the auto-credit works,
or staff simply lose the ability to record referrals at all.

---

## 3. The 24-hour clock — and escalation, not expiry

**RULING (2026-08-09): a referral never expires for the person who referred it.
It escalates upward until a decision is given.**

Acceptance or return is due within **24 working hours** of sending (via
`workcal`, so a referral sent 16:00 Friday is not overdue on Monday morning for
a weekend nobody was rostered for). Missing that deadline does not kill the
referral — it moves it up:

    recipient
      → their validator            (branch triad, or line manager at Head Office)
      → up the solid line          (org_validator.unit_for_role)
      → THE UNIT OWNER — Director  ← escalation STOPS here
      → also visible on the consolidated view (MD / Business Manager)

The Director is terminal because they can compel a decision. Escalating past
them would relocate the silence rather than resolve it: a queue at the top that
nobody owns is not an escalation, it is a dumping ground. The MD and Business
Manager *see* it at that point, but ownership stays with the Director.

The ladder reuses the existing tree — `unit_for_role` and the reporting
hierarchy — so it needs no new structure and follows any change to `org_config`.

### The consequence this creates

No expiry means **a decision can arrive after the referral's day has locked**.
A referral escalating for three days is decided when day 2 is already sealed, so
a credit *written into* that log would be impossible.

**So it is not written.** The referral credit is DERIVED AT READ TIME from the
referral's accepted state, exactly as `carried_forward` already derives variance.
The lock prevents editing; it has no bearing on a figure that is computed rather
than stored. A decision on day 9 simply heals day 2's index the next time anyone
reads it — no unlock, no correcting entry, no retroactive surprise.

This is more robust than crediting on write, and it falls straight out of the
no-expiry ruling: the arithmetic carries no deadline pressure, only the person
does.

---

## 4. The referral bench

Same shape as the validation queues, because a manager should not learn a third
layout:

```
Referrals to me                                   3 awaiting · 1 overdue
┌──────────┬─────────────────┬──────────┬───────────┬────────┬──────────────┐
│ From     │ Client          │ Product  │ Sent      │ Due in │ Decision     │
├──────────┼─────────────────┼──────────┼───────────┼────────┼──────────────┤
│ N. Oywer │ Acme Ltd        │ SME loan │ 09:14     │ 19h    │ Accept │ Return │
│ V. Kibet │ J. Kamau        │ Current  │ Fri 15:02 │ OVERDUE│ Accept │ Return │
└──────────┴─────────────────┴──────────┴───────────┴────────┴──────────────┘

Referrals I sent — not yet actioned                                  2
   Acme Ltd → M. Chege        sent 2h ago      awaiting
   J. Mwangi → Premier desk   sent 3 days ago  EXPIRED — nobody accepted
```

Returning **requires a note**, as everywhere else. The referrer's own list is
the point: today they send a referral and hear nothing.

---

## 5. Referral tag through the pipeline

On acceptance the deal joins the normal pipeline unchanged, carrying
`origin: referral` and the referrer's code. It validates, ages and reports like
any other deal — the tag is for attribution and ranking, never for different
treatment.

---

## 6. Pipeline ranking, two levels

The leaderboard gains a dimension: **referred** vs **direct**.

* a deal's value counts once, for whoever owns it
* the **referrer** is credited separately in a referral ranking — deals referred,
  accepted, converted, and value converted

Keeping them as two rankings rather than one blended number avoids the
double-count trap: a referred deal must not inflate both the owner's and the
referrer's pipeline totals as though the bank booked it twice.

---

## 7. The Deals Warehouse

> "a referral is direct to a person, the warehouse is a prospect"

A shared shelf of prospects anyone can add to and anyone can pick up.

**Object:** client name, contact, location, category, notes, source event,
created_by, created_at, status (`available` / `claimed` / `converted` /
`archived`).

**Shelves** — categorised browsing, driven by config not code, so the bank can
add a category without a deploy. Starting proposal: by product family (SME,
Corporate, Consumer, Bancassurance, Trade), with cross-cutting filters for
location and recency. A prospect sits on exactly one shelf.

**Claiming.** Someone with nothing to pursue browses, picks a prospect, and
claims it. On claim:

* it becomes a normal deal owned by the claimer
* it **roots back to the creator as a referral**, so the creator is credited on
  the same "credit on acceptance" rule — the claim *is* the acceptance
* both parties can track it, exactly like a direct referral

**The question that needs your ruling:** can two people claim the same prospect?
My proposal is no — first claim wins, the prospect leaves the shelf, and the
lister sees who took it. Allowing duplicates would have several officers calling
one customer, which is worse than an idle prospect.

**Staleness.** A prospect nobody claims in N days should surface to its creator,
not rot on the shelf. The daily log's non-filer list is the pattern.

---

## 8. Build order

1. **RF1** — credit on acceptance: referral state machine (`sent` / `accepted` /
   `returned` / `expired`), the 24-hour working-hours clock, and the daily-log
   credit hook. Backend, provable in isolation.
2. **RF2** — the referral bench UI, both directions.
3. **RF3** — `origin: referral` through the pipeline plus the two-level ranking.
4. **DW1** — warehouse object, shelves, browse and claim. Backend.
5. **DW2** — the warehouse UI.

RF1 first because the credit rule decides what every later screen is counting.

---

## Open

1. Warehouse — first claim wins, or multiple pursuers? (proposed: first wins)
2. Warehouse shelves — is product family the right axis, or should it be
   industry, or geography?

Settled 2026-08-09: credit on acceptance only; referrals escalate rather than
expire, stopping at the Director; the daily-log referral field becomes
uneditable; referral clocks run on working hours.
