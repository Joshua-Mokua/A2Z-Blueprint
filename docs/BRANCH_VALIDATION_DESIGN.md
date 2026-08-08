# Branch validation, totals and submission

**Status:** design, not built. Written 2026-08-08, after V2 shipped.
**Goal:** the validation tab closes the branch's day, not just each person's.

---

## What you asked for, mapped to what exists

| Your requirement | Already built | What's missing |
|---|---|---|
| Every activity added in admin config appears here | **Yes.** Columns come from `fields_schema()`, so Index Setup drives the grid automatically. | nothing |
| A totals line under the staff rows | no | sum the column, per day |
| A branch line ("Fortis Branch") the manager can add items to | **Yes** — `branch_log_reconcile.set_control_totals(branch, day, totals)`, stored in `data/branch_control_totals.json`, exposed at `POST /branch-log/control-totals` | the UI row |
| Nothing flows if reported > actual branch performance | **Yes** — `reconcile_branch_day()` flags only over-reporting; under-reporting is deliberately silent. `GET /branch-log/reconciliation` | wire it as a *gate*, not a report |
| Branch productivity index feeding rankings | partially — the per-staff index exists, `/ranking` exists | a branch-level index and its place in the ranking |
| Save and Submit for the branch | no | a branch-day submission record |
| Follow up non-submitters within three days | **Yes** — `RETURN_WINDOW_DAYS = 3` and `sweep_locks` in `branch_log_state.py`, business-day aware since WC-2b | surfacing it in the tab |

Most of this is wiring, not invention. The one genuinely new concept is the
**branch-day submission** — a record that says "Fortis, 8 August, closed by
Joyce Meeme" with the branch index attached.

---

## The shape

```
Staff    Name              Accounts  Txns  ...  Index  Target  Note        Decision
KE1039   Sharleen Alli          2      30         9.9   12.5   —           ✓ Validated
KE343    Nancy Oywer            1       —         4.0   12.5   —           Validate | Return
CN207    Victor Kibet           ·       ·           —   12.5   Not filed   —
─────────────────────────────────────────────────────────────────────────────────────
STAFF TOTAL                     3      30        13.9   150.0              10 of 12 filed
FORTIS BRANCH (actual)        [ 4 ] [ 34 ]                                 manager enters
VARIANCE                       -1     -4                                   ✓ within actuals
─────────────────────────────────────────────────────────────────────────────────────
BRANCH PRODUCTIVITY INDEX     17.2                          [ Save ]  [ Submit branch day ]
```

Three rows under the staff:

**STAFF TOTAL** — the column sum of what individuals reported. Read-only.

**FORTIS BRANCH (actual)** — editable by the triad. These are the branch's real
numbers for the day, and they are also where the manager records activity that
belongs to the branch rather than to a named person. Persisted through the
existing `set_control_totals`.

**VARIANCE** — actual minus reported, per column. Green when reported ≤ actual.
Red when a column is over-reported, naming it.

---

## The submission gate

> "nothing should flow if what is being submitted is more than the actual
> branch performance"

`reconcile_branch_day()` already computes this. The change is that its result
becomes a **precondition**, not a report:

* **Submit is disabled** while any column is over-reported, and the offending
  columns are named on the button's tooltip and in an inline banner.
* Individual validations still flow immediately as they happen — a manager
  should not be blocked from validating a correct row because a different row
  is wrong.
* Columns with no control total entered are not checked, exactly as the module
  already specifies. Silence is not an anomaly.

That ordering matters: per-row validation is continuous, branch submission is a
single deliberate act at the end of the day.

---

## Branch productivity index

The per-staff index is `Σ(count × weight)`. The branch index has to answer a
different question — is the branch performing, not is the person performing —
and this is the part I do not want to guess at. Three candidates:

1. **Sum of validated staff indices.** Simple, but a big branch always beats a
   small one, so it cannot rank branches against each other.
2. **Mean validated staff index vs the branch's target.** Comparable across
   branches of different sizes; a branch with many non-filers is punished,
   which may be right.
3. **Branch actuals × weights** — score the FORTIS BRANCH row itself rather
   than the staff rows. Measures the branch's real output regardless of who
   reported it, but then individual reporting no longer affects the branch
   score at all.

These rank branches very differently, so it's a business decision.

---

## Follow-up on non-submitters

`RETURN_WINDOW_DAYS = 3` and `sweep_locks` already implement a three-business-day
window (business days since WC-2b). What's missing is visibility: the tab should
show the manager who owes a log and for how long, and offer a nudge. The
`send_notification_digests.py` path exists on the pilot side for email.

---

## Build order

1. **B1** — totals row + branch actuals row + variance, wired to
   `set_control_totals` / `control_totals_for`. Read-only variance display.
2. **B2** — the submit gate: `reconcile_branch_day()` as a precondition, plus a
   branch-day submission record.
3. **B3** — branch productivity index, once its definition is decided, and its
   entry into `/ranking`.
4. **B4** — non-filer follow-up: age in business days, nudge action.

B1 is useful on its own: a manager sees reported-vs-actual immediately, even
before submission is gated.

---

## Before any of this: simulation data

Every row currently reads "Not filed", so none of the above can be seen working.
A seeder should produce a realistic spread across branches and Head Office —
some staff ahead of target, some behind, some with remarks, a few genuinely
absent — plus branch control totals that are mostly consistent and deliberately
over-reported in one or two places, so the gate can be demonstrated firing.
