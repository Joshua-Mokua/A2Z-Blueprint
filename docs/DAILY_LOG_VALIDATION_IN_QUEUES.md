# Daily Log validation → Manager Queues

**Status:** design, not built. Written 2026-08-08.
**Goal:** one place where a line manager validates everything, instead of two.

---

## The change in one line

`Manager Queues` gains a **Daily log validation** tab beside deal validation;
the Daily Log page loses its **Supervisor Review** tab.

```
BEFORE                                  AFTER
/pipeline/queues                        /pipeline/queues
   ├── New deal validation                 ├── New deal validation
   └── Cancellation requests               ├── Daily log validation   ← new
                                           └── Cancellation requests
/branch-log
   ├── Daily Log Entry                  /branch-log
   ├── Log History                         ├── Daily Log Entry
   ├── Supervisor Review   ← removed       ├── Log History
   ├── Ranking                             ├── Ranking
   └── Index Setup                         └── Index Setup
```

A manager's day becomes: open one page, clear both queues.

---

## What already exists (reuse, do not reinvent)

Today's session cost three defects to the habit of writing new logic where old
logic already existed. Every item below is the canonical implementation and the
new tab must call it rather than derive its own.

| Concern | Canonical implementation | Notes |
|---|---|---|
| Who validates a **daily log** | `utils/org_validator.line_manager_of(staff_code)` | Pure reporting-tree line manager, **no** branch→BM override. Its docstring says explicitly: *"Used for daily-log validation, where each person's immediate supervisor validates."* |
| Who validates a **deal** | `utils/org_validator.resolve_validator(owner_code)` | Deliberately different from the above. Do not conflate. |
| Whose rows a user may see | `api_pipeline_scope.get_visible_staff_codes` → `core_audit.get_visible_staff` | Knows all-view roles, register roots, data custodians, HO segment scope, REPORTING_TREE. |
| Pending queue | `GET /api/branch-log/pending` | Runs `run_maintenance` (deadline + lock sweeps) as a side effect. |
| Validate | `POST /api/branch-log/{log_id}/validate` `{approved, note}` | Records validator name/role on the log. |
| Return for amendment | `POST /api/branch-log/{log_id}/return` `{note}` | Business-day window via `_window_elapsed` (WC-2b). |
| Working day / target weight | `utils/workcal` | Sat 0.5, Sun + gazetted holidays 0. |

**No new hierarchy, no new validator rule, no new scope rule.** If something is
missing from the canonical layer, extend it there — not in the queue page.

---

## The view

A **day-scoped table**, one row per staff member the manager validates, for the
selected date. Deliberately the same shape as the History grid so a manager
reads one visual language across both screens.

```
Date: [ Fri 7 Aug ▾ ]   Branch: [ Fortis ▾ ]        3 pending · 12 validated
┌────────┬──────────────┬───────────┬─────┬─────┬─────┬───────┬──────────────┐
│ Staff  │ Name         │ Role      │ Acc │ Txn │ ... │ Index │ Actions      │
├────────┼──────────────┼───────────┼─────┼─────┼─────┼───────┼──────────────┤
│ KE0949 │ M. Gikonyo   │ RO        │  2  │  —  │     │ 173.2 │ ✓ Validate   │
│        │ note: "…"    │           │     │     │     │ /25.0 │ ↩ Return     │
├────────┼──────────────┼───────────┼─────┼─────┼─────┼───────┼──────────────┤
│ KE0852 │ F. Busolo    │ ABSOM     │  1  │ 160 │     │ 185.5 │ ✓ validated  │
├────────┼──────────────┼───────────┼─────┼─────┼─────┼───────┼──────────────┤
│ KE0561 │ S. Abok      │ BOO       │  ·  │  ·  │     │  Not  │ — no entry   │
│        │              │           │     │     │     │ filed │              │
└────────┴──────────────┴───────────┴─────┴─────┴─────┴───────┴──────────────┘
```

Carried over from the History grid: activity columns coloured by family (teal
acquisition, amber money, blue service, pink exceptions), `Not filed` rows in an
amber wash, rest days excluded entirely (a manager is never asked to validate a
Sunday).

Status colour, consistent with the ribbon tabs:

| State | Treatment |
|---|---|
| Pending | white row, actions live |
| Validated | green tick, `#3B6D11`, row settles to a light green wash |
| Returned | amber `#E0A02B`, shows the manager note |
| Auto-submitted | amber `auto` chip — it was swept at the deadline, so the low index is expected |
| Not filed | grey `·` cells, no actions (nothing to validate) |

---

## Interaction

* **Per row:** Validate, or Return with a note.
* **Whole day:** "Validate all pending" acts on the filtered view only, with a
  confirm dialog naming the count. A manager clearing a branch of 12 should not
  click 12 times.
* **Return requires a note.** A returned log with no reason is a dead end for
  the staff member; the note is what they act on.
* **Date picker** defaults to the most recent working day with pending items,
  not to today — on a Monday morning the queue that matters is Friday's.

---

## Open decisions

1. **Validator model.** `line_manager_of` gives each person's immediate
   supervisor. Alex's branch also carries a *branch triad* (Branch Manager /
   Operations Manager / Service Manager all see the branch queue). Which
   applies here, and does it differ between branch and Head Office?
2. **Bulk validate.** Allowed, or must every row be seen individually?
3. **Not-filed rows.** Should they appear in the validation queue at all —
   as visibility of who owes a log — or only in History?

---

## Build order

1. **V1** — backend: a day-scoped queue endpoint returning the same row shape as
   the history grid, scoped by the canonical engine and filtered to logs this
   user is the validator for. Structural post-checks in the patcher.
2. **V2** — frontend: the new Manager Queues tab, reusing the HistoryGrid
   column/colour vocabulary.
3. **V3** — remove `Supervisor Review` from the Daily Log page, plus its
   `TAB_TONE` entry and the now-unused pending fetch.

V3 last, so validation is never unavailable in both places at once.
