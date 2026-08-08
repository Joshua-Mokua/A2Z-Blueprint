# Daily Log roll-up: Head of Branches → Business Manager → MD

**Status:** design, not built. Written 2026-08-08.
**Source of truth:** `REPORTING_TREE` (= `org_config.hierarchy` overlaid at
`core.py:7200`) via `get_visible_staff_codes`. No second tree, no title
matching, no roster-string grouping.

---

## The rule

**Validation terminates.** It does not repeat at every level.

| Object | Validated by | Above that |
|---|---|---|
| a staff member's daily log | the branch triad (branch) or their line manager (Head Office) | — |
| a **branch** day | **Head of Branches** | nobody validates it again |
| a **department** day | its **Director** (the MD-reporting role that holds it) | nobody validates it again |

Business Manager and MD **observe**. They see every level, including who has
not filed and the reason recorded, but they do not re-validate work that has
already been countersigned. Re-validating the same object at three levels is
ceremony, and it would make "validated" mean nothing in particular.

---

## What the MD sees

```
▾ Branches (consolidated)          16 branches · 169 staff · index 2,418   ✓ 14 of 16 countersigned
    ▸ Fortis        13 staff  10 filed  index 167.9   ✓ Head of Branches
    ▸ Kisii         16 staff  10 filed  index 155.1   ⚠ over-reported
        KE461  Betty Waiguru    12.2  ✓ validated
        KE637  Brenda Rono       6.5  ✓ validated
        KE546  Elizabeth Miano    —   Not filed — no reason recorded
▸ Consumer & Commercial Banking (CCB)   41 staff  ...  ✓ Director CCB
▸ Corporate Banking                     19 staff  ...  awaiting Director
▸ Internal Control                      12 staff  ...  ✓ Director
▸ Finance                                7 staff  ...  not submitted
...
```

Branches collapse to **one row** with a drop to individual branches, and a
further drop to that branch's staff. Departments sit as siblings, each showing
its Director's validation as the department's validation.

The consolidated Branches node is a **roll-up, not an owner** — its index is the
sum of the branch indices, and it carries no action. That resolves the CCB
overlap: `Head of Branches` sits inside CCB's subtree, but branch days stop at
Head of Branches, so CCB's unit day covers only its non-branch staff (Commercial
Banking, SME, Local Corporates, Bancassurance…). Nothing is counted twice.

---

## Units are not invented

The department rows are the roles that report to the Managing Director in
`org_config.hierarchy` — 16 of them today:

    Director Consumer & Commercial Banking (CCB)
    Director, Corporate Banking Kenya & EAC
    Director Operations & Technology
    Director, Credit Risk Management- Kenya & EAC
    Director, Internal Audit
    Director, Internal Control
    Director, Legal Services & Company Secretary
    Director, Treasury & FICC, EAC
    Director Compliance- CESA 1
    Chief Finance Officer
    Ag. Head Human Resources & Senior HR Business Partner
    Country Risk Manager, Kenya & EAC
    Corporate Communications Manager
    Head of Consumer
    Business Manager
    Personal Assistant

A unit's members are `get_visible_staff_codes` for that role's holder — the
same call the deal and referral analytics use. If a reporting line changes in
`org_config`, the Daily Log follows on the next read.

`branch_day.py` generalises from `branch` to `unit`, keyed by branch name OR
MD-reporting role. Store, over-reporting gate, exceptions and notifications all
carry over unchanged.

---

## Non-filers stay visible all the way up

The follow-up list already computes days outstanding in business days and
excludes excused staff. At Business Manager and MD level it is the same list,
unfiltered by branch — every person across the bank who owes a log, with the
reason where one was recorded and "no reason recorded" where none was. That is
the point of the roll-up: the top of the house can see the bottom.

---

## Build order

1. **R1** — `units_validated_by()` on the MD-reporting roles; generalise
   `branch_day` to unit days. Backend.
2. **R2** — the consolidated tree view: Branches node (collapsed) + department
   rows, expanding to branch, then to staff. Read-only above the owner level.
3. **R3** — bank-wide follow-up list for Business Manager and MD.

---

## Open

1. Does the **Business Manager** see exactly the MD's view, or a subset?
2. Can the MD or Business Manager **return** a unit day to its owner, or is
   their role purely observational? Returning is the only action that would
   make sense above the owner, and it is a real escalation path — but it also
   reopens something already countersigned.
