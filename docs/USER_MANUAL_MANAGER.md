# A2Z MIS 360 — Manager User Manual

This manual is for branch managers, team leads, regional heads, unit
heads, and directors. It builds on the
[Staff User Manual](USER_MANUAL_STAFF.md) — read that first if you
haven't, since you'll also use the staff features for your own
performance tracking.

This document covers the **management** features: viewing your team,
cascading targets, approving requests, reviewing exceptions, and
authoring the BSC narrative.

## Your manager view

After login, your home page shows everything a staff member sees —
your own scorecard — plus a "My Team" section.

The **My Team** card shows:
- Direct reports count
- Average team score
- Pillar averages across the team
- Top performer + Bottom performer (anonymous if your team is small)
- Outstanding approvals waiting for you

## Team scorecard

Go to **Performance → Team Scorecard**.

This is your team's BSC roll-up. Columns:

| Column | Meaning |
|---|---|
| Staff | Direct report (clickable to drill down) |
| Role | Their position |
| Score | Their overall BSC score this period |
| Band | Did Not Meet → Exceeded By Far |
| Trend | Arrow vs prior period (▲ up, ▼ down, → flat) |
| Last Updated | When their actuals last refreshed |

### Sorting and filtering
- Click any column header to sort
- Use the **Pillar filter** to see "who's strong on Customer Focus?"
- Use the **Band filter** to find anyone "Did Not Meet" for a 1:1

### Drilling in
Click any staff name to open their detailed scorecard. From there:
- See per-KPI actuals
- View their pipeline, referrals, alerts
- Comment on a specific KPI (visible to that staff and your peer
  managers)
- Trigger an "asked for explanation" workflow — they get a notification
  and must respond within 48 h

## Cascading targets

Targets are set top-down. As a manager, you receive your aggregate
target from above and split it among direct reports.

Go to **Performance → Target Cascade**.

Steps:

1. **Confirm your aggregate target.** Shown at the top — set by your
   manager (or by the bank for top-of-house).
2. **Set per-KPI weights.** Each pillar has a weight; each KPI within
   the pillar has a weight; weights sum to 1.0.
3. **Distribute by direct report.** For each KPI, allocate a portion
   of the aggregate target to each report. The tool warns if the
   allocations don't sum to your aggregate.
4. **Apply.** This writes to `target_cascade.json` and triggers a
   per-staff scorecard recompute.

### Cascade rules

- **You can only cascade DOWN.** A branch manager can cascade to their
  branch staff but cannot adjust their own incoming target.
- **Allocations must reconcile.** Sum of allocations to direct reports
  for a KPI must equal your aggregate ± 1% (rounding allowance).
- **Locked targets** can't be re-cascaded mid-period. The HR cycle
  determines when targets unlock — typically twice a year.
- **Manual overrides are audit-logged.** Both the value and the
  override reason are recorded.

## Approvals

You'll see pending approvals on your home page and in the **My Tasks**
inbox. Common types:

### Purchase request approval

Go to **Operations → My Approvals → Purchase Requests**.

For each PR:
- Verify the business need
- Check the budget line is appropriate
- Verify amount within your delegated authority (DOA limit)
- Approve, Reject, or Send Back for revisions

If above your DOA, the PR escalates automatically. **Don't approve
above your DOA** — that's an audit finding.

### Loan application approval

Go to **Credit → My Approvals → Loan Applications**.

For each application:
- Review credit memo
- Check applicant DSR / KYC / risk rating
- Sanction, Decline, or Sanction with Conditions
- Add credit committee notes

The **PB credit decisioning TAT** KPI tracks how fast you turn these around.

### Onboarding / KYC update approval

Go to **CRM → My Approvals → Customer Updates**.

Review and approve KYC document refreshes, beneficial owner updates,
risk-rating changes proposed by frontline staff.

### Disciplinary case sign-off

Go to **HR → My Approvals → Disciplinary** (Branch Managers and above).

For each case:
- Review the underlying violation + evidence
- Confirm the proposed action (warning / suspension / termination
  recommendation)
- Sign off OR escalate to HR Director

## Exception management

Go to **Operations → Exceptions** for a unified view of:
- Late pipeline deals (no stage update in 14+ days) for your team
- AML alerts overdue for any staff under you
- Loan applications stuck > 5 days at any approval stage in your branch
- Customer complaints unresolved > 7 days

This is your daily walkthrough. Filter by staff or category and act.

The **Exception clearance %** KPI in your scorecard measures how fast
your team clears these.

## BSC narrative

End of period, you write the **BSC narrative** — a paragraph for each
pillar explaining performance. This is what the Board sees.

Go to **Performance → BSC Narrative → New (Period: <month>)**.

Template prompts:
- **Financial** — "What drove the deposit/loan growth this period?
  What's the outlook?"
- **Customer Focus** — "How did NPS / complaints / retention move?
  Any product feedback worth flagging?"
- **Operational Excellence** — "Were there outages, audit findings,
  process breaks? What's the remediation?"
- **People & Learning** — "Hires, exits, training completion, engagement
  pulse?"

Save as draft, refine, then **Submit for review**. Your manager
sees it next.

### Quality bar
Don't write fluff. The CEO reads the top-of-house narratives. Be
specific: numbers, not adjectives. "NPS increased from 42 to 51,
driven by faster pipeline conversion in Trade Finance" beats "we had
a great quarter on customer focus."

## Reviewing your team's narratives

Go to **Performance → Direct Report Narratives**.

For each:
- Read it
- Add comments inline
- Either Approve or Send Back (with comments)

Once approved, the narrative is locked and contributes to the bank's
roll-up.

## Reports for your team

Common reports you'll run:

| Report | Where | When |
|---|---|---|
| Branch Performance Summary | Performance → Reports → Branch | Weekly |
| Pipeline Funnel | Pipeline → Reports → Funnel | Weekly |
| AML Alert Aging | AML → Reports → Aging | Daily |
| Loan Book Quality | Credit → Reports → Quality | Monthly |
| Team Engagement Pulse | HR → Reports → Pulse | Quarterly |

All reports support CSV/Excel export. Use **Export → Excel** for
formatted reports; **Export → CSV** for raw data dumps you'll
massage in your own spreadsheet.

## Setting up new staff

(Branch Managers + above only)

Go to **Admin → Users → New User**.

Fields:
- Username (typically `firstname###`, e.g. `jane002`)
- Staff code (the HR-issued ID, e.g. `300042`)
- Full name
- Role (one of the configured roles)
- Initial password (set to `ECOStaff` + last 4 digits of staff code;
  user must change on first login)
- Branch / Unit
- Start date

After creation:
- The user receives an email with their initial credentials (if SMTP
  is configured)
- Their scorecard is auto-generated based on their role's KPI assignment
- They appear in your team list immediately

## Off-boarding

Go to **Admin → Users → <username> → Disable**.

Disabling:
- Immediately invalidates their JWT
- Prevents future logins
- Preserves their historical data (audit trail, scorecards, deals)
- Marks them as `disabled=true` — NOT deleted

If they had open work (pending approvals, active deals), reassign
first via **HR → Reassignment Wizard**. Then disable.

**Never delete a user account.** Audit trail integrity requires the
historical record. Disabled is the correct end state.

## Things only Directors and above do

- **Override BSC scores** — for genuine data issues. Always log a reason.
- **Adjust the bank-wide BSC weight scheme** — done at the start of
  the year, never mid-period.
- **Approve cross-unit reorganisations** — when a banker moves between
  branches mid-period.
- **Sign off on terminations** — disciplinary cases that escalate
  past Branch Manager require HR Director sign-off.

## Common questions

### "A staff member's scorecard hasn't refreshed in 3 days"

The nightly job runs at 02:00. If it failed:
1. Check the FLEXCUBE pipeline:
   `python scripts/test_flexcube_pipeline.py --mode=live`
2. If that exits non-zero, file a SEV-2 ticket — see [DR Runbook](DR_RUNBOOK.md).
3. If the pipeline is healthy, the issue may be specific to that staff's
   role configuration. Open Admin → Users → <user> → "Recompute
   scorecard now".

### "I want to credit a deal split across multiple bankers"

In the deal record, use the **Co-bankers** field. The split percentage
controls how the deal value distributes into each banker's "Deals Closed"
KPI.

### "A staff is gaming a KPI" (e.g. closing deals at end-of-period at
loss to inflate volume)

You see it in the data. Two responses:
1. **Coach in the moment.** Open the deal, reverse the close, comment
   on it.
2. **Adjust the targets.** If the KPI rewards the wrong behavior,
   request a target structure change for next period via HR.

### "How do I compare my team to another branch?"

Go to **Performance → Bench Reports → Inter-branch**. Shown anonymized
by default; named if you have Regional Head role or above.

## Where to get help

- [Staff User Manual](USER_MANUAL_STAFF.md) — what your team sees
- [Admin Guide](ADMIN_GUIDE.md) — for advanced operator tasks
- [Security Architecture](SECURITY_ARCHITECTURE.md) — RBAC model + audit
- Slack `#a2z-support`
- Email `a2z-help@<bank>`
