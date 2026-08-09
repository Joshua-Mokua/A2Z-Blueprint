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
| expired unactioned (>24h) | nothing | see the escalation below |

**Which day does the credit land on?** The **day the referral was sent**, not the
day it was accepted. The work happened that day, and the carried-forward engine
recomputes at read time, so a credit arriving a few hours later simply heals the
original day — no correcting entry, no retroactive surprise.

That only holds because the acceptance window is 24 hours: the credit always
lands well inside the three-business-day lock. If the window were ever widened
past the lock, this rule breaks and the credit would have to land on the
acceptance date instead. Worth remembering if the window is ever revisited.

**Automatic, not typed.** Once credit is automatic, `loans_referred` should stop
being a manual field for referrals routed through the system — otherwise the
same referral can be counted twice, by hand and by machine. Manual entry stays
only for referrals made outside the system.

---

## 3. The 24-hour clock

Acceptance or return is due within **24 hours of sending**. Two questions the
implementation has to answer, and my proposals:

* **Working hours or wall clock?** Working hours, via `workcal`. A referral sent
  at 16:00 on Friday should not expire over a weekend the recipient was never
  rostered for — the same reasoning that put the daily log's return window on
  business days.
* **What happens at expiry?** It does not silently vanish. The referral moves to
  an `expired` state, stays on the referrer's unactioned list, and escalates to
  the recipient's validator. Nobody is credited, and the failure is visible to
  the person who can do something about it.

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

1. Referral expiry — working hours or wall clock? (proposed: working hours)
2. Warehouse — first claim wins, or multiple pursuers? (proposed: first wins)
3. Warehouse shelves — is product family the right axis, or should it be
   industry, or geography?
